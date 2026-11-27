"""Shared SQL AST utility helpers for expression translation.

Also provides module-level constants (BINARY_OPERATOR_MAP, etc.) that are
imported by mixin modules to avoid circular imports with the package __init__.
"""
from __future__ import annotations

from typing import Any, Optional

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
    SQLQualifiedIdentifier,
    SQLSelect,
    SQLSubquery,
    SQLUnaryOp,
)
from ...translator.fhirpath_builder import escape_fhirpath_string_literal
from ....fhirpath.duckdb.fhir_types_generated import FHIR_TYPES as _FHIR_R4_TYPES

_FHIR_R4_TYPE_NAMES = frozenset(_FHIR_R4_TYPES)
_FHIR_R4_TYPE_NAMES_BY_LOWER = {
    type_name.lower(): type_name for type_name in _FHIR_R4_TYPE_NAMES
}

try:
    from ...translator.types import SQLList
except ImportError:
    SQLList = None  # type: ignore[assignment,misc]


def _json_array_text_from_fhirpath(node):
    """Re-serialise a list-valued FHIRPath navigation into JSON array TEXT.

    ``fhirpath()`` returns ``VARCHAR[]`` (one JSON text per node), which cannot
    be fed back into another ``fhirpath`` call — the UDF takes a single JSON
    document. Chained navigations therefore need the list re-serialised:
    ``COALESCE('[' || array_to_string(<list>, ',') || ']', '[]')``.
    """
    from ...translator.types import SQLLiteral

    # NOTE: ``concat(...)`` would resolve to the CQL ``Concat`` macro on a
    # registered connection (2-arg VARCHAR only), so build the text with the
    # SQL concatenation operator instead.
    body = SQLBinaryOp(
        operator="||",
        left=SQLBinaryOp(
            operator="||",
            left=SQLLiteral(value="["),
            right=SQLFunctionCall(
                name="array_to_string",
                args=[node, SQLLiteral(value=",")],
            ),
        ),
        right=SQLLiteral(value="]"),
    )
    return SQLFunctionCall(name="COALESCE", args=[body, SQLLiteral(value="[]")])


def _is_json_array_source(node) -> bool:
    """True when *node* materialises a JSON ARRAY of resources.

    Query-valued bindings (``let claim: ([Claim] C where ...)``) are lowered to
    a single-column subquery that builds the array with
    ``'[' || string_agg(<resource col>, ',') || ']'``. Only such sources hold
    MULTIPLE resources, so only they need the trail promoted to the full node
    list — a scalar resource column already navigates correctly with
    ``fhirpath_text``.
    """
    def _has_string_agg(n) -> bool:
        if n is None:
            return False
        name = getattr(n, "name", None)
        if isinstance(name, str) and name.lower() == "string_agg":
            return True
        if isinstance(n, (list, tuple)):
            return any(_has_string_agg(x) for x in n)
        for f in getattr(n, "__dataclass_fields__", {}) or ():
            if _has_string_agg(getattr(n, f, None)):
                return True
        return False

    query = node.query if isinstance(node, SQLSubquery) else node
    if not isinstance(query, SQLSelect):
        return False
    return _has_string_agg(query.columns)


def _promote_source_trail(node):
    """Promote the SOURCE TRAIL of a list operand to the list-returning UDF.

    A list operand's trail is often built from scalar ``fhirpath_text``
    navigations wrapped in a filtering CASE, e.g. CQMCommon.claimDiagnosis::

        let claimItem: (claim.item I where I.encounter.references(E))
        ...
        claimItem.diagnosisSequence

    lowers to ``fhirpath_text(CASE WHEN <encounter matches> THEN
    fhirpath_text(claims, 'item') ELSE NULL END, 'diagnosisSequence')``.
    ``fhirpath_text`` keeps only the FIRST node, so every claim after the first
    (and every item/diagnosis after the first) was silently dropped — leaving
    the claimDiagnosis POA arms FALSE for CMS1028's Numerator and CMS1017's
    fall-POA.

    The trail step is rewritten into JSON array text built from the
    list-returning ``fhirpath`` navigation so the enclosing path sees every
    node.
    """
    if (
        isinstance(node, SQLFunctionCall)
        and node.name == "fhirpath_text"
        and len(node.args) == 2
        and _is_json_array_source(node.args[0])
    ):
        inner = _promote_source_trail(node.args[0])
        return _json_array_text_from_fhirpath(
            SQLFunctionCall(name="fhirpath", args=[inner, node.args[1]])
        )
    if isinstance(node, SQLCase):
        return SQLCase(
            when_clauses=[
                (_promote_source_trail(when), _promote_source_trail(then))
                for when, then in node.when_clauses
            ],
            else_clause=_promote_source_trail(node.else_clause),
        )
    return node


def _promote_fhirpath_text_list(node):
    """Rewrite a scalar 2-arg ``fhirpath_text(...)`` call to its list-valued
    projection ``from_json(fhirpath(...), '["VARCHAR"]')``.

    Multi-valued FHIR property operands (e.g. ``Patient.name.given``) lower to
    ``fhirpath_text``, which truncates to the FIRST matching node. CQL list
    operators (CQL 1.5 Appendix B §10.x) require the full element list, so
    list-operator dispatch must promote such operands. This mirrors the
    established repair for the ``in`` operator in ``_operators.py``
    ("the right side may be multi-valued (e.g., claimItem.diagnosisSequence)").
    """
    from ...translator.types import SQLLiteral

    if (
        isinstance(node, SQLFunctionCall)
        and node.name == "fhirpath_text"
        and len(node.args) == 2
    ):
        return SQLFunctionCall(
            name="from_json",
            args=[
                SQLFunctionCall(
                    name="fhirpath",
                    args=[_promote_source_trail(node.args[0]), node.args[1]],
                ),
                SQLLiteral(value='["VARCHAR"]'),
            ],
        )
    return node


def _is_list_returning_sql(node) -> bool:
    """Return True if *node* is an SQL expression that returns a list/array.

    Detects patterns like ``list_transform(...)``, ``list(...)``,
    ``(SELECT list(...) FROM ...)``, ``from_json(..., '["VARCHAR"]')``,
    or ``SQLArray`` literals.
    """
    if node is None:
        return False
    result_type = getattr(node, "result_type", None)
    if result_type is not None and str(result_type).lower().startswith("list<"):
        return True
    if isinstance(node, SQLArray):
        return True
    if isinstance(node, SQLCast) and node.target_type.endswith("[]"):
        return True
    if isinstance(node, SQLFunctionCall):
        if node.name.upper() == "COALESCE":
            return any(_is_list_returning_sql(arg) for arg in node.args)
        if node.name in ("list_transform", "list_filter", "list", "list_sort",
                         "list_distinct", "list_concat", "list_intersect", "flatten",
                         "str_split", "STR_SPLIT", "string_split",
                         "Distinct", '"Distinct"', "list_reverse", "list_slice",
                         "Skip", "Take", "Tail",
                         # CQL 2.0 list functions (FHIR-40612 etc.): Head/TailN/
                         # Slice are registered list-returning macros — a
                         # define of one of them must be marked stores_list_
                         # value or alias consumers nest the whole list
                         # (d3-EXPLORER QA-D3E-002: Length(HeadAlias) was 1).
                         "Head", "TailN", "Slice",
                         "CQLListDistinctEq", "CQLListExceptEq",
                         "CQLListIntersectEq", "jsonConcat",
                         "cqlChildren", "cqlDescendants", "ExpandValueSet",
                         # Iteration 7 QA-011: expand/collapse UDF forms return
                         # a JSON array string (VARCHAR) holding the whole
                         # element list — one value per patient.
                         "expand", "expand1", "expand_points", "expand_points1",
                         "collapse_intervals", "collapse_intervals_per"):
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


def _is_fhir_r4_type_name(type_name: str | None) -> bool:
    """Return True when *type_name* names a generated FHIR R4 type."""
    if not type_name:
        return False
    bare = type_name.rsplit(".", 1)[-1]
    return bare in _FHIR_R4_TYPE_NAMES or bare.lower() in _FHIR_R4_TYPE_NAMES_BY_LOWER


def _canonical_fhir_r4_type_name(type_name: str | None) -> str | None:
    """Return the generated FHIR R4 spelling for *type_name*, if known."""
    if not type_name:
        return None
    bare = type_name.rsplit(".", 1)[-1]
    if bare in _FHIR_R4_TYPE_NAMES:
        return bare
    return _FHIR_R4_TYPE_NAMES_BY_LOWER.get(bare.lower())


def _is_list_valued_projection(expr) -> bool:
    """True when a projected expression already evaluates to a LIST value.

    Iteration 10 QA-017: the `{ <query> }` list selector lowers to
    ``SELECT COALESCE(list(...), [])`` — a scalar LIST projection.
    Re-coercing such a node (as many consumer sites do) would wrap
    ``list(list(...))`` and nest lists. Idempotence guard.
    """
    if isinstance(expr, SQLFunctionCall):
        if expr.name in ("list", "LIST"):
            return True
        if expr.name == "COALESCE" and expr.args:
            return _is_list_valued_projection(expr.args[0])
    return False


def _typed_list_cast_type(ast_node: Any) -> Optional[str]:
    """The element type of ``<expression> as List<T>``, else None.

    A cast to a list type only names the element type: the value is the (possibly empty or null)
    list the operand evaluates to. Used for define metadata (FHIR4-75: `({} as List<String>)`
    inferred as Any and the define was filed as a resource).
    """
    from ...parser.ast_nodes import BinaryExpression, ListTypeSpecifier

    if (
        isinstance(ast_node, BinaryExpression)
        and ast_node.operator == "as"
        and isinstance(ast_node.right, ListTypeSpecifier)
    ):
        return getattr(ast_node.right.element_type, "name", None) or "Any"
    return None


def _typed_list_cast_is_null(ast_node: Any) -> bool:
    """True for ``(null as List<T>)``."""
    from ...parser.ast_nodes import Literal

    return (
        _typed_list_cast_type(ast_node) is not None
        and isinstance(ast_node.left, Literal)
        and ast_node.left.value is None
    )


def _fold_start_is_typed_list(agg: Any) -> bool:
    """True when an aggregate starts from a typed null or empty list.

    ``aggregate R starting (null as List<T>)`` / ``starting ({} as List<T>)`` makes the accumulator
    a list, so the fold needs a list-typed anchor instead of the integer one a scalar accumulator
    gets (FHIR4-73: the multi-source fold cast every anchor to BIGINT and did not bind).
    """
    from ...parser.ast_nodes import (
        BinaryExpression,
        ListExpression,
        ListTypeSpecifier,
        Literal,
    )

    starting = agg.starting
    return (
        starting is not None
        and isinstance(starting, BinaryExpression)
        and starting.operator == "as"
        and isinstance(starting.right, ListTypeSpecifier)
        and (
            (isinstance(starting.left, Literal) and starting.left.value is None)
            or (isinstance(starting.left, ListExpression) and not starting.left.elements)
        )
    )


def _fold_list_start_sql(agg: Any) -> str:
    """The anchor of a list-accumulator fold: SQL NULL for ``null as List<T>`` and an empty list
    for ``{} as List<T>``."""
    from ...parser.ast_nodes import Literal

    if isinstance(agg.starting.left, Literal):
        return "CAST(NULL AS VARCHAR[])"
    return "CAST([] AS VARCHAR[])"


#: SQL type of a scalar fold's accumulator, by the CQL type of its starting value. A type that
#: is not listed keeps the starting value's own SQL type.
_FOLD_ACCUMULATOR_SQL_TYPES = {
    "Integer": "INTEGER",
    "Long": "BIGINT",
    "Decimal": "DECIMAL(38,8)",
    "String": "VARCHAR",
    "Boolean": "BOOLEAN",
    "Date": "VARCHAR",
    "DateTime": "VARCHAR",
    "Time": "VARCHAR",
}

#: An integral start whose body is statically a wider numeric type (FHIR4-76).
_FOLD_NUMERIC_WIDENING = {
    ("Integer", "Long"): "Long",
    ("Integer", "Decimal"): "Decimal",
    ("Long", "Decimal"): "Decimal",
}


def _fold_accumulator_sql_type(
    start_cql_type: str | None, body_cql_type: str | None
) -> str | None:
    """The SQL type of a scalar fold's accumulator column (FHIR4-76).

    Every step's result is cast back to the accumulator's type, so the type must cover the
    whole CQL type of the starting value: an Integer start is INT32 (overflow then reaches the
    body's ``TRY`` guard and is null per spec), a Decimal start is DECIMAL(38,8). The first
    shape cast every multi-source start to BIGINT (``starting 0.5`` over six rows with
    ``R + 1`` answered 7, not 6.5) and carried a single-source accumulator inside the element
    list, so each step was rounded to the element type. An integral start whose body is
    statically Long or Decimal is widened: the body's type is what the steps compute, and
    truncating each step was silently wrong.
    """
    if start_cql_type is None:
        return None
    kind = _FOLD_NUMERIC_WIDENING.get((start_cql_type, body_cql_type), start_cql_type)
    return _FOLD_ACCUMULATOR_SQL_TYPES.get(kind)


def _fold_anchor_sql(starting_sql: str, sql_type: str | None) -> str:
    """The anchor (first accumulator value) of a scalar fold, cast to its accumulator type."""
    return starting_sql if sql_type is None else f"CAST({starting_sql} AS {sql_type})"


#: SQL transport of a list-typed fold accumulator that has NO starting value. A list
#: accumulator is a DuckDB list of the element TEXT form, exactly as the element lists are.
_FOLD_LIST_ACCUMULATOR_SQL_TYPE = "VARCHAR[]"

#: SQL types of a fold accumulator whose type comes from its BODY, for the CQL types whose
#: transport differs from the starting-value table (FHIR4-84). A Quantity accumulator travels
#: as its JSON text; the starting-value table has no Quantity entry because a Quantity ANCHOR
#: is written as the literal itself, which is already that text.
_FOLD_BODY_ACCUMULATOR_SQL_TYPES = {"Quantity": "VARCHAR"}


def _fold_body_accumulator_sql_type(body_cql_type: str | None) -> str | None:
    """The SQL type of a fold accumulator that has NO starting value, from the BODY (FHIR4-84).

    ``aggregate R: Coalesce(R, 0.0) + N`` has no anchor to take a type from, so the type comes
    from the fold body — which is the accumulator's own type, because the body's result is what
    the next step reads. Leaving the anchor untyped is not an option: DuckDB binds an untyped
    ``CAST(NULL AS ...)``/``NULL`` anchor as INTEGER and coerces every recursive step to it, so
    a Decimal body was truncated (`Coalesce(R, 0.0) + 0.5` over ``{1, 2, 3}`` answered 0, where
    the same fold with ``starting 0.0`` answers 1.5).

    None — an unknown or untyped body — leaves the fold on the older ``list_reduce`` lowering.
    """
    if not body_cql_type or body_cql_type == "Any":
        return None
    if body_cql_type.startswith("List<"):
        return _FOLD_LIST_ACCUMULATOR_SQL_TYPE
    if body_cql_type in _FOLD_BODY_ACCUMULATOR_SQL_TYPES:
        return _FOLD_BODY_ACCUMULATOR_SQL_TYPES[body_cql_type]
    return _FOLD_ACCUMULATOR_SQL_TYPES.get(body_cql_type)


def _coerce_query_rows_to_list(node):
    """Convert a row-producing single-column query into a scalar DuckDB list."""
    inner_select = None
    if isinstance(node, SQLSubquery) and isinstance(node.query, SQLSelect):
        inner_select = node.query
    elif isinstance(node, SQLSelect):
        inner_select = node

    if inner_select is None or not inner_select.columns:
        return node

    first_col = inner_select.columns[0]
    if isinstance(first_col, tuple):
        first_expr = first_col[0]
    elif isinstance(first_col, SQLAlias):
        first_expr = first_col.expr
    else:
        first_expr = first_col

    # Idempotence (iteration 10 QA-017): a projection that already
    # evaluates to a LIST value needs no rows-to-list coercion.
    if _is_list_valued_projection(first_expr):
        return node

    value_alias = "__cql_list_value"

    # QA-D3E-001: a star projection (`SELECT * FROM "CTE" AS X`) cannot be
    # re-projected as `SELECT * AS __cql_list_value` — the alias renames
    # EVERY expanded column and DuckDB resolves the qualified reference to
    # the FIRST one (patient_id), so the element list silently holds
    # patient ids instead of values. Callers with schema context must
    # rewrite the star to the CTE's element column first (see the
    # count-unnest leaf loop in _functions.py); coerce never aliases a
    # star and degrades to no-op so mis-shapes fail loudly downstream.
    _first_is_star = (
        isinstance(first_expr, SQLIdentifier) and first_expr.name == "*"
    ) or (
        isinstance(first_expr, SQLQualifiedIdentifier)
        and first_expr.parts[-1] == "*"
    )
    if _first_is_star:
        return node

    # QA-D3H-001: a query used as a query source lowers to a one-row-per-
    # element projection whose WHERE/HAVING/ORDER BY may reference the
    # PROJECTED ALIAS (DuckDB allows alias references in WHERE):
    #   SELECT <cast> AS Q FROM "Observation" O WHERE Q IS NOT NULL AND ...
    # Re-projecting the column as __cql_list_value while copying the WHERE
    # verbatim drops the alias column and yields
    # "Referenced column Q not found". When any trailing clause references
    # the alias, nest the ORIGINAL select as a derived table instead and
    # project the qualified alias column — semantically equivalent and the
    # alias binding survives.
    _first_alias = first_col.alias if isinstance(first_col, SQLAlias) else None
    if _first_alias:
        def _sql_references_name(node, name: str) -> bool:
            if node is None:
                return False
            if isinstance(node, (list, tuple)):
                return any(_sql_references_name(e, name) for e in node)
            if isinstance(node, SQLIdentifier):
                return node.name == name
            if isinstance(node, SQLQualifiedIdentifier):
                return name in node.parts
            stack = [node]
            seen = set()
            while stack:
                cur = stack.pop()
                if id(cur) in seen:
                    continue
                seen.add(id(cur))
                if isinstance(cur, SQLIdentifier) and cur.name == name:
                    return True
                if isinstance(cur, SQLQualifiedIdentifier) and name in cur.parts:
                    return True
                for value in vars(cur).values():
                    if hasattr(value, "__dict__"):
                        stack.append(value)
                    elif isinstance(value, (list, tuple)):
                        stack.extend(
                            e for e in value if hasattr(e, "__dict__")
                        )
            return False

        _trailing = (inner_select.where, inner_select.having,
                     inner_select.order_by, inner_select.group_by)
        if any(_sql_references_name(clause, _first_alias) for clause in _trailing):
            _qualified = SQLQualifiedIdentifier(
                parts=["_cql_row_source", _first_alias]
            )
            return SQLSubquery(query=SQLSelect(
                columns=[SQLFunctionCall(
                    name="COALESCE",
                    args=[
                        SQLFunctionCall(name="list", args=[_qualified]),
                        SQLArray([]),
                    ],
                )],
                from_clause=SQLAlias(
                    expr=SQLSubquery(query=inner_select),
                    alias="_cql_row_source",
                ),
            ))

    # Engine-backlog: DISTINCT (the CQL default `return` de-dup at the
    # definition root) reorders rows hash-wise, scrambling list() order
    # against order-sensitive comparison. With no explicit ORDER BY, order
    # the aggregate by the element so deduped lists come out deterministic
    # (source-order for already-ordered literals, ascending otherwise).
    _order_elem = first_expr if (inner_select.distinct and not inner_select.order_by) else None
    projected = SQLSelect(
        columns=[SQLAlias(expr=first_expr, alias=value_alias)],
        from_clause=inner_select.from_clause,
        joins=inner_select.joins,
        where=inner_select.where,
        group_by=inner_select.group_by,
        having=inner_select.having,
        order_by=inner_select.order_by,
        limit=inner_select.limit,
        distinct=inner_select.distinct,
    )
    value_ref = SQLQualifiedIdentifier(parts=["_cql_list_source", value_alias])
    if _order_elem is not None:
        _list_call = SQLFunctionCall(
            name="list",
            args=[value_ref],
            order_by=[(value_ref, "ASC")],
        )
    else:
        _list_call = SQLFunctionCall(name="list", args=[value_ref])
    return SQLSubquery(query=SQLSelect(
        columns=[SQLFunctionCall(
            name="COALESCE",
            args=[
                _list_call,
                SQLArray([]),
            ],
        )],
        from_clause=SQLAlias(
            expr=SQLSubquery(query=projected),
            alias="_cql_list_source",
        ),
    ))


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
    # NOTE (FHIR4-43): there is deliberately no "properly contains" entry.
    # CQL has no such operator (the point reads are `properly includes` /
    # `properly included in`), and listing it here as "handled specially"
    # was false — no dispatch site handled it, so the raw text reached
    # DuckDB. The parser now rejects the spelling outright.
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

    Resolves against the OWNING library's parsed AST first — the global
    ``context.codes`` table is populated by copying included-library codes
    under their bare names, so with two included libraries declaring the
    same code NAME (e.g. Status and FHIRCommon both declare "confirmed"),
    the global table holds whichever registered last and a qualified
    ``A."shared"`` could silently resolve to library B's code value.
    Falls back to the global table only when the library's AST is
    unavailable. Returns None if not found — caller must handle non-code
    references (e.g., definitions).
    """
    if context is not None and hasattr(context, 'includes'):
        lib_info = context.includes.get(library_name)
        if lib_info and hasattr(lib_info, 'library_ast') and lib_info.library_ast:
            for code_def in lib_info.library_ast.codes:
                if code_def.name == constant_name:
                    return code_def.code

    if context is not None and hasattr(context, 'codes'):
        code_info = context.codes.get(constant_name)
        if code_info is not None:
            return code_info.get("code")

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
            escaped_url = escape_fhirpath_string_literal(ext.url)
            return f"extension.where(url='{escaped_url}').value{ext.value_type}"
    for key, entry in registry._property_extensions.items():
        if key.split(".", 1)[-1] == prop_name:
            escaped_url = escape_fhirpath_string_literal(entry["url"])
            return f"extension.where(url='{escaped_url}').value{entry['value_type']}"
    return None


# Canonical set of functions returning a JSON-array-string list. Shared by
# the aggregate lowering (_functions.py) and _coerce_json_list_source — keep
# ONE definition (REV-002 drift doctrine; code review L-2, v0.0.25).
JSON_LIST_SOURCE_FUNCS = frozenset(
    {
        "collapse_intervals",
        "collapse_intervals_per",
        "expand",
        "expand1",
        "expand_points",
        "expand_points1",
    }
)

# Backwards-compatible alias for existing importers.
_JSON_LIST_SOURCE_FUNCS = JSON_LIST_SOURCE_FUNCS


def _coerce_json_list_source(node):
    """Rewrite a JSON-array-string list function call to a native DuckDB list.

    ``collapse_intervals``/``collapse_intervals_per``/``expand*`` return a JSON
    array text (VARCHAR), not a list. List consumers that call DuckDB list
    functions/macros directly (``CQLListEqualEq``, ``CQLListContainsEq``,
    ``array_length``) binder-error on the raw VARCHAR. This extends the CQL-15
    HISTORIAN JSON-list doctrine (``_JSON_LIST_FUNCS`` in ``_functions.py``,
    the LIST_EXTRACT wrap in ``_lists.py``) to the list equality/membership
    lowering sites (D3 EXPLORER 2026-11-17).
    """
    from ...translator.types import SQLFunctionCall, SQLLiteral

    if (
        isinstance(node, SQLFunctionCall)
        and node.name in _JSON_LIST_SOURCE_FUNCS
    ):
        return SQLFunctionCall(
            name="from_json",
            args=[node, SQLLiteral(value='["VARCHAR"]')],
        )
    return node
