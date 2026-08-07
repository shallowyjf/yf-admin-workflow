"""Idempotent standard work-order workflow seed."""

from dataclasses import dataclass

from app.core.config import get_settings
from app.db.session import Database

from .models import WorkflowDefinition
from .repository import WorkflowRepository

WORK_ORDER_STANDARD_CODE = "WORK_ORDER_STANDARD"
WORK_ORDER_STANDARD_VERSION = 1
WORK_ORDER_STANDARD_DEFINITION = {
    "business_type": "WORK_ORDER",
    "initial_node": "DISPATCH",
    "nodes": [
        {"code": "DISPATCH", "type": "HUMAN_TASK"},
        {"code": "HANDLE", "type": "HUMAN_TASK"},
        {"code": "REVIEW", "type": "HUMAN_TASK"},
    ],
    "transitions": [
        {"from": "DISPATCH", "to": "HANDLE"},
        {"from": "HANDLE", "to": "REVIEW"},
        {"from": "REVIEW", "to": "END"},
    ],
}


@dataclass(frozen=True)
class WorkflowSeedSummary:
    definitions: int = 1


def seed_workflow(repository: WorkflowRepository) -> WorkflowSeedSummary:
    definition = repository.get_definition(
        WORK_ORDER_STANDARD_CODE,
        WORK_ORDER_STANDARD_VERSION,
    )
    if definition is None:
        repository.add(
            WorkflowDefinition(
                code=WORK_ORDER_STANDARD_CODE,
                name="标准工单流程",
                version=WORK_ORDER_STANDARD_VERSION,
                definition_json=WORK_ORDER_STANDARD_DEFINITION,
                is_active=True,
            )
        )
        repository.commit()
    elif not definition.is_active:
        definition.is_active = True
        repository.commit()
    return WorkflowSeedSummary()


def main() -> None:
    database = Database(get_settings().database_url)
    try:
        with database.session_factory() as session:
            summary = seed_workflow(WorkflowRepository(session))
        print(f"Workflow seed ready: {summary.definitions} definition")
    finally:
        database.dispose()


if __name__ == "__main__":
    main()
