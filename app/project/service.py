"""Read model for city lifeline system/project/permission demonstrations."""

from dataclasses import dataclass

from app.iam.authorization import PermissionService

from .repository import ProjectRepository


class ProjectPermissionDenied(Exception):
    """Raised when the current organization context cannot view projects."""


@dataclass(frozen=True)
class ProjectActor:
    user_id: int
    active_org_id: int


class ProjectService:
    def __init__(
        self,
        repository: ProjectRepository,
        permission_service: PermissionService,
    ) -> None:
        self.repository = repository
        self.permission_service = permission_service

    def structure(self, actor: ProjectActor) -> dict:
        required_permissions = ("system:application:view", "project:view")
        missing_permissions = [
            permission_code
            for permission_code in required_permissions
            if not self.permission_service.has_permission(
                actor.user_id, permission_code, actor.active_org_id
            )
        ]
        if missing_permissions:
            raise ProjectPermissionDenied(
                f"缺少项目结构查看权限：{', '.join(missing_permissions)}"
            )

        can_view_all = self.permission_service.has_permission(
            actor.user_id, "project:progress:view-all", actor.active_org_id
        )
        projects = self.repository.list_projects()
        if not can_view_all:
            projects = [
                project
                for project in projects
                if any(
                    member.is_active
                    and member.membership.is_active
                    and member.membership.user_id == actor.user_id
                    for member in project.members
                )
            ]

        applications = []
        for application in self.repository.list_applications():
            app_projects = [
                self._project_item(project)
                for project in projects
                if project.application_id == application.id
            ]
            applications.append(
                {
                    "application_code": application.application_code,
                    "application_name": application.application_name,
                    "domain_type": application.domain_type,
                    "projects": app_projects,
                }
            )

        return {
            "applications": applications,
            "role_matrix": [self._role_item(role) for role in self.repository.list_roles()],
            "can_view_all_projects": can_view_all,
        }

    @staticmethod
    def _project_item(project) -> dict:
        return {
            "project_code": project.project_code,
            "project_name": project.project_name,
            "project_status": project.project_status,
            "start_date": project.start_date,
            "end_date": project.end_date,
            "organizations": [
                {
                    "org_code": link.organization.org_code,
                    "org_name": link.organization.org_name,
                    "party_type": link.party_type,
                    "is_lead": link.is_lead,
                }
                for link in sorted(
                    project.organization_links,
                    key=lambda item: (item.party_type, item.organization.sort_no),
                )
            ],
            "members": [
                {
                    "username": member.membership.user.username,
                    "display_name": member.membership.user.display_name,
                    "org_code": member.membership.organization.org_code,
                    "org_name": member.membership.organization.org_name,
                    "role_code": member.role.role_code,
                    "role_name": member.role.role_name,
                }
                for member in sorted(
                    (item for item in project.members if item.is_active),
                    key=lambda item: (item.role.role_code, item.membership.user.username),
                )
            ],
        }

    @staticmethod
    def _role_item(role) -> dict:
        scopes = {scope.permission_code: scope.scope_type for scope in role.data_scopes}
        return {
            "role_code": role.role_code,
            "role_name": role.role_name,
            "role_type": role.role_type,
            "permissions": [
                {
                    "permission_code": link.permission.permission_code,
                    "permission_name": link.permission.permission_name,
                    "scope_type": scopes.get(link.permission.permission_code),
                }
                for link in sorted(
                    role.permission_links,
                    key=lambda item: item.permission.permission_code,
                )
            ],
        }
