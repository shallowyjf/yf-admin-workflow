"""Operational API schemas."""

from datetime import datetime

from pydantic import BaseModel, Field


class SaveViewRequest(BaseModel):
    module: str = Field(min_length=1, max_length=40)
    name: str = Field(min_length=1, max_length=80)
    filters: dict = Field(default_factory=dict)
    is_default: bool = False


class SavedViewResponse(BaseModel):
    id: int
    module: str
    name: str
    filters_json: dict
    is_default: bool
    created_at: datetime
    updated_at: datetime
