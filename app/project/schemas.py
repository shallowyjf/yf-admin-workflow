"""API response schemas for the city lifeline permission structure."""

from datetime import date

from pydantic import BaseModel


class ProjectOrganizationResponse(BaseModel):
    org_code: str
    org_name: str
    party_type: str
    is_lead: bool


class ProjectMemberResponse(BaseModel):
    username: str
    display_name: str
    org_code: str
    org_name: str
    role_code: str
    role_name: str


class ProjectResponse(BaseModel):
    project_code: str
    project_name: str
    project_status: str
    start_date: date | None
    end_date: date | None
    organizations: list[ProjectOrganizationResponse]
    members: list[ProjectMemberResponse]


class ApplicationResponse(BaseModel):
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
