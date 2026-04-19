"""Compare baseline vs audit benchmark results and generate a performance report.

Usage:
    python -m benchmarking.runner.audit_perf_compare \
        --baseline benchmarking/output/baseline-2025 \
        --audit benchmarking/output/audit-2025 \
        --output benchmarking/output/audit-performance-report.md
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path


def load_summary(directory: Path) -> dict:
    """Load the all_measures_summary.json from a benchmark output directory."""
    path = directory / "all_measures_summary.json"
    if not path.exists():
        sys.exit(f"ERROR: Summary not found: {path}")
    with open(path) as f:
        return json.load(f)


def load_stats(directory: Path) -> dict[str, dict]:
    """Load per-measure stats JSONs keyed by measure ID."""
    stats_dir = directory / "stats"
    result = {}
    if stats_dir.exists():
        for p in sorted(stats_dir.glob("*.json")):
            with open(p) as f:
                data = json.load(f)
            result[data.get("measure_id", p.stem)] = data
    return result


def compute_comparison(
    baseline_summary: dict,
    audit_summary: dict,
    baseline_stats: dict[str, dict],
    audit_stats: dict[str, dict],
) -> dict:
    """Compute per-measure and aggregate comparison metrics."""
    measures = []
    overhead_ratios = []
    accuracy_regressions = []
    new_failures = []

    baseline_by_id = {m["id"]: m for m in baseline_summary["measures"]}
    audit_by_id = {m["id"]: m for m in audit_summary["measures"]}

    all_ids = sorted(set(baseline_by_id) | set(audit_by_id))

    for mid in all_ids:
        b = baseline_by_id.get(mid)
        a = audit_by_id.get(mid)

        if not b or not a:
            measures.append({
                "id": mid,
                "status": "missing",
                "note": f"{'audit' if not a else 'baseline'} missing",
            })
            if b and not a:
                new_failures.append(mid)
            continue

        b_stats = baseline_stats.get(mid, {})
        a_stats = audit_stats.get(mid, {})

        b_timings = b_stats.get("timings_ms", {})
        a_timings = a_stats.get("timings_ms", {})

        b_total = b.get("total_ms", b_timings.get("total_ms", 0))
        a_total = a.get("total_ms", a_timings.get("total_ms", 0))

        ratio = a_total / b_total if b_total > 0 else None

        b_acc = b.get("accuracy_pct", 0)
        a_acc = a.get("accuracy_pct", 0)

        entry = {
            "id": mid,
            "baseline_accuracy": b_acc,
            "audit_accuracy": a_acc,
            "accuracy_diff": a_acc - b_acc,
            "baseline_total_ms": round(b_total, 1),
            "audit_total_ms": round(a_total, 1),
            "overhead_ratio": round(ratio, 2) if ratio else None,
            "parse_overhead_ms": round(
                a_timings.get("cql_parse_ms", 0) - b_timings.get("cql_parse_ms", 0), 1
            ),
            "translation_overhead_ms": round(
                a_timings.get("sql_generation_ms", 0) - b_timings.get("sql_generation_ms", 0), 1
            ),
            "execution_overhead_ms": round(
                a_timings.get("sql_execution_ms", 0) - b_timings.get("sql_execution_ms", 0), 1
            ),
        }
        measures.append(entry)

        if ratio:
            overhead_ratios.append(ratio)

        if a_acc < b_acc:
            accuracy_regressions.append(mid)

        if a.get("status") != "success" and b.get("status") == "success":
            new_failures.append(mid)

    agg = {}
    if overhead_ratios:
        agg = {
            "mean": round(statistics.mean(overhead_ratios), 2),
            "median": round(statistics.median(overhead_ratios), 2),
            "p95": round(sorted(overhead_ratios)[int(len(overhead_ratios) * 0.95)], 2),
            "max": round(max(overhead_ratios), 2),
            "min": round(min(overhead_ratios), 2),
        }

    return {
        "measures": measures,
        "aggregate": agg,
        "accuracy_regressions": accuracy_regressions,
        "new_failures": new_failures,
    }


def generate_report(comparison: dict, suite_label: str) -> str:
    """Generate a markdown performance report."""
    lines = [
        f"# Audit Performance Report — {suite_label}",
        "",
        "## Summary",
        "",
    ]

    agg = comparison["aggregate"]
    if agg:
        lines += [
            f"| Metric | Value |",
            f"|--------|-------|",
            f"| Mean overhead ratio | {agg['mean']}x |",
            f"| Median overhead ratio | {agg['median']}x |",
            f"| P95 overhead ratio | {agg['p95']}x |",
            f"| Max overhead ratio | {agg['max']}x |",
            f"| Min overhead ratio | {agg['min']}x |",
            "",
        ]

    regs = comparison["accuracy_regressions"]
    fails = comparison["new_failures"]
    lines.append(f"**Accuracy regressions:** {len(regs)} {'⚠️ ' + ', '.join(regs) if regs else '✅ None'}")
    lines.append(f"**New failures (audit-only):** {len(fails)} {'⚠️ ' + ', '.join(fails) if fails else '✅ None'}")
    lines.append("")

    lines += [
        "## Per-Measure Comparison",
        "",
        "| Measure | Baseline Acc | Audit Acc | Δ Acc | Baseline (ms) | Audit (ms) | Ratio | Parse Δ | Trans Δ | Exec Δ | Flag |",
        "|---------|-------------|-----------|-------|---------------|------------|-------|---------|---------|--------|------|",
    ]

    for m in comparison["measures"]:
        if m.get("status") == "missing":
            lines.append(f"| {m['id']} | — | — | — | — | — | — | — | — | — | {m['note']} |")
            continue

        flag = ""
        if m["accuracy_diff"] < 0:
            flag = "🔴 REGRESSION"
        elif m.get("overhead_ratio") and m["overhead_ratio"] > 5:
            flag = "⚠️ SLOW"

        lines.append(
            f"| {m['id']} "
            f"| {m['baseline_accuracy']:.1f}% "
            f"| {m['audit_accuracy']:.1f}% "
            f"| {m['accuracy_diff']:+.1f}% "
            f"| {m['baseline_total_ms']:,.0f} "
            f"| {m['audit_total_ms']:,.0f} "
            f"| {m['overhead_ratio']}x "
            f"| {m['parse_overhead_ms']:+.0f} "
            f"| {m['translation_overhead_ms']:+.0f} "
            f"| {m['execution_overhead_ms']:+.0f} "
            f"| {flag} |"
        )

    lines += [
        "",
        "## Flagged Measures",
        "",
    ]

    flagged = [m for m in comparison["measures"] if m.get("overhead_ratio") and m["overhead_ratio"] > 5]
    if flagged:
        for m in sorted(flagged, key=lambda x: x["overhead_ratio"], reverse=True):
            lines.append(f"- **{m['id']}**: {m['overhead_ratio']}x overhead ({m['baseline_total_ms']:,.0f}ms → {m['audit_total_ms']:,.0f}ms)")
    else:
        lines.append("No measures exceed 5x overhead threshold.")

    lines.append("")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Compare baseline vs audit benchmark results")
    parser.add_argument("--baseline", type=Path, required=True, help="Baseline output directory")
    parser.add_argument("--audit", type=Path, required=True, help="Audit output directory")
    parser.add_argument("--output", "-o", type=Path, default=None, help="Output markdown report path")
    parser.add_argument("--suite", default="2025", help="Suite label for report header")
    parser.add_argument("--csv", type=Path, default=None, help="Optional CSV output path")
    args = parser.parse_args()

    baseline_summary = load_summary(args.baseline)
    audit_summary = load_summary(args.audit)
    baseline_stats = load_stats(args.baseline)
    audit_stats = load_stats(args.audit)

    comparison = compute_comparison(baseline_summary, audit_summary, baseline_stats, audit_stats)
    report = generate_report(comparison, f"Suite {args.suite}")

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(report)
        print(f"Report written to: {args.output}")
    else:
        print(report)

    if args.csv:
        import csv
        args.csv.parent.mkdir(parents=True, exist_ok=True)
        with open(args.csv, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=[
                "id", "baseline_accuracy", "audit_accuracy", "accuracy_diff",
                "baseline_total_ms", "audit_total_ms", "overhead_ratio",
                "parse_overhead_ms", "translation_overhead_ms", "execution_overhead_ms",
            ])
            writer.writeheader()
            for m in comparison["measures"]:
                if m.get("status") != "missing":
                    writer.writerow(m)
        print(f"CSV written to: {args.csv}")

    # Exit with error if regressions found
    if comparison["accuracy_regressions"] or comparison["new_failures"]:
        print(f"\n⚠️  BLOCKERS: {len(comparison['accuracy_regressions'])} accuracy regressions, "
              f"{len(comparison['new_failures'])} new failures")
        sys.exit(1)

    print("\n✅ No regressions detected.")


if __name__ == "__main__":
    main()
