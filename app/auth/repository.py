"""Persistence operations for authentication sessions and user context."""

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload, selectinload

from app.iam.models import (
    Organization,
    User,
    UserOrganization,
    UserOrganizationRole,
)

from .models import AuthSession


class AuthRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_user_by_username(self, username: str) -> User | None:
        return self.session.scalar(select(User).where(User.username == username))

    def list_active_memberships(self, user_id: int) -> list[UserOrganization]:
        return list(
            self.session.scalars(
                select(UserOrganization)
                .join(Organization, Organization.id == UserOrganization.org_id)
                .where(
                    UserOrganization.user_id == user_id,
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
    ) -> UserOrganization | None:
        return self.session.scalar(
            select(UserOrganization)
            .join(Organization, Organization.id == UserOrganization.org_id)
            .where(
                UserOrganization.user_id == user_id,
                UserOrganization.org_id == org_id,
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
