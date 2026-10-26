"""Paged IAM queries and row-level import/export orchestration."""

from dataclasses import dataclass

from app.core.pagination import PageResult

from .admin_service import (
    CreateOrganizationCommand,
    IAMAdministrationActor,
    IAMAdministrationPermissionDenied,
    IAMAdministrationValidationError,
    OrganizationAdministrationService,
    UpdateOrganizationCommand,
)
from .authorization import PermissionService
from .repository import IAMListQuery, IAMRepository
from .role_admin_service import (
    CreateRoleCommand,
    PermissionScopeConfiguration,
    RoleAdministrationService,
    UpdateRoleCommand,
)
from .service import IAMError
from .user_admin_service import (
    CreateUserCommand,
    MembershipConfiguration,
    UpdateUserCommand,
    UserAdministrationService,
)


@dataclass(frozen=True)
class IAMImportItemResult:
    row: int
    key: str
    success: bool
    detail: str


@dataclass(frozen=True)
class IAMImportResult:
    entity: str
    items: list[IAMImportItemResult]

    @property
    def total(self) -> int:
        return len(self.items)

    @property
    def succeeded(self) -> int:
        return sum(item.success for item in self.items)

    @property
    def failed(self) -> int:
        return self.total - self.succeeded


class IAMBulkService:
    ENTITIES = frozenset({"ORGANIZATIONS", "USERS", "ROLES"})
    VIEW_PERMISSIONS = {
        "ORGANIZATIONS": "system:org:view",
        "USERS": "system:user:view",
        "ROLES": "system:role:view",
    }

    def __init__(
        self,
        repository: IAMRepository,
        permission_service: PermissionService,
        organization_service: OrganizationAdministrationService,
        user_service: UserAdministrationService,
        role_service: RoleAdministrationService,
    ) -> None:
        self.repository = repository
        self.permission_service = permission_service
        self.organization_service = organization_service
        self.user_service = user_service
        self.role_service = role_service

    def search(
        self,
        entity: str,
        query: IAMListQuery,
        actor: IAMAdministrationActor,
    ) -> PageResult[dict]:
        normalized = self._entity(entity)
        self._require(actor, self.VIEW_PERMISSIONS[normalized])
        self._validate_query(query)
        if normalized == "ORGANIZATIONS":
            page = self.repository.search_organizations(query)
            items = [self._organization_record(item) for item in page.items]
        elif normalized == "USERS":
            page = self.repository.search_users(query)
            items = [self._user_record(item) for item in page.items]
        else:
            page = self.repository.search_roles(query)
            items = [self._role_record(item) for item in page.items]
        return PageResult(items, page.total, page.page, page.page_size)

    def export(
        self,
        entity: str,
        actor: IAMAdministrationActor,
    ) -> list[dict]:
        normalized = self._entity(entity)
        self._require(actor, "system:iam:export")
        if normalized == "ORGANIZATIONS":
            return [
                self._organization_record(item)
                for item in self.repository.list_organizations()
            ]
        if normalized == "USERS":
            return [self._user_record(item) for item in self.repository.list_users()]
        return [self._role_record(item) for item in self.repository.list_roles()]

    def import_records(
        self,
        entity: str,
        records: list[dict],
        actor: IAMAdministrationActor,
    ) -> IAMImportResult:
        normalized = self._entity(entity)
        self._require(actor, "system:iam:import")
        if not records or len(records) > 500:
            raise IAMAdministrationValidationError("import requires 1..500 records")
        handler = {
            "ORGANIZATIONS": self._import_organization,
            "USERS": self._import_user,
            "ROLES": self._import_role,
        }[normalized]
        items = []
        for index, record in enumerate(records, start=1):
            key = str(
                record.get("org_code")
                or record.get("username")
                or record.get("role_code")
                or ""
            )
            try:
                handler(record, actor)
            except (IAMError, KeyError, TypeError, ValueError) as error:
                items.append(IAMImportItemResult(index, key, False, str(error)))
            else:
                items.append(IAMImportItemResult(index, key, True, "OK"))
        return IAMImportResult(normalized, items)

    def _import_organization(
        self, record: dict, actor: IAMAdministrationActor
    ) -> None:
        code = str(record["org_code"])
        existing = self.repository.get_organization_by_code(code.strip().upper())
        if existing is None:
            self.organization_service.create(
                CreateOrganizationCommand(
                    org_code=code,
                    org_name=str(record["org_name"]),
                    org_type=record.get("org_type"),
                    parent_code=record.get("parent_code"),
                    sort_no=int(record.get("sort_no", 0)),
                ),
                actor,
            )
        else:
            self.organization_service.update(
                existing.id,
                UpdateOrganizationCommand(
                    org_name=str(record["org_name"]),
                    org_type=record.get("org_type"),
                    parent_code=record.get("parent_code"),
                    sort_no=int(record.get("sort_no", 0)),
                ),
                actor,
            )

    def _import_user(self, record: dict, actor: IAMAdministrationActor) -> None:
        username = str(record["username"])
        user = self.repository.get_user_by_username(username.strip().lower())
        if user is None:
            password = record.get("password")
            if not isinstance(password, str) or not password:
                raise IAMAdministrationValidationError("new user requires password")
            user = self.user_service.create(
                CreateUserCommand(
                    username=username,
                    login_name=record.get("login_name"),
                    display_name=str(record["display_name"]),
                    password=password,
                    phone=record.get("phone"),
                ),
                actor,
            )
        else:
            user = self.user_service.update(
                user.id,
                UpdateUserCommand(
                    display_name=str(record["display_name"]),
                    phone=record.get("phone"),
                ),
                actor,
            )
        if "memberships" in record:
            memberships = tuple(
                MembershipConfiguration(
                    org_code=str(item["org_code"]),
                    is_primary=bool(item.get("is_primary", False)),
                    is_active=bool(item.get("is_active", True)),
                    role_codes=tuple(item.get("role_codes", ())),
                )
                for item in record["memberships"]
            )
            self.user_service.replace_memberships(user.id, memberships, actor)

    def _import_role(self, record: dict, actor: IAMAdministrationActor) -> None:
        code = str(record["role_code"])
        role = self.repository.get_role_by_code(code.strip().upper())
        if role is None:
            role = self.role_service.create(
                CreateRoleCommand(
                    role_code=code,
                    role_name=str(record["role_name"]),
                    role_type=record.get("role_type"),
                ),
                actor,
            )
        else:
            role = self.role_service.update(
                role.id,
                UpdateRoleCommand(
                    role_name=str(record["role_name"]),
                    role_type=record.get("role_type"),
                ),
                actor,
            )
        if "authorization" in record:
            authorization = tuple(
                PermissionScopeConfiguration(
                    permission_code=str(item["permission_code"]),
                    scope_type=str(item["scope_type"]),
                    custom_org_codes=tuple(item.get("custom_org_codes", ())),
                )
                for item in record["authorization"]
            )
            self.role_service.replace_authorization(role.id, authorization, actor)

    def _organization_record(self, item) -> dict:
        parent = (
            self.repository.get_organization(item.parent_id)
            if item.parent_id is not None
            else None
        )
        return {
            "org_code": item.org_code,
            "org_name": item.org_name,
            "org_type": item.org_type,
            "parent_code": parent.org_code if parent else None,
            "sort_no": item.sort_no,
            "is_active": item.is_active,
        }

    @staticmethod
    def _user_record(item) -> dict:
        return {
            "username": item.username,
            "display_name": item.display_name,
            "phone": item.phone,
            "is_active": item.is_active,
            "memberships": [
                {
                    "org_code": membership.organization.org_code,
                    "is_primary": membership.is_primary,
                    "is_active": membership.is_active,
                    "role_codes": sorted(
                        link.role.role_code for link in membership.role_links
                    ),
                }
                for membership in item.memberships
            ],
        }

    def _role_record(self, item) -> dict:
        organizations = {
            org.id: org.org_code for org in self.repository.list_organizations()
        }
        scopes = {scope.permission_code: scope for scope in item.data_scopes}
        authorization = []
        for link in item.permission_links:
            code = link.permission.permission_code
            scope = scopes.get(code)
            if scope is None:
                continue
            org_ids = (
                scope.scope_config.get("org_ids", [])
                if isinstance(scope.scope_config, dict)
                else []
            )
            authorization.append(
                {
                    "permission_code": code,
                    "scope_type": scope.scope_type,
                    "custom_org_codes": [
                        organizations[org_id]
                        for org_id in org_ids
                        if org_id in organizations
                    ],
                }
            )
        return {
            "role_code": item.role_code,
            "role_name": item.role_name,
            "role_type": item.role_type,
            "is_active": item.is_active,
            "authorization": sorted(
                authorization, key=lambda row: row["permission_code"]
            ),
        }

    def _require(self, actor: IAMAdministrationActor, permission_code: str) -> None:
        if not self.permission_service.has_permission(
            actor.user_id, permission_code, actor.active_org_id
        ):
            raise IAMAdministrationPermissionDenied(
                f"permission required: {permission_code}"
            )

    def _entity(self, entity: str) -> str:
        normalized = entity.strip().upper()
        if normalized not in self.ENTITIES:
            raise IAMAdministrationValidationError("unsupported IAM entity")
        return normalized

    @staticmethod
    def _validate_query(query: IAMListQuery) -> None:
        if query.page < 1 or not 1 <= query.page_size <= 100:
            raise IAMAdministrationValidationError("invalid pagination")
        if query.sort_direction not in {"asc", "desc"}:
            raise IAMAdministrationValidationError("invalid sort direction")
        if query.sort_by not in {"code", "name", "sort_no", "created_at"}:
            raise IAMAdministrationValidationError("unsupported sort field")
