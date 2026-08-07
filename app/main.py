"""FastAPI application factory."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.core.config import Settings, get_settings
from app.db.session import Database
from app.system.repository import HealthRepository
from app.system.router import router as system_router
from app.system.service import HealthService


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
    return application


app = create_app()
