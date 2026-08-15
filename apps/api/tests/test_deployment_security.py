from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]


def test_caddy_applies_security_headers_to_web_and_api_hosts() -> None:
    caddyfile = (REPOSITORY_ROOT / "deploy" / "Caddyfile").read_text(
        encoding="utf-8"
    )

    for directive in (
        'Strict-Transport-Security "max-age=31536000; includeSubDomains"',
        'X-Content-Type-Options "nosniff"',
        'X-Frame-Options "DENY"',
        'Referrer-Policy "strict-origin-when-cross-origin"',
        'Permissions-Policy "camera=(), geolocation=(), microphone=()"',
    ):
        assert caddyfile.count(directive) == 2


def test_production_compose_passes_every_abuse_control_setting() -> None:
    compose = (REPOSITORY_ROOT / "docker-compose.production.yml").read_text(
        encoding="utf-8"
    )

    for variable in (
        "RATE_LIMIT_WINDOW_SECONDS",
        "REGISTRATION_RATE_LIMIT",
        "PASSWORD_RESET_RATE_LIMIT",
        "DOCUMENT_UPLOAD_RATE_LIMIT",
        "OPPORTUNITY_INGEST_RATE_LIMIT",
        "OPPORTUNITY_ANALYSIS_RATE_LIMIT",
        "FREE_BETA_DOCUMENT_LIMIT",
        "FREE_BETA_OPPORTUNITY_LIMIT",
        "FREE_BETA_REVIEW_LIMIT",
        "FREE_BETA_TASK_LIMIT",
    ):
        assert f"{variable}: ${{{variable}:-" in compose
