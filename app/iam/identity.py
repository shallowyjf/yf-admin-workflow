"""Public read service used by candidate resolution."""

from .repository import IAMRepository


class IdentityQueryService:
    def __init__(self, repository: IAMRepository) -> None:
        self.repository = repository

    def active_user(self, user_id: int) -> set[int]:
        active_user_id = self.repository.get_active_user_id(user_id)
        return {active_user_id} if active_user_id is not None else set()

    def users_by_role(
        self,
        role_code: str,
        org_id: int | None = None,
    ) -> set[int]:
        return self.repository.list_active_user_ids_by_role(role_code, org_id)

    def users_by_organization(self, org_id: int) -> set[int]:
        return self.repository.list_active_user_ids_by_organization(org_id)

    def users_by_position(self, position_code: str, org_id: int) -> set[int]:
        return self.repository.list_active_user_ids_by_position(position_code, org_id)

    def descendant_org_ids(self, org_id: int) -> set[int]:
        return self.repository.list_active_descendant_org_ids(org_id)

    def active_user_labels(self, user_ids: set[int]) -> dict[int, str]:
        return self.repository.active_user_labels(user_ids)
