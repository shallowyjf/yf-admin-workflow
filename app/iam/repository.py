"""Repository for IAM and authorization entities."""

from dataclasses import dataclass

from sqlalchemy import asc, desc, func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.core.pagination import PageResult

from .models import (
    IAMAuditLog,
    Organization,
    Permission,
    Position,
    Role,
    RoleDataScope,
    RolePermission,
    Tenant,
    User,
    UserOrganization,
    UserOrganizationPosition,
    UserOrganizationRole,
)


@dataclass(frozen=True)
class IAMListQuery:
    keyword: str | None = None
    is_active: bool | None = None
    sort_by: str = "code"
    sort_direction: str = "asc"
    page: int = 1
    page_size: int = 20


class IAMRepository:
    def __init__(self, session: Session, tenant_id: int | None = None) -> None:
        self.session = session
        self.tenant_id = tenant_id

    def require_tenant_id(self) -> int:
        return self.tenant_id or 1

    def get_tenant_by_code(self, tenant_code: str) -> Tenant | None:
        return self.session.scalar(
            select(Tenant).where(Tenant.tenant_code == tenant_code)
        )

    def get_tenant(self, tenant_id: int) -> Tenant | None:
        return self.session.get(Tenant, tenant_id)

    def list_tenants(self) -> list[Tenant]:
        return list(
            self.session.scalars(select(Tenant).order_by(Tenant.tenant_code))
        )

    def _tenant_conditions(self, model) -> list:
        if self.tenant_id is None or not hasattr(model, "tenant_id"):
            return []
        return [model.tenant_id == self.tenant_id]

    def add(self, entity: object) -> None:
        if (
            isinstance(entity, (IAMAuditLog, Organization, Position, Role, User))
            and entity.tenant_id is None
        ):
            entity.tenant_id = self.require_tenant_id()
        self.session.add(entity)

    def commit(self) -> None:
        try:
            self.session.commit()
        except Exception:
            self.session.rollback()
            raise

    def refresh(self, entity: object) -> None:
        self.session.refresh(entity)

    def expire_all(self) -> None:
        self.session.expire_all()

    def flush(self) -> None:
        self.session.flush()

    def delete(self, entity: object) -> None:
        self.session.delete(entity)

    def get_user_by_username(self, username: str) -> User | None:
        return self.session.scalar(
            select(User).where(
                User.username == username,
                *self._tenant_conditions(User),
            )
        )

    def get_user(self, user_id: int) -> User | None:
        return self.session.scalar(
            select(User)
            .where(User.id == user_id, *self._tenant_conditions(User))
            .options(
                selectinload(User.memberships).selectinload(
                    UserOrganization.organization
                ),
                selectinload(User.memberships)
                .selectinload(UserOrganization.role_links)
                .selectinload(UserOrganizationRole.role),
                selectinload(User.memberships)
                .selectinload(UserOrganization.position_links)
                .selectinload(UserOrganizationPosition.position),
            )
        )

    def get_organization_by_code(self, org_code: str) -> Organization | None:
        return self.session.scalar(
            select(Organization).where(
                Organization.org_code == org_code,
                *self._tenant_conditions(Organization),
            )
        )

    def get_organization(self, organization_id: int) -> Organization | None:
        return self.session.scalar(
            select(Organization).where(
                Organization.id == organization_id,
                *self._tenant_conditions(Organization),
            )
        )

    def list_descendant_organizations(
        self,
        organization: Organization,
    ) -> list[Organization]:
        return list(
            self.session.scalars(
                select(Organization)
                .where(
                    Organization.org_path.like(f"{organization.org_path}/%"),
                    *self._tenant_conditions(Organization),
                )
                .order_by(Organization.org_path)
            )
        )

    def count_organization_children(self, organization_id: int) -> int:
        return int(
            self.session.scalar(
                select(func.count())
                .select_from(Organization)
                .where(
                    Organization.parent_id == organization_id,
                    *self._tenant_conditions(Organization),
                )
            )
            or 0
        )

    def count_organization_memberships(self, organization_id: int) -> int:
        return int(
            self.session.scalar(
                select(func.count())
                .select_from(UserOrganization)
                .where(UserOrganization.org_id == organization_id)
            )
            or 0
        )

    def list_iam_audit_logs(
        self,
        entity_type: str,
        entity_id: int,
    ) -> list[IAMAuditLog]:
        return list(
            self.session.scalars(
                select(IAMAuditLog)
                .where(
                    IAMAuditLog.entity_type == entity_type,
                    IAMAuditLog.entity_id == entity_id,
                    *self._tenant_conditions(IAMAuditLog),
                )
                .order_by(IAMAuditLog.id)
            )
        )

    def list_iam_audit_logs_filtered(
        self,
        *,
        entity_type: str | None = None,
        entity_id: int | None = None,
        action: str | None = None,
        operator_username: str | None = None,
        offset: int = 0,
        limit: int = 100,
    ) -> list[IAMAuditLog]:
        statement = (
            select(IAMAuditLog)
            .where(*self._tenant_conditions(IAMAuditLog))
            .options(selectinload(IAMAuditLog.operator))
        )
        if entity_type is not None:
            statement = statement.where(IAMAuditLog.entity_type == entity_type)
        if entity_id is not None:
            statement = statement.where(IAMAuditLog.entity_id == entity_id)
        if action is not None:
            statement = statement.where(IAMAuditLog.action == action)
        if operator_username is not None:
            statement = statement.join(
                User,
                User.id == IAMAuditLog.operator_id,
            ).where(User.username == operator_username)
        return list(
            self.session.scalars(
                statement.order_by(
                    IAMAuditLog.created_at.desc(),
                    IAMAuditLog.id.desc(),
                )
                .offset(offset)
                .limit(limit)
            )
        )

    def get_role_by_code(self, role_code: str) -> Role | None:
        return self.session.scalar(
            select(Role).where(
                Role.role_code == role_code,
                *self._tenant_conditions(Role),
            )
        )

    def get_role(self, role_id: int) -> Role | None:
        return self.session.scalar(
            select(Role)
            .where(Role.id == role_id, *self._tenant_conditions(Role))
            .options(
                selectinload(Role.permission_links).selectinload(
                    RolePermission.permission
                ),
                selectinload(Role.data_scopes),
            )
        )

    def get_position_by_code(self, position_code: str) -> Position | None:
        return self.session.scalar(
            select(Position).where(
                Position.position_code == position_code,
                *self._tenant_conditions(Position),
            )
        )

    def get_position(self, position_id: int) -> Position | None:
        return self.session.scalar(
            select(Position)
            .where(Position.id == position_id, *self._tenant_conditions(Position))
            .options(selectinload(Position.membership_links))
        )

    def get_permission_by_code(self, permission_code: str) -> Permission | None:
        return self.session.scalar(
            select(Permission).where(Permission.permission_code == permission_code)
        )

    def get_permission(self, permission_id: int) -> Permission | None:
        return self.session.scalar(
            select(Permission)
            .where(Permission.id == permission_id)
            .options(selectinload(Permission.role_links))
        )

    def count_permission_data_scopes(self, permission_code: str) -> int:
        return int(
            self.session.scalar(
                select(func.count())
                .select_from(RoleDataScope)
                .where(RoleDataScope.permission_code == permission_code)
            )
            or 0
        )

    def get_membership(self, user_id: int, org_id: int) -> UserOrganization | None:
        return self.session.scalar(
            select(UserOrganization)
            .join(User, User.id == UserOrganization.user_id)
            .join(Organization, Organization.id == UserOrganization.org_id)
            .where(
                UserOrganization.user_id == user_id,
                UserOrganization.org_id == org_id,
                User.tenant_id == Organization.tenant_id,
                *self._tenant_conditions(User),
            )
            .options(
                selectinload(UserOrganization.role_links).selectinload(
                    UserOrganizationRole.role
                ),
                selectinload(UserOrganization.position_links).selectinload(
                    UserOrganizationPosition.position
                ),
            )
        )

    def get_role_link(
        self, membership_id: int, role_id: int
    ) -> UserOrganizationRole | None:
        return self.session.scalar(
            select(UserOrganizationRole).where(
                UserOrganizationRole.user_org_id == membership_id,
                UserOrganizationRole.role_id == role_id,
            )
        )

    def get_position_link(
        self, membership_id: int, position_id: int
    ) -> UserOrganizationPosition | None:
        return self.session.scalar(
            select(UserOrganizationPosition).where(
                UserOrganizationPosition.user_org_id == membership_id,
                UserOrganizationPosition.position_id == position_id,
            )
        )

    def get_role_permission(
        self, role_id: int, permission_id: int
    ) -> RolePermission | None:
        return self.session.scalar(
            select(RolePermission).where(
                RolePermission.role_id == role_id,
                RolePermission.permission_id == permission_id,
            )
        )

    def get_role_data_scope(
        self, role_id: int, permission_code: str
    ) -> RoleDataScope | None:
        return self.session.scalar(
            select(RoleDataScope).where(
                RoleDataScope.role_id == role_id,
                RoleDataScope.permission_code == permission_code,
            )
        )

    def list_authorized_role_ids(
        self,
        user_id: int,
        permission_code: str,
        active_org_id: int,
    ) -> list[int]:
        statement = (
            select(Role.id)
            .join(RolePermission, RolePermission.role_id == Role.id)
            .join(Permission, Permission.id == RolePermission.permission_id)
            .join(UserOrganizationRole, UserOrganizationRole.role_id == Role.id)
            .join(
                UserOrganization,
                UserOrganization.id == UserOrganizationRole.user_org_id,
            )
            .join(User, User.id == UserOrganization.user_id)
            .join(Organization, Organization.id == UserOrganization.org_id)
            .where(
                User.id == user_id,
                User.is_active.is_(True),
                User.tenant_id == Organization.tenant_id,
                User.tenant_id == Role.tenant_id,
                *self._tenant_conditions(User),
                UserOrganization.org_id == active_org_id,
                UserOrganization.is_active.is_(True),
                Organization.is_active.is_(True),
                Role.is_active.is_(True),
                Permission.permission_code == permission_code,
            )
            .distinct()
        )
        return list(self.session.scalars(statement))

    def list_effective_permission_codes(
        self,
        user_id: int,
        active_org_id: int,
    ) -> set[str]:
        statement = (
            select(Permission.permission_code)
            .join(RolePermission, RolePermission.permission_id == Permission.id)
            .join(Role, Role.id == RolePermission.role_id)
            .join(UserOrganizationRole, UserOrganizationRole.role_id == Role.id)
            .join(
                UserOrganization,
                UserOrganization.id == UserOrganizationRole.user_org_id,
            )
            .join(User, User.id == UserOrganization.user_id)
            .join(Organization, Organization.id == UserOrganization.org_id)
            .where(
                User.id == user_id,
                User.is_active.is_(True),
                User.tenant_id == Organization.tenant_id,
                User.tenant_id == Role.tenant_id,
                *self._tenant_conditions(User),
                UserOrganization.org_id == active_org_id,
                UserOrganization.is_active.is_(True),
                Organization.is_active.is_(True),
                Role.is_active.is_(True),
            )
            .distinct()
        )
        return set(self.session.scalars(statement))

    def list_role_data_scopes(
        self,
        role_ids: list[int],
        permission_code: str,
    ) -> list[RoleDataScope]:
        if not role_ids:
            return []
        return list(
            self.session.scalars(
                select(RoleDataScope).where(
                    RoleDataScope.role_id.in_(role_ids),
                    RoleDataScope.permission_code == permission_code,
                )
            )
        )

    def list_active_descendant_org_ids(self, org_id: int) -> set[int]:
        organization = self.session.get(Organization, org_id)
        if (
            organization is None
            or not organization.is_active
            or (self.tenant_id is not None and organization.tenant_id != self.tenant_id)
        ):
            return set()
        descendant_path = f"{organization.org_path}/%"
        return set(
            self.session.scalars(
                select(Organization.id).where(
                    Organization.is_active.is_(True),
                    *self._tenant_conditions(Organization),
                    (
                        (Organization.id == org_id)
                        | Organization.org_path.like(descendant_path)
                    ),
                )
            )
        )

    def get_active_user_id(self, user_id: int) -> int | None:
        return self.session.scalar(
            select(User.id).where(
                User.id == user_id,
                User.is_active.is_(True),
                *self._tenant_conditions(User),
            )
        )

    def list_active_user_ids_by_organization(self, org_id: int) -> set[int]:
        return set(
            self.session.scalars(
                select(User.id)
                .join(UserOrganization, UserOrganization.user_id == User.id)
                .join(Organization, Organization.id == UserOrganization.org_id)
                .where(
                    User.is_active.is_(True),
                    User.tenant_id == Organization.tenant_id,
                    *self._tenant_conditions(User),
                    UserOrganization.is_active.is_(True),
                    Organization.is_active.is_(True),
                    Organization.id == org_id,
                )
                .distinct()
            )
        )

    def list_active_user_ids_by_role(
        self,
        role_code: str,
        org_id: int | None = None,
    ) -> set[int]:
        statement = (
            select(User.id)
            .join(UserOrganization, UserOrganization.user_id == User.id)
            .join(Organization, Organization.id == UserOrganization.org_id)
            .join(
                UserOrganizationRole,
                UserOrganizationRole.user_org_id == UserOrganization.id,
            )
            .join(Role, Role.id == UserOrganizationRole.role_id)
            .where(
                User.is_active.is_(True),
                User.tenant_id == Organization.tenant_id,
                User.tenant_id == Role.tenant_id,
                *self._tenant_conditions(User),
                UserOrganization.is_active.is_(True),
                Organization.is_active.is_(True),
                Role.is_active.is_(True),
                Role.role_code == role_code,
            )
            .distinct()
        )
        if org_id is not None:
            statement = statement.where(Organization.id == org_id)
        return set(self.session.scalars(statement))

    def list_active_user_ids_by_position(
        self,
        position_code: str,
        org_id: int,
    ) -> set[int]:
        statement = (
            select(User.id)
            .join(UserOrganization, UserOrganization.user_id == User.id)
            .join(Organization, Organization.id == UserOrganization.org_id)
            .join(
                UserOrganizationPosition,
                UserOrganizationPosition.user_org_id == UserOrganization.id,
            )
            .join(Position, Position.id == UserOrganizationPosition.position_id)
            .where(
                User.is_active.is_(True),
                User.tenant_id == Organization.tenant_id,
                User.tenant_id == Position.tenant_id,
                *self._tenant_conditions(User),
                UserOrganization.is_active.is_(True),
                Organization.is_active.is_(True),
                Position.is_active.is_(True),
                Position.position_code == position_code,
                Organization.id == org_id,
            )
            .distinct()
        )
        return set(self.session.scalars(statement))

    def active_user_labels(self, user_ids: set[int]) -> dict[int, str]:
        if not user_ids:
            return {}
        return {
            user.id: user.username
            for user in self.session.scalars(
                select(User).where(
                    User.id.in_(user_ids),
                    User.is_active.is_(True),
                    *self._tenant_conditions(User),
                )
            )
        }

    def list_organizations(self) -> list[Organization]:
        return list(
            self.session.scalars(
                select(Organization)
                .where(*self._tenant_conditions(Organization))
                .order_by(Organization.sort_no, Organization.id)
            )
        )

    def list_users(self) -> list[User]:
        return list(
            self.session.scalars(
                select(User)
                .where(*self._tenant_conditions(User))
                .options(
                    selectinload(User.memberships).selectinload(
                        UserOrganization.organization
                    ),
                    selectinload(User.memberships)
                    .selectinload(UserOrganization.role_links)
                    .selectinload(UserOrganizationRole.role),
                    selectinload(User.memberships)
                    .selectinload(UserOrganization.position_links)
                    .selectinload(UserOrganizationPosition.position),
                )
                .order_by(User.username)
            )
        )

    def list_roles(self) -> list[Role]:
        return list(
            self.session.scalars(
                select(Role)
                .where(*self._tenant_conditions(Role))
                .options(
                    selectinload(Role.permission_links).selectinload(
                        RolePermission.permission
                    ),
                    selectinload(Role.data_scopes),
                )
                .order_by(Role.role_code)
            )
        )

    def list_positions(self) -> list[Position]:
        return list(
            self.session.scalars(
                select(Position)
                .where(*self._tenant_conditions(Position))
                .options(selectinload(Position.membership_links))
                .order_by(Position.position_code)
            )
        )

    def list_permissions(self) -> list[Permission]:
        return list(
            self.session.scalars(
                select(Permission)
                .options(selectinload(Permission.role_links))
                .order_by(Permission.permission_code)
            )
        )

    def search_organizations(
        self, query: IAMListQuery
    ) -> PageResult[Organization]:
        conditions = self._tenant_conditions(Organization)
        keyword = (query.keyword or "").strip()
        if keyword:
            pattern = f"%{keyword}%"
            conditions.append(
                or_(
                    Organization.org_code.ilike(pattern),
                    Organization.org_name.ilike(pattern),
                )
            )
        if query.is_active is not None:
            conditions.append(Organization.is_active.is_(query.is_active))
        sort_columns = {
            "code": Organization.org_code,
            "name": Organization.org_name,
            "sort_no": Organization.sort_no,
            "created_at": Organization.created_at,
        }
        return self._page(Organization, conditions, sort_columns, query)

    def search_users(self, query: IAMListQuery) -> PageResult[User]:
        conditions = self._tenant_conditions(User)
        keyword = (query.keyword or "").strip()
        if keyword:
            pattern = f"%{keyword}%"
            conditions.append(
                or_(User.username.ilike(pattern), User.display_name.ilike(pattern))
            )
        if query.is_active is not None:
            conditions.append(User.is_active.is_(query.is_active))
        sort_columns = {
            "code": User.username,
            "name": User.display_name,
            "created_at": User.created_at,
        }
        options = (
            selectinload(User.memberships).selectinload(
                UserOrganization.organization
            ),
            selectinload(User.memberships)
            .selectinload(UserOrganization.role_links)
            .selectinload(UserOrganizationRole.role),
            selectinload(User.memberships)
            .selectinload(UserOrganization.position_links)
            .selectinload(UserOrganizationPosition.position),
        )
        return self._page(User, conditions, sort_columns, query, options=options)

    def search_roles(self, query: IAMListQuery) -> PageResult[Role]:
        conditions = self._tenant_conditions(Role)
        keyword = (query.keyword or "").strip()
        if keyword:
            pattern = f"%{keyword}%"
            conditions.append(
                or_(Role.role_code.ilike(pattern), Role.role_name.ilike(pattern))
            )
        if query.is_active is not None:
            conditions.append(Role.is_active.is_(query.is_active))
        sort_columns = {
            "code": Role.role_code,
            "name": Role.role_name,
            "created_at": Role.created_at,
        }
        options = (
            selectinload(Role.permission_links).selectinload(
                RolePermission.permission
            ),
            selectinload(Role.data_scopes),
        )
        return self._page(Role, conditions, sort_columns, query, options=options)

    def _page(
        self,
        model,
        conditions: list,
        sort_columns: dict,
        query: IAMListQuery,
        *,
        options: tuple = (),
    ) -> PageResult:
        sort_column = sort_columns.get(query.sort_by, sort_columns["code"])
        order = asc(sort_column) if query.sort_direction == "asc" else desc(sort_column)
        total = self.session.scalar(
            select(func.count(model.id)).where(*conditions)
        ) or 0
        statement = (
            select(model)
            .where(*conditions)
            .order_by(order, model.id)
            .offset((query.page - 1) * query.page_size)
            .limit(query.page_size)
        )
        if options:
            statement = statement.options(*options)
        return PageResult(
            list(self.session.scalars(statement)),
            total,
            query.page,
            query.page_size,
        )
