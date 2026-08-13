"""Permission-checked IAM organization administration use cases."""

from __future__ import annotations

import re
from dataclasses import dataclass

from sqlalchemy.exc import IntegrityError

from .authorization import PermissionService
from .models import IAMAuditLog, Organization
from .repository import IAMRepository
from .service import DuplicateIAMCode, IAMEntityNotFound, IAMError


class IAMAdministrationPermissionDenied(IAMError):
    """Raised when the actor lacks a stable IAM management permission."""


class IAMAdministrationValidationError(IAMError):
    """Raised when an IAM management command is invalid."""


class IAMAdministrationConflict(IAMError):
    """Raised when relationships prevent an IAM management action."""


@dataclass(frozen=True)
class IAMAdministrationActor:
    user_id: int
    active_org_id: int


@dataclass(frozen=True)
class CreateOrganizationCommand:
    org_code: str
    org_name: str
    org_type: str | None = None
    parent_code: str | None = None
    sort_no: int = 0


@dataclass(frozen=True)
class UpdateOrganizationCommand:
    org_name: str
    org_type: str | None
    parent_code: str | None
    sort_no: int


class OrganizationAdministrationService:
    VIEW_PERMISSION = "system:org:view"
    CREATE_PERMISSION = "system:org:create"
    UPDATE_PERMISSION = "system:org:update"
    STATUS_PERMISSION = "system:org:status"
    DELETE_PERMISSION = "system:org:delete"
    CODE_PATTERN = re.compile(r"^[A-Z][A-Z0-9_]{1,79}$")

    def __init__(
        self,
        repository: IAMRepository,
        permission_service: PermissionService,
    ) -> None:
        self.repository = repository
        self.permission_service = permission_service

    def list_organizations(
        self,
        actor: IAMAdministrationActor,
    ) -> list[Organization]:
        self._require_permission(actor, self.VIEW_PERMISSION)
        organizations = self.repository.list_organizations()
        visible_ids = self.permission_service.organization_scope_ids(
            actor.user_id,
            self.VIEW_PERMISSION,
            actor.active_org_id,
        )
        if visible_ids is None:
            return organizations
        return [item for item in organizations if item.id in visible_ids]

    def get_organization(
        self,
        organization_id: int,
        actor: IAMAdministrationActor,
    ) -> Organization:
        self._require_permission(actor, self.VIEW_PERMISSION)
        organization = self._require_organization(organization_id)
        visible_ids = self.permission_service.organization_scope_ids(
            actor.user_id,
            self.VIEW_PERMISSION,
            actor.active_org_id,
        )
        if visible_ids is not None and organization.id not in visible_ids:
            raise IAMAdministrationPermissionDenied("当前数据范围不可查看该组织")
        return organization

    def create(
        self,
        command: CreateOrganizationCommand,
        actor: IAMAdministrationActor,
    ) -> Organization:
        self._require_permission(actor, self.CREATE_PERMISSION)
        org_code = command.org_code.strip().upper()
        org_name = self._required_name(command.org_name)
        if not self.CODE_PATTERN.fullmatch(org_code):
            raise IAMAdministrationValidationError(
                "组织编码须以字母开头，且只能包含大写字母、数字和下划线"
            )
        if self.repository.get_organization_by_code(org_code) is not None:
            raise DuplicateIAMCode(f"organization already exists: {org_code}")
        parent = self._optional_parent(command.parent_code)
        if parent is not None and not parent.is_active:
            raise IAMAdministrationValidationError("不能在已停用组织下新增子组织")
        organization = Organization(
            parent_id=parent.id if parent else None,
            org_code=org_code,
            org_name=org_name,
            org_type=self._optional_text(command.org_type),
            org_path=(f"{parent.org_path}/{org_code}" if parent else f"/{org_code}"),
            sort_no=command.sort_no,
        )
        self.repository.add(organization)
        self.repository.flush()
        self._audit(
            organization.id,
            "CREATE",
            actor,
            {"after": self._snapshot(organization)},
        )
        self.repository.commit()
        self.repository.refresh(organization)
        return organization

    def update(
        self,
        organization_id: int,
        command: UpdateOrganizationCommand,
        actor: IAMAdministrationActor,
    ) -> Organization:
        self._require_permission(actor, self.UPDATE_PERMISSION)
        organization = self._require_organization(organization_id)
        before = self._snapshot(organization)
        parent = self._optional_parent(command.parent_code)
        if parent is not None:
            if parent.id == organization.id or parent.org_path.startswith(
                f"{organization.org_path}/"
            ):
                raise IAMAdministrationValidationError(
                    "组织父级不能是自身或自身的下级组织"
                )
            if not parent.is_active:
                raise IAMAdministrationValidationError("不能移动到已停用组织下")
        new_path = (
            f"{parent.org_path}/{organization.org_code}"
            if parent
            else f"/{organization.org_code}"
        )
        old_path = organization.org_path
        descendants = self.repository.list_descendant_organizations(organization)
        organization.parent_id = parent.id if parent else None
        organization.org_name = self._required_name(command.org_name)
        organization.org_type = self._optional_text(command.org_type)
        organization.sort_no = command.sort_no
        organization.org_path = new_path
        for descendant in descendants:
            descendant.org_path = f"{new_path}{descendant.org_path[len(old_path):]}"
        self._audit(
            organization.id,
            "UPDATE",
            actor,
            {"before": before, "after": self._snapshot(organization)},
        )
        self.repository.commit()
        self.repository.refresh(organization)
        return organization

    def set_active(
        self,
        organization_id: int,
        is_active: bool,
        actor: IAMAdministrationActor,
    ) -> Organization:
        self._require_permission(actor, self.STATUS_PERMISSION)
        organization = self._require_organization(organization_id)
        if organization.is_active == is_active:
            return organization
        if is_active:
            parent = (
                self.repository.get_organization(organization.parent_id)
                if organization.parent_id is not None
                else None
            )
            if parent is not None and not parent.is_active:
                raise IAMAdministrationConflict("请先启用父组织")
        else:
            active_descendants = [
                item
                for item in self.repository.list_descendant_organizations(organization)
                if item.is_active
            ]
            if active_descendants:
                raise IAMAdministrationConflict("请先停用全部下级组织")
        before = organization.is_active
        organization.is_active = is_active
        self._audit(
            organization.id,
            "ENABLE" if is_active else "DISABLE",
            actor,
            {"before": {"is_active": before}, "after": {"is_active": is_active}},
        )
        self.repository.commit()
        self.repository.refresh(organization)
        return organization

    def delete(
        self,
        organization_id: int,
        actor: IAMAdministrationActor,
    ) -> None:
        self._require_permission(actor, self.DELETE_PERMISSION)
        organization = self._require_organization(organization_id)
        if self.repository.count_organization_children(organization.id):
            raise IAMAdministrationConflict("组织存在下级组织，不能删除")
        if self.repository.count_organization_memberships(organization.id):
            raise IAMAdministrationConflict("组织存在成员关系，不能删除")
        snapshot = self._snapshot(organization)
        self.repository.delete(organization)
        self._audit(
            organization.id,
            "DELETE",
            actor,
            {"before": snapshot},
        )
        try:
            self.repository.commit()
        except IntegrityError as error:
            raise IAMAdministrationConflict(
                "组织已被业务数据引用，只能停用，不能删除"
            ) from error

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

    def _require_organization(self, organization_id: int) -> Organization:
        organization = self.repository.get_organization(organization_id)
        if organization is None:
            raise IAMEntityNotFound(f"organization not found: {organization_id}")
        return organization

    def _optional_parent(self, parent_code: str | None) -> Organization | None:
        normalized = self._optional_text(parent_code)
        if normalized is None:
            return None
        parent = self.repository.get_organization_by_code(normalized.upper())
        if parent is None:
            raise IAMEntityNotFound(f"parent organization not found: {normalized}")
        return parent

    def _audit(
        self,
        entity_id: int,
        action: str,
        actor: IAMAdministrationActor,
        payload: dict,
    ) -> None:
        self.repository.add(
            IAMAuditLog(
                entity_type="ORGANIZATION",
                entity_id=entity_id,
                action=action,
                operator_id=actor.user_id,
                payload_json=payload,
            )
        )

    @staticmethod
    def _required_name(value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise IAMAdministrationValidationError("组织名称不能为空")
        return normalized

    @staticmethod
    def _optional_text(value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None

    @staticmethod
    def _snapshot(organization: Organization) -> dict:
        return {
            "org_code": organization.org_code,
            "org_name": organization.org_name,
            "org_type": organization.org_type,
            "parent_id": organization.parent_id,
            "org_path": organization.org_path,
            "sort_no": organization.sort_no,
            "is_active": organization.is_active,
        }
