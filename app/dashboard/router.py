"""Server-rendered demonstration pages and form actions."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Annotated
from urllib.parse import parse_qs, quote

from fastapi import APIRouter, Depends, File, Request, UploadFile, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.auth.repository import AuthRepository
from app.auth.router import get_auth_service
from app.auth.service import (
    ActiveApplicationDenied,
    ActiveOrganizationDenied,
    ActiveProjectDenied,
    AuthenticationError,
    AuthProfile,
    AuthService,
    AuthSessionRevocationService,
    RequestContext,
)
from app.db.dependencies import get_db_session
from app.iam.admin_service import (
    CreateOrganizationCommand,
    IAMAdministrationActor,
    IAMAdministrationConflict,
    IAMAdministrationPermissionDenied,
    IAMAdministrationValidationError,
    OrganizationAdministrationService,
    UpdateOrganizationCommand,
)
from app.iam.authorization import PermissionService
from app.iam.dictionary_admin_service import (
    CreatePermissionCommand,
    CreatePositionCommand,
    IAMAuditFilter,
    IAMAuditQueryService,
    PermissionDictionaryService,
    PositionAdministrationService,
    UpdatePermissionCommand,
    UpdatePositionCommand,
)
from app.iam.repository import IAMRepository
from app.iam.role_admin_service import (
    CreateRoleCommand,
    PermissionScopeConfiguration,
    RoleAdministrationService,
    UpdateRoleCommand,
)
from app.iam.service import DuplicateIAMCode, IAMEntityNotFound, IAMService
from app.iam.user_admin_service import (
    CreateUserCommand,
    MembershipConfiguration,
    UpdateUserCommand,
    UserAdministrationService,
)
from app.notification.repository import NotificationRepository
from app.notification.service import NotificationNotFound, NotificationService
from app.operation.repository import SavedViewRepository
from app.operation.service import SavedViewError, SavedViewService
from app.project.repository import ProjectRepository
from app.project.service import (
    CreateProjectCommand,
    ProjectActor,
    ProjectConflict,
    ProjectMemberConfiguration,
    ProjectNotFound,
    ProjectOrganizationConfiguration,
    ProjectPermissionDenied,
    ProjectService,
    ProjectValidationError,
    UpdateProjectCommand,
)
from app.workflow.domain import TaskAccessDenied, WorkflowError
from app.workflow.factory import build_workflow_service
from app.workflow.repository import WorkflowRepository
from app.workorder.attachment_service import WorkOrderAttachmentService
from app.workorder.domain import (
    WorkOrderError,
    WorkOrderNotFound,
    WorkOrderPermissionDenied,
    WorkOrderValidationError,
)
from app.workorder.repository import WorkOrderListQuery, WorkOrderRepository
from app.workorder.service import (
    CreateWorkOrderCommand,
    WorkOrderActor,
    WorkOrderService,
)

from .domain import PageAccessDenied, PageAuthenticationRequired
from .service import DashboardService

router = APIRouter(tags=["demo-pages"])
templates = Jinja2Templates(
    directory=str(Path(__file__).resolve().parents[1] / "templates")
)


@dataclass(frozen=True)
class PageIdentity:
    context: RequestContext
    profile: AuthProfile


def get_page_identity(
    request: Request,
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
) -> PageIdentity:
    settings = request.app.state.settings
    try:
        context = auth_service.authenticate(
            request.cookies.get(settings.auth_cookie_name)
        )
        return PageIdentity(context, auth_service.profile(context))
    except (AuthenticationError, ActiveOrganizationDenied) as error:
        raise PageAuthenticationRequired(str(error)) from error


def get_dashboard_service(
    session: Annotated[Session, Depends(get_db_session)],
    identity: Annotated[PageIdentity, Depends(get_page_identity)],
) -> DashboardService:
    iam_repository = IAMRepository(session, identity.context.tenant_id)
    permission_service = PermissionService(iam_repository)
    workflow_service = build_workflow_service(session, identity.context.tenant_id)
    notification_service = NotificationService(NotificationRepository(session))
    work_order_repository = WorkOrderRepository(session)
    project_service = ProjectService(
        ProjectRepository(session, identity.context.tenant_id), permission_service
    )
    work_order_service = WorkOrderService(
        work_order_repository,
        permission_service,
        workflow_service,
        notification_service,
        project_service,
    )
    return DashboardService(
        IAMService(iam_repository),
        permission_service,
        work_order_service,
        workflow_service,
        OrganizationAdministrationService(iam_repository, permission_service),
        UserAdministrationService(
            iam_repository,
            permission_service,
            AuthSessionRevocationService(AuthRepository(session)),
        ),
        RoleAdministrationService(iam_repository, permission_service),
        PositionAdministrationService(
            iam_repository,
            permission_service,
            WorkflowRepository(session),
        ),
        PermissionDictionaryService(iam_repository, permission_service),
        IAMAuditQueryService(iam_repository, permission_service),
        WorkOrderAttachmentService(
            work_order_repository, permission_service, project_service=project_service
        ),
        notification_service,
        SavedViewService(SavedViewRepository(session)),
    )


def get_page_project_service(
    session: Annotated[Session, Depends(get_db_session)],
    identity: Annotated[PageIdentity, Depends(get_page_identity)],
) -> ProjectService:
    iam_repository = IAMRepository(session, identity.context.tenant_id)
    return ProjectService(
        ProjectRepository(session, identity.context.tenant_id),
        PermissionService(iam_repository),
    )


def _page(
    request: Request,
    service: DashboardService,
    identity: PageIdentity,
    template_name: str,
    title: str,
    active_page: str,
    data: dict | None = None,
    *,
    status_code: int = status.HTTP_200_OK,
) -> HTMLResponse:
    context = service.common_context(identity.profile, title, active_page)
    context.update(data or {})
    context["request"] = request
    return templates.TemplateResponse(
        request=request,
        name=template_name,
        context=context,
        status_code=status_code,
    )


async def _form(request: Request) -> dict[str, str]:
    parsed = parse_qs((await request.body()).decode("utf-8"), keep_blank_values=True)
    return {key: values[-1] for key, values in parsed.items()}


async def _form_lists(request: Request) -> dict[str, list[str]]:
    return parse_qs((await request.body()).decode("utf-8"), keep_blank_values=True)


def _actor(identity: PageIdentity) -> WorkOrderActor:
    return WorkOrderActor(
        identity.context.current_user_id, identity.context.active_org_id,
        identity.context.tenant_id, identity.context.active_application_id,
        identity.context.active_project_id,
    )


def _friendly_error(
    request: Request,
    service: DashboardService,
    identity: PageIdentity,
    error: Exception,
) -> HTMLResponse:
    if isinstance(
        error,
        (
            IAMAdministrationPermissionDenied,
            PageAccessDenied,
            TaskAccessDenied,
            WorkOrderPermissionDenied,
            ProjectPermissionDenied,
        ),
    ):
        code = status.HTTP_403_FORBIDDEN
        title = "没有访问权限"
    elif isinstance(
        error,
        (IAMEntityNotFound, NotificationNotFound, ProjectNotFound, WorkOrderNotFound),
    ):
        code = status.HTTP_404_NOT_FOUND
        title = "没有找到工单"
    elif isinstance(
        error,
        (
            IAMAdministrationValidationError,
            ProjectValidationError,
            ValueError,
            WorkOrderValidationError,
        ),
    ):
        code = status.HTTP_422_UNPROCESSABLE_CONTENT
        title = "提交内容不完整"
    else:
        code = status.HTTP_409_CONFLICT
        title = "当前操作无法完成"
    return _page(
        request,
        service,
        identity,
        "error.html",
        title,
        "",
        {"error_title": title, "error_message": str(error)},
        status_code=code,
    )


@router.get("/", include_in_schema=False)
def root() -> RedirectResponse:
    return RedirectResponse("/dashboard", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/login", response_class=HTMLResponse, include_in_schema=False)
def login_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request=request,
        name="login.html",
        context={"request": request},
    )


@router.get("/dashboard", response_class=HTMLResponse, include_in_schema=False)
def dashboard_page(
    request: Request,
    identity: Annotated[PageIdentity, Depends(get_page_identity)],
    service: Annotated[DashboardService, Depends(get_dashboard_service)],
) -> HTMLResponse:
    return _page(
        request,
        service,
        identity,
        "dashboard.html",
        "工作台",
        "dashboard",
        service.dashboard(identity.profile),
    )


@router.get("/lifeline", response_class=HTMLResponse, include_in_schema=False)
def lifeline_page(
    request: Request,
    identity: Annotated[PageIdentity, Depends(get_page_identity)],
    dashboard_service: Annotated[DashboardService, Depends(get_dashboard_service)],
    project_service: Annotated[ProjectService, Depends(get_page_project_service)],
) -> HTMLResponse:
    try:
        structure = project_service.structure(
            ProjectActor(
                identity.context.current_user_id,
                identity.context.active_org_id,
            )
        )
    except ProjectPermissionDenied as error:
        raise PageAccessDenied(str(error)) from error
    structure.update(
        {
            "organizations": dashboard_service.iam_service.list_organizations(),
            "users": dashboard_service.iam_service.list_users(),
            "roles": dashboard_service.iam_service.list_roles(),
        }
    )
    return _page(
        request,
        dashboard_service,
        identity,
        "lifeline.html",
        "城市生命线权限结构",
        "lifeline",
        structure,
    )


def _optional_date(value: str | None) -> date | None:
    return date.fromisoformat(value) if value else None


@router.post("/ui/projects", include_in_schema=False, response_model=None)
async def create_project_page(
    request: Request,
    identity: Annotated[PageIdentity, Depends(get_page_identity)],
    dashboard_service: Annotated[DashboardService, Depends(get_dashboard_service)],
    project_service: Annotated[ProjectService, Depends(get_page_project_service)],
) -> HTMLResponse | RedirectResponse:
    values = await _form(request)
    try:
        project_service.create(
            CreateProjectCommand(
                application_id=int(values.get("application_id", "0")),
                project_code=values.get("project_code", ""),
                project_name=values.get("project_name", ""),
                start_date=_optional_date(values.get("start_date")),
                end_date=_optional_date(values.get("end_date")),
            ),
            ProjectActor(
                identity.context.current_user_id,
                identity.context.active_org_id,
            ),
        )
    except (ProjectPermissionDenied, ProjectValidationError, ProjectConflict, ValueError) as error:
        return _friendly_error(request, dashboard_service, identity, error)
    return RedirectResponse("/lifeline", status_code=status.HTTP_303_SEE_OTHER)


@router.post(
    "/ui/projects/{project_id}/update",
    include_in_schema=False,
    response_model=None,
)
async def update_project_page(
    request: Request,
    project_id: int,
    identity: Annotated[PageIdentity, Depends(get_page_identity)],
    dashboard_service: Annotated[DashboardService, Depends(get_dashboard_service)],
    project_service: Annotated[ProjectService, Depends(get_page_project_service)],
) -> HTMLResponse | RedirectResponse:
    values = await _form(request)
    try:
        project_service.update(
            project_id,
            UpdateProjectCommand(
                project_name=values.get("project_name", ""),
                project_status=values.get("project_status", ""),
                start_date=_optional_date(values.get("start_date")),
                end_date=_optional_date(values.get("end_date")),
            ),
            ProjectActor(
                identity.context.current_user_id,
                identity.context.active_org_id,
            ),
        )
    except (
        ProjectPermissionDenied,
        ProjectNotFound,
        ProjectValidationError,
        ValueError,
    ) as error:
        return _friendly_error(request, dashboard_service, identity, error)
    return RedirectResponse("/lifeline", status_code=status.HTTP_303_SEE_OTHER)


@router.post(
    "/ui/projects/{project_id}/organizations",
    include_in_schema=False,
    response_model=None,
)
async def replace_project_organizations_page(
    request: Request,
    project_id: int,
    identity: Annotated[PageIdentity, Depends(get_page_identity)],
    dashboard_service: Annotated[DashboardService, Depends(get_dashboard_service)],
    project_service: Annotated[ProjectService, Depends(get_page_project_service)],
) -> HTMLResponse | RedirectResponse:
    values = await _form_lists(request)
    selected_org_ids = values.get("party_org_id", [])
    lead_org_id = values.get("lead_org_id", [""])[-1]
    try:
        configurations = tuple(
            ProjectOrganizationConfiguration(
                org_id=int(org_id),
                party_type=values.get(f"party_type_{org_id}", [""])[-1],
                is_lead=org_id == lead_org_id,
            )
            for org_id in selected_org_ids
        )
        project_service.replace_organizations(
            project_id,
            configurations,
            ProjectActor(
                identity.context.current_user_id,
                identity.context.active_org_id,
            ),
        )
    except (
        ProjectConflict,
        ProjectNotFound,
        ProjectPermissionDenied,
        ProjectValidationError,
        ValueError,
    ) as error:
        return _friendly_error(request, dashboard_service, identity, error)
    return RedirectResponse("/lifeline", status_code=status.HTTP_303_SEE_OTHER)


@router.post(
    "/ui/projects/{project_id}/members",
    include_in_schema=False,
    response_model=None,
)
async def replace_project_members_page(
    request: Request,
    project_id: int,
    identity: Annotated[PageIdentity, Depends(get_page_identity)],
    dashboard_service: Annotated[DashboardService, Depends(get_dashboard_service)],
    project_service: Annotated[ProjectService, Depends(get_page_project_service)],
) -> HTMLResponse | RedirectResponse:
    values = await _form_lists(request)
    selected_membership_ids = values.get("member_user_org_id", [])
    try:
        configurations = tuple(
            ProjectMemberConfiguration(
                user_org_id=int(user_org_id),
                role_code=values.get(f"member_role_{user_org_id}", [""])[-1],
            )
            for user_org_id in selected_membership_ids
        )
        project_service.replace_members(
            project_id,
            configurations,
            ProjectActor(
                identity.context.current_user_id,
                identity.context.active_org_id,
            ),
        )
    except (
        ProjectNotFound,
        ProjectPermissionDenied,
        ProjectValidationError,
        ValueError,
    ) as error:
        return _friendly_error(request, dashboard_service, identity, error)
    return RedirectResponse("/lifeline", status_code=status.HTTP_303_SEE_OTHER)


def _iam_page(
    request: Request,
    identity: PageIdentity,
    service: DashboardService,
    page: str,
    title: str,
) -> HTMLResponse:
    try:
        data = getattr(service, page)(identity.profile)
    except PageAccessDenied as error:
        return _friendly_error(request, service, identity, error)
    return _page(request, service, identity, f"{page}.html", title, page, data)


@router.get("/iam/organizations", response_class=HTMLResponse, include_in_schema=False)
def organizations_page(
    request: Request,
    identity: Annotated[PageIdentity, Depends(get_page_identity)],
    service: Annotated[DashboardService, Depends(get_dashboard_service)],
) -> HTMLResponse:
    return _iam_page(request, identity, service, "organizations", "组织管理")


@router.get("/iam/users", response_class=HTMLResponse, include_in_schema=False)
def users_page(
    request: Request,
    identity: Annotated[PageIdentity, Depends(get_page_identity)],
    service: Annotated[DashboardService, Depends(get_dashboard_service)],
) -> HTMLResponse:
    return _iam_page(request, identity, service, "users", "用户管理")


@router.get("/iam/roles", response_class=HTMLResponse, include_in_schema=False)
def roles_page(
    request: Request,
    identity: Annotated[PageIdentity, Depends(get_page_identity)],
    service: Annotated[DashboardService, Depends(get_dashboard_service)],
) -> HTMLResponse:
    return _iam_page(request, identity, service, "roles", "角色管理")


@router.get("/iam/positions", response_class=HTMLResponse, include_in_schema=False)
def positions_page(
    request: Request,
    identity: Annotated[PageIdentity, Depends(get_page_identity)],
    service: Annotated[DashboardService, Depends(get_dashboard_service)],
) -> HTMLResponse:
    return _iam_page(request, identity, service, "positions", "岗位管理")


@router.get("/iam/permissions", response_class=HTMLResponse, include_in_schema=False)
def permissions_page(
    request: Request,
    identity: Annotated[PageIdentity, Depends(get_page_identity)],
    service: Annotated[DashboardService, Depends(get_dashboard_service)],
) -> HTMLResponse:
    return _iam_page(request, identity, service, "permissions", "权限管理")


@router.get("/iam/audit", response_class=HTMLResponse, include_in_schema=False)
def iam_audit_page(
    request: Request,
    identity: Annotated[PageIdentity, Depends(get_page_identity)],
    service: Annotated[DashboardService, Depends(get_dashboard_service)],
) -> HTMLResponse:
    entity_id_value = request.query_params.get("entity_id", "").strip()
    try:
        filters = IAMAuditFilter(
            entity_type=request.query_params.get("entity_type") or None,
            entity_id=int(entity_id_value) if entity_id_value else None,
            action=request.query_params.get("action") or None,
            operator_username=(
                request.query_params.get("operator_username") or None
            ),
            limit=100,
        )
        data = service.audit_logs(identity.profile, filters)
    except (
        IAMAdministrationPermissionDenied,
        IAMAdministrationValidationError,
        PageAccessDenied,
        ValueError,
    ) as error:
        return _friendly_error(request, service, identity, error)
    return _page(
        request,
        service,
        identity,
        "audit.html",
        "IAM 审计",
        "audit",
        data,
    )


@router.get("/workorders", response_class=HTMLResponse, include_in_schema=False)
def work_orders_page(
    request: Request,
    identity: Annotated[PageIdentity, Depends(get_page_identity)],
    service: Annotated[DashboardService, Depends(get_dashboard_service)],
) -> HTMLResponse:
    query = WorkOrderListQuery(
        keyword=request.query_params.get("keyword"),
        statuses=tuple(
            item for item in request.query_params.getlist("status") if item
        ),
        priorities=tuple(
            item for item in request.query_params.getlist("priority") if item
        ),
        sla_statuses=tuple(
            item for item in request.query_params.getlist("sla_status") if item
        ),
        organization_id=(
            int(request.query_params["organization_id"])
            if request.query_params.get("organization_id")
            else None
        ),
        sort_by=request.query_params.get("sort_by", "created_at"),
        sort_direction=request.query_params.get("sort_direction", "desc"),
        page=int(request.query_params.get("page", "1")),
        page_size=int(request.query_params.get("page_size", "20")),
    )
    try:
        data = service.work_orders(identity.profile, query)
        data["batch_message"] = request.query_params.get("batch")
    except (ValueError, WorkOrderError) as error:
        return _friendly_error(request, service, identity, error)
    return _page(
        request, service, identity, "workorders.html", "工单中心", "workorders", data
    )


@router.post(
    "/ui/workorders/saved-views",
    include_in_schema=False,
    response_model=None,
)
async def save_work_order_view_page(
    request: Request,
    identity: Annotated[PageIdentity, Depends(get_page_identity)],
    service: Annotated[DashboardService, Depends(get_dashboard_service)],
) -> HTMLResponse | RedirectResponse:
    values = await _form_lists(request)
    filters = {
        key: value if len(value) > 1 else value[0]
        for key, value in values.items()
        if key
        in {
            "keyword",
            "status",
            "priority",
            "sla_status",
            "organization_id",
            "sort_by",
            "sort_direction",
            "page_size",
        }
        and any(value)
    }
    try:
        service.saved_view_service.save(
            identity.profile.user_id,
            "WORKORDERS",
            values.get("view_name", [""])[-1],
            filters,
            values.get("is_default", ["false"])[-1] == "true",
        )
    except SavedViewError as error:
        return _friendly_error(request, service, identity, ValueError(str(error)))
    return RedirectResponse("/workorders", status_code=status.HTTP_303_SEE_OTHER)


@router.post(
    "/ui/workorders/batch",
    include_in_schema=False,
    response_model=None,
)
async def batch_work_orders_page(
    request: Request,
    identity: Annotated[PageIdentity, Depends(get_page_identity)],
    service: Annotated[DashboardService, Depends(get_dashboard_service)],
) -> HTMLResponse | RedirectResponse:
    values = await _form_lists(request)
    work_order_ids = [int(item) for item in values.get("work_order_ids", [])]
    action = values.get("batch_action", [""])[-1]
    actor = _actor(identity)
    try:
        if action == "dispatch":
            result = service.work_order_batch_service.dispatch(
                work_order_ids,
                int(values.get("target_org_id", [""])[-1]),
                actor,
                values.get("comment", [""])[-1] or None,
            )
        elif action == "urge":
            result = service.work_order_batch_service.urge(
                work_order_ids,
                actor,
                values.get("comment", [""])[-1],
            )
        else:
            raise ValueError("请选择批量操作")
    except (ValueError, WorkOrderError, WorkflowError) as error:
        return _friendly_error(request, service, identity, error)
    message = f"批量处理完成：成功 {result.succeeded}，失败 {result.failed}"
    return RedirectResponse(
        f"/workorders?batch={quote(message)}",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.get("/workorders/{work_order_id}", response_class=HTMLResponse, include_in_schema=False)
def work_order_detail_page(
    request: Request,
    work_order_id: int,
    identity: Annotated[PageIdentity, Depends(get_page_identity)],
    service: Annotated[DashboardService, Depends(get_dashboard_service)],
) -> HTMLResponse:
    try:
        data = service.work_order_detail(identity.profile, work_order_id)
    except (WorkOrderError, WorkflowError) as error:
        return _friendly_error(request, service, identity, error)
    return _page(
        request,
        service,
        identity,
        "workorder_detail.html",
        "工单详情",
        "workorders",
        data,
    )


@router.get("/tasks/mine", response_class=HTMLResponse, include_in_schema=False)
def my_tasks_page(
    request: Request,
    identity: Annotated[PageIdentity, Depends(get_page_identity)],
    service: Annotated[DashboardService, Depends(get_dashboard_service)],
) -> HTMLResponse:
    return _page(
        request,
        service,
        identity,
        "tasks.html",
        "我的任务",
        "tasks",
        service.my_tasks(identity.profile),
    )


@router.get("/notifications", response_class=HTMLResponse, include_in_schema=False)
def notifications_page(
    request: Request,
    identity: Annotated[PageIdentity, Depends(get_page_identity)],
    service: Annotated[DashboardService, Depends(get_dashboard_service)],
) -> HTMLResponse:
    return _page(
        request,
        service,
        identity,
        "notifications.html",
        "通知中心",
        "notifications",
        service.notifications(identity.profile),
    )


@router.post(
    "/ui/notifications/{notification_id}/read",
    include_in_schema=False,
    response_model=None,
)
def read_notification_page(
    request: Request,
    notification_id: int,
    identity: Annotated[PageIdentity, Depends(get_page_identity)],
    service: Annotated[DashboardService, Depends(get_dashboard_service)],
) -> HTMLResponse | RedirectResponse:
    try:
        service.notification_service.mark_read(
            notification_id,
            identity.profile.user_id,
        )
    except NotificationNotFound as error:
        return _friendly_error(request, service, identity, error)
    return RedirectResponse("/notifications", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/logout", include_in_schema=False)
def logout_page(
    request: Request,
    identity: Annotated[PageIdentity, Depends(get_page_identity)],
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
) -> RedirectResponse:
    settings = request.app.state.settings
    auth_service.logout(identity.context)
    response = RedirectResponse("/login", status_code=status.HTTP_303_SEE_OTHER)
    response.delete_cookie(settings.auth_cookie_name, path="/")
    return response


@router.post("/active-org", include_in_schema=False)
async def active_organization_page(
    request: Request,
    identity: Annotated[PageIdentity, Depends(get_page_identity)],
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
) -> RedirectResponse:
    values = await _form(request)
    try:
        auth_service.switch_active_organization(identity.context, int(values["org_id"]))
    except (ActiveOrganizationDenied, KeyError, ValueError) as error:
        raise PageAccessDenied("无法切换到该组织") from error
    return RedirectResponse(
        values.get("next", "/dashboard"), status_code=status.HTTP_303_SEE_OTHER
    )


@router.post("/active-application", include_in_schema=False)
async def active_application_page(
    request: Request,
    identity: Annotated[PageIdentity, Depends(get_page_identity)],
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
) -> RedirectResponse:
    values = await _form(request)
    try:
        auth_service.switch_active_application(
            identity.context, int(values["application_id"])
        )
    except (ActiveApplicationDenied, KeyError, ValueError) as error:
        raise PageAccessDenied("无法切换到该生命线系统") from error
    return RedirectResponse(
        values.get("next", "/dashboard"), status_code=status.HTTP_303_SEE_OTHER
    )


@router.post("/active-project", include_in_schema=False)
async def active_project_page(
    request: Request,
    identity: Annotated[PageIdentity, Depends(get_page_identity)],
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
) -> RedirectResponse:
    values = await _form(request)
    try:
        auth_service.switch_active_project(
            identity.context, int(values["project_id"])
        )
    except (ActiveProjectDenied, KeyError, ValueError) as error:
        raise PageAccessDenied("无法切换到该工程项目") from error
    return RedirectResponse(
        values.get("next", "/dashboard"), status_code=status.HTTP_303_SEE_OTHER
    )


def _iam_actor(identity: PageIdentity) -> IAMAdministrationActor:
    return IAMAdministrationActor(
        identity.context.current_user_id,
        identity.context.active_org_id,
    )


@router.post("/ui/organizations", include_in_schema=False, response_model=None)
async def create_organization_page(
    request: Request,
    identity: Annotated[PageIdentity, Depends(get_page_identity)],
    service: Annotated[DashboardService, Depends(get_dashboard_service)],
) -> HTMLResponse | RedirectResponse:
    values = await _form(request)
    try:
        service.organization_admin_service.create(
            CreateOrganizationCommand(
                org_code=values.get("org_code", ""),
                org_name=values.get("org_name", ""),
                org_type=values.get("org_type") or None,
                parent_code=values.get("parent_code") or None,
                sort_no=int(values.get("sort_no", "0")),
            ),
            _iam_actor(identity),
        )
    except (
        DuplicateIAMCode,
        IAMAdministrationPermissionDenied,
        IAMAdministrationValidationError,
        IAMEntityNotFound,
        ValueError,
    ) as error:
        return _friendly_error(request, service, identity, error)
    return RedirectResponse(
        "/iam/organizations", status_code=status.HTTP_303_SEE_OTHER
    )


@router.post(
    "/ui/organizations/{organization_id}/update",
    include_in_schema=False,
    response_model=None,
)
async def update_organization_page(
    request: Request,
    organization_id: int,
    identity: Annotated[PageIdentity, Depends(get_page_identity)],
    service: Annotated[DashboardService, Depends(get_dashboard_service)],
) -> HTMLResponse | RedirectResponse:
    values = await _form(request)
    try:
        service.organization_admin_service.update(
            organization_id,
            UpdateOrganizationCommand(
                org_name=values.get("org_name", ""),
                org_type=values.get("org_type") or None,
                parent_code=values.get("parent_code") or None,
                sort_no=int(values.get("sort_no", "0")),
            ),
            _iam_actor(identity),
        )
    except (
        IAMAdministrationPermissionDenied,
        IAMAdministrationValidationError,
        IAMEntityNotFound,
        ValueError,
    ) as error:
        return _friendly_error(request, service, identity, error)
    return RedirectResponse(
        "/iam/organizations", status_code=status.HTTP_303_SEE_OTHER
    )


@router.post(
    "/ui/organizations/{organization_id}/status",
    include_in_schema=False,
    response_model=None,
)
async def organization_status_page(
    request: Request,
    organization_id: int,
    identity: Annotated[PageIdentity, Depends(get_page_identity)],
    service: Annotated[DashboardService, Depends(get_dashboard_service)],
) -> HTMLResponse | RedirectResponse:
    values = await _form(request)
    try:
        service.organization_admin_service.set_active(
            organization_id,
            values.get("is_active", "").lower() == "true",
            _iam_actor(identity),
        )
    except (
        IAMAdministrationConflict,
        IAMAdministrationPermissionDenied,
        IAMEntityNotFound,
    ) as error:
        return _friendly_error(request, service, identity, error)
    return RedirectResponse(
        "/iam/organizations", status_code=status.HTTP_303_SEE_OTHER
    )


@router.post(
    "/ui/organizations/{organization_id}/delete",
    include_in_schema=False,
    response_model=None,
)
async def delete_organization_page(
    request: Request,
    organization_id: int,
    identity: Annotated[PageIdentity, Depends(get_page_identity)],
    service: Annotated[DashboardService, Depends(get_dashboard_service)],
) -> HTMLResponse | RedirectResponse:
    try:
        service.organization_admin_service.delete(
            organization_id,
            _iam_actor(identity),
        )
    except (
        IAMAdministrationConflict,
        IAMAdministrationPermissionDenied,
        IAMEntityNotFound,
    ) as error:
        return _friendly_error(request, service, identity, error)
    return RedirectResponse(
        "/iam/organizations", status_code=status.HTTP_303_SEE_OTHER
    )


@router.post("/ui/users", include_in_schema=False, response_model=None)
async def create_user_page(
    request: Request,
    identity: Annotated[PageIdentity, Depends(get_page_identity)],
    service: Annotated[DashboardService, Depends(get_dashboard_service)],
) -> HTMLResponse | RedirectResponse:
    values = await _form(request)
    try:
        service.user_admin_service.create(
            CreateUserCommand(
                username=values.get("username", ""),
                display_name=values.get("display_name", ""),
                password=values.get("password", ""),
                phone=values.get("phone") or None,
            ),
            _iam_actor(identity),
        )
    except (
        DuplicateIAMCode,
        IAMAdministrationPermissionDenied,
        IAMAdministrationValidationError,
    ) as error:
        return _friendly_error(request, service, identity, error)
    return RedirectResponse("/iam/users", status_code=status.HTTP_303_SEE_OTHER)


@router.post(
    "/ui/users/{user_id}/update",
    include_in_schema=False,
    response_model=None,
)
async def update_user_page(
    request: Request,
    user_id: int,
    identity: Annotated[PageIdentity, Depends(get_page_identity)],
    service: Annotated[DashboardService, Depends(get_dashboard_service)],
) -> HTMLResponse | RedirectResponse:
    values = await _form(request)
    try:
        service.user_admin_service.update(
            user_id,
            UpdateUserCommand(
                display_name=values.get("display_name", ""),
                phone=values.get("phone") or None,
            ),
            _iam_actor(identity),
        )
    except (
        IAMAdministrationPermissionDenied,
        IAMAdministrationValidationError,
        IAMEntityNotFound,
    ) as error:
        return _friendly_error(request, service, identity, error)
    return RedirectResponse("/iam/users", status_code=status.HTTP_303_SEE_OTHER)


@router.post(
    "/ui/users/{user_id}/status",
    include_in_schema=False,
    response_model=None,
)
async def user_status_page(
    request: Request,
    user_id: int,
    identity: Annotated[PageIdentity, Depends(get_page_identity)],
    service: Annotated[DashboardService, Depends(get_dashboard_service)],
) -> HTMLResponse | RedirectResponse:
    values = await _form(request)
    try:
        service.user_admin_service.set_active(
            user_id,
            values.get("is_active", "").lower() == "true",
            _iam_actor(identity),
        )
    except (
        IAMAdministrationConflict,
        IAMAdministrationPermissionDenied,
        IAMEntityNotFound,
    ) as error:
        return _friendly_error(request, service, identity, error)
    return RedirectResponse("/iam/users", status_code=status.HTTP_303_SEE_OTHER)


@router.post(
    "/ui/users/{user_id}/password",
    include_in_schema=False,
    response_model=None,
)
async def reset_user_password_page(
    request: Request,
    user_id: int,
    identity: Annotated[PageIdentity, Depends(get_page_identity)],
    service: Annotated[DashboardService, Depends(get_dashboard_service)],
) -> HTMLResponse | RedirectResponse:
    values = await _form(request)
    try:
        service.user_admin_service.reset_password(
            user_id,
            values.get("new_password", ""),
            _iam_actor(identity),
        )
    except (
        IAMAdministrationPermissionDenied,
        IAMAdministrationValidationError,
        IAMEntityNotFound,
    ) as error:
        return _friendly_error(request, service, identity, error)
    return RedirectResponse("/iam/users", status_code=status.HTTP_303_SEE_OTHER)


@router.post(
    "/ui/users/{user_id}/memberships",
    include_in_schema=False,
    response_model=None,
)
async def replace_user_memberships_page(
    request: Request,
    user_id: int,
    identity: Annotated[PageIdentity, Depends(get_page_identity)],
    service: Annotated[DashboardService, Depends(get_dashboard_service)],
) -> HTMLResponse | RedirectResponse:
    values = await _form_lists(request)
    organizations = {
        str(item.id): item
        for item in service.iam_service.list_organizations()
    }
    selected_ids = set(values.get("member_org_id", []))
    primary_id = (values.get("primary_org_id") or [""])[-1]
    configurations = tuple(
        MembershipConfiguration(
            org_code=organizations[org_id].org_code,
            is_primary=org_id == primary_id,
            is_active=f"active_org_{org_id}" in values,
            role_codes=tuple(values.get(f"role_{org_id}", [])),
            position_codes=tuple(values.get(f"position_{org_id}", [])),
        )
        for org_id in selected_ids
        if org_id in organizations
    )
    try:
        service.user_admin_service.replace_memberships(
            user_id,
            configurations,
            _iam_actor(identity),
        )
    except (
        IAMAdministrationPermissionDenied,
        IAMAdministrationValidationError,
        IAMEntityNotFound,
    ) as error:
        return _friendly_error(request, service, identity, error)
    return RedirectResponse("/iam/users", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/ui/roles", include_in_schema=False, response_model=None)
async def create_role_page(
    request: Request,
    identity: Annotated[PageIdentity, Depends(get_page_identity)],
    service: Annotated[DashboardService, Depends(get_dashboard_service)],
) -> HTMLResponse | RedirectResponse:
    values = await _form(request)
    try:
        service.role_admin_service.create(
            CreateRoleCommand(
                role_code=values.get("role_code", ""),
                role_name=values.get("role_name", ""),
                role_type=values.get("role_type") or None,
            ),
            _iam_actor(identity),
        )
    except (
        DuplicateIAMCode,
        IAMAdministrationPermissionDenied,
        IAMAdministrationValidationError,
    ) as error:
        return _friendly_error(request, service, identity, error)
    return RedirectResponse("/iam/roles", status_code=status.HTTP_303_SEE_OTHER)


@router.post(
    "/ui/roles/{role_id}/update",
    include_in_schema=False,
    response_model=None,
)
async def update_role_page(
    request: Request,
    role_id: int,
    identity: Annotated[PageIdentity, Depends(get_page_identity)],
    service: Annotated[DashboardService, Depends(get_dashboard_service)],
) -> HTMLResponse | RedirectResponse:
    values = await _form(request)
    try:
        service.role_admin_service.update(
            role_id,
            UpdateRoleCommand(
                role_name=values.get("role_name", ""),
                role_type=values.get("role_type") or None,
            ),
            _iam_actor(identity),
        )
    except (
        IAMAdministrationPermissionDenied,
        IAMAdministrationValidationError,
        IAMEntityNotFound,
    ) as error:
        return _friendly_error(request, service, identity, error)
    return RedirectResponse("/iam/roles", status_code=status.HTTP_303_SEE_OTHER)


@router.post(
    "/ui/roles/{role_id}/status",
    include_in_schema=False,
    response_model=None,
)
async def role_status_page(
    request: Request,
    role_id: int,
    identity: Annotated[PageIdentity, Depends(get_page_identity)],
    service: Annotated[DashboardService, Depends(get_dashboard_service)],
) -> HTMLResponse | RedirectResponse:
    values = await _form(request)
    try:
        service.role_admin_service.set_active(
            role_id,
            values.get("is_active", "").lower() == "true",
            _iam_actor(identity),
        )
    except (
        IAMAdministrationConflict,
        IAMAdministrationPermissionDenied,
        IAMEntityNotFound,
    ) as error:
        return _friendly_error(request, service, identity, error)
    return RedirectResponse("/iam/roles", status_code=status.HTTP_303_SEE_OTHER)


@router.post(
    "/ui/roles/{role_id}/authorization",
    include_in_schema=False,
    response_model=None,
)
async def replace_role_authorization_page(
    request: Request,
    role_id: int,
    identity: Annotated[PageIdentity, Depends(get_page_identity)],
    service: Annotated[DashboardService, Depends(get_dashboard_service)],
) -> HTMLResponse | RedirectResponse:
    values = await _form_lists(request)
    permissions = {
        item.permission_code: item
        for item in service.iam_service.list_permissions()
    }
    organizations = {
        str(item.id): item
        for item in service.iam_service.list_organizations()
    }
    configuration_items = []
    for permission_code in values.get("permission_code", []):
        permission = permissions.get(permission_code)
        if permission is None:
            continue
        scope_type = (values.get(f"scope_{permission.id}") or ["ORG"])[-1]
        custom_org_codes = (
            tuple(
                organizations[org_id].org_code
                for org_id in values.get(f"custom_org_{permission.id}", [])
                if org_id in organizations
            )
            if scope_type == "CUSTOM"
            else ()
        )
        configuration_items.append(
            PermissionScopeConfiguration(
                permission_code=permission_code,
                scope_type=scope_type,
                custom_org_codes=custom_org_codes,
            )
        )
    configurations = tuple(configuration_items)
    try:
        service.role_admin_service.replace_authorization(
            role_id,
            configurations,
            _iam_actor(identity),
        )
    except (
        IAMAdministrationConflict,
        IAMAdministrationPermissionDenied,
        IAMAdministrationValidationError,
        IAMEntityNotFound,
    ) as error:
        return _friendly_error(request, service, identity, error)
    return RedirectResponse("/iam/roles", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/ui/positions", include_in_schema=False, response_model=None)
async def create_position_page(
    request: Request,
    identity: Annotated[PageIdentity, Depends(get_page_identity)],
    service: Annotated[DashboardService, Depends(get_dashboard_service)],
) -> HTMLResponse | RedirectResponse:
    values = await _form(request)
    try:
        service.position_admin_service.create(
            CreatePositionCommand(
                position_code=values.get("position_code", ""),
                position_name=values.get("position_name", ""),
            ),
            _iam_actor(identity),
        )
    except (
        DuplicateIAMCode,
        IAMAdministrationPermissionDenied,
        IAMAdministrationValidationError,
    ) as error:
        return _friendly_error(request, service, identity, error)
    return RedirectResponse("/iam/positions", status_code=status.HTTP_303_SEE_OTHER)


@router.post(
    "/ui/positions/{position_id}/update",
    include_in_schema=False,
    response_model=None,
)
async def update_position_page(
    request: Request,
    position_id: int,
    identity: Annotated[PageIdentity, Depends(get_page_identity)],
    service: Annotated[DashboardService, Depends(get_dashboard_service)],
) -> HTMLResponse | RedirectResponse:
    values = await _form(request)
    try:
        service.position_admin_service.update(
            position_id,
            UpdatePositionCommand(
                position_name=values.get("position_name", ""),
            ),
            _iam_actor(identity),
        )
    except (
        IAMAdministrationPermissionDenied,
        IAMAdministrationValidationError,
        IAMEntityNotFound,
    ) as error:
        return _friendly_error(request, service, identity, error)
    return RedirectResponse("/iam/positions", status_code=status.HTTP_303_SEE_OTHER)


@router.post(
    "/ui/positions/{position_id}/status",
    include_in_schema=False,
    response_model=None,
)
async def position_status_page(
    request: Request,
    position_id: int,
    identity: Annotated[PageIdentity, Depends(get_page_identity)],
    service: Annotated[DashboardService, Depends(get_dashboard_service)],
) -> HTMLResponse | RedirectResponse:
    values = await _form(request)
    try:
        service.position_admin_service.set_active(
            position_id,
            values.get("is_active", "").lower() == "true",
            _iam_actor(identity),
        )
    except (
        IAMAdministrationPermissionDenied,
        IAMEntityNotFound,
    ) as error:
        return _friendly_error(request, service, identity, error)
    return RedirectResponse("/iam/positions", status_code=status.HTTP_303_SEE_OTHER)


@router.post(
    "/ui/positions/{position_id}/delete",
    include_in_schema=False,
    response_model=None,
)
def delete_position_page(
    request: Request,
    position_id: int,
    identity: Annotated[PageIdentity, Depends(get_page_identity)],
    service: Annotated[DashboardService, Depends(get_dashboard_service)],
) -> HTMLResponse | RedirectResponse:
    try:
        service.position_admin_service.delete(
            position_id,
            _iam_actor(identity),
        )
    except (
        IAMAdministrationConflict,
        IAMAdministrationPermissionDenied,
        IAMEntityNotFound,
    ) as error:
        return _friendly_error(request, service, identity, error)
    return RedirectResponse("/iam/positions", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/ui/permissions", include_in_schema=False, response_model=None)
async def create_permission_page(
    request: Request,
    identity: Annotated[PageIdentity, Depends(get_page_identity)],
    service: Annotated[DashboardService, Depends(get_dashboard_service)],
) -> HTMLResponse | RedirectResponse:
    values = await _form(request)
    try:
        service.permission_dictionary_service.create(
            CreatePermissionCommand(
                permission_code=values.get("permission_code", ""),
                permission_name=values.get("permission_name", ""),
                resource_type=values.get("resource_type") or None,
                description=values.get("description") or None,
            ),
            _iam_actor(identity),
        )
    except (
        DuplicateIAMCode,
        IAMAdministrationPermissionDenied,
        IAMAdministrationValidationError,
    ) as error:
        return _friendly_error(request, service, identity, error)
    return RedirectResponse("/iam/permissions", status_code=status.HTTP_303_SEE_OTHER)


@router.post(
    "/ui/permissions/{permission_id}/update",
    include_in_schema=False,
    response_model=None,
)
async def update_permission_page(
    request: Request,
    permission_id: int,
    identity: Annotated[PageIdentity, Depends(get_page_identity)],
    service: Annotated[DashboardService, Depends(get_dashboard_service)],
) -> HTMLResponse | RedirectResponse:
    values = await _form(request)
    try:
        service.permission_dictionary_service.update(
            permission_id,
            UpdatePermissionCommand(
                permission_name=values.get("permission_name", ""),
                resource_type=values.get("resource_type") or None,
                description=values.get("description") or None,
            ),
            _iam_actor(identity),
        )
    except (
        IAMAdministrationPermissionDenied,
        IAMAdministrationValidationError,
        IAMEntityNotFound,
    ) as error:
        return _friendly_error(request, service, identity, error)
    return RedirectResponse("/iam/permissions", status_code=status.HTTP_303_SEE_OTHER)


@router.post(
    "/ui/permissions/{permission_id}/delete",
    include_in_schema=False,
    response_model=None,
)
def delete_permission_page(
    request: Request,
    permission_id: int,
    identity: Annotated[PageIdentity, Depends(get_page_identity)],
    service: Annotated[DashboardService, Depends(get_dashboard_service)],
) -> HTMLResponse | RedirectResponse:
    try:
        service.permission_dictionary_service.delete(
            permission_id,
            _iam_actor(identity),
        )
    except (
        IAMAdministrationConflict,
        IAMAdministrationPermissionDenied,
        IAMEntityNotFound,
    ) as error:
        return _friendly_error(request, service, identity, error)
    return RedirectResponse("/iam/permissions", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/ui/workorders", include_in_schema=False, response_model=None)
async def create_work_order_page(
    request: Request,
    identity: Annotated[PageIdentity, Depends(get_page_identity)],
    service: Annotated[DashboardService, Depends(get_dashboard_service)],
) -> HTMLResponse | RedirectResponse:
    values = await _form(request)
    try:
        work_order = service.work_order_service.create(
            CreateWorkOrderCommand(
                title=values.get("title", ""),
                work_order_type=values.get("type", ""),
                priority=values.get("priority", "NORMAL"),
                location=values.get("location") or None,
                description=values.get("description") or None,
            ),
            _actor(identity),
        )
    except WorkOrderError as error:
        return _friendly_error(request, service, identity, error)
    return RedirectResponse(
        f"/workorders/{work_order.id}", status_code=status.HTTP_303_SEE_OTHER
    )


@router.post(
    "/ui/workorders/sla/evaluate",
    include_in_schema=False,
    response_model=None,
)
def evaluate_sla_page(
    request: Request,
    identity: Annotated[PageIdentity, Depends(get_page_identity)],
    service: Annotated[DashboardService, Depends(get_dashboard_service)],
) -> HTMLResponse | RedirectResponse:
    try:
        service.work_order_service.evaluate_sla(_actor(identity))
    except WorkOrderError as error:
        return _friendly_error(request, service, identity, error)
    return RedirectResponse("/workorders", status_code=status.HTTP_303_SEE_OTHER)


@router.post(
    "/ui/workorders/{work_order_id}/attachments",
    include_in_schema=False,
    response_model=None,
)
async def upload_attachment_page(
    request: Request,
    work_order_id: int,
    file: Annotated[UploadFile, File()],
    identity: Annotated[PageIdentity, Depends(get_page_identity)],
    service: Annotated[DashboardService, Depends(get_dashboard_service)],
) -> HTMLResponse | RedirectResponse:
    try:
        service.attachment_service.upload(
            work_order_id,
            _actor(identity),
            file.filename or "",
            file.content_type or "application/octet-stream",
            await file.read(WorkOrderAttachmentService.MAX_SIZE_BYTES + 1),
        )
    except WorkOrderError as error:
        return _friendly_error(request, service, identity, error)
    finally:
        await file.close()
    return RedirectResponse(
        f"/workorders/{work_order_id}",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.post(
    "/ui/workorders/{work_order_id}/{action}",
    include_in_schema=False,
    response_model=None,
)
async def work_order_action_page(
    request: Request,
    work_order_id: int,
    action: str,
    identity: Annotated[PageIdentity, Depends(get_page_identity)],
    service: Annotated[DashboardService, Depends(get_dashboard_service)],
) -> HTMLResponse | RedirectResponse:
    values = await _form(request)
    actor = _actor(identity)
    actions = {
        "submit": lambda: service.work_order_service.submit(
            work_order_id, actor, values.get("comment") or None
        ),
        "dispatch": lambda: service.work_order_service.dispatch(
            work_order_id,
            int(values.get("target_org_id", "")),
            actor,
            values.get("comment") or None,
        ),
        "claim": lambda: service.work_order_service.claim(
            work_order_id, actor, values.get("comment") or None
        ),
        "result": lambda: service.work_order_service.submit_result(
            work_order_id,
            actor,
            values.get("result", ""),
            values.get("comment") or None,
        ),
        "transfer": lambda: service.work_order_service.transfer(
            work_order_id,
            int(values.get("target_user_id", "")),
            actor,
            values.get("comment") or None,
        ),
        "comment": lambda: service.work_order_service.add_comment(
            work_order_id,
            actor,
            values.get("comment", ""),
        ),
        "urge": lambda: service.work_order_service.urge(
            work_order_id,
            actor,
            values.get("comment", ""),
        ),
        "review": lambda: service.work_order_service.review(
            work_order_id,
            actor,
            values.get("decision", ""),
            values.get("comment") or None,
        ),
        "close": lambda: service.work_order_service.close(
            work_order_id, actor, values.get("comment") or None
        ),
    }
    try:
        actions[action]()
    except KeyError:
        return _friendly_error(
            request, service, identity, ValueError(f"不支持的操作：{action}")
        )
    except (ValueError, WorkOrderError, WorkflowError) as error:
        return _friendly_error(request, service, identity, error)
    next_page = values.get("next") or f"/workorders/{work_order_id}"
    return RedirectResponse(next_page, status_code=status.HTTP_303_SEE_OTHER)


async def page_authentication_handler(
    request: Request, error: PageAuthenticationRequired
) -> RedirectResponse:
    next_page = request.url.path
    return RedirectResponse(
        f"/login?next={next_page}", status_code=status.HTTP_303_SEE_OTHER
    )


async def page_access_handler(request: Request, error: PageAccessDenied) -> HTMLResponse:
    return templates.TemplateResponse(
        request=request,
        name="error.html",
        context={
            "request": request,
            "page_title": "没有访问权限",
            "error_title": "没有访问权限",
            "error_message": str(error),
            "navigation": [],
            "profile": None,
            "active_page": "",
        },
        status_code=status.HTTP_403_FORBIDDEN,
    )
