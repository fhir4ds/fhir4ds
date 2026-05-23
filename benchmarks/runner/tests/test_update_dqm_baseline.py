from __future__ import annotations

import json
from pathlib import Path

from benchmarks.runner.update_dqm_baseline import load_report, validate_report, write_comparison


def _report(total_ms: float) -> dict:
    return {
        "CMS0001": {
            "tests": [{"name": "Full Logic Accuracy", "result": {"passed": True}}],
            "patient_count": 1,
            "accuracy_pct": 100.0,
            "sql_size_bytes": 100,
            "timings_ms": {
                "total_ms": total_ms,
                "library_translation_ms": total_ms / 4,
                "sql_generation_ms": total_ms / 4,
                "sql_execution_ms": total_ms / 4,
            },
        },
        "_summary": {
            "total_measures": 1,
            "passed_measures": 1,
        },
    }


def test_write_comparison_uses_previous_baseline(tmp_path: Path) -> None:
    current = _report(3000.0)
    previous = _report(1000.0)
    output_json = tmp_path / "comparison.json"
    output_md = tmp_path / "comparison.md"

    write_comparison(current, previous, output_json, output_md)

    comparison = json.loads(output_json.read_text())
    metric = comparison["measures"][0]["metrics"]["total_ms"]
    assert metric["baseline_ms"] == 1000.0
    assert metric["current_ms"] == 3000.0
    assert metric["delta_ms"] == 2000.0
    assert metric["ratio"] == 3.0
    assert comparison["regressions"]


def test_validate_report_rejects_failed_measure() -> None:
    report = _report(1000.0)
    report["CMS0001"]["tests"][0]["result"]["passed"] = False

    try:
        validate_report(report, expected_measures=1)
    except ValueError as exc:
        assert "Cannot update baseline" in str(exc)
    else:  # pragma: no cover - explicit failure branch
        raise AssertionError("expected validate_report to reject failed measure")


def test_load_report_requires_existing_path(tmp_path: Path) -> None:
    try:
        load_report(tmp_path / "missing.json")
    except FileNotFoundError as exc:
        assert "DQM report not found" in str(exc)
    else:  # pragma: no cover - explicit failure branch
        raise AssertionError("expected missing report to raise")
