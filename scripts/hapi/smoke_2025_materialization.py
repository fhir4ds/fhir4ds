#!/usr/bin/env python3
"""Run a local HAPI PostgreSQL materialization smoke test with 2025 eCQM data."""

from __future__ import annotations

import argparse
import copy
import json
import re
import subprocess
import sys
import time
import urllib.error
import urllib.parse
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
    parser.add_argument(
        "--all-measures",
        action="store_true",
        help="Smoke every discovered measure in the selected suite",
    )
    parser.add_argument(
        "--limit-measures",
        type=int,
        default=None,
        help="Limit the number of discovered measures used with --all-measures",
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
        "--artifact-source",
        choices=["files", "hapi"],
        default="files",
        help="Resolve Measure/CQL/ValueSet artifacts from local files or HAPI",
    )
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

    if args.all_measures:
        measure_configs = _discover_measures(suite=args.suite)
        if args.limit_measures is not None:
            if args.limit_measures <= 0:
                raise RuntimeError("--limit-measures must be positive")
            measure_configs = measure_configs[: args.limit_measures]
        measure_ids = [config.id for config in measure_configs]
    else:
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
    loaded_artifacts = 0
    if args.artifact_source == "hapi":
        loaded_artifacts = _put_hapi_artifacts(args.base_url, measure_configs)

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
        artifact_source=args.artifact_source,
    )
    sync_measure_config(materialization_config)

    smoke_started = datetime.now(timezone.utc)
    smoke_stamp = str(time.time_ns())
    loaded_resources = 0
    loaded_reference_stubs = 0
    seen_resources: dict[tuple[str, str], str] = {}
    stubbed_resources: set[tuple[str, str]] = set()
    target_patients: set[str] = set()
    configured_measure_ids = [
        measure.measure_id for measure in materialization_config.measures
    ]
    for measure_id in configured_measure_ids:
        for case in cases_by_measure[measure_id]:
            target_patients.add(case.patient_id)
            case_keys = _resource_keys(case.resources)
            for resource in dependency_ordered_resources(case.resources):
                loaded_reference_stubs += _put_missing_reference_stubs(
                    args.base_url,
                    resource,
                    local_keys=case_keys,
                    seen_resources=seen_resources,
                    stubbed_resources=stubbed_resources,
                    stamp=smoke_stamp,
                )
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
            if row["status"] == "ok"
            and (not row["has_measure_report"] or not row["has_measure_report_row"])
        ]
        if args.publish_measure_report_to_hapi:
            missing_reports.extend(
                row
                for row in persisted
                if row["status"] == "ok"
                and not row["measure_report_published_to_hapi"]
            )
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
                "loaded_reference_stubs": loaded_reference_stubs,
                "loaded_artifacts": loaded_artifacts,
                "artifact_source": args.artifact_source,
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


def _put_hapi_artifacts(base_url: str, measure_configs: list[Any]) -> int:
    count = 0
    seen: set[tuple[str, str]] = set()
    for measure_config in measure_configs:
        for resource in _hapi_artifacts_for_measure(measure_config):
            resource_type = resource.get("resourceType")
            resource_id = resource.get("id")
            if not resource_type or not resource_id:
                continue
            key = (str(resource_type), str(resource_id))
            if key in seen:
                continue
            put_resource(base_url, resource)
            seen.add(key)
            count += 1
    return count


def _hapi_artifacts_for_measure(measure_config: Any) -> list[dict[str, Any]]:
    artifact_root = measure_config.test_dir.parents[3] / "input" / "resources"
    resources: list[dict[str, Any]] = []

    measure_path = artifact_root / "measure" / f"{measure_config.name}.json"
    resources.append(_read_resource(measure_path))

    for library_name in _cql_library_names(measure_config.cql_path):
        library_path = artifact_root / "library" / f"{library_name}.json"
        if not library_path.exists():
            raise RuntimeError(f"Library resource not found: {library_path}")
        resources.append(_read_resource(library_path))

    for valueset in _valueset_resources_for_paths(measure_config.valueset_paths):
        resources.append(valueset)
    return resources


def _read_resource(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise RuntimeError(f"FHIR artifact resource not found: {path}")
    return json.loads(path.read_text())


def _valueset_resources_for_paths(paths: list[Path]) -> list[dict[str, Any]]:
    valuesets: list[dict[str, Any]] = []
    for path in _iter_json_files(paths):
        data = _read_resource(path)
        if data.get("resourceType") == "Bundle":
            for entry in data.get("entry", []):
                resource = entry.get("resource", {}) if isinstance(entry, dict) else {}
                if resource.get("resourceType") == "ValueSet":
                    valuesets.append(resource)
        elif data.get("resourceType") == "ValueSet":
            valuesets.append(data)
    return valuesets


def _iter_json_files(paths: list[Path]):
    for path in paths:
        if path.is_dir():
            yield from sorted(path.rglob("*.json"))
        elif path.is_file():
            yield path


def _cql_library_names(cql_path: Path) -> list[str]:
    include_re = re.compile(r"^\s*include\s+([A-Za-z][A-Za-z0-9_.]*)\b", re.MULTILINE)
    root = cql_path.parent
    names: list[str] = []
    seen: set[str] = set()

    def visit(path: Path) -> None:
        name = path.stem
        if name in seen:
            return
        seen.add(name)
        names.append(name)
        text = path.read_text()
        for include_name in include_re.findall(text):
            simple_name = include_name.rsplit(".", 1)[-1]
            include_path = root / f"{simple_name}.cql"
            if include_path.exists():
                visit(include_path)

    visit(cql_path)
    return names


def dependency_ordered_resources(resources: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Order same-case resources so local references are created first."""
    keyed: list[tuple[tuple[str, str], dict[str, Any]]] = []
    for resource in resources:
        resource_type = resource.get("resourceType")
        resource_id = resource.get("id")
        if isinstance(resource_type, str) and isinstance(resource_id, str):
            keyed.append(((resource_type, resource_id), resource))

    keyed_by_id = dict(keyed)
    local_keys = set(keyed_by_id)
    dependencies: dict[tuple[str, str], set[tuple[str, str]]] = {}
    for key, resource in keyed:
        dependencies[key] = {
            ref
            for ref in _resource_references(resource)
            if ref in local_keys and ref != key
        }

    ordered: list[dict[str, Any]] = []
    emitted: set[tuple[str, str]] = set()
    while len(emitted) < len(keyed):
        ready = [
            key
            for key, _resource in keyed
            if key not in emitted and dependencies[key].issubset(emitted)
        ]
        if not ready:
            break
        for key in ready:
            emitted.add(key)
            ordered.append(keyed_by_id[key])

    if len(emitted) < len(keyed):
        ordered.extend(
            resource
            for key, resource in keyed
            if key not in emitted
        )

    unkeyed = [
        resource
        for resource in resources
        if not (
            isinstance(resource.get("resourceType"), str)
            and isinstance(resource.get("id"), str)
        )
    ]
    return [*ordered, *unkeyed]


def _resource_references(value: Any) -> set[tuple[str, str]]:
    refs: set[tuple[str, str]] = set()
    if isinstance(value, dict):
        reference = value.get("reference")
        if isinstance(reference, str):
            normalized = _normalize_local_reference(reference)
            if normalized is not None:
                refs.add(normalized)
        for child in value.values():
            refs.update(_resource_references(child))
    elif isinstance(value, list):
        for child in value:
            refs.update(_resource_references(child))
    return refs


def _resource_keys(resources: list[dict[str, Any]]) -> set[tuple[str, str]]:
    keys: set[tuple[str, str]] = set()
    for resource in resources:
        resource_type = resource.get("resourceType")
        resource_id = resource.get("id")
        if isinstance(resource_type, str) and isinstance(resource_id, str):
            keys.add((resource_type, resource_id))
    return keys


def _put_missing_reference_stubs(
    base_url: str,
    resource: dict[str, Any],
    *,
    local_keys: set[tuple[str, str]],
    seen_resources: dict[tuple[str, str], str],
    stubbed_resources: set[tuple[str, str]],
    stamp: str,
) -> int:
    count = 0
    for ref in sorted(_resource_references(resource)):
        if ref in local_keys or ref in seen_resources or ref in stubbed_resources:
            continue
        stub = _reference_stub(ref)
        put_resource(base_url, _stamp_resource(stub, stamp))
        stubbed_resources.add(ref)
        count += 1
    return count


def _reference_stub(ref: tuple[str, str]) -> dict[str, Any]:
    resource_type, resource_id = ref
    stub: dict[str, Any] = {
        "resourceType": resource_type,
        "id": resource_id,
    }
    if resource_type == "Encounter":
        stub.update(
            {
                "status": "unknown",
                "class": {
                    "system": "http://terminology.hl7.org/CodeSystem/v3-ActCode",
                    "code": "UNK",
                },
            }
        )
    elif resource_type == "Observation":
        stub.update({"status": "unknown", "code": {"text": "Reference placeholder"}})
    elif resource_type == "MedicationRequest":
        stub.update({"status": "unknown", "intent": "order"})
    elif resource_type == "Claim":
        stub.update(
            {
                "status": "active",
                "type": {
                    "coding": [
                        {
                            "system": "http://terminology.hl7.org/CodeSystem/claim-type",
                            "code": "professional",
                        }
                    ]
                },
                "use": "claim",
            }
        )
    elif resource_type == "Location":
        stub.update({"status": "active"})
    return stub


def _normalize_local_reference(reference: str) -> tuple[str, str] | None:
    if reference.startswith("#"):
        return None
    if reference.startswith("http://") or reference.startswith("https://"):
        path = urllib.parse.urlsplit(reference).path.strip("/")
        parts = path.split("/")
        if len(parts) >= 2:
            return parts[-2], parts[-1]
        return None
    if "/" not in reference:
        return None
    resource_type, resource_id = reference.split("/", 1)
    if not resource_type or not resource_id or "/" in resource_id:
        return None
    return resource_type, resource_id


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
    artifact_source: str,
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
                measure_path=(
                    _measure_bundle_path(measure_config)
                    if artifact_source == "files"
                    else None
                ),
                cql_path=(
                    measure_config.cql_path if artifact_source == "files" else None
                ),
                artifact_source=artifact_source,
                artifact_ref=(
                    measure_config.name if artifact_source == "hapi" else None
                ),
                library_paths=(
                    list(measure_config.include_paths)
                    if artifact_source == "files"
                    else []
                ),
                valueset_paths=(
                    list(measure_config.valueset_paths)
                    if artifact_source == "files"
                    else []
                ),
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


def _valueset_bundle_path(measure_config: Any) -> Path:
    return (
        measure_config.test_dir.parents[3]
        / "bundles"
        / "measure"
        / measure_config.name
        / f"{measure_config.name}-files"
        / f"valuesets-{measure_config.name}-bundle.json"
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
                result.measure_id,
                result.patient_id,
                result.status,
                result.error,
                result.measure_report_json IS NOT NULL AS has_measure_report,
                result.measure_report_json->>'id' AS measure_report_id,
                report.resource_json IS NOT NULL AS has_measure_report_row,
                report.measure_report_id AS measure_report_row_id,
                COALESCE(report.published_to_hapi, false) AS measure_report_published_to_hapi
            FROM fhir4ds_measure_result result
            LEFT JOIN fhir4ds_measure_report report
              ON report.result_id = result.result_id
             AND report.active = true
            WHERE result.active = true
              AND result.measure_id = ANY(%s::TEXT[])
              AND result.patient_id = ANY(%s::TEXT[])
              AND result.calculated_at >= %s
            ORDER BY result.measure_id, result.patient_id
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
            "has_measure_report_row": bool(row[6]),
            "measure_report_row_id": row[7],
            "measure_report_published_to_hapi": bool(row[8]),
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
