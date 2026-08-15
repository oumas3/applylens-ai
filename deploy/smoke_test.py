"""Non-destructive post-deployment checks for an ApplyLens environment."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit, urlunsplit
from urllib.request import Request, urlopen


MAX_RESPONSE_BYTES = 2 * 1024 * 1024
DEFAULT_TIMEOUT_SECONDS = 10.0


class Response(Protocol):
    status: int
    headers: Any

    def read(self, amount: int = -1) -> bytes: ...

    def __enter__(self) -> "Response": ...

    def __exit__(self, *args: object) -> None: ...


Opener = Callable[..., Response]


class SmokeCheckError(RuntimeError):
    """Raised when a public deployment contract is not satisfied."""


@dataclass(frozen=True)
class CheckResult:
    name: str
    detail: str


def normalize_base_url(value: str, *, allow_http: bool) -> str:
    """Validate and normalize a public deployment base URL."""
    parsed = urlsplit(value.strip())
    allowed_schemes = {"https", "http"} if allow_http else {"https"}
    if parsed.scheme not in allowed_schemes or not parsed.hostname:
        expected = "an absolute HTTP(S) URL" if allow_http else "an absolute HTTPS URL"
        raise SmokeCheckError(f"Expected {expected}: {value!r}")
    if parsed.username or parsed.password:
        raise SmokeCheckError("Deployment URLs must not contain credentials")
    if parsed.query or parsed.fragment:
        raise SmokeCheckError("Deployment URLs must not contain a query or fragment")
    if parsed.path not in {"", "/"}:
        raise SmokeCheckError("Deployment URLs must not contain a path")
    return urlunsplit((parsed.scheme, parsed.netloc, "", "", ""))


def fetch(
    url: str,
    *,
    timeout: float,
    opener: Opener,
) -> tuple[int, Any, bytes]:
    request = Request(
        url,
        headers={
            "Accept": "application/json, text/html;q=0.9",
            "User-Agent": "ApplyLens-Staging-Smoke-Test/1.0",
        },
    )
    try:
        with opener(request, timeout=timeout) as response:
            body = response.read(MAX_RESPONSE_BYTES + 1)
            if len(body) > MAX_RESPONSE_BYTES:
                raise SmokeCheckError(f"Response from {url} exceeded 2 MiB")
            return response.status, response.headers, body
    except SmokeCheckError:
        raise
    except HTTPError as error:
        raise SmokeCheckError(f"{url} returned HTTP {error.code}") from error
    except (URLError, OSError) as error:
        reason = getattr(error, "reason", str(error))
        raise SmokeCheckError(f"Could not reach {url}: {reason}") from error


def parse_json_object(body: bytes, *, url: str) -> dict[str, Any]:
    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise SmokeCheckError(f"{url} did not return valid UTF-8 JSON") from error
    if not isinstance(payload, dict):
        raise SmokeCheckError(f"{url} returned JSON that was not an object")
    return payload


def run_smoke_checks(
    *,
    web_url: str,
    api_url: str,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
    allow_http: bool = False,
    opener: Opener = urlopen,
) -> list[CheckResult]:
    """Verify the public frontend, API health, and launch metadata."""
    if timeout <= 0:
        raise SmokeCheckError("Timeout must be greater than zero")

    normalized_web_url = normalize_base_url(web_url, allow_http=allow_http)
    normalized_api_url = normalize_base_url(api_url, allow_http=allow_http)
    results: list[CheckResult] = []

    health_url = f"{normalized_api_url}/health"
    status, headers, body = fetch(health_url, timeout=timeout, opener=opener)
    health = parse_json_object(body, url=health_url)
    request_id = headers.get("X-Request-ID")
    if status != 200 or health.get("status") != "ok":
        raise SmokeCheckError("API liveness check did not report status=ok")
    if health.get("environment") != "production":
        raise SmokeCheckError("Staging API is not running with APP_ENV=production")
    if not request_id or not str(request_id).strip():
        raise SmokeCheckError("API liveness response did not include X-Request-ID")
    results.append(CheckResult("API liveness", f"ok; request_id={request_id}"))

    readiness_url = f"{normalized_api_url}/health/ready"
    status, _, body = fetch(readiness_url, timeout=timeout, opener=opener)
    readiness = parse_json_object(body, url=readiness_url)
    checks = readiness.get("checks")
    if status != 200 or readiness.get("status") != "ready":
        raise SmokeCheckError("API readiness check did not report status=ready")
    if not isinstance(checks, dict) or not checks:
        raise SmokeCheckError("API readiness response did not include dependency checks")
    unhealthy = {name: value for name, value in checks.items() if value != "ok"}
    if unhealthy:
        details = ", ".join(f"{name}={value}" for name, value in unhealthy.items())
        raise SmokeCheckError(f"API dependencies are not fully ready: {details}")
    results.append(
        CheckResult("API readiness", f"ok; dependencies={','.join(sorted(checks))}")
    )

    product_url = f"{normalized_api_url}/api/v1/product"
    status, _, body = fetch(product_url, timeout=timeout, opener=opener)
    product = parse_json_object(body, url=product_url)
    if status != 200 or product.get("name") != "ApplyLens AI":
        raise SmokeCheckError("Product endpoint did not identify ApplyLens AI")
    version = product.get("version")
    if not isinstance(version, str) or not version.strip():
        raise SmokeCheckError("Product endpoint did not include a release version")
    if product.get("release_channel") != "free-public-beta":
        raise SmokeCheckError("Product endpoint did not report the free-public-beta channel")
    support_email = product.get("support_email")
    if (
        not isinstance(support_email, str)
        or "@" not in support_email
        or support_email.startswith("@")
        or support_email.endswith("@")
    ):
        raise SmokeCheckError("Product endpoint did not include a public support email")
    results.append(
        CheckResult(
            "Product metadata",
            f"ok; version={version}; support={support_email}",
        )
    )

    status, _, body = fetch(normalized_web_url, timeout=timeout, opener=opener)
    try:
        html = body.decode("utf-8")
    except UnicodeDecodeError as error:
        raise SmokeCheckError("Frontend did not return UTF-8 HTML") from error
    if status != 200 or "ApplyLens AI" not in html or 'id="root"' not in html:
        raise SmokeCheckError("Frontend response was not the ApplyLens application shell")
    results.append(CheckResult("Frontend", "ok; application shell loaded"))

    return results


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--web-url", required=True, help="Public ApplyLens frontend URL")
    parser.add_argument("--api-url", required=True, help="Public ApplyLens API URL")
    parser.add_argument(
        "--timeout",
        type=float,
        default=DEFAULT_TIMEOUT_SECONDS,
        help=f"Per-request timeout in seconds (default: {DEFAULT_TIMEOUT_SECONDS:g})",
    )
    parser.add_argument(
        "--allow-http",
        action="store_true",
        help="Allow HTTP URLs for local-only verification",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        results = run_smoke_checks(
            web_url=args.web_url,
            api_url=args.api_url,
            timeout=args.timeout,
            allow_http=args.allow_http,
        )
    except SmokeCheckError as error:
        print(f"FAIL: {error}", file=sys.stderr)
        return 1

    for result in results:
        print(f"PASS: {result.name} - {result.detail}")
    print(f"PASS: {len(results)} staging smoke checks completed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
