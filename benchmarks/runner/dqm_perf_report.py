"""Generate a DQM timing comparison report from conformance output.

The input report is the JSON produced by ``conformance/scripts/run_dqm.py``.
By default this script is report-only and exits successfully even when timing
regressions are detected. Pass ``--fail-on-regression`` when the baseline is
stable enough to use as a hard CI gate.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DEFAULT_METRICS = (
    "total_ms",
    "library_translation_ms",
    "sql_generation_ms",
    "sql_execution_ms",
)


def is_measure_record(value: Any) -> bool:
    return (
        isinstance(value, dict)
        and isinstance(value.get("timings_ms"), dict)
        and isinstance(value.get("tests"), list)
    )


def load_report(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Report not found: {path}")
    return json.loads(path.read_text())


def measure_passed(record: dict[str, Any]) -> bool:
    tests = record.get("tests", [])
    return bool(tests) and all(
        bool(test.get("result", {}).get("passed"))
        for test in tests
        if isinstance(test, dict)
    )


def timing(record: dict[str, Any], metric: str) -> float:
    value = record.get("timings_ms", {}).get(metric, 0.0)
    return float(value or 0.0)


def summarize_suite(report: dict[str, Any]) -> dict[str, Any]:
    measures = [record for record in report.values() if is_measure_record(record)]
    totals = [timing(record, "total_ms") for record in measures]
    passed = sum(1 for record in measures if measure_passed(record))
    return {
        "measure_count": len(measures),
        "passed": passed,
        "total_ms": round(sum(totals), 3),
        "median_total_ms": round(statistics.median(totals), 3) if totals else 0.0,
        "max_total_ms": round(max(totals), 3) if totals else 0.0,
    }


def compare_reports(
    current: dict[str, Any],
    baseline: dict[str, Any] | None,
    *,
    ratio_threshold: float,
    absolute_threshold_ms: float,
    metrics: tuple[str, ...] = DEFAULT_METRICS,
) -> dict[str, Any]:
    current_ids = sorted(k for k, v in current.items() if is_measure_record(v))
    baseline = baseline or {}
    baseline_ids = sorted(k for k, v in baseline.items() if is_measure_record(v))
    all_ids = sorted(set(current_ids) | set(baseline_ids))

    rows: list[dict[str, Any]] = []
    regressions: list[dict[str, Any]] = []
    accuracy_regressions: list[str] = []
    missing_current: list[str] = []
    missing_baseline: list[str] = []

    for measure_id in all_ids:
        cur = current.get(measure_id)
        base = baseline.get(measure_id)
        if not is_measure_record(cur):
            missing_current.append(measure_id)
            rows.append({"measure": measure_id, "status": "missing-current"})
            continue
        if not is_measure_record(base):
            missing_baseline.append(measure_id)
            rows.append({
                "measure": measure_id,
                "status": "missing-baseline",
                "current_total_ms": round(timing(cur, "total_ms"), 3),
                "passed": measure_passed(cur),
            })
            continue

        current_passed = measure_passed(cur)
        baseline_passed = measure_passed(base)
        if baseline_passed and not current_passed:
            accuracy_regressions.append(measure_id)

        metric_deltas: dict[str, dict[str, float | bool]] = {}
        flagged = False
        for metric in metrics:
            cur_ms = timing(cur, metric)
            base_ms = timing(base, metric)
            delta_ms = cur_ms - base_ms
            ratio = cur_ms / base_ms if base_ms > 0 else 0.0
            metric_flagged = (
                base_ms > 0
                and ratio >= ratio_threshold
                and delta_ms >= absolute_threshold_ms
            )
            flagged = flagged or metric_flagged
            metric_deltas[metric] = {
                "baseline_ms": round(base_ms, 3),
                "current_ms": round(cur_ms, 3),
                "delta_ms": round(delta_ms, 3),
                "ratio": round(ratio, 3) if base_ms > 0 else 0.0,
                "flagged": metric_flagged,
            }

        row = {
            "measure": measure_id,
            "status": "ok",
            "passed": current_passed,
            "baseline_passed": baseline_passed,
            "patient_count": cur.get("patient_count"),
            "accuracy_pct": cur.get("accuracy_pct"),
            "sql_size_bytes": cur.get("sql_size_bytes"),
            "metrics": metric_deltas,
            "flagged": flagged,
        }
        rows.append(row)
        if flagged:
            regressions.append(row)

    suite = {
        "current": summarize_suite(current),
        "baseline": summarize_suite(baseline) if baseline else None,
    }
    if baseline:
        base_total = suite["baseline"]["total_ms"]
        cur_total = suite["current"]["total_ms"]
        suite["delta_total_ms"] = round(cur_total - base_total, 3)
        suite["total_ratio"] = round(cur_total / base_total, 3) if base_total > 0 else 0.0

    return {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "thresholds": {
            "ratio": ratio_threshold,
            "absolute_ms": absolute_threshold_ms,
        },
        "suite": suite,
        "regressions": regressions,
        "accuracy_regressions": accuracy_regressions,
        "missing_current": missing_current,
        "missing_baseline": missing_baseline,
        "measures": rows,
    }


def markdown_report(comparison: dict[str, Any]) -> str:
    suite = comparison["suite"]
    current = suite["current"]
    baseline = suite.get("baseline")
    thresholds = comparison["thresholds"]
    lines = [
        "# DQM Performance Report",
        "",
        f"Generated: `{comparison['generated_at']}`",
        "",
        "## Summary",
        "",
        "| Metric | Current | Baseline |",
        "|--------|---------|----------|",
        f"| Measures passed | {current['passed']}/{current['measure_count']} | "
        f"{baseline['passed']}/{baseline['measure_count'] if baseline else 0}"
        if baseline else f"| Measures passed | {current['passed']}/{current['measure_count']} | n/a |",
        f"| Total measured time | {current['total_ms']:,.0f} ms | "
        f"{baseline['total_ms']:,.0f} ms |" if baseline
        else f"| Total measured time | {current['total_ms']:,.0f} ms | n/a |",
        f"| Median measure total | {current['median_total_ms']:,.0f} ms | "
        f"{baseline['median_total_ms']:,.0f} ms |" if baseline
        else f"| Median measure total | {current['median_total_ms']:,.0f} ms | n/a |",
        "",
    ]

    if baseline:
        lines.extend([
            f"Suite total ratio: `{suite['total_ratio']}x` "
            f"({suite['delta_total_ms']:+,.0f} ms).",
            "",
        ])
    else:
        lines.extend([
            "No baseline was provided. This report records current timings only.",
            "",
        ])

    lines.extend([
        "Regression threshold:",
        f"- Ratio >= `{thresholds['ratio']}x`",
        f"- Absolute increase >= `{thresholds['absolute_ms']:,.0f} ms`",
        "",
    ])

    accuracy = comparison["accuracy_regressions"]
    regressions = comparison["regressions"]
    missing_current = comparison["missing_current"]
    missing_baseline = comparison["missing_baseline"]

    lines.extend([
        "## Findings",
        "",
        f"- Accuracy regressions: `{len(accuracy)}`"
        + (f" ({', '.join(accuracy)})" if accuracy else ""),
        f"- Timing regressions: `{len(regressions)}`",
        f"- Missing current measures: `{len(missing_current)}`"
        + (f" ({', '.join(missing_current)})" if missing_current else ""),
        f"- New measures without baseline: `{len(missing_baseline)}`"
        + (f" ({', '.join(missing_baseline)})" if missing_baseline else ""),
        "",
    ])

    flagged = sorted(
        regressions,
        key=lambda row: row["metrics"]["total_ms"]["ratio"],
        reverse=True,
    )
    if flagged:
        lines.extend([
            "## Flagged Measures",
            "",
            "| Measure | Total | Ratio | Translation | SQL Gen | SQL Exec |",
            "|---------|-------|-------|-------------|---------|----------|",
        ])
        for row in flagged:
            metrics = row["metrics"]
            lines.append(
                f"| {row['measure']} "
                f"| {metrics['total_ms']['current_ms']:,.0f} ms "
                f"| {metrics['total_ms']['ratio']}x "
                f"| {metrics['library_translation_ms']['delta_ms']:+,.0f} ms "
                f"| {metrics['sql_generation_ms']['delta_ms']:+,.0f} ms "
                f"| {metrics['sql_execution_ms']['delta_ms']:+,.0f} ms |"
            )
        lines.append("")

    lines.extend([
        "## Slowest Measures",
        "",
        "| Measure | Total | SQL Gen | SQL Exec | Translation |",
        "|---------|-------|---------|----------|-------------|",
    ])
    ok_rows = [row for row in comparison["measures"] if row.get("status") == "ok"]
    slowest = sorted(
        ok_rows,
        key=lambda row: row["metrics"]["total_ms"]["current_ms"],
        reverse=True,
    )[:10]
    for row in slowest:
        metrics = row["metrics"]
        lines.append(
            f"| {row['measure']} "
            f"| {metrics['total_ms']['current_ms']:,.0f} ms "
            f"| {metrics['sql_generation_ms']['current_ms']:,.0f} ms "
            f"| {metrics['sql_execution_ms']['current_ms']:,.0f} ms "
            f"| {metrics['library_translation_ms']['current_ms']:,.0f} ms |"
        )
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate a DQM performance report")
    parser.add_argument("--current", type=Path, required=True, help="Current dqm_report.json")
    parser.add_argument("--baseline", type=Path, help="Baseline dqm_report.json")
    parser.add_argument("--output-json", type=Path, required=True, help="Comparison JSON output")
    parser.add_argument("--output-md", type=Path, required=True, help="Markdown report output")
    parser.add_argument("--ratio-threshold", type=float, default=2.0)
    parser.add_argument("--absolute-threshold-ms", type=float, default=500.0)
    parser.add_argument("--fail-on-regression", action="store_true")
    args = parser.parse_args()

    current = load_report(args.current)
    baseline = load_report(args.baseline) if args.baseline and args.baseline.exists() else None
    comparison = compare_reports(
        current,
        baseline,
        ratio_threshold=args.ratio_threshold,
        absolute_threshold_ms=args.absolute_threshold_ms,
    )

    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_md.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(comparison, indent=2) + "\n")
    args.output_md.write_text(markdown_report(comparison) + "\n")

    print(f"Wrote JSON comparison: {args.output_json}")
    print(f"Wrote markdown report: {args.output_md}")

    has_regression = bool(
        comparison["accuracy_regressions"]
        or comparison["missing_current"]
        or comparison["regressions"]
    )
    if args.fail_on_regression and has_regression:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
