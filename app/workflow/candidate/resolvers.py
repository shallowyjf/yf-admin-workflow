"""Resolver implementations and registry dispatch."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from .models import CandidateRule, CandidateRuleError, CandidateType
from .ports import IdentityQueryPort


class CandidateResolver(Protocol):
    candidate_type: CandidateType

    def resolve(self, rule: CandidateRule) -> set[int]: ...


def _required_id(value: int | None, field_name: str) -> int:
    if value is None or value <= 0:
        raise CandidateRuleError(f"{field_name} is required")
    return value


def _required_code(value: str | None, field_name: str) -> str:
    if value is None or not value.strip():
        raise CandidateRuleError(f"{field_name} is required")
    return value.strip()


@dataclass(frozen=True)
class UserCandidateResolver:
    identity_queries: IdentityQueryPort
    candidate_type = CandidateType.USER

    def resolve(self, rule: CandidateRule) -> set[int]:
        return self.identity_queries.active_user(_required_id(rule.user_id, "user_id"))


@dataclass(frozen=True)
class RoleCandidateResolver:
    identity_queries: IdentityQueryPort
    candidate_type = CandidateType.ROLE

    def resolve(self, rule: CandidateRule) -> set[int]:
        return self.identity_queries.users_by_role(
            _required_code(rule.role_code, "role_code")
        )


@dataclass(frozen=True)
class OrganizationCandidateResolver:
    identity_queries: IdentityQueryPort
    candidate_type = CandidateType.ORG

    def resolve(self, rule: CandidateRule) -> set[int]:
        return self.identity_queries.users_by_organization(
            _required_id(rule.org_id, "org_id")
        )


@dataclass(frozen=True)
class OrganizationRoleCandidateResolver:
    identity_queries: IdentityQueryPort
    candidate_type = CandidateType.ORG_ROLE

    def resolve(self, rule: CandidateRule) -> set[int]:
        return self.identity_queries.users_by_role(
            _required_code(rule.role_code, "role_code"),
            _required_id(rule.org_id, "org_id"),
        )


@dataclass(frozen=True)
class OrganizationPositionCandidateResolver:
    identity_queries: IdentityQueryPort
    candidate_type = CandidateType.ORG_POSITION

    def resolve(self, rule: CandidateRule) -> set[int]:
        return self.identity_queries.users_by_position(
            _required_code(rule.position_code, "position_code"),
            _required_id(rule.org_id, "org_id"),
        )


class CandidateResolverRegistry:
    def __init__(self, resolvers: list[CandidateResolver]) -> None:
        self._resolvers: dict[CandidateType, CandidateResolver] = {}
        for resolver in resolvers:
            if resolver.candidate_type in self._resolvers:
                raise CandidateRuleError(
                    f"duplicate resolver: {resolver.candidate_type.value}"
                )
            self._resolvers[resolver.candidate_type] = resolver

    @classmethod
    def default(
        cls,
        identity_queries: IdentityQueryPort,
    ) -> CandidateResolverRegistry:
        return cls(
            [
                UserCandidateResolver(identity_queries),
                RoleCandidateResolver(identity_queries),
                OrganizationCandidateResolver(identity_queries),
                OrganizationRoleCandidateResolver(identity_queries),
                OrganizationPositionCandidateResolver(identity_queries),
            ]
        )

    @property
    def supported_types(self) -> set[CandidateType]:
        return set(self._resolvers)

    def resolve(self, rule: CandidateRule) -> set[int]:
        try:
            candidate_type = CandidateType(rule.candidate_type)
            resolver = self._resolvers[candidate_type]
        except (ValueError, KeyError) as error:
            raise CandidateRuleError(
                f"unsupported candidate type: {rule.candidate_type}"
            ) from error
        return set(resolver.resolve(rule))
