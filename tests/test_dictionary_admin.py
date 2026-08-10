from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.base import Base
from app.iam.admin_service import (
    IAMAdministrationActor,
    IAMAdministrationConflict,
    IAMAdministrationPermissionDenied,
)
from app.iam.authorization import DataScopeType, PermissionService
from app.iam.dictionary_admin_service import (
    CreatePermissionCommand,
    CreatePositionCommand,
    IAMAuditFilter,
    IAMAuditQueryService,
    PermissionDictionaryService,
    PositionAdministrationService,
    UpdatePermissionCommand,
    UpdatePositionCommand,
)
from app.iam.identity import IdentityQueryService
from app.iam.repository import IAMRepository
from app.iam.role_admin_service import (
    CreateRoleCommand,
    PermissionScopeConfiguration,
    RoleAdministrationService,
)
from app.iam.seed import DEMO_INITIAL_PASSWORD, seed_iam
from app.iam.service import IAMService
from app.main import create_app
from app.workflow.models import WorkflowDefinition
from app.workflow.repository import WorkflowRepository


def _services(
    session: Session,
) -> tuple[
    PositionAdministrationService,
    PermissionDictionaryService,
    IAMAuditQueryService,
    RoleAdministrationService,
    IAMAdministrationActor,
    IAMRepository,
]:
    repository = IAMRepository(session)
    iam_service = IAMService(repository)
    seed_iam(iam_service)
    admin = iam_service.get_user("admin")
    group = iam_service.get_organization("GROUP")
    assert admin is not None and group is not None
    permissions = PermissionService(repository)
    actor = IAMAdministrationActor(admin.id, group.id)
    return (
        PositionAdministrationService(
            repository,
            permissions,
            WorkflowRepository(session),
        ),
        PermissionDictionaryService(repository, permissions),
        IAMAuditQueryService(repository, permissions),
        RoleAdministrationService(repository, permissions),
        actor,
        repository,
    )


def test_position_lifecycle_candidate_effect_and_audit(db_session: Session) -> None:
    positions, _, audits, _, actor, repository = _services(db_session)
    position = positions.create(
        CreatePositionCommand("FIELD_SUPERVISOR", "现场主管"),
        actor,
    )
    position = positions.update(
        position.id,
        UpdatePositionCommand("现场值守主管"),
        actor,
    )
    assert position.position_code == "FIELD_SUPERVISOR"
    positions.set_active(position.id, False, actor)
    positions.delete(position.id, actor)
    assert repository.get_position(position.id) is None
    logs = audits.list_logs(
        IAMAuditFilter(entity_type="position", entity_id=position.id),
        actor,
    )
    assert [log.action for log in reversed(logs)] == [
        "CREATE",
        "UPDATE",
        "DISABLE",
        "DELETE",
    ]

    repairer_position = repository.get_position_by_code("REPAIRER")
    lisi = repository.get_user_by_username("lisi")
    pipe = repository.get_organization_by_code("PIPE_OPERATION")
    assert repairer_position is not None and lisi is not None and pipe is not None
    identity = IdentityQueryService(repository)
    assert lisi.id in identity.users_by_position("REPAIRER", pipe.id)
    positions.set_active(repairer_position.id, False, actor)
    assert lisi.id not in identity.users_by_position("REPAIRER", pipe.id)
    positions.set_active(repairer_position.id, True, actor)


def test_position_delete_protects_memberships_and_workflow_json(
    db_session: Session,
) -> None:
    positions, _, _, _, actor, repository = _services(db_session)
    repairer = repository.get_position_by_code("REPAIRER")
    assert repairer is not None
    with pytest.raises(IAMAdministrationConflict, match="用户组织关系"):
        positions.delete(repairer.id, actor)

    workflow_position = positions.create(
        CreatePositionCommand("FLOW_REVIEWER", "流程复核岗位"),
        actor,
    )
    workflow_repository = WorkflowRepository(db_session)
    workflow_repository.add(
        WorkflowDefinition(
            code="POSITION_REFERENCE",
            name="岗位引用测试",
            version=1,
            definition_json={
                "candidate_rule": {
                    "candidate_type": "ORG_POSITION",
                    "position_code": "FLOW_REVIEWER",
                }
            },
            is_active=True,
        )
    )
    workflow_repository.commit()
    with pytest.raises(IAMAdministrationConflict, match="流程候选规则"):
        positions.delete(workflow_position.id, actor)


def test_permission_lifecycle_reference_cleanup_and_builtin_protection(
    db_session: Session,
) -> None:
    _, permissions, audits, roles, actor, repository = _services(db_session)
    permission = permissions.create(
        CreatePermissionCommand(
            "asset:view",
            "查看资产",
            "ASSET",
            "资产台账查询",
        ),
        actor,
    )
    permission = permissions.update(
        permission.id,
        UpdatePermissionCommand(
            "查看资产档案",
            "ASSET",
            "资产台账和档案查询",
        ),
        actor,
    )
    assert permission.permission_code == "asset:view"
    role = roles.create(CreateRoleCommand("ASSET_VIEWER", "资产查看员"), actor)
    roles.replace_authorization(
        role.id,
        (
            PermissionScopeConfiguration(
                "asset:view",
                DataScopeType.ORG,
            ),
        ),
        actor,
    )
    with pytest.raises(IAMAdministrationConflict, match="角色授权"):
        permissions.delete(permission.id, actor)
    roles.replace_authorization(role.id, (), actor)
    assert repository.get_role_data_scope(role.id, "asset:view") is None
    permissions.delete(permission.id, actor)
    assert repository.get_permission(permission.id) is None

    builtin = repository.get_permission_by_code("workorder:view")
    assert builtin is not None
    with pytest.raises(IAMAdministrationConflict, match="内置稳定权限"):
        permissions.delete(builtin.id, actor)
    logs = audits.list_logs(
        IAMAuditFilter(
            entity_type="PERMISSION",
            entity_id=permission.id,
            operator_username="ADMIN",
        ),
        actor,
    )
    assert [log.action for log in reversed(logs)] == ["CREATE", "UPDATE", "DELETE"]
    assert all(log.operator is not None for log in logs)


def test_business_user_receives_only_explicitly_granted_iam_capability(
    db_session: Session,
) -> None:
    positions, permissions, audits, roles, admin_actor, repository = _services(
        db_session
    )
    lisi = repository.get_user_by_username("lisi")
    pipe = repository.get_organization_by_code("PIPE_OPERATION")
    assert lisi is not None and pipe is not None
    actor = IAMAdministrationActor(lisi.id, pipe.id)
    with pytest.raises(IAMAdministrationPermissionDenied):
        positions.list_positions(actor)
    with pytest.raises(IAMAdministrationPermissionDenied):
        permissions.list_permissions(actor)
    with pytest.raises(IAMAdministrationPermissionDenied):
        audits.list_logs(IAMAuditFilter(), actor)

    audit_role = roles.create(
        CreateRoleCommand("IAM_AUDITOR", "IAM 审计员"),
        admin_actor,
    )
    roles.replace_authorization(
        audit_role.id,
        (
            PermissionScopeConfiguration(
                "system:audit:view",
                DataScopeType.ORG,
            ),
        ),
        admin_actor,
    )
    IAMService(repository).assign_role("lisi", "PIPE_OPERATION", "IAM_AUDITOR")
    assert audits.list_logs(IAMAuditFilter(), actor)
    with pytest.raises(IAMAdministrationPermissionDenied):
        positions.list_positions(actor)
    with pytest.raises(IAMAdministrationPermissionDenied):
        permissions.list_permissions(actor)


@pytest.fixture()
def dictionary_client(tmp_path) -> Iterator[TestClient]:
    database_path = tmp_path / "dictionary-api.sqlite3"
    settings = Settings(
        app_name="I14 字典管理回归",
        environment="test",
        database_url=f"sqlite:///{database_path.as_posix()}",
    )
    application = create_app(settings)
    with TestClient(application) as client:
        database = application.state.database
        Base.metadata.create_all(database.engine)
        with database.session_factory() as session:
            seed_iam(IAMService(IAMRepository(session)))
        yield client


def _login(client: TestClient, username: str) -> None:
    response = client.post(
        "/auth/login",
        json={"username": username, "password": DEMO_INITIAL_PASSWORD},
    )
    assert response.status_code == 200


def test_dictionary_and_audit_api_lifecycle(dictionary_client: TestClient) -> None:
    _login(dictionary_client, "admin")
    position = dictionary_client.post(
        "/api/positions",
        json={"position_code": "API_POSITION", "position_name": "API 岗位"},
    )
    assert position.status_code == 201
    position_id = position.json()["id"]
    assert dictionary_client.put(
        f"/api/positions/{position_id}",
        json={"position_name": "API 岗位（更新）"},
    ).status_code == 200
    assert dictionary_client.post(
        f"/api/positions/{position_id}/status",
        json={"is_active": False},
    ).status_code == 200
    assert dictionary_client.delete(
        f"/api/positions/{position_id}"
    ).status_code == 204

    permission = dictionary_client.post(
        "/api/permissions",
        json={
            "permission_code": "api:export",
            "permission_name": "API 导出",
            "resource_type": "API",
            "description": "导出接口数据",
        },
    )
    assert permission.status_code == 201
    permission_id = permission.json()["id"]
    assert dictionary_client.put(
        f"/api/permissions/{permission_id}",
        json={
            "permission_name": "API 数据导出",
            "resource_type": "API",
            "description": "导出接口数据和日志",
        },
    ).status_code == 200
    logs = dictionary_client.get(
        "/api/iam/audit-logs",
        params={
            "entity_type": "permission",
            "entity_id": permission_id,
            "operator_username": "admin",
        },
    )
    assert logs.status_code == 200
    assert [item["action"] for item in reversed(logs.json())] == [
        "CREATE",
        "UPDATE",
    ]
    assert all(item["operator_username"] == "admin" for item in logs.json())
    assert dictionary_client.delete(
        f"/api/permissions/{permission_id}"
    ).status_code == 204

    builtin = next(
        item
        for item in dictionary_client.get("/api/permissions").json()
        if item["permission_code"] == "workorder:view"
    )
    assert dictionary_client.delete(
        f"/api/permissions/{builtin['id']}"
    ).status_code == 409
    repairer = next(
        item
        for item in dictionary_client.get("/api/positions").json()
        if item["position_code"] == "REPAIRER"
    )
    assert dictionary_client.delete(
        f"/api/positions/{repairer['id']}"
    ).status_code == 409

    _login(dictionary_client, "lisi")
    assert dictionary_client.get("/api/positions").status_code == 403
    assert dictionary_client.get("/api/permissions").status_code == 403
    assert dictionary_client.get("/api/iam/audit-logs").status_code == 403
