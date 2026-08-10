import hmac
from typing import Annotated

from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.config import get_settings
from app.services.auth_service import AuthService, SESSION_MAX_AGE_SECONDS


SESSION_COOKIE = "applylens_session"
router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


class AuthRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    email: EmailStr
    password: str = Field(..., min_length=8, max_length=128)


class UserResponse(BaseModel):
    id: str
    email: EmailStr
    is_active: bool


class PasswordChangeRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    current_password: str = Field(..., min_length=1, max_length=128)
    new_password: str = Field(..., min_length=12, max_length=128)


def get_auth_service() -> AuthService:
    settings = get_settings()
    return AuthService(settings.auth_database_path, settings.database_url)


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
def register(request: AuthRequest) -> UserResponse:
    try:
        user = get_auth_service().create_user(request.email.lower(), request.password)
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error
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
