# ApplyLens AI

ApplyLens AI turns Master's and PhD calls into evidence-based eligibility decisions, comparisons, and application checklists.

## Current verification

- Backend test suite: 81 passing tests
- Frontend production build: passing


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

- Parse academic opportunity requirements and deadlines
- Compare candidate evidence against each requirement
- Produce eligibility status with supporting evidence and gaps
- Surface application tasks, fees, and funding considerations
- Add structured opportunity review flows in the UI

### Sprint 3 — Review and task tracking

- Save opportunity reviews for later comparison
- Compare saved opportunities and recommend the strongest match
- Generate application tasks from missing requirements, deadlines, and funding
- Track task progress through pending, in-progress, and completed states

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

The default retrieval implementation remains local and deterministic, so the MVP
works without external services. Production deployments can opt into OpenAI
embeddings and PostgreSQL/pgvector using the configuration below.

### Production vector storage preparation

The first pgvector migration is at `apps/api/migrations/001_pgvector.sql`.
It creates a persistent `opportunity_chunks` table for OpenAI
`text-embedding-3-small` vectors and a cosine-similarity HNSW index. Applying
it requires PostgreSQL with the `pgvector` extension installed; local retrieval
continues to work without that database.

To activate persistent retrieval in a deployment, set `RETRIEVAL_PROVIDER=openai`,
`RETRIEVAL_STORAGE=pgvector`, `OPENAI_API_KEY`, and `DATABASE_URL`, then apply
the migration before starting the API.

### Local pgvector development

Docker is the quickest way to run the same vector database locally:

```bash
docker compose up -d postgres
```

The compose service runs PostgreSQL 16 with pgvector and automatically applies
`apps/api/migrations/001_pgvector.sql` when its data volume is initialized. Add
the following to the repository `.env` (never commit that file):

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

## MVP boundary

The MVP handles candidate documents and Master's/PhD calls. It extracts requirements, displays citations, supports `Eligible`, `Not eligible`, `Unclear`, and `Action required`, compares opportunities, and tracks application tasks. It does not submit applications automatically.

