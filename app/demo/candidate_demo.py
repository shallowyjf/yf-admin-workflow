"""Read-only CandidateResolver demonstration for the seeded database."""

import json

from app.core.config import get_settings
from app.db.session import Database
from app.iam.identity import IdentityQueryService
from app.iam.repository import IAMRepository
from app.iam.service import IAMService
from app.workflow.candidate import CandidateResolverRegistry, CandidateRule, CandidateType


def _require_id(entity, label: str) -> int:
    if entity is None:
        raise RuntimeError(f"missing seed entity: {label}; run app.iam.seed first")
    return entity.id


def main() -> None:
    database = Database(get_settings().database_url)
    try:
        with database.session_factory() as session:
            repository = IAMRepository(session)
            identities = IdentityQueryService(repository)
            iam = IAMService(repository)
            resolver = CandidateResolverRegistry.default(identities)

            pipe_org_id = _require_id(
                iam.get_organization("PIPE_OPERATION"),
                "PIPE_OPERATION",
            )
            lisi_id = _require_id(iam.get_user("lisi"), "lisi")
            scenarios = (
                CandidateRule(CandidateType.USER, user_id=lisi_id),
                CandidateRule(CandidateType.ROLE, role_code="REPAIRER"),
                CandidateRule(CandidateType.ORG, org_id=pipe_org_id),
                CandidateRule(
                    CandidateType.ORG_ROLE,
                    org_id=pipe_org_id,
                    role_code="REPAIRER",
                ),
            )
            output = []
            for rule in scenarios:
                user_ids = resolver.resolve(rule)
                labels = identities.active_user_labels(user_ids)
                output.append(
                    {
                        "candidate_type": CandidateType(rule.candidate_type).value,
                        "user_ids": sorted(user_ids),
                        "usernames": [labels[user_id] for user_id in sorted(user_ids)],
                    }
                )
            print(json.dumps(output, ensure_ascii=False, indent=2))
    finally:
        database.dispose()


if __name__ == "__main__":
    main()
