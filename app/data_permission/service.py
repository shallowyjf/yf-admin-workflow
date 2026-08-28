"""Authorization decisions for application-scoped business resources."""

from dataclasses import dataclass

from app.iam.authorization import PermissionService
from app.iam.models import Role, UserOrganization

from .models import ApplicationRoleGrant, BusinessResource, DataSpace, ResourcePolicy
from .repository import DataPermissionRepository


class DataPermissionDenied(Exception):
    pass


class DataResourceNotFound(Exception):
    pass


class DataPermissionValidationError(Exception):
    pass


@dataclass(frozen=True)
class DataActor:
    user_id: int
    active_org_id: int


class DataPermissionService:
    def __init__(
        self,
        repository: DataPermissionRepository,
        permission_service: PermissionService,
    ) -> None:
        self.repository = repository
        self.permission_service = permission_service

    def explain(
        self, resource_id: int, action_code: str, actor: DataActor
    ) -> dict:
        resource = self.repository.get_resource(resource_id)
        if resource is None:
            raise DataResourceNotFound("数据资源不存在或不属于当前租户")
        app_access = self.repository.has_application_access(
            actor.user_id, resource.application_id
        )
        grants = self.repository.list_user_grants(
            actor.user_id, resource.application_id
        )
        permitted_grants = [
            grant
            for grant in grants
            if self.repository.role_has_permission(grant.role_id, action_code)
        ]
        role_ids = {grant.role_id for grant in permitted_grants}
        policies = self.repository.list_policies(resource.id, role_ids, action_code)
        deny = any(policy.effect == "DENY" for policy in policies)
        allow = any(policy.effect == "ALLOW" for policy in policies)
        allowed = app_access and bool(permitted_grants) and allow and not deny
        return {
            "tenant_id": self.repository.tenant_id,
            "resource_id": resource.id,
            "resource_key": resource.resource_key,
            "application_id": resource.application_id,
            "action_code": action_code,
            "checks": {
                "tenant_match": True,
                "application_entrance": app_access,
                "active_application_role": bool(grants),
                "role_has_action_permission": bool(permitted_grants),
                "matching_allow_policy": allow,
                "matching_deny_policy": deny,
            },
            "matching_role_codes": sorted(
                {grant.role.role_code for grant in permitted_grants}
            ),
            "policy_effects": [policy.effect for policy in policies],
            "allowed": allowed,
            "decision_reason": self._decision_reason(
                app_access, grants, permitted_grants, allow, deny
            ),
        }

    def list_resources(
        self,
        actor: DataActor,
        *,
        application_id: int | None = None,
        action_code: str = "data:resource:view",
    ) -> list[BusinessResource]:
        return [
            resource
            for resource in self.repository.list_resources(application_id)
            if self.explain(resource.id, action_code, actor)["allowed"]
        ]

    def get_resource(
        self, resource_id: int, action_code: str, actor: DataActor
    ) -> BusinessResource:
        explanation = self.explain(resource_id, action_code, actor)
        if not explanation["allowed"]:
            raise DataPermissionDenied(explanation["decision_reason"])
        resource = self.repository.get_resource(resource_id)
        assert resource is not None
        return resource

    def list_visible_spaces(
        self, actor: DataActor, application_id: int | None = None
    ) -> list[DataSpace]:
        visible_space_ids = {
            resource.data_space_id
            for resource in self.list_resources(actor, application_id=application_id)
        }
        return [
            space
            for space in self.repository.list_spaces(application_id)
            if space.id in visible_space_ids
        ]

    def grant_application_role(
        self,
        application_id: int,
        membership: UserOrganization,
        role: Role,
        actor: DataActor,
    ) -> ApplicationRoleGrant:
        self._require_management(actor, "data:application-role:manage")
        subscription = self.repository.get_subscription(application_id)
        if subscription is None:
            raise DataPermissionValidationError("租户未开通目标应用")
        existing = self.repository.get_grant(subscription.id, membership.id, role.id)
        if existing is not None:
            existing.is_active = True
            grant = existing
        else:
            grant = self.repository.add(
                ApplicationRoleGrant(
                    tenant_id=self.repository.tenant_id,
                    tenant_application_id=subscription.id,
                    user_org_id=membership.id,
                    role_id=role.id,
                )
            )
        self.repository.commit()
        self.repository.refresh(grant)
        return grant

    def create_space(self, space: DataSpace, actor: DataActor) -> DataSpace:
        self._require_management(actor, "data:space:manage")
        if space.tenant_id != self.repository.tenant_id:
            raise DataPermissionValidationError("数据空间租户不匹配")
        if self.repository.get_space_by_code(space.space_code) is not None:
            raise DataPermissionValidationError("数据空间编码已存在")
        self.repository.add(space)
        self.repository.commit()
        self.repository.refresh(space)
        return space

    def create_resource(
        self, resource: BusinessResource, actor: DataActor
    ) -> BusinessResource:
        self._require_management(actor, "data:resource:manage")
        if resource.tenant_id != self.repository.tenant_id:
            raise DataPermissionValidationError("数据资源租户不匹配")
        space = next(
            (
                item
                for item in self.repository.list_spaces(resource.application_id)
                if item.id == resource.data_space_id
            ),
            None,
        )
        if space is None:
            raise DataPermissionValidationError("数据空间与应用不匹配")
        if self.repository.get_resource_by_key(resource.resource_key) is not None:
            raise DataPermissionValidationError("数据资源标识已存在")
        self.repository.add(resource)
        self.repository.commit()
        self.repository.refresh(resource)
        return resource

    def add_policy(
        self,
        resource_id: int,
        role: Role,
        action_code: str,
        effect: str,
        actor: DataActor,
    ) -> ResourcePolicy:
        self._require_management(actor, "data:resource:manage")
        if self.repository.get_resource(resource_id) is None:
            raise DataResourceNotFound("数据资源不存在或不属于当前租户")
        normalized_effect = effect.strip().upper()
        if normalized_effect not in {"ALLOW", "DENY"}:
            raise DataPermissionValidationError("策略效果必须为 ALLOW 或 DENY")
        policy = self.repository.get_policy(
            role.id, resource_id, action_code, normalized_effect
        )
        if policy is None:
            policy = self.repository.add(
                ResourcePolicy(
                    tenant_id=self.repository.tenant_id,
                    subject_type="ROLE",
                    subject_id=role.id,
                    resource_id=resource_id,
                    action_code=action_code,
                    effect=normalized_effect,
                )
            )
        else:
            policy.is_active = True
        self.repository.commit()
        self.repository.refresh(policy)
        return policy

    def _require_management(self, actor: DataActor, permission_code: str) -> None:
        if not self.permission_service.has_permission(
            actor.user_id, permission_code, actor.active_org_id
        ):
            raise DataPermissionDenied(f"缺少管理权限：{permission_code}")

    @staticmethod
    def _decision_reason(app_access, grants, permitted_grants, allow, deny) -> str:
        if not app_access:
            return "拒绝：没有业务系统入口"
        if not grants:
            return "拒绝：没有该系统的应用级角色"
        if not permitted_grants:
            return "拒绝：应用级角色不包含目标操作"
        if deny:
            return "拒绝：命中显式 DENY 策略"
        if not allow:
            return "拒绝：默认拒绝，未命中 ALLOW 策略"
        return "允许：系统入口、应用角色、操作权限和资源策略均通过"


def resource_item(resource: BusinessResource) -> dict:
    return {
        "id": resource.id,
        "data_space_id": resource.data_space_id,
        "space_code": resource.data_space.space_code,
        "space_name": resource.data_space.space_name,
        "application_id": resource.application_id,
        "application_code": resource.application.application_code,
        "application_name": resource.application.application_name,
        "project_id": resource.project_id,
        "project_name": resource.project.project_name if resource.project else None,
        "owner_org_id": resource.owner_org_id,
        "owner_org_name": resource.owner_organization.org_name,
        "resource_type": resource.resource_type,
        "resource_key": resource.resource_key,
        "resource_name": resource.resource_name,
        "derivation_stage": resource.derivation_stage,
        "sensitivity_level": resource.sensitivity_level,
        "status": resource.status,
    }
