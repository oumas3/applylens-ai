# ApplyLens AI

ApplyLens AI turns Master's and PhD calls into evidence-based eligibility decisions, comparisons, and application checklists.


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
- Frontend upload, document list, and text-preview interface
- 15 passing backend tests
- Successful production frontend build

### Sprint 2 — Opportunity analysis

- Parse academic opportunity requirements and deadlines
- Compare candidate evidence against each requirement
- Produce eligibility status with supporting evidence and gaps
- Surface application tasks, fees, and funding considerations
- Add structured opportunity review flows in the UI

### Sprint 4 â€” Evidence retrieval foundation

- Split opportunity source text into traceable chunks with stable IDs
- Support configurable chunk overlap while preserving source metadata
- Rank matching evidence through a provider-neutral retrieval interface
- Include a deterministic local hash embedding provider for development and tests
- Search ingested opportunity evidence from the API and web interface
- Send selected search results into the eligibility analysis evidence field

The current retrieval implementation is intentionally local and deterministic. A
production embedding provider and vector database are future extensions, not
required for the current MVP.

### Production vector storage preparation

The first pgvector migration is at `apps/api/migrations/001_pgvector.sql`.
It creates a persistent `opportunity_chunks` table for OpenAI
`text-embedding-3-small` vectors and a cosine-similarity HNSW index. Applying
it requires PostgreSQL with the `pgvector` extension installed; local retrieval
continues to work without that database.

To activate persistent retrieval in a deployment, set `RETRIEVAL_PROVIDER=openai`,
`RETRIEVAL_STORAGE=pgvector`, `OPENAI_API_KEY`, and `DATABASE_URL`, then apply
the migration before starting the API.
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

