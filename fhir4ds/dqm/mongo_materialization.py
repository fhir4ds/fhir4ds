"""Mongo change-stream DQM materialization for Mongo-backed FHIR servers."""

from __future__ import annotations

import hashlib
import json
import logging
import re
import signal
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import fhir4ds
from fhir4ds.dqm.artifacts import FileArtifactResolver
from fhir4ds.dqm.batch import _resolve_cql_path
from fhir4ds.dqm.config import DQMConfigError, MeasureSpec
from fhir4ds.dqm.evaluator import MeasureEvaluator
from fhir4ds.dqm.models import MeasureResult
from fhir4ds.dqm.types import AuditMode
from fhir4ds.sources import (
    MongoFhirServerSchema,
    MongoFhirServerSource,
    MongoResourceCollection,
)
from fhir4ds.sources.mongo_fhir import (
    _DEFAULT_BASE_VERSION,
    _DEFAULT_HIDDEN_TAG_CODE,
    _DEFAULT_HIDDEN_TAG_SYSTEM,
    _json_path_to_mongo_key,
)

FHIR4DS_MATERIALIZATION_TAG_SYSTEM = "https://fhir4ds.com/materialization"
FHIR4DS_MEASURE_REPORT_TAG_CODE = "measure-report"
FHIR4DS_MEASURE_REPORT_IDENTIFIER_SYSTEM = (
    "https://fhir4ds.com/materialization/measure-report"
)

DEFAULT_QUEUE_COLLECTION = "fhir4ds_patient_change_queue"
DEFAULT_MEASURE_CONFIG_COLLECTION = "fhir4ds_measure_config"
DEFAULT_RUN_COLLECTION = "fhir4ds_measure_run"
DEFAULT_RESULT_COLLECTION = "fhir4ds_measure_result"
DEFAULT_REPORT_COLLECTION = "fhir4ds_measure_report"
DEFAULT_AUDIT_COLLECTION = "fhir4ds_measure_audit"

_ENV_REF_RE = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)(?::-(.*?))?\}")
logger = logging.getLogger(__name__)


@dataclass
class MongoMaterializedMeasure:
    """One measure configured for Mongo DQM materialization."""

    measure_id: str
    measure_path: Path | None = None
    cql_path: Path | None = None
    enabled: bool = True
    measure_version: str | None = None
    library_paths: list[Path] = field(default_factory=list)
    valueset_paths: list[Path] = field(default_factory=list)
    parameters: dict[str, Any] = field(default_factory=dict)
    tags: list[str] = field(default_factory=list)
    audit_mode: AuditMode = AuditMode.NONE
    persist_audit: bool = False
    persist_measure_report: bool = False
    publish_measure_report_to_mongo: bool = False
    generate_narratives: bool = False
    include_supporting_evidence: bool = False
    filter_to_ip: bool = False


@dataclass
class MongoRetentionPolicy:
    """Retention windows for Mongo materialization history."""

    inactive_result_days: int | None = None
    audit_days: int | None = None
    run_days: int | None = None


@dataclass
class MongoMaterializationCollections:
    """FHIR4DS-owned Mongo collection names used by the worker."""

    queue: str = DEFAULT_QUEUE_COLLECTION
    measure_config: str = DEFAULT_MEASURE_CONFIG_COLLECTION
    runs: str = DEFAULT_RUN_COLLECTION
    results: str = DEFAULT_RESULT_COLLECTION
    reports: str = DEFAULT_REPORT_COLLECTION
    audits: str = DEFAULT_AUDIT_COLLECTION


@dataclass
class MongoMaterializationConfig:
    """Configuration for a Mongo DQM materialization worker."""

    connection_string: str
    source_schema: MongoFhirServerSchema = field(default_factory=MongoFhirServerSchema)
    materialization_database_name: str | None = None
    collections: MongoMaterializationCollections = field(
        default_factory=MongoMaterializationCollections
    )
    measures: list[MongoMaterializedMeasure] = field(default_factory=list)
    parameters: dict[str, Any] = field(default_factory=dict)
    library_paths: list[Path] = field(default_factory=list)
    valueset_paths: list[Path] = field(default_factory=list)
    batch_size: int = 100
    poll_interval_seconds: float = 30.0
    max_attempts: int = 3
    retry_backoff_seconds: float = 60.0
    processing_timeout_seconds: float = 900.0
    retention: MongoRetentionPolicy = field(default_factory=MongoRetentionPolicy)
    include_delete_pre_images: bool = False
    source_patient_pushdown: bool = True

    @property
    def source_database_name(self) -> str:
        return self.source_schema.database_name

    @property
    def materialization_database(self) -> str:
        return self.materialization_database_name or self.source_schema.database_name


@dataclass
class ClaimedPatient:
    """One patient claimed from the durable Mongo queue."""

    patient_id: str
    input_watermark: datetime | None = None


@dataclass
class QueueProcessResult:
    """Summary of one queue-processing pass."""

    run_id: str | None
    claimed: list[str]
    measures: int
    stale_reset: int = 0
    errors: dict[str, str] = field(default_factory=dict)
    metrics: dict[str, Any] = field(default_factory=dict)


@dataclass
class MongoMaterializationRuntime:
    """Long-lived DuckDB runtime for a Mongo materialization worker."""

    duck_conn: Any
    source: MongoFhirServerSource
    evaluator: MeasureEvaluator

    @classmethod
    def open(cls, config: MongoMaterializationConfig) -> MongoMaterializationRuntime:
        duck_conn = fhir4ds.create_connection()
        source = MongoFhirServerSource(
            config.connection_string,
            schema=config.source_schema,
        )
        try:
            source.register(duck_conn)
            return cls(
                duck_conn=duck_conn,
                source=source,
                evaluator=MeasureEvaluator(duck_conn),
            )
        except Exception:
            source.unregister(duck_conn)
            duck_conn.close()
            raise

    def close(self) -> None:
        self.source.unregister(self.duck_conn)
        self.duck_conn.close()

    def __enter__(self) -> MongoMaterializationRuntime:
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        self.close()


def require_pymongo() -> Any:
    """Import pymongo with an actionable error for optional Mongo worker usage."""
    try:
        import pymongo  # type: ignore[import-not-found]
    except ImportError as exc:  # pragma: no cover - depends on optional extra
        raise DQMConfigError(
            "Mongo materialization requires pymongo. Install with "
            "`pip install 'fhir4ds-v2[mongo]'` or install `pymongo>=4.6`."
        ) from exc
    return pymongo


def load_mongo_materialization_config(path: str | Path) -> MongoMaterializationConfig:
    """Load a Mongo materialization config from JSON or YAML."""
    config_path = Path(path)
    if not config_path.exists():
        raise FileNotFoundError(f"Mongo materialization config not found: {config_path}")

    text = config_path.read_text()
    suffix = config_path.suffix.lower()
    if suffix == ".json":
        try:
            raw = json.loads(text)
        except json.JSONDecodeError as exc:
            raise DQMConfigError(
                f"Invalid JSON Mongo materialization config {config_path}: {exc}"
            ) from exc
    elif suffix in {".yaml", ".yml"}:
        try:
            import yaml  # type: ignore[import-untyped]
        except ImportError as exc:  # pragma: no cover - PyYAML is required
            raise DQMConfigError("YAML config files require PyYAML") from exc
        try:
            raw = yaml.safe_load(text)
        except Exception as exc:  # pragma: no cover - depends on optional PyYAML internals
            raise DQMConfigError(
                f"Invalid YAML Mongo materialization config {config_path}: {exc}"
            ) from exc
    else:
        raise DQMConfigError("Mongo materialization config must be JSON or YAML")
    return parse_mongo_materialization_config(raw, base_dir=config_path.parent)


def parse_mongo_materialization_config(
    raw: dict[str, Any],
    *,
    base_dir: Path | None = None,
) -> MongoMaterializationConfig:
    """Parse a Mongo materialization config dictionary."""
    if not isinstance(raw, dict):
        raise DQMConfigError("Mongo materialization config must be an object")
    raw = _expand_env_refs(raw)
    base = base_dir or Path.cwd()

    mongo = raw.get("mongo") or {}
    if not isinstance(mongo, dict):
        raise DQMConfigError("'mongo' must be an object")
    connection_string = mongo.get("connection_string") or raw.get("connection_string")
    if not isinstance(connection_string, str) or not connection_string:
        raise DQMConfigError("'mongo.connection_string' is required")
    database_name = mongo.get("database_name", "fhir")
    if not isinstance(database_name, str) or not database_name:
        raise DQMConfigError("'mongo.database_name' must be a non-empty string")
    materialization_database = mongo.get("materialization_database")
    if materialization_database is not None and (
        not isinstance(materialization_database, str) or not materialization_database
    ):
        raise DQMConfigError("'mongo.materialization_database' must be a non-empty string")

    worker = raw.get("worker") or {}
    if not isinstance(worker, dict):
        raise DQMConfigError("'worker' must be an object")
    retention = raw.get("retention") or {}
    if not isinstance(retention, dict):
        raise DQMConfigError("'retention' must be an object")
    defaults = raw.get("defaults") or {}
    if not isinstance(defaults, dict):
        raise DQMConfigError("'defaults' must be an object")
    results = raw.get("results") or {}
    if not isinstance(results, dict):
        raise DQMConfigError("'results' must be an object")

    global_period = raw.get("period") or {}
    if global_period is None:
        global_period = {}
    if not isinstance(global_period, dict):
        raise DQMConfigError("'period' must be an object")
    global_parameters = raw.get("parameters") or {}
    if not isinstance(global_parameters, dict):
        raise DQMConfigError("'parameters' must be an object")
    if global_period.get("start") and global_period.get("end"):
        global_parameters = dict(global_parameters)
        global_parameters.setdefault(
            "Measurement Period",
            (global_period["start"], global_period["end"]),
        )

    global_libraries = _parse_section_paths(raw.get("libraries"), "libraries", "paths", base)
    global_valuesets = _parse_section_paths(
        raw.get("terminology"), "terminology", "valuesets", base
    )
    source_schema = _parse_source_schema(mongo.get("source_schema"), database_name)
    collections = _parse_materialization_collections(mongo.get("collections"))
    measures = _parse_materialized_measures(
        raw.get("measures", []),
        base=base,
        defaults=defaults,
        results=results,
    )

    return MongoMaterializationConfig(
        connection_string=connection_string,
        source_schema=source_schema,
        materialization_database_name=materialization_database,
        collections=collections,
        measures=measures,
        parameters=global_parameters,
        library_paths=global_libraries,
        valueset_paths=global_valuesets,
        batch_size=int(worker.get("batch_size", 100)),
        poll_interval_seconds=float(worker.get("poll_interval_seconds", 30.0)),
        max_attempts=int(worker.get("max_attempts", 3)),
        retry_backoff_seconds=float(worker.get("retry_backoff_seconds", 60.0)),
        processing_timeout_seconds=float(
            worker.get("processing_timeout_seconds", 900.0)
        ),
        include_delete_pre_images=bool(worker.get("include_delete_pre_images", False)),
        source_patient_pushdown=bool(worker.get("source_patient_pushdown", True)),
        retention=_parse_retention_policy(retention),
    )


def install_mongo_materialization(config: MongoMaterializationConfig) -> None:
    """Create FHIR4DS-owned Mongo indexes used by the materialization worker."""
    pymongo = require_pymongo()
    with pymongo.MongoClient(config.connection_string) as client:
        db = client[config.materialization_database]
        db[config.collections.queue].create_index([("status", 1), ("last_seen_at", 1)])
        db[config.collections.queue].create_index(
            [("retry_after_at", 1), ("status", 1)]
        )
        db[config.collections.results].create_index(
            [("patient_id", 1), ("measure_id", 1), ("active", 1)]
        )
        db[config.collections.results].create_index([("run_id", 1)])
        db[config.collections.reports].create_index(
            [("patient_id", 1), ("measure_id", 1), ("active", 1)]
        )
        db[config.collections.reports].create_index([("measure_report_id", 1)])
        db[config.collections.runs].create_index([("started_at", -1)])


def sync_measure_config(config: MongoMaterializationConfig) -> int:
    """Upsert configured measures into the Mongo materialization config collection."""
    pymongo = require_pymongo()
    now = _utcnow()
    with pymongo.MongoClient(config.connection_string) as client:
        db = client[config.materialization_database]
        count = 0
        for measure in config.measures:
            effective_parameters = dict(config.parameters)
            effective_parameters.update(measure.parameters)
            db[config.collections.measure_config].update_one(
                {"_id": measure.measure_id},
                {
                    "$set": {
                        "measure_id": measure.measure_id,
                        "enabled": measure.enabled,
                        "measure_version": measure.measure_version,
                        "measure_path": (
                            str(measure.measure_path)
                            if measure.measure_path is not None
                            else None
                        ),
                        "cql_path": (
                            str(measure.cql_path) if measure.cql_path is not None else None
                        ),
                        "library_paths": [
                            str(path)
                            for path in [*config.library_paths, *measure.library_paths]
                        ],
                        "valueset_paths": [
                            str(path)
                            for path in [*config.valueset_paths, *measure.valueset_paths]
                        ],
                        "parameters": effective_parameters,
                        "tags": measure.tags,
                        "audit_mode": measure.audit_mode.value,
                        "persist_audit": measure.persist_audit,
                        "persist_measure_report": measure.persist_measure_report,
                        "publish_measure_report_to_mongo": (
                            measure.publish_measure_report_to_mongo
                        ),
                        "generate_narratives": measure.generate_narratives,
                        "include_supporting_evidence": measure.include_supporting_evidence,
                        "filter_to_ip": measure.filter_to_ip,
                        "updated_at": now,
                    },
                    "$setOnInsert": {"created_at": now},
                },
                upsert=True,
            )
            count += 1
    return count


def enqueue_existing_patients(
    config: MongoMaterializationConfig,
    *,
    patient_ids: list[str] | tuple[str, ...] | None = None,
    limit: int | None = None,
) -> int:
    """Queue current Patient resources from the configured Mongo source."""
    if limit is not None and limit <= 0:
        raise DQMConfigError("enqueue patient limit must be positive")
    pymongo = require_pymongo()
    source = MongoFhirServerSource(config.connection_string, schema=config.source_schema)
    con = fhir4ds.create_connection(source=source)
    try:
        conditions = ["resourceType = 'Patient'"]
        params: list[Any] = []
        if patient_ids:
            patient_list = sorted({str(patient_id) for patient_id in patient_ids})
            placeholders = ", ".join(["?"] * len(patient_list))
            conditions.append(f"id IN ({placeholders})")
            params.extend(patient_list)
        limit_sql = ""
        if limit is not None:
            limit_sql = " LIMIT ?"
            params.append(limit)
        rows = con.execute(
            f"""
            SELECT id
            FROM resources
            WHERE {" AND ".join(conditions)}
            ORDER BY id
            {limit_sql}
            """,
            params,
        ).fetchall()
    finally:
        source.unregister(con)
        con.close()

    now = _utcnow()
    with pymongo.MongoClient(config.connection_string) as client:
        queue = client[config.materialization_database][config.collections.queue]
        count = 0
        for row in rows:
            patient_id = str(row[0])
            _enqueue_patient_change(
                queue,
                patient_id=patient_id,
                resource_type="Patient",
                resource_id=patient_id,
                seen_at=now,
            )
            count += 1
    return count


def process_queue_once(
    config: MongoMaterializationConfig,
    *,
    limit: int | None = None,
    runtime: MongoMaterializationRuntime | None = None,
) -> QueueProcessResult:
    """Claim pending patients, run configured measures, and persist results."""
    pymongo = require_pymongo()
    batch_limit = limit or config.batch_size
    with pymongo.MongoClient(config.connection_string) as client:
        db = client[config.materialization_database]
        stale_reset = reset_stale_processing(
            db,
            collections=config.collections,
            processing_timeout_seconds=config.processing_timeout_seconds,
            max_attempts=config.max_attempts,
        )
        patients = claim_pending_patients(
            db,
            batch_limit,
            collections=config.collections,
            max_attempts=config.max_attempts,
            retry_backoff_seconds=config.retry_backoff_seconds,
        )
        if not patients:
            return QueueProcessResult(
                run_id=None,
                claimed=[],
                measures=0,
                stale_reset=stale_reset,
            )

        measures = config.measures or load_enabled_measure_config(
            db,
            collections=config.collections,
        )
        measures = [measure for measure in measures if measure.enabled]
        run_id = start_measure_run(
            db,
            collections=config.collections,
            patient_count=len(patients),
            measure_count=len(measures),
            trigger_reason="queue",
        )
        errors: dict[str, str] = {}
        before_metrics = (
            runtime.evaluator.compiled_measure_metrics() if runtime is not None else None
        )
        try:
            after_metrics = _process_claimed_patients(
                db,
                config,
                run_id,
                patients,
                measures,
                errors,
                runtime=runtime,
            )
            metrics = _compiled_metrics_delta(before_metrics, after_metrics)
            complete_measure_run(
                db,
                run_id,
                collections=config.collections,
                status="partial" if errors else "ok",
                metrics=metrics,
            )
        except Exception as exc:
            complete_measure_run(
                db,
                run_id,
                collections=config.collections,
                status="error",
                error=str(exc),
            )
            for patient in patients:
                mark_patient_failed(
                    db,
                    patient.patient_id,
                    str(exc),
                    collections=config.collections,
                    max_attempts=config.max_attempts,
                    retry_backoff_seconds=config.retry_backoff_seconds,
                )
            raise
        return QueueProcessResult(
            run_id=run_id,
            claimed=[patient.patient_id for patient in patients],
            measures=len(measures),
            stale_reset=stale_reset,
            errors=errors,
            metrics=metrics,
        )


def listen_and_process(
    config: MongoMaterializationConfig,
    *,
    stop_after: int | None = None,
) -> None:
    """
    Watch Mongo resource collections and process queued patient changes.

    Mongo change streams require a replica set or sharded cluster. This is the
    Mongo-native analogue to the HAPI PostgreSQL trigger plus LISTEN/NOTIFY
    worker: the durable queue is the contract, and the change stream is the
    wake-up source.
    """
    pymongo = require_pymongo()
    loops = 0
    shutdown, old_handlers = _install_shutdown_handlers()
    try:
        with pymongo.MongoClient(config.connection_string) as client:
            source_db = client[config.source_database_name]
            materialization_db = client[config.materialization_database]
            queue = materialization_db[config.collections.queue]
            with MongoMaterializationRuntime.open(config) as runtime:
                with _open_change_stream(source_db, config) as stream:
                    while not shutdown["requested"]:
                        process_queue_once(config, runtime=runtime)
                        loops += 1
                        if stop_after is not None and loops >= stop_after:
                            return
                        deadline = time.monotonic() + config.poll_interval_seconds
                        while not shutdown["requested"]:
                            change = stream.try_next()
                            if change is not None:
                                enqueue_patient_change_from_mongo_change(
                                    queue,
                                    config,
                                    change,
                                )
                                break
                            if time.monotonic() >= deadline:
                                break
                            time.sleep(0.25)
    finally:
        _restore_shutdown_handlers(old_handlers)


def claim_pending_patients(
    db: Any,
    limit: int,
    *,
    collections: MongoMaterializationCollections | None = None,
    max_attempts: int = 3,
    retry_backoff_seconds: float = 60.0,
) -> list[ClaimedPatient]:
    """Atomically claim eligible queue rows."""
    collections = collections or MongoMaterializationCollections()
    queue = db[collections.queue]
    now = _utcnow()
    claimed: list[ClaimedPatient] = []
    for _ in range(limit):
        doc = queue.find_one_and_update(
            {
                "$or": [
                    {"status": "pending"},
                    {
                        "status": "failed",
                        "attempts": {"$lt": max_attempts},
                        "retry_after_at": {"$lte": now},
                    },
                ]
            },
            {
                "$set": {
                    "status": "processing",
                    "processing_started_at": now,
                },
                "$inc": {"attempts": 1},
            },
            sort=[("last_seen_at", 1), ("patient_id", 1)],
            return_document=True,
        )
        if doc is None:
            break
        claimed.append(
            ClaimedPatient(
                patient_id=str(doc["patient_id"]),
                input_watermark=doc.get("last_seen_at"),
            )
        )
    return claimed


def reset_stale_processing(
    db: Any,
    *,
    collections: MongoMaterializationCollections | None = None,
    processing_timeout_seconds: float = 900.0,
    max_attempts: int = 3,
) -> int:
    """Return timed-out processing rows to pending, or fail exhausted rows."""
    collections = collections or MongoMaterializationCollections()
    queue = db[collections.queue]
    cutoff = _utcnow() - timedelta(seconds=processing_timeout_seconds)
    exhausted = queue.update_many(
        {
            "status": "processing",
            "processing_started_at": {"$lt": cutoff},
            "attempts": {"$gte": max_attempts},
        },
        {
            "$set": {
                "status": "failed",
                "last_error": "Processing timeout; max attempts reached",
                "processed_at": _utcnow(),
                "processing_started_at": None,
            }
        },
    )
    retryable = queue.update_many(
        {
            "status": "processing",
            "processing_started_at": {"$lt": cutoff},
            "attempts": {"$lt": max_attempts},
        },
        {
            "$set": {
                "status": "pending",
                "last_error": "Processing timeout; reset for retry",
                "processing_started_at": None,
            }
        },
    )
    return int(exhausted.modified_count + retryable.modified_count)


def reset_patient_queue(
    db: Any,
    *,
    collections: MongoMaterializationCollections | None = None,
    statuses: list[str] | tuple[str, ...] = ("failed",),
    patient_ids: list[str] | tuple[str, ...] | None = None,
    reset_attempts: bool = True,
) -> int:
    """Reset selected queue rows to pending for a manual retry."""
    collections = collections or MongoMaterializationCollections()
    allowed_statuses = {"failed", "processing", "complete"}
    selected_statuses = sorted(set(statuses))
    if not selected_statuses:
        raise DQMConfigError("At least one queue status is required")
    unsupported = sorted(set(selected_statuses) - allowed_statuses)
    if unsupported:
        raise DQMConfigError(
            "Queue reset supports statuses: "
            + ", ".join(sorted(allowed_statuses))
            + f"; got {', '.join(unsupported)}"
        )
    query: dict[str, Any] = {"status": {"$in": selected_statuses}}
    if patient_ids:
        query["patient_id"] = {"$in": sorted(set(patient_ids))}
    update: dict[str, Any] = {
        "$set": {
            "status": "pending",
            "processing_started_at": None,
            "processed_at": None,
            "last_error": None,
            "retry_after_at": None,
        }
    }
    if reset_attempts:
        update["$set"]["attempts"] = 0
    result = db[collections.queue].update_many(query, update)
    return int(result.modified_count)


def materialization_status(
    config: MongoMaterializationConfig,
    *,
    limit: int = 5,
) -> dict[str, Any]:
    """Return operational status for Mongo materialization collections."""
    if limit <= 0:
        raise DQMConfigError("status limit must be positive")
    pymongo = require_pymongo()
    with pymongo.MongoClient(config.connection_string) as client:
        db = client[config.materialization_database]
        queue_counts = _count_by_field(db[config.collections.queue], "status")
        result_counts = list(
            db[config.collections.results].aggregate(
                [
                    {"$group": {"_id": {"active": "$active", "status": "$status"}, "count": {"$sum": 1}}},
                    {"$sort": {"_id.active": -1, "_id.status": 1}},
                ]
            )
        )
        report_counts = list(
            db[config.collections.reports].aggregate(
                [
                    {
                        "$group": {
                            "_id": {
                                "active": "$active",
                                "published_to_mongo": "$published_to_mongo",
                            },
                            "count": {"$sum": 1},
                        }
                    },
                    {"$sort": {"_id.active": -1, "_id.published_to_mongo": -1}},
                ]
            )
        )
        runs = list(
            db[config.collections.runs].find(
                {},
                sort=[("started_at", -1)],
                limit=limit,
            )
        )
        measures = list(db[config.collections.measure_config].find({}, sort=[("measure_id", 1)]))

    return {
        "queue": queue_counts,
        "results": [
            {
                "active": bool(row["_id"].get("active")),
                "status": str(row["_id"].get("status")),
                "count": int(row["count"]),
            }
            for row in result_counts
        ],
        "measure_reports": [
            {
                "active": bool(row["_id"].get("active")),
                "published_to_mongo": bool(row["_id"].get("published_to_mongo")),
                "count": int(row["count"]),
            }
            for row in report_counts
        ],
        "latest_runs": [_jsonable_run(row) for row in runs],
        "measures": [
            {
                "measure_id": row.get("measure_id") or row.get("_id"),
                "enabled": bool(row.get("enabled", True)),
                "publish_measure_report_to_mongo": bool(
                    row.get("publish_measure_report_to_mongo", False)
                ),
                "updated_at": _jsonable(row.get("updated_at")),
            }
            for row in measures
        ],
    }


def prune_materialization_history(
    config: MongoMaterializationConfig,
) -> dict[str, int]:
    """Prune old inactive results, audit rows, and unreferenced run rows."""
    pymongo = require_pymongo()
    deleted = {"audits": 0, "inactive_results": 0, "runs": 0}
    now = _utcnow()
    with pymongo.MongoClient(config.connection_string) as client:
        db = client[config.materialization_database]
        if config.retention.audit_days is not None:
            cutoff = now - timedelta(days=config.retention.audit_days)
            result = db[config.collections.audits].delete_many({"created_at": {"$lt": cutoff}})
            deleted["audits"] = int(result.deleted_count)
        if config.retention.inactive_result_days is not None:
            cutoff = now - timedelta(days=config.retention.inactive_result_days)
            result = db[config.collections.results].delete_many(
                {"active": False, "calculated_at": {"$lt": cutoff}}
            )
            deleted["inactive_results"] = int(result.deleted_count)
        if config.retention.run_days is not None:
            cutoff = now - timedelta(days=config.retention.run_days)
            active_run_ids = set(
                db[config.collections.results].distinct("run_id", {"active": True})
            )
            result = db[config.collections.runs].delete_many(
                {
                    "_id": {"$nin": list(active_run_ids)},
                    "$or": [
                        {"completed_at": {"$lt": cutoff}},
                        {"completed_at": None, "started_at": {"$lt": cutoff}},
                    ],
                }
            )
            deleted["runs"] = int(result.deleted_count)
    return deleted


def enqueue_patient_change_from_mongo_change(
    queue: Any,
    config: MongoMaterializationConfig,
    change: dict[str, Any],
) -> bool:
    """Translate one Mongo change-stream event into a patient queue row."""
    spec = _spec_for_change(config, change)
    if spec is None:
        return False
    document = change.get("fullDocument")
    if document is None and config.include_delete_pre_images:
        document = change.get("fullDocumentBeforeChange")
    operation = change.get("operationType")
    if document is None:
        if operation == "delete" and spec.resource_type == "Patient":
            resource_id = _document_key_id(change)
            if resource_id is None:
                return False
            return _enqueue_patient_change(
                queue,
                patient_id=resource_id,
                resource_type="Patient",
                resource_id=resource_id,
            )
        return False

    resource = _extract_resource(document, spec.resource_path)
    if not isinstance(resource, dict):
        return False
    resource_type = str(resource.get("resourceType") or spec.resource_type)
    resource_id = str(resource.get("id") or "")
    if _is_generated_measure_report(resource_type, resource_id, resource):
        return False
    patient_id = _extract_patient_id(resource_type, resource_id, resource)
    if patient_id is None:
        return False
    return _enqueue_patient_change(
        queue,
        patient_id=patient_id,
        resource_type=resource_type,
        resource_id=resource_id,
    )


def publish_measure_report_to_mongo(
    config: MongoMaterializationConfig,
    report: dict[str, Any],
    *,
    client: Any | None = None,
) -> None:
    """Upsert a generated MeasureReport resource into the configured Mongo FHIR store."""
    resource_id = report.get("id")
    if not isinstance(resource_id, str) or not resource_id:
        raise DQMConfigError("Generated MeasureReport is missing a FHIR id")
    spec = _measure_report_collection_spec(config)
    id_key = _json_path_to_mongo_key(spec.id_path)
    if not id_key:
        raise DQMConfigError("MeasureReport id_path must not be '$' for Mongo publishing")
    update_set = _resource_update_for_path(spec.resource_path, report)
    owns_client = client is None
    if owns_client:
        pymongo = require_pymongo()
        client = pymongo.MongoClient(config.connection_string)
    try:
        collection = client[config.source_database_name][spec.collection_name]
        collection.update_one(
            {id_key: resource_id},
            {"$set": update_set, "$setOnInsert": {"created_at": _utcnow()}},
            upsert=True,
        )
    finally:
        if owns_client:
            client.close()


def load_enabled_measure_config(
    db: Any,
    *,
    collections: MongoMaterializationCollections | None = None,
) -> list[MongoMaterializedMeasure]:
    """Load enabled materialized measure configuration from Mongo."""
    collections = collections or MongoMaterializationCollections()
    rows = db[collections.measure_config].find({"enabled": True}, sort=[("measure_id", 1)])
    measures: list[MongoMaterializedMeasure] = []
    for row in rows:
        measures.append(
            MongoMaterializedMeasure(
                measure_id=str(row["measure_id"]),
                measure_version=row.get("measure_version"),
                measure_path=Path(row["measure_path"]) if row.get("measure_path") else None,
                cql_path=Path(row["cql_path"]) if row.get("cql_path") else None,
                library_paths=[Path(path) for path in row.get("library_paths", [])],
                valueset_paths=[Path(path) for path in row.get("valueset_paths", [])],
                parameters=dict(row.get("parameters") or {}),
                tags=list(row.get("tags") or []),
                audit_mode=AuditMode(row.get("audit_mode", "none")),
                persist_audit=bool(row.get("persist_audit", False)),
                persist_measure_report=bool(row.get("persist_measure_report", False)),
                publish_measure_report_to_mongo=bool(
                    row.get("publish_measure_report_to_mongo", False)
                ),
                generate_narratives=bool(row.get("generate_narratives", False)),
                include_supporting_evidence=bool(
                    row.get("include_supporting_evidence", False)
                ),
                filter_to_ip=bool(row.get("filter_to_ip", False)),
            )
        )
    return measures


def start_measure_run(
    db: Any,
    *,
    collections: MongoMaterializationCollections,
    patient_count: int,
    measure_count: int,
    trigger_reason: str,
) -> str:
    row = {
        "started_at": _utcnow(),
        "completed_at": None,
        "status": "running",
        "trigger_reason": trigger_reason,
        "patient_count": patient_count,
        "measure_count": measure_count,
        "metrics_json": {},
        "error": None,
    }
    result = db[collections.runs].insert_one(row)
    return str(result.inserted_id)


def complete_measure_run(
    db: Any,
    run_id: str,
    *,
    collections: MongoMaterializationCollections,
    status: str,
    error: str | None = None,
    metrics: dict[str, Any] | None = None,
) -> None:
    metrics = metrics or {}
    db[collections.runs].update_one(
        {"_id": _object_id_or_str(run_id)},
        {
            "$set": {
                "status": status,
                "completed_at": _utcnow(),
                "error": error,
                "compile_cache_hits": int(metrics.get("cache_hits", 0) or 0),
                "compile_cache_misses": int(metrics.get("cache_misses", 0) or 0),
                "compile_count": int(metrics.get("compile_count", 0) or 0),
                "compile_ms": float(metrics.get("compile_ms", 0.0) or 0.0),
                "execute_count": int(metrics.get("execute_count", 0) or 0),
                "execute_ms": float(metrics.get("execute_ms", 0.0) or 0.0),
                "prepared_count": int(metrics.get("prepared_count", 0) or 0),
                "prepared_fallback_count": int(
                    metrics.get("prepared_fallback_count", 0) or 0
                ),
                "metrics_json": metrics,
            }
        },
    )


def mark_patient_complete(
    db: Any,
    patient_id: str,
    *,
    collections: MongoMaterializationCollections,
) -> None:
    db[collections.queue].update_one(
        {"patient_id": patient_id},
        {
            "$set": {
                "status": "complete",
                "processed_at": _utcnow(),
                "processing_started_at": None,
                "last_error": None,
                "retry_after_at": None,
            }
        },
    )


def mark_patient_failed(
    db: Any,
    patient_id: str,
    error: str,
    *,
    collections: MongoMaterializationCollections,
    max_attempts: int,
    retry_backoff_seconds: float,
) -> None:
    row = db[collections.queue].find_one({"patient_id": patient_id}) or {}
    attempts = int(row.get("attempts", 0) or 0)
    status = "failed"
    retry_after = None
    if attempts < max_attempts:
        retry_after = _utcnow() + timedelta(
            seconds=retry_backoff_seconds * max(attempts, 1)
        )
    db[collections.queue].update_one(
        {"patient_id": patient_id},
        {
            "$set": {
                "status": status,
                "processed_at": _utcnow(),
                "processing_started_at": None,
                "last_error": error,
                "retry_after_at": retry_after,
            }
        },
    )


def persist_patient_measure_result(
    db: Any,
    *,
    collections: MongoMaterializationCollections,
    run_id: str,
    patient_id: str,
    measure: MongoMaterializedMeasure,
    status: str,
    result_json: dict[str, Any] | None,
    summary_json: dict[str, Any] | None,
    input_watermark: datetime | None,
    config_hash: str,
    measure_report_json: dict[str, Any] | None = None,
    measure_report_published_to_mongo: bool = False,
    error: str | None = None,
    audit_json: dict[str, Any] | None = None,
) -> str:
    """Deactivate previous active result and insert a new result document."""
    now = _utcnow()
    db[collections.results].update_many(
        {"patient_id": patient_id, "measure_id": measure.measure_id, "active": True},
        {"$set": {"active": False}},
    )
    db[collections.reports].update_many(
        {"patient_id": patient_id, "measure_id": measure.measure_id, "active": True},
        {"$set": {"active": False}},
    )
    result_doc = {
        "run_id": run_id,
        "patient_id": patient_id,
        "measure_id": measure.measure_id,
        "measure_version": measure.measure_version,
        "calculated_at": now,
        "active": True,
        "status": status,
        "result_json": result_json,
        "summary_json": summary_json,
        "measure_report_json": measure_report_json,
        "input_watermark": input_watermark,
        "config_hash": config_hash,
        "error": error,
    }
    inserted = db[collections.results].insert_one(result_doc)
    result_id = str(inserted.inserted_id)
    if measure_report_json is not None:
        measure_report_id = measure_report_json.get("id")
        if not isinstance(measure_report_id, str) or not measure_report_id:
            raise DQMConfigError("Persisted MeasureReport JSON is missing a FHIR id")
        db[collections.reports].insert_one(
            {
                "result_id": result_id,
                "run_id": run_id,
                "patient_id": patient_id,
                "measure_id": measure.measure_id,
                "measure_version": measure.measure_version,
                "measure_report_id": measure_report_id,
                "calculated_at": now,
                "active": True,
                "resource_json": measure_report_json,
                "published_to_mongo": measure_report_published_to_mongo,
                "config_hash": config_hash,
            }
        )
    if audit_json is not None:
        audit_text = json.dumps(audit_json, default=str)
        db[collections.audits].insert_one(
            {
                "result_id": result_id,
                "created_at": now,
                "audit_json": audit_json,
                "size_bytes": len(audit_text.encode("utf-8")),
            }
        )
    return result_id


def materialized_measure_hash(measure: MongoMaterializedMeasure) -> str:
    """Hash measure configuration fields that affect materialized results."""
    payload = {
        "measure_id": measure.measure_id,
        "measure_version": measure.measure_version,
        "measure_path": str(measure.measure_path) if measure.measure_path else None,
        "cql_path": str(measure.cql_path) if measure.cql_path else None,
        "library_paths": [str(path) for path in measure.library_paths],
        "valueset_paths": [str(path) for path in measure.valueset_paths],
        "parameters": measure.parameters,
        "audit_mode": measure.audit_mode.value,
        "persist_measure_report": measure.persist_measure_report,
        "publish_measure_report_to_mongo": measure.publish_measure_report_to_mongo,
        "generate_narratives": measure.generate_narratives,
        "include_supporting_evidence": measure.include_supporting_evidence,
        "filter_to_ip": measure.filter_to_ip,
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()


def split_patient_result_rows(rows: list[dict[str, Any]]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Return compact result JSON and full audit JSON for patient result rows."""
    compact_rows = [_compact_row(row) for row in rows]
    full_rows = [_jsonable(row) for row in rows]
    return {"rows": compact_rows}, {"rows": full_rows}


def _process_claimed_patients(
    db: Any,
    config: MongoMaterializationConfig,
    run_id: str,
    patients: list[ClaimedPatient],
    measures: list[MongoMaterializedMeasure],
    errors: dict[str, str],
    runtime: MongoMaterializationRuntime | None = None,
) -> dict[str, Any]:
    if runtime is None:
        with MongoMaterializationRuntime.open(config) as owned_runtime:
            return _process_claimed_patients(
                db,
                config,
                run_id,
                patients,
                measures,
                errors,
                runtime=owned_runtime,
            )

    patient_ids = [patient.patient_id for patient in patients]
    watermark_by_patient = {
        patient.patient_id: patient.input_watermark for patient in patients
    }
    _apply_source_patient_scope(runtime, config, patient_ids)
    patient_errors: dict[str, str] = {}
    evaluator = runtime.evaluator
    for measure in measures:
        try:
            result = _evaluate_materialized_measure(
                runtime,
                config,
                measure,
                patient_ids,
            )
            _persist_successful_measure(
                db,
                evaluator,
                config,
                run_id,
                patients,
                measure,
                result,
                watermark_by_patient,
            )
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"
            errors[measure.measure_id] = error
            for patient_id in patient_ids:
                patient_errors[patient_id] = error
                persist_patient_measure_result(
                    db,
                    collections=config.collections,
                    run_id=run_id,
                    patient_id=patient_id,
                    measure=measure,
                    status="error",
                    result_json=None,
                    summary_json=None,
                    input_watermark=watermark_by_patient.get(patient_id),
                    config_hash=materialized_measure_hash(measure),
                    error=error,
                )
    metrics = evaluator.compiled_measure_metrics()

    for patient in patients:
        error = patient_errors.get(patient.patient_id)
        if error:
            mark_patient_failed(
                db,
                patient.patient_id,
                error,
                collections=config.collections,
                max_attempts=config.max_attempts,
                retry_backoff_seconds=config.retry_backoff_seconds,
            )
        else:
            mark_patient_complete(
                db,
                patient.patient_id,
                collections=config.collections,
            )
    return metrics


def _apply_source_patient_scope(
    runtime: MongoMaterializationRuntime,
    config: MongoMaterializationConfig,
    patient_ids: list[str],
) -> None:
    if config.source_patient_pushdown:
        runtime.source.set_patient_scope(patient_ids)
    else:
        runtime.source.clear_patient_scope()
    runtime.evaluator.invalidate_prepared_statements()


def _evaluate_materialized_measure(
    runtime: MongoMaterializationRuntime,
    config: MongoMaterializationConfig,
    measure: MongoMaterializedMeasure,
    patient_ids: list[str],
) -> MeasureResult:
    evaluator = runtime.evaluator
    parameters = dict(config.parameters)
    parameters.update(measure.parameters)
    if measure.measure_path is None:
        raise DQMConfigError(
            f"Measure path is required for Mongo materialization: {measure.measure_id}"
        )
    cql_path = measure.cql_path or _resolve_cql_path(
        MeasureSpec(path=measure.measure_path, cql=None, id=measure.measure_id),
        [*config.library_paths, *measure.library_paths],
    )
    resolver = FileArtifactResolver(
        include_paths=[*config.library_paths, *measure.library_paths],
        valueset_paths=[*config.valueset_paths, *measure.valueset_paths],
    )
    compiled = evaluator.compile_measure(
        measure_bundle=measure.measure_path,
        cql_library_path=cql_path,
        artifact_resolver=resolver,
        parameters=parameters,
        audit_mode=measure.audit_mode,
        filter_to_ip=measure.filter_to_ip,
        patient_scope="target_table",
        generate_narratives=measure.generate_narratives,
        include_supporting_evidence=measure.include_supporting_evidence
        or measure.persist_audit,
    )
    return evaluator.execute_compiled_measure(compiled, patient_ids=patient_ids)


def _persist_successful_measure(
    db: Any,
    evaluator: MeasureEvaluator,
    config: MongoMaterializationConfig,
    run_id: str,
    patients: list[ClaimedPatient],
    measure: MongoMaterializedMeasure,
    result: MeasureResult,
    watermark_by_patient: dict[str, datetime | None],
) -> None:
    df = result.dataframe
    rows = df.to_dict("records") if "patient_id" in df.columns else []
    rows_by_patient: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        patient_id = str(row.get("patient_id"))
        rows_by_patient.setdefault(patient_id, []).append(row)

    config_hash = materialized_measure_hash(measure)
    for patient in patients:
        patient_rows = rows_by_patient.get(patient.patient_id, [])
        if not patient_rows:
            persist_patient_measure_result(
                db,
                collections=config.collections,
                run_id=run_id,
                patient_id=patient.patient_id,
                measure=measure,
                status="no_result",
                result_json={"rows": []},
                summary_json={"total_patients": 0},
                input_watermark=watermark_by_patient.get(patient.patient_id),
                config_hash=config_hash,
            )
            continue

        result_json, audit_json = split_patient_result_rows(patient_rows)
        patient_result = MeasureResult(
            dataframe=df[df["patient_id"].astype(str) == patient.patient_id],
            populations=result.populations,
            parameters=result.parameters,
            measure_url=result.measure_url,
            pop_map=result.pop_map,
        )
        summary = evaluator.summary_report(patient_result)
        measure_report_json = None
        if measure.persist_measure_report or measure.publish_measure_report_to_mongo:
            measure_report_json = evaluator.to_measure_report(
                patient_result,
                report_type="individual",
            )
            measure_report_json = _prepare_measure_report_for_materialization(
                measure_report_json,
                measure=measure,
                patient_id=patient.patient_id,
            )
        if measure.publish_measure_report_to_mongo and measure_report_json is not None:
            publish_measure_report_to_mongo(config, measure_report_json)
            measure_report_published_to_mongo = True
        else:
            measure_report_published_to_mongo = False
        persist_patient_measure_result(
            db,
            collections=config.collections,
            run_id=run_id,
            patient_id=patient.patient_id,
            measure=measure,
            status="ok",
            result_json=result_json,
            summary_json=summary,
            measure_report_json=measure_report_json,
            measure_report_published_to_mongo=measure_report_published_to_mongo,
            input_watermark=watermark_by_patient.get(patient.patient_id),
            config_hash=config_hash,
            audit_json=audit_json if measure.persist_audit else None,
        )


def _prepare_measure_report_for_materialization(
    report: dict[str, Any],
    *,
    measure: MongoMaterializedMeasure,
    patient_id: str,
) -> dict[str, Any]:
    report["id"] = _measure_report_id(measure.measure_id, patient_id)
    meta = report.setdefault("meta", {})
    tags = meta.setdefault("tag", [])
    _append_unique_dict(
        tags,
        {
            "system": FHIR4DS_MATERIALIZATION_TAG_SYSTEM,
            "code": FHIR4DS_MEASURE_REPORT_TAG_CODE,
            "display": "FHIR4DS generated MeasureReport",
        },
        keys=("system", "code"),
    )
    identifiers = report.setdefault("identifier", [])
    _append_unique_dict(
        identifiers,
        {
            "system": FHIR4DS_MEASURE_REPORT_IDENTIFIER_SYSTEM,
            "value": f"{measure.measure_id}|{patient_id}",
        },
        keys=("system", "value"),
    )
    return report


def _measure_report_id(measure_id: str, patient_id: str) -> str:
    measure_slug = re.sub(r"[^A-Za-z0-9.-]+", "-", measure_id).strip(".-")
    measure_slug = measure_slug[:20] or "measure"
    digest = hashlib.sha256(f"{measure_id}|{patient_id}".encode()).hexdigest()
    return f"fhir4ds-{measure_slug}-{digest[:32]}"


def _append_unique_dict(
    items: list[Any],
    item: dict[str, Any],
    *,
    keys: tuple[str, ...],
) -> None:
    for existing in items:
        if not isinstance(existing, dict):
            continue
        if all(existing.get(key) == item.get(key) for key in keys):
            return
    items.append(item)


def _parse_source_schema(raw: Any, database_name: str) -> MongoFhirServerSchema:
    if raw is None:
        return MongoFhirServerSchema(database_name=database_name)
    if not isinstance(raw, dict):
        raise DQMConfigError("'mongo.source_schema' must be an object")
    collections_raw = raw.get("collections")
    collections = None
    if collections_raw is not None:
        if not isinstance(collections_raw, list):
            raise DQMConfigError("'mongo.source_schema.collections' must be a list")
        collections = tuple(_parse_resource_collection(item) for item in collections_raw)
    return MongoFhirServerSchema(
        database_name=str(raw.get("database_name", database_name)),
        base_version=str(raw.get("base_version", _DEFAULT_BASE_VERSION)),
        collection_strategy=str(raw.get("collection_strategy", "per_resource")),
        resource_types=tuple(raw["resource_types"]) if raw.get("resource_types") else None,
        collections=collections,
        collection_mappings=raw.get("collection_mappings"),
        shared_collection=raw.get("shared_collection"),
        shared_resource_path=str(raw.get("shared_resource_path", "$")),
        shared_id_path=str(raw.get("shared_id_path", "$.id")),
        shared_resource_type_path=str(
            raw.get("shared_resource_type_path", "$.resourceType")
        ),
        shared_current_filter=raw.get("shared_current_filter"),
        shared_deleted_filter=raw.get("shared_deleted_filter"),
        sample_size=raw.get("sample_size", -1),
        include_hidden=bool(raw.get("include_hidden", False)),
        hidden_tag_system=str(raw.get("hidden_tag_system", _DEFAULT_HIDDEN_TAG_SYSTEM)),
        hidden_tag_code=str(raw.get("hidden_tag_code", _DEFAULT_HIDDEN_TAG_CODE)),
        patient_reference_paths=tuple(
            raw.get(
                "patient_reference_paths",
                (
                    "$.subject.reference",
                    "$.patient.reference",
                    "$.beneficiary.reference",
                ),
            )
        ),
        scrub_private_fields=tuple(
            raw.get(
                "scrub_private_fields",
                (
                    "_id",
                    "_uuid",
                    "_sourceId",
                    "_sourceAssigningAuthority",
                ),
            )
        ),
    )


def _parse_resource_collection(raw: Any) -> MongoResourceCollection:
    if not isinstance(raw, dict):
        raise DQMConfigError("Mongo resource collection entries must be objects")
    return MongoResourceCollection(
        resource_type=str(raw["resource_type"]),
        collection_name=str(raw["collection_name"]),
        resource_path=str(raw.get("resource_path", "$")),
        id_path=str(raw.get("id_path", "$.id")),
        resource_type_path=str(raw.get("resource_type_path", "$.resourceType")),
        current_filter=raw.get("current_filter"),
        deleted_filter=raw.get("deleted_filter"),
    )


def _parse_materialization_collections(raw: Any) -> MongoMaterializationCollections:
    if raw is None:
        return MongoMaterializationCollections()
    if not isinstance(raw, dict):
        raise DQMConfigError("'mongo.collections' must be an object")
    allowed = {
        "queue",
        "measure_config",
        "runs",
        "results",
        "reports",
        "audits",
    }
    unknown = sorted(set(raw) - allowed)
    if unknown:
        raise DQMConfigError(
            "Unknown mongo.collections field(s): " + ", ".join(unknown)
        )
    return MongoMaterializationCollections(**raw)


def _parse_materialized_measures(
    raw: Any,
    *,
    base: Path,
    defaults: dict[str, Any],
    results: dict[str, Any],
) -> list[MongoMaterializedMeasure]:
    if raw in (None, []):
        return []
    if not isinstance(raw, list):
        raise DQMConfigError("'measures' must be a list")
    measures: list[MongoMaterializedMeasure] = []
    for index, item in enumerate(raw):
        if not isinstance(item, dict):
            raise DQMConfigError(f"measures[{index}] must be an object")
        path = item.get("path")
        if not isinstance(path, str) or not path:
            raise DQMConfigError(f"measures[{index}].path is required")
        measure_path = _resolve_path(path, base)
        cql_path = _resolve_path(item["cql"], base) if item.get("cql") else None
        measure_id = item.get("id") or measure_path.stem.replace("Measure-", "")
        if not isinstance(measure_id, str) or not measure_id:
            raise DQMConfigError(f"measures[{index}].id must be a string")
        publish_measure_report = bool(
            item.get(
                "publish_measure_report_to_mongo",
                results.get("publish_measure_report_to_mongo", False),
            )
        )
        persist_measure_report = bool(
            item.get(
                "persist_measure_report",
                results.get("persist_measure_report", False),
            )
        ) or publish_measure_report
        measures.append(
            MongoMaterializedMeasure(
                measure_id=measure_id,
                measure_path=measure_path,
                cql_path=cql_path,
                enabled=bool(item.get("enabled", True)),
                measure_version=item.get("version"),
                library_paths=_parse_paths(item.get("libraries", []), base),
                valueset_paths=_parse_paths(item.get("valuesets", []), base),
                parameters=dict(item.get("parameters") or {}),
                tags=list(item.get("tags") or []),
                audit_mode=AuditMode(
                    item.get("audit_mode", defaults.get("audit_mode", "none"))
                ),
                persist_audit=bool(
                    item.get("persist_audit", results.get("persist_audit", False))
                ),
                persist_measure_report=persist_measure_report,
                publish_measure_report_to_mongo=publish_measure_report,
                generate_narratives=bool(
                    item.get("narratives", defaults.get("narratives", False))
                ),
                include_supporting_evidence=bool(
                    item.get(
                        "include_supporting_evidence",
                        defaults.get("include_supporting_evidence", False),
                    )
                ),
                filter_to_ip=bool(
                    item.get("filter_to_ip", defaults.get("filter_to_ip", False))
                ),
            )
        )
    return measures


def _parse_paths(raw: Any, base: Path) -> list[Path]:
    if raw in (None, []):
        return []
    if isinstance(raw, str):
        raw = [raw]
    if not isinstance(raw, list):
        raise DQMConfigError("path fields must be a string or list of strings")
    paths = []
    for value in raw:
        if not isinstance(value, str) or not value:
            raise DQMConfigError("path values must be non-empty strings")
        paths.append(_resolve_path(value, base))
    return paths


def _parse_section_paths(raw: Any, section: str, field: str, base: Path) -> list[Path]:
    if raw is None:
        return []
    if not isinstance(raw, dict):
        raise DQMConfigError(f"'{section}' must be an object")
    return _parse_paths(raw.get(field, []), base)


def _resolve_path(value: str, base: Path) -> Path:
    path = Path(value)
    if not path.is_absolute():
        path = base / path
    return path


def _parse_retention_policy(raw: dict[str, Any]) -> MongoRetentionPolicy:
    return MongoRetentionPolicy(
        inactive_result_days=_parse_optional_positive_int(
            raw.get("inactive_result_days"),
            "retention.inactive_result_days",
        ),
        audit_days=_parse_optional_positive_int(raw.get("audit_days"), "retention.audit_days"),
        run_days=_parse_optional_positive_int(raw.get("run_days"), "retention.run_days"),
    )


def _parse_optional_positive_int(value: Any, name: str) -> int | None:
    if value is None:
        return None
    parsed = int(value)
    if parsed <= 0:
        raise DQMConfigError(f"{name} must be positive")
    return parsed


def _expand_env_refs(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _expand_env_refs(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_expand_env_refs(item) for item in value]
    if isinstance(value, str):
        import os

        def replace(match: re.Match[str]) -> str:
            name = match.group(1)
            default = match.group(2)
            if name in os.environ:
                return os.environ[name]
            if default is not None:
                return default
            raise DQMConfigError(
                f"Environment variable '{name}' is required by Mongo materialization config"
            )

        return _ENV_REF_RE.sub(replace, value)
    return value


def _open_change_stream(db: Any, config: MongoMaterializationConfig) -> Any:
    specs = _configured_collection_specs(config)
    collection_names = sorted({spec.collection_name for spec in specs})
    pipeline = [
        {
            "$match": {
                "operationType": {"$in": ["insert", "replace", "update", "delete"]},
                "ns.coll": {"$in": collection_names},
            }
        }
    ]
    kwargs: dict[str, Any] = {
        "pipeline": pipeline,
        "full_document": "updateLookup",
        "max_await_time_ms": 1000,
    }
    if config.include_delete_pre_images:
        kwargs["full_document_before_change"] = "whenAvailable"
    return db.watch(**kwargs)


def _configured_collection_specs(
    config: MongoMaterializationConfig,
) -> tuple[MongoResourceCollection, ...]:
    source = MongoFhirServerSource(
        config.connection_string,
        schema=config.source_schema,
        install_extension=False,
    )
    specs = source._collection_specs()
    if specs is None:
        raise DQMConfigError(
            "Mongo materialization requires explicit source_schema.resource_types, "
            "collections, or collection_mappings; catalog discovery is not supported "
            "for change streams."
        )
    return specs


def _spec_for_change(
    config: MongoMaterializationConfig,
    change: dict[str, Any],
) -> MongoResourceCollection | None:
    collection_name = (change.get("ns") or {}).get("coll")
    if not collection_name:
        return None
    for spec in _configured_collection_specs(config):
        if spec.collection_name == collection_name:
            return spec
    return None


def _measure_report_collection_spec(config: MongoMaterializationConfig) -> MongoResourceCollection:
    source = MongoFhirServerSource(
        config.connection_string,
        schema=config.source_schema,
        install_extension=False,
    )
    specs = source._collection_specs()
    if specs:
        for spec in specs:
            if spec.resource_type == "MeasureReport":
                return spec
    schema = config.source_schema
    if schema.collection_strategy == "per_resource":
        return MongoResourceCollection(
            resource_type="MeasureReport",
            collection_name=f"MeasureReport_{schema.base_version}",
        )
    if schema.collection_strategy == "shared" and schema.shared_collection is not None:
        return MongoResourceCollection(
            resource_type="MeasureReport",
            collection_name=schema.shared_collection,
            resource_path=schema.shared_resource_path,
            id_path=schema.shared_id_path,
            resource_type_path=schema.shared_resource_type_path,
        )
    raise DQMConfigError(
        "Publishing MeasureReport to Mongo requires source_schema to include "
        "MeasureReport or use per_resource/shared collection strategy."
    )


def _enqueue_patient_change(
    queue: Any,
    *,
    patient_id: str,
    resource_type: str | None,
    resource_id: str | None,
    seen_at: datetime | None = None,
) -> bool:
    if not patient_id:
        return False
    now = seen_at or _utcnow()
    queue.update_one(
        {"_id": patient_id},
        {
            "$set": {
                "patient_id": patient_id,
                "last_seen_at": now,
                "status": "pending",
                "processed_at": None,
                "last_error": None,
                "last_resource_type": resource_type,
                "last_resource_id": resource_id,
            },
            "$setOnInsert": {
                "first_seen_at": now,
                "attempts": 0,
                "processing_started_at": None,
            },
            "$inc": {"notify_count": 1},
        },
        upsert=True,
    )
    return True


def _extract_patient_id(
    resource_type: str,
    resource_id: str,
    resource: dict[str, Any],
) -> str | None:
    if resource_type == "Patient":
        return resource_id or None
    for path in ("subject", "patient", "beneficiary"):
        ref = resource.get(path)
        if isinstance(ref, dict):
            ref_text = ref.get("reference")
            patient_id = _patient_id_from_reference(ref_text)
            if patient_id is not None:
                return patient_id
    return None


def _patient_id_from_reference(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    for pattern in (r"^Patient/([^/?#]+)$", r"^https?://.*/Patient/([^/?#]+)$"):
        match = re.match(pattern, value)
        if match:
            return match.group(1)
    return None


def _is_generated_measure_report(
    resource_type: str,
    resource_id: str,
    resource: dict[str, Any],
) -> bool:
    if resource_type != "MeasureReport":
        return False
    if resource_id.startswith("fhir4ds-"):
        return True
    for tag in ((resource.get("meta") or {}).get("tag") or []):
        if not isinstance(tag, dict):
            continue
        if (
            tag.get("system") == FHIR4DS_MATERIALIZATION_TAG_SYSTEM
            and tag.get("code") == FHIR4DS_MEASURE_REPORT_TAG_CODE
        ):
            return True
    return False


def _extract_resource(document: dict[str, Any], resource_path: str) -> Any:
    if resource_path == "$":
        return document
    current: Any = document
    for part in resource_path[2:].split("."):
        if not isinstance(current, dict):
            return None
        current = current.get(part)
    return current


def _resource_update_for_path(resource_path: str, resource: dict[str, Any]) -> dict[str, Any]:
    if resource_path == "$":
        return dict(resource)
    return {_json_path_to_mongo_key(resource_path): dict(resource)}


def _document_key_id(change: dict[str, Any]) -> str | None:
    key = change.get("documentKey")
    if not isinstance(key, dict):
        return None
    value = key.get("id") or key.get("_id")
    return str(value) if value is not None else None


def _compact_row(row: dict[str, Any]) -> dict[str, Any]:
    compact = {}
    for key, value in row.items():
        if key == "patient_id":
            compact[key] = _jsonable(value)
        elif isinstance(value, dict) and "result" in value:
            compact[key] = _jsonable(value.get("result"))
        elif key.startswith("evidence_") or key.endswith("_evidence") or key.endswith("_narrative"):
            continue
        else:
            compact[key] = _jsonable(value)
    return compact


def _jsonable(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if hasattr(value, "item"):
        try:
            return value.item()
        except Exception:
            pass
    if isinstance(value, dict):
        return {key: _jsonable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    return value


def _jsonable_run(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "run_id": str(row.get("_id")),
        "status": row.get("status"),
        "started_at": _jsonable(row.get("started_at")),
        "completed_at": _jsonable(row.get("completed_at")),
        "patient_count": int(row.get("patient_count", 0) or 0),
        "measure_count": int(row.get("measure_count", 0) or 0),
        "compile_cache_hits": int(row.get("compile_cache_hits", 0) or 0),
        "compile_cache_misses": int(row.get("compile_cache_misses", 0) or 0),
        "prepared_count": int(row.get("prepared_count", 0) or 0),
        "prepared_fallback_count": int(row.get("prepared_fallback_count", 0) or 0),
        "error": row.get("error"),
    }


def _count_by_field(collection: Any, field_name: str) -> dict[str, int]:
    rows = collection.aggregate(
        [{"$group": {"_id": f"${field_name}", "count": {"$sum": 1}}}]
    )
    return {str(row["_id"]): int(row["count"]) for row in rows}


def _compiled_metrics_delta(
    before: dict[str, Any] | None,
    after: dict[str, Any] | None,
) -> dict[str, Any]:
    if after is None:
        return {}
    if before is None:
        return dict(after)
    delta = {}
    for key, value in after.items():
        if isinstance(value, (int, float)) and isinstance(before.get(key), (int, float)):
            delta[key] = value - before[key]
        else:
            delta[key] = value
    delta["cumulative"] = after
    return delta


def _object_id_or_str(value: str) -> Any:
    try:
        from bson import ObjectId  # type: ignore[import-not-found]

        if ObjectId.is_valid(value):
            return ObjectId(value)
    except Exception:
        pass
    return value


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _install_shutdown_handlers() -> tuple[dict[str, bool], dict[int, Any]]:
    state = {"requested": False}
    old_handlers: dict[int, Any] = {}

    def handler(signum: int, frame: Any) -> None:
        state["requested"] = True

    for signum in (signal.SIGINT, signal.SIGTERM):
        old_handlers[signum] = signal.getsignal(signum)
        signal.signal(signum, handler)
    return state, old_handlers


def _restore_shutdown_handlers(old_handlers: dict[int, Any]) -> None:
    for signum, handler in old_handlers.items():
        signal.signal(signum, handler)
