# ApplyLens AI Project Context

## Project overview
ApplyLens AI is an evidence-based application intelligence platform for Master's and PhD candidates. It analyzes candidate documents and academic calls to identify eligibility, supporting evidence, missing requirements, deadlines, fees, funding, and application tasks. It does not submit applications automatically.

## Repository
- Repository: https://github.com/oumas3/applylens-ai
- Local workspace: C:\Users\Oumi.LAPTOP-OUMA\Desktop\applylens-ai

## Tech stack
- Frontend: React, TypeScript, Vite
- Backend: FastAPI, Python 3.12, Pydantic
- Testing: pytest
- Version control: Git and GitHub

## Current status
- Sprints 0 through 17 are complete; release hardening is in progress.
- The React interface works and looks professional.
- The frontend connects successfully to the FastAPI health endpoint.
- npm dependencies are installed. 
- The current Git branch is `main`.
- Sprint 1 document ingestion is complete.
- Opportunity analysis, eligibility reasoning, application task tracking, account privacy, and launch packaging are implemented.
- The backend has 233 passing local tests plus 3 PostgreSQL integration tests configured for CI.
- The frontend has 18 passing unit tests, a passing Chromium smoke test, and a passing production build.

## Working rules
- Guide the work carefully, one step at a time.
- Explain what each command or file change is doing.
- Do not make large batches of unexplained changes.
- Inspect existing files before modifying them.
- Preserve all existing work.
- Show the Git diff before committing.
- Do not commit or push unless explicitly approved.
- Use PowerShell-compatible commands because the workspace is on Windows.

## Development approach
- Prefer small, verified changes.
- Investigate the current filesystem and repository state before assuming anything.
- Verify fixes with the relevant test or command output before claiming success.
- Keep the project moving in a transparent, collaborative way.
