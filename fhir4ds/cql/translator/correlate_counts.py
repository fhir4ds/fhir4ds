"""Post-pass: correlate flattened Count subqueries to their enclosing row.

CQL patient context scopes every retrieve to ONE patient, but the SQL
retrieve CTE holds ALL patients' rows. When ``Count(<inline query>)`` is
lowered to ``SELECT COUNT(*) FROM <retrieve CTE> AS X WHERE <conjuncts>``
inside an enclosing query's where clause (e.g. CMS832
``where Count("E".fluent()) < 2``), the conjuncts correlate to the
enclosing row only through VALUE columns — the count silently aggregates
OTHER patients' rows (measured: count=10 for a patient with exactly 1
matching observation).

At translation time the where carries ParameterPlaceholder receiver refs,
so the correlation cannot be decided in ``_translate_count``; this pass
runs AFTER placeholder resolution (same slot as
``fix_derived_alias_column_refs``) when outer references are concrete.

The pass finds, for each SELECT scope, scalar ``SELECT COUNT(*)`` subqueries
whose FROM is a CTE reference, whose WHERE references one of the enclosing
scope's visible aliases, and which lack any patient_id correlation — and
appends ``<from_alias>.patient_id = <visible_alias>.patient_id`` conjuncts.
"""

from __future__ import annotations

from typing import Set

from .types import (
    SQLAlias,
    SQLBinaryOp,
    SQLExpression,
    SQLFunctionCall,
    SQLIdentifier,
    SQLQualifiedIdentifier,
    SQLSelect,
    SQLSubquery,
)

_LAMBDA_FN_NAMES = frozenset({
    "list_transform", "list_filter", "list_reduce", "list_sort",
    "list_apply", "list_distinct", "array_transform", "transform",
    "filter", "reduce", "sort", "map",
})

_INTERNAL_ALIAS_PREFIXES = ("_pt", "_patients", "_lv", "_lt_", "_agg", "_cql")

def _iter_child_values(expr):
    """Yield every SQL-valued child of ``expr`` for generic walking.

    Handles the container shapes the dataclass field loop used to drop:
    plain ``list``/``tuple`` field values (``SQLUnion.operands``,
    ``SQLSelect.columns``) and ``SQLCase.when_clauses`` entries, which are
    ``(condition, result)`` tuples without named attributes.
    """
    if isinstance(expr, (list, tuple)):
        # Yield the ITEMS themselves — the caller decides whether to descend.
        yield from expr
        return
    if hasattr(expr, "__dataclass_fields__"):
        for f in expr.__dataclass_fields__:
            yield getattr(expr, f, None)
        return
    # Non-dataclass expression-shaped objects.
    items = getattr(expr, "args", None)
    if items:
        yield from items
    yield from getattr(expr, "elements", None) or []


_CHILd_ATTRS = ("left", "right", "operand", "expression", "condition",
                "then", "else_clause", "source")


def _is_internal_alias(name: str) -> bool:
    return name.startswith(_INTERNAL_ALIAS_PREFIXES)


def _collect_outer_roots(expr, from_alias: str, roots: Set[str]) -> None:
    """Collect alias roots of outer-scope qualified references.

    Does not descend into SQLSubquery/SQLSelect (own FROM scopes) or
    list-lambda function calls (lambda param bindings).
    """
    if expr is None:
        return
    if isinstance(expr, SQLQualifiedIdentifier):
        if expr.parts:
            root = expr.parts[0]
            if root != from_alias and not _is_internal_alias(root):
                roots.add(root)
        return
    if isinstance(expr, (SQLSubquery, SQLSelect)):
        return
    if isinstance(expr, SQLFunctionCall):
        if expr.name and expr.name.lower() in _LAMBDA_FN_NAMES:
            return
        for a in expr.args:
            _collect_outer_roots(a, from_alias, roots)
        return
    for attr in _CHILd_ATTRS:
        _collect_outer_roots(getattr(expr, attr, None), from_alias, roots)
    for child in _iter_child_values(expr):
        _collect_outer_roots(child, from_alias, roots)


def _has_patient_id_correlation(expr) -> bool:
    if expr is None:
        return False
    if isinstance(expr, SQLQualifiedIdentifier):
        return len(expr.parts) == 2 and expr.parts[1] == "patient_id"
    if isinstance(expr, (SQLSubquery, SQLSelect)):
        return False
    if isinstance(expr, SQLFunctionCall):
        if expr.name and expr.name.lower() in _LAMBDA_FN_NAMES:
            return False
        return any(_has_patient_id_correlation(a) for a in expr.args)
    for attr in _CHILd_ATTRS:
        if _has_patient_id_correlation(getattr(expr, attr, None)):
            return True
    return any(_has_patient_id_correlation(c) for c in _iter_child_values(expr))


def _is_count_star_subquery(sub) -> bool:
    """True for `SELECT COUNT(*) FROM <cte> AS X [WHERE ...]` shapes."""
    if not (isinstance(sub, SQLSubquery) and isinstance(sub.query, SQLSelect)):
        return False
    q = sub.query
    if q.group_by or q.having or q.limit or q.distinct or q.joins:
        return False
    if len(q.columns) != 1:
        return False
    col = q.columns[0]
    expr = col.expr if isinstance(col, SQLAlias) else col
    if not (isinstance(expr, SQLFunctionCall) and expr.name.upper() == "COUNT"):
        return False
    if len(expr.args) != 1:
        return False
    arg = expr.args[0]
    if not (isinstance(arg, SQLIdentifier) and arg.name == "*"):
        return False
    fc = q.from_clause
    return (
        isinstance(fc, SQLAlias)
        and isinstance(fc.expr, (SQLIdentifier, SQLQualifiedIdentifier))
        and bool(fc.alias)
    )


def _correlate_one(sub, visible: Set[str]) -> bool:
    q = sub.query
    from_alias = q.from_clause.alias
    if q.where is None:
        return False
    if _has_patient_id_correlation(q.where):
        return False
    roots: Set[str] = set()
    _collect_outer_roots(q.where, from_alias, roots)
    if not roots:
        return False
    # Only correlate through aliases visible in the enclosing scope; if a
    # root is not visible there, the where is bound elsewhere — leave it.
    visible_roots = roots & visible
    if not visible_roots:
        return False
    conj = q.where
    for root in sorted(visible_roots):
        conj = SQLBinaryOp(
            operator="AND",
            left=conj,
            right=SQLBinaryOp(
                operator="=",
                left=SQLQualifiedIdentifier(parts=[from_alias, "patient_id"]),
                right=SQLQualifiedIdentifier(parts=[root, "patient_id"]),
            ),
        )
    q.where = conj
    return True


def _visible_aliases(sel: SQLSelect) -> Set[str]:
    vis: Set[str] = set()
    fc = sel.from_clause
    if isinstance(fc, SQLAlias) and fc.alias:
        vis.add(fc.alias)
    elif isinstance(fc, SQLIdentifier):
        vis.add(fc.name)
    for j in sel.joins or []:
        ja = getattr(j, "alias", None)
        if ja:
            vis.add(ja)
    return vis


def _walk(node, visible: Set[str], changed: list) -> None:
    """Recursively rewrite count subqueries under an enclosing scope."""
    if node is None or isinstance(node, str):
        return
    if isinstance(node, (list, tuple)):
        for e in node:
            _walk(e, visible, changed)
        return
    if isinstance(node, SQLSelect):
        # Entering a new scope: recompute visible aliases for THIS select
        vis = _visible_aliases(node)
        # correlate count subqueries in where/having/columns of this select
        for attr in ("where", "having"):
            v = getattr(node, attr, None)
            if v is None:
                continue
            if _is_count_star_subquery(v):
                if _correlate_one(v, vis):
                    changed.append(1)
            elif isinstance(v, (SQLBinaryOp, SQLFunctionCall, SQLCase)):
                _rewrite_nested(v, vis, changed)
            _walk(v, vis, changed)
        for c in node.columns or []:
            _walk(c, vis, changed)
        _walk(node.from_clause, vis, changed)
        for j in node.joins or []:
            _walk(j, vis, changed)
        return
    if isinstance(node, SQLSubquery):
        _walk(node.query, visible, changed)
        return
    if _is_count_star_subquery(node):
        if _correlate_one(node, visible):
            changed.append(1)
        return
    # Generic recursion over dataclass fields
    if hasattr(node, "__dataclass_fields__"):
        for f in node.__dataclass_fields__:
            _walk(getattr(node, f, None), visible, changed)
        return
    for attr in _CHILd_ATTRS:
        _walk(getattr(node, attr, None), visible, changed)


def _rewrite_nested(expr, visible: Set[str], changed: list) -> None:
    """Rewrite count subqueries nested inside scalar expressions."""
    if expr is None or isinstance(expr, str):
        return
    if isinstance(expr, (list, tuple)):
        for e in expr:
            _rewrite_nested(e, visible, changed)
        return
    if isinstance(expr, SQLSubquery):
        if _is_count_star_subquery(expr):
            if _correlate_one(expr, visible):
                changed.append(1)
        else:
            _rewrite_nested(expr.query, visible, changed)
        return
    if isinstance(expr, SQLSelect):
        return  # handled by _walk scope logic
    if hasattr(expr, "__dataclass_fields__"):
        for f in expr.__dataclass_fields__:
            v = getattr(expr, f, None)
            if isinstance(v, SQLSubquery) and _is_count_star_subquery(v):
                if _correlate_one(v, visible):
                    changed.append(1)
            else:
                _rewrite_nested(v, visible, changed)
        return
    for attr in _CHILd_ATTRS:
        _rewrite_nested(getattr(expr, attr, None), visible, changed)


from .types import SQLCase  # noqa: E402  (used in _walk isinstance check)


def correlate_count_subqueries(ast: SQLExpression) -> SQLExpression:
    """Entry point: add patient_id correlation to flattened Count subqueries.

    Deliberately NOT wrapped in a blanket ``except Exception``. It used to be,
    which meant any bug in the walk silently returned the input AST and a
    miscorrelated ``Count`` shipped as a wrong measure result with no signal
    (review REV-010). A failure here is a translator bug and must surface.
    """
    _walk(ast, set(), [])
    return ast
