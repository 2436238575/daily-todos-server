"""FastAPI routes for authentication and sync."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import models, schemas
from .security import create_access_token, decode_access_token, hash_refresh_token, verify_password
from .rate_limit import RateLimiter
from .services import (
    aware_now,
    create_refresh_token,
    current_server_version,
    get_or_create_device,
    record_sync_event,
)
from .settings import Settings

router = APIRouter()


def get_session(request: Request):
    session_factory = request.app.state.session_factory
    with session_factory() as session:
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise


def get_settings_from_app(request: Request) -> Settings:
    return request.app.state.settings


SessionDep = Annotated[Session, Depends(get_session)]
SettingsDep = Annotated[Settings, Depends(get_settings_from_app)]


def _require_user(
    session: SessionDep,
    settings: SettingsDep,
    authorization: Annotated[str | None, Header()] = None,
) -> models.User:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="missing bearer token")
    payload = decode_access_token(authorization[7:].strip(), settings.secret_key)
    if payload is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid bearer token")
    user = session.get(models.User, payload["sub"])
    if user is None or user.disabled_at is not None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="inactive user")
    return user


CurrentUserDep = Annotated[models.User, Depends(_require_user)]


def _token_response(
    session: Session,
    settings: Settings,
    user: models.User,
    refresh_token: str,
) -> schemas.TokenResponse:
    expires = timedelta(minutes=settings.access_token_minutes)
    return schemas.TokenResponse(
        access_token=create_access_token(user.id, settings.secret_key, expires),
        refresh_token=refresh_token,
        expires_in=int(expires.total_seconds()),
        server_version=current_server_version(session, user.id),
    )


@router.post("/v1/auth/login", response_model=schemas.TokenResponse)
def login(payload: schemas.LoginRequest, request: Request, session: SessionDep, settings: SettingsDep):
    _check_auth_rate_limit(request, settings, f"login:{payload.username}")
    user = session.scalar(select(models.User).where(models.User.username == payload.username))
    if user is None or user.disabled_at is not None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid username or password")
    device = get_or_create_device(session, user, payload.device_name)
    raw_refresh, _ = create_refresh_token(session, settings, user, device)
    return _token_response(session, settings, user, raw_refresh)


@router.post("/v1/auth/refresh", response_model=schemas.TokenResponse)
def refresh(payload: schemas.RefreshRequest, request: Request, session: SessionDep, settings: SettingsDep):
    _check_auth_rate_limit(request, settings, f"refresh:{hash_refresh_token(payload.refresh_token)}")
    token = session.scalar(
        select(models.RefreshToken).where(models.RefreshToken.token_hash == hash_refresh_token(payload.refresh_token))
    )
    now = aware_now()
    if token is None or token.revoked_at is not None or _is_expired(token.expires_at, now):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid refresh token")
    user = session.get(models.User, token.user_id)
    if user is None or user.disabled_at is not None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="inactive user")
    device = session.get(models.Device, token.device_id) if token.device_id else None
    if device is not None:
        device.last_seen_at = now
    token.revoked_at = now
    raw_refresh, _ = create_refresh_token(session, settings, user, device)
    return _token_response(session, settings, user, raw_refresh)


def _check_auth_rate_limit(request: Request | None, settings: Settings, bucket: str) -> None:
    if request is None:
        return
    limiter: RateLimiter | None = getattr(request.app.state, "auth_rate_limiter", None)
    if limiter is None:
        limiter = RateLimiter(settings.auth_rate_limit_requests, settings.auth_rate_limit_window_seconds)
        request.app.state.auth_rate_limiter = limiter
    client_host = request.client.host if request.client else "unknown"
    if not limiter.allow(f"{client_host}:{bucket}"):
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="too many authentication attempts")


def _is_expired(expires_at: datetime, now: datetime) -> bool:
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    return expires_at <= now


@router.post("/v1/auth/logout")
def logout(payload: schemas.LogoutRequest, session: SessionDep, current_user: CurrentUserDep):
    if payload.refresh_token:
        token = session.scalar(
            select(models.RefreshToken).where(
                models.RefreshToken.user_id == current_user.id,
                models.RefreshToken.token_hash == hash_refresh_token(payload.refresh_token),
            )
        )
        if token is not None and token.revoked_at is None:
            token.revoked_at = aware_now()
    return {"status": "ok"}


def _task_to_payload(task: models.Task) -> dict[str, Any]:
    return {
        "id": task.id,
        "content": task.content,
        "target_date": task.target_date.isoformat(),
        "completed": task.completed,
        "sort_order": task.sort_order,
        "deleted": task.deleted_at is not None,
        "version": task.version,
        "updated_at": task.updated_at.isoformat(),
    }


def _template_item_to_payload(item: models.TemplateItem) -> dict[str, Any]:
    return {
        "id": item.id,
        "content": item.content,
        "sort_order": item.sort_order,
        "deleted": item.deleted_at is not None,
        "version": item.version,
        "updated_at": item.updated_at.isoformat(),
    }


def _conflict_to_schema(conflict: models.Conflict) -> schemas.ConflictRecord:
    return schemas.ConflictRecord(
        id=conflict.id,
        entity_type=conflict.entity_type,
        entity_id=conflict.entity_id,
        base_version=conflict.base_version,
        server_version=conflict.server_version,
        client_payload=conflict.client_payload,
        server_payload=conflict.server_payload,
        created_at=conflict.created_at,
    )


def _task_input_to_payload(payload: schemas.TaskMutation | dict[str, Any]) -> dict[str, Any]:
    if isinstance(payload, schemas.TaskMutation):
        return payload.model_dump(mode="json")
    normalized = dict(payload)
    if isinstance(normalized.get("target_date"), date):
        normalized["target_date"] = normalized["target_date"].isoformat()
    return normalized


def _template_input_to_payload(payload: schemas.TemplateItemMutation | dict[str, Any]) -> dict[str, Any]:
    if isinstance(payload, schemas.TemplateItemMutation):
        return payload.model_dump(mode="json")
    return dict(payload)


def _touch_deleted(deleted: bool) -> datetime | None:
    return aware_now() if deleted else None


def _upsert_task(
    session: Session,
    user: models.User,
    payload: schemas.TaskMutation | dict[str, Any],
    force: bool = False,
) -> tuple[schemas.PushAccepted | None, models.Conflict | None]:
    raw = _task_input_to_payload(payload)
    existing = session.get(models.Task, raw["id"])
    if existing is not None and existing.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="task not found")
    base_version = int(raw.get("base_version", 0))
    if existing is not None and not force and existing.version != base_version:
        conflict = _create_conflict(
            session,
            user,
            "task",
            existing.id,
            base_version,
            existing.version,
            raw,
            _task_to_payload(existing),
        )
        return None, conflict

    if existing is None:
        task = models.Task(id=raw["id"], user_id=user.id, content=raw["content"], target_date=date.fromisoformat(raw["target_date"]))
        session.add(task)
    else:
        task = existing
    task.content = raw["content"]
    task.target_date = date.fromisoformat(raw["target_date"])
    task.completed = bool(raw.get("completed", False))
    task.sort_order = int(raw.get("sort_order", 0))
    task.deleted_at = _touch_deleted(bool(raw.get("deleted", False)))
    task.updated_at = aware_now()
    action = "delete" if task.deleted_at is not None else "upsert"
    version = record_sync_event(session, user.id, "task", task.id, action)
    task.version = version
    session.flush()
    return schemas.PushAccepted(entity_type="task", entity_id=task.id, version=version), None


def _upsert_template_item(
    session: Session,
    user: models.User,
    payload: schemas.TemplateItemMutation | dict[str, Any],
    force: bool = False,
) -> tuple[schemas.PushAccepted | None, models.Conflict | None]:
    raw = _template_input_to_payload(payload)
    existing = session.get(models.TemplateItem, raw["id"])
    if existing is not None and existing.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="template item not found")
    base_version = int(raw.get("base_version", 0))
    if existing is not None and not force and existing.version != base_version:
        conflict = _create_conflict(
            session,
            user,
            "template_item",
            existing.id,
            base_version,
            existing.version,
            raw,
            _template_item_to_payload(existing),
        )
        return None, conflict

    if existing is None:
        item = models.TemplateItem(id=raw["id"], user_id=user.id, content=raw["content"])
        session.add(item)
    else:
        item = existing
    item.content = raw["content"]
    item.sort_order = int(raw.get("sort_order", 0))
    item.deleted_at = _touch_deleted(bool(raw.get("deleted", False)))
    item.updated_at = aware_now()
    action = "delete" if item.deleted_at is not None else "upsert"
    version = record_sync_event(session, user.id, "template_item", item.id, action)
    item.version = version
    session.flush()
    return schemas.PushAccepted(entity_type="template_item", entity_id=item.id, version=version), None


def _create_conflict(
    session: Session,
    user: models.User,
    entity_type: str,
    entity_id: str,
    base_version: int,
    server_version: int,
    client_payload: dict[str, Any],
    server_payload: dict[str, Any],
) -> models.Conflict:
    conflict = models.Conflict(
        user_id=user.id,
        entity_type=entity_type,
        entity_id=entity_id,
        base_version=base_version,
        server_version=server_version,
        client_payload=client_payload,
        server_payload=server_payload,
    )
    session.add(conflict)
    session.flush()
    return conflict


@router.get("/v1/sync/pull", response_model=schemas.PullResponse)
def pull(since: int = 0, session: SessionDep = None, current_user: CurrentUserDep = None):
    if since < 0:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="since must be non-negative")
    events = session.scalars(
        select(models.SyncEvent).where(models.SyncEvent.user_id == current_user.id, models.SyncEvent.id > since)
    ).all()
    task_ids = [event.entity_id for event in events if event.entity_type == "task"]
    template_ids = [event.entity_id for event in events if event.entity_type == "template_item"]
    tasks = session.scalars(
        select(models.Task).where(models.Task.user_id == current_user.id, models.Task.id.in_(set(task_ids)))
    ).all() if task_ids else []
    template_items = session.scalars(
        select(models.TemplateItem).where(
            models.TemplateItem.user_id == current_user.id,
            models.TemplateItem.id.in_(set(template_ids)),
        )
    ).all() if template_ids else []
    conflicts = session.scalars(
        select(models.Conflict).where(models.Conflict.user_id == current_user.id, models.Conflict.resolved_at.is_(None))
    ).all()
    return schemas.PullResponse(
        server_version=current_server_version(session, current_user.id),
        tasks=[schemas.TaskRecord(**_task_to_payload(task)) for task in tasks],
        template_items=[schemas.TemplateItemRecord(**_template_item_to_payload(item)) for item in template_items],
        conflicts=[_conflict_to_schema(conflict) for conflict in conflicts],
    )


@router.post("/v1/sync/push", response_model=schemas.PushResponse)
def push(payload: schemas.PushRequest, session: SessionDep, current_user: CurrentUserDep):
    accepted: list[schemas.PushAccepted] = []
    conflicts: list[models.Conflict] = []
    for task_payload in payload.tasks:
        item, conflict = _upsert_task(session, current_user, task_payload)
        if item:
            accepted.append(item)
        if conflict:
            conflicts.append(conflict)
    for template_payload in payload.template_items:
        item, conflict = _upsert_template_item(session, current_user, template_payload)
        if item:
            accepted.append(item)
        if conflict:
            conflicts.append(conflict)
    return schemas.PushResponse(
        server_version=current_server_version(session, current_user.id),
        accepted=accepted,
        conflicts=[_conflict_to_schema(conflict) for conflict in conflicts],
    )


@router.post("/v1/sync/resolve", response_model=schemas.ResolveResponse)
def resolve(payload: schemas.ResolveRequest, session: SessionDep, current_user: CurrentUserDep):
    resolved: list[str] = []
    accepted: list[schemas.PushAccepted] = []
    for item in payload.resolutions:
        conflict = session.get(models.Conflict, item.conflict_id)
        if conflict is None or conflict.user_id != current_user.id or conflict.resolved_at is not None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="conflict not found")
        if item.choice == "remote":
            conflict.resolved_at = aware_now()
            resolved.append(conflict.id)
            continue
        if item.choice == "local":
            selected_payload = conflict.client_payload
        else:
            if item.merged_payload is None:
                raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="merged_payload required")
            selected_payload = item.merged_payload
        selected_payload = dict(selected_payload)
        selected_payload["id"] = conflict.entity_id
        selected_payload["base_version"] = conflict.server_version
        if conflict.entity_type == "task":
            applied, _ = _upsert_task(session, current_user, selected_payload, force=True)
        else:
            applied, _ = _upsert_template_item(session, current_user, selected_payload, force=True)
        if applied:
            accepted.append(applied)
        conflict.resolved_at = aware_now()
        resolved.append(conflict.id)
    session.flush()
    return schemas.ResolveResponse(
        server_version=current_server_version(session, current_user.id),
        resolved=resolved,
        accepted=accepted,
    )
