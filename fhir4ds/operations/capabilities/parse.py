"""parse_cql capability: parse/validate + declaration metadata."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..envelopes import _EnvelopeFields
from ..errors import diagnostic_from_exception


@dataclass(frozen=True)
class ParseResult(_EnvelopeFields):
    ok: bool = True
    passed: object = None
    diagnostics: tuple = ()
    library_name: str = ""
    definition_names: tuple[str, ...] = ()
    parameter_names: tuple[str, ...] = ()
    declarations: tuple[dict[str, Any], ...] = ()

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "schema": self.schema,
            "ok": self.ok,
        }
        if self.passed is not None:
            out["passed"] = self.passed
        if self.diagnostics:
            out["diagnostics"] = [d.to_dict() for d in self.diagnostics]
        out.update(
            {
                "library_name": self.library_name,
                "definition_names": list(self.definition_names),
                "parameter_names": list(self.parameter_names),
                "declarations": list(self.declarations),
            }
        )
        return out


def _declarations(library: Any) -> tuple[dict[str, Any], ...]:
    out: list[dict[str, Any]] = []
    for stmt in getattr(library, "parameters", []) or []:
        out.append(
            {
                "kind": "parameter",
                "name": stmt.name,
                "type": getattr(getattr(stmt, "parameter_type", None), "name", None)
                or str(getattr(stmt, "parameter_type", "") or ""),
                "has_default": getattr(stmt, "default", None) is not None,
            }
        )
    for stmt in getattr(library, "includes", []) or []:
        out.append(
            {
                "kind": "include",
                "library": getattr(stmt, "path", None),
                "alias": getattr(stmt, "alias", None),
                "version": getattr(stmt, "version", None),
            }
        )
    for attr, kind in (
        ("codes", "code"),
        ("codesystems", "codesystem"),
        ("concepts", "concept"),
        ("valuesets", "valueset"),
    ):
        for stmt in getattr(library, attr, []) or []:
            name = getattr(stmt, "name", None)
            if name:
                out.append({"kind": kind, "name": name})
    return tuple(out)


def parse_cql(cql_text: str) -> ParseResult:
    """Parse CQL text into a declaration-metadata envelope.

    Engine seam: fhir4ds.cql.parse_cql (typed ParseError/LexerError ->
    PARSE_ERROR diagnostics with structured location).
    """
    try:
        from fhir4ds.cql import parse_cql as engine_parse

        library = engine_parse(cql_text)
    except Exception as exc:  # typed mapping below; never leak tracebacks
        return ParseResult(
            ok=False,
            diagnostics=(diagnostic_from_exception(exc, context="parse"),),
        )
    from fhir4ds.cql.parser.ast_nodes import Definition, FunctionDefinition

    definition_names = tuple(
        stmt.name
        for stmt in getattr(library, "statements", [])
        if isinstance(stmt, (Definition, FunctionDefinition))
    )
    decls = _declarations(library)
    parameter_names = tuple(
        d["name"] for d in decls if d.get("kind") == "parameter"
    )
    return ParseResult(
        library_name=getattr(library, "identifier", "") or "",
        definition_names=definition_names,
        parameter_names=parameter_names,
        declarations=decls,
    )
