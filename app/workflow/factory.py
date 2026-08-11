"""Application composition for workflow services."""

from sqlalchemy.orm import Session

from app.iam.authorization import PermissionService
from app.iam.identity import IdentityQueryService
from app.iam.repository import IAMRepository
from app.project.repository import ProjectRepository
from app.project.service import ProjectService

from .candidate import CandidateResolverRegistry
from .repository import WorkflowRepository
from .service import WorkflowService


def build_workflow_service(
    session: Session,
    tenant_id: int | None = None,
) -> WorkflowService:
    identity_queries = IdentityQueryService(IAMRepository(session, tenant_id))
    project_service = None
    if tenant_id is not None:
        project_service = ProjectService(
            ProjectRepository(session, tenant_id),
            PermissionService(IAMRepository(session, tenant_id)),
        )
    return WorkflowService(
        WorkflowRepository(session),
        CandidateResolverRegistry.default(identity_queries),
        candidate_filter=(
            project_service.filter_operational_candidates
            if project_service is not None else None
        ),
    )
