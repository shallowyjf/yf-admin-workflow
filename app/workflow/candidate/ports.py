"""Ports required by workflow candidate resolvers."""

from typing import Protocol


class IdentityQueryPort(Protocol):
    def active_user(self, user_id: int) -> set[int]: ...

    def users_by_role(
        self,
        role_code: str,
        org_id: int | None = None,
    ) -> set[int]: ...

    def users_by_organization(self, org_id: int) -> set[int]: ...

    def users_by_position(self, position_code: str, org_id: int) -> set[int]: ...
