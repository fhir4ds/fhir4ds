"""
Extract status filter configurations from parsed CQL function ASTs.

Replaces hardcoded status filter dict by dynamically analyzing fluent function
bodies from Status.cql (or similar libraries) to produce equivalent filter configs.

Handles 4 AST patterns:
1. Simple equality:  E.status = 'finished'
2. In-list:          O.status in { 'final', 'amended', 'corrected' }
3. AND compound:     D.status in {...} and D.intent in {...}
4. Implies:          C.verificationStatus is not null implies (... or ...)
"""

from __future__ import annotations

import logging
from typing import Dict, List, Optional, TYPE_CHECKING

from ..parser.ast_nodes import (
    BinaryExpression,
    FunctionDefinition,
    Identifier,
    ListExpression,
    Literal,
    Property,
    UnaryExpression,
)

if TYPE_CHECKING:
    from ..parser.ast_nodes import Library

logger = logging.getLogger(__name__)


def extract_status_filter(func_def: FunctionDefinition, codes: Optional[Dict] = None) -> Optional[dict]:
    """Extract a status filter config from a fluent function definition.

    Args:
        func_def: A FunctionDefinition AST node (must be fluent, with a Query body).
        codes: Optional dict mapping code names to their info (for resolving ~ comparisons).

    Returns:
        A dict matching the status filter fallback format, or None if the pattern is not recognized.
        Example: {"status_field": "status", "allowed": ["final", "amended"], ...}
    """
    if not func_def.fluent:
        return None

    expr = func_def.expression
    if expr is None or not hasattr(expr, 'where') or expr.where is None:
        return None

    where_expr = expr.where.expression if hasattr(expr.where, 'expression') else expr.where

    return _extract_from_where(where_expr, codes)


def _extract_from_where(where_expr, codes: Optional[Dict] = None) -> Optional[dict]:
    """Extract status filter from a WHERE clause expression."""
    if not isinstance(where_expr, BinaryExpression):
        return None

    op = where_expr.operator

    # Pattern 4: implies (null_passes semantics)
    if op == 'implies':
        return _extract_implies(where_expr, codes)

    # Pattern 3: AND compound (status + intent/category)
    if op == 'and':
        return _extract_and_compound(where_expr, codes)

    # Pattern 1: Simple equality (E.status = 'finished')
    if op == '=' and _is_property_literal(where_expr):
        field = _get_property_field(where_expr.left)
        value = _get_literal_value(where_expr.right)
        if field and value is not None:
            return {"status_field": field, "allowed": [value]}

    # Pattern 2: In-list (O.status in { 'final', 'amended', 'corrected' })
    if op == 'in' and _is_property_list(where_expr):
        field = _get_property_field(where_expr.left)
        values = _get_list_values(where_expr.right)
        if field and values:
            return {"status_field": field, "allowed": values}

    # Pattern 1b: Equivalence with code (I.status ~ 'completed')
    if op == '~':
        return _extract_equivalence(where_expr, codes)

    return None


def _extract_implies(expr: BinaryExpression, codes: Optional[Dict] = None) -> Optional[dict]:
    """Extract from `X is not null implies (X ~ code1 or X ~ code2 or ...)`."""
    # Left should be: Property is not null
    left = expr.left
    if not isinstance(left, UnaryExpression) or left.operator != 'is not null':
        return None

    prop = left.operand
    if not isinstance(prop, Property):
        return None

    field = _get_status_field_from_property(prop)
    if not field:
        return None

    # Right is an or-chain of equivalence comparisons
    allowed = _collect_or_values(expr.right, codes)
    if not allowed:
        return None

    return {"status_field": field, "allowed": allowed, "null_passes": True}


def _extract_and_compound(expr: BinaryExpression, codes: Optional[Dict] = None) -> Optional[dict]:
    """Extract from `status IN {...} AND intent IN {...}`."""
    left_filter = _extract_single_filter(expr.left, codes)
    right_filter = _extract_single_filter(expr.right, codes)

    if not left_filter or not right_filter:
        # Could be AND with exists() for category — skip those for now
        # Try just the left side as a simple status filter
        if left_filter and not right_filter:
            return {"status_field": left_filter["field"], "allowed": left_filter["values"]}
        return None

    # Determine which is status and which is intent/category
    result = {}
    for f in (left_filter, right_filter):
        field = f["field"]
        values = f["values"]
        if field == "status":
            result["status_field"] = field
            result["allowed"] = values
        elif field == "intent":
            result["status_field"] = result.get("status_field", "status")
            result["intent_field"] = field
            result["intent_allowed"] = values
        else:
            # Could be category or other secondary field
            if "status_field" not in result:
                result["status_field"] = field
                result["allowed"] = values
            else:
                result["intent_field"] = field
                result["intent_allowed"] = values

    if "status_field" not in result or "allowed" not in result:
        return None

    return result


def _extract_single_filter(expr, codes: Optional[Dict] = None) -> Optional[dict]:
    """Extract a single field IN list or field = value."""
    if not isinstance(expr, BinaryExpression):
        return None

    if expr.operator == 'in' and _is_property_list(expr):
        field = _get_property_field(expr.left)
        values = _get_list_values(expr.right)
        if field and values:
            return {"field": field, "values": values}

    if expr.operator == '=' and _is_property_literal(expr):
        field = _get_property_field(expr.left)
        value = _get_literal_value(expr.right)
        if field and value is not None:
            return {"field": field, "values": [value]}

    if expr.operator == '~':
        result = _extract_equivalence(expr, codes)
        if result:
            return {"field": result["status_field"], "values": result["allowed"]}

    return None


def _extract_equivalence(expr: BinaryExpression, codes: Optional[Dict] = None) -> Optional[dict]:
    """Extract from `X ~ 'value'` or `X ~ CodeName`."""
    field = _get_property_field(expr.left)
    if not field:
        return None

    # Right could be a Literal or an Identifier (code reference)
    value = _resolve_value(expr.right, codes)
    if value is not None:
        return {"status_field": field, "allowed": [value]}
    return None


def _collect_or_values(expr, codes: Optional[Dict] = None) -> List[str]:
    """Collect all values from an or-chain of equivalence comparisons."""
    if not isinstance(expr, BinaryExpression):
        return []

    if expr.operator == 'or':
        left_vals = _collect_or_values(expr.left, codes)
        right_vals = _collect_or_values(expr.right, codes)
        return left_vals + right_vals

    if expr.operator == '~':
        value = _resolve_value(expr.right, codes)
        if value is not None:
            return [value]

    return []


def _is_property_literal(expr: BinaryExpression) -> bool:
    """Check if expr is Property op Literal."""
    return isinstance(expr.left, Property) and isinstance(expr.right, Literal)


def _is_property_list(expr: BinaryExpression) -> bool:
    """Check if expr is Property IN ListExpression."""
    return isinstance(expr.left, Property) and isinstance(expr.right, ListExpression)


def _get_property_field(node) -> Optional[str]:
    """Get the field name from a Property node."""
    if isinstance(node, Property):
        return _get_status_field_from_property(node)
    return None


def _get_status_field_from_property(prop: Property) -> Optional[str]:
    """Get the status field path from a Property (e.g., 'status', 'verificationStatus')."""
    return prop.path if hasattr(prop, 'path') else None


def _get_literal_value(node) -> Optional[str]:
    """Get string value from a Literal node."""
    if isinstance(node, Literal):
        return node.value
    return None


def _get_list_values(node) -> Optional[List[str]]:
    """Get list of string values from a ListExpression."""
    if isinstance(node, ListExpression) and hasattr(node, 'elements'):
        values = []
        for elem in node.elements:
            if isinstance(elem, Literal):
                values.append(elem.value)
            else:
                return None  # Non-literal in list
        return values
    return None


def _resolve_value(node, codes: Optional[Dict] = None) -> Optional[str]:
    """Resolve a value node to a string. Handles Literals and code Identifiers."""
    if isinstance(node, Literal):
        return node.value
    if isinstance(node, Identifier) and codes:
        code_info = codes.get(node.name)
        if code_info is not None:
            return code_info.get("code", node.name)
    if isinstance(node, Identifier):
        # Without codes context, use the identifier name itself
        # (works for well-known codes like "confirmed" where name == code)
        return node.name
    return None


def extract_all_status_filters(library, codes: Optional[Dict] = None) -> Dict[str, dict]:
    """Extract status filter configs from all fluent functions in a parsed library.

    Args:
        library: A parsed Library AST node.
        codes: Optional dict mapping code names to their info.

    Returns:
        Dict mapping function name to status filter config.
    """
    filters = {}
    for stmt in library.statements:
        if isinstance(stmt, FunctionDefinition) and stmt.fluent:
            config = extract_status_filter(stmt, codes)
            if config is not None:
                filters[stmt.name] = config
                logger.debug(f"Extracted status filter for {stmt.name}: {config}")
    return filters
