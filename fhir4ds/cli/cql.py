"""CLI for CQL translation and evaluation aligned with the WASM demo surface.

``fhir4ds cql translate``  — CQL → SQL (the CQLEditor/SQLOutput capability).
``fhir4ds cql evaluate``   — evaluate a library against a dataset
                             (the CQLEditor Run capability; ``verify``
                             remains the battery command with tests,
                             evidence, and baselines).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from fhir4ds.operations.envelopes import LibraryText


def configure_parser(parser: argparse.ArgumentParser) -> None:
    sub = parser.add_subparsers(dest="cql_command")

    translate = sub.add_parser(
        "translate", help="Translate CQL to SQL (no execution)"
    )
    translate.add_argument("library", help="Path to the main .cql library")
    translate.add_argument(
        "--include-dir", action="append", default=None,
        help="Directory containing included libraries (repeatable)",
    )
    translate.add_argument(
        "--audit", action="store_true",
        help="Use population SQL shape (one row per patient, plain boolean "
        "columns) instead of the one-row CTE shape the SQL viewer shows",
    )
    translate.add_argument(
        "--parameters", default=None, help="JSON object of parameter values"
    )
    translate.add_argument(
        "--output-columns", default=None,
        help='JSON object {"COLUMN": "CQL define name"} (population mode)',
    )
    translate.add_argument(
        "--sql-out", default=None,
        help="Write the generated SQL to this path instead of stdout",
    )

    evaluate = sub.add_parser(
        "evaluate", help="Evaluate a CQL library against a dataset"
    )
    evaluate.add_argument("library", help="Path to the main .cql library")
    evaluate.add_argument(
        "--include-dir", action="append", default=None,
        help="Directory containing included libraries (repeatable)",
    )
    evaluate.add_argument(
        "--data", action="append", default=None,
        help="Dataset: NDJSON file, Bundle .json file, or directory (repeatable)",
    )
    evaluate.add_argument(
        "--valueset", action="append", default=None,
        help="ValueSet JSON file (repeatable)",
    )
    evaluate.add_argument(
        "--parameters", default=None, help="JSON object of parameter values"
    )
    evaluate.add_argument(
        "--output-columns", default=None,
        help='JSON object {"COLUMN": "CQL define name"}',
    )
    evaluate.add_argument(
        "--emit-sql", action="store_true", help="Include generated SQL in output"
    )


def _load_library(path: str) -> LibraryText:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"library not found: {path}")
    return LibraryText(name=p.stem, text=p.read_text(encoding="utf-8"))


def _load_includes(include_dirs: list[str] | None) -> list[LibraryText]:
    libs: list[LibraryText] = []
    for directory in include_dirs or []:
        for path in sorted(Path(directory).glob("*.cql")):
            libs.append(
                LibraryText(name=path.stem, text=path.read_text(encoding="utf-8"))
            )
    return libs


def _json_arg(raw: str | None, label: str) -> dict | None:
    if raw is None:
        return None
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError(f"--{label} must be a JSON object")
    return value


def _translate(args: argparse.Namespace) -> int:
    from fhir4ds.operations import translate_cql

    try:
        main = _load_library(args.library)
        libraries = [main, *_load_includes(args.include_dir)]
        parameters = _json_arg(args.parameters, "parameters")
        output_columns = _json_arg(args.output_columns, "output-columns")
    except (ValueError, TypeError, FileNotFoundError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    result = translate_cql(
        libraries,
        main,
        audit_mode="population" if args.audit else "none",
        parameters=parameters,
        output_columns=output_columns,
    )
    payload = result.to_dict()
    payload["library"] = str(args.library)
    if not result.ok:
        print(json.dumps(payload, indent=2))
        return 1
    if args.sql_out:
        Path(args.sql_out).write_text(result.sql, encoding="utf-8")
        payload["sql_path"] = str(args.sql_out)
        payload.pop("sql", None)
        print(json.dumps(payload, indent=2))
    else:
        print(json.dumps(payload, indent=2))
    return 0


def _evaluate(args: argparse.Namespace) -> int:
    from fhir4ds import create_connection
    from fhir4ds.operations import evaluate_library

    try:
        main = _load_library(args.library)
        libraries = [main, *_load_includes(args.include_dir)]
        parameters = _json_arg(args.parameters, "parameters")
        output_columns = _json_arg(args.output_columns, "output-columns")
        dataset = _dataset_from_args(args.data, args.valueset)
    except (ValueError, TypeError, FileNotFoundError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    conn = create_connection()
    try:
        result = evaluate_library(
            libraries, main, dataset, conn,
            parameters=parameters, output_columns=output_columns,
            emit_sql=args.emit_sql,
        )
    except Exception as exc:  # adapter boundary: never a traceback
        from fhir4ds.operations import diagnostic_from_exception

        diag = diagnostic_from_exception(exc, context="cql evaluate")
        print(
            json.dumps(
                {"schema": 1, "ok": False, "passed": None,
                 "diagnostics": [diag.to_dict()]},
                indent=2,
            )
        )
        return 1
    finally:
        conn.close()

    payload = result.to_dict()
    payload["library"] = str(args.library)
    print(json.dumps(payload, indent=2))
    return 0 if result.ok else 1


def _dataset_from_args(
    data: list[str] | None, valuesets: list[str] | None
):
    if not data and not valuesets:
        return None
    from fhir4ds.operations import dataset_spec_from_dict

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
    spec: dict = {}
    if ndjson_paths:
        spec["ndjson_paths"] = ndjson_paths
    if bundle_paths:
        spec["bundle_paths"] = bundle_paths
    if valuesets:
        spec["valueset_paths"] = list(valuesets)
    return dataset_spec_from_dict(spec)


def run(args: argparse.Namespace) -> int:
    if args.cql_command == "translate":
        return _translate(args)
    if args.cql_command == "evaluate":
        return _evaluate(args)
    print("ERROR: fhir4ds cql requires a subcommand: translate or evaluate", file=sys.stderr)
    return 2
