"""Functional permission checks and work-order data-scope resolution."""

from dataclasses import dataclass, field
from enum import StrEnum

from .repository import IAMRepository


class DataScopeType(StrEnum):
    ALL = "ALL"
    ORG = "ORG"
    ORG_AND_CHILD = "ORG_AND_CHILD"
    SELF = "SELF"
    CUSTOM = "CUSTOM"


@dataclass
class WorkOrderScopeFilter:
    """Structured OR-filter consumed by a future work-order repository."""

    all_data: bool = False
    org_ids: set[int] = field(default_factory=set)
    self_user_id: int | None = None

    @property
    def is_empty(self) -> bool:
        return not self.all_data and not self.org_ids and self.self_user_id is None


class PermissionService:
    """Resolve stable permission codes within one active organization."""

    def __init__(self, repository: IAMRepository) -> None:
        self.repository = repository

    def has_permission(
        self,
        user_id: int,
        permission_code: str,
        active_org_id: int,
    ) -> bool:
        return bool(
            self.repository.list_authorized_role_ids(
                user_id,
                permission_code,
                active_org_id,
            )
        )

    def work_order_scope(
        self,
        user_id: int,
        permission_code: str,
        active_org_id: int,
    ) -> WorkOrderScopeFilter:
        role_ids = self.repository.list_authorized_role_ids(
            user_id,
            permission_code,
            active_org_id,
        )
        scopes = self.repository.list_role_data_scopes(role_ids, permission_code)
        result = WorkOrderScopeFilter()

        for scope in scopes:
            scope_type = DataScopeType(scope.scope_type)
            if scope_type is DataScopeType.ALL:
                return WorkOrderScopeFilter(all_data=True)
            if scope_type is DataScopeType.ORG:
                result.org_ids.add(active_org_id)
            elif scope_type is DataScopeType.ORG_AND_CHILD:
                result.org_ids.update(
                    self.repository.list_active_descendant_org_ids(active_org_id)
                )
            elif scope_type is DataScopeType.SELF:
                result.self_user_id = user_id
            elif scope_type is DataScopeType.CUSTOM:
                result.org_ids.update(self._custom_org_ids(scope.scope_config))

        return result

    @staticmethod
    def _custom_org_ids(scope_config: dict | None) -> set[int]:
        if not isinstance(scope_config, dict):
            return set()
        org_ids = scope_config.get("org_ids", [])
        if not isinstance(org_ids, list):
            return set()
        return {org_id for org_id in org_ids if isinstance(org_id, int)}
