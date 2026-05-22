"""Configuration objects for DQM batch evaluation."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .types import AuditMode


class DQMConfigError(ValueError):
    """Raised when a DQM runner configuration is invalid."""


@dataclass
class MeasureSpec:
    """One measure artifact to evaluate."""

    path: Path
    cql: Path | None = None
    id: str | None = None


@dataclass
class SourceSpec:
    """FHIR source configuration."""

    type: str
    path: str | None = None
    format: str | None = None
    hive_partitioning: bool = False


@dataclass
class TerminologySpec:
    """Terminology configuration."""

    valuesets: list[Path] = field(default_factory=list)


@dataclass
class AuditSpec:
    """Audit configuration."""

    mode: AuditMode = AuditMode.NONE
    narratives: bool = False


@dataclass
class DefinitionOutputSpec:
    """Machine-readable evaluated CQL definition output configuration."""

    mode: str = "none"
    formats: list[str] = field(default_factory=list)
    include_sde: bool = False
    definitions: list[str] = field(default_factory=list)


@dataclass
class OutputSpec:
    """Output configuration."""

    directory: Path
    formats: list[str] = field(default_factory=lambda: ["json"])
    measure_reports: str = "summary"
    definitions: DefinitionOutputSpec = field(default_factory=DefinitionOutputSpec)


@dataclass
class DQMRunConfig:
    """Complete DQM batch runner configuration."""

    measures: list[MeasureSpec]
    source: SourceSpec
    outputs: OutputSpec
    libraries: list[Path] = field(default_factory=list)
    terminology: TerminologySpec = field(default_factory=TerminologySpec)
    parameters: dict[str, Any] = field(default_factory=dict)
    period_start: str | None = None
    period_end: str | None = None
    patient_ids: list[str] | None = None
    filter_to_ip: bool = False
    audit: AuditSpec = field(default_factory=AuditSpec)
    continue_on_error: bool = True


def load_run_config(path: str | Path) -> DQMRunConfig:
    """Load a DQM run config from JSON or YAML."""
    config_path = Path(path)
    if not config_path.exists():
        raise FileNotFoundError(f"DQM config not found: {config_path}")
    text = config_path.read_text()
    suffix = config_path.suffix.lower()
    if suffix == ".json":
        raw = json.loads(text)
    elif suffix in {".yaml", ".yml"}:
        try:
            import yaml  # type: ignore[import-untyped]
        except ImportError as exc:
            raise DQMConfigError(
                "YAML config files require PyYAML. Install PyYAML or use JSON config."
            ) from exc
        raw = yaml.safe_load(text)
    else:
        raise DQMConfigError("DQM config must be a .json, .yaml, or .yml file")
    return parse_run_config(raw, base_dir=config_path.parent)


def parse_run_config(raw: dict[str, Any], *, base_dir: Path | None = None) -> DQMRunConfig:
    """Parse a dict into a validated DQMRunConfig."""
    if not isinstance(raw, dict):
        raise DQMConfigError("DQM config must be an object")
    base = base_dir or Path.cwd()

    measures = _parse_measures(raw.get("measures"), base)
    libraries = _parse_paths(raw.get("libraries", {}).get("paths", []), base)
    source = _parse_source(raw.get("source"), base)
    terminology = _parse_terminology(raw.get("terminology", {}), base)
    audit = _parse_audit(raw.get("audit", {}))
    outputs = _parse_outputs(raw.get("outputs"), base)

    period = raw.get("period") or {}
    if period is None:
        period = {}
    if not isinstance(period, dict):
        raise DQMConfigError("'period' must be an object")
    period_start = period.get("start")
    period_end = period.get("end")

    parameters = raw.get("parameters") or {}
    if not isinstance(parameters, dict):
        raise DQMConfigError("'parameters' must be an object")
    parameters = dict(parameters)
    if period_start and period_end and "Measurement Period" not in parameters:
        parameters["Measurement Period"] = (period_start, period_end)

    patient_ids = raw.get("patient_ids")
    if patient_ids is not None:
        if not isinstance(patient_ids, list) or not all(isinstance(p, str) for p in patient_ids):
            raise DQMConfigError("'patient_ids' must be a list of strings")

    return DQMRunConfig(
        measures=measures,
        libraries=libraries,
        source=source,
        terminology=terminology,
        parameters=parameters,
        period_start=period_start,
        period_end=period_end,
        patient_ids=patient_ids,
        filter_to_ip=bool(raw.get("filter_to_ip", False)),
        audit=audit,
        outputs=outputs,
        continue_on_error=bool(raw.get("continue_on_error", True)),
    )


def _parse_measures(raw: Any, base: Path) -> list[MeasureSpec]:
    if not isinstance(raw, list) or not raw:
        raise DQMConfigError("'measures' must be a non-empty list")
    measures: list[MeasureSpec] = []
    for index, item in enumerate(raw):
        if isinstance(item, str):
            measures.append(MeasureSpec(path=_resolve_path(item, base)))
            continue
        if not isinstance(item, dict):
            raise DQMConfigError(f"measures[{index}] must be a path string or object")
        path = item.get("path")
        if not isinstance(path, str) or not path:
            raise DQMConfigError(f"measures[{index}].path is required")
        cql = item.get("cql")
        if cql is not None and not isinstance(cql, str):
            raise DQMConfigError(f"measures[{index}].cql must be a string")
        measure_id = item.get("id")
        if measure_id is not None and not isinstance(measure_id, str):
            raise DQMConfigError(f"measures[{index}].id must be a string")
        measures.append(
            MeasureSpec(
                path=_resolve_path(path, base),
                cql=_resolve_path(cql, base) if cql else None,
                id=measure_id,
            )
        )
    return measures


def _parse_source(raw: Any, base: Path) -> SourceSpec:
    if not isinstance(raw, dict):
        raise DQMConfigError("'source' must be an object")
    source_type = raw.get("type")
    if not isinstance(source_type, str) or not source_type:
        raise DQMConfigError("'source.type' is required")
    source_path = raw.get("path")
    if source_path is not None and not isinstance(source_path, str):
        raise DQMConfigError("'source.path' must be a string")
    source_format = raw.get("format")
    if source_format is not None and not isinstance(source_format, str):
        raise DQMConfigError("'source.format' must be a string")
    return SourceSpec(
        type=source_type.lower(),
        path=str(_resolve_path(source_path, base)) if source_path and not _is_cloud_path(source_path) else source_path,
        format=source_format.lower() if source_format else None,
        hive_partitioning=bool(raw.get("hive_partitioning", False)),
    )


def _parse_terminology(raw: Any, base: Path) -> TerminologySpec:
    if raw is None:
        return TerminologySpec()
    if not isinstance(raw, dict):
        raise DQMConfigError("'terminology' must be an object")
    valuesets = raw.get("valuesets") or []
    if isinstance(valuesets, str):
        valueset_paths = [_resolve_path(valuesets, base)]
    elif isinstance(valuesets, list):
        valueset_paths = _parse_paths(valuesets, base)
    else:
        raise DQMConfigError("'terminology.valuesets' must be a path or list of paths")
    return TerminologySpec(valuesets=valueset_paths)


def _parse_audit(raw: Any) -> AuditSpec:
    if raw is None:
        return AuditSpec()
    if not isinstance(raw, dict):
        raise DQMConfigError("'audit' must be an object")
    try:
        mode = AuditMode(raw.get("mode", AuditMode.NONE))
    except ValueError as exc:
        allowed = ", ".join(mode.value for mode in AuditMode)
        raise DQMConfigError(f"'audit.mode' must be one of: {allowed}") from exc
    return AuditSpec(mode=mode, narratives=bool(raw.get("narratives", False)))


def _parse_outputs(raw: Any, base: Path) -> OutputSpec:
    if not isinstance(raw, dict):
        raise DQMConfigError("'outputs' must be an object")
    directory = raw.get("directory")
    if not isinstance(directory, str) or not directory:
        raise DQMConfigError("'outputs.directory' is required")
    formats = raw.get("formats") or ["json"]
    if isinstance(formats, str):
        formats = [formats]
    if not isinstance(formats, list) or not all(isinstance(fmt, str) for fmt in formats):
        raise DQMConfigError("'outputs.formats' must be a string or list of strings")
    normalized = [fmt.lower() for fmt in formats]
    allowed = {"csv", "json", "parquet"}
    invalid = sorted(set(normalized) - allowed)
    if invalid:
        raise DQMConfigError(f"Unsupported output format(s): {invalid}")
    raw_report_mode = raw.get("measure_reports", "summary")
    if isinstance(raw_report_mode, dict):
        report_mode = raw_report_mode.get("mode", "summary")
    else:
        report_mode = raw_report_mode
    if report_mode not in {"none", "summary", "individual", "both"}:
        raise DQMConfigError("'outputs.measure_reports' must be none, summary, individual, or both")
    definition_outputs = _parse_definition_outputs(raw.get("definitions"), normalized)
    return OutputSpec(
        directory=_resolve_path(directory, base),
        formats=normalized,
        measure_reports=report_mode,
        definitions=definition_outputs,
    )


def _parse_definition_outputs(raw: Any, default_formats: list[str]) -> DefinitionOutputSpec:
    if raw is None or raw is False:
        return DefinitionOutputSpec()
    if raw is True:
        return DefinitionOutputSpec(mode="all", formats=list(default_formats))
    if isinstance(raw, str):
        raw = {"mode": raw}
    if not isinstance(raw, dict):
        raise DQMConfigError("'outputs.definitions' must be an object, string, or boolean")

    mode = raw.get("mode", "none")
    if mode not in {"none", "all", "selected"}:
        raise DQMConfigError("'outputs.definitions.mode' must be none, all, or selected")

    formats = raw.get("formats")
    if formats is None:
        formats = default_formats
    elif isinstance(formats, str):
        formats = [formats]
    if not isinstance(formats, list) or not all(isinstance(fmt, str) for fmt in formats):
        raise DQMConfigError("'outputs.definitions.formats' must be a string or list of strings")
    normalized_formats = [fmt.lower() for fmt in formats]
    allowed = {"csv", "json", "parquet"}
    invalid = sorted(set(normalized_formats) - allowed)
    if invalid:
        raise DQMConfigError(f"Unsupported definition output format(s): {invalid}")

    definitions = raw.get("names") or raw.get("definitions") or []
    if isinstance(definitions, str):
        definitions = [definitions]
    if not isinstance(definitions, list) or not all(isinstance(name, str) for name in definitions):
        raise DQMConfigError("'outputs.definitions.names' must be a string or list of strings")
    if mode == "selected" and not definitions:
        raise DQMConfigError("'outputs.definitions.names' is required when mode is selected")

    return DefinitionOutputSpec(
        mode=mode,
        formats=normalized_formats,
        include_sde=bool(raw.get("include_sde", False)),
        definitions=definitions,
    )


def _parse_paths(raw: Any, base: Path) -> list[Path]:
    if raw is None:
        return []
    if isinstance(raw, str):
        return [_resolve_path(raw, base)]
    if not isinstance(raw, list) or not all(isinstance(path, str) for path in raw):
        raise DQMConfigError("Expected a path string or list of path strings")
    return [_resolve_path(path, base) for path in raw]


def _resolve_path(path: str, base: Path) -> Path:
    candidate = Path(path)
    return candidate if candidate.is_absolute() else base / candidate


def _is_cloud_path(path: str) -> bool:
    return path.startswith(("s3://", "az://", "abfs://", "gs://", "gcs://"))
