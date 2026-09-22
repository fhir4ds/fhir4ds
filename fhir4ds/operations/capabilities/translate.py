"""translate_cql capability: emit generated SQL (stateless, no conn)."""

from __future__ import annotations

from dataclasses import dataclass

from ..envelopes import Diagnostics, LibraryText, _EnvelopeFields
from ..errors import diagnostic_from_exception
from ..library_sources import LibraryResolver


@dataclass(frozen=True)
class TranslateResult(_EnvelopeFields):
    ok: bool = True
    passed: object = None
    diagnostics: tuple = ()
    sql: str = ""

    def to_dict(self) -> dict[str, object]:
        out: dict[str, object] = {"schema": self.schema, "ok": self.ok}
        if self.passed is not None:
            out["passed"] = self.passed
        if self.diagnostics:
            out["diagnostics"] = [d.to_dict() for d in self.diagnostics]
        out["sql"] = self.sql
        return out


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
) -> TranslateResult:
    """Translate the main library (includes via the §3.3.1 chain) to SQL.

    Engine seam: CQLToSQLTranslator with a library_loader wired to the
    resolution chain (fhir4ds.cql.translator.CQLToSQLTranslator).
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
        translator = CQLToSQLTranslator()
        translator.set_library_loader(resolver.resolve)
        sql = translator.translate_library_to_sql(main_ast)
    except Exception as exc:
        return TranslateResult(
            ok=False,
            diagnostics=(
                diagnostic_from_exception(exc, library=main.name, context="translate"),
            ),
        )
    return TranslateResult(sql=sql)
