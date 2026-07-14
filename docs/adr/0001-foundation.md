# ADR 0001: Foundation architecture

## Status

Accepted — 14 July 2026

## Decision

ApplyLens AI starts as a monorepo. The user interface uses React and TypeScript. The API uses FastAPI and Pydantic. PostgreSQL will hold application state, while document processing will run asynchronously in a worker introduced during Sprint 1.

## Reason

This separates the user interface, API, and expensive document processing without creating unnecessary services in the first vertical slice.

## Guardrails

- Every eligibility decision must cite the official call.
- An `Eligible` decision must also cite candidate evidence.
- Missing evidence produces `Unclear`, never a guessed result.
- No automatic application submission is part of the MVP.

