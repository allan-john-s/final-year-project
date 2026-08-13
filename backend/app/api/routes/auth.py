"""Auth API surface — routes only.

The endpoints are fully shaped (schemas, status codes, docs) and delegate to
the auth service via dependency injection. With no Supabase credentials the
service is the placeholder and operations answer 501; once configured, the
same routes talk to Supabase with zero routing changes. ``GET /me`` is always
protected by the bearer-token dependency (401 without a valid token).
"""

from typing import Annotated

from fastapi import APIRouter, Depends

from app.auth.interfaces import AuthService, AuthUser, ResetPasswordInput, SignInInput, SignUpInput
from app.dependencies.auth import get_auth_service, get_current_user
from app.schemas.auth import (
    AuthResultResponse,
    AuthUserResponse,
    PasswordResetRequest,
    ResetPasswordRequest,
    SignInRequest,
    SignUpRequest,
    VerifyEmailRequest,
)

router = APIRouter(prefix="/auth", tags=["auth"])

AuthServiceDep = Annotated[AuthService, Depends(get_auth_service)]
AuthUserDep = Annotated[AuthUser, Depends(get_current_user)]


@router.post(
    "/signup",
    response_model=AuthResultResponse,
    status_code=201,
    summary="Create an account",
)
async def sign_up(payload: SignUpRequest, service: AuthServiceDep) -> AuthResultResponse:
    result = await service.sign_up(SignUpInput(**payload.model_dump()))
    return AuthResultResponse(**result.model_dump())


@router.post("/login", response_model=AuthResultResponse, summary="Sign in")
async def sign_in(payload: SignInRequest, service: AuthServiceDep) -> AuthResultResponse:
    result = await service.sign_in(SignInInput(**payload.model_dump()))
    return AuthResultResponse(**result.model_dump())


@router.post("/logout", status_code=204, summary="Sign out")
async def sign_out(service: AuthServiceDep) -> None:
    await service.sign_out()


@router.get("/me", response_model=AuthUserResponse, summary="Current user")
async def current_user(user: AuthUserDep) -> AuthUserResponse:
    return AuthUserResponse(**user.model_dump())


@router.post(
    "/password/forgot",
    status_code=202,
    summary="Request a password reset link",
)
async def request_password_reset(
    payload: PasswordResetRequest,
    service: AuthServiceDep,
) -> None:
    await service.request_password_reset(payload.email)


@router.post(
    "/password/reset",
    status_code=204,
    summary="Reset the password with a token",
)
async def reset_password(payload: ResetPasswordRequest, service: AuthServiceDep) -> None:
    await service.reset_password(ResetPasswordInput(**payload.model_dump()))


@router.post(
    "/email/verify",
    status_code=204,
    summary="Verify an email address with a token",
)
async def verify_email(payload: VerifyEmailRequest, service: AuthServiceDep) -> None:
    await service.verify_email(payload.token)
