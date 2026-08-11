"""Authentication and active-organization HTTP endpoints."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.dependencies import get_db_session
from app.iam.authorization import PermissionService
from app.iam.repository import IAMRepository

from .repository import AuthRepository
from .schemas import ActiveOrganizationRequest, LoginRequest, MeResponse
from .service import (
    ActiveOrganizationDenied,
    AuthenticationError,
    AuthProfile,
    AuthService,
    RequestContext,
)

router = APIRouter(prefix="/auth", tags=["auth"])


def get_auth_service(
    request: Request,
    session: Annotated[Session, Depends(get_db_session)],
) -> AuthService:
    settings: Settings = request.app.state.settings
    iam_repository = IAMRepository(session)
    return AuthService(
        AuthRepository(session),
        PermissionService(iam_repository),
        session_hours=settings.auth_session_hours,
        default_tenant_code=settings.default_tenant_code,
    )


def get_request_context(
    request: Request,
    service: Annotated[AuthService, Depends(get_auth_service)],
) -> RequestContext:
    settings: Settings = request.app.state.settings
    try:
        return service.authenticate(request.cookies.get(settings.auth_cookie_name))
    except AuthenticationError as error:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(error),
        ) from error


def _profile_response(profile: AuthProfile) -> MeResponse:
    return MeResponse.model_validate(profile, from_attributes=True)


@router.post("/login", response_model=MeResponse)
def login(
    command: LoginRequest,
    response: Response,
    request: Request,
    service: Annotated[AuthService, Depends(get_auth_service)],
) -> MeResponse:
    settings: Settings = request.app.state.settings
    try:
        result = service.login(
            command.username,
            command.password,
            command.tenant_code,
        )
    except AuthenticationError as error:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(error),
        ) from error
    except ActiveOrganizationDenied as error:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(error),
        ) from error
    response.set_cookie(
        key=settings.auth_cookie_name,
        value=result.token,
        max_age=settings.auth_session_hours * 60 * 60,
        httponly=True,
        secure=settings.auth_cookie_secure,
        samesite="lax",
        path="/",
    )
    return _profile_response(result.profile)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    response: Response,
    request: Request,
    context: Annotated[RequestContext, Depends(get_request_context)],
    service: Annotated[AuthService, Depends(get_auth_service)],
) -> None:
    settings: Settings = request.app.state.settings
    service.logout(context)
    response.delete_cookie(settings.auth_cookie_name, path="/")


@router.get("/me", response_model=MeResponse)
def me(
    context: Annotated[RequestContext, Depends(get_request_context)],
    service: Annotated[AuthService, Depends(get_auth_service)],
) -> MeResponse:
    return _profile_response(service.profile(context))


@router.post("/active-org", response_model=MeResponse)
def switch_active_organization(
    command: ActiveOrganizationRequest,
    context: Annotated[RequestContext, Depends(get_request_context)],
    service: Annotated[AuthService, Depends(get_auth_service)],
) -> MeResponse:
    try:
        profile = service.switch_active_organization(context, command.org_id)
    except ActiveOrganizationDenied as error:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(error),
        ) from error
    return _profile_response(profile)
