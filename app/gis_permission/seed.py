"""Idempotent GIS field, scope, feature, and export-policy demo seed."""

from dataclasses import dataclass

from app.core.config import get_settings
from app.data_permission.models import ResourcePolicy
from app.data_permission.repository import DataPermissionRepository
from app.db.session import Database
from app.iam.repository import IAMRepository
from app.iam.seed import CITY_TENANTS
from app.iam.service import IAMService

from .models import (
    GISFeature,
    ResourceField,
    ResourceFieldPolicy,
    SpatialScopeGrant,
)
from .repository import GISPermissionRepository

GIS_RESOURCES = {
    "WS_WATER_NETWORK_LAYER": (
        ("WS-PIPE-001", "滨江路 DN600 供水管段", "DMA", "DMA_07", 118.781231, 32.041872, 0.43),
        ("WS-PIPE-002", "城北路 DN400 供水管段", "DMA", "DMA_12", 118.742913, 32.092611, 0.38),
        ("WS-PIPE-003", "东湖路 DN800 供水管段", "DMA", "DMA_19", 118.829614, 32.065823, 0.51),
    ),
    "DRAINAGE_WATERLOGGING_LAYER": (
        ("DR-POINT-001", "人民路下穿易涝点", "DISTRICT", "CENTER", 118.775231, 32.052818, 0.81),
        ("DR-POINT-002", "城南泵站汇水区", "DISTRICT", "SOUTH", 118.761992, 31.998313, 0.56),
        ("DR-POINT-003", "开发区主干管节点", "DISTRICT", "EAST", 118.861248, 32.044991, 0.47),
    ),
    "GAS_PIPELINE_RISK_LAYER": (
        ("GAS-PIPE-001", "高新区中压燃气管段", "DISTRICT", "EAST", 118.872915, 32.061483, 0.72),
        ("GAS-PIPE-002", "经开大道燃气阀井", "DISTRICT", "SOUTH", 118.804326, 31.987561, 0.64),
        ("GAS-PIPE-003", "西环路高压燃气支线", "DISTRICT", "WEST", 118.701946, 32.048291, 0.69),
    ),
}

FIELD_DEFINITIONS = (
    ("asset_code", "设施编码", "STRING", "INTERNAL", None),
    ("asset_type", "设施类型", "STRING", "INTERNAL", None),
    ("metric_value", "运行指标", "DECIMAL", "INTERNAL", None),
    ("exact_address", "精确地址", "STRING", "SENSITIVE", "ADDRESS"),
    ("owner_phone", "责任人电话", "STRING", "SENSITIVE", "PHONE"),
)

GIS_ACTIONS = {
    "SYSTEM_ADMIN": (
        "gis:feature:view",
        "gis:feature:edit",
        "gis:spatial:query",
        "gis:coordinate:exact",
        "gis:field:sensitive:view",
        "gis:export",
        "gis:export:sensitive",
    ),
    "DATA_MANAGER": (
        "gis:feature:view",
        "gis:feature:edit",
        "gis:spatial:query",
        "gis:coordinate:exact",
        "gis:field:sensitive:view",
        "gis:export",
    ),
    "DATA_VIEWER": ("gis:feature:view", "gis:spatial:query"),
    "DATA_STEWARD": ("gis:feature:view", "gis:spatial:query"),
}


@dataclass(frozen=True)
class GISPermissionSeedSummary:
    fields: int = len(GIS_RESOURCES) * len(FIELD_DEFINITIONS)
    features: int = sum(len(items) for items in GIS_RESOURCES.values())


def seed_gis_permissions(
    repository: GISPermissionRepository,
    data_repository: DataPermissionRepository,
    iam_service: IAMService,
) -> GISPermissionSeedSummary:
    roles = {code: iam_service.get_role(code) for code in GIS_ACTIONS}
    for resource_key, features in GIS_RESOURCES.items():
        resource = data_repository.get_resource_by_key(resource_key)
        if resource is None:
            raise RuntimeError(f"GIS seed missing business resource: {resource_key}")

        for role_code, actions in GIS_ACTIONS.items():
            role = roles[role_code]
            assert role is not None
            for action in actions:
                if data_repository.get_policy(role.id, resource.id, action, "ALLOW") is None:
                    data_repository.add(
                        ResourcePolicy(
                            tenant_id=repository.tenant_id,
                            subject_type="ROLE",
                            subject_id=role.id,
                            resource_id=resource.id,
                            action_code=action,
                            effect="ALLOW",
                            priority=10,
                        )
                    )
        data_repository.commit()

        fields = {}
        for code, name, data_type, sensitivity, mask_rule in FIELD_DEFINITIONS:
            field = repository.get_field(resource.id, code)
            if field is None:
                field = repository.add(
                    ResourceField(
                        tenant_id=repository.tenant_id,
                        resource_id=resource.id,
                        field_code=code,
                        field_name=name,
                        data_type=data_type,
                        sensitivity_level=sensitivity,
                        mask_rule=mask_rule,
                    )
                )
                repository.commit()
                repository.refresh(field)
            fields[code] = field

        for role_code, role in roles.items():
            assert role is not None
            for field_code, field in fields.items():
                if role_code in {"SYSTEM_ADMIN", "DATA_MANAGER"}:
                    mode = "VISIBLE"
                elif field_code in {"exact_address", "owner_phone"}:
                    mode = "HIDDEN" if role_code == "DATA_STEWARD" else "MASKED"
                else:
                    mode = "VISIBLE"
                policy = repository.get_field_policy(role.id, field.id)
                if policy is None:
                    repository.add(
                        ResourceFieldPolicy(
                            tenant_id=repository.tenant_id,
                            role_id=role.id,
                            resource_field_id=field.id,
                            access_mode=mode,
                        )
                    )
        repository.commit()

        for role_code, role in roles.items():
            assert role is not None
            scope_definitions = []
            if role_code in {"SYSTEM_ADMIN", "DATA_MANAGER"}:
                scope_definitions = [("ALL", "*", "EXACT")]
            elif role_code == "DATA_VIEWER":
                scope_definitions = [("ALL", "*", "REGION_ONLY")]
            elif resource_key == "WS_WATER_NETWORK_LAYER":
                scope_definitions = [
                    ("DMA", "DMA_07", "GRID_1KM"),
                    ("DMA", "DMA_12", "GRID_1KM"),
                ]
            for scope_type, scope_value, precision in scope_definitions:
                if (
                    repository.get_spatial_grant(
                        role.id, resource.id, scope_type, scope_value
                    )
                    is None
                ):
                    repository.add(
                        SpatialScopeGrant(
                            tenant_id=repository.tenant_id,
                            role_id=role.id,
                            resource_id=resource.id,
                            scope_type=scope_type,
                            scope_value=scope_value,
                            coordinate_precision=precision,
                        )
                    )
        repository.commit()

        for index, (
            feature_key,
            feature_name,
            scope_type,
            scope_value,
            longitude,
            latitude,
            metric,
        ) in enumerate(features, start=1):
            if repository.get_feature(resource.id, feature_key) is None:
                repository.add(
                    GISFeature(
                        tenant_id=repository.tenant_id,
                        resource_id=resource.id,
                        feature_key=feature_key,
                        feature_name=feature_name,
                        scope_type=scope_type,
                        scope_value=scope_value,
                        longitude=longitude,
                        latitude=latitude,
                        properties_json={
                            "asset_code": feature_key,
                            "asset_type": resource.resource_name,
                            "metric_value": metric,
                            "exact_address": f"江城市示范路段 {index} 号",
                            "owner_phone": f"1380000{index:04d}",
                        },
                    )
                )
        repository.commit()
    return GISPermissionSeedSummary()


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
                    seed_gis_permissions(
                        GISPermissionRepository(session, tenant.id),
                        DataPermissionRepository(session, tenant.id),
                        iam_service,
                    )
                )
        print(
            "GIS permission seed ready: "
            f"{len(summaries)} cities, "
            f"{sum(item.fields for item in summaries)} fields, "
            f"{sum(item.features for item in summaries)} features"
        )
    finally:
        database.dispose()


if __name__ == "__main__":
    main()
