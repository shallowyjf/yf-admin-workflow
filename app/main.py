"""FastAPI application factory."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.auth.router import router as auth_router
from app.core.config import Settings, get_settings
from app.dashboard.domain import PageAccessDenied, PageAuthenticationRequired
from app.dashboard.router import (
    page_access_handler,
    page_authentication_handler,
)
from app.dashboard.router import (
    router as dashboard_router,
)
from app.data_permission.router import router as data_permission_router
from app.db.session import Database
from app.iam.bulk_router import router as iam_bulk_router
from app.iam.dictionary_router import router as iam_dictionary_router
from app.iam.role_router import router as iam_role_router
from app.iam.router import router as iam_router
from app.iam.user_router import router as iam_user_router
from app.notification.router import router as notification_router
from app.operation.router import router as operation_router
from app.project.router import router as project_router
from app.system.repository import HealthRepository
from app.system.router import router as system_router
from app.system.service import HealthService
from app.workflow.router import router as workflow_router
from app.workorder.router import router as work_order_router


def create_app(settings: Settings | None = None) -> FastAPI:
    application_settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        database = Database(application_settings.database_url)
        application.state.settings = application_settings
        application.state.database = database
        application.state.health_service = HealthService(
            HealthRepository(database.session_factory)
        )
        try:
            yield
        finally:
            database.dispose()

    application = FastAPI(
        title=application_settings.app_name,
        description="统一权限、流程任务与工单平台架构验证 Demo",
        version="0.1.0",
        debug=application_settings.debug,
        lifespan=lifespan,
    )
    application.include_router(system_router)
    application.include_router(auth_router)
    application.include_router(iam_router)
    application.include_router(iam_user_router)
    application.include_router(iam_role_router)
    application.include_router(iam_dictionary_router)
    application.include_router(iam_bulk_router)
    application.include_router(notification_router)
    application.include_router(operation_router)
    application.include_router(project_router)
    application.include_router(data_permission_router)
    application.include_router(work_order_router)
    application.include_router(workflow_router)
    application.include_router(dashboard_router)
    application.mount(
        "/static",
        StaticFiles(directory=str(Path(__file__).resolve().parent / "static")),
        name="static",
    )
    application.add_exception_handler(
        PageAuthenticationRequired, page_authentication_handler
    )
    application.add_exception_handler(PageAccessDenied, page_access_handler)
    return application


app = create_app()
