# ApplyLens free public beta launch checklist

This document is the release contract for launching ApplyLens AI as a free
public beta. Payment, subscriptions, automatic application submission, and
admission guarantees are explicitly outside the release scope.

## Product boundary

ApplyLens helps Master's and PhD candidates organize evidence, understand an
academic call, review eligibility, and track application work. Every important
decision must remain traceable to candidate or opportunity evidence. Missing
evidence is reported as unclear or actionable; it is never invented.

The candidate remains responsible for checking the original call and submitting
the application. ApplyLens is not a university, admissions service, lawyer, or
guarantor of admission or funding.

## Launch gates

| Gate | Required evidence | Status |
| --- | --- | --- |
| Private accounts and recovery | Authentication, session, throttling, password-change, and one-time reset tests pass | Implemented |
| Tenant isolation | Cross-user document, opportunity, profile, review, task, export, and deletion tests pass | Opportunities, profiles, export, and deletion are proven; final CRUD matrix required |
| Evidence workflow | Upload, extraction, citations, retrieval, eligibility, profile evidence, reviews, and task tests pass | Implemented |
| Durable production data | PostgreSQL schema readiness, file storage, migration, backup, and restore procedures are verified | Implemented; final restore drill required |
| Privacy lifecycle | Explicit external-AI consent, data export, account deletion, and user-facing limitations are verified | Implemented |
| First-use experience | Real onboarding progress, accessible navigation, responsive UI, empty states, and account-switch isolation pass | Sprint 15 ready for commit |
| Public-beta abuse safety | Same-origin write protection, bounded free-use limits, sensitive-route throttling, and consistent password policy pass | Sprint 16 required |
| Launch information | Privacy notice, terms, acceptable-use rules, support route, release metadata, and operator contacts are present | Sprint 17 required |
| Release verification | Backend, frontend, build, Compose, smoke, migration, backup/restore, and manual acceptance checks all pass | Final release gate |

## Sprint 16 — security and reliability

Sprint 16 is complete only when all of the following are true:

- Cookie-authenticated state-changing requests reject an untrusted `Origin` or
  `Referer` while allowing the configured frontend origin.
- Registration uses the same minimum password strength as password changes and
  resets.
- Registration, password-reset requests, uploads, opportunity ingestion, and
  analysis have bounded abuse controls with safe `429` responses.
- Configurable per-account free-beta limits prevent unbounded document,
  opportunity, review, and task growth.
- Reviews and tasks support tenant-scoped individual deletion, and explicit
  two-user tests prove every supported list, create, update, compare, and delete
  boundary across documents, opportunities, profiles, reviews, and tasks.
- Security headers are present when the API is accessed directly as well as
  through the HTTPS proxy.
- Expired sessions and security records have bounded cleanup behavior.
- All controls work with both local development storage and PostgreSQL where
  persistence is involved.
- Focused security tests and the complete backend/frontend suites pass.

## Sprint 17 — launch packaging

Sprint 17 is complete only when all of the following are true:

- Privacy, terms of use, acceptable-use, AI-limitations, and support information
  are reachable before registration and from the authenticated workspace.
- Legal copy accurately describes stored data, external-AI opt-in, retention,
  export, deletion, candidate responsibility, and the no-submission boundary.
- The application exposes consistent beta version and release information.
- Production and staging environment examples contain every required setting
  without containing real secrets.
- The deployment runbook covers initial migration, HTTPS, SMTP, health probes,
  backups, restoration, rollback, and incident contacts.
- A controlled staging account completes registration, upload, profile save,
  opportunity extraction, analysis, review, task update, export, logout/login,
  password recovery, and account deletion.
- The final release diff contains no secret, generated build output, or unrelated
  file.

## Final verification commands

Run these checks from a clean release commit:

```powershell
.\.venv\Scripts\python.exe -m pytest apps/api/tests -q
npm --prefix apps/web test -- --run
npm --prefix apps/web run build
.\.venv\Scripts\python.exe -m pytest deploy/test_smoke_test.py -q
git diff --check HEAD^ HEAD
docker compose config
docker compose -f docker-compose.production.yml config
docker compose -f docker-compose.production.yml -f docker-compose.staging.yml config
```

After deployment, run:

```powershell
.\.venv\Scripts\python.exe deploy/smoke_test.py `
  --web-url https://app.example.com `
  --api-url https://api.example.com
```

Docker and public smoke checks require the target machine or CI environment.
Their absence on a developer machine is an environment limitation, not a pass.

## Operator inputs required before public launch

The repository cannot invent or safely commit these values:

- Public frontend and API hostnames.
- A PostgreSQL password and `DATABASE_URL`.
- A support/contact email address.
- SMTP host, username, password, and sender address for account recovery.
- The trusted reverse-proxy address or CIDR.
- A backup location outside the application server.
- The person responsible for privacy, support, and incident response.

These inputs do not require payment code. Hosting, domains, and email delivery
may depend on the chosen provider, while the product remains fully runnable
locally and deployable to any compatible container host.
