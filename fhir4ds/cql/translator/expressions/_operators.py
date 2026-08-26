"""Binary and unary operator translation for CQL to SQL."""
from __future__ import annotations

import json
import logging
import re as _re
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple, Union

_logger = logging.getLogger(__name__)


def _is_patient_id_correlation(w) -> bool:
    """Return True if *w* is purely ``sub.patient_id = X.patient_id``."""
    from ...translator.types import SQLBinaryOp, SQLQualifiedIdentifier
    if not isinstance(w, SQLBinaryOp) or w.operator != "=":
        return False
    for side_a, side_b in [(w.left, w.right), (w.right, w.left)]:
        if (isinstance(side_a, SQLQualifiedIdentifier)
                and len(side_a.parts) == 2
                and side_a.parts[1] == "patient_id"
                and isinstance(side_b, SQLQualifiedIdentifier)
                and len(side_b.parts) == 2
                and side_b.parts[1] == "patient_id"):
            return True
    return False

from ...parser.ast_nodes import (
    AggregateExpression,
    AliasRef,
    AllExpression,
    AnyExpression,
    BinaryExpression,
    CaseExpression,
    CaseItem,
    ChoiceTypeSpecifier,
    CodeSelector,
    ConditionalExpression,
    DateComponent,
    DateTimeLiteral,
    DifferenceBetween,
    DurationBetween,
    ExistsExpression,
    FirstExpression,
    FunctionRef,
    Identifier,
    IndexerExpression,
    InstanceExpression,
    Interval,
    LastExpression,
    ListExpression,
    ListTypeSpecifier,
    Literal,
    MethodInvocation,
    IntervalTypeSpecifier,
    NamedTypeSpecifier,
    Property,
    QualifiedIdentifier,
    Quantity,
    Query,
    QuerySource,
    Retrieve,
    SingletonExpression,
    SkipExpression,
    TakeExpression,
    TimeLiteral,
    TupleElement,
    TupleExpression,
    TupleTypeSpecifier,
    UnaryExpression,
)
from ...translator.context import ExprUsage, RowShape, DefinitionMeta
from ...translator.function_inliner import ParameterPlaceholder
from ...translator.placeholder import RetrievePlaceholder
from ...translator.types import (
    PRECEDENCE,
    SQLAlias,
    SQLArray,
    SQLAuditStruct,
    SQLBinaryOp,
    SQLCase,
    SQLCast,
    SQLExists,
    SQLExpression,
    SQLExtract,
    SQLFunctionCall,
    SQLIdentifier,
    SQLInterval,
    SQLIntervalLiteral,
    SQLJoin,
    SQLLambda,
    SQLLiteral,
    SQLNamedArg,
    SQLNull,
    SQLParameterRef,
    SQLQualifiedIdentifier,
    SQLRaw,
    SQLSelect,
    SQLSubquery,
    SQLUnaryOp,
    SQLUnion,
    SQLIntersect,
    SQLExcept,
    _is_null_expression,
)

_AUDIT_MACRO_NAMES = frozenset({"audit_and", "audit_or", "audit_or_all", "audit_not", "audit_leaf", "audit_comparison", "audit_breadcrumb", "compact_audit"})
_STRUCTURAL_TYPE_SPECIFIER_TYPES = (
    NamedTypeSpecifier,
    IntervalTypeSpecifier,
    ListTypeSpecifier,
    ChoiceTypeSpecifier,
    TupleTypeSpecifier,
)

_CQL_INTEGER_MIN = -2147483648
_CQL_INTEGER_MAX = 2147483647
_CQL_LONG_MIN = -9223372036854775808
_CQL_LONG_MAX = 9223372036854775807


def _infer_static_numeric_type(node: Any) -> Optional[str]:
    """Statically infer the numeric CQL type of a literal-ish expression.

    Limited to literals and unary +/- of literals so callers (e.g. Power
    operand typing) can pick the correct result type per CQL §16 without
    needing the full inference engine. Returns one of ``"Integer"``,
    ``"Long"``, ``"Decimal"`` or ``None`` when the type is not statically
    determinable.
    """
    if isinstance(node, Literal):
        if isinstance(node.value, bool):
            return None
        name = getattr(node, "type", None)
        if name is None:
            return None
        return str(name).split(".")[-1]
    if isinstance(node, UnaryExpression) and node.operator in {"+", "-"}:
        return _infer_static_numeric_type(node.operand)
    if isinstance(node, FunctionRef) and node.name.lower() == "coalesce":
        # Coalesce preserves the static type of its first non-null-typed
        # argument; numeric callers (e.g. integer literal lists) keep the
        # element type through the lowering.
        inferred: Optional[str] = None
        for arg in getattr(node, "arguments", []):
            elements = getattr(arg, "elements", None)
            candidates = elements if elements is not None else [arg]
            for element in candidates:
                arg_type = _infer_static_numeric_type(element)
                if arg_type is None:
                    continue
                if inferred is None:
                    inferred = arg_type
                elif inferred != arg_type:
                    return None
        return inferred
    return None


def _static_numeric_value(node: Any) -> Optional[float]:
    """Statically evaluate a literal-ish numeric expression to a Python float.

    Returns None when the value cannot be statically determined. Used by
    Power translation to detect negative-Integer exponents (which per the
    official CQL conformance suite produce Decimal results even for
    Integer operand signatures — e.g. ``Power(2, -2) = 0.25``).
    """
    if isinstance(node, Literal):
        if isinstance(node.value, bool):
            return None
        if isinstance(node.value, (int, float)):
            return float(node.value)
        return None
    if isinstance(node, UnaryExpression) and node.operator in {"+", "-"}:
        inner = _static_numeric_value(node.operand)
        if inner is None:
            return None
        return -inner if node.operator == "-" else inner
    return None


def _sql_list_type_for_cql_list_specifier(specifier: ListTypeSpecifier) -> str:
    """Return a DuckDB list type for a statically typed empty CQL list."""
    element = specifier.element_type
    if isinstance(element, NamedTypeSpecifier):
        bare = element.name.split(".")[-1].lower()
        if bare == "boolean":
            return "BOOLEAN[]"
        if bare == "integer":
            return "INTEGER[]"
        if bare == "long":
            return "BIGINT[]"
        if bare == "decimal":
            return "DOUBLE[]"
    return "VARCHAR[]"


def _literal_int_values(args: list) -> Optional[list[int]]:
    values: list[int] = []
    for arg in args:
        if not isinstance(arg, Literal) or not isinstance(arg.value, int) or isinstance(arg.value, bool):
            return None
        values.append(arg.value)
    return values


def _is_untyped_null_bound_interval(node: object) -> bool:
    """Return true for authored ``Interval[null, null]`` literals."""
    return (
        isinstance(node, Interval)
        and isinstance(node.low, Literal)
        and node.low.value is None
        and isinstance(node.high, Literal)
        and node.high.value is None
    )


def _is_datetime_boundary_constructor(node: object, values: list[int]) -> bool:
    if not isinstance(node, FunctionRef) or node.name.lower() != "datetime":
        return False
    actual = _literal_int_values(node.arguments)
    return actual is not None and actual[: len(values)] == values


def _is_time_boundary_literal(node: object, value: str) -> bool:
    return isinstance(node, DateTimeLiteral) and node.value == value


def _is_datetime_boundary_literal(node: object, value: str) -> bool:
    if not isinstance(node, DateTimeLiteral):
        return False
    return node.value == value or node.value == f"{value}Z"


def _contains_aggregate_lambda_identifier(expr: "SQLExpression") -> bool:
    """DuckDB TRY() cannot bind lambda parameters; avoid wrapping those bodies."""
    if isinstance(expr, SQLIdentifier):
        return (
            expr.name.startswith("_agg_")
            or expr.name.startswith("_lt_")
            or expr.name in {"_v", "_cql_item", "x", "r"}
        )
    if isinstance(expr, SQLBinaryOp):
        return (
            _contains_aggregate_lambda_identifier(expr.left)
            or _contains_aggregate_lambda_identifier(expr.right)
        )
    if isinstance(expr, SQLUnaryOp):
        return _contains_aggregate_lambda_identifier(expr.operand)
    if isinstance(expr, SQLCast):
        return _contains_aggregate_lambda_identifier(expr.expression)
    if isinstance(expr, SQLFunctionCall):
        return any(_contains_aggregate_lambda_identifier(arg) for arg in expr.args)
    if isinstance(expr, SQLLambda):
        return _contains_aggregate_lambda_identifier(expr.body)
    if isinstance(expr, SQLCase):
        if expr.operand is not None and _contains_aggregate_lambda_identifier(expr.operand):
            return True
        if expr.else_clause is not None and _contains_aggregate_lambda_identifier(expr.else_clause):
            return True
        return any(
            _contains_aggregate_lambda_identifier(condition)
            or _contains_aggregate_lambda_identifier(result)
            for condition, result in expr.when_clauses
        )
    return False


def _extract_audit_target(
    expr: "SQLExpression",
    context: "Optional[SQLTranslationContext]" = None,
) -> "Optional[SQLExpression]":
    """Recursively walk a SQL AST to find or synthesize an audit target expression.

    First/Last attach ``_audit_target`` on their SQLSubquery.  But by the time
    a comparison is translated, the operand may be a fresh correlated subquery
    to a CTE — the metadata is lost.  So we also *synthesize* a target when we
    find a ``SELECT sub.resource FROM "CTE" ...`` pattern, constructing a twin
    subquery that returns ``resourceType/id`` from the same row.

    When *context* is provided, the function can also detect scalar SELECTs whose
    FROM clause references a RESOURCE_ROWS CTE (via ``definition_meta``).
    """
    if hasattr(expr, "_audit_target"):
        return expr._audit_target  # type: ignore[attr-defined]
    if isinstance(expr, SQLCast):
        return _extract_audit_target(expr.expression, context)
    if isinstance(expr, SQLFunctionCall):
        for arg in expr.args:
            t = _extract_audit_target(arg, context)
            if t is not None:
                return t
    if isinstance(expr, SQLCase):
        # Walk through CASE WHEN branches to find the resource subquery
        for _cond, then_val in expr.when_clauses:
            t = _extract_audit_target(then_val, context)
            if t is not None:
                return t
        if expr.else_clause:
            t = _extract_audit_target(expr.else_clause, context)
            if t is not None:
                return t
    if isinstance(expr, SQLSubquery):
        inner = expr.query
        if isinstance(inner, SQLSelect):
            synth = _synthesize_target_from_resource_select(inner, context)
            if synth is not None:
                return synth
            for col in (inner.columns or []):
                t = _extract_audit_target(col, context)
                if t is not None:
                    return t
    if isinstance(expr, SQLSelect) and expr.columns:
        for col in expr.columns:
            t = _extract_audit_target(col, context)
            if t is not None:
                return t
    if isinstance(expr, SQLAlias):
        return _extract_audit_target(expr.expr, context)
    return None


def _contains_function_call(expr: "SQLExpression") -> bool:
    """True when the SQL expression tree contains any SQLFunctionCall node."""
    if isinstance(expr, SQLFunctionCall):
        return True
    if isinstance(expr, SQLBinaryOp):
        return _contains_function_call(expr.left) or _contains_function_call(expr.right)
    if isinstance(expr, SQLUnaryOp):
        return _contains_function_call(expr.operand)
    if isinstance(expr, SQLCast):
        return _contains_function_call(expr.expression)
    if isinstance(expr, SQLCase):
        # Strict casts lower to CASE ... ELSE error('...') END; error() is a
        # volatile SQLFunctionCall that DuckDB forbids inside TRY(...), so it
        # must be visible to the volatile-guard recursion.
        if _contains_function_call(expr.else_clause):
            return True
        for condition, result in expr.when_clauses or []:
            if _contains_function_call(condition) or _contains_function_call(result):
                return True
        return _contains_function_call(expr.operand)
    return False


def _decimal_static_arithmetic_unrepresentable(expr: Any) -> bool:
    """True when a statically evaluable Decimal arithmetic result overflows.

    CQL 1.5 Appendix B arithmetic header: "operations that cause arithmetic
    overflow or underflow, or otherwise cannot be performed ... will result
    in null, rather than a run-time error." Integer/Long pairs are covered
    by ``_static_integer_arithmetic_overflows``; this helper covers Decimal
    (and mixed Decimal/Integer) literal +, -, * whose exact result exceeds
    the implementation Decimal width DECIMAL(38, 8) (i.e. an integer part
    beyond 30 digits), which DuckDB would otherwise raise
    OutOfRangeException on instead of returning null.
    """

    from decimal import Decimal as _Decimal, InvalidOperation as _InvalidOperation

    def _eval(node: Any) -> Optional[_Decimal]:
        if isinstance(node, Literal):
            value = getattr(node, "value", None)
            if isinstance(value, bool) or not isinstance(value, (int, _Decimal, float)):
                return None
            try:
                return _Decimal(str(value))
            except (_InvalidOperation, ValueError):
                return None
        if isinstance(node, UnaryExpression) and getattr(node, "operator", None) in ("+", "-"):
            inner = _eval(node.operand)
            if inner is None:
                return None
            return -inner if node.operator == "-" else inner
        if isinstance(node, BinaryExpression) and node.operator in ("+", "-", "*"):
            left = _eval(node.left)
            right = _eval(node.right)
            if left is None or right is None:
                return None
            if node.operator == "+":
                return left + right
            if node.operator == "-":
                return left - right
            return left * right
        return None

    evaluated = _eval(expr)
    if evaluated is None or evaluated == 0:
        return False
    # DECIMAL(38, 8): 30 integer digits max. Excess fractional scale is
    # rounded per the CQL-01 representability doctrine, not overflow.
    return abs(evaluated) >= _Decimal(10) ** 30


def _numeric_static_operand_types(expr: Any) -> bool:
    """True when every statically-known numeric operand type is Integer/Long/Decimal.

    Decimal-inclusive variant of ``_integral_static_operand_types`` used to
    guard Decimal arithmetic with TRY(...) so DuckDB decimal overflow
    becomes NULL per the CQL 1.5 arithmetic overflow-to-null rule instead
    of raising OutOfRangeException at execution.
    """
    for side in (getattr(expr, "left", None), getattr(expr, "right", None)):
        t = _infer_static_numeric_type(side)
        if t is not None and t not in ("Integer", "Long", "Decimal"):
            return False
    return True


def _integral_static_operand_types(expr: Any) -> bool:
    """True when every statically-known numeric operand type is Integer/Long.

    Unknown (None) operand types are allowed so runtime values (columns,
    type extents) are guarded; any statically-known Decimal/String/Quantity
    operand disqualifies the expression from the integral TRY guard.
    """
    for side in (getattr(expr, "left", None), getattr(expr, "right", None)):
        t = _infer_static_numeric_type(side)
        if t is not None and t not in ("Integer", "Long"):
            return False
    return True


def _static_integer_arithmetic_overflows(expr: Any) -> bool:
    """Return True when a statically evaluable Integer/Long arithmetic result overflows."""

    def _eval(node: Any) -> Optional[Tuple[int, Tuple[int, int]]]:
        if isinstance(node, Literal) and isinstance(node.value, int) and not isinstance(node.value, bool):
            cql_type = getattr(node, "type", None)
            bounds = (_CQL_LONG_MIN, _CQL_LONG_MAX) if cql_type == "Long" else (_CQL_INTEGER_MIN, _CQL_INTEGER_MAX)
            return node.value, bounds
        if isinstance(node, UnaryExpression) and getattr(node, "operator", None) in ("+", "-"):
            inner = _eval(node.operand)
            if inner is None:
                return None
            value, bounds = inner
            return (-value if node.operator == "-" else value), bounds
        if isinstance(node, BinaryExpression) and node.operator in ("+", "-", "*"):
            left = _eval(node.left)
            right = _eval(node.right)
            if left is None or right is None:
                return None
            left_value, left_bounds = left
            right_value, right_bounds = right
            if node.operator == "+":
                value = left_value + right_value
            elif node.operator == "-":
                value = left_value - right_value
            else:
                value = left_value * right_value
            bounds = (
                (_CQL_LONG_MIN, _CQL_LONG_MAX)
                if left_bounds == (_CQL_LONG_MIN, _CQL_LONG_MAX)
                or right_bounds == (_CQL_LONG_MIN, _CQL_LONG_MAX)
                else (_CQL_INTEGER_MIN, _CQL_INTEGER_MAX)
            )
            return value, bounds
        return None

    evaluated = _eval(expr)
    if evaluated is None:
        return False
    value, (minimum, maximum) = evaluated
    return value < minimum or value > maximum


def _build_resource_id_expr(resource_ref: "SQLExpression") -> "SQLExpression":
    """Build an AST expression for ``resourceType/id`` from a resource column.

    Produces: COALESCE(fhirpath_text(ref, 'resourceType'), '') || '/' ||
              COALESCE(fhirpath_text(ref, 'id'), '')
    """
    return SQLBinaryOp(
        operator="||",
        left=SQLBinaryOp(
            operator="||",
            left=SQLFunctionCall(
                name="COALESCE",
                args=[
                    SQLFunctionCall(name="fhirpath_text", args=[resource_ref, SQLLiteral("resourceType")]),
                    SQLLiteral(""),
                ],
            ),
            right=SQLLiteral("/"),
        ),
        right=SQLFunctionCall(
            name="COALESCE",
            args=[
                SQLFunctionCall(name="fhirpath_text", args=[resource_ref, SQLLiteral("id")]),
                SQLLiteral(""),
            ],
        ),
    )


def _synthesize_target_from_resource_select(
    select: "SQLSelect",
    context: "Optional[SQLTranslationContext]" = None,
) -> "Optional[SQLExpression]":
    """Synthesize a target expression from a correlated subquery to a CTE.

    **Case 0** — Stored target: The CTE has a stored ``audit_target_expr`` from
    First/Last attribution.  Use it directly.

    **Case 1** — ``SELECT sub.resource FROM "CTE" ...``:
    The SELECT retrieves a ``resource`` column directly.

    **Case 2** — ``SELECT sub.value FROM "CTE" ...`` (with context):
    The SELECT retrieves a scalar, but the CTE's FROM source is a RESOURCE_ROWS
    CTE with a ``resource`` column.  Use ``definition_meta.has_resource`` to detect
    this and construct the target from the underlying resource.
    """
    if not select.columns or len(select.columns) != 1:
        return None

    # Case 0: check for stored audit target expression from First/Last attribution
    if context is not None:
        cte_name = _extract_cte_name_from_select(select)
        if cte_name:
            meta = getattr(context, "definition_meta", {}).get(cte_name)
            if meta and getattr(meta, "audit_target_expr", None) is not None:
                return meta.audit_target_expr

    col = select.columns[0]
    if isinstance(col, SQLAlias):
        col = col.expr

    # Case 1: directly selecting 'resource' column
    if isinstance(col, SQLQualifiedIdentifier) and col.parts[-1] == "resource":
        resource_ref = col
    elif isinstance(col, SQLIdentifier) and col.name == "resource":
        resource_ref = col
    else:
        # Case 2: scalar column — check if FROM CTE has resource via context
        resource_sql = _detect_resource_in_from_clause(select, context)
        if resource_sql is None:
            return None
        resource_ref = SQLRaw(resource_sql)

    id_expr = _build_resource_id_expr(resource_ref)
    target_select = SQLSelect(
        columns=[id_expr],
        from_clause=select.from_clause,
        where=select.where,
        order_by=select.order_by,
        limit=select.limit,
    )
    return SQLSubquery(query=target_select)


def _extract_cte_name_from_select(select: "SQLSelect") -> "Optional[str]":
    """Extract the CTE name from a SELECT's FROM clause.

    Returns the unquoted CTE name, or None if the FROM clause is not a simple CTE ref.
    """
    from_clause = select.from_clause
    if isinstance(from_clause, SQLAlias):
        inner = from_clause.expr
    else:
        inner = from_clause
    if inner is None:
        return None
    if isinstance(inner, SQLIdentifier):
        return inner.name
    if isinstance(inner, SQLRaw):
        raw = inner.raw_sql.strip().strip('"')
        return raw
    return None


def _detect_resource_in_from_clause(
    select: "SQLSelect",
    context: "Optional[SQLTranslationContext]" = None,
) -> "Optional[str]":
    """Check if the FROM clause references a CTE with a ``resource`` column.

    Returns a qualified ``alias.resource`` SQL string if the CTE is RESOURCE_ROWS,
    or None otherwise.
    """
    if context is None:
        return None
    from_clause = select.from_clause
    if not isinstance(from_clause, SQLAlias):
        return None
    alias = from_clause.alias
    # Extract CTE name from the FROM expression
    inner = from_clause.expr
    cte_name = None
    if isinstance(inner, SQLIdentifier):
        cte_name = inner.name
    elif isinstance(inner, SQLRaw):
        raw = inner.raw_sql.strip().strip('"')
        cte_name = raw
    if not cte_name:
        return None
    # Look up definition_meta
    meta = getattr(context, "definition_meta", {}).get(cte_name)
    if meta and getattr(meta, "has_resource", False):
        return f'"{alias}".resource' if alias else "resource"
    return None


def _ensure_audit_struct(expr: SQLExpression) -> SQLExpression:
    """Wrap a plain boolean expression in audit_leaf() if not already an audit struct."""
    if isinstance(expr, SQLAuditStruct):
        return expr
    if isinstance(expr, SQLFunctionCall) and expr.name in _AUDIT_MACRO_NAMES:
        return expr
    # Demote any nested audit macros (e.g. audit_not) that appear as SQL
    # AND/OR operands inside the expression.  Temporal operator handlers
    # combine their result with extra conditions via SQL AND, and the extra
    # condition may already be an audit struct (audit_not, audit_leaf, …).
    # Without demoting, audit_leaf(X AND audit_not(Y)) would pass a STRUCT
    # where DuckDB expects BOOLEAN, causing a ConversionException.
    from ...translator.expressions._query import _demote_audit_struct_to_bool
    expr = _demote_audit_struct_to_bool(expr)
    return SQLFunctionCall(name="audit_leaf", args=[expr])
from ...translator.expressions._utils import (
    BINARY_OPERATOR_MAP,
    UNARY_OPERATOR_MAP,
    _coerce_query_rows_to_list,
    _is_fhir_r4_type_name,
    _is_list_returning_sql,
    _contains_sql_subquery,
    _promote_fhirpath_text_list,
    _ensure_scalar_body,
    escape_fhirpath_string_literal,
    _get_qicore_extension_fhirpath,
    _resolve_library_code_constant,
)
from ...errors import TranslationError

if TYPE_CHECKING:
    from ...translator.context import SQLTranslationContext


def _normalize_cql_type_name(cql_type: Optional[str]) -> str:
    if not cql_type:
        return "Any"
    bare = str(cql_type).strip()
    return bare.split(".")[-1] if "." in bare else bare


_CQL_STRING_CONVERSION_TYPES = {
    "Any",
    "Boolean",
    "Integer",
    "Long",
    "Decimal",
    "String",
    "Quantity",
    "Ratio",
    "Date",
    "DateTime",
    "Time",
}


def _static_type_supports_string_conversion(cql_type: Optional[str]) -> bool:
    """Return false for known CQL types outside Appendix B ToString overloads."""
    normalized = _normalize_cql_type_name(cql_type)
    if normalized in _CQL_STRING_CONVERSION_TYPES:
        return True
    if (
        normalized.startswith("List<")
        or normalized.startswith("Interval<")
        or normalized.startswith("Choice<")
        or normalized.startswith("Tuple")
        or normalized in {"Code", "Concept", "ValueSet", "CodeSystem", "Vocabulary"}
    ):
        return False
    return True

logger = logging.getLogger(__name__)

from ...translator.component_codes import get_code_to_column_mapping
from ...translator.fhirpath_builder import (
    build_coding_exists_expr,
    build_multi_coding_exists_expr,
    build_where_return_expr,
    FHIRPathBuilder,
)


def _operand_is_type_specifier(node: Any) -> bool:
    """Phase 3 helper: True when ``node`` is a CQL NamedTypeSpecifier.

    Used by the ``is``-operator branch to distinguish the type-check form
    (``Order is MedicationRequest``) from the code-vs-code subsumption form
    (``Code 'X' from S is Code 'Y' from S``). The type-check form must stay
    routed through the existing type-check translator; the code-vs-code form
    routes through the closure table when loaded.
    """
    return isinstance(node, NamedTypeSpecifier)


def _is_quantity_expression(expr: SQLExpression) -> bool:
    """Check if an SQL expression is likely a Quantity value.

    Detects parse_quantity() calls, quantity UDF results, CASE expressions
    with parse_quantity branches, and expressions annotated with
    result_type="Quantity" (e.g., correlated subqueries
    referencing Quantity-returning definitions).
    """
    if getattr(expr, 'result_type', None) == "Quantity":
        return True
    if isinstance(expr, SQLFunctionCall):
        if (expr.name or "").upper() == "COALESCE":
            return any(_is_quantity_expression(arg) for arg in expr.args)
        _QUANTITY_RETURNING_FUNCS = frozenset({
            "parse_quantity", "ToQuantity", "quantityNegate", "quantityAbs",
            "quantityAdd", "quantity_add", "quantitySubtract", "quantity_subtract",
            "quantityMultiply", "quantityDivide", "quantityTruncatedDivide",
            "quantityModulo", "quantityConvert", "quantity_convert",
        })
        if expr.name in _QUANTITY_RETURNING_FUNCS:
            return True
    if isinstance(expr, SQLCase):
        for _, result in expr.when_clauses:
            if _is_quantity_expression(result):
                return True
        if expr.else_clause and _is_quantity_expression(expr.else_clause):
            return True
    return False


def _ensure_parse_quantity(expr: SQLExpression) -> SQLExpression:
    """Wrap an expression in parse_quantity if it isn't already."""
    if isinstance(expr, SQLFunctionCall) and expr.name == "parse_quantity":
        return expr
    return SQLFunctionCall(name="parse_quantity", args=[expr])


def _quantity_operand_for_arithmetic(expr: SQLExpression, is_quantity: bool) -> SQLExpression:
    """Return a Quantity JSON expression, converting scalar numeric operands to unit '1'."""
    if is_quantity:
        return _ensure_parse_quantity(expr)

    value = expr if isinstance(expr, SQLLiteral) and isinstance(expr.value, (int, float)) and not isinstance(expr.value, bool) else SQLCast(
        expression=expr,
        target_type="DOUBLE",
        try_cast=True,
    )
    json_obj = SQLFunctionCall(
        name="json_object",
        args=[
            SQLLiteral(value="value"), value,
            SQLLiteral(value="unit"), SQLLiteral(value="1"),
            SQLLiteral(value="system"), SQLLiteral(value="http://unitsofmeasure.org"),
        ],
    )
    parsed = SQLFunctionCall(
        name="parse_quantity",
        args=[SQLCast(expression=json_obj, target_type="VARCHAR")],
    )
    return SQLCase(
        when_clauses=[(SQLBinaryOp(operator="IS", left=value, right=SQLNull()), SQLNull())],
        else_clause=parsed,
    )


def _quantity_literal_json(qty: Quantity) -> SQLLiteral:
    """Return raw Quantity JSON while preserving integer vs decimal spelling."""
    return SQLLiteral(
        value=json.dumps(
            {
                "value": qty.value,
                "unit": qty.unit,
                "system": "http://unitsofmeasure.org",
            }
        )
    )


def _is_ratio_expression(expr: SQLExpression) -> bool:
    """Check if an SQL expression is known to produce a CQL Ratio JSON value."""
    if getattr(expr, 'result_type', None) == "Ratio":
        return True
    if isinstance(expr, SQLFunctionCall):
        return expr.name.lower() == "toratio"
    return False


_UNCERTAIN_BETWEEN_UDFS = {
    "cqlDurationBetween",
    "cqlDifferenceBetween",
    "cqlUncertainAdd",
    "cqlUncertainSubtract",
    "cqlUncertainMultiply",
    # CQL §Age/§AgeAt/§CalculateAge/§CalculateAgeAt: age operators are
    # duration calculations and share the §22.21 scalar-or-interval VARCHAR
    # contract, so comparisons/arithmetic on them need the uncertain UDFs.
    "AgeInYears", "AgeInMonths", "AgeInWeeks", "AgeInDays",
    "AgeInHours", "AgeInMinutes", "AgeInSeconds",
    "AgeInYearsAt", "AgeInMonthsAt", "AgeInWeeksAt", "AgeInDaysAt",
    "AgeInHoursAt", "AgeInMinutesAt", "AgeInSecondsAt",
    "CalculateAgeInYears", "CalculateAgeInMonths", "CalculateAgeInWeeks",
    "CalculateAgeInDays", "CalculateAgeInHours", "CalculateAgeInMinutes",
    "CalculateAgeInSeconds",
    "CalculateAgeInYearsAt", "CalculateAgeInMonthsAt", "CalculateAgeInWeeksAt",
    "CalculateAgeInDaysAt", "CalculateAgeInHoursAt", "CalculateAgeInMinutesAt",
    "CalculateAgeInSecondsAt",
}

_CQL_AGE_FUNC_NAMES = {
    "age",
    "ageinyears", "ageinmonths", "ageinweeks", "ageindays",
    "ageinhours", "ageinminutes", "ageinseconds",
    "ageinyearsat", "ageinmonthsat", "ageinweeksat", "ageindaysat",
    "ageinhoursat", "ageinminutesat", "ageinsecondsat",
    "calculateageinyears", "calculateageinmonths", "calculateageinweeks",
    "calculateageindays", "calculateageinhours", "calculateageinminutes",
    "calculateageinseconds",
    "calculateageinyearsat", "calculateageinmonthsat", "calculateageinweeksat",
    "calculateageindaysat", "calculateageinhoursat", "calculateageinminutesat",
    "calculateageinsecondsat",
}


def _uncertain_between_sql_name(expr: SQLExpression) -> Optional[str]:
    while isinstance(expr, SQLCast):
        expr = expr.expression
    if (
        isinstance(expr, SQLFunctionCall)
        and expr.name.upper() in ("TRUNC", "TRUNCATE", "ROUND", "FLOOR", "CEIL", "CEILING", "ABS")
        and expr.args
    ):
        return _uncertain_between_sql_name(expr.args[0])
    if isinstance(expr, SQLFunctionCall) and expr.name in _UNCERTAIN_BETWEEN_UDFS:
        return expr.name
    return None


def _is_uncertain_between_sql(expr: SQLExpression) -> bool:
    return _uncertain_between_sql_name(expr) is not None


def _unwrap_cast(expr: SQLExpression) -> SQLExpression:
    """Strip SQLCast wrappers around an expression."""
    while isinstance(expr, SQLCast):
        expr = expr.expression
    return expr


def _literal_is_null(node: object) -> bool:
    return isinstance(node, Literal) and node.value is None


class OperatorsMixin:
    """Mixin providing binary and unary operator translations."""

    # Comparison operators eligible for audit_comparison wrapping
    _AUDIT_COMPARISON_OPS = frozenset({"=", "!=", "<>", "<", "<=", ">", ">="})

    def _temporal_ast_kind(self, node: object) -> Optional[str]:
        """Return a coarse temporal kind when the CQL AST preserves one."""
        if isinstance(node, TimeLiteral):
            return "time"
        if isinstance(node, DateTimeLiteral):
            return "datetime"
        if isinstance(node, FunctionRef):
            name = node.name.lower()
            if name in {"time", "totime", "timeofday"}:
                return "time"
            if name in {"date", "datetime", "todate", "todatetime", "today", "now"}:
                return "datetime"
        if isinstance(node, Identifier):
            meta = self.context.definition_meta.get(node.name)
            cql_type = (meta.cql_type if meta else "") or ""
            lower_type = cql_type.lower()
            if lower_type == "time":
                return "time"
            if lower_type in {"date", "datetime"}:
                return "datetime"
            ast_defs = getattr(self.context, "_definition_cql_asts", {})
            ast_def = ast_defs.get(node.name)
            if ast_def is not None and ast_def is not node:
                return self._temporal_ast_kind(ast_def)
        if isinstance(node, BinaryExpression) and node.operator == "as":
            target = getattr(node.right, "name", None)
            if isinstance(target, str):
                target_lower = target.lower()
                if target_lower == "time":
                    return "time"
                if target_lower in {"date", "datetime"}:
                    return "datetime"
        return None

    def _temporal_list_ast_kind(self, node: object) -> Optional[str]:
        """Return the temporal kind for a list expression when all values agree."""
        if isinstance(node, ListExpression):
            kinds = [
                self._temporal_ast_kind(element)
                for element in node.elements
                if not _literal_is_null(element)
            ]
            if kinds and all(kind == kinds[0] for kind in kinds):
                return kinds[0]
            return None
        if isinstance(node, Identifier):
            meta = self.context.definition_meta.get(node.name)
            cql_type = (meta.cql_type if meta else "") or ""
            lower_type = cql_type.lower()
            if lower_type in {"list<time>", "list<system.time>"}:
                return "time"
            if lower_type in {
                "list<date>",
                "list<datetime>",
                "list<system.date>",
                "list<system.datetime>",
            }:
                return "datetime"
            ast_defs = getattr(self.context, "_definition_cql_asts", {})
            ast_def = ast_defs.get(node.name)
            if ast_def is not None and ast_def is not node:
                return self._temporal_list_ast_kind(ast_def)
        if isinstance(node, FunctionRef):
            name = node.name.lower()
            if name in {"skip", "take", "tail", "distinct", "sort"} and node.arguments:
                return self._temporal_list_ast_kind(node.arguments[0])
        if isinstance(node, BinaryExpression) and node.operator in ("union", "|"):
            left_kind = self._temporal_list_ast_kind(node.left)
            right_kind = self._temporal_list_ast_kind(node.right)
            return left_kind if left_kind and left_kind == right_kind else None
        return None

    def _use_temporal_list_contains(self, list_ast: object, element_ast: object) -> bool:
        list_kind = self._temporal_list_ast_kind(list_ast)
        elem_kind = self._temporal_ast_kind(element_ast)
        return bool(list_kind and elem_kind and list_kind == elem_kind)

    def _use_temporal_list_list_op(self, left_ast: object, right_ast: object) -> bool:
        left_kind = self._temporal_list_ast_kind(left_ast)
        right_kind = self._temporal_list_ast_kind(right_ast)
        return bool(left_kind and right_kind and left_kind == right_kind)

    def _list_contains_call(
        self,
        list_sql: SQLExpression,
        element_sql: SQLExpression,
        list_ast: object,
        element_ast: object,
    ) -> SQLFunctionCall:
        # In audit_mode='full' (audit_mode + audit_expressions), the
        # `CQLListContainsEq` / `CQLListContainsTemporalEq` SQL macros trigger
        # a DuckDB binder bug ("Need named argument for struct pack") when
        # they appear inside audit_leaf() wrapping inside audit_and/or chains
        # inside correlated EXISTS subqueries. The macros expand to SQL
        # containing EXISTS(SELECT FROM UNNEST...); DuckDB's binder fails to
        # resolve the struct_pack argument shape when that expansion is nested
        # through audit_and/or struct_extract calls.
        #
        # The fix: emit `list_contains(...)` directly (a DuckDB scalar
        # built-in, no macro expansion) whenever audit_mode is active. This
        # preserves correctness for primitive element types (the common case
        # in audit contexts — status, intent, code strings). CQL's complex
        # equality semantics for Code/Quantity list elements (which would
        # require the UNNEST path) are not exercised by audit SQL today; if
        # that changes, the audit pipeline must lift the macro to a pre-compute
        # CTE instead of inlining it into audit_leaf.
        if (
            getattr(self, "context", None) is not None
            and self.context.audit_mode
            and self.context.audit_expressions
        ):
            return SQLFunctionCall(
                name="list_contains",
                args=[list_sql, element_sql],
            )
        name = (
            "CQLListContainsTemporalEq"
            if self._use_temporal_list_contains(list_ast, element_ast)
            else "CQLListContainsEq"
        )
        # CQL-21 HISTORIAN QA-001: uncertainty-capable (§22.21 VARCHAR)
        # elements — the age/duration family — never match the typed
        # CQLListContainsEq macro (INTEGER literals vs VARCHAR interval
        # JSON). For a static literal list, lower to an OR chain of
        # cqlUncertainCompare '=' per CQL In (list) ≡ x = e1 or ... or en,
        # preserving three-valued uncertainty semantics.
        if _is_uncertain_between_sql(element_sql) and isinstance(
            _unwrap_cast(list_sql), SQLArray
        ):
            comparisons: list = []
            for item in _unwrap_cast(list_sql).elements:
                item_sql = item
                if not _is_uncertain_between_sql(item):
                    item_sql = SQLCast(expression=item, target_type="VARCHAR")
                comparisons.append(
                    SQLFunctionCall(
                        name="cqlUncertainCompare",
                        args=[element_sql, item_sql, SQLLiteral(value="=")],
                    )
                )
            result = None
            for comparison in comparisons:
                result = comparison if result is None else SQLBinaryOp(
                    operator="OR", left=result, right=comparison
                )
            if result is not None:
                return result
        # CQL-18 SKEPTIC relaunch QA-002: dynamic multi-valued FHIR properties
        # lower to scalar fhirpath_text (first-node truncation); list
        # operators need the full element list.
        list_sql = _promote_fhirpath_text_list(list_sql)
        return SQLFunctionCall(name=name, args=[list_sql, element_sql])

    def _definitely_null_sql(self, translated: SQLExpression) -> bool:
        if isinstance(translated, SQLNull) or (
            isinstance(translated, SQLLiteral) and translated.value is None
        ):
            return True
        if isinstance(translated, SQLCase):
            if translated.else_clause is None or not self._definitely_null_sql(translated.else_clause):
                return False
            return all(
                self._definitely_null_sql(result)
                for _condition, result in translated.when_clauses
            )
        return False

    def _definitely_null_ast(self, node: object) -> bool:
        if isinstance(node, Literal) and node.value is None:
            return True
        if isinstance(node, BinaryExpression) and node.operator in {"as", "convert"}:
            return self._definitely_null_ast(node.left)
        return False

    def _definitely_null_operand(self, node: object, translated: SQLExpression) -> bool:
        return self._definitely_null_ast(node) or self._definitely_null_sql(translated)

    def _interval_selector_is_untyped_null_interval(self, node: object) -> bool:
        if not isinstance(node, Interval):
            return False
        bounds = [node.low, node.high]
        return all(isinstance(bound, Literal) and bound.value is None for bound in bounds)

    def _null_contains_container_returns_false(self, container_ast: object, element_ast: object) -> bool:
        container_type = self._static_structural_type_name(container_ast)
        if container_type and (
            container_type.startswith("Interval<")
            or container_type.startswith("List<")
        ):
            return True
        # A null container cannot contain a known non-null element, regardless
        # of whether the intended container is a list, interval, or string.
        return True

    def _list_has_all_call(
        self,
        left_sql: SQLExpression,
        right_sql: SQLExpression,
        left_ast: object,
        right_ast: object,
    ) -> SQLFunctionCall:
        name = (
            "CQLListHasAllTemporalEq"
            if self._use_temporal_list_list_op(left_ast, right_ast)
            else "CQLListHasAllEq"
        )
        # CQL-18 SKEPTIC relaunch: promote scalar fhirpath_text operands
        # (first-node truncation) to full list projections (CQL 1.5 §10.x).
        left_sql = _promote_fhirpath_text_list(left_sql)
        right_sql = _promote_fhirpath_text_list(right_sql)
        return SQLFunctionCall(name=name, args=[left_sql, right_sql])

    def _list_except_call(
        self,
        left_sql: SQLExpression,
        right_sql: SQLExpression,
        left_ast: object,
        right_ast: object,
    ) -> SQLFunctionCall:
        name = (
            "CQLListExceptTemporalEq"
            if self._use_temporal_list_list_op(left_ast, right_ast)
            else "CQLListExceptEq"
        )
        # CQL-18 SKEPTIC relaunch: promote scalar fhirpath_text operands
        # (first-node truncation) to full list projections (CQL 1.5 §10.x).
        left_sql = _promote_fhirpath_text_list(left_sql)
        right_sql = _promote_fhirpath_text_list(right_sql)
        return SQLFunctionCall(name=name, args=[left_sql, right_sql])

    def _list_intersect_call(
        self,
        left_sql: SQLExpression,
        right_sql: SQLExpression,
        left_ast: object,
        right_ast: object,
    ) -> SQLFunctionCall:
        name = (
            "CQLListIntersectTemporalEq"
            if self._use_temporal_list_list_op(left_ast, right_ast)
            else "CQLListIntersectEq"
        )
        # CQL-18 SKEPTIC relaunch: promote scalar fhirpath_text operands
        # (first-node truncation) to full list projections (CQL 1.5 §10.x).
        left_sql = _promote_fhirpath_text_list(left_sql)
        right_sql = _promote_fhirpath_text_list(right_sql)
        return SQLFunctionCall(name=name, args=[left_sql, right_sql])

    def _list_index_of_call(
        self,
        list_sql: SQLExpression,
        element_sql: SQLExpression,
        list_ast: object,
        element_ast: object,
    ) -> SQLFunctionCall:
        name = (
            "CQLIndexOfTemporal"
            if self._use_temporal_list_contains(list_ast, element_ast)
            else "CQLIndexOf"
        )
        # CQL-18 SKEPTIC relaunch: promote scalar fhirpath_text list operand.
        list_sql = _promote_fhirpath_text_list(list_sql)
        return SQLFunctionCall(name=name, args=[list_sql, element_sql])

    def _quantity_interval_point_arg(self, point: SQLExpression) -> SQLExpression:
        """Preserve FHIR Quantity shape for Quantity interval membership."""
        candidate = point.expression if isinstance(point, SQLCast) else point
        if (
            isinstance(candidate, SQLFunctionCall)
            and candidate.name == "fhirpath_number"
            and len(candidate.args) == 2
            and isinstance(candidate.args[1], SQLLiteral)
            and isinstance(candidate.args[1].value, str)
        ):
            path = candidate.args[1].value
            if path.endswith(".valueQuantity.value"):
                return SQLFunctionCall(
                    name="fhirpath_text",
                    args=[
                        candidate.args[0],
                        SQLLiteral(value=path[: -len(".value")]),
                    ],
                )
        return self._ensure_interval_varchar(point)

    @staticmethod
    def _is_quantity_interval_sql(interval: SQLExpression) -> bool:
        candidate = interval.expression if isinstance(interval, SQLCast) else interval
        if isinstance(candidate, SQLInterval):
            bounds = [candidate.low, candidate.high]
        elif isinstance(candidate, SQLFunctionCall) and candidate.name == "intervalFromBounds":
            bounds = list(candidate.args[:2])
        else:
            return False
        for bound in bounds:
            bound_candidate = bound.expression if isinstance(bound, SQLCast) else bound
            if _is_quantity_expression(bound_candidate):
                return True
        return False

    def _list_equal_call(
        self,
        left_sql: SQLExpression,
        right_sql: SQLExpression,
        left_ast: object,
        right_ast: object,
    ) -> SQLFunctionCall:
        name = (
            "CQLListEqualTemporalEq"
            if self._use_temporal_list_list_op(left_ast, right_ast)
            else "CQLListEqualEq"
        )
        # CQL-18 SKEPTIC relaunch: promote scalar fhirpath_text operands
        # (first-node truncation) to full list projections (CQL 1.5 §10.x).
        left_sql = _promote_fhirpath_text_list(left_sql)
        right_sql = _promote_fhirpath_text_list(right_sql)
        return SQLFunctionCall(name=name, args=[left_sql, right_sql])

    def _infer_static_cql_type_for_logical_operand(self, operand: object) -> str:
        if isinstance(operand, Literal):
            if operand.value is None:
                return "Any"
            literal_type = getattr(operand, "type", None)
            if literal_type:
                return literal_type
            if isinstance(operand.value, bool):
                return "Boolean"
            if isinstance(operand.value, int):
                return "Integer"
            if isinstance(operand.value, float):
                return "Decimal"
            if isinstance(operand.value, str):
                return "String"
            return "Any"
        if isinstance(operand, CodeSelector):
            return "Code"
        if isinstance(operand, InstanceExpression):
            type_name = getattr(operand, "type", "")
            bare = type_name.split(".")[-1] if "." in type_name else type_name
            if bare in {"Code", "Concept", "ValueSet", "CodeSystem", "Vocabulary"}:
                return bare
            return type_name or "Any"
        if isinstance(operand, Quantity):
            return "Quantity"
        if isinstance(operand, DateTimeLiteral):
            value = str(getattr(operand, "value", "") or "")
            if value.startswith("T"):
                return "Time"
            return "DateTime" if "T" in value else "Date"
        if isinstance(operand, TimeLiteral):
            return "Time"
        if isinstance(operand, Interval):
            return "Interval<Any>"
        if isinstance(operand, TupleExpression):
            return "Tuple"
        if isinstance(operand, ListExpression):
            return "List<Any>"
        if isinstance(operand, ExistsExpression):
            return "Boolean"
        if isinstance(operand, Identifier):
            meta = self.context.definition_meta.get(operand.name)
            if meta:
                return meta.cql_type
            param_info = self.context.parameters.get(operand.name)
            if param_info and getattr(param_info, "cql_type", None):
                return str(param_info.cql_type)
            ast_defs = getattr(self.context, "_definition_cql_asts", {})
            ast_def = ast_defs.get(operand.name)
            if ast_def is not None and ast_def is not operand:
                return self._infer_static_cql_type_for_logical_operand(ast_def)
            return "Any"
        if isinstance(operand, FunctionRef):
            function_return_types = {
                "toboolean": "Boolean",
                "convertstoboolean": "Boolean",
                "convertstodate": "Boolean",
                "convertstodatetime": "Boolean",
                "convertstodecimal": "Boolean",
                "convertstointeger": "Boolean",
                "convertstolong": "Boolean",
                "convertstoquantity": "Boolean",
                "convertstoratio": "Boolean",
                "convertstostring": "Boolean",
                "convertstotime": "Boolean",
                "istrue": "Boolean",
                "isfalse": "Boolean",
                "alltrue": "Boolean",
                "anytrue": "Boolean",
                "allfalse": "Boolean",
                "anyfalse": "Boolean",
                "tostring": "String",
                "tointeger": "Integer",
                "tolong": "Long",
                "todecimal": "Decimal",
                "todate": "Date",
                "todatetime": "DateTime",
                "totime": "Time",
                "toquantity": "Quantity",
                "toratio": "Ratio",
                "toconcept": "Concept",
                "date": "Date",
                "datetime": "DateTime",
                "time": "Time",
                "now": "DateTime",
                "timeofday": "Time",
                "today": "Date",
            }
            if operand.name.lower() == "coalesce":
                # CQL 1.5 §Coalesce: the return type is the common type of
                # the arguments, i.e. the first non-null argument's type.
                # Infer from the first statically-known non-Any argument so
                # nested Coalesce calls propagate their static type to the
                # enclosing type-family guard (e.g. Coalesce(1,
                # Coalesce(null, 'a')) must be rejected at translation, not
                # leak a DuckDB binder error at execution).
                for arg in getattr(operand, "arguments", []):
                    arg_type = self._infer_static_cql_type_for_logical_operand(arg)
                    if arg_type and arg_type != "Any":
                        return arg_type
                return "Any"
            return function_return_types.get(operand.name.lower(), "Any")
        if isinstance(operand, BinaryExpression):
            op = operand.operator.lower() if isinstance(operand.operator, str) else operand.operator
            if op == "as":
                target = getattr(operand.right, "name", None)
                if _normalize_cql_type_name(target) == "Any":
                    return self._infer_static_cql_type_for_logical_operand(operand.left)
                return target or "Any"
            if op == "convert":
                target = getattr(operand.right, "name", None)
                if _normalize_cql_type_name(target) == "Any":
                    return self._infer_static_cql_type_for_logical_operand(operand.left)
                return target or "Any"
            if op in {
                "=", "!=", "<>", "<", ">", "<=", ">=",
                "and", "or", "xor", "implies",
                "on or before", "on or after", "before", "after",
                "starts", "ends", "during", "overlaps", "in",
                "~", "!~", "equivalent", "not equivalent",
                "same or before", "same or after",
                "includes", "included in",
                "properly includes", "properly included in",
                "meets", "meets before", "meets after",
                "contains", "is",
            } or (isinstance(op, str) and op.startswith("same ")):
                return "Boolean"
            # CQL-04 HISTORIAN QA-001: binary arithmetic operators
            # (+,-,*,/,div,mod,^) yield Integer/Long/Decimal/Quantity (or
            # Date/DateTime/Time for +/-). Mirror inference.py:1306-1333 so
            # that arithmetic expressions used as logical operands do not
            # bypass _validate_boolean_operand via the fall-through path
            # (which returns "Any" when _infer_cql_type is unavailable on
            # the ExpressionTranslator mixin stack). Without this, expressions
            # such as `1 + 1 and true` translated to raw SQL `1 + 1 AND TRUE`,
            # inheriting DuckDB numeric truthiness.
            if op in ("+", "-"):
                left_type = self._infer_static_cql_type_for_logical_operand(operand.left)
                right_type = self._infer_static_cql_type_for_logical_operand(operand.right)
                if left_type in ("Date", "DateTime", "Time"):
                    return left_type
                if right_type in ("Date", "DateTime", "Time"):
                    return right_type
                if left_type == "Quantity" or right_type == "Quantity":
                    return "Quantity"
                if "Decimal" in (left_type, right_type):
                    return "Decimal"
                if "Long" in (left_type, right_type):
                    return "Long"
                if "Integer" in (left_type, right_type):
                    return "Integer"
                return "Any"
            if op in ("*", "/", "div", "mod", "^"):
                left_type = self._infer_static_cql_type_for_logical_operand(operand.left)
                right_type = self._infer_static_cql_type_for_logical_operand(operand.right)
                if left_type == "Quantity" or right_type == "Quantity":
                    return "Quantity"
                if "Decimal" in (left_type, right_type) or op == "/":
                    return "Decimal"
                if "Long" in (left_type, right_type):
                    return "Long"
                if "Integer" in (left_type, right_type):
                    return "Integer"
                return "Any"
        if isinstance(operand, UnaryExpression):
            op = operand.operator.lower() if isinstance(operand.operator, str) else operand.operator
            if op in {"not", "is null", "is not null", "is true", "is false", "exists"}:
                return "Boolean"
            # CQL-04 SKEPTIC QA-001: unary +/-/predecessor of/successor of
            # preserve the operand's static type. Mirror inference.py:1378-1379
            # so that logical-operand validation does not bypass non-Boolean
            # numeric/quantity operands via the fall-through path (which
            # returns "Any" when _infer_cql_type is unavailable on the
            # ExpressionTranslator mixin stack). Without this, expressions
            # such as `-1 and true` translated to raw SQL `-1 AND TRUE`,
            # inheriting DuckDB numeric truthiness.
            if op in {"+", "-", "predecessor of", "successor of"}:
                return self._infer_static_cql_type_for_logical_operand(operand.operand)
        infer = getattr(self, "_infer_cql_type", None)
        return infer(operand) if infer else "Any"

    def _validate_boolean_operand(self, operand: object, operator: str) -> None:
        """Reject statically known non-Boolean operands for CQL logical operators."""
        inferred = self._infer_static_cql_type_for_logical_operand(operand)
        normalized = _normalize_cql_type_name(inferred)
        if normalized in ("Any", "Boolean"):
            return
        if normalized.startswith("Choice<") and "Boolean" in normalized:
            return
        raise TranslationError(
            f"CQL logical operator '{operator}' requires Boolean operands; "
            f"got {inferred}"
        )

    def _is_static_string_operand(self, operand: object) -> bool:
        """Return true when a statically known operand is String-compatible."""
        if isinstance(operand, Literal) and operand.value is None:
            return True
        inferred = self._infer_static_cql_type_for_logical_operand(operand)
        normalized = _normalize_cql_type_name(inferred)
        if normalized in ("Any", "String"):
            return True
        if normalized.startswith("Choice<") and "String" in normalized:
            return True
        return False

    def _validate_static_string_operand(self, operand: object, operator: str) -> None:
        """Reject statically known non-String operands for CQL string operators."""
        if self._is_static_string_operand(operand):
            return
        inferred = self._infer_static_cql_type_for_logical_operand(operand)
        raise TranslationError(
            f"CQL string operator '{operator}' requires String operands; got {inferred}"
        )

    def _validate_static_string_list_operand(self, operand: object, operator: str) -> None:
        """Reject statically known non-List<String> operands for CQL Combine."""
        if isinstance(operand, Literal) and operand.value is None:
            return
        if isinstance(operand, ListExpression):
            for element in operand.elements:
                self._validate_static_string_operand(element, operator)
            return
        if isinstance(operand, BinaryExpression) and operand.operator == "as":
            target = getattr(operand, "right", None)
            target_text = str(target)
            if "List" in target_text and "String" not in target_text and "Any" not in target_text:
                raise TranslationError(
                    f"CQL string operator '{operator}' requires List<String> source; got {target_text}"
                )
            source = getattr(operand, "left", None)
            if isinstance(source, ListExpression):
                self._validate_static_string_list_operand(source, operator)
            return
        inferred = self._infer_static_cql_type_for_logical_operand(operand)
        normalized = _normalize_cql_type_name(inferred)
        if normalized in ("Any", "List<Any>"):
            return
        if normalized.startswith("List<") and ("String" in normalized or "Any" in normalized):
            return
        raise TranslationError(
            f"CQL string operator '{operator}' requires List<String> source; got {inferred}"
        )

    def _is_known_named_type_target(self, type_name: str) -> bool:
        bare = type_name.split(".")[-1] if "." in type_name else type_name
        known = {
            "Any", "Boolean", "Integer", "Long", "Decimal", "String",
            "Date", "DateTime", "Time", "Quantity", "Ratio",
            "Code", "Concept", "ValueSet", "CodeSystem", "Vocabulary",
            "Period", "Range", "Timing",
        }
        if bare in known or bare.lower() in {item.lower() for item in known}:
            return True
        if _is_fhir_r4_type_name(bare):
            return True
        registry = getattr(self.context, "profile_registry", None)
        if registry is not None:
            if registry.get_negation_info(type_name) is not None:
                return True
            if registry.resolve_named_profile(type_name) is not None:
                return True
        fhir_schema = getattr(self.context, "fhir_schema", None)
        if fhir_schema is not None:
            if bare in getattr(fhir_schema, "resources", {}):
                return True
            base_path = getattr(fhir_schema, "_base_path", None)
            if base_path is not None and (base_path / f"{bare}.json").exists():
                return True
        return False

    def _ensure_known_named_type_target(self, type_name: str, operator: str) -> None:
        if not self._is_known_named_type_target(type_name):
            raise TranslationError(
                f"CQL type operator '{operator}' references unknown type '{type_name}'"
            )

    def _is_cql_conversion_unit_target(self, type_name: str) -> bool:
        return type_name.lower() in {
            "year", "years", "month", "months", "week", "weeks", "day", "days",
            "hour", "hours", "minute", "minutes", "second", "seconds",
            "millisecond", "milliseconds",
        }

    def _extract_fhirpath_from_sql(self, expr: "SQLExpression") -> "Optional[str]":
        """Extract FHIRPath string from fhirpath_* UDF calls in a SQL expression tree."""
        from ...translator.types import SQLFunctionCall, SQLLiteral, SQLCast, SQLCase
        _FHIRPATH_UDFS = ('fhirpath_text', 'fhirpath_number', 'fhirpath_date',
                          'fhirpath_scalar', 'fhirpath_bool')
        if isinstance(expr, SQLFunctionCall):
            if expr.name in _FHIRPATH_UDFS and len(expr.args) >= 2:
                arg = expr.args[1]
                if isinstance(arg, SQLLiteral) and isinstance(arg.value, str):
                    return arg.value
        if isinstance(expr, SQLCast):
            return self._extract_fhirpath_from_sql(expr.expression)
        if isinstance(expr, SQLCase):
            for _, then_expr in (expr.when_clauses or []):
                path = self._extract_fhirpath_from_sql(then_expr)
                if path:
                    return path
            if expr.else_clause:
                return self._extract_fhirpath_from_sql(expr.else_clause)
        return None

    def _extract_scalar_def_name_from_sql(self, expr: "SQLExpression") -> "Optional[str]":
        """Extract a scalar CQL definition name from a correlated subquery expression.

        When a comparison like ``"Lowest Diastolic Reading" < 90`` is translated,
        the LHS becomes a correlated subquery
        ``(SELECT sub.value FROM "Lowest Diastolic Reading" AS sub WHERE ...)``.
        This helper walks the AST to extract the definition name from the FROM clause.
        """
        from ...translator.types import SQLSubquery, SQLSelect, SQLIdentifier, SQLQualifiedIdentifier

        def _walk(node: "SQLExpression") -> "Optional[str]":
            if isinstance(node, SQLSubquery):
                return _walk(node.query)
            if isinstance(node, SQLSelect) and node.from_clause:
                fc = node.from_clause
                if isinstance(fc, SQLIdentifier):
                    return fc.name
                if isinstance(fc, SQLQualifiedIdentifier) and fc.parts:
                    return fc.parts[0]
                return _walk(fc)
            return None

        try:
            return _walk(expr)
        except (AttributeError, TypeError, RecursionError) as e:
            logger.debug(
                "Failed to extract CTE name from %s: %s",
                type(expr).__name__, e,
            )
            return None

    def _maybe_wrap_audit_comparison(
        self, result_expr: "SQLExpression", operator: str,
        left_sql: "SQLExpression", right_sql: "SQLExpression",
    ) -> "SQLExpression":
        """Wrap a comparison in audit_comparison() when audit_mode is enabled."""
        if not self.context.audit_mode or not self.context.audit_expressions or operator not in self._AUDIT_COMPARISON_OPS:
            return result_expr
        from ...translator.types import SQLFunctionCall, SQLLiteral, SQLNull, SQLCast

        # Extract FHIRPath from either operand; fall back to scalar definition name
        path = (
            self._extract_fhirpath_from_sql(left_sql)
            or self._extract_fhirpath_from_sql(right_sql)
            or self._extract_scalar_def_name_from_sql(left_sql)
            or self._extract_scalar_def_name_from_sql(right_sql)
        )
        path_expr: SQLExpression = SQLLiteral(path) if path else SQLCast(expression=SQLNull(), target_type="VARCHAR")

        # Extract audit target (winner resource ID) from operands if available.
        # First/Last/Min/Max attach _audit_target on the returned SQLExpression.
        target_expr: SQLExpression = SQLCast(expression=SQLNull(), target_type="VARCHAR")
        target = _extract_audit_target(left_sql, self.context) or _extract_audit_target(right_sql, self.context)
        if target is not None:
            target_expr = target

        return SQLFunctionCall(
            name="audit_comparison",
            args=[result_expr, SQLLiteral(operator), left_sql, right_sql, path_expr, target_expr],
        )

    def _is_temporal_cql_expr(self, node, _depth: int = 0) -> bool:
        """Check if a CQL AST node evaluates to a DateTime, Date, or Time type.

        CQL §12.3: Date, DateTime, and Time comparison uses precision-aware
        semantics. This helper detects temporal expressions so that <, <=, >,
        >= operators route through precision-aware UDFs.
        """
        if _depth > 4:
            return False
        if isinstance(node, DateTimeLiteral):
            return True
        if isinstance(node, FunctionRef) and node.name.lower() in (
            "datetime", "date", "time", "todatetime", "todate", "totime",
            "today", "now", "timeofday",
        ):
            return True
        # Arithmetic on DateTime: DateTime + Quantity → DateTime
        if isinstance(node, BinaryExpression) and node.operator in ("+", "-"):
            if self._is_temporal_cql_expr(node.left, _depth + 1):
                return True
        # Property of a temporal expression (e.g., x.period.start)
        if isinstance(node, Identifier):
            meta = self.context.definition_meta.get(node.name)
            if meta and meta.sql_result_type in ("DateTime", "Date", "Time", "TIMESTAMP", "DATE"):
                return True
        return False

    def _is_timeofday_cql_expr(self, node) -> bool:
        return isinstance(node, FunctionRef) and node.name.lower() == "timeofday"

    def _is_definitely_non_temporal_quantity_peer(
        self,
        node,
        sql_expr: "SQLExpression",
    ) -> bool:
        """Return true for operands that cannot be Date/DateTime/Time.

        Date/Time plus a time-valued Quantity is valid CQL, and query/aggregate
        temporals can be difficult to infer statically.  Only reject the cases
        that are definitely scalar non-temporal values, such as Quantity + 2.
        """
        if self._is_temporal_cql_expr(node):
            return False
        if isinstance(node, Literal):
            return True
        if isinstance(sql_expr, SQLLiteral) and not isinstance(sql_expr.value, str):
            return True
        if isinstance(sql_expr, SQLCast) and sql_expr.target_type in (
            "INTEGER", "DOUBLE", "BIGINT", "FLOAT", "DECIMAL", "BOOLEAN",
        ):
            return True
        return False

    def _is_uncertain_between_expr(self, node, _depth: int = 0) -> bool:
        """Check if a CQL AST node may return scalar-or-interval VARCHAR.

        CQL §22.21: DurationBetween may return uncertainty intervals (VARCHAR
        from cqlDurationBetween UDF), and DifferenceBetween uses the same
        public SQL shape for parity. Arithmetic and comparison on these
        expressions need uncertainty-aware UDFs.
        """
        if _depth > 4:
            return False
        if isinstance(node, (DurationBetween, DifferenceBetween)):
            return True
        # CQL §Age family: age operators are duration calculations with the
        # same scalar-or-interval VARCHAR shape.
        if isinstance(node, FunctionRef) and node.name.lower() in _CQL_AGE_FUNC_NAMES:
            return True
        # Arithmetic on duration results propagates uncertainty
        if isinstance(node, BinaryExpression) and node.operator in ("+", "-", "*"):
            return (self._is_uncertain_between_expr(node.left, _depth + 1) or
                    self._is_uncertain_between_expr(node.right, _depth + 1))
        return False

    @staticmethod
    def _static_temporal_precision_info(node) -> Optional[tuple[int, bool]]:
        """Return (precision_rank, is_date_only) for static temporal operands."""
        rank_by_count = {
            1: 1,  # year
            2: 2,  # month
            3: 3,  # day
            4: 4,  # hour
            5: 5,  # minute
            6: 6,  # second
            7: 7,  # millisecond
        }
        if isinstance(node, FunctionRef):
            name = node.name.lower()
            if name in {"date", "datetime"}:
                component_count = min(len(node.arguments), 7)
                if component_count < 1:
                    return None
                if not all(
                    isinstance(arg, Literal) and isinstance(arg.value, (int, float)) and not isinstance(arg.value, bool)
                    for arg in node.arguments[:component_count]
                ):
                    return None
                return rank_by_count.get(component_count), name == "date"
            if name == "time":
                component_count = min(len(node.arguments), 4)
                if component_count < 1:
                    return None
                if not all(
                    isinstance(arg, Literal) and isinstance(arg.value, (int, float)) and not isinstance(arg.value, bool)
                    for arg in node.arguments[:component_count]
                ):
                    return None
                return rank_by_count.get(component_count + 3), False
        if isinstance(node, DateTimeLiteral):
            text = node.value
            if text.startswith("T"):
                time_text = text[1:].rstrip("Z")
                if "." in time_text:
                    return 7, False
                colons = time_text.count(":")
                return {0: 4, 1: 5, 2: 6}.get(colons), False
            date_text, _, time_text = text.partition("T")
            if time_text:
                time_body = time_text.rstrip("Z")
                if "." in time_body:
                    return 7, False
                colons = time_body.count(":")
                return {0: 4, 1: 5, 2: 6}.get(colons), False
            if date_text.count("-") == 0:
                return 1, True
            if date_text.count("-") == 1:
                return 2, True
            return 3, True
        if isinstance(node, TimeLiteral):
            text = node.value[1:] if node.value.startswith("T") else node.value
            if "." in text:
                return 7, False
            colons = text.count(":")
            return {0: 4, 1: 5, 2: 6}.get(colons), False
        return None

    def _is_definite_uncertainty_interval_expr(self, node, _depth: int = 0) -> bool:
        """Return true when static duration/difference math is known interval-valued."""
        if _depth > 4:
            return False
        if isinstance(node, BinaryExpression) and node.operator in {"+", "-", "*"}:
            return (
                self._is_definite_uncertainty_interval_expr(node.left, _depth + 1)
                or self._is_definite_uncertainty_interval_expr(node.right, _depth + 1)
            )
        if not isinstance(node, (DurationBetween, DifferenceBetween)):
            return False

        unit = node.precision.lower().rstrip("s")
        if unit == "week":
            unit = "day"
        unit_rank = {
            "year": 1,
            "month": 2,
            "day": 3,
            "hour": 4,
            "minute": 5,
            "second": 6,
            "millisecond": 7,
        }.get(unit)
        if unit_rank is None:
            return False
        left_info = self._static_temporal_precision_info(node.operand_left)
        right_info = self._static_temporal_precision_info(node.operand_right)
        if left_info is None or right_info is None:
            return False
        left_rank, left_date_only = left_info
        right_rank, right_date_only = right_info
        if isinstance(node, DifferenceBetween):
            return not (left_rank >= unit_rank and right_rank >= unit_rank)

        date_unit = unit in {"year", "month", "day"}
        date_fully_specified = (
            date_unit
            and left_date_only
            and right_date_only
            and left_rank == 3
            and right_rank == 3
        )
        if date_fully_specified:
            return False
        if date_unit:
            return not (left_rank > unit_rank and right_rank > unit_rank)
        return not (left_rank >= unit_rank and right_rank >= unit_rank)

    def _is_duration_between_expr(self, node, _depth: int = 0) -> bool:
        """Backward-compatible alias for duration/difference uncertainty checks."""
        return self._is_uncertain_between_expr(node, _depth)

    def _is_cql_quantity_expr(self, node, _depth: int = 0) -> bool:
        """Check if a CQL AST node is expected to evaluate to a Quantity.

        Uses CQL-level type information (Quantity literals, ``as Quantity``
        casts, definition metadata, quantity_fields, and function body
        analysis) to detect Quantity expressions that the SQL-level helper
        might miss.
        """
        if _depth > 6:
            return False
        static_type = self._static_structural_type_name(node)
        if self._bare_cql_type_name(static_type) == "Quantity":
            return True
        if isinstance(node, Quantity):
            return True
        # CQL-03 QA-004: Ratio component accessors (.numerator/.denominator)
        # yield Quantity values and must participate in Quantity arithmetic.
        if isinstance(node, Property) and getattr(node, "path", None) in ("numerator", "denominator"):
            if self._static_source_cql_type(getattr(node, "source", None)) == "Ratio":
                return True
        if isinstance(node, UnaryExpression):
            op = node.operator.lower() if isinstance(node.operator, str) else node.operator
            if op == "singleton from":
                operand = node.operand
                if isinstance(operand, ListExpression):
                    return any(
                        self._is_cql_quantity_expr(element, _depth + 1)
                        for element in operand.elements
                    )
                return self._is_cql_quantity_expr(operand, _depth + 1)
        if isinstance(node, ListExpression):
            return False
        if isinstance(node, Query):
            sources = node.source if isinstance(node.source, list) else [node.source]
            if node.return_clause and getattr(node.return_clause, "expression", None) is not None:
                returned = node.return_clause.expression
                if isinstance(returned, Identifier):
                    for source in sources:
                        if isinstance(source, QuerySource) and source.alias == returned.name:
                            return self._is_cql_quantity_expr(source.expression, _depth + 1)
                return self._is_cql_quantity_expr(returned, _depth + 1)
            return any(
                isinstance(source, QuerySource)
                and self._is_cql_quantity_expr(source.expression, _depth + 1)
                for source in sources
            )
        # "as Quantity" cast
        if isinstance(node, BinaryExpression) and node.operator == "as":
            ts = node.right
            if isinstance(ts, NamedTypeSpecifier) and getattr(ts, "name", "") == "Quantity":
                return True
            if isinstance(ts, Identifier) and ts.name == "Quantity":
                return True
        if isinstance(node, BinaryExpression) and node.operator == "convert":
            ts = node.right
            target_name = None
            if isinstance(ts, NamedTypeSpecifier):
                target_name = getattr(ts, "name", None)
            elif isinstance(ts, Identifier):
                target_name = getattr(ts, "name", None)
            if target_name:
                bare_target = target_name.split(".")[-1]
                if bare_target == "Quantity":
                    return True
                if bare_target == "Any":
                    return self._is_cql_quantity_expr(node.left, _depth + 1)
        # Arithmetic on Quantity: for +/- both operands must be Quantity
        # (DateTime + Quantity → DateTime, not Quantity per CQL §16.2).
        # For */ a single Quantity operand preserves Quantity type.
        if isinstance(node, BinaryExpression) and node.operator in ("+", "-"):
            if (self._is_cql_quantity_expr(node.left, _depth + 1)
                    and self._is_cql_quantity_expr(node.right, _depth + 1)):
                return True
        if isinstance(node, BinaryExpression) and node.operator in ("*", "/"):
            if self._is_cql_quantity_expr(node.left, _depth + 1):
                return True
            if self._is_cql_quantity_expr(node.right, _depth + 1):
                return True
        # Identifier referencing a definition whose result type is Quantity
        if isinstance(node, Identifier):
            meta = self.context.definition_meta.get(node.name)
            if meta and meta.sql_result_type == "Quantity":
                return True
            if meta and self._bare_cql_type_name(meta.cql_type) == "Quantity":
                return True
        # FunctionRef: check built-in aggregates and user-defined functions
        if isinstance(node, FunctionRef):
            if node.name.lower() == "coalesce":
                return any(self._is_cql_quantity_expr(arg, _depth + 1) for arg in (node.arguments or []))
            # Built-in aggregates (Max, Min, Sum) preserve the element type
            if node.name in ("Max", "Min", "Sum", "Avg"):
                for arg in (node.arguments or []):
                    if self._is_cql_quantity_expr(arg, _depth + 1):
                        return True
            # User-defined function: check its body
            func_info = self.context.get_function(node.name)
            if func_info and func_info.expression:
                return self._is_cql_quantity_expr(func_info.expression, _depth + 1)
        # Property access on a definition or query source — check quantity_fields
        if isinstance(node, Property):
            path = node.path if hasattr(node, "path") else ""
            if node.source and path:
                # Check if the source is a definition with quantity_fields
                src_name = getattr(node.source, "name", None)
                if src_name:
                    meta = self.context.definition_meta.get(src_name)
                    if meta and meta.quantity_fields and path in meta.quantity_fields:
                        return True
                # Walk through Query sources to find the underlying definition
                def _find_definition_names(q, depth=0):
                    """Recursively find definition Identifiers in nested Queries."""
                    if depth > 4:
                        return
                    if isinstance(q, Identifier):
                        yield q.name
                        return
                    if isinstance(q, Query):
                        sources = q.source if isinstance(q.source, list) else [q.source]
                        for qs in sources:
                            if qs and hasattr(qs, "expression"):
                                yield from _find_definition_names(qs.expression, depth + 1)

                if isinstance(node.source, Query):
                    for def_name in _find_definition_names(node.source):
                        meta = self.context.definition_meta.get(def_name)
                        if meta and meta.quantity_fields and path in meta.quantity_fields:
                            return True
            # .value on a resource alias — recurse into source
            if path in ("value",) and node.source:
                if self._is_cql_quantity_expr(node.source, _depth + 1):
                    return False
                return self._is_cql_quantity_expr(node.source, _depth + 1)
        return False

    def _might_be_quantity_comparison(self, expr: BinaryExpression) -> bool:
        """Check if a comparison *might* involve Quantity values.

        Returns True when neither side was positively identified as Quantity
        but the CQL AST pattern suggests it could be (e.g. ``.value``
        property on a resource alias, or an opaque function call returning
        an unknown type).  The caller should use a safe COALESCE pattern.
        """
        def _has_value_property(node) -> bool:
            return isinstance(node, Property) and getattr(node, "path", "") == "value"

        left, right = expr.left, expr.right
        # Trigger when one side is .value and the other is non-trivial,
        # or when both sides involve opaque function calls.
        if _has_value_property(left) and not isinstance(right, (Literal, ListExpression)):
            return True
        if _has_value_property(right) and not isinstance(left, (Literal, ListExpression)):
            return True
        if isinstance(left, FunctionRef) and isinstance(right, FunctionRef):
            return True
        return False

    def _is_cql_ratio_expr(self, node, _depth: int = 0) -> bool:
        """Check if a CQL AST node is expected to evaluate to a Ratio."""
        if _depth > 6:
            return False
        static_type = self._static_structural_type_name(node)
        if self._bare_cql_type_name(static_type) == "Ratio":
            return True
        if isinstance(node, UnaryExpression):
            op = node.operator.lower() if isinstance(node.operator, str) else node.operator
            if op == "singleton from":
                return self._is_cql_ratio_expr(node.operand, _depth + 1)
        if isinstance(node, ListExpression):
            return any(self._is_cql_ratio_expr(element, _depth + 1) for element in node.elements)
        if isinstance(node, FunctionRef) and node.name.lower() == "toratio":
            return True
        if isinstance(node, BinaryExpression) and node.operator in ("as", "convert"):
            target = node.right
            target_name = None
            if isinstance(target, NamedTypeSpecifier):
                target_name = getattr(target, "name", None)
            elif isinstance(target, Identifier):
                target_name = getattr(target, "name", None)
            if target_name:
                bare_target = target_name.split(".")[-1]
                if bare_target == "Ratio":
                    return True
                if bare_target == "Any":
                    return self._is_cql_ratio_expr(node.left, _depth + 1)
        if isinstance(node, Identifier):
            meta = self.context.definition_meta.get(node.name)
            if meta and (
                getattr(meta, "sql_result_type", None) == "Ratio"
                or self._bare_cql_type_name(getattr(meta, "cql_type", None)) == "Ratio"
            ):
                return True
            ast_defs = getattr(self.context, "_definition_cql_asts", {})
            ast_def = ast_defs.get(node.name)
            if ast_def is not None and ast_def is not node:
                return self._is_cql_ratio_expr(ast_def, _depth + 1)
        return False

    def _is_unsupported_ordered_comparison_operand(
        self,
        node,
        sql_expr: SQLExpression,
    ) -> bool:
        """Return true for operands outside CQL's ordered comparison overloads."""
        if _is_ratio_expression(sql_expr) or self._is_cql_ratio_expr(node):
            return True
        if self._is_fhir_interval_expression(sql_expr):
            return True

        static_type = self._static_structural_type_name(node)
        if not static_type:
            return False
        bare_type = self._bare_cql_type_name(static_type) or static_type
        if bare_type in {
            "Ratio",
            "Code",
            "Concept",
            "Vocabulary",
            "ValueSet",
            "CodeSystem",
        }:
            return True
        return (
            static_type.startswith("List<")
            or static_type.startswith("Tuple ")
            or static_type.startswith("Interval<")
        )

    @staticmethod
    def _between_null_guard(*args: SQLExpression) -> SQLExpression:
        checks = [
            SQLUnaryOp(operator="IS NULL", operand=arg, prefix=False)
            for arg in args
        ]
        guard = checks[0]
        for check in checks[1:]:
            guard = SQLBinaryOp(operator="OR", left=guard, right=check)
        return guard

    def _translate_between_expression(self, expr: BinaryExpression) -> Optional[SQLExpression]:
        """Translate CQL between with explicit null-argument and interval rules."""
        if not (
            isinstance(expr.right, BinaryExpression)
            and str(expr.right.operator).lower() == "and"
        ):
            return None

        low_ast = expr.right.left
        high_ast = expr.right.right
        value_sql = self.translate(expr.left, usage=ExprUsage.SCALAR)
        low_sql = self.translate(low_ast, usage=ExprUsage.SCALAR)
        high_sql = self.translate(high_ast, usage=ExprUsage.SCALAR)

        if self._is_fhir_interval_expression(value_sql):
            inclusive_interval = SQLFunctionCall(
                name="intervalFromBounds",
                args=[
                    SQLCast(expression=low_sql, target_type="VARCHAR"),
                    SQLCast(expression=high_sql, target_type="VARCHAR"),
                    SQLLiteral(value=True),
                    SQLLiteral(value=True),
                ],
            )
            result: SQLExpression = SQLFunctionCall(
                name="intervalIncludedIn",
                args=[value_sql, inclusive_interval],
            )
        else:
            low_check = self.translate(
                BinaryExpression(operator=">=", left=expr.left, right=low_ast),
                usage=ExprUsage.BOOLEAN,
            )
            high_check = self.translate(
                BinaryExpression(operator="<=", left=expr.left, right=high_ast),
                usage=ExprUsage.BOOLEAN,
            )
            result = SQLBinaryOp(operator="AND", left=low_check, right=high_check)

        return SQLCase(
            when_clauses=[
                (self._between_null_guard(value_sql, low_sql, high_sql), SQLNull())
            ],
            else_clause=result,
        )

    def _translate_binary_expression(self, expr: BinaryExpression, boolean_context: bool = False) -> SQLExpression:
        """
        Translate a CQL binary expression to SQL.

        Context propagation rules:
        - Logical operators (AND, OR) -> pass BOOLEAN context to operands
        - NOT -> pass BOOLEAN context to operand
        - Comparison operators (=, <>, <, >, <=, >=) -> pass SCALAR context to operands
        - IN operator -> left is SCALAR, right is LIST
        """
        operator = expr.operator.lower() if isinstance(expr.operator, str) else expr.operator

        # Handle "duration in <unit> of <interval>" pattern before translating operands.
        # Parser produces: BinaryExpression(left=Identifier('duration'), operator='in',
        #   right=BinaryExpression(operator='precision of', left=Literal(unit), right=interval))
        if (operator == "in"
                and isinstance(expr.left, Identifier)
                and expr.left.name.lower() == "duration"
                and isinstance(expr.right, BinaryExpression)
                and expr.right.operator.lower() == "precision of"):
            return self._translate_duration_of(expr.right)

        # Handle "duration in days between X and Y" parsed as
        # BinaryExpression(left=Identifier('duration'), operator='in',
        #   right=DurationBetween(precision, left, right))
        # This is the same construct as above but the parser resolved the
        # "between" directly into a DurationBetween node.
        if (operator == "in"
                and isinstance(expr.left, Identifier)
                and expr.left.name.lower() == "duration"
                and isinstance(expr.right, DurationBetween)):
            return self._translate_duration_between(expr.right)

        # Handle CQL `is` type-check operator (e.g., `Order is MedicationRequest`)
        # Must be handled BEFORE generic operand translation because the right operand
        # is a NamedTypeSpecifier that translates to SQLNull() in the generic path.
        if operator == "is" and isinstance(expr.right, _STRUCTURAL_TYPE_SPECIFIER_TYPES):
            return self._translate_is_type_check(expr)

        # CQL §12.1: Tuple equality/inequality requires element-wise comparison
        # with three-valued null propagation.  DuckDB JSON comparison would treat
        # {"Name":null} as a concrete value, breaking CQL semantics.
        if operator in ("=", "!=", "not equal", "equal"):
            if isinstance(expr.left, TupleExpression) and isinstance(expr.right, TupleExpression):
                return self._translate_tuple_comparison(expr, operator)
            clinical_result = self._translate_static_clinical_equality(expr, operator)
            if clinical_result is not None:
                return clinical_result
            # CQL-21 EXPLORER QA-001: Equal (=) between a dynamically
            # retrieved code and a static Code literal must extract the
            # coding and compare code/system/version/display (Authors Guide:
            # `=` on codes is an exact match). The raw JSON-vs-JSON lowering
            # compared a CodeableConcept JSON against the literal Code JSON
            # and could never match.
            dynamic_code_eq = self._translate_dynamic_code_equality(expr, operator)
            if dynamic_code_eq is not None:
                return dynamic_code_eq

        # CQL `between` uses `and` as a bound separator, not as a logical
        # operator. Lower it before translating the synthetic right-side node.
        if operator == "between":
            between_result = self._translate_between_expression(expr)
            if between_result is not None:
                return between_result

        if operator == "&":
            self._validate_static_string_operand(expr.left, operator)
            self._validate_static_string_operand(expr.right, operator)

        if operator == "+":
            left_type = _normalize_cql_type_name(
                self._infer_static_cql_type_for_logical_operand(expr.left)
            )
            right_type = _normalize_cql_type_name(
                self._infer_static_cql_type_for_logical_operand(expr.right)
            )
            if "String" in {left_type, right_type}:
                self._validate_static_string_operand(expr.left, operator)
                self._validate_static_string_operand(expr.right, operator)

        # CQL-10 HISTORIAN QA-002: numeric-only arithmetic binary operators
        # have no String/Boolean overloads (CQL 1.5 §16) and Table 9-E
        # defines no implicit String/Boolean -> numeric conversion, so
        # statically String/Boolean operands must raise a typed
        # TranslationError instead of silently nulling at execution.
        if operator in ("/", "^", "*", "-"):
            for operand in (expr.left, expr.right):
                operand_type = _normalize_cql_type_name(
                    self._infer_static_cql_type_for_logical_operand(operand)
                )
                if operand_type in ("String", "Boolean"):
                    raise TranslationError(
                        f"CQL arithmetic operator '{operator}' requires "
                        f"numeric operands; got {operand_type}"
                    )

        # CQL-10 EXPLORER QA-002: statically-known scalar-vs-Quantity
        # mixtures with no valid overload must raise a typed
        # TranslationError instead of silently nulling at execution.
        # CQL 1.5 §9.1 Add / §9.4 Divide / §9.5 Subtract / §9.9 Power:
        #   + and - accept Quantity only against Quantity (temporal +/-
        #   Quantity stays valid: Date/DateTime/Time are not scalar);
        #   / accepts Quantity on the left with a Decimal right (implicit
        #   Decimal->Quantity conversion, fixture Divide1Q1Q) but a scalar
        #   left with a Quantity right has no signature;
        #   ^ has no Quantity overload at all;
        #   * accepts Quantity on either side (Multiply §9.6).
        # The reference engine raises InvalidOperatorArgument for these
        # mixtures; the pre-fix translator silently emitted NULL SQL.
        _SCALAR_NUM = ("Integer", "Long", "Decimal")
        if operator in ("+", "-", "/", "^"):
            left_type = _normalize_cql_type_name(
                self._infer_static_cql_type_for_logical_operand(expr.left)
            )
            right_type = _normalize_cql_type_name(
                self._infer_static_cql_type_for_logical_operand(expr.right)
            )
            left_scalar_qty = left_type in _SCALAR_NUM and right_type == "Quantity"
            right_scalar_qty = right_type in _SCALAR_NUM and left_type == "Quantity"
            invalid = False
            if operator == "/":
                invalid = left_scalar_qty
            elif operator == "^":
                invalid = "Quantity" in (left_type, right_type)
            else:  # + and -
                invalid = left_scalar_qty or right_scalar_qty
            if invalid:
                raise TranslationError(
                    f"CQL arithmetic operator '{operator}' has no overload for "
                    f"mixed {left_type} and {right_type} operands (CQL 1.5 §9); "
                    f"use a Quantity with a compatible unit or an explicit "
                    f"conversion"
                )

        if operator == "implies":
            self._validate_boolean_operand(expr.left, operator)
            self._validate_boolean_operand(expr.right, operator)

        if operator in ("and", "or", "xor"):
            self._validate_boolean_operand(expr.left, operator)
            self._validate_boolean_operand(expr.right, operator)
            left = self.translate(expr.left, usage=ExprUsage.BOOLEAN)
            right = self.translate(expr.right, usage=ExprUsage.BOOLEAN)
            if self.context.audit_mode and self.context.audit_expressions and operator in ("and", "or"):
                left = _ensure_audit_struct(left)
                right = _ensure_audit_struct(right)
                if operator == "and":
                    return SQLFunctionCall(name="audit_and", args=[left, right])
                macro = "audit_or_all" if self.context.audit_or_strategy == "all" else "audit_or"
                return SQLFunctionCall(name=macro, args=[left, right])
            if operator == "xor":
                # DuckDB doesn't support XOR keyword; use registered Xor() macro.
                return SQLFunctionCall(name="Xor", args=[left, right])
            sql_op = BINARY_OPERATOR_MAP.get(operator, operator.upper())
            return SQLBinaryOp(operator=sql_op, left=left, right=right)

        # Parser workaround for temporal operators with precision:
        # The parser sometimes mis-parses:
        #   X on or before day of end of "MAP" and Y
        # as: X on_or_before(precision_of(day, end_of("MAP" and Y)))
        # The AND leaks inside the precision/end-of wrappers.
        # Strip the AND from the right operand before translating it.
        extra_temporal_cond_ast = None
        _TEMPORAL_PREFIXES = ("on or before", "on or after", "before", "after")
        if any(operator.startswith(p) for p in _TEMPORAL_PREFIXES):
            cleaned_right, extra_temporal_cond_ast = self._strip_and_conditions(expr.right)
            # QA7-001: When the ON_OR_BEFORE/ON_OR_AFTER token path is used,
            # the parser emits operator="on or before" with the precision
            # nested inside the right operand as BinaryExpression(op="precision of").
            # Detect this and promote the precision into the operator string so
            # the translator routes to the precision-qualified UDF.
            if operator in ("on or before", "on or after") and isinstance(cleaned_right, BinaryExpression) and getattr(cleaned_right, 'operator', '') == "precision of":
                prec_node = getattr(cleaned_right, 'left', None)
                prec_val = getattr(prec_node, 'value', None) if prec_node else None
                if isinstance(prec_val, str) and prec_val.lower() in ("year", "month", "week", "day", "hour", "minute", "second", "millisecond"):
                    operator = f"{operator} {prec_val.lower()} of"
                    cleaned_right = cleaned_right.right
            left = self.translate(expr.left, usage=ExprUsage.SCALAR)
            right = self.translate(cleaned_right, usage=ExprUsage.SCALAR)
        elif operator == "as" and isinstance(expr.right, _STRUCTURAL_TYPE_SPECIFIER_TYPES):
            left = self.translate(expr.left, usage=ExprUsage.SCALAR)
            right = SQLNull()
        else:
            left = self.translate(expr.left, usage=ExprUsage.SCALAR)
            right = self.translate(expr.right, usage=ExprUsage.SCALAR)

        if operator in {
            "=", "!=", "<>", "~", "!~", "equivalent", "not equivalent",
            "in", "contains", "includes", "included in",
            "properly includes", "properly included in",
            "union", "intersect", "except",
        }:
            def _is_query_list_source(node: object) -> bool:
                source = self._definition_ast_for_identifier(node) or node
                return isinstance(source, Query) and self._is_list_typed_ast(source)

            if _is_query_list_source(expr.left):
                left = _coerce_query_rows_to_list(left)
            if _is_query_list_source(expr.right):
                right = _coerce_query_rows_to_list(right)

        # CQL §12.3: between — `X between low and high` → `X >= low and X <= high`
        if operator == "between":
            if isinstance(right, SQLBinaryOp) and right.operator.upper() == "AND":
                low_check = self.translate(
                    BinaryExpression(operator=">=", left=expr.left, right=expr.right.left),
                    usage=ExprUsage.BOOLEAN,
                )
                high_check = self.translate(
                    BinaryExpression(operator="<=", left=expr.left, right=expr.right.right),
                    usage=ExprUsage.BOOLEAN,
                )
                return SQLBinaryOp(
                    operator="AND",
                    left=low_check,
                    right=high_check,
                )

        # Handle type cast operator (X as Quantity)
        # When casting to Quantity, wrap in parse_quantity for date arithmetic recognition
        if operator == "as":
            if isinstance(expr.right, _STRUCTURAL_TYPE_SPECIFIER_TYPES):
                if isinstance(expr.right, NamedTypeSpecifier):
                    target_name = expr.right.name
                    self._ensure_known_named_type_target(target_name, "as")
                else:
                    target_name = self._type_specifier_name(expr.right)
                    self._ensure_known_type_specifier_target(expr.right, "as")
                bare_target = target_name.split(".")[-1] if "." in target_name else target_name
                strict_cast = bool(getattr(expr, "strict", False))

                def _strict_cast_result(
                    value: SQLExpression,
                    type_check: Optional[SQLExpression] = None,
                ) -> SQLExpression:
                    if not strict_cast:
                        return value
                    check = type_check
                    if check is None:
                        check = self._translate_is_type_check(
                            BinaryExpression(operator="is", left=expr.left, right=expr.right)
                        )
                    if isinstance(check, SQLLiteral) and check.value is True:
                        return value
                    failure = SQLFunctionCall(
                        name="error",
                        args=[SQLLiteral(value=f"CQL strict cast failed: value is not {target_name}")],
                    )
                    if isinstance(check, SQLLiteral) and check.value is False:
                        return failure
                    return SQLCase(
                        when_clauses=[(check, value)],
                        else_clause=failure,
                    )

                if (
                    isinstance(expr.right, ListTypeSpecifier)
                    and isinstance(expr.left, ListExpression)
                    and not expr.left.elements
                ):
                    return _strict_cast_result(SQLCast(
                        expression=SQLArray(elements=[]),
                        target_type=_sql_list_type_for_cql_list_specifier(expr.right),
                    ))
                primitive_targets = {
                    "Boolean", "boolean",
                    "Integer", "integer",
                    "Long", "long",
                    "Decimal", "decimal",
                    "String", "string",
                    "Any", "any",
                }
                if bare_target in primitive_targets:
                    if bare_target in ("Any", "any"):
                        return _strict_cast_result(left)
                    if isinstance(expr.left, Literal):
                        literal_type = getattr(expr.left, "type", None)
                        if literal_type is not None and literal_type.lower() == bare_target.lower():
                            return _strict_cast_result(left, SQLLiteral(value=True))
                        return _strict_cast_result(SQLNull(), SQLLiteral(value=False))
                    if isinstance(expr.left, FunctionRef):
                        function_return_types = {
                            "toboolean": "boolean",
                            "tointeger": "integer",
                            "tolong": "long",
                            "todecimal": "decimal",
                            "tostring": "string",
                        }
                        return_type = function_return_types.get(expr.left.name.lower())
                        if return_type is not None and return_type != bare_target.lower():
                            return _strict_cast_result(SQLNull(), SQLLiteral(value=False))
                        if return_type is not None:
                            return _strict_cast_result(left, SQLLiteral(value=True))

                    if isinstance(expr.left, Identifier):
                        meta = self.context.definition_meta.get(expr.left.name)
                        meta_type = self._bare_cql_type_name(getattr(meta, "cql_type", None)) if meta else None
                        if meta_type is None:
                            symbol = self.context.lookup_symbol(expr.left.name)
                            if symbol and getattr(symbol, "symbol_type", None) == "parameter":
                                meta_type = self._bare_cql_type_name(getattr(symbol, "cql_type", None))
                        if meta_type and meta_type.lower() in {target.lower() for target in primitive_targets}:
                            if meta_type.lower() != bare_target.lower():
                                return _strict_cast_result(SQLNull(), SQLLiteral(value=False))
                            target_sql_type = {
                                "boolean": "BOOLEAN",
                                "integer": "INTEGER",
                                "long": "BIGINT",
                                "decimal": "DOUBLE",
                                "string": "VARCHAR",
                            }.get(bare_target.lower())
                            if target_sql_type and bare_target.lower() != "string":
                                return _strict_cast_result(
                                    SQLCast(expression=left, target_type=target_sql_type, try_cast=True),
                                )
                            return _strict_cast_result(left)

                    static_source = self._static_structural_type_name(expr.left)
                    if static_source is not None:
                        if self._structural_type_conforms(static_source, target_name):
                            return _strict_cast_result(left, SQLLiteral(value=True))
                        return _strict_cast_result(SQLNull(), SQLLiteral(value=False))

                    fhirpath_type_check = self._fhirpath_primitive_type_check(left, bare_target)
                    fhirpath_value = self._fhirpath_primitive_as_value(left, bare_target)
                    if fhirpath_type_check is not None and fhirpath_value is not None:
                        return _strict_cast_result(SQLCase(
                            when_clauses=[(fhirpath_type_check, fhirpath_value)],
                            else_clause=SQLNull(),
                        ), fhirpath_type_check)

                    cql_typed_value = self._cql_typed_value_as_value(left, bare_target)
                    if cql_typed_value is not None:
                        return _strict_cast_result(cql_typed_value)

                    not_null = SQLBinaryOp(operator="IS NOT", left=left, right=SQLNull())
                    text_value = SQLCast(expression=left, target_type="VARCHAR")
                    not_json = SQLUnaryOp(
                        operator="NOT",
                        operand=SQLFunctionCall(
                            name="starts_with",
                            args=[
                                SQLFunctionCall(name="LTRIM", args=[text_value]),
                                SQLLiteral(value="{"),
                            ],
                        ),
                    )
                    textual_primitive = SQLBinaryOp(operator="AND", left=not_null, right=not_json)

                    if bare_target in ("Integer", "integer", "Long", "long"):
                        target_sql = "INTEGER" if bare_target in ("Integer", "integer") else "BIGINT"
                        integer_text = SQLFunctionCall(
                            name="regexp_full_match",
                            args=[text_value, SQLLiteral(value="^[+-]?[0-9]+$")],
                        )
                        can_cast = SQLBinaryOp(operator="AND", left=textual_primitive, right=integer_text)
                        return _strict_cast_result(SQLCase(
                            when_clauses=[(can_cast, SQLCast(expression=left, target_type=target_sql, try_cast=True))],
                            else_clause=SQLNull(),
                        ), can_cast)

                    if bare_target in ("Decimal", "decimal"):
                        return _strict_cast_result(SQLCase(
                            when_clauses=[
                                (
                                    textual_primitive,
                                    SQLCast(expression=left, target_type="DOUBLE", try_cast=True),
                                )
                            ],
                            else_clause=SQLNull(),
                        ), textual_primitive)

                    if bare_target in ("Boolean", "boolean"):
                        lowered = SQLFunctionCall(name="LOWER", args=[text_value])
                        is_true = SQLBinaryOp(operator="=", left=lowered, right=SQLLiteral(value="true"))
                        is_false = SQLBinaryOp(operator="=", left=lowered, right=SQLLiteral(value="false"))
                        bool_text = SQLBinaryOp(operator="OR", left=is_true, right=is_false)
                        can_cast = SQLBinaryOp(operator="AND", left=textual_primitive, right=bool_text)
                        return _strict_cast_result(SQLCase(
                            when_clauses=[(can_cast, SQLCast(expression=left, target_type="BOOLEAN", try_cast=True))],
                            else_clause=SQLNull(),
                        ), can_cast)

                    return _strict_cast_result(
                        SQLCase(when_clauses=[(textual_primitive, left)], else_clause=SQLNull()),
                        textual_primitive,
                    )

                clinical_target = self._CLINICAL_CQL_TYPES.get(bare_target.lower())
                if clinical_target is not None:
                    clinical_source = self._static_clinical_type(expr.left)
                    if clinical_source is not None:
                        if self._clinical_type_matches(clinical_source, clinical_target):
                            source_node = self._static_conversion_source_node(expr.left)
                            if source_node is not None:
                                return _strict_cast_result(
                                    self.translate(source_node, usage=ExprUsage.SCALAR),
                                    SQLLiteral(value=True),
                                )
                            return _strict_cast_result(left, SQLLiteral(value=True))
                        return _strict_cast_result(SQLNull(), SQLLiteral(value=False))
                    static_source = self._static_structural_type_name(expr.left)
                    if static_source is not None:
                        return _strict_cast_result(SQLNull(), SQLLiteral(value=False))
                    if bare_target in ("Code", "code", "Concept", "concept"):
                        # CQL §As: "If the argument is null, the result is null."
                        # When the source is statically null, skip the runtime
                        # JSON shape-check wrapper (which would otherwise produce
                        # a non-NULL CASE that defeats downstream null-guards in
                        # Code/Concept equivalence — see _translate_equivalence_op
                        # line ~5028 `isinstance(resource_expr, SQLNull)` guard).
                        if _is_null_expression(left):
                            return _strict_cast_result(SQLNull(), SQLLiteral(value=True))
                        if self._extract_fhirpath_value_call(left) is not None:
                            return _strict_cast_result(left)
                        runtime_check = self._clinical_json_type_check(left, bare_target)
                        if runtime_check is not None:
                            return _strict_cast_result(SQLCase(
                                when_clauses=[(runtime_check, left)],
                                else_clause=SQLNull(),
                            ), runtime_check)
                        return _strict_cast_result(SQLNull(), SQLLiteral(value=False))

                if bare_target in ("Quantity", "quantity"):
                    type_check = self._translate_is_type_check(
                        BinaryExpression(operator="is", left=expr.left, right=expr.right)
                    )
                    if isinstance(left, SQLFunctionCall) and left.name == "parse_quantity":
                        quantity_value = left
                    else:
                        quantity_value = SQLFunctionCall(
                            name="parse_quantity",
                            args=[SQLCast(expression=left, target_type="VARCHAR")],
                        )
                    result = SQLCase(
                        when_clauses=[(type_check, quantity_value)],
                        else_clause=SQLNull(),
                    )
                    result.result_type = "Quantity"
                    return _strict_cast_result(result, type_check)

                if isinstance(left, SQLFunctionCall) and left.name == "CQLMessage":
                    return _strict_cast_result(left)

                type_check = self._translate_is_type_check(
                    BinaryExpression(operator="is", left=expr.left, right=expr.right)
                )
                as_value = self._cql_typed_value_as_value(left, bare_target) or left
                source_node = self._definition_ast_for_identifier(expr.left)
                if source_node is not None and self._static_structural_type_name(source_node):
                    as_value = self.translate(source_node, usage=ExprUsage.SCALAR)
                return _strict_cast_result(SQLCase(
                    when_clauses=[(type_check, as_value)],
                    else_clause=SQLNull(),
                ), type_check)
            return left

        # Handle convert expression: convert X to Y
        # CQL convert converts values between types/units (e.g., days, hours)
        # Return operand as-is since our UDFs handle type coercion natively
        if operator == "convert":
            # CQL convert: convert <value> to <type>
            # Returns null on invalid input (§22.28-34).
            # The right operand is a NamedTypeSpecifier with the target type.
            source_node = self._static_conversion_source_node(expr.left)
            if source_node is not None:
                left = self.translate(source_node, usage=ExprUsage.SCALAR)
            target_type_name = getattr(expr.right, 'name', '') if hasattr(expr, 'right') else ''
            if isinstance(expr.right, NamedTypeSpecifier):
                if self._is_cql_conversion_unit_target(expr.right.name):
                    return left
                self._ensure_known_named_type_target(expr.right.name, "convert")
            elif isinstance(expr.right, ListTypeSpecifier):
                self._ensure_known_type_specifier_target(expr.right, "convert")
                target_type_name = self._type_specifier_name(expr.right)
            target_type_name = target_type_name.split(".")[-1].lower()
            source_type_name = self._static_structural_type_name(expr.left)
            if target_type_name == "concept" and source_type_name is not None:
                if self._structural_type_conforms(source_type_name, "List<Code>"):
                    concept_source = left
                    if isinstance(concept_source, SQLArray):
                        concept_source = SQLArray(
                            elements=[
                                SQLCast(expression=item, target_type="VARCHAR")
                                for item in concept_source.elements
                            ]
                        )
                    return SQLFunctionCall(name="ToConceptFromList", args=[concept_source])
            if target_type_name == "list<code>" and source_type_name is not None:
                if self._structural_type_conforms(source_type_name, "Concept"):
                    return SQLFunctionCall(name="ConceptToListCode", args=[left])
            convert_type_map = {
                'integer': 'INTEGER', 'decimal': 'DOUBLE', 'string': 'VARCHAR',
                'boolean': 'BOOLEAN', 'date': 'DATE', 'datetime': 'TIMESTAMP',
                'time': 'TIME', 'long': 'BIGINT',
            }
            if target_type_name == "any":
                return left
            conversion_functions = {
                "integer": "ToInteger",
                "long": "ToLong",
                "decimal": "ToDecimal",
                "boolean": "ToBoolean",
                "date": "ToDate",
                "datetime": "ToDateTime",
                "time": "ToTime",
                "quantity": "ToQuantity",
                "ratio": "ToRatio",
                "concept": "ToConcept",
                "string": "ToString",
            }
            conversion_function = conversion_functions.get(target_type_name)
            if conversion_function is not None:
                if target_type_name == "string" and (
                    _is_quantity_expression(left) or self._is_cql_quantity_expr(expr.left)
                ):
                    return SQLFunctionCall(
                        name="QuantityToString",
                        args=[_ensure_parse_quantity(left)],
                    )
                if target_type_name == "string" and (
                    source_type_name == "Ratio" or _is_ratio_expression(left)
                ):
                    return SQLFunctionCall(name="RatioToString", args=[left])
                if target_type_name == "string" and not _static_type_supports_string_conversion(source_type_name):
                    return SQLNull()
                # CQL §9 Convert + Table 9-E: same-type conversions are identity
                # ("N/A" cells). ToQuantity has no Quantity self-overload per the
                # CQL ToQuantity spec, so routing an existing Quantity through
                # ToQuantity silently returns NULL. Return the source unchanged
                # for any case where the static source type already conforms to
                # the target type. Comparison is case-insensitive because
                # ``target_type_name`` is lowercased while ``source_type_name``
                # preserves CQL casing.
                if source_type_name is not None and (
                    source_type_name.lower() == target_type_name.lower()
                    or self._structural_type_conforms(
                        source_type_name.lower(), target_type_name
                    )
                ):
                    return left
                return SQLFunctionCall(conversion_function, [left])
            target = convert_type_map.get(target_type_name)
            if target:
                return SQLCast(expression=left, target_type=target, try_cast=True)
            return SQLNull()

        # Handle special operators
        if operator == "implies":
            # A implies B = NOT A OR B
            not_left = SQLUnaryOp(operator="NOT", operand=left)
            return SQLBinaryOp(operator="OR", left=not_left, right=right)

        if operator == "contains":
            return self._translate_contains_op(operator, left, right, expr, boolean_context)
        if operator == "in":
            return self._translate_in_op(operator, left, right, expr, boolean_context)
        # Phase 3 (medterm4ds subsumption): intercept code-vs-code `is` and
        # `is not` BEFORE the type-check / `is null` fallthrough at line 2244.
        # CQL §5.6 between two code-typed operands means "the left code is a
        # member of the right code's subsumption closure" (directional). When
        # no closure table is loaded, we fall back to a literal
        # (system, code) equality (preserving the pre-Phase-3 intent for
        # case-sensitive code equality that previously collapsed to IS NULL).
        if operator in ("is", "is not") and not _operand_is_type_specifier(
            expr.right
        ):
            code_is_result = self._translate_code_is_op(expr, negated=(operator == "is not"))
            if code_is_result is not None:
                return code_is_result
        if operator.startswith("is"):
            # IS NULL / IS NOT NULL
            if operator == "is null" or operator == "is":
                return SQLUnaryOp(operator="IS NULL", operand=left, prefix=False)
            elif operator == "is not null" or operator == "is not":
                return SQLUnaryOp(operator="IS NOT NULL", operand=left, prefix=False)
            elif operator == "is true":
                return SQLFunctionCall(name="IsTrue", args=[left])
            elif operator == "is false":
                return SQLFunctionCall(name="IsFalse", args=[left])

        if operator == "div":
            # CQL truncated divide: truncates toward zero (not floor toward -inf)
            # CQL §16.4: division by zero returns null
            # Check for Quantity operands
            left_is_quantity = _is_quantity_expression(left) or self._is_cql_quantity_expr(expr.left)
            right_is_quantity = _is_quantity_expression(right) or self._is_cql_quantity_expr(expr.right)
            if left_is_quantity or right_is_quantity:
                left_q = _quantity_operand_for_arithmetic(left, left_is_quantity)
                right_q = _quantity_operand_for_arithmetic(right, right_is_quantity)
                return SQLFunctionCall(name="quantityTruncatedDivide", args=[left_q, right_q])
            if (
                self._is_definite_uncertainty_interval_expr(expr.left)
                or self._is_definite_uncertainty_interval_expr(expr.right)
            ):
                raise TranslationError("Cannot apply div to an uncertainty interval")
            left = self._fhirpath_number_projection(left) or left
            right = self._fhirpath_number_projection(right) or right
            if self._is_uncertain_between_expr(expr.left) or _is_uncertain_between_sql(left):
                left = SQLCast(expression=left, target_type="DOUBLE", try_cast=True)
            if self._is_uncertain_between_expr(expr.right) or _is_uncertain_between_sql(right):
                right = SQLCast(expression=right, target_type="DOUBLE", try_cast=True)
            # CQL §16.16 TruncatedDivide: Integer/Long operands yield
            # Integer/Long results and "if the result of the operation
            # cannot be represented, the result is null". DuckDB's `/`
            # always promotes DECIMAL to DOUBLE, which silently corrupts
            # exact-decimal quotients near integer boundaries (0.3 div 0.1
            # -> 2 instead of 3) and loses Long-range precision, so compute
            # the exact scale-8 quotient through cqlDivide (null on a zero
            # divisor), truncate toward zero, and narrow with TRY_CAST so
            # overflow yields NULL.
            exact_div = SQLFunctionCall(name="cqlDivide", args=[
                SQLCast(expression=left, target_type="VARCHAR"),
                SQLCast(expression=right, target_type="VARCHAR"),
            ])
            truncated = SQLFunctionCall(name="TRUNC", args=[exact_div])
            left_cql_type = _infer_static_numeric_type(expr.left)
            right_cql_type = _infer_static_numeric_type(expr.right)
            operand_types = {left_cql_type, right_cql_type} - {None}
            if "Decimal" in operand_types or not operand_types:
                # Decimal (or dynamic/unknown) operands: Decimal result at
                # the implementation scale, already exact from cqlDivide.
                return truncated
            if "Long" in operand_types:
                return SQLCast(expression=truncated, target_type="BIGINT", try_cast=True)
            return SQLCast(expression=truncated, target_type="INTEGER", try_cast=True)

        if operator == "^":
            # CQL §16 Power: ^(Integer,Integer) Integer, ^(Long,Long) Long,
            # ^(Decimal,Decimal) Decimal. "If the result of the operation
            # cannot be represented, the result is null."
            left_arg = self._fhirpath_number_projection(left) or left
            right_arg = self._fhirpath_number_projection(right) or right
            power_core = SQLFunctionCall(name="mathPower", args=[
                SQLCast(expression=left_arg, target_type="VARCHAR"),
                SQLCast(expression=right_arg, target_type="VARCHAR"),
            ])
            # Determine result type from CQL operand types when statically known.
            left_cql_type = _infer_static_numeric_type(expr.left)
            right_cql_type = _infer_static_numeric_type(expr.right)
            operand_types = {left_cql_type, right_cql_type} - {None}
            # Decimal takes precedence per spec implicit conversion rules;
            # otherwise Integer/Long stays integral.
            if "Decimal" in operand_types or "Quantity" in operand_types:
                # CQL §16 Power Decimal overload: result must fit in Decimal
                # range. Use DECIMAL(38, 8) (the implementation's standard
                # Decimal width) so TRY_CAST returns NULL on overflow
                # (e.g. Power(10.0, 100.0) = 1e100 cannot be represented).
                target_sql_type = "DECIMAL(38, 8)"
            elif "Long" in operand_types:
                target_sql_type = "BIGINT"
            elif operand_types == {"Integer"}:
                # CQL §16 Power Integer overload: ^Integer,Integer) Integer.
                # However, the official HL7 CQL conformance suite
                # (CqlArithmeticFunctionsTest.xml::Power2ToNeg2) expects
                # Power(2, -2) = 0.25 — a Decimal result, because raising
                # an Integer to a negative exponent yields a fraction. The
                # reference implementation promotes to Decimal in that case.
                # Statically detect negative exponents and use DECIMAL so
                # the result is not truncated to 0 by TRY_CAST(AS INTEGER).
                right_value = _static_numeric_value(expr.right)
                if right_value is not None and right_value < 0:
                    target_sql_type = "DECIMAL(38, 8)"
                else:
                    target_sql_type = "INTEGER"
            else:
                target_sql_type = "DOUBLE"
            return SQLCast(
                expression=power_core,
                target_type=target_sql_type,
                try_cast=True,
            )

        # List set operators
        # CQL v1.5.3 §20.29: the union operator can also be invoked with the
        # symbolic operator (|). The parser emits operator == "|" for the
        # symbolic form; route it through the same dispatcher so list and
        # interval union semantics are preserved.
        if operator == "union" or operator == "|":
            return self._translate_union_op(operator, left, right, expr)
        if operator == "intersect":
            return self._translate_intersect_op(operator, left, right, expr)
        if operator == "except":
            left, right = self._promote_list_setop_scalar_operands(left, right, expr)
            if self._is_list_operands(left, right, expr):
                if isinstance(right, SQLNull):
                    return left
                if isinstance(left, SQLNull):
                    return SQLNull()
                # CQL §9 Except list overload: a scalar Interval operand
                # (implicitly promoted to a singleton List) must be coerced
                # to a list before the list-except macro — otherwise the
                # macro receives a VARCHAR scalar and DuckDB raises a
                # BinderException on valid CQL. Only literal Interval AST
                # nodes are wrapped; identifiers keep their list typing.
                if isinstance(expr.right, Interval) and not _is_list_returning_sql(right):
                    right = SQLFunctionCall(name="list_value", args=[right])
                if isinstance(expr.left, Interval) and not _is_list_returning_sql(left):
                    left = SQLFunctionCall(name="list_value", args=[left])
                return self._list_except_call(left, right, expr.left, expr.right)
            # Row-producing operands -> SQL EXCEPT set operation
            left_is_rows = isinstance(left, (SQLSelect, SQLSubquery, SQLUnion, SQLExcept, SQLIntersect))
            right_is_rows = isinstance(right, (SQLSelect, SQLSubquery, SQLUnion, SQLExcept, SQLIntersect))
            if left_is_rows or right_is_rows:
                left_op = SQLSubquery(query=left) if isinstance(left, SQLSelect) else left
                right_op = SQLSubquery(query=right) if isinstance(right, SQLSelect) else right
                return SQLExcept(operands=[left_op, right_op])
            # CQL §19.14: X except null returns X
            if isinstance(right, SQLNull):
                return left
            # CQL §19.14: null except X returns null
            if isinstance(left, SQLNull):
                return SQLNull()
            # Interval operands → use intervalExcept UDF (CQL §19.12)
            left_is_interval = self._is_fhir_interval_expression(left)
            right_is_interval = self._is_fhir_interval_expression(right)
            if left_is_interval or right_is_interval:
                return SQLFunctionCall(name="intervalExcept", args=[left, right])
            # Fallback: CQL except for literal lists
            return self._list_except_call(left, right, expr.left, expr.right)

        # Interval operators - call UDFs
        if operator == "overlaps":
            return self._translate_overlaps_op(operator, left, right, expr)
        if operator == "overlaps after":
            return self._translate_overlaps_after_op(operator, left, right, expr)
        if operator == "overlaps before":
            return self._translate_overlaps_before_op(operator, left, right, expr)
        if operator == "during":
            return self._translate_during_op(operator, left, right, expr)
        if operator == "includes":
            # CQL-18 HISTORIAN QA-002: `A includes B` with BOTH operands
            # dynamic multi-valued FHIR properties lowers both sides to
            # scalar fhirpath_text, misses the list gate above, and falls
            # through to intervalContains -> always false (CQL 1.5 §10.10
            # List Includes: a list includes itself). Promote both sides to
            # their list projections first; the interval path keeps period-
            # property operands (see _is_fhir_interval_expression).
            if (
                isinstance(left, SQLFunctionCall)
                and left.name == "fhirpath_text"
                and len(left.args) == 2
                and isinstance(right, SQLFunctionCall)
                and right.name == "fhirpath_text"
                and len(right.args) == 2
                and not self._is_fhir_interval_expression(left)
                and not self._is_fhir_interval_expression(right)
            ):
                left = _promote_fhirpath_text_list(left)
                right = _promote_fhirpath_text_list(right)
            if self._is_list_operands(left, right, expr):
                left_is_list = self._is_single_list_expr(left, getattr(expr, 'left', None))
                right_is_list = self._is_single_list_expr(right, getattr(expr, 'right', None))
                if left_is_list and not right_is_list:
                    # List includes element → list_contains. CQL 1.5 §10.10
                    # Includes: "For the list-singleton overload, this
                    # operator is a synonym for the contains operator." A
                    # null element therefore keeps contains semantics
                    # (true iff the list contains any null elements) — do
                    # NOT short-circuit to null before the equality macro.
                    return self._list_contains_call(left, right, expr.left, expr.right)
                # List-list overload: "If either argument is null, the
                # result is null" (CQL 1.5 §10.10). Detect typed-null list
                # operands (`(null as List<T>)` lowers to an all-NULL CASE)
                # the same way `properly includes` does.
                if self._definitely_null_operand(expr.left, left) or self._definitely_null_operand(expr.right, right):
                    return SQLNull()
                return self._list_has_all_call(left, right, expr.left, expr.right)
            left = self._ensure_resource_to_interval(left, expr.left)
            # CQL 1.5 §9 Includes [precision] (Interval, Interval): "If
            # precision is specified and the point type is a date/time
            # type, comparisons used in the operation are performed at
            # the specified precision." Mirror the `included in` branch:
            # unwrap the `precision of` wrapper around an interval
            # operand and route to intervalIncludesPrecise, rather than
            # letting the generic precision-of translation truncate the
            # right bounds and compare at mixed precision (which
            # collapses determined results to NULL).
            cql_right_inc_iv = getattr(expr, 'right', None)
            includes_precision = None
            includes_precision_interval = None
            if (
                cql_right_inc_iv is not None
                and hasattr(cql_right_inc_iv, 'operator')
                and cql_right_inc_iv.operator == 'precision of'
                and hasattr(cql_right_inc_iv.left, 'value')
            ):
                _inner_iv = self.translate(
                    cql_right_inc_iv.right, usage=ExprUsage.SCALAR
                )
                if self._is_fhir_interval_expression(_inner_iv):
                    includes_precision = str(cql_right_inc_iv.left.value).lower()
                    includes_precision_interval = _inner_iv
            right_for_includes = (
                includes_precision_interval
                if includes_precision_interval is not None
                else right
            )
            right = self._ensure_resource_to_interval(right_for_includes, expr.right)
            right_is_interval = self._is_fhir_interval_expression(right)
            if right_is_interval and includes_precision is not None:
                l_inc = self._unwrap_precision_wrapper(left)
                r_inc = self._unwrap_precision_wrapper(right)
                return SQLFunctionCall(
                    name="intervalIncludesPrecise",
                    args=[l_inc, r_inc, SQLLiteral(value=includes_precision)],
                )
            if right_is_interval:
                return SQLFunctionCall(name="intervalIncludes", args=[left, right])
            # CQL §19.12 Includes: "For the point-interval overload, this
            # operator is a synonym for the contains operator." Detect the
            # precision-of wrapper for point-interval includes and dispatch
            # to intervalContainsPrecise so partial-precision Date/DateTime/
            # Time uncertainty propagates to NULL rather than collapsing to
            # raw string comparison.
            cql_right_inc = getattr(expr, 'right', None)
            if (
                cql_right_inc is not None
                and hasattr(cql_right_inc, 'operator')
                and cql_right_inc.operator == 'precision of'
                and hasattr(cql_right_inc.left, 'value')
            ):
                precision = str(cql_right_inc.left.value).lower()
                point_sql_inc = self.translate(cql_right_inc.right, usage=ExprUsage.SCALAR)
                point_sql_inc = (
                    self._unwrap_precision_wrapper(point_sql_inc)
                    if self._is_fhir_interval_expression(point_sql_inc)
                    else point_sql_inc
                )
                return SQLFunctionCall(
                    name="intervalContainsPrecise",
                    args=[
                        left,
                        self._quantity_interval_point_arg(point_sql_inc)
                        if self._is_quantity_interval_sql(left)
                        else self._ensure_interval_varchar(point_sql_inc),
                        SQLLiteral(value=precision),
                    ],
                )
            point_arg = (
                self._quantity_interval_point_arg(right)
                if self._is_quantity_interval_sql(left)
                else self._ensure_interval_varchar(right)
            )
            return SQLFunctionCall(name="intervalContains", args=[left, point_arg])
        if operator == "included in":
            # CQL-18 HISTORIAN QA-002 (mirror of the `includes` branch):
            # both-dynamic fhirpath_text operands must reach the list
            # has-all comparison, not intervalContains.
            if (
                isinstance(left, SQLFunctionCall)
                and left.name == "fhirpath_text"
                and len(left.args) == 2
                and isinstance(right, SQLFunctionCall)
                and right.name == "fhirpath_text"
                and len(right.args) == 2
                and not self._is_fhir_interval_expression(left)
                and not self._is_fhir_interval_expression(right)
            ):
                left = _promote_fhirpath_text_list(left)
                right = _promote_fhirpath_text_list(right)
            if self._is_list_operands(left, right, expr):
                left_is_list = self._is_single_list_expr(left, getattr(expr, 'left', None))
                right_is_list = self._is_single_list_expr(right, getattr(expr, 'right', None))
                if right_is_list and not left_is_list:
                    # Element included in list → list_contains. CQL 1.5
                    # §10.11 Included In: "For the singleton-list overload,
                    # this operator is a synonym for the in operator." A
                    # null element keeps in semantics (true iff the list
                    # contains any null elements) — do NOT short-circuit to
                    # null before the equality macro.
                    return self._list_contains_call(right, left, expr.right, expr.left)
                # List-list overload: "If either argument is null, the
                # result is null" (CQL 1.5 §10.11).
                if self._definitely_null_operand(expr.left, left) or self._definitely_null_operand(expr.right, right):
                    return SQLNull()
                return self._list_has_all_call(right, left, expr.right, expr.left)
            left = self._ensure_resource_to_interval(left, expr.left)
            right = self._ensure_resource_to_interval(right, expr.right)
            cql_right = getattr(expr, 'right', None)
            precision = None
            precision_interval = None
            if (cql_right is not None
                    and hasattr(cql_right, 'operator')
                    and cql_right.operator == 'precision of'
                    and hasattr(cql_right, 'left')
                    and hasattr(cql_right.left, 'value')):
                precision = str(cql_right.left.value).lower()
                precision_interval = self.translate(cql_right.right, usage=ExprUsage.SCALAR)
            right_for_interval = precision_interval if precision_interval is not None else right
            left_is_interval = self._is_fhir_interval_expression(left)
            right_is_interval = self._is_fhir_interval_expression(right_for_interval)
            if left_is_interval:
                l = self._unwrap_precision_wrapper(left)
                r = self._unwrap_precision_wrapper(right_for_interval) if right_is_interval else right_for_interval
                if precision is not None:
                    return SQLFunctionCall(name="intervalIncludedInPrecise", args=[l, r, SQLLiteral(value=precision)])
                return SQLFunctionCall(name="intervalIncludedIn", args=[l, r])
            if right_is_interval:
                r = self._unwrap_precision_wrapper(right_for_interval)
                if precision is not None:
                    return SQLFunctionCall(
                        name="intervalContainsPrecise",
                        args=[
                            r,
                            self._quantity_interval_point_arg(left)
                            if self._is_quantity_interval_sql(r)
                            else self._ensure_interval_varchar(left),
                            SQLLiteral(value=precision),
                        ],
                    )
                point_arg = (
                    self._quantity_interval_point_arg(left)
                    if self._is_quantity_interval_sql(r)
                    else self._ensure_interval_varchar(left)
                )
                return SQLFunctionCall(name="intervalContains", args=[r, point_arg])
            return SQLFunctionCall(name="intervalContains", args=[right, self._ensure_interval_varchar(left)])
        if operator == "properly includes":
            # CQL-19 SKEPTIC QA-004: `_is_single_list_expr` does not
            # recognize promoted dynamic list projections (from_json), so
            # the element overload fell into the list-list branch and
            # compared array_length(list) > array_length('Kim' literal).
            # Widen the recognition with _is_list_returning_sql.
            def _properly_is_list(node_sql, node_ast):
                return self._is_single_list_expr(node_sql, node_ast) or _is_list_returning_sql(node_sql)

            # CQL-19 SKEPTIC QA-004: a dynamic multi-valued FHIR property
            # operand lowers to scalar fhirpath_text (first-node truncation),
            # misses the list gate, and falls through to
            # intervalProperlyContains -> silently false with data present.
            # Promote to the list projection first (mirrors the CQL-18
            # includes pre-promotion); interval operands are not
            # fhirpath_text and are unaffected.
            if (
                isinstance(left, SQLFunctionCall)
                and left.name == "fhirpath_text"
                and len(left.args) == 2
                and not self._is_fhir_interval_expression(left)
            ):
                left = _promote_fhirpath_text_list(left)
            if (
                isinstance(right, SQLFunctionCall)
                and right.name == "fhirpath_text"
                and len(right.args) == 2
                and not self._is_fhir_interval_expression(right)
            ):
                right = _promote_fhirpath_text_list(right)
            if self._is_list_operands(left, right, expr):
                left_is_list = _properly_is_list(left, getattr(expr, 'left', None))
                right_is_list = _properly_is_list(right, getattr(expr, 'right', None))
                left_is_null = isinstance(left, SQLNull) or (isinstance(left, SQLLiteral) and left.value is None) or self._is_static_null_case(left)
                right_is_null = isinstance(right, SQLNull) or (isinstance(right, SQLLiteral) and right.value is None) or self._is_static_null_case(right)
                # CQL §20 List Properly Includes: "For the list-list overload, if
                # either argument is null, the result is null." Detect typed-null
                # list operands (translated to `CASE WHEN FALSE THEN NULL ELSE
                # NULL END`) so the array_length comparison does not silently
                # short-circuit to FALSE.
                if left_is_list and left_is_null:
                    return SQLNull()
                if right_is_list and right_is_null:
                    return SQLNull()
                if left_is_null:
                    return SQLNull()
                if right_is_null and right_is_list:
                    return SQLNull()
                if left_is_list and not right_is_list:
                    # List properly includes element = CQL equality contains AND len > 1.
                    contains_check = self._list_contains_call(left, right, expr.left, expr.right)
                    return SQLBinaryOp(
                        operator="AND",
                        left=contains_check,
                        right=SQLBinaryOp(
                            operator=">",
                            left=SQLFunctionCall(name="array_length", args=[left]),
                            right=SQLLiteral(1),
                        ),
                    )
                return SQLBinaryOp(
                    operator="AND",
                    left=self._list_has_all_call(left, right, expr.left, expr.right),
                    right=SQLBinaryOp(
                        operator=">",
                        left=SQLFunctionCall(name="array_length", args=[left]),
                        right=SQLFunctionCall(name="array_length", args=[right]),
                    ),
                )
            left = self._ensure_resource_to_interval(left, expr.left)
            right = self._ensure_resource_to_interval(right, expr.right)
            cql_right = getattr(expr, 'right', None)
            precision = None
            precision_interval = None
            if (cql_right is not None
                    and hasattr(cql_right, 'operator')
                    and cql_right.operator == 'precision of'
                    and hasattr(cql_right, 'left')
                    and hasattr(cql_right.left, 'value')):
                precision = str(cql_right.left.value).lower()
                precision_interval = self.translate(cql_right.right, usage=ExprUsage.SCALAR)
            right_for_interval = precision_interval if precision_interval is not None else right
            right_is_interval = self._is_fhir_interval_expression(right)
            right_for_precision_is_interval = self._is_fhir_interval_expression(right_for_interval)
            if precision is not None:
                left_interval = left if self._is_fhir_interval_expression(left) else self._point_as_interval(left)
                right_interval = (
                    right_for_interval
                    if right_for_precision_is_interval
                    else self._point_as_interval(right_for_interval)
                )
                includes = SQLFunctionCall(
                    name="intervalIncludesPrecise",
                    args=[left_interval, right_interval, SQLLiteral(value=precision)],
                )
                same = (
                    self._interval_same_at_precision(left_interval, right_interval, precision)
                    if right_for_precision_is_interval
                    else self._point_same_as_interval_boundary_at_precision(left_interval, right_interval, precision)
                )
                return SQLBinaryOp(operator="AND", left=includes, right=SQLUnaryOp(operator="NOT", operand=same))
            if right_is_interval:
                return SQLFunctionCall(name="intervalProperlyIncludes", args=[left, right])
            return SQLFunctionCall(name="intervalProperlyContains", args=[left, self._ensure_interval_varchar(right)])
        if operator == "properly included in":
            # CQL-19 SKEPTIC QA-004: same widened list-recognition as
            # properly includes (see helper there).
            def _properly_is_list(node_sql, node_ast):
                return self._is_single_list_expr(node_sql, node_ast) or _is_list_returning_sql(node_sql)
            # CQL-19 SKEPTIC QA-004: mirror the properly-includes
            # pre-promotion — a dynamic multi-valued FHIR property operand
            # must reach the list gate as a full list projection, not the
            # truncated scalar fhirpath_text.
            if (
                isinstance(left, SQLFunctionCall)
                and left.name == "fhirpath_text"
                and len(left.args) == 2
                and not self._is_fhir_interval_expression(left)
            ):
                left = _promote_fhirpath_text_list(left)
            if (
                isinstance(right, SQLFunctionCall)
                and right.name == "fhirpath_text"
                and len(right.args) == 2
                and not self._is_fhir_interval_expression(right)
            ):
                right = _promote_fhirpath_text_list(right)
            if self._is_list_operands(left, right, expr):
                left_is_list = _properly_is_list(left, getattr(expr, 'left', None))
                right_is_list = _properly_is_list(right, getattr(expr, 'right', None))
                left_is_null = isinstance(left, SQLNull) or (isinstance(left, SQLLiteral) and left.value is None) or self._is_static_null_case(left)
                right_is_null = isinstance(right, SQLNull) or (isinstance(right, SQLLiteral) and right.value is None) or self._is_static_null_case(right)
                # CQL §20 List Properly Included In: "For the list-list overload,
                # if either argument is null, the result is null." Detect typed-
                # null list operands (translated to `CASE WHEN FALSE THEN NULL
                # ELSE NULL END`) so the array_length comparison does not
                # silently short-circuit to FALSE.
                if left_is_list and left_is_null:
                    return SQLNull()
                if right_is_list and right_is_null:
                    return SQLNull()
                if right_is_null:
                    return SQLNull()
                if left_is_null and left_is_list:
                    return SQLNull()
                if right_is_list and not left_is_list:
                    # Element properly included in list = CQL equality contains AND len > 1.
                    contains_check = self._list_contains_call(right, left, expr.right, expr.left)
                    return SQLBinaryOp(
                        operator="AND",
                        left=contains_check,
                        right=SQLBinaryOp(
                            operator=">",
                            left=SQLFunctionCall(name="array_length", args=[right]),
                            right=SQLLiteral(1),
                        ),
                    )
                return SQLBinaryOp(
                    operator="AND",
                    left=self._list_has_all_call(right, left, expr.right, expr.left),
                    right=SQLBinaryOp(
                        operator=">",
                        left=SQLFunctionCall(name="array_length", args=[right]),
                        right=SQLFunctionCall(name="array_length", args=[left]),
                    ),
                )
            left = self._ensure_resource_to_interval(left, expr.left)
            right = self._ensure_resource_to_interval(right, expr.right)
            cql_right = getattr(expr, 'right', None)
            precision = None
            precision_interval = None
            if (cql_right is not None
                    and hasattr(cql_right, 'operator')
                    and cql_right.operator == 'precision of'
                    and hasattr(cql_right, 'left')
                    and hasattr(cql_right.left, 'value')):
                precision = str(cql_right.left.value).lower()
                precision_interval = self.translate(cql_right.right, usage=ExprUsage.SCALAR)
            right_for_interval = precision_interval if precision_interval is not None else right
            if precision is not None:
                left_for_precision_is_interval = self._is_fhir_interval_expression(left)
                left_interval = left if self._is_fhir_interval_expression(left) else self._point_as_interval(left)
                right_interval = (
                    right_for_interval
                    if self._is_fhir_interval_expression(right_for_interval)
                    else self._point_as_interval(right_for_interval)
                )
                included = SQLFunctionCall(
                    name="intervalIncludesPrecise",
                    args=[right_interval, left_interval, SQLLiteral(value=precision)],
                )
                same = (
                    self._interval_same_at_precision(left_interval, right_interval, precision)
                    if left_for_precision_is_interval
                    else self._point_same_as_interval_boundary_at_precision(right_interval, left_interval, precision)
                )
                return SQLBinaryOp(operator="AND", left=included, right=SQLUnaryOp(operator="NOT", operand=same))
            left_is_interval = self._is_fhir_interval_expression(left)
            right_is_interval = self._is_fhir_interval_expression(right)
            if left_is_interval:
                l = self._unwrap_precision_wrapper(left)
                r = self._unwrap_precision_wrapper(right) if right_is_interval else right
                if _is_untyped_null_bound_interval(getattr(expr, "right", None)):
                    r = SQLFunctionCall(
                        name="intervalFromBounds",
                        args=[
                            SQLLiteral("__null__"),
                            SQLLiteral("__null__"),
                            SQLLiteral(expr.right.low_closed),
                            SQLLiteral(expr.right.high_closed),
                        ],
                    )
                return SQLFunctionCall(name="intervalProperlyIncludedIn", args=[l, r])
            if right_is_interval:
                r = self._unwrap_precision_wrapper(right)
                return SQLFunctionCall(name="intervalProperlyContains", args=[r, self._ensure_interval_varchar(left)])
            return SQLFunctionCall(name="intervalProperlyContains", args=[right, self._ensure_interval_varchar(left)])
        if operator == "before":
            return self._translate_before_op(operator, left, right, expr)
        if operator == "after":
            return self._translate_after_op(operator, left, right, expr)
        # Precision-qualified "before/after <precision> of": e.g. "after day of", "before day of"
        # Also handles "on or before/after <precision> of"
        # Truncate both sides to the specified precision and compare.
        import re as _re
        _prec_temporal_match = _re.match(r'^(on or before|on or after|before|after)\s+(\w+)\s+of$', operator)
        if _prec_temporal_match:
            _direction = _prec_temporal_match.group(1)
            _precision = _prec_temporal_match.group(2).lower()
            # Handle compound pattern: "X ends/starts Quantity <direction> <precision> of Y"
            # AST: BinaryExpression(op='after day of',
            #        left=BinaryExpression(op='ends', left=Interval, right=Quantity),
            #        right=Y)
            if isinstance(expr.left, BinaryExpression) and expr.left.operator in ("starts", "ends"):
                from ...parser.ast_nodes import Quantity as ASTQuantity
                if isinstance(expr.left.right, ASTQuantity):
                    _boundary_fn = "intervalStart" if expr.left.operator == "starts" else "intervalEnd"
                    _interval_sql = self.translate(expr.left.left, usage=ExprUsage.SCALAR)
                    _qty_val = int(float(expr.left.right.value))
                    _qty_unit = expr.left.right.unit
                    _boundary_expr = SQLFunctionCall(name=_boundary_fn, args=[_interval_sql])
                    _interval_lit = SQLIntervalLiteral(value=_qty_val, unit=_qty_unit)
                    _cast_type = self._temporal_target_type(_qty_unit)
                    _right_cast = self._ensure_date_cast(right, _cast_type)
                    # INTERVAL arithmetic requires TIMESTAMP — cast VARCHAR back
                    _right_ts = SQLCast(expression=_right_cast, target_type="TIMESTAMP")
                    if _direction in ("after", "on or after"):
                        _offset_right = self._timestamp_arith_for_compare(
                            SQLBinaryOp(operator="+", left=_right_ts, right=_interval_lit))
                    else:
                        _offset_right = self._timestamp_arith_for_compare(
                            SQLBinaryOp(operator="-", left=_right_ts, right=_interval_lit))
                    _boundary_expr = self._truncate_to_precision(
                        self._ensure_date_cast(_boundary_expr, _cast_type), _precision)
                    _offset_right = self._truncate_to_precision(_offset_right, _precision)
                    return SQLBinaryOp(operator="=", left=_boundary_expr, right=_offset_right)
            if _direction in ("before", "on or before"):
                _op = "<" if _direction == "before" else "<="
            else:
                _op = ">" if _direction == "after" else ">="
            # Resolve FHIR intervals: extract appropriate bounds for comparison.
            # For "on or after": start(left) >= end(right)
            # For "on or before": end(left) <= start(right)
            _left = left
            _right = right
            if self._is_fhir_interval_expression(left):
                if _direction in ("before", "on or before"):
                    _left = SQLFunctionCall(name="intervalEnd", args=[left])
                else:
                    _left = SQLFunctionCall(name="intervalStart", args=[left])
            if self._is_fhir_interval_expression(right):
                if _direction in ("before", "on or before"):
                    _right = SQLFunctionCall(name="intervalStart", args=[right])
                else:
                    _right = SQLFunctionCall(name="intervalEnd", args=[right])
            # Use precision-qualified UDFs — handles timezone normalization
            # and returns null when operand precision < target precision.
            _udf_map = {
                "before": "cqlBeforeP",
                "on or before": "cqlSameOrBeforeP",
                "after": "cqlAfterP",
                "on or after": "cqlSameOrAfterP",
            }
            _udf_name = _udf_map.get(_direction, "cqlSameOrBeforeP")
            return SQLFunctionCall(
                name=_udf_name,
                args=[
                    SQLCast(expression=_left, target_type="VARCHAR"),
                    SQLCast(expression=_right, target_type="VARCHAR"),
                    SQLLiteral(value=_precision),
                ],
            )
        if operator == "meets":
            left = self._ensure_resource_to_interval(left, expr.left)
            right = self._ensure_resource_to_interval(right, expr.right)
            return self._translate_meets_op("intervalMeets", left, right, expr)
        if operator == "meets before":
            left = self._ensure_resource_to_interval(left, expr.left)
            right = self._ensure_resource_to_interval(right, expr.right)
            return self._translate_meets_op("intervalMeetsBefore", left, right, expr)
        if operator == "meets after":
            left = self._ensure_resource_to_interval(left, expr.left)
            right = self._ensure_resource_to_interval(right, expr.right)
            return self._translate_meets_op("intervalMeetsAfter", left, right, expr)
        if operator == "starts":
            return self._translate_starts_op(operator, left, right, expr)
        if operator == "ends":
            return self._translate_ends_op(operator, left, right, expr)
        if operator.startswith("same "):
            return self._translate_same_operator(operator, left, right, expr=expr)

        # During with precision: during day of, during month of, etc.
        if operator.startswith("during "):
            return self._translate_during_operator(operator, left, right)

        # Precision operator: 'day' precision of DateTime -> DATE(DateTime)
        if operator == "precision of":
            # Check if left is a SQLLiteral with a string value
            if hasattr(left, 'value') and isinstance(left.value, str):
                precision = left.value.lower()
                return self._truncate_to_precision(right, precision)

        # On or before/after with precision
        if operator.startswith("on or before"):
            result = self._translate_on_or_before_operator(operator, left, right)
            if extra_temporal_cond_ast:
                extra_sql = self.translate(extra_temporal_cond_ast, boolean_context=True)
                return SQLBinaryOp(operator="AND", left=result, right=extra_sql)
            return result
        if operator.startswith("on or after"):
            result = self._translate_on_or_after_operator(operator, left, right)
            if extra_temporal_cond_ast:
                extra_sql = self.translate(extra_temporal_cond_ast, boolean_context=True)
                return SQLBinaryOp(operator="AND", left=result, right=extra_sql)
            return result

        # Equivalence operator (~) and not-equivalent (!~): null-safe comparison
        # a ~ b is true if both are equal (including both NULL), false otherwise
        # a !~ b is the negation of a ~ b
        if operator in ("~", "!~"):
            return self._translate_equivalence_op(operator, left, right, expr)

        return self._translate_tail_operators(operator, left, right, expr, extra_temporal_cond_ast)
    def _translate_contains_op(self, operator, left, right, expr, boolean_context) -> SQLExpression:
        """Extracted from _translate_binary_expression."""
        # CQL `contains` has three meanings:
        # 1. ValueSet contains element: left is a valueset identifier → in_valueset
        # 2. List contains element: left is a list/subquery, right is scalar → use IN
        # 3. String contains: left is a string, right is a substring → use LIKE

        # Check if left is a ValueSet reference ("VS" contains X ≡ X in "VS")
        vs_name_c: Optional[str] = None
        vs_url_c: Optional[str] = None
        if isinstance(expr.left, Identifier):
            vs_name_c = expr.left.name
        elif isinstance(expr.left, ParameterPlaceholder):
            vs_url_c = self._valueset_url_from_placeholder(expr.left)
            if vs_url_c is None and isinstance(expr.left.sql_expr, SQLIdentifier):
                vs_name_c = expr.left.sql_expr.name
        if vs_name_c is not None:
            vs_url_c = self._resolve_valueset_identifier(vs_name_c)
        if vs_url_c:
            if (isinstance(right, SQLFunctionCall)
                    and right.name in ('fhirpath_text', 'fhirpath_date')
                    and len(right.args) == 2):
                resource_arg = right.args[0]
                path_arg = right.args[1]
            else:
                resource_arg = right
                path_arg = SQLLiteral("code")
            if _is_list_returning_sql(resource_arg):
                _iv_param = "_ivr"
                _inner_from = SQLSubquery(query=SQLSelect(
                    columns=[SQLAlias(
                        expr=SQLFunctionCall(
                            name="unnest", args=[resource_arg]),
                        alias=_iv_param,
                    )],
                ))
                _iv_select = SQLSelect(
                    columns=[SQLLiteral(1)],
                    from_clause=SQLAlias(
                        expr=_inner_from, alias="_ivt"),
                    where=SQLFunctionCall(
                        name="in_valueset",
                        args=[
                            SQLIdentifier(name=_iv_param),
                            path_arg,
                            SQLLiteral(vs_url_c),
                        ],
                    ),
                )
                return SQLExists(
                    subquery=SQLSubquery(query=_iv_select))
            return SQLFunctionCall(
                name="in_valueset",
                args=[resource_arg, path_arg, SQLLiteral(vs_url_c)],
            )

        # CQL §19.3 Contains: "If the first argument is null, the result is
        # false. If the second argument is null, the result is null."
        # First-arg-null short-circuit MUST fire before second-arg-null so
        # `(null as Interval<T>) contains (null as T)` → False, not null.
        if self._definitely_null_operand(expr.left, left):
            if self._null_contains_container_returns_false(expr.left, expr.right):
                return SQLLiteral(value=False)
            if self._definitely_null_operand(expr.right, right):
                return SQLNull()

        if (
            self._interval_selector_is_untyped_null_interval(expr.left)
            and self._definitely_null_operand(expr.right, right)
        ):
            return SQLNull()
        if self._interval_selector_is_untyped_null_interval(expr.left):
            return SQLLiteral(value=False)

        # CQL §19.3 Contains precision: "Interval<T> contains <precision> of
        # <point>" — dispatch to intervalContainsPrecise for partial-precision
        # Date/DateTime/Time uncertainty propagation. Parser emits
        # BinaryExpression(operator='precision of', left=Literal(unit),
        # right=<point>) as the right operand of contains.
        cql_right_contains = getattr(expr, 'right', None)
        if (
            cql_right_contains is not None
            and hasattr(cql_right_contains, 'operator')
            and cql_right_contains.operator == 'precision of'
            and hasattr(cql_right_contains.left, 'value')
        ):
            precision = str(cql_right_contains.left.value).lower()
            point_expr = self.translate(cql_right_contains.right, usage=ExprUsage.SCALAR)
            # Strip any precision-wrapper that the point translator may have
            # added (defensive — usually a no-op for plain points).
            point_sql = (
                self._unwrap_precision_wrapper(point_expr)
                if self._is_fhir_interval_expression(point_expr)
                else point_expr
            )
            return SQLFunctionCall(
                name="intervalContainsPrecise",
                args=[
                    left,
                    self._quantity_interval_point_arg(point_sql)
                    if self._is_quantity_interval_sql(left)
                    else self._ensure_interval_varchar(point_sql),
                    SQLLiteral(value=precision),
                ],
            )

        # Detect list context by checking if left translated to a subquery
        # BUT first check if it's an interval reference (CTE producing interval)
        if isinstance(left, SQLSubquery) and self._is_fhir_interval_expression(left):
            if self._is_fhir_interval_expression(right):
                # Interval includes interval
                return SQLFunctionCall(name="intervalIncludes", args=[left, right])
            # Interval contains point
            return SQLFunctionCall(
                name="intervalContains",
                args=[
                    left,
                    self._quantity_interval_point_arg(right)
                    if self._is_quantity_interval_sql(left)
                    else self._ensure_interval_varchar(right),
                ],
            )
        if self._is_list_operands(left, right, expr):
            # CQL-15 EXPLORER QA-001: element selection over an interval
            # list (First/Last/indexer → LIST_EXTRACT) is interval-typed
            # even though the SQL looks list-returning; interval contains
            # must win over generic list containment.
            if self._is_fhir_interval_expression(left):
                if self._is_fhir_interval_expression(right):
                    return SQLFunctionCall(name="intervalIncludes", args=[left, right])
                return SQLFunctionCall(
                    name="intervalContains",
                    args=[
                        left,
                        self._quantity_interval_point_arg(right)
                        if self._is_quantity_interval_sql(left)
                        else self._ensure_interval_varchar(right),
                    ],
                )
            return self._list_contains_call(left, right, expr.left, expr.right)
        if isinstance(left, SQLSubquery):
            # Check if the CQL type system indicates this should be an interval
            cql_left = getattr(expr, 'left', None) if expr else None
            if cql_left is not None:
                left_type = self._infer_cql_type(cql_left) if hasattr(self, '_infer_cql_type') else None
                if left_type and (left_type.startswith("Interval") or left_type == "Period"):
                    _logger.warning(
                        "Contains operator: CQL type indicates interval (%s) but "
                        "interval detection failed for SQLSubquery — falling through "
                        "to list containment.",
                        left_type,
                    )
            # List containment: right IN (left subquery)
            return SQLBinaryOp(
                operator="IN",
                left=right,
                right=left,
            )
        # Check if left is a list/array-returning expression
        if _is_list_returning_sql(left):
            # CQL §20.5: list contains null → true if list has null elements
            return self._list_contains_call(left, right, expr.left, expr.right)
        # Interval contains point: when left is an interval-producing expression
        if self._is_fhir_interval_expression(left) or (
            isinstance(left, SQLFunctionCall) and left.name == "intervalFromBounds"
        ):
            return SQLFunctionCall(
                name="intervalContains",
                args=[
                    left,
                    self._quantity_interval_point_arg(right)
                    if self._is_quantity_interval_sql(left)
                    else self._ensure_interval_varchar(right),
                ],
            )
        # CQL-18 SKEPTIC relaunch QA-002: `left contains right` where left is a
        # dynamic FHIR property lowered to scalar fhirpath_text (first-node
        # truncation). CQL 1.5 §10.1 Contains uses equality semantics over the
        # full list, not substring semantics over one node.
        if (
            isinstance(left, SQLFunctionCall)
            and left.name == "fhirpath_text"
            and len(left.args) == 2
        ):
            return self._list_contains_call(left, right, expr.left, expr.right)
        # String contains: CQL 'left contains right' → contains(left, right)
        return SQLFunctionCall(name="system.contains", args=[left, right])

    def _static_clinical_value_object(self, node) -> Optional[dict[str, Any]]:
        """Return a static CQL Code or Concept value object when known."""
        if isinstance(node, CodeSelector):
            value = {
                "code": node.code,
                "system": self.context.codesystems.get(node.system, node.system),
            }
            if node.display is not None:
                value["display"] = node.display
            return value
        if (
            isinstance(node, FunctionRef)
            and node.name.split(".")[-1] == "ToConcept"
            and len(node.arguments) == 1
        ):
            # CQL-02 QA-003: ToConcept(Code) propagates display; ToConcept(
            # List<Code>) keeps code displays but has no Concept display.
            argument = node.arguments[0]
            if isinstance(argument, ListExpression):
                codes: list[dict[str, Any]] = []
                for item in argument.elements:
                    item_value = self._static_clinical_value_object(item)
                    if not (isinstance(item_value, dict) and item_value.get("code")):
                        return None
                    codes.append(self._normalize_static_clinical_code(item_value))
                return {"codes": codes}
            single = self._static_clinical_value_object(argument)
            if isinstance(single, dict) and single.get("code"):
                normalized = self._normalize_static_clinical_code(single)
                concept: dict[str, Any] = {"codes": [normalized]}
                if normalized.get("display") is not None:
                    concept["display"] = normalized["display"]
                return concept
            return None
        if isinstance(node, Identifier):
            if self.context.is_alias(node.name):
                return None
            info = self.context.get_code(node.name)
            if info is None:
                # CQL-02 EXPLORER QA-001/QA-002 fix: when the Identifier is a
                # top-level `define` whose body is a statically-known clinical
                # literal (Code selector or Concept instance), recurse on the
                # definition's CQL AST so equivalence/equality can fold at
                # translation time. Without this, `define C: Code 'x' from CS`
                # followed by `define Test: C ~ <other Code/Concept>` falls
                # through to a generic SQL CASE that compares raw JSON shapes
                # (Code {code,system,...} != Concept {codes:[...]}) and
                # silently returns False instead of the spec-correct result.
                source_ast = self._definition_source_ast(node.name, node)
                if source_ast is not None:
                    return self._static_clinical_value_object(source_ast)
                return None
            if info.get("is_concept") or isinstance(info.get("codes"), list):
                value = {
                    "codes": [
                        self._normalize_static_clinical_code(code)
                        for code in info.get("codes", [])
                        if isinstance(code, dict)
                    ],
                }
                if info.get("display") is not None:
                    value["display"] = info.get("display")
                return value
            if info.get("code"):
                return self._normalize_static_clinical_code(info)
        if isinstance(node, QualifiedIdentifier) and node.parts:
            info = self.context.get_code(node.parts[-1])
            if info is None:
                # CQL-02 EXPLORER QA-001/QA-002 fix (QualifiedIdentifier path):
                # resolve library-qualified define references whose body is a
                # statically-known clinical literal.
                source_ast = self._definition_source_ast(node.parts[-1], node)
                if source_ast is not None:
                    return self._static_clinical_value_object(source_ast)
                return None
            if info.get("is_concept") or isinstance(info.get("codes"), list):
                value = {
                    "codes": [
                        self._normalize_static_clinical_code(code)
                        for code in info.get("codes", [])
                        if isinstance(code, dict)
                    ],
                }
                if info.get("display") is not None:
                    value["display"] = info.get("display")
                return value
            if info.get("code"):
                return self._normalize_static_clinical_code(info)
        if isinstance(node, InstanceExpression):
            bare = self._bare_cql_type_name(node.type)
            fields: dict[str, Any] = {}
            for element in node.elements:
                value_expr = element.type
                if isinstance(value_expr, Literal):
                    fields[element.name] = value_expr.value
                elif element.name == "codes" and isinstance(value_expr, ListExpression):
                    codes: list[dict[str, Any]] = []
                    for item in value_expr.elements:
                        code_value = self._static_clinical_value_object(item)
                        if code_value is None or "code" not in code_value:
                            return None
                        codes.append(self._normalize_static_clinical_code(code_value))
                    fields[element.name] = codes
            if bare == "Code" and fields.get("code"):
                return self._normalize_static_clinical_code(fields)
            if bare == "Concept":
                return fields
        return None

    def _normalize_static_clinical_code(self, value: dict[str, Any]) -> dict[str, Any]:
        # CQL-02 EXPLORER QA-001: an absent element and an explicit `null`
        # element are both "no value" for tuple equality (CQL 1.5 Equal:
        # "the values for all elements that have values ... are equal"), so
        # null-valued elements must not be materialized as keys. Previously
        # an absent system folded to '' while `system: null` folded to None,
        # making `Code { code: 'x' } = Code { code: 'x', system: null }`
        # compare '' vs None and return False instead of True.
        code: dict[str, Any] = {"code": value.get("code", "")}
        system = value.get("system", value.get("codesystem"))
        if system is not None:
            code["system"] = self.context.codesystems.get(system, system)
        if value.get("version") is not None:
            code["version"] = value.get("version")
        if value.get("display") is not None:
            code["display"] = value.get("display")
        return code

    def _code_equivalence_key(self, code_info: dict[str, Any]) -> tuple:
        """CQL 1.5 Equivalent (Code): equivalence on the code and system
        elements only, using String equivalence (case/locale-insensitive,
        whitespace-normalized). Null is equivalent only to null — NOT to the
        empty string (CQL 1.5 Equivalent: "null is not equivalent to the
        empty string") — so null elements map to a None key while '' keeps
        its normalized string form (CQL-02 EXPLORER QA-001)."""
        def _element_key(value: Any) -> Any:
            if value is None:
                return None
            if not isinstance(value, str):
                return value
            return " ".join(value.split()).casefold()

        system = code_info.get("codesystem", code_info.get("system"))
        resolved = (
            self.context.codesystems.get(system, system)
            if isinstance(system, str)
            else system
        )
        return (_element_key(resolved), _element_key(code_info.get("code")))

    def _static_code_list(self, node) -> Optional[list[dict[str, Any]]]:
        """Resolve a CQL AST node to a static List<Code> when possible.

        Covers list literals of Code values and statically-folded ``.codes``
        accessors on Concept values (including through ToConcept(...) and
        define aliases, via ``_static_clinical_value_object``). Bare Concept
        values are intentionally NOT resolved here: Concept equivalence uses
        code-intersection semantics, not list equivalence. Returns None when
        the node is not a statically-known List<Code>.
        """
        from ...parser.ast_nodes import ListExpression as CQLListExpression
        from ...parser.ast_nodes import Property as _CQLProperty

        if isinstance(node, _CQLProperty) and node.path == "codes":
            base = self._static_clinical_value_object(node.source)
            if isinstance(base, dict) and isinstance(base.get("codes"), list):
                return [c for c in base["codes"] if isinstance(c, dict)]
            return None
        if isinstance(node, CQLListExpression):
            codes: list[dict[str, Any]] = []
            for item in node.elements:
                value = self._static_clinical_value_object(item)
                if not (isinstance(value, dict) and value.get("code") is not None):
                    return None
                codes.append(value)
            return codes
        return None

    def _translate_static_clinical_equality(
        self,
        expr: BinaryExpression,
        operator: str,
    ) -> Optional[SQLExpression]:
        left_type = self._static_clinical_type(expr.left)
        right_type = self._static_clinical_type(expr.right)
        if left_type not in {"Code", "Concept"} or right_type not in {"Code", "Concept"}:
            return None

        left_value = self._static_clinical_value_object(expr.left)
        right_value = self._static_clinical_value_object(expr.right)
        if left_value is None or right_value is None:
            return None

        if set(left_value.keys()) != set(right_value.keys()):
            return SQLNull()

        result: SQLExpression = SQLLiteral(value=left_value == right_value)
        if operator in ("!=", "not equal"):
            result = SQLCase(
                when_clauses=[
                    (
                        SQLUnaryOp(operator="IS NULL", operand=result, prefix=False),
                        SQLNull(),
                    )
                ],
                else_clause=SQLUnaryOp(operator="NOT", operand=result),
            )
        return result


    def _resolve_code_ref_for_dynamic_equality(self, ast) -> Optional[dict]:
        """Resolve a single-code (non-Concept) static Code reference.

        Supports the shapes the equivalence path resolves for `~`
        (CodeSelector literals, `code X:` declarations via
        context.get_code, library-qualified references, and define aliases
        whose source is a static Code literal). Returns None for Concepts,
        dynamic expressions, and query aliases.
        """
        from ...parser.ast_nodes import (
            CodeSelector,
            Identifier,
            QualifiedIdentifier,
        )

        if isinstance(ast, CodeSelector):
            system_url = self.context.codesystems.get(ast.system, ast.system)
            return {
                "code": ast.code,
                "codesystem": system_url,
                "version": getattr(ast, "version", None),
                "display": ast.display,
            }
        if isinstance(ast, Identifier):
            if self.context.is_alias(ast.name):
                return None
            info = self.context.get_code(ast.name)
            if info is not None and not info.get("is_concept"):
                return info
            source_ast = self._definition_source_ast(ast.name, ast)
            if source_ast is not None:
                static_value = self._static_clinical_value_object(source_ast)
                if (
                    isinstance(static_value, dict)
                    and static_value.get("code")
                    and not isinstance(static_value.get("codes"), list)
                ):
                    return {
                        "code": static_value.get("code", ""),
                        "codesystem": static_value.get("system", ""),
                        "version": static_value.get("version"),
                        "display": static_value.get("display"),
                    }
            return None
        if isinstance(ast, QualifiedIdentifier) and len(ast.parts) >= 2:
            info = self.context.get_code(ast.parts[-1])
            if info is not None and not info.get("is_concept"):
                return info
        return None

    def _translate_dynamic_code_equality(
        self, expr: BinaryExpression, operator: str
    ) -> Optional[SQLExpression]:
        """CQL-21 EXPLORER QA-001: Equal/NotEqual between a static Code
        literal and a dynamically retrieved code value.

        CQL 1.5 Authors Guide: `=` on codes is an exact match considering
        code, system, version, and display (unlike `~`, which ignores
        version and display). Lowered through coding_matches_exact, which
        extracts the Coding and applies exact (case-sensitive) matching on
        the elements the literal defines. Null retrieved values propagate
        as SQL null; `!=` wraps the match in NOT.
        """
        if operator not in ("=", "!=", "not equal", "equal"):
            return None
        left_info = self._resolve_code_ref_for_dynamic_equality(expr.left)
        right_info = self._resolve_code_ref_for_dynamic_equality(expr.right)
        if bool(left_info) == bool(right_info):
            # Both static (handled by the static path) or neither (generic).
            return None
        code_info = left_info or right_info
        dynamic_ast = expr.right if left_info else expr.left
        dynamic_sql = self.translate(dynamic_ast, usage=ExprUsage.SCALAR)
        system_raw = code_info.get("codesystem", code_info.get("system", ""))
        system_url = self.context.codesystems.get(system_raw, system_raw)
        result: SQLExpression = SQLFunctionCall(
            name="coding_matches_exact",
            args=[
                dynamic_sql,
                SQLLiteral(value="code"),
                SQLLiteral(value=system_url or ""),
                SQLLiteral(value=code_info.get("code", "")),
                SQLLiteral(value=code_info.get("display")),
                SQLLiteral(value=code_info.get("version")),
            ],
        )
        if operator in ("!=", "not equal"):
            result = SQLUnaryOp(operator="NOT", operand=result)
        return result

    def _translate_in_op(self, operator, left, right, expr, boolean_context) -> SQLExpression:
        """Extracted from _translate_binary_expression."""
        def _code_entries_from_ast(node) -> Optional[list[dict[str, Any]]]:
            if isinstance(node, Literal) and node.value is None:
                return []
            if isinstance(node, ListExpression):
                entries: list[dict[str, Any]] = []
                for item in node.elements:
                    item_entries = _code_entries_from_ast(item)
                    if item_entries is None:
                        return None
                    entries.extend(item_entries)
                return entries
            if isinstance(node, CodeSelector):
                system = self.context.codesystems.get(node.system, node.system)
                entry = {"code": node.code, "system": system}
                if node.display is not None:
                    entry["display"] = node.display
                return [entry]
            if isinstance(node, Identifier):
                if self.context.is_alias(node.name):
                    return None
                info = self.context.get_code(node.name)
                if info is None:
                    return None
                if info.get("is_concept") or isinstance(info.get("codes"), list):
                    return [
                        dict(code)
                        for code in info.get("codes", [])
                        if isinstance(code, dict)
                    ]
                return [dict(info)] if info.get("code") else None
            if isinstance(node, QualifiedIdentifier) and node.parts:
                info = self.context.get_code(node.parts[-1])
                if info is None:
                    return None
                if info.get("is_concept") or isinstance(info.get("codes"), list):
                    return [
                        dict(code)
                        for code in info.get("codes", [])
                        if isinstance(code, dict)
                    ]
                return [dict(info)] if info.get("code") else None
            if isinstance(node, InstanceExpression):
                bare = self._bare_cql_type_name(node.type)
                fields: dict[str, Any] = {}
                # CQL-21 HISTORIAN QA-001 fix: Concept { codes: { Code {...} } }
                # parses the codes field as a ListExpression of Code
                # InstanceExpressions (not Literal). The prior Literal-only
                # guard skipped ListExpression values, leaving fields['codes']
                # unset, so the function returned None and the translator fell
                # through to generic JSON translation producing a non-FHIR
                # {codes:[...]} shape that the in_valueset UDF cannot navigate.
                # The fix recurses into each Code in the ListExpression.
                for element in node.elements:
                    value_expr = element.type
                    if isinstance(value_expr, Literal):
                        fields[element.name] = value_expr.value
                    elif (
                        bare == "Concept"
                        and element.name == "codes"
                        and isinstance(value_expr, ListExpression)
                    ):
                        codes_list: list[dict[str, Any]] = []
                        for item in value_expr.elements:
                            item_entries = _code_entries_from_ast(item)
                            if item_entries is None:
                                return None
                            codes_list.extend(item_entries)
                        fields[element.name] = codes_list
                if bare == "Code" and fields.get("code"):
                    return [fields]
                if bare == "Concept":
                    # CQL-02 HISTORIAN QA-002: `Concept { }` (no codes element)
                    # is a valid concept selector whose codes list is empty.
                    # Previously this returned None, falling through to the
                    # generic membership path which emitted invalid SQL such as
                    # `json_object() IN '{"id":...}'` for `Concept { } in CS`.
                    # A present-but-unparsed codes element still returns None
                    # (runtime evaluation) to avoid silently emptying concepts.
                    saw_codes_element = any(
                        element.name == "codes" for element in node.elements
                    )
                    if not saw_codes_element:
                        return []
                    if isinstance(fields.get("codes"), list):
                        return [
                            code for code in fields["codes"] if isinstance(code, dict)
                        ]
            return None

        def _string_codes_from_ast(node) -> Optional[list[str]]:
            if isinstance(node, Literal) and isinstance(node.value, str):
                return [node.value]
            if isinstance(node, Literal) and node.value is None:
                return []
            if isinstance(node, BinaryExpression) and node.operator == "as":
                return _string_codes_from_ast(node.left)
            if isinstance(node, ListExpression):
                codes: list[str] = []
                for item in node.elements:
                    item_codes = _string_codes_from_ast(item)
                    if item_codes is None:
                        return None
                    codes.extend(item_codes)
                return codes
            return None

        def _normalize_code_entry(entry: dict[str, Any]) -> dict[str, Any]:
            normalized = dict(entry)
            system = normalized.get("system", normalized.get("codesystem", ""))
            if system:
                normalized["system"] = self.context.codesystems.get(system, system)
            normalized.pop("codesystem", None)
            return normalized

        def _synthetic_code_resource(entry: dict[str, Any]) -> SQLLiteral:
            code = _normalize_code_entry(entry)
            coding = {"code": code.get("code", "")}
            if code.get("system") is not None:
                coding["system"] = code.get("system") or ""
            if code.get("display") is not None:
                coding["display"] = code.get("display")
            resource = {"resourceType": "Basic", "code": {"coding": [coding]}}
            return SQLLiteral(json.dumps(resource, separators=(",", ":")))

        def _or_chain(expressions: list[SQLExpression]) -> SQLExpression:
            if not expressions:
                return SQLLiteral(value=False)
            result = expressions[0]
            for expression in expressions[1:]:
                result = SQLBinaryOp(operator="OR", left=result, right=expression)
            return result

        def _is_definitely_null_operand(node: Any, translated: SQLExpression) -> bool:
            if isinstance(translated, SQLNull) or (
                isinstance(translated, SQLLiteral) and translated.value is None
            ):
                return True
            if isinstance(node, Literal) and node.value is None:
                return True
            if isinstance(node, BinaryExpression) and node.operator == "as":
                return _is_definitely_null_operand(node.left, translated)
            return False

        # CQL interval/list `in`: a null container/list argument returns false.
        if self._definitely_null_operand(expr.right, right):
            return SQLLiteral(value=False)

        # CQL §9 Included In interval-interval overload: `in` between two
        # intervals is accepted by the CQL grammar (inclusiveIntervalOperatorPhrase)
        # and the reference engine routes it through includedIn. Previously a
        # interval-valued left operand fell through to the point-in-interval
        # BETWEEN lowering and raised a DuckDB BinderException.
        left_interval = self._ensure_resource_to_interval(left, expr.left)
        if self._is_fhir_interval_expression(left_interval):
            cql_right = getattr(expr, 'right', None)
            precision = None
            right_for_interval = right
            if (isinstance(cql_right, BinaryExpression)
                    and cql_right.operator == 'precision of'
                    and hasattr(cql_right, 'left')
                    and hasattr(cql_right.left, 'value')):
                precision = str(cql_right.left.value).lower()
                right_for_interval = self.translate(cql_right.right, usage=ExprUsage.SCALAR)
            right_interval = self._ensure_resource_to_interval(
                right_for_interval, getattr(expr, 'right', None))
            if self._is_fhir_interval_expression(right_interval):
                l = self._unwrap_precision_wrapper(left_interval)
                r = self._unwrap_precision_wrapper(right_interval)
                if precision is not None:
                    return SQLFunctionCall(
                        name="intervalIncludedInPrecise",
                        args=[l, r, SQLLiteral(value=precision)],
                    )
                return SQLFunctionCall(name="intervalIncludedIn", args=[l, r])
        # Do NOT short-circuit when left is null — list `in` has special
        # null semantics: null in list → true if list has null elements.
        # (This is handled by the list_has_null check below.)
        # Handle "X in <precision> of <interval>" (e.g., X in day of Y)
        # Parser produces: BinaryExpression(operator='in',
        #   left=X, right=BinaryExpression(operator='precision of', left=Literal(unit), right=interval))
        if isinstance(expr.right, BinaryExpression) and expr.right.operator == "precision of":
            precision = getattr(expr.right.left, 'value', 'day')
            if isinstance(precision, str):
                precision = precision.lower()
            # Handle parser AND-inside-precision workaround
            actual_interval_ast = expr.right.right
            extra_conditions = []
            while isinstance(actual_interval_ast, BinaryExpression) and actual_interval_ast.operator == "and":
                extra_conditions.append(actual_interval_ast.right)
                actual_interval_ast = actual_interval_ast.left
            extra_condition_ast = None
            for cond in reversed(extra_conditions):
                if extra_condition_ast is None:
                    extra_condition_ast = cond
                else:
                    extra_condition_ast = BinaryExpression(operator="and", left=extra_condition_ast, right=cond)

            interval_expr = self.translate(actual_interval_ast, usage=ExprUsage.SCALAR)
            # CQL §19.11 In precision: dispatch to intervalContainsPrecise
            # when the interval is a recognized interval expression so that
            # partial-precision Date/DateTime/Time bounds propagate
            # uncertainty to NULL rather than collapsing to raw string
            # comparison (e.g., `@2024-06-15 in day of Interval[@2024,
            # @2024]` must return NULL, not False). The raw-SQL fallback
            # below remains for query-source / dynamic FHIR Period values
            # that are not statically recognized intervals.
            if self._is_fhir_interval_expression(interval_expr) or (
                isinstance(interval_expr, SQLFunctionCall)
                and interval_expr.name == "intervalFromBounds"
            ):
                left_for_precise = (
                    self._quantity_interval_point_arg(left)
                    if self._is_quantity_interval_sql(interval_expr)
                    else self._ensure_interval_varchar(left)
                )
                in_precise = SQLFunctionCall(
                    name="intervalContainsPrecise",
                    args=[interval_expr, left_for_precise, SQLLiteral(value=precision)],
                )
                if extra_condition_ast:
                    extra_sql = self.translate(extra_condition_ast, boolean_context=True)
                    return SQLBinaryOp(operator="AND", left=in_precise, right=extra_sql)
                return in_precise
            left_truncated = self._ensure_date_cast(
                self._truncate_to_precision(left, precision))

            interval_bounds = self._extract_interval_bounds(interval_expr, actual_interval_ast)
            if interval_bounds:
                right_start, right_end, low_closed, high_closed = interval_bounds
                start_truncated = self._ensure_date_cast(
                    self._truncate_to_precision(right_start, precision))
                end_truncated = self._ensure_date_cast(
                    self._truncate_to_precision(right_end, precision))
                start_op = ">=" if low_closed else ">"
                end_op = "<=" if high_closed else "<"
                start_check = SQLBinaryOp(operator=start_op, left=left_truncated, right=start_truncated)
                end_check = SQLBinaryOp(operator=end_op, left=left_truncated, right=end_truncated)
            else:
                right_start = SQLFunctionCall(name="intervalStart", args=[interval_expr])
                right_end = SQLFunctionCall(name="intervalEnd", args=[interval_expr])
                start_truncated = self._ensure_date_cast(
                    self._truncate_to_precision(right_start, precision))
                end_truncated = self._ensure_date_cast(
                    self._truncate_to_precision(right_end, precision))
                start_check = SQLBinaryOp(operator=">=", left=left_truncated, right=start_truncated)
                end_check = SQLBinaryOp(operator="<=", left=left_truncated, right=end_truncated)

            in_result = SQLBinaryOp(operator="AND", left=start_check, right=end_check)
            if extra_condition_ast:
                extra_sql = self.translate(extra_condition_ast, boolean_context=True)
                return SQLBinaryOp(operator="AND", left=in_result, right=extra_sql)
            return in_result

        # IN operator - left is SCALAR, right is LIST (for ListExpression) or SCALAR (for Interval)
        # Gap 7: Check if right side is an Identifier referencing a valueset
        # Also handle ParameterPlaceholder from function inlining (e.g. hasPrincipalDiagnosisOf(valueSet))
        vs_name: Optional[str] = None
        vs_url: Optional[str] = None
        if isinstance(expr.right, Identifier):
            vs_name = expr.right.name
        elif isinstance(expr.right, ParameterPlaceholder):
            # Function inlining substitutes ValueSet parameters with ParameterPlaceholder
            # whose sql_expr is the translated argument (typically SQLIdentifier for valueset names)
            vs_url = self._valueset_url_from_placeholder(expr.right)
            if vs_url is None and isinstance(expr.right.sql_expr, SQLIdentifier):
                vs_name = expr.right.sql_expr.name
        if vs_name is not None:
            vs_url = self._resolve_valueset_identifier(vs_name)
        if vs_url:
            if _is_definitely_null_operand(expr.left, left):
                return SQLLiteral(value=False)
            static_code_entries = _code_entries_from_ast(expr.left)
            if static_code_entries is not None:
                return _or_chain([
                    SQLFunctionCall(
                        name="in_valueset",
                        args=[_synthetic_code_resource(entry), SQLLiteral("code"), SQLLiteral(vs_url)],
                    )
                    for entry in static_code_entries
                ])
            static_string_codes = _string_codes_from_ast(expr.left)
            if static_string_codes is not None:
                return _or_chain([
                    SQLFunctionCall(
                        name="in_valueset",
                        args=[
                            _synthetic_code_resource({"system": "", "code": code}),
                            SQLLiteral("code"),
                            SQLLiteral(vs_url),
                        ],
                    )
                    for code in static_string_codes
                ])
            # If left is fhirpath_text(resource, path), extract resource and path
            # so in_valueset operates on the resource with the property path
            if (isinstance(left, SQLFunctionCall)
                    and left.name in ('fhirpath_text', 'fhirpath_date')
                    and len(left.args) == 2):
                resource_arg = left.args[0]
                path_arg = left.args[1]
            else:
                resource_arg = left
                path_arg = SQLLiteral("code")
            # When the resource argument is a list-returning
            # expression (e.g. encounterDiagnosis() results),
            # unwrap into EXISTS + unnest so in_valueset receives
            # individual resources, not the whole list.
            if _is_list_returning_sql(resource_arg):
                _iv_param = "_ivr"
                _inner_from = SQLSubquery(query=SQLSelect(
                    columns=[SQLAlias(
                        expr=SQLFunctionCall(
                            name="unnest", args=[resource_arg]),
                        alias=_iv_param,
                    )],
                ))
                _iv_select = SQLSelect(
                    columns=[SQLLiteral(1)],
                    from_clause=SQLAlias(
                        expr=_inner_from, alias="_ivt"),
                    where=SQLFunctionCall(
                        name="in_valueset",
                        args=[
                            SQLIdentifier(name=_iv_param),
                            path_arg,
                            SQLLiteral(vs_url),
                        ],
                    ),
                )
                return SQLExists(
                    subquery=SQLSubquery(query=_iv_select))
            return SQLFunctionCall(
                name="in_valueset",
                args=[resource_arg, path_arg, SQLLiteral(vs_url)],
            )

        if isinstance(expr.right, Identifier):
            # CQL-02 HISTORIAN QA-001: resolve both direct codesystem names and
            # define aliases of codesystem references to the canonical URL.
            codesystem_url = self._resolve_codesystem_identifier(expr.right.name)
        else:
            codesystem_url = None
        if codesystem_url is not None:
            if _is_definitely_null_operand(expr.left, left):
                return SQLLiteral(value=False)
            static_code_entries = _code_entries_from_ast(expr.left)
            if static_code_entries is not None:
                return SQLLiteral(
                    value=any(
                        _normalize_code_entry(entry).get("system", "") == codesystem_url
                        for entry in static_code_entries
                    )
                )
            static_string_codes = _string_codes_from_ast(expr.left)
            if static_string_codes is not None:
                # CQL 1.5.3 §In (Codesystem) — String overload: "if the given
                # code system contains a code with an equivalent code element,
                # the result is true." Without a runtime terminology service
                # for CodeSystem membership (unlike ValueSet's in_valueset
                # UDF), the translator cannot know whether the codesystem
                # contains the given code. Previously this returned TRUE for
                # any non-empty string, masking the membership check entirely.
                # Per GLOBAL_RULES.md §CQL Translator Invariants ("Do not use
                # silent fallbacks that mask schema, context, or translation
                # errors"), raise a TranslationError so the missing capability
                # is surfaced rather than silently producing wrong results.
                # Null/empty-string inputs return False per the spec's
                # "If the code argument is null, the result is false" rule.
                if all(code == "" for code in static_string_codes):
                    return SQLLiteral(value=False)
                raise TranslationError(
                    f"String 'in CodeSystem' membership for "
                    f"{expr.right.name!r} ({codesystem_url!r}) is unsupported: "
                    f"CQL requires a terminology service to verify code "
                    f"membership in an externally-defined code system. "
                    f"Use a Code-typed operand or supply the code system "
                    f"definition at translation time."
                )
            if (
                isinstance(left, SQLFunctionCall)
                and left.name in ("fhirpath_text", "fhirpath_date", "fhirpath_scalar", "fhirpath_json")
                and len(left.args) == 2
            ):
                resource_arg = left.args[0]
                path_arg = left.args[1]
                if isinstance(path_arg, SQLLiteral) and isinstance(path_arg.value, str):
                    escaped_system = escape_fhirpath_string_literal(codesystem_url)
                    path = path_arg.value
                    fhirpath_expr = (
                        f"({path}.coding.where(system='{escaped_system}').exists() "
                        f"or {path}.where(system='{escaped_system}').exists())"
                    )
                    return SQLFunctionCall(
                        name="fhirpath_bool",
                        args=[resource_arg, SQLLiteral(fhirpath_expr)],
                    )
        if self._is_list_operands(right, left, expr):
            return self._list_contains_call(right, left, expr.right, expr.left)
        if isinstance(expr.right, ListExpression):
            # IN list - translate left as SCALAR, list elements as LIST context
            left = self.translate(expr.left, usage=ExprUsage.SCALAR)
            list_elements = [self.translate(e, usage=ExprUsage.SCALAR) for e in expr.right.elements]
            array = SQLArray(elements=list_elements)
            return self._list_contains_call(array, left, expr.right, expr.left)
        # Check if right is an Interval - use BETWEEN
        if isinstance(expr.right, Interval):
            interval = self.translate(expr.right, usage=ExprUsage.SCALAR)
            if isinstance(interval, SQLInterval):
                # If bounds are Quantity expressions, delegate to intervalContains UDF
                # to avoid type mismatch between scalar and VARCHAR Quantity bounds
                low_is_qty = _is_quantity_expression(interval.low) if interval.low else False
                high_is_qty = _is_quantity_expression(interval.high) if interval.high else False
                if low_is_qty or high_is_qty:
                    # Build interval from bounds and use intervalContains
                    low_bound = SQLCast(expression=interval.low, target_type="VARCHAR") if interval.low else SQLNull()
                    high_bound = SQLCast(expression=interval.high, target_type="VARCHAR") if interval.high else SQLNull()
                    interval_expr = SQLFunctionCall(
                        name="intervalFromBounds",
                        args=[
                            low_bound, high_bound,
                            SQLLiteral(value=interval.low_closed),
                            SQLLiteral(value=interval.high_closed),
                        ],
                    )
                    point_str = self._quantity_interval_point_arg(left)
                    return SQLFunctionCall(name="intervalContains", args=[interval_expr, point_str])

                # Generate BETWEEN syntax
                low_sql = interval.low
                high_sql = interval.high
                # When comparing a numeric value against Quantity bounds,
                # extract the numeric value from parse_quantity() calls.
                for bound_name in ("low_sql", "high_sql"):
                    bound = low_sql if bound_name == "low_sql" else high_sql
                    if isinstance(bound, SQLFunctionCall) and bound.name == "parse_quantity":
                        qty_val = self._extract_quantity_numeric_value(bound)
                        if qty_val is not None:
                            if bound_name == "low_sql":
                                low_sql = qty_val
                            else:
                                high_sql = qty_val
                # Handle closed/open bounds
                # Check if either bound is null (unbounded interval)
                low_is_null = isinstance(low_sql, SQLNull) or (isinstance(low_sql, SQLLiteral) and low_sql.value is None)
                high_is_null = isinstance(high_sql, SQLNull) or (isinstance(high_sql, SQLLiteral) and high_sql.value is None)
                if not low_is_null and not high_is_null and interval.low_closed and interval.high_closed:
                    # CQL §Age/§22.21: age and duration operands are
                    # scalar-or-interval VARCHAR; `in Interval[a, b]` must
                    # lower to uncertainty-aware comparisons (a raw SQL
                    # BETWEEN would mix VARCHAR with numeric bounds).
                    if self._is_uncertain_between_expr(expr.left) or _is_uncertain_between_sql(left):
                        conditions = [
                            SQLFunctionCall(
                                name="cqlUncertainCompare",
                                args=[
                                    SQLCast(expression=left, target_type="VARCHAR"),
                                    SQLCast(expression=low_sql, target_type="VARCHAR"),
                                    SQLLiteral(value=">="),
                                ],
                            ),
                            SQLFunctionCall(
                                name="cqlUncertainCompare",
                                args=[
                                    SQLCast(expression=left, target_type="VARCHAR"),
                                    SQLCast(expression=high_sql, target_type="VARCHAR"),
                                    SQLLiteral(value="<="),
                                ],
                            ),
                        ]
                        return SQLBinaryOp(operator="AND", left=conditions[0], right=conditions[1])
                    # [a, b] -> x BETWEEN a AND b
                    return SQLBinaryOp(
                        operator="BETWEEN",
                        left=left,
                        right=SQLFunctionCall(name="__between_args__", args=[low_sql, high_sql]),
                        precedence=PRECEDENCE["BETWEEN"],
                    )
                else:
                    # For open bounds, use comparison operators
                    # (a, b) -> x > a AND x < b
                    # [a, b) -> x >= a AND x < b
                    # (a, b] -> x > a AND x <= b
                    conditions = []
                    # CQL §Age/§22.21: age/duration operands are
                    # scalar-or-interval VARCHAR; use uncertainty-aware
                    # comparisons instead of raw SQL operators.
                    uncertain_operand = (
                        self._is_uncertain_between_expr(expr.left)
                        or _is_uncertain_between_sql(left)
                    )
                    if not low_is_null and interval.low is not None:
                        op_low = ">=" if interval.low_closed else ">"
                        if uncertain_operand:
                            conditions.append(SQLFunctionCall(
                                name="cqlUncertainCompare",
                                args=[
                                    SQLCast(expression=left, target_type="VARCHAR"),
                                    SQLCast(expression=low_sql, target_type="VARCHAR"),
                                    SQLLiteral(value=op_low),
                                ],
                            ))
                        else:
                            conditions.append(SQLBinaryOp(operator=op_low, left=left, right=low_sql))
                    if not high_is_null and interval.high is not None:
                        op_high = "<=" if interval.high_closed else "<"
                        if uncertain_operand:
                            conditions.append(SQLFunctionCall(
                                name="cqlUncertainCompare",
                                args=[
                                    SQLCast(expression=left, target_type="VARCHAR"),
                                    SQLCast(expression=high_sql, target_type="VARCHAR"),
                                    SQLLiteral(value=op_high),
                                ],
                            ))
                        else:
                            conditions.append(SQLBinaryOp(operator=op_high, left=left, right=high_sql))
                    if len(conditions) == 2:
                        return SQLBinaryOp(operator="AND", left=conditions[0], right=conditions[1])
                    elif len(conditions) == 1:
                        return conditions[0]
                    # Both bounds null: per CQL §19.14, if the interval is null, result is false.
                    # Interval[null, null] with untyped nulls is a null interval (§5.4).
                    return SQLLiteral(value=False)
        if self._is_fhir_interval_expression(right):
            return SQLFunctionCall(
                name="intervalContains",
                args=[
                    right,
                    self._quantity_interval_point_arg(left)
                    if self._is_quantity_interval_sql(right)
                    else self._ensure_interval_varchar(left),
                ],
            )
        # Otherwise, regular IN operator.
        # When the right side is fhirpath_text (returns only the first
        # value), convert to list_contains so all values are checked.
        # CQL `in` on a list means membership — the right side may be
        # multi-valued (e.g., claimItem.diagnosisSequence).
        if (
            isinstance(right, SQLFunctionCall)
            and right.name == "fhirpath_text"
            and len(right.args) == 2
        ):
            all_values = SQLFunctionCall(
                name="from_json",
                args=[
                    SQLFunctionCall(name="fhirpath", args=right.args),
                    SQLLiteral(value='["VARCHAR"]'),
                ],
            )
            return SQLFunctionCall(
                name="list_contains", args=[all_values, left],
            )
        sql_op = BINARY_OPERATOR_MAP.get(operator, operator)
        return SQLBinaryOp(operator=sql_op, left=left, right=right)


    def _translate_tuple_comparison(self, expr: "BinaryExpression", operator: str) -> "SQLExpression":
        """Translate tuple = / != with CQL §12.1 null propagation.

        CQL tuple equality per element:
          both null  → true
          one null   → null  (uncertainty)
          both present → normal =
        AND-chain gives: false if ANY mismatch, null if no mismatch but uncertainty.
        """
        left_tup = expr.left
        right_tup = expr.right

        left_elems = {e.name: e for e in left_tup.elements}
        right_elems = {e.name: e for e in right_tup.elements}
        all_names = sorted(set(left_elems.keys()) | set(right_elems.keys()))

        comparisons: list["SQLExpression"] = []
        for name in all_names:
            le = left_elems.get(name)
            re = right_elems.get(name)
            if le and re:
                lv = self.translate(le.type, boolean_context=False)
                rv = self.translate(re.type, boolean_context=False)
                # CQL: both null → true, one null → null, both present → =
                lv_is_null = SQLUnaryOp(operator="IS NULL", operand=lv, prefix=False)
                rv_is_null = SQLUnaryOp(operator="IS NULL", operand=rv, prefix=False)
                semantic_equal = self.translate(
                    BinaryExpression(
                        operator="=",
                        left=le.type,
                        right=re.type,
                        strict=getattr(expr, "strict", False),
                    ),
                    usage=ExprUsage.BOOLEAN,
                )
                elem_cmp = SQLCase(
                    when_clauses=[
                        (SQLBinaryOp(operator="AND",
                                     left=lv_is_null,
                                     right=rv_is_null),
                         SQLLiteral(value=True)),
                        (SQLBinaryOp(operator="OR",
                                     left=lv_is_null,
                                     right=rv_is_null),
                         SQLNull()),
                    ],
                    else_clause=semantic_equal,
                )
                comparisons.append(elem_cmp)
            else:
                comparisons.append(SQLLiteral(value=False))

        if not comparisons:
            result: "SQLExpression" = SQLLiteral(value=True)
        elif len(comparisons) == 1:
            result = comparisons[0]
        else:
            result = comparisons[0]
            for c in comparisons[1:]:
                result = SQLBinaryOp(operator="AND", left=result, right=c)

        if operator in ("!=", "not equal"):
            result = SQLUnaryOp(operator="NOT", operand=result)

        return result


    def _translate_union_op(self, operator, left, right, expr) -> SQLExpression:
        """Extracted from _translate_binary_expression."""
        left_is_rows = isinstance(left, (SQLSelect, SQLSubquery, SQLUnion, SQLExcept, SQLIntersect))
        right_is_rows = isinstance(right, (SQLSelect, SQLSubquery, SQLUnion, SQLExcept, SQLIntersect))

        # CQL-19 SKEPTIC QA-003: CQL 1.5 §10.25 list union needs the full
        # element list on BOTH operands. Three operand shapes arrived rows-
        # shaped or scalar-truncated and broke the list branches below:
        #   (a) dynamic multi-valued FHIR properties (scalar fhirpath_text,
        #       first-node truncation) -> list_concat(VARCHAR, VARCHAR[])
        #       BinderException;
        #   (b) stored-list define identifiers (dynamic-list defines like
        #       `define G: Patient.name.given`) -> rows-shaped
        #       (SELECT * FROM "G") that the Distinct wrap rejects as a
        #       multi-column subquery;
        #   (c) property paths over retrieve aliases
        #       (`Obs.component.code.coding.code`) -> rows-shaped CTE scans.
        # Retrieve/Query operands keep their row shape (resource unions).
        from ...parser.ast_nodes import Identifier as CQLIdentifier, Property as CQLProperty

        def _operand_rows_shaped(sql_node, ast_node) -> bool:
            if isinstance(sql_node, (SQLSelect, SQLSubquery, SQLUnion, SQLExcept, SQLIntersect, RetrievePlaceholder)):
                return True
            if isinstance(ast_node, CQLIdentifier):
                _m = self.context.definition_meta.get(ast_node.name)
                return _m is not None and getattr(_m, "has_resource", False)
            return False

        def _union_operand_as_list(sql_node, ast_node, is_rows, peer_rows=False):
            """Return (list_sql, converted); converted=True when the operand
            was re-shaped into a single list value per patient and must not
            be treated as a rows operand below."""
            if isinstance(ast_node, CQLIdentifier):
                meta = self.context.definition_meta.get(ast_node.name)
                if meta is not None and getattr(meta, "stores_list_value", False):
                    # Stored-list define: scalar translation yields the
                    # whole element list held in the CTE value column.
                    return self.translate(ast_node, usage=ExprUsage.SCALAR), True
                # CQL-19 EXPLORER QA-001: element-rows value defines
                # (`define CondIds: [Condition] C return C.id`) hold one row
                # per element; a union operand must be the per-patient
                # element LIST, not the 2-column rows scan. Only convert
                # when the PEER operand is also element-list-shaped — with a
                # rows-shaped peer (retrieves, resource defines) the union
                # must keep rows semantics (DQM resource unions, CMS117/
                # CMS645 regression guard).
                if (
                    meta is not None
                    and not getattr(meta, "has_resource", False)
                    and meta.shape == RowShape.PATIENT_MULTI_VALUE
                    and not peer_rows
                ):
                    _list_sql = self._list_operator_full_list_source(ast_node)
                    if _list_sql is not None:
                        return _list_sql, True
            if is_rows and isinstance(ast_node, CQLProperty):
                static_type = self._static_structural_type_name(ast_node) or ""
                if not static_type.startswith("Interval<"):
                    list_sql = self.translate(ast_node, usage=ExprUsage.LIST)
                    # LIST usage over a multi-valued navigation yields a
                    # one-row list-valued subquery
                    # (COALESCE(flatten(LIST(...)), [])) — accepted; a bare
                    # rows scan (SELECT * FROM cte) is not list-valued and
                    # keeps its rows shape.
                    if _is_list_returning_sql(list_sql):
                        return list_sql, True
            promoted = _promote_fhirpath_text_list(sql_node)
            return promoted, promoted is not sql_node

        _right_peer_rows = _operand_rows_shaped(right, getattr(expr, "right", None))
        _left_peer_rows = _operand_rows_shaped(left, getattr(expr, "left", None))
        left, _left_converted = _union_operand_as_list(
            left, getattr(expr, "left", None), left_is_rows, peer_rows=_right_peer_rows
        )
        right, _right_converted = _union_operand_as_list(
            right, getattr(expr, "right", None), right_is_rows, peer_rows=_left_peer_rows
        )
        # RetrievePlaceholder is not a rows SQL type but is rows-shaped
        # (converted to a subquery by _as_subquery below) — keep it rows
        # so the retrieve-UNION cases still fire (DQM resource unions).
        left_is_rows = not _left_converted and (
            isinstance(left, (SQLSelect, SQLSubquery, SQLUnion, SQLExcept, SQLIntersect, RetrievePlaceholder))
        )
        right_is_rows = not _right_converted and (
            isinstance(right, (SQLSelect, SQLSubquery, SQLUnion, SQLExcept, SQLIntersect, RetrievePlaceholder))
        )

        # CQL §19.31: Interval union — use intervalUnion UDF which returns
        # null when intervals do not overlap or meet.
        # Null propagation for intervals: §19.31 says null → null.
        if not left_is_rows and not right_is_rows:
            left_is_interval = self._is_fhir_interval_expression(left)
            right_is_interval = self._is_fhir_interval_expression(right)
            # CQL-17 SKEPTIC QA-001: `(null as Interval<T>)` lowers to a null
            # CASE that is neither an SQLNull nor recognized by
            # _is_fhir_interval_expression, so the union dispatch fell into
            # list-union semantics (jsonConcat) and raised a BinderException
            # on valid CQL. §19.31 requires interval-union routing whenever
            # both operands are interval-typed; resolve the CQL AST type.
            for node in (expr.left, expr.right):
                static_type = self._static_structural_type_name(node)
                if static_type and static_type.startswith("Interval<"):
                    if node is expr.left:
                        left_is_interval = True
                    else:
                        right_is_interval = True
            if left_is_interval and right_is_interval:
                return SQLFunctionCall(name="intervalUnion", args=[left, right])
            if (left_is_interval or right_is_interval) and (isinstance(left, SQLNull) or isinstance(right, SQLNull)):
                return SQLNull()

        # CQL §20.29: List union — null is treated as empty list.
        # Return the non-null operand instead of propagating null.
        # CQL-19 HISTORIAN QA-003: a statically-null list operand
        # (`(null as List<T>)`, lowering to an all-NULL SQLCase, and the
        # untyped `null` in a list context) must be treated the same as a
        # literal SQLNull — otherwise promoted dynamic list operands fall
        # through to the jsonConcat fallback which NESTS the list
        # (`Patient.name.given union null` -> [[...]] instead of [...]).
        if not left_is_rows and not right_is_rows:
            _left_is_null = isinstance(left, SQLNull) or self._is_static_null_case(left)
            _right_is_null = isinstance(right, SQLNull) or self._is_static_null_case(right)
            if _left_is_null and _right_is_null:
                return SQLArray([])
            if _left_is_null:
                return right
            if _right_is_null:
                return left

        # CQL union -> SQL UNION ALL (preserves duplicates)
        # Use the already-translated SCALAR operands but normalize for union.
        # Widening single-column selects to SELECT * ensures column parity.
        def _as_subquery(expr):
            if isinstance(expr, SQLSelect):
                expr = SQLSubquery(query=expr)
            if isinstance(expr, RetrievePlaceholder):
                return SQLSubquery(query=expr)
            # Normalize subqueries for union column parity
            if isinstance(expr, SQLSubquery) and isinstance(expr.query, SQLSelect):
                inner = expr.query
                cols = inner.columns or []
                from_clause = inner.from_clause
                # Handle aliased FROM (e.g., FROM "CTE" AS sub)
                if isinstance(from_clause, SQLAlias) and isinstance(from_clause.expr, SQLIdentifier):
                    from_ident = from_clause.expr
                elif isinstance(from_clause, SQLIdentifier):
                    from_ident = from_clause
                else:
                    from_ident = None
                # Widen narrow scalar CTE references to SELECT * for
                # consistent UNION column parity.  Only widen simple
                # CTE references that have no WHERE clause — if the
                # query has a WHERE, preserve it to avoid dropping
                # filters (e.g., from inlined library functions).
                #
                # Special case: strip patient_id correlation added by
                # SCALAR-context translation.  In UNION context each
                # branch must produce ALL rows; the patient scoping
                # is applied later by CTE wrapping.  Pattern:
                #   WHERE sub.patient_id = <alias>.patient_id
                effective_where = inner.where
                if effective_where is not None and _is_patient_id_correlation(effective_where):
                    effective_where = None

                if (len(cols) >= 1 and len(cols) <= 2
                        and from_ident and from_ident.quoted
                        and not inner.joins):
                    if effective_where is None:
                        return SQLSubquery(query=SQLSelect(
                            columns=[SQLIdentifier(name="*")],
                            from_clause=from_ident,
                        ))
                    else:
                        return SQLSubquery(query=SQLSelect(
                            columns=[SQLIdentifier(name="*")],
                            from_clause=inner.from_clause,
                            where=effective_where,
                        ))
            return expr

        # CQL-19 SKEPTIC QA-003: do not widen list operands re-translated
        # above into star subqueries — they carry one list value per patient.
        # RetrievePlaceholder operands are NOT rows-typed but _as_subquery
        # is what converts them to subqueries (retrieve unions, DQM path).
        left = left if _left_converted else _as_subquery(left)
        right = right if _right_converted else _as_subquery(right)

        # Case 1: Both operands are subqueries (from retrieves or query expressions)
        if left_is_rows and right_is_rows and isinstance(left, SQLSubquery) and isinstance(right, SQLSubquery):
            operands = [left, right]
            use_distinct = not self._check_union_disjointness(operands)
            return SQLUnion(operands=operands, distinct=use_distinct)

        # Case 2: One operand is SQLUnion, other is subquery - flatten
        if left_is_rows and right_is_rows and isinstance(left, SQLUnion) and isinstance(right, SQLSubquery):
            operands = left.operands + [right]
            use_distinct = not self._check_union_disjointness(operands)
            return SQLUnion(operands=operands, distinct=use_distinct)
        if left_is_rows and right_is_rows and isinstance(left, SQLSubquery) and isinstance(right, SQLUnion):
            operands = [left] + right.operands
            use_distinct = not self._check_union_disjointness(operands)
            return SQLUnion(operands=operands, distinct=use_distinct)

        # Case 3: Both are SQLUnion - merge them
        if isinstance(left, SQLUnion) and isinstance(right, SQLUnion):
            operands = left.operands + right.operands
            use_distinct = not self._check_union_disjointness(operands)
            return SQLUnion(operands=operands, distinct=use_distinct)

        # Case 4: One or both are function calls (e.g., jsonConcat from nested unions)
        # Try to extract subqueries from function calls
        if isinstance(left, SQLFunctionCall) or isinstance(right, SQLFunctionCall):
            left_subqueries = self._extract_subqueries_from_union(left)
            right_subqueries = self._extract_subqueries_from_union(right)
            if left_subqueries or right_subqueries:
                all_subqueries = left_subqueries + right_subqueries
                if len(all_subqueries) > 1:
                    use_distinct = not self._check_union_disjointness(all_subqueries)
                    return SQLUnion(operands=all_subqueries, distinct=use_distinct)

        # Case 5: One or both operands are set operations (INTERSECT/EXCEPT).
        # Wrap each set op in SQLSubquery so it can participate in UNION.
        set_op_types = (SQLIntersect, SQLExcept)
        left_is_set = isinstance(left, set_op_types)
        right_is_set = isinstance(right, set_op_types)
        if left_is_set or right_is_set:
            def _wrap_set_op(set_op):
                """Wrap a set op in SQLSubquery, stripping patient_id correlation."""
                normalized_ops = []
                for op in set_op.operands:
                    normalized_ops.append(_normalize_for_union(op))
                return SQLSubquery(query=type(set_op)(operands=normalized_ops))

            def _normalize_for_union(op):
                """Strip patient_id correlation from a set operand."""
                if isinstance(op, SQLSubquery) and isinstance(op.query, SQLSelect):
                    inner = op.query
                    if inner.where is not None and _is_patient_id_correlation(inner.where):
                        from_clause = inner.from_clause
                        if isinstance(from_clause, SQLAlias) and isinstance(from_clause.expr, SQLIdentifier):
                            from_ident = from_clause.expr
                        elif isinstance(from_clause, SQLIdentifier):
                            from_ident = from_clause
                        else:
                            return op
                        return SQLSubquery(query=SQLSelect(
                            columns=[SQLIdentifier(name="*")],
                            from_clause=from_ident,
                        ))
                elif isinstance(op, SQLUnion):
                    # Normalize each operand of a nested UNION
                    normalized = [_normalize_for_union(u) for u in op.operands]
                    return SQLUnion(operands=normalized, distinct=op.distinct)
                return op

            left_norm = _wrap_set_op(left) if left_is_set else left
            right_norm = _wrap_set_op(right) if right_is_set else right
            if isinstance(left_norm, SQLSubquery) and isinstance(right_norm, SQLSubquery):
                operands = [left_norm, right_norm]
                use_distinct = not self._check_union_disjointness(operands)
                return SQLUnion(operands=operands, distinct=use_distinct)
            if isinstance(left_norm, SQLUnion) and isinstance(right_norm, SQLSubquery):
                operands = left_norm.operands + [right_norm]
                use_distinct = not self._check_union_disjointness(operands)
                return SQLUnion(operands=operands, distinct=use_distinct)
            if isinstance(left_norm, SQLSubquery) and isinstance(right_norm, SQLUnion):
                operands = [left_norm] + right_norm.operands
                use_distinct = not self._check_union_disjointness(operands)
                return SQLUnion(operands=operands, distinct=use_distinct)

        # Case 6: Both are SQL arrays (list literals) → use list_concat
        if isinstance(left, SQLArray) and isinstance(right, SQLArray):
            return SQLFunctionCall(
                name='"Distinct"',
                args=[SQLFunctionCall(name="list_concat", args=[left, right])],
            )

        # Case 6a: Both operands are typed list expressions (e.g., from CQL
        # `({} as List<Integer>)` or `(null as List<Integer>)`). Use
        # list_concat + Distinct directly to preserve the typed element type.
        # Falling through to the jsonConcat fallback would return VARCHAR[],
        # mixing with the typed CASE arms and raising BinderException.
        # CQL §20.29: null in list union is treated as empty list. We wrap
        # each operand in COALESCE(<expr>, <typed-empty-array>) so runtime
        # NULL lists are treated as empty (preserving the typed element).
        # See CQL-19 HISTORIAN iter 1 QA-001.
        if (self._is_typed_list_expr(left) and self._is_typed_list_expr(right)
                and not left_is_rows and not right_is_rows):
            left_typed_empty = self._typed_empty_array_for(left)
            right_typed_empty = self._typed_empty_array_for(right)
            # Both-NULL-typed-list case: CQL §20.29 says null is treated as
            # empty list, so both-null = empty list. We need to return a
            # typed empty array (or empty untyped SQLArray; the surrounding
            # context will accept it). The pre-existing test
            # `UnionNullBoth` exercises this.
            if left_typed_empty is None and right_typed_empty is None:
                # Try to detect that both operands lower to runtime NULL
                # (e.g., SQLCase with all-NULL arms). If so, return empty.
                if self._is_static_null_case(left) and self._is_static_null_case(right):
                    return SQLArray([])
            if left_typed_empty is not None and right_typed_empty is not None:
                left_safe = SQLFunctionCall(
                    name="COALESCE", args=[left, left_typed_empty]
                )
                right_safe = SQLFunctionCall(
                    name="COALESCE", args=[right, right_typed_empty]
                )
                return SQLFunctionCall(
                    name='"Distinct"',
                    args=[SQLFunctionCall(name="list_concat", args=[left_safe, right_safe])],
                )
            # If we cannot infer the typed empty array, fall back to list_concat
            # directly. (Both-null literal case is already handled by the
            # early-return at line 3577.)
            return SQLFunctionCall(
                name='"Distinct"',
                args=[SQLFunctionCall(name="list_concat", args=[left, right])],
            )

        # Case 6b: One array literal, one list expression → use list_concat.
        # CQL §20.29: null in list union is treated as empty list.
        # Use CASE WHEN IS NULL to handle runtime null accumulator (e.g., first iteration
        # of list_reduce). COALESCE(var, []) cannot be used here because DuckDB cannot
        # always infer the element type of an empty literal array.
        if isinstance(left, SQLArray) or isinstance(right, SQLArray):
            non_array = right if isinstance(left, SQLArray) else left
            array_side = left if isinstance(left, SQLArray) else right
            # Compile-time null: CQL §20.29 null = empty list → return the array side
            if isinstance(non_array, SQLNull):
                return array_side
            # Runtime-nullable list expression: null union [x] = [x] (CQL §20.29)
            null_check = SQLUnaryOp(operator="IS NULL", operand=non_array, prefix=False)
            if isinstance(left, SQLArray):
                concat = SQLFunctionCall(
                    name="list_concat", args=[array_side, non_array]
                )
            else:
                concat = SQLFunctionCall(
                    name="list_concat", args=[non_array, array_side]
                )
            inner = SQLFunctionCall(
                name='"Distinct"',
                args=[SQLCase(
                    when_clauses=[(null_check, array_side)],
                    else_clause=concat,
                )],
            )
            return inner

        # Case 6c: Both operands are list-returning expressions (e.g., two
        # promoted dynamic FHIR list projections). CQL 1.5 §10.25 list union
        # concatenates the element lists and deduplicates — routing through
        # the jsonConcat fallback wraps a whole list operand as a single
        # element (nested list). Null operands are treated as empty lists
        # (§10.25 / cqframework clinical_quality_language#887).
        if (
            not left_is_rows
            and not right_is_rows
            and not isinstance(left, SQLArray)
            and not isinstance(right, SQLArray)
            and _is_list_returning_sql(left)
            and _is_list_returning_sql(right)
        ):
            left_null = SQLUnaryOp(operator="IS NULL", operand=left, prefix=False)
            right_null = SQLUnaryOp(operator="IS NULL", operand=right, prefix=False)
            result = SQLFunctionCall(
                name='"Distinct"',
                args=[SQLCase(
                    when_clauses=[
                        (SQLBinaryOp(left=left_null, operator="AND", right=right_null), SQLArray([])),
                        (left_null, right),
                        (right_null, left),
                    ],
                    else_clause=SQLFunctionCall(name="list_concat", args=[left, right]),
                )],
            )
            # Mark the define as a single list value so the population wrap
            # does not LIST()-aggregate it into a nested list.
            result.result_type = "List<Any>"
            return result

        # Fallback: use jsonConcat UDF which handles scalars, lists, and JSON
        # values from subqueries. Wrap in order-preserving Distinct for CQL dedup.
        # CQL §20.29: For list union, null is treated as empty list — return
        # the other argument. Use COALESCE to handle runtime nulls.
        inner = SQLFunctionCall(
            name='"Distinct"',
            args=[SQLFunctionCall(name="jsonConcat", args=[left, right])],
        )
        if not left_is_rows and not right_is_rows:
            left_not_null = SQLUnaryOp(operator="IS NOT NULL", operand=left, prefix=False)
            right_not_null = SQLUnaryOp(operator="IS NOT NULL", operand=right, prefix=False)
            return SQLCase(
                when_clauses=[
                    (
                        SQLBinaryOp(
                            left=left_not_null,
                            operator="AND",
                            right=right_not_null,
                        ),
                        inner,
                    ),
                    (
                        left_not_null,
                        left,
                    ),
                    (
                        right_not_null,
                        right,
                    ),
                ],
                else_clause=SQLArray([]),
            )
        return inner

    def _promote_list_setop_scalar_operands(self, left, right, expr):
        """CQL-18 EXPLORER QA-001 residual: CQL 1.5 App B List Operators note
        that list operators may be invoked with singleton arguments when list
        promotion is enabled — a scalar operand alongside a list operand
        (`{1,3,5} except 3`, `CC except '8867-4'`) must be promoted to a
        singleton list before the list set-op macro, not passed as a bare
        scalar (DuckDB BinderException on array_length(scalar)).
        """
        from ...parser.ast_nodes import Interval as CQLInterval

        def _is_listy(sql, ast_node):
            return _is_list_returning_sql(sql) or (
                hasattr(self, "_is_list_typed_ast")
                and self._is_list_typed_ast(ast_node)
            )

        def _is_promotable_scalar(sql, ast_node):
            if isinstance(sql, (SQLNull, SQLSelect, SQLSubquery, SQLUnion,
                                SQLExcept, SQLIntersect)):
                return False
            if _is_listy(sql, ast_node):
                return False
            # Dynamic multi-valued FHIR properties lower to scalar
            # fhirpath_text here but are promoted to their full list
            # projection later in the list set-op call — wrapping them in
            # list_value() now would freeze the first-node truncation.
            if isinstance(sql, SQLFunctionCall) and sql.name in (
                "fhirpath_text", "fhirpath_date",
            ):
                return False
            if isinstance(ast_node, CQLInterval):
                return False
            return True

        if (
            _is_listy(left, getattr(expr, "left", None))
            and _is_promotable_scalar(right, getattr(expr, "right", None))
        ):
            right = SQLFunctionCall(name="list_value", args=[right])
        elif (
            _is_listy(right, getattr(expr, "right", None))
            and _is_promotable_scalar(left, getattr(expr, "left", None))
        ):
            left = SQLFunctionCall(name="list_value", args=[left])
        return left, right

    def _translate_intersect_op(self, operator, left, right, expr) -> SQLExpression:
        """Extracted from _translate_binary_expression."""
        left, right = self._promote_list_setop_scalar_operands(left, right, expr)
        if self._is_list_operands(left, right, expr):
            return self._list_intersect_call(left, right, expr.left, expr.right)
        # Row-producing operands -> SQL INTERSECT set operation
        left_is_rows = isinstance(left, (SQLSelect, SQLSubquery, SQLUnion, SQLIntersect))
        right_is_rows = isinstance(right, (SQLSelect, SQLSubquery, SQLUnion, SQLIntersect))
        if left_is_rows or right_is_rows:
            left_op = SQLSubquery(query=left) if isinstance(left, SQLSelect) else left
            right_op = SQLSubquery(query=right) if isinstance(right, SQLSelect) else right
            return SQLIntersect(operands=[left_op, right_op])
        # Interval intersect: if either operand is an interval expression or
        # the CQL AST has an Interval node, compute interval intersection
        from ...parser.ast_nodes import Interval as CQLInterval
        left_is_interval = (self._is_fhir_interval_expression(left) or isinstance(left, SQLInterval)
                            or isinstance(expr.left, CQLInterval))
        right_is_interval = (self._is_fhir_interval_expression(right) or isinstance(right, SQLInterval)
                             or isinstance(expr.right, CQLInterval))
        if left_is_interval or right_is_interval:
            # Use intervalIntersect UDF for type-safe comparison of interval bounds
            return SQLFunctionCall(name="intervalIntersect", args=[left, right])
        # Fallback: CQL intersect for literal lists.
        return self._list_intersect_call(left, right, expr.left, expr.right)

    @staticmethod
    def _precision_digit_count(precision: str) -> int | None:
        return {
            "year": 4,
            "month": 6,
            "week": 8,
            "day": 8,
            "hour": 10,
            "minute": 12,
            "second": 14,
            "millisecond": 17,
        }.get(str(precision).lower())

    @staticmethod
    def _time_precision_digit_count(precision: str) -> int | None:
        return {
            "hour": 2,
            "minute": 4,
            "second": 6,
            "millisecond": 9,
        }.get(str(precision).lower())

    def _runtime_temporal_precision_guard(
        self,
        precision: str,
        bounds: list[SQLExpression | tuple[SQLExpression | None, SQLExpression | None] | None],
    ) -> SQLExpression | None:
        required_digits = self._precision_digit_count(precision)
        if required_digits is None:
            return None

        guard = None
        for item in bounds:
            peer = None
            if isinstance(item, tuple):
                bound, peer = item
            else:
                bound = item
            if bound is None or isinstance(bound, (SQLNull, SQLLiteral)):
                continue
            text = SQLCast(expression=bound, target_type="VARCHAR")
            without_offset = SQLFunctionCall(
                name="regexp_replace",
                args=[text, SQLLiteral(value=r"(Z|[+-]\d{2}:\d{2})$"), SQLLiteral(value="")],
            )
            digits = SQLFunctionCall(
                name="regexp_replace",
                args=[
                    without_offset,
                    SQLLiteral(value=r"[^0-9]"),
                    SQLLiteral(value=""),
                    SQLLiteral(value="g"),
                ],
            )
            condition = SQLBinaryOp(
                operator="AND",
                left=SQLUnaryOp(operator="IS NOT NULL", operand=text, prefix=False),
                right=SQLBinaryOp(
                    operator="<",
                    left=SQLFunctionCall(name="LENGTH", args=[digits]),
                    right=SQLLiteral(value=required_digits),
                ),
            )
            if peer is not None and not isinstance(peer, SQLLiteral):
                condition = SQLBinaryOp(
                    operator="AND",
                    left=condition,
                    right=SQLUnaryOp(
                        operator="IS NOT NULL",
                        operand=SQLCast(expression=peer, target_type="VARCHAR"),
                        prefix=False,
                    ),
                )
            guard = condition if guard is None else SQLBinaryOp(
                operator="OR",
                left=guard,
                right=condition,
            )
        return guard

    @staticmethod
    def _interval_from_bounds_low_high(
        interval_expr: SQLExpression,
    ) -> tuple[SQLExpression | None, SQLExpression | None]:
        candidate = interval_expr.expression if isinstance(interval_expr, SQLCast) else interval_expr
        if isinstance(candidate, SQLInterval):
            return candidate.low, candidate.high
        if isinstance(candidate, SQLFunctionCall) and candidate.name == "intervalFromBounds" and len(candidate.args) >= 2:
            return candidate.args[0], candidate.args[1]
        if isinstance(candidate, SQLCase):
            low_clauses = []
            high_clauses = []
            found_interval = False
            for condition, result in candidate.when_clauses:
                low, high = OperatorsMixin._interval_from_bounds_low_high(result)
                if low is not None or high is not None:
                    found_interval = True
                low_clauses.append((condition, low if low is not None else SQLNull()))
                high_clauses.append((condition, high if high is not None else SQLNull()))
            low_else = None
            high_else = None
            if candidate.else_clause is not None:
                low_else, high_else = OperatorsMixin._interval_from_bounds_low_high(candidate.else_clause)
                if low_else is not None or high_else is not None:
                    found_interval = True
            if found_interval:
                return (
                    SQLCase(when_clauses=low_clauses, else_clause=low_else or SQLNull()),
                    SQLCase(when_clauses=high_clauses, else_clause=high_else or SQLNull()),
                )
        return None, None

    def _temporal_precision_guard_for_intervals(
        self,
        precision: str,
        left_interval: SQLExpression,
        right_interval: SQLExpression,
        left_start: SQLExpression,
        left_end: SQLExpression,
        right_start: SQLExpression,
        right_end: SQLExpression,
    ) -> SQLExpression | None:
        left_low_peer, left_high_peer = self._interval_from_bounds_low_high(left_interval)
        right_low_peer, right_high_peer = self._interval_from_bounds_low_high(right_interval)
        return self._runtime_temporal_precision_guard(
            precision,
            [
                (left_start, left_high_peer or left_end),
                (left_end, left_low_peer or left_start),
                (right_start, right_high_peer or right_end),
                (right_end, right_low_peer or right_start),
            ],
        )

    def _temporal_literal_digit_count(self, node: object) -> int | None:
        if not isinstance(node, (DateTimeLiteral, TimeLiteral)):
            return None
        value = str(node.value)
        # Offset digits do not contribute to CQL temporal precision.
        value = _re.sub(r"(Z|[+-]\d{2}:\d{2})$", "", value)
        return sum(1 for char in value if char.isdigit())

    def _temporal_literal_under_precision(self, node: object, precision: str) -> bool:
        actual_digits = self._temporal_literal_digit_count(node)
        if actual_digits is None:
            return False
        if isinstance(node, TimeLiteral) or str(getattr(node, "value", "")).startswith("T"):
            required_digits = self._time_precision_digit_count(precision)
        else:
            required_digits = self._precision_digit_count(precision)
        if required_digits is None:
            return False
        return actual_digits < required_digits

    def _interval_literal_under_precision(self, node: object, precision: str) -> bool:
        if not isinstance(node, Interval):
            return False
        return any(
            self._temporal_literal_under_precision(bound, precision)
            for bound in (node.low, node.high)
            if bound is not None
        )

    def _overlap_literal_under_precision(self, left_ast: object, right_ast: object, precision: str) -> bool:
        return (
            self._interval_literal_under_precision(left_ast, precision)
            or self._interval_literal_under_precision(right_ast, precision)
        )

    def _translate_overlaps_op(self, operator, left, right, expr) -> SQLExpression:
        """Extracted from _translate_binary_expression."""
        # Convert bare resource aliases to their primary date intervals
        left = self._ensure_resource_to_interval(left, expr.left)
        right = self._ensure_resource_to_interval(right, expr.right)
        # Check if right side is a 'precision of' expression
        if isinstance(expr.right, BinaryExpression) and expr.right.operator == "precision of":
            precision = getattr(expr.right.left, 'value', 'day')
            if isinstance(precision, str):
                precision = precision.lower()

            # Parser workaround: same AND-inside-precision issue as during
            actual_interval_ast = expr.right.right
            extra_conditions = []
            while isinstance(actual_interval_ast, BinaryExpression) and actual_interval_ast.operator == "and":
                extra_conditions.append(actual_interval_ast.right)
                actual_interval_ast = actual_interval_ast.left
            extra_condition_ast = None
            for cond in reversed(extra_conditions):
                if extra_condition_ast is None:
                    extra_condition_ast = cond
                else:
                    extra_condition_ast = BinaryExpression(operator="and", left=extra_condition_ast, right=cond)

            if self._overlap_literal_under_precision(expr.left, actual_interval_ast, precision):
                result: SQLExpression = SQLNull()
                if extra_condition_ast:
                    extra_sql = self.translate(extra_condition_ast, boolean_context=True)
                    return SQLBinaryOp(operator="AND", left=result, right=extra_sql)
                return result

            interval_expr = self.translate(actual_interval_ast, usage=ExprUsage.SCALAR)
            left_start_raw = SQLFunctionCall(name="intervalStart", args=[left])
            left_end_raw_bound = SQLFunctionCall(name="intervalEnd", args=[left])
            right_start_raw = SQLFunctionCall(name="intervalStart", args=[interval_expr])
            right_end_raw_bound = SQLFunctionCall(name="intervalEnd", args=[interval_expr])

            # Keep the DQM-proven day-window decomposition for concrete FHIR
            # DateTime intervals. Static partial temporal interval literals
            # are handled above so dynamic/resource intervals keep measure
            # behavior stable.
            left_start = self._ensure_date_cast(self._truncate_to_precision(left_start_raw, precision))
            left_end_raw = self._ensure_date_cast(self._truncate_to_precision(left_end_raw_bound, precision))
            left_end = SQLFunctionCall(
                name="COALESCE",
                args=[left_end_raw, SQLCast(expression=SQLLiteral(value="9999-12-31"), target_type="DATE")],
            )
            right_start = self._ensure_date_cast(self._truncate_to_precision(right_start_raw, precision))
            right_end_raw = self._ensure_date_cast(self._truncate_to_precision(right_end_raw_bound, precision))
            right_end = SQLFunctionCall(
                name="COALESCE",
                args=[right_end_raw, SQLCast(expression=SQLLiteral(value="9999-12-31"), target_type="DATE")],
            )
            overlaps_result = SQLBinaryOp(
                operator="AND",
                left=SQLBinaryOp(operator="<=", left=left_start, right=right_end),
                right=SQLBinaryOp(operator=">=", left=left_end, right=right_start),
            )
            precision_guard = self._temporal_precision_guard_for_intervals(
                precision,
                left,
                interval_expr,
                left_start,
                left_end_raw,
                right_start,
                right_end_raw,
            )
            if precision_guard is not None:
                overlaps_result = SQLCase(
                    when_clauses=[(precision_guard, SQLNull())],
                    else_clause=overlaps_result,
                )
            if extra_condition_ast:
                extra_sql = self.translate(extra_condition_ast, boolean_context=True)
                return SQLBinaryOp(operator="AND", left=overlaps_result, right=extra_sql)
            return overlaps_result

        # Try to decompose interval overlaps to simple date comparisons
        decomposed = self._try_decompose_interval_overlaps(left, right, expr)
        if decomposed is not None:
            return decomposed

        return SQLFunctionCall(name="intervalOverlaps", args=[left, right])

    def _translate_meets_op(
        self, udf_name: str, left: SQLExpression, right: SQLExpression, expr
    ) -> SQLExpression:
        """Translate ``meets`` / ``meets before`` / ``meets after`` operators.

        CQL 1.5.3 §Meets: "If precision is specified and the point type is a
        Date, DateTime, or Time type, comparisons used in the operation are
        performed at the specified precision."

        When the CQL author writes ``X meets day of Y``, the parser desugars
        ``day of Y`` to ``day precision of Y`` (a BinaryExpression with
        operator ``"precision of"``). The desugared right operand is then
        translated by ``_truncate_to_precision`` to truncate Y to day
        precision. Without a symmetric truncation on the left operand, the
        emitted ``intervalMeets(left_full_precision, right_truncated)`` call
        compares a full-precision DateTime end against a date-only start,
        yielding wrong answers (CQL-16 EXPLORER QA-001).

        This helper detects the ``precision of`` wrapper, truncates BOTH
        interval operands' Start/End bounds to the specified precision,
        rebuilds interval JSON via ``intervalFromBounds``, and forwards to
        the existing ``intervalMeets`` / ``intervalMeetsBefore`` /
        ``intervalMeetsAfter`` UDFs. Mirrors the pattern used by
        ``_translate_overlaps_op`` / ``_translate_overlaps_after_op`` /
        ``_translate_overlaps_before_op``.
        """
        # No precision wrapper on the right operand: simple UDF call.
        if not (
            isinstance(expr.right, BinaryExpression)
            and expr.right.operator == "precision of"
        ):
            return SQLFunctionCall(name=udf_name, args=[left, right])

        precision = getattr(expr.right.left, "value", "day")
        if isinstance(precision, str):
            precision = precision.lower()
        actual_interval_ast = expr.right.right
        # Strip extra AND-conditions inside the precision-of wrapper (parser
        # workaround shared with the overlaps handlers).
        extra_conditions = []
        while (
            isinstance(actual_interval_ast, BinaryExpression)
            and actual_interval_ast.operator == "and"
        ):
            extra_conditions.append(actual_interval_ast.right)
            actual_interval_ast = actual_interval_ast.left
        extra_condition_ast = None
        for cond in reversed(extra_conditions):
            if extra_condition_ast is None:
                extra_condition_ast = cond
            else:
                extra_condition_ast = BinaryExpression(
                    operator="and", left=extra_condition_ast, right=cond
                )

        # CQL-16 EXPLORER QA-001: when either interval's literal bounds are
        # already at coarser precision than the requested comparison, the
        # spec-compliant result is NULL (uncertain). Mirrors overlaps behavior.
        if self._overlap_literal_under_precision(
            expr.left, actual_interval_ast, precision
        ):
            result: SQLExpression = SQLNull()
            if extra_condition_ast:
                extra_sql = self.translate(extra_condition_ast, boolean_context=True)
                return SQLBinaryOp(operator="AND", left=result, right=extra_sql)
            return result

        interval_expr = self.translate(actual_interval_ast, usage=ExprUsage.SCALAR)

        # Truncate BOTH sides to the requested precision. intervalStart /
        # intervalEnd extract the effective boundary points (closed/open
        # aware); _truncate_to_precision reduces them to the precision;
        # intervalFromBounds rebuilds interval JSON for the UDF call.
        left_start = SQLFunctionCall(name="intervalStart", args=[left])
        left_end = SQLFunctionCall(name="intervalEnd", args=[left])
        right_start = SQLFunctionCall(name="intervalStart", args=[interval_expr])
        right_end = SQLFunctionCall(name="intervalEnd", args=[interval_expr])

        left_start_trunc = self._truncate_to_precision(left_start, precision)
        left_end_trunc = self._truncate_to_precision(left_end, precision)
        right_start_trunc = self._truncate_to_precision(right_start, precision)
        right_end_trunc = self._truncate_to_precision(right_end, precision)

        # Preserve original closedness flags for each side. We rebuild the
        # interval JSON with the original lowClosed/highClosed booleans so
        # intervalMeets' successor/predecessor logic still applies correctly
        # after the precision-truncated bounds.
        def _rebuild_interval(start_trunc, end_trunc, original_iv):
            low_closed = True
            high_closed = True
            if isinstance(original_iv, SQLInterval):
                low_closed = original_iv.low_closed
                high_closed = original_iv.high_closed
            elif isinstance(original_iv, SQLFunctionCall) and original_iv.name == "intervalFromBounds":
                # intervalFromBounds(low, high, lowClosed, highClosed)
                if len(original_iv.args) >= 4:
                    low_closed_arg = original_iv.args[2]
                    high_closed_arg = original_iv.args[3]
                    if isinstance(low_closed_arg, SQLLiteral):
                        low_closed = bool(low_closed_arg.value)
                    if isinstance(high_closed_arg, SQLLiteral):
                        high_closed = bool(high_closed_arg.value)
            return SQLFunctionCall(
                name="intervalFromBounds",
                args=[
                    start_trunc,
                    end_trunc,
                    SQLLiteral(value=low_closed),
                    SQLLiteral(value=high_closed),
                ],
            )

        left_truncated = _rebuild_interval(left_start_trunc, left_end_trunc, left)
        right_truncated = _rebuild_interval(
            right_start_trunc, right_end_trunc, interval_expr
        )

        meets_result = SQLFunctionCall(
            name=udf_name, args=[left_truncated, right_truncated]
        )

        if extra_condition_ast:
            extra_sql = self.translate(extra_condition_ast, boolean_context=True)
            return SQLBinaryOp(operator="AND", left=meets_result, right=extra_sql)
        return meets_result

    def _translate_overlaps_after_op(self, operator, left, right, expr) -> SQLExpression:
        """Extracted from _translate_binary_expression."""
        # Convert bare resource aliases to their primary date intervals
        left = self._ensure_resource_to_interval(left, expr.left)
        right = self._ensure_resource_to_interval(right, expr.right)
        if isinstance(expr.right, BinaryExpression) and expr.right.operator == "precision of":
            precision = getattr(expr.right.left, 'value', 'day')
            if isinstance(precision, str):
                precision = precision.lower()
            actual_interval_ast = expr.right.right
            extra_conditions = []
            while isinstance(actual_interval_ast, BinaryExpression) and actual_interval_ast.operator == "and":
                extra_conditions.append(actual_interval_ast.right)
                actual_interval_ast = actual_interval_ast.left
            extra_condition_ast = None
            for cond in reversed(extra_conditions):
                if extra_condition_ast is None:
                    extra_condition_ast = cond
                else:
                    extra_condition_ast = BinaryExpression(operator="and", left=extra_condition_ast, right=cond)
            if self._overlap_literal_under_precision(expr.left, actual_interval_ast, precision):
                result: SQLExpression = SQLNull()
                if extra_condition_ast:
                    extra_sql = self.translate(extra_condition_ast, boolean_context=True)
                    return SQLBinaryOp(operator="AND", left=result, right=extra_sql)
                return result
            interval_expr = self.translate(actual_interval_ast, usage=ExprUsage.SCALAR)
            left_start_raw = SQLFunctionCall(name="intervalStart", args=[left])
            left_end_raw_bound = SQLFunctionCall(name="intervalEnd", args=[left])
            right_start_raw = SQLFunctionCall(name="intervalStart", args=[interval_expr])
            right_end_raw_bound = SQLFunctionCall(name="intervalEnd", args=[interval_expr])
            left_start = self._ensure_date_cast(self._truncate_to_precision(left_start_raw, precision))
            right_start = self._ensure_date_cast(self._truncate_to_precision(right_start_raw, precision))
            left_end_raw = self._ensure_date_cast(self._truncate_to_precision(left_end_raw_bound, precision))
            right_end_raw = self._ensure_date_cast(self._truncate_to_precision(right_end_raw_bound, precision))
            left_end = SQLFunctionCall(
                name="COALESCE",
                args=[
                    left_end_raw,
                    SQLCast(expression=SQLLiteral(value="9999-12-31"), target_type="DATE"),
                ],
            )
            right_end = SQLFunctionCall(
                name="COALESCE",
                args=[
                    right_end_raw,
                    SQLCast(expression=SQLLiteral(value="9999-12-31"), target_type="DATE"),
                ],
            )
            overlap_check = SQLBinaryOp(
                operator="AND",
                left=SQLBinaryOp(operator="<=", left=left_start, right=right_end),
                right=SQLBinaryOp(operator=">=", left=left_end, right=right_start),
            )
            ends_after = SQLBinaryOp(operator=">", left=left_end, right=right_end)
            result = SQLBinaryOp(operator="AND", left=overlap_check, right=ends_after)
            precision_guard = self._temporal_precision_guard_for_intervals(
                precision,
                left,
                interval_expr,
                left_start,
                left_end_raw,
                right_start,
                right_end_raw,
            )
            if precision_guard is not None:
                result = SQLCase(when_clauses=[(precision_guard, SQLNull())], else_clause=result)
            if extra_condition_ast:
                extra_sql = self.translate(extra_condition_ast, boolean_context=True)
                return SQLBinaryOp(operator="AND", left=result, right=extra_sql)
            return result
        return SQLFunctionCall(name="intervalOverlapsAfter", args=[left, right])

    def _translate_overlaps_before_op(self, operator, left, right, expr) -> SQLExpression:
        """Extracted from _translate_binary_expression."""
        # Convert bare resource aliases to their primary date intervals
        left = self._ensure_resource_to_interval(left, expr.left)
        right = self._ensure_resource_to_interval(right, expr.right)
        if isinstance(expr.right, BinaryExpression) and expr.right.operator == "precision of":
            precision = getattr(expr.right.left, 'value', 'day')
            if isinstance(precision, str):
                precision = precision.lower()
            actual_interval_ast = expr.right.right
            extra_conditions = []
            while isinstance(actual_interval_ast, BinaryExpression) and actual_interval_ast.operator == "and":
                extra_conditions.append(actual_interval_ast.right)
                actual_interval_ast = actual_interval_ast.left
            extra_condition_ast = None
            for cond in reversed(extra_conditions):
                if extra_condition_ast is None:
                    extra_condition_ast = cond
                else:
                    extra_condition_ast = BinaryExpression(operator="and", left=extra_condition_ast, right=cond)
            if self._overlap_literal_under_precision(expr.left, actual_interval_ast, precision):
                result: SQLExpression = SQLNull()
                if extra_condition_ast:
                    extra_sql = self.translate(extra_condition_ast, boolean_context=True)
                    return SQLBinaryOp(operator="AND", left=result, right=extra_sql)
                return result
            interval_expr = self.translate(actual_interval_ast, usage=ExprUsage.SCALAR)
            left_start_raw = SQLFunctionCall(name="intervalStart", args=[left])
            left_end_raw_bound = SQLFunctionCall(name="intervalEnd", args=[left])
            right_start_raw = SQLFunctionCall(name="intervalStart", args=[interval_expr])
            right_end_raw_bound = SQLFunctionCall(name="intervalEnd", args=[interval_expr])
            left_start = self._ensure_date_cast(self._truncate_to_precision(left_start_raw, precision))
            right_start = self._ensure_date_cast(self._truncate_to_precision(right_start_raw, precision))
            left_end_raw = self._ensure_date_cast(self._truncate_to_precision(left_end_raw_bound, precision))
            right_end_raw = self._ensure_date_cast(self._truncate_to_precision(right_end_raw_bound, precision))
            left_end = SQLFunctionCall(
                name="COALESCE",
                args=[
                    left_end_raw,
                    SQLCast(expression=SQLLiteral(value="9999-12-31"), target_type="DATE"),
                ],
            )
            right_end = SQLFunctionCall(
                name="COALESCE",
                args=[
                    right_end_raw,
                    SQLCast(expression=SQLLiteral(value="9999-12-31"), target_type="DATE"),
                ],
            )
            overlap_check = SQLBinaryOp(
                operator="AND",
                left=SQLBinaryOp(operator="<=", left=left_start, right=right_end),
                right=SQLBinaryOp(operator=">=", left=left_end, right=right_start),
            )
            starts_before = SQLBinaryOp(operator="<", left=left_start, right=right_start)
            result = SQLBinaryOp(operator="AND", left=overlap_check, right=starts_before)
            precision_guard = self._temporal_precision_guard_for_intervals(
                precision,
                left,
                interval_expr,
                left_start,
                left_end_raw,
                right_start,
                right_end_raw,
            )
            if precision_guard is not None:
                result = SQLCase(when_clauses=[(precision_guard, SQLNull())], else_clause=result)
            if extra_condition_ast:
                extra_sql = self.translate(extra_condition_ast, boolean_context=True)
                return SQLBinaryOp(operator="AND", left=result, right=extra_sql)
            return result
        return SQLFunctionCall(name="intervalOverlapsBefore", args=[left, right])

    def _translate_during_op(self, operator, left, right, expr) -> SQLExpression:
        """Extracted from _translate_binary_expression."""
        # Check if right side is a 'precision of' expression (e.g., 'day of "Measurement Period"')
        if isinstance(expr.right, BinaryExpression) and expr.right.operator == "precision of":
            # Get the precision and the interval
            precision = getattr(expr.right.left, 'value', 'day')
            if isinstance(precision, str):
                precision = precision.lower()

            # Parser workaround: "during day of X and Y" may parse as
            # during(precision of(day, and(X, Y))) instead of and(during(precision of(day, X)), Y)
            # Detect and split the AND out of the interval expression
            # The AND can be nested: and(and(and(period, cond1), cond2), cond3)
            actual_interval_ast = expr.right.right
            extra_conditions = []
            while isinstance(actual_interval_ast, BinaryExpression) and actual_interval_ast.operator == "and":
                extra_conditions.append(actual_interval_ast.right)
                actual_interval_ast = actual_interval_ast.left
            # Combine extra conditions into a single AND chain (reversed for correct order)
            extra_condition_ast = None
            for cond in reversed(extra_conditions):
                if extra_condition_ast is None:
                    extra_condition_ast = cond
                else:
                    extra_condition_ast = BinaryExpression(operator="and", left=extra_condition_ast, right=cond)

            # Translate the interval (not the precision expression)
            interval_expr = self.translate(actual_interval_ast, usage=ExprUsage.SCALAR)

            # Detect if left operand is a FHIR Period (interval) property.
            # fhirpath_text(resource, 'period') returns JSON like {"start":...,"end":...}
            # For interval-during-interval: check both start AND end are within bounds.
            # For point-during-interval: check the point is within bounds.
            left_is_interval = self._is_fhir_interval_expression(left)
            if left_is_interval:
                left_start = SQLFunctionCall(name="intervalStart", args=[left])
                left_end = SQLFunctionCall(name="intervalEnd", args=[left])
            else:
                left_start = left
                left_end = None
            left_start_truncated = self._truncate_to_precision(left_start, precision)

            # Gap 11: Extract interval bounds and use boundary-aware comparisons
            interval_bounds = self._extract_interval_bounds(interval_expr, actual_interval_ast)
            if interval_bounds:
                right_start, right_end, low_closed, high_closed = interval_bounds
                start_truncated = self._ensure_date_cast(
                    self._truncate_to_precision(right_start, precision))
                end_truncated = self._ensure_date_cast(
                    self._truncate_to_precision(right_end, precision))
                left_start_cast = self._ensure_date_cast(left_start_truncated)
                # Use boundary-aware operators (not BETWEEN which is always inclusive)
                start_op = ">=" if low_closed else ">"
                end_op = "<=" if high_closed else "<"
                start_check = SQLBinaryOp(operator=start_op, left=left_start_cast, right=start_truncated)
                if left_is_interval and left_end is not None:
                    left_end_truncated = self._truncate_to_precision(left_end, precision)
                    left_end_cast = self._ensure_date_cast(left_end_truncated)
                    end_check = SQLBinaryOp(operator=end_op, left=left_end_cast, right=end_truncated)
                else:
                    end_check = SQLBinaryOp(operator=end_op, left=left_start_cast, right=end_truncated)
                during_result = SQLBinaryOp(
                    operator="AND",
                    left=start_check,
                    right=end_check,
                )
                if extra_condition_ast:
                    extra_sql = self.translate(extra_condition_ast, boolean_context=True)
                    return SQLBinaryOp(operator="AND", left=during_result, right=extra_sql)
                return during_result

            # Fallback: use intervalStart/intervalEnd
            right_start = SQLFunctionCall(name="intervalStart", args=[interval_expr])
            right_end = SQLFunctionCall(name="intervalEnd", args=[interval_expr])
            start_truncated = self._ensure_date_cast(
                self._truncate_to_precision(right_start, precision))
            end_truncated = self._ensure_date_cast(
                self._truncate_to_precision(right_end, precision))
            # Handle NULL end bound (open-ended intervals like active conditions
            # without abatementDateTime): treat NULL as far-future so "during"
            # succeeds for any point after the start.
            end_coalesced = SQLFunctionCall(
                name="COALESCE",
                args=[end_truncated, SQLCast(expression=SQLLiteral("9999-12-31"), target_type="DATE")],
            )
            left_start_cast = self._ensure_date_cast(left_start_truncated)
            start_check = SQLBinaryOp(operator=">=", left=left_start_cast, right=start_truncated)
            if left_is_interval and left_end is not None:
                left_end_truncated = self._truncate_to_precision(left_end, precision)
                left_end_cast = self._ensure_date_cast(left_end_truncated)
                end_check = SQLBinaryOp(operator="<=", left=left_end_cast, right=end_coalesced)
            else:
                end_check = SQLBinaryOp(operator="<=", left=left_start_cast, right=end_coalesced)
            during_result = SQLBinaryOp(
                operator="AND",
                left=start_check,
                right=end_check,
            )
            if extra_condition_ast:
                extra_sql = self.translate(extra_condition_ast, boolean_context=True)
                return SQLBinaryOp(operator="AND", left=during_result, right=extra_sql)
            return during_result
        # X during Y = Y includes X (interval-in-interval) or Y contains X (point-in-interval)
        left_is_interval = self._is_fhir_interval_expression(left)
        if left_is_interval:
            return SQLFunctionCall(name="intervalIncludes", args=[right, left])
        return SQLFunctionCall(name="intervalContains", args=[right, self._ensure_interval_varchar(left)])

    @staticmethod
    def _unwrap_precision_wrapper(expr: SQLExpression) -> SQLExpression:
        """Strip DATE_TRUNC / CAST wrappers added by precision-of translation.

        When ``X on or after month of Interval[...]`` is parsed, the right
        operand becomes ``DATE_TRUNC('month', intervalFromBounds(...))``.
        For interval UDF calls we need the raw interval, not the truncated
        form.
        """
        if isinstance(expr, SQLFunctionCall) and expr.name and expr.name.upper() == "DATE_TRUNC":
            if len(expr.args) >= 2:
                return expr.args[1]
        if isinstance(expr, SQLCast):
            return expr.expression
        return expr

    @staticmethod
    def _point_as_interval(point: SQLExpression) -> SQLExpression:
        """Wrap a point value as a degenerate interval [point, point].

        Used for before/after/on-or-before/on-or-after when comparing
        non-temporal intervals (Quantity, Integer, Decimal) where SQL
        comparison operators can't handle the VARCHAR values from
        intervalStart/End.
        """
        cast_point = SQLCast(expression=point, target_type="VARCHAR")
        return SQLFunctionCall(
            name="intervalFromBounds",
            args=[cast_point, cast_point, SQLLiteral(value=True), SQLLiteral(value=True)],
        )

    @staticmethod
    def _interval_same_at_precision(
        left_interval: SQLExpression,
        right_interval: SQLExpression,
        precision: str,
    ) -> SQLExpression:
        starts_same = SQLFunctionCall(
            name="cqlSameAsP",
            args=[
                SQLCast(
                    expression=SQLFunctionCall(name="intervalStart", args=[left_interval]),
                    target_type="VARCHAR",
                ),
                SQLCast(
                    expression=SQLFunctionCall(name="intervalStart", args=[right_interval]),
                    target_type="VARCHAR",
                ),
                SQLLiteral(value=precision),
            ],
        )
        ends_same = SQLFunctionCall(
            name="cqlSameAsP",
            args=[
                SQLCast(
                    expression=SQLFunctionCall(name="intervalEnd", args=[left_interval]),
                    target_type="VARCHAR",
                ),
                SQLCast(
                    expression=SQLFunctionCall(name="intervalEnd", args=[right_interval]),
                    target_type="VARCHAR",
                ),
                SQLLiteral(value=precision),
            ],
        )
        return SQLBinaryOp(operator="AND", left=starts_same, right=ends_same)

    @staticmethod
    def _point_same_as_interval_boundary_at_precision(
        interval: SQLExpression,
        point_interval: SQLExpression,
        precision: str,
    ) -> SQLExpression:
        point = SQLCast(
            expression=SQLFunctionCall(name="intervalStart", args=[point_interval]),
            target_type="VARCHAR",
        )
        starts_same = SQLFunctionCall(
            name="cqlSameAsP",
            args=[
                SQLCast(
                    expression=SQLFunctionCall(name="intervalStart", args=[interval]),
                    target_type="VARCHAR",
                ),
                point,
                SQLLiteral(value=precision),
            ],
        )
        ends_same = SQLFunctionCall(
            name="cqlSameAsP",
            args=[
                SQLCast(
                    expression=SQLFunctionCall(name="intervalEnd", args=[interval]),
                    target_type="VARCHAR",
                ),
                point,
                SQLLiteral(value=precision),
            ],
        )
        return SQLBinaryOp(operator="OR", left=starts_same, right=ends_same)

    def _translate_before_op(self, operator, left, right, expr) -> SQLExpression:
        """Extracted from _translate_binary_expression."""
        # Convert bare resource aliases to their primary date intervals
        left = self._ensure_resource_to_interval(left, expr.left)
        right = self._ensure_resource_to_interval(right, expr.right)
        left_is_interval = self._is_fhir_interval_expression(left)
        right_is_interval = self._is_fhir_interval_expression(right)
        if left_is_interval and right_is_interval:
            return SQLFunctionCall(name="intervalBefore", args=[left, right])
        # Mixed interval/point: wrap point as degenerate interval and use UDF
        if left_is_interval and not right_is_interval:
            return SQLFunctionCall(
                name="intervalBefore",
                args=[left, self._point_as_interval(right)],
            )
        if right_is_interval and not left_is_interval:
            return SQLFunctionCall(
                name="intervalBefore",
                args=[self._point_as_interval(left), right],
            )
        # Point before point — use precision-aware UDF for temporal,
        # standard SQL operator for numeric (CQL §19.9).
        cast_type = self._infer_cast_type_for_comparison(left, right)
        if cast_type in ("TIMESTAMP", "DATE"):
            # Temporal: use precision-aware cqlBefore UDF that handles
            # partial-precision ISO 8601 strings and returns NULL for
            # uncertain comparisons per CQL §18.4.
            return SQLFunctionCall(
                name="cqlBefore",
                args=[
                    SQLCast(expression=left, target_type="VARCHAR"),
                    SQLCast(expression=right, target_type="VARCHAR"),
                ],
            )
        return SQLBinaryOp(
            operator="<",
            left=self._ensure_date_cast(left, cast_type),
            right=self._ensure_date_cast(right, cast_type),
        )

    def _translate_after_op(self, operator, left, right, expr) -> SQLExpression:
        """Extracted from _translate_binary_expression."""
        # Convert bare resource aliases to their primary date intervals
        left = self._ensure_resource_to_interval(left, expr.left)
        right = self._ensure_resource_to_interval(right, expr.right)
        left_is_interval = self._is_fhir_interval_expression(left)
        right_is_interval = self._is_fhir_interval_expression(right)
        if left_is_interval and right_is_interval:
            return SQLFunctionCall(name="intervalAfter", args=[left, right])
        # Mixed interval/point: wrap point as degenerate interval and use UDF
        if left_is_interval and not right_is_interval:
            return SQLFunctionCall(
                name="intervalAfter",
                args=[left, self._point_as_interval(right)],
            )
        if right_is_interval and not left_is_interval:
            return SQLFunctionCall(
                name="intervalAfter",
                args=[self._point_as_interval(left), right],
            )
        # Point after point — use precision-aware UDF for temporal,
        # standard SQL operator for numeric (CQL §19.10).
        cast_type = self._infer_cast_type_for_comparison(left, right)
        if cast_type in ("TIMESTAMP", "DATE"):
            return SQLFunctionCall(
                name="cqlAfter",
                args=[
                    SQLCast(expression=left, target_type="VARCHAR"),
                    SQLCast(expression=right, target_type="VARCHAR"),
                ],
            )
        return SQLBinaryOp(
            operator=">",
            left=self._ensure_date_cast(left, cast_type),
            right=self._ensure_date_cast(right, cast_type),
        )

    def _translate_starts_op(self, operator, left, right, expr) -> SQLExpression:
        """Extracted from _translate_binary_expression."""
        # Convert bare resource alias to its primary interval
        left = self._ensure_resource_to_interval(left, expr.left)
        # Check if right is a temporal expression with "on or before" / "on or after"
        if isinstance(expr.right, UnaryExpression):
            inner_op = expr.right.operator
            # Handle simple "on or before" / "on or after" patterns
            if inner_op == "on or before":
                # Parser workaround: strip mis-parsed AND conditions
                cleaned_operand, extra_cond_ast = self._strip_and_conditions(expr.right.operand)
                # "starts on or before <precision> of X": compare BOTH bounds at
                # the specified precision (CQL 1.5 §9.19/§9.26) — the old DATE
                # casts silently forced day precision and produced false
                # negatives at year/month (and day-collapse at finer units).
                if isinstance(cleaned_operand, BinaryExpression) and cleaned_operand.operator == "precision of":
                    precision = getattr(cleaned_operand.left, 'value', 'day')
                    if isinstance(precision, str):
                        precision = precision.lower()
                    right_prec = self.translate(cleaned_operand.right, usage=ExprUsage.SCALAR)
                    if self._is_fhir_interval_expression(right_prec):
                        right_prec = SQLFunctionCall(name="intervalStart", args=[right_prec])
                    return SQLFunctionCall(
                        name="cqlSameOrBeforeP",
                        args=[
                            SQLCast(
                                expression=SQLFunctionCall(name="intervalStart", args=[left]),
                                target_type="VARCHAR",
                            ),
                            SQLCast(expression=right_prec, target_type="VARCHAR"),
                            SQLLiteral(value=precision),
                        ],
                    )
                right_inner = self.translate(cleaned_operand)
                # Resolve FHIR interval: point on or before Interval → point <= start of Interval
                if self._is_fhir_interval_expression(right_inner):
                    right_inner = SQLFunctionCall(name="intervalStart", args=[right_inner])
                right_inner = self._ensure_date_cast(right_inner)
                # Gap 18: Use < for exclusive boundary
                op = "<" if getattr(right_inner, 'is_exclusive_boundary', False) else "<="
                # Symmetric DATE truncation on BOTH sides (CQL §18.2 —
                # compare at minimum precision).  Old code only truncated
                # the left, causing 10-char vs 29-char mismatches.
                interval_start = SQLFunctionCall(name="intervalStart", args=[left])
                result = SQLBinaryOp(
                    operator=op,
                    left=SQLCast(expression=interval_start, target_type="DATE"),
                    right=SQLCast(expression=right_inner, target_type="DATE"),
                )
                if extra_cond_ast:
                    extra_sql = self.translate(extra_cond_ast, boolean_context=True)
                    return SQLBinaryOp(operator="AND", left=result, right=extra_sql)
                return result
            if inner_op == "on or after":
                # Parser workaround: strip mis-parsed AND conditions
                cleaned_operand, extra_cond_ast = self._strip_and_conditions(expr.right.operand)
                # "starts on or after <precision> of X": compare BOTH bounds at
                # the specified precision (CQL 1.5 §9.18/§9.25).
                if isinstance(cleaned_operand, BinaryExpression) and cleaned_operand.operator == "precision of":
                    precision = getattr(cleaned_operand.left, 'value', 'day')
                    if isinstance(precision, str):
                        precision = precision.lower()
                    right_prec = self.translate(cleaned_operand.right, usage=ExprUsage.SCALAR)
                    if self._is_fhir_interval_expression(right_prec):
                        right_prec = SQLFunctionCall(name="intervalEnd", args=[right_prec])
                    return SQLFunctionCall(
                        name="cqlSameOrAfterP",
                        args=[
                            SQLCast(
                                expression=SQLFunctionCall(name="intervalStart", args=[left]),
                                target_type="VARCHAR",
                            ),
                            SQLCast(expression=right_prec, target_type="VARCHAR"),
                            SQLLiteral(value=precision),
                        ],
                    )
                right_inner = self.translate(cleaned_operand)
                # Resolve FHIR interval: point on or after Interval → point >= end of Interval
                if self._is_fhir_interval_expression(right_inner):
                    right_inner = SQLFunctionCall(name="intervalEnd", args=[right_inner])
                right_inner = self._ensure_date_cast(right_inner)
                # Symmetric DATE truncation on BOTH sides (CQL §18.2).
                interval_start = SQLFunctionCall(name="intervalStart", args=[left])
                result = SQLBinaryOp(
                    operator=">=",
                    left=SQLCast(expression=interval_start, target_type="DATE"),
                    right=SQLCast(expression=right_inner, target_type="DATE"),
                )
                if extra_cond_ast:
                    extra_sql = self.translate(extra_cond_ast, boolean_context=True)
                    return SQLBinaryOp(operator="AND", left=result, right=extra_sql)
                return result
            if inner_op == "before":
                # starts before X -> intervalStart(left) < X
                # Parser workaround: strip mis-parsed AND conditions
                cleaned_operand, extra_cond_ast = self._strip_and_conditions(expr.right.operand)
                right_inner = self.translate(cleaned_operand)
                # Resolve FHIR interval: point before Interval → point < start of Interval
                if self._is_fhir_interval_expression(right_inner):
                    right_inner = SQLFunctionCall(name="intervalStart", args=[right_inner])
                interval_start = SQLFunctionCall(name="intervalStart", args=[left])
                # Use TIMESTAMP to preserve sub-day precision for dateTime values
                result = SQLBinaryOp(
                    operator="<",
                    left=self._ensure_date_cast(interval_start, "TIMESTAMP"),
                    right=self._ensure_date_cast(right_inner, "TIMESTAMP"),
                )
                if extra_cond_ast:
                    extra_sql = self.translate(extra_cond_ast, boolean_context=True)
                    return SQLBinaryOp(operator="AND", left=result, right=extra_sql)
                return result
            if inner_op == "after":
                # starts after X -> intervalStart(left) > X
                # Parser workaround: strip mis-parsed AND conditions
                cleaned_operand, extra_cond_ast = self._strip_and_conditions(expr.right.operand)
                right_inner = self.translate(cleaned_operand)
                # Resolve FHIR interval: point after Interval → point > end of Interval
                if self._is_fhir_interval_expression(right_inner):
                    right_inner = SQLFunctionCall(name="intervalEnd", args=[right_inner])
                interval_start = SQLFunctionCall(name="intervalStart", args=[left])
                # Use TIMESTAMP to preserve sub-day precision for dateTime values
                result = SQLBinaryOp(
                    operator=">",
                    left=self._ensure_date_cast(interval_start, "TIMESTAMP"),
                    right=self._ensure_date_cast(right_inner, "TIMESTAMP"),
                )
                if extra_cond_ast:
                    extra_sql = self.translate(extra_cond_ast, boolean_context=True)
                    return SQLBinaryOp(operator="AND", left=result, right=extra_sql)
                return result
            # Handle "starts during day of X" pattern (UnaryExpression with during)
            if inner_op == "during":
                interval_start = SQLFunctionCall(name="intervalStart", args=[left])
                # Check if the operand is a 'precision of' expression
                if isinstance(expr.right.operand, BinaryExpression) and expr.right.operand.operator == "precision of":
                    precision = getattr(expr.right.operand.left, 'value', 'day')
                    if isinstance(precision, str):
                        precision = precision.lower()
                    interval_expr = self.translate(expr.right.operand.right, usage=ExprUsage.SCALAR)
                    left_truncated = self._ensure_date_cast(
                        self._truncate_to_precision(interval_start, precision))
                    # Try boundary-aware comparison via _extract_interval_bounds
                    right_bounds = self._extract_interval_bounds(interval_expr, expr.right.operand.right)
                    if right_bounds:
                        r_start, r_end, low_closed, high_closed = right_bounds
                        start_truncated = self._ensure_date_cast(
                            self._truncate_to_precision(r_start, precision))
                        end_truncated = self._ensure_date_cast(
                            self._truncate_to_precision(r_end, precision))
                        end_coalesced = SQLFunctionCall(
                            name="COALESCE",
                            args=[end_truncated, start_truncated],
                        )
                        start_op = ">=" if low_closed else ">"
                        end_op = "<=" if high_closed else "<"
                        return SQLBinaryOp(
                            operator="AND",
                            left=SQLBinaryOp(operator=start_op, left=left_truncated, right=start_truncated),
                            right=SQLBinaryOp(operator=end_op, left=left_truncated, right=end_coalesced),
                        )
                    # Fallback: use intervalStart/intervalEnd (closed by semantics)
                    right_start = SQLFunctionCall(name="intervalStart", args=[interval_expr])
                    right_end = SQLFunctionCall(name="intervalEnd", args=[interval_expr])
                    start_truncated = self._ensure_date_cast(
                        self._truncate_to_precision(right_start, precision))
                    end_truncated = self._ensure_date_cast(
                        self._truncate_to_precision(right_end, precision))
                    end_coalesced = SQLFunctionCall(
                        name="COALESCE",
                        args=[end_truncated, start_truncated],
                    )
                    return SQLBinaryOp(
                        operator="AND",
                        left=SQLBinaryOp(operator=">=", left=left_truncated, right=start_truncated),
                        right=SQLBinaryOp(operator="<=", left=left_truncated, right=end_coalesced),
                    )
                # Plain "starts during X" -> intervalContains(X, intervalStart(left))
                interval_arg = self.translate(expr.right.operand, usage=ExprUsage.SCALAR)
                return SQLFunctionCall(name="intervalContains", args=[interval_arg, interval_start])
        if isinstance(expr.right, BinaryExpression):
            inner_op = expr.right.operator
            # Complex pattern like "starts 1 day or less on or after day of"
            if " or " in inner_op:
                return self._translate_complex_interval_temporal_with_interval(
                    inner_op, left, expr.right, "start"
                )
            # "starts day of X" / "starts month of X" → precision comparison
            if inner_op == "precision of":
                precision_node = expr.right.left
                precision_str = getattr(precision_node, 'value', 'day')
                if isinstance(precision_str, str):
                    precision_str = precision_str.lower()
                inner_expr = expr.right.right
                right_translated = self.translate(inner_expr, usage=ExprUsage.SCALAR)
                left_interval = left if self._is_fhir_interval_expression(left) else self._point_as_interval(left)
                right_interval = (
                    right_translated
                    if self._is_fhir_interval_expression(right_translated) or isinstance(right_translated, SQLInterval)
                    else self._point_as_interval(right_translated)
                )
                starts_same = SQLFunctionCall(
                    name="cqlSameAsP",
                    args=[
                        SQLCast(
                            expression=SQLFunctionCall(name="intervalStart", args=[left_interval]),
                            target_type="VARCHAR",
                        ),
                        SQLCast(
                            expression=SQLFunctionCall(name="intervalStart", args=[right_interval]),
                            target_type="VARCHAR",
                        ),
                        SQLLiteral(value=precision_str),
                    ],
                )
                ends_within = SQLFunctionCall(
                    name="cqlSameOrBeforeP",
                    args=[
                        SQLCast(
                            expression=SQLFunctionCall(name="intervalEnd", args=[left_interval]),
                            target_type="VARCHAR",
                        ),
                        SQLCast(
                            expression=SQLFunctionCall(name="intervalEnd", args=[right_interval]),
                            target_type="VARCHAR",
                        ),
                        SQLLiteral(value=precision_str),
                    ],
                )
                return SQLBinaryOp(operator="AND", left=starts_same, right=ends_within)
        # intervalStartsSame expects two interval VARCHAR strings.
        # If right is a point (DATE cast), compare start directly instead.
        if isinstance(right, SQLCast) and right.target_type == "DATE":
            return SQLBinaryOp(
                operator="=",
                left=SQLCast(expression=SQLFunctionCall(name="intervalStart", args=[left]), target_type="DATE"),
                right=right,
            )
        # Promote point operands to degenerate intervals [x, x] so that
        # intervalStartsSame receives two well-formed interval VARCHARs.
        left_is_interval = self._is_fhir_interval_expression(left) or isinstance(left, SQLInterval)
        right_is_interval = self._is_fhir_interval_expression(right) or isinstance(right, SQLInterval)
        left_arg = left if left_is_interval else self._point_as_interval(left)
        right_arg = right if right_is_interval else self._point_as_interval(right)
        return SQLFunctionCall(name="intervalStartsSame", args=[left_arg, right_arg])

    def _translate_ends_op(self, operator, left, right, expr) -> SQLExpression:
        """Extracted from _translate_binary_expression."""
        # Convert bare resource alias to its primary interval
        left = self._ensure_resource_to_interval(left, expr.left)
        # Check if right is a temporal expression with "on or before" / "on or after"
        if isinstance(expr.right, UnaryExpression):
            inner_op = expr.right.operator
            # Handle simple "on or before" / "on or after" patterns
            if inner_op == "on or before":
                # Parser workaround: strip mis-parsed AND conditions
                cleaned_operand, extra_cond_ast = self._strip_and_conditions(expr.right.operand)
                # "ends on or before <precision> of X": compare BOTH bounds at
                # the specified precision (CQL 1.5 §9.19/§9.26) — the old DATE
                # casts silently forced day precision and produced false
                # negatives at year/month (and day-collapse at finer units).
                if isinstance(cleaned_operand, BinaryExpression) and cleaned_operand.operator == "precision of":
                    precision = getattr(cleaned_operand.left, 'value', 'day')
                    if isinstance(precision, str):
                        precision = precision.lower()
                    right_prec = self.translate(cleaned_operand.right, usage=ExprUsage.SCALAR)
                    if self._is_fhir_interval_expression(right_prec):
                        right_prec = SQLFunctionCall(name="intervalStart", args=[right_prec])
                    return SQLFunctionCall(
                        name="cqlSameOrBeforeP",
                        args=[
                            SQLCast(
                                expression=SQLFunctionCall(name="intervalEnd", args=[left]),
                                target_type="VARCHAR",
                            ),
                            SQLCast(expression=right_prec, target_type="VARCHAR"),
                            SQLLiteral(value=precision),
                        ],
                    )
                right_inner = self._ensure_date_cast(self.translate(cleaned_operand))
                # Gap 18: Use < for exclusive boundary
                op = "<" if getattr(right_inner, 'is_exclusive_boundary', False) else "<="
                interval_end = SQLFunctionCall(name="intervalEnd", args=[left])
                # Symmetric DATE truncation on BOTH sides (CQL §18.2).
                result = SQLBinaryOp(
                    operator=op,
                    left=SQLCast(expression=interval_end, target_type="DATE"),
                    right=SQLCast(expression=right_inner, target_type="DATE"),
                )
                if extra_cond_ast:
                    extra_sql = self.translate(extra_cond_ast, boolean_context=True)
                    return SQLBinaryOp(operator="AND", left=result, right=extra_sql)
                return result
            if inner_op == "on or after":
                # Parser workaround: strip mis-parsed AND conditions
                cleaned_operand, extra_cond_ast = self._strip_and_conditions(expr.right.operand)
                # "ends on or after <precision> of X": compare BOTH bounds at
                # the specified precision (CQL 1.5 §9.18/§9.25).
                if isinstance(cleaned_operand, BinaryExpression) and cleaned_operand.operator == "precision of":
                    precision = getattr(cleaned_operand.left, 'value', 'day')
                    if isinstance(precision, str):
                        precision = precision.lower()
                    right_prec = self.translate(cleaned_operand.right, usage=ExprUsage.SCALAR)
                    if self._is_fhir_interval_expression(right_prec):
                        right_prec = SQLFunctionCall(name="intervalEnd", args=[right_prec])
                    return SQLFunctionCall(
                        name="cqlSameOrAfterP",
                        args=[
                            SQLCast(
                                expression=SQLFunctionCall(name="intervalEnd", args=[left]),
                                target_type="VARCHAR",
                            ),
                            SQLCast(expression=right_prec, target_type="VARCHAR"),
                            SQLLiteral(value=precision),
                        ],
                    )
                right_inner = self._ensure_date_cast(self.translate(cleaned_operand))
                interval_end = SQLFunctionCall(name="intervalEnd", args=[left])
                # Symmetric DATE truncation on BOTH sides (CQL §18.2).
                result = SQLBinaryOp(
                    operator=">=",
                    left=SQLCast(expression=interval_end, target_type="DATE"),
                    right=SQLCast(expression=right_inner, target_type="DATE"),
                )
                if extra_cond_ast:
                    extra_sql = self.translate(extra_cond_ast, boolean_context=True)
                    return SQLBinaryOp(operator="AND", left=result, right=extra_sql)
                return result
            if inner_op == "before":
                # ends before X -> intervalEnd(left) < X
                # Parser workaround: strip mis-parsed AND conditions
                cleaned_operand, extra_cond_ast = self._strip_and_conditions(expr.right.operand)
                # Use TIMESTAMP to preserve sub-day precision for dateTime values
                right_inner = self._ensure_date_cast(self.translate(cleaned_operand), "TIMESTAMP")
                interval_end = SQLFunctionCall(name="intervalEnd", args=[left])
                result = SQLBinaryOp(
                    operator="<",
                    left=SQLCast(expression=interval_end, target_type="VARCHAR"),
                    right=right_inner
                )
                if extra_cond_ast:
                    extra_sql = self.translate(extra_cond_ast, boolean_context=True)
                    return SQLBinaryOp(operator="AND", left=result, right=extra_sql)
                return result
            if inner_op == "after":
                # ends after X -> intervalEnd(left) > X
                # Parser workaround: strip mis-parsed AND conditions
                cleaned_operand, extra_cond_ast = self._strip_and_conditions(expr.right.operand)
                # Use TIMESTAMP to preserve sub-day precision for dateTime values
                right_inner = self._ensure_date_cast(self.translate(cleaned_operand), "TIMESTAMP")
                interval_end = SQLFunctionCall(name="intervalEnd", args=[left])
                result = SQLBinaryOp(
                    operator=">",
                    left=SQLCast(expression=interval_end, target_type="VARCHAR"),
                    right=right_inner
                )
                if extra_cond_ast:
                    extra_sql = self.translate(extra_cond_ast, boolean_context=True)
                    return SQLBinaryOp(operator="AND", left=result, right=extra_sql)
                return result
            # Handle "ends during day of X" pattern (UnaryExpression with during)
            if inner_op == "during":
                interval_end = SQLFunctionCall(name="intervalEnd", args=[left])
                # Check if the operand is a 'precision of' expression
                if isinstance(expr.right.operand, BinaryExpression) and expr.right.operand.operator == "precision of":
                    precision = getattr(expr.right.operand.left, 'value', 'day')
                    if isinstance(precision, str):
                        precision = precision.lower()
                    # Parser workaround: strip mis-parsed AND conditions from right side
                    actual_interval_ast = expr.right.operand.right
                    extra_conditions = []
                    while isinstance(actual_interval_ast, BinaryExpression) and actual_interval_ast.operator == "and":
                        extra_conditions.append(actual_interval_ast.right)
                        actual_interval_ast = actual_interval_ast.left
                    extra_condition_ast = None
                    for cond in reversed(extra_conditions):
                        if extra_condition_ast is None:
                            extra_condition_ast = cond
                        else:
                            extra_condition_ast = BinaryExpression(
                                operator="and", left=extra_condition_ast, right=cond
                            )
                    interval_expr = self.translate(actual_interval_ast, usage=ExprUsage.SCALAR)
                    left_truncated = self._ensure_date_cast(
                        self._truncate_to_precision(interval_end, precision))
                    # Try boundary-aware comparison via _extract_interval_bounds
                    right_bounds = self._extract_interval_bounds(interval_expr, actual_interval_ast)
                    if right_bounds:
                        r_start, r_end, low_closed, high_closed = right_bounds
                        start_truncated = self._ensure_date_cast(
                            self._truncate_to_precision(r_start, precision))
                        end_truncated = self._ensure_date_cast(
                            self._truncate_to_precision(r_end, precision))
                        end_coalesced = SQLFunctionCall(
                            name="COALESCE",
                            args=[end_truncated, start_truncated],
                        )
                        start_op = ">=" if low_closed else ">"
                        end_op = "<=" if high_closed else "<"
                        result = SQLBinaryOp(
                            operator="AND",
                            left=SQLBinaryOp(operator=start_op, left=left_truncated, right=start_truncated),
                            right=SQLBinaryOp(operator=end_op, left=left_truncated, right=end_coalesced),
                        )
                    else:
                        # Fallback: use intervalStart/intervalEnd (closed by semantics)
                        right_start = SQLFunctionCall(name="intervalStart", args=[interval_expr])
                        right_end = SQLFunctionCall(name="intervalEnd", args=[interval_expr])
                        start_truncated = self._ensure_date_cast(
                            self._truncate_to_precision(right_start, precision))
                        end_truncated = self._ensure_date_cast(
                            self._truncate_to_precision(right_end, precision))
                        end_coalesced = SQLFunctionCall(
                            name="COALESCE",
                            args=[end_truncated, start_truncated],
                        )
                        result = SQLBinaryOp(
                            operator="AND",
                            left=SQLBinaryOp(operator=">=", left=left_truncated, right=start_truncated),
                            right=SQLBinaryOp(operator="<=", left=left_truncated, right=end_coalesced),
                        )
                    if extra_condition_ast:
                        extra_sql = self.translate(extra_condition_ast, boolean_context=True)
                        return SQLBinaryOp(operator="AND", left=result, right=extra_sql)
                    return result
                # Plain "ends during X" -> intervalContains(X, intervalEnd(left))
                interval_arg = self.translate(expr.right.operand, usage=ExprUsage.SCALAR)
                return SQLFunctionCall(name="intervalContains", args=[interval_arg, interval_end])
        if isinstance(expr.right, BinaryExpression):
            inner_op = expr.right.operator
            # Handle "ends during X" pattern - check if interval end is in X
            if inner_op == "during":
                interval_end = SQLFunctionCall(name="intervalEnd", args=[left])
                # Check if right.right is a 'precision of' expression
                if isinstance(expr.right.right, BinaryExpression) and expr.right.right.operator == "precision of":
                    precision = getattr(expr.right.right.left, 'value', 'day')
                    if isinstance(precision, str):
                        precision = precision.lower()
                    # Parser workaround: strip mis-parsed AND conditions
                    actual_interval_ast = expr.right.right.right
                    extra_conditions = []
                    while isinstance(actual_interval_ast, BinaryExpression) and actual_interval_ast.operator == "and":
                        extra_conditions.append(actual_interval_ast.right)
                        actual_interval_ast = actual_interval_ast.left
                    extra_condition_ast = None
                    for cond in reversed(extra_conditions):
                        if extra_condition_ast is None:
                            extra_condition_ast = cond
                        else:
                            extra_condition_ast = BinaryExpression(
                                operator="and", left=extra_condition_ast, right=cond
                            )
                    interval_expr = self.translate(actual_interval_ast, boolean_context=False)
                    left_truncated = self._ensure_date_cast(
                        self._truncate_to_precision(interval_end, precision))
                    right_start = SQLFunctionCall(name="intervalStart", args=[interval_expr])
                    right_end = SQLFunctionCall(name="intervalEnd", args=[interval_expr])
                    start_truncated = self._ensure_date_cast(
                        self._truncate_to_precision(right_start, precision))
                    end_truncated = self._ensure_date_cast(
                        self._truncate_to_precision(right_end, precision))
                    # Add COALESCE for NULL end date handling
                    end_with_null_handling = SQLFunctionCall(
                        name="COALESCE",
                        args=[end_truncated, start_truncated],
                    )
                    result = SQLBinaryOp(
                        operator="BETWEEN",
                        left=left_truncated,
                        right=SQLFunctionCall(
                            name="__between_args__",
                            args=[start_truncated, end_with_null_handling],
                        ),
                        precedence=PRECEDENCE["BETWEEN"],
                    )
                    if extra_condition_ast:
                        extra_sql = self.translate(extra_condition_ast, boolean_context=True)
                        return SQLBinaryOp(operator="AND", left=result, right=extra_sql)
                    return result
                # Plain "ends during X" -> intervalContains(X, intervalEnd(left))
                interval_arg = self.translate(expr.right.right, usage=ExprUsage.SCALAR)
                return SQLFunctionCall(name="intervalContains", args=[interval_arg, interval_end])
            # Complex pattern like "ends 1 day or less on or before day of"
            if " or " in inner_op:
                return self._translate_complex_interval_temporal_with_interval(
                    inner_op, left, expr.right, "end"
                )
            # "ends day of X" / "ends month of X" → precision comparison
            if inner_op == "precision of":
                precision_node = expr.right.left
                precision_str = getattr(precision_node, 'value', 'day')
                if isinstance(precision_str, str):
                    precision_str = precision_str.lower()
                inner_expr = expr.right.right
                interval_end = SQLFunctionCall(name="intervalEnd", args=[left])
                interval_start = SQLFunctionCall(name="intervalStart", args=[left])
                right_translated = self.translate(inner_expr, usage=ExprUsage.SCALAR)
                if self._is_fhir_interval_expression(right_translated) or isinstance(right_translated, SQLInterval):
                    # CQL 1.5 §9 Ends: start(left) >= start(right) AND
                    # end(left) == end(right), both at the given precision.
                    # Point operands promote to degenerate intervals [p, p],
                    # so the start conjunct compares against the point itself.
                    right_start = SQLFunctionCall(name="intervalStart", args=[right_translated])
                    right_end = SQLFunctionCall(name="intervalEnd", args=[right_translated])
                else:
                    right_start = right_translated
                    right_end = right_translated
                end_equal = SQLBinaryOp(
                    operator="=",
                    left=self._truncate_to_precision(interval_end, precision_str),
                    right=self._truncate_to_precision(right_end, precision_str),
                )
                start_ge = SQLBinaryOp(
                    operator=">=",
                    left=self._truncate_to_precision(interval_start, precision_str),
                    right=self._truncate_to_precision(right_start, precision_str),
                )
                return SQLBinaryOp(operator="AND", left=start_ge, right=end_equal)
        # intervalEndsSame expects two interval VARCHAR strings.
        # If right is a point (DATE cast), compare end directly instead.
        if isinstance(right, SQLCast) and right.target_type == "DATE":
            return SQLBinaryOp(
                operator="=",
                left=SQLCast(expression=SQLFunctionCall(name="intervalEnd", args=[left]), target_type="DATE"),
                right=right,
            )
        # Promote point operands to degenerate intervals [x, x] so that
        # intervalEndsSame receives two well-formed interval VARCHARs.
        left_is_interval = self._is_fhir_interval_expression(left) or isinstance(left, SQLInterval)
        right_is_interval = self._is_fhir_interval_expression(right) or isinstance(right, SQLInterval)
        left_arg = left if left_is_interval else self._point_as_interval(left)
        right_arg = right if right_is_interval else self._point_as_interval(right)
        return SQLFunctionCall(name="intervalEndsSame", args=[left_arg, right_arg])

        # Temporal precision operators: same day as, same month as, etc.
        # Also handles: same or before day of, same or after day of, etc.

    def _is_string_equivalence_operand(self, ast_expr, sql_expr) -> bool:
        """Return true when an operand is statically or operationally String."""
        if isinstance(ast_expr, Literal) and getattr(ast_expr, "type", None) == "String":
            return True
        if isinstance(ast_expr, Identifier):
            meta = self.context.definition_meta.get(ast_expr.name)
            meta_type = _normalize_cql_type_name(getattr(meta, "cql_type", None)) if meta else "Any"
            if meta_type == "String":
                return True
        if isinstance(ast_expr, BinaryExpression) and ast_expr.operator == "as":
            target = ast_expr.right
            if isinstance(target, NamedTypeSpecifier) and target.name.split(".")[-1] == "String":
                return True
        if isinstance(ast_expr, FunctionRef) and ast_expr.name.lower() == "tostring":
            return True
        if isinstance(sql_expr, SQLLiteral) and isinstance(sql_expr.value, str):
            return True
        if isinstance(sql_expr, SQLCast) and sql_expr.target_type.upper() in {"VARCHAR", "TEXT", "STRING"}:
            return True
        if isinstance(sql_expr, SQLFunctionCall) and sql_expr.name in {
            "fhirpath_text", "fhirpath_scalar", "ToString", "RatioToString",
            "QuantityToString", "system.substring", "system.upper",
            "system.lower", "system.replace", "CONCAT", "TRIM", "LTRIM", "RTRIM",
            "UPPER", "LOWER", "REPLACE", "SUBSTRING",
        }:
            return True
        return False

    @staticmethod
    def _normalize_string_for_equivalence(expr: SQLExpression) -> SQLExpression:
        lowered = SQLFunctionCall(name="lower", args=[expr])
        collapsed = SQLFunctionCall(
            name="regexp_replace",
            args=[lowered, SQLLiteral(r"\s+"), SQLLiteral(" "), SQLLiteral("g")],
        )
        return SQLFunctionCall(name="trim", args=[collapsed])

    @staticmethod
    def _and_all(expressions: list[SQLExpression]) -> SQLExpression:
        if not expressions:
            return SQLLiteral(value=True)
        result = expressions[0]
        for expression in expressions[1:]:
            result = SQLBinaryOp(operator="AND", left=result, right=expression)
        return result

    def _translate_list_equivalence(self, expr: BinaryExpression, is_negated: bool) -> Optional[SQLExpression]:
        if not isinstance(expr.left, ListExpression) or not isinstance(expr.right, ListExpression):
            return None
        if len(expr.left.elements) != len(expr.right.elements):
            result: SQLExpression = SQLLiteral(value=False)
        else:
            result = self._and_all([
                self.translate(
                    BinaryExpression(operator="~", left=left_item, right=right_item),
                    usage=ExprUsage.BOOLEAN,
                )
                for left_item, right_item in zip(expr.left.elements, expr.right.elements)
            ])
        if is_negated:
            return SQLUnaryOp(operator="NOT", operand=result)
        return result

    def _translate_tuple_equivalence(self, expr: BinaryExpression, is_negated: bool) -> Optional[SQLExpression]:
        if not isinstance(expr.left, TupleExpression) or not isinstance(expr.right, TupleExpression):
            return None
        left_elems = {element.name: element.type for element in expr.left.elements}
        right_elems = {element.name: element.type for element in expr.right.elements}
        if set(left_elems) != set(right_elems):
            result: SQLExpression = SQLLiteral(value=False)
        else:
            result = self._and_all([
                self.translate(
                    BinaryExpression(operator="~", left=left_elems[name], right=right_elems[name]),
                    usage=ExprUsage.BOOLEAN,
                )
                for name in sorted(left_elems)
            ])
        if is_negated:
            return SQLUnaryOp(operator="NOT", operand=result)
        return result

    def _translate_string_equivalence(
        self,
        left: SQLExpression,
        right: SQLExpression,
        expr: BinaryExpression,
        is_negated: bool,
    ) -> Optional[SQLExpression]:
        if not (
            self._is_string_equivalence_operand(expr.left, left)
            and self._is_string_equivalence_operand(expr.right, right)
        ):
            return None
        normalized_equal = SQLBinaryOp(
            operator="=",
            left=self._normalize_string_for_equivalence(left),
            right=self._normalize_string_for_equivalence(right),
        )
        result: SQLExpression = SQLCase(
            when_clauses=[
                (
                    SQLBinaryOp(
                        operator="AND",
                        left=SQLUnaryOp(operator="IS NULL", operand=left, prefix=False),
                        right=SQLUnaryOp(operator="IS NULL", operand=right, prefix=False),
                    ),
                    SQLLiteral(value=True),
                ),
                (
                    SQLBinaryOp(
                        operator="OR",
                        left=SQLUnaryOp(operator="IS NULL", operand=left, prefix=False),
                        right=SQLUnaryOp(operator="IS NULL", operand=right, prefix=False),
                    ),
                    SQLLiteral(value=False),
                ),
            ],
            else_clause=normalized_equal,
        )
        if is_negated:
            return SQLUnaryOp(operator="NOT", operand=result)
        return result

    @staticmethod
    def _numeric_literal_equivalence_precision(ast_expr) -> Optional[int]:
        if not isinstance(ast_expr, Literal):
            return None
        literal_type = _normalize_cql_type_name(getattr(ast_expr, "type", None))
        if literal_type in {"Integer", "Long"}:
            return 0
        if literal_type != "Decimal":
            return None
        raw_value = str(getattr(ast_expr, "raw_str", "") or "")
        if "." not in raw_value:
            return 0
        fraction = raw_value.split(".", 1)[1].rstrip("0")
        return len(fraction)

    def _translate_decimal_literal_equivalence(
        self,
        left: SQLExpression,
        right: SQLExpression,
        expr: BinaryExpression,
        is_negated: bool,
    ) -> Optional[SQLExpression]:
        left_precision = self._numeric_literal_equivalence_precision(expr.left)
        right_precision = self._numeric_literal_equivalence_precision(expr.right)
        if left_precision is None or right_precision is None:
            return None
        if not (
            _normalize_cql_type_name(getattr(expr.left, "type", None)) == "Decimal"
            or _normalize_cql_type_name(getattr(expr.right, "type", None)) == "Decimal"
        ):
            return None
        precision = min(left_precision, right_precision)
        delta = SQLFunctionCall(
            name="ABS",
            args=[
                SQLBinaryOp(
                    operator="-",
                    left=SQLCast(expression=left, target_type="DECIMAL(38,8)"),
                    right=SQLCast(expression=right, target_type="DECIMAL(38,8)"),
                )
            ],
        )
        tolerance = SQLCast(
            expression=SQLLiteral(value=f"{0.5 * (10 ** -precision):.8f}"),
            target_type="DECIMAL(38,8)",
        )
        result: SQLExpression = SQLBinaryOp(
            operator="<=",
            left=delta,
            right=tolerance,
        )
        if is_negated:
            return SQLUnaryOp(operator="NOT", operand=result)
        return result

    def _static_equivalence_incompatible(self, left_ast, right_ast) -> bool:
        """Detect statically incompatible primitive operands for CQL equivalence."""
        def _literal_type(node) -> Optional[str]:
            if not isinstance(node, Literal):
                return None
            if node.value is None:
                return "Any"
            explicit = getattr(node, "type", None)
            if explicit:
                return _normalize_cql_type_name(explicit)
            if isinstance(node.value, bool):
                return "Boolean"
            if isinstance(node.value, int):
                return "Integer"
            if isinstance(node.value, float):
                return "Decimal"
            if isinstance(node.value, str):
                return "String"
            return None

        left_type = _literal_type(left_ast)
        right_type = _literal_type(right_ast)
        if left_type is None or right_type is None:
            return False
        if "Any" in {left_type, right_type}:
            return False
        if left_type == right_type:
            return False
        numeric = {"Integer", "Long", "Decimal"}
        temporal = {"Date", "DateTime", "Time"}
        if left_type in numeric and right_type in numeric:
            return False
        if left_type in temporal and right_type in temporal:
            return False
        return True

    def _translate_code_is_op(self, expr, *, negated: bool) -> Optional[SQLExpression]:
        """Phase 3: code-vs-code ``is`` / ``is not`` operator.

        Returns ``None`` if either operand does not statically resolve to a
        code reference (the caller falls through to the existing
        ``IS NULL`` / ``IS NOT NULL`` behavior). When both resolve:

        * Closure table loaded: emit
          ``EXISTS (... ancestor=Y, descendant=X ...)`` per FDD §3d.
        * Closure table NOT loaded: emit literal
          ``(X_sys, X_code) = (Y_sys, Y_code)`` (or ``!=`` for negated).

        Direction (INV-6): right subsumes left. The reflexive row inserted
        by the closure builder means ``X is X`` returns True.
        """
        left_info = self._resolve_code_ref_inline(expr.left)
        right_info = self._resolve_code_ref_inline(expr.right)
        if not left_info or not right_info:
            return None

        left_entries = self._code_entries_static(left_info)
        right_entries = self._code_entries_static(right_info)
        if not left_entries or not right_entries:
            return None

        from ...duckdb.udf.system_resolver import SystemResolver

        # Build a disjunction across every (left, right) entry pair (Concept
        # operands may carry multiple codes). Singleton-vs-singleton is the
        # overwhelmingly common case.
        ors: List[SQLExpression] = []
        for le in left_entries:
            for re_ in right_entries:
                l_sys = SystemResolver.normalize(le.get("codesystem", "")) or le.get(
                    "codesystem", ""
                )
                l_code = le.get("code", "")
                r_sys = SystemResolver.normalize(re_.get("codesystem", "")) or re_.get(
                    "codesystem", ""
                )
                r_code = re_.get("code", "")

                l_sys_lit = SQLLiteral(value=l_sys)
                l_code_lit = SQLLiteral(value=l_code)
                r_sys_lit = SQLLiteral(value=r_sys)
                r_code_lit = SQLLiteral(value=r_code)

                if getattr(self.context, "closure_table_loaded", False):
                    # Direction: right subsumes left (ancestor=Y, descendant=X).
                    l_sys_sql = l_sys_lit.to_sql()
                    l_code_sql = l_code_lit.to_sql()
                    r_sys_sql = r_sys_lit.to_sql()
                    r_code_sql = r_code_lit.to_sql()
                    pair_match: SQLExpression = SQLRaw(
                        raw_sql=(
                            "EXISTS (SELECT 1 FROM terminology_closure _tc "
                            f"WHERE _tc.ancestor_system = {r_sys_sql} "
                            f"AND _tc.ancestor_code = {r_code_sql} "
                            f"AND _tc.descendant_system = {l_sys_sql} "
                            f"AND _tc.descendant_code = {l_code_sql})"
                        )
                    )
                else:
                    # Literal-match fallback: (L_sys, L_code) = (R_sys, R_code).
                    pair_match = SQLBinaryOp(
                        operator="AND",
                        left=SQLBinaryOp(operator="=", left=l_sys_lit, right=r_sys_lit),
                        right=SQLBinaryOp(operator="=", left=l_code_lit, right=r_code_lit),
                    )
                ors.append(pair_match)

        if not ors:
            return None
        result: SQLExpression = ors[0]
        for next_clause in ors[1:]:
            result = SQLBinaryOp(operator="OR", left=result, right=next_clause)
        if negated:
            result = SQLUnaryOp(operator="NOT", operand=result)
        return result

    def _resolve_code_ref_inline(self, operand_ast) -> Optional[dict]:
        """Phase 3 inline code-ref resolver used by ``_translate_code_is_op``.

        This is a thin wrapper around the existing
        :meth:`_static_clinical_value_object` so the ``is`` operator can
        statically resolve both CodeSelector and Identifier-with-Code-def
        operands. Returns ``None`` when the operand is not a compile-time
        code reference (query alias, runtime parameter, etc.).
        """
        if isinstance(operand_ast, CodeSelector):
            system_url = self.context.codesystems.get(
                operand_ast.system, operand_ast.system
            )
            return {
                "code": operand_ast.code,
                "codesystem": system_url,
                "display": operand_ast.display,
            }
        if isinstance(operand_ast, Identifier):
            if self.context.is_alias(operand_ast.name):
                return None
            info = self.context.get_code(operand_ast.name)
            if info is not None:
                return info
        static_value = self._static_clinical_value_object(operand_ast)
        if static_value:
            if isinstance(static_value.get("codes"), list):
                return {
                    "codes": static_value.get("codes", []),
                    "display": static_value.get("display"),
                    "is_concept": True,
                }
            if static_value.get("code"):
                return {
                    "code": static_value.get("code", ""),
                    "codesystem": static_value.get("system", ""),
                    "version": static_value.get("version"),
                    "display": static_value.get("display"),
                }
        return None

    @staticmethod
    def _code_entries_static(code_info: Optional[dict]) -> List[dict]:
        """Mirror of the inline ``_code_entries`` from the equivalence path,
        exposed as a static helper for ``_translate_code_is_op``.
        """
        if not isinstance(code_info, dict):
            return []
        if code_info.get("is_concept") or isinstance(code_info.get("codes"), list):
            entries = code_info.get("codes") or []
            return [entry for entry in entries if isinstance(entry, dict)]
        if code_info.get("code"):
            return [code_info]
        return []

    def _translate_equivalence_op(self, operator, left, right, expr) -> SQLExpression:
        """Extracted from _translate_binary_expression."""
        is_negated = operator == "!~"

        left_is_interval = self._is_fhir_interval_expression(left)
        right_is_interval = self._is_fhir_interval_expression(right)
        if left_is_interval or right_is_interval:
            result: SQLExpression = SQLFunctionCall(name="intervalEquivalent", args=[left, right])
            if is_negated:
                result = SQLUnaryOp(operator="NOT", operand=result)
            return result

        # CQL-02 EXPLORER QA-002: statically-known List<Code> operands (list
        # literals, Concept.codes / ToConcept(...).codes accessors, Concept
        # values) must use element-wise Code equivalence (CQL 1.5 Equivalent
        # for lists: same length, element-wise equivalence in order). Without
        # this fold, a `.codes` SQLArray operand falls through to the generic
        # CQLListEquivalentEq SQL path, which compares Code JSON byte-wise
        # (case-sensitive) instead of applying Code equivalence.
        _qa002_left_codes = self._static_code_list(expr.left)
        _qa002_right_codes = self._static_code_list(expr.right)
        if _qa002_left_codes is not None and _qa002_right_codes is not None:
            if len(_qa002_left_codes) != len(_qa002_right_codes):
                return SQLLiteral(value=is_negated)
            pairs: list[SQLExpression] = [
                SQLLiteral(
                    value=self._code_equivalence_key(l) == self._code_equivalence_key(r)
                )
                for l, r in zip(_qa002_left_codes, _qa002_right_codes)
            ]
            result = self._and_all(pairs) if pairs else SQLLiteral(value=True)
            if is_negated:
                result = SQLUnaryOp(operator="NOT", operand=result)
            return result

        # Gap 12: Check if either operand is a code reference
        code_info = None
        resource_expr = None

        list_result = self._translate_list_equivalence(expr, is_negated)
        if list_result is not None:
            return list_result

        if self._is_list_operands(left, right, expr):
            # CQL-18 SKEPTIC relaunch QA-003: promote scalar fhirpath_text
            # operands (first-node truncation) to full list projections.
            left = _promote_fhirpath_text_list(left)
            right = _promote_fhirpath_text_list(right)
            result: SQLExpression = SQLFunctionCall(
                name="CQLListEquivalentEq",
                args=[left, right],
            )
            if is_negated:
                result = SQLUnaryOp(operator="NOT", operand=result)
            return result

        tuple_result = self._translate_tuple_equivalence(expr, is_negated)
        if tuple_result is not None:
            return tuple_result

        decimal_result = self._translate_decimal_literal_equivalence(left, right, expr, is_negated)
        if decimal_result is not None:
            return decimal_result

        if self._static_equivalence_incompatible(expr.left, expr.right):
            return SQLLiteral(value=is_negated)

        def _resolve_code_ref(operand_ast):
            """Try to resolve a code reference from Identifier, QualifiedIdentifier, Property, CodeSelector, or ParameterPlaceholder."""
            if isinstance(operand_ast, CodeSelector):
                system_url = self.context.codesystems.get(operand_ast.system, operand_ast.system)
                return {"code": operand_ast.code, "codesystem": system_url, "display": operand_ast.display}
            if isinstance(operand_ast, Identifier):
                # Skip query aliases — they shadow code definitions
                if self.context.is_alias(operand_ast.name):
                    return None
                info = self.context.get_code(operand_ast.name)
                if info is not None:
                    return info
                # CQL-02 EXPLORER QA-001 fix: top-level `define X: <clinical literal>`
                # was not resolved by get_code (which only sees `code "X": ...`
                # declarations). Fall back to the definition's CQL AST so the
                # equivalence operator can fold static Code/Concept comparisons
                # at translation time.
                source_ast = self._definition_source_ast(operand_ast.name, operand_ast)
                if source_ast is not None:
                    static_value = self._static_clinical_value_object(source_ast)
                    if static_value:
                        if isinstance(static_value.get("codes"), list):
                            return {
                                "codes": static_value.get("codes", []),
                                "display": static_value.get("display"),
                                "is_concept": True,
                            }
                        if static_value.get("code"):
                            return {
                                "code": static_value.get("code", ""),
                                "codesystem": static_value.get("system", ""),
                                "version": static_value.get("version"),
                                "display": static_value.get("display"),
                            }
                return None
            if isinstance(operand_ast, QualifiedIdentifier) and len(operand_ast.parts) >= 2:
                # Library-qualified code ref: QICoreCommon."confirmed" → look up "confirmed"
                code_name = operand_ast.parts[-1]
                return self.context.get_code(code_name)
            if isinstance(operand_ast, Property) and isinstance(operand_ast.source, Identifier):
                # Property(source=Identifier('QICoreCommon'), path='confirmed')
                # This is a library-qualified code reference from function inlining
                if operand_ast.source.name in self.context.includes:
                    return self.context.get_code(operand_ast.path)
            if isinstance(operand_ast, ParameterPlaceholder):
                # Inlined function parameter carrying a pre-translated SQL literal
                # for a code reference (legacy "system|code" or JSON Code).
                sql_val = operand_ast.sql_expr
                if isinstance(sql_val, SQLLiteral) and isinstance(sql_val.value, str):
                    if '|' in sql_val.value and not sql_val.value.strip().startswith("{"):
                        system, code = sql_val.value.rsplit('|', 1)
                        return {"code": code, "codesystem": system}
                    try:
                        parsed = json.loads(sql_val.value)
                    except (TypeError, ValueError):
                        return None
                    if isinstance(parsed, dict) and parsed.get("code"):
                        return {
                            "code": parsed.get("code", ""),
                            "codesystem": parsed.get("system", ""),
                        }
                    if isinstance(parsed, dict) and isinstance(parsed.get("codes"), list):
                        return {
                            "codes": parsed.get("codes", []),
                            "display": parsed.get("display"),
                            "is_concept": True,
                        }
            static_value = self._static_clinical_value_object(operand_ast)
            if static_value:
                if isinstance(static_value.get("codes"), list):
                    return {
                        "codes": static_value.get("codes", []),
                        "display": static_value.get("display"),
                        "is_concept": True,
                    }
                if static_value.get("code"):
                    return {
                        "code": static_value.get("code", ""),
                        "codesystem": static_value.get("system", ""),
                        "version": static_value.get("version"),
                        "display": static_value.get("display"),
                    }
            return None

        def _code_entries(code_info):
            """Return normalized Code entries for Code or Concept metadata."""
            if not isinstance(code_info, dict):
                return []
            if code_info.get("is_concept") or isinstance(code_info.get("codes"), list):
                entries = code_info.get("codes") or []
                return [entry for entry in entries if isinstance(entry, dict)]
            if code_info.get("code"):
                return [code_info]
            return []

        def _code_key(code_info):
            # CQL-02 EXPLORER QA-001: shared null-aware key. Absent and
            # explicit-null systems/codes both map to None (equivalent to
            # each other, but NOT to the empty string).
            return self._code_equivalence_key(code_info)

        def _codes_equivalent(left_info, right_info):
            left_codes = _code_entries(left_info)
            right_codes = _code_entries(right_info)
            if not left_codes or not right_codes:
                return False
            left_keys = {_code_key(code) for code in left_codes}
            return any(_code_key(code) in left_keys for code in right_codes)

        def _emit_closure_aware_codes_equivalent(
            left_info, right_info, negated: bool
        ) -> SQLExpression:
            """Phase 3: emit SQL that OR's literal match with bidirectional
            closure membership. Falls back to the byte-identical literal
            SQLLiteral form when no closure table is loaded.
            """
            left_entries = _code_entries(left_info)
            right_entries = _code_entries(right_info)
            if not left_entries or not right_entries:
                return SQLLiteral(value=negated)

            # Build disjunction of (literal OR closure-EXISTS) over every
            # (left_code, right_code) pair. For singleton-vs-singleton (the
            # overwhelmingly common case), this is a single OR-of-3.
            from ...duckdb.udf.system_resolver import SystemResolver

            ors: list[SQLExpression] = []
            for le in left_entries:
                for re_ in right_entries:
                    l_sys, l_code = _code_key(le)
                    r_sys, r_code = _code_key(re_)
                    l_sys_n = SystemResolver.normalize(l_sys) or l_sys
                    r_sys_n = SystemResolver.normalize(r_sys) or r_sys
                    l_sys_sql = SQLLiteral(value=l_sys_n).to_sql()
                    l_code_sql = SQLLiteral(value=l_code).to_sql()
                    r_sys_sql = SQLLiteral(value=r_sys_n).to_sql()
                    r_code_sql = SQLLiteral(value=r_code).to_sql()

                    l_sys_lit = SQLLiteral(value=l_sys_n)
                    l_code_lit = SQLLiteral(value=l_code)
                    r_sys_lit = SQLLiteral(value=r_sys_n)
                    r_code_lit = SQLLiteral(value=r_code)

                    # Literal match: (L_sys, L_code) = (R_sys, R_code)
                    literal_match = SQLBinaryOp(
                        operator="AND",
                        left=SQLBinaryOp(operator="=", left=l_sys_lit, right=r_sys_lit),
                        right=SQLBinaryOp(operator="=", left=l_code_lit, right=r_code_lit),
                    )

                    # Bidirectional closure: L subsumes R OR R subsumes L.
                    l_anc_r = SQLRaw(
                        raw_sql=(
                            "EXISTS (SELECT 1 FROM terminology_closure _tc "
                            f"WHERE _tc.ancestor_system = {l_sys_sql} "
                            f"AND _tc.ancestor_code = {l_code_sql} "
                            f"AND _tc.descendant_system = {r_sys_sql} "
                            f"AND _tc.descendant_code = {r_code_sql})"
                        )
                    )
                    r_anc_l = SQLRaw(
                        raw_sql=(
                            "EXISTS (SELECT 1 FROM terminology_closure _tc "
                            f"WHERE _tc.ancestor_system = {r_sys_sql} "
                            f"AND _tc.ancestor_code = {r_code_sql} "
                            f"AND _tc.descendant_system = {l_sys_sql} "
                            f"AND _tc.descendant_code = {l_code_sql})"
                        )
                    )
                    pair_match = SQLBinaryOp(
                        operator="OR",
                        left=SQLBinaryOp(operator="OR", left=literal_match, right=l_anc_r),
                        right=r_anc_l,
                    )
                    ors.append(pair_match)

            if not ors:
                return SQLLiteral(value=negated)
            result: SQLExpression = ors[0]
            for next_clause in ors[1:]:
                result = SQLBinaryOp(operator="OR", left=result, right=next_clause)
            if negated:
                result = SQLUnaryOp(operator="NOT", operand=result)
            return result

        # QA-010: When both sides are compile-time code references,
        # compare directly instead of routing through the terminology translator.
        _left_code = _resolve_code_ref(expr.left)
        _right_code = _resolve_code_ref(expr.right)
        if _left_code and _right_code:
            # Phase 3: route through the closure table when populated so
            # subsumption is honored; otherwise byte-identical fallback.
            if getattr(self.context, "closure_table_loaded", False):
                return _emit_closure_aware_codes_equivalent(
                    _left_code, _right_code, is_negated
                )
            _match = _codes_equivalent(_left_code, _right_code)
            return SQLLiteral(value=_match != is_negated)

        code_info = _resolve_code_ref(expr.right)
        if code_info:
            resource_expr = left
        if not code_info:
            code_info = _resolve_code_ref(expr.left)
            if code_info:
                resource_expr = right
        if code_info and resource_expr:
            # CQL §12.2: null ~ X = false (equivalence with null is always false)
            if isinstance(resource_expr, SQLNull):
                return SQLLiteral(value=is_negated)
            code_entries = _code_entries(code_info)
            if not code_entries:
                return SQLLiteral(value=is_negated)
            # Extract the property path from the CQL AST for the resource side
            # Default to "code" if we can't determine it
            base_path = "code"
            resource_side_ast = expr.left if resource_expr is left else expr.right
            # Unwrap 'as' cast (e.g., O.value as Concept ~ code)
            _as_type_spec: Optional[NamedTypeSpecifier] = None
            if isinstance(resource_side_ast, BinaryExpression) and resource_side_ast.operator == "as":
                _as_type_spec = resource_side_ast.right if isinstance(resource_side_ast.right, NamedTypeSpecifier) else None
                resource_side_ast = resource_side_ast.left
            if isinstance(resource_side_ast, Property):
                # Walk the Property chain to build the full path
                # (e.g., hospitalization.dischargeDisposition, not just dischargeDisposition)
                parts = []
                current = resource_side_ast
                while isinstance(current, Property):
                    parts.append(current.path)
                    current = current.source
                parts.reverse()
                property_root = current
                # Resolve choice type when 'as' cast is present
                # (e.g., value as Concept → valueCodeableConcept)
                if _as_type_spec and parts:
                    _cql_to_fhir_suffix = {
                        "Concept": "CodeableConcept",
                        "Code": "Coding",
                        "Quantity": "Quantity",
                        "Integer": "Integer",
                        "Decimal": "Decimal",
                        "String": "String",
                        "Boolean": "Boolean",
                        "DateTime": "DateTime",
                        "Date": "Date",
                        "Time": "Time",
                        "CodeableConcept": "CodeableConcept",
                        "Coding": "Coding",
                        "Reference": "Reference",
                        "Period": "Period",
                    }
                    _fhir_suffix = _cql_to_fhir_suffix.get(_as_type_spec.name)
                    if _fhir_suffix:
                        last_part = parts[-1]
                        _res_type = self.context.resource_type
                        if not _res_type and isinstance(property_root, Identifier):
                            _res_type = self.context._alias_resource_types.get(property_root.name)
                        if _res_type and self.context.fhir_schema:
                            _choice_types = self.context.fhir_schema.get_choice_types(_res_type, last_part)
                            if _choice_types:
                                parts[-1] = last_part + _fhir_suffix
                base_path = ".".join(parts)
            elif isinstance(resource_side_ast, Identifier) and self.context.is_alias(resource_side_ast.name):
                # Alias for a property access (e.g., `(E.type) T` — T aliases E.type).
                # Extract the property path from the translated SQL expression.
                if isinstance(resource_expr, SQLFunctionCall) and resource_expr.name in ("fhirpath_text", "fhirpath_date", "fhirpath_bool"):
                    if len(resource_expr.args) >= 2 and isinstance(resource_expr.args[1], SQLLiteral):
                        base_path = resource_expr.args[1].value
                elif isinstance(resource_expr, SQLQualifiedIdentifier) and len(resource_expr.parts) >= 2:
                    base_path = resource_expr.parts[-1]
            # QICore extension properties need extension FHIRPath navigation
            _ext_prop = _get_qicore_extension_fhirpath(
                self.context.profile_registry, self.context.resource_type, base_path
            )
            if _ext_prop is not None:
                # Strip the value-type suffix for the code-comparison path (bare .value)
                base_path = _ext_prop.rsplit(".value", 1)[0] + ".value"

            # Detect whether the property is a Coding type (vs
            # CodeableConcept).  Coding properties (e.g. Encounter.class)
            # do NOT have a nested .coding array, so we must skip
            # the .coding() navigation step.
            _is_coding_type = False
            if self.context.fhir_schema:
                # Determine the FHIR resource type from the AST context
                _res_type = self.context.resource_type
                if not _res_type:
                    # Try to resolve from alias→resource_type mapping
                    _src_ast = resource_side_ast
                    while isinstance(_src_ast, Property) and _src_ast.source:
                        _src_ast = _src_ast.source
                    if isinstance(_src_ast, Identifier):
                        _res_type = self.context._alias_resource_types.get(_src_ast.name)
                if _res_type:
                    _lookup_path = (base_path.split(".")[0]
                        if "." not in base_path or base_path.startswith("extension")
                        else base_path)
                    _el_type = self.context.fhir_schema.get_element_type(
                        _res_type, _lookup_path,
                    )
                    if _el_type == "Coding":
                        _is_coding_type = True

            if len(code_entries) > 1 or code_info.get("is_concept"):
                normalized_codes = []
                for entry in code_entries:
                    normalized = dict(entry)
                    system = normalized.get("codesystem", normalized.get("system", ""))
                    if system:
                        normalized["system"] = self.context.codesystems.get(system, system)
                    normalized_codes.append(normalized)
                fhirpath_expr = build_multi_coding_exists_expr(
                    base_path, normalized_codes, is_coding_type=_is_coding_type
                )
            else:
                code_entry = code_entries[0] if code_entries else {}
                system_raw = code_entry.get("codesystem", code_entry.get("system", ""))
                system_url = self.context.codesystems.get(system_raw, system_raw)
                code_value = code_entry.get("code", "")
                fhirpath_expr = build_coding_exists_expr(
                    base_path, system_url=system_url, code_value=code_value,
                    is_coding_type=_is_coding_type,
                )
            # resource_expr is the translated property (e.g., fhirpath_text(resource, 'verificationStatus'))
            # but we need the actual resource, not the property value, for fhirpath_bool
            # Extract the resource reference from the translated fhirpath call
            if isinstance(resource_expr, SQLFunctionCall) and resource_expr.name in ("fhirpath_text", "fhirpath_date", "fhirpath_bool"):
                # Use the first arg (the resource reference)
                resource_ref = resource_expr.args[0]
            elif isinstance(resource_expr, SQLQualifiedIdentifier) and len(resource_expr.parts) >= 2:
                # E.type → E.resource (replace last part with "resource")
                resource_ref = SQLQualifiedIdentifier(parts=resource_expr.parts[:-1] + ["resource"])
            elif isinstance(resource_side_ast, Property):
                root = resource_side_ast
                while isinstance(root, Property):
                    root = root.source
                if (
                    isinstance(root, Identifier)
                    and (
                        self.context.is_alias(root.name)
                        or root.name in self.context._alias_resource_types
                    )
                ):
                    resource_ref = SQLQualifiedIdentifier(parts=[root.name, "resource"])
                else:
                    resource_ref = resource_expr
            elif isinstance(resource_expr, SQLIdentifier) and not resource_expr.quoted:
                # Bare alias (e.g., HospiceAssessment) — needs .resource for fhirpath
                alias_name = resource_expr.name
                if self.context.is_alias(alias_name):
                    resource_ref = SQLQualifiedIdentifier(parts=[alias_name, "resource"])
                else:
                    resource_ref = resource_expr
            else:
                resource_ref = resource_expr
            result_expr = SQLFunctionCall(
                name="fhirpath_bool",
                args=[resource_ref, SQLLiteral(value=fhirpath_expr)],
            )
            if is_negated:
                return SQLUnaryOp(operator="NOT", operand=result_expr)
            return result_expr

        # CodeableConcept ~ string literal: compare against coding.code values.
        # When one operand is a CodeableConcept-typed property and the other is a
        # bare string literal (no system), we cannot use the code-reference path
        # above (which requires system+code). Instead, check if any coding.code
        # in the CodeableConcept matches the string value.
        _cc_result = self._try_codeable_concept_string_equiv(expr, left, right)
        if _cc_result is not None:
            if is_negated:
                return SQLUnaryOp(operator="NOT", operand=_cc_result)
            return _cc_result

        # CQL §12.1/§12.2: List equivalence requires element type compatibility.
        # DuckDB implicitly coerces [1,2,3] = ['1','2','3'] to true; CQL does not.
        if isinstance(left, SQLArray) and isinstance(right, SQLArray):
            left_types = {type(e.value).__name__ for e in left.elements if isinstance(e, SQLLiteral)}
            right_types = {type(e.value).__name__ for e in right.elements if isinstance(e, SQLLiteral)}
            if left_types and right_types and left_types.isdisjoint(right_types):
                return SQLLiteral(value=is_negated)

        # CQL §Equivalent (Date, DateTime, Time): "the comparison is performed
        # in the same way as it is for equality, except that if one input has
        # a value for a given precision and the other does not, the comparison
        # stops and the result is false, rather than null."
        #
        # Route Date/DateTime/Time equivalence through the same precision-aware
        # `cqlDateTimeEqual` UDF that `=` uses, then convert any NULL (uncertain)
        # result to False (per spec: equivalence "always returns true or false").
        # This must run BEFORE the string-equivalence fall-through because
        # DateTime literals translate to SQLLiteral(VARCHAR), which would
        # otherwise be misclassified as String operands and compared with raw
        # string equality (no timezone normalization).
        if (
            (self._is_temporal_cql_expr(expr.left) or self._is_temporal_cql_expr(expr.right))
            and not (
                self._is_timeofday_cql_expr(expr.left)
                or self._is_timeofday_cql_expr(expr.right)
            )
        ):
            cmp_result = SQLFunctionCall(
                name="cqlDateTimeEqual",
                args=[
                    SQLCast(expression=left, target_type="VARCHAR"),
                    SQLCast(expression=right, target_type="VARCHAR"),
                ],
            )
            equiv_temporal = SQLCase(
                when_clauses=[
                    (
                        SQLUnaryOp(operator="IS NULL", operand=cmp_result, prefix=False),
                        SQLLiteral(value=False),
                    ),
                ],
                else_clause=cmp_result,
            )
            if is_negated:
                return SQLUnaryOp(operator="NOT", operand=equiv_temporal)
            return equiv_temporal

        string_result = self._translate_string_equivalence(left, right, expr, is_negated)
        if string_result is not None:
            return string_result

        # CQL §12.2: Ratio equivalence compares the represented ratio value,
        # not the internal JSON/string representation.
        left_is_ratio = _is_ratio_expression(left) or self._is_cql_ratio_expr(expr.left)
        right_is_ratio = _is_ratio_expression(right) or self._is_cql_ratio_expr(expr.right)
        if left_is_ratio or right_is_ratio:
            cmp_result = SQLFunctionCall(
                name="ratioCompare",
                args=[
                    SQLCast(expression=left, target_type="VARCHAR"),
                    SQLCast(expression=right, target_type="VARCHAR"),
                    SQLLiteral(value="~"),
                ],
            )
            equiv_ratio = SQLCase(
                when_clauses=[
                    (
                        SQLBinaryOp(
                            operator="AND",
                            left=SQLUnaryOp(operator="IS NULL", operand=left, prefix=False),
                            right=SQLUnaryOp(operator="IS NULL", operand=right, prefix=False),
                        ),
                        SQLLiteral(value=True),
                    ),
                    (
                        SQLBinaryOp(
                            operator="OR",
                            left=SQLUnaryOp(operator="IS NULL", operand=left, prefix=False),
                            right=SQLUnaryOp(operator="IS NULL", operand=right, prefix=False),
                        ),
                        SQLLiteral(value=False),
                    ),
                ],
                else_clause=SQLFunctionCall(
                    name="COALESCE",
                    args=[cmp_result, SQLLiteral(value=False)],
                ),
            )
            if is_negated:
                return SQLUnaryOp(operator="NOT", operand=equiv_ratio)
            return equiv_ratio

        # CQL §12.2: Quantity equivalence — convert units and compare values.
        left_is_qty = _is_quantity_expression(left) or self._is_cql_quantity_expr(expr.left)
        right_is_qty = _is_quantity_expression(right) or self._is_cql_quantity_expr(expr.right)
        if left_is_qty or right_is_qty:
            # CQL 1.5 Table 9-E: Integer/Long/Decimal implicitly convert to
            # Quantity with default unit '1'. A static bare numeric literal
            # compared against a Quantity must therefore be promoted to a
            # unit-'1' quantity, not passed raw to quantityCompare (which
            # expects quantity JSON and would raise a binder error).
            def _static_numeric(e):
                return (isinstance(e, SQLLiteral)
                        and isinstance(e.value, (int, float))
                        and not isinstance(e.value, bool))

            def _static_qty(e):
                return (isinstance(e, SQLFunctionCall) and e.name == "parse_quantity"
                        and self._extract_quantity_numeric_value(e) is not None)

            # Static literals only: dynamic FHIR-sourced quantities keep their
            # FHIRHelpers/fixture-pinned comparison path (CMS72 INR > 3.5 with
            # a non-UCUM unit display).
            if right_is_qty and _static_qty(right) and _static_numeric(left):
                left = _quantity_operand_for_arithmetic(left, is_quantity=False)
            elif left_is_qty and _static_qty(left) and _static_numeric(right):
                right = _quantity_operand_for_arithmetic(right, is_quantity=False)
            cmp_result = SQLFunctionCall(
                name="quantityCompare",
                args=[left, right, SQLLiteral(value="~")],
            )
            # Equivalence: null-safe (both null → true, one null → false)
            equiv_qty = SQLCase(
                when_clauses=[
                    (
                        SQLBinaryOp(
                            operator="AND",
                            left=SQLUnaryOp(operator="IS NULL", operand=left, prefix=False),
                            right=SQLUnaryOp(operator="IS NULL", operand=right, prefix=False),
                        ),
                        SQLLiteral(value=True),
                    ),
                    (
                        SQLBinaryOp(
                            operator="OR",
                            left=SQLUnaryOp(operator="IS NULL", operand=left, prefix=False),
                            right=SQLUnaryOp(operator="IS NULL", operand=right, prefix=False),
                        ),
                        SQLLiteral(value=False),
                    ),
                ],
                else_clause=SQLFunctionCall(
                    name="COALESCE",
                    args=[cmp_result, SQLLiteral(value=False)],
                ),
            )
            if is_negated:
                return SQLUnaryOp(operator="NOT", operand=equiv_qty)
            return equiv_qty

        # CQL §Equivalent (Date, DateTime, Time): "the comparison is performed
        # in the same way as it is for equality, except that if one input has
        # a value for a given precision and the other does not, the comparison
        # stops and the result is false, rather than null."
        #
        # Route Date/DateTime/Time equivalence through the same precision-aware
        # `cqlDateTimeEqual` UDF that `=` uses, then convert any NULL (uncertain)
        # result to False (per spec: equivalence "always returns true or false").
        # This fixes the previous fall-through that used raw VARCHAR equality,
        # which did not perform same-instant timezone normalization for
        # DateTimes with different offsets (e.g.,
        # @2024-01-01T10:00:00+00:00 ~ @2024-01-01T12:00:00+02:00 must be True).
        if (
            (self._is_temporal_cql_expr(expr.left) or self._is_temporal_cql_expr(expr.right))
            and not (
                self._is_timeofday_cql_expr(expr.left)
                or self._is_timeofday_cql_expr(expr.right)
            )
        ):
            cmp_result = SQLFunctionCall(
                name="cqlDateTimeEqual",
                args=[
                    SQLCast(expression=left, target_type="VARCHAR"),
                    SQLCast(expression=right, target_type="VARCHAR"),
                ],
            )
            # Equivalence is null-safe: NULL (uncertain) -> False, never NULL.
            equiv_temporal = SQLCase(
                when_clauses=[
                    (
                        SQLUnaryOp(operator="IS NULL", operand=cmp_result, prefix=False),
                        SQLLiteral(value=False),
                    ),
                ],
                else_clause=cmp_result,
            )
            if is_negated:
                return SQLUnaryOp(operator="NOT", operand=equiv_temporal)
            return equiv_temporal

        equiv_case = SQLCase(
            when_clauses=[
                (
                    SQLBinaryOp(
                        operator="AND",
                        left=SQLUnaryOp(operator="IS NULL", operand=left, prefix=False),
                        right=SQLUnaryOp(operator="IS NULL", operand=right, prefix=False),
                    ),
                    SQLLiteral(value=True),
                ),
                (
                    SQLBinaryOp(
                        operator="OR",
                        left=SQLUnaryOp(operator="IS NULL", operand=left, prefix=False),
                        right=SQLUnaryOp(operator="IS NULL", operand=right, prefix=False),
                    ),
                    SQLLiteral(value=False),
                ),
            ],
            else_clause=SQLBinaryOp(operator="=", left=left, right=right),
        )

        if is_negated:
            return SQLUnaryOp(operator="NOT", operand=equiv_case)
        return equiv_case

    def _try_codeable_concept_string_equiv(self, expr, left, right) -> "Optional[SQLExpression]":
        """Handle CodeableConcept/Coding ~ string-literal by checking code values.

        Returns an SQLExpression if one operand is a CodeableConcept or Coding
        property and the other is a bare string literal; None otherwise (fall
        through to generic equivalence).
        """
        from ...parser.ast_nodes import Literal, Property, Identifier
        from ...translator.types import SQLFunctionCall, SQLLiteral, SQLQualifiedIdentifier

        # Identify which side is the property and which is the string literal
        prop_ast, str_val, resource_sql = None, None, None
        if isinstance(expr.right, Literal) and getattr(expr.right, 'type', None) == 'String':
            prop_ast = expr.left
            str_val = expr.right.value
            resource_sql = left
        elif isinstance(expr.left, Literal) and getattr(expr.left, 'type', None) == 'String':
            prop_ast = expr.right
            str_val = expr.left.value
            resource_sql = right
        if prop_ast is None or str_val is None:
            return None

        # Resolve the property path and resource type
        if not isinstance(prop_ast, Property):
            return None
        parts = []
        current = prop_ast
        while isinstance(current, Property):
            parts.append(current.path)
            current = current.source
        parts.reverse()
        base_path = ".".join(parts)

        # Determine resource type from alias
        source_ast = prop_ast
        while isinstance(source_ast, Property) and source_ast.source:
            source_ast = source_ast.source
        res_type = None
        if isinstance(source_ast, Identifier):
            res_type = self.context._alias_resource_types.get(source_ast.name)
        if not res_type:
            res_type = self.context.resource_type

        if not res_type or not self.context.fhir_schema:
            return None

        el_type = self.context.fhir_schema.get_element_type(res_type, base_path.split(".")[0])
        safe_val = str_val.replace("'", "\\'")
        if el_type == "CodeableConcept":
            fhirpath_expr = f"{base_path}.coding.code = '{safe_val}'"
        elif el_type == "Coding":
            fhirpath_expr = f"{base_path}.code = '{safe_val}'"
        else:
            return None

        # Extract the resource reference from the translated expression
        if (isinstance(resource_sql, SQLFunctionCall)
                and resource_sql.name in ("fhirpath_text", "fhirpath_date", "fhirpath_bool")):
            resource_ref = resource_sql.args[0]
        elif isinstance(resource_sql, SQLQualifiedIdentifier) and len(resource_sql.parts) >= 2:
            resource_ref = SQLQualifiedIdentifier(parts=resource_sql.parts[:-1] + ["resource"])
        else:
            resource_ref = resource_sql

        return SQLFunctionCall(
            name="fhirpath_bool",
            args=[resource_ref, SQLLiteral(value=fhirpath_expr)],
        )

    @staticmethod
    def _build_scaled_quantity(qty_expr: "SQLExpression", scalar: "SQLExpression", operator: str) -> "SQLExpression":
        """Build a quantity JSON from quantity_value * scalar, preserving the unit."""
        val = SQLFunctionCall(name="quantity_value", args=[qty_expr])
        unit = SQLFunctionCall(name="quantity_unit", args=[qty_expr])
        new_val = SQLBinaryOp(operator=operator, left=val, right=scalar)
        json_obj = SQLFunctionCall(
            name="json_object",
            args=[
                SQLLiteral(value="value"), new_val,
                SQLLiteral(value="unit"), unit,
                SQLLiteral(value="system"), SQLLiteral(value="http://unitsofmeasure.org"),
            ],
        )
        parsed = SQLFunctionCall(name="parse_quantity", args=[
            SQLCast(expression=json_obj, target_type="VARCHAR"),
        ])
        null_conditions = [
            SQLBinaryOp(operator="IS", left=val, right=SQLNull()),
            SQLBinaryOp(operator="IS", left=scalar, right=SQLNull()),
        ]
        if operator == "/":
            null_conditions.append(SQLBinaryOp(operator="=", left=scalar, right=SQLLiteral(value=0)))
        condition = null_conditions[0]
        for extra in null_conditions[1:]:
            condition = SQLBinaryOp(operator="OR", left=condition, right=extra)
        return SQLCase(when_clauses=[(condition, SQLNull())], else_clause=parsed)

    @staticmethod
    def _quantity_numeric_projection(expr: "SQLExpression") -> "SQLExpression":
        """Extract a numeric value from either Quantity JSON text or a scalar number."""
        text_expr = SQLCast(expression=expr, target_type="VARCHAR")
        json_value = SQLFunctionCall(
            name="json_extract_string",
            args=[text_expr, SQLLiteral(value="$.value")],
        )
        value_text = SQLCase(
            when_clauses=[
                (
                    SQLFunctionCall(
                        name="starts_with",
                        args=[
                            SQLFunctionCall(name="LTRIM", args=[text_expr]),
                            SQLLiteral(value="{"),
                        ],
                    ),
                    json_value,
                )
            ],
            else_clause=text_expr,
        )
        return SQLCast(expression=value_text, target_type="DOUBLE", try_cast=True)

    @staticmethod
    def _quantity_json_object_check(expr: "SQLExpression") -> "SQLExpression":
        """Return true when an expression serializes as a JSON object Quantity."""
        text_expr = SQLCast(expression=expr, target_type="VARCHAR")
        return SQLFunctionCall(
            name="starts_with",
            args=[
                SQLFunctionCall(name="LTRIM", args=[text_expr]),
                SQLLiteral(value="{"),
            ],
        )

    @staticmethod
    def _fhirpath_number_projection(expr: "SQLExpression") -> "Optional[SQLExpression]":
        """Use the typed FHIRPath numeric wrapper for dynamic FHIR values.

        Casting fhirpath_text() to DOUBLE treats string-valued FHIR choices such
        as valueString="5" as numeric evidence. fhirpath_number() preserves the
        runtime FHIR type boundary and returns NULL for non-numeric choices.
        Keep this limited to FHIR value[x] paths; internal CQL tuple JSON is
        also read with fhirpath_text(), but its serialized strings may still
        represent statically numeric CQL properties.
        """
        if isinstance(expr, SQLFunctionCall) and expr.name in ("fhirpath_text", "fhirpath_scalar"):
            if len(expr.args) >= 2:
                path_arg = expr.args[1]
                if not (
                    isinstance(path_arg, SQLLiteral)
                    and isinstance(path_arg.value, str)
                    and (
                        path_arg.value == "value"
                        or path_arg.value.startswith("value.")
                    )
                ):
                    return None
                return SQLFunctionCall(name="fhirpath_number", args=expr.args[:2])
        return None

    def _dynamic_quantity_literal_comparison(
        self,
        dynamic_expr: "SQLExpression",
        quantity_expr: "SQLExpression",
        numeric_quantity: "SQLExpression",
        operator: str,
        sql_cmp_op: str,
        dynamic_on_left: bool,
    ) -> "Optional[SQLExpression]":
        """Compare a dynamic FHIR value against a static Quantity literal.

        Choice-valued FHIR paths can yield either primitive text/numbers or a
        Quantity JSON object. For JSON objects, CQL comparison must be
        unit-aware. For primitive numeric choices, keep the previous numeric
        fallback but obtain the number through fhirpath_number() so valueString
        is not silently accepted as a number.
        """
        number_projection = self._fhirpath_number_projection(dynamic_expr)
        if number_projection is None:
            return None

        quantity_result = SQLFunctionCall(
            name="quantity_compare",
            args=[
                SQLFunctionCall(
                    name="parse_quantity",
                    args=[SQLCast(expression=dynamic_expr, target_type="VARCHAR")],
                ),
                _ensure_parse_quantity(quantity_expr),
                SQLLiteral(sql_cmp_op),
            ],
        )
        numeric_result = (
            SQLBinaryOp(operator=operator, left=number_projection, right=numeric_quantity)
            if dynamic_on_left
            else SQLBinaryOp(operator=operator, left=numeric_quantity, right=number_projection)
        )
        return SQLCase(
            when_clauses=[
                (self._quantity_json_object_check(dynamic_expr), quantity_result)
            ],
            else_clause=numeric_result,
        )

    def _translate_tail_operators(self, operator, left, right, expr, extra_temporal_cond_ast) -> SQLExpression:
        """Handle remaining operators: starts/ends temporal, within, quantity, standard fallback."""
        # Simple starts/ends temporal operators: "starts on or before", "starts on or after", etc.
        # Also handles precision variants like "starts on or before day of".
        # These compare interval boundaries with optional precision truncation.
        _simple_starts_ends = self._translate_simple_starts_ends_temporal(operator, left, right)
        if _simple_starts_ends is not None:
            return _simple_starts_ends

        # "starts within N unit of" / "ends within N unit of" operators
        # Extract the interval boundary, then delegate to within operator
        for _prefix, _boundary_fn in (("starts within ", "intervalStart"), ("ends within ", "intervalEnd")):
            if operator.startswith(_prefix):
                _rest = operator[len(_prefix):]
                within_components = self._parse_within_operator(f"within {_rest}")
                if within_components is not None:
                    boundary_expr = SQLFunctionCall(name=_boundary_fn, args=[left])
                    return self._translate_within_operator(within_components, boundary_expr, right)

        # Complex temporal operators with quantity: "starts 1 day or less on or after day of", etc.
        # Pattern: <starts|ends> <quantity> <or less|or more> <on or before|on or after> [<precision> of]
        # The "same ... or after/before" timing-phrase forms are handled by the
        # dedicated same-family delegation below (CQL 1.5 §9.18/§9.19: "same"
        # is a synonym for "on" in timing phrases) and must not fall into the
        # quantity-offset interpretation.
        if operator.startswith("starts ") and not operator.startswith("starts same ") and " or " in operator:
            return self._translate_complex_interval_temporal(operator, left, right, "start")
        if operator.startswith("ends ") and not operator.startswith("ends same ") and " or " in operator:
            return self._translate_complex_interval_temporal(operator, left, right, "end")

        # Exact temporal offset: "starts/ends <N> <unit> <before|after> [<precision> of]"
        # No "or less/more" — exact offset with optional precision truncation.
        # e.g. "ends 1 day after day of" → CAST(intervalEnd(X) AS DATE) = CAST(Y AS DATE) + INTERVAL '1 day'
        for _boundary_prefix, _boundary_fn in (("starts ", "intervalStart"), ("ends ", "intervalEnd")):
            if operator.startswith(_boundary_prefix) and " or " not in operator:
                _rest = operator[len(_boundary_prefix):]
                _parts = _rest.split()
                # Need at least: <N> <unit> <before|after>
                if len(_parts) >= 3:
                    try:
                        _qty_val = float(_parts[0])
                        _qty_unit = _parts[1]
                        # Find direction
                        _remaining = " ".join(_parts[2:])
                        _direction = None
                        for _d in ("before", "after"):
                            if _remaining.startswith(_d):
                                _direction = _d
                                _remaining = _remaining[len(_d):].strip()
                                break
                        if _direction is not None:
                            # Optional precision: "<precision> of" at end
                            _precision = None
                            if _remaining.endswith(" of"):
                                _precision = _remaining[:-3].strip()
                            elif _remaining:
                                _precision = _remaining.strip() or None

                            # Build: boundary(left) = right ± INTERVAL, truncated to precision
                            boundary_expr = SQLFunctionCall(name=_boundary_fn, args=[left])
                            interval_lit = SQLIntervalLiteral(value=int(_qty_val), unit=_qty_unit)
                            # Cast right to TIMESTAMP for INTERVAL arithmetic
                            right_ts = SQLCast(expression=right, target_type="TIMESTAMP")
                            if _direction == "after":
                                offset_right = self._timestamp_arith_for_compare(
                                    SQLBinaryOp(operator="+", left=right_ts, right=interval_lit))
                            else:
                                offset_right = self._timestamp_arith_for_compare(
                                    SQLBinaryOp(operator="-", left=right_ts, right=interval_lit))
                            # Apply precision truncation via VARCHAR LEFT()
                            if _precision:
                                boundary_expr = self._truncate_to_precision(boundary_expr, _precision)
                                offset_right = self._truncate_to_precision(offset_right, _precision)
                            else:
                                # No explicit precision — normalize both sides
                                # to 23-char ISO 8601 for consistent comparison.
                                boundary_expr = self._normalize_temporal_for_compare(boundary_expr)
                                offset_right = self._normalize_temporal_for_compare(offset_right)
                            return SQLBinaryOp(operator="=", left=boundary_expr, right=offset_right)
                    except ValueError:
                        pass  # Not a numeric token, fall through

        # Compound "starts same X as" / "ends same X as" temporal operators
        # e.g. "starts same day as", "ends same day as"
        if operator.startswith("starts same "):
            # Extract intervalStart(left), then delegate to same_operator
            interval_start = SQLFunctionCall(name="intervalStart", args=[left])
            same_part = operator[len("starts "):]  # "same day as"
            return self._translate_same_operator(same_part, interval_start, right)
        if operator.startswith("ends same "):
            # Extract intervalEnd(left), then delegate to same_operator
            interval_end = SQLFunctionCall(name="intervalEnd", args=[left])
            same_part = operator[len("ends "):]  # "same day as"
            return self._translate_same_operator(same_part, interval_end, right)

        # Bare point-level temporal quantifiers (no starts/ends prefix):
        # Pattern: <N> <unit> <or less|or more> <before|after|on or before|on or after> [<precision> of]
        # e.g. "42 weeks or less before", "241 minutes or more before", "3 days or less after day of"
        bare_temporal = self._parse_bare_temporal_operator(operator)
        if bare_temporal is not None:
            return self._translate_bare_temporal_operator(bare_temporal, left, right)

        # "within N unit of" operator: |left - right| <= N unit
        # e.g. "within 60 days of", "within 3 months of"
        within_temporal = self._parse_within_operator(operator)
        if within_temporal is not None:
            return self._translate_within_operator(within_temporal, left, right)

        # CQL §22.21: Arithmetic on DurationBetween results (which may be
        # uncertainty intervals as VARCHAR). Use uncertainty-aware UDFs.
        if operator in ("+", "-", "*"):
            left_is_duration = self._is_duration_between_expr(expr.left)
            right_is_duration = self._is_duration_between_expr(expr.right)
            if left_is_duration or right_is_duration:
                udf_map = {"+": "cqlUncertainAdd", "-": "cqlUncertainSubtract", "*": "cqlUncertainMultiply"}
                return SQLFunctionCall(
                    name=udf_map[operator],
                    args=[
                        SQLCast(expression=left, target_type="VARCHAR"),
                        SQLCast(expression=right, target_type="VARCHAR"),
                    ],
                )

        # Division with DurationBetween: cast VARCHAR to INTEGER
        # CQL §5.6.4: DurationBetween may return VARCHAR (uncertainty interval JSON
        # or integer string). Division requires numeric operands.
        if operator == "/":
            left_is_duration = self._is_duration_between_expr(expr.left)
            right_is_duration = self._is_duration_between_expr(expr.right)
            # SQL-level fallback: detect cqlDurationBetween in translated SQL
            # (handles ExpressionRef indirection the CQL AST check misses)
            if not left_is_duration and _is_uncertain_between_sql(left):
                left_is_duration = True
            if not right_is_duration and _is_uncertain_between_sql(right):
                right_is_duration = True
            if left_is_duration:
                left = SQLCast(expression=left, target_type="INTEGER", try_cast=True)
            if right_is_duration:
                right = SQLCast(expression=right, target_type="INTEGER", try_cast=True)

        # Date/DateTime arithmetic with Quantity, or Quantity ± Quantity
        # Pattern: date + quantity, date - quantity, quantity - quantity
        if operator in ("+", "-"):
            # CQL-17 EXPLORER QA-001: interval-derived scalars (start of /
            # end of / point from / width of / Size) over NUMERIC or
            # QUANTITY point intervals must use numeric/quantity arithmetic.
            # CQL §19.19 Start (and siblings) return the interval's point
            # type, so `(start of Interval[1, 5]) + 1` is Integer addition
            # (§9 Add), not a temporal quantity add. Without this gate the
            # Integer-literal case fell into the Date +/- Integer year-unit
            # path (returning NULL for numeric points) and decimal/width
            # cases fell through to raw SQL '+'(VARCHAR, x) binder errors.
            scalar_kind = (
                self._interval_scalar_point_kind(expr.left)
                or self._interval_scalar_point_kind(expr.right)
            )
            if scalar_kind == "numeric":
                return SQLBinaryOp(
                    operator=operator,
                    left=SQLCast(expression=left, target_type="DECIMAL(38,10)"),
                    right=SQLCast(expression=right, target_type="DECIMAL(38,10)"),
                )
            if scalar_kind == "quantity":
                left_is_q = self._interval_scalar_point_kind(expr.left) == "quantity" or _is_quantity_expression(left) or self._is_cql_quantity_expr(expr.left)
                right_is_q = self._interval_scalar_point_kind(expr.right) == "quantity" or _is_quantity_expression(right) or self._is_cql_quantity_expr(expr.right)
                left_q = _quantity_operand_for_arithmetic(left, left_is_q)
                right_q = _quantity_operand_for_arithmetic(right, right_is_q)
                if operator == "+":
                    return SQLFunctionCall(name="quantity_add", args=[left_q, right_q])
                return SQLFunctionCall(name="quantity_subtract", args=[left_q, right_q])

            # Check if either side is a quantity (parse_quantity function call or CQL AST)
            left_is_quantity = _is_quantity_expression(left) or self._is_cql_quantity_expr(expr.left)
            right_is_quantity = _is_quantity_expression(right) or self._is_cql_quantity_expr(expr.right)

            if left_is_quantity and right_is_quantity:
                # Quantity ± Quantity — use unit-aware arithmetic UDFs
                left_q = _ensure_parse_quantity(left)
                right_q = _ensure_parse_quantity(right)
                if operator == "+":
                    return SQLFunctionCall(name="quantity_add", args=[left_q, right_q])
                else:
                    return SQLFunctionCall(name="quantity_subtract", args=[left_q, right_q])

            if right_is_quantity:
                if self._is_definitely_non_temporal_quantity_peer(expr.left, left):
                    return SQLNull()
                # date + quantity or date - quantity
                # dateAddQuantity UDF expects VARCHAR inputs, returns VARCHAR
                date_arg = SQLCast(expression=left, target_type="VARCHAR") if not isinstance(left, SQLLiteral) else left
                right_q_json = right.args[0] if isinstance(right, SQLFunctionCall) and right.name == "parse_quantity" else right
                if operator == "+":
                    return SQLFunctionCall(name="dateAddQuantity", args=[date_arg, right_q_json])
                else:  # operator == "-"
                    return SQLFunctionCall(name="dateSubtractQuantity", args=[date_arg, right_q_json])
            elif left_is_quantity:
                if operator != "+" or self._is_definitely_non_temporal_quantity_peer(expr.right, right):
                    return SQLNull()
                # quantity + date (swap order)
                date_arg = SQLCast(expression=right, target_type="VARCHAR") if not isinstance(right, SQLLiteral) else right
                left_q_json = left.args[0] if isinstance(left, SQLFunctionCall) and left.name == "parse_quantity" else left
                return SQLFunctionCall(name="dateAddQuantity", args=[date_arg, left_q_json])

            # CQL Date/DateTime +/- Integer: per CQL spec, integer arithmetic on
            # Date values uses years as the unit.  DuckDB DATE - INTEGER subtracts
            # days, so we must explicitly convert to INTERVAL year.
            if not left_is_quantity and not right_is_quantity:
                if (isinstance(expr.right, Literal) and getattr(expr.right, 'type', None) == 'Integer'
                        and self._is_cql_date_expression(expr.left)):
                    date_arg = SQLCast(expression=left, target_type="VARCHAR") if not isinstance(left, SQLLiteral) else left
                    quantity_arg = SQLLiteral(value=json.dumps({
                        "value": int(expr.right.value),
                        "unit": "year",
                        "system": "http://unitsofmeasure.org",
                    }))
                    return SQLFunctionCall(
                        name="dateAddQuantity" if operator == "+" else "dateSubtractQuantity",
                        args=[date_arg, quantity_arg],
                    )

        # Quantity * scalar and Quantity / scalar arithmetic, or Quantity * Quantity / Quantity / Quantity.
        if operator in ("*", "/"):
            # CQL-17 EXPLORER QA-001 (multiplication/division variant):
            # numeric interval-derived scalars must scale numerically.
            scalar_kind = (
                self._interval_scalar_point_kind(expr.left)
                or self._interval_scalar_point_kind(expr.right)
            )
            if scalar_kind == "numeric":
                return SQLBinaryOp(
                    operator=operator,
                    left=SQLCast(expression=left, target_type="DECIMAL(38,10)"),
                    right=SQLCast(expression=right, target_type="DECIMAL(38,10)"),
                )
            if scalar_kind == "quantity":
                left_is_q = self._interval_scalar_point_kind(expr.left) == "quantity" or _is_quantity_expression(left) or self._is_cql_quantity_expr(expr.left)
                right_is_q = self._interval_scalar_point_kind(expr.right) == "quantity" or _is_quantity_expression(right) or self._is_cql_quantity_expr(expr.right)
                left_q = _quantity_operand_for_arithmetic(left, left_is_q)
                right_q = _quantity_operand_for_arithmetic(right, right_is_q)
                return SQLFunctionCall(
                    name="quantityMultiply" if operator == "*" else "quantityDivide",
                    args=[left_q, right_q],
                )
            left_is_quantity = _is_quantity_expression(left) or self._is_cql_quantity_expr(expr.left)
            right_is_quantity = _is_quantity_expression(right) or self._is_cql_quantity_expr(expr.right)

            def _quantity_scalar_operand(scalar_expr: SQLExpression) -> SQLExpression:
                number_projection = self._fhirpath_number_projection(scalar_expr)
                if number_projection is not None:
                    return number_projection
                if isinstance(scalar_expr, SQLLiteral):
                    if isinstance(scalar_expr.value, (int, float)) and not isinstance(scalar_expr.value, bool):
                        return scalar_expr
                    return SQLNull()
                return SQLCast(expression=scalar_expr, target_type="DOUBLE", try_cast=True)

            if left_is_quantity and right_is_quantity:
                # Quantity * Quantity or Quantity / Quantity — use UDFs
                left_q = _ensure_parse_quantity(left)
                right_q = _ensure_parse_quantity(right)
                if operator == "*":
                    return SQLFunctionCall(name="quantityMultiply", args=[left_q, right_q])
                else:
                    return SQLFunctionCall(name="quantityDivide", args=[left_q, right_q])
            if left_is_quantity and not right_is_quantity:
                scalar = _quantity_scalar_operand(right)
                return self._build_scaled_quantity(left, scalar, operator)
            if right_is_quantity and not left_is_quantity:
                if operator == "*":
                    scalar = _quantity_scalar_operand(left)
                    return self._build_scaled_quantity(right, scalar, "*")

        # CQL §12.3: For Date, DateTime, and Time values, comparison operators
        # use precision-aware semantics (compare at min precision, NULL if uncertain).
        # Route <, <=, >, >=, = through precision-aware UDFs when operands are temporal.
        if operator in ("<", "<=", ">", ">=", "=", "!=", "<>"):
            if (
                operator in ("<", "<=", ">", ">=")
                and (
                    self._is_unsupported_ordered_comparison_operand(expr.left, left)
                    or self._is_unsupported_ordered_comparison_operand(expr.right, right)
                    or self._is_list_operands(left, right, expr)
                )
            ):
                return SQLNull()

            if (
                self._is_uncertain_between_expr(expr.left)
                or self._is_uncertain_between_expr(expr.right)
                or _is_uncertain_between_sql(left)
                or _is_uncertain_between_sql(right)
            ):
                cmp_op = "!=" if operator == "<>" else operator
                return SQLFunctionCall(
                    name="cqlUncertainCompare",
                    args=[
                        SQLCast(expression=left, target_type="VARCHAR"),
                        SQLCast(expression=right, target_type="VARCHAR"),
                        SQLLiteral(value=cmp_op),
                    ],
                )

            if (
                (self._is_temporal_cql_expr(expr.left) or self._is_temporal_cql_expr(expr.right))
                and not (
                    self._is_timeofday_cql_expr(expr.left)
                    or self._is_timeofday_cql_expr(expr.right)
                )
            ):
                _udf_map = {
                    "<": "cqlBefore",
                    ">": "cqlAfter",
                    "<=": "cqlSameOrBefore",
                    ">=": "cqlSameOrAfter",
                    "=": "cqlDateTimeEqual",
                    "!=": "cqlDateTimeEqual",  # negate below
                    "<>": "cqlDateTimeEqual",  # negate below
                }
                udf_name = _udf_map.get(operator)
                if udf_name:
                    result = SQLFunctionCall(
                        name=udf_name,
                        args=[
                            SQLCast(expression=left, target_type="VARCHAR"),
                            SQLCast(expression=right, target_type="VARCHAR"),
                        ],
                    )
                    if operator in ("!=", "<>"):
                        # NOT cqlDateTimeEqual(...) — but preserve null propagation
                        result = SQLCase(
                            when_clauses=[
                                (SQLUnaryOp(operator="IS NULL", operand=result, prefix=False),
                                 SQLNull()),
                                (result,
                                 SQLLiteral(value=False)),
                            ],
                            else_clause=SQLLiteral(value=True),
                        )
                    return result

        # CQL §9 Equal/Greater/Less/<et al>: =<T>(left T, right T) and
        # >T(left T, right T) require compatible operand types. When both
        # operands are statically-known primitive literals of incompatible
        # types (e.g. 'foo' > 5, 'foo' = 5, true > 'foo'), the comparison
        # has no defined value — emit NULL (matching how the spec's three-
        # valued logic treats undefined equality/ordering) instead of
        # letting DuckDB raise a runtime ConversionException. Mirrors
        # _static_equivalence_incompatible. The ordered-comparison
        # extension (>, <, >=, <=) was added by CQL-09 EXPLORER QA-001
        # after SKEPTIC's initial =/!=/<> guard proved incomplete.
        if operator in ("=", "!=", "<>", "<", "<=", ">", ">=") and self._static_equivalence_incompatible(
            expr.left, expr.right
        ):
            return self._maybe_wrap_audit_comparison(SQLNull(), operator, left, right)

        # CQL §12.1: Ratio equality compares numerator and denominator using
        # Quantity equality. Keep this before quantity fallback because Ratio
        # JSON is not itself a Quantity JSON object.
        if operator in ("=", "!=", "<>"):
            left_is_ratio = _is_ratio_expression(left) or self._is_cql_ratio_expr(expr.left)
            right_is_ratio = _is_ratio_expression(right) or self._is_cql_ratio_expr(expr.right)
            if left_is_ratio or right_is_ratio:
                cmp_op = "!=" if operator in ("!=", "<>") else "=="
                result = SQLFunctionCall(
                    name="ratioCompare",
                    args=[
                        SQLCast(expression=left, target_type="VARCHAR"),
                        SQLCast(expression=right, target_type="VARCHAR"),
                        SQLLiteral(value=cmp_op),
                    ],
                )
                return self._maybe_wrap_audit_comparison(result, operator, left, right)

        # Quantity comparison: use unit-aware quantity_compare when either
        # side is a Quantity expression (parse_quantity call or CASE with
        # parse_quantity branches), or when the CQL AST indicates a Quantity
        # type (e.g., Quantity literal, as Quantity cast, or reference to a
        # definition known to return Quantity).
        if operator in ("<", "<=", ">", ">=", "=", "!=", "<>"):
            left_sql_quantity = _is_quantity_expression(left)
            right_sql_quantity = _is_quantity_expression(right)
            left_is_quantity = left_sql_quantity or self._is_cql_quantity_expr(expr.left)
            right_is_quantity = right_sql_quantity or self._is_cql_quantity_expr(expr.right)
            if left_is_quantity or right_is_quantity:
                cql_to_sql_op = {"=": "==", "!=": "!=", "<>": "!="}
                sql_cmp_op = cql_to_sql_op.get(operator, operator)
                sql_op = BINARY_OPERATOR_MAP.get(operator, operator)
                if left_is_quantity and right_is_quantity:
                    left_q = (
                        _ensure_parse_quantity(left)
                        if left_sql_quantity
                        else SQLFunctionCall(name="parse_quantity", args=[SQLCast(expression=left, target_type="VARCHAR")])
                    )
                    right_q = (
                        _ensure_parse_quantity(right)
                        if right_sql_quantity
                        else SQLFunctionCall(name="parse_quantity", args=[SQLCast(expression=right, target_type="VARCHAR")])
                    )
                    quantity_result = SQLFunctionCall(
                        name="quantity_compare",
                        args=[left_q, right_q, SQLLiteral(sql_cmp_op)],
                    )
                    fallback = None
                    right_qty_val = self._extract_quantity_numeric_value(right) if isinstance(right, SQLFunctionCall) and right.name == "parse_quantity" else None
                    left_qty_val = self._extract_quantity_numeric_value(left) if isinstance(left, SQLFunctionCall) and left.name == "parse_quantity" else None
                    dynamic_side = None
                    if right_qty_val is not None and left_qty_val is None:
                        dynamic_side = left
                        fallback = SQLBinaryOp(
                            operator=sql_op,
                            left=self._quantity_numeric_projection(left),
                            right=right_qty_val,
                        )
                    elif left_qty_val is not None and right_qty_val is None:
                        dynamic_side = right
                        fallback = SQLBinaryOp(
                            operator=sql_op,
                            left=left_qty_val,
                            right=self._quantity_numeric_projection(right),
                        )
                    result = quantity_result
                    if fallback is not None and dynamic_side is not None:
                        result = SQLCase(
                            when_clauses=[
                                (self._quantity_json_object_check(dynamic_side), quantity_result)
                            ],
                            else_clause=SQLFunctionCall(name="COALESCE", args=[quantity_result, fallback]),
                        )
                    return self._maybe_wrap_audit_comparison(result, operator, left, right)
                elif right_is_quantity and not left_is_quantity:
                    # Right is Quantity. If it's a literal, extract numeric value.
                    qty_val = self._extract_quantity_numeric_value(right) if isinstance(right, SQLFunctionCall) and right.name == "parse_quantity" else None
                    if qty_val is not None and isinstance(left, SQLLiteral) and isinstance(left.value, (int, float)) and not isinstance(left.value, bool):
                        # CQL 1.5 Table 9-E: Integer/Long/Decimal implicitly
                        # convert to Quantity with default unit '1'. A bare
                        # numeric literal vs a STATIC Quantity literal must
                        # compare unit-aware (incompatible units → NULL per
                        # §9.5 Equal), never by raw value with the unit
                        # dropped. Dynamic FHIR-sourced quantities keep the
                        # FHIRHelpers/fixture-pinned numeric path below
                        # (FHIRHelpers unit: Coalesce(code, unit, '1') admits
                        # non-UCUM display strings; official eCQM fixtures
                        # pin numeric comparison there, e.g. CMS72 INR > 3.5
                        # with a unit display of "0").
                        return self._maybe_wrap_audit_comparison(
                            SQLFunctionCall(
                                name="quantity_compare",
                                args=[
                                    _quantity_operand_for_arithmetic(left, is_quantity=False),
                                    _ensure_parse_quantity(right),
                                    SQLLiteral(sql_cmp_op),
                                ],
                            ),
                            operator, left, right,
                        )
                    if qty_val is not None:
                        dynamic_quantity_cmp = self._dynamic_quantity_literal_comparison(
                            left, right, qty_val, sql_op, sql_cmp_op, dynamic_on_left=True
                        )
                        if dynamic_quantity_cmp is not None:
                            return self._maybe_wrap_audit_comparison(dynamic_quantity_cmp, operator, left, right)
                        right = qty_val
                    elif isinstance(left, SQLLiteral) and isinstance(left.value, (int, float)):
                        # Left is a numeric literal — extract Quantity's numeric value
                        right = SQLFunctionCall(name="quantity_value", args=[_ensure_parse_quantity(right)])
                    else:
                        # Non-literal Quantity — wrap other side in parse_quantity
                        result = SQLFunctionCall(
                            name="quantity_compare",
                            args=[SQLFunctionCall(name="parse_quantity", args=[SQLCast(expression=left, target_type="VARCHAR")]),
                                  _ensure_parse_quantity(right), SQLLiteral(sql_cmp_op)],
                        )
                        return self._maybe_wrap_audit_comparison(result, operator, left, right)
                elif left_is_quantity and not right_is_quantity:
                    qty_val = self._extract_quantity_numeric_value(left) if isinstance(left, SQLFunctionCall) and left.name == "parse_quantity" else None
                    if qty_val is not None and isinstance(right, SQLLiteral) and isinstance(right.value, (int, float)) and not isinstance(right.value, bool):
                        # Mirror of the right-quantity branch above: promote the
                        # bare numeric literal to a unit-'1' quantity (CQL 1.5
                        # Table 9-E implicit conversion) and compare unit-aware,
                        # static literals only (see comment above).
                        return self._maybe_wrap_audit_comparison(
                            SQLFunctionCall(
                                name="quantity_compare",
                                args=[
                                    _ensure_parse_quantity(left),
                                    _quantity_operand_for_arithmetic(right, is_quantity=False),
                                    SQLLiteral(sql_cmp_op),
                                ],
                            ),
                            operator, left, right,
                        )
                    if qty_val is not None:
                        dynamic_quantity_cmp = self._dynamic_quantity_literal_comparison(
                            right, left, qty_val, sql_op, sql_cmp_op, dynamic_on_left=False
                        )
                        if dynamic_quantity_cmp is not None:
                            return self._maybe_wrap_audit_comparison(dynamic_quantity_cmp, operator, left, right)
                        left = qty_val
                    elif isinstance(right, SQLLiteral) and isinstance(right.value, (int, float)):
                        # Right is a numeric literal — extract Quantity's numeric value
                        left = SQLFunctionCall(name="quantity_value", args=[_ensure_parse_quantity(left)])
                    else:
                        result = SQLFunctionCall(
                            name="quantity_compare",
                            args=[_ensure_parse_quantity(left),
                                  SQLFunctionCall(name="parse_quantity", args=[SQLCast(expression=right, target_type="VARCHAR")]), SQLLiteral(sql_cmp_op)],
                        )
                        return self._maybe_wrap_audit_comparison(result, operator, left, right)
            elif self._might_be_quantity_comparison(expr):
                # Neither side was detected as Quantity, but the CQL AST
                # pattern suggests the comparison might involve Quantity
                # values (e.g., .value property or opaque function call).
                # Use a safe COALESCE: try quantity_compare first (which
                # handles JSON format differences), fall back to regular
                # comparison for non-Quantity values.
                # Cast to VARCHAR first since parse_quantity expects VARCHAR
                # and the expression might be DOUBLE or other numeric types.
                cql_to_sql_op = {"=": "==", "!=": "!=", "<>": "!="}
                sql_cmp_op = cql_to_sql_op.get(operator, operator)
                sql_op = BINARY_OPERATOR_MAP.get(operator, operator)
                left_pq = SQLFunctionCall(
                    name="parse_quantity",
                    args=[SQLCast(expression=left, target_type="VARCHAR")],
                )
                right_pq = SQLFunctionCall(
                    name="parse_quantity",
                    args=[SQLCast(expression=right, target_type="VARCHAR")],
                )
                def _quantity_fallback_operand(operand: SQLExpression) -> SQLExpression:
                    number_projection = self._fhirpath_number_projection(operand)
                    if number_projection is not None:
                        return number_projection
                    if isinstance(operand, (SQLQualifiedIdentifier, SQLSubquery)):
                        return self._quantity_numeric_projection(operand)
                    if (
                        isinstance(operand, SQLFunctionCall)
                        and operand.name in {
                            "fhirpath_text",
                            "fhirpath_scalar",
                            "dateSubtractQuantity",
                            "dateAddQuantity",
                            "quantitySubtract",
                            "quantity_subtract",
                            "quantityAdd",
                            "quantity_add",
                        }
                    ):
                        return self._quantity_numeric_projection(operand)
                    return operand

                result = SQLFunctionCall(
                    name="COALESCE",
                    args=[
                        SQLFunctionCall(
                            name="quantity_compare",
                            args=[left_pq, right_pq, SQLLiteral(sql_cmp_op)],
                        ),
                        SQLBinaryOp(
                            operator=sql_op,
                            left=_quantity_fallback_operand(left),
                            right=_quantity_fallback_operand(right),
                        ),
                    ],
                )
                return self._maybe_wrap_audit_comparison(result, operator, left, right)

        # Type coercion for intervalStart/intervalEnd VARCHAR results compared
        # with typed literals (integer, float).  The interval UDFs return VARCHAR
        # but the point values may be numeric.
        if operator in ("<", "<=", ">", ">=", "=", "!=", "<>"):
            left_is_interval = self._is_fhir_interval_expression(left)
            right_is_interval = self._is_fhir_interval_expression(right)
            if left_is_interval or right_is_interval:
                result: SQLExpression = SQLFunctionCall(name="intervalEquals", args=[left, right])
                if operator in ("!=", "<>"):
                    result = SQLCase(
                        when_clauses=[
                            (SQLUnaryOp(operator="IS NULL", operand=result, prefix=False), SQLNull()),
                            (result, SQLLiteral(value=False)),
                        ],
                        else_clause=SQLLiteral(value=True),
                    )
                return result

            def _is_interval_start_end(e):
                return isinstance(e, SQLFunctionCall) and e.name in ("intervalStart", "intervalEnd")

            if _is_interval_start_end(left) or _is_interval_start_end(right):
                cast_type = self._infer_cast_type_for_comparison(left, right)
                if cast_type != "TIMESTAMP":
                    # Numeric comparison — cast the intervalStart/End result
                    if _is_interval_start_end(left):
                        left = SQLCast(expression=left, target_type=cast_type, try_cast=True)
                    if _is_interval_start_end(right):
                        right = SQLCast(expression=right, target_type=cast_type, try_cast=True)

        # Standard binary operator
        sql_op = BINARY_OPERATOR_MAP.get(operator, operator)

        if operator == "&":
            empty = SQLLiteral(value="")
            return SQLBinaryOp(
                operator="||",
                left=SQLFunctionCall(name="COALESCE", args=[left, empty]),
                right=SQLFunctionCall(name="COALESCE", args=[right, empty]),
            )

        # Safety: handle operators mapped to None that weren't caught above
        if sql_op is None:
            if operator == "implies":
                not_left = SQLUnaryOp(operator="NOT", operand=left)
                return SQLBinaryOp(operator="OR", left=not_left, right=right)
            # Temporal operators mapped to None — fall back to UDF call
            sql_op = operator

        # Handle precedence
        precedence = PRECEDENCE.get(sql_op.upper(), PRECEDENCE["PRIMARY"])

        # CQL '+' on strings is concatenation → DuckDB '||'
        if sql_op == "+":
            def _is_numeric_typed(e):
                if isinstance(e, SQLLiteral) and (
                    isinstance(e.value, (int, float)) or str(type(e.value).__name__) == "Decimal"
                ) and not isinstance(e.value, bool):
                    return True
                if isinstance(e, SQLCast) and e.target_type in ('INTEGER', 'DOUBLE', 'BIGINT', 'FLOAT', 'DECIMAL'):
                    return True
                if isinstance(e, SQLFunctionCall) and e.name == "fhirpath_number":
                    return True
                if isinstance(e, SQLBinaryOp) and e.operator in ('+', '-', '*', '/', '%'):
                    return True
                return False

            def _is_string_typed(e):
                if isinstance(e, SQLLiteral) and isinstance(e.value, str):
                    return True
                if isinstance(e, SQLFunctionCall) and e.name in (
                    'fhirpath_text', 'fhirpath_scalar', 'UPPER', 'LOWER',
                    'REPLACE', 'CONCAT', 'SUBSTRING', 'LTRIM', 'RTRIM', 'TRIM',
                ):
                    return True
                if isinstance(e, SQLCast) and e.target_type in ('VARCHAR', 'TEXT'):
                    return True
                return False
            if (
                (_is_string_typed(left) or _is_string_typed(right))
                and not (_is_numeric_typed(left) or _is_numeric_typed(right))
            ):
                return SQLBinaryOp(operator="||", left=left, right=right)

        # Quantity arithmetic for mod (%) operator: route to quantityModulo UDF
        if sql_op == "%":
            left_is_quantity = _is_quantity_expression(left) or self._is_cql_quantity_expr(expr.left)
            right_is_quantity = _is_quantity_expression(right) or self._is_cql_quantity_expr(expr.right)
            if left_is_quantity or right_is_quantity:
                left_q = _quantity_operand_for_arithmetic(left, left_is_quantity)
                right_q = _quantity_operand_for_arithmetic(right, right_is_quantity)
                return SQLFunctionCall(name="quantityModulo", args=[left_q, right_q])

        # Cast fhirpath_text results to DOUBLE for arithmetic operators
        # alias_narrow_targets is populated when an integral definition-alias
        # subquery operand is widened to DECIMAL(38,0); the final result is
        # narrowed back with TRY_CAST at result assembly (overflow -> NULL).
        alias_narrow_targets: list = []
        if sql_op in ("+", "-", "*", "/", "%"):
            def _cast_if_fhirpath(expr):
                if isinstance(expr, SQLFunctionCall) and expr.name in ('fhirpath_text', 'fhirpath_scalar'):
                    number_projection = self._fhirpath_number_projection(expr)
                    if number_projection is not None:
                        return number_projection
                    # Handle Quantity JSON objects by extracting $.value first.
                    # cql_quantity_value is a SQL macro defined in clinical.py;
                    # using it here keeps the emitted SQL DRY and audit-safe
                    # (the macro is globally resolvable from any scope).
                    return SQLCast(
                        expression=SQLFunctionCall(name="cql_quantity_value", args=[expr]),
                        target_type="DOUBLE",
                        try_cast=True,
                    )
                return expr

            def _is_numeric(expr):
                """Check if expression is known to be numeric."""
                if isinstance(expr, SQLLiteral) and isinstance(expr.value, (int, float)) and not isinstance(expr.value, bool):
                    return True
                if isinstance(expr, SQLCast) and expr.target_type in ('INTEGER', 'DOUBLE', 'BIGINT', 'FLOAT'):
                    return True
                if isinstance(expr, SQLBinaryOp) and expr.operator in ('+', '-', '*', '/', '%'):
                    return True
                return False

            left = _cast_if_fhirpath(left)
            right = _cast_if_fhirpath(right)

            # CQL 1.5 Appendix B Add/Subtract/Multiply: "With mixed Integer
            # and Decimal or Long, the Integer argument will be implicitly
            # converted to Decimal or Long." A Long literal whose value fits
            # in INT32 range lowers to a bare SQL integer, so DuckDB would
            # compute INT32 + INT32 and raise OutOfRangeError (e.g.
            # 1 + 2147483647L) instead of promoting to Long. Cast integral
            # operands to BIGINT whenever any operand is statically Long.
            if sql_op in ("+", "-", "*"):
                left_static_type = _infer_static_numeric_type(expr.left)
                right_static_type = _infer_static_numeric_type(expr.right)
                integral_types = {left_static_type, right_static_type} - {None}
                if integral_types and integral_types <= {"Integer", "Long"} and "Long" in integral_types:
                    if left_static_type in ("Integer", "Long"):
                        left = SQLCast(expression=left, target_type="BIGINT", try_cast=True)
                    if right_static_type in ("Integer", "Long"):
                        right = SQLCast(expression=right, target_type="BIGINT", try_cast=True)

            # When one operand is a numeric literal and the other is an
            # untyped identifier (e.g., a lambda parameter from
            # intervalEnd() which returns VARCHAR), CAST the identifier so
            # DuckDB arithmetic works. CQL 1.5 Appendix B Add: "With mixed
            # Integer and Decimal ... the Integer argument will be
            # implicitly converted to Decimal" — a Decimal (float) literal
            # must not force an INTEGER cast that truncates Decimal sources
            # to NULL (CQL-20 HISTORIAN QA-004: `D + 0.0` over a Decimal
            # list-literal query alias summed to 0).
            def _identifier_numeric_target(ident_ast, other_sql):
                inferred = _infer_static_numeric_type(ident_ast)
                if inferred == "Long":
                    return "BIGINT"
                if inferred == "Decimal":
                    return "DECIMAL(38, 8)"
                if inferred == "Integer":
                    return "INTEGER"
                if isinstance(other_sql, SQLLiteral) and isinstance(other_sql.value, float):
                    return "DECIMAL(38, 8)"
                return "INTEGER"

            if _is_numeric(right) and isinstance(left, SQLIdentifier):
                left = SQLCast(
                    expression=left,
                    target_type=_identifier_numeric_target(expr.left, right),
                    try_cast=True,
                )
            elif _is_numeric(left) and isinstance(right, SQLIdentifier):
                right = SQLCast(
                    expression=right,
                    target_type=_identifier_numeric_target(expr.right, left),
                    try_cast=True,
                )

            # When one side is numeric and the other is a subquery or other
            # non-numeric expression (e.g. SELECT MAX(fhirpath_text(...))),
            # cast the non-numeric side so DuckDB arithmetic works.
            # CQL 1.5 09-b Types/Arithmetic: Decimal arithmetic must stay
            # exact at implementation precision and Integer/Long overflow
            # results in null — so a definition-alias scalar subquery with a
            # declared primitive numeric cql_type is cast to a spec-exact SQL
            # type, never to DOUBLE (DOUBLE silently loses base-10 precision
            # and cannot signal integral overflow). Integral aliases compute
            # in DECIMAL(38,0) (wide enough for any single + - * over
            # Integer/Long CQL ranges) and the final result is narrowed with
            # TRY_CAST so overflow becomes NULL per spec; DuckDB rejects
            # TRY() around scalar subqueries, so the wide-compute/narrow
            # strategy is used instead of a TRY wrap. Unknown-typed subqueries
            # (e.g. MAX(fhirpath_text(...))) keep the DOUBLE fallback.
            def _cast_numeric_subquery(sub, other):
                cte_name = None
                query = getattr(sub, "query", None)
                if isinstance(query, SQLSelect):
                    cte_name = _extract_cte_name_from_select(query)
                if cte_name:
                    meta = self.context.definition_meta.get(cte_name)
                    cql_type = (getattr(meta, "cql_type", None) or "").split(".")[-1]
                    other_is_integral = isinstance(other, SQLLiteral) and isinstance(
                        other.value, int
                    ) and not isinstance(other.value, bool)
                    if cql_type == "Decimal":
                        # Spec-exact CQL Decimal extent: 20 integer + 8 fraction digits.
                        return SQLCast(expression=sub, target_type="DECIMAL(28,8)", try_cast=True)
                    if cql_type in ("Integer", "Long") and sql_op in ("+", "-", "*"):
                        if other_is_integral:
                            alias_narrow_targets.append(
                                "INTEGER" if cql_type == "Integer" else "BIGINT"
                            )
                            return SQLCast(expression=sub, target_type="DECIMAL(38,0)", try_cast=True)
                        return SQLCast(expression=sub, target_type="DOUBLE", try_cast=True)
                    if cql_type in ("Integer", "Long"):
                        return SQLCast(
                            expression=sub,
                            target_type="INTEGER" if cql_type == "Integer" else "BIGINT",
                            try_cast=True,
                        )
                return SQLCast(expression=sub, target_type="DOUBLE", try_cast=True)

            if _is_numeric(right) and not _is_numeric(left) and not isinstance(left, (SQLIdentifier, SQLCast)):
                if isinstance(left, SQLSubquery):
                    left = _cast_numeric_subquery(left, right)
            elif _is_numeric(left) and not _is_numeric(right) and not isinstance(right, (SQLIdentifier, SQLCast)):
                if isinstance(right, SQLSubquery):
                    right = _cast_numeric_subquery(right, left)

        # For comparison operators, ensure type compatibility when one side
        # is a numeric literal and the other is VARCHAR (fhirpath result or CTE column)
        if sql_op in (">", "<", ">=", "<=", "=", "!="):
            def _is_numeric_literal(expr):
                """Check if expression is known to produce a numeric result."""
                if isinstance(expr, SQLLiteral) and isinstance(expr.value, (int, float)) and not isinstance(expr.value, bool):
                    return True
                if isinstance(expr, SQLCast) and expr.target_type in ('INTEGER', 'DOUBLE', 'BIGINT', 'FLOAT', 'DECIMAL'):
                    return True
                if isinstance(expr, SQLBinaryOp) and expr.operator in ('+', '-', '*', '/', '%'):
                    return True
                return False
            # UDFs that return VARCHAR (plain text or JSON quantity strings)
            _VARCHAR_RETURNING_UDFS = frozenset((
                'fhirpath_text', 'fhirpath_scalar', 'fhirpath_number',
                'dateSubtractQuantity', 'dateAddQuantity',
                'quantitySubtract', 'quantity_subtract',
                'quantityAdd', 'quantity_add',
            ))
            def _needs_numeric_cast(expr):
                # Qualified identifier like Alias.value — likely VARCHAR from CTE
                if isinstance(expr, SQLQualifiedIdentifier):
                    return True
                if isinstance(expr, SQLSubquery):
                    return True
                if isinstance(expr, SQLFunctionCall) and expr.name in _VARCHAR_RETURNING_UDFS:
                    return True
                return False
            # UDFs that may return JSON quantity objects like {"value":0.5,"unit":"mg/dL"}
            _QUANTITY_JSON_UDFS = frozenset((
                'fhirpath_text',
                'dateSubtractQuantity', 'dateAddQuantity',
                'quantitySubtract', 'quantity_subtract',
                'quantityAdd', 'quantity_add',
            ))
            def _safe_numeric_cast(expr):
                """Cast to DOUBLE, handling Quantity JSON objects by extracting $.value."""
                number_projection = self._fhirpath_number_projection(expr)
                if number_projection is not None:
                    return number_projection
                if isinstance(expr, SQLFunctionCall) and expr.name in _QUANTITY_JSON_UDFS:
                    # cql_quantity_value is a SQL macro defined in clinical.py;
                    # using it here keeps the emitted SQL DRY and audit-safe.
                    return SQLCast(
                        expression=SQLFunctionCall(name="cql_quantity_value", args=[expr]),
                        target_type="DOUBLE",
                        try_cast=True,
                    )
                return SQLCast(expression=expr, target_type="DOUBLE", try_cast=True)
            if _is_numeric_literal(right) and _needs_numeric_cast(left):
                left = _safe_numeric_cast(left)
            elif _is_numeric_literal(left) and _needs_numeric_cast(right):
                right = _safe_numeric_cast(right)

            # Handle DATE vs VARCHAR type mismatch — with VARCHAR-based datetime
            # representation, both sides should remain VARCHAR strings for comparison.
        # No CAST needed since ISO 8601 strings compare correctly as VARCHAR.

        # CQL §16.4 divide: Decimal division limited to the implementation
        # precision/scale. DuckDB's native `/` promotes DECIMAL operands to
        # DOUBLE (9.9 / 3.0 -> 3.3000000000000003), so route scalar numeric
        # division through the exact cqlDivide UDF (registered by the CQL
        # math macros), which quantizes half-up to scale 8 and returns null
        # for a zero divisor or unrepresentable result (spec: "If the result
        # of the division cannot be represented, or the right argument is 0,
        # the result is null").
        if sql_op == "/":
            return SQLFunctionCall(name="cqlDivide", args=[
                SQLCast(expression=left, target_type="VARCHAR"),
                SQLCast(expression=right, target_type="VARCHAR"),
            ])

        # Nested FHIR extension predicates such as
        # `exists(C.extension Ext where Ext.url = '...')` are translated through
        # a projected `extension.url` path.  Scalar `fhirpath_text` cannot
        # represent all extension repetitions, so route URL equality through an
        # existential FHIRPath predicate over the original resource.
        def _extension_url_exists_call(candidate: SQLExpression, url_expr: SQLExpression) -> Optional[SQLExpression]:
            if not (
                isinstance(candidate, SQLFunctionCall)
                and candidate.name == "fhirpath_text"
                and len(candidate.args) == 2
                and isinstance(candidate.args[1], SQLLiteral)
                and candidate.args[1].value == "extension.url"
                and isinstance(url_expr, SQLLiteral)
                and isinstance(url_expr.value, str)
            ):
                return None
            escaped_url = escape_fhirpath_string_literal(url_expr.value)
            return SQLFunctionCall(
                name="fhirpath_bool",
                args=[
                    candidate.args[0],
                    SQLLiteral(f"extension.where(url='{escaped_url}').exists()"),
                ],
            )

        if sql_op == "=":
            extension_exists = _extension_url_exists_call(left, right)
            if extension_exists is None:
                extension_exists = _extension_url_exists_call(right, left)
            if extension_exists is not None:
                return self._maybe_wrap_audit_comparison(extension_exists, operator, left, right)

        # CQL §12.1/§12.2: List equality requires element type compatibility.
        # DuckDB implicitly coerces [1,2,3] = ['1','2','3'] to true; CQL does not.
        # Per CQL §Equal, however, Integer/Long and Decimal are all numeric and
        # compare by value (1 = 1.0 is true); only non-numeric type mismatches
        # (e.g. String vs Integer) are certain inequality. Map Python literal
        # types to CQL categories before the disjointness check so that
        # {1} = {1.0} does NOT short-circuit to FALSE here — it must reach the
        # runtime CQLListEqualEq macro which performs DECIMAL-cast comparison.
        if sql_op in ("=", "!=") and isinstance(left, SQLArray) and isinstance(right, SQLArray):
            def _cql_numeric_category(py_type_name: str) -> str:
                # bool is a Python int subclass but CQL Boolean is non-numeric.
                if py_type_name == "bool":
                    return "bool"
                if py_type_name in ("int", "float"):
                    return "numeric"
                return py_type_name

            left_types = {
                _cql_numeric_category(type(e.value).__name__)
                for e in left.elements
                if isinstance(e, SQLLiteral)
            }
            right_types = {
                _cql_numeric_category(type(e.value).__name__)
                for e in right.elements
                if isinstance(e, SQLLiteral)
            }
            if left_types and right_types and left_types.isdisjoint(right_types):
                result = SQLLiteral(value=(sql_op == "!="))
                return self._maybe_wrap_audit_comparison(result, operator, left, right)

        if sql_op in ("=", "!=") and self._is_list_operands(left, right, expr):
            if (
                isinstance(left, SQLNull) or (isinstance(left, SQLLiteral) and left.value is None)
                or isinstance(right, SQLNull) or (isinstance(right, SQLLiteral) and right.value is None)
            ):
                return SQLNull()
            equal_result: SQLExpression = self._list_equal_call(left, right, expr.left, expr.right)
            if sql_op == "!=":
                equal_result = SQLUnaryOp(operator="NOT", operand=equal_result)
            return self._maybe_wrap_audit_comparison(equal_result, operator, left, right)

        result = SQLBinaryOp(operator=sql_op, left=left, right=right, precedence=precedence)
        if (
            sql_op in ("+", "-", "*", "/", "%")
            and _static_integer_arithmetic_overflows(expr)
            and not _contains_aggregate_lambda_identifier(result)
            and not _contains_sql_subquery(result)
        ):
            result = SQLNull()
        elif (
            sql_op in ("+", "-", "*")
            # CQL-11 HISTORIAN QA-002: Decimal arithmetic overflow is also
            # null per the CQL 1.5 Appendix B arithmetic header ("operations
            # that cause arithmetic overflow ... will result in null, rather
            # than a run-time error"). Statically-foldable Decimal literal
            # pairs whose exact result exceeds DECIMAL(38, 8) fold to NULL;
            # DuckDB would otherwise raise OutOfRangeException at execution
            # (e.g. 9999999999999999999999999999.0 * 9999999999999999999999999999.0).
            and _decimal_static_arithmetic_unrepresentable(expr)
            and not _contains_aggregate_lambda_identifier(result)
            and not _contains_sql_subquery(result)
        ):
            result = SQLNull()
        elif (
            sql_op in ("+", "-", "*")
            # CQL logical spec: arithmetic overflow results in null, not a
            # run-time error. Statically-foldable literal pairs are handled
            # above; guard the runtime path (at least one operand with no
            # static literal value) whose statically-known numeric operand
            # types are integral (Integer/Long) or Decimal. DuckDB raises on
            # INT32/INT64 and DECIMAL(38) overflow, so wrap in TRY(...) to
            # produce NULL per spec.
            and (_static_numeric_value(expr.left) is None or _static_numeric_value(expr.right) is None)
            and _numeric_static_operand_types(expr)
            and not _contains_aggregate_lambda_identifier(result)
            and not _contains_sql_subquery(result)
            # DuckDB forbids TRY() around volatile functions (including all
            # Python UDFs, which default to volatile). Restrict the guard to
            # function-call-free arithmetic (literals, identifiers, casts,
            # binary/unary operators) so DQM/measure SQL keeps binding.
            and not _contains_function_call(result)
        ):
            result = SQLFunctionCall(name="TRY", args=[result])
        elif (
            sql_op in ("+", "-", "*")
            # CQL 1.5 overflow-to-null for definition-alias integral
            # arithmetic: the alias side computed in DECIMAL(38,0) (see
            # _cast_numeric_subquery) is narrowed back to its CQL type with
            # TRY_CAST, so out-of-range results become NULL instead of
            # raising (DuckDB rejects TRY() around scalar subqueries).
            and alias_narrow_targets
            and not _contains_aggregate_lambda_identifier(result)
            and not _contains_function_call(result)
        ):
            narrow = "INTEGER" if "INTEGER" in alias_narrow_targets else "BIGINT"
            result = SQLCast(expression=result, target_type=narrow, try_cast=True)
        return self._maybe_wrap_audit_comparison(result, operator, left, right)


    def _resolve_valueset_identifier(self, ident_name: str, _depth: int = 0) -> Optional[str]:
        """Resolve a valueset identifier to its canonical URL."""
        # Check direct valueset registry
        if ident_name in self.context.valuesets:
            return self.context.valuesets[ident_name]
        # Check included libraries
        if hasattr(self.context, 'includes'):
            for lib_name, lib in self.context.includes.items():
                if hasattr(lib, 'valuesets') and ident_name in lib.valuesets:
                    return lib.valuesets[ident_name]
        # CQL-02 HISTORIAN QA-001: a define alias whose body is a ValueSet
        # reference (e.g. `define VSDef: "Example VS"` then `X in VSDef`)
        # must resolve through the alias to the canonical URL so the
        # terminology boundary receives a URL, never the structured clinical
        # JSON (which produced `... IN '{"id":...}'` ParserExceptions).
        # Only Identifier chains ending in a valueset declaration resolve.
        if _depth < 4:
            ast_def = self._definition_source_ast(ident_name)
            if isinstance(ast_def, Identifier):
                return self._resolve_valueset_identifier(ast_def.name, _depth + 1)
            if isinstance(ast_def, QualifiedIdentifier) and ast_def.parts:
                return self._resolve_valueset_identifier(ast_def.parts[-1], _depth + 1)
        return None

    def _resolve_codesystem_identifier(self, ident_name: str, _depth: int = 0) -> Optional[str]:
        """Resolve a codesystem identifier (or define alias of one) to its URL."""
        if ident_name in self.context.codesystems:
            return self.context.codesystems[ident_name]
        # CQL-02 HISTORIAN QA-001: same alias discipline as ValueSet —
        # `define CSDef: LOINC` then `X in CSDef` must unwrap to the URL.
        if _depth < 4:
            ast_def = self._definition_source_ast(ident_name)
            if isinstance(ast_def, Identifier):
                return self._resolve_codesystem_identifier(ast_def.name, _depth + 1)
            if isinstance(ast_def, QualifiedIdentifier) and ast_def.parts:
                return self._resolve_codesystem_identifier(ast_def.parts[-1], _depth + 1)
        return None

    @staticmethod
    def _valueset_url_from_literal(value: Any) -> Optional[str]:
        """Extract a ValueSet URL from a structured CQL ValueSet literal."""
        if not isinstance(value, str):
            return None
        text = value.strip()
        if not text:
            return None
        if not text.startswith("{"):
            return text
        try:
            parsed = json.loads(text)
        except (TypeError, ValueError):
            return None
        if not isinstance(parsed, dict):
            return None
        identifier = parsed.get("id")
        if not isinstance(identifier, str) or not identifier:
            return None
        version = parsed.get("version")
        if isinstance(version, str) and version:
            return f"{identifier}|{version}"
        return identifier

    def _valueset_url_from_placeholder(self, placeholder: ParameterPlaceholder) -> Optional[str]:
        """Resolve an inlined ValueSet parameter placeholder to a URL."""
        sql_expr = placeholder.sql_expr
        if isinstance(sql_expr, SQLIdentifier):
            return self._resolve_valueset_identifier(sql_expr.name)
        if isinstance(sql_expr, SQLLiteral):
            return self._valueset_url_from_literal(sql_expr.value)
        return None

    def _translate_unary_expression(self, expr: UnaryExpression, boolean_context: bool = False) -> SQLExpression:
        """Translate a CQL unary expression to SQL."""
        operator = expr.operator.lower() if isinstance(expr.operator, str) else expr.operator

        # Check for singleton from with component filter BEFORE translating operand
        if operator == "singleton from" and self._is_component_filter_query(expr.operand):
            return self._translate_component_filter_singleton(expr.operand)

        if operator == "singleton from":
            # CQL-19 HISTORIAN QA-002: a stored-list define reference
            # (`define G: Patient.name.given; singleton from G`) stores one
            # row whose value column IS the element list — counting rows (1)
            # instead of elements silently returns the whole list instead of
            # the §20.30 run-time error. Translate the reference as the
            # scalar element list and apply the element-cardinality CASE.
            if isinstance(expr.operand, Identifier):
                _sf_meta = self.context.definition_meta.get(expr.operand.name)
                if (
                    _sf_meta is not None
                    and not _sf_meta.has_resource
                    and getattr(_sf_meta, "stores_list_value", False)
                ):
                    return self._apply_singleton_from_list_value(
                        self.translate(expr.operand, usage=ExprUsage.SCALAR)
                    )
            source_node = self._definition_ast_for_identifier(expr.operand) or expr.operand
            if isinstance(source_node, Query) and self._is_list_typed_ast(source_node):
                operand = _coerce_query_rows_to_list(self.translate(source_node, usage=ExprUsage.LIST))
                return self._apply_singleton_from(operand)
            # Bare retrieve (e.g. singleton from [Observation]) lowers to a CTE
            # placeholder; wrap it in a row subquery so the cardinality-checking
            # branch of _apply_singleton_from applies with patient correlation.
            if isinstance(source_node, Retrieve):
                placeholder = self.translate(source_node, usage=ExprUsage.LIST)
                return self._apply_singleton_from(SQLSubquery(query=SQLSelect(
                    columns=[SQLIdentifier(name="*")],
                    from_clause=SQLAlias(expr=placeholder, alias="_sf_src"),
                )))

        if operator == "not":
            self._validate_boolean_operand(expr.operand, operator)
            operand = self.translate(expr.operand, boolean_context=True)
            if self.context.audit_mode and self.context.audit_expressions:
                return SQLFunctionCall(name="audit_not", args=[_ensure_audit_struct(operand)])
            return SQLUnaryOp(operator="NOT", operand=operand, prefix=True)

        if operator == "-":
            # Signed CQL numeric minima are represented as unary negation of a
            # positive literal one step beyond the positive maximum.
            if isinstance(expr.operand, Literal) and isinstance(expr.operand.value, int) and not isinstance(expr.operand.value, bool):
                lit_type = getattr(expr.operand, "type", None)
                if lit_type == "Integer":
                    if expr.operand.value > 2147483648:
                        raise ValueError(
                            f"Integer literal -{expr.operand.value} out of range for CQL Integer type "
                            f"[-2147483648, 2147483647]"
                        )
                    return SQLLiteral(value=-expr.operand.value)
                if lit_type == "Long":
                    if expr.operand.value > 9223372036854775808:
                        raise ValueError(
                            f"Long literal -{expr.operand.value} out of range for CQL Long type "
                            f"[-9223372036854775808, 9223372036854775807]"
                        )
                    return SQLLiteral(value=-expr.operand.value)

        if operator in {"predecessor of", "successor of"} and isinstance(expr.operand, FunctionRef):
            boundary_name = expr.operand.name.lower()
            if boundary_name in {"minimum", "maximum"} and expr.operand.arguments:
                type_arg = expr.operand.arguments[0]
                if isinstance(type_arg, (NamedTypeSpecifier, Identifier)):
                    type_name = type_arg.name.lower()
                    if (
                        (operator == "predecessor of" and boundary_name == "minimum")
                        or (operator == "successor of" and boundary_name == "maximum")
                    ) and type_name in {"integer", "long", "decimal"}:
                        return SQLNull()

        if operator == "predecessor of" and (
            _is_datetime_boundary_constructor(expr.operand, [1, 1, 1, 0, 0, 0, 0])
            or _is_datetime_boundary_literal(expr.operand, "0001-01-01T00:00:00.000")
            or _is_time_boundary_literal(expr.operand, "T00:00:00.000")
        ):
            raise ValueError(
                "The result of the predecessor operation precedes "
                "the minimum value allowed for the type"
            )

        if operator == "successor of" and (
            _is_datetime_boundary_constructor(expr.operand, [9999, 12, 31, 23, 59, 59, 999])
            or _is_datetime_boundary_literal(expr.operand, "9999-12-31T23:59:59.999")
            or _is_time_boundary_literal(expr.operand, "T23:59:59.999")
        ):
            raise ValueError(
                "The result of the successor operation exceeds "
                "the maximum value allowed for the type"
            )

        # CQL §Nullological Operators (Developer's Guide): the infix null-test
        # and boolean-test operators (`is null`, `is not null`, `is true`,
        # `is false`, `is not true`, `is not false`) are equivalent to their
        # function-call forms (`IsNull`, `IsNotNull`, `IsTrue`, `IsFalse`) per
        # Translation Semantics Table 6-F. The function-call path already
        # inlines static `define` aliases (see `static_inline_functions` in
        # `_translate_function_call`); apply the same inlining here so that
        # `MyVal is true` (where `define MyVal: true`) emits `IsTrue(TRUE)`
        # rather than treating the alias as a resource retrieve.
        if operator in {
            "is null", "is not null",
            "is true", "is false",
            "is not true", "is not false",
        }:
            operand_node = self._static_conversion_source_node(expr.operand)
            # Boolean-test operators must keep boolean_context=True so that
            # dynamic FHIR Boolean fields continue to project through
            # `fhirpath_bool` (not `fhirpath_text`). Null-test operators do
            # not require Boolean projection.
            is_boolean_test = operator in {
                "is true", "is false", "is not true", "is not false"
            }
            translate_source = operand_node if operand_node is not None else expr.operand
            operand = self.translate(
                translate_source,
                boolean_context=is_boolean_test,
            )

            if operator == "is null":
                return SQLUnaryOp(operator="IS NULL", operand=operand, prefix=False)
            if operator == "is not null":
                return SQLUnaryOp(operator="IS NOT NULL", operand=operand, prefix=False)
            if operator == "is true":
                return SQLFunctionCall(name="IsTrue", args=[operand])
            if operator == "is false":
                return SQLFunctionCall(name="IsFalse", args=[operand])
            if operator == "is not true":
                return SQLUnaryOp(
                    operator="NOT",
                    operand=SQLFunctionCall(name="IsTrue", args=[operand]),
                    prefix=True,
                )
            if operator == "is not false":
                return SQLUnaryOp(
                    operator="NOT",
                    operand=SQLFunctionCall(name="IsFalse", args=[operand]),
                    prefix=True,
                )

        operand = self.translate(expr.operand, boolean_context=False)

        if operator == "-":
            # CQL §16.8: Negate — for Quantity operands, use quantityNegate UDF
            if _is_quantity_expression(operand) or self._is_cql_quantity_expr(expr.operand):
                return SQLFunctionCall(name="quantityNegate", args=[_ensure_parse_quantity(operand)])
            if isinstance(expr.operand, FunctionRef) and expr.operand.name.lower() == "minimum" and expr.operand.arguments:
                type_arg = expr.operand.arguments[0]
                if isinstance(type_arg, (NamedTypeSpecifier, Identifier)):
                    type_name = type_arg.name.lower()
                    if type_name in {"integer", "long"}:
                        return SQLNull()
                    if type_name == "decimal":
                        return SQLLiteral(
                            value="99999999999999999999.99999999",
                            raw_sql="99999999999999999999.99999999",
                        )
            # CQL §16 Negate: "If the result of negating the argument cannot be
            # represented (e.g. -(minimum Integer)), the result is null." Detect a
            # folded SQL literal whose value is exactly the type minimum (which
            # happens when the source is a literal-spelled minimum like
            # `-(-2147483648)` after parser-level unary folding).
            if isinstance(operand, SQLLiteral) and isinstance(operand.value, int) and not isinstance(operand.value, bool):
                v = operand.value
                if v == -2147483648 or v == -9223372036854775808:
                    return SQLNull()
            # CQL §16.8 Negate overloads Integer/Long/Decimal/Quantity. The
            # duration/difference-between and age operators are
            # Integer-valued in CQL but lower to VARCHAR-returning §22.21
            # helpers (crisp integer string or uncertainty interval JSON).
            # Binary arithmetic on those results routes through
            # cqlUncertainAdd/cqlUncertainSubtract; unary negation must
            # likewise stay interval-aware: -x ≡ x * -1 through
            # cqlUncertainMultiply, which collapses crisp values and
            # propagates uncertainty intervals (CQL-11 EXPLORER QA-002;
            # generalized in CQL-21 HISTORIAN QA-003 — the previous BIGINT
            # cast dropped uncertain ranges to NULL).
            if _uncertain_between_sql_name(operand) is not None:
                return SQLFunctionCall(
                    name="cqlUncertainMultiply",
                    args=[
                        operand,
                        SQLCast(expression=SQLLiteral(value="-1"), target_type="VARCHAR"),
                    ],
                )
            return SQLUnaryOp(operator="-", operand=operand, prefix=True)

        if operator == "+":
            return operand  # Unary plus is a no-op

        if operator == "exists":
            return self._translate_exists(operand, negated=False)

        # Interval operators: start of, end of, width of
        if operator == "start of":
            # Convert bare resource alias to its primary interval
            operand = self._ensure_resource_to_interval(operand, expr.operand)
            # Gap 8: If operand is intervalFromBounds(start, end), simplify to start
            if isinstance(operand, SQLFunctionCall) and operand.name == "intervalFromBounds" and len(operand.args) >= 2:
                return operand.args[0]
            return SQLFunctionCall(name="intervalStart", args=[operand])

        if operator == "end of":
            # Convert bare resource alias to its primary interval
            operand = self._ensure_resource_to_interval(operand, expr.operand)
            # Gap 8: If operand is intervalFromBounds(start, end), simplify to end
            if isinstance(operand, SQLFunctionCall) and operand.name == "intervalFromBounds" and len(operand.args) >= 2:
                result = operand.args[1]
                # Gap 18: Mark as exclusive boundary only for open (half-open) intervals
                # intervalFromBounds(low, high, lowClosed, highClosed) — if highClosed is
                # False, the end is exclusive; if True (or unspecified), it's inclusive.
                is_closed = True  # default: closed
                if len(operand.args) >= 4:
                    high_closed_arg = operand.args[3]
                    if isinstance(high_closed_arg, SQLLiteral) and high_closed_arg.value in (False, 'FALSE', 'false'):
                        is_closed = False
                if not is_closed:
                    result.is_exclusive_boundary = True
                return result
            return SQLFunctionCall(name="intervalEnd", args=[operand])

        if operator == "width of":
            return SQLFunctionCall(name="intervalWidth", args=[operand])

        # CQL §19.22: point from — extracts the single point from a unit interval
        if operator == "point from":
            return SQLFunctionCall(name="pointFrom", args=[operand])

        # Ordinal operators: predecessor of, successor of
        # CQL §22.25/§22.26: step size depends on type
        # Integer: ±1, Decimal: ±10^-8, Long: ±1
        if operator == "predecessor of":
            if isinstance(expr.operand, Quantity):
                return SQLFunctionCall(name="predecessorOf", args=[_quantity_literal_json(expr.operand)])
            if (
                isinstance(expr.operand, UnaryExpression)
                and expr.operand.operator.lower() == "singleton from"
                and isinstance(expr.operand.operand, ListExpression)
                and len(expr.operand.operand.elements) == 1
                and isinstance(expr.operand.operand.elements[0], Quantity)
            ):
                return SQLFunctionCall(
                    name="predecessorOf",
                    args=[_quantity_literal_json(expr.operand.operand.elements[0])],
                )
            # CQL-11 EXPLORER QA-001: CQL §22.25 Predecessor: "If the result
            # cannot be represented (e.g. predecessor of (minimum Integer)),
            # the result is null." The FunctionRef form is special-cased
            # above (line ~6580); mirror the same guard for the literal-
            # spelled form. DuckDB silently promotes INTEGER to BIGINT during
            # execution, so `predecessorOf(-2147483648)` returns -2147483649
            # (a valid BIGINT, but not a valid CQL Integer). The Long check
            # also runs as a defense-in-depth even though BIGINT cannot
            # represent _CQL_LONG_MIN - 1.
            if isinstance(operand, SQLLiteral) and isinstance(operand.value, int) and not isinstance(operand.value, bool):
                if operand.value == _CQL_INTEGER_MIN or operand.value == _CQL_LONG_MIN:
                    return SQLNull()
            # CQL-11 EXPLORER QA-001 follow-up: the same Integer-range rule
            # applies to statically Integer-typed NON-literal operands (the
            # literal guard above cannot fire because the value is dynamic).
            # DuckDB's BIGINT helper clamps only at Long bounds, so guard the
            # Integer boundary here with a CASE. Statically Long operands keep
            # the plain helper (BIGINT overload nulls at int64 bounds).
            if _infer_static_numeric_type(expr.operand) == "Integer":
                return SQLCase(
                    when_clauses=[
                        (
                            SQLBinaryOp(
                                left=operand,
                                operator="<=",
                                right=SQLLiteral(value=_CQL_INTEGER_MIN),
                            ),
                            SQLNull(),
                        )
                    ],
                    else_clause=SQLFunctionCall(name="predecessorOf", args=[operand]),
                )
            return SQLFunctionCall(name="predecessorOf", args=[operand])

        if operator == "successor of":
            if isinstance(expr.operand, Quantity):
                return SQLFunctionCall(name="successorOf", args=[_quantity_literal_json(expr.operand)])
            if (
                isinstance(expr.operand, UnaryExpression)
                and expr.operand.operator.lower() == "singleton from"
                and isinstance(expr.operand.operand, ListExpression)
                and len(expr.operand.operand.elements) == 1
                and isinstance(expr.operand.operand.elements[0], Quantity)
            ):
                return SQLFunctionCall(
                    name="successorOf",
                    args=[_quantity_literal_json(expr.operand.operand.elements[0])],
                )
            # CQL-11 EXPLORER QA-001: CQL §22.26 Successor: "If the result
            # cannot be represented (e.g. successor of (maximum Integer)),
            # the result is null." Mirror the FunctionRef guard for the
            # literal-spelled form. DuckDB silently promotes INTEGER to
            # BIGINT, so `successorOf(2147483647)` returns 2147483648 (a
            # valid BIGINT, but not a valid CQL Integer).
            if isinstance(operand, SQLLiteral) and isinstance(operand.value, int) and not isinstance(operand.value, bool):
                if operand.value == _CQL_INTEGER_MAX or operand.value == _CQL_LONG_MAX:
                    return SQLNull()
            # CQL-11 EXPLORER QA-001 follow-up: statically Integer-typed
            # non-literal operands need the Integer-range boundary guard in
            # translation (see predecessor mirror above).
            if _infer_static_numeric_type(expr.operand) == "Integer":
                return SQLCase(
                    when_clauses=[
                        (
                            SQLBinaryOp(
                                left=operand,
                                operator=">=",
                                right=SQLLiteral(value=_CQL_INTEGER_MAX),
                            ),
                            SQLNull(),
                        )
                    ],
                    else_clause=SQLFunctionCall(name="successorOf", args=[operand]),
                )
            return SQLFunctionCall(name="successorOf", args=[operand])

        # Singleton from operator - extract single element from list
        if operator == "singleton from":
            return self._apply_singleton_from(operand)

        # Default: pass through
        return SQLUnaryOp(operator=operator, operand=operand, prefix=True)
