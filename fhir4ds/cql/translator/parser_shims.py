"""Parser AST shims for the translator (CQL 2.0 model definitions, CQL20-E).

Keeps ast_nodes imports out of translator.py's hot import path.
"""

from __future__ import annotations

from typing import Optional


def type_specifier_to_cql_string(specifier) -> Optional[str]:
    """Render a CQL type-specifier AST node to its CQL type string.

    NamedTypeSpecifier -> "System.String"; ListTypeSpecifier -> "List<T>";
    IntervalTypeSpecifier -> "Interval<T>"; TupleTypeSpecifier -> "Tuple";
    ChoiceTypeSpecifier -> "Choice<A, B>".
    """
    if specifier is None:
        return None
    name = type(specifier).__name__
    if name == "NamedTypeSpecifier":
        return getattr(specifier, "name", None)
    if name == "ListTypeSpecifier":
        inner = type_specifier_to_cql_string(getattr(specifier, "element_type", None))
        return f"List<{inner}>" if inner else "List<Any>"
    if name == "IntervalTypeSpecifier":
        inner = type_specifier_to_cql_string(getattr(specifier, "point_type", None))
        return f"Interval<{inner}>" if inner else "Interval<Any>"
    if name == "ChoiceTypeSpecifier":
        parts = [
            type_specifier_to_cql_string(c)
            for c in getattr(specifier, "choices", None) or []
        ]
        parts = [p for p in parts if p]
        return f"Choice<{', '.join(parts)}>" if parts else "Choice"
    if name == "TupleTypeSpecifier":
        return "Tuple"
    return getattr(specifier, "name", None)
