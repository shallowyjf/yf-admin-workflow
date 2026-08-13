"""Platform root authentication and city-tenant entry."""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from app.iam.models import Tenant, User

from .models import PlatformSession
from .repository import AuthRepository
from .security import PasswordHasher, new_session_token, session_token_hash


class PlatformAuthenticationError(Exception):
    pass


@dataclass(frozen=True)
class PlatformContext:
    platform_user_id: int
    username: str
    display_name: str


class PlatformAuthService:
    def __init__(self, repository: AuthRepository, session_hours: int = 8) -> None:
        self.repository = repository
        self.session_hours = session_hours
        self.password_hasher = PasswordHasher()

    def login(self, username: str, password: str) -> str:
        user = self.repository.get_platform_user(username.strip())
        if (
            user is None
            or not user.is_active
            or not self.password_hasher.verify(password, user.password_hash)
        ):
            raise PlatformAuthenticationError("invalid platform credentials")
        token = new_session_token()
        self.repository.save(
            PlatformSession(
                platform_user_id=user.id,
                token_hash=session_token_hash(token),
                expires_at=self._now() + timedelta(hours=self.session_hours),
            )
        )
        return token

    def authenticate(self, token: str | None) -> PlatformContext:
        if not token:
            raise PlatformAuthenticationError("platform authentication required")
        session = self.repository.get_platform_session(session_token_hash(token))
        if (
            session is None
            or session.revoked_at is not None
            or session.expires_at <= self._now()
            or not session.platform_user.is_active
        ):
            raise PlatformAuthenticationError("platform session is invalid")
        return PlatformContext(
            session.platform_user_id,
            session.platform_user.username,
            session.platform_user.display_name,
        )

    def list_tenants(self) -> list[Tenant]:
        return self.repository.list_active_tenants()

    def tenant_administrator(self, tenant_id: int) -> tuple[Tenant, User]:
        tenant = self.repository.get_tenant(tenant_id)
        if tenant is None or not tenant.is_active:
            raise PlatformAuthenticationError("city tenant is unavailable")
        admin = self.repository.get_user_by_username("admin", tenant.id)
        if admin is None or not admin.is_active:
            raise PlatformAuthenticationError("city administrator is unavailable")
        return tenant, admin

    def logout(self, token: str | None) -> None:
        if not token:
            return
        session = self.repository.get_platform_session(session_token_hash(token))
        if session is not None and session.revoked_at is None:
            session.revoked_at = self._now()
            self.repository.save(session)

    @staticmethod
    def _now() -> datetime:
        return datetime.now(UTC).replace(tzinfo=None)
