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
        "REQUEST_MAX_BODY_BYTES",
    ):
        assert f"{variable}: ${{{variable}:-" in compose


def test_production_compose_requires_launch_identity_and_contacts() -> None:
    compose = (REPOSITORY_ROOT / "docker-compose.production.yml").read_text(
        encoding="utf-8"
    )

    assert "PRODUCT_VERSION: ${PRODUCT_VERSION:-0.1.0-beta.1}" in compose
    assert "RELEASE_CHANNEL: ${RELEASE_CHANNEL:-free-public-beta}" in compose
    assert "SUPPORT_EMAIL: ${SUPPORT_EMAIL:?Set the public support email}" in compose
    assert (
        "INCIDENT_CONTACT_EMAIL: "
        "${INCIDENT_CONTACT_EMAIL:?Set the incident response email}"
    ) in compose

    workflow = (REPOSITORY_ROOT / ".github" / "workflows" / "ci.yml").read_text(
        encoding="utf-8"
    )
    assert "SUPPORT_EMAIL: support@example.com" in workflow
    assert "INCIDENT_CONTACT_EMAIL: incident-response@example.com" in workflow


def test_restricted_demo_runbook_stays_provider_neutral_and_safe() -> None:
    runbook = (REPOSITORY_ROOT / "docs" / "deployment.md").read_text(
        encoding="utf-8"
    )

    for expected in (
        "`Dockerfile.demo`",
        "`GET /health/ready`",
        "DOCUMENT_STORAGE=database",
        "RETRIEVAL_PROVIDER=lexical",
        "EMAIL_DELIVERY=disabled",
        "Do not configure `OPENAI_API_KEY`",
    ):
        assert expected in runbook

    assert "Render" not in runbook
    assert not (REPOSITORY_ROOT / "render.yaml").exists()


def test_restricted_demo_image_builds_web_and_runs_migrations() -> None:
    dockerfile = (REPOSITORY_ROOT / "Dockerfile.demo").read_text(encoding="utf-8")

    assert "FROM node:24-alpine AS web-build" in dockerfile
    assert "ARG VITE_API_URL=" in dockerfile
    assert "COPY --from=web-build" in dockerfile
    assert "ENV WEB_STATIC_DIR=" in dockerfile
    assert "python -m app.migrations" in dockerfile
    assert "${PORT:-10000}" in dockerfile


def test_restricted_demo_build_context_excludes_local_secrets_and_artifacts() -> None:
    dockerignore = (REPOSITORY_ROOT / ".dockerignore").read_text(encoding="utf-8")

    for excluded in (
        ".git",
        ".env",
        ".neon",
        "**/node_modules",
        "**/.venv",
        "apps/api/storage",
    ):
        assert excluded in dockerignore.splitlines()


def test_vercel_entrypoint_builds_frontend_and_loads_fastapi() -> None:
    pyproject = (REPOSITORY_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    entrypoint = (REPOSITORY_ROOT / "vercel_app.py").read_text(encoding="utf-8")
    requirements = (REPOSITORY_ROOT / "requirements.txt").read_text(
        encoding="utf-8"
    )

    assert 'entrypoint = "vercel_app:app"' in pyproject
    assert "npm --prefix apps/web ci" in pyproject
    assert "npm --prefix apps/web run build" in pyproject
    assert 'os.environ.setdefault("WEB_STATIC_DIR", str(WEB_BUILD))' in entrypoint
    assert "from app.main import app" in entrypoint
    assert requirements.splitlines() == [
        "fastapi==0.116.1",
        "-r apps/api/requirements.txt",
    ]

    vercelignore = (REPOSITORY_ROOT / ".vercelignore").read_text(
        encoding="utf-8"
    )
    for excluded in (".env", ".env.*", ".neon", "**/node_modules", "apps/api/storage"):
        assert excluded in vercelignore.splitlines()
