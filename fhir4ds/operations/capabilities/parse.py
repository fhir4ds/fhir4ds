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
    ast: dict[str, Any] | None = None

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
        if self.ast is not None:
            out["ast"] = self.ast
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
                entry: dict[str, Any] = {"kind": kind, "name": name}
                # Terminology declarations carry their canonical url on
                # the `id` attribute (ValueSet/CodeSystem declarations:
                # `valueset "VS": 'url'`). Surface id/codesystem/version
                # so adapters can resolve terminology without re-parsing.
                url = getattr(stmt, "id", None)
                if url:
                    entry["id"] = url
                cs = getattr(stmt, "codesystem", None)
                if cs is not None:
                    entry["codesystem"] = cs
                version = getattr(stmt, "version", None)
                if version is not None:
                    entry["version"] = version
                out.append(entry)
    return tuple(out)


def _ast_to_dict(node: Any) -> Any:
    """Serialize the CQL AST to JSON-safe dicts (client-side tree view).

    Nodes serialize as {"kind": <class name>, "children": [...]}; leaf
    values pass through. Recursion is depth-capped defensively (the
    parser rejects pathological nesting long before this, but the
    envelope boundary stays row-resilient).
    """
    import dataclasses as _dc

    def conv(obj: Any, depth: int) -> Any:
        if depth > 200:
            return None
        if obj is None or isinstance(obj, (bool, int, float, str)):
            return obj
        if isinstance(obj, (list, tuple)):
            return [conv(v, depth + 1) for v in obj]
        if _dc.is_dataclass(obj):
            fields = {}
            for f in _dc.fields(obj):
                v = getattr(obj, f.name, None)
                if callable(v):
                    continue
                fields[f.name] = conv(v, depth + 1)
            return {"kind": type(obj).__name__, "children": fields}
        return str(obj)

    return conv(node, 0)


def parse_cql(cql_text: str, *, include_ast: bool = False) -> ParseResult:
    """Parse CQL text into a declaration-metadata envelope.

    Engine seam: fhir4ds.cql.parse_cql (typed ParseError/LexerError ->
    PARSE_ERROR diagnostics with structured location).

    ``include_ast=True`` additionally exposes the statement-level AST
    (one serialized tree per define) via ``statements`` — the AstPane
    surface. Default False keeps the envelope cheap for live typing.
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

    definitions = [
        stmt
        for stmt in getattr(library, "statements", [])
        if isinstance(stmt, (Definition, FunctionDefinition))
    ]
    definition_names = tuple(stmt.name for stmt in definitions)
    decls = _declarations(library)
    parameter_names = tuple(
        d["name"] for d in decls if d.get("kind") == "parameter"
    )
    ast: dict[str, Any] | None = None
    if include_ast:
        ast = {
            "library": getattr(library, "identifier", "") or "",
            "statements": {
                stmt.name: _ast_to_dict(stmt.expression) for stmt in definitions
            },
        }
    return ParseResult(
        library_name=getattr(library, "identifier", "") or "",
        definition_names=definition_names,
        parameter_names=parameter_names,
        declarations=decls,
        ast=ast,
    )
