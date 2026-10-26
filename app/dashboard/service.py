"""Read models and UI-only action visibility for server-rendered pages."""

from collections import Counter
from urllib.parse import urlencode

from app.auth.service import AuthProfile
from app.iam.admin_service import (
    IAMAdministrationActor,
    OrganizationAdministrationService,
)
from app.iam.authorization import PermissionService
from app.iam.dictionary_admin_service import (
    IAMAuditFilter,
    IAMAuditQueryService,
    PermissionDictionaryService,
)
from app.iam.permission_catalog import BUILT_IN_PERMISSION_CODES
from app.iam.role_admin_service import RoleAdministrationService
from app.iam.service import IAMEntityNotFound, IAMService
from app.iam.user_admin_service import UserAdministrationService
from app.notification.service import NotificationService
from app.operation.service import SavedViewService
from app.workflow.models import WorkflowTask
from app.workflow.service import WorkflowService
from app.workorder.attachment_service import WorkOrderAttachmentService
from app.workorder.batch_service import WorkOrderBatchService
from app.workorder.domain import WorkOrderPermissionDenied
from app.workorder.models import WorkOrder
from app.workorder.repository import WorkOrderListQuery
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
ACTION_LABELS = {
    "CREATE": "创建工单",
    "SUBMIT": "提交工单",
    "DISPATCH": "派单",
    "CLAIM": "认领",
    "SUBMIT_RESULT": "提交处理结果",
    "TRANSFER": "转派",
    "COMMENT": "协作评论",
    "URGE": "催办",
    "ATTACHMENT_UPLOAD": "上传附件",
    "SLA_RESPONSE_BREACH": "响应超时",
    "SLA_RESOLUTION_BREACH": "解决超时",
    "REJECT": "驳回返工",
    "APPROVE": "复核通过",
    "CLOSE": "关闭工单",
}


class DashboardService:
    SYSTEM_PAGES = {
        "organizations": "system:org:view",
        "users": "system:user:view",
        "roles": "system:role:view",
        "permissions": "system:permission:view",
        "audit": "system:audit:view",
    }

    def __init__(
        self,
        iam_service: IAMService,
        permission_service: PermissionService,
        work_order_service: WorkOrderService,
        workflow_service: WorkflowService,
        organization_admin_service: OrganizationAdministrationService,
        user_admin_service: UserAdministrationService,
        role_admin_service: RoleAdministrationService,
        permission_dictionary_service: PermissionDictionaryService,
        iam_audit_query_service: IAMAuditQueryService,
        attachment_service: WorkOrderAttachmentService,
        notification_service: NotificationService,
        saved_view_service: SavedViewService,
    ) -> None:
        self.iam_service = iam_service
        self.permission_service = permission_service
        self.work_order_service = work_order_service
        self.workflow_service = workflow_service
        self.organization_admin_service = organization_admin_service
        self.user_admin_service = user_admin_service
        self.role_admin_service = role_admin_service
        self.permission_dictionary_service = permission_dictionary_service
        self.iam_audit_query_service = iam_audit_query_service
        self.attachment_service = attachment_service
        self.notification_service = notification_service
        self.saved_view_service = saved_view_service
        self.work_order_batch_service = WorkOrderBatchService(work_order_service)

    def common_context(
        self,
        profile: AuthProfile,
        page_title: str,
        active_page: str,
    ) -> dict:
        permissions = set(profile.permission_codes)
        navigation = [
            {"code": "portal", "label": "应用导航", "href": "/portal"},
        ]
        if "project:progress:view" in permissions:
            navigation.append(
                {
                    "code": "project-progress",
                    "label": "项目进度驾驶舱",
                    "href": "/project-progress",
                }
            )
        if profile.applications:
            navigation.append(
                {
                    "code": "data-resources",
                    "label": "数据资源权限",
                    "href": "/data-resources",
                }
            )
        if "workorder:view" in permissions:
            navigation.append({"code": "workorders", "label": "工单中心", "href": "/workorders"})
        navigation.append({"code": "tasks", "label": "我的任务", "href": "/tasks/mine"})
        notifications = self.notification_service.list_for_user(profile.user_id)
        unread_notifications = sum(item.status == "UNREAD" for item in notifications)
        navigation.append(
            {
                "code": "notifications",
                "label": f"通知 ({unread_notifications})" if unread_notifications else "通知",
                "href": "/notifications",
            }
        )
        system_navigation = [
            ("organizations", "组织管理", "/iam/organizations"),
            ("users", "用户管理", "/iam/users"),
            ("roles", "角色管理", "/iam/roles"),
            ("permissions", "权限管理", "/iam/permissions"),
            ("audit", "IAM 审计", "/iam/audit"),
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
            "action_labels": ACTION_LABELS,
            "unread_notifications": unread_notifications,
        }

    @staticmethod
    def default_landing(profile: AuthProfile) -> str:
        if "BUSINESS_LEADER" in profile.role_codes:
            domains = {item.domain_type for item in profile.applications}
            if len(domains) == 1:
                return f"/business-dashboard/{domains.pop()}"
        management_roles = {
            "SYSTEM_ADMIN",
            "OWNER_LEADER",
            "BUSINESS_LEADER",
            "SYSTEM_SPECIALIST",
            "OWNER_PROJECT_MANAGER",
            "SUPERVISOR_ENGINEER",
            "SOFTWARE_DELIVERY",
            "PLATFORM_OPERATOR",
        }
        return "/portal" if management_roles.intersection(profile.role_codes) else "/workorders"

    def portal(self, profile: AuthProfile) -> dict:
        permissions = set(profile.permission_codes)
        domains = []
        domain_metadata = {
            "WATER_SUPPLY": ("供水", "DMA 漏损、水力模型与供水设施 GIS 态势"),
            "DRAINAGE": ("排水", "防涝设施、泵站与积水风险 GIS 态势"),
            "GAS": ("燃气", "燃气管网、阀井与安全隐患 GIS 态势"),
            "HEATING": ("供热", "热力管网、换热站与运行参数 GIS 态势"),
            "ROAD": ("道路", "道路桥梁、监测设施与风险 GIS 态势"),
        }
        for domain_type in dict.fromkeys(item.domain_type for item in profile.applications):
            label, description = domain_metadata.get(
                domain_type, (domain_type, "业务系统与工程项目态势")
            )
            applications = [
                item for item in profile.applications if item.domain_type == domain_type
            ]
            domains.append(
                {
                    "code": domain_type,
                    "label": label,
                    "description": description,
                    "applications": applications,
                    "project_count": sum(
                        project.application_id in {item.id for item in applications}
                        for project in profile.projects
                    ),
                }
            )
        return {
            "portal_domains": domains,
            "can_manage_iam": any(code in permissions for code in self.SYSTEM_PAGES.values()),
            "can_view_workorders": "workorder:view" in permissions,
            "can_view_data_resources": bool(profile.applications),
        }

    def business_dashboard(self, profile: AuthProfile, domain_type: str) -> dict:
        domain = domain_type.strip().upper()
        portal = self.portal(profile)
        visible = next(
            (item for item in portal["portal_domains"] if item["code"] == domain),
            None,
        )
        if visible is None:
            raise PageAccessDenied("当前账号没有该业务方向的系统入口权限")
        application_ids = {item.id for item in visible["applications"]}
        projects = [item for item in profile.projects if item.application_id in application_ids]
        gis_profiles = {
            "WATER_SUPPLY": {
                "theme": "water",
                "metrics": (
                    ("管网总长", "1,286 km"),
                    ("监测点", "842"),
                    ("DMA 分区", "126"),
                    ("今日预警", "7"),
                ),
                "layers": ("供水管网", "DMA 边界", "阀门", "流量计", "压力监测点"),
                "events": (
                    ("滨江路 DMA-07", "夜间最小流量异常", "高", "处理中"),
                    ("城北加压站", "出口压力波动", "中", "待确认"),
                    ("东湖路 DN600", "疑似漏损", "中", "已派单"),
                ),
            },
            "DRAINAGE": {
                "theme": "drainage",
                "metrics": (
                    ("排水管网", "1,640 km"),
                    ("泵站", "48"),
                    ("易涝点", "92"),
                    ("今日预警", "5"),
                ),
                "layers": ("雨水管网", "污水管网", "排水泵站", "易涝点", "液位监测点"),
                "events": (
                    ("人民路下穿", "积水深度超限", "高", "处理中"),
                    ("城南 3# 泵站", "泵组运行异常", "中", "已派单"),
                    ("开发区主干管", "液位快速上涨", "中", "待确认"),
                ),
            },
            "GAS": {
                "theme": "gas",
                "metrics": (
                    ("燃气管网", "986 km"),
                    ("阀井", "1,204"),
                    ("监测设备", "636"),
                    ("今日告警", "4"),
                ),
                "layers": ("高压管线", "中压管线", "调压站", "阀井", "气体监测点"),
                "events": (
                    ("高新区调压站", "出口压力偏高", "高", "处理中"),
                    ("经开大道阀井", "可燃气体浓度预警", "高", "已派单"),
                    ("西环路支线", "第三方施工风险", "中", "待确认"),
                ),
            },
            "HEATING": {
                "theme": "heating",
                "metrics": (
                    ("热力管网", "728 km"),
                    ("换热站", "136"),
                    ("在线测点", "2,418"),
                    ("今日告警", "3"),
                ),
                "layers": ("一次热网", "二次热网", "热源厂", "换热站", "温压监测点"),
                "events": (
                    ("城西换热站", "供回水温差偏低", "中", "处理中"),
                    ("北区一次网", "压力下降", "高", "已派单"),
                    ("学院路小区", "末端温度偏低", "中", "待确认"),
                ),
            },
            "ROAD": {
                "theme": "road",
                "metrics": (
                    ("道路里程", "2,105 km"),
                    ("桥梁", "286"),
                    ("监测设备", "518"),
                    ("今日告警", "6"),
                ),
                "layers": ("城市道路", "桥梁", "隧道", "边坡", "结构监测点"),
                "events": (
                    ("跨江大桥", "伸缩缝位移预警", "中", "处理中"),
                    ("南山隧道", "渗水告警", "中", "已派单"),
                    ("机场快速路", "路面沉降趋势", "高", "待确认"),
                ),
            },
        }
        gis_profile = gis_profiles.get(domain, gis_profiles["ROAD"])
        return {
            "business_domain": visible,
            "business_projects": projects,
            "dashboard_metrics": {
                "systems": len(visible["applications"]),
                "projects": len(projects),
                "online_rate": 98,
                "open_events": max(2, len(projects) * 3),
            },
            "gis_profile": gis_profile,
            "gis_markers": (
                {"left": 18, "top": 62, "label": "西部片区"},
                {"left": 41, "top": 34, "label": "中心城区"},
                {"left": 66, "top": 56, "label": "滨江片区"},
                {"left": 78, "top": 25, "label": "高新片区"},
            ),
            "district_health": (
                ("中心城区", 96),
                ("滨江片区", 91),
                ("高新片区", 88),
                ("西部片区", 94),
            ),
        }

    def dashboard(self, profile: AuthProfile) -> dict:
        actor = self._actor(profile)
        try:
            work_orders = self.work_order_service.list_visible(actor)
        except WorkOrderPermissionDenied:
            work_orders = []
        tasks = self.workflow_service.list_my_tasks(
            profile.user_id,
            profile.tenant_id,
            profile.active_application_id,
            profile.active_project_id,
        )
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

    def organizations(
        self,
        profile: AuthProfile,
        selected_organization_id: int | None = None,
    ) -> dict:
        self._require_system_page(profile, "organizations")
        organizations = self.organization_admin_service.list_organizations(self._iam_actor(profile))
        permissions = set(profile.permission_codes)
        selected_organization = next(
            (
                item
                for item in organizations
                if item.id == selected_organization_id
            ),
            None,
        )
        if selected_organization is None:
            selected_organization = next(
                (item for item in organizations if item.id == profile.active_org_id),
                organizations[0] if organizations else None,
            )
        organization_by_id = {item.id: item for item in organizations}
        return {
            "organizations": organizations,
            "organization_tree": self._organization_tree(organizations),
            "organization_codes": {item.id: item.org_code for item in organizations},
            "selected_organization": selected_organization,
            "selected_parent_organization": (
                organization_by_id.get(selected_organization.parent_id)
                if selected_organization is not None
                else None
            ),
            "selected_child_organizations": (
                [
                    item
                    for item in organizations
                    if item.parent_id == selected_organization.id
                ]
                if selected_organization is not None
                else []
            ),
            "organization_scope_label": self._organization_scope_label(profile),
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
                    "role_codes": {link.role.role_code for link in membership.role_links},
                }
                for membership in user.memberships
            }
            for user in users
        }
        return {
            "users": users,
            "organizations": self.iam_service.list_organizations(),
            "roles": self.iam_service.list_roles(),
            "membership_forms": membership_forms,
            "user_capabilities": {
                "create": "system:user:create" in permissions,
                "update": "system:user:update" in permissions,
                "status": "system:user:status" in permissions,
                "password": "system:user:password" in permissions,
                "membership": "system:user:membership" in permissions,
            },
        }

    def user_detail(self, profile: AuthProfile, user_id: int) -> dict:
        context = self.users(profile)
        context["user"] = self._find_entity(context["users"], user_id, "用户")
        return context

    def roles(self, profile: AuthProfile) -> dict:
        self._require_system_page(profile, "roles")
        roles = self.iam_service.list_roles()
        organizations = self.iam_service.list_organizations()
        permissions = set(profile.permission_codes)
        authorization_forms = {
            role.id: {
                scope.permission_code: {
                    "scope_type": scope.scope_type,
                    "custom_org_ids": set(
                        scope.scope_config.get("org_ids", [])
                        if isinstance(scope.scope_config, dict)
                        else []
                    ),
                }
                for scope in role.data_scopes
            }
            for role in roles
        }
        role_bindings = self._role_bindings(self.iam_service.list_users())
        return {
            "roles": roles,
            "permissions": self.iam_service.list_permissions(),
            "organizations": organizations,
            "authorization_forms": authorization_forms,
            "role_bindings": role_bindings,
            "role_capabilities": {
                "create": "system:role:create" in permissions,
                "update": "system:role:update" in permissions,
                "status": "system:role:status" in permissions,
                "authorize": "system:role:authorize" in permissions,
            },
        }

    def role_detail(self, profile: AuthProfile, role_id: int) -> dict:
        context = self.roles(profile)
        context["role"] = self._find_entity(context["roles"], role_id, "角色")
        return context

    def permissions(self, profile: AuthProfile) -> dict:
        self._require_system_page(profile, "permissions")
        permissions = set(profile.permission_codes)
        return {
            "permissions": self.iam_service.list_permissions(),
            "built_in_permission_codes": BUILT_IN_PERMISSION_CODES,
            "permission_capabilities": {
                "create": "system:permission:create" in permissions,
                "update": "system:permission:update" in permissions,
                "delete": "system:permission:delete" in permissions,
            },
        }

    def audit_logs(
        self,
        profile: AuthProfile,
        filters: IAMAuditFilter,
    ) -> dict:
        self._require_system_page(profile, "audit")
        logs = self.iam_audit_query_service.list_logs(filters, self._iam_actor(profile))
        return {"audit_logs": logs, "audit_filters": filters}

    def work_orders(
        self,
        profile: AuthProfile,
        query: WorkOrderListQuery,
    ) -> dict:
        actor = self._actor(profile)
        result = self.work_order_service.search_visible(actor, query)
        saved_views = self.saved_view_service.list(profile.user_id, "WORKORDERS")
        filter_params: dict[str, object] = {
            "sort_by": query.sort_by,
            "sort_direction": query.sort_direction,
            "page_size": query.page_size,
        }
        if query.keyword:
            filter_params["keyword"] = query.keyword
        if query.statuses:
            filter_params["status"] = list(query.statuses)
        if query.priorities:
            filter_params["priority"] = list(query.priorities)
        if query.sla_statuses:
            filter_params["sla_status"] = list(query.sla_statuses)
        if query.organization_id is not None:
            filter_params["organization_id"] = query.organization_id
        pages = max(1, (result.total + result.page_size - 1) // result.page_size)
        return {
            "work_orders": result.items,
            "work_order_page": result,
            "list_query": query,
            "list_filter_params": filter_params,
            "work_order_pages": pages,
            "previous_page_href": (
                f"/workorders?{urlencode({**filter_params, 'page': query.page - 1}, doseq=True)}"
                if query.page > 1
                else None
            ),
            "next_page_href": (
                f"/workorders?{urlencode({**filter_params, 'page': query.page + 1}, doseq=True)}"
                if query.page < pages
                else None
            ),
            "saved_views": [
                {
                    "view": item,
                    "href": f"/workorders?{urlencode(item.filters_json, doseq=True)}",
                }
                for item in saved_views
            ],
            "organizations": [
                item for item in self.iam_service.list_organizations() if item.is_active
            ],
            "can_create": "workorder:create" in profile.permission_codes,
            "can_evaluate_sla": "workorder:sla:evaluate" in profile.permission_codes,
            "can_batch_dispatch": "workorder:dispatch" in profile.permission_codes,
            "can_batch_urge": "workorder:urge" in profile.permission_codes,
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
        matching_tasks = [task for task in tasks if task.instance.business_id == work_order_id]
        review_organizations = self.work_order_service.review_organizations(work_order)
        if review_organizations is None:
            review_organizations = self._role_organizations("REVIEWER")
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
            "review_organizations": review_organizations,
            "transfer_targets": [
                user
                for user in self.iam_service.list_users()
                if user.id != work_order.current_assignee_id
                and self.permission_service.has_permission(
                    user.id,
                    "workorder:handle",
                    work_order.current_org_id,
                )
            ],
            "attachments": self.attachment_service.list_for_work_order(
                work_order.id,
                actor,
            ),
            "can_upload_attachment": "workorder:attachment" in profile.permission_codes,
        }

    def _role_organizations(self, role_code: str) -> list:
        organization_ids = {
            membership.org_id
            for user in self.iam_service.list_users()
            if user.is_active
            for membership in user.memberships
            if membership.is_active
            and any(
                link.role.is_active and link.role.role_code == role_code
                for link in membership.role_links
            )
        }
        return [
            organization
            for organization in self.iam_service.list_organizations()
            if organization.is_active and organization.id in organization_ids
        ]

    def notifications(self, profile: AuthProfile) -> dict:
        return {"notifications": self.notification_service.list_for_user(profile.user_id)}

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
        return WorkOrderActor(
            profile.user_id,
            profile.active_org_id,
            profile.tenant_id,
            profile.active_application_id,
            profile.active_project_id,
        )

    @staticmethod
    def _iam_actor(profile: AuthProfile) -> IAMAdministrationActor:
        return IAMAdministrationActor(profile.user_id, profile.active_org_id)

    def _require_system_page(self, profile: AuthProfile, page: str) -> None:
        permission_code = self.SYSTEM_PAGES[page]
        if not self.permission_service.has_permission(
            profile.user_id,
            permission_code,
            profile.active_org_id,
        ):
            raise PageAccessDenied(f"缺少页面权限：{permission_code}")

    def _organization_scope_label(self, profile: AuthProfile) -> str:
        visible_ids = self.permission_service.organization_scope_ids(
            profile.user_id,
            self.SYSTEM_PAGES["organizations"],
            profile.active_org_id,
        )
        return "租户全部组织" if visible_ids is None else "当前角色数据范围"

    @staticmethod
    def _organization_tree(organizations: list) -> list[dict]:
        nodes = {item.id: {"organization": item, "children": []} for item in organizations}
        roots = []
        for item in organizations:
            node = nodes[item.id]
            parent = nodes.get(item.parent_id)
            if parent is None:
                roots.append(node)
            else:
                parent["children"].append(node)
        return roots

    @staticmethod
    def _find_entity(items: list, entity_id: int, label: str):
        entity = next((item for item in items if item.id == entity_id), None)
        if entity is None:
            raise IAMEntityNotFound(f"{label}不存在或不在当前租户中")
        return entity

    @staticmethod
    def _role_bindings(users: list) -> dict[int, list[dict]]:
        result: dict[int, list[dict]] = {}
        for user in users:
            for membership in user.memberships:
                for link in membership.role_links:
                    result.setdefault(link.role_id, []).append(
                        {"user": user, "membership": membership}
                    )
        return result

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
        if "workorder:comment" in permissions:
            actions.add("comment")
        if (
            work_order.status in WorkOrderService.COLLABORATION_STATUSES
            and "workorder:urge" in permissions
        ):
            actions.add("urge")
        if work_order.status == "PROCESSING" and "workorder:transfer" in permissions:
            actions.add("transfer")
        return actions

    def _task_candidate_labels(
        self,
        tasks: list[WorkflowTask],
    ) -> dict[int, list[str]]:
        user_ids = {candidate.resolved_user_id for task in tasks for candidate in task.candidates}
        labels = self.iam_service.active_user_labels(user_ids)
        return {
            task.id: [
                labels[candidate.resolved_user_id]
                for candidate in task.candidates
                if candidate.resolved_user_id in labels
            ]
            for task in tasks
        }
