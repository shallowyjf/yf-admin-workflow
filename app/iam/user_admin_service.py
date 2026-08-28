"""Permission-checked user lifecycle and organization membership use cases."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from app.auth.security import PasswordHasher

from .admin_service import (
    IAMAdministrationActor,
    IAMAdministrationConflict,
    IAMAdministrationPermissionDenied,
    IAMAdministrationValidationError,
)
from .authorization import PermissionService
from .models import (
    IAMAuditLog,
    Organization,
    Position,
    Role,
    User,
    UserOrganization,
    UserOrganizationPosition,
    UserOrganizationRole,
)
from .repository import IAMRepository
from .service import DuplicateIAMCode, IAMEntityNotFound


class SessionRevocationPort(Protocol):
    def revoke_user_sessions(self, user_id: int) -> None: ...


@dataclass(frozen=True)
class CreateUserCommand:
    username: str
    display_name: str
    password: str
    phone: str | None = None
    login_name: str | None = None


@dataclass(frozen=True)
class UpdateUserCommand:
    display_name: str
    phone: str | None = None


@dataclass(frozen=True)
class MembershipConfiguration:
    org_code: str
    is_primary: bool
    is_active: bool = True
    role_codes: tuple[str, ...] = ()
    position_codes: tuple[str, ...] = ()


@dataclass(frozen=True)
class _ResolvedMembership:
    command: MembershipConfiguration
    organization: Organization
    roles: tuple[Role, ...]
    positions: tuple[Position, ...]


class UserAdministrationService:
    VIEW_PERMISSION = "system:user:view"
    CREATE_PERMISSION = "system:user:create"
    UPDATE_PERMISSION = "system:user:update"
    STATUS_PERMISSION = "system:user:status"
    PASSWORD_PERMISSION = "system:user:password"
    MEMBERSHIP_PERMISSION = "system:user:membership"
    USERNAME_PATTERN = re.compile(r"^[a-z][a-z0-9_.-]{2,79}$")

    def __init__(
        self,
        repository: IAMRepository,
        permission_service: PermissionService,
        session_revocation: SessionRevocationPort,
        *,
        password_hasher: PasswordHasher | None = None,
    ) -> None:
        self.repository = repository
        self.permission_service = permission_service
        self.session_revocation = session_revocation
        self.password_hasher = password_hasher or PasswordHasher()

    def list_users(self, actor: IAMAdministrationActor) -> list[User]:
        self._require_permission(actor, self.VIEW_PERMISSION)
        return self.repository.list_users()

    def get_user(self, user_id: int, actor: IAMAdministrationActor) -> User:
        self._require_permission(actor, self.VIEW_PERMISSION)
        return self._require_user(user_id)

    def create(
        self,
        command: CreateUserCommand,
        actor: IAMAdministrationActor,
    ) -> User:
        self._require_permission(actor, self.CREATE_PERMISSION)
        username = command.username.strip().lower()
        if not self.USERNAME_PATTERN.fullmatch(username):
            raise IAMAdministrationValidationError(
                "用户名须以小写字母开头，且只能包含小写字母、数字、点、横线和下划线"
            )
        if self.repository.get_user_by_username(username) is not None:
            raise DuplicateIAMCode(f"username already exists: {username}")
        login_name = (
            command.login_name.strip().lower()
            if command.login_name
            else self._default_login_name(username)
        )
        if not self.USERNAME_PATTERN.fullmatch(login_name):
            raise IAMAdministrationValidationError(
                "登录账号须以小写字母开头，且只能包含小写字母、数字、点、横线和下划线"
            )
        if login_name == "root":
            raise IAMAdministrationValidationError("root 是平台保留登录名")
        if self.repository.get_user_by_login_name(login_name) is not None:
            raise DuplicateIAMCode(f"login name already exists: {login_name}")
        display_name = self._required_display_name(command.display_name)
        self._validate_password(command.password)
        user = User(
            username=username,
            login_name=login_name,
            display_name=display_name,
            password_hash=self.password_hasher.hash(command.password),
            phone=self._optional_text(command.phone),
        )
        self.repository.add(user)
        self.repository.flush()
        self._audit(
            user.id,
            "CREATE",
            actor,
            {"after": self._user_snapshot(user)},
        )
        self.repository.commit()
        return self._require_user(user.id)

    def _default_login_name(self, username: str) -> str:
        tenant = self.repository.get_tenant(self.repository.require_tenant_id())
        tenant_code = tenant.tenant_code if tenant is not None else "DEMO"
        if tenant_code == "DEMO":
            return username
        prefix = tenant_code[5:] if tenant_code.startswith("CITY_") else tenant_code
        return f"{prefix.lower()}.{username}"

    def update(
        self,
        user_id: int,
        command: UpdateUserCommand,
        actor: IAMAdministrationActor,
    ) -> User:
        self._require_permission(actor, self.UPDATE_PERMISSION)
        user = self._require_user(user_id)
        before = self._user_snapshot(user)
        user.display_name = self._required_display_name(command.display_name)
        user.phone = self._optional_text(command.phone)
        self._audit(
            user.id,
            "UPDATE",
            actor,
            {"before": before, "after": self._user_snapshot(user)},
        )
        self.repository.commit()
        return self._require_user(user.id)

    def set_active(
        self,
        user_id: int,
        is_active: bool,
        actor: IAMAdministrationActor,
    ) -> User:
        self._require_permission(actor, self.STATUS_PERMISSION)
        user = self._require_user(user_id)
        if user.is_active == is_active:
            return user
        if user.id == actor.user_id and not is_active:
            raise IAMAdministrationConflict("不能停用当前登录账号")
        before = user.is_active
        user.is_active = is_active
        if not is_active:
            self.session_revocation.revoke_user_sessions(user.id)
        self._audit(
            user.id,
            "ENABLE" if is_active else "DISABLE",
            actor,
            {"before": {"is_active": before}, "after": {"is_active": is_active}},
        )
        self.repository.commit()
        return self._require_user(user.id)

    def reset_password(
        self,
        user_id: int,
        new_password: str,
        actor: IAMAdministrationActor,
    ) -> None:
        self._require_permission(actor, self.PASSWORD_PERMISSION)
        user = self._require_user(user_id)
        self._validate_password(new_password)
        user.password_hash = self.password_hasher.hash(new_password)
        self.session_revocation.revoke_user_sessions(user.id)
        self._audit(
            user.id,
            "RESET_PASSWORD",
            actor,
            {"password_changed": True},
        )
        self.repository.commit()

    def replace_memberships(
        self,
        user_id: int,
        configurations: tuple[MembershipConfiguration, ...],
        actor: IAMAdministrationActor,
    ) -> User:
        self._require_permission(actor, self.MEMBERSHIP_PERMISSION)
        user = self._require_user(user_id)
        resolved = self._resolve_memberships(configurations)
        before = self._membership_snapshot(user)
        current = {membership.org_id: membership for membership in user.memberships}
        target_org_ids = {item.organization.id for item in resolved}
        for org_id, membership in current.items():
            if org_id not in target_org_ids:
                self.repository.delete(membership)
        for item in resolved:
            membership = current.get(item.organization.id)
            if membership is None:
                membership = UserOrganization(
                    user_id=user.id,
                    org_id=item.organization.id,
                    joined_at=datetime.now(),
                )
                self.repository.add(membership)
                self.repository.flush()
            membership.is_primary = item.command.is_primary
            membership.is_active = item.command.is_active
            self._replace_roles(membership, item.roles)
            self._replace_positions(membership, item.positions)
        self.repository.flush()
        self.repository.expire_all()
        refreshed = self._require_user(user.id)
        self.session_revocation.revoke_user_sessions(user.id)
        self._audit(
            user.id,
            "REPLACE_MEMBERSHIPS",
            actor,
            {"before": before, "after": self._membership_snapshot(refreshed)},
        )
        self.repository.commit()
        return self._require_user(user.id)

    def _resolve_memberships(
        self,
        configurations: tuple[MembershipConfiguration, ...],
    ) -> tuple[_ResolvedMembership, ...]:
        if not configurations:
            raise IAMAdministrationValidationError("用户至少需要一个组织成员关系")
        normalized_codes = [item.org_code.strip().upper() for item in configurations]
        if len(set(normalized_codes)) != len(normalized_codes):
            raise IAMAdministrationValidationError("组织成员关系不能重复")
        active_primary = [
            item for item in configurations if item.is_primary and item.is_active
        ]
        if len(active_primary) != 1 or any(
            item.is_primary and not item.is_active for item in configurations
        ):
            raise IAMAdministrationValidationError(
                "必须且只能配置一个启用的主组织"
            )
        resolved = []
        for command, org_code in zip(configurations, normalized_codes, strict=True):
            organization = self.repository.get_organization_by_code(org_code)
            if organization is None:
                raise IAMEntityNotFound(f"organization not found: {org_code}")
            if command.is_active and not organization.is_active:
                raise IAMAdministrationValidationError(
                    f"不能启用已停用组织的成员关系: {org_code}"
                )
            roles = self._resolve_roles(command.role_codes)
            positions = self._resolve_positions(command.position_codes)
            resolved.append(
                _ResolvedMembership(command, organization, roles, positions)
            )
        return tuple(resolved)

    def _resolve_roles(self, role_codes: tuple[str, ...]) -> tuple[Role, ...]:
        normalized = tuple(code.strip().upper() for code in role_codes if code.strip())
        if len(set(normalized)) != len(normalized):
            raise IAMAdministrationValidationError("同一组织内角色不能重复")
        roles = []
        for role_code in normalized:
            role = self.repository.get_role_by_code(role_code)
            if role is None:
                raise IAMEntityNotFound(f"role not found: {role_code}")
            if not role.is_active:
                raise IAMAdministrationValidationError(
                    f"不能绑定已停用角色: {role_code}"
                )
            roles.append(role)
        return tuple(roles)

    def _resolve_positions(
        self,
        position_codes: tuple[str, ...],
    ) -> tuple[Position, ...]:
        normalized = tuple(
            code.strip().upper() for code in position_codes if code.strip()
        )
        if len(set(normalized)) != len(normalized):
            raise IAMAdministrationValidationError("同一组织内岗位不能重复")
        positions = []
        for position_code in normalized:
            position = self.repository.get_position_by_code(position_code)
            if position is None:
                raise IAMEntityNotFound(f"position not found: {position_code}")
            if not position.is_active:
                raise IAMAdministrationValidationError(
                    f"不能绑定已停用岗位: {position_code}"
                )
            positions.append(position)
        return tuple(positions)

    def _replace_roles(
        self,
        membership: UserOrganization,
        roles: tuple[Role, ...],
    ) -> None:
        target_ids = {role.id for role in roles}
        current_ids = {link.role_id for link in membership.role_links}
        for link in list(membership.role_links):
            if link.role_id not in target_ids:
                self.repository.delete(link)
        for role in roles:
            if role.id not in current_ids:
                self.repository.add(
                    UserOrganizationRole(
                        user_org_id=membership.id,
                        role_id=role.id,
                    )
                )

    def _replace_positions(
        self,
        membership: UserOrganization,
        positions: tuple[Position, ...],
    ) -> None:
        target_ids = {position.id for position in positions}
        current_ids = {link.position_id for link in membership.position_links}
        for link in list(membership.position_links):
            if link.position_id not in target_ids:
                self.repository.delete(link)
        for position in positions:
            if position.id not in current_ids:
                self.repository.add(
                    UserOrganizationPosition(
                        user_org_id=membership.id,
                        position_id=position.id,
                    )
                )

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

    def _require_user(self, user_id: int) -> User:
        user = self.repository.get_user(user_id)
        if user is None:
            raise IAMEntityNotFound(f"user not found: {user_id}")
        return user

    def _audit(
        self,
        entity_id: int,
        action: str,
        actor: IAMAdministrationActor,
        payload: dict,
    ) -> None:
        self.repository.add(
            IAMAuditLog(
                entity_type="USER",
                entity_id=entity_id,
                action=action,
                operator_id=actor.user_id,
                payload_json=payload,
            )
        )

    @staticmethod
    def _required_display_name(value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise IAMAdministrationValidationError("用户姓名不能为空")
        return normalized

    @staticmethod
    def _optional_text(value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None

    @staticmethod
    def _validate_password(value: str) -> None:
        if len(value) < 8 or len(value) > 128:
            raise IAMAdministrationValidationError("密码长度须为 8 到 128 位")

    @staticmethod
    def _user_snapshot(user: User) -> dict:
        return {
            "username": user.username,
            "login_name": user.login_name,
            "display_name": user.display_name,
            "phone": user.phone,
            "is_active": user.is_active,
        }

    @staticmethod
    def _membership_snapshot(user: User) -> list[dict]:
        return sorted(
            (
                {
                    "org_code": membership.organization.org_code,
                    "is_primary": membership.is_primary,
                    "is_active": membership.is_active,
                    "role_codes": sorted(
                        link.role.role_code for link in membership.role_links
                    ),
                    "position_codes": sorted(
                        link.position.position_code
                        for link in membership.position_links
                    ),
                }
                for membership in user.memberships
            ),
            key=lambda item: item["org_code"],
        )
