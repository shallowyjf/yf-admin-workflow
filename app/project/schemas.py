"""API response schemas for the city lifeline permission structure."""

from datetime import date

from pydantic import BaseModel, Field


class ProjectOrganizationResponse(BaseModel):
    id: int
    org_id: int
    org_code: str
    org_name: str
    party_type: str
    is_lead: bool


class ProjectMemberResponse(BaseModel):
    id: int
    user_org_id: int
    user_id: int
    username: str
    display_name: str
    org_code: str
    org_name: str
    role_code: str
    role_name: str


class ProjectResponse(BaseModel):
    id: int
    application_id: int
    project_code: str
    project_name: str
    project_status: str
    start_date: date | None
    end_date: date | None
    organizations: list[ProjectOrganizationResponse]
    members: list[ProjectMemberResponse]


class ApplicationResponse(BaseModel):
    id: int
    application_code: str
    application_name: str
    domain_type: str
    projects: list[ProjectResponse]


class RolePermissionResponse(BaseModel):
    permission_code: str
    permission_name: str
    scope_type: str | None


class RoleMatrixResponse(BaseModel):
    role_code: str
    role_name: str
    role_type: str | None
    permissions: list[RolePermissionResponse]


class LifelineStructureResponse(BaseModel):
    applications: list[ApplicationResponse]
    role_matrix: list[RoleMatrixResponse]
    can_view_all_projects: bool
    capabilities: dict[str, bool]


class CreateProjectRequest(BaseModel):
    application_id: int = Field(gt=0)
    project_code: str = Field(min_length=2, max_length=80)
    project_name: str = Field(min_length=1, max_length=200)
    start_date: date | None = None
    end_date: date | None = None


class UpdateProjectRequest(BaseModel):
    project_name: str = Field(min_length=1, max_length=200)
    project_status: str = Field(min_length=1, max_length=40)
    start_date: date | None = None
    end_date: date | None = None


class ProjectOrganizationConfigurationRequest(BaseModel):
    org_id: int = Field(gt=0)
    party_type: str = Field(min_length=1, max_length=40)
    is_lead: bool = False


class ReplaceProjectOrganizationsRequest(BaseModel):
    organizations: list[ProjectOrganizationConfigurationRequest] = Field(
        min_length=1
    )


class ProjectMemberConfigurationRequest(BaseModel):
    user_org_id: int = Field(gt=0)
    role_code: str = Field(min_length=1, max_length=80)


class ReplaceProjectMembersRequest(BaseModel):
    members: list[ProjectMemberConfigurationRequest] = Field(min_length=1)


class AuthorizationExplanationResponse(BaseModel):
    tenant_id: int
    application_id: int
    project_id: int
    subject_user_id: int
    permission_code: str
    checks: dict[str, bool]
    matching_role_codes: list[str]
    allowed: bool


class ReplaceUserApplicationsRequest(BaseModel):
    application_ids: list[int] = Field(default_factory=list)


class UserApplicationAccessResponse(BaseModel):
    id: int
    application_code: str
    application_name: str
