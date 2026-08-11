"""Authentication, server-side sessions, and request context."""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from app.iam.authorization import PermissionService

from .models import AuthSession
from .repository import AuthRepository
from .security import PasswordHasher, new_session_token, session_token_hash


class AuthenticationError(Exception):
    """Raised for invalid credentials or invalid sessions."""


class ActiveOrganizationDenied(Exception):
    """Raised when an active organization is not a valid membership."""


@dataclass(frozen=True)
class RequestContext:
    current_user_id: int
    tenant_id: int
    active_org_id: int
    session_id: int


@dataclass(frozen=True)
class OrganizationContext:
    id: int
    org_code: str
    org_name: str
    is_primary: bool


@dataclass(frozen=True)
class AuthProfile:
    user_id: int
    tenant_id: int
    tenant_code: str
    tenant_name: str
    username: str
    display_name: str
    active_org_id: int
    organizations: list[OrganizationContext]
    role_codes: list[str]
    permission_codes: list[str]


@dataclass(frozen=True)
class LoginResult:
    token: str
    profile: AuthProfile


class AuthService:
    def __init__(
        self,
        repository: AuthRepository,
        permission_service: PermissionService,
        *,
        session_hours: int = 8,
        default_tenant_code: str = "DEMO",
        password_hasher: PasswordHasher | None = None,
    ) -> None:
        self.repository = repository
        self.permission_service = permission_service
        self.session_hours = session_hours
        self.default_tenant_code = default_tenant_code
        self.password_hasher = password_hasher or PasswordHasher()

    def login(
        self,
        username: str,
        password: str,
        tenant_code: str | None = None,
    ) -> LoginResult:
        normalized_tenant_code = (tenant_code or self.default_tenant_code).strip().upper()
        tenant = self.repository.get_tenant_by_code(normalized_tenant_code)
        if tenant is None or not tenant.is_active:
            raise AuthenticationError("invalid tenant or credentials")
        user = self.repository.get_user_by_username(username, tenant.id)
        if (
            user is None
            or not user.is_active
            or not self.password_hasher.verify(password, user.password_hash)
        ):
            raise AuthenticationError("invalid username or password")

        memberships = self.repository.list_active_memberships(user.id, tenant.id)
        if not memberships:
            raise ActiveOrganizationDenied("user has no active organization")

        token = new_session_token()
        auth_session = AuthSession(
            tenant_id=tenant.id,
            user_id=user.id,
            active_org_id=memberships[0].org_id,
            token_hash=session_token_hash(token),
            expires_at=self._now() + timedelta(hours=self.session_hours),
        )
        self.repository.save(auth_session)
        self.repository.refresh(auth_session)
        context = RequestContext(
            user.id,
            tenant.id,
            auth_session.active_org_id,
            auth_session.id,
        )
        return LoginResult(token, self.profile(context))

    def authenticate(self, token: str | None) -> RequestContext:
        if not token:
            raise AuthenticationError("authentication required")
        auth_session = self.repository.get_session_by_token_hash(
            session_token_hash(token)
        )
        if not self._is_valid(auth_session):
            raise AuthenticationError("session is invalid or expired")
        assert auth_session is not None
        if self.repository.get_active_membership(
            auth_session.user_id,
            auth_session.active_org_id,
            auth_session.tenant_id,
        ) is None:
            raise AuthenticationError("active organization is no longer available")
        return RequestContext(
            auth_session.user_id,
            auth_session.tenant_id,
            auth_session.active_org_id,
            auth_session.id,
        )

    def logout(self, context: RequestContext) -> None:
        auth_session = self._session_for_context(context)
        auth_session.revoked_at = self._now()
        self.repository.save(auth_session)

    def switch_active_organization(
        self,
        context: RequestContext,
        org_id: int,
    ) -> AuthProfile:
        auth_session = self._session_for_context(context)
        if self.repository.get_active_membership(
            context.current_user_id,
            org_id,
            context.tenant_id,
        ) is None:
            raise ActiveOrganizationDenied("user does not belong to target organization")
        auth_session.active_org_id = org_id
        self.repository.save(auth_session)
        return self.profile(
            RequestContext(
                context.current_user_id,
                context.tenant_id,
                org_id,
                context.session_id,
            )
        )

    def profile(self, context: RequestContext) -> AuthProfile:
        auth_session = self._session_for_context(context)
        user = auth_session.user
        memberships = self.repository.list_active_memberships(
            user.id,
            context.tenant_id,
        )
        active_membership = next(
            (
                membership
                for membership in memberships
                if membership.org_id == context.active_org_id
            ),
            None,
        )
        if active_membership is None:
            raise ActiveOrganizationDenied("active organization is unavailable")

        role_codes = sorted(
            {
                link.role.role_code
                for link in active_membership.role_links
                if link.role.is_active
            }
        )
        permission_codes = sorted(
            self.permission_service.effective_permissions(
                user.id,
                context.active_org_id,
            )
        )
        return AuthProfile(
            user_id=user.id,
            tenant_id=auth_session.tenant_id,
            tenant_code=auth_session.tenant.tenant_code,
            tenant_name=auth_session.tenant.tenant_name,
            username=user.username,
            display_name=user.display_name,
            active_org_id=context.active_org_id,
            organizations=[
                OrganizationContext(
                    id=membership.organization.id,
                    org_code=membership.organization.org_code,
                    org_name=membership.organization.org_name,
                    is_primary=membership.is_primary,
                )
                for membership in memberships
            ],
            role_codes=role_codes,
            permission_codes=permission_codes,
        )

    def _is_valid(self, auth_session: AuthSession | None) -> bool:
        return bool(
            auth_session
            and auth_session.revoked_at is None
            and auth_session.expires_at > self._now()
            and auth_session.user.is_active
            and auth_session.tenant.is_active
            and auth_session.user.tenant_id == auth_session.tenant_id
            and auth_session.active_organization.tenant_id == auth_session.tenant_id
        )

    def _session_for_context(self, context: RequestContext) -> AuthSession:
        auth_session = self.repository.session.get(AuthSession, context.session_id)
        if (
            auth_session is None
            or not self._is_valid(auth_session)
            or auth_session.user_id != context.current_user_id
            or auth_session.tenant_id != context.tenant_id
            or auth_session.active_org_id != context.active_org_id
        ):
            raise AuthenticationError("session context is invalid or expired")
        return auth_session

    @staticmethod
    def _now() -> datetime:
        return datetime.now(UTC).replace(tzinfo=None)


class AuthSessionRevocationService:
    """Stage revocation of all sessions owned by a user in the caller transaction."""

    def __init__(self, repository: AuthRepository) -> None:
        self.repository = repository

    def revoke_user_sessions(self, user_id: int) -> None:
        self.repository.revoke_user_sessions(
            user_id,
            datetime.now(UTC).replace(tzinfo=None),
        )
