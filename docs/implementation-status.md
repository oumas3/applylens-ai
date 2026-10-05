# ApplyLens AI implementation status

Last updated: 2026-10-05

This is the resumable engineering checklist for the ApplyLens AI personal
project. A checked item means the behavior was verified in the current
repository or by a command recorded below; it does not imply a public
deployment or production-scale validation.

## Current baseline

- Branch: `main`.
- Working tree was clean before this effort began.
- Main journey: authenticate, upload applicant evidence, ingest an academic
  opportunity, inspect evidence-linked eligibility assistance, create tasks,
  and save or compare reviews.
- Default AI mode is deterministic lexical retrieval. OpenAI embeddings are
  optional and require a separately funded API key. There is no generative LLM
  call in the verified eligibility path.

### Verification run on 2026-09-28

- [x] Backend suite: 192 tests passed before changes.
- [x] Frontend suite: 17 tests passed across 2 test files.
- [x] Frontend TypeScript and production build passed.
- [x] Deployment smoke-test suite: 7 tests passed.
- [x] `pip check` reported no broken requirements.
- [x] `git diff --check` passed before changes.
- [ ] Docker/Compose runtime validation: Docker is not installed in the local
  environment.
- [ ] Real PostgreSQL/pgvector integration: no reachable test database was
  available and CI does not currently execute database integration tests.
- [ ] Public hosting: no authenticated hosting access or verified public URL
  was available during the baseline.

Pytest emitted one environmental warning because Windows denied writes to the
existing `.pytest_cache` directory. Test execution itself succeeded.

### Latest verification on 2026-10-05

- [x] Backend suite: 233 passed, with 3 database integration tests skipped
  because no local PostgreSQL URL was configured.
- [x] Frontend suite: 18 passed across 2 test files.
- [x] Chromium smoke suite: 1 browser test passed.
- [x] Frontend TypeScript and production build passed.
- [x] Deployment smoke-test suite: 7 passed.
- [x] Project virtual-environment `pip check` reported no broken requirements.
- [x] The 30-case deterministic evaluation reproduced the recorded accuracy
  and retrieval metrics.
- [ ] Docker image build and provider deployment remain unverified locally.

## Audit findings

### Implemented and working

- [x] FastAPI routes use explicit Pydantic request and response models.
- [x] Cookie authentication, password hashing, session expiry, login
  throttling, password reset, origin checks, CORS restrictions, and security
  headers have automated coverage.
- [x] Cross-user isolation is tested for documents, opportunities, candidate
  profiles, reviews, tasks, analysis, and evidence references.
- [x] Uploads are restricted to PDF/TXT, streamed with a 10 MB bound, assigned
  server-side storage names, and protected from filename traversal.
- [x] Opportunity chunks retain source name, page, index, and stable chunk ID.
- [x] Eligibility assistance distinguishes `Eligible`, `Not eligible`, and
  `Insufficient information`, and returns requirement-level evidence.
- [x] Local JSON/SQLite development persistence and PostgreSQL application
  persistence are implemented as explicit modes.
- [x] Ten ordered, idempotent SQL migration files are present.
- [x] Structured request logs, request IDs, liveness, readiness, and
  privacy-safe security headers are implemented.
- [x] GitHub Actions runs Python tests, frontend tests/build, deployment smoke
  tests, Compose validation, and container builds.
- [x] The React interface includes authentication, upload, opportunity,
  evidence, review, task, profile, onboarding, loading, empty, and error states.

### Implemented but needing stronger verification or correction

- [x] Configured PostgreSQL load failures now fail closed during application
  startup instead of initializing empty application collections.
- [x] PostgreSQL routes use request-time, tenant-scoped CRUD instead of
  module-level application collections; transactional writes enforce quotas.
- [x] A checksum-verified migration runner records applied versions and fails
  on edited migration history.
- [x] CI is configured to execute migrations and pgvector isolation tests
  against PostgreSQL 16 with pgvector.
- [x] Database-backed integration tests cover pgvector opportunity isolation
  and request-fresh tenant-scoped application CRUD.
- [x] The restricted demo extracts bounded text into PostgreSQL and discards
  source bytes, avoiding reliance on the free host's ephemeral filesystem.
  Self-hosted/local mode can still retain bytes on its configured volume.
- [ ] The OpenAI embedding adapter has a timeout and mocked tests, but no
  bounded retry policy. Any live-provider test must remain opt-in and funded by
  the operator.
- [x] The API container applies pending migrations before Uvicorn starts, for
  both fresh and existing database volumes.
- [ ] Dependency versions are pinned in `requirements.txt`, but there is no
  hash-locked Python dependency artifact.

### Partially implemented

- [ ] Retrieval supports lexical, deterministic hash, OpenAI embeddings, and
  pgvector, but the default demonstrable path is lexical/in-memory.
- [x] Page citations exist for opportunity and applicant PDFs. Applicant PDF
  evidence preserves page-level provenance through storage and analysis.
- [x] A provider-neutral Docker plus Neon Free architecture, limitations, and
  recovery notes are documented.
- [ ] The README now includes measured evaluation results, an architecture
  diagram, and a fictional sample walkthrough; refreshed screenshots still
  require a running demo.

### Absent

- [x] Versioned 30-case synthetic retrieval/eligibility evaluation set with 20
  development and 10 held-out cases.
- [x] Repeatable deterministic evaluation CLI with saved baseline/comparison
  results for Recall@k, evidence-presence proxy, insufficient-information
  accuracy, structured validity, and local-process latency.
- [x] Real PostgreSQL/pgvector CI is configured; the expanded tenant CRUD test
  must pass on the exact release commit before deployment.
- [x] The deployment architecture is provider-neutral and keeps strict
  zero-cost safeguards; provider terms must be verified before provisioning.
- [ ] Verified public demo URL and restart/persistence acceptance evidence.

### Not verified because access or dependencies are missing

- [ ] Container images and Compose services running locally (Docker missing).
- [ ] The expanded PostgreSQL transaction, migration, CRUD, and pgvector suite
  is not runnable locally because Docker/PostgreSQL is unavailable; CI provides
  the real server and must be green on the release commit.
- [ ] SMTP delivery with a real provider (credentials intentionally absent).
- [ ] OpenAI embeddings with a live API (no paid call was authorized).
- [ ] Deployed behavior (provider access was not supplied). Hosting constraints
  were checked against dated official provider documentation.

## Highest-risk failure points

1. The restricted demo stores extracted text rather than source bytes; users
   must understand that downloads and OCR are intentionally unavailable.
2. Rule matching still lacks reliable numeric and synonym handling for GPA,
   work-duration, programming-skill, undergraduate-qualification, and CEFR
   evidence cases recorded in the evaluation report.
3. A public host, restart persistence, backup restoration, SMTP, and public
   two-user isolation still require deployed acceptance evidence.

## Implementation queue

### In progress — bounded ingestion hardening

- [x] Add configurable PDF page and extracted-character limits.
- [x] Reject invalid UTF-8, encrypted PDFs, whitespace-only text, and PDFs with
  no extractable text using clear client errors.
- [x] State explicitly that OCR is not supported for textless PDFs.
- [x] Apply the same extraction policy to applicant and opportunity uploads.
- [x] Add focused service and API regression tests.
- [x] Full backend suite: 201 tests passed after ingestion hardening.
- [x] Diff hygiene passed after ingestion hardening.

### Complete — persistence correctness

- [x] Stop swallowing configured PostgreSQL load failures.
- [x] Use request-time tenant-scoped queries and transactional quota writes.
- [x] Add a small idempotent migration runner with an applied-version ledger.
- [x] Add PostgreSQL/pgvector integration tests and a CI database service.
- [x] PostgreSQL/pgvector integration passed on GitHub Actions for `4f70904`.

### Then — measurable AI quality and demo deployment

- [x] Create 30 fully synthetic evaluation fixtures with fictional applicant
  data and explicit annotation rationales.
- [x] Record a deterministic lexical baseline, improve the measured missing-
  information weakness, and compare under identical conditions.
- [x] Overall outcome accuracy improved from 0.6000 to 0.8333; held-out
  accuracy improved from 0.6000 to 0.8000; insufficient-information accuracy
  improved from 0.0000 to 1.0000. Retrieval was unchanged at Recall@1 0.8824
  and Recall@3 0.9412.
- [x] Preserve page-level applicant PDF evidence provenance in analysis output.
- [x] Keep provider-neutral Docker packaging and strict zero-cost requirements.
- [ ] Select a host only after verifying its current zero-cost terms.
- [ ] Deploy only after CI passes and verify the public sample journey,
  isolation, failure states, cold starts, and persistence.
- [x] Refresh README evidence, demo walkthrough, limitations, and CV bullets
  from completed—not planned—work.
- [ ] Add screenshots after the demo is running and visually verified.
