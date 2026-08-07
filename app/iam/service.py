"""IAM use cases for organizations and user memberships."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from .authorization import DataScopeType
from .models import (
    Organization,
    Permission,
    Position,
    Role,
    RoleDataScope,
    RolePermission,
    User,
    UserOrganization,
    UserOrganizationPosition,
    UserOrganizationRole,
)
from .repository import IAMRepository


class IAMError(Exception):
    """Base class for IAM domain errors."""


class IAMEntityNotFound(IAMError):
    """Raised when a referenced IAM entity does not exist."""


class DuplicateIAMRelation(IAMError):
    """Raised when an IAM relationship already exists."""


class DuplicateIAMCode(IAMError):
    """Raised when a stable username or code already exists."""


@dataclass
class OrganizationTreeNode:
    org_code: str
    org_name: str
    org_type: str | None
    children: list[OrganizationTreeNode] = field(default_factory=list)


class IAMService:
    def __init__(self, repository: IAMRepository) -> None:
        self.repository = repository

    def create_user(
        self,
        username: str,
        display_name: str,
        password_hash: str,
        phone: str | None = None,
    ) -> User:
        if self.repository.get_user_by_username(username):
            raise DuplicateIAMCode(f"username already exists: {username}")
        user = User(
            username=username,
            display_name=display_name,
            password_hash=password_hash,
            phone=phone,
        )
        return self._save(user)

    def set_password_hash(self, username: str, password_hash: str) -> User:
        user = self._require_user(username)
        user.password_hash = password_hash
        self.repository.commit()
        self.repository.refresh(user)
        return user

    def create_organization(
        self,
        org_code: str,
        org_name: str,
        org_type: str | None = None,
        parent_code: str | None = None,
        sort_no: int = 0,
    ) -> Organization:
        if self.repository.get_organization_by_code(org_code):
            raise DuplicateIAMCode(f"organization already exists: {org_code}")
        parent = None
        if parent_code:
            parent = self._require_organization(parent_code)
        org_path = f"{parent.org_path}/{org_code}" if parent else f"/{org_code}"
        organization = Organization(
            parent_id=parent.id if parent else None,
            org_code=org_code,
            org_name=org_name,
            org_type=org_type,
            org_path=org_path,
            sort_no=sort_no,
        )
        return self._save(organization)

    def create_role(
        self,
        role_code: str,
        role_name: str,
        role_type: str | None = None,
    ) -> Role:
        if self.repository.get_role_by_code(role_code):
            raise DuplicateIAMCode(f"role already exists: {role_code}")
        return self._save(
            Role(role_code=role_code, role_name=role_name, role_type=role_type)
        )

    def create_position(self, position_code: str, position_name: str) -> Position:
        if self.repository.get_position_by_code(position_code):
            raise DuplicateIAMCode(f"position already exists: {position_code}")
        return self._save(
            Position(position_code=position_code, position_name=position_name)
        )

    def create_permission(
        self,
        permission_code: str,
        permission_name: str,
        resource_type: str | None = None,
        description: str | None = None,
    ) -> Permission:
        if self.repository.get_permission_by_code(permission_code):
            raise DuplicateIAMCode(f"permission already exists: {permission_code}")
        return self._save(
            Permission(
                permission_code=permission_code,
                permission_name=permission_name,
                resource_type=resource_type,
                description=description,
            )
        )

    def add_user_to_organization(
        self,
        username: str,
        org_code: str,
        *,
        is_primary: bool = False,
    ) -> UserOrganization:
        user = self._require_user(username)
        organization = self._require_organization(org_code)
        if self.repository.get_membership(user.id, organization.id):
            raise DuplicateIAMRelation(f"membership already exists: {username}/{org_code}")
        membership = UserOrganization(
            user_id=user.id,
            org_id=organization.id,
            is_primary=is_primary,
            joined_at=datetime.now(),
        )
        return self._save(membership)

    def assign_role(
        self, username: str, org_code: str, role_code: str
    ) -> UserOrganizationRole:
        membership = self._require_membership(username, org_code)
        role = self._require_role(role_code)
        if self.repository.get_role_link(membership.id, role.id):
            raise DuplicateIAMRelation(
                f"role assignment already exists: {username}/{org_code}/{role_code}"
            )
        return self._save(UserOrganizationRole(user_org_id=membership.id, role_id=role.id))

    def assign_position(
        self, username: str, org_code: str, position_code: str
    ) -> UserOrganizationPosition:
        membership = self._require_membership(username, org_code)
        position = self._require_position(position_code)
        if self.repository.get_position_link(membership.id, position.id):
            raise DuplicateIAMRelation(
                "position assignment already exists: "
                f"{username}/{org_code}/{position_code}"
            )
        return self._save(
            UserOrganizationPosition(
                user_org_id=membership.id,
                position_id=position.id,
            )
        )

    def grant_permission(
        self,
        role_code: str,
        permission_code: str,
    ) -> RolePermission:
        role = self._require_role(role_code)
        permission = self._require_permission(permission_code)
        if self.repository.get_role_permission(role.id, permission.id):
            raise DuplicateIAMRelation(
                f"permission grant already exists: {role_code}/{permission_code}"
            )
        return self._save(
            RolePermission(role_id=role.id, permission_id=permission.id)
        )

    def set_role_data_scope(
        self,
        role_code: str,
        permission_code: str,
        scope_type: DataScopeType | str,
        *,
        custom_org_codes: tuple[str, ...] = (),
    ) -> RoleDataScope:
        role = self._require_role(role_code)
        self._require_permission(permission_code)
        normalized_scope = DataScopeType(scope_type)
        scope_config = None
        if normalized_scope is DataScopeType.CUSTOM:
            scope_config = {
                "org_ids": [
                    self._require_organization(org_code).id
                    for org_code in custom_org_codes
                ]
            }

        scope = self.repository.get_role_data_scope(role.id, permission_code)
        if scope is None:
            scope = RoleDataScope(
                role_id=role.id,
                permission_code=permission_code,
            )
            self.repository.add(scope)
        scope.scope_type = normalized_scope.value
        scope.scope_config = scope_config
        self.repository.commit()
        self.repository.refresh(scope)
        return scope

    def organization_tree(self) -> list[OrganizationTreeNode]:
        organizations = self.repository.list_organizations()
        nodes = {
            org.id: OrganizationTreeNode(org.org_code, org.org_name, org.org_type)
            for org in organizations
        }
        roots: list[OrganizationTreeNode] = []
        for organization in organizations:
            node = nodes[organization.id]
            if organization.parent_id is None:
                roots.append(node)
            else:
                nodes[organization.parent_id].children.append(node)
        return roots

    def list_organizations(self) -> list[Organization]:
        return self.repository.list_organizations()

    def list_users(self) -> list[User]:
        return self.repository.list_users()

    def list_roles(self) -> list[Role]:
        return self.repository.list_roles()

    def list_positions(self) -> list[Position]:
        return self.repository.list_positions()

    def list_permissions(self) -> list[Permission]:
        return self.repository.list_permissions()

    def active_user_labels(self, user_ids: set[int]) -> dict[int, str]:
        return self.repository.active_user_labels(user_ids)

    def get_user(self, username: str) -> User | None:
        return self.repository.get_user_by_username(username)

    def get_organization(self, org_code: str) -> Organization | None:
        return self.repository.get_organization_by_code(org_code)

    def get_role(self, role_code: str) -> Role | None:
        return self.repository.get_role_by_code(role_code)

    def get_position(self, position_code: str) -> Position | None:
        return self.repository.get_position_by_code(position_code)

    def get_permission(self, permission_code: str) -> Permission | None:
        return self.repository.get_permission_by_code(permission_code)

    def get_membership(
        self, username: str, org_code: str
    ) -> UserOrganization | None:
        user = self.get_user(username)
        organization = self.get_organization(org_code)
        if user is None or organization is None:
            return None
        return self.repository.get_membership(user.id, organization.id)

    def _require_user(self, username: str) -> User:
        user = self.get_user(username)
        if user is None:
            raise IAMEntityNotFound(f"user not found: {username}")
        return user

    def _require_organization(self, org_code: str) -> Organization:
        organization = self.get_organization(org_code)
        if organization is None:
            raise IAMEntityNotFound(f"organization not found: {org_code}")
        return organization

    def _require_role(self, role_code: str) -> Role:
        role = self.get_role(role_code)
        if role is None:
            raise IAMEntityNotFound(f"role not found: {role_code}")
        return role

    def _require_position(self, position_code: str) -> Position:
        position = self.get_position(position_code)
        if position is None:
            raise IAMEntityNotFound(f"position not found: {position_code}")
        return position

    def _require_permission(self, permission_code: str) -> Permission:
        permission = self.get_permission(permission_code)
        if permission is None:
            raise IAMEntityNotFound(f"permission not found: {permission_code}")
        return permission

    def _require_membership(self, username: str, org_code: str) -> UserOrganization:
        membership = self.get_membership(username, org_code)
        if membership is None:
            raise IAMEntityNotFound(f"membership not found: {username}/{org_code}")
        return membership

    def _save(self, entity):
        self.repository.add(entity)
        self.repository.commit()
        self.repository.refresh(entity)
        return entity
