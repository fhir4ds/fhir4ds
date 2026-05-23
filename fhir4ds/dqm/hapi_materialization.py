"""HAPI PostgreSQL change queue and DQM result materialization."""

from __future__ import annotations

import hashlib
import json
import logging
import re
import signal
import time
from dataclasses import dataclass, field
from datetime import datetime
from importlib import resources
from pathlib import Path
from typing import Any

import fhir4ds
from fhir4ds.dqm.batch import _load_valuesets, _resolve_cql_path
from fhir4ds.dqm.config import DQMConfigError, MeasureSpec
from fhir4ds.dqm.evaluator import MeasureEvaluator
from fhir4ds.dqm.models import MeasureResult
from fhir4ds.dqm.types import AuditMode
from fhir4ds.sources import HapiPostgresSchema, HapiPostgresSource
from fhir4ds.sources.base import quote_identifier, quote_sql_literal

NOTIFICATION_CHANNEL = "fhir4ds_patient_changed"
DEFAULT_DECODED_VIEW = "fhir4ds_hapi_current_resources"
_PG_CHANNEL_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
logger = logging.getLogger(__name__)


@dataclass
class HapiMaterializedMeasure:
    """One measure configured for HAPI queue materialization."""

    measure_id: str
    measure_path: Path
    cql_path: Path | None = None
    enabled: bool = True
    measure_version: str | None = None
    library_paths: list[Path] = field(default_factory=list)
    valueset_paths: list[Path] = field(default_factory=list)
    parameters: dict[str, Any] = field(default_factory=dict)
    tags: list[str] = field(default_factory=list)
    audit_mode: AuditMode = AuditMode.NONE
    persist_audit: bool = False
    generate_narratives: bool = False
    include_supporting_evidence: bool = False
    filter_to_ip: bool = False


@dataclass
class HapiRetentionPolicy:
    """Retention windows for materialized HAPI measure history."""

    inactive_result_days: int | None = None
    audit_days: int | None = None
    run_days: int | None = None


@dataclass
class HapiMaterializationConfig:
    """Configuration for the HAPI materialization worker."""

    postgres_connection_string: str
    hapi_connection_string: str | None = None
    measures: list[HapiMaterializedMeasure] = field(default_factory=list)
    parameters: dict[str, Any] = field(default_factory=dict)
    library_paths: list[Path] = field(default_factory=list)
    valueset_paths: list[Path] = field(default_factory=list)
    batch_size: int = 100
    poll_interval_seconds: float = 30.0
    max_attempts: int = 3
    retry_backoff_seconds: float = 60.0
    processing_timeout_seconds: float = 900.0
    notification_channel: str = NOTIFICATION_CHANNEL
    fail_on_unsupported_storage: bool = True
    hapi_schema: HapiPostgresSchema = field(default_factory=HapiPostgresSchema)
    retention: HapiRetentionPolicy = field(default_factory=HapiRetentionPolicy)

    @property
    def hapi_source_connection_string(self) -> str:
        return self.hapi_connection_string or self.postgres_connection_string


@dataclass
class ClaimedPatient:
    """One patient claimed from the durable queue."""

    patient_id: str
    input_watermark: datetime | None = None


@dataclass
class QueueProcessResult:
    """Summary of one queue-processing pass."""

    run_id: int | None
    claimed: list[str]
    measures: int
    stale_reset: int = 0
    errors: dict[str, str] = field(default_factory=dict)
    metrics: dict[str, Any] = field(default_factory=dict)


@dataclass
class HapiMaterializationRuntime:
    """Long-lived DuckDB runtime for a HAPI materialization worker."""

    duck_conn: Any
    source: HapiPostgresSource
    evaluator: MeasureEvaluator
    loaded_valueset_keys: set[tuple[str, ...]] = field(default_factory=set)

    @classmethod
    def open(cls, config: HapiMaterializationConfig) -> HapiMaterializationRuntime:
        duck_conn = fhir4ds.create_connection()
        source = HapiPostgresSource(
            config.hapi_source_connection_string,
            schema=config.hapi_schema,
            fail_on_unsupported_storage=config.fail_on_unsupported_storage,
        )
        try:
            source.register(duck_conn)
            runtime = cls(
                duck_conn=duck_conn,
                source=source,
                evaluator=MeasureEvaluator(duck_conn),
            )
            runtime.load_valuesets_once(config.valueset_paths)
            return runtime
        except Exception:
            source.unregister(duck_conn)
            duck_conn.close()
            raise

    def load_valuesets_once(self, paths: list[Path]) -> None:
        key = tuple(sorted(str(path) for path in paths))
        if key in self.loaded_valueset_keys:
            return
        _load_valuesets(self.duck_conn, paths)
        self.loaded_valueset_keys.add(key)

    def close(self) -> None:
        self.source.unregister(self.duck_conn)
        self.duck_conn.close()

    def __enter__(self) -> HapiMaterializationRuntime:
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        self.close()


def require_psycopg() -> Any:
    """Import psycopg with an actionable error for optional HAPI worker usage."""
    try:
        import psycopg  # type: ignore[import-not-found]
    except ImportError as exc:  # pragma: no cover - depends on optional extra
        raise DQMConfigError(
            "HAPI materialization requires psycopg. Install with "
            "`pip install 'fhir4ds-v2[hapi]'` or install `psycopg[binary]`."
        ) from exc
    return psycopg


def materialization_sql(
    schema: HapiPostgresSchema | None = None,
    *,
    notification_channel: str = NOTIFICATION_CHANNEL,
    decoded_view: str | None = None,
) -> str:
    """Return rendered PostgreSQL schema/trigger SQL for HAPI materialization."""
    hapi_schema = schema or HapiPostgresSchema()
    view_name = decoded_view or hapi_schema.decoded_view or DEFAULT_DECODED_VIEW
    channel = _validate_notification_channel(notification_channel)
    template = (
        resources.files("fhir4ds.dqm.sql")
        .joinpath("hapi_postgres_materialization.sql")
        .read_text()
    )
    rendered = _render_materialization_sql(
        template,
        schema=hapi_schema,
        notification_channel=channel,
        decoded_view=view_name,
    )
    leftovers = sorted(set(re.findall(r"\{\{[A-Z0-9_]+\}\}", rendered)))
    if leftovers:
        raise RuntimeError(
            "Unrendered HAPI materialization SQL placeholder(s): "
            + ", ".join(leftovers)
        )
    return rendered


def install_materialization_schema(
    connection_string: str,
    *,
    schema: HapiPostgresSchema | None = None,
    notification_channel: str = NOTIFICATION_CHANNEL,
) -> None:
    """Install FHIR4DS queue/result tables and HAPI change triggers."""
    psycopg = require_psycopg()
    with psycopg.connect(connection_string, autocommit=True) as conn:
        conn.execute(
            materialization_sql(
                schema=schema,
                notification_channel=notification_channel,
            )
        )


def load_materialization_config(path: str | Path) -> HapiMaterializationConfig:
    """Load a HAPI materialization config from JSON or YAML."""
    config_path = Path(path)
    if not config_path.exists():
        raise FileNotFoundError(f"HAPI materialization config not found: {config_path}")

    text = config_path.read_text()
    suffix = config_path.suffix.lower()
    if suffix == ".json":
        raw = json.loads(text)
    elif suffix in {".yaml", ".yml"}:
        try:
            import yaml  # type: ignore[import-untyped]
        except ImportError as exc:  # pragma: no cover - PyYAML is a dependency
            raise DQMConfigError("YAML config files require PyYAML") from exc
        raw = yaml.safe_load(text)
    else:
        raise DQMConfigError("HAPI materialization config must be JSON or YAML")
    return parse_materialization_config(raw, base_dir=config_path.parent)


def parse_materialization_config(
    raw: dict[str, Any],
    *,
    base_dir: Path | None = None,
) -> HapiMaterializationConfig:
    """Parse a HAPI materialization config dictionary."""
    if not isinstance(raw, dict):
        raise DQMConfigError("HAPI materialization config must be an object")
    base = base_dir or Path.cwd()

    postgres = raw.get("postgres") or {}
    if not isinstance(postgres, dict):
        raise DQMConfigError("'postgres' must be an object")
    connection_string = postgres.get("connection_string") or raw.get("connection_string")
    if not isinstance(connection_string, str) or not connection_string:
        raise DQMConfigError("'postgres.connection_string' is required")

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

    global_libraries = _parse_paths(raw.get("libraries", {}).get("paths", []), base)
    global_valuesets = _parse_paths(raw.get("terminology", {}).get("valuesets", []), base)
    measures = _parse_materialized_measures(
        raw.get("measures", []),
        base=base,
        defaults=defaults,
        results=results,
    )

    return HapiMaterializationConfig(
        postgres_connection_string=connection_string,
        hapi_connection_string=postgres.get("hapi_connection_string"),
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
        notification_channel=_validate_notification_channel(
            str(worker.get("notification_channel", NOTIFICATION_CHANNEL))
        ),
        fail_on_unsupported_storage=bool(
            worker.get("fail_on_unsupported_storage", True)
        ),
        hapi_schema=_parse_hapi_schema(
            postgres.get("hapi_schema", raw.get("hapi_schema"))
        ),
        retention=_parse_retention_policy(retention),
    )


def sync_measure_config(config: HapiMaterializationConfig) -> int:
    """Upsert configured measures into ``fhir4ds_measure_config``."""
    psycopg = require_psycopg()
    with psycopg.connect(config.postgres_connection_string) as conn:
        count = 0
        for measure in config.measures:
            effective_parameters = dict(config.parameters)
            effective_parameters.update(measure.parameters)
            conn.execute(
                """
                INSERT INTO fhir4ds_measure_config (
                    measure_id,
                    enabled,
                    measure_version,
                    measure_path,
                    cql_path,
                    library_paths,
                    valueset_paths,
                    parameters,
                    tags,
                    audit_mode,
                    persist_audit,
                    generate_narratives,
                    include_supporting_evidence,
                    filter_to_ip,
                    updated_at
                )
                VALUES (
                    %s, %s, %s, %s, %s,
                    %s::jsonb, %s::jsonb, %s::jsonb, %s,
                    %s, %s, %s, %s, %s, now()
                )
                ON CONFLICT (measure_id)
                DO UPDATE SET
                    enabled = EXCLUDED.enabled,
                    measure_version = EXCLUDED.measure_version,
                    measure_path = EXCLUDED.measure_path,
                    cql_path = EXCLUDED.cql_path,
                    library_paths = EXCLUDED.library_paths,
                    valueset_paths = EXCLUDED.valueset_paths,
                    parameters = EXCLUDED.parameters,
                    tags = EXCLUDED.tags,
                    audit_mode = EXCLUDED.audit_mode,
                    persist_audit = EXCLUDED.persist_audit,
                    generate_narratives = EXCLUDED.generate_narratives,
                    include_supporting_evidence = EXCLUDED.include_supporting_evidence,
                    filter_to_ip = EXCLUDED.filter_to_ip,
                    updated_at = now()
                """,
                [
                    measure.measure_id,
                    measure.enabled,
                    measure.measure_version,
                    str(measure.measure_path),
                    str(measure.cql_path) if measure.cql_path else None,
                    json.dumps(
                        [str(path) for path in [*config.library_paths, *measure.library_paths]]
                    ),
                    json.dumps(
                        [str(path) for path in [*config.valueset_paths, *measure.valueset_paths]]
                    ),
                    json.dumps(effective_parameters, default=str),
                    measure.tags,
                    measure.audit_mode.value,
                    measure.persist_audit,
                    measure.generate_narratives,
                    measure.include_supporting_evidence,
                    measure.filter_to_ip,
                ],
            )
            count += 1
        conn.commit()
    return count


def process_queue_once(
    config: HapiMaterializationConfig,
    *,
    limit: int | None = None,
    runtime: HapiMaterializationRuntime | None = None,
) -> QueueProcessResult:
    """Claim pending patients, run configured measures, and persist results."""
    psycopg = require_psycopg()
    batch_limit = limit or config.batch_size
    with psycopg.connect(config.postgres_connection_string) as pg_conn:
        stale_reset = reset_stale_processing(
            pg_conn,
            processing_timeout_seconds=config.processing_timeout_seconds,
            max_attempts=config.max_attempts,
        )
        patients = claim_pending_patients(
            pg_conn,
            batch_limit,
            max_attempts=config.max_attempts,
            retry_backoff_seconds=config.retry_backoff_seconds,
        )
        _log_worker_event(
            "queue_claimed",
            claimed=len(patients),
            stale_reset=stale_reset,
            limit=batch_limit,
        )
        if not patients:
            return QueueProcessResult(
                run_id=None,
                claimed=[],
                measures=0,
                stale_reset=stale_reset,
            )

        measures = config.measures or load_enabled_measure_config(pg_conn)
        measures = [measure for measure in measures if measure.enabled]
        run_id = start_measure_run(
            pg_conn,
            patient_count=len(patients),
            measure_count=len(measures),
            trigger_reason="queue",
        )
        errors: dict[str, str] = {}
        metrics: dict[str, Any] = {}
        before_metrics = (
            runtime.evaluator.compiled_measure_metrics() if runtime is not None else None
        )
        try:
            after_metrics = _process_claimed_patients(
                pg_conn,
                config,
                run_id,
                patients,
                measures,
                errors,
                runtime=runtime,
            )
            metrics = _compiled_metrics_delta(before_metrics, after_metrics)
            status = "partial" if errors else "ok"
            complete_measure_run(pg_conn, run_id, status=status, metrics=metrics)
        except Exception as exc:
            complete_measure_run(pg_conn, run_id, status="error", error=str(exc))
            for patient in patients:
                mark_patient_failed(pg_conn, patient.patient_id, str(exc))
            _log_worker_event(
                "queue_batch_error",
                run_id=run_id,
                patients=len(patients),
                error=str(exc),
            )
            raise
        _log_worker_event(
            "queue_batch_complete",
            run_id=run_id,
            patients=len(patients),
            measures=len(measures),
            errors=len(errors),
            metrics=metrics,
        )
        return QueueProcessResult(
            run_id=run_id,
            claimed=[patient.patient_id for patient in patients],
            measures=len(measures),
            stale_reset=stale_reset,
            errors=errors,
            metrics=metrics,
        )


def listen_and_process(
    config: HapiMaterializationConfig,
    *,
    stop_after: int | None = None,
) -> None:
    """Run the event-driven worker loop with polling fallback."""
    psycopg = require_psycopg()
    loops = 0
    shutdown, old_handlers = _install_shutdown_handlers()
    _log_worker_event(
        "listener_start",
        notification_channel=config.notification_channel,
        poll_interval_seconds=config.poll_interval_seconds,
    )
    try:
        with HapiMaterializationRuntime.open(config) as runtime:
            while not shutdown["requested"]:
                process_queue_once(config, runtime=runtime)
                loops += 1
                if stop_after is not None and loops >= stop_after:
                    return

                with psycopg.connect(
                    config.postgres_connection_string,
                    autocommit=True,
                ) as conn:
                    conn.execute(f"LISTEN {config.notification_channel}")
                    deadline = time.monotonic() + config.poll_interval_seconds
                    while not shutdown["requested"]:
                        timeout = max(0.0, min(1.0, deadline - time.monotonic()))
                        notified = False
                        for _notify in conn.notifies(timeout=timeout, stop_after=1):
                            notified = True
                            break
                        if notified:
                            break
                        if time.monotonic() >= deadline:
                            break
    finally:
        _restore_shutdown_handlers(old_handlers)
        _log_worker_event("listener_stop", loops=loops)


def claim_pending_patients(
    conn: Any,
    limit: int,
    *,
    max_attempts: int = 3,
    retry_backoff_seconds: float = 60.0,
) -> list[ClaimedPatient]:
    """Claim eligible queue rows with ``FOR UPDATE SKIP LOCKED``."""
    rows = conn.execute(
        """
        WITH claimed AS (
            SELECT patient_id, last_seen_at
            FROM fhir4ds_patient_change_queue
            WHERE (
                status = 'pending'
                OR (
                    status = 'failed'
                    AND attempts < %s
                    AND COALESCE(processed_at, last_seen_at)
                        <= now() - ((%s * GREATEST(attempts, 1)) * INTERVAL '1 second')
                )
            )
            ORDER BY last_seen_at, patient_id
            LIMIT %s
            FOR UPDATE SKIP LOCKED
        )
        UPDATE fhir4ds_patient_change_queue q
        SET status = 'processing',
            attempts = attempts + 1,
            processing_started_at = now()
        FROM claimed
        WHERE q.patient_id = claimed.patient_id
        RETURNING q.patient_id, claimed.last_seen_at
        """,
        [max_attempts, retry_backoff_seconds, limit],
    ).fetchall()
    conn.commit()
    return [ClaimedPatient(patient_id=row[0], input_watermark=row[1]) for row in rows]


def reset_stale_processing(
    conn: Any,
    *,
    processing_timeout_seconds: float = 900.0,
    max_attempts: int = 3,
) -> int:
    """Return timed-out ``processing`` queue rows to ``pending`` for retry."""
    row = conn.execute(
        """
        UPDATE fhir4ds_patient_change_queue
        SET status = CASE
                WHEN attempts >= %s THEN 'failed'
                ELSE 'pending'
            END,
            last_error = CASE
                WHEN attempts >= %s
                    THEN 'Processing timeout; max attempts reached'
                ELSE 'Processing timeout; reset for retry'
            END,
            processed_at = CASE
                WHEN attempts >= %s THEN now()
                ELSE processed_at
            END,
            processing_started_at = NULL
        WHERE status = 'processing'
          AND processing_started_at
              < now() - (%s * INTERVAL '1 second')
        RETURNING patient_id
        """,
        [max_attempts, max_attempts, max_attempts, processing_timeout_seconds],
    ).fetchall()
    conn.commit()
    return len(row)


def load_enabled_measure_config(conn: Any) -> list[HapiMaterializedMeasure]:
    """Load enabled materialized measure configuration from PostgreSQL."""
    rows = conn.execute(
        """
        SELECT
            measure_id,
            measure_version,
            measure_path,
            cql_path,
            library_paths::text,
            valueset_paths::text,
            parameters::text,
            tags,
            audit_mode,
            persist_audit,
            generate_narratives,
            include_supporting_evidence,
            filter_to_ip
        FROM fhir4ds_measure_config
        WHERE enabled = true
        ORDER BY measure_id
        """
    ).fetchall()
    measures: list[HapiMaterializedMeasure] = []
    for row in rows:
        measures.append(
            HapiMaterializedMeasure(
                measure_id=row[0],
                measure_version=row[1],
                measure_path=Path(row[2]),
                cql_path=Path(row[3]) if row[3] else None,
                library_paths=[Path(path) for path in json.loads(row[4] or "[]")],
                valueset_paths=[Path(path) for path in json.loads(row[5] or "[]")],
                parameters=json.loads(row[6] or "{}"),
                tags=list(row[7] or []),
                audit_mode=AuditMode(row[8]),
                persist_audit=bool(row[9]),
                generate_narratives=bool(row[10]),
                include_supporting_evidence=bool(row[11]),
                filter_to_ip=bool(row[12]),
            )
        )
    return measures


def start_measure_run(
    conn: Any,
    *,
    patient_count: int,
    measure_count: int,
    trigger_reason: str,
) -> int:
    row = conn.execute(
        """
        INSERT INTO fhir4ds_measure_run (
            patient_count,
            measure_count,
            trigger_reason
        )
        VALUES (%s, %s, %s)
        RETURNING run_id
        """,
        [patient_count, measure_count, trigger_reason],
    ).fetchone()
    conn.commit()
    return int(row[0])


def complete_measure_run(
    conn: Any,
    run_id: int,
    *,
    status: str,
    error: str | None = None,
    metrics: dict[str, Any] | None = None,
) -> None:
    metrics = metrics or {}
    conn.execute(
        """
        UPDATE fhir4ds_measure_run
        SET status = %s,
            completed_at = now(),
            error = %s,
            compile_cache_hits = %s,
            compile_cache_misses = %s,
            compile_count = %s,
            compile_ms = %s,
            execute_count = %s,
            execute_ms = %s,
            prepared_count = %s,
            prepared_fallback_count = %s,
            metrics_json = %s::jsonb
        WHERE run_id = %s
        """,
        [
            status,
            error,
            int(metrics.get("cache_hits", 0) or 0),
            int(metrics.get("cache_misses", 0) or 0),
            int(metrics.get("compile_count", 0) or 0),
            float(metrics.get("compile_ms", 0.0) or 0.0),
            int(metrics.get("execute_count", 0) or 0),
            float(metrics.get("execute_ms", 0.0) or 0.0),
            int(metrics.get("prepared_count", 0) or 0),
            int(metrics.get("prepared_fallback_count", 0) or 0),
            json.dumps(metrics, default=str),
            run_id,
        ],
    )
    conn.commit()


def mark_patient_complete(conn: Any, patient_id: str) -> None:
    conn.execute(
        """
        UPDATE fhir4ds_patient_change_queue
        SET status = 'complete',
            processed_at = now(),
            last_error = NULL
        WHERE patient_id = %s
        """,
        [patient_id],
    )
    conn.commit()


def mark_patient_failed(conn: Any, patient_id: str, error: str) -> None:
    conn.execute(
        """
        UPDATE fhir4ds_patient_change_queue
        SET status = 'failed',
            processed_at = now(),
            last_error = %s
        WHERE patient_id = %s
        """,
        [error, patient_id],
    )
    conn.commit()


def persist_patient_measure_result(
    conn: Any,
    *,
    run_id: int,
    patient_id: str,
    measure: HapiMaterializedMeasure,
    status: str,
    result_json: dict[str, Any] | None,
    summary_json: dict[str, Any] | None,
    input_watermark: datetime | None,
    config_hash: str,
    error: str | None = None,
    audit_json: dict[str, Any] | None = None,
) -> int:
    """Deactivate previous active result and insert the new result row."""
    conn.execute(
        """
        UPDATE fhir4ds_measure_result
        SET active = false
        WHERE patient_id = %s
          AND measure_id = %s
          AND active = true
        """,
        [patient_id, measure.measure_id],
    )
    row = conn.execute(
        """
        INSERT INTO fhir4ds_measure_result (
            run_id,
            patient_id,
            measure_id,
            measure_version,
            active,
            status,
            result_json,
            summary_json,
            input_watermark,
            config_hash,
            error
        )
        VALUES (
            %s, %s, %s, %s, true, %s,
            %s::jsonb, %s::jsonb, %s, %s, %s
        )
        RETURNING result_id
        """,
        [
            run_id,
            patient_id,
            measure.measure_id,
            measure.measure_version,
            status,
            json.dumps(result_json, default=str) if result_json is not None else None,
            json.dumps(summary_json, default=str) if summary_json is not None else None,
            input_watermark,
            config_hash,
            error,
        ],
    ).fetchone()
    result_id = int(row[0])
    if audit_json is not None:
        audit_text = json.dumps(audit_json, default=str)
        conn.execute(
            """
            INSERT INTO fhir4ds_measure_audit (
                result_id,
                audit_json,
                size_bytes
            )
            VALUES (%s, %s::jsonb, %s)
            """,
            [result_id, audit_text, len(audit_text.encode("utf-8"))],
        )
    conn.commit()
    return result_id


def prune_materialization_history(
    connection_string: str,
    retention: HapiRetentionPolicy,
) -> dict[str, int]:
    """Prune old inactive results, audit rows, and unreferenced run rows."""
    psycopg = require_psycopg()
    deleted = {"audits": 0, "inactive_results": 0, "runs": 0}
    with psycopg.connect(connection_string) as conn:
        if retention.audit_days is not None:
            rows = conn.execute(
                """
                DELETE FROM fhir4ds_measure_audit
                WHERE created_at < now() - (%s * INTERVAL '1 day')
                RETURNING audit_id
                """,
                [retention.audit_days],
            ).fetchall()
            deleted["audits"] = len(rows)
        if retention.inactive_result_days is not None:
            rows = conn.execute(
                """
                DELETE FROM fhir4ds_measure_result
                WHERE active = false
                  AND calculated_at < now() - (%s * INTERVAL '1 day')
                RETURNING result_id
                """,
                [retention.inactive_result_days],
            ).fetchall()
            deleted["inactive_results"] = len(rows)
        if retention.run_days is not None:
            rows = conn.execute(
                """
                DELETE FROM fhir4ds_measure_run r
                WHERE COALESCE(r.completed_at, r.started_at)
                    < now() - (%s * INTERVAL '1 day')
                  AND NOT EXISTS (
                      SELECT 1
                      FROM fhir4ds_measure_result mr
                      WHERE mr.run_id = r.run_id
                  )
                RETURNING r.run_id
                """,
                [retention.run_days],
            ).fetchall()
            deleted["runs"] = len(rows)
        conn.commit()
    _log_worker_event("history_pruned", **deleted)
    return deleted


def split_patient_result_rows(rows: list[dict[str, Any]]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Return compact result JSON and full audit JSON for patient result rows."""
    compact_rows = [_compact_row(row) for row in rows]
    full_rows = [_jsonable(row) for row in rows]
    return {"rows": compact_rows}, {"rows": full_rows}


def materialized_measure_hash(measure: HapiMaterializedMeasure) -> str:
    """Hash measure configuration fields that affect materialized results."""
    payload = {
        "measure_id": measure.measure_id,
        "measure_version": measure.measure_version,
        "measure_path": str(measure.measure_path),
        "cql_path": str(measure.cql_path) if measure.cql_path else None,
        "library_paths": [str(path) for path in measure.library_paths],
        "valueset_paths": [str(path) for path in measure.valueset_paths],
        "parameters": measure.parameters,
        "audit_mode": measure.audit_mode.value,
        "filter_to_ip": measure.filter_to_ip,
    }
    text = json.dumps(payload, sort_keys=True, default=str)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _process_claimed_patients(
    pg_conn: Any,
    config: HapiMaterializationConfig,
    run_id: int,
    patients: list[ClaimedPatient],
    measures: list[HapiMaterializedMeasure],
    errors: dict[str, str],
    runtime: HapiMaterializationRuntime | None = None,
) -> dict[str, Any]:
    if runtime is None:
        with HapiMaterializationRuntime.open(config) as owned_runtime:
            return _process_claimed_patients(
                pg_conn,
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
    patient_errors: dict[str, str] = {}

    metrics: dict[str, Any] = {}
    evaluator = runtime.evaluator
    runtime.load_valuesets_once(config.valueset_paths)
    for measure in measures:
        try:
            runtime.load_valuesets_once(measure.valueset_paths)
            result = _evaluate_materialized_measure(
                evaluator,
                config,
                measure,
                patient_ids,
            )
            _persist_successful_measure(
                pg_conn,
                evaluator,
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
                    pg_conn,
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
            mark_patient_failed(pg_conn, patient.patient_id, error)
        else:
            mark_patient_complete(pg_conn, patient.patient_id)
    return metrics


def _evaluate_materialized_measure(
    evaluator: MeasureEvaluator,
    config: HapiMaterializationConfig,
    measure: HapiMaterializedMeasure,
    patient_ids: list[str],
) -> MeasureResult:
    cql_path = measure.cql_path or _resolve_cql_path(
        MeasureSpec(path=measure.measure_path, cql=None, id=measure.measure_id),
        [*config.library_paths, *measure.library_paths],
    )
    parameters = dict(config.parameters)
    parameters.update(measure.parameters)
    compiled = evaluator.compile_measure(
        measure_bundle=measure.measure_path,
        cql_library_path=cql_path,
        parameters=parameters,
        audit_mode=measure.audit_mode,
        filter_to_ip=measure.filter_to_ip,
        patient_scope="target_table",
        include_paths=[str(path) for path in [*config.library_paths, *measure.library_paths]],
        generate_narratives=measure.generate_narratives,
        include_supporting_evidence=measure.include_supporting_evidence
        or measure.persist_audit,
    )
    return evaluator.execute_compiled_measure(compiled, patient_ids=patient_ids)


def _persist_successful_measure(
    pg_conn: Any,
    evaluator: MeasureEvaluator,
    run_id: int,
    patients: list[ClaimedPatient],
    measure: HapiMaterializedMeasure,
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
                pg_conn,
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
        persist_patient_measure_result(
            pg_conn,
            run_id=run_id,
            patient_id=patient.patient_id,
            measure=measure,
            status="ok",
            result_json=result_json,
            summary_json=summary,
            input_watermark=watermark_by_patient.get(patient.patient_id),
            config_hash=config_hash,
            audit_json=audit_json if measure.persist_audit else None,
        )


def _parse_materialized_measures(
    raw: Any,
    *,
    base: Path,
    defaults: dict[str, Any],
    results: dict[str, Any],
) -> list[HapiMaterializedMeasure]:
    if raw in (None, []):
        return []
    if not isinstance(raw, list):
        raise DQMConfigError("'measures' must be a list")
    measures: list[HapiMaterializedMeasure] = []
    for index, item in enumerate(raw):
        if not isinstance(item, dict):
            raise DQMConfigError(f"measures[{index}] must be an object")
        path = item.get("path")
        if not isinstance(path, str) or not path:
            raise DQMConfigError(f"measures[{index}].path is required")
        measure_path = _resolve_path(path, base)
        measure_id = item.get("id") or measure_path.stem.replace("Measure-", "")
        if not isinstance(measure_id, str) or not measure_id:
            raise DQMConfigError(f"measures[{index}].id must be a string")

        audit_mode = item.get("audit_mode", defaults.get("audit_mode", AuditMode.NONE.value))
        measures.append(
            HapiMaterializedMeasure(
                measure_id=measure_id,
                measure_path=measure_path,
                cql_path=_optional_path(item.get("cql"), base),
                enabled=bool(item.get("enabled", True)),
                measure_version=item.get("version"),
                library_paths=_parse_paths(item.get("libraries", []), base),
                valueset_paths=_parse_paths(item.get("valuesets", []), base),
                parameters=dict(item.get("parameters") or {}),
                tags=list(item.get("tags") or []),
                audit_mode=AuditMode(audit_mode),
                persist_audit=bool(
                    item.get("persist_audit", results.get("persist_audit", False))
                ),
                generate_narratives=bool(
                    item.get("generate_narratives", defaults.get("narratives", False))
                ),
                include_supporting_evidence=bool(
                    item.get("include_supporting_evidence", False)
                ),
                filter_to_ip=bool(item.get("filter_to_ip", defaults.get("filter_to_ip", False))),
            )
        )
    return measures


def _render_materialization_sql(
    template: str,
    *,
    schema: HapiPostgresSchema,
    notification_channel: str,
    decoded_view: str,
) -> str:
    tokens = {
        "NOTIFICATION_CHANNEL_LITERAL": quote_sql_literal(notification_channel),
        "DECODED_VIEW_RELATION": _pg_relation(schema.schema, decoded_view),
        "RESOURCE_RELATION": _pg_relation(schema.schema, schema.resource_table),
        "VERSION_RELATION": _pg_relation(schema.schema, schema.version_table),
        "RESOURCE_TABLE_NAME_LITERAL": quote_sql_literal(schema.resource_table),
        "RESOURCE_PK_COLUMN": quote_identifier(schema.resource_pk_column),
        "VERSION_FK_COLUMN": quote_identifier(schema.version_resource_fk_column),
        "RESOURCE_TYPE_COLUMN": quote_identifier(schema.resource_type_column),
        "FHIR_ID_COLUMN": quote_identifier(schema.fhir_id_column),
        "CURRENT_VERSION_COLUMN": quote_identifier(schema.current_version_column),
        "VERSION_NUMBER_COLUMN": quote_identifier(schema.version_number_column),
        "ENCODING_COLUMN": quote_identifier(schema.encoding_column),
        "TEXT_VC_COLUMN": quote_identifier(schema.text_vc_column),
        "TEXT_LOB_COLUMN": quote_identifier(schema.text_lob_column),
        "RESOURCE_PK_SELECT": _pg_col("r", schema.resource_pk_column),
        "VERSION_FK_SELECT": _pg_col("v", schema.version_resource_fk_column),
        "RESOURCE_TYPE_SELECT": _pg_col("r", schema.resource_type_column),
        "FHIR_ID_SELECT": _pg_col("r", schema.fhir_id_column),
        "CURRENT_VERSION_SELECT": _pg_col("r", schema.current_version_column),
        "VERSION_NUMBER_SELECT": _pg_col("v", schema.version_number_column),
        "UPDATED_AT_SELECT": _pg_col("r", schema.updated_at_column),
        "DELETED_AT_SELECT": _pg_col("r", schema.deleted_at_column),
        "ENCODING_SELECT": _pg_col("v", schema.encoding_column),
        "TEXT_VC_SELECT": _pg_col("v", schema.text_vc_column),
        "TEXT_LOB_SELECT": _pg_col("v", schema.text_lob_column),
    }
    rendered = template
    for key, value in tokens.items():
        rendered = rendered.replace(f"{{{{{key}}}}}", value)
    return rendered


def _pg_relation(schema_name: str, table_name: str) -> str:
    return f"{quote_identifier(schema_name)}.{quote_identifier(table_name)}"


def _pg_col(alias: str, column_name: str) -> str:
    return f"{alias}.{quote_identifier(column_name)}"


def _validate_notification_channel(channel: str) -> str:
    if not _PG_CHANNEL_RE.match(channel):
        raise DQMConfigError(
            "'worker.notification_channel' must be a simple PostgreSQL identifier"
        )
    return channel


def _parse_hapi_schema(raw: Any) -> HapiPostgresSchema:
    if raw in (None, {}):
        return HapiPostgresSchema()
    if not isinstance(raw, dict):
        raise DQMConfigError("'postgres.hapi_schema' must be an object")

    allowed = set(HapiPostgresSchema.__dataclass_fields__)
    unknown = sorted(set(raw) - allowed)
    if unknown:
        raise DQMConfigError(
            "'postgres.hapi_schema' contains unknown field(s): "
            + ", ".join(unknown)
        )

    values: dict[str, str] = {}
    for key, value in raw.items():
        if value is None:
            continue
        if not isinstance(value, str) or not value:
            raise DQMConfigError(
                f"'postgres.hapi_schema.{key}' must be a non-empty string"
            )
        values[key] = value
    return HapiPostgresSchema(**values)


def _parse_retention_policy(raw: dict[str, Any]) -> HapiRetentionPolicy:
    return HapiRetentionPolicy(
        inactive_result_days=_optional_positive_int(
            raw.get("inactive_result_days"),
            "retention.inactive_result_days",
        ),
        audit_days=_optional_positive_int(raw.get("audit_days"), "retention.audit_days"),
        run_days=_optional_positive_int(raw.get("run_days"), "retention.run_days"),
    )


def _optional_positive_int(value: Any, field_name: str) -> int | None:
    if value is None:
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise DQMConfigError(f"'{field_name}' must be a positive integer") from exc
    if parsed <= 0:
        raise DQMConfigError(f"'{field_name}' must be a positive integer")
    return parsed


def _compiled_metrics_delta(
    before: dict[str, Any] | None,
    after: dict[str, Any],
) -> dict[str, Any]:
    if before is None:
        return dict(after)

    metrics = dict(after)
    delta_fields = (
        "cache_hits",
        "cache_misses",
        "compile_count",
        "compile_ms",
        "execute_count",
        "execute_ms",
        "prepared_count",
        "prepared_fallback_count",
    )
    for field_name in delta_fields:
        value = (after.get(field_name, 0) or 0) - (
            before.get(field_name, 0) or 0
        )
        metrics[field_name] = (
            round(float(value), 3) if field_name.endswith("_ms") else value
        )
    metrics["cumulative"] = dict(after)
    return metrics


def _log_worker_event(event: str, **fields: Any) -> None:
    payload = {"event": event, **fields}
    logger.info(json.dumps(payload, default=str, sort_keys=True))


def _install_shutdown_handlers() -> tuple[dict[str, bool], dict[int, Any]]:
    shutdown = {"requested": False}
    old_handlers: dict[int, Any] = {}

    def _request_shutdown(signum: int, frame: Any) -> None:
        shutdown["requested"] = True
        _log_worker_event("shutdown_requested", signal=signum)

    for sig in (signal.SIGINT, signal.SIGTERM):
        old_handlers[sig] = signal.getsignal(sig)
        signal.signal(sig, _request_shutdown)
    return shutdown, old_handlers


def _restore_shutdown_handlers(old_handlers: dict[int, Any]) -> None:
    for sig, handler in old_handlers.items():
        signal.signal(sig, handler)


def _compact_row(row: dict[str, Any]) -> dict[str, Any]:
    compact: dict[str, Any] = {}
    for key, value in row.items():
        if key == "patient_id":
            compact[key] = _jsonable(value)
        elif isinstance(value, dict) and "result" in value:
            compact[key] = _jsonable(value.get("result"))
        elif key.startswith("evidence_"):
            continue
        else:
            compact[key] = _jsonable(value)
    return compact


def _jsonable(value: Any) -> Any:
    if value is None:
        return None
    try:
        import pandas as pd
    except ImportError:  # pragma: no cover
        pd = None  # type: ignore[assignment]
    if pd is not None:
        try:
            if pd.isna(value):
                return None
        except (TypeError, ValueError):
            pass
    if hasattr(value, "item"):
        try:
            return value.item()
        except Exception:
            pass
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    if isinstance(value, tuple):
        return [_jsonable(item) for item in value]
    if isinstance(value, (datetime, Path)):
        return str(value)
    return value


def _parse_paths(raw: Any, base: Path) -> list[Path]:
    if raw is None:
        return []
    if isinstance(raw, str):
        return [_resolve_path(raw, base)]
    if not isinstance(raw, list) or not all(isinstance(path, str) for path in raw):
        raise DQMConfigError("Expected a path string or list of path strings")
    return [_resolve_path(path, base) for path in raw]


def _optional_path(raw: Any, base: Path) -> Path | None:
    if raw is None:
        return None
    if not isinstance(raw, str) or not raw:
        raise DQMConfigError("Optional path fields must be strings when provided")
    return _resolve_path(raw, base)


def _resolve_path(raw: str, base: Path) -> Path:
    path = Path(raw)
    return path if path.is_absolute() else base / path
