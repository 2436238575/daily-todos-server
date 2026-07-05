"""Application service functions shared by API and CLI code."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from . import models
from .security import hash_password, hash_refresh_token, new_refresh_token
from .settings import Settings


def aware_now() -> datetime:
    return datetime.now(UTC)


def create_user(session: Session, username: str, password: str) -> models.User:
    existing = session.scalar(select(models.User).where(models.User.username == username))
    if existing is not None:
        raise ValueError(f"user already exists: {username}")
    user = models.User(username=username, password_hash=hash_password(password))
    session.add(user)
    session.flush()
    return user


def set_user_disabled(session: Session, username: str, disabled: bool) -> models.User:
    user = session.scalar(select(models.User).where(models.User.username == username))
    if user is None:
        raise LookupError(f"user not found: {username}")
    user.disabled_at = aware_now() if disabled else None
    session.flush()
    return user


def current_server_version(session: Session, user_id: str) -> int:
    return session.scalar(
        select(func.coalesce(func.max(models.SyncEvent.id), 0)).where(models.SyncEvent.user_id == user_id)
    )


def get_or_create_device(session: Session, user: models.User, name: str) -> models.Device:
    device = session.scalar(
        select(models.Device).where(models.Device.user_id == user.id, models.Device.name == name)
    )
    if device is None:
        device = models.Device(user_id=user.id, name=name)
        session.add(device)
    device.last_seen_at = aware_now()
    session.flush()
    return device


def create_refresh_token(
    session: Session,
    settings: Settings,
    user: models.User,
    device: models.Device | None,
) -> tuple[str, models.RefreshToken]:
    raw = new_refresh_token()
    token = models.RefreshToken(
        user_id=user.id,
        device_id=device.id if device else None,
        token_hash=hash_refresh_token(raw),
        expires_at=aware_now() + timedelta(days=settings.refresh_token_days),
    )
    session.add(token)
    session.flush()
    return raw, token


def record_sync_event(
    session: Session,
    user_id: str,
    entity_type: str,
    entity_id: str,
    action: str,
) -> int:
    event = models.SyncEvent(user_id=user_id, entity_type=entity_type, entity_id=entity_id, action=action)
    session.add(event)
    session.flush()
    return event.id
