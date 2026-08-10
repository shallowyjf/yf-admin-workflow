"""Permission-checked role lifecycle and atomic authorization use cases."""

from __future__ import annotations

import re
from dataclasses import dataclass

from .admin_service import (
    IAMAdministrationActor,
    IAMAdministrationConflict,
    IAMAdministrationPermissionDenied,
    IAMAdministrationValidationError,
)
from .authorization import DataScopeType, PermissionService
from .models import IAMAuditLog, Permission, Role, RoleDataScope, RolePermission
from .repository import IAMRepository
from .service import DuplicateIAMCode, IAMEntityNotFound


@dataclass(frozen=True)
class CreateRoleCommand:
    role_code: str
    role_name: str
    role_type: str | None = None


@dataclass(frozen=True)
class UpdateRoleCommand:
    role_name: str
    role_type: str | None = None


@dataclass(frozen=True)
class PermissionScopeConfiguration:
    permission_code: str
    scope_type: DataScopeType | str
    custom_org_codes: tuple[str, ...] = ()


@dataclass(frozen=True)
class _ResolvedAuthorization:
    permission: Permission
    scope_type: DataScopeType
    scope_config: dict | None


class RoleAdministrationService:
    VIEW_PERMISSION = "system:role:view"
    CREATE_PERMISSION = "system:role:create"
    UPDATE_PERMISSION = "system:role:update"
    STATUS_PERMISSION = "system:role:status"
    AUTHORIZE_PERMISSION = "system:role:authorize"
    CODE_PATTERN = re.compile(r"^[A-Z][A-Z0-9_]{1,79}$")
    PROTECTED_ROLE_CODE = "SYSTEM_ADMIN"
    PROTECTED_PERMISSIONS = frozenset(
        {
            VIEW_PERMISSION,
            CREATE_PERMISSION,
            UPDATE_PERMISSION,
            STATUS_PERMISSION,
            AUTHORIZE_PERMISSION,
        }
    )

    def __init__(
        self,
        repository: IAMRepository,
        permission_service: PermissionService,
    ) -> None:
        self.repository = repository
        self.permission_service = permission_service

    def list_roles(self, actor: IAMAdministrationActor) -> list[Role]:
        self._require_permission(actor, self.VIEW_PERMISSION)
        return self.repository.list_roles()

    def get_role(self, role_id: int, actor: IAMAdministrationActor) -> Role:
        self._require_permission(actor, self.VIEW_PERMISSION)
        return self._require_role(role_id)

    def create(
        self,
        command: CreateRoleCommand,
        actor: IAMAdministrationActor,
    ) -> Role:
        self._require_permission(actor, self.CREATE_PERMISSION)
        role_code = command.role_code.strip().upper()
        if not self.CODE_PATTERN.fullmatch(role_code):
            raise IAMAdministrationValidationError(
                "角色编码须以字母开头，且只能包含大写字母、数字和下划线"
            )
        if self.repository.get_role_by_code(role_code) is not None:
            raise DuplicateIAMCode(f"role already exists: {role_code}")
        role = Role(
            role_code=role_code,
            role_name=self._required_name(command.role_name),
            role_type=self._optional_text(command.role_type),
        )
        self.repository.add(role)
        self.repository.flush()
        self._audit(role.id, "CREATE", actor, {"after": self._snapshot(role)})
        self.repository.commit()
        return self._require_role(role.id)

    def update(
        self,
        role_id: int,
        command: UpdateRoleCommand,
        actor: IAMAdministrationActor,
    ) -> Role:
        self._require_permission(actor, self.UPDATE_PERMISSION)
        role = self._require_role(role_id)
        before = self._snapshot(role)
        role.role_name = self._required_name(command.role_name)
        role.role_type = self._optional_text(command.role_type)
        self._audit(
            role.id,
            "UPDATE",
            actor,
            {"before": before, "after": self._snapshot(role)},
        )
        self.repository.commit()
        return self._reload(role.id)

    def set_active(
        self,
        role_id: int,
        is_active: bool,
        actor: IAMAdministrationActor,
    ) -> Role:
        self._require_permission(actor, self.STATUS_PERMISSION)
        role = self._require_role(role_id)
        if role.role_code == self.PROTECTED_ROLE_CODE and not is_active:
            raise IAMAdministrationConflict("系统管理员角色不能停用")
        if role.is_active == is_active:
            return role
        before = role.is_active
        role.is_active = is_active
        self._audit(
            role.id,
            "ENABLE" if is_active else "DISABLE",
            actor,
            {"before": {"is_active": before}, "after": {"is_active": is_active}},
        )
        self.repository.commit()
        return self._reload(role.id)

    def replace_authorization(
        self,
        role_id: int,
        configurations: tuple[PermissionScopeConfiguration, ...],
        actor: IAMAdministrationActor,
    ) -> Role:
        """Atomically replace permissions and the scope belonging to each permission."""

        self._require_permission(actor, self.AUTHORIZE_PERMISSION)
        role = self._require_role(role_id)
        resolved = self._resolve_authorization(configurations)
        target_codes = {item.permission.permission_code for item in resolved}
        if (
            role.role_code == self.PROTECTED_ROLE_CODE
            and not self.PROTECTED_PERMISSIONS.issubset(target_codes)
        ):
            raise IAMAdministrationConflict(
                "系统管理员角色必须保留全部角色管理核心权限"
            )

        before = self._snapshot(role)
        existing_permissions = {
            link.permission.permission_code: link for link in role.permission_links
        }
        existing_scopes = {scope.permission_code: scope for scope in role.data_scopes}

        for code, link in existing_permissions.items():
            if code not in target_codes:
                self.repository.delete(link)
        for code, scope in existing_scopes.items():
            if code not in target_codes:
                self.repository.delete(scope)

        for item in resolved:
            code = item.permission.permission_code
            if code not in existing_permissions:
                self.repository.add(
                    RolePermission(role_id=role.id, permission_id=item.permission.id)
                )
            scope = existing_scopes.get(code)
            if scope is None:
                scope = RoleDataScope(role_id=role.id, permission_code=code)
                self.repository.add(scope)
            scope.scope_type = item.scope_type.value
            scope.scope_config = item.scope_config

        self.repository.flush()
        self._audit(
            role.id,
            "REPLACE_AUTHORIZATION",
            actor,
            {
                "before": before.get("authorization", []),
                "after": self._authorization_snapshot(resolved),
            },
        )
        self.repository.commit()
        return self._reload(role.id)

    def _resolve_authorization(
        self,
        configurations: tuple[PermissionScopeConfiguration, ...],
    ) -> tuple[_ResolvedAuthorization, ...]:
        normalized_codes = [item.permission_code.strip() for item in configurations]
        if len(normalized_codes) != len(set(normalized_codes)):
            raise IAMAdministrationValidationError("同一权限不能重复配置")
        organizations = {
            organization.org_code: organization
            for organization in self.repository.list_organizations()
        }
        resolved: list[_ResolvedAuthorization] = []
        for command, permission_code in zip(
            configurations,
            normalized_codes,
            strict=True,
        ):
            permission = self.repository.get_permission_by_code(permission_code)
            if permission is None:
                raise IAMEntityNotFound(f"permission not found: {permission_code}")
            try:
                scope_type = DataScopeType(command.scope_type)
            except ValueError as error:
                raise IAMAdministrationValidationError(
                    f"不支持的数据范围: {command.scope_type}"
                ) from error
            custom_codes = tuple(
                code.strip().upper() for code in command.custom_org_codes if code.strip()
            )
            if len(custom_codes) != len(set(custom_codes)):
                raise IAMAdministrationValidationError("CUSTOM 组织不能重复")
            if scope_type is DataScopeType.CUSTOM:
                if not custom_codes:
                    raise IAMAdministrationValidationError(
                        "CUSTOM 数据范围至少需要一个组织"
                    )
                custom_org_ids: list[int] = []
                for org_code in custom_codes:
                    organization = organizations.get(org_code)
                    if organization is None:
                        raise IAMEntityNotFound(
                            f"custom organization not found: {org_code}"
                        )
                    if not organization.is_active:
                        raise IAMAdministrationValidationError(
                            f"CUSTOM 组织必须处于启用状态: {org_code}"
                        )
                    custom_org_ids.append(organization.id)
                scope_config: dict | None = {"org_ids": custom_org_ids}
            else:
                if custom_codes:
                    raise IAMAdministrationValidationError(
                        "只有 CUSTOM 数据范围可以配置自定义组织"
                    )
                scope_config = None
            resolved.append(
                _ResolvedAuthorization(permission, scope_type, scope_config)
            )
        return tuple(resolved)

    def _require_permission(
        self,
        actor: IAMAdministrationActor,
        permission_code: str,
    ) -> None:
        if not self.permission_service.has_permission(
            actor.user_id,
            permission_code,
            actor.active_org_id,
        ):
            raise IAMAdministrationPermissionDenied(
                f"missing permission: {permission_code}"
            )

    def _require_role(self, role_id: int) -> Role:
        role = self.repository.get_role(role_id)
        if role is None:
            raise IAMEntityNotFound(f"role not found: {role_id}")
        return role

    def _reload(self, role_id: int) -> Role:
        self.repository.expire_all()
        return self._require_role(role_id)

    def _audit(
        self,
        role_id: int,
        action: str,
        actor: IAMAdministrationActor,
        payload: dict,
    ) -> None:
        self.repository.add(
            IAMAuditLog(
                entity_type="ROLE",
                entity_id=role_id,
                action=action,
                operator_id=actor.user_id,
                payload_json=payload,
            )
        )

    @classmethod
    def _snapshot(cls, role: Role) -> dict:
        scopes = {scope.permission_code: scope for scope in role.data_scopes}
        authorization = []
        for link in sorted(
            role.permission_links,
            key=lambda item: item.permission.permission_code,
        ):
            code = link.permission.permission_code
            scope = scopes.get(code)
            authorization.append(
                {
                    "permission_code": code,
                    "scope_type": scope.scope_type if scope else None,
                    "scope_config": scope.scope_config if scope else None,
                }
            )
        return {
            "role_code": role.role_code,
            "role_name": role.role_name,
            "role_type": role.role_type,
            "is_active": role.is_active,
            "authorization": authorization,
        }

    @staticmethod
    def _authorization_snapshot(
        resolved: tuple[_ResolvedAuthorization, ...],
    ) -> list[dict]:
        return [
            {
                "permission_code": item.permission.permission_code,
                "scope_type": item.scope_type.value,
                "scope_config": item.scope_config,
            }
            for item in sorted(
                resolved,
                key=lambda entry: entry.permission.permission_code,
            )
        ]

    @staticmethod
    def _required_name(value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise IAMAdministrationValidationError("角色名称不能为空")
        return normalized

    @staticmethod
    def _optional_text(value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None
