# Free restricted-demo deployment

Provider facts were checked on 2026-09-28 against the official pages linked
below. Recheck them before provisioning because free-plan terms can change.

## Selected architecture

- One Render Free web service builds the React application and serves it from
  FastAPI at the same HTTPS origin.
- Neon Free provides PostgreSQL and the `pgvector` extension.
- The public demo uses deterministic lexical retrieval. It makes no OpenAI or
  other paid inference calls and does not describe lexical results as embedding
  retrieval.
- Uploaded source PDF/TXT bytes are discarded after bounded extraction. Only
  extracted text and metadata are retained in PostgreSQL for the authenticated
  user. The demo does not offer source-file downloads or OCR.
- Password recovery is explicitly disabled. Registration, login, password
  change while authenticated, account export, and account deletion remain
  available. Render Free blocks outbound SMTP ports 25, 465, and 587.

This is a restricted personal-project demo, not a production service.

## Why these providers

### Render Free web service

Official documentation:

- https://render.com/docs/free
- https://render.com/docs/compute-plans
- https://render.com/docs/deploys
- https://render.com/docs/health-checks

Verified constraints:

- Free web services receive 750 instance-hours per workspace each month.
- A service spins down after 15 minutes without inbound traffic and can take
  about one minute to wake.
- The free instance is 0.1 CPU and 512 MB RAM and cannot scale beyond one
  instance.
- The filesystem is ephemeral and free services cannot attach persistent disks.
- HTTPS, custom domains, log streams, and two recent rollback artifacts are
  available.
- Bandwidth/build overages can incur charges only if a payment method is added;
  without one, Render suspends/limits the service instead. Do not add a payment
  method for this strict-zero-cost demo.
- `autoDeployTrigger: checksPass` prevents deploys when GitHub checks fail.
- Render Free PostgreSQL expires after 30 days and is therefore not used.

No artificial keep-alive traffic is permitted. The UI and walkthrough must set
the expectation that the first request can take roughly one minute.

### Neon Free PostgreSQL

Official documentation and current announcements:

- https://neon.com/blog/neon-backend-is-ga
- https://neon.com/blog/major-compute-price-reduction-on-neon
- https://neon.com/docs/manage/endpoints
- https://neon.com/blog/building-a-rag-application-with-llama-3-1-and-pgvector

Verified constraints:

- The current Free Plan announcement states 100 projects, 100 CU-hours per
  project per month, 0.5 GB database storage per project, and 10 branches.
- Compute scales to zero after inactivity by default; resumption adds database
  cold-start latency.
- Neon supplies `pgvector`; `CREATE EXTENSION vector` is supported.
- Pooled connection strings are available and should be used by the demo.
- The same announcement includes 5 GB object storage per project, but ApplyLens
  does not need it because source uploads are intentionally not retained.
- Neon's official material describes the free tier as no-card-required. Do not
  upgrade to a usage-billed plan for this demo.

Choose Neon's Frankfurt region to keep it near the Render Frankfurt service.

## Deployment configuration

`render.yaml` defines the free service, readiness health check, Frankfurt
region, and CI-gated deployment. `Dockerfile.demo` builds the React bundle with
a relative API URL, installs the FastAPI service, runs versioned migrations,
and then starts Uvicorn on Render's `PORT`.

Create a Neon Free project first and copy its pooled PostgreSQL connection
string. When creating the Render Blueprint, supply these secret values:

- `DATABASE_URL`: Neon pooled connection string; never commit it.
- `WEB_ORIGIN`: final Render URL, for example
  `https://applylens-ai-demo.onrender.com`.
- `SUPPORT_EMAIL`: public address shown to users.
- `INCIDENT_CONTACT_EMAIL`: private operator contact used by configuration and
  runbooks; it is not returned by the API.

The committed non-secret values select `DOCUMENT_STORAGE=database`, lexical
retrieval, memory retrieval indexes, and disabled password-recovery email.
Do not set `OPENAI_API_KEY` for the zero-cost demo.

## Database bootstrap and recovery

Every container start runs:

```powershell
python -m app.migrations
```

The runner takes a PostgreSQL advisory lock, verifies checksums in
`schema_migrations`, and applies pending files transactionally. A failure stops
the API before it can pass readiness.

Neon Free is not an audited backup system. Before a risky change, create a Neon
branch or export the small demo database with `pg_dump`. Test restoration into a
separate branch before claiming recovery is verified. Never put private user
documents into a public sample or repository backup.

## CI, redeploy, and rollback

The Render service watches `main` and uses `checksPass`. Protect `main` in
GitHub so pull requests require the backend, frontend, PostgreSQL/pgvector, and
container jobs. A failing commit must not deploy.

To redeploy, merge a reviewed pull request after all required checks pass.
Render builds the exact merged revision. For rollback, select one of the two
retained prior deploys in Render. Migrations are forward-only; roll back code
only when the previous version remains compatible with the applied schema.

## Verification checklist

- [ ] Render build and GitHub checks passed for the deployed commit.
- [ ] `/health` returns 200 over HTTPS with `X-Request-ID`.
- [ ] `/health/ready` reports database `ok`.
- [ ] The React shell loads from the same origin.
- [ ] A fictional user can register, upload a synthetic TXT/PDF, ingest a
  synthetic opportunity, review evidence/uncertainty, and create tasks.
- [ ] Another user cannot access the first user's document/result IDs.
- [ ] Extracted text survives a service restart; source bytes are not present
  on the service filesystem after restart.
- [ ] Password recovery shows the restricted-demo unavailability message.
- [ ] A cold start resolves without leaving the UI indefinitely stuck.
- [ ] No server credential appears in the browser bundle.
- [ ] `deploy/smoke_test.py` passes against the final URL.

Until every item is checked against an authenticated provider deployment, the
correct status is **deployment-ready**, not deployed.
