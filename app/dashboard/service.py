"""Read models and UI-only action visibility for server-rendered pages."""

from collections import Counter

from app.auth.service import AuthProfile
from app.iam.admin_service import OrganizationAdministrationService
from app.iam.authorization import PermissionService
from app.iam.service import IAMService
from app.iam.user_admin_service import UserAdministrationService
from app.workflow.models import WorkflowTask
from app.workflow.service import WorkflowService
from app.workorder.domain import WorkOrderPermissionDenied
from app.workorder.models import WorkOrder
from app.workorder.service import WorkOrderActor, WorkOrderService

from .domain import PageAccessDenied

STATUS_LABELS = {
    "DRAFT": "草稿",
    "PENDING_DISPATCH": "待派单",
    "PENDING_CLAIM": "待认领",
    "PROCESSING": "处理中",
    "PENDING_REVIEW": "待复核",
    "COMPLETED": "已完成",
    "CLOSED": "已关闭",
}


class DashboardService:
    SYSTEM_PAGES = {
        "organizations": "system:org:view",
        "users": "system:user:view",
        "roles": "system:role:view",
        "positions": "system:position:view",
        "permissions": "system:permission:view",
    }

    def __init__(
        self,
        iam_service: IAMService,
        permission_service: PermissionService,
        work_order_service: WorkOrderService,
        workflow_service: WorkflowService,
        organization_admin_service: OrganizationAdministrationService,
        user_admin_service: UserAdministrationService,
    ) -> None:
        self.iam_service = iam_service
        self.permission_service = permission_service
        self.work_order_service = work_order_service
        self.workflow_service = workflow_service
        self.organization_admin_service = organization_admin_service
        self.user_admin_service = user_admin_service

    def common_context(
        self,
        profile: AuthProfile,
        page_title: str,
        active_page: str,
    ) -> dict:
        permissions = set(profile.permission_codes)
        navigation = [
            {"code": "dashboard", "label": "工作台", "href": "/dashboard"},
        ]
        if "workorder:view" in permissions:
            navigation.append(
                {"code": "workorders", "label": "工单中心", "href": "/workorders"}
            )
        navigation.append(
            {"code": "tasks", "label": "我的任务", "href": "/tasks/mine"}
        )
        system_navigation = [
            ("organizations", "组织管理", "/iam/organizations"),
            ("users", "用户管理", "/iam/users"),
            ("roles", "角色管理", "/iam/roles"),
            ("positions", "岗位管理", "/iam/positions"),
            ("permissions", "权限管理", "/iam/permissions"),
        ]
        navigation.extend(
            {"code": code, "label": label, "href": href}
            for code, label, href in system_navigation
            if self.SYSTEM_PAGES[code] in permissions
        )
        return {
            "page_title": page_title,
            "active_page": active_page,
            "profile": profile,
            "navigation": navigation,
            "status_labels": STATUS_LABELS,
        }

    def dashboard(self, profile: AuthProfile) -> dict:
        actor = self._actor(profile)
        try:
            work_orders = self.work_order_service.list_visible(actor)
        except WorkOrderPermissionDenied:
            work_orders = []
        tasks = self.workflow_service.list_my_tasks(profile.user_id)
        stats = Counter(work_order.status for work_order in work_orders)
        recent_actions = []
        for work_order in work_orders[:8]:
            for action in self.work_order_service.timeline(work_order.id, actor):
                recent_actions.append((action, work_order))
        recent_actions.sort(key=lambda item: (item[0].created_at, item[0].id), reverse=True)
        return {
            "work_orders": work_orders[:6],
            "tasks": tasks[:6],
            "stats": stats,
            "recent_actions": recent_actions[:8],
            "candidate_labels": self._task_candidate_labels(tasks),
        }

    def organizations(self, profile: AuthProfile) -> dict:
        self._require_system_page(profile, "organizations")
        organizations = self.iam_service.list_organizations()
        permissions = set(profile.permission_codes)
        return {
            "organizations": organizations,
            "organization_codes": {item.id: item.org_code for item in organizations},
            "organization_capabilities": {
                "create": "system:org:create" in permissions,
                "update": "system:org:update" in permissions,
                "status": "system:org:status" in permissions,
                "delete": "system:org:delete" in permissions,
            },
        }

    def users(self, profile: AuthProfile) -> dict:
        self._require_system_page(profile, "users")
        users = self.iam_service.list_users()
        permissions = set(profile.permission_codes)
        membership_forms = {
            user.id: {
                membership.org_id: {
                    "is_primary": membership.is_primary,
                    "is_active": membership.is_active,
                    "role_codes": {
                        link.role.role_code for link in membership.role_links
                    },
                    "position_codes": {
                        link.position.position_code
                        for link in membership.position_links
                    },
                }
                for membership in user.memberships
            }
            for user in users
        }
        return {
            "users": users,
            "organizations": self.iam_service.list_organizations(),
            "roles": self.iam_service.list_roles(),
            "positions": self.iam_service.list_positions(),
            "membership_forms": membership_forms,
            "user_capabilities": {
                "create": "system:user:create" in permissions,
                "update": "system:user:update" in permissions,
                "status": "system:user:status" in permissions,
                "password": "system:user:password" in permissions,
                "membership": "system:user:membership" in permissions,
            },
        }

    def roles(self, profile: AuthProfile) -> dict:
        self._require_system_page(profile, "roles")
        return {"roles": self.iam_service.list_roles()}

    def positions(self, profile: AuthProfile) -> dict:
        self._require_system_page(profile, "positions")
        return {"positions": self.iam_service.list_positions()}

    def permissions(self, profile: AuthProfile) -> dict:
        self._require_system_page(profile, "permissions")
        return {"permissions": self.iam_service.list_permissions()}

    def work_orders(self, profile: AuthProfile) -> dict:
        actor = self._actor(profile)
        return {
            "work_orders": self.work_order_service.list_visible(actor),
            "can_create": "workorder:create" in profile.permission_codes,
        }

    def work_order_detail(
        self,
        profile: AuthProfile,
        work_order_id: int,
    ) -> dict:
        actor = self._actor(profile)
        work_order = self.work_order_service.get_visible(work_order_id, actor)
        timeline = self.work_order_service.timeline(work_order_id, actor)
        tasks = self.workflow_service.list_my_tasks(profile.user_id)
        matching_tasks = [
            task
            for task in tasks
            if task.instance.business_id == work_order_id
        ]
        return {
            "work_order": work_order,
            "timeline": timeline,
            "current_tasks": matching_tasks,
            "actions": self._visible_actions(profile, work_order, matching_tasks),
            "organizations": [
                organization
                for organization in self.iam_service.list_organizations()
                if organization.is_active
            ],
        }

    def my_tasks(self, profile: AuthProfile) -> dict:
        tasks = self.workflow_service.list_my_tasks(profile.user_id)
        return {
            "tasks": tasks,
            "candidate_labels": self._task_candidate_labels(tasks),
            "claimable_task_ids": {
                task.id
                for task in tasks
                if task.task_type == "HANDLE"
                and task.status == "PENDING"
                and "workorder:claim" in profile.permission_codes
            },
        }

    @staticmethod
    def _actor(profile: AuthProfile) -> WorkOrderActor:
        return WorkOrderActor(profile.user_id, profile.active_org_id)

    def _require_system_page(self, profile: AuthProfile, page: str) -> None:
        permission_code = self.SYSTEM_PAGES[page]
        if not self.permission_service.has_permission(
            profile.user_id,
            permission_code,
            profile.active_org_id,
        ):
            raise PageAccessDenied(f"缺少页面权限：{permission_code}")

    @staticmethod
    def _visible_actions(
        profile: AuthProfile,
        work_order: WorkOrder,
        tasks: list[WorkflowTask],
    ) -> set[str]:
        permissions = set(profile.permission_codes)
        task_types = {task.task_type for task in tasks}
        actions = set()
        if (
            work_order.status == "DRAFT"
            and work_order.created_by == profile.user_id
            and "workorder:create" in permissions
        ):
            actions.add("submit")
        if (
            work_order.status == "PENDING_DISPATCH"
            and "workorder:dispatch" in permissions
            and "DISPATCH" in task_types
        ):
            actions.add("dispatch")
        if (
            work_order.status == "PROCESSING"
            and work_order.current_assignee_id == profile.user_id
            and "workorder:handle" in permissions
        ):
            actions.add("result")
        if (
            work_order.status == "PENDING_REVIEW"
            and "workorder:review" in permissions
            and "REVIEW" in task_types
        ):
            actions.add("review")
        if work_order.status == "COMPLETED" and "workorder:close" in permissions:
            actions.add("close")
        return actions

    def _task_candidate_labels(
        self,
        tasks: list[WorkflowTask],
    ) -> dict[int, list[str]]:
        user_ids = {
            candidate.resolved_user_id
            for task in tasks
            for candidate in task.candidates
        }
        labels = self.iam_service.active_user_labels(user_ids)
        return {
            task.id: [
                labels[candidate.resolved_user_id]
                for candidate in task.candidates
                if candidate.resolved_user_id in labels
            ]
            for task in tasks
        }
