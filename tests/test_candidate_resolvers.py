from pathlib import Path

import pytest
from sqlalchemy.orm import Session

from app.iam.identity import IdentityQueryService
from app.iam.repository import IAMRepository
from app.iam.seed import seed_iam
from app.iam.service import IAMService
from app.workflow.candidate import (
    CandidateResolverRegistry,
    CandidateRule,
    CandidateRuleError,
    CandidateType,
)


@pytest.fixture()
def candidate_environment(
    db_session: Session,
) -> tuple[IAMService, CandidateResolverRegistry]:
    repository = IAMRepository(db_session)
    service = IAMService(repository)
    seed_iam(service)
    resolver = CandidateResolverRegistry.default(IdentityQueryService(repository))
    return service, resolver


def _user_id(service: IAMService, username: str) -> int:
    user = service.get_user(username)
    assert user is not None
    return user.id


def _org_id(service: IAMService, org_code: str) -> int:
    organization = service.get_organization(org_code)
    assert organization is not None
    return organization.id


def test_registry_supports_all_candidate_types(
    candidate_environment: tuple[IAMService, CandidateResolverRegistry],
) -> None:
    _, resolver = candidate_environment

    assert resolver.supported_types == set(CandidateType)


def test_user_and_organization_resolvers_return_active_users(
    candidate_environment: tuple[IAMService, CandidateResolverRegistry],
) -> None:
    service, resolver = candidate_environment
    lisi_id = _user_id(service, "lisi")
    pipe_org_id = _org_id(service, "PIPE_OPERATION")

    assert resolver.resolve(
        CandidateRule(CandidateType.USER, user_id=lisi_id)
    ) == {lisi_id}
    assert resolver.resolve(
        CandidateRule(CandidateType.ORG, org_id=pipe_org_id)
    ) == {
        _user_id(service, "wangwu"),
        _user_id(service, "zhangsan"),
        lisi_id,
        _user_id(service, "zhaoliu"),
    }


def test_org_role_resolves_repairers_in_exact_organization(
    candidate_environment: tuple[IAMService, CandidateResolverRegistry],
) -> None:
    service, resolver = candidate_environment

    pipe_result = resolver.resolve(
        CandidateRule(
            CandidateType.ORG_ROLE,
            org_id=_org_id(service, "PIPE_OPERATION"),
            role_code="REPAIRER",
        )
    )
    dispatch_result = resolver.resolve(
        CandidateRule(
            CandidateType.ORG_ROLE,
            org_id=_org_id(service, "DISPATCH_CENTER"),
            role_code="REPAIRER",
        )
    )

    assert pipe_result == {
        _user_id(service, "lisi"),
        _user_id(service, "zhaoliu"),
    }
    assert dispatch_result == set()


def test_inactive_user_and_membership_are_filtered(
    candidate_environment: tuple[IAMService, CandidateResolverRegistry],
    db_session: Session,
) -> None:
    service, resolver = candidate_environment
    lisi = service.get_user("lisi")
    assert lisi is not None
    lisi.is_active = False
    membership = service.get_membership("zhaoliu", "PIPE_OPERATION")
    assert membership is not None
    membership.is_active = False
    db_session.commit()

    assert resolver.resolve(
        CandidateRule(CandidateType.USER, user_id=lisi.id)
    ) == set()
    assert resolver.resolve(
        CandidateRule(
            CandidateType.ORG_ROLE,
            org_id=_org_id(service, "PIPE_OPERATION"),
            role_code="REPAIRER",
        )
    ) == set()


def test_inactive_org_and_role_are_filtered(
    candidate_environment: tuple[IAMService, CandidateResolverRegistry],
    db_session: Session,
) -> None:
    service, resolver = candidate_environment
    pipe_org = service.get_organization("PIPE_OPERATION")
    repairer_role = service.get_role("REPAIRER")
    assert pipe_org is not None
    assert repairer_role is not None

    pipe_org.is_active = False
    db_session.commit()
    assert resolver.resolve(
        CandidateRule(CandidateType.ORG, org_id=pipe_org.id)
    ) == set()

    pipe_org.is_active = True
    repairer_role.is_active = False
    db_session.commit()
    assert resolver.resolve(
        CandidateRule(
            CandidateType.ORG_ROLE,
            org_id=pipe_org.id,
            role_code="REPAIRER",
        )
    ) == set()



def test_role_resolver_deduplicates_user_across_organizations(
    candidate_environment: tuple[IAMService, CandidateResolverRegistry],
) -> None:
    service, resolver = candidate_environment
    lisi_id = _user_id(service, "lisi")
    service.add_user_to_organization("lisi", "INSPECTION_TEAM_1")
    service.assign_role("lisi", "INSPECTION_TEAM_1", "REPAIRER")

    result = resolver.resolve(
        CandidateRule(CandidateType.ROLE, role_code="REPAIRER")
    )

    assert result == {lisi_id, _user_id(service, "zhaoliu")}


@pytest.mark.parametrize(
    "rule",
    [
        CandidateRule(CandidateType.USER),
        CandidateRule(CandidateType.ORG, org_id=0),
        CandidateRule(CandidateType.ORG_ROLE, org_id=1),
        CandidateRule("UNKNOWN"),
    ],
)
def test_invalid_candidate_rules_fail_explicitly(
    candidate_environment: tuple[IAMService, CandidateResolverRegistry],
    rule: CandidateRule,
) -> None:
    _, resolver = candidate_environment

    with pytest.raises(CandidateRuleError):
        resolver.resolve(rule)


def test_candidate_resolvers_do_not_query_iam_models_directly() -> None:
    source = Path("app/workflow/candidate/resolvers.py").read_text(encoding="utf-8")

    assert "app.iam.models" not in source
    assert "app.iam.repository" not in source
    assert "select(" not in source
