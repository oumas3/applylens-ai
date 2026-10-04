# ApplyLens deterministic evaluation

This evaluation uses 30 fully synthetic academic calls and fictional applicant
profiles. Twenty cases are development cases and ten are held out. The cases
cover clear requirements, absent evidence, explicit negative evidence,
qualified or conflicting wording, multiple source pages, irrelevant passages,
and instruction-like text embedded inside documents.

The labels are human-authored rules for this repository, not admissions advice.
No LLM judge or paid API is used.
The runner also overrides deployment database and retrieval settings before it
imports the API, so a linked local `.env` cannot send evaluation traffic to
Neon or an external model provider.

## Metrics

- Retrieval Recall@1 and Recall@3 measure whether each annotated evidence span
  and page appears in the lexical retriever's top results.
- Eligibility outcome accuracy compares the deterministic result with
  `Eligible`, `Not eligible`, or `Insufficient information`.
- Insufficient-information accuracy isolates the cases where evidence is absent
  or the call is underspecified.
- Structured-output validity revalidates the result with the API response model.
- Decisive evidence presence is a proxy: it checks that an eligible/ineligible
  requirement has attached evidence, but does not prove semantic entailment.
- Latency is measured in a warm local Python process. It excludes HTTP,
  database, network, provider, hosting cold-start, and browser time.

## Run

From the repository root:

```powershell
.\.venv\Scripts\python.exe evaluation\run_evaluation.py `
  --label baseline `
  --output evaluation\results\baseline.json
```

Use the same dataset, interpreter, and command conditions for comparisons.
Saved result files contain the dataset version, Git revision, measurement
conditions, aggregate metrics, split metrics, and per-case failures.
