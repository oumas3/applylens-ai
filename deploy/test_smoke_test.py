from __future__ import annotations

import unittest
from email.message import Message
from urllib.error import URLError

from deploy.smoke_test import SmokeCheckError, normalize_base_url, run_smoke_checks


class FakeResponse:
    def __init__(self, body: str, *, status: int = 200, request_id: str | None = None):
        self.status = status
        self.body = body.encode("utf-8")
        self.headers = Message()
        if request_id:
            self.headers["X-Request-ID"] = request_id

    def read(self, amount: int = -1) -> bytes:
        return self.body[:amount] if amount >= 0 else self.body

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *args: object) -> None:
        return None


def successful_opener(request: object, *, timeout: float) -> FakeResponse:
    del timeout
    url = request.full_url  # type: ignore[attr-defined]
    if url.endswith("/health/ready"):
        return FakeResponse(
            '{"status":"ready","checks":{"api":"ok","database":"ok","retrieval":"ok"}}'
        )
    if url.endswith("/health"):
        return FakeResponse(
            '{"status":"ok","environment":"production"}',
            request_id="staging-check-123",
        )
    if url.endswith("/api/v1/product"):
        return FakeResponse(
            '{"name":"ApplyLens AI","version":"0.1.0-beta.1",'
            '"release_channel":"free-public-beta",'
            '"support_email":"support@example.com"}'
        )
    return FakeResponse('<html><title>ApplyLens AI</title><div id="root"></div></html>')


class SmokeTestTests(unittest.TestCase):
    def test_success_requires_all_public_contracts(self) -> None:
        results = run_smoke_checks(
            web_url="https://staging.example.com/",
            api_url="https://api.staging.example.com",
            opener=successful_opener,
        )

        self.assertEqual(
            [result.name for result in results],
            ["API liveness", "API readiness", "Product metadata", "Frontend"],
        )

    def test_product_metadata_requires_a_public_support_route(self) -> None:
        def opener(request: object, *, timeout: float) -> FakeResponse:
            del timeout
            if request.full_url.endswith("/api/v1/product"):  # type: ignore[attr-defined]
                return FakeResponse(
                    '{"name":"ApplyLens AI","version":"0.1.0-beta.1",'
                    '"release_channel":"free-public-beta","support_email":null}'
                )
            return successful_opener(request, timeout=1)

        with self.assertRaisesRegex(SmokeCheckError, "public support email"):
            run_smoke_checks(
                web_url="https://staging.example.com",
                api_url="https://api.staging.example.com",
                opener=opener,
            )

    def test_https_is_required_unless_local_override_is_explicit(self) -> None:
        with self.assertRaisesRegex(SmokeCheckError, "HTTPS"):
            normalize_base_url("http://staging.example.com", allow_http=False)

        self.assertEqual(
            normalize_base_url("http://localhost:8080/", allow_http=True),
            "http://localhost:8080",
        )

    def test_liveness_requires_request_id(self) -> None:
        def opener(request: object, *, timeout: float) -> FakeResponse:
            del timeout
            if request.full_url.endswith("/health"):  # type: ignore[attr-defined]
                return FakeResponse('{"status":"ok","environment":"production"}')
            return successful_opener(request, timeout=1)

        with self.assertRaisesRegex(SmokeCheckError, "X-Request-ID"):
            run_smoke_checks(
                web_url="https://staging.example.com",
                api_url="https://api.staging.example.com",
                opener=opener,
            )

    def test_readiness_rejects_fallback_dependencies(self) -> None:
        def opener(request: object, *, timeout: float) -> FakeResponse:
            del timeout
            if request.full_url.endswith("/health/ready"):  # type: ignore[attr-defined]
                return FakeResponse(
                    '{"status":"ready","checks":{"api":"ok","database":"fallback"}}'
                )
            return successful_opener(request, timeout=1)

        with self.assertRaisesRegex(SmokeCheckError, "database=fallback"):
            run_smoke_checks(
                web_url="https://staging.example.com",
                api_url="https://api.staging.example.com",
                opener=opener,
            )

    def test_network_failures_are_reported_without_a_traceback(self) -> None:
        def opener(request: object, *, timeout: float) -> FakeResponse:
            del request, timeout
            raise URLError("DNS unavailable")

        with self.assertRaisesRegex(SmokeCheckError, "DNS unavailable"):
            run_smoke_checks(
                web_url="https://staging.example.com",
                api_url="https://api.staging.example.com",
                opener=opener,
            )

    def test_operating_system_network_errors_are_reported(self) -> None:
        def opener(request: object, *, timeout: float) -> FakeResponse:
            del request, timeout
            raise OSError("TLS handshake failed")

        with self.assertRaisesRegex(SmokeCheckError, "TLS handshake failed"):
            run_smoke_checks(
                web_url="https://staging.example.com",
                api_url="https://api.staging.example.com",
                opener=opener,
            )


if __name__ == "__main__":
    unittest.main()
