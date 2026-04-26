"""MeasureEvaluator — orchestrates FHIR Measure evaluation with optional audit."""

from __future__ import annotations

import json
import logging
import warnings
from datetime import date, datetime, timezone
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
            from fhir4ds.cql import parse_cql, CQLToSQLTranslator
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

        if len(group_dfs) == 1:
            result_df = group_dfs[0].drop(columns=["_group_id"])
        else:
            result_df = pd.concat(group_dfs, ignore_index=True)

        if generate_narratives and effective_mode != AuditMode.NONE:
            result_df = self._add_narratives(result_df, pop_map)

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
        """
        if isinstance(result, MeasureResult):
            df = result.dataframe
        elif hasattr(result, "df"):
            df = result.df()
        else:
            df = result

        def _count_col(col_name: str) -> int:
            if col_name not in df.columns:
                return 0
            col = df[col_name]
            if len(col) > 0 and isinstance(col.iloc[0], dict):
                return int(col.apply(lambda x: x.get("result", False) if isinstance(x, dict) else bool(x)).sum())
            return int(col.astype(bool).sum())

        ip = _count_col("initial_population")
        denom = _count_col("denominator")
        denom_excl = _count_col("denominator_exclusion")
        denom_except = _count_col("denominator_exception")
        numer = _count_col("numerator")
        numer_excl = _count_col("numerator_exclusion")

        denom_final = denom - denom_excl - denom_except
        numer_final = numer - numer_excl

        # CQL §10: Numerator is a subset of Denominator — cap numer_final
        # to denom_final so excluded-denominator patients are also removed
        # from the numerator count.
        if denom_final >= 0 and numer_final > denom_final:
            numer_final = denom_final

        if denom_final < 0:
            raise DQMError(
                f"Negative denominator_final ({denom_final}): denominator({denom}) < "
                f"exclusions({denom_excl}) + exceptions({denom_except}). "
                f"Check measure logic or data."
            )
        if numer_final < 0:
            raise DQMError(
                f"Negative numerator_final ({numer_final}): numerator({numer}) < "
                f"numerator_exclusion({numer_excl}). Check measure logic or data."
            )

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
        if "patient_id" in df.columns:
            total = df["patient_id"].nunique()
        else:
            total = len(df)

        return {
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

        summary = self.summary_report(df)

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

        # Build group populations
        groups = []
        for group in pop_map.groups:
            populations = []
            for pop in group.populations:
                col_name = self._col_name(pop.population_code)
                count = summary.get(col_name, 0)
                if col_name in ("denominator_final", "numerator_final"):
                    continue
                if isinstance(count, float):
                    count = int(count)
                populations.append({
                    "code": {
                        "coding": [{
                            "system": "http://terminology.hl7.org/CodeSystem/measure-population",
                            "code": pop.population_code,
                        }]
                    },
                    "count": count,
                })
            groups.append({"population": populations})

        report: dict[str, Any] = {
            "resourceType": "MeasureReport",
            "status": status,
            "type": report_type,
            "measure": pop_map.cql_library_ref,
            "date": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "period": {"start": ps, "end": pe},
            "group": groups,
        }

        if report_type == "summary":
            report["extension"] = [{
                "url": "http://hl7.org/fhir/us/davinci-deqm/StructureDefinition/performanceRate",
                "valueDecimal": summary["performance_rate"],
            }]

        return report

    # ── Internal Helpers ───────────────────────────────────────────────

    def _load_measure(self, measure_bundle: str | Path | dict) -> dict:
        """Load a Measure JSON from path or dict."""
        if isinstance(measure_bundle, dict):
            return measure_bundle
        path = Path(measure_bundle)
        if not path.exists():
            raise FileNotFoundError(f"Measure file not found: {measure_bundle}")
        return json.loads(path.read_text())

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
            # Catch CQL ParseError, TranslationError, and other downstream errors
            if type(e).__name__ in ('ParseError', 'TranslationError'):
                raise DQMError(f"Evaluation failed for group '{group.group_id}': {e}") from e
            raise
        finally:
            # Clear per-evaluation state to prevent memory accumulation
            try:
                from fhir4ds.cql.duckdb.udf.variable import clear_variables
                clear_variables(self.conn)
            except ImportError:
                pass

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

    def _add_narratives(self, df: pd.DataFrame, pop_map: PopulationMap) -> pd.DataFrame:
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
                    narrative = self._generate_narrative(val, pc)
                    return {**val, "narrative": narrative}

                df[col_name] = df[col_name].apply(_enrich)

        return df

    def _generate_narrative(self, val: Any, population_code: str) -> list[str]:
        """Generate narrative for a single cell value."""
        if isinstance(val, dict):
            evidence = val.get("evidence", [])
            is_satisfied = val.get("result", False)
            ev_dicts = [e if isinstance(e, dict) else {} for e in evidence]
            return self._narrative.generate(population_code, ev_dicts, is_satisfied)
        return self._narrative.generate(population_code, [], bool(val))

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
