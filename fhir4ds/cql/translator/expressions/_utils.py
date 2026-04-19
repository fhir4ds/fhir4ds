"""Shared SQL AST utility helpers for expression translation.

Also provides module-level constants (BINARY_OPERATOR_MAP, etc.) that are
imported by mixin modules to avoid circular imports with the package __init__.
"""
from __future__ import annotations

from typing import Optional

from ...translator.types import (
    SQLAlias,
    SQLArray,
    SQLBinaryOp,
    SQLCase,
    SQLCast,
    SQLExists,
    SQLFunctionCall,
    SQLIdentifier,
    SQLInterval,
    SQLNamedArg,
    SQLSelect,
    SQLSubquery,
    SQLUnaryOp,
)

try:
    from ...translator.types import SQLList
except ImportError:
    SQLList = None  # type: ignore[assignment,misc]


def _is_list_returning_sql(node) -> bool:
    """Return True if *node* is an SQL expression that returns a list/array.

    Detects patterns like ``list_transform(...)``, ``list(...)``,
    ``(SELECT list(...) FROM ...)``, ``from_json(..., '["VARCHAR"]')``,
    or ``SQLArray`` literals.
    """
    if node is None:
        return False
    if isinstance(node, SQLArray):
        return True
    if isinstance(node, SQLFunctionCall):
        if node.name in ("list_transform", "list_filter", "list", "list_sort",
                         "list_distinct", "list_concat"):
            return True
        if node.name == "from_json" and len(node.args) >= 2:
            return True
        return False
    if isinstance(node, SQLSubquery):
        return _is_list_returning_sql(node.query)
    if isinstance(node, SQLSelect) and node.columns:
        col = node.columns[0]
        if isinstance(col, SQLAlias):
            return _is_list_returning_sql(col.expr)
        return _is_list_returning_sql(col)
    return False


def _list_has_order_by(node) -> bool:
    """Return True if *node* contains a list() aggregate with ORDER BY.

    Backbone UNNEST queries produce ``list(x ORDER BY sort_key)`` which
    already sorts correctly.  Callers can use this to avoid adding a
    redundant (and incorrect) ``list_sort`` wrapper.
    """
    if node is None:
        return False
    if isinstance(node, SQLFunctionCall):
        if node.name == "list" and node.order_by:
            return True
        return False
    if isinstance(node, SQLSubquery):
        return _list_has_order_by(node.query)
    if isinstance(node, SQLSelect) and node.columns:
        col = node.columns[0]
        if isinstance(col, SQLAlias):
            return _list_has_order_by(col.expr)
        return _list_has_order_by(col)
    return False


def _contains_sql_subquery(node) -> bool:
    """Return True if *node* (an SQL AST) contains any SQLSelect / SQLSubquery."""
    if node is None:
        return False
    if isinstance(node, (SQLSelect, SQLSubquery)):
        return True
    if isinstance(node, SQLFunctionCall):
        return any(_contains_sql_subquery(a) for a in node.args)
    if isinstance(node, SQLBinaryOp):
        return _contains_sql_subquery(node.left) or _contains_sql_subquery(node.right)
    if isinstance(node, SQLUnaryOp):
        return _contains_sql_subquery(node.operand)
    if isinstance(node, SQLCase):
        for cond, then in node.when_clauses:
            if _contains_sql_subquery(cond) or _contains_sql_subquery(then):
                return True
        return _contains_sql_subquery(node.else_clause)
    if isinstance(node, SQLAlias):
        return _contains_sql_subquery(node.expr)
    if isinstance(node, SQLCast):
        return _contains_sql_subquery(node.expression)
    if isinstance(node, SQLExists):
        return True
    if isinstance(node, SQLNamedArg):
        return _contains_sql_subquery(node.value)
    if isinstance(node, SQLInterval):
        return _contains_sql_subquery(node.low) or _contains_sql_subquery(node.high)
    _list_types = (SQLList,) if SQLList is not None else ()
    if isinstance(node, (SQLArray, *_list_types)):
        items = getattr(node, 'elements', None) or getattr(node, 'items', None) or []
        return any(_contains_sql_subquery(i) for i in items)
    return False


def _ensure_scalar_body(node):
    """Ensure an SQL expression is scalar (single-value) for use in list().

    When a lambda body is a subquery with multiple columns (e.g., SELECT *
    returning patient_id, resource), reduce it to a single column.
    """
    inner = node
    if isinstance(inner, SQLSubquery):
        inner = inner.query
    if isinstance(inner, SQLSelect) and inner.columns:
        has_star = any(
            isinstance(c, SQLIdentifier) and c.name == "*"
            for c in inner.columns
        )
        if has_star or len(inner.columns) > 1:
            new_select = SQLSelect(
                columns=[SQLIdentifier(name="resource")],
                from_clause=inner.from_clause,
                where=inner.where,
                joins=inner.joins,
                group_by=inner.group_by,
                having=inner.having,
                order_by=inner.order_by,
                limit=inner.limit,
                distinct=inner.distinct,
            )
            if isinstance(node, SQLSubquery):
                return SQLSubquery(query=new_select)
            return new_select
    return node


# ---------------------------------------------------------------------------
# Module-level constants shared across mixin modules
# ---------------------------------------------------------------------------

# CQL to SQL operator mappings
BINARY_OPERATOR_MAP = {
    # Arithmetic
    "+": "+",
    "-": "-",
    "*": "*",
    "/": "/",
    "div": "/",  # Integer division - handled specially
    "mod": "%",
    "^": "pow",  # Power function
    # Comparison
    "=": "=",
    "!=": "!=",
    "<>": "!=",
    "<": "<",
    "<=": "<=",
    ">": ">",
    ">=": ">=",
    # Logical
    "and": "AND",
    "or": "OR",
    "xor": "XOR",  # DuckDB supports XOR
    "implies": None,  # Handled specially: NOT A OR B
    # String
    "&": "||",  # String concatenation
    # Null handling
    "is": "IS",
    "is not": "IS NOT",
    # Membership
    "in": "IN",
    "contains": None,  # Handled specially
    # Pattern matching
    "like": "LIKE",
    "matches": "regexp_matches",  # Regex matching
    # Interval
    "properly includes": None,  # Handled specially
    "includes": None,  # Handled specially
    "overlaps": None,  # Handled specially - calls intervalOverlaps UDF
    "during": None,  # Handled specially - calls intervalContains UDF
    "before": None,  # Handled specially
    "after": None,  # Handled specially
    "starts": None,  # Handled specially
    "ends": None,  # Handled specially
    "meets": None,  # Handled specially
    "properly included in": None,
    "included in": None,
    "properly contains": None,
    "meets before": None,
    "meets after": None,
    "overlaps before": None,
    "overlaps after": None,
    "width": None,
    # Date/time comparison
    "same or before": None,
    "same or after": None,
    "same": None,
}

UNARY_OPERATOR_MAP = {
    "not": "NOT",
    "is null": "IS NULL",
    "is not null": "IS NOT NULL",
    "exists": None,  # Handled specially
    "-": "-",
    "+": "+",
}


def _resolve_library_code_constant(library_name: str, constant_name: str, context=None) -> Optional[str]:
    """Resolve a library code constant to its literal value.

    Uses context.codes (populated from parsed library ASTs) when available.
    Returns None if not found — caller must handle non-code references (e.g., definitions).
    """
    if context is not None and hasattr(context, 'codes'):
        code_info = context.codes.get(constant_name)
        if code_info is not None:
            return code_info.get("code")

    if context is not None and hasattr(context, 'includes'):
        lib_info = context.includes.get(library_name)
        if lib_info and hasattr(lib_info, 'library_ast') and lib_info.library_ast:
            for code_def in lib_info.library_ast.codes:
                if code_def.name == constant_name:
                    return code_def.code

    return None


def _get_qicore_extension_fhirpath(registry, resource_type: Optional[str], prop_name: str) -> Optional[str]:
    """Look up a QICore extension FHIRPath expression via ProfileRegistry.

    Tries resource-type-qualified lookup first (e.g. "ServiceRequest.recorded"),
    then falls back to scanning all entries matching the property name for
    cases where the resource type is unknown at translation time.

    Returns a FHIRPath string like
    ``extension.where(url='...').valueDateTime``, or None if not an extension property.
    """
    if registry is None:
        return None
    if resource_type:
        ext = registry.get_extension_info(resource_type, prop_name)
        if ext is not None:
            return f"extension.where(url='{ext.url}').value{ext.value_type}"
    for key, entry in registry._property_extensions.items():
        if key.split(".", 1)[-1] == prop_name:
            return f"extension.where(url='{entry['url']}').value{entry['value_type']}"
    return None
