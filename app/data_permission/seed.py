"""Idempotent application-role and governed-resource demo data."""

from dataclasses import dataclass

from app.core.config import get_settings
from app.db.session import Database
from app.iam.repository import IAMRepository
from app.iam.seed import CITY_TENANTS
from app.iam.service import IAMService
from app.project.repository import ProjectRepository

from .models import ApplicationRoleGrant, BusinessResource, DataSpace, ResourcePolicy
from .repository import DataPermissionRepository

APPLICATION_ROLE_GRANTS = {
    "admin": {"*": ("GROUP", "SYSTEM_ADMIN")},
    "owner_leader": {"*": ("GROUP", "DATA_VIEWER")},
    "water_drainage_leader": {
        "WATER_SUPPLY": ("OWNER_WATER", "DATA_VIEWER"),
        "WATER_HYDRAULIC": ("OWNER_WATER", "DATA_VIEWER"),
        "DRAINAGE": ("OWNER_DRAINAGE", "DATA_VIEWER"),
    },
    "water_manager": {
        "WATER_SUPPLY": ("OWNER_WATER", "DATA_MANAGER"),
        "WATER_HYDRAULIC": ("OWNER_WATER", "DATA_VIEWER"),
    },
    "drainage_manager": {"DRAINAGE": ("OWNER_DRAINAGE", "DATA_MANAGER")},
    "gas_manager": {"GAS": ("OWNER_GAS", "DATA_MANAGER")},
    "heating_manager": {"HEATING": ("OWNER_HEATING", "DATA_MANAGER")},
    "road_manager": {"ROAD": ("OWNER_ROAD", "DATA_MANAGER")},
    "dma_specialist": {"WATER_SUPPLY": ("OWNER_WATER", "DATA_STEWARD")},
    "hydraulic_specialist": {
        "WATER_HYDRAULIC": ("OWNER_WATER", "MODEL_ANALYST")
    },
}

SPACE_DEFINITIONS = (
    (
        "WS_DMA_PRIVATE",
        "供水 DMA 应用私有数据空间",
        "APPLICATION_PRIVATE",
        "WATER_SUPPLY",
        "OWNER_WATER",
        "INTERNAL",
    ),
    (
        "WS_MODEL_SANDBOX",
        "供水水力模型沙箱",
        "MODEL_SANDBOX",
        "WATER_HYDRAULIC",
        "OWNER_WATER",
        "RESTRICTED",
    ),
    (
        "DRAINAGE_PRIVATE",
        "排水应用私有数据空间",
        "APPLICATION_PRIVATE",
        "DRAINAGE",
        "OWNER_DRAINAGE",
        "INTERNAL",
    ),
    (
        "GAS_PRIVATE",
        "燃气应用私有数据空间",
        "APPLICATION_PRIVATE",
        "GAS",
        "OWNER_GAS",
        "INTERNAL",
    ),
    (
        "HEATING_PRIVATE",
        "供热应用私有数据空间",
        "APPLICATION_PRIVATE",
        "HEATING",
        "OWNER_HEATING",
        "INTERNAL",
    ),
    (
        "ROAD_PRIVATE",
        "道路应用私有数据空间",
        "APPLICATION_PRIVATE",
        "ROAD",
        "OWNER_ROAD",
        "INTERNAL",
    ),
)

RESOURCE_DEFINITIONS = (
    (
        "WS_DMA_PRESSURE_RAW",
        "DMA 压力监测采集数据",
        "DATASET",
        "ACQUIRED",
        "WS_DMA_PRIVATE",
        "INTERNAL",
    ),
    (
        "WS_DMA_PRESSURE_CLEAN",
        "DMA 压力清洗处理数据",
        "DATASET",
        "PROCESSED",
        "WS_DMA_PRIVATE",
        "INTERNAL",
    ),
    (
        "WS_WATER_NETWORK_LAYER",
        "供水管网 GIS 图层",
        "GIS_LAYER",
        "PROCESSED",
        "WS_DMA_PRIVATE",
        "INTERNAL",
    ),
    (
        "WS_DMA_LEAK_PREDICTION",
        "DMA 漏损模型计算结果",
        "MODEL_RESULT",
        "MODEL_RESULT",
        "WS_DMA_PRIVATE",
        "RESTRICTED",
    ),
    (
        "WS_HYDRAULIC_MODEL",
        "供水管网水力模型",
        "HYDRAULIC_MODEL",
        "MODEL_INPUT",
        "WS_MODEL_SANDBOX",
        "RESTRICTED",
    ),
    (
        "WS_HYDRAULIC_RESULT_DETAIL",
        "水力模型计算结果明细",
        "MODEL_RESULT",
        "MODEL_RESULT",
        "WS_MODEL_SANDBOX",
        "RESTRICTED",
    ),
    (
        "DRAINAGE_WATERLOGGING_LAYER",
        "排水易涝点 GIS 图层",
        "GIS_LAYER",
        "PROCESSED",
        "DRAINAGE_PRIVATE",
        "INTERNAL",
    ),
    (
        "GAS_PIPELINE_RISK_LAYER",
        "燃气管网风险 GIS 图层",
        "GIS_LAYER",
        "PROCESSED",
        "GAS_PRIVATE",
        "INTERNAL",
    ),
    (
        "HEATING_STATION_DATASET",
        "换热站运行数据集",
        "DATASET",
        "PROCESSED",
        "HEATING_PRIVATE",
        "INTERNAL",
    ),
    (
        "ROAD_BRIDGE_SENSOR_DATASET",
        "桥梁监测数据集",
        "DATASET",
        "PROCESSED",
        "ROAD_PRIVATE",
        "INTERNAL",
    ),
)


@dataclass(frozen=True)
class DataPermissionSeedSummary:
    application_role_grants: int
    data_spaces: int = len(SPACE_DEFINITIONS)
    resources: int = len(RESOURCE_DEFINITIONS)


def seed_data_permissions(
    repository: DataPermissionRepository,
    iam_service: IAMService,
) -> DataPermissionSeedSummary:
    project_repository = ProjectRepository(repository.session, repository.tenant_id)
    applications = {
        item.application_code: item for item in project_repository.list_applications()
    }
    subscriptions = {
        item.application.application_code: item
        for item in project_repository.list_subscriptions()
    }

    grant_count = 0
    for username, configured in APPLICATION_ROLE_GRANTS.items():
        expanded = (
            {code: configured["*"] for code in applications}
            if "*" in configured
            else configured
        )
        for application_code, (org_code, role_code) in expanded.items():
            membership = iam_service.get_membership(username, org_code)
            role = iam_service.get_role(role_code)
            subscription = subscriptions.get(application_code)
            if membership is None or role is None or subscription is None:
                raise RuntimeError(
                    "data permission seed missing binding: "
                    f"{username}/{application_code}/{org_code}/{role_code}"
                )
            grant = repository.get_grant(subscription.id, membership.id, role.id)
            if grant is None:
                repository.add(
                    ApplicationRoleGrant(
                        tenant_id=repository.tenant_id,
                        tenant_application_id=subscription.id,
                        user_org_id=membership.id,
                        role_id=role.id,
                        grant_source="SEED",
                    )
                )
            grant_count += 1
    repository.commit()

    spaces: dict[str, DataSpace] = {}
    for code, name, space_type, app_code, org_code, sensitivity in SPACE_DEFINITIONS:
        space = repository.get_space_by_code(code)
        application = applications[app_code]
        organization = iam_service.get_organization(org_code)
        if organization is None:
            raise RuntimeError(f"data permission seed missing organization: {org_code}")
        if space is None:
            space = repository.add(
                DataSpace(
                    tenant_id=repository.tenant_id,
                    space_code=code,
                    space_name=name,
                    space_type=space_type,
                    domain_type=application.domain_type,
                    application_id=application.id,
                    owner_org_id=organization.id,
                    sensitivity_level=sensitivity,
                )
            )
            repository.commit()
            repository.refresh(space)
        spaces[code] = space

    resources: list[BusinessResource] = []
    for key, name, resource_type, stage, space_code, sensitivity in RESOURCE_DEFINITIONS:
        resource = repository.get_resource_by_key(key)
        space = spaces[space_code]
        if resource is None:
            resource = repository.add(
                BusinessResource(
                    tenant_id=repository.tenant_id,
                    data_space_id=space.id,
                    application_id=space.application_id,
                    project_id=space.project_id,
                    owner_org_id=space.owner_org_id,
                    resource_type=resource_type,
                    resource_key=key,
                    resource_name=name,
                    derivation_stage=stage,
                    sensitivity_level=sensitivity,
                )
            )
            repository.commit()
            repository.refresh(resource)
        resources.append(resource)

    roles = {
        code: iam_service.get_role(code)
        for code in (
            "SYSTEM_ADMIN",
            "DATA_MANAGER",
            "DATA_VIEWER",
            "DATA_STEWARD",
            "MODEL_ANALYST",
        )
    }
    for resource in resources:
        role_effects = {
            "SYSTEM_ADMIN": "ALLOW",
            "DATA_MANAGER": "ALLOW",
            "DATA_VIEWER": "ALLOW",
        }
        if resource.derivation_stage in {"ACQUIRED", "PROCESSED"}:
            role_effects["DATA_STEWARD"] = "ALLOW"
        elif resource.derivation_stage == "MODEL_RESULT":
            role_effects["DATA_STEWARD"] = "DENY"
        if resource.application.application_code == "WATER_HYDRAULIC":
            role_effects["MODEL_ANALYST"] = "ALLOW"
        for role_code, effect in role_effects.items():
            role = roles[role_code]
            assert role is not None
            actions = ("data:resource:view", "data:resource:query")
            if role_code in {"SYSTEM_ADMIN", "DATA_MANAGER"}:
                actions += ("data:resource:manage",)
            for action in actions:
                if repository.get_policy(role.id, resource.id, action, effect) is None:
                    repository.add(
                        ResourcePolicy(
                            tenant_id=repository.tenant_id,
                            subject_type="ROLE",
                            subject_id=role.id,
                            resource_id=resource.id,
                            action_code=action,
                            effect=effect,
                            priority=100 if effect == "DENY" else 10,
                        )
                    )
    repository.commit()
    return DataPermissionSeedSummary(grant_count)


def main() -> None:
    database = Database(get_settings().database_url)
    try:
        with database.session_factory() as session:
            summaries = []
            for tenant_code, _, _ in CITY_TENANTS:
                tenant = IAMRepository(session).get_tenant_by_code(tenant_code)
                if tenant is None:
                    raise RuntimeError(f"IAM city tenant missing: {tenant_code}")
                iam_service = IAMService(IAMRepository(session, tenant.id))
                summaries.append(
                    seed_data_permissions(
                        DataPermissionRepository(session, tenant.id), iam_service
                    )
                )
        print(
            "Data permission seed ready: "
            f"{len(summaries)} cities, "
            f"{sum(item.application_role_grants for item in summaries)} app roles, "
            f"{sum(item.data_spaces for item in summaries)} spaces, "
            f"{sum(item.resources for item in summaries)} resources"
        )
    finally:
        database.dispose()


if __name__ == "__main__":
    main()
