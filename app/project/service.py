"""City lifeline project administration and authorization decisions."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

from app.iam.authorization import PermissionService

from .models import (
    Project,
    ProjectMember,
    ProjectOrganization,
    UserApplicationAccess,
)
from .repository import ProjectRepository


class ProjectError(Exception):
    """Base project domain error."""


class ProjectPermissionDenied(ProjectError):
    """Raised when the current context cannot perform a project action."""


class ProjectNotFound(ProjectError):
    """Raised when a project does not exist in the current tenant."""


class ProjectValidationError(ProjectError):
    """Raised when project configuration violates a domain invariant."""


class ProjectConflict(ProjectError):
    """Raised when a project operation conflicts with existing relations."""


@dataclass(frozen=True)
class ProjectActor:
    user_id: int
    active_org_id: int


@dataclass(frozen=True)
class CreateProjectCommand:
    application_id: int
    project_code: str
    project_name: str
    start_date: date | None = None
    end_date: date | None = None


@dataclass(frozen=True)
class UpdateProjectCommand:
    project_name: str
    project_status: str
    start_date: date | None = None
    end_date: date | None = None


@dataclass(frozen=True)
class ProjectOrganizationConfiguration:
    org_id: int
    party_type: str
    is_lead: bool = False


@dataclass(frozen=True)
class ProjectMemberConfiguration:
    user_org_id: int
    role_code: str


@dataclass(frozen=True)
class UpdateMilestoneCommand:
    actual_percent: int
    status: str


class ProjectService:
    CODE_PATTERN = re.compile(r"^[A-Z][A-Z0-9_]{1,79}$")
    STATUSES = frozenset({"PLANNED", "ACTIVE", "SUSPENDED", "ARCHIVED"})
    PARTY_TYPES = frozenset(
        {
            "OWNER",
            "REGULATOR",
            "SUPERVISOR",
            "CONTRACTOR",
            "SOFTWARE_VENDOR",
            "PLATFORM",
        }
    )
    MILESTONE_STATUSES = frozenset(
        {"NOT_STARTED", "IN_PROGRESS", "DELAYED", "COMPLETED"}
    )
    MANAGEMENT_ROLES = frozenset(
        {"SYSTEM_ADMIN", "OWNER_LEADER", "WORKORDER_MANAGER"}
    )

    def __init__(
        self,
        repository: ProjectRepository,
        permission_service: PermissionService,
    ) -> None:
        self.repository = repository
        self.permission_service = permission_service

    def structure(self, actor: ProjectActor) -> dict:
        self._require_functional_permissions(
            actor, ("system:application:view", "project:view")
        )
        can_view_all = self._has_functional_permission(
            actor, "project:progress:view-all"
        )
        projects = self.repository.list_accessible_projects(
            actor.user_id,
            include_all=can_view_all,
        )
        applications = []
        for application in self.repository.list_user_applications(actor.user_id):
            applications.append(
                {
                    "id": application.id,
                    "application_code": application.application_code,
                    "application_name": application.application_name,
                    "domain_type": application.domain_type,
                    "projects": [
                        self.project_item(project)
                        for project in projects
                        if project.application_id == application.id
                    ],
                }
            )

        return {
            "applications": applications,
            "role_matrix": [self._role_item(role) for role in self.repository.list_roles()],
            "can_view_all_projects": can_view_all,
            "capabilities": {
                "create": self._has_functional_permission(actor, "project:create"),
                "update": self._has_functional_permission(actor, "project:update"),
                "organizations": self._has_functional_permission(
                    actor, "project:organization:manage"
                ),
                "members": self._has_functional_permission(
                    actor, "project:member:manage"
                ),
                "explain": self._has_functional_permission(
                    actor, "project:authorization:explain"
                ),
            },
        }

    def list_projects(self, actor: ProjectActor) -> list[Project]:
        self._require_functional_permissions(
            actor, ("system:application:view", "project:view")
        )
        return self.repository.list_accessible_projects(
            actor.user_id,
            include_all=self._has_functional_permission(
                actor, "project:progress:view-all"
            ),
        )

    def progress_dashboard(self, actor: ProjectActor) -> dict:
        """Return the lightweight I23 demo read model."""
        self._require_functional_permissions(actor, ("project:progress:view",))
        can_view_all = self._has_functional_permission(
            actor, "project:progress:view-all"
        )
        projects = self.repository.list_accessible_projects(
            actor.user_id, include_all=can_view_all
        )
        items = [self._progress_item(project, actor) for project in projects]
        overall = round(
            sum(item["actual_percent"] for item in items) / len(items)
        ) if items else 0
        planned = round(
            sum(item["planned_percent"] for item in items) / len(items)
        ) if items else 0
        return {
            "summary": {
                "project_count": len(items),
                "system_count": len({item["application_id"] for item in items}),
                "overall_percent": overall,
                "planned_percent": planned,
                "delayed_projects": sum(item["risk_status"] == "DELAYED" for item in items),
            },
            "projects": items,
            "can_view_all_projects": can_view_all,
        }

    def update_milestone(
        self,
        project_id: int,
        milestone_id: int,
        command: UpdateMilestoneCommand,
        actor: ProjectActor,
    ) -> dict:
        project = self._require_project(project_id)
        self._require_project_permission(project, actor, "project:update")
        if project.project_status in {"SUSPENDED", "ARCHIVED"}:
            raise ProjectPermissionDenied("暂停或归档项目不能更新进度")
        if not 0 <= command.actual_percent <= 100:
            raise ProjectValidationError("实际完成率必须在 0 到 100 之间")
        milestone_status = command.status.strip().upper()
        if milestone_status not in self.MILESTONE_STATUSES:
            raise ProjectValidationError(f"不支持的里程碑状态：{milestone_status}")
        if command.actual_percent == 100:
            milestone_status = "COMPLETED"
        elif milestone_status == "COMPLETED":
            raise ProjectValidationError("完成状态的实际完成率必须为 100")
        milestone = self.repository.get_milestone(project.id, milestone_id)
        if milestone is None:
            raise ProjectNotFound(f"项目里程碑不存在：{milestone_id}")
        before = {
            "actual_percent": milestone.actual_percent,
            "status": milestone.status,
        }
        milestone.actual_percent = command.actual_percent
        milestone.status = milestone_status
        self.repository.add_audit(
            "PROJECT_MILESTONE",
            milestone.id,
            "UPDATE",
            actor.user_id,
            {
                "project_id": project.id,
                "before": before,
                "after": {
                    "actual_percent": milestone.actual_percent,
                    "status": milestone.status,
                },
            },
        )
        self.repository.commit()
        self.repository.expire_all()
        return self._progress_item(self._require_project(project.id), actor)

    def get_project(self, project_id: int, actor: ProjectActor) -> Project:
        project = self._require_project(project_id)
        self._require_project_permission(project, actor, "project:view")
        return project

    def require_operational_permission(
        self,
        project_id: int,
        actor: ProjectActor,
        permission_code: str,
        *,
        allow_archived: bool = False,
    ) -> Project:
        """Authorize a business operation in one project data space."""
        project = self._require_project(project_id)
        self._require_project_permission(project, actor, permission_code)
        if project.project_status == "ARCHIVED" and not allow_archived:
            raise ProjectPermissionDenied("项目已归档，仅允许只读访问")
        if project.project_status == "SUSPENDED" and permission_code != "workorder:view":
            raise ProjectPermissionDenied("项目已暂停，仅允许只读访问")
        return project

    def filter_operational_candidates(
        self,
        project_id: int,
        candidate_user_ids: set[int],
        permission_code: str,
    ) -> set[int]:
        """Keep candidates who hold both org and project-role permission."""
        if not self.repository.list_projects():
            return candidate_user_ids
        project = self._require_project(project_id)
        if project.project_status != "ACTIVE":
            return set()
        allowed: set[int] = set()
        for user_id in candidate_user_ids:
            if project.application_id not in {
                application.id
                for application in self.repository.list_user_applications(user_id)
            }:
                continue
            members = self.repository.list_project_members_for_user(project.id, user_id)
            if any(
                self.repository.role_has_permission(member.role_id, permission_code)
                and self.permission_service.has_permission(
                    user_id, permission_code, member.membership.org_id
                )
                for member in members
            ):
                allowed.add(user_id)
        return allowed

    def create(
        self,
        command: CreateProjectCommand,
        actor: ProjectActor,
    ) -> Project:
        self._require_functional_permissions(
            actor, ("system:application:view", "project:create")
        )
        if command.application_id not in {
            application.id
            for application in self.repository.list_user_applications(actor.user_id)
        }:
            raise ProjectPermissionDenied("没有目标生命线系统入口权限")
        code = command.project_code.strip().upper()
        if not self.CODE_PATTERN.fullmatch(code):
            raise ProjectValidationError(
                "项目编码须以字母开头，且只能包含大写字母、数字和下划线"
            )
        if self.repository.get_project(code) is not None:
            raise ProjectConflict(f"项目编码已存在：{code}")
        name = self._required_name(command.project_name)
        self._validate_dates(command.start_date, command.end_date)
        project = Project(
            tenant_id=self.repository.tenant_id,
            application_id=command.application_id,
            project_code=code,
            project_name=name,
            project_status="PLANNED",
            start_date=command.start_date,
            end_date=command.end_date,
        )
        self.repository.add(project)
        self.repository.flush()
        self.repository.add_audit(
            "PROJECT",
            project.id,
            "CREATE",
            actor.user_id,
            {
                "application_id": project.application_id,
                "project_code": project.project_code,
                "project_name": project.project_name,
            },
        )
        self.repository.commit()
        self.repository.refresh(project)
        return self._require_project(project.id)

    def update(
        self,
        project_id: int,
        command: UpdateProjectCommand,
        actor: ProjectActor,
    ) -> Project:
        project = self._require_project(project_id)
        self._require_project_permission(project, actor, "project:update")
        status = command.project_status.strip().upper()
        if status not in self.STATUSES:
            raise ProjectValidationError(f"不支持的项目状态：{status}")
        self._validate_dates(command.start_date, command.end_date)
        before = {
            "project_name": project.project_name,
            "project_status": project.project_status,
            "start_date": str(project.start_date) if project.start_date else None,
            "end_date": str(project.end_date) if project.end_date else None,
        }
        project.project_name = self._required_name(command.project_name)
        project.project_status = status
        project.start_date = command.start_date
        project.end_date = command.end_date
        self.repository.add_audit(
            "PROJECT",
            project.id,
            "UPDATE",
            actor.user_id,
            {
                "before": before,
                "after": {
                    "project_name": project.project_name,
                    "project_status": project.project_status,
                    "start_date": str(project.start_date) if project.start_date else None,
                    "end_date": str(project.end_date) if project.end_date else None,
                },
            },
        )
        self.repository.commit()
        return self._require_project(project.id)

    def delete(self, project_id: int, actor: ProjectActor) -> None:
        project = self._require_project(project_id)
        self._require_project_permission(project, actor, "project:update")
        if project.organization_links or project.members:
            raise ProjectConflict("项目已有参与组织或成员，只能归档，不能删除")
        self.repository.add_audit(
            "PROJECT",
            project.id,
            "DELETE",
            actor.user_id,
            {"project_code": project.project_code},
        )
        self.repository.delete(project)
        self.repository.commit()

    def replace_organizations(
        self,
        project_id: int,
        configurations: tuple[ProjectOrganizationConfiguration, ...],
        actor: ProjectActor,
    ) -> Project:
        project = self._require_project(project_id)
        self._require_project_permission(
            project, actor, "project:organization:manage"
        )
        if not configurations:
            raise ProjectValidationError("项目至少需要一个参与组织")
        if len({item.org_id for item in configurations}) != len(configurations):
            raise ProjectValidationError("同一组织不能重复参加项目")
        lead_items = [item for item in configurations if item.is_lead]
        if len(lead_items) != 1 or lead_items[0].party_type.upper() != "OWNER":
            raise ProjectValidationError("项目必须且只能配置一个甲方牵头组织")

        links: list[ProjectOrganization] = []
        roots = []
        for item in configurations:
            party_type = item.party_type.strip().upper()
            if party_type not in self.PARTY_TYPES:
                raise ProjectValidationError(f"不支持的参与方类型：{party_type}")
            organization = self.repository.get_organization(item.org_id)
            if organization is None or not organization.is_active:
                raise ProjectValidationError(f"参与组织不可用：{item.org_id}")
            roots.append(organization)
            links.append(
                ProjectOrganization(
                    project_id=project.id,
                    org_id=organization.id,
                    party_type=party_type,
                    is_lead=item.is_lead,
                )
            )

        invalid_members = [
            member
            for member in project.members
            if not self._organization_within_roots(
                member.membership.organization.org_path, roots
            )
        ]
        if invalid_members:
            raise ProjectConflict("现有项目成员不属于新的参与组织范围，请先调整成员")
        self.repository.replace_project_organizations(project.id, links)
        self.repository.add_audit(
            "PROJECT_ORGANIZATION",
            project.id,
            "REPLACE",
            actor.user_id,
            {
                "organizations": [
                    {
                        "org_id": item.org_id,
                        "party_type": item.party_type,
                        "is_lead": item.is_lead,
                    }
                    for item in links
                ]
            },
        )
        self.repository.commit()
        self.repository.expire_all()
        return self._require_project(project.id)

    def replace_members(
        self,
        project_id: int,
        configurations: tuple[ProjectMemberConfiguration, ...],
        actor: ProjectActor,
    ) -> Project:
        project = self._require_project(project_id)
        self._require_project_permission(project, actor, "project:member:manage")
        keys = [(item.user_org_id, item.role_code.strip().upper()) for item in configurations]
        if len(keys) != len(set(keys)):
            raise ProjectValidationError("同一项目成员角色不能重复")
        if not configurations:
            raise ProjectValidationError("项目至少需要一个成员")

        roots = [link.organization for link in project.organization_links]
        if not roots:
            raise ProjectValidationError("请先配置项目参与组织")
        members: list[ProjectMember] = []
        management_role_found = False
        for item, (_, role_code) in zip(configurations, keys, strict=True):
            membership = self.repository.get_membership(item.user_org_id)
            if (
                membership is None
                or not membership.is_active
                or not membership.user.is_active
                or not membership.organization.is_active
            ):
                raise ProjectValidationError(f"组织成员关系不可用：{item.user_org_id}")
            if not self._organization_within_roots(
                membership.organization.org_path, roots
            ):
                raise ProjectValidationError("项目成员必须属于参与组织或其下级组织")
            role = self.repository.get_role(role_code)
            if role is None or not role.is_active:
                raise ProjectValidationError(f"项目角色不可用：{role_code}")
            if not self.repository.role_has_permission(role.id, "project:view"):
                raise ProjectValidationError(f"项目角色必须具备 project:view：{role_code}")
            if not self.repository.role_has_permission(
                role.id, "system:application:view"
            ):
                raise ProjectValidationError(
                    f"项目角色必须具备 system:application:view：{role_code}"
                )
            if project.application_id not in {
                application.id
                for application in self.repository.list_user_applications(
                    membership.user_id
                )
            }:
                raise ProjectValidationError("项目成员尚未获得目标系统入口权限")
            management_role_found |= role_code in self.MANAGEMENT_ROLES
            members.append(
                ProjectMember(
                    project_id=project.id,
                    user_org_id=membership.id,
                    role_id=role.id,
                )
            )
        if not management_role_found:
            raise ProjectValidationError("项目至少保留一个管理角色")
        self.repository.replace_project_members(project.id, members)
        self.repository.add_audit(
            "PROJECT_MEMBER",
            project.id,
            "REPLACE",
            actor.user_id,
            {
                "members": [
                    {"user_org_id": item.user_org_id, "role_id": item.role_id}
                    for item in members
                ]
            },
        )
        self.repository.commit()
        self.repository.expire_all()
        return self._require_project(project.id)

    def explain_authorization(
        self,
        project_id: int,
        subject_user_id: int,
        permission_code: str,
        actor: ProjectActor,
    ) -> dict:
        project = self._require_project(project_id)
        self._require_project_permission(
            project, actor, "project:authorization:explain"
        )
        code = permission_code.strip()
        if not code:
            raise ProjectValidationError("权限编码不能为空")
        subject_members = self.repository.list_project_members_for_user(
            project.id, subject_user_id
        )
        matching_roles = sorted(
            member.role.role_code
            for member in subject_members
            if self.repository.role_has_permission(member.role_id, code)
        )
        application_access = project.application_id in {
            application.id
            for application in self.repository.list_user_applications(subject_user_id)
        }
        functional_permission = any(
            self.permission_service.has_permission(
                subject_user_id,
                code,
                member.membership.org_id,
            )
            for member in subject_members
        )
        allowed = bool(
            application_access
            and subject_members
            and matching_roles
            and functional_permission
            and project.project_status != "ARCHIVED"
        )
        return {
            "tenant_id": self.repository.tenant_id,
            "application_id": project.application_id,
            "project_id": project.id,
            "subject_user_id": subject_user_id,
            "permission_code": code,
            "checks": {
                "same_tenant": bool(subject_members),
                "tenant_application_active": project.application.is_active,
                "user_application_access": application_access,
                "project_membership_active": bool(subject_members),
                "member_role_permission": bool(matching_roles),
                "functional_permission": functional_permission,
                "project_not_archived": project.project_status != "ARCHIVED",
            },
            "matching_role_codes": matching_roles,
            "allowed": allowed,
        }

    def replace_user_application_accesses(
        self,
        user_id: int,
        application_ids: tuple[int, ...],
        actor: ProjectActor,
    ) -> list:
        self._require_functional_permissions(
            actor, ("system:application:manage",)
        )
        user = self.repository.get_user(user_id)
        if user is None or not user.is_active:
            raise ProjectValidationError(f"用户不可用：{user_id}")
        if len(application_ids) != len(set(application_ids)):
            raise ProjectValidationError("系统入口不能重复")
        subscriptions = {
            item.application_id: item for item in self.repository.list_subscriptions()
        }
        unknown_ids = set(application_ids) - set(subscriptions)
        if unknown_ids:
            raise ProjectValidationError(
                f"租户未开通目标系统：{sorted(unknown_ids)}"
            )
        accesses = [
            UserApplicationAccess(
                tenant_application_id=subscriptions[application_id].id,
                user_id=user.id,
            )
            for application_id in application_ids
        ]
        self.repository.replace_user_application_accesses(user.id, accesses)
        self.repository.add_audit(
            "USER_APPLICATION",
            user.id,
            "REPLACE",
            actor.user_id,
            {"application_ids": list(application_ids)},
        )
        self.repository.commit()
        return self.repository.list_user_applications(user.id)

    def _require_project_permission(
        self,
        project: Project,
        actor: ProjectActor,
        permission_code: str,
    ) -> None:
        if not self._has_functional_permission(actor, permission_code):
            raise ProjectPermissionDenied(f"缺少功能权限：{permission_code}")
        if project.application_id not in {
            application.id
            for application in self.repository.list_user_applications(actor.user_id)
        }:
            raise ProjectPermissionDenied("没有项目所属系统入口权限")
        if not project.members and permission_code in {
            "project:update",
            "project:organization:manage",
            "project:member:manage",
        }:
            return
        if permission_code in {"project:view", "project:progress:view"} and (
            self._has_functional_permission(actor, "project:progress:view-all")
        ):
            return
        members = self.repository.list_project_members_for_user(
            project.id, actor.user_id
        )
        if not any(
            self.repository.role_has_permission(member.role_id, permission_code)
            for member in members
        ):
            raise ProjectPermissionDenied("项目成员角色未授予该操作")

    def _require_functional_permissions(
        self, actor: ProjectActor, permission_codes: tuple[str, ...]
    ) -> None:
        missing = [
            code
            for code in permission_codes
            if not self._has_functional_permission(actor, code)
        ]
        if missing:
            raise ProjectPermissionDenied(f"缺少功能权限：{', '.join(missing)}")

    def _has_functional_permission(
        self, actor: ProjectActor, permission_code: str
    ) -> bool:
        return self.permission_service.has_permission(
            actor.user_id, permission_code, actor.active_org_id
        )

    def _require_project(self, project_id: int) -> Project:
        project = self.repository.get_project_by_id(project_id)
        if project is None:
            raise ProjectNotFound(f"项目不存在：{project_id}")
        return project

    @staticmethod
    def project_item(project: Project) -> dict:
        return {
            "id": project.id,
            "application_id": project.application_id,
            "project_code": project.project_code,
            "project_name": project.project_name,
            "project_status": project.project_status,
            "start_date": project.start_date,
            "end_date": project.end_date,
            "organizations": [
                {
                    "id": link.id,
                    "org_id": link.org_id,
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
                    "id": member.id,
                    "user_org_id": member.user_org_id,
                    "user_id": member.membership.user_id,
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

    def _progress_item(self, project: Project, actor: ProjectActor) -> dict:
        milestones = sorted(
            project.milestones, key=lambda item: (item.due_date or date.max, item.id)
        )
        total_weight = sum(item.weight for item in milestones) or 1
        planned = round(
            sum(item.weight * item.planned_percent for item in milestones)
            / total_weight
        )
        actual = round(
            sum(item.weight * item.actual_percent for item in milestones)
            / total_weight
        )
        try:
            self._require_project_permission(project, actor, "project:update")
            can_update = project.project_status not in {"SUSPENDED", "ARCHIVED"}
        except ProjectPermissionDenied:
            can_update = False
        return {
            "project_id": project.id,
            "application_id": project.application_id,
            "application_code": project.application.application_code,
            "application_name": project.application.application_name,
            "project_code": project.project_code,
            "project_name": project.project_name,
            "project_status": project.project_status,
            "planned_percent": planned,
            "actual_percent": actual,
            "variance_percent": actual - planned,
            "risk_status": (
                "DELAYED"
                if any(item.status == "DELAYED" for item in milestones)
                else "ON_TRACK"
            ),
            "can_update": can_update,
            "milestones": [
                {
                    "id": item.id,
                    "milestone_code": item.milestone_code,
                    "milestone_name": item.milestone_name,
                    "weight": item.weight,
                    "planned_percent": item.planned_percent,
                    "actual_percent": item.actual_percent,
                    "status": item.status,
                    "due_date": item.due_date,
                }
                for item in milestones
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

    @staticmethod
    def _organization_within_roots(org_path: str, roots: list) -> bool:
        return any(
            org_path == root.org_path or org_path.startswith(f"{root.org_path}/")
            for root in roots
        )

    @staticmethod
    def _required_name(value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ProjectValidationError("项目名称不能为空")
        return normalized

    @staticmethod
    def _validate_dates(start_date: date | None, end_date: date | None) -> None:
        if start_date and end_date and end_date < start_date:
            raise ProjectValidationError("项目结束日期不能早于开始日期")
