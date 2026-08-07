"""IAM organization administration HTTP schemas."""

from pydantic import BaseModel, Field


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
