"""Empty-database V0.1 release acceptance for IAM configuration and DMA flow."""

from __future__ import annotations

import json
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect

from app.auth.repository import AuthRepository
from app.auth.service import AuthSessionRevocationService
from app.db.session import Database
from app.demo.dma_workflow_demo import run_dma_demo
from app.iam.admin_service import IAMAdministrationActor
from app.iam.authorization import DataScopeType, PermissionService
from app.iam.dictionary_admin_service import (
    CreatePermissionCommand,
    CreatePositionCommand,
    PermissionDictionaryService,
    PositionAdministrationService,
)
from app.iam.repository import IAMRepository
from app.iam.role_admin_service import (
    CreateRoleCommand,
    PermissionScopeConfiguration,
    RoleAdministrationService,
)
from app.iam.seed import seed_iam
from app.iam.service import IAMService
from app.iam.user_admin_service import (
    CreateUserCommand,
    MembershipConfiguration,
    UserAdministrationService,
)
from app.workflow.repository import WorkflowRepository
from app.workflow.seed import seed_workflow
from app.workorder.repository import WorkOrderRepository
from app.workorder.seed import seed_workorder

REPO_ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class ReleaseSmokeResult:
    migration_revision: str
    table_count: int
    configured_username: str
    configured_permission: str
    authorization_effective: bool
    audited_entities: tuple[str, ...]
    dma_final_status: str
    dma_timeline: tuple[str, ...]


def _upgrade_to_head(database_url: str) -> None:
    config = Config(str(REPO_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(REPO_ROOT / "migrations"))
    config.set_main_option("sqlalchemy.url", database_url)
    command.upgrade(config, "head")


def run_release_smoke(database_url: str) -> ReleaseSmokeResult:
    """Build an empty database and verify configuration affects authorization."""

    _upgrade_to_head(database_url)
    database = Database(database_url)
    try:
        with database.session_factory() as session:
            repository = IAMRepository(session)
            iam_service = IAMService(repository)
            seed_iam(iam_service)
            workflow_repository = WorkflowRepository(session)
            seed_workflow(workflow_repository)
            seed_workorder(WorkOrderRepository(session))

            admin = repository.get_user_by_username("admin")
            group = repository.get_organization_by_code("GROUP")
            if admin is None or group is None:
                raise RuntimeError("IAM seed did not create the administrator context")
            actor = IAMAdministrationActor(admin.id, group.id)
            permission_service = PermissionService(repository)

            position = PositionAdministrationService(
                repository,
                permission_service,
                workflow_repository,
            ).create(
                CreatePositionCommand("V01_ACCEPTANCE", "V0.1 验收岗"),
                actor,
            )
            permission = PermissionDictionaryService(
                repository,
                permission_service,
            ).create(
                CreatePermissionCommand(
                    "acceptance:view",
                    "查看发布验收资源",
                    "RELEASE_ACCEPTANCE",
                    "I15 empty-database release smoke permission",
                ),
                actor,
            )
            role_service = RoleAdministrationService(repository, permission_service)
            role = role_service.create(
                CreateRoleCommand("V01_ACCEPTANCE", "V0.1 验收角色", "ACCEPTANCE"),
                actor,
            )
            role_service.replace_authorization(
                role.id,
                (
                    PermissionScopeConfiguration(
                        permission.permission_code,
                        DataScopeType.ORG,
                    ),
                ),
                actor,
            )

            user_service = UserAdministrationService(
                repository,
                permission_service,
                AuthSessionRevocationService(AuthRepository(session)),
            )
            user = user_service.create(
                CreateUserCommand(
                    "release.smoke",
                    "发布验收用户",
                    "Release@123",
                ),
                actor,
            )
            user = user_service.replace_memberships(
                user.id,
                (
                    MembershipConfiguration(
                        org_code="PIPE_OPERATION",
                        is_primary=True,
                        role_codes=(role.role_code,),
                        position_codes=(position.position_code,),
                    ),
                ),
                actor,
            )
            pipe_org = repository.get_organization_by_code("PIPE_OPERATION")
            if pipe_org is None:
                raise RuntimeError("IAM seed did not create PIPE_OPERATION")
            authorization_effective = permission_service.has_permission(
                user.id,
                permission.permission_code,
                pipe_org.id,
            )
            audited_entities = tuple(
                sorted(
                    {
                        log.entity_type
                        for log in repository.list_iam_audit_logs_filtered(limit=100)
                    }
                )
            )

            dma = run_dma_demo(session)
            table_names = inspect(database.engine).get_table_names()

        return ReleaseSmokeResult(
            migration_revision="head",
            table_count=len(table_names),
            configured_username=user.username,
            configured_permission=permission.permission_code,
            authorization_effective=authorization_effective,
            audited_entities=audited_entities,
            dma_final_status=dma.final_status,
            dma_timeline=dma.timeline_actions,
        )
    finally:
        database.dispose()


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="yf-v01-release-") as temp_directory:
        database_path = Path(temp_directory) / "release.db"
        result = run_release_smoke(f"sqlite:///{database_path.as_posix()}")
    print(json.dumps(asdict(result), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
