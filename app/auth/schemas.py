"""HTTP schemas for authentication endpoints."""

from pydantic import BaseModel, ConfigDict, Field


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    username: str = Field(min_length=1, max_length=120)
    password: str = Field(min_length=1, max_length=256)


class UnifiedLoginResponse(BaseModel):
    identity_type: str
    next_path: str


class ActiveOrganizationRequest(BaseModel):
    org_id: int = Field(gt=0)


class ActiveApplicationRequest(BaseModel):
    application_id: int = Field(gt=0)


class ActiveProjectRequest(BaseModel):
    project_id: int = Field(gt=0)


class OrganizationResponse(BaseModel):
    id: int
    org_code: str
    org_name: str
    is_primary: bool


class ApplicationContextResponse(BaseModel):
    id: int
    application_code: str
    application_name: str
    domain_type: str


class ProjectContextResponse(BaseModel):
    id: int
    application_id: int
    project_code: str
    project_name: str
    project_status: str


class MeResponse(BaseModel):
    user_id: int
    tenant_id: int
    tenant_code: str
    tenant_name: str
    username: str
    login_name: str
    display_name: str
    active_org_id: int
    active_application_id: int | None
    active_project_id: int | None
    organizations: list[OrganizationResponse]
    applications: list[ApplicationContextResponse]
    projects: list[ProjectContextResponse]
    role_codes: list[str]
    permission_codes: list[str]
