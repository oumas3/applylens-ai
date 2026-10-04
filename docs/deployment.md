# Restricted demo deployment

Last updated: 2026-10-03

This runbook is provider-neutral. ApplyLens is ready to run as one Docker web
service backed by Neon PostgreSQL, but no public hosting provider is currently
selected or verified.

## Architecture

- `Dockerfile.demo` builds the React application and serves it from FastAPI at
  the same HTTPS origin.
- Neon Free supplies PostgreSQL and `pgvector` through a pooled TLS connection.
- The public demo uses deterministic lexical retrieval and makes no paid model
  API calls.
- Uploaded PDF/TXT bytes are discarded after bounded extraction. Extracted text
  and metadata are retained in PostgreSQL for the authenticated user.
- Password recovery remains disabled until a supported transactional email
  service is configured and tested.

## Hosting requirements

Choose a host only after verifying its current pricing and limits. It must:

- build and run `Dockerfile.demo`;
- provide public HTTPS and a configurable `PORT`;
- allow outbound TLS connections to Neon;
- inject secret environment variables without committing them;
- probe `GET /health/ready` for readiness;
- provide enough memory for FastAPI, PDF extraction, and the bundled React app;
- permit the application to run without persistent local filesystem storage.

Do not add a payment method or select a paid plan for the strict-zero-cost demo.

## Required environment variables

Configure these values in the selected host's secret manager:

- `DATABASE_URL`: Neon pooled connection string.
- `WEB_ORIGIN`: exact public HTTPS origin.
- `SUPPORT_EMAIL`: public support address shown to users.
- `INCIDENT_CONTACT_EMAIL`: private operator contact.

Use these non-secret values:

```text
APP_ENV=production
DOCUMENT_STORAGE=database
DOCUMENT_MAX_PAGES=100
DOCUMENT_MAX_EXTRACTED_CHARS=500000
REQUEST_MAX_BODY_BYTES=12582912
RETRIEVAL_PROVIDER=lexical
RETRIEVAL_STORAGE=memory
EMAIL_DELIVERY=disabled
PRODUCT_VERSION=0.1.0-beta.1
RELEASE_CHANNEL=free-public-beta
LOG_LEVEL=INFO
```

Do not configure `OPENAI_API_KEY` for the zero-cost demo.

## Database bootstrap

Every container start runs:

```powershell
python -m app.migrations
```

The migration runner takes a PostgreSQL advisory lock, verifies checksums in
`schema_migrations`, and applies pending migrations transactionally. A failure
stops the API before it can pass readiness.

Before a risky database change, create a Neon branch or export the database.
Test restoration into a separate branch before claiming recovery is verified.

## Release process

1. Require the backend, frontend, PostgreSQL/pgvector, and container CI jobs to
   pass for the exact revision.
2. Build and deploy `Dockerfile.demo` on the selected host.
3. Set the required environment variables through the host's secret manager.
4. Run `deploy/smoke_test.py` against the final public URL.
5. Complete the manual acceptance checklist below.
6. Record the deployed revision and rollback procedure.

## Verification checklist

- [ ] Container build and GitHub checks pass for the deployed commit.
- [ ] `/health` returns 200 over HTTPS with `X-Request-ID`.
- [ ] `/health/ready` reports the database as `ok`.
- [ ] The React application loads from the same origin.
- [ ] A fictional user can register, upload a synthetic TXT/PDF, analyze a
  synthetic opportunity, inspect evidence, and create tasks.
- [ ] A second user cannot access the first user's records.
- [ ] Extracted text survives a service restart.
- [ ] Password recovery displays the restricted-demo message.
- [ ] No server credential appears in the browser bundle.
- [ ] `deploy/smoke_test.py` passes against the final URL.

Until every item is checked against a real deployment, the correct project
status is **deployment-ready**, not deployed.
