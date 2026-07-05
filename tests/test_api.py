from __future__ import annotations

import uuid

from dailytodo_server import api
from dailytodo_server.db import Base, create_session_factory
from dailytodo_server.models import User
from dailytodo_server.security import decode_access_token
from dailytodo_server.services import create_user
from dailytodo_server.settings import Settings


def make_state(tmp_path):
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'daily-todos-test.db'}",
        secret_key="test-secret-key-12345",
        access_token_minutes=5,
        refresh_token_days=7,
    )
    session_factory = create_session_factory(settings)
    Base.metadata.create_all(session_factory.kw["bind"])
    with session_factory() as session:
        create_user(session, "alice", "correct-password")
        session.commit()
    return settings, session_factory


def login(session, settings, device_name: str = "pytest"):
    response = api.login(
        payload=api.schemas.LoginRequest(
            username="alice",
            password="correct-password",
            device_name=device_name,
        ),
        request=None,
        session=session,
        settings=settings,
    )
    payload = decode_access_token(response.access_token, settings.secret_key)
    assert payload is not None
    user = session.get(User, payload["sub"])
    assert user is not None
    return response, user


def test_auth_refresh_and_logout(tmp_path):
    settings, session_factory = make_state(tmp_path)
    with session_factory() as session:
        tokens, user = login(session, settings)

        refreshed = api.refresh(
            payload=api.schemas.RefreshRequest(refresh_token=tokens.refresh_token),
            request=None,
            session=session,
            settings=settings,
        )
        assert refreshed.refresh_token != tokens.refresh_token

        try:
            api.refresh(
                payload=api.schemas.RefreshRequest(refresh_token=tokens.refresh_token),
                request=None,
                session=session,
                settings=settings,
            )
        except api.HTTPException as exc:
            assert exc.status_code == 401
        else:
            raise AssertionError("old refresh token should be revoked")

        assert api.logout(api.schemas.LogoutRequest(refresh_token=refreshed.refresh_token), session, user) == {
            "status": "ok"
        }

        try:
            api.refresh(
                payload=api.schemas.RefreshRequest(refresh_token=refreshed.refresh_token),
                request=None,
                session=session,
                settings=settings,
            )
        except api.HTTPException as exc:
            assert exc.status_code == 401
        else:
            raise AssertionError("logout should revoke the refresh token")


def test_task_push_pull_conflict_and_resolution(tmp_path):
    settings, session_factory = make_state(tmp_path)
    with session_factory() as session:
        tokens, user = login(session, settings, "desktop")
        task_id = str(uuid.uuid4())

        created = api.push(
            api.schemas.PushRequest(
                tasks=[
                    api.schemas.TaskMutation(
                        id=task_id,
                        base_version=0,
                        content="buy milk",
                        target_date="2026-07-05",
                        completed=False,
                        sort_order=10,
                    )
                ]
            ),
            session,
            user,
        )
        version_1 = created.accepted[0].version
        assert version_1 == 1

        updated = api.push(
            api.schemas.PushRequest(
                tasks=[
                    api.schemas.TaskMutation(
                        id=task_id,
                        base_version=version_1,
                        content="buy oat milk",
                        target_date="2026-07-05",
                        completed=False,
                        sort_order=10,
                    )
                ]
            ),
            session,
            user,
        )
        version_2 = updated.accepted[0].version

        stale = api.push(
            api.schemas.PushRequest(
                tasks=[
                    api.schemas.TaskMutation(
                        id=task_id,
                        base_version=version_1,
                        content="buy soy milk",
                        target_date="2026-07-05",
                        completed=False,
                        sort_order=10,
                    )
                ]
            ),
            session,
            user,
        )
        assert stale.accepted == []
        assert stale.conflicts[0].server_version == version_2
        assert stale.conflicts[0].server_payload["content"] == "buy oat milk"

        pulled = api.pull(since=version_1, session=session, current_user=user)
        assert pulled.tasks[0].content == "buy oat milk"
        assert pulled.conflicts[0].client_payload["content"] == "buy soy milk"

        resolved = api.resolve(
            api.schemas.ResolveRequest(
                resolutions=[api.schemas.ConflictResolution(conflict_id=stale.conflicts[0].id, choice="local")]
            ),
            session,
            user,
        )
        version_3 = resolved.accepted[0].version
        assert version_3 > version_2

        final_pull = api.pull(since=version_2, session=session, current_user=user)
        assert final_pull.tasks[0].content == "buy soy milk"
        assert final_pull.conflicts == []
        assert tokens.server_version == 0


def test_template_item_sync(tmp_path):
    settings, session_factory = make_state(tmp_path)
    with session_factory() as session:
        _, user = login(session, settings, "mobile")
        item_id = str(uuid.uuid4())

        response = api.push(
            api.schemas.PushRequest(
                template_items=[
                    api.schemas.TemplateItemMutation(
                        id=item_id,
                        base_version=0,
                        content="standup note",
                        sort_order=1,
                    )
                ]
            ),
            session,
            user,
        )
        version = response.accepted[0].version

        pulled = api.pull(since=0, session=session, current_user=user)
        assert pulled.server_version == version
        assert len(pulled.template_items) == 1
        assert pulled.template_items[0].id == item_id
        assert pulled.template_items[0].content == "standup note"
        assert pulled.template_items[0].sort_order == 1
        assert pulled.template_items[0].deleted is False
        assert pulled.template_items[0].version == version
