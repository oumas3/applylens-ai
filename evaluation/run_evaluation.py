"""Run the deterministic ApplyLens retrieval and eligibility evaluation."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import platform
import statistics
import subprocess
import sys
from time import perf_counter
from typing import Any
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
API_ROOT = ROOT / "apps" / "api"
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from app.routers.opportunities import (  # noqa: E402
    OpportunityAnalysisRequest,
    OpportunityAnalysisResponse,
    analyse_opportunity,
)
from app.services.retrieval_service import (  # noqa: E402
    InMemoryRetriever,
    chunk_text,
)


def git_revision() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"],
        cwd=ROOT,
        capture_output=True,
        check=False,
        text=True,
    )
    return result.stdout.strip() or "unknown"


def percentile(values: list[float], percentile_value: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(0, math.ceil(percentile_value * len(ordered)) - 1)
    return ordered[index]


def round_ratio(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 4) if denominator else 0.0


def evaluate_case(case: dict[str, Any]) -> dict[str, Any]:
    retriever = InMemoryRetriever()
    chunks = []
    for page_number, page_text in enumerate(case["source_pages"], start=1):
        chunks.extend(
            chunk_text(
                page_text,
                source_name=f"{case['id']}.txt",
                page=page_number,
                max_chars=240,
            )
        )
    retriever.index(chunks)

    started = perf_counter()
    retrieved = retriever.search(case["query"], top_k=3)
    with patch("app.routers.opportunities.enforce_rate_limit"):
        response = analyse_opportunity(
            OpportunityAnalysisRequest(
                title=case["title"],
                requirements=case["requirements"],
                evidence=case["applicant_evidence"],
            ),
            user={
                "id": f"evaluation-{case['id']}",
                "email": f"{case['id']}@example.invalid",
                "is_active": True,
            },
        )
    elapsed_ms = (perf_counter() - started) * 1000

    structured_valid = True
    try:
        OpportunityAnalysisResponse.model_validate(response.model_dump())
    except Exception:
        structured_valid = False

    retrieved_payload = [result.model_dump(mode="json") for result in retrieved]
    expected_matches: list[dict[str, Any]] = []
    for expected in case["expected_evidence"]:
        matching_ranks = [
            rank
            for rank, result in enumerate(retrieved, start=1)
            if expected["text"].lower() in result.chunk.text.lower()
            and expected["page"] == result.chunk.page
        ]
        expected_matches.append(
            {
                **expected,
                "first_matching_rank": matching_ranks[0] if matching_ranks else None,
            }
        )

    decisive_results = [
        item
        for item in response.requirement_results
        if item.status in {"Eligible", "Not eligible"}
    ]
    supported_decisions = sum(bool(item.evidence) for item in decisive_results)

    return {
        "id": case["id"],
        "split": case["split"],
        "expected_eligibility": case["expected_eligibility"],
        "actual_eligibility": response.eligibility,
        "outcome_correct": response.eligibility == case["expected_eligibility"],
        "structured_output_valid": structured_valid,
        "decisive_requirements": len(decisive_results),
        "decisive_requirements_with_evidence": supported_decisions,
        "retrieval_expected_matches": expected_matches,
        "retrieved": retrieved_payload,
        "latency_ms": round(elapsed_ms, 3),
    }


def summarize(results: list[dict[str, Any]]) -> dict[str, Any]:
    expected_items = [
        item
        for result in results
        for item in result["retrieval_expected_matches"]
    ]
    decisive = sum(result["decisive_requirements"] for result in results)
    supported = sum(
        result["decisive_requirements_with_evidence"] for result in results
    )
    insufficient = [
        result
        for result in results
        if result["expected_eligibility"] == "Insufficient information"
    ]
    latencies = [float(result["latency_ms"]) for result in results]

    return {
        "case_count": len(results),
        "retrieval_annotation_count": len(expected_items),
        "retrieval_recall_at_1": round_ratio(
            sum(item["first_matching_rank"] == 1 for item in expected_items),
            len(expected_items),
        ),
        "retrieval_recall_at_3": round_ratio(
            sum(
                item["first_matching_rank"] is not None
                and item["first_matching_rank"] <= 3
                for item in expected_items
            ),
            len(expected_items),
        ),
        "eligibility_outcome_accuracy": round_ratio(
            sum(result["outcome_correct"] for result in results),
            len(results),
        ),
        "insufficient_information_accuracy": round_ratio(
            sum(result["outcome_correct"] for result in insufficient),
            len(insufficient),
        ),
        "structured_output_validity": round_ratio(
            sum(result["structured_output_valid"] for result in results),
            len(results),
        ),
        "decisive_evidence_presence_proxy": round_ratio(supported, decisive),
        "latency_ms_median": round(statistics.median(latencies), 3),
        "latency_ms_p95": round(percentile(latencies, 0.95), 3),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--cases",
        type=Path,
        default=ROOT / "evaluation" / "cases" / "v1.json",
    )
    parser.add_argument("--label", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    dataset = json.loads(args.cases.read_text(encoding="utf-8"))
    case_results = [evaluate_case(case) for case in dataset["cases"]]
    splits = {
        split: summarize(
            [result for result in case_results if result["split"] == split]
        )
        for split in ("development", "held_out")
    }
    report = {
        "label": args.label,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "git_revision": git_revision(),
        "dataset_version": dataset["version"],
        "data_classification": dataset["data_classification"],
        "conditions": {
            "retrieval": "InMemoryRetriever lexical token overlap, top_k=3",
            "chunking": "Per synthetic page, max_chars=240, no overlap",
            "eligibility": "ApplyLens deterministic opportunity analysis",
            "external_ai_calls": False,
            "timing": "Warm local process; retrieval plus eligibility; not a hosting benchmark",
            "python": platform.python_version(),
            "platform": platform.system(),
        },
        "metric_notes": {
            "decisive_evidence_presence_proxy": "Checks that each decisive requirement result includes evidence; it does not judge semantic entailment.",
            "structured_output_validity": "Validates the returned object against OpportunityAnalysisResponse.",
            "latency": "Local deterministic execution only; excludes HTTP, database, cold start, and network time."
        },
        "overall": summarize(case_results),
        "splits": splits,
        "cases": case_results,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"overall": report["overall"], "splits": splits}, indent=2))


if __name__ == "__main__":
    main()
