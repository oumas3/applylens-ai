"""Request tracing and structured access logging."""

import json
import logging
import re
from time import perf_counter
from typing import Any
from uuid import uuid4

from starlette.responses import JSONResponse


REQUEST_ID_HEADER = b"x-request-id"
REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")
UNHANDLED_EXCEPTION_STATE_KEY = "applylens_unhandled_exception"


def normalize_request_id(value: str | None) -> str:
    if value and REQUEST_ID_PATTERN.fullmatch(value):
        return value
    return str(uuid4())


def configure_request_logger(log_level: str) -> logging.Logger:
    """Create a self-contained logger that works with Uvicorn's defaults."""
    logger = logging.getLogger("applylens.request")
    logger.setLevel(log_level)
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(message)s"))
        logger.addHandler(handler)
    logger.propagate = False
    return logger


class RequestObservabilityMiddleware:
    """Attach request IDs and emit one privacy-safe JSON access log per request."""

    def __init__(self, app: Any, logger: logging.Logger | None = None) -> None:
        self.app = app
        self.logger = logger or logging.getLogger("applylens.request")

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        incoming_headers = {
            key.lower(): value for key, value in scope.get("headers", [])
        }
        raw_request_id = incoming_headers.get(REQUEST_ID_HEADER)
        try:
            incoming_request_id = raw_request_id.decode("ascii") if raw_request_id else None
        except UnicodeDecodeError:
            incoming_request_id = None
        request_id = normalize_request_id(incoming_request_id)
        scope.setdefault("state", {})["request_id"] = request_id
        started_at = perf_counter()
        status_code = 500
        response_started = False

        async def send_with_request_id(message: dict[str, Any]) -> None:
            nonlocal response_started, status_code
            if message["type"] == "http.response.start":
                response_started = True
                status_code = int(message["status"])
                headers = [
                    (key, value)
                    for key, value in message.get("headers", [])
                    if key.lower() != REQUEST_ID_HEADER
                ]
                headers.append((REQUEST_ID_HEADER, request_id.encode("ascii")))
                message["headers"] = headers
            await send(message)

        try:
            await self.app(scope, receive, send_with_request_id)
        except Exception as exception:
            self._log(
                scope,
                request_id,
                status_code if response_started else 500,
                started_at,
                exception=exception,
            )
            if response_started:
                raise
            response = JSONResponse(
                status_code=500,
                content={"detail": "Internal server error."},
            )
            await response(scope, receive, send_with_request_id)
        else:
            exception = scope.get("state", {}).pop(
                UNHANDLED_EXCEPTION_STATE_KEY,
                None,
            )
            self._log(
                scope,
                request_id,
                status_code,
                started_at,
                exception=exception,
            )

    def _log(
        self,
        scope: dict[str, Any],
        request_id: str,
        status_code: int,
        started_at: float,
        *,
        exception: Exception | None = None,
    ) -> None:
        payload = json.dumps(
            {
                "event": "http_request",
                "request_id": request_id,
                "method": scope.get("method", ""),
                "path": scope.get("path", ""),
                "status_code": status_code,
                "duration_ms": round((perf_counter() - started_at) * 1000, 2),
            },
            separators=(",", ":"),
        )
        if exception is not None:
            self.logger.error(
                payload,
                exc_info=(type(exception), exception, exception.__traceback__),
            )
        else:
            self.logger.info(payload)


class UnhandledExceptionMiddleware:
    """Convert unexpected endpoint failures into safe responses inside CORS."""

    def __init__(self, app: Any) -> None:
        self.app = app

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        response_started = False

        async def track_response_start(message: dict[str, Any]) -> None:
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        try:
            await self.app(scope, receive, track_response_start)
        except Exception as exception:
            if response_started:
                raise
            scope.setdefault("state", {})[
                UNHANDLED_EXCEPTION_STATE_KEY
            ] = exception
            response = JSONResponse(
                status_code=500,
                content={"detail": "Internal server error."},
            )
            await response(scope, receive, track_response_start)
