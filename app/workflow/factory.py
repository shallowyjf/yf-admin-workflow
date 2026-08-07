"""Application composition for workflow services."""

from sqlalchemy.orm import Session

from app.iam.identity import IdentityQueryService
from app.iam.repository import IAMRepository

from .candidate import CandidateResolverRegistry
from .repository import WorkflowRepository
from .service import WorkflowService


def build_workflow_service(session: Session) -> WorkflowService:
    identity_queries = IdentityQueryService(IAMRepository(session))
    return WorkflowService(
        WorkflowRepository(session),
        CandidateResolverRegistry.default(identity_queries),
    )
