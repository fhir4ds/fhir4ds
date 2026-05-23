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
    parser.add_argument("--measure", default="CMS122", help="Measure ID to smoke")
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
        "--persist-audit",
        action="store_true",
        help="Persist full audit rows during the smoke run",
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

    measure_config = _find_measure(args.measure, args.suite)
    test_suite = load_test_suite(measure_config)
    cases = test_suite.test_cases[: args.limit_patients]
    if not cases:
        raise RuntimeError(f"No test cases found for {measure_config.id}")

    schema = HapiPostgresSchema(decoded_view=DEFAULT_DECODED_VIEW)
    install_materialization_schema(args.connection, schema=schema)

    materialization_config = _build_materialization_config(
        args.connection,
        schema=schema,
        measure_config=measure_config,
        test_suite_period=test_suite.measurement_period,
        batch_size=args.batch_size,
        persist_audit=args.persist_audit,
    )
    sync_measure_config(materialization_config)

    smoke_started = datetime.now(timezone.utc)
    smoke_stamp = str(time.time_ns())
    loaded_resources = 0
    for case in cases:
        for resource in patient_first(case.resources):
            put_resource(args.base_url, _stamp_resource(resource, smoke_stamp))
            loaded_resources += 1

    target_patients = [case.patient_id for case in cases]
    results = []
    claimed_patients: set[str] = set()
    with HapiMaterializationRuntime.open(materialization_config) as runtime:
        for _ in range(5):
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
            if set(target_patients).issubset(claimed_patients):
                break
            if not result.claimed:
                time.sleep(1)

    persisted = _fetch_persisted_results(
        args.connection,
        measure_config.id,
        target_patients,
        calculated_after=smoke_started,
    )
    missing = sorted(set(target_patients) - {row["patient_id"] for row in persisted})
    errors = [row for row in persisted if row["status"] == "error"]
    if missing or errors:
        raise RuntimeError(
            "HAPI materialization smoke failed: "
            + json.dumps({"missing": missing, "errors": errors}, default=str)
        )

    print(
        json.dumps(
            {
                "measure_id": measure_config.id,
                "loaded_patients": len(cases),
                "loaded_resources": loaded_resources,
                "target_patients": target_patients,
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


def _find_measure(measure_id: str, suite: str) -> Any:
    configs = _discover_measures(suite=suite)
    requested = measure_id.upper()
    matches = [config for config in configs if config.id.upper() == requested]
    if not matches:
        available = ", ".join(config.id for config in configs[:12])
        raise RuntimeError(f"Measure not found: {measure_id}. Available examples: {available}")
    return matches[0]


def _build_materialization_config(
    connection_string: str,
    *,
    schema: HapiPostgresSchema,
    measure_config: Any,
    test_suite_period: dict[str, str] | None,
    batch_size: int,
    persist_audit: bool,
) -> HapiMaterializationConfig:
    measure_bundle = (
        measure_config.test_dir.parents[3]
        / "bundles"
        / "measure"
        / measure_config.name
        / f"{measure_config.name}-bundle.json"
    )
    period = test_suite_period or {"start": "2026-01-01", "end": "2026-12-31"}
    parameters = {"Measurement Period": (period["start"], period["end"])}
    return HapiMaterializationConfig(
        postgres_connection_string=connection_string,
        hapi_schema=schema,
        measures=[
            HapiMaterializedMeasure(
                measure_id=measure_config.id,
                measure_path=measure_bundle,
                cql_path=measure_config.cql_path,
                library_paths=list(measure_config.include_paths),
                valueset_paths=list(measure_config.valueset_paths),
                measure_version="2025",
                audit_mode=AuditMode.POPULATION if persist_audit else AuditMode.NONE,
                persist_audit=persist_audit,
            )
        ],
        parameters=parameters,
        batch_size=batch_size,
        max_attempts=3,
        retry_backoff_seconds=1.0,
        processing_timeout_seconds=120.0,
        fail_on_unsupported_storage=True,
    )


def _fetch_persisted_results(
    connection_string: str,
    measure_id: str,
    patient_ids: list[str],
    *,
    calculated_after: datetime,
) -> list[dict[str, Any]]:
    import psycopg

    with psycopg.connect(connection_string) as conn:
        rows = conn.execute(
            """
            SELECT patient_id, status, error
            FROM fhir4ds_measure_result
            WHERE active = true
              AND measure_id = %s
              AND patient_id = ANY(%s::TEXT[])
              AND calculated_at >= %s
            ORDER BY patient_id
            """,
            [measure_id, patient_ids, calculated_after],
        ).fetchall()
    return [
        {"patient_id": row[0], "status": row[1], "error": row[2]}
        for row in rows
    ]


if __name__ == "__main__":
    raise SystemExit(main())
