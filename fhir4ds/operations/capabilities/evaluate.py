"""evaluate_library / run_tests / explain_patient capabilities.

Evaluation operations take a caller-supplied DuckDB connection plus an
optional DatasetSpec (None = use the connection's loaded state) and
orchestrate the existing engine APIs (evaluate_measure) — no engine
code paths are added or changed.
"""

from __future__ import annotations

import json
import time
from collections import OrderedDict
from dataclasses import dataclass
from typing import Any

from ..envelopes import DatasetSpec, LibraryText, TestsInput, _EnvelopeFields
from ..errors import diagnostic_from_exception, input_error, not_found
from .dataset_ops import load_dataset as _load_dataset


@dataclass(frozen=True)
class EvaluateResult(_EnvelopeFields):
    ok: bool = True
    passed: object = None
    diagnostics: tuple = ()
    patient_count: int = 0
    columns: tuple[str, ...] = ()
    rows: list[dict[str, Any]] = None  # type: ignore[assignment]
    column_types: dict[str, str] = None  # type: ignore[assignment]
    sql: str | None = None
    timing_ms: dict[str, float] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.rows is None:
            object.__setattr__(self, "rows", [])
        if self.column_types is None:
            object.__setattr__(self, "column_types", {})
        if self.timing_ms is None:
            object.__setattr__(self, "timing_ms", {})

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {"schema": self.schema, "ok": self.ok}
        if self.passed is not None:
            out["passed"] = self.passed
        if self.diagnostics:
            out["diagnostics"] = [d.to_dict() for d in self.diagnostics]
        out.update(
            {
                "patient_count": self.patient_count,
                "columns": list(self.columns),
                "rows": list(self.rows),
                "column_types": dict(self.column_types),
                "timing_ms": {k: round(v, 3) for k, v in self.timing_ms.items()},
            }
        )
        if self.sql is not None:
            out["sql"] = self.sql
        return out


@dataclass(frozen=True)
class VerifyEnvelope(_EnvelopeFields):
    ok: bool = True
    passed: object = None
    diagnostics: tuple = ()
    library: str = ""
    patients_evaluated: int = 0
    summary: dict[str, int] = None  # type: ignore[assignment]
    tests: dict[str, Any] = None  # type: ignore[assignment]
    timing_ms: dict[str, float] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.summary is None:
            object.__setattr__(self, "summary", {})
        if self.tests is None:
            object.__setattr__(self, "tests", {})
        if self.timing_ms is None:
            object.__setattr__(self, "timing_ms", {})

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "schema": self.schema,
            "ok": self.ok,
            "passed": self.passed,
        }
        if self.diagnostics:
            out["diagnostics"] = [d.to_dict() for d in self.diagnostics]
        out.update(
            {
                "library": self.library,
                "patients_evaluated": self.patients_evaluated,
                "summary": dict(self.summary),
                "tests": dict(self.tests),
                "timing_ms": {k: round(v, 3) for k, v in self.timing_ms.items()},
            }
        )
        return out


@dataclass(frozen=True)
class EvidenceResult(_EnvelopeFields):
    ok: bool = True
    passed: object = None
    diagnostics: tuple = ()
    patient_id: str = ""
    populations: dict[str, bool] = None  # type: ignore[assignment]
    definitions: list[dict[str, Any]] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.populations is None:
            object.__setattr__(self, "populations", {})
        if self.definitions is None:
            object.__setattr__(self, "definitions", [])

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {"schema": self.schema, "ok": self.ok}
        if self.passed is not None:
            out["passed"] = self.passed
        if self.diagnostics:
            out["diagnostics"] = [d.to_dict() for d in self.diagnostics]
        out.update(
            {
                "patient_id": self.patient_id,
                "populations": dict(self.populations),
                "definitions": list(self.definitions),
            }
        )
        return out


# ---------------------------------------------------------------------------
# helpers


def _write_main_library(main: LibraryText, libraries: list[LibraryText], tmp_dir) -> tuple[str, list[str]]:
    """Materialize inline libraries to files for evaluate_measure (path-based).

    Returns (main_path, include_dirs). The include dir ALWAYS exists so
    evaluate_measure wires a library_loader; every DIRECT include of the
    main library is satisfied — inline copies first, then the bundled
    tier (any bundled name, via the dynamic index) — and transitive
    bundled includes are materialized too.
    """
    import re as _re

    from ..library_sources import _bundled_index, _bundled_text

    include_dir = tmp_dir / "includes"
    include_dir.mkdir(parents=True, exist_ok=True)
    inline_names: set[str] = set()
    for lib in libraries:
        if lib.name == main.name:
            continue
        (include_dir / f"{lib.name}.cql").write_text(lib.text, encoding="utf-8")
        inline_names.add(lib.name)

    # Direct includes of main (parse-light regex: include <Name> version '..')
    direct = set(_re.findall(r"^\s*include\s+([A-Za-z][A-Za-z0-9_]*)", main.text, _re.MULTILINE))
    missing = sorted(
        name
        for name in direct
        if not (include_dir / f"{name}.cql").exists()
        and _bundled_text(name) is None
    )
    # Materialize every direct include not already inline from the bundled tier
    for name in direct:
        target = include_dir / f"{name}.cql"
        if target.exists():
            continue
        text = _bundled_text(name)
        if text is not None:
            target.write_text(text, encoding="utf-8")

    # Transitive includes of materialized/bundled libraries, one hop at a
    # time until closure (bounded by the bundled catalog size).
    index = _bundled_index()
    resolved = {p.stem for p in include_dir.glob("*.cql")}
    frontier = list(resolved)
    seen = set(frontier)
    while frontier:
        nxt: list[str] = []
        for stem in frontier:
            path = include_dir / f"{stem}.cql"
            text = path.read_text(encoding="utf-8")
            for dep in _re.findall(r"^\s*include\s+([A-Za-z][A-Za-z0-9_]*)", text, _re.MULTILINE):
                if dep in seen:
                    continue
                seen.add(dep)
                dep_target = include_dir / f"{dep}.cql"
                if not dep_target.exists():
                    dep_text = _bundled_text(dep)
                    if dep_text is None:
                        continue  # unresolved transitive — engine reports it
                    dep_target.write_text(dep_text, encoding="utf-8")
                nxt.append(dep_target.stem)
        frontier = nxt
        if len(seen) >= len(index) + len(libraries) + 1:
            break

    if missing:
        raise FileNotFoundError(
            f"Could not resolve included libraries: {', '.join(missing)}"
        )
    main_path = tmp_dir / f"{main.name}.cql"
    main_path.write_text(main.text, encoding="utf-8")
    return str(main_path), [str(include_dir)] if include_dir else []


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, dict):
        return {k: _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    return json.loads(json.dumps(value, default=str))


def _rows_from_relation(relation: Any) -> tuple[list[str], list[dict[str, Any]]]:
    """Normalize the engine's DataFrame result into JSON-safe row dicts."""
    if hasattr(relation, "columns") and hasattr(relation, "itertuples"):
        # pandas DataFrame from evaluate_measure
        columns = [str(c) for c in relation.columns.tolist()]
        rows = [
            {col: _json_safe(val) for col, val in zip(columns, record, strict=False)}
            for record in relation.itertuples(index=False, name=None)
        ]
        return columns, rows
    columns = [d[0] for d in relation.description]
    raw_rows = relation.fetchall()
    rows = [dict(zip(columns, [_json_safe(v) for v in row], strict=False)) for row in raw_rows]
    return columns, rows


def _column_types(library: Any, columns: tuple[str, ...], output_columns: dict[str, str] | None) -> dict[str, str]:
    """CQL type per output column from definition metadata (0.0.16 type map).

    ``library`` may be a translator-like object exposing
    ``_definition_meta``/``context.definition_meta``, or a plain dict
    (name -> meta view with cql_type_ref), as produced by
    ``_definition_meta_map``.
    """
    meta_by_name: dict[str, Any] = {}
    if isinstance(library, dict):
        meta_by_name = library
    else:
        translator_meta = getattr(library, "_definition_meta", None)
        if translator_meta is None:
            translator_meta = getattr(
                getattr(library, "context", None), "definition_meta", None
            )
        if translator_meta:
            for name, meta in translator_meta.items():
                meta_by_name[name] = meta
    types: dict[str, str] = {}
    for col in columns:
        if col == "patient_id":
            continue
        define = (output_columns or {}).get(col, col)
        meta = meta_by_name.get(define)
        if meta is None:
            types[col] = "Any"
            continue
        if isinstance(meta, dict):
            types[col] = str(meta.get("cql_type_ref") or "Any")
            continue
        ref = getattr(meta, "cql_type_ref", None)
        if ref is not None and str(ref) not in ("Any", ""):
            types[col] = str(ref)
        elif getattr(meta, "cql_type", None):
            types[col] = str(meta.cql_type)
        else:
            types[col] = "Any"
    return types


_DEFINITION_META_CACHE: OrderedDict[tuple, dict] = OrderedDict()
_DEFINITION_META_CACHE_MAX = 32


def _definition_meta_map(
    libraries: list[LibraryText], main: LibraryText
) -> dict[str, Any]:
    """Definition metadata (name -> meta view) via the same resolution chain.

    Adapter-only metadata recovery: evaluate_measure does not expose its
    translator, so we re-run the stateless translation to harvest
    definition meta (cql_type_ref). The map feeds _column_types; misses
    degrade to "Any" exactly as before. Metadata is best-effort typing
    on top of a succeeded evaluation — never an evaluation failure.

    REV-C1-002: the re-translation is cached (LRU, 32 entries) keyed on
    the library texts — repeated evaluate_library/run_tests calls on the
    same library skip the duplicate parse+translate round.
    """
    key = (
        tuple((lib.name, lib.text) for lib in libraries),
        (main.name, main.text),
    )
    cached = _DEFINITION_META_CACHE.get(key)
    if cached is not None:
        _DEFINITION_META_CACHE.move_to_end(key)
        return cached
    try:
        from fhir4ds.cql import parse_cql as engine_parse
        from fhir4ds.cql.translator import CQLToSQLTranslator

        from ..library_sources import LibraryResolver

        main_ast = engine_parse(main.text)
        inline_others = [lib for lib in libraries if lib.name != main.name]
        resolver = LibraryResolver(inline=[main, *inline_others])
        translator = CQLToSQLTranslator()
        translator.set_library_loader(resolver.resolve)
        translator.translate_library_to_sql(main_ast)
        from .translate import _type_ref_name

        meta: dict[str, Any] = {}
        for name, entry in (translator.context.definition_meta or {}).items():
            ref = getattr(entry, "cql_type_ref", None)
            rendered = _type_ref_name(ref) if ref is not None else None
            if rendered is None or rendered in ("Any", ""):
                rendered = str(getattr(entry, "cql_type", None) or "Any")
            meta[name] = {"cql_type_ref": rendered}
    except Exception:
        meta = {}
    _DEFINITION_META_CACHE[key] = meta
    if len(_DEFINITION_META_CACHE) > _DEFINITION_META_CACHE_MAX:
        _DEFINITION_META_CACHE.popitem(last=False)
    return meta


def _evaluate(
    libraries: list[LibraryText],
    main: LibraryText,
    dataset: DatasetSpec | None,
    conn: Any,
    *,
    parameters: dict[str, Any] | None = None,
    output_columns: dict[str, str] | None = None,
    audit_mode: str = "population",
    patient_ids: list[str] | None = None,
    want_sql: bool = False,
):
    """Shared evaluation core. Returns (result_kwargs, diagnostics).

    BF-003: evaluate now calls translate_cql (population/full shape,
    same LibraryResolver include chain as the SQL viewer) and executes
    the SQL directly on the connection — the temp-file materialization
    + evaluate_measure include_paths dance is GONE. One translation
    path, one include-resolution mechanism.
    """
    from .translate import translate_cql

    timing: dict[str, float] = {}
    diag: list[Any] = []
    t0 = time.perf_counter()

    tr = translate_cql(
        libraries,
        main,
        audit_mode=audit_mode,
        patient_ids=patient_ids,
        output_columns=output_columns,
        parameters=parameters,
    )
    if not tr.ok:
        return None, list(tr.diagnostics)
    t_load = time.perf_counter()
    timing["load"] = (t_load - t0) * 1000

    if dataset is not None and not dataset.is_empty:
        ds_result = _load_dataset(dataset, conn)
        if not ds_result.ok:
            return None, list(ds_result.diagnostics)

    try:
        relation = conn.execute(tr.sql)
    except Exception as exc:
        return None, [diagnostic_from_exception(exc, library=main.name, context="evaluate")]
    timing["evaluate"] = (time.perf_counter() - t_load) * 1000

    columns, rows = _rows_from_relation(relation)
    kwargs: dict[str, Any] = {
        "patient_count": len(rows),
        "columns": tuple(columns),
        "rows": rows,
        "timing_ms": timing,
    }
    if want_sql:
        kwargs["sql"] = tr.sql
    return (kwargs, relation), diag


def _summary_from_rows(rows: list[dict[str, Any]], columns: tuple[str, ...]) -> dict[str, int]:
    summary: dict[str, int] = {}
    for col in columns:
        if col == "patient_id":
            continue
        summary[col] = sum(1 for r in rows if r.get(col) is True)
    return summary


# ---------------------------------------------------------------------------
# public operations


def evaluate_library(
    libraries: list[LibraryText],
    main: LibraryText,
    dataset: DatasetSpec | None,
    conn: Any,
    *,
    parameters: dict[str, Any] | None = None,
    output_columns: dict[str, str] | None = None,
    emit_sql: bool = False,
) -> EvaluateResult:
    """Evaluate the main library against the dataset; one row per patient."""
    outcome = _evaluate(
        libraries, main, dataset, conn,
        parameters=parameters, output_columns=output_columns,
        audit_mode="population",
        want_sql=emit_sql,
    )
    payload, diag = outcome
    if payload is None:
        return EvaluateResult(ok=False, diagnostics=tuple(diag))
    kwargs, relation = payload
    return EvaluateResult(
        column_types=_column_types(
            _definition_meta_map(libraries, main),
            kwargs["columns"],
            output_columns,
        ),
        **kwargs,
    )


def run_tests(
    libraries: list[LibraryText],
    main: LibraryText,
    dataset: DatasetSpec | None,
    cases: TestsInput,
    conn: Any,
    *,
    parameters: dict[str, Any] | None = None,
    output_columns: dict[str, str] | None = None,
) -> VerifyEnvelope:
    """Evaluate once, then check each case against the patient's row."""
    outcome = _evaluate(
        libraries, main, dataset, conn,
        parameters=parameters, output_columns=output_columns,
        audit_mode="population",
    )
    payload, diag = outcome
    if payload is None:
        return VerifyEnvelope(
            ok=False,
            library=main.name,
            diagnostics=tuple(diag),
        )
    kwargs, _ = payload
    rows = kwargs["rows"]
    columns = kwargs["columns"]
    by_patient = {r.get("patient_id"): r for r in rows}
    failures: list[dict[str, Any]] = []
    passed_count = 0
    for case in cases.cases:
        row = by_patient.get(case.patient)
        if row is None:
            failures.append(
                {
                    "patient": case.patient,
                    "target": case.target,
                    "expected": case.expect,
                    "actual": None,
                    "reason": "unknown patient: not present in evaluation results",
                }
            )
            continue
        actual = _case_value(row, case, output_columns)
        if actual is None:
            failures.append(
                {
                    "patient": case.patient,
                    "target": case.target,
                    "expected": case.expect,
                    "actual": None,
                    "reason": f"unknown population/define column: {case.target!r}",
                }
            )
            continue
        if bool(actual) != case.expect:
            failures.append(
                {
                    "patient": case.patient,
                    "target": case.target,
                    "expected": case.expect,
                    "actual": bool(actual),
                    "reason": None,
                }
            )
        else:
            passed_count += 1
    total = len(cases.cases)
    tests = {
        "total": total,
        "passed": passed_count,
        "failed": len(failures),
        "failures": failures,
    }
    return VerifyEnvelope(
        ok=True,
        passed=failures == [],
        library=main.name,
        patients_evaluated=kwargs["patient_count"],
        summary=_summary_from_rows(rows, columns),
        tests=tests,
        timing_ms=kwargs["timing_ms"],
    )


def _case_value(
    row: dict[str, Any], case: Any, output_columns: dict[str, str] | None
) -> Any:
    if case.population is not None:
        if output_columns and case.population in output_columns:
            return row.get(case.population)
        # population name may be a define name used directly as a column
        if case.population in row:
            return row.get(case.population)
        # resolve define -> default column name
        for col, define in (output_columns or {}).items():
            if define == case.population:
                return row.get(col)
        return None
    if case.define is not None:
        if case.define in row:
            return row.get(case.define)
        for col, define in (output_columns or {}).items():
            if define == case.define:
                return row.get(col)
        return None
    return None


def explain_patient(
    libraries: list[LibraryText],
    main: LibraryText,
    dataset: DatasetSpec | None,
    patient_id: str,
    conn: Any,
    *,
    parameters: dict[str, Any] | None = None,
    output_columns: dict[str, str] | None = None,
) -> EvidenceResult:
    """Audit-evidence drill-in for one patient (patient_ids pushdown)."""
    if not isinstance(patient_id, str) or not patient_id:
        return EvidenceResult(
            ok=False,
            diagnostics=(input_error("patient_id must be a non-empty string"),),
        )
    outcome = _evaluate(
        libraries, main, dataset, conn,
        parameters=parameters, output_columns=output_columns,
        audit_mode="full", patient_ids=[patient_id],
    )
    payload, diag = outcome
    if payload is None:
        return EvidenceResult(ok=False, diagnostics=tuple(diag))
    kwargs, relation = payload
    rows = kwargs["rows"]
    if not rows:
        return EvidenceResult(
            ok=False,
            patient_id=patient_id,
            diagnostics=(
                not_found(
                    f"patient {patient_id!r} not present in evaluation results",
                ),
            ),
        )
    row = rows[0]
    populations: dict[str, bool] = {}
    evidence_by_col: dict[str, Any] = {}
    for col in kwargs["columns"]:
        if col == "patient_id":
            continue
        value = row.get(col)
        if isinstance(value, bool):
            populations[col] = value
        elif isinstance(value, dict) and "result" in value:
            # audit_mode="full" wraps population values: {result, evidence}
            populations[col] = bool(value.get("result"))
            evidence_by_col[col] = value.get("evidence", [])
    definitions = [
        {"column": col, "result": populations.get(col), "evidence": ev}
        for col, ev in evidence_by_col.items()
    ]
    return EvidenceResult(
        patient_id=patient_id,
        populations=populations,
        definitions=definitions,
    )


def _audit_definitions(relation: Any) -> list[dict[str, Any]]:
    """Extract per-definition audit evidence when present on the relation."""
    candidates = ("audit", "audit_evidence", "evidence", "_audit")
    for attr in candidates:
        value = getattr(relation, attr, None)
        if value:
            return _json_safe(value) if not isinstance(value, list) else value
    return []
