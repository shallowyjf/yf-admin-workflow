"""Persistence operations for authentication sessions and user context."""

from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.orm import Session, joinedload, selectinload

from app.iam.models import (
    Organization,
    Tenant,
    User,
    UserOrganization,
    UserOrganizationRole,
)

from .models import AuthSession


class AuthRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_tenant_by_code(self, tenant_code: str) -> Tenant | None:
        return self.session.scalar(
            select(Tenant).where(Tenant.tenant_code == tenant_code)
        )

    def get_user_by_username(self, username: str, tenant_id: int) -> User | None:
        return self.session.scalar(
            select(User).where(
                User.username == username,
                User.tenant_id == tenant_id,
            )
        )

    def list_active_memberships(
        self,
        user_id: int,
        tenant_id: int,
    ) -> list[UserOrganization]:
        return list(
            self.session.scalars(
                select(UserOrganization)
                .join(Organization, Organization.id == UserOrganization.org_id)
                .where(
                    UserOrganization.user_id == user_id,
                    Organization.tenant_id == tenant_id,
                    UserOrganization.is_active.is_(True),
                    Organization.is_active.is_(True),
                )
                .options(
                    joinedload(UserOrganization.organization),
                    selectinload(UserOrganization.role_links).joinedload(
                        UserOrganizationRole.role
                    ),
                )
                .order_by(
                    UserOrganization.is_primary.desc(),
                    Organization.sort_no,
                    UserOrganization.id,
                )
            ).unique()
        )

    def get_active_membership(
        self,
        user_id: int,
        org_id: int,
        tenant_id: int,
    ) -> UserOrganization | None:
        return self.session.scalar(
            select(UserOrganization)
            .join(Organization, Organization.id == UserOrganization.org_id)
            .where(
                UserOrganization.user_id == user_id,
                UserOrganization.org_id == org_id,
                Organization.tenant_id == tenant_id,
                UserOrganization.is_active.is_(True),
                Organization.is_active.is_(True),
            )
        )

    def get_session_by_token_hash(self, token_hash: str) -> AuthSession | None:
        return self.session.scalar(
            select(AuthSession)
            .where(AuthSession.token_hash == token_hash)
            .options(
                joinedload(AuthSession.user),
                joinedload(AuthSession.tenant),
                joinedload(AuthSession.active_organization),
            )
        )

    def save(self, entity: object) -> None:
        self.session.add(entity)
        try:
            self.session.commit()
        except Exception:
            self.session.rollback()
            raise

    def refresh(self, entity: object) -> None:
        self.session.refresh(entity)

    def revoke_user_sessions(self, user_id: int, revoked_at: datetime) -> None:
        self.session.execute(
            update(AuthSession)
            .where(
                AuthSession.user_id == user_id,
                AuthSession.revoked_at.is_(None),
            )
            .values(revoked_at=revoked_at)
        )
