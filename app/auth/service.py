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


class ActiveApplicationDenied(Exception):
    """Raised when a system is not available to the current user."""


class ActiveProjectDenied(Exception):
    """Raised when a project is not available to the current user."""


@dataclass(frozen=True)
class RequestContext:
    current_user_id: int
    tenant_id: int
    active_org_id: int
    session_id: int
    active_application_id: int | None = None
    active_project_id: int | None = None


@dataclass(frozen=True)
class OrganizationContext:
    id: int
    org_code: str
    org_name: str
    is_primary: bool


@dataclass(frozen=True)
class ApplicationContext:
    id: int
    application_code: str
    application_name: str
    domain_type: str


@dataclass(frozen=True)
class ProjectContext:
    id: int
    application_id: int
    project_code: str
    project_name: str
    project_status: str


@dataclass(frozen=True)
class AuthProfile:
    user_id: int
    tenant_id: int
    tenant_code: str
    tenant_name: str
    username: str
    login_name: str
    display_name: str
    active_org_id: int
    active_application_id: int | None
    active_project_id: int | None
    organizations: list[OrganizationContext]
    applications: list[ApplicationContext]
    projects: list[ProjectContext]
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
    ) -> LoginResult:
        user = self.repository.get_user_by_login_name(username)
        if (
            user is None
            or not user.is_active
            or not self.password_hasher.verify(password, user.password_hash)
        ):
            raise AuthenticationError("invalid username or password")
        tenant = self.repository.get_tenant(user.tenant_id)
        if tenant is None or not tenant.is_active:
            raise AuthenticationError("invalid username or password")

        return self.create_tenant_session(user.id, tenant.id)

    def create_tenant_session(self, user_id: int, tenant_id: int) -> LoginResult:
        """Create a tenant session after credentials or trusted platform entry."""
        tenant = self.repository.get_tenant(tenant_id)
        user = self.repository.get_user(user_id)
        if tenant is None or user is None or user.tenant_id != tenant.id:
            raise AuthenticationError("tenant administrator is unavailable")
        memberships = self.repository.list_active_memberships(user.id, tenant.id)
        if not memberships:
            raise ActiveOrganizationDenied("user has no active organization")

        token = new_session_token()
        active_org_id = memberships[0].org_id
        applications, projects = self._available_contexts(
            user.id, tenant.id, active_org_id
        )
        active_application_id = applications[0].id if applications else None
        active_project = next(
            (
                project
                for project in projects
                if project.application_id == active_application_id
            ),
            None,
        )
        auth_session = AuthSession(
            tenant_id=tenant.id,
            user_id=user.id,
            active_org_id=active_org_id,
            active_application_id=active_application_id,
            active_project_id=active_project.id if active_project else None,
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
            auth_session.active_application_id,
            auth_session.active_project_id,
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
        context = RequestContext(
            auth_session.user_id,
            auth_session.tenant_id,
            auth_session.active_org_id,
            auth_session.id,
            auth_session.active_application_id,
            auth_session.active_project_id,
        )
        self._require_active_resource_context(context)
        return context

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
        applications, projects = self._available_contexts(
            context.current_user_id,
            context.tenant_id,
            org_id,
        )
        auth_session.active_application_id = applications[0].id if applications else None
        active_project = next(
            (
                project
                for project in projects
                if project.application_id == auth_session.active_application_id
            ),
            None,
        )
        auth_session.active_project_id = active_project.id if active_project else None
        self.repository.save(auth_session)
        return self.profile(
            RequestContext(
                context.current_user_id,
                context.tenant_id,
                org_id,
                context.session_id,
                auth_session.active_application_id,
                auth_session.active_project_id,
            )
        )

    def switch_active_application(
        self,
        context: RequestContext,
        application_id: int,
    ) -> AuthProfile:
        auth_session = self._session_for_context(context)
        applications, projects = self._available_contexts(
            context.current_user_id,
            context.tenant_id,
            context.active_org_id,
        )
        if application_id not in {application.id for application in applications}:
            raise ActiveApplicationDenied("system entrance is not available")
        auth_session.active_application_id = application_id
        active_project = next(
            (
                project
                for project in projects
                if project.application_id == application_id
            ),
            None,
        )
        auth_session.active_project_id = active_project.id if active_project else None
        self.repository.save(auth_session)
        return self.profile(
            RequestContext(
                context.current_user_id,
                context.tenant_id,
                context.active_org_id,
                context.session_id,
                application_id,
                auth_session.active_project_id,
            )
        )

    def switch_active_project(
        self,
        context: RequestContext,
        project_id: int,
    ) -> AuthProfile:
        auth_session = self._session_for_context(context)
        _, projects = self._available_contexts(
            context.current_user_id,
            context.tenant_id,
            context.active_org_id,
        )
        project = next((item for item in projects if item.id == project_id), None)
        if project is None:
            raise ActiveProjectDenied("project is not available")
        auth_session.active_application_id = project.application_id
        auth_session.active_project_id = project.id
        self.repository.save(auth_session)
        return self.profile(
            RequestContext(
                context.current_user_id,
                context.tenant_id,
                context.active_org_id,
                context.session_id,
                project.application_id,
                project.id,
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
        applications, projects = self._available_contexts(
            user.id,
            context.tenant_id,
            context.active_org_id,
        )
        return AuthProfile(
            user_id=user.id,
            tenant_id=auth_session.tenant_id,
            tenant_code=auth_session.tenant.tenant_code,
            tenant_name=auth_session.tenant.tenant_name,
            username=user.username,
            login_name=user.login_name,
            display_name=user.display_name,
            active_org_id=context.active_org_id,
            active_application_id=context.active_application_id,
            active_project_id=context.active_project_id,
            organizations=[
                OrganizationContext(
                    id=membership.organization.id,
                    org_code=membership.organization.org_code,
                    org_name=membership.organization.org_name,
                    is_primary=membership.is_primary,
                )
                for membership in memberships
            ],
            applications=[
                ApplicationContext(
                    id=application.id,
                    application_code=application.application_code,
                    application_name=application.application_name,
                    domain_type=application.domain_type,
                )
                for application in applications
            ],
            projects=[
                ProjectContext(
                    id=project.id,
                    application_id=project.application_id,
                    project_code=project.project_code,
                    project_name=project.project_name,
                    project_status=project.project_status,
                )
                for project in projects
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
            or auth_session.active_application_id != context.active_application_id
            or auth_session.active_project_id != context.active_project_id
        ):
            raise AuthenticationError("session context is invalid or expired")
        return auth_session

    def _available_contexts(self, user_id: int, tenant_id: int, active_org_id: int):
        if not self.permission_service.has_permission(
            user_id, "system:application:view", active_org_id
        ):
            return [], []
        applications = self.repository.list_user_applications(user_id, tenant_id)
        if not self.permission_service.has_permission(
            user_id, "project:view", active_org_id
        ):
            return applications, []
        include_all = self.permission_service.has_permission(
            user_id, "project:progress:view-all", active_org_id
        )
        projects = self.repository.list_accessible_projects(
            user_id,
            tenant_id,
            include_all=include_all,
        )
        return applications, projects

    def _require_active_resource_context(self, context: RequestContext) -> None:
        applications, projects = self._available_contexts(
            context.current_user_id,
            context.tenant_id,
            context.active_org_id,
        )
        application_ids = {application.id for application in applications}
        if (
            context.active_application_id is not None
            and context.active_application_id not in application_ids
        ):
            raise AuthenticationError("active system is no longer available")
        if context.active_project_id is None:
            return
        project = next(
            (item for item in projects if item.id == context.active_project_id),
            None,
        )
        if (
            project is None
            or project.application_id != context.active_application_id
        ):
            raise AuthenticationError("active project is no longer available")

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
