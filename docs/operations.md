# ApplyLens production operations

For the first public staging environment, follow
[`staging-deployment.md`](staging-deployment.md). It adds automatic HTTPS,
provider-neutral DNS guidance, public smoke checks, and explicit go/no-go
criteria on top of the production procedures below.

## Deployment

1. Copy `deploy/production.env.example` to a secure file outside the repository.
2. Replace the database password, both public HTTPS URLs, and all SMTP placeholders. URL-encode special characters in `DATABASE_URL`.
3. Put an HTTPS reverse proxy or load balancer in front of the web and API ports. They bind to `127.0.0.1` by default; change `BIND_ADDRESS` only when the host network is protected appropriately.
4. Set `FORWARDED_ALLOW_IPS` to the proxy address or CIDR seen by the API container. Login throttling uses the trusted client address. Do not use `*` when untrusted clients can reach the API directly.
5. Validate the deployment configuration:

   ```powershell
   docker compose --env-file C:\secure\applylens-production.env -f docker-compose.production.yml config
   ```

6. Start or update the stack:

   ```powershell
   docker compose --env-file C:\secure\applylens-production.env -f docker-compose.production.yml up -d --build
   ```

7. Confirm `GET /health` returns `200` and `GET /health/ready` reports every configured dependency as `ok`.

The repository includes a non-destructive public check for these endpoints and
the frontend application shell:

```powershell
python deploy/smoke_test.py --web-url https://app.example.com --api-url https://api.example.com
```

PostgreSQL initialization scripts run only when the database volume is first created. For an existing database, apply new migration SQL explicitly before deploying the API that depends on it.

For Sprint 10, apply the idempotent login-throttling migration to an existing database before updating the API:

```powershell
docker compose --env-file C:\secure\applylens-production.env -f docker-compose.production.yml exec -T postgres psql -U applylens -d applylens -f /docker-entrypoint-initdb.d/003_login_attempts.sql
```

For Sprint 11, apply the account-recovery-token migration before updating the API:

```powershell
docker compose --env-file C:\secure\applylens-production.env -f docker-compose.production.yml exec -T postgres psql -U applylens -d applylens -f /docker-entrypoint-initdb.d/004_password_reset_tokens.sql
```

Adjust the database user and name if the production environment overrides their defaults.

## Account recovery email

Production startup requires `EMAIL_DELIVERY=smtp`, complete SMTP credentials, and STARTTLS. Use a transactional-email provider that supports STARTTLS, use a dedicated credential, and keep `SMTP_PASSWORD` only in the secure environment file.

Development defaults to `EMAIL_DELIVERY=console`. In that mode the reset link is written to the local API log so the flow can be tested without an email provider. Never use console delivery in a shared or production environment because the link is an account-recovery secret.

After deployment, request a reset for a controlled test account and confirm that the message arrives, the link works once, the link expires, and existing sessions are rejected after the password changes.

## Logs and request tracing

The API writes one JSON access-log event per request. Use the response `X-Request-ID` value to find the matching log event. Request bodies, cookies, authorization headers, and query strings are intentionally excluded.

The Compose services use bounded log rotation. Forward container logs to the chosen production log platform when operating more than one host.

## Backups

Back up both independent data stores:

- PostgreSQL contains users, sessions, document metadata, opportunities, reviews, tasks, and optional vectors.
- The `applylens-uploads` volume contains original PDF/TXT document bytes.

Example PostgreSQL backup:

```powershell
docker compose --env-file C:\secure\applylens-production.env -f docker-compose.production.yml exec -T postgres pg_dump -U applylens -d applylens -Fc -f /tmp/applylens.dump
docker compose --env-file C:\secure\applylens-production.env -f docker-compose.production.yml cp postgres:/tmp/applylens.dump C:\secure\backups\applylens.dump
```

Example upload-volume backup:

```powershell
docker run --rm -v applylens_applylens-uploads:/data:ro -v C:\secure\backups:/backup alpine tar -czf /backup/applylens-uploads.tar.gz -C /data .
```

## Restore rehearsal

Never make the first restore attempt against the live database or upload volume. Restore into isolated targets first:

```powershell
docker compose --env-file C:\secure\applylens-production.env -f docker-compose.production.yml cp C:\secure\backups\applylens.dump postgres:/tmp/applylens.dump
docker compose --env-file C:\secure\applylens-production.env -f docker-compose.production.yml exec -T postgres createdb -U applylens applylens_restore
docker compose --env-file C:\secure\applylens-production.env -f docker-compose.production.yml exec -T postgres pg_restore -U applylens -d applylens_restore --no-owner /tmp/applylens.dump
docker volume create applylens-uploads-restore
docker run --rm -v applylens-uploads-restore:/data -v C:\secure\backups:/backup alpine tar -xzf /backup/applylens-uploads.tar.gz -C /data
```

Point a staging API instance at the restored database and upload volume. Test `/health/ready`, authentication, document text retrieval, and user isolation before treating the backup as valid. Delete the isolated restore targets only after that validation is complete.

## Rollback

Keep the previous application image available. Roll back application containers without deleting either named volume. Database migrations must be backward-compatible with the previous application version or require a documented forward-only recovery plan.

Never use `docker compose down -v` in production: `-v` deletes the database and upload volumes.
