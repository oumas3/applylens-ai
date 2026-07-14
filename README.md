# ApplyLens AI

ApplyLens AI turns Master's and PhD calls into evidence-based eligibility decisions, comparisons, and application checklists.

## Sprint 0 status

- React + TypeScript web skeleton
- FastAPI service with health and product endpoints
- Shared environment configuration
- Architecture decision record
- API unit test

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

