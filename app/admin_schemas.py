from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import UserRole, UserStatus


class AdminAction(StrEnum):
    STATUS_CHANGED = "status_changed"
    ROLE_CHANGED = "role_changed"
    TEMPORARY_PASSWORD_RESET = "temporary_password_reset"
    SESSION_REVOKED = "session_revoked"
    ALL_SESSIONS_REVOKED = "all_sessions_revoked"


class AdminUserRead(BaseModel):
    id: UUID
    name: str
    email: str
    status: UserStatus
    role: UserRole
    must_change_password: bool
    created_at: datetime
    updated_at: datetime
    last_login_at: datetime | None

    account_count: int
    category_count: int
    transaction_count: int
    active_session_count: int

    is_current_admin: bool

    model_config = ConfigDict(from_attributes=True)


class AdminUserSummary(BaseModel):
    total: int
    pending: int
    active: int
    rejected: int
    suspended: int
    admins: int
    active_sessions: int


class AdminUserListRead(BaseModel):
    items: list[AdminUserRead]
    page: int
    page_size: int
    total: int
    total_pages: int
    summary: AdminUserSummary


class AdminStatusUpdate(BaseModel):
    status: UserStatus
    reason: str | None = Field(default=None, max_length=500)


class AdminRoleUpdate(BaseModel):
    role: UserRole
    reason: str | None = Field(default=None, max_length=500)


class TemporaryPasswordRead(BaseModel):
    user_id: UUID
    temporary_password: str
    must_change_password: bool
    sessions_revoked: int


class AdminSessionRead(BaseModel):
    id: UUID
    device_name: str | None
    created_at: datetime
    expires_at: datetime
    revoked_at: datetime | None
    is_active: bool


class AdminSessionListRead(BaseModel):
    items: list[AdminSessionRead]
    active_count: int


class AdminAuditRead(BaseModel):
    id: UUID
    admin_user_id: UUID
    admin_name: str
    target_user_id: UUID | None
    target_name: str | None
    action: AdminAction
    metadata: dict
    created_at: datetime


class AdminAuditListRead(BaseModel):
    items: list[AdminAuditRead]
    page: int
    page_size: int
    total: int
    total_pages: int


class AdminMessageRead(BaseModel):
    message: str
