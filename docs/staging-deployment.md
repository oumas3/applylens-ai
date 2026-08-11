# ApplyLens staging deployment

This runbook creates the first internet-reachable ApplyLens environment. Staging
uses production security rules and PostgreSQL, but it must use separate DNS,
credentials, data, email identities, and backups from the eventual production
environment.

## Architecture

```text
Browser
  | HTTPS
  v
Caddy (automatic TLS)
  |--------------------|
  v                    v
React/Nginx         FastAPI
                         |
                         v
                 PostgreSQL + pgvector

Persistent volumes: PostgreSQL, uploaded files, and Caddy certificate state
```

The API and frontend debug ports bind to `127.0.0.1`. Only Caddy publishes ports
80 and 443. Caddy connects to the `web` and `api` services over the private
Compose network.

## 1. Provision prerequisites

- A staging Linux host or VM with Docker Engine and Docker Compose v2.
- Two DNS names under the same registrable parent domain, for example
  `staging.example.com` and `api.staging.example.com`, with A records pointing
  to the host. The shared parent is required because authenticated frontend
  requests use the API's `SameSite=Lax` session cookie. Add AAAA records only
  when IPv6 reaches the same host.
- Inbound TCP 80 and TCP/UDP 443 allowed. Restrict SSH to trusted source
  addresses. Do not expose ports 5432, 8000, or 8080 publicly.
- A STARTTLS-capable transactional SMTP account and a verified sender address.
- A backup destination outside the staging host.

Caddy needs ports 80 and 443 plus working public DNS to obtain certificates.
Wait for DNS to resolve to the new host before starting the full stack.

## 2. Create the secret environment file

Copy `deploy/staging.env.example` to a location outside the repository, such as
`/etc/applylens/staging.env`. Replace every placeholder and restrict the file to
the deployment account.

Generate a unique database password. If it contains URL-sensitive characters,
URL-encode the password only in `DATABASE_URL`; keep the original value in
`POSTGRES_PASSWORD`. Ensure these pairs match exactly:

- `STAGING_WEB_HOST=staging.example.com`
- `WEB_ORIGIN=https://staging.example.com`
- `STAGING_API_HOST=api.staging.example.com`
- `PUBLIC_API_URL=https://api.staging.example.com`

Never copy the populated file into `deploy/` or commit it. The repository ignores
`deploy/*.env` as a second line of defense, but the secure external location is
the primary protection.

## 3. Validate before changing runtime state

Run these commands from the repository root:

```powershell
docker compose --env-file /etc/applylens/staging.env -f docker-compose.production.yml -f docker-compose.staging.yml config --quiet
docker compose --env-file /etc/applylens/staging.env -f docker-compose.production.yml -f docker-compose.staging.yml build api web
```

The first command resolves every required variable and validates the combined
Compose model. The second proves both application images build before any
running container is replaced.

## 4. Start PostgreSQL and apply migrations

```powershell
docker compose --env-file /etc/applylens/staging.env -f docker-compose.production.yml -f docker-compose.staging.yml up -d --wait postgres
docker compose --env-file /etc/applylens/staging.env -f docker-compose.production.yml -f docker-compose.staging.yml exec -T postgres psql -v ON_ERROR_STOP=1 -U applylens -d applylens -f /docker-entrypoint-initdb.d/001_pgvector.sql
docker compose --env-file /etc/applylens/staging.env -f docker-compose.production.yml -f docker-compose.staging.yml exec -T postgres psql -v ON_ERROR_STOP=1 -U applylens -d applylens -f /docker-entrypoint-initdb.d/002_application_data.sql
docker compose --env-file /etc/applylens/staging.env -f docker-compose.production.yml -f docker-compose.staging.yml exec -T postgres psql -v ON_ERROR_STOP=1 -U applylens -d applylens -f /docker-entrypoint-initdb.d/003_login_attempts.sql
docker compose --env-file /etc/applylens/staging.env -f docker-compose.production.yml -f docker-compose.staging.yml exec -T postgres psql -v ON_ERROR_STOP=1 -U applylens -d applylens -f /docker-entrypoint-initdb.d/004_password_reset_tokens.sql
```

Replace `applylens` in the `-U` and `-d` arguments when `POSTGRES_USER` or
`POSTGRES_DB` is customized. `ON_ERROR_STOP=1` prevents a partial migration
sequence from being mistaken for success. The current migrations are designed
to be safely re-applied.

## 5. Start the application and HTTPS proxy

```powershell
docker compose --env-file /etc/applylens/staging.env -f docker-compose.production.yml -f docker-compose.staging.yml up -d
docker compose --env-file /etc/applylens/staging.env -f docker-compose.production.yml -f docker-compose.staging.yml ps
```

The API waits for PostgreSQL, the frontend waits for the API health check, and
Caddy waits for the application services. Inspect logs if any service does not
become healthy:

```powershell
docker compose --env-file /etc/applylens/staging.env -f docker-compose.production.yml -f docker-compose.staging.yml logs --tail 100 api web caddy postgres
```

Do not paste logs containing password-reset links or other secrets into public
issues.

## 6. Run automated and manual acceptance checks

From a trusted machine with Python 3.12 or newer:

```powershell
python deploy/smoke_test.py --web-url https://staging.example.com --api-url https://api.staging.example.com
```

The command fails unless all of these contracts hold:

- API liveness returns `status=ok` in production mode.
- Responses contain an `X-Request-ID` for log correlation.
- PostgreSQL and every configured readiness dependency report `ok`.
- The public frontend returns the ApplyLens application shell.

Then use a controlled staging account to verify the state-changing flows:

1. Register, sign out, sign in, and change the password.
2. Upload one TXT and one multi-page PDF; verify extracted text and delete one.
3. Ingest an opportunity, search its evidence, run eligibility analysis, save the
   review, compare it, and update a generated task.
4. Request password recovery, receive the SMTP email, use the link once, and
   confirm the old password and old sessions no longer work.
5. Create a second account and confirm it cannot see the first account's data.

Do not promote the release when an automated check fails, a browser reports a
TLS warning, SMTP delivery fails, or tenant isolation is uncertain.

## 7. Prove recovery and rollback

Create `/srv/applylens-staging/backups` on the host with access restricted to the
deployment account. The staging override changes the Compose project name to
`applylens-staging`, so production-only commands from `operations.md` must not be
used unchanged.

Back up the staging PostgreSQL database through the combined Compose project:

```powershell
docker compose --env-file /etc/applylens/staging.env -f docker-compose.production.yml -f docker-compose.staging.yml exec -T postgres pg_dump -U applylens -d applylens -Fc -f /tmp/applylens-staging.dump
docker compose --env-file /etc/applylens/staging.env -f docker-compose.production.yml -f docker-compose.staging.yml cp postgres:/tmp/applylens-staging.dump /srv/applylens-staging/backups/applylens-staging.dump
```

Verify that the expected staging upload volume exists before mounting it. This
prevents Docker from silently creating and backing up a new empty volume after a
name typo:

```powershell
docker volume inspect applylens-staging_applylens-uploads
docker run --rm -v applylens-staging_applylens-uploads:/data:ro -v /srv/applylens-staging/backups:/backup alpine tar -czf /backup/applylens-staging-uploads.tar.gz -C /data .
```

Restore both backups into isolated targets, never over the active staging data:

```powershell
docker compose --env-file /etc/applylens/staging.env -f docker-compose.production.yml -f docker-compose.staging.yml cp /srv/applylens-staging/backups/applylens-staging.dump postgres:/tmp/applylens-staging.dump
docker compose --env-file /etc/applylens/staging.env -f docker-compose.production.yml -f docker-compose.staging.yml exec -T postgres createdb -U applylens applylens_staging_restore
docker compose --env-file /etc/applylens/staging.env -f docker-compose.production.yml -f docker-compose.staging.yml exec -T postgres pg_restore -U applylens -d applylens_staging_restore --no-owner /tmp/applylens-staging.dump
docker volume create applylens-staging-uploads-restore
docker run --rm -v applylens-staging-uploads-restore:/data -v /srv/applylens-staging/backups:/backup alpine tar -xzf /backup/applylens-staging-uploads.tar.gz -C /data
```

Adjust `-U` and `-d` for customized database settings. Point an isolated API
instance at the restored database and upload volume, then repeat the smoke check
and retrieve an uploaded document's extracted text before calling the backup
usable.

For application rollback, keep the last known-good Git revision or tagged images.
Rebuild that revision and run `up -d` without removing named volumes. Never use
`docker compose down -v`: it deletes the database and uploaded files.

## Exit criteria

Sprint 12 deployment is operationally complete only when:

- both public hostnames have trusted HTTPS;
- CI passes for the exact revision deployed;
- automated and manual acceptance checks pass;
- SMTP recovery works end to end;
- an off-host backup and isolated restore have been demonstrated;
- request logs can be found by `X-Request-ID`; and
- the rollback revision and operator are documented.
