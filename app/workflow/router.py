"""Authenticated workflow task query endpoints."""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.auth.router import get_request_context
from app.auth.service import RequestContext
from app.db.dependencies import get_db_session

from .factory import build_workflow_service
from .models import WorkflowTask
from .schemas import MyTaskResponse
from .service import WorkflowService

router = APIRouter(prefix="/api/tasks", tags=["workflow-tasks"])


def get_workflow_service(
    session: Annotated[Session, Depends(get_db_session)],
    context: Annotated[RequestContext, Depends(get_request_context)],
) -> WorkflowService:
    return build_workflow_service(session, context.tenant_id)


def _task_response(task: WorkflowTask, user_id: int) -> MyTaskResponse:
    candidate_user_ids = sorted(
        candidate.resolved_user_id for candidate in task.candidates
    )
    return MyTaskResponse(
        id=task.id,
        instance_id=task.instance_id,
        tenant_id=task.tenant_id,
        application_id=task.application_id,
        project_id=task.project_id,
        business_type=task.instance.business_type,
        business_id=task.instance.business_id,
        task_type=task.task_type,
        status=task.status,
        assignee_id=task.assignee_id,
        is_candidate=user_id in candidate_user_ids,
        candidate_user_ids=candidate_user_ids,
        created_at=task.created_at,
    )


@router.get("/mine", response_model=list[MyTaskResponse])
def list_my_tasks(
    context: Annotated[RequestContext, Depends(get_request_context)],
    service: Annotated[WorkflowService, Depends(get_workflow_service)],
) -> list[MyTaskResponse]:
    return [
        _task_response(task, context.current_user_id)
        for task in service.list_my_tasks(
            context.current_user_id, context.tenant_id,
            context.active_application_id, context.active_project_id,
        )
    ]
