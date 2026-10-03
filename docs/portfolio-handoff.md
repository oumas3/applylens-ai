# ApplyLens AI portfolio handoff

Last updated: 2026-09-28

## One-line project story

ApplyLens AI is a full-stack, evidence-first application intelligence tool that
turns Master's and PhD calls plus candidate documents into traceable eligibility
assistance, missing-information flags, and application tasks.

## What the repository demonstrates

- React and TypeScript product UX with authentication, onboarding, responsive
  states, document/profile workflows, opportunity comparison, and task tracking.
- FastAPI and Pydantic API design with tenant ownership checks, rate limits,
  quotas, structured logs, request IDs, security headers, and explicit health
  probes.
- PostgreSQL persistence, ordered checksum-verified migrations, and pgvector
  integration tests without making vector search a requirement for the free
  demo.
- Defensive PDF/TXT ingestion with byte, page, and extracted-character bounds;
  encrypted, corrupt, blank, invalid-UTF-8, and OCR-only inputs fail clearly.
- A 30-case synthetic evaluation split into development and held-out cases,
  with saved baseline/improved results and honest proxy-metric limitations.
- CI-gated, provider-neutral container deployment configuration for a
  restricted Neon Free demo that uses deterministic retrieval and no paid
  model API.

## CV-ready bullets

- Built an evidence-first Master's/PhD application intelligence platform using
  React, TypeScript, FastAPI, Pydantic, and PostgreSQL, covering document intake,
  candidate profiles, eligibility reasoning, opportunity comparison, and task
  tracking.
- Hardened multi-tenant document processing with bounded PDF/TXT extraction,
  fail-closed persistence, account isolation tests, rate limits, quotas, and
  privacy-safe observability; verified 224 backend and 18 frontend tests locally.
- Designed a checksum-verified PostgreSQL migration runner and pgvector CI job,
  plus a zero-paid-API deployment path that serves the React bundle and FastAPI
  API from one free-tier container.
- Created a 30-case synthetic evaluation harness; improved overall deterministic
  eligibility outcome accuracy from 60.0% to 83.3% and held-out accuracy from
  60.0% to 80.0% while preserving explicit insufficient-information handling.

## Interview talking points

- Why lexical retrieval is the honest default: it is deterministic, cheap,
  testable, and sufficient for a portfolio demo; OpenAI/pgvector remains an
  optional, separately funded path.
- Why unknown evidence is not a negative decision: the product now emits
  `Insufficient information`, preventing absence of proof from becoming proof
  of ineligibility.
- Why source bytes are discarded in the restricted demo: the application host
  does not need persistent storage because bounded extracted text is stored in
  PostgreSQL, while downloads and OCR are explicitly out of scope.
- Why the app is not called production-ready: remote CI, provider deployment,
  cold-start behavior, restart persistence, backup restoration, and public
  tenant-isolation acceptance still require external verification.

## Claims to avoid until deployment verification

- Do not publish a live-demo URL until the full checklist in `docs/deployment.md`
  passes against that exact revision.
- Do not call the synthetic metrics admissions accuracy or general model quality.
- Do not claim local Docker or real PostgreSQL execution was verified on this
  workstation; Docker was unavailable and the two integration tests skipped.
- Do not claim password recovery works in the restricted demo; outbound SMTP is
  intentionally disabled there.
