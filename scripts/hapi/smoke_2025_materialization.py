#!/usr/bin/env python3
"""Run a local HAPI PostgreSQL materialization smoke test with 2025 eCQM data."""

from __future__ import annotations

import argparse
import copy
import json
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from fhir4ds.dqm.hapi_materialization import (
    DEFAULT_DECODED_VIEW,
    HapiMaterializationConfig,
    HapiMaterializationRuntime,
    HapiMaterializedMeasure,
    install_materialization_schema,
    process_queue_once,
    sync_measure_config,
)
from fhir4ds.dqm.tests.conformance.cli import _discover_measures
from fhir4ds.dqm.tests.conformance.loader import load_test_suite
from fhir4ds.dqm.types import AuditMode
from fhir4ds.sources import HapiPostgresSchema


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--measure",
        action="append",
        default=None,
        help=(
            "Measure ID(s) to smoke. May be repeated or comma-separated. "
            "Defaults to CMS122."
        ),
    )
    parser.add_argument("--suite", choices=["2025", "2026"], default="2025")
    parser.add_argument("--limit-patients", type=int, default=1)
    parser.add_argument("--base-url", default="http://localhost:18080/fhir")
    parser.add_argument(
        "--connection",
        default="postgresql://hapi:hapi@localhost:15432/hapi",
        help="PostgreSQL connection string for the local HAPI database",
    )
    parser.add_argument(
        "--compose-file",
        type=Path,
        default=Path("docker/hapi-postgres/docker-compose.yml"),
    )
    parser.add_argument(
        "--skip-compose",
        action="store_true",
        help="Do not start docker compose services before the smoke run",
    )
    parser.add_argument("--timeout", type=float, default=180.0)
    parser.add_argument("--batch-size", type=int, default=25)
    parser.add_argument(
        "--max-process-loops",
        type=int,
        default=10,
        help="Maximum queue processing passes before declaring the smoke incomplete",
    )
    parser.add_argument(
        "--persist-audit",
        action="store_true",
        help="Persist full audit rows during the smoke run",
    )
    parser.add_argument(
        "--persist-measure-report",
        action="store_true",
        help="Persist generated individual MeasureReport JSON rows",
    )
    parser.add_argument(
        "--publish-measure-report-to-hapi",
        action="store_true",
        help="Publish generated individual MeasureReport resources back to HAPI",
    )
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[2]
    compose_file = args.compose_file
    if not compose_file.is_absolute():
        compose_file = repo_root / compose_file

    if not args.skip_compose:
        _run_compose(compose_file, "up", "-d", "postgres", "hapi")

    _wait_for_hapi(args.base_url, args.timeout)
    _wait_for_postgres(args.connection, args.timeout)

    measure_ids = _parse_measure_ids(args.measure)
    measure_configs = _find_measures(measure_ids, args.suite)
    test_suites = {config.id: load_test_suite(config) for config in measure_configs}
    cases_by_measure = {
        config.id: test_suites[config.id].test_cases[: args.limit_patients]
        for config in measure_configs
    }
    missing_cases = [
        measure_id for measure_id, cases in cases_by_measure.items() if not cases
    ]
    if missing_cases:
        raise RuntimeError(f"No test cases found for: {', '.join(missing_cases)}")

    schema = HapiPostgresSchema(decoded_view=DEFAULT_DECODED_VIEW)
    install_materialization_schema(args.connection, schema=schema)

    materialization_config = _build_materialization_config(
        args.connection,
        schema=schema,
        measure_configs=measure_configs,
        test_suite_periods=[
            test_suites[config.id].measurement_period for config in measure_configs
        ],
        measure_version=args.suite,
        batch_size=args.batch_size,
        persist_audit=args.persist_audit,
        persist_measure_report=(
            args.persist_measure_report or args.publish_measure_report_to_hapi
        ),
        publish_measure_report_to_hapi=args.publish_measure_report_to_hapi,
        hapi_base_url=args.base_url,
    )
    sync_measure_config(materialization_config)

    smoke_started = datetime.now(timezone.utc)
    smoke_stamp = str(time.time_ns())
    loaded_resources = 0
    seen_resources: dict[tuple[str, str], str] = {}
    target_patients: set[str] = set()
    configured_measure_ids = [
        measure.measure_id for measure in materialization_config.measures
    ]
    for measure_id in configured_measure_ids:
        for case in cases_by_measure[measure_id]:
            target_patients.add(case.patient_id)
            for resource in patient_first(case.resources):
                if _is_duplicate_resource(resource, seen_resources):
                    continue
                put_resource(args.base_url, _stamp_resource(resource, smoke_stamp))
                loaded_resources += 1

    target_patient_ids = sorted(target_patients)
    target_measure_ids = configured_measure_ids
    results = []
    claimed_patients: set[str] = set()
    persisted: list[dict[str, Any]] = []
    with HapiMaterializationRuntime.open(materialization_config) as runtime:
        for _ in range(args.max_process_loops):
            result = process_queue_once(
                materialization_config,
                limit=args.batch_size,
                runtime=runtime,
            )
            results.append(
                {
                    "run_id": result.run_id,
                    "claimed": result.claimed,
                    "errors": result.errors,
                    "metrics": result.metrics,
                }
            )
            claimed_patients.update(result.claimed)
            persisted = _fetch_persisted_results(
                args.connection,
                target_measure_ids,
                target_patient_ids,
                calculated_after=smoke_started,
            )
            if not _missing_result_pairs(
                persisted,
                target_measure_ids,
                target_patient_ids,
            ):
                break
            if not result.claimed:
                time.sleep(1)

    if not persisted:
        persisted = _fetch_persisted_results(
            args.connection,
            target_measure_ids,
            target_patient_ids,
            calculated_after=smoke_started,
        )
    missing = _missing_result_pairs(
        persisted,
        target_measure_ids,
        target_patient_ids,
    )
    errors = [row for row in persisted if row["status"] == "error"]
    missing_reports = []
    if args.persist_measure_report or args.publish_measure_report_to_hapi:
        missing_reports = [
            row
            for row in persisted
            if row["status"] == "ok" and not row["has_measure_report"]
        ]
    if missing or errors or missing_reports:
        raise RuntimeError(
            "HAPI materialization smoke failed: "
            + json.dumps(
                {
                    "missing": missing,
                    "errors": errors,
                    "missing_measure_reports": missing_reports,
                },
                default=str,
            )
        )

    print(
        json.dumps(
            {
                "measure_ids": target_measure_ids,
                "loaded_cases_by_measure": {
                    measure_id: len(cases)
                    for measure_id, cases in cases_by_measure.items()
                },
                "loaded_patients": len(target_patient_ids),
                "loaded_resources": loaded_resources,
                "target_patients": target_patient_ids,
                "claimed_target_patients": sorted(
                    set(target_patient_ids).intersection(claimed_patients)
                ),
                "persisted_results": persisted,
                "queue_runs": results,
            },
            indent=2,
            default=str,
        )
    )
    return 0


def _run_compose(compose_file: Path, *args: str) -> None:
    subprocess.run(
        ["docker", "compose", "-f", str(compose_file), *args],
        check=True,
    )


def put_resource(base_url: str, resource: dict[str, Any]) -> None:
    resource_type = resource.get("resourceType")
    resource_id = resource.get("id")
    if not resource_type or not resource_id:
        return
    url = f"{base_url.rstrip('/')}/{resource_type}/{resource_id}"
    data = json.dumps(resource).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=data,
        method="PUT",
        headers={"Content-Type": "application/fhir+json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            response.read()
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(
            f"HAPI PUT failed for {resource_type}/{resource_id}: {body}"
        ) from exc


def patient_first(resources: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        resources,
        key=lambda resource: 0 if resource.get("resourceType") == "Patient" else 1,
    )


def _stamp_resource(resource: dict[str, Any], stamp: str) -> dict[str, Any]:
    stamped = copy.deepcopy(resource)
    meta = stamped.setdefault("meta", {})
    tags = meta.setdefault("tag", [])
    tags.append(
        {
            "system": "https://fhir4ds.com/smoke-test",
            "code": stamp,
        }
    )
    return stamped


def _wait_for_hapi(base_url: str, timeout: float) -> None:
    deadline = time.monotonic() + timeout
    url = f"{base_url.rstrip('/')}/metadata"
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=5) as response:
                response.read()
                return
        except (urllib.error.URLError, TimeoutError) as exc:
            last_error = exc
            time.sleep(2)
    raise RuntimeError(f"HAPI server did not become ready at {url}: {last_error}")


def _wait_for_postgres(connection_string: str, timeout: float) -> None:
    import psycopg

    deadline = time.monotonic() + timeout
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            with psycopg.connect(connection_string) as conn:
                conn.execute("SELECT 1").fetchone()
                return
        except Exception as exc:
            last_error = exc
            time.sleep(2)
    raise RuntimeError(f"PostgreSQL did not become ready: {last_error}")


def _parse_measure_ids(raw_measure_ids: list[str] | None) -> list[str]:
    measure_ids: list[str] = []
    seen: set[str] = set()
    for raw in raw_measure_ids or ["CMS122"]:
        for item in raw.split(","):
            measure_id = item.strip().upper()
            if not measure_id or measure_id in seen:
                continue
            measure_ids.append(measure_id)
            seen.add(measure_id)
    if not measure_ids:
        raise RuntimeError("At least one measure ID is required")
    return measure_ids


def _find_measures(measure_ids: list[str], suite: str) -> list[Any]:
    configs = _discover_measures(suite=suite)
    by_id = {config.id.upper(): config for config in configs}
    missing = [measure_id for measure_id in measure_ids if measure_id.upper() not in by_id]
    if missing:
        available = ", ".join(config.id for config in configs[:12])
        raise RuntimeError(
            f"Measure not found: {', '.join(missing)}. "
            f"Available examples: {available}"
        )
    return [by_id[measure_id.upper()] for measure_id in measure_ids]


def _build_materialization_config(
    connection_string: str,
    *,
    schema: HapiPostgresSchema,
    measure_configs: list[Any],
    test_suite_periods: list[dict[str, str] | None],
    measure_version: str,
    batch_size: int,
    persist_audit: bool,
    persist_measure_report: bool,
    publish_measure_report_to_hapi: bool,
    hapi_base_url: str,
) -> HapiMaterializationConfig:
    period = _shared_measurement_period(test_suite_periods)
    parameters = {"Measurement Period": (period["start"], period["end"])}
    return HapiMaterializationConfig(
        postgres_connection_string=connection_string,
        hapi_base_url=hapi_base_url,
        hapi_schema=schema,
        measures=[
            HapiMaterializedMeasure(
                measure_id=measure_config.id,
                measure_path=_measure_bundle_path(measure_config),
                cql_path=measure_config.cql_path,
                library_paths=list(measure_config.include_paths),
                valueset_paths=list(measure_config.valueset_paths),
                measure_version=measure_version,
                audit_mode=AuditMode.POPULATION if persist_audit else AuditMode.NONE,
                persist_audit=persist_audit,
                persist_measure_report=persist_measure_report,
                publish_measure_report_to_hapi=publish_measure_report_to_hapi,
            )
            for measure_config in measure_configs
        ],
        parameters=parameters,
        batch_size=batch_size,
        max_attempts=3,
        retry_backoff_seconds=1.0,
        processing_timeout_seconds=120.0,
        fail_on_unsupported_storage=True,
    )


def _measure_bundle_path(measure_config: Any) -> Path:
    return (
        measure_config.test_dir.parents[3]
        / "bundles"
        / "measure"
        / measure_config.name
        / f"{measure_config.name}-bundle.json"
    )


def _shared_measurement_period(
    periods: list[dict[str, str] | None],
) -> dict[str, str]:
    configured = [
        (period["start"], period["end"])
        for period in periods
        if period and period.get("start") and period.get("end")
    ]
    unique = sorted(set(configured))
    if len(unique) > 1:
        rendered = ", ".join(f"{start}..{end}" for start, end in unique)
        raise RuntimeError(
            "Multi-measure smoke currently requires one shared measurement "
            f"period. Found: {rendered}"
        )
    if unique:
        start, end = unique[0]
        return {"start": start, "end": end}
    return {"start": "2026-01-01", "end": "2026-12-31"}


def _is_duplicate_resource(
    resource: dict[str, Any],
    seen_resources: dict[tuple[str, str], str],
) -> bool:
    resource_type = resource.get("resourceType")
    resource_id = resource.get("id")
    if not resource_type or not resource_id:
        return False
    key = (str(resource_type), str(resource_id))
    canonical = json.dumps(resource, sort_keys=True, separators=(",", ":"))
    existing = seen_resources.get(key)
    if existing is None:
        seen_resources[key] = canonical
        return False
    if existing != canonical:
        raise RuntimeError(
            f"Conflicting fixture resource for {resource_type}/{resource_id}"
        )
    return True


def _fetch_persisted_results(
    connection_string: str,
    measure_ids: list[str],
    patient_ids: list[str],
    *,
    calculated_after: datetime,
) -> list[dict[str, Any]]:
    import psycopg

    with psycopg.connect(connection_string) as conn:
        rows = conn.execute(
            """
            SELECT
                measure_id,
                patient_id,
                status,
                error,
                measure_report_json IS NOT NULL AS has_measure_report,
                measure_report_json->>'id' AS measure_report_id
            FROM fhir4ds_measure_result
            WHERE active = true
              AND measure_id = ANY(%s::TEXT[])
              AND patient_id = ANY(%s::TEXT[])
              AND calculated_at >= %s
            ORDER BY measure_id, patient_id
            """,
            [measure_ids, patient_ids, calculated_after],
        ).fetchall()
    return [
        {
            "measure_id": row[0],
            "patient_id": row[1],
            "status": row[2],
            "error": row[3],
            "has_measure_report": bool(row[4]),
            "measure_report_id": row[5],
        }
        for row in rows
    ]


def _missing_result_pairs(
    persisted: list[dict[str, Any]],
    measure_ids: list[str],
    patient_ids: list[str],
) -> list[dict[str, str]]:
    found = {(row["measure_id"], row["patient_id"]) for row in persisted}
    return [
        {"measure_id": measure_id, "patient_id": patient_id}
        for measure_id in measure_ids
        for patient_id in patient_ids
        if (measure_id, patient_id) not in found
    ]


if __name__ == "__main__":
    raise SystemExit(main())
