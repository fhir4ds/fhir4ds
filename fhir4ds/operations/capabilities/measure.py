"""Measure/MeasureReport capabilities for FHIR-native population mapping.

Stateless, pandas-free (Pyodide-importable). Implements the
FEATURE_CLEANROOM_MEASURE_REPORTS.md design:

- measure_from_definitions: Measure resource from library boolean
  defines via an explicit mapping (no silent name heuristics).
- measure_report_from_rows: per-patient individual MeasureReports from
  evaluation rows (population membership as 0/1 counts).
- rows_from_measure_reports: inverse — MeasureReports (single, list, or
  Bundle) back to normalized rows (expected-values import / MADiE
  interop).
- flatten_view: run an authored ViewDefinition over staged resources on
  the caller's connection (exact-SQL doctrine; isolated temp-table
  staging, SO-3).

Population-role semantics resolve from ONE authority: the Measure
resource parsed by dqm.parser.MeasureParser (pure Python).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..envelopes import (
    DiagnosticCode,
    Diagnostics,
    LibraryText,
    _EnvelopeFields,
)
from ..errors import OperationError, diagnostic_from_exception
from ..library_sources import LibraryResolver

# Canonical order for FHIR CQM population roles (UI labels + Sankey
# ordering source; replaces string-prefix heuristics).
POPULATION_ORDER: tuple[str, ...] = (
    "initial-population",
    "denominator",
    "denominator-exclusion",
    "denominator-exception",
    "numerator",
    "numerator-exclusion",
    "measure-population",
    "measure-population-exclusion",
)

_POPULATION_SYSTEM = "http://terminology.hl7.org/CodeSystem/measure-population"
_POPULATION_BASIS_EXT = (
    "http://hl7.org/fhir/us/cqf-measures/StructureDefinition/cqfm-populationBasis"
)
_CQL_IDENTIFIER_LANGUAGE = "text/cql-identifier"


def _population_column(code: str) -> str:
    """DQM column convention: initial-population -> initial_population."""
    return code.replace("-", "_")


@dataclass(frozen=True)
class MeasureResult(_EnvelopeFields):
    ok: bool = True
    passed: object = None
    diagnostics: tuple = ()
    measure: dict[str, Any] = field(default_factory=dict)
    mapping: tuple[dict[str, str], ...] = ()

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {"schema": self.schema, "ok": self.ok}
        if self.passed is not None:
            out["passed"] = self.passed
        if self.diagnostics:
            out["diagnostics"] = [d.to_dict() for d in self.diagnostics]
        out["measure"] = self.measure
        out["mapping"] = [dict(m) for m in self.mapping]
        return out


@dataclass(frozen=True)
class MeasureReportResult(_EnvelopeFields):
    ok: bool = True
    passed: object = None
    diagnostics: tuple = ()
    reports: tuple[dict[str, Any], ...] = ()

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {"schema": self.schema, "ok": self.ok}
        if self.passed is not None:
            out["passed"] = self.passed
        if self.diagnostics:
            out["diagnostics"] = [d.to_dict() for d in self.diagnostics]
        out["reports"] = [dict(r) for r in self.reports]
        return out


@dataclass(frozen=True)
class MeasureRowsResult(_EnvelopeFields):
    ok: bool = True
    passed: object = None
    diagnostics: tuple = ()
    rows: tuple[dict[str, Any], ...] = ()
    columns: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {"schema": self.schema, "ok": self.ok}
        if self.passed is not None:
            out["passed"] = self.passed
        if self.diagnostics:
            out["diagnostics"] = [d.to_dict() for d in self.diagnostics]
        out["rows"] = [dict(r) for r in self.rows]
        out["columns"] = list(self.columns)
        return out


@dataclass(frozen=True)
class FlattenViewResult(_EnvelopeFields):
    ok: bool = True
    passed: object = None
    diagnostics: tuple = ()
    sql: str = ""
    columns: tuple[str, ...] = ()
    rows: tuple[dict[str, Any], ...] = ()

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {"schema": self.schema, "ok": self.ok}
        if self.passed is not None:
            out["passed"] = self.passed
        if self.diagnostics:
            out["diagnostics"] = [d.to_dict() for d in self.diagnostics]
        out["sql"] = self.sql
        out["columns"] = list(self.columns)
        out["rows"] = [dict(r) for r in self.rows]
        return out


def _validate_mapping(
    mapping: list[dict[str, str]] | None,
    definition_names: tuple[str, ...],
) -> tuple[list[tuple[str, str]], Diagnostics | None]:
    """Validate an explicit [{define, code}] mapping against the defines."""
    if mapping is None:
        return [], None
    if not isinstance(mapping, list):
        raise OperationError(
            f"mapping must be a list of {{define, code}} objects; got "
            f"{type(mapping).__name__}"
        )
    known = set(definition_names)
    seen_codes: set[str] = set()
    pairs: list[tuple[str, str]] = []
    for i, raw in enumerate(mapping):
        if not isinstance(raw, dict):
            raise OperationError(
                f"mapping[{i}] must be an object with 'define' and 'code'; got "
                f"{type(raw).__name__}"
            )
        define = raw.get("define")
        code = raw.get("code")
        if not isinstance(define, str) or not define:
            raise OperationError(f"mapping[{i}].define must be a non-empty string")
        if not isinstance(code, str) or not code:
            raise OperationError(f"mapping[{i}].code must be a non-empty string")
        if define not in known:
            return [], Diagnostics(
                code=DiagnosticCode.INPUT_ERROR,
                severity="error",
                message=f"unknown define {define!r} in measure mapping",
                data={"expected": "one of the library's defines", "found": define},
            )
        if code not in POPULATION_ORDER:
            return [], Diagnostics(
                code=DiagnosticCode.INPUT_ERROR,
                severity="error",
                message=f"unknown population code {code!r} in measure mapping",
                data={"expected": list(POPULATION_ORDER), "found": code},
            )
        if code in seen_codes:
            return [], Diagnostics(
                code=DiagnosticCode.INPUT_ERROR,
                severity="error",
                message=f"duplicate population code {code!r} in measure mapping",
                data={"found": code},
            )
        seen_codes.add(code)
        pairs.append((define, code))
    return pairs, None


def dependency_closure(
    libraries: list[LibraryText], main: LibraryText
) -> tuple[list[LibraryText], list[str]]:
    """Transitive include closure of ``main`` within ``libraries``.

    Returns (ordered_libraries, missing_names): ordered MAIN-FIRST
    (MADiE convention: Measure.library[0] is the primary), then each
    included library depth-first in include order. ``missing_names``
    lists include targets not present in the workspace (bundled
    libraries like FHIRHelpers resolve elsewhere and are NOT missing).
    """
    from fhir4ds.cql import parse_cql as engine_parse

    by_name = {lib.name: lib for lib in libraries}
    ordered: list[LibraryText] = []
    seen: set[str] = set()
    missing: list[str] = []

    def visit(lib: LibraryText) -> None:
        if lib.name in seen:
            return
        seen.add(lib.name)
        ordered.append(lib)
        try:
            ast = engine_parse(lib.text)
        except Exception:
            return
        for inc in getattr(ast, "includes", []) or []:
            target = getattr(inc, "path", None) or getattr(inc, "alias", None)
            if not target or target in seen:
                continue
            dep = by_name.get(target)
            if dep is None:
                if target not in missing:
                    missing.append(target)
                continue
            visit(dep)

    visit(main)
    return ordered, missing


def measure_from_definitions(
    libraries: list[LibraryText],
    main: LibraryText,
    *,
    mapping: list[dict[str, str]] | None = None,
    measure_name: str = "CleanroomMeasure",
    group_id: str = "group-1",
    library_urls: list[str] | None = None,
) -> MeasureResult:
    """Build a FHIR Measure resource from the main library's defines.

    ``mapping`` is an explicit ``[{"define": ..., "code": ...}]`` list —
    the capability never guesses define roles from names (the UI may
    OFFER a default suggestion, but the mapping itself is explicit).
    When ``mapping`` is None the result carries only the candidate
    define list (bootstrap mode).
    """
    from fhir4ds.cql import parse_cql as engine_parse

    try:
        ast = engine_parse(main.text)
        inline_others = [lib for lib in libraries if lib.name != main.name]
        resolver = LibraryResolver(inline=[main, *inline_others])
        from .translate import _resolve_all

        missing = _resolve_all(resolver, ast, main.name)
        if missing:
            return MeasureResult(ok=False, diagnostics=tuple(missing))  # type: ignore[arg-type]

        from fhir4ds.cql.parser.ast_nodes import Definition, FunctionDefinition

        definition_names = tuple(
            stmt.name
            for stmt in getattr(ast, "statements", [])
            if isinstance(stmt, (Definition, FunctionDefinition))
        )
        pairs, diag = _validate_mapping(mapping, definition_names)
        if diag is not None:
            return MeasureResult(ok=False, diagnostics=(diag,))

        populations: list[dict[str, Any]] = [
            {
                "code": {
                    "coding": [{"system": _POPULATION_SYSTEM, "code": code}]
                },
                "criteria": {
                    "language": _CQL_IDENTIFIER_LANGUAGE,
                    "expression": define,
                },
            }
            for define, code in pairs
        ]
        # Measure.library[]: primary first (canonical), then dependency
        # closure. Explicit library_urls wins; else mint stable urns from
        # the closure so exported Measures are self-describing.
        if library_urls is not None:
            measure_libraries: list[str] = list(library_urls)
        else:
            closure, _missing = dependency_closure(
                [main, *[l for l in libraries if l.name != main.name]], main
            )
            measure_libraries = [
                f"urn:cleanroom:lib:{lib.name}" for lib in closure
            ]
        measure: dict[str, Any] = {
            "resourceType": "Measure",
            "name": measure_name,
            "status": "draft",
            "library": measure_libraries,
            "scoring": {
                "coding": [
                    {
                        "system": "http://terminology.hl7.org/CodeSystem/measure-scoring",
                        "code": "proportion",
                    }
                ]
            },
            "group": [
                {
                    "id": group_id,
                    "extension": [
                        {"url": _POPULATION_BASIS_EXT, "valueCode": "boolean"}
                    ],
                    "population": populations,
                }
            ],
        }
        return MeasureResult(
            measure=measure,
            mapping=tuple({"define": d, "code": c} for d, c in pairs),
        )
    except Exception as exc:
        return MeasureResult(
            ok=False,
            diagnostics=(diagnostic_from_exception(exc, context="measure_from_definitions"),),
        )


def measure_population_map(measure: dict[str, Any]) -> tuple[list[tuple[str, str]], Diagnostics | None]:
    """Measure -> [(code, cql_expression)] via the DQM MeasureParser.

    The single authority for population-role semantics (INV-3). Returns
    (pairs, None) or ([], diagnostic) on an invalid/unusable Measure.
    """
    if not isinstance(measure, dict):
        return [], Diagnostics(
            code=DiagnosticCode.INPUT_ERROR,
            severity="error",
            message="measure must be a FHIR Measure resource (JSON object)",
            data={"found": type(measure).__name__},
        )
    if measure.get("resourceType") != "Measure":
        return [], Diagnostics(
            code=DiagnosticCode.INPUT_ERROR,
            severity="error",
            message="resourceType must be 'Measure'",
            data={"found": str(measure.get("resourceType"))},
        )
    try:
        from fhir4ds.dqm.parser import MeasureParser

        pop_map = MeasureParser().parse(measure)
    except Exception as exc:
        diag = diagnostic_from_exception(exc, context="measure_population_map")
        return [], Diagnostics(
            code=DiagnosticCode.INPUT_ERROR,
            severity="error",
            message=f"Measure failed to parse: {exc}",
        )
    groups = list(getattr(pop_map, "groups", ()) or ())
    if not groups:
        return [], Diagnostics(
            code=DiagnosticCode.INPUT_ERROR,
            severity="error",
            message="Measure has no usable population groups",
        )
    pairs: list[tuple[str, str]] = []
    for g in groups:
        for entry in getattr(g, "populations", ()) or ():
            pairs.append((entry.population_code, entry.cql_expression))
    if not pairs:
        return [], Diagnostics(
            code=DiagnosticCode.INPUT_ERROR,
            severity="error",
            message="Measure groups contain no populations with CQL criteria",
        )
    return pairs, None


def output_columns_from_measure(measure: dict[str, Any]) -> dict[str, str]:
    """Translate-mode output_columns from a Measure.

    ``{initial_population: "Initial Population", ...}`` — the DQM
    ``_col_name`` convention feeding translate_cql output_columns.
    Raises OperationError with a typed diagnostic message when the
    Measure is unusable (callers convert to envelopes).
    """
    pairs, diag = measure_population_map(measure)
    if diag is not None:
        raise OperationError(diag.message)
    return {_population_column(code): define for code, define in pairs}


def measure_report_from_rows(
    measure: dict[str, Any],
    rows: list[dict[str, Any]],
    columns: list[str] | tuple[str, ...],
    *,
    period_start: str | None = None,
    period_end: str | None = None,
    library_url: str | None = None,
) -> MeasureReportResult:
    """Per-patient individual MeasureReports from evaluation rows.

    Boolean membership becomes population ``count`` 0/1 (S-1 dual
    representation; reports are the interop form, the grid stays
    boolean). ``group.id`` is preserved verbatim (SO-2) so multi-group
    Measures round-trip even when the UI edits one group.
    """
    pairs, diag = measure_population_map(measure)
    if diag is not None:
        return MeasureReportResult(ok=False, diagnostics=(diag,))
    col_to_code = {_population_column(code): code for code, _ in pairs}

    reports: list[dict[str, Any]] = []
    known_cols = set(columns) if columns is not None else set()
    for row in rows:
        pid = row.get("patient_id")
        if pid is None:
            continue
        group_counts: dict[str, int] = {}
        for col, value in row.items():
            code = col_to_code.get(col)
            if code is None:
                continue
            if known_cols and col not in known_cols:
                continue
            group_counts[code] = 1 if value is True else 0
        report: dict[str, Any] = {
            "resourceType": "MeasureReport",
            "status": "complete",
            "type": "individual",
            "measure": library_url or f"urn:cleanroom:measure",
            "subject": {"reference": f"Patient/{pid}"},
            "group": [],
        }
        if period_start or period_end:
            period: dict[str, str] = {}
            if period_start:
                period["start"] = period_start
            if period_end:
                period["end"] = period_end
            report["period"] = period
        # Emit groups in the Measure's declared order; only codes the
        # Measure declares (parser-filtered) appear.
        for g in _ordered_groups(measure, pairs):
            code = g["_code"]
            entry: dict[str, Any] = {
                "id": g.get("id"),
                "population": [
                    {
                        "code": {
                            "coding": [
                                {"system": _POPULATION_SYSTEM, "code": code}
                            ]
                        },
                        "count": group_counts.get(code, 0),
                    }
                ],
            }
            report["group"].append(entry)
        reports.append(report)
    return MeasureReportResult(reports=tuple(reports))


def _ordered_groups(measure: dict[str, Any], pairs: list[tuple[str, str]]) -> list[dict[str, Any]]:
    """Group skeletons in declared order with their codes resolved."""
    out: list[dict[str, Any]] = []
    for g in measure.get("group") or []:
        if not isinstance(g, dict):
            continue
        for pop in g.get("population") or []:
            if not isinstance(pop, dict):
                continue
            coding = ((pop.get("code") or {}).get("coding") or [{}])[0]
            code = coding.get("code")
            if isinstance(code, str) and any(code == c for c, _ in pairs):
                out.append({"id": g.get("id"), "_code": code})
    return out


def rows_from_measure_reports(
    reports: Any,
    *,
    population_codes: list[str] | tuple[str, ...] | None = None,
) -> MeasureRowsResult:
    """MeasureReports (single, list, or Bundle) -> normalized rows.

    Inverse of measure_report_from_rows: one row per subject with
    ``patient_id`` + ``<_population_column(code)>`` boolean columns.
    Unknown population codes in the reports are skipped with an info
    diagnostic (best-effort MADiE interop); malformed shapes raise
    OperationError -> typed envelope.
    """
    if isinstance(reports, dict) and reports.get("resourceType") == "Bundle":
        entries = reports.get("entry") or []
        report_list = [
            e.get("resource") for e in entries
            if isinstance(e, dict)
            and isinstance(e.get("resource"), dict)
            and e["resource"].get("resourceType") == "MeasureReport"
        ]
    elif isinstance(reports, dict) and reports.get("resourceType") == "MeasureReport":
        report_list = [reports]
    elif isinstance(reports, list):
        report_list = []
        for item in reports:
            if isinstance(item, dict) and item.get("resourceType") == "MeasureReport":
                report_list.append(item)
    else:
        raise OperationError(
            "reports must be a MeasureReport, a list of MeasureReports, "
            f"or a Bundle of them; got {type(reports).__name__}"
        )

    codes: list[str] = (
        list(population_codes)
        if population_codes is not None
        else list(POPULATION_ORDER)
    )
    code_set = set(codes)
    rows_map: dict[str, dict[str, Any]] = {}
    skipped_codes: set[str] = set()
    for rep in report_list:
        subject_ref = ((rep.get("subject") or {}).get("reference")) or ""
        pid = subject_ref.split("/")[-1] if subject_ref else None
        if not pid:
            raise OperationError(
                "MeasureReport is missing subject.reference (Patient/<id>)"
            )
        row = rows_map.setdefault(
            pid, {"patient_id": pid, **{_population_column(c): False for c in codes}}
        )
        for g in rep.get("group") or []:
            for pop in g.get("population") or []:
                coding = ((pop.get("code") or {}).get("coding") or [{}])[0]
                code = coding.get("code")
                if not isinstance(code, str):
                    continue
                if code not in code_set:
                    skipped_codes.add(code)
                    continue
                count = pop.get("count")
                row[_population_column(code)] = bool(count)

    diags: tuple[Diagnostics, ...] = (
        (
            Diagnostics(
                code=DiagnosticCode.INPUT_ERROR,
                severity="info",
                message="skipped unknown population codes in reports",
                data={"found": sorted(skipped_codes)},
            ),
        )
        if skipped_codes
        else ()
    )
    ordered_cols = ["patient_id"] + [_population_column(c) for c in codes]
    ordered_rows = [rows_map[k] for k in sorted(rows_map)]
    return MeasureRowsResult(
        rows=tuple(ordered_rows),
        columns=tuple(ordered_cols),
        diagnostics=diags,
    )


def flatten_view(
    view_definition: dict[str, Any],
    resources: list[dict[str, Any]],
    conn: Any,
) -> FlattenViewResult:
    """Run a ViewDefinition over staged resources on the caller's conn.

    Exact-SQL doctrine: the viewdef generator's SQL runs VERBATIM (no
    rewriting). Resources stage into an ISOLATED per-call temp table
    (SO-3) — never the live ``resources`` table — and the table drops
    after the query. The VD's ``resource`` binding names the staged
    resource type (e.g. ``MeasureReport``).
    """
    try:
        from fhir4ds.viewdef.parser import parse_view_definition
        from fhir4ds.viewdef.generator import SQLGenerator

        vd = parse_view_definition(view_definition)
        generator = SQLGenerator(source_table="__cleanroom_flatten_src")
        sql = generator.generate(vd)

        import json as _json

        # Isolated staging (SO-3): temp table exists only for this call,
        # dropped in the finally block; never touches the live
        # ``resources`` table. Identifiers are internal constants.
        conn.execute(
            "CREATE OR REPLACE TEMP TABLE __cleanroom_flatten_src "
            "(resource JSON)"
        )
        conn.executemany(
            "INSERT INTO __cleanroom_flatten_src VALUES (?)",
            [(_json.dumps(r),) for r in resources],
        )
        try:
            rel = conn.execute(sql)
            cols = [d[0] for d in rel.description]
            rows_raw = rel.fetchall()
            rows = [dict(zip(cols, r)) for r in rows_raw]
            return FlattenViewResult(
                sql=sql,
                columns=tuple(cols),
                rows=tuple(rows),
            )
        finally:
            conn.execute("DROP TABLE IF EXISTS __cleanroom_flatten_src")
    except OperationError:
        raise
    except Exception as exc:
        return FlattenViewResult(
            ok=False,
            diagnostics=(diagnostic_from_exception(exc, context="flatten_view"),),
        )


DEFAULT_MEASURE_REPORT_VIEW: dict[str, Any] = {
    "resource": "MeasureReport",
    "name": "MeasureReportFlat",
    "select": [
        {
            "column": [
                # Focus-relative after forEach: group is the focus.
                {"name": "patient_id", "path": "%resource.subject.reference", "type": "string"},
                {"name": "group_id", "path": "id", "type": "string"},
                {
                    "name": "population_code",
                    "path": "population.code.coding.code",
                    "type": "string",
                },
                {"name": "population_count", "path": "population.count", "type": "integer"},
            ],
            "forEach": "group",
        }
    ],
}
