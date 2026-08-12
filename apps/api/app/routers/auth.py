import hmac
import logging
from typing import Annotated
from urllib.parse import urlencode

from fastapi import APIRouter, BackgroundTasks, Cookie, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.config import get_settings
from app.services.auth_service import AuthService, SESSION_MAX_AGE_SECONDS
from app.services.email_service import PasswordResetEmailSender


SESSION_COOKIE = "applylens_session"
PASSWORD_RESET_REQUEST_MESSAGE = (
    "If an active account matches that email, a password reset link will be sent."
)
logger = logging.getLogger("applylens.auth")
router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


class AuthRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    email: EmailStr
    password: str = Field(..., min_length=8, max_length=128)


class UserResponse(BaseModel):
    id: str
    email: EmailStr
    is_active: bool
    external_ai_consent: bool = False


class PasswordChangeRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    current_password: str = Field(..., min_length=1, max_length=128)
    new_password: str = Field(..., min_length=12, max_length=128)


class PasswordResetRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    email: EmailStr


class PasswordResetConfirmRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    token: str = Field(..., min_length=32, max_length=512)
    new_password: str = Field(..., min_length=12, max_length=128)


class MessageResponse(BaseModel):
    message: str


def get_auth_service() -> AuthService:
    settings = get_settings()
    return AuthService(settings.auth_database_path, settings.database_url)


def get_password_reset_sender() -> PasswordResetEmailSender:
    return PasswordResetEmailSender(get_settings())


def deliver_password_reset_email(recipient: str, reset_url: str) -> None:
    try:
        get_password_reset_sender().send(recipient, reset_url)
    except Exception:
        logger.exception("Password reset email delivery failed.")


def set_session_cookie(response: Response, session_id: str) -> None:
    response.set_cookie(
        SESSION_COOKIE,
        session_id,
        max_age=SESSION_MAX_AGE_SECONDS,
        httponly=True,
        secure=get_settings().app_env == "production",
        samesite="lax",
    )


def get_current_user(
    session_id: Annotated[str | None, Cookie(alias=SESSION_COOKIE)] = None,
) -> dict[str, str | bool]:
    if not session_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required.")
    user = get_auth_service().get_user_by_session(session_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required.")
    return user


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def register(request: AuthRequest, response: Response) -> UserResponse:
    service = get_auth_service()
    try:
        user = service.create_user(request.email.lower(), request.password)
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error
    set_session_cookie(response, service.create_session(str(user["id"])))
    return UserResponse.model_validate(user)


@router.post("/login", response_model=UserResponse)
def login(
    credentials: AuthRequest,
    http_request: Request,
    response: Response,
) -> UserResponse:
    service = get_auth_service()
    email = credentials.email.lower()
    attempt_key = service.login_attempt_key(
        email,
        http_request.client.host if http_request.client else None,
    )
    retry_after = service.login_retry_after(attempt_key)
    if retry_after is not None:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many failed login attempts. Try again later.",
            headers={"Retry-After": str(retry_after)},
        )
    user = service.authenticate(email, credentials.password)
    if user is None:
        retry_after = service.record_failed_login(attempt_key)
        if retry_after is not None:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many failed login attempts. Try again later.",
                headers={"Retry-After": str(retry_after)},
            )
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password.")
    service.clear_login_failures(attempt_key)
    set_session_cookie(response, service.create_session(str(user["id"])))
    return UserResponse.model_validate(user)


@router.post("/password", status_code=status.HTTP_204_NO_CONTENT)
def change_password(
    request: PasswordChangeRequest,
    response: Response,
    user: dict[str, str | bool] = Depends(get_current_user),
) -> None:
    if hmac.compare_digest(request.current_password, request.new_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The new password must be different from the current password.",
        )
    service = get_auth_service()
    if not service.change_password(
        str(user["id"]),
        request.current_password,
        request.new_password,
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The current password is incorrect.",
        )
    set_session_cookie(response, service.create_session(str(user["id"])))


@router.post(
    "/password-reset/request",
    response_model=MessageResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def request_password_reset(
    request: PasswordResetRequest,
    background_tasks: BackgroundTasks,
) -> MessageResponse:
    settings = get_settings()
    token = get_auth_service().create_password_reset_token(request.email.lower())
    if token is not None:
        reset_url = f"{settings.web_origin}/#{urlencode({'reset_token': token})}"
        background_tasks.add_task(
            deliver_password_reset_email,
            request.email.lower(),
            reset_url,
        )
    return MessageResponse(message=PASSWORD_RESET_REQUEST_MESSAGE)


@router.post("/password-reset/confirm", status_code=status.HTTP_204_NO_CONTENT)
def confirm_password_reset(
    request: PasswordResetConfirmRequest,
    response: Response,
) -> None:
    if not get_auth_service().reset_password(request.token, request.new_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The password reset link is invalid or has expired.",
        )
    response.delete_cookie(SESSION_COOKIE)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    response: Response,
    session_id: Annotated[str | None, Cookie(alias=SESSION_COOKIE)] = None,
) -> None:
    if session_id:
        get_auth_service().delete_session(session_id)
    response.delete_cookie(SESSION_COOKIE)


@router.get("/me", response_model=UserResponse)
def current_user(user: dict[str, str | bool] = Depends(get_current_user)) -> UserResponse:
    return UserResponse.model_validate(user)
