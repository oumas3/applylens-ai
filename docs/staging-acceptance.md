# ApplyLens controlled staging acceptance

Complete this record against the exact release commit before public promotion.
Use dedicated staging accounts and synthetic documents; never write passwords,
reset links, API keys, or document contents into this file or an issue.

## Evidence record

| Field | Operator records |
| --- | --- |
| Release commit | Git SHA |
| Product version | Value from `/api/v1/product` |
| Web and API URLs | Public HTTPS hostnames |
| CI run | Successful workflow URL or run ID |
| Operator | Name or internal identifier |
| Test time | UTC start and finish |
| Browser/device | Browser version and viewport |
| Smoke output | Private log or artifact reference |
| Backup/restore evidence | Private log or ticket reference |
| Result | GO or NO-GO with unresolved issue references |

## 1. Public and infrastructure checks

- [ ] Both hosts use trusted HTTPS with no browser warning.
- [ ] The exact commit's backend, frontend, container-build, and Compose CI jobs pass.
- [ ] `deploy/smoke_test.py` passes liveness, readiness, product metadata, and
      frontend-shell checks.
- [ ] Privacy, terms, acceptable-use, AI-limitations, release version, and the
      support mail link are visible before registration.
- [ ] A PostgreSQL backup and uploaded-file backup are copied off host, restored
      into isolated targets, and an uploaded document is readable from the
      restored environment.

## 2. Primary-account workflow

- [ ] Register the first account with a unique staging email and 12+ character password.
- [ ] Upload one TXT and one multi-page PDF; preview extracted text from both.
- [ ] Add profile education/research evidence linked to an owned document and save it.
- [ ] Upload and extract an academic-call PDF or TXT; inspect requirements,
      deadline, funding, and source citations against the original file.
- [ ] Search opportunity evidence and use a result in eligibility analysis.
- [ ] Save the review, compare it, generate tasks, and change a task status.
- [ ] Export account data; verify the profile, both documents and their exact
      file content, opportunity, review, and task are present.
- [ ] Sign out and sign in again; confirm saved state remains available.
- [ ] Change the password; confirm another active session is revoked.

## 3. Recovery, privacy, and isolation

- [ ] Request password recovery and receive the SMTP message at the controlled address.
- [ ] Use the reset link once; confirm reuse fails and the old password no longer works.
- [ ] Create a second account and confirm it cannot list, read, change, compare,
      export, or delete any first-account record or file.
- [ ] Confirm external AI is off initially. If the deployment enables an external
      provider, confirm search is blocked without consent and works only after opt-in.
- [ ] Delete one review and one task and confirm they remain absent after reload.
- [ ] Permanently delete both staging accounts; confirm their old sessions and
      credentials no longer work and active records/files are gone.

## Promotion rule

Record `GO` only when every box passes for the same deployed commit. Any failed
TLS, SMTP, tenant-isolation, export, deletion, backup/restore, or smoke check is
an automatic `NO-GO`. Fix the cause, deploy a new commit, and repeat the full
record rather than carrying evidence forward from an older release.
