#!/usr/bin/env python3
"""Export and optionally compare HAPI materialized DQM patient results."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from fhir4ds.dqm.config import DQMConfigError
from fhir4ds.dqm.hapi_materialization import load_materialization_config, require_psycopg


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Export active HAPI materialized DQM results and compare to a baseline."
    )
    parser.add_argument("--config", help="HAPI materialization config")
    parser.add_argument("--connection", help="PostgreSQL connection string")
    parser.add_argument("--output", help="Output file; defaults to stdout")
    parser.add_argument("--format", choices=["json", "csv"], default="json")
    parser.add_argument("--expected", help="Expected CSV/JSON patient-level baseline")
    parser.add_argument(
        "--key",
        action="append",
        help="Comparison key field; repeatable. Defaults to measure_id and patient_id.",
    )
    parser.add_argument(
        "--compare-field",
        action="append",
        help="Field to compare; repeatable. Defaults to fields present in expected rows.",
    )
    parser.add_argument("--measure", action="append", help="Measure id filter")
    parser.add_argument("--patient-id", action="append", help="Patient id filter")
    parser.add_argument("--include-inactive", action="store_true")
    parser.add_argument("--limit", type=int, help="Maximum materialized result rows to read")
    args = parser.parse_args(argv)

    try:
        connection_string = _connection_string(args)
        records = export_records(
            connection_string,
            measures=args.measure,
            patient_ids=args.patient_id,
            include_inactive=args.include_inactive,
            limit=args.limit,
        )
        comparison = None
        if args.expected:
            expected = read_records(Path(args.expected))
            comparison = compare_records(
                records,
                expected,
                key_fields=args.key or ["measure_id", "patient_id"],
                compare_fields=args.compare_field,
            )

        if args.format == "csv":
            write_csv(records, Path(args.output) if args.output else None)
        else:
            payload: dict[str, Any] = {
                "record_count": len(records),
                "records": records,
            }
            if comparison is not None:
                payload["comparison"] = comparison
            write_json(payload, Path(args.output) if args.output else None)

        if comparison is not None and comparison["delta_count"] > 0:
            print(
                f"Comparison found {comparison['delta_count']} delta(s)",
                file=sys.stderr,
            )
            return 1
        return 0
    except (DQMConfigError, FileNotFoundError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


def _connection_string(args: argparse.Namespace) -> str:
    if args.connection:
        return args.connection
    if args.config:
        return load_materialization_config(args.config).postgres_connection_string
    raise DQMConfigError("--config or --connection is required")


def export_records(
    connection_string: str,
    *,
    measures: list[str] | None = None,
    patient_ids: list[str] | None = None,
    include_inactive: bool = False,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    if limit is not None and limit <= 0:
        raise DQMConfigError("--limit must be positive")

    conditions: list[str] = []
    params: list[Any] = []
    if not include_inactive:
        conditions.append("active = true")
    if measures:
        conditions.append("measure_id = ANY(%s::text[])")
        params.append(sorted(set(measures)))
    if patient_ids:
        conditions.append("patient_id = ANY(%s::text[])")
        params.append(sorted(set(patient_ids)))

    where_sql = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    limit_sql = ""
    if limit is not None:
        limit_sql = "LIMIT %s"
        params.append(limit)

    psycopg = require_psycopg()
    with psycopg.connect(connection_string) as conn:
        rows = conn.execute(
            f"""
            SELECT
                result_id,
                run_id,
                patient_id,
                measure_id,
                measure_version,
                calculated_at,
                active,
                status,
                result_json,
                error
            FROM fhir4ds_measure_result
            {where_sql}
            ORDER BY measure_id, patient_id, active DESC, calculated_at DESC, result_id
            {limit_sql}
            """,
            params,
        ).fetchall()

    records: list[dict[str, Any]] = []
    for row in rows:
        base = {
            "result_id": row[0],
            "run_id": row[1],
            "patient_id": row[2],
            "measure_id": row[3],
            "measure_version": row[4],
            "calculated_at": _jsonable(row[5]),
            "active": bool(row[6]),
            "status": row[7],
            "error": row[9],
        }
        result_json = _json_object(row[8])
        result_rows = result_json.get("rows") if isinstance(result_json, dict) else None
        if not result_rows:
            records.append({**base, "row_index": 0})
            continue
        for index, result_row in enumerate(result_rows):
            flattened = _json_object(result_row)
            if not isinstance(flattened, dict):
                flattened = {"value": flattened}
            records.append({**flattened, **base, "row_index": index})
    return records


def read_records(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(path)
    if path.suffix.lower() == ".json":
        payload = json.loads(path.read_text())
        if isinstance(payload, dict):
            payload = payload.get("records", [])
        if not isinstance(payload, list):
            raise DQMConfigError("Expected JSON baseline to be a list or object with records")
        return [_json_object(item) for item in payload]
    with path.open(newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def compare_records(
    actual: list[dict[str, Any]],
    expected: list[dict[str, Any]],
    *,
    key_fields: list[str],
    compare_fields: list[str] | None = None,
) -> dict[str, Any]:
    if not key_fields:
        raise DQMConfigError("At least one comparison key is required")
    fields = compare_fields or sorted(
        {
            field
            for row in expected
            for field in row
            if field not in set(key_fields)
        }
    )
    actual_index, actual_duplicates = _index_records(actual, key_fields)
    expected_index, expected_duplicates = _index_records(expected, key_fields)

    deltas: list[dict[str, Any]] = []
    for key, rows in actual_duplicates.items():
        deltas.append({"type": "duplicate_actual", "key": list(key), "count": len(rows)})
    for key, rows in expected_duplicates.items():
        deltas.append({"type": "duplicate_expected", "key": list(key), "count": len(rows)})

    for key, expected_row in sorted(expected_index.items()):
        actual_row = actual_index.get(key)
        if actual_row is None:
            deltas.append({"type": "missing_actual", "key": list(key)})
            continue
        for field in fields:
            expected_value = _normalize(expected_row.get(field))
            actual_value = _normalize(actual_row.get(field))
            if actual_value != expected_value:
                deltas.append(
                    {
                        "type": "mismatch",
                        "key": list(key),
                        "field": field,
                        "expected": expected_value,
                        "actual": actual_value,
                    }
                )

    for key in sorted(set(actual_index) - set(expected_index)):
        deltas.append({"type": "unexpected_actual", "key": list(key)})

    return {
        "actual_count": len(actual),
        "expected_count": len(expected),
        "key_fields": key_fields,
        "compare_fields": fields,
        "delta_count": len(deltas),
        "deltas": deltas,
    }


def write_json(payload: dict[str, Any], output: Path | None) -> None:
    text = json.dumps(payload, indent=2, default=str)
    if output is None:
        print(text)
    else:
        output.write_text(text + "\n")


def write_csv(records: list[dict[str, Any]], output: Path | None) -> None:
    fields = sorted({field for record in records for field in record})
    handle = output.open("w", newline="") if output is not None else sys.stdout
    close_handle = output is not None
    try:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(records)
    finally:
        if close_handle:
            handle.close()


def _index_records(
    records: list[dict[str, Any]],
    key_fields: list[str],
) -> tuple[dict[tuple[str, ...], dict[str, Any]], dict[tuple[str, ...], list[dict[str, Any]]]]:
    index: dict[tuple[str, ...], dict[str, Any]] = {}
    duplicates: dict[tuple[str, ...], list[dict[str, Any]]] = {}
    for row in records:
        key = tuple(str(_normalize(row.get(field))) for field in key_fields)
        if key in index:
            duplicates.setdefault(key, [index[key]]).append(row)
            continue
        index[key] = row
    return index, duplicates


def _json_object(value: Any) -> Any:
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value
    return value


def _normalize(value: Any) -> Any:
    if isinstance(value, str):
        stripped = value.strip()
        lowered = stripped.lower()
        if lowered in {"true", "t", "1"}:
            return True
        if lowered in {"false", "f", "0"}:
            return False
        if lowered in {"", "null", "none"}:
            return None
        return stripped
    return _jsonable(value)


def _jsonable(value: Any) -> Any:
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    return value


if __name__ == "__main__":
    raise SystemExit(main())
