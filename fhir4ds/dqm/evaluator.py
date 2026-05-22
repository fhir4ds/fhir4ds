"""MeasureEvaluator — orchestrates FHIR Measure evaluation with optional audit."""

from __future__ import annotations

import json
import logging
import warnings
from datetime import date, datetime, timezone
from html import escape
from pathlib import Path
from typing import Any

import duckdb
import numpy as np
import pandas as pd

from .audit import AuditEngine
from .errors import DQMError, MeasureParseError  # noqa: F401
from .models import MeasureResult
from .narrative import NarrativeGenerator
from .parser import MeasureParser
from .types import AuditMode, AuditOrStrategy, GroupMap, PopulationMap

logger = logging.getLogger(__name__)


class MeasureEvaluator:
    """Evaluate FHIR Measures against patient data with optional audit trails."""

    def __init__(
        self,
        conn: Any,
        audit_or_strategy: AuditOrStrategy = AuditOrStrategy.TRUE_BRANCH,
        narrative_generator: NarrativeGenerator | None = None,
    ):
        if conn is not None and not hasattr(conn, "execute"):
            raise TypeError(
                f"Expected a DuckDB connection for 'conn', got {type(conn).__name__}"
            )
        self.conn = conn
        self._parser = MeasureParser()
        self._audit_engine = AuditEngine()
        self._audit_or_strategy = audit_or_strategy
        self._narrative = narrative_generator or NarrativeGenerator()
        # Stored after evaluate() for downstream exports
        self._last_pop_map: PopulationMap | None = None
        self._last_parameters: dict | None = None
        # Cache expensive registries across evaluate() calls (QA-005)
        self._cached_fhir_schema: Any = None
        self._cached_profile_registry: Any = None
        self._cached_model_config: Any = None

    def evaluate(
        self,
        measure_bundle: str | Path | dict,
        cql_library_path: str | Path,
        parameters: dict | None = None,
        audit: bool = False,
        audit_mode: str | AuditMode = AuditMode.NONE,
        filter_to_ip: bool = False,
        patient_ids: list[str] | None = None,
        include_paths: list[str] | None = None,
        generate_narratives: bool = False,
    ) -> MeasureResult:
        """Evaluate a FHIR Measure against the resources table.

        Args:
            measure_bundle: Path to Measure JSON, or parsed dict.
            cql_library_path: Path to the CQL library file (.cql).
            parameters: CQL parameter overrides.
            audit: If True, use full audit mode (backward compat).
                   Ignored when ``audit_mode`` is explicitly set to a
                   non-NONE value.
            audit_mode: Controls audit granularity:
                - ``"none"``: No audit (default).
                - ``"population"``: Population-only audit — lightweight
                  struct_pack(result, evidence) from retrieve CTEs without
                  expression-level wrapping.  Much smaller SQL.
                - ``"full"``: Full expression wrapping with audit_and/or/leaf
                  macros for maximum evidence detail.
            filter_to_ip: If True, only return rows for patients who meet
                the Initial Population criteria.
            patient_ids: Optional patient ID filter.
            include_paths: Paths to directories containing included CQL libraries.
            generate_narratives: If True (requires audit), enriches each
                   audit struct in-place with a ``narrative`` field containing
                   a plain-English explanation.  No separate columns are added.

        Returns:
            MeasureResult containing the DataFrame, population map, and parameters.
            Access the DataFrame via ``result.dataframe``.

        Raises:
            FileNotFoundError: If measure_bundle or cql_library_path not found.
            MeasureParseError: If Measure JSON is malformed.
            DQMError: If CQL translation or execution fails.
            ValueError: If generate_narratives=True but audit is disabled.
        """
        # Resolve effective audit mode (backward compat: audit=True → FULL)
        effective_mode = AuditMode(audit_mode)
        if effective_mode == AuditMode.NONE and audit:
            effective_mode = AuditMode.FULL

        if generate_narratives and effective_mode == AuditMode.NONE:
            raise ValueError("Narratives require audit=True")

        measure_dict = self._load_measure(measure_bundle)
        pop_map = self._parser.parse(measure_dict)
        self._last_pop_map = pop_map
        self._last_parameters = parameters or {}

        cql_path = Path(cql_library_path)
        if not cql_path.exists():
            raise FileNotFoundError(f"CQL library not found: {cql_library_path}")

        try:
            from fhir4ds.cql import CQLToSQLTranslator, parse_cql
        except ImportError as e:
            raise DQMError(f"cql-py is required: {e}") from e

        # Evaluate each group
        group_dfs: list[pd.DataFrame] = []
        for group in pop_map.groups:
            df = self._evaluate_group(
                group=group,
                pop_map=pop_map,
                cql_path=cql_path,
                parameters=parameters or {},
                patient_ids=patient_ids,
                audit_mode=effective_mode,
                include_paths=include_paths,
                parse_cql=parse_cql,
                translator_cls=CQLToSQLTranslator,
            )
            if filter_to_ip:
                df = self._filter_to_initial_population(df, effective_mode)
            df["_group_id"] = group.group_id
            group_dfs.append(df)

        if not group_dfs:
            raise DQMError(f"Measure '{pop_map.measure_id}' produced no results")

        # Prune evidence before concatenation to preserve group context
        if effective_mode != AuditMode.NONE:
            for i, gdf in enumerate(group_dfs):
                group_dfs[i] = self._prune_population_evidence(gdf, pop_map)

        if len(group_dfs) == 1:
            result_df = group_dfs[0].drop(columns=["_group_id"])
        else:
            result_df = pd.concat(group_dfs, ignore_index=True)

        if generate_narratives and effective_mode != AuditMode.NONE:
            result_df = self._add_narratives(result_df, pop_map, effective_mode)

        populations = {
            self._col_name(p.population_code): p.cql_expression
            for g in pop_map.groups
            for p in g.populations
        }
        return MeasureResult(
            dataframe=result_df,
            populations=populations,
            parameters=parameters or {},
            measure_url=pop_map.cql_library_ref,
            pop_map=pop_map,
        )

    def summary_report(self, result: Any) -> dict:
        """Generate a summary report from evaluation results.

        Args:
            result: MeasureResult, DataFrame, or a DuckDB relation.

        Returns:
            Dict with population counts and performance rate.
            For multi-group measures (DataFrame has ``_group_id`` column),
            the dict additionally contains a ``"groups"`` key mapping each
            group_id to its own summary dict.
        """
        pop_map: PopulationMap | None = None
        if isinstance(result, MeasureResult):
            df = result.dataframe
            pop_map = result.pop_map
        elif hasattr(result, "df"):
            df = result.df()
        else:
            df = result
            pop_map = self._last_pop_map

        def _summary_for_df(frame: pd.DataFrame, group: GroupMap | None = None) -> dict:
            def _population_mask(col_name: str) -> pd.Series:
                if col_name not in frame.columns:
                    return pd.Series(False, index=frame.index, dtype=bool)

                def _is_true(value: Any) -> bool:
                    if isinstance(value, dict):
                        value = value.get("result", False)
                    if value is None:
                        return False
                    try:
                        if pd.isna(value):
                            return False
                    except (TypeError, ValueError):
                        pass
                    return bool(value)

                return frame[col_name].apply(_is_true).astype(bool)

            population_masks = self._population_masks(frame, _population_mask)
            ip_mask = population_masks["initial_population"]
            denom_mask = population_masks["denominator"]
            denom_excl_mask = population_masks["denominator_exclusion"]
            denom_after_excl_mask = population_masks["denominator_after_exclusion"]
            numer_mask = population_masks["numerator"]
            denom_except_mask = (
                denom_after_excl_mask
                & ~numer_mask
                & _population_mask("denominator_exception")
            )
            population_masks["denominator_exception"] = denom_except_mask
            population_masks["denominator_final"] = denom_after_excl_mask & ~denom_except_mask
            numer_excl_mask = population_masks["numerator_exclusion"]

            ip = int(ip_mask.sum())
            denom = int(denom_mask.sum())
            denom_excl = int(denom_excl_mask.sum())
            denom_except = int(denom_except_mask.sum())
            numer = int(numer_mask.sum())
            numer_excl = int(numer_excl_mask.sum())

            denom_final = int(population_masks["denominator_final"].sum())
            numer_final = int(population_masks["numerator_final"].sum())

            if denom_final > 0:
                performance_rate = numer_final / denom_final
                if performance_rate < 0.0 or performance_rate > 1.0:
                    logger.warning(
                        "Performance rate %.4f out of [0,1] range "
                        "(numer_final=%d, denom_final=%d) - clamping",
                        performance_rate, numer_final, denom_final,
                    )
                    performance_rate = max(0.0, min(1.0, performance_rate))
            else:
                performance_rate = 0.0

            # Use distinct patient count if patient_id column exists,
            # guarding against any residual row duplication from audit JOINs.
            if "patient_id" in frame.columns:
                total = frame["patient_id"].nunique()
            else:
                total = len(frame)

            summary = {
                "initial_population": ip,
                "denominator": denom,
                "denominator_exclusion": denom_excl,
                "denominator_exception": denom_except,
                "denominator_final": denom_final,
                "numerator": numer,
                "numerator_exclusion": numer_excl,
                "numerator_final": numer_final,
                "performance_rate": round(performance_rate, 4),
                "total_patients": total,
            }

            if group is not None and group.stratifiers:
                summary["stratifiers"] = self._stratifier_summaries(
                    frame, group, population_masks
                )

            return summary

        group_by_id = {g.group_id: g for g in pop_map.groups} if pop_map else {}
        sole_group = pop_map.groups[0] if pop_map and len(pop_map.groups) == 1 else None

        overall = _summary_for_df(df, sole_group if "_group_id" not in df.columns else None)

        # Multi-group: add per-group breakdowns
        if "_group_id" in df.columns:
            group_summaries: dict[str, dict] = {}
            for gid in df["_group_id"].unique():
                gdf = df[df["_group_id"] == gid]
                # Drop _group_id so it doesn't interfere with patient counts
                group_summaries[str(gid)] = _summary_for_df(
                    gdf.drop(columns=["_group_id"]),
                    group_by_id.get(str(gid)),
                )
            overall["groups"] = group_summaries

        return overall

    def _population_masks(self, frame: pd.DataFrame, population_mask: Any) -> dict[str, pd.Series]:
        """Build DQM population masks with exclusion/exception semantics applied."""
        ip_mask = population_mask("initial_population")
        denom_mask = ip_mask & population_mask("denominator")
        denom_excl_mask = denom_mask & population_mask("denominator_exclusion")
        denom_after_excl_mask = denom_mask & ~denom_excl_mask
        numer_mask = denom_after_excl_mask & population_mask("numerator")
        numer_excl_mask = numer_mask & population_mask("numerator_exclusion")

        false_mask = pd.Series(False, index=frame.index, dtype=bool)
        return {
            "initial_population": ip_mask,
            "denominator": denom_mask,
            "denominator_exclusion": denom_excl_mask,
            "denominator_after_exclusion": denom_after_excl_mask,
            "denominator_exception": false_mask,
            "denominator_final": denom_after_excl_mask,
            "numerator": numer_mask,
            "numerator_exclusion": numer_excl_mask,
            "numerator_final": numer_mask & ~numer_excl_mask,
            "measure_population": ip_mask & population_mask("measure_population"),
        }

    def _stratifier_summaries(
        self,
        frame: pd.DataFrame,
        group: GroupMap,
        population_masks: dict[str, pd.Series],
    ) -> list[dict[str, Any]]:
        """Summarize configured Measure stratifiers for one group frame."""
        summaries: list[dict[str, Any]] = []
        for strat_index, stratifier in enumerate(group.stratifiers):
            base = {
                "id": stratifier.stratifier_id,
                "code_text": stratifier.code_text,
                "strata": [],
            }
            if stratifier.components:
                component_cols = [
                    self._stratifier_component_col(strat_index, comp_index)
                    for comp_index, _ in enumerate(stratifier.components)
                ]
                if not all(col in frame.columns for col in component_cols):
                    summaries.append(base)
                    continue
                columns = tuple(component_cols)
                keys = frame.apply(
                    lambda row, columns=columns: tuple(
                        self._stratifier_value(row[col]) for col in columns
                    ),
                    axis=1,
                )
                for key in self._ordered_unique(keys):
                    mask = keys == key
                    components = [
                        {
                            "id": component.component_id,
                            "code_text": component.code_text,
                            "value": value,
                            "text": self._stratum_value_text(value),
                        }
                        for component, value in zip(stratifier.components, key, strict=True)
                    ]
                    base["strata"].append(
                        {
                            "components": components,
                            "population": self._stratum_population_counts(
                                mask, group, population_masks
                            ),
                        }
                    )
            else:
                col_name = self._stratifier_col(strat_index)
                if col_name not in frame.columns:
                    summaries.append(base)
                    continue
                values = frame[col_name].apply(self._stratifier_value)
                keys = self._ordered_unique(values)
                if self._has_boolean_values(keys):
                    keys = [True, False]
                for key in keys:
                    mask = values == key
                    base["strata"].append(
                        {
                            "value": key,
                            "text": self._stratum_value_text(key),
                            "population": self._stratum_population_counts(
                                mask, group, population_masks
                            ),
                        }
                    )
            summaries.append(base)
        return summaries

    def _stratum_population_counts(
        self,
        stratum_mask: pd.Series,
        group: GroupMap,
        population_masks: dict[str, pd.Series],
    ) -> dict[str, int]:
        """Count each configured population inside a stratum."""
        counts: dict[str, int] = {}
        for pop in group.populations:
            col_name = self._col_name(pop.population_code)
            mask = population_masks.get(col_name)
            if mask is None:
                mask = pd.Series(False, index=stratum_mask.index, dtype=bool)
            counts[pop.population_code] = int((stratum_mask & mask).sum())
        return counts

    @staticmethod
    def _stratifier_value(value: Any) -> Any:
        """Return the value part of a raw or audit-wrapped stratifier cell."""
        if isinstance(value, dict) and "result" in value:
            value = value.get("result")
        try:
            if pd.isna(value):
                return None
        except (TypeError, ValueError):
            pass
        if isinstance(value, np.generic):
            return value.item()
        if isinstance(value, (dict, list)):
            return json.dumps(value, sort_keys=True, default=str)
        return value

    @staticmethod
    def _ordered_unique(values: Any) -> list[Any]:
        """Return unique values in first-seen order."""
        seen: set[str] = set()
        out: list[Any] = []
        for value in values:
            key = json.dumps(value, sort_keys=True, default=str)
            if key in seen:
                continue
            seen.add(key)
            out.append(value)
        return out

    @staticmethod
    def _has_boolean_values(values: list[Any]) -> bool:
        """Whether a stratum value set is boolean-shaped."""
        return any(isinstance(value, (bool, np.bool_)) for value in values)

    @staticmethod
    def _stratum_value_text(value: Any) -> str:
        """Serialize a stratum value into MeasureReport text form."""
        if isinstance(value, (bool, np.bool_)):
            return "true" if bool(value) else "false"
        if value is None:
            return "null"
        return str(value)

    # ── Export Methods ──────────────────────────────────────────────────

    def to_csv(self, result: pd.DataFrame | MeasureResult, path: str | Path) -> Path:
        """Export evaluation results to CSV.

        Dict/list columns (e.g., audit structs) are serialized as JSON strings
        to ensure round-trip fidelity.

        Args:
            result: MeasureResult or DataFrame from evaluate().
            path: Destination file path.

        Returns:
            Path to the written CSV file.
        """
        out = Path(path)
        df = result.dataframe if isinstance(result, MeasureResult) else result
        # Serialize complex columns (dicts/lists) as JSON, not Python repr
        df_out = df.copy()
        for col in df_out.columns:
            sample = df_out[col].dropna().head(1)
            if not sample.empty and isinstance(sample.iloc[0], (dict, list)):
                df_out[col] = df_out[col].apply(
                    lambda x: json.dumps(x, default=str) if isinstance(x, (dict, list)) else x
                )
        df_out.to_csv(out, index=False)
        return out

    def to_measure_report(
        self,
        result: pd.DataFrame | MeasureResult,
        period_start: str | date | None = None,
        period_end: str | date | None = None,
        status: str = "complete",
        report_type: str = "summary",
    ) -> dict:
        """Generate a FHIR MeasureReport resource from evaluation results.

        Args:
            result: MeasureResult from evaluate(), or a DataFrame (legacy).
            period_start: Measurement period start (ISO date string or date).
            period_end: Measurement period end (ISO date string or date).
            status: Report status (default: "complete").
            report_type: Report type — "summary", "individual", "subject-list".

        Returns:
            Dict conforming to FHIR MeasureReport resource structure.
        """
        if isinstance(result, MeasureResult):
            pop_map = result.pop_map
            params = result.parameters
            df = result.dataframe
        else:
            # Legacy: fall back to instance state (deprecated)
            warnings.warn(
                "Passing a DataFrame to to_measure_report() is deprecated. "
                "Pass the MeasureResult returned by evaluate() instead.",
                DeprecationWarning,
                stacklevel=2,
            )
            pop_map = self._last_pop_map
            params = self._last_parameters or {}
            df = result

        if pop_map is None:
            raise DQMError("No evaluation has been run yet. Call evaluate() first.")
        if report_type == "individual":
            self._validate_individual_report_frame(df)

        summary_input: Any = result if isinstance(result, MeasureResult) else df
        summary = self.summary_report(summary_input)
        group_summaries = summary.get("groups", {})

        # Resolve period
        ps = _to_date_str(period_start) if period_start else None
        pe = _to_date_str(period_end) if period_end else None
        if ps is None or pe is None:
            mp = params.get("Measurement Period")
            if isinstance(mp, (list, tuple)) and len(mp) >= 2:
                ps = ps or _to_date_str(mp[0])
                pe = pe or _to_date_str(mp[1])
        if ps is None or pe is None:
            raise DQMError(
                "Measurement period is required but was not provided. "
                "Pass period_start/period_end or set the 'Measurement Period' parameter."
            )

        # Build group populations — use per-group summary when available
        groups = []
        for group in pop_map.groups:
            group_summary = group_summaries.get(group.group_id, summary)
            populations = []
            for pop in group.populations:
                col_name = self._col_name(pop.population_code)
                count = group_summary.get(col_name, 0)
                if col_name in ("denominator_final", "numerator_final"):
                    continue
                if isinstance(count, float):
                    count = int(count)
                population_report = {
                    "code": {
                        "coding": [{
                            "system": "http://terminology.hl7.org/CodeSystem/measure-population",
                            "code": pop.population_code,
                        }]
                    },
                    "count": count,
                }
                if pop.source_population_id:
                    population_report["id"] = pop.source_population_id
                    population_report["extension"] = [{
                        "url": "http://hl7.org/fhir/5.0/StructureDefinition/extension-MeasureReport.group.population.linkId",
                        "valueString": pop.source_population_id,
                    }]
                if report_type == "individual":
                    support = self._supporting_evidence_extensions(df, pop)
                    if support:
                        population_report.setdefault("extension", []).extend(support)
                populations.append(population_report)
            group_report: dict[str, Any] = {"population": populations}
            if group.source_group_id:
                group_report["id"] = group.source_group_id
                group_report["extension"] = [{
                    "url": "http://hl7.org/fhir/5.0/StructureDefinition/extension-MeasureReport.group.linkId",
                    "valueString": group.source_group_id,
                }]
            stratifier_summaries = group_summary.get("stratifiers", [])
            if stratifier_summaries:
                group_report["stratifier"] = [
                    self._measure_report_stratifier(strat_summary, group)
                    for strat_summary in stratifier_summaries
                ]
            groups.append(group_report)

        report: dict[str, Any] = {
            "resourceType": "MeasureReport",
            "status": status,
            "type": report_type,
            "measure": pop_map.cql_library_ref,
            "date": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "period": {"start": ps, "end": pe},
            "group": groups,
        }

        if report_type == "individual":
            report["meta"] = {
                "profile": [
                    "http://hl7.org/fhir/us/davinci-deqm/StructureDefinition/indv-measurereport-deqm"
                ]
            }
            patient_id = self._single_patient_id(df)
            if patient_id:
                report["subject"] = {"reference": f"Patient/{patient_id}"}
            report["text"] = self._individual_report_text(report, patient_id)

        if report_type == "summary":
            report["extension"] = [{
                "url": "http://hl7.org/fhir/us/davinci-deqm/StructureDefinition/performanceRate",
                "valueDecimal": summary["performance_rate"],
            }]

        return report

    def _validate_individual_report_frame(self, df: pd.DataFrame) -> None:
        if "patient_id" not in df.columns:
            raise DQMError("Individual MeasureReport requires a patient_id column.")
        patient_ids = df["patient_id"].dropna().astype(str).unique()
        if len(patient_ids) != 1:
            raise DQMError(
                "Individual MeasureReport requires exactly one patient row; "
                f"found {len(patient_ids)} patients."
            )

    def _single_patient_id(self, df: pd.DataFrame) -> str | None:
        if "patient_id" not in df.columns:
            return None
        patient_ids = df["patient_id"].dropna().astype(str).unique()
        return patient_ids[0] if len(patient_ids) == 1 else None

    def _supporting_evidence_extensions(
        self, df: pd.DataFrame, pop: Any,
    ) -> list[dict[str, Any]]:
        if not pop.supporting_evidence or len(df) != 1:
            return []
        row = df.iloc[0]
        extensions: list[dict[str, Any]] = []
        for ev in pop.supporting_evidence:
            col_name = f"evidence_{self._col_name(ev.name)}"
            if col_name not in df.columns:
                continue
            extension_children: list[dict[str, Any]] = [
                {"url": "name", "valueCode": ev.name}
            ]
            if ev.description:
                extension_children.append({"url": "description", "valueString": ev.description})
            if ev.code:
                extension_children.append({"url": "code", "valueCodeableConcept": ev.code})
            extension_children.extend(self._supporting_evidence_value_extensions(row[col_name]))
            extensions.append({
                "url": "http://hl7.org/fhir/StructureDefinition/cqf-supportingEvidence",
                "extension": extension_children,
            })
        return extensions

    def _supporting_evidence_value_extensions(self, value: Any) -> list[dict[str, Any]]:
        value = self._normalize_evidence_value(value)
        if self._is_null_like(value):
            return [{
                "url": "value",
                "extension": [
                    {
                        "url": "http://hl7.org/fhir/StructureDefinition/data-absent-reason",
                        "valueCode": "unknown",
                    },
                    {
                        "url": "http://hl7.org/fhir/StructureDefinition/cqf-cqlType",
                        "valueString": "System.Any",
                    },
                ],
            }]
        if isinstance(value, (list, tuple, np.ndarray)):
            if len(value) == 0:
                return [{
                    "url": "value",
                    "extension": [
                        {
                            "url": "http://hl7.org/fhir/StructureDefinition/cqf-isEmptyList",
                            "valueBoolean": True,
                        },
                        {
                            "url": "http://hl7.org/fhir/StructureDefinition/cqf-cqlType",
                            "valueString": "List<System.Any>",
                        },
                    ],
                }]
            result: list[dict[str, Any]] = []
            for item in value:
                result.extend(self._supporting_evidence_value_extensions(item))
            return result
        return [self._supporting_evidence_single_value(value)]

    def _supporting_evidence_single_value(self, value: Any) -> dict[str, Any]:
        value = self._normalize_evidence_value(value)
        if isinstance(value, bool):
            return {"url": "value", "valueBoolean": value}
        if isinstance(value, int) and not isinstance(value, bool):
            return {"url": "value", "valueInteger": value}
        if isinstance(value, float):
            return {"url": "value", "valueDecimal": value}
        if isinstance(value, dict):
            fhir_value = self._dict_to_fhir_value(value)
            if fhir_value:
                return {"url": "value", **fhir_value}
            return {
                "url": "value",
                "extension": [
                    self._tuple_field_extension(key, val)
                    for key, val in value.items()
                ],
            }
        return {"url": "value", "valueString": str(value)}

    def _dict_to_fhir_value(self, value: dict[str, Any]) -> dict[str, Any] | None:
        resource_type = value.get("resourceType")
        resource_id = value.get("id")
        if resource_type and resource_id:
            return {"valueReference": {"reference": f"{resource_type}/{resource_id}"}}
        if "reference" in value and isinstance(value["reference"], str):
            return {"valueReference": {"reference": value["reference"]}}
        if "coding" in value or ("text" in value and any(k in value for k in ("coding", "code"))):
            return {"valueCodeableConcept": value}
        if "system" in value and "code" in value:
            return {"valueCoding": value}
        if "value" in value and any(k in value for k in ("unit", "code", "system")):
            return {"valueQuantity": value}
        if "start" in value or "end" in value:
            return {"valuePeriod": value}
        return None

    def _tuple_field_extension(self, key: str, value: Any) -> dict[str, Any]:
        child = self._supporting_evidence_single_value(value)
        child["url"] = key if key else "field"
        return child

    def _normalize_evidence_value(self, value: Any) -> Any:
        if isinstance(value, np.generic):
            return value.item()
        if isinstance(value, str):
            stripped = value.strip()
            if stripped.startswith(("{", "[")):
                try:
                    return json.loads(stripped)
                except json.JSONDecodeError:
                    return value
        return value

    def _is_null_like(self, value: Any) -> bool:
        if value is None:
            return True
        if isinstance(value, float) and np.isnan(value):
            return True
        return bool(pd.isna(value)) if not isinstance(value, (dict, list, tuple, np.ndarray)) else False

    def _individual_report_text(
        self, report: dict[str, Any], patient_id: str | None,
    ) -> dict[str, str]:
        subject = escape(patient_id or "unknown")
        parts = [f"Measure report for Patient/{subject}."]
        for group in report.get("group", []):
            for pop in group.get("population", []):
                code = pop.get("code", {}).get("coding", [{}])[0].get("code", "population")
                count = pop.get("count", 0)
                parts.append(f"{escape(code)}: {'met' if count else 'not met'}.")
        return {
            "status": "generated",
            "div": f"<div xmlns=\"http://www.w3.org/1999/xhtml\"><p>{' '.join(parts)}</p></div>",
        }

    def _measure_report_stratifier(
        self, stratifier_summary: dict[str, Any], group: GroupMap
    ) -> dict[str, Any]:
        """Convert an internal stratifier summary to FHIR MeasureReport shape."""
        stratifier: dict[str, Any] = {"stratum": []}
        if stratifier_summary.get("id"):
            stratifier["id"] = stratifier_summary["id"]
        if stratifier_summary.get("code_text"):
            stratifier["code"] = {"text": stratifier_summary["code_text"]}

        for stratum_summary in stratifier_summary.get("strata", []):
            stratum: dict[str, Any] = {
                "population": self._measure_report_stratum_populations(
                    stratum_summary.get("population", {}),
                    group,
                )
            }
            if "components" in stratum_summary:
                stratum["component"] = [
                    {
                        **(
                            {"code": {"text": component["code_text"]}}
                            if component.get("code_text")
                            else {}
                        ),
                        "value": {"text": component.get("text", "null")},
                    }
                    for component in stratum_summary["components"]
                ]
            else:
                stratum["value"] = {"text": stratum_summary.get("text", "null")}
            stratifier["stratum"].append(stratum)

        return stratifier

    def _measure_report_stratum_populations(
        self, counts: dict[str, int], group: GroupMap
    ) -> list[dict[str, Any]]:
        """Build population count entries for a MeasureReport stratum."""
        populations: list[dict[str, Any]] = []
        for pop in group.populations:
            populations.append({
                "code": {
                    "coding": [{
                        "system": "http://terminology.hl7.org/CodeSystem/measure-population",
                        "code": pop.population_code,
                    }]
                },
                "count": int(counts.get(pop.population_code, 0)),
            })
        return populations

    # ── Internal Helpers ───────────────────────────────────────────────

    def _load_measure(self, measure_bundle: str | Path | dict) -> dict:
        """Load a Measure JSON from path or dict."""
        if isinstance(measure_bundle, dict):
            return measure_bundle
        path = Path(measure_bundle)
        if not path.exists():
            raise FileNotFoundError(f"Measure file not found: {measure_bundle}")
        try:
            return json.loads(path.read_text())
        except json.JSONDecodeError as e:
            raise MeasureParseError(
                f"Invalid JSON in measure file '{measure_bundle}': {e}"
            ) from e

    def _evaluate_group(
        self,
        group: GroupMap,
        pop_map: PopulationMap,
        cql_path: Path,
        parameters: dict,
        patient_ids: list[str] | None,
        audit_mode: AuditMode,
        include_paths: list[str] | None,
        parse_cql: Any,
        translator_cls: Any,
    ) -> pd.DataFrame:
        """Evaluate a single group from a FHIR Measure. Always returns DataFrame."""
        cql_text = cql_path.read_text()
        library = parse_cql(cql_text)

        translator = translator_cls(connection=self.conn)

        # Reuse cached registries to avoid ~1.5MB allocation per call
        if self._cached_fhir_schema is not None:
            translator.fhir_schema = self._cached_fhir_schema
        else:
            self._cached_fhir_schema = translator.fhir_schema

        if self._cached_profile_registry is not None:
            translator.profile_registry = self._cached_profile_registry
        else:
            self._cached_profile_registry = translator.profile_registry

        if audit_mode == AuditMode.FULL:
            translator.context.set_audit_mode(True)
            if self._audit_or_strategy == AuditOrStrategy.ALL:
                translator.context.set_audit_or_strategy("all")
        elif audit_mode == AuditMode.POPULATION:
            translator.context.set_audit_mode(True)
            translator.context.set_audit_expressions(False)
            if self._audit_or_strategy == AuditOrStrategy.ALL:
                translator.context.set_audit_or_strategy("all")

        # Default include path: the directory containing the CQL file, so that
        # sibling CQL libraries (Status, QICoreCommon, etc.) are auto-discovered.
        effective_include_paths = list(include_paths) if include_paths else [cql_path.parent]
        translator.set_library_loader(self._make_library_loader(effective_include_paths, parse_cql))

        output_columns = {
            self._col_name(p.population_code): p.cql_expression
            for p in group.populations
        }
        for strat_index, stratifier in enumerate(group.stratifiers):
            if stratifier.cql_expression:
                output_columns[self._stratifier_col(strat_index)] = stratifier.cql_expression
            for comp_index, component in enumerate(stratifier.components):
                output_columns[
                    self._stratifier_component_col(strat_index, comp_index)
                ] = component.cql_expression

        if audit_mode != AuditMode.NONE:
            for pop in group.populations:
                for ev in pop.supporting_evidence:
                    output_columns[f"evidence_{self._col_name(ev.name)}"] = ev.cql_expression

        try:
            sql = translator.translate_library_to_population_sql(
                library=library,
                output_columns=output_columns,
                parameters=parameters,
                patient_ids=patient_ids,
            )
            # Audit-mode SQL generates deeply nested audit_and/audit_or expressions;
            # raise the limit to avoid DuckDB's default 1000-node cap.
            self.conn.execute("SET max_expression_depth TO 10000")
            df = self.conn.execute(sql).df()

            # Full audit mode may produce Cartesian-product row explosion
            # (N^K rows per patient) because retrieve CTEs are LEFT JOINed
            # to capture per-resource evidence.  Deduplicate to one row per
            # patient by keeping the first occurrence — evidence items across
            # duplicate rows are identical per patient since the audit macros
            # (audit_and / audit_or) already merge evidence lists.
            if audit_mode == AuditMode.FULL and "patient_id" in df.columns:
                pre_dedup = len(df)
                df = df.drop_duplicates(subset=["patient_id"], keep="first")
                if len(df) < pre_dedup:
                    logger.debug(
                        "Audit dedup: %d → %d rows (removed %d Cartesian duplicates)",
                        pre_dedup, len(df), pre_dedup - len(df),
                    )
                df = df.reset_index(drop=True)

            return df
        except (DQMError, KeyboardInterrupt):
            raise
        except (duckdb.Error, ValueError, FileNotFoundError, RuntimeError,
                SyntaxError, TypeError) as e:
            raise DQMError(f"Evaluation failed for group '{group.group_id}': {e}") from e
        except Exception as e:
            # Import actual exception classes instead of string-matching type names
            from fhir4ds.cql.errors import ParseError, TranslationError
            if isinstance(e, (ParseError, TranslationError)):
                raise DQMError(f"Evaluation failed for group '{group.group_id}': {e}") from e
            raise
        finally:
            # Clear per-evaluation state to prevent memory accumulation
            try:
                from fhir4ds.cql.duckdb.udf.variable import clear_variables
                clear_variables(self.conn)
            except ImportError:
                pass

    def _prune_population_evidence(
        self, df: pd.DataFrame, pop_map: PopulationMap,
    ) -> pd.DataFrame:
        """Apply persona-based evidence pruning to population columns.

        For exclusion populations, evidence is only relevant when the patient
        IS excluded. For non-excluded patients the evidence is pruned to reduce
        noise in downstream narratives and exports.
        """
        for group in pop_map.groups:
            for pop in group.populations:
                col_name = self._col_name(pop.population_code)
                if col_name not in df.columns:
                    continue

                def _prune(
                    cell,
                    persona=pop.audit_persona,
                    code=pop.population_code,
                    column=col_name,
                ):
                    if not isinstance(cell, dict):
                        return cell
                    try:
                        pruned = self._audit_engine.prune_evidence(
                            {column: cell}, code, persona
                        )
                        return {**cell, "evidence": pruned}
                    except Exception:
                        logger.warning(
                            "Evidence pruning failed for population %s — "
                            "returning original cell",
                            code, exc_info=True,
                        )
                        return cell

                df[col_name] = df[col_name].apply(_prune)
        return df

    def _filter_to_initial_population(
        self, df: pd.DataFrame, audit_mode: AuditMode,
    ) -> pd.DataFrame:
        """Filter DataFrame to only rows where Initial Population is truthy."""
        ip_col = self._col_name("initial-population")
        if ip_col not in df.columns:
            return df
        if audit_mode != AuditMode.NONE:
            mask = df[ip_col].apply(
                lambda x: x.get("result", False) if isinstance(x, dict) else bool(x)
            )
        else:
            mask = df[ip_col].astype(bool)
        return df[mask].reset_index(drop=True)

    def _add_narratives(self, df: pd.DataFrame, pop_map: PopulationMap,
                        audit_mode: AuditMode = AuditMode.FULL) -> pd.DataFrame:
        """Enrich audit struct columns with a ``narrative`` field in-place.

        Instead of adding separate ``*_narrative`` columns, this method updates
        each audit struct dict so it gains a ``narrative`` key.  The DataFrame
        schema is therefore unchanged — population columns remain as audit structs,
        just with an additional field.
        """
        for group in pop_map.groups:
            for pop in group.populations:
                col_name = self._col_name(pop.population_code)
                if col_name not in df.columns:
                    continue

                def _enrich(val, pc=pop.population_code):
                    if not isinstance(val, dict):
                        return val
                    narrative = self._generate_narrative(val, pc, audit_mode)
                    return {**val, "narrative": narrative}

                df[col_name] = df[col_name].apply(_enrich)

        return df

    def _generate_narrative(self, val: Any, population_code: str,
                            audit_mode: AuditMode = AuditMode.FULL) -> list[str]:
        """Generate narrative for a single cell value."""
        evidence_captured = audit_mode != AuditMode.POPULATION
        if isinstance(val, dict):
            evidence = val.get("evidence", [])
            is_satisfied = val.get("result", False)
            ev_dicts = [e if isinstance(e, dict) else {} for e in evidence]
            return self._narrative.generate(population_code, ev_dicts, is_satisfied,
                                            evidence_captured=evidence_captured)
        return self._narrative.generate(population_code, [], bool(val),
                                        evidence_captured=evidence_captured)

    def _make_library_loader(self, include_paths: list[str], parse_cql: Any):
        """Create a library loader function for included CQL libraries.

        Raises DQMError if a library file is found but fails to parse,
        since silent fallback would produce incorrect measure results.
        """
        def loader(alias: str):
            # Resolve canonical URLs to simple filenames.
            # e.g. "hl7.fhir.uv.cql.FHIRHelpers" → "FHIRHelpers"
            resolved_alias = alias.rsplit(".", 1)[-1] if "." in alias else alias
            for search_alias in dict.fromkeys([alias, resolved_alias]):
                for path in include_paths:
                    base = Path(path)
                    # Try exact name first, then versioned filenames (e.g. FHIRHelpers-4.4.000.cql)
                    candidates = [base / f"{search_alias}.cql"] + sorted(base.glob(f"{search_alias}-*.cql"))
                    for lib_file in candidates:
                        if lib_file.exists():
                            try:
                                return parse_cql(lib_file.read_text())
                            except (SyntaxError, ValueError, KeyError) as e:
                                raise DQMError(
                                    f"Failed to parse included library '{lib_file}': {e}"
                                ) from e
            return None
        return loader

    @staticmethod
    def _col_name(population_code: str) -> str:
        """Convert population code to column name."""
        return population_code.replace("-", "_")

    @staticmethod
    def _stratifier_col(index: int) -> str:
        """Generated output column name for a group stratifier."""
        return f"stratifier_{index + 1}"

    @staticmethod
    def _stratifier_component_col(stratifier_index: int, component_index: int) -> str:
        """Generated output column name for a composite stratifier component."""
        return f"stratifier_{stratifier_index + 1}_component_{component_index + 1}"


# ── Module-level helpers ───────────────────────────────────────────────


def _to_date_str(val: Any) -> str:
    """Convert a date/datetime/string to ISO date string.

    Raises ValueError for types that cannot represent a valid date.
    """
    if isinstance(val, datetime):
        return val.strftime("%Y-%m-%d")
    if isinstance(val, date):
        return val.isoformat()
    if isinstance(val, str):
        return val
    raise ValueError(
        f"Cannot convert {type(val).__name__!r} to a date string. "
        "Expected str, datetime.date, or datetime.datetime."
    )
