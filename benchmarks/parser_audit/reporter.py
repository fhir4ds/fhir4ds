"""
Report formatter: produces JSON (machine-readable) and Markdown (human/git-trackable)
audit reports from scan results and categories.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import List

from .scanner import ParseResult
from .categorizer import ConstructCategory


def build_summary(results: List[ParseResult], categories: List[ConstructCategory]) -> dict:
    """Build a structured summary dict (used for both JSON output and stdout)."""
    total = len(results)
    passed = sum(1 for r in results if r.success)
    failed = total - passed
    libraries_failed = sum(1 for r in results if not r.success and r.is_library)
    measures_failed = failed - libraries_failed

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "totals": {
            "files": total,
            "passed": passed,
            "failed": failed,
            "pass_rate_pct": round(passed / total * 100, 1) if total else 0,
        },
        "by_file_type": {
            "measures_failed": measures_failed,
            "libraries_failed": libraries_failed,
        },
        "construct_categories": [
            {
                "key": c.key,
                "label": c.label,
                "error_type": c.error_type,
                "affected_files": c.count,
                "measure_files": c.measure_count,
                "library_files": c.library_count,
                "files": sorted(c.affected_files),
                "sample_messages": c.sample_messages,
            }
            for c in categories
        ],
        "failed_files": [
            {
                "file": r.file.name,
                "is_library": r.is_library,
                "error_type": r.error_type,
                "message": r.message,
                "position": list(r.position) if r.position else None,
                "found": r.found,
                "expected": r.expected,
                "feature_name": r.feature_name,
            }
            for r in results if not r.success
        ],
        "passed_files": [r.file.name for r in results if r.success],
    }


def write_json(summary: dict, output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "parser_audit.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)
    return path


def write_markdown(summary: dict, output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "parser_audit_report.md"

    t = summary["totals"]
    bf = summary["by_file_type"]
    categories = summary["construct_categories"]
    generated_at = summary["generated_at"]

    lines = [
        "# CQL Parser Audit Report",
        "",
        f"_Generated: {generated_at}_",
        "",
        "## Summary",
        "",
        f"| Metric | Value |",
        f"|--------|-------|",
        f"| Total CQL files | {t['files']} |",
        f"| Parsed successfully | {t['passed']} |",
        f"| Parse failures | {t['failed']} |",
        f"| Pass rate | {t['pass_rate_pct']}% |",
        f"| Measure files failed | {bf['measures_failed']} |",
        f"| Library files failed | {bf['libraries_failed']} |",
        "",
    ]

    if not categories:
        lines += ["## Result", "", "All files parsed successfully. No gaps found.", ""]
    else:
        lines += [
            "## Parser Gaps by Construct (ranked by impact)",
            "",
            "| Rank | Construct | Files Affected | Measures | Libraries | Error Type |",
            "|------|-----------|---------------|----------|-----------|------------|",
        ]
        for i, c in enumerate(categories, 1):
            lines.append(
                f"| {i} | `{c['key']}` | {c['affected_files']} "
                f"| {c['measure_files']} | {c['library_files']} | {c['error_type']} |"
            )

        lines += [""]

        for i, c in enumerate(categories, 1):
            lines += [
                f"### {i}. {c['label']}",
                "",
                f"- **Key:** `{c['key']}`",
                f"- **Error type:** {c['error_type']}",
                f"- **Files affected ({c['affected_files']}):** "
                + ", ".join(f"`{f}`" for f in c["files"]),
                "",
            ]
            if c["sample_messages"]:
                lines.append("**Sample error messages:**")
                lines.append("```")
                for msg in c["sample_messages"]:
                    lines.append(msg)
                lines.append("```")
                lines.append("")

    # Failed files detail
    failed = summary["failed_files"]
    if failed:
        lines += [
            "## All Failed Files",
            "",
            "| File | Type | Error | Location |",
            "|------|------|-------|----------|",
        ]
        for f in sorted(failed, key=lambda x: x["file"]):
            loc = f"line {f['position'][0]}" if f.get("position") else "—"
            msg = (f["message"] or "")[:60].replace("|", "\\|")
            ftype = "library" if f["is_library"] else "measure"
            lines.append(f"| `{f['file']}` | {ftype} | {msg} | {loc} |")
        lines.append("")

    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    return path


def print_summary(summary: dict) -> None:
    """Print a concise summary to stdout."""
    t = summary["totals"]
    bf = summary["by_file_type"]
    categories = summary["construct_categories"]

    print(f"\n{'='*60}")
    print("CQL PARSER AUDIT RESULTS")
    print(f"{'='*60}")
    print(f"Files scanned : {t['files']}")
    print(f"Passed        : {t['passed']}  ({t['pass_rate_pct']}%)")
    print(f"Failed        : {t['failed']}")
    if t["failed"]:
        print(f"  Measures    : {bf['measures_failed']}")
        print(f"  Libraries   : {bf['libraries_failed']}")

    if categories:
        print(f"\nTop parser gaps (by files affected):")
        for i, c in enumerate(categories[:10], 1):
            print(f"  {i:>2}. {c['label']:<45} {c['affected_files']:>3} file(s)")
        if len(categories) > 10:
            print(f"      ... and {len(categories) - 10} more construct(s)")
    else:
        print("\nNo parser gaps found!")
    print()
