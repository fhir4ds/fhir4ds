"""Repeat-compare (FHIR4-110): run N measures twice on one tree and diff the cells.

A long run that only compares against an expectation cannot notice a value that moved with
no code change. This helper runs the conformance CLI several times, each in a fresh process,
and compares the content digests the CLI records:

- ``same``     the two runs produced the same cells;
- ``order``    same cells, another order (a list came back permuted) — an ordering
               nondeterminism, not a value change;
- ``content``  a cell's value or count moved — a fault instance or a wrong-answer bug;
- ``missing``  a measure produced no digest in one of the runs (it errored).

With ``--cell-digests`` a moved measure is diffed cell by cell through the Tier C comparator
(``tier_c.compare``), which names the columns and an example. There is no retry anywhere: a
run that fails or moves is reported, never repeated quietly.

    python -m fhir4ds.dqm.tests.conformance.repeat_compare --suite us-core-2025 \\
        --measures CMS139 CMS986 --runs 2 --attempts 3 --cell-digests
    python -m fhir4ds.dqm.tests.conformance.repeat_compare --compare run1 run2

Exit status: 0 when every pair is ``same``, 1 when anything moved, 2 when a run failed.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from .content_digest import compare_records, load_record

DIGEST_FILE = "content_digests.json"
CRASH_MARKERS = ("Fatal Python error", "Segmentation fault", "Segmentation Fault")

#: Signs that the process died rather than answered. A dead run is never "no movement".
CRASH_EXIT_CODES = {134, 139}  # SIGABRT, SIGSEGV


def run_once(
    tree: Path,
    suite: str,
    measures: list[str],
    output_dir: Path,
    *,
    cell_digests: bool = False,
    timeout_s: int = 3600,
) -> dict[str, Any]:
    """One fresh CLI process. Returns what it did; never raises for a failing run."""
    command = [
        sys.executable,
        "-m",
        "fhir4ds.dqm.tests.conformance.cli",
        "--suite",
        suite,
        "--measure",
        ",".join(measures),
        "--skip-errors",
        "--output",
        str(output_dir),
    ]
    if cell_digests:
        command.append("--cell-digests")
    environment = dict(os.environ)
    # The same hash seed on both sides: a seed-dependent ordering is not what this measures.
    environment["PYTHONHASHSEED"] = "0"

    output_dir.mkdir(parents=True, exist_ok=True)
    log_path = output_dir / "run.log"
    timed_out = False
    with open(log_path, "w") as log:
        try:
            completed = subprocess.run(
                command, cwd=tree, env=environment, stdout=log, stderr=subprocess.STDOUT,
                timeout=timeout_s, check=False,
            )
            returncode: int | None = completed.returncode
        except subprocess.TimeoutExpired:
            returncode, timed_out = None, True

    text = log_path.read_text(errors="replace")
    markers = [marker for marker in CRASH_MARKERS if marker in text]
    record, record_error = None, None
    try:
        record = load_record(output_dir / DIGEST_FILE)
    except ValueError as error:
        record_error = str(error)
    return {
        "returncode": returncode,
        "timed_out": timed_out,
        "crashed": returncode in CRASH_EXIT_CODES or bool(markers),
        "markers": markers,
        "record": record,
        "record_error": record_error,
        "log": log_path,
    }


def _cells(output_dir: Path, measure_id: str) -> dict[str, Any] | None:
    path = output_dir / "results" / f"{measure_id}.cells.json"
    if not path.is_file():
        return None
    with open(path) as f:
        columns = json.loads(f.readline())["columns"]
        rows = [json.loads(line) for line in f if line.strip()]
    return {"columns": columns, "rows": rows}


def _cell_diff(first: Path, second: Path, measure_id: str, limit: int) -> list[dict[str, Any]]:
    """Per column, what moved, through the Tier C comparator (the one cell comparator)."""
    from fhir4ds.operations.tests.wasm_parity import tier_c

    before, after = _cells(first, measure_id), _cells(second, measure_id)
    if before is None or after is None:
        return []
    diffs, _ = tier_c.compare(before["columns"], before["rows"], after["rows"])
    return [
        {
            "column": name,
            "kind": info["kind"],
            "diff_cells": info["diff_cells"],
            "example": [str(item)[:200] for item in info["example"]],
        }
        for name, info in sorted(diffs.items())[:limit]
    ]


def compare_runs(
    first: Path, second: Path, *, cells: bool = False, cell_limit: int = 20
) -> dict[str, Any]:
    """Compare two run directories (or their digest files). Never raises for movement."""
    def resolve(path: Path) -> Path:
        return path / DIGEST_FILE if path.is_dir() else path

    first_dir, second_dir = (path if path.is_dir() else path.parent for path in (first, second))
    result: dict[str, Any] = {"moved": 0, "failed": False, "problems": [], "measures": {}}
    records = []
    for path in (first, second):
        try:
            records.append(load_record(resolve(path)))
        except ValueError as error:
            result["failed"] = True
            result["problems"].append(str(error))
    if result["failed"]:
        return result

    before, after = records
    if (before["measures"] or {}) and set(before["measures"]) != set(after["measures"] or {}):
        result["failed"] = True
        result["problems"].append(
            f"the runs digest different measures: {sorted(before['measures'])} vs "
            f"{sorted(after['measures'])}"
        )
    comparison = compare_records(before["measures"] or {}, after["measures"] or {})
    result.update(comparison)
    for measure_id, entry in comparison["measures"].items():
        if entry["class"] == "same":
            continue
        detail = dict(entry)
        if cells and entry["class"] in ("order", "content"):
            detail["cells"] = _cell_diff(first_dir, second_dir, measure_id, cell_limit)
        result["measures"][measure_id] = detail
    result["normalised"] = [
        (record["digest"] or {}).get("digest_normalised") for record in records
    ]
    return result


def _format(report: dict[str, Any]) -> str:
    lines = []
    if report["failed"]:
        lines.append("repeat-compare: a run produced no digest")
        lines += [f"  - {problem}" for problem in report["problems"]]
        return "\n".join(lines)
    lines.append(
        f"  normalised digest: run 1 {report['normalised'][0]} | run 2 {report['normalised'][1]}"
    )
    for measure_id, entry in sorted(report["measures"].items()):
        line = f"  {measure_id}: {entry['class']}"
        if entry.get("moved_columns"):
            line += f" (columns: {', '.join(entry['moved_columns'])})"
        lines.append(line)
        for cell in entry.get("cells", []):
            lines.append(
                f"      {cell['column']}: {cell['kind']} in {cell['diff_cells']} cell(s); "
                f"example {cell['example']}"
            )
    counts = report["counts"]
    lines.append(
        f"repeat-compare: {report['moved']} of {report['compared']} measure pair(s) moved "
        f"(order {counts['order']}, content {counts['content']}, missing {counts['missing']})"
    )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--suite", default="us-core-2025", help="Content suite")
    parser.add_argument(
        "--measures", "-m", nargs="+", required=True, help="Measure IDs to run"
    )
    parser.add_argument("--runs", type=int, default=2, help="Runs per attempt (default 2)")
    parser.add_argument(
        "--attempts", type=int, default=1, help="How many run sets to compare (default 1)"
    )
    parser.add_argument(
        "--cell-digests",
        action="store_true",
        help="Also write each run's cells and name the columns that moved",
    )
    parser.add_argument("--tree", type=Path, default=Path.cwd(), help="Tree to measure")
    parser.add_argument("--workdir", type=Path, default=None, help="Keep run outputs here")
    parser.add_argument("--keep", action="store_true", help="Keep the run output directories")
    parser.add_argument("--timeout-s", type=int, default=3600, help="Per-run timeout")
    parser.add_argument(
        "--compare",
        nargs=2,
        type=Path,
        metavar=("FIRST", "SECOND"),
        help="Compare two existing run directories or digest files; run nothing",
    )
    args = parser.parse_args(argv)

    if args.compare:
        report = compare_runs(*args.compare, cells=True)
        print(_format(report))
        return 2 if report["failed"] else (1 if report["moved"] else 0)

    tree = args.tree.resolve()
    root = args.workdir or Path(tempfile.mkdtemp(prefix="repeat-compare-"))
    moved, compared, failed = 0, 0, False
    try:
        for attempt in range(1, args.attempts + 1):
            outputs, runs = [], []
            for run in range(1, args.runs + 1):
                output_dir = root / f"attempt{attempt}-run{run}"
                outputs.append(output_dir)
                runs.append(
                    run_once(
                        tree, args.suite, args.measures, output_dir,
                        cell_digests=args.cell_digests, timeout_s=args.timeout_s,
                    )
                )
            print(f"attempt {attempt} of {args.attempts}:")
            dead = []
            for index, run in enumerate(runs, start=1):
                if run["timed_out"]:
                    dead.append(f"run {index} timed out after {args.timeout_s}s")
                elif run["crashed"]:
                    how = f"exited {run['returncode']}"
                    if run["markers"]:
                        how += f" ({', '.join(run['markers'])})"
                    dead.append(f"run {index} died: {how}")
                elif run["record"] is None:
                    dead.append(
                        f"run {index} exited {run['returncode']} and left no digest "
                        f"({run['record_error']})"
                    )
            if dead:
                failed = True
                print("repeat-compare: a run did not answer")
                for line in dead:
                    print(f"  - {line}")
                for run in runs:
                    print(f"  log: {run['log']}")
                continue
            for other in outputs[1:]:
                report = compare_runs(outputs[0], other, cells=args.cell_digests)
                print(_format(report))
                moved += report["moved"]
                compared += report["compared"]
                failed = failed or report["failed"]
    finally:
        if not args.keep:
            import shutil

            shutil.rmtree(root, ignore_errors=True)
        else:
            print(f"run outputs kept in {root}")

    print(
        f"repeat-compare: {moved} of {compared} measure pair(s) moved over "
        f"{args.attempts} attempt(s) of {args.runs} run(s)"
    )
    return 2 if failed else (1 if moved else 0)


if __name__ == "__main__":
    sys.exit(main())
