"""Candidate rule value objects and validation errors."""

from dataclasses import dataclass
from enum import StrEnum


class CandidateType(StrEnum):
    USER = "USER"
    ROLE = "ROLE"
    ORG = "ORG"
    ORG_ROLE = "ORG_ROLE"
    ORG_POSITION = "ORG_POSITION"


@dataclass(frozen=True)
class CandidateRule:
    candidate_type: CandidateType | str
    user_id: int | None = None
    org_id: int | None = None
    role_code: str | None = None
    position_code: str | None = None


class CandidateRuleError(ValueError):
    """Raised when a rule type or required input is invalid."""
