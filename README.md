# ApplyLens AI

ApplyLens AI turns Master's and PhD calls into evidence-based eligibility decisions, comparisons, and application checklists.

## Current verification

- Backend test suite: 224 passing, 2 PostgreSQL integration tests skipped locally
- Deployment smoke-check suite: 7 passing tests
- Frontend test suite: 18 passing tests
- Frontend production build: passing
- Deterministic evaluation: 30 synthetic cases, including 10 held out

The repository is deployment-ready, but it does not yet claim a verified public
URL. Provider deployment and restart/persistence acceptance remain explicit
release gates in [`docs/deployment.md`](docs/deployment.md).

## Restricted demo architecture

```mermaid
flowchart LR
    Browser[React browser client] -->|same-origin HTTPS| API[FastAPI Docker service]
    API -->|pooled TLS connection| DB[(Neon Free PostgreSQL)]
    API --> Rules[Local lexical retrieval and deterministic eligibility rules]
```

The free demo deliberately has no paid model dependency. It stores bounded
extracted text in PostgreSQL and discards uploaded source bytes, which avoids
depending on persistent application-host storage. `Dockerfile.demo` serves the
built React app and API from one provider-neutral container. A hosting provider
will be selected separately after its current free-tier terms are verified.

### Reviewer walkthrough

1. Register a fictional account and select **Load fictional sample** in the
   opportunity analysis form.
2. Run the analysis and inspect matched evidence, missing information, funding,
   deadline, and generated application tasks.
3. Save or compare reviews, update task progress, and try account export.

The sample uses a fictional institution and no private applicant data.

For an evidence-backed project summary, interview talking points, and CV-ready
bullets, see [`docs/portfolio-handoff.md`](docs/portfolio-handoff.md).

## Project status

### Sprint 0 — Foundation

- React, TypeScript, and Vite frontend
- FastAPI backend with validated configuration
- Frontend-to-API connection
- Health and product endpoints
- Automated API tests

### Sprint 1 — Document ingestion

- Secure PDF and TXT uploads
- Document categories for CVs, transcripts, and application letters
- File-type, empty-file, filename, and corrupted-PDF validation
- Real multi-page PDF extraction with pypdf
- Document metadata and extracted-text endpoints
- Document listing and deletion
- Document metadata persists across API restarts
- Frontend upload, document list, and text-preview interface
- Successful production frontend build

### Sprint 2 — Opportunity analysis

- Parse academic opportunity requirements, deadlines, and funding evidence
- Compare candidate evidence against each requirement
- Produce eligibility status with supporting evidence and gaps
- Surface application tasks, fees, and funding considerations
- Add structured opportunity review flows in the UI

### Sprint 3 — Review and task tracking

- Save opportunity reviews for later comparison
- Compare saved opportunities and recommend the strongest match
- Generate application tasks from missing requirements, deadlines, and funding
- Track task progress through pending, in-progress, and completed states
- Keep generated tasks scoped to their opportunity

### Sprint 4 — Evidence retrieval foundation

- Split opportunity source text into traceable chunks with stable IDs
- Support configurable chunk overlap while preserving source metadata
- Rank matching evidence through a provider-neutral retrieval interface
- Include a deterministic local hash embedding provider for development and tests
- Search ingested opportunity evidence from the API and web interface
- Send selected search results into the eligibility analysis evidence field

### Sprint 5 — Production hardening

- Persist document metadata across API restarts
- Enforce bounded upload sizes for documents and opportunity files
- Provide dependency readiness checks for deployment health probes
- Support optional OpenAI embeddings and PostgreSQL/pgvector storage
- Provide a Docker Compose pgvector development environment

### Sprint 8 — Production persistence

- Persist authentication and application records in PostgreSQL when `DATABASE_URL` is configured.
- Keep deterministic JSON/SQLite fallbacks for local development and tests.
- Use atomic, path-safe file storage for uploaded document bytes.
- Report database schema readiness through `/health/ready`.
- Verify migration structure, storage integrity, and ownership boundaries with automated tests.

### Sprint 9 — Deployment and observability

- Reject incomplete or insecure production configuration at startup.
- Add privacy-safe JSON request logs and traceable `X-Request-ID` responses.
- Run CI checks for Sprint branches, backend compilation, dependency consistency, tests, builds, and Compose files.
- Provide a production Compose stack with persistent database/upload volumes and bounded container logs.
- Document deployment, readiness checks, backups, restores, request tracing, and rollback safety.

### Sprint 10 — Account security

- Bound authentication database connections and reduce credential timing signals.
- Persist source-aware login throttling with `429` and `Retry-After` responses.
- Allow authenticated password changes with stronger new-password requirements.
- Revoke other active sessions and rotate the current session after a password change.
- Add a compact account-security panel and automated backend/frontend coverage.

### Sprint 11 — Account recovery

- Request password recovery without revealing whether an account exists.
- Store only hashed, one-time reset tokens with one-hour expiry and request cooldowns.
- Deliver reset links through SMTP in production and console output in local development.
- Revoke every active session after a successful reset.
- Provide compact forgot-password and reset-password screens with automated coverage.

### Sprint 12 — Staging deployment preparation

- Reuse the production stack behind a Caddy HTTPS reverse proxy.
- Keep database, uploads, and TLS state in separate persistent volumes.
- Validate public API liveness, dependency readiness, request tracing, and the
  frontend shell with a non-destructive smoke-test command.
- Validate production/staging Compose and proxy configuration in CI.
- Document DNS, secrets, migrations, SMTP, acceptance testing, backups,
  restoration, and rollback as a repeatable staging runbook.

### Sprint 13 — Privacy and account lifecycle

- Export every account-owned record and exact uploaded file content as private JSON.
- Permanently delete accounts, sessions, reset tokens, files, vectors, reviews, and tasks.
- Require explicit per-account consent before external AI evidence processing.
- Explain privacy boundaries, AI limitations, and candidate responsibility in the UI.

### Sprint 14 — Evidence-linked candidate profiles

- Store one structured candidate profile per account in JSON or PostgreSQL.
- Model education, work, research, languages, skills, and publications.
- Link individual profile claims to uploaded documents owned by the same account.
- Automatically include only live, document-supported profile claims in eligibility analysis.
- Edit and validate the profile through a compact, responsive React interface.

### Sprint 15 — Launch onboarding and accessible workspace

- Guide new users through evidence upload, profile setup, opportunity extraction,
  eligibility review, and application tasks using real saved-workspace progress.
- Add keyboard-visible focus, skip navigation, reduced-motion support, and
  responsive onboarding layouts.
- Clear private in-memory workspace data on logout and permanent account deletion
  before another account can sign in.
- Explain empty task and review states with direct next actions.
- Verify onboarding progress, navigation, account switching, and the production build.

### Sprint 16 — Security and reliability

- Reject untrusted cookie-authenticated browser writes and attach defensive API
  and HTTPS-proxy response headers.
- Apply consistent password strength, persistent sensitive-action throttling,
  and configurable per-account free-beta quotas.
- Support tenant-scoped task and review deletion with a complete two-user CRUD
  isolation matrix.
- Opportunistically remove expired sessions, reset tokens, login attempts, and
  request-limit records using indexed SQLite/PostgreSQL storage.

### Sprint 17 — Free public beta launch packaging

- Publish privacy, terms, acceptable-use, external-AI limitations, release
  version, and operator support information before registration and inside the
  authenticated workspace.
- Require public support and private incident contacts in production while
  keeping real addresses and credentials out of source control.
- Verify release identity and support metadata through the non-destructive
  deployment smoke test.
- Provide an exact-release staging acceptance record covering the full product
  workflow, SMTP recovery, tenant isolation, export, deletion, backup/restore,
  rollback, and incident response.

The default retrieval implementation remains local and deterministic, so the MVP
works without external services. Production deployments can opt into OpenAI
embeddings and PostgreSQL/pgvector using the configuration below.

### Measured deterministic evaluation

The repository includes 30 fully synthetic, human-annotated cases split into
20 development and 10 held-out examples. Under the recorded local lexical
conditions, making missing evidence explicitly `Insufficient information`
improved overall eligibility outcome accuracy from 0.6000 to 0.8333 and
held-out accuracy from 0.6000 to 0.8000. Insufficient-information accuracy
improved from 0.0000 to 1.0000; retrieval was unchanged at Recall@1 0.8824 and
Recall@3 0.9412.

These are small synthetic-set measurements, not admissions-accuracy or hosted
performance claims. See `evaluation/REPORT.md` for methodology, remaining
failures, proxy-metric caveats, and the saved per-case results.

### Production vector storage preparation

The pgvector migration is at `apps/api/migrations/001_pgvector.sql`, and
application/authentication tables start in
`apps/api/migrations/002_application_data.sql`. Account privacy and candidate
profiles are added by migrations `005_account_privacy.sql` and
`006_candidate_profiles.sql`. Persistent abuse controls use
`007_request_limits.sql`, with security cleanup indexes in
`008_security_cleanup_indexes.sql`. Migration
`009_document_extracted_text.sql` adds database-backed extracted document text
for ephemeral-filesystem demo hosting.
It creates a persistent `opportunity_chunks` table for OpenAI
`text-embedding-3-small` vectors and a cosine-similarity HNSW index. Applying
it requires PostgreSQL with the `pgvector` extension installed; local retrieval
continues to work without that database.

To activate persistent retrieval in a deployment, set `RETRIEVAL_PROVIDER=openai`,
`RETRIEVAL_STORAGE=pgvector`, `OPENAI_API_KEY`, and `DATABASE_URL`. Run
`python -m app.migrations` from `apps/api` before starting a non-containerized
API. The API container runs the same migration command before Uvicorn starts.
Applied filenames and checksums are recorded in `schema_migrations`; never edit
an applied migration—add the next numbered file instead.

### Local pgvector development

Docker is the quickest way to run the complete application locally:

```bash
docker compose up -d
```

This starts PostgreSQL 16 with pgvector, the FastAPI service, and an Nginx-served
production frontend. PostgreSQL initializes a new volume, then the API's
versioned runner records or applies every migration before serving requests.
The same runner applies pending migrations to an existing volume. Open
the web app at `http://localhost:8080` and the API at `http://localhost:8000`.

The compose defaults use local lexical retrieval so no external API key is
needed. To enable persistent OpenAI retrieval, override the API environment with
the following values (never commit API keys):

```dotenv
RETRIEVAL_PROVIDER=openai
RETRIEVAL_STORAGE=pgvector
DATABASE_URL=postgresql://applylens:applylens@localhost:5432/applylens
OPENAI_API_KEY=your_key_here
```

Do not recreate a volume merely to apply a migration. Add a new ordered SQL file
and restart the API; checksum validation rejects edits to migration history.
## Local setup

### Web

```bash
cd apps/web
npm install
npm run dev
```

### API

```bash
cd apps/api
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Open the web app at `http://localhost:5173` and API documentation at `http://localhost:8000/docs`.
For deployment probes, `/health` checks process liveness and `/health/ready`
checks configured runtime dependencies.

For production deployment and recovery procedures, see
[`docs/operations.md`](docs/operations.md). Start from
`deploy/production.env.example`; never commit the populated production environment file.
For the strict-zero-cost restricted demo, use the dated provider analysis and
checklist in [`docs/deployment.md`](docs/deployment.md).
For the first HTTPS staging environment, follow
[`docs/staging-deployment.md`](docs/staging-deployment.md) and start from
`deploy/staging.env.example`.
The remaining free-beta release gates and their required evidence are tracked in
[`docs/free-beta-launch-checklist.md`](docs/free-beta-launch-checklist.md).
Public product terms are in
[`docs/public-beta-terms.md`](docs/public-beta-terms.md), and deployment approval
is recorded with
[`docs/staging-acceptance.md`](docs/staging-acceptance.md).

## MVP boundary

The MVP handles candidate documents and Master's/PhD calls. It extracts
requirements, displays citations, distinguishes `Eligible`, `Not eligible`,
and `Insufficient information`, compares opportunities, and tracks application
tasks. Legacy saved reviews using `Unclear` or `Action required` remain readable.
It does not submit applications automatically.

