"""fhir4ds-mcp: MCP stdio server exposing the operations capabilities.

Install with `pip install fhir4ds-v2[mcp]`; run via the `fhir4ds-mcp`
entry point. Tools map 1:1 onto fhir4ds.operations. One DuckDB
connection per process (single-tenant stdio doctrine); dataset handles
reference the single active dataset.
"""

from __future__ import annotations

import sys
from typing import Any

__all__ = ["main", "build_server"]


def _require_mcp():
    try:
        from mcp.server.fastmcp import FastMCP
    except ImportError as exc:  # typed, actionable (INV-8)
        raise ImportError(
            "The MCP server requires the optional 'mcp' package. "
            "Install it with: pip install fhir4ds-v2[mcp]"
        ) from exc
    return FastMCP


# 5 MB inline resources[] payload cap (FDD §3.7).
_MAX_INLINE_BYTES = 5 * 1024 * 1024


def _check_inline_payload(resources: Any) -> None:
    import json

    size = len(json.dumps(resources, default=str).encode("utf-8"))
    if size > _MAX_INLINE_BYTES:
        from fhir4ds.operations.errors import input_error

        diag = input_error(
            f"Inline resources payload exceeds 5MB limit ({size} bytes). "
            "Write the resources to an NDJSON file and pass ndjson_paths instead.",
        )
        raise _ToolError(diag.to_dict())


class _ToolError(Exception):
    """Carries a pre-built diagnostics payload to the tool wrapper."""

    def __init__(self, payload: dict) -> None:
        super().__init__(payload.get("message", "tool error"))
        self.payload = payload


def build_server() -> Any:
    """Construct the FastMCP server (exposed for in-process tests)."""
    FastMCP = _require_mcp()
    from fhir4ds import create_connection
    from fhir4ds.operations import (
        DatasetSpec,
        LibraryText,
        evaluate_library,
        explain_patient,
        fhirpath_eval,
        load_dataset,
        parse_cql,
        run_tests,
        tests_input_from_dict,
        translate_cql,
    )
    from fhir4ds.operations.envelopes import _library_text_from_dict

    mcp: Any = FastMCP("fhir4ds")
    state: dict[str, Any] = {"conn": None, "handle": None, "includes": {}, "handle_seq": 0}

    def _conn():
        if state["conn"] is None:
            state["conn"] = create_connection()
        return state["conn"]

    def _libraries(raw_list: list[dict]) -> list[LibraryText]:
        libs = [_library_text_from_dict(item) for item in raw_list or []]
        for lib in libs:
            state["includes"][lib.name] = lib  # session include cache
        return libs

    def _resolve_main(libs: list[LibraryText], main_name: str) -> LibraryText:
        if main_name:
            for lib in libs:
                if lib.name == main_name:
                    return lib
            raise _ToolError(
                {"code": "not_found", "message": f"main library {main_name!r} not in libraries[]"}
            )
        return libs[-1]  # last library is the main by convention

    def _dataset(raw: Any) -> DatasetSpec | None:
        if raw is None:
            return None
        if isinstance(raw, dict) and set(raw.keys()) == {"handle"}:
            handle = raw["handle"]
            if handle != state["handle"]:
                raise _ToolError(
                    {
                        "code": "not_found",
                        "message": f"unknown dataset handle {handle!r} "
                        f"(active: {state['handle']!r})",
                    }
                )
            return None  # already loaded on the connection
        if isinstance(raw, dict) and "resources" in raw and raw.get("resources") is not None:
            _check_inline_payload(raw["resources"])
        from fhir4ds.operations import dataset_spec_from_dict

        return dataset_spec_from_dict(raw)

    def _maybe_cached(libs: list[LibraryText], main_name: str) -> list[LibraryText]:
        """Merge session include cache under caller-provided libraries."""
        merged = {lib.name: lib for lib in state["includes"].values()}
        for lib in libs:
            merged[lib.name] = lib  # explicit beats cached
        return list(merged.values())

    @mcp.tool()
    def parse_cql_tool(cql_text: str) -> dict:
        """Parse/validate CQL text; returns declaration metadata + diagnostics."""
        return parse_cql(cql_text).to_dict()

    @mcp.tool()
    def translate_cql_tool(libraries: list[dict], main: str = "") -> dict:
        """Translate a CQL library (plus includes) to SQL."""
        libs = _libraries(libraries)
        main_lib = _resolve_main(libs, main)
        return translate_cql(_maybe_cached(libs, main), main_lib).to_dict()

    @mcp.tool()
    def evaluate_library_tool(
        libraries: list[dict],
        dataset: dict | None = None,
        main: str = "",
        parameters: dict | None = None,
        output_columns: dict | None = None,
        emit_sql: bool = False,
    ) -> dict:
        """Evaluate a CQL library against a dataset; one row per patient."""
        libs = _libraries(libraries)
        main_lib = _resolve_main(libs, main)
        spec = _dataset(dataset)
        return evaluate_library(
            _maybe_cached(libs, main), main_lib, spec, _conn(),
            parameters=parameters, output_columns=output_columns,
            emit_sql=emit_sql,
        ).to_dict()

    @mcp.tool()
    def run_tests_tool(
        libraries: list[dict],
        dataset: dict | None = None,
        cases: dict | None = None,
        main: str = "",
        parameters: dict | None = None,
        output_columns: dict | None = None,
    ) -> dict:
        """Run declarative test cases; returns the verify envelope."""
        libs = _libraries(libraries)
        main_lib = _resolve_main(libs, main)
        spec = _dataset(dataset)
        try:
            parsed_cases = tests_input_from_dict(cases)
        except (ValueError, TypeError) as exc:
            from fhir4ds.operations.errors import input_error

            raise _ToolError(input_error(f"invalid cases: {exc}").to_dict()) from exc
        return run_tests(
            _maybe_cached(libs, main), main_lib, spec, parsed_cases, _conn(),
            parameters=parameters, output_columns=output_columns,
        ).to_dict()

    @mcp.tool()
    def fhirpath_eval_tool(expression: str, resource: dict) -> dict:
        """Evaluate a FHIRPath expression against one FHIR resource."""
        return fhirpath_eval(expression, resource).to_dict()

    @mcp.tool()
    def load_dataset_tool(dataset: dict) -> dict:
        """Load a dataset (inline resources, NDJSON/Bundle paths, valuesets)."""
        spec = _dataset(dataset)
        if spec is None:
            raise _ToolError(
                {"code": "input_error", "message": "load_dataset requires a dataset spec, not a handle"}
            )
        result = load_dataset(spec, _conn())
        if result.ok:
            state["handle_seq"] += 1
            state["handle"] = f"ds-{state['handle_seq']}"
            payload = result.to_dict()
            payload["handle"] = state["handle"]
            return payload
        return result.to_dict()

    @mcp.tool()
    def explain_patient_tool(
        libraries: list[dict],
        patient_id: str,
        dataset: dict | None = None,
        main: str = "",
        parameters: dict | None = None,
        output_columns: dict | None = None,
    ) -> dict:
        """Explain why a patient is in/out of each population (audit evidence)."""
        libs = _libraries(libraries)
        main_lib = _resolve_main(libs, main)
        spec = _dataset(dataset)
        return explain_patient(
            _maybe_cached(libs, main), main_lib, spec, patient_id, _conn(),
            parameters=parameters, output_columns=output_columns,
        ).to_dict()

    @mcp.tool()
    def compare_evidence_tool(
        baseline: dict,
        current: dict,
        output_columns: dict | None = None,
    ) -> dict:
        """Diff two evidence payloads (baseline vs current run).

        Accepts EvidenceResult envelopes (single patient) or
        {"patients": {id: {"populations": {...}}}} collections; returns
        the compare_evidence delta envelope.
        """
        from fhir4ds.operations import compare_evidence

        return compare_evidence(
            baseline, current, output_columns=output_columns
        ).to_dict()

    @mcp.tool()
    def measure_from_definitions_tool(
        libraries: list[dict],
        main: str = "",
        mapping: list[dict] | None = None,
        measure_name: str | None = None,
        group_id: str | None = None,
    ) -> dict:
        """Build/validate a FHIR Measure from a define->population-code
        mapping (explicit mapping only; no heuristics)."""
        from fhir4ds.operations import measure_from_definitions

        libs = _libraries(libraries)
        main_lib = _resolve_main(libs, main)
        return measure_from_definitions(
            libs, main_lib, mapping, measure_name=measure_name, group_id=group_id
        ).to_dict()

    @mcp.tool()
    def measure_population_map_tool(measure: dict) -> dict:
        """Measure -> [(population code, CQL define)] pairs (DQM
        MeasureParser authority)."""
        from fhir4ds.operations import measure_population_map

        pairs, diag = measure_population_map(measure)
        if diag is not None:
            return {"schema": 1, "ok": False, "diagnostics": [diag.to_dict()]}
        return {
            "schema": 1,
            "ok": True,
            "pairs": [{"code": c, "define": d} for c, d in pairs],
        }

    @mcp.tool()
    def measure_report_from_rows_tool(
        measure: dict,
        rows: list[dict],
        columns: list[str],
        period_start: str | None = None,
        period_end: str | None = None,
    ) -> dict:
        """Evaluation rows -> per-patient individual MeasureReports
        (0/1 boolean-basis membership counts)."""
        from fhir4ds.operations import measure_report_from_rows

        return measure_report_from_rows(
            measure, rows, columns,
            period_start=period_start, period_end=period_end,
        ).to_dict()

    @mcp.tool()
    def rows_from_measure_reports_tool(
        reports: dict | list,
        population_codes: list[str] | None = None,
    ) -> dict:
        """MeasureReports (single/list/Bundle) -> normalized boolean
        rows (patient_id + snake_case population columns)."""
        from fhir4ds.operations import rows_from_measure_reports

        return rows_from_measure_reports(
            reports, population_codes=population_codes
        ).to_dict()

    @mcp.tool()
    def measure_roundtrip_tool(
        libraries: list[dict],
        mapping: list[dict],
        dataset: dict | None = None,
        main: str = "",
    ) -> dict:
        """Composed Measure flow: build the Measure from the mapping,
        evaluate with Measure-derived output columns, materialize
        per-patient MeasureReports, and invert them back to rows."""
        from fhir4ds.operations import (
            evaluate_library,
            measure_from_definitions,
            measure_report_from_rows,
            rows_from_measure_reports,
        )
        from fhir4ds.operations.capabilities.measure import (
            output_columns_from_measure,
        )

        libs = _libraries(libraries)
        main_lib = _resolve_main(libs, main)
        m_env = measure_from_definitions(libs, main_lib, mapping=mapping)
        if not m_env.ok:
            return m_env.to_dict()
        out_cols = output_columns_from_measure(m_env.measure)
        spec = _dataset(dataset)
        ev = evaluate_library(libs, main_lib, spec, _conn(), output_columns=out_cols)
        if not ev.ok:
            return ev.to_dict()
        rep = measure_report_from_rows(m_env.measure, ev.rows, ev.columns)
        if not rep.ok:
            return rep.to_dict()
        return rows_from_measure_reports(
            list(rep.reports),
            population_codes=[e["code"] for e in mapping],
        ).to_dict()

    return mcp


def main() -> None:
    import asyncio

    # stdout hygiene (FDD §3.7): stdout belongs to JSON-RPC; engine prints go to stderr.
    sys.stdout = sys.stderr  # type: ignore[assignment]
    server = build_server()
    asyncio.run(server.run_stdio_async())
