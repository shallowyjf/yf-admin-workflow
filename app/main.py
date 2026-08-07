"""FastAPI entrypoint for the water operations demo."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

from .data import DemoRepository, build_overview


BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


class AcknowledgePayload(BaseModel):
    operator: str = Field(default="演示调度员", min_length=2, max_length=30)


def create_app(repository: DemoRepository | None = None) -> FastAPI:
    app = FastAPI(
        title="澄川智慧供水运营平台",
        description="第一轮：运营总览与 DMA 异常处置闭环",
        version="0.1.0",
    )
    app.state.repository = repository or DemoRepository()
    app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")

    @app.get("/", response_class=HTMLResponse, include_in_schema=False)
    async def index(request: Request) -> HTMLResponse:
        return templates.TemplateResponse(
            request=request,
            name="index.html",
            context={"iteration": "ITERATION 01", "version": app.version},
        )

    @app.get("/api/health", tags=["system"])
    async def health() -> dict[str, str]:
        return {"status": "ok", "version": app.version, "iteration": "01"}

    @app.get("/api/overview", tags=["operations"])
    async def overview(zone: str = "all") -> dict:
        payload = build_overview(app.state.repository, zone)
        if payload is None:
            raise HTTPException(status_code=404, detail="DMA 分区不存在")
        return payload

    @app.get("/api/events", tags=["events"])
    async def events(zone: str = "all") -> dict[str, list[dict]]:
        valid_ids = {item["id"] for item in app.state.repository.zones} | {"all"}
        if zone not in valid_ids:
            raise HTTPException(status_code=404, detail="DMA 分区不存在")
        return {"items": app.state.repository.list_events(zone)}

    @app.post("/api/events/{event_id}/acknowledge", tags=["events"])
    async def acknowledge(event_id: str, payload: AcknowledgePayload) -> dict:
        event = app.state.repository.acknowledge_event(event_id, payload.operator)
        if event is None:
            raise HTTPException(status_code=404, detail="事件不存在")
        return event

    return app


app = create_app()
