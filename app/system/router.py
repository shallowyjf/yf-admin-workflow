"""HTTP endpoints for system diagnostics."""

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

from .service import HealthService

router = APIRouter(tags=["system"])


class HealthResponse(BaseModel):
    status: str
    database: str
    iteration: str
    version: str


def get_health_service(request: Request) -> HealthService:
    return request.app.state.health_service


@router.get("/health", response_model=HealthResponse)
def health(service: Annotated[HealthService, Depends(get_health_service)]) -> HealthResponse:
    return HealthResponse.model_validate(service.check(), from_attributes=True)
