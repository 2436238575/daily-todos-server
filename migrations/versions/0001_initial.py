"""Initial DailyTodo server schema.

Revision ID: 0001_initial
Revises:
Create Date: 2026-07-05
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("username", sa.String(length=150), nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column("disabled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_users_username"), "users", ["username"], unique=True)

    op.create_table(
        "devices",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "name", name="uq_devices_user_name"),
    )
    op.create_index(op.f("ix_devices_user_id"), "devices", ["user_id"], unique=False)

    op.create_table(
        "refresh_tokens",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("device_id", sa.String(length=36), nullable=True),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["device_id"], ["devices.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_refresh_tokens_active", "refresh_tokens", ["user_id", "revoked_at", "expires_at"])
    op.create_index(op.f("ix_refresh_tokens_device_id"), "refresh_tokens", ["device_id"])
    op.create_index(op.f("ix_refresh_tokens_token_hash"), "refresh_tokens", ["token_hash"], unique=True)
    op.create_index(op.f("ix_refresh_tokens_user_id"), "refresh_tokens", ["user_id"])

    op.create_table(
        "tasks",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("target_date", sa.Date(), nullable=False),
        sa.Column("is_completed", sa.Boolean(), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_tasks_user_target_date", "tasks", ["user_id", "target_date", "sort_order"])
    op.create_index(op.f("ix_tasks_user_id"), "tasks", ["user_id"])

    op.create_table(
        "template_items",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_template_items_user_sort_order", "template_items", ["user_id", "sort_order"])
    op.create_index(op.f("ix_template_items_user_id"), "template_items", ["user_id"])

    op.create_table(
        "sync_events",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("entity_type", sa.String(length=40), nullable=False),
        sa.Column("entity_id", sa.String(length=36), nullable=False),
        sa.Column("action", sa.String(length=40), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_sync_events_user_id_id", "sync_events", ["user_id", "id"])
    op.create_index(op.f("ix_sync_events_user_id"), "sync_events", ["user_id"])

    op.create_table(
        "conflicts",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("entity_type", sa.String(length=40), nullable=False),
        sa.Column("entity_id", sa.String(length=36), nullable=False),
        sa.Column("base_version", sa.Integer(), nullable=False),
        sa.Column("server_version", sa.Integer(), nullable=False),
        sa.Column("client_payload", sa.JSON(), nullable=False),
        sa.Column("server_payload", sa.JSON(), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_conflicts_unresolved", "conflicts", ["user_id", "resolved_at"])
    op.create_index(op.f("ix_conflicts_user_id"), "conflicts", ["user_id"])


def downgrade() -> None:
    op.drop_table("conflicts")
    op.drop_table("sync_events")
    op.drop_table("template_items")
    op.drop_table("tasks")
    op.drop_table("refresh_tokens")
    op.drop_table("devices")
    op.drop_index(op.f("ix_users_username"), table_name="users")
    op.drop_table("users")
