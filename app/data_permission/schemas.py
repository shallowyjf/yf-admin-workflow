"""HTTP schemas for data authorization."""

from pydantic import BaseModel, Field


class DataResourceResponse(BaseModel):
    id: int
    data_space_id: int
    space_code: str
    space_name: str
    application_id: int
    application_code: str
    application_name: str
    project_id: int | None
    project_name: str | None
    owner_org_id: int
    owner_org_name: str
    resource_type: str
    resource_key: str
    resource_name: str
    derivation_stage: str
    sensitivity_level: str
    status: str


class DataSpaceResponse(BaseModel):
    id: int
    space_code: str
    space_name: str
    space_type: str
    domain_type: str | None
    application_id: int | None
    project_id: int | None
    owner_org_id: int
    sensitivity_level: str

    model_config = {"from_attributes": True}


class AuthorizationExplanationResponse(BaseModel):
    tenant_id: int
    resource_id: int
    resource_key: str
    application_id: int
    action_code: str
    checks: dict[str, bool]
    matching_role_codes: list[str]
    policy_effects: list[str]
    allowed: bool
    decision_reason: str


class GrantApplicationRoleRequest(BaseModel):
    user_org_id: int = Field(gt=0)
    role_code: str = Field(min_length=1, max_length=80)


class CreateDataSpaceRequest(BaseModel):
    space_code: str = Field(min_length=2, max_length=80)
    space_name: str = Field(min_length=1, max_length=160)
    space_type: str = Field(min_length=1, max_length=40)
    domain_type: str | None = Field(default=None, max_length=40)
    application_id: int | None = Field(default=None, gt=0)
    project_id: int | None = Field(default=None, gt=0)
    owner_org_id: int = Field(gt=0)
    sensitivity_level: str = Field(default="INTERNAL", max_length=20)


class CreateDataResourceRequest(BaseModel):
    data_space_id: int = Field(gt=0)
    application_id: int = Field(gt=0)
    project_id: int | None = Field(default=None, gt=0)
    owner_org_id: int = Field(gt=0)
    resource_type: str = Field(min_length=1, max_length=40)
    resource_key: str = Field(min_length=2, max_length=120)
    resource_name: str = Field(min_length=1, max_length=200)
    derivation_stage: str = Field(min_length=1, max_length=40)
    sensitivity_level: str = Field(default="INTERNAL", max_length=20)


class CreateResourcePolicyRequest(BaseModel):
    role_code: str = Field(min_length=1, max_length=80)
    action_code: str = Field(min_length=1, max_length=120)
    effect: str = Field(pattern="^(?i:ALLOW|DENY)$")
