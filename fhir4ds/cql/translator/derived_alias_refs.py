"""Reverse optimizer column substitutions on derived-table (union) aliases.

The retrieve optimizer replaces ``fhirpath_text(A.resource, 'period')`` with
``A.period`` when the alias-to-CTE map binds A to a CTE that precomputes the
column. When the select's FROM is a DERIVED table (an inlined union or
subquery) the alias binds no CTE: the union arms' contract exposes only
``(patient_id, resource)``, so the substituted column reference dangles and
DuckDB binder-fails (``Values list "A" does not have a column named
"period"`` — CMS145 ValidEncounter.period over an inlined encounter union).

The substitution can still fire for derived FROMs because the global
alias→CTE map is additive across sibling selects in one definition AST. This
Phase-3 post-pass walks the RESOLVED+OPTIMIZED AST and, for every select
whose FROM is a derived table, rewrites non-exposed ``A.<col>`` references
back to their fhirpath/interval-bound forms using the column registry's
reverse map (column_name → fhirpath). Rewrites only occur where the
reference would otherwise be a guaranteed binder error, so working SQL is
untouched.
"""
from __future__ import annotations

from typing import Dict, Optional, Set

from .types import (
    SQLExpression,
    SQLSelect,
    SQLSubquery,
    SQLUnion,
    SQLIntersect,
    SQLExcept,
    SQLAlias,
    SQLIdentifier,
    SQLQualifiedIdentifier,
    SQLFunctionCall,
    SQLLiteral,
)

# Columns every union/subquery derived table is contractually guaranteed to
# expose (the rows-shape projection contract used across the translator).
_EXPOSED_COLS = {"patient_id", "resource", "value", "*"}


def _is_derived_from(from_clause) -> bool:
    """True when the FROM binds a derived table (inline union/subquery)."""
    if not isinstance(from_clause, SQLAlias):
        return False
    expr = from_clause.expr
    if isinstance(expr, (SQLUnion, SQLIntersect, SQLExcept)):
        return True
    if isinstance(expr, SQLSubquery):
        # A subquery over a bare identifier is a CTE scan, not derived shape.
        return not isinstance(expr.query, SQLIdentifier)
    return False


def _build_reverse_column_map(registry) -> Dict[str, str]:
    """column_name -> fhirpath path (first registry entry wins)."""
    reverse: Dict[str, str] = {}
    if registry is None:
        return reverse
    columns_store = getattr(registry, "_columns", None) or {}
    for cte_name, cols in columns_store.items():
        for col_name, info in (cols or {}).items():
            if col_name not in reverse and getattr(info, "fhirpath", None):
                reverse[col_name] = info.fhirpath
    return reverse


def _rewrite_scope(
    node: SQLExpression,
    alias: str,
    reverse_cols: Dict[str, str],
    rebound: Set[str],
    is_root: bool = False,
) -> SQLExpression:
    """Rewrite ``alias.<col>`` refs inside one select's scope.

    ``rebound`` accumulates aliases re-bound by NESTED selects so refs to
    those aliases inside the nested scope are left alone. The ROOT select's
    own FROM alias is NOT rebound — its references are exactly the ones to
    rewrite.
    """
    if node is None or isinstance(node, (str, int, float, bool)):
        return node

    if isinstance(node, SQLSelect):
        if not is_root and isinstance(node.from_clause, SQLAlias):
            rebound = rebound | {node.from_clause.alias.lower()}
        node.columns = [
            ( _rewrite_scope(c[0], alias, reverse_cols, rebound), c[1])
            if isinstance(c, tuple)
            else _rewrite_scope(c, alias, reverse_cols, rebound)
            for c in (node.columns or [])
        ]
        if node.from_clause is not None:
            node.from_clause = _rewrite_scope(node.from_clause, alias, reverse_cols, rebound)
        if node.where is not None:
            node.where = _rewrite_scope(node.where, alias, reverse_cols, rebound)
        if node.having is not None:
            node.having = _rewrite_scope(node.having, alias, reverse_cols, rebound)
        if node.order_by:
            node.order_by = [
                (_rewrite_scope(e, alias, reverse_cols, rebound), d) for e, d in node.order_by
            ]
        if node.group_by:
            node.group_by = [_rewrite_scope(g, alias, reverse_cols, rebound) for g in node.group_by]
        return node

    if isinstance(node, SQLQualifiedIdentifier) and len(node.parts) == 2:
        root, col = node.parts
        if root.lower() in rebound:
            return node
        if root == alias and col not in _EXPOSED_COLS:
            rewritten = _reverse_column_ref(alias, col, reverse_cols)
            if rewritten is not None:
                return rewritten
        return node

    # Generic recursion over dataclass fields / lists
    if hasattr(node, "__dict__"):
        for name, value in list(vars(node).items()):
            if isinstance(value, SQLExpression):
                setattr(node, name, _rewrite_scope(value, alias, reverse_cols, rebound))
            elif isinstance(value, list):
                setattr(node, name, [
                    _rewrite_scope(v, alias, reverse_cols, rebound)
                    if isinstance(v, SQLExpression) else v
                    for v in value
                ])
    return node


def _reverse_column_ref(alias: str, col: str, reverse_cols: Dict[str, str]) -> Optional[SQLExpression]:
    """Rebuild the pre-optimization expression for ``alias.col``."""
    resource = SQLQualifiedIdentifier(parts=[alias, "resource"])

    # Interval-bound columns reverse to intervalStart/intervalEnd over the
    # base path's fhirpath extraction (the UDFs implement the closed-null
    # sentinel doctrine themselves).
    for suffix, fn in (("_start", "intervalStart"), ("_end", "intervalEnd")):
        if col.endswith(suffix):
            base_col = col[: -len(suffix)]
            path = reverse_cols.get(base_col)
            if path:
                return SQLFunctionCall(
                    name=fn,
                    args=[
                        SQLFunctionCall(
                            name="fhirpath_text",
                            args=[resource, SQLLiteral(value=path)],
                        )
                    ],
                )
            return None

    path = reverse_cols.get(col)
    if path:
        return SQLFunctionCall(
            name="fhirpath_text",
            args=[resource, SQLLiteral(value=path)],
        )
    # Unknown column with no registry entry: leave as-is (may be a real
    # column of a subquery projection we do not model).
    return None


def fix_derived_alias_column_refs(ast: SQLExpression, registry) -> SQLExpression:
    """Top-level entry: fix all derived-table alias column references."""
    if ast is None:
        return ast
    reverse_cols = _build_reverse_column_map(registry)

    stack = [ast]
    seen = set()
    while stack:
        node = stack.pop()
        if node is None or id(node) in seen:
            continue
        seen.add(id(node))
        if isinstance(node, SQLSelect):
            if _is_derived_from(node.from_clause) and isinstance(node.from_clause, SQLAlias):
                alias = node.from_clause.alias
                # Rewrite this select's scope (columns/where/order/having and
                # nested scopes that do not rebind the alias). The root's
                # own FROM alias stays rewritable.
                _rewrite_scope(node, alias, reverse_cols, set(), is_root=True)
            # continue walking to find nested derived selects
        if hasattr(node, "__dict__"):
            for value in vars(node).values():
                if isinstance(value, SQLExpression):
                    stack.append(value)
                elif isinstance(value, list):
                    stack.extend(v for v in value if isinstance(v, SQLExpression))
    return ast
