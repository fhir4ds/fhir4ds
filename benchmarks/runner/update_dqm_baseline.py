"""Safely update the checked-in DQM performance baseline."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from dqm_perf_report import compare_reports, markdown_report, summarize_suite
else:
    from .dqm_perf_report import compare_reports, markdown_report, summarize_suite


DEFAULT_REPORT = Path("conformance/reports/dqm_report.json")
DEFAULT_BASELINE = Path("benchmarks/baselines/dqm_2025.json")
DEFAULT_OUTPUT_JSON = Path("benchmarks/output/dqm-performance-report.json")
DEFAULT_OUTPUT_MD = Path("benchmarks/output/dqm-performance-report.md")


def load_report(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"DQM report not found: {path}")
    return json.loads(path.read_text())


def measure_records(report: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        measure_id: record
        for measure_id, record in report.items()
        if (
            isinstance(record, dict)
            and isinstance(record.get("timings_ms"), dict)
            and isinstance(record.get("tests"), list)
        )
    }


def failed_measures(report: dict[str, Any]) -> list[str]:
    failed: list[str] = []
    for measure_id, record in measure_records(report).items():
        tests = record.get("tests", [])
        if not tests or any(not test.get("result", {}).get("passed") for test in tests):
            failed.append(measure_id)
    return sorted(failed)


def validate_report(report: dict[str, Any], *, expected_measures: int | None) -> None:
    records = measure_records(report)
    if expected_measures is not None and len(records) != expected_measures:
        raise ValueError(
            f"Expected {expected_measures} measure records, found {len(records)}"
        )
    failures = failed_measures(report)
    if failures:
        raise ValueError(f"Cannot update baseline from failing report: {failures}")


def run_dqm_conformance() -> None:
    subprocess.run(
        [sys.executable, "conformance/scripts/run_dqm.py"],
        check=True,
    )


def write_comparison(
    report: dict[str, Any],
    baseline: dict[str, Any] | None,
    output_json: Path,
    output_md: Path,
) -> None:
    comparison = compare_reports(
        report,
        baseline,
        ratio_threshold=2.0,
        absolute_threshold_ms=500.0,
    )
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_md.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(comparison, indent=2) + "\n")
    output_md.write_text(markdown_report(comparison) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description="Update the DQM 2025 performance baseline")
    parser.add_argument("--run", action="store_true", help="Run DQM conformance before updating")
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--baseline", type=Path, default=DEFAULT_BASELINE)
    parser.add_argument("--output-json", type=Path, default=DEFAULT_OUTPUT_JSON)
    parser.add_argument("--output-md", type=Path, default=DEFAULT_OUTPUT_MD)
    parser.add_argument("--expected-measures", type=int, default=47)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate and summarize without writing the baseline",
    )
    args = parser.parse_args()

    if args.run:
        run_dqm_conformance()

    report = load_report(args.report)
    validate_report(report, expected_measures=args.expected_measures)
    suite = summarize_suite(report)
    old_baseline = load_report(args.baseline) if args.baseline.exists() else None

    print(
        "DQM report validated: "
        f"{suite['passed']}/{suite['measure_count']} measures passed; "
        f"total measured time {suite['total_ms']:,.0f} ms"
    )

    if args.dry_run:
        print(f"Dry run: baseline not updated ({args.baseline})")
        return 0

    args.baseline.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(args.report, args.baseline)
    print(f"Updated baseline: {args.baseline}")

    write_comparison(report, old_baseline, args.output_json, args.output_md)
    print(f"Wrote comparison JSON: {args.output_json}")
    print(f"Wrote comparison Markdown: {args.output_md}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
