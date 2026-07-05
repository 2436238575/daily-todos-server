"""Pydantic request and response schemas."""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=150)
    password: str = Field(min_length=1)
    device_name: str = Field(default="unknown", min_length=1, max_length=200)


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    server_version: int


class RefreshRequest(BaseModel):
    refresh_token: str = Field(min_length=1)


class LogoutRequest(BaseModel):
    refresh_token: str | None = None


class TaskRecord(BaseModel):
    id: str
    content: str
    target_date: date
    completed: bool = False
    sort_order: int = 0
    deleted: bool = False
    version: int
    updated_at: datetime


class TemplateItemRecord(BaseModel):
    id: str
    content: str
    sort_order: int = 0
    deleted: bool = False
    version: int
    updated_at: datetime


class TaskMutation(BaseModel):
    id: str
    base_version: int = Field(ge=0)
    content: str
    target_date: date
    completed: bool = False
    sort_order: int = 0
    deleted: bool = False


class TemplateItemMutation(BaseModel):
    id: str
    base_version: int = Field(ge=0)
    content: str
    sort_order: int = 0
    deleted: bool = False


class ConflictRecord(BaseModel):
    id: str
    entity_type: Literal["task", "template_item"]
    entity_id: str
    base_version: int
    server_version: int
    client_payload: dict
    server_payload: dict
    created_at: datetime


class PushRequest(BaseModel):
    tasks: list[TaskMutation] = Field(default_factory=list)
    template_items: list[TemplateItemMutation] = Field(default_factory=list)


class PushAccepted(BaseModel):
    entity_type: Literal["task", "template_item"]
    entity_id: str
    version: int


class PushResponse(BaseModel):
    server_version: int
    accepted: list[PushAccepted]
    conflicts: list[ConflictRecord]


class PullResponse(BaseModel):
    server_version: int
    tasks: list[TaskRecord]
    template_items: list[TemplateItemRecord]
    conflicts: list[ConflictRecord]


class ConflictResolution(BaseModel):
    conflict_id: str
    choice: Literal["local", "remote", "merged"]
    merged_payload: dict | None = None


class ResolveRequest(BaseModel):
    resolutions: list[ConflictResolution]


class ResolveResponse(BaseModel):
    server_version: int
    resolved: list[str]
    accepted: list[PushAccepted]
