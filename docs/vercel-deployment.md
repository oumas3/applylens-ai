# Vercel Hobby deployment

ApplyLens can run on Vercel Hobby as one FastAPI application with its built
React frontend mounted at the same origin. The deployment uses Neon PostgreSQL
for every durable record and does not depend on Vercel's ephemeral filesystem.

## Repository configuration

- `vercel_app.py` exposes the existing FastAPI `app` and points it at the Vite
  production build.
- `pyproject.toml` identifies the FastAPI entrypoint and builds the frontend.
- `requirements.txt` exposes the backend dependencies to Vercel's Python
  framework detector.
- `.vercelignore` excludes local secrets, databases, tests, and generated files.
- `VERCEL_PROJECT_PRODUCTION_URL`, supplied by Vercel, becomes the trusted
  production origin. Preview deployments remain read-only for authenticated
  writes unless their origin is explicitly configured.

## Environment variables

Add these to the Vercel project for **Production**. Store `DATABASE_URL` as a
secret and use the Neon pooled hostname containing `-pooler`.

```text
APP_ENV=production
DATABASE_URL=<Neon pooled connection string>
DOCUMENT_STORAGE=database
DOCUMENT_MAX_PAGES=100
DOCUMENT_MAX_EXTRACTED_CHARS=100000
REQUEST_MAX_BODY_BYTES=4194304
FREE_BETA_DOCUMENT_LIMIT=20
FREE_BETA_OPPORTUNITY_LIMIT=50
FREE_BETA_REVIEW_LIMIT=100
FREE_BETA_TASK_LIMIT=200
RETRIEVAL_PROVIDER=lexical
RETRIEVAL_STORAGE=memory
EMAIL_DELIVERY=disabled
PRODUCT_VERSION=0.1.0-beta.1
RELEASE_CHANNEL=free-public-beta
LOG_LEVEL=INFO
SUPPORT_EMAIL=<public support address>
INCIDENT_CONTACT_EMAIL=<private operator address>
```

Do not add `OPENAI_API_KEY` to the free deterministic deployment. Password
recovery stays disabled until SMTP is configured and tested.

Vercel Functions limit request and response payloads to 4.5 MB. ApplyLens uses
a 4 MiB request limit on Vercel to leave room for multipart form overhead, and
the lower extraction/document limits keep account exports inside the platform
response limit.

## Database and release order

1. Confirm the exact commit is green in GitHub Actions.
2. Check the production schema using the direct Neon URL. Run versioned
   migrations separately with the direct URL if any are pending.
3. Import the GitHub repository into Vercel and select the free Hobby plan.
4. Add the production variables above. Do not select Pro or add a payment
   method.
5. Deploy, then run `deploy/smoke_test.py` against the generated HTTPS URL.
6. Complete restart persistence, two-user isolation, export, and recovery
   acceptance before calling the deployment a public beta.

The application runtime must receive the pooled Neon URL. Direct/unpooled URLs
are reserved for migrations, dumps, and restores and must not be added to the
Vercel environment.
