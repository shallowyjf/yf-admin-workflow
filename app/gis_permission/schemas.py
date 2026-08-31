"""API schemas for GIS queries and simulated exports."""

from datetime import datetime

from pydantic import BaseModel, Field


class GISFieldResponse(BaseModel):
    field_code: str
    field_name: str
    data_type: str
    sensitivity_level: str
    access_mode: str


class GISFeatureResponse(BaseModel):
    feature_key: str
    feature_name: str
    scope_type: str
    scope_value: str
    longitude: float | None
    latitude: float | None
    properties: dict


class GISQueryResponse(BaseModel):
    resource_id: int
    fields: list[GISFieldResponse]
    features: list[GISFeatureResponse]
    spatial_scopes: list[str]
    coordinate_precision: str


class GISExportRequest(BaseModel):
    field_codes: list[str] = Field(default_factory=list)
    export_format: str = Field(default="CSV", max_length=20)


class GISExportResponse(BaseModel):
    id: int
    resource_id: int
    resource_name: str
    export_format: str
    status: str
    row_count: int
    field_codes: list[str]
    spatial_scopes: list[str]
    file_name: str
    created_at: datetime


class CreateResourceFieldRequest(BaseModel):
    field_code: str = Field(min_length=1, max_length=80)
    field_name: str = Field(min_length=1, max_length=120)
    data_type: str = Field(min_length=1, max_length=40)
    sensitivity_level: str = Field(default="INTERNAL", max_length=20)
    mask_rule: str | None = Field(default=None, max_length=40)


class SetFieldPolicyRequest(BaseModel):
    role_code: str = Field(min_length=1, max_length=80)
    access_mode: str = Field(pattern="^(?i:VISIBLE|MASKED|HIDDEN)$")


class CreateSpatialScopeRequest(BaseModel):
    role_code: str = Field(min_length=1, max_length=80)
    scope_type: str = Field(min_length=1, max_length=40)
    scope_value: str = Field(min_length=1, max_length=120)
    coordinate_precision: str = Field(
        default="REGION_ONLY", pattern="^(?i:EXACT|GRID_100M|GRID_1KM|REGION_ONLY)$"
    )
