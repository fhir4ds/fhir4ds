"""`fhir4ds verify` command-line implementation (adapter).

argv -> dataclasses -> fhir4ds.operations -> envelope -> stdout JSON.
Exit codes: 0 all cases pass; 1 failing cases or run validation errors;
2 invalid CLI input. stdout is the contract under --format json.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from fhir4ds.operations import (
    DatasetSpec,
    LibraryText,
    TestsInput,
    evaluate_library,
    run_tests,
    tests_input_from_dict,
)
from fhir4ds.operations.errors import diagnostic_from_exception


def configure_parser(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--library", required=True, help="Path to the main .cql library")
    parser.add_argument(
        "--include-dir", action="append", default=None,
        help="Directory containing included libraries (repeatable)",
    )
    parser.add_argument(
        "--data", action="append", default=None,
        help="Dataset: NDJSON file, Bundle .json file, or directory (repeatable)",
    )
    parser.add_argument(
        "--valueset", action="append", default=None,
        help="ValueSet JSON file (repeatable)",
    )
    parser.add_argument("--tests", default=None, help="Path to declarative cases JSON")
    parser.add_argument("--parameters", default=None, help="JSON object of parameter values")
    parser.add_argument(
        "--output-columns", default=None,
        help='JSON object {"COLUMN": "CQL define name"}',
    )
    parser.add_argument("--emit-sql", action="store_true", help="Include generated SQL in output")
    parser.add_argument(
        "--evidence", default=None,
        help="Write the evaluation's per-patient evidence JSON artifact to "
        "this path for later --baseline comparison",
    )
    parser.add_argument(
        "--baseline", default=None,
        help="Path to a prior evidence JSON artifact; when set, the command "
        "emits a compare_evidence delta envelope instead of a plain result",
    )
    parser.add_argument("--format", choices=["json", "text"], default="json")
    parser.add_argument("--timeout-seconds", type=float, default=120.0)


def _load_include_libraries(include_dirs: list[str]) -> list[LibraryText]:
    libs: list[LibraryText] = []
    for directory in include_dirs or []:
        for path in sorted(Path(directory).glob("*.cql")):
            libs.append(LibraryText(name=path.stem, text=path.read_text(encoding="utf-8")))
    return libs


def _dataset_from_args(data: list[str] | None, valuesets: list[str] | None) -> DatasetSpec:
    ndjson_paths: list[str] = []
    bundle_paths: list[str] = []
    for entry in data or []:
        p = Path(entry)
        if p.is_dir():
            ndjson_paths.extend(sorted(str(f) for f in p.glob("*.ndjson")))
        elif entry.endswith(".ndjson"):
            ndjson_paths.append(entry)
        else:
            bundle_paths.append(entry)
    return DatasetSpec(
        ndjson_paths=ndjson_paths or None,
        bundle_paths=bundle_paths or None,
        valueset_paths=valuesets or None,
    )


def _parse_json_arg(raw: str | None, name: str) -> dict[str, Any] | None:
    if raw is None:
        return None
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"--{name} is not valid JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"--{name} must be a JSON object")
    return value


def run(args: argparse.Namespace) -> int:
    if not (args.timeout_seconds > 0):
        print("ERROR: --timeout-seconds must be positive", file=sys.stderr)
        return 2
    library_path = Path(args.library)
    if not library_path.exists():
        print(f"ERROR: library not found: {args.library}", file=sys.stderr)
        return 2
    try:
        main = LibraryText(
            name=library_path.stem,
            text=library_path.read_text(encoding="utf-8"),
        )
        libraries = [main, *_load_include_libraries(args.include_dir)]
        dataset = _dataset_from_args(args.data, args.valueset)
        parameters = _parse_json_arg(args.parameters, "parameters")
        output_columns = _parse_json_arg(args.output_columns, "output-columns")
        cases: TestsInput | None = None
        if args.tests:
            raw = json.loads(Path(args.tests).read_text(encoding="utf-8"))
            cases = tests_input_from_dict(raw)
    except (ValueError, TypeError, FileNotFoundError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    from fhir4ds import create_connection

    conn = create_connection()

    try:
        if cases is not None:
            envelope = run_tests(
                libraries, main, dataset, cases, conn,
                parameters=parameters, output_columns=output_columns,
            )
        else:
            envelope = evaluate_library(
                libraries, main, dataset, conn,
                parameters=parameters, output_columns=output_columns,
                emit_sql=args.emit_sql,
            )
    except Exception as exc:  # adapter boundary: never a traceback
        diag = diagnostic_from_exception(exc, context="verify")
        print(
            json.dumps(
                {"schema": 1, "ok": False, "passed": None,
                 "diagnostics": [diag.to_dict()]},
                indent=2,
            )
        )
        return 1

    payload = envelope.to_dict()
    payload["library"] = str(args.library)
    payload["timeout_seconds"] = args.timeout_seconds
    if "summary" not in payload and "rows" in payload:
        # Derive a population summary from evaluation rows (parity with run_tests).
        payload["summary"] = {
            col: sum(1 for row in payload["rows"] if row.get(col) is True)
            for col in payload.get("columns", [])
            if col != "patient_id"
        }
    if args.evidence:
        evidence_artifact = _evidence_artifact(libraries, main, dataset, conn, args)
        if isinstance(evidence_artifact, int):
            return evidence_artifact
        Path(args.evidence).write_text(
            json.dumps(evidence_artifact, indent=2), encoding="utf-8"
        )
    if args.baseline:
        baseline_payload = _load_evidence_file(args.baseline)
        if isinstance(baseline_payload, int):
            return baseline_payload
        current_payload = _evidence_artifact(libraries, main, dataset, conn, args)
        if isinstance(current_payload, int):
            return current_payload
        from fhir4ds.operations import compare_evidence

        delta = compare_evidence(baseline_payload, current_payload)
        delta_payload = delta.to_dict()
        delta_payload["library"] = str(args.library)
        if args.format == "json":
            print(json.dumps(delta_payload, indent=2))
        else:
            for entry in delta_payload["patients"]:
                print(
                    f"  {entry['patient_id']}: {entry['column']} "
                    f"{entry['classification']} ({entry['from']} -> {entry['to']})"
                )
        return 0 if delta.ok else 1
    if args.format == "json":
        print(json.dumps(payload, indent=2))
    else:
        _print_text(payload)
    if not envelope.ok:
        return 1
    if envelope.passed is False:
        return 1
    return 0


def _evidence_artifact(
    libraries: list[LibraryText],
    main: LibraryText,
    dataset: DatasetSpec,
    conn: Any,
    args: argparse.Namespace,
) -> dict[str, Any] | int:
    """Multi-patient evidence artifact from the current evaluation.

    Runs explain per patient (audit_mode='full' equivalent via the
    operations capability). Returns the payload dict or a process exit
    code on failure.
    """
    from fhir4ds.operations import evaluate_library, explain_patient

    output_columns = _parse_json_arg(args.output_columns, "output-columns")
    ev = evaluate_library(
        libraries, main, dataset, conn, output_columns=output_columns
    )
    if not ev.ok:
        print(
            json.dumps(ev.to_dict(), indent=2),
        )
        return 1
    patients_map: dict[str, dict[str, Any]] = {}
    for row in ev.rows:
        pid = row.get("patient_id")
        if not isinstance(pid, str):
            continue
        populations = {
            col: bool(val) if val is not None else None
            for col, val in row.items()
            if col != "patient_id" and isinstance(val, (bool, type(None)))
        }
        patients_map[pid] = {"populations": populations}
    return {"schema": 1, "ok": True, "patients": patients_map}


def _load_evidence_file(path_str: str) -> dict[str, Any] | int:
    path = Path(path_str)
    if not path.exists():
        print(f"ERROR: baseline evidence not found: {path_str}", file=sys.stderr)
        return 2
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(f"ERROR: baseline evidence is not valid JSON: {exc}", file=sys.stderr)
        return 2
    if not isinstance(payload, dict):
        print("ERROR: baseline evidence must be a JSON object", file=sys.stderr)
        return 2
    return payload


def _print_text(payload: dict[str, Any]) -> None:
    status = "PASS" if payload.get("passed") else ("OK" if payload.get("ok") else "FAIL")
    print(f"[{status}] library: {payload.get('library', '')}")
    for col, count in (payload.get("summary") or {}).items():
        print(f"  {col}: {count}")
    tests = payload.get("tests")
    if tests:
        print(f"  tests: {tests.get('passed')}/{tests.get('total')} passed")
        for failure in tests.get("failures", []):
            reason = failure.get("reason") or "assertion mismatch"
            print(
                f"    FAIL {failure.get('patient')} {failure.get('target')}: "
                f"expected {failure.get('expected')}, got {failure.get('actual')} ({reason})"
            )
    for diag in payload.get("diagnostics", []):
        print(f"  diagnostic [{diag.get('code')}]: {diag.get('message')}")
