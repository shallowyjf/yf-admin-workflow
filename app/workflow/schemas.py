"""Workflow task HTTP schemas."""

from datetime import datetime

from pydantic import BaseModel


class MyTaskResponse(BaseModel):
    id: int
    instance_id: int
    tenant_id: int
    application_id: int
    project_id: int
    business_type: str
    business_id: int
    task_type: str
    status: str
    assignee_id: int | None
    is_candidate: bool
    candidate_user_ids: list[int]
    created_at: datetime
