import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
DATASET = ROOT / "evaluation" / "cases" / "v1.json"
BASELINE = ROOT / "evaluation" / "results" / "baseline.json"
IMPROVED = ROOT / "evaluation" / "results" / "improved.json"


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_evaluation_dataset_is_versioned_split_and_fully_annotated() -> None:
    dataset = load_json(DATASET)
    cases = dataset["cases"]

    assert dataset["version"] == "1.0.0"
    assert len(cases) == 30
    assert len({case["id"] for case in cases}) == 30
    assert sum(case["split"] == "development" for case in cases) == 20
    assert sum(case["split"] == "held_out" for case in cases) == 10
    assert all(case["expected_evidence"] for case in cases)
    assert all(case["rationale"].strip() for case in cases)
    assert {
        case["expected_eligibility"] for case in cases
    } <= {"Eligible", "Not eligible", "Insufficient information"}


def test_saved_evaluation_comparison_uses_the_same_dataset_and_conditions() -> None:
    baseline = load_json(BASELINE)
    improved = load_json(IMPROVED)

    assert baseline["dataset_version"] == improved["dataset_version"] == "1.0.0"
    assert baseline["conditions"]["retrieval"] == improved["conditions"]["retrieval"]
    assert baseline["conditions"]["chunking"] == improved["conditions"]["chunking"]
    assert baseline["overall"]["case_count"] == improved["overall"]["case_count"] == 30


def test_saved_result_records_measured_uncertainty_improvement() -> None:
    baseline = load_json(BASELINE)["overall"]
    improved = load_json(IMPROVED)["overall"]

    assert baseline["insufficient_information_accuracy"] == 0.0
    assert improved["insufficient_information_accuracy"] == 1.0
    assert improved["eligibility_outcome_accuracy"] > baseline[
        "eligibility_outcome_accuracy"
    ]
    assert improved["retrieval_recall_at_1"] == baseline["retrieval_recall_at_1"]
    assert improved["retrieval_recall_at_3"] == baseline["retrieval_recall_at_3"]
