"""Server-rendered demonstration pages and form actions."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Annotated
from urllib.parse import parse_qs

from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.auth.repository import AuthRepository
from app.auth.router import get_auth_service
from app.auth.service import (
    ActiveOrganizationDenied,
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
from app.iam.repository import IAMRepository
from app.iam.service import DuplicateIAMCode, IAMEntityNotFound, IAMService
from app.iam.user_admin_service import (
    CreateUserCommand,
    MembershipConfiguration,
    UpdateUserCommand,
    UserAdministrationService,
)
from app.workflow.domain import TaskAccessDenied, WorkflowError
from app.workflow.factory import build_workflow_service
from app.workorder.domain import (
    WorkOrderError,
    WorkOrderNotFound,
    WorkOrderPermissionDenied,
    WorkOrderValidationError,
)
from app.workorder.repository import WorkOrderRepository
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
) -> DashboardService:
    iam_repository = IAMRepository(session)
    permission_service = PermissionService(iam_repository)
    workflow_service = build_workflow_service(session)
    work_order_service = WorkOrderService(
        WorkOrderRepository(session),
        permission_service,
        workflow_service,
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
    return WorkOrderActor(identity.context.current_user_id, identity.context.active_org_id)


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
        ),
    ):
        code = status.HTTP_403_FORBIDDEN
        title = "没有访问权限"
    elif isinstance(error, (IAMEntityNotFound, WorkOrderNotFound)):
        code = status.HTTP_404_NOT_FOUND
        title = "没有找到工单"
    elif isinstance(
        error,
        (IAMAdministrationValidationError, ValueError, WorkOrderValidationError),
    ):
        code = status.HTTP_422_UNPROCESSABLE_ENTITY
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


@router.get("/workorders", response_class=HTMLResponse, include_in_schema=False)
def work_orders_page(
    request: Request,
    identity: Annotated[PageIdentity, Depends(get_page_identity)],
    service: Annotated[DashboardService, Depends(get_dashboard_service)],
) -> HTMLResponse:
    try:
        data = service.work_orders(identity.profile)
    except WorkOrderError as error:
        return _friendly_error(request, service, identity, error)
    return _page(
        request, service, identity, "workorders.html", "工单中心", "workorders", data
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
