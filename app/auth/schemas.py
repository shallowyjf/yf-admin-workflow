"""HTTP schemas for authentication endpoints."""

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=1, max_length=256)


class ActiveOrganizationRequest(BaseModel):
    org_id: int = Field(gt=0)


class OrganizationResponse(BaseModel):
    id: int
    org_code: str
    org_name: str
    is_primary: bool


class MeResponse(BaseModel):
    user_id: int
    username: str
    display_name: str
    active_org_id: int
    organizations: list[OrganizationResponse]
    role_codes: list[str]
    permission_codes: list[str]
