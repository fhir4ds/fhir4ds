"""DQM command-line implementation."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from fhir4ds.dqm.batch import inspect_config, run_batch, validate_config
from fhir4ds.dqm.config import (
    AuditSpec,
    DefinitionOutputSpec,
    DQMConfigError,
    DQMRunConfig,
    MeasureSpec,
    OutputSpec,
    SourceSpec,
    TerminologySpec,
    load_run_config,
)
from fhir4ds.dqm.hapi_materialization import (
    enqueue_existing_patients,
    explain_patient_scope_plan,
    install_materialization_schema,
    listen_and_process,
    load_materialization_config,
    materialization_status,
    process_queue_once,
    prune_materialization_history,
    reset_materialization_queue,
    sync_measure_config,
)
from fhir4ds.dqm.mongo_materialization import (
    enqueue_existing_patients as mongo_enqueue_existing_patients,
)
from fhir4ds.dqm.mongo_materialization import (
    install_mongo_materialization,
    load_mongo_materialization_config,
)
from fhir4ds.dqm.mongo_materialization import (
    listen_and_process as mongo_listen_and_process,
)
from fhir4ds.dqm.mongo_materialization import (
    materialization_status as mongo_materialization_status,
)
from fhir4ds.dqm.mongo_materialization import (
    process_queue_once as mongo_process_queue_once,
)
from fhir4ds.dqm.mongo_materialization import (
    prune_materialization_history as mongo_prune_materialization_history,
)
from fhir4ds.dqm.mongo_materialization import (
    require_pymongo as mongo_require_pymongo,
)
from fhir4ds.dqm.mongo_materialization import (
    reset_patient_queue as mongo_reset_patient_queue,
)
from fhir4ds.dqm.mongo_materialization import (
    sync_measure_config as mongo_sync_measure_config,
)
from fhir4ds.dqm.types import AuditMode


def configure_parser(parser: argparse.ArgumentParser) -> None:
    subparsers = parser.add_subparsers(dest="dqm_command")

    run_parser = subparsers.add_parser("run", help="Evaluate DQM measures")
    _add_config_and_run_args(run_parser)

    validate_parser = subparsers.add_parser("validate", help="Validate DQM configuration")
    _add_config_and_run_args(validate_parser)

    inspect_parser = subparsers.add_parser("inspect", help="Inspect DQM configuration")
    _add_config_and_run_args(inspect_parser)

    hapi_parser = subparsers.add_parser(
        "hapi",
        help="Manage HAPI PostgreSQL DQM materialization",
    )
    _add_hapi_args(hapi_parser)

    mongo_parser = subparsers.add_parser(
        "mongo",
        help="Manage Mongo DQM materialization",
    )
    _add_mongo_args(mongo_parser)


def run(args: argparse.Namespace) -> int:
    if args.dqm_command is None:
        print(
            "fhir4ds dqm requires a subcommand: run, validate, inspect, hapi, or mongo",
            file=sys.stderr,
        )
        return 2
    try:
        if args.dqm_command == "hapi":
            return _run_hapi(args)
        if args.dqm_command == "mongo":
            return _run_mongo(args)

        config = _load_config_from_args(args)
        if args.dqm_command == "validate":
            errors = validate_config(config)
            if errors:
                for error in errors:
                    print(f"ERROR: {error}", file=sys.stderr)
                return 1
            print("DQM configuration is valid")
            return 0
        if args.dqm_command == "inspect":
            print(json.dumps(inspect_config(config), indent=2, default=str))
            return 0

        result = run_batch(config)
        for record in result.records:
            if record.status == "ok":
                print(
                    f"{record.measure_id}: ok "
                    f"({record.result_rows} rows, {record.duration_ms:.1f} ms)"
                )
            else:
                print(f"{record.measure_id}: error: {record.error}", file=sys.stderr)
        print(
            f"Wrote DQM outputs to {result.output_dir} "
            f"({len(result.records) - len(result.failed)}/{len(result.records)} succeeded)"
        )
        return 1 if result.failed else 0
    except (DQMConfigError, FileNotFoundError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


def _add_hapi_args(parser: argparse.ArgumentParser) -> None:
    subparsers = parser.add_subparsers(dest="hapi_command")

    install_parser = subparsers.add_parser(
        "install",
        help="Install queue, result tables, and HAPI triggers",
    )
    install_parser.add_argument(
        "--connection",
        help="PostgreSQL connection string for the HAPI database",
    )
    install_parser.add_argument(
        "--config",
        help="Optional HAPI materialization config; supplies connection, schema, and channel",
    )

    sync_parser = subparsers.add_parser(
        "sync-config",
        help="Sync materialized measure config into PostgreSQL",
    )
    sync_parser.add_argument("--config", required=True, help="HAPI materialization config")

    process_parser = subparsers.add_parser(
        "process-queue",
        help="Process one batch of queued HAPI patient changes",
    )
    process_parser.add_argument("--config", required=True, help="HAPI materialization config")
    process_parser.add_argument("--limit", type=int, help="Maximum patients to claim")
    process_parser.add_argument("--log-level", default="WARNING", help="Python logging level")

    enqueue_parser = subparsers.add_parser(
        "enqueue-patients",
        help="Queue current Patient resources for initial materialization or re-run",
    )
    enqueue_parser.add_argument("--config", required=True, help="HAPI materialization config")
    enqueue_parser.add_argument(
        "--patient-id",
        action="append",
        default=[],
        help="Specific patient id to enqueue; may be repeated",
    )
    enqueue_parser.add_argument(
        "--all",
        action="store_true",
        help="Queue all current Patient resources when no --patient-id is supplied",
    )
    enqueue_parser.add_argument("--limit", type=int, help="Maximum patients to enqueue")

    listen_parser = subparsers.add_parser(
        "listen",
        help="Listen for HAPI patient-change notifications and process continuously",
    )
    listen_parser.add_argument("--config", required=True, help="HAPI materialization config")
    listen_parser.add_argument("--log-level", default="INFO", help="Python logging level")

    prune_parser = subparsers.add_parser(
        "prune",
        help="Apply configured HAPI materialization retention policy",
    )
    prune_parser.add_argument("--config", required=True, help="HAPI materialization config")
    prune_parser.add_argument("--log-level", default="WARNING", help="Python logging level")

    status_parser = subparsers.add_parser(
        "status",
        help="Show queue, run, result, and MeasureReport materialization status",
    )
    status_parser.add_argument("--config", required=True, help="HAPI materialization config")
    status_parser.add_argument(
        "--limit",
        type=int,
        default=5,
        help="Number of recent runs to include",
    )

    explain_parser = subparsers.add_parser(
        "explain-scope",
        help="Show PostgreSQL EXPLAIN for HAPI decoded-view patient scope",
    )
    explain_parser.add_argument("--config", required=True, help="HAPI materialization config")
    explain_parser.add_argument(
        "--patient-id",
        action="append",
        required=True,
        help="Patient id to include in the scoped plan; may be repeated",
    )
    explain_parser.add_argument(
        "--analyze",
        action="store_true",
        help="Run EXPLAIN ANALYZE with BUFFERS",
    )

    reset_parser = subparsers.add_parser(
        "reset-queue",
        help="Reset selected patient-change queue rows to pending for retry",
    )
    reset_parser.add_argument("--config", required=True, help="HAPI materialization config")
    reset_parser.add_argument(
        "--status",
        action="append",
        choices=["failed", "processing", "complete"],
        help="Queue status to reset; may be repeated. Defaults to failed.",
    )
    reset_parser.add_argument(
        "--patient-id",
        action="append",
        default=[],
        help="Specific patient id to reset; may be repeated",
    )
    reset_parser.add_argument(
        "--all",
        action="store_true",
        help="Reset all rows matching --status when no --patient-id is supplied",
    )
    reset_parser.add_argument(
        "--keep-attempts",
        action="store_true",
        help="Preserve queue attempt counters instead of resetting them to zero",
    )


def _add_mongo_args(parser: argparse.ArgumentParser) -> None:
    subparsers = parser.add_subparsers(dest="mongo_command")

    install_parser = subparsers.add_parser(
        "install",
        help="Create Mongo materialization indexes",
    )
    install_parser.add_argument("--config", required=True, help="Mongo materialization config")

    sync_parser = subparsers.add_parser(
        "sync-config",
        help="Sync materialized measure config into Mongo",
    )
    sync_parser.add_argument("--config", required=True, help="Mongo materialization config")

    process_parser = subparsers.add_parser(
        "process-queue",
        help="Process one batch of queued Mongo patient changes",
    )
    process_parser.add_argument("--config", required=True, help="Mongo materialization config")
    process_parser.add_argument("--limit", type=int, help="Maximum patients to claim")
    process_parser.add_argument("--log-level", default="WARNING", help="Python logging level")

    enqueue_parser = subparsers.add_parser(
        "enqueue-patients",
        help="Queue current Patient resources for initial Mongo materialization or re-run",
    )
    enqueue_parser.add_argument("--config", required=True, help="Mongo materialization config")
    enqueue_parser.add_argument(
        "--patient-id",
        action="append",
        default=[],
        help="Specific patient id to enqueue; may be repeated",
    )
    enqueue_parser.add_argument(
        "--all",
        action="store_true",
        help="Queue all current Patient resources when no --patient-id is supplied",
    )
    enqueue_parser.add_argument("--limit", type=int, help="Maximum patients to enqueue")

    listen_parser = subparsers.add_parser(
        "listen",
        help="Watch Mongo change streams and process continuously",
    )
    listen_parser.add_argument("--config", required=True, help="Mongo materialization config")
    listen_parser.add_argument("--log-level", default="INFO", help="Python logging level")

    prune_parser = subparsers.add_parser(
        "prune",
        help="Apply configured Mongo materialization retention policy",
    )
    prune_parser.add_argument("--config", required=True, help="Mongo materialization config")
    prune_parser.add_argument("--log-level", default="WARNING", help="Python logging level")

    status_parser = subparsers.add_parser(
        "status",
        help="Show queue, run, result, and MeasureReport materialization status",
    )
    status_parser.add_argument("--config", required=True, help="Mongo materialization config")
    status_parser.add_argument(
        "--limit",
        type=int,
        default=5,
        help="Number of recent runs to include",
    )

    reset_parser = subparsers.add_parser(
        "reset-queue",
        help="Reset selected Mongo patient-change queue rows to pending for retry",
    )
    reset_parser.add_argument("--config", required=True, help="Mongo materialization config")
    reset_parser.add_argument(
        "--status",
        action="append",
        choices=["failed", "processing", "complete"],
        help="Queue status to reset; may be repeated. Defaults to failed.",
    )
    reset_parser.add_argument(
        "--patient-id",
        action="append",
        default=[],
        help="Specific patient id to reset; may be repeated",
    )
    reset_parser.add_argument(
        "--all",
        action="store_true",
        help="Reset all rows matching --status when no --patient-id is supplied",
    )
    reset_parser.add_argument(
        "--keep-attempts",
        action="store_true",
        help="Preserve queue attempt counters instead of resetting them to zero",
    )


def _run_hapi(args: argparse.Namespace) -> int:
    if args.hapi_command is None:
        print(
            "fhir4ds dqm hapi requires a subcommand: "
            "install, sync-config, enqueue-patients, process-queue, listen, prune, "
            "status, explain-scope, or reset-queue",
            file=sys.stderr,
        )
        return 2

    if args.hapi_command == "install":
        config = load_materialization_config(args.config) if args.config else None
        connection = args.connection or (
            config.postgres_connection_string if config is not None else None
        )
        if connection is None:
            print("ERROR: hapi install requires --connection or --config", file=sys.stderr)
            return 2
        install_materialization_schema(
            connection,
            schema=config.hapi_schema if config is not None else None,
            notification_channel=(
                config.notification_channel
                if config is not None
                else "fhir4ds_patient_changed"
            ),
        )
        print("Installed HAPI materialization schema and triggers")
        return 0

    config = load_materialization_config(args.config)
    if args.hapi_command == "sync-config":
        count = sync_measure_config(config)
        print(f"Synced {count} measure configuration row(s)")
        return 0
    if args.hapi_command == "process-queue":
        _configure_logging(args.log_level)
        result = process_queue_once(config, limit=args.limit)
        metrics_suffix = ""
        if result.metrics:
            metrics_suffix = (
                f", cache_hits={result.metrics.get('cache_hits', 0)}, "
                f"cache_misses={result.metrics.get('cache_misses', 0)}, "
                f"execute_ms={float(result.metrics.get('execute_ms', 0.0) or 0.0):.1f}"
            )
        print(
            f"Processed queue batch: run_id={result.run_id}, "
            f"patients={len(result.claimed)}, measures={result.measures}, "
            f"errors={len(result.errors)}, stale_reset={result.stale_reset}"
            f"{metrics_suffix}"
        )
        return 1 if result.errors else 0
    if args.hapi_command == "enqueue-patients":
        if not args.patient_id and not args.all:
            print(
                "ERROR: enqueue-patients requires --patient-id or --all",
                file=sys.stderr,
            )
            return 2
        count = enqueue_existing_patients(
            config,
            patient_ids=args.patient_id or None,
            limit=args.limit,
        )
        print(f"Queued HAPI patients for materialization: count={count}")
        return 0
    if args.hapi_command == "listen":
        _configure_logging(args.log_level)
        listen_and_process(config)
        return 0
    if args.hapi_command == "prune":
        _configure_logging(args.log_level)
        deleted = prune_materialization_history(
            config.postgres_connection_string,
            config.retention,
        )
        print(
            "Pruned HAPI materialization history: "
            f"audits={deleted['audits']}, "
            f"inactive_results={deleted['inactive_results']}, "
            f"runs={deleted['runs']}"
        )
        return 0
    if args.hapi_command == "status":
        print(
            json.dumps(
                materialization_status(
                    config.postgres_connection_string,
                    limit=args.limit,
                ),
                indent=2,
                default=str,
            )
        )
        return 0
    if args.hapi_command == "explain-scope":
        for line in explain_patient_scope_plan(
            config,
            args.patient_id,
            analyze=args.analyze,
        ):
            print(line)
        return 0
    if args.hapi_command == "reset-queue":
        if not args.patient_id and not args.all:
            print(
                "ERROR: reset-queue requires --patient-id or --all",
                file=sys.stderr,
            )
            return 2
        statuses = args.status or ["failed"]
        count = reset_materialization_queue(
            config.postgres_connection_string,
            statuses=statuses,
            patient_ids=args.patient_id or None,
            reset_attempts=not args.keep_attempts,
        )
        print(
            "Reset HAPI materialization queue rows: "
            f"count={count}, statuses={','.join(statuses)}"
        )
        return 0

    print(f"Unknown HAPI command: {args.hapi_command}", file=sys.stderr)
    return 2


def _run_mongo(args: argparse.Namespace) -> int:
    if args.mongo_command is None:
        print(
            "fhir4ds dqm mongo requires a subcommand: "
            "install, sync-config, enqueue-patients, process-queue, listen, prune, "
            "status, or reset-queue",
            file=sys.stderr,
        )
        return 2

    config = load_mongo_materialization_config(args.config)
    if args.mongo_command == "install":
        install_mongo_materialization(config)
        print("Installed Mongo materialization indexes")
        return 0
    if args.mongo_command == "sync-config":
        count = mongo_sync_measure_config(config)
        print(f"Synced {count} Mongo measure configuration row(s)")
        return 0
    if args.mongo_command == "process-queue":
        _configure_logging(args.log_level)
        result = mongo_process_queue_once(config, limit=args.limit)
        metrics_suffix = ""
        if result.metrics:
            metrics_suffix = (
                f", cache_hits={result.metrics.get('cache_hits', 0)}, "
                f"cache_misses={result.metrics.get('cache_misses', 0)}, "
                f"execute_ms={float(result.metrics.get('execute_ms', 0.0) or 0.0):.1f}"
            )
        print(
            f"Processed Mongo queue batch: run_id={result.run_id}, "
            f"patients={len(result.claimed)}, measures={result.measures}, "
            f"errors={len(result.errors)}, stale_reset={result.stale_reset}"
            f"{metrics_suffix}"
        )
        return 1 if result.errors else 0
    if args.mongo_command == "enqueue-patients":
        if not args.patient_id and not args.all:
            print(
                "ERROR: enqueue-patients requires --patient-id or --all",
                file=sys.stderr,
            )
            return 2
        count = mongo_enqueue_existing_patients(
            config,
            patient_ids=args.patient_id or None,
            limit=args.limit,
        )
        print(f"Queued Mongo patients for materialization: count={count}")
        return 0
    if args.mongo_command == "listen":
        _configure_logging(args.log_level)
        mongo_listen_and_process(config)
        return 0
    if args.mongo_command == "prune":
        _configure_logging(args.log_level)
        deleted = mongo_prune_materialization_history(config)
        print(
            "Pruned Mongo materialization history: "
            f"audits={deleted['audits']}, "
            f"inactive_results={deleted['inactive_results']}, "
            f"runs={deleted['runs']}"
        )
        return 0
    if args.mongo_command == "status":
        print(
            json.dumps(
                mongo_materialization_status(config, limit=args.limit),
                indent=2,
                default=str,
            )
        )
        return 0
    if args.mongo_command == "reset-queue":
        if not args.patient_id and not args.all:
            print(
                "ERROR: reset-queue requires --patient-id or --all",
                file=sys.stderr,
            )
            return 2
        statuses = args.status or ["failed"]
        pymongo = mongo_require_pymongo()
        with pymongo.MongoClient(config.connection_string) as client:
            count = mongo_reset_patient_queue(
                client[config.materialization_database],
                collections=config.collections,
                statuses=statuses,
                patient_ids=args.patient_id or None,
                reset_attempts=not args.keep_attempts,
            )
        print(
            "Reset Mongo materialization queue rows: "
            f"count={count}, statuses={','.join(statuses)}"
        )
        return 0

    print(f"Unknown Mongo command: {args.mongo_command}", file=sys.stderr)
    return 2


def _configure_logging(level_name: str) -> None:
    level = getattr(logging, str(level_name).upper(), logging.INFO)
    logging.basicConfig(level=level, format="%(message)s")


def _add_config_and_run_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--config", help="Path to DQM JSON/YAML config")
    parser.add_argument("--measure", action="append", help="Measure JSON path")
    parser.add_argument("--cql", action="append", help="CQL file path for the matching measure")
    parser.add_argument("--library-dir", action="append", default=[], help="Directory of CQL libraries")
    parser.add_argument("--source", help="FHIR source path")
    parser.add_argument(
        "--source-type",
        choices=["filesystem", "directory", "ndjson", "json"],
        default="directory",
        help="FHIR source type when not using --config",
    )
    parser.add_argument("--source-format", help="filesystem source format")
    parser.add_argument("--valuesets", action="append", default=[], help="ValueSet file or directory")
    parser.add_argument("--period", help="Measurement period as START:END")
    parser.add_argument(
        "--audit-mode",
        choices=[mode.value for mode in AuditMode],
        default=AuditMode.NONE.value,
    )
    parser.add_argument("--narratives", action="store_true", help="Generate audit narratives")
    parser.add_argument("--patient-id", action="append", help="Restrict evaluation to a patient id")
    parser.add_argument("--filter-to-ip", action="store_true", help="Only emit initial-population rows")
    parser.add_argument("--output", help="Output directory")
    parser.add_argument(
        "--format",
        action="append",
        choices=["csv", "json", "parquet"],
        dest="formats",
        help="Result output format; may be repeated",
    )
    parser.add_argument(
        "--measure-reports",
        choices=["none", "summary", "individual", "both"],
        default="summary",
    )
    parser.add_argument(
        "--definitions",
        choices=["none", "all"],
        default="none",
        help="Write evaluated CQL define statements as per-measure machine-readable output",
    )
    parser.add_argument(
        "--definition-format",
        action="append",
        choices=["csv", "json", "parquet"],
        dest="definition_formats",
        help="Definition output format; may be repeated",
    )
    parser.add_argument(
        "--include-sde-definitions",
        action="store_true",
        help="Include SDE-prefixed definitions in --definitions all output",
    )
    parser.add_argument(
        "--fail-fast",
        action="store_true",
        help="Stop after the first measure failure",
    )


def _load_config_from_args(args: argparse.Namespace) -> DQMRunConfig:
    if args.config:
        return load_run_config(args.config)

    if not args.measure:
        raise DQMConfigError("Either --config or --measure is required")
    if not args.source:
        raise DQMConfigError("Either --config or --source is required")
    if not args.output:
        raise DQMConfigError("Either --config or --output is required")

    cql_paths = [Path(path) for path in args.cql or []]
    if cql_paths and len(cql_paths) != len(args.measure):
        raise DQMConfigError("--cql must be supplied once per --measure when used")
    measures = [
        MeasureSpec(
            path=Path(path),
            cql=cql_paths[index] if cql_paths else None,
        )
        for index, path in enumerate(args.measure)
    ]
    period_start = None
    period_end = None
    parameters = {}
    if args.period:
        if ":" not in args.period:
            raise DQMConfigError("--period must use START:END format")
        period_start, period_end = args.period.split(":", 1)
        parameters["Measurement Period"] = (period_start, period_end)

    return DQMRunConfig(
        measures=measures,
        source=SourceSpec(
            type=args.source_type,
            path=args.source,
            format=args.source_format,
        ),
        outputs=OutputSpec(
            directory=Path(args.output),
            formats=args.formats or ["json"],
            measure_reports=args.measure_reports,
            definitions=DefinitionOutputSpec(
                mode=args.definitions,
                formats=args.definition_formats or args.formats or ["json"],
                include_sde=args.include_sde_definitions,
            ),
        ),
        libraries=[Path(path) for path in args.library_dir],
        terminology=TerminologySpec(valuesets=[Path(path) for path in args.valuesets]),
        parameters=parameters,
        period_start=period_start,
        period_end=period_end,
        patient_ids=args.patient_id,
        filter_to_ip=args.filter_to_ip,
        audit=AuditSpec(mode=AuditMode(args.audit_mode), narratives=args.narratives),
        continue_on_error=not args.fail_fast,
    )
