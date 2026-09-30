# Evaluation report: explicit insufficient-information state

Run date: 2026-09-28

## Question

Does replacing the ambiguous missing-evidence result `Action required` with the
explicit result `Insufficient information` improve eligibility outcome accuracy
without changing retrieval behavior?

## Method

The version 1.0.0 set contains 30 fully synthetic cases: 20 development and 10
held-out cases. Applicant identities and evidence are fictional. Each case has
human-authored evidence spans, source pages, requirements, expected outcome,
and a short rationale.

The runner used the repository's deterministic `InMemoryRetriever`, page-aware
chunking at 240 characters, and the actual `analyse_opportunity` function.
Rate-limit persistence alone was mocked so evaluation traffic did not mutate
local abuse-control state. No LLM judge, external model, network request, or
paid API was used.

The baseline was run from the dirty `codex/portfolio-reliability` working tree
at Git revision `cd91c71`, immediately before the eligibility vocabulary change.
The comparison was run immediately after that change under the same local
conditions. Full per-case outputs and timing conditions are preserved in
`results/baseline.json` and `results/improved.json`.

## Results

| Metric | Baseline | Improved | Change |
| --- | ---: | ---: | ---: |
| Retrieval Recall@1 | 0.8824 | 0.8824 | 0.0000 |
| Retrieval Recall@3 | 0.9412 | 0.9412 | 0.0000 |
| Eligibility outcome accuracy | 0.6000 | 0.8333 | +0.2333 |
| Held-out outcome accuracy | 0.6000 | 0.8000 | +0.2000 |
| Insufficient-information accuracy | 0.0000 | 1.0000 | +1.0000 |
| Structured-output validity | 1.0000 | 1.0000 | 0.0000 |
| Decisive evidence presence proxy | 1.0000 | 1.0000 | 0.0000 |

Latency was sub-millisecond in both local runs, but this is not a deployment
benchmark. The runner excludes HTTP, database, browser, provider, network, and
cold-start time, so minor timing differences should not be interpreted as a
performance change.

## Remaining failures

Five cases expected to be eligible remain `Insufficient information`:

- GPA threshold comparison (`dev-009`)
- duration of professional experience (`dev-015`)
- Python skill evidence (`dev-016`)
- undergraduate qualification synonym (`held-005`)
- CEFR C1 language evidence (`held-006`)

These are real limitations of the deliberately small rule matcher. Adding
explicit, tested rules may be appropriate, but none should infer equivalence or
numeric sufficiency without parsing the requirement and evidence reliably.

Two evidence annotations miss the lexical top three: the partner-country
citizenship passage (`dev-010`) and the undergraduate-qualification passage
(`held-005`). Both are query/document vocabulary mismatches. No embedding claim
is made: this evaluation is explicitly lexical.

## Interpretation

The change fixes the measured uncertainty-state defect on both development and
held-out cases without affecting retrieval. The result does not establish
admissions correctness, semantic entailment, generalization to real documents,
or hosted latency. The evidence-presence metric is a proxy and does not replace
human review of whether an evidence item truly supports a conclusion.
