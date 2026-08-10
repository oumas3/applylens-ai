# ApplyLens AI

ApplyLens AI turns Master's and PhD calls into evidence-based eligibility decisions, comparisons, and application checklists.

## Current verification

- Backend test suite: 125 passing tests
- Frontend tests and production build: passing


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

The default retrieval implementation remains local and deterministic, so the MVP
works without external services. Production deployments can opt into OpenAI
embeddings and PostgreSQL/pgvector using the configuration below.

### Production vector storage preparation

The pgvector migration is at `apps/api/migrations/001_pgvector.sql`, and
application/authentication tables are defined in
`apps/api/migrations/002_application_data.sql`.
It creates a persistent `opportunity_chunks` table for OpenAI
`text-embedding-3-small` vectors and a cosine-similarity HNSW index. Applying
it requires PostgreSQL with the `pgvector` extension installed; local retrieval
continues to work without that database.

To activate persistent retrieval in a deployment, set `RETRIEVAL_PROVIDER=openai`,
`RETRIEVAL_STORAGE=pgvector`, `OPENAI_API_KEY`, and `DATABASE_URL`, then apply
the migration before starting the API.

### Local pgvector development

Docker is the quickest way to run the complete application locally:

```bash
docker compose up -d
```

This starts PostgreSQL 16 with pgvector, the FastAPI service, and an Nginx-served
production frontend. PostgreSQL automatically applies all migration files when
its data volume is initialized. Open
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

If the volume already exists, apply a changed migration manually or recreate
the development volume with `docker compose down -v`.
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

## MVP boundary

The MVP handles candidate documents and Master's/PhD calls. It extracts requirements, displays citations, supports `Eligible`, `Not eligible`, `Unclear`, and `Action required`, compares opportunities, and tracks application tasks. It does not submit applications automatically.

