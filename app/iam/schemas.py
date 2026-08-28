"""IAM organization administration HTTP schemas."""

from datetime import datetime

from pydantic import BaseModel, Field

from .authorization import DataScopeType


class CreateOrganizationRequest(BaseModel):
    org_code: str = Field(min_length=2, max_length=80)
    org_name: str = Field(min_length=1, max_length=160)
    org_type: str | None = Field(default=None, max_length=40)
    parent_code: str | None = Field(default=None, max_length=80)
    sort_no: int = 0


class UpdateOrganizationRequest(BaseModel):
    org_name: str = Field(min_length=1, max_length=160)
    org_type: str | None = Field(default=None, max_length=40)
    parent_code: str | None = Field(default=None, max_length=80)
    sort_no: int = 0


class OrganizationStatusRequest(BaseModel):
    is_active: bool


class OrganizationResponse(BaseModel):
    id: int
    parent_id: int | None
    org_code: str
    org_name: str
    org_type: str | None
    org_path: str
    sort_no: int
    is_active: bool


class OrganizationTreeResponse(OrganizationResponse):
    children: list["OrganizationTreeResponse"] = Field(default_factory=list)


class CreateUserRequest(BaseModel):
    username: str = Field(min_length=3, max_length=80)
    login_name: str | None = Field(default=None, min_length=3, max_length=120)
    display_name: str = Field(min_length=1, max_length=120)
    password: str = Field(min_length=8, max_length=128)
    phone: str | None = Field(default=None, max_length=40)


class UpdateUserRequest(BaseModel):
    display_name: str = Field(min_length=1, max_length=120)
    phone: str | None = Field(default=None, max_length=40)


class UserStatusRequest(BaseModel):
    is_active: bool


class ResetUserPasswordRequest(BaseModel):
    new_password: str = Field(min_length=8, max_length=128)


class MembershipConfigurationRequest(BaseModel):
    org_code: str = Field(min_length=1, max_length=80)
    is_primary: bool = False
    is_active: bool = True
    role_codes: list[str] = Field(default_factory=list)
    position_codes: list[str] = Field(default_factory=list)


class ReplaceUserMembershipsRequest(BaseModel):
    memberships: list[MembershipConfigurationRequest] = Field(min_length=1)


class UserMembershipResponse(BaseModel):
    id: int
    org_id: int
    org_code: str
    org_name: str
    is_primary: bool
    is_active: bool
    role_codes: list[str]
    position_codes: list[str]


class UserResponse(BaseModel):
    id: int
    username: str
    login_name: str
    display_name: str
    phone: str | None
    is_active: bool
    memberships: list[UserMembershipResponse]


class CreateRoleRequest(BaseModel):
    role_code: str = Field(min_length=2, max_length=80)
    role_name: str = Field(min_length=1, max_length=120)
    role_type: str | None = Field(default=None, max_length=40)


class UpdateRoleRequest(BaseModel):
    role_name: str = Field(min_length=1, max_length=120)
    role_type: str | None = Field(default=None, max_length=40)


class RoleStatusRequest(BaseModel):
    is_active: bool


class PermissionScopeConfigurationRequest(BaseModel):
    permission_code: str = Field(min_length=1, max_length=120)
    scope_type: DataScopeType
    custom_org_codes: list[str] = Field(default_factory=list)


class ReplaceRoleAuthorizationRequest(BaseModel):
    permissions: list[PermissionScopeConfigurationRequest] = Field(
        default_factory=list
    )


class RolePermissionScopeResponse(BaseModel):
    permission_code: str
    permission_name: str
    scope_type: DataScopeType
    custom_org_codes: list[str]


class RoleResponse(BaseModel):
    id: int
    role_code: str
    role_name: str
    role_type: str | None
    is_active: bool
    authorization: list[RolePermissionScopeResponse]


class CreatePositionRequest(BaseModel):
    position_code: str = Field(min_length=2, max_length=80)
    position_name: str = Field(min_length=1, max_length=120)


class UpdatePositionRequest(BaseModel):
    position_name: str = Field(min_length=1, max_length=120)


class PositionStatusRequest(BaseModel):
    is_active: bool


class PositionResponse(BaseModel):
    id: int
    position_code: str
    position_name: str
    is_active: bool
    membership_count: int


class CreatePermissionRequest(BaseModel):
    permission_code: str = Field(min_length=3, max_length=120)
    permission_name: str = Field(min_length=1, max_length=160)
    resource_type: str | None = Field(default=None, max_length=40)
    description: str | None = Field(default=None, max_length=1000)


class UpdatePermissionRequest(BaseModel):
    permission_name: str = Field(min_length=1, max_length=160)
    resource_type: str | None = Field(default=None, max_length=40)
    description: str | None = Field(default=None, max_length=1000)


class PermissionResponse(BaseModel):
    id: int
    permission_code: str
    permission_name: str
    resource_type: str | None
    description: str | None
    role_count: int


class IAMAuditLogResponse(BaseModel):
    id: int
    entity_type: str
    entity_id: int
    action: str
    operator_id: int | None
    operator_username: str | None
    operator_display_name: str | None
    payload: dict | None
    created_at: datetime
