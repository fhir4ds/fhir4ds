"""translate_cql capability: emit generated SQL (stateless, no conn)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..envelopes import Diagnostics, LibraryText, _EnvelopeFields
from ..errors import OperationError, diagnostic_from_exception
from ..library_sources import LibraryResolver


@dataclass(frozen=True)
class TranslateResult(_EnvelopeFields):
    ok: bool = True
    passed: object = None
    diagnostics: tuple = ()
    sql: str = ""
    column_types: dict[str, str] = field(default_factory=dict)
    definitions: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.column_types is None:
            object.__setattr__(self, "column_types", {})

    def to_dict(self) -> dict[str, object]:
        out: dict[str, object] = {"schema": self.schema, "ok": self.ok}
        if self.passed is not None:
            out["passed"] = self.passed
        if self.diagnostics:
            out["diagnostics"] = [d.to_dict() for d in self.diagnostics]
        out["sql"] = self.sql
        out["column_types"] = dict(self.column_types)
        out["definitions"] = list(self.definitions)
        return out


def _type_ref_name(ref: Any) -> str | None:
    """Render a CQLTypeRef as its CQL type spelling (name + args)."""
    name = getattr(ref, "name", None)
    if not name:
        text = str(ref).strip()
        return text or None
    args = getattr(ref, "args", None) or ()
    if args:
        rendered = ", ".join(_type_ref_name(a) or "Any" for a in args)
        return f"{name}<{rendered}>"
    return str(name)


def _definition_column_types(translator: Any) -> tuple[dict[str, str], tuple[str, ...]]:
    """CQL type per define from translator definition metadata (cql_type_ref).

    Single metadata source for executor column typing: the same map the
    0.0.16 type-map builder attaches post-lowering. Falls back to
    ``cql_type`` when ``cql_type_ref`` is absent/Any (legacy shapes).
    """
    types: dict[str, str] = {}
    names: list[str] = []
    meta = getattr(getattr(translator, "context", None), "definition_meta", None) or {}
    for name, entry in meta.items():
        names.append(name)
        ref = getattr(entry, "cql_type_ref", None)
        rendered = _type_ref_name(ref) if ref is not None else None
        if rendered is not None and rendered not in ("Any", ""):
            types[name] = rendered
        elif getattr(entry, "cql_type", None):
            types[name] = str(entry.cql_type)
        else:
            types[name] = "Any"
    return types, tuple(names)


def _resolve_all(resolver: LibraryResolver, library, main_name: str):
    """Walk the include graph, seeding the resolver cache; returns diagnostics."""
    diags: list[Diagnostics] = []
    seen = set()
    stack = [(library, main_name)]
    while stack:
        lib, name = stack.pop()
        if name in seen:
            continue
        seen.add(name)
        for inc in getattr(lib, "includes", []) or []:
            alias = getattr(inc, "alias", None) or getattr(inc, "path", None)
            if not alias or alias in seen:
                continue
            path = getattr(inc, "path", None) or alias
            resolved = resolver.resolve(path)
            if resolved is None:
                diags.append(resolver.unresolved_diagnostic(alias, path=path))
                continue
            stack.append((resolved, alias))
    return diags


def translate_cql(
    libraries: list[LibraryText],
    main: LibraryText,
    *,
    audit_mode: str = "none",
    patient_ids: list[str] | None = None,
    output_columns: dict[str, str] | None = None,
    parameters: dict[str, Any] | None = None,
) -> TranslateResult:
    """Translate the main library (includes via the §3.3.1 chain) to SQL.

    Engine seam: CQLToSQLTranslator with a library_loader wired to the
    resolution chain (fhir4ds.cql.translator.CQLToSQLTranslator).

    Modes:
    - ``audit_mode="none"`` (default): one-row CTE SQL via
      ``translate_library_to_sql`` — the shape the SQL viewer shows.
    - ``audit_mode="population"``: one-row-per-patient population SQL
      WITHOUT audit structs (plain boolean columns) via
      ``translate_library_to_population_sql`` — the shape
      evaluate_library/run_tests execute.
    - ``audit_mode="full"`` (with optional ``patient_ids`` pushdown):
      population SQL WITH audit structs — the shape explain_patient
      executes; the executor unwraps ``{result, evidence}`` columns per
      evaluate.py semantics.

    ``column_types`` carries the CQL type per define (cql_type_ref
    metadata) so executors can type result columns without a Python
    library object.
    """
    from fhir4ds.cql.translator import CQLToSQLTranslator

    try:
        from fhir4ds.cql import parse_cql as engine_parse

        main_ast = engine_parse(main.text)
        inline_others = [lib for lib in libraries if lib.name != main.name]
        resolver = LibraryResolver(inline=[main, *inline_others])
        missing = _resolve_all(resolver, main_ast, main.name)
        if missing:
            return TranslateResult(ok=False, diagnostics=tuple(missing))
        if audit_mode not in ("none", "population", "full"):
            raise OperationError(
                f"audit_mode must be one of 'none', 'population', 'full'; "
                f"got {audit_mode!r}"
            )
        translator = CQLToSQLTranslator(
            audit_mode=audit_mode == "full",
        )
        translator.set_library_loader(resolver.resolve)
        if audit_mode in ("population", "full"):
            sql = translator.translate_library_to_population_sql(
                main_ast,
                output_columns=output_columns,
                patient_ids=patient_ids,
                parameters=parameters,
            )
        else:
            if patient_ids:
                # patient pushdown only applies to the population shapes;
                # reject the impossible combination explicitly.
                raise OperationError(
                    "patient_ids requires audit_mode='population' or 'full' "
                    "(population SQL shape)"
                )
            if output_columns:
                # column aliasing is a population-shape feature; reject
                # the impossible combination explicitly.
                raise OperationError(
                    "output_columns requires audit_mode='population' or 'full' "
                    "(population SQL shape)"
                )
            sql = translator.translate_library_to_sql(main_ast)
        column_types, definitions = _definition_column_types(translator)
    except Exception as exc:
        return TranslateResult(
            ok=False,
            diagnostics=(
                diagnostic_from_exception(exc, library=main.name, context="translate"),
            ),
        )
    return TranslateResult(
        sql=sql,
        column_types=column_types,
        definitions=definitions,
    )
