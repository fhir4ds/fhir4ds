"""Reusable DQM batch runner."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from glob import has_magic
from pathlib import Path
from typing import Any

import fhir4ds
from fhir4ds.cql import FHIRDataLoader, evaluate_measure
from fhir4ds.cql.parser import parse_cql
from fhir4ds.cql.parser.ast_nodes import Definition
from fhir4ds.sources import FileSystemSource

from .config import DefinitionOutputSpec, DQMConfigError, DQMRunConfig, MeasureSpec, SourceSpec
from .evaluator import MeasureEvaluator
from .parser import MeasureParser
from .types import AuditMode


@dataclass
class MeasureRunRecord:
    """Outcome for one evaluated measure."""

    measure_id: str
    status: str
    result_rows: int = 0
    summary: dict[str, Any] | None = None
    outputs: dict[str, str] = field(default_factory=dict)
    duration_ms: float = 0.0
    error: str | None = None


@dataclass
class BatchRunResult:
    """Outcome for a DQM batch run."""

    records: list[MeasureRunRecord]
    output_dir: Path
    duration_ms: float

    @property
    def failed(self) -> list[MeasureRunRecord]:
        return [record for record in self.records if record.status != "ok"]


def validate_config(config: DQMRunConfig) -> list[str]:
    """Return validation errors for a DQM run config."""
    errors: list[str] = []
    if not config.measures:
        errors.append("At least one measure is required")
    for measure in config.measures:
        if not measure.path.exists():
            errors.append(f"Measure file not found: {measure.path}")
        if measure.cql is not None and not measure.cql.exists():
            errors.append(f"CQL library not found: {measure.cql}")
    for path in config.libraries:
        if not path.exists():
            errors.append(f"Library path not found: {path}")
    for path in config.terminology.valuesets:
        if not path.exists():
            errors.append(f"ValueSet path not found: {path}")
    source_path = config.source.path
    if (
        source_path
        and not _is_cloud_path(source_path)
        and not has_magic(source_path)
        and not Path(source_path).exists()
    ):
        errors.append(f"Source path not found: {source_path}")
    if config.audit.narratives and config.audit.mode == AuditMode.NONE:
        errors.append("Narratives require audit.mode to be population or full")
    if config.outputs.measure_reports in {"summary", "individual", "both"}:
        has_period = bool(config.period_start and config.period_end)
        mp_param = config.parameters.get("Measurement Period")
        has_mp_param = isinstance(mp_param, (list, tuple)) and len(mp_param) >= 2
        if not has_period and not has_mp_param:
            errors.append(
                "MeasureReport output requires period.start and period.end "
                "or Measurement Period parameters"
            )
    return errors


def inspect_config(config: DQMRunConfig) -> dict[str, Any]:
    """Return a lightweight description of what a DQM run config references."""
    parser = MeasureParser()
    measures: list[dict[str, Any]] = []
    for measure in config.measures:
        entry: dict[str, Any] = {"path": str(measure.path), "exists": measure.path.exists()}
        if measure.path.exists():
            try:
                pop_map = parser.parse(json.loads(measure.path.read_text()))
                entry.update(
                    {
                        "id": pop_map.measure_id,
                        "library": pop_map.cql_library_ref,
                        "groups": len(pop_map.groups),
                        "populations": sum(len(group.populations) for group in pop_map.groups),
                    }
                )
            except Exception as exc:  # pragma: no cover - defensive reporting
                entry["error"] = str(exc)
        measures.append(entry)

    return {
        "measures": measures,
        "source": {
            "type": config.source.type,
            "path": config.source.path,
            "format": config.source.format,
        },
        "libraries": [str(path) for path in config.libraries],
        "valuesets": [str(path) for path in _iter_valueset_files(config.terminology.valuesets)],
        "outputs": {
            "directory": str(config.outputs.directory),
            "formats": config.outputs.formats,
            "measure_reports": config.outputs.measure_reports,
            "definitions": {
                "mode": config.outputs.definitions.mode,
                "formats": config.outputs.definitions.formats,
                "include_sde": config.outputs.definitions.include_sde,
                "names": config.outputs.definitions.definitions,
            },
        },
        "audit": {
            "mode": config.audit.mode.value,
            "narratives": config.audit.narratives,
        },
    }


def run_batch(config: DQMRunConfig) -> BatchRunResult:
    """Execute a DQM batch run and write configured outputs."""
    errors = validate_config(config)
    if errors:
        raise DQMConfigError("; ".join(errors))

    started = time.perf_counter()
    output_dir = config.outputs.directory
    output_dir.mkdir(parents=True, exist_ok=True)

    conn = _create_connection(config.source)
    try:
        _load_valuesets(conn, config.terminology.valuesets)
        evaluator = MeasureEvaluator(conn)
        records: list[MeasureRunRecord] = []
        for measure in config.measures:
            record = _run_one_measure(evaluator, config, measure)
            records.append(record)
            if record.status != "ok" and not config.continue_on_error:
                break
    finally:
        conn.close()

    duration_ms = _elapsed_ms(started)
    result = BatchRunResult(records=records, output_dir=output_dir, duration_ms=duration_ms)
    _write_json(
        output_dir / "run.json",
        {
            "duration_ms": round(duration_ms, 3),
            "failed": len(result.failed),
            "measures": [_record_to_dict(record) for record in records],
        },
    )
    return result


def _run_one_measure(
    evaluator: MeasureEvaluator,
    config: DQMRunConfig,
    measure: MeasureSpec,
) -> MeasureRunRecord:
    started = time.perf_counter()
    measure_id = measure.id or measure.path.stem.replace("Measure-", "")
    try:
        cql_path = measure.cql or _resolve_cql_path(measure, config.libraries)
        result = evaluator.evaluate(
            measure_bundle=measure.path,
            cql_library_path=cql_path,
            parameters=config.parameters,
            audit_mode=config.audit.mode,
            filter_to_ip=config.filter_to_ip,
            patient_ids=config.patient_ids,
            include_paths=[str(path) for path in config.libraries],
            generate_narratives=config.audit.narratives,
            include_supporting_evidence=config.outputs.measure_reports in {"individual", "both"},
        )
        summary = evaluator.summary_report(result)
        outputs = _write_measure_outputs(
            evaluator,
            config,
            measure_id,
            result,
            summary,
            cql_path,
        )
        return MeasureRunRecord(
            measure_id=measure_id,
            status="ok",
            result_rows=len(result.dataframe),
            summary=summary,
            outputs=outputs,
            duration_ms=_elapsed_ms(started),
        )
    except Exception as exc:
        return MeasureRunRecord(
            measure_id=measure_id,
            status="error",
            duration_ms=_elapsed_ms(started),
            error=f"{type(exc).__name__}: {exc}",
        )


def _write_measure_outputs(
    evaluator: MeasureEvaluator,
    config: DQMRunConfig,
    measure_id: str,
    result: Any,
    summary: dict[str, Any],
    cql_path: Path,
) -> dict[str, str]:
    output_dir = config.outputs.directory / _safe_name(measure_id)
    output_dir.mkdir(parents=True, exist_ok=True)
    outputs: dict[str, str] = {}

    for fmt in config.outputs.formats:
        path = output_dir / f"results.{fmt}"
        if fmt == "csv":
            evaluator.to_csv(result, path)
        elif fmt == "json":
            result.dataframe.to_json(path, orient="records", indent=2, date_format="iso")
        elif fmt == "parquet":
            result.dataframe.to_parquet(path, index=False)
        outputs[f"results_{fmt}"] = str(path)

    summary_path = output_dir / "summary.json"
    _write_json(summary_path, summary)
    outputs["summary"] = str(summary_path)

    definition_outputs = _write_definition_outputs(
        evaluator,
        config,
        output_dir,
        cql_path,
        result,
    )
    outputs.update(definition_outputs)

    report_mode = config.outputs.measure_reports
    if report_mode in {"summary", "both"}:
        report = evaluator.to_measure_report(
            result,
            period_start=config.period_start,
            period_end=config.period_end,
            report_type="summary",
        )
        report_path = output_dir / "MeasureReport-summary.json"
        _write_json(report_path, report)
        outputs["measure_report_summary"] = str(report_path)
    if report_mode in {"individual", "both"}:
        reports_dir = output_dir / "individual-reports"
        reports_dir.mkdir(exist_ok=True)
        for row in result.dataframe.to_dict("records"):
            patient_id = str(row.get("patient_id", "unknown"))
            patient_df = result.dataframe[result.dataframe["patient_id"] == row.get("patient_id")]
            patient_result = result.__class__(
                dataframe=patient_df,
                populations=result.populations,
                parameters=result.parameters,
                measure_url=result.measure_url,
                pop_map=result.pop_map,
            )
            report = evaluator.to_measure_report(
                patient_result,
                period_start=config.period_start,
                period_end=config.period_end,
                report_type="individual",
            )
            _write_json(reports_dir / f"{_safe_name(patient_id)}.json", report)
        outputs["measure_report_individual_dir"] = str(reports_dir)

    return outputs


def _write_definition_outputs(
    evaluator: MeasureEvaluator,
    config: DQMRunConfig,
    output_dir: Path,
    cql_path: Path,
    result: Any,
) -> dict[str, str]:
    spec = config.outputs.definitions
    if spec.mode == "none":
        return {}

    column_mapping, schema = _build_definition_output_mapping(cql_path, spec)
    definitions_df = evaluate_measure(
        library_path=str(cql_path),
        conn=evaluator.conn,
        output_columns=column_mapping,
        parameters=config.parameters,
        patient_ids=_result_patient_ids(result),
        include_paths=_include_paths_for_cql(config, cql_path),
        audit_mode=AuditMode.NONE.value,
    )

    outputs: dict[str, str] = {}
    for fmt in spec.formats:
        path = output_dir / f"definitions.{fmt}"
        if fmt == "csv":
            definitions_df.to_csv(path, index=False)
        elif fmt == "json":
            definitions_df.to_json(path, orient="records", indent=2, date_format="iso")
        elif fmt == "parquet":
            definitions_df.to_parquet(path, index=False)
        outputs[f"definitions_{fmt}"] = str(path)

    schema_path = output_dir / "definitions.schema.json"
    _write_json(schema_path, schema)
    outputs["definitions_schema"] = str(schema_path)
    return outputs


def _result_patient_ids(result: Any) -> list[str]:
    if "patient_id" not in result.dataframe.columns:
        return []
    return [str(patient_id) for patient_id in result.dataframe["patient_id"].tolist()]


def _build_definition_output_mapping(
    cql_path: Path,
    spec: DefinitionOutputSpec,
) -> tuple[dict[str, str], dict[str, Any]]:
    library = parse_cql(cql_path.read_text())
    all_definitions = [
        stmt.name
        for stmt in library.statements
        if isinstance(stmt, Definition)
    ]
    available = set(all_definitions)
    if spec.mode == "selected":
        missing = [name for name in spec.definitions if name not in available]
        if missing:
            raise DQMConfigError(
                f"Selected definition(s) not found in {cql_path.name}: {missing}"
            )
        definition_names = list(spec.definitions)
    else:
        definition_names = [
            name
            for name in all_definitions
            if spec.include_sde or not name.startswith("SDE")
        ]

    used_columns: set[str] = {"patient_id"}
    column_mapping: dict[str, str] = {}
    definition_schema: list[dict[str, str]] = []
    for definition_name in definition_names:
        column_name = _unique_column_name(_safe_column_name(definition_name), used_columns)
        used_columns.add(column_name)
        column_mapping[column_name] = definition_name
        definition_schema.append(
            {
                "column": column_name,
                "definition": definition_name,
                "library": cql_path.stem,
            }
        )

    schema = {
        "resourceType": "CQLDefinitionOutputSchema",
        "library": cql_path.stem,
        "mode": spec.mode,
        "include_sde": spec.include_sde,
        "patient_id_column": "patient_id",
        "definitions": definition_schema,
    }
    return column_mapping, schema


def _safe_column_name(value: str) -> str:
    chars = [ch.lower() if ch.isalnum() else "_" for ch in value.strip()]
    name = "".join(chars).strip("_")
    while "__" in name:
        name = name.replace("__", "_")
    return name or "definition"


def _unique_column_name(candidate: str, used: set[str]) -> str:
    if candidate not in used:
        return candidate
    suffix = 2
    while f"{candidate}_{suffix}" in used:
        suffix += 1
    return f"{candidate}_{suffix}"


def _include_paths_for_cql(config: DQMRunConfig, cql_path: Path) -> list[str]:
    paths: list[str] = []
    seen: set[str] = set()
    for path in [*config.libraries, cql_path.parent]:
        path_str = str(path)
        if path_str not in seen:
            paths.append(path_str)
            seen.add(path_str)
    return paths


def _create_connection(source: SourceSpec):
    source_type = source.type
    if source_type == "filesystem":
        if not source.path:
            raise DQMConfigError("source.path is required for filesystem sources")
        fmt = source.format or _infer_source_format(source.path)
        return fhir4ds.create_connection(
            source=FileSystemSource(
                source.path,
                format=fmt,
                hive_partitioning=source.hive_partitioning,
            )
        )

    conn = fhir4ds.create_connection()
    loader = FHIRDataLoader(conn)
    if source_type == "directory":
        if not source.path:
            raise DQMConfigError("source.path is required for directory sources")
        loader.load_directory(Path(source.path))
    elif source_type == "ndjson":
        if not source.path:
            raise DQMConfigError("source.path is required for ndjson sources")
        path = Path(source.path)
        if path.is_dir():
            loader.load_directory(path, extensions=[".ndjson"])
        else:
            loader.load_ndjson(path)
    elif source_type == "json":
        if not source.path:
            raise DQMConfigError("source.path is required for json sources")
        path = Path(source.path)
        if path.is_dir():
            loader.load_directory(path, extensions=[".json"])
        else:
            loader.load_file(path)
    else:
        raise DQMConfigError(
            "source.type must be filesystem, directory, ndjson, or json"
        )
    return conn


def _load_valuesets(conn: Any, paths: list[Path]) -> int:
    valuesets: list[dict[str, Any]] = []
    for path in _iter_valueset_files(paths):
        try:
            data = json.loads(path.read_text())
        except json.JSONDecodeError as exc:
            raise DQMConfigError(f"Invalid ValueSet JSON {path}: {exc}") from exc
        if data.get("resourceType") == "Bundle":
            for entry in data.get("entry", []):
                resource = entry.get("resource", {}) if isinstance(entry, dict) else {}
                if resource.get("resourceType") == "ValueSet":
                    valuesets.append(resource)
        elif data.get("resourceType") == "ValueSet":
            valuesets.append(data)
    if not valuesets:
        return 0
    return _load_valueset_resources(conn, valuesets)


def _load_valueset_resources(conn: Any, valuesets: list[dict[str, Any]]) -> int:
    """Load already-resolved FHIR ValueSet resources into DuckDB terminology."""
    if not valuesets:
        return 0
    return FHIRDataLoader(conn, create_table=False).load_valuesets(valuesets)


def _iter_valueset_files(paths: list[Path]):
    for path in paths:
        if path.is_dir():
            yield from sorted(path.rglob("*.json"))
        elif path.is_file():
            yield path


def _resolve_cql_path(measure: MeasureSpec, library_dirs: list[Path]) -> Path:
    parser = MeasureParser()
    pop_map = parser.parse(json.loads(measure.path.read_text()))
    candidates: list[str] = []
    if pop_map.cql_library_ref:
        library_name = pop_map.cql_library_ref.rstrip("/").split("/")[-1].split("|")[0]
        candidates.append(f"{library_name}.cql")
    candidates.append(f"{pop_map.measure_id}.cql")
    candidates.append(f"{measure.path.stem.replace('Measure-', '')}.cql")

    search_dirs = list(library_dirs) + [measure.path.parent]
    for directory in search_dirs:
        for candidate in candidates:
            path = directory / candidate
            if path.exists():
                return path
    raise FileNotFoundError(
        f"Could not resolve CQL library for {measure.path}. "
        "Set measures[].cql or add the library directory to libraries.paths."
    )


def _infer_source_format(path: str) -> str:
    suffix = Path(path).suffix.lower().lstrip(".")
    return suffix if suffix in {"parquet", "ndjson", "json", "iceberg"} else "parquet"


def _is_cloud_path(path: str) -> bool:
    return path.startswith(("s3://", "az://", "abfs://", "gs://", "gcs://"))


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, indent=2, default=str) + "\n")


def _safe_name(value: str) -> str:
    return "".join(ch if ch.isalnum() or ch in "-_." else "_" for ch in value)


def _elapsed_ms(start: float) -> float:
    return round((time.perf_counter() - start) * 1000, 3)


def _record_to_dict(record: MeasureRunRecord) -> dict[str, Any]:
    return {
        "measure_id": record.measure_id,
        "status": record.status,
        "result_rows": record.result_rows,
        "summary": record.summary,
        "outputs": record.outputs,
        "duration_ms": record.duration_ms,
        "error": record.error,
    }
