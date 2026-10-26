"""Permission-checked permission dictionary and IAM audit use cases."""

from __future__ import annotations

import re
from dataclasses import dataclass

from .admin_service import (
    IAMAdministrationActor,
    IAMAdministrationConflict,
    IAMAdministrationPermissionDenied,
    IAMAdministrationValidationError,
)
from .authorization import PermissionService
from .models import IAMAuditLog, Permission
from .permission_catalog import BUILT_IN_PERMISSION_CODES
from .repository import IAMRepository
from .service import DuplicateIAMCode, IAMEntityNotFound


@dataclass(frozen=True)
class CreatePermissionCommand:
    permission_code: str
    permission_name: str
    resource_type: str | None = None
    description: str | None = None


@dataclass(frozen=True)
class UpdatePermissionCommand:
    permission_name: str
    resource_type: str | None = None
    description: str | None = None


@dataclass(frozen=True)
class IAMAuditFilter:
    entity_type: str | None = None
    entity_id: int | None = None
    action: str | None = None
    operator_username: str | None = None
    offset: int = 0
    limit: int = 100


class _PermissionCheckedService:
    def __init__(
        self,
        repository: IAMRepository,
        permission_service: PermissionService,
    ) -> None:
        self.repository = repository
        self.permission_service = permission_service

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

    def _audit(
        self,
        entity_type: str,
        entity_id: int,
        action: str,
        actor: IAMAdministrationActor,
        payload: dict,
    ) -> None:
        self.repository.add(
            IAMAuditLog(
                entity_type=entity_type,
                entity_id=entity_id,
                action=action,
                operator_id=actor.user_id,
                payload_json=payload,
            )
        )

    @staticmethod
    def _required_name(value: str, field_name: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise IAMAdministrationValidationError(f"{field_name}不能为空")
        return normalized

    @staticmethod
    def _optional_text(value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None


class PermissionDictionaryService(_PermissionCheckedService):
    VIEW_PERMISSION = "system:permission:view"
    CREATE_PERMISSION = "system:permission:create"
    UPDATE_PERMISSION = "system:permission:update"
    DELETE_PERMISSION = "system:permission:delete"
    CODE_PATTERN = re.compile(
        r"^[a-z][a-z0-9_.-]*(?::[a-z][a-z0-9_.-]*)+$"
    )

    def list_permissions(self, actor: IAMAdministrationActor) -> list[Permission]:
        self._require_permission(actor, self.VIEW_PERMISSION)
        return self.repository.list_permissions()

    def get_permission(
        self,
        permission_id: int,
        actor: IAMAdministrationActor,
    ) -> Permission:
        self._require_permission(actor, self.VIEW_PERMISSION)
        return self._require_dictionary_entry(permission_id)

    def create(
        self,
        command: CreatePermissionCommand,
        actor: IAMAdministrationActor,
    ) -> Permission:
        self._require_permission(actor, self.CREATE_PERMISSION)
        permission_code = command.permission_code.strip().lower()
        if not self.CODE_PATTERN.fullmatch(permission_code):
            raise IAMAdministrationValidationError(
                "权限编码须为小写命名空间格式，例如 resource:action"
            )
        if self.repository.get_permission_by_code(permission_code) is not None:
            raise DuplicateIAMCode(f"permission already exists: {permission_code}")
        permission = Permission(
            permission_code=permission_code,
            permission_name=self._required_name(
                command.permission_name,
                "权限名称",
            ),
            resource_type=self._optional_text(command.resource_type),
            description=self._optional_text(command.description),
        )
        self.repository.add(permission)
        self.repository.flush()
        self._audit(
            "PERMISSION",
            permission.id,
            "CREATE",
            actor,
            {"after": self._snapshot(permission)},
        )
        self.repository.commit()
        return self._reload(permission.id)

    def update(
        self,
        permission_id: int,
        command: UpdatePermissionCommand,
        actor: IAMAdministrationActor,
    ) -> Permission:
        self._require_permission(actor, self.UPDATE_PERMISSION)
        permission = self._require_dictionary_entry(permission_id)
        before = self._snapshot(permission)
        permission.permission_name = self._required_name(
            command.permission_name,
            "权限名称",
        )
        permission.resource_type = self._optional_text(command.resource_type)
        permission.description = self._optional_text(command.description)
        self._audit(
            "PERMISSION",
            permission.id,
            "UPDATE",
            actor,
            {"before": before, "after": self._snapshot(permission)},
        )
        self.repository.commit()
        return self._reload(permission.id)

    def delete(
        self,
        permission_id: int,
        actor: IAMAdministrationActor,
    ) -> None:
        self._require_permission(actor, self.DELETE_PERMISSION)
        permission = self._require_dictionary_entry(permission_id)
        if permission.permission_code in BUILT_IN_PERMISSION_CODES:
            raise IAMAdministrationConflict("内置稳定权限不能删除")
        if permission.role_links or self.repository.count_permission_data_scopes(
            permission.permission_code
        ):
            raise IAMAdministrationConflict(
                "权限已被角色授权引用，撤销角色授权后才能删除"
            )
        before = self._snapshot(permission)
        self.repository.delete(permission)
        self._audit("PERMISSION", permission.id, "DELETE", actor, {"before": before})
        self.repository.commit()

    def _require_dictionary_entry(self, permission_id: int) -> Permission:
        permission = self.repository.get_permission(permission_id)
        if permission is None:
            raise IAMEntityNotFound(f"permission not found: {permission_id}")
        return permission

    def _reload(self, permission_id: int) -> Permission:
        self.repository.expire_all()
        return self._require_dictionary_entry(permission_id)

    @staticmethod
    def _snapshot(permission: Permission) -> dict:
        return {
            "permission_code": permission.permission_code,
            "permission_name": permission.permission_name,
            "resource_type": permission.resource_type,
            "description": permission.description,
        }


class IAMAuditQueryService(_PermissionCheckedService):
    VIEW_PERMISSION = "system:audit:view"

    def list_logs(
        self,
        command: IAMAuditFilter,
        actor: IAMAdministrationActor,
    ) -> list[IAMAuditLog]:
        self._require_permission(actor, self.VIEW_PERMISSION)
        if command.offset < 0:
            raise IAMAdministrationValidationError("offset 不能小于 0")
        if command.limit < 1 or command.limit > 200:
            raise IAMAdministrationValidationError("limit 必须在 1 到 200 之间")
        return self.repository.list_iam_audit_logs_filtered(
            entity_type=self._normalized_upper(command.entity_type),
            entity_id=command.entity_id,
            action=self._normalized_upper(command.action),
            operator_username=self._normalized_lower(command.operator_username),
            offset=command.offset,
            limit=command.limit,
        )

    @staticmethod
    def _normalized_upper(value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip().upper()
        return normalized or None

    @staticmethod
    def _normalized_lower(value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip().lower()
        return normalized or None
