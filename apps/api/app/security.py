"""Browser request protections and defensive API response headers."""

from collections.abc import Iterable
from typing import Any
from urllib.parse import urlparse

from starlette.responses import JSONResponse


SESSION_COOKIE = "applylens_session"
UNSAFE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})
SECURITY_HEADERS = (
    (b"x-content-type-options", b"nosniff"),
    (b"x-frame-options", b"DENY"),
    (b"referrer-policy", b"strict-origin-when-cross-origin"),
    (
        b"permissions-policy",
        b"camera=(), geolocation=(), microphone=()",
    ),
)


def _header_map(scope: dict[str, Any]) -> dict[bytes, bytes]:
    return {key.lower(): value for key, value in scope.get("headers", [])}


def _referer_origin(value: str) -> str | None:
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None
    return f"{parsed.scheme}://{parsed.netloc}"


class TrustedOriginMiddleware:
    """Reject cross-site writes that rely on the session cookie."""

    def __init__(
        self,
        app: Any,
        *,
        allowed_origins: Iterable[str],
        require_origin: bool,
    ) -> None:
        self.app = app
        self.allowed_origins = frozenset(allowed_origins)
        self.require_origin = require_origin

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope["type"] != "http" or scope.get("method") not in UNSAFE_METHODS:
            await self.app(scope, receive, send)
            return

        headers = _header_map(scope)
        cookie = headers.get(b"cookie", b"").decode("latin-1")
        has_session_cookie = any(
            item.strip().partition("=")[0] == SESSION_COOKIE
            for item in cookie.split(";")
        )
        if not has_session_cookie:
            await self.app(scope, receive, send)
            return

        raw_origin = headers.get(b"origin")
        raw_referer = headers.get(b"referer")
        origin = raw_origin.decode("latin-1") if raw_origin else None
        if origin is None and raw_referer:
            origin = _referer_origin(raw_referer.decode("latin-1"))

        if origin not in self.allowed_origins and (origin is not None or self.require_origin):
            response = JSONResponse(
                status_code=403,
                content={"detail": "Request origin is not allowed."},
            )
            await response(scope, receive, send)
            return

        await self.app(scope, receive, send)


class SecurityHeadersMiddleware:
    """Attach browser hardening headers to every HTTP response."""

    def __init__(self, app: Any) -> None:
        self.app = app

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_with_security_headers(message: dict[str, Any]) -> None:
            if message["type"] == "http.response.start":
                protected_names = {name for name, _value in SECURITY_HEADERS}
                headers = [
                    (name, value)
                    for name, value in message.get("headers", [])
                    if name.lower() not in protected_names
                ]
                headers.extend(SECURITY_HEADERS)
                message["headers"] = headers
            await send(message)

        await self.app(scope, receive, send_with_security_headers)
