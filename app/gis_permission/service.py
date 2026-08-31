"""Server-side GIS feature filtering, masking, and export authorization."""

from dataclasses import dataclass

from app.data_permission.repository import DataPermissionRepository
from app.data_permission.service import (
    DataActor,
    DataPermissionDenied,
    DataPermissionService,
    DataResourceNotFound,
)

from .models import (
    GISExportJob,
    ResourceField,
    ResourceFieldPolicy,
    SpatialScopeGrant,
)
from .repository import GISPermissionRepository


class GISValidationError(Exception):
    pass


@dataclass(frozen=True)
class GISQueryResult:
    resource_id: int
    fields: tuple[dict, ...]
    features: tuple[dict, ...]
    spatial_scopes: tuple[str, ...]
    coordinate_precision: str


class GISPermissionService:
    PRECISION_RANK = {"REGION_ONLY": 0, "GRID_1KM": 1, "GRID_100M": 2, "EXACT": 3}

    def __init__(
        self,
        repository: GISPermissionRepository,
        data_repository: DataPermissionRepository,
        data_permission_service: DataPermissionService,
    ) -> None:
        self.repository = repository
        self.data_repository = data_repository
        self.data_permission_service = data_permission_service

    def query_features(self, resource_id: int, actor: DataActor) -> GISQueryResult:
        resource = self.repository.get_gis_resource(resource_id)
        if resource is None:
            raise DataResourceNotFound("GIS 图层不存在或不属于当前租户")
        if not self.data_repository.has_application_access(
            actor.user_id, resource.application_id
        ):
            raise DataResourceNotFound("GIS 图层不存在或不属于当前系统授权范围")
        explanation = self.data_permission_service.explain(
            resource_id, "gis:spatial:query", actor
        )
        if not explanation["allowed"]:
            raise DataPermissionDenied(explanation["decision_reason"])

        role_ids = self._allowed_role_ids(
            actor.user_id, resource.application_id, resource_id, "gis:spatial:query"
        )
        spatial_grants = self.repository.list_spatial_grants(resource_id, role_ids)
        if not spatial_grants:
            raise DataPermissionDenied("拒绝：没有匹配的 GIS 空间范围")
        sensitive_role_ids = self._allowed_role_ids(
            actor.user_id,
            resource.application_id,
            resource_id,
            "gis:field:sensitive:view",
        )
        exact_coordinate_role_ids = self._allowed_role_ids(
            actor.user_id,
            resource.application_id,
            resource_id,
            "gis:coordinate:exact",
        )
        field_modes = self._field_modes(
            resource_id, role_ids, sensitive_role_ids
        )
        fields = self.repository.list_fields(resource_id)
        visible_fields = tuple(
            self._field_item(field, field_modes[field.id])
            for field in fields
            if field_modes.get(field.id) != "HIDDEN"
        )
        precision = self._coordinate_precision(
            spatial_grants, exact_coordinate_role_ids
        )
        features = tuple(
            self._feature_item(feature, fields, field_modes, precision)
            for feature in self.repository.list_features(resource_id)
            if self._in_scope(feature.scope_type, feature.scope_value, spatial_grants)
        )
        return GISQueryResult(
            resource_id,
            visible_fields,
            features,
            tuple(
                sorted(
                    f"{grant.scope_type}:{grant.scope_value}"
                    for grant in spatial_grants
                )
            ),
            precision,
        )

    def request_export(
        self,
        resource_id: int,
        actor: DataActor,
        field_codes: tuple[str, ...],
        export_format: str = "CSV",
    ) -> GISExportJob:
        resource = self.repository.get_gis_resource(resource_id)
        if resource is None:
            raise DataResourceNotFound("GIS 图层不存在或不属于当前租户")
        if not self.data_repository.has_application_access(
            actor.user_id, resource.application_id
        ):
            raise DataResourceNotFound("GIS 图层不存在或不属于当前系统授权范围")
        explanation = self.data_permission_service.explain(resource_id, "gis:export", actor)
        if not explanation["allowed"]:
            raise DataPermissionDenied(explanation["decision_reason"])
        query = self.query_features(resource_id, actor)
        ordered_visible_codes = tuple(field["field_code"] for field in query.fields)
        visible_codes = set(ordered_visible_codes)
        selected_codes = tuple(dict.fromkeys(field_codes or ordered_visible_codes))
        if not selected_codes or not set(selected_codes) <= visible_codes:
            raise GISValidationError("导出字段包含隐藏或不存在的字段")
        fields = {
            field.field_code: field for field in self.repository.list_fields(resource_id)
        }
        if any(fields[code].sensitivity_level == "SENSITIVE" for code in selected_codes):
            role_ids = self._allowed_role_ids(
                actor.user_id,
                resource.application_id,
                resource_id,
                "gis:export:sensitive",
            )
            if not role_ids:
                raise DataPermissionDenied("拒绝：缺少 GIS 敏感字段导出权限")
        normalized_format = export_format.strip().upper()
        if normalized_format not in {"CSV", "GEOJSON"}:
            raise GISValidationError("演示导出仅支持 CSV 或 GEOJSON")
        job = self.repository.add(
            GISExportJob(
                tenant_id=self.repository.tenant_id,
                resource_id=resource_id,
                requested_by=actor.user_id,
                export_format=normalized_format,
                status="COMPLETED",
                row_count=len(query.features),
                field_codes_json=list(selected_codes),
                spatial_scope_json=list(query.spatial_scopes),
                file_name=f"{resource.resource_key.lower()}-{actor.user_id}.{normalized_format.lower()}",
            )
        )
        self.repository.commit()
        self.repository.refresh(job)
        return job

    def list_exports(self, actor: DataActor) -> list[GISExportJob]:
        return self.repository.list_export_jobs(actor.user_id)

    def create_field(
        self, resource_id: int, field: ResourceField, actor: DataActor
    ) -> ResourceField:
        self._require_management(actor)
        if self.repository.get_gis_resource(resource_id) is None:
            raise DataResourceNotFound("GIS 图层不存在或不属于当前租户")
        if self.repository.get_field(resource_id, field.field_code) is not None:
            raise GISValidationError("GIS 字段编码已存在")
        self.repository.add(field)
        self.repository.commit()
        self.repository.refresh(field)
        return field

    def set_field_policy(
        self,
        field_id: int,
        role_code: str,
        access_mode: str,
        actor: DataActor,
    ) -> ResourceFieldPolicy:
        self._require_management(actor)
        field = self.repository.get_field_by_id(field_id)
        role = self.data_repository.get_role(role_code)
        if field is None or role is None:
            raise GISValidationError("字段或角色不存在")
        policy = self.repository.get_field_policy(role.id, field.id)
        if policy is None:
            policy = self.repository.add(
                ResourceFieldPolicy(
                    tenant_id=self.repository.tenant_id,
                    role_id=role.id,
                    resource_field_id=field.id,
                    access_mode=access_mode.upper(),
                )
            )
        else:
            policy.access_mode = access_mode.upper()
            policy.is_active = True
        self.repository.commit()
        self.repository.refresh(policy)
        return policy

    def set_spatial_scope(
        self,
        resource_id: int,
        role_code: str,
        scope_type: str,
        scope_value: str,
        coordinate_precision: str,
        actor: DataActor,
    ) -> SpatialScopeGrant:
        self._require_management(actor)
        resource = self.repository.get_gis_resource(resource_id)
        role = self.data_repository.get_role(role_code)
        if resource is None or role is None:
            raise GISValidationError("GIS 图层或角色不存在")
        normalized_scope_type = scope_type.upper()
        normalized_precision = coordinate_precision.upper()
        grant = self.repository.get_spatial_grant(
            role.id, resource_id, normalized_scope_type, scope_value
        )
        if grant is None:
            grant = self.repository.add(
                SpatialScopeGrant(
                    tenant_id=self.repository.tenant_id,
                    role_id=role.id,
                    resource_id=resource_id,
                    scope_type=normalized_scope_type,
                    scope_value=scope_value,
                    coordinate_precision=normalized_precision,
                )
            )
        else:
            grant.coordinate_precision = normalized_precision
            grant.is_active = True
        self.repository.commit()
        self.repository.refresh(grant)
        return grant

    def _require_management(self, actor: DataActor) -> None:
        if not self.data_permission_service.permission_service.has_permission(
            actor.user_id, "data:resource:manage", actor.active_org_id
        ):
            raise DataPermissionDenied("缺少 GIS 资源策略管理权限")

    def _allowed_role_ids(
        self,
        user_id: int,
        application_id: int,
        resource_id: int,
        action_code: str,
    ) -> set[int]:
        result = set()
        for grant in self.data_repository.list_user_grants(user_id, application_id):
            if not self.data_repository.role_has_permission(grant.role_id, action_code):
                continue
            policies = self.data_repository.list_policies(
                resource_id, {grant.role_id}, action_code
            )
            if any(item.effect == "DENY" for item in policies):
                continue
            if any(item.effect == "ALLOW" for item in policies):
                result.add(grant.role_id)
        return result

    def _field_modes(
        self,
        resource_id: int,
        role_ids: set[int],
        sensitive_role_ids: set[int],
    ) -> dict[int, str]:
        grouped: dict[int, list[str]] = {}
        for policy in self.repository.list_field_policies(resource_id, role_ids):
            grouped.setdefault(policy.resource_field_id, []).append(policy.access_mode)
        sensitive_allowed = bool(role_ids & sensitive_role_ids)
        result = {}
        for field in self.repository.list_fields(resource_id):
            modes = grouped.get(field.id, [])
            if "HIDDEN" in modes or not modes:
                result[field.id] = "HIDDEN"
            elif field.sensitivity_level == "SENSITIVE" and not sensitive_allowed:
                result[field.id] = "MASKED" if field.mask_rule else "HIDDEN"
            elif "VISIBLE" in modes:
                result[field.id] = "VISIBLE"
            else:
                result[field.id] = "MASKED"
        return result

    def _coordinate_precision(self, grants, exact_role_ids: set[int]) -> str:
        precision_values = [
            grant.coordinate_precision
            if grant.role_id in exact_role_ids
            else min(
                grant.coordinate_precision,
                "GRID_1KM",
                key=lambda item: self.PRECISION_RANK[item],
            )
            for grant in grants
        ]
        return max(precision_values, key=lambda item: self.PRECISION_RANK[item])

    @staticmethod
    def _in_scope(scope_type: str, scope_value: str, grants) -> bool:
        return any(
            grant.scope_type == "ALL"
            or (grant.scope_type == scope_type and grant.scope_value == scope_value)
            for grant in grants
        )

    @staticmethod
    def _field_item(field: ResourceField, mode: str) -> dict:
        return {
            "field_code": field.field_code,
            "field_name": field.field_name,
            "data_type": field.data_type,
            "sensitivity_level": field.sensitivity_level,
            "access_mode": mode,
        }

    def _feature_item(self, feature, fields, field_modes, precision: str) -> dict:
        properties = {}
        for field in fields:
            mode = field_modes.get(field.id, "HIDDEN")
            if mode == "HIDDEN" or field.field_code not in feature.properties_json:
                continue
            value = feature.properties_json[field.field_code]
            properties[field.field_code] = (
                self._mask(value, field.mask_rule) if mode == "MASKED" else value
            )
        longitude, latitude = self._coordinates(
            feature.longitude, feature.latitude, precision
        )
        return {
            "feature_key": feature.feature_key,
            "feature_name": feature.feature_name,
            "scope_type": feature.scope_type,
            "scope_value": feature.scope_value,
            "longitude": longitude,
            "latitude": latitude,
            "properties": properties,
        }

    @staticmethod
    def _coordinates(longitude: float, latitude: float, precision: str):
        decimals = {"EXACT": 6, "GRID_100M": 3, "GRID_1KM": 2}.get(precision)
        if decimals is None:
            return None, None
        return round(longitude, decimals), round(latitude, decimals)

    @staticmethod
    def _mask(value, rule: str | None):
        text = str(value)
        if rule == "PHONE" and len(text) >= 7:
            return f"{text[:3]}****{text[-4:]}"
        if rule == "ADDRESS":
            return f"{text[:4]}***" if text else "***"
        return "***"
