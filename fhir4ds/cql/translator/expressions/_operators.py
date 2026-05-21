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
    _is_list_returning_sql,
    _contains_sql_subquery,
    _ensure_scalar_body,
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

logger = logging.getLogger(__name__)

from ...translator.component_codes import get_code_to_column_mapping
from ...translator.fhirpath_builder import (
    build_coding_exists_expr,
    build_multi_coding_exists_expr,
    build_where_return_expr,
    FHIRPathBuilder,
)


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
        _QUANTITY_RETURNING_FUNCS = frozenset({
            "parse_quantity", "quantityNegate", "quantityAbs",
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
        if isinstance(node, BinaryExpression) and node.operator == "union":
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
        name = (
            "CQLListContainsTemporalEq"
            if self._use_temporal_list_contains(list_ast, element_ast)
            else "CQLListContainsEq"
        )
        return SQLFunctionCall(name=name, args=[list_sql, element_sql])

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
        return SQLFunctionCall(name=name, args=[left_sql, right_sql])

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
        if isinstance(operand, ListExpression):
            return "List<Any>"
        if isinstance(operand, ExistsExpression):
            return "Boolean"
        if isinstance(operand, Identifier):
            meta = self.context.definition_meta.get(operand.name)
            if meta:
                return meta.cql_type
            ast_defs = getattr(self.context, "_definition_cql_asts", {})
            ast_def = ast_defs.get(operand.name)
            if ast_def is not None and ast_def is not operand:
                return self._infer_static_cql_type_for_logical_operand(ast_def)
            return "Any"
        if isinstance(operand, FunctionRef):
            boolean_functions = {
                "toboolean",
                "convertstoboolean",
                "istrue",
                "isfalse",
                "alltrue",
                "anytrue",
                "allfalse",
                "anyfalse",
            }
            return "Boolean" if operand.name.lower() in boolean_functions else "Any"
        if isinstance(operand, BinaryExpression):
            op = operand.operator.lower() if isinstance(operand.operator, str) else operand.operator
            if op == "as":
                target = getattr(operand.right, "name", None)
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
        if isinstance(operand, UnaryExpression):
            op = operand.operator.lower() if isinstance(operand.operator, str) else operand.operator
            if op in {"not", "is null", "is not null", "is true", "is false", "exists"}:
                return "Boolean"
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
        if isinstance(node, Quantity):
            return True
        # "as Quantity" cast
        if isinstance(node, BinaryExpression) and node.operator == "as":
            ts = node.right
            if isinstance(ts, NamedTypeSpecifier) and getattr(ts, "name", "") == "Quantity":
                return True
            if isinstance(ts, Identifier) and ts.name == "Quantity":
                return True
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

        # CQL `between` uses `and` as a bound separator, not as a logical
        # operator. Lower it before translating the synthetic right-side node.
        if operator == "between":
            if isinstance(expr.right, BinaryExpression) and str(expr.right.operator).lower() == "and":
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
                if (
                    isinstance(expr.right, ListTypeSpecifier)
                    and isinstance(expr.left, ListExpression)
                    and not expr.left.elements
                ):
                    return SQLCast(
                        expression=SQLArray(elements=[]),
                        target_type=_sql_list_type_for_cql_list_specifier(expr.right),
                    )
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
                        return left
                    if isinstance(expr.left, Literal):
                        literal_type = getattr(expr.left, "type", None)
                        if literal_type is not None and literal_type.lower() == bare_target.lower():
                            return left
                        return SQLNull()
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
                            return SQLNull()
                        if return_type is not None:
                            return left

                    if isinstance(expr.left, Identifier):
                        meta = self.context.definition_meta.get(expr.left.name)
                        meta_type = self._bare_cql_type_name(getattr(meta, "cql_type", None)) if meta else None
                        if meta_type and meta_type.lower() in {target.lower() for target in primitive_targets}:
                            if meta_type.lower() != bare_target.lower():
                                return SQLNull()
                            target_sql_type = {
                                "boolean": "BOOLEAN",
                                "integer": "INTEGER",
                                "long": "BIGINT",
                                "decimal": "DOUBLE",
                                "string": "VARCHAR",
                            }.get(bare_target.lower())
                            if target_sql_type and bare_target.lower() != "string":
                                return SQLCast(expression=left, target_type=target_sql_type, try_cast=True)
                            return left

                    static_source = self._static_structural_type_name(expr.left)
                    if static_source is not None:
                        if self._structural_type_conforms(static_source, target_name):
                            return left
                        return SQLNull()

                    fhirpath_type_check = self._fhirpath_primitive_type_check(left, bare_target)
                    fhirpath_value = self._fhirpath_primitive_as_value(left, bare_target)
                    if fhirpath_type_check is not None and fhirpath_value is not None:
                        return SQLCase(
                            when_clauses=[(fhirpath_type_check, fhirpath_value)],
                            else_clause=SQLNull(),
                        )

                    cql_typed_value = self._cql_typed_value_as_value(left, bare_target)
                    if cql_typed_value is not None:
                        return cql_typed_value

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
                        return SQLCase(
                            when_clauses=[(can_cast, SQLCast(expression=left, target_type=target_sql, try_cast=True))],
                            else_clause=SQLNull(),
                        )

                    if bare_target in ("Decimal", "decimal"):
                        return SQLCase(
                            when_clauses=[
                                (
                                    textual_primitive,
                                    SQLCast(expression=left, target_type="DOUBLE", try_cast=True),
                                )
                            ],
                            else_clause=SQLNull(),
                        )

                    if bare_target in ("Boolean", "boolean"):
                        lowered = SQLFunctionCall(name="LOWER", args=[text_value])
                        is_true = SQLBinaryOp(operator="=", left=lowered, right=SQLLiteral(value="true"))
                        is_false = SQLBinaryOp(operator="=", left=lowered, right=SQLLiteral(value="false"))
                        bool_text = SQLBinaryOp(operator="OR", left=is_true, right=is_false)
                        can_cast = SQLBinaryOp(operator="AND", left=textual_primitive, right=bool_text)
                        return SQLCase(
                            when_clauses=[(can_cast, SQLCast(expression=left, target_type="BOOLEAN", try_cast=True))],
                            else_clause=SQLNull(),
                        )

                    return SQLCase(when_clauses=[(textual_primitive, left)], else_clause=SQLNull())

                clinical_target = self._CLINICAL_CQL_TYPES.get(bare_target.lower())
                if clinical_target is not None:
                    clinical_source = self._static_clinical_type(expr.left)
                    if clinical_source is not None:
                        if self._clinical_type_matches(clinical_source, clinical_target):
                            return left
                        return SQLNull()
                    static_source = self._static_structural_type_name(expr.left)
                    if static_source is not None:
                        return SQLNull()
                    if bare_target in ("Code", "code", "Concept", "concept"):
                        if self._extract_fhirpath_value_call(left) is not None:
                            return left
                        runtime_check = self._clinical_json_type_check(left, bare_target)
                        if runtime_check is not None:
                            return SQLCase(
                                when_clauses=[(runtime_check, left)],
                                else_clause=SQLNull(),
                            )
                        return SQLNull()

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
                    return result

                if isinstance(left, SQLFunctionCall) and left.name == "CQLMessage":
                    return left

                type_check = self._translate_is_type_check(
                    BinaryExpression(operator="is", left=expr.left, right=expr.right)
                )
                as_value = self._cql_typed_value_as_value(left, bare_target) or left
                source_node = self._definition_ast_for_identifier(expr.left)
                if source_node is not None and self._static_structural_type_name(source_node):
                    as_value = self.translate(source_node, usage=ExprUsage.SCALAR)
                return SQLCase(
                    when_clauses=[(type_check, as_value)],
                    else_clause=SQLNull(),
                )
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
            safe_div = SQLBinaryOp(operator="/", left=left,
                                   right=SQLFunctionCall(name="NULLIF", args=[right, SQLLiteral(value=0)]))
            return SQLFunctionCall(name="TRUNC", args=[safe_div])

        if operator == "^":
            left_arg = self._fhirpath_number_projection(left) or left
            right_arg = self._fhirpath_number_projection(right) or right
            return SQLCast(
                expression=SQLFunctionCall(name="mathPower", args=[
                    SQLCast(expression=left_arg, target_type="VARCHAR"),
                    SQLCast(expression=right_arg, target_type="VARCHAR"),
                ]),
                target_type="DOUBLE",
                try_cast=True,
            )

        # List set operators
        if operator == "union":
            return self._translate_union_op(operator, left, right, expr)
        if operator == "intersect":
            return self._translate_intersect_op(operator, left, right, expr)
        if operator == "except":
            if self._is_list_operands(left, right, expr):
                if isinstance(right, SQLNull):
                    return left
                if isinstance(left, SQLNull):
                    return SQLNull()
                return SQLFunctionCall(name="CQLListExceptEq", args=[left, right])
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
            return SQLFunctionCall(name="CQLListExceptEq", args=[left, right])

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
            if self._is_list_operands(left, right, expr):
                left_is_list = self._is_single_list_expr(left, getattr(expr, 'left', None))
                right_is_list = self._is_single_list_expr(right, getattr(expr, 'right', None))
                if left_is_list and not right_is_list:
                    # List includes element → list_contains
                    if isinstance(right, SQLNull) or (isinstance(right, SQLLiteral) and right.value is None):
                        return SQLNull()
                    return self._list_contains_call(left, right, expr.left, expr.right)
                if (
                    isinstance(left, SQLNull) or (isinstance(left, SQLLiteral) and left.value is None)
                    or isinstance(right, SQLNull) or (isinstance(right, SQLLiteral) and right.value is None)
                ):
                    return SQLNull()
                return self._list_has_all_call(left, right, expr.left, expr.right)
            left = self._ensure_resource_to_interval(left, expr.left)
            right = self._ensure_resource_to_interval(right, expr.right)
            right_is_interval = self._is_fhir_interval_expression(right)
            if right_is_interval:
                return SQLFunctionCall(name="intervalIncludes", args=[left, right])
            return SQLFunctionCall(name="intervalContains", args=[left, self._ensure_interval_varchar(right)])
        if operator == "included in":
            if self._is_list_operands(left, right, expr):
                left_is_list = self._is_single_list_expr(left, getattr(expr, 'left', None))
                right_is_list = self._is_single_list_expr(right, getattr(expr, 'right', None))
                if right_is_list and not left_is_list:
                    # Element included in list → list_contains
                    if isinstance(left, SQLNull) or (isinstance(left, SQLLiteral) and left.value is None):
                        return SQLNull()
                    return self._list_contains_call(right, left, expr.right, expr.left)
                if (
                    isinstance(left, SQLNull) or (isinstance(left, SQLLiteral) and left.value is None)
                    or isinstance(right, SQLNull) or (isinstance(right, SQLLiteral) and right.value is None)
                ):
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
                        args=[r, self._ensure_interval_varchar(left), SQLLiteral(value=precision)],
                    )
                return SQLFunctionCall(name="intervalContains", args=[r, self._ensure_interval_varchar(left)])
            return SQLFunctionCall(name="intervalContains", args=[right, self._ensure_interval_varchar(left)])
        if operator == "properly includes":
            if self._is_list_operands(left, right, expr):
                left_is_list = self._is_single_list_expr(left, getattr(expr, 'left', None))
                right_is_list = self._is_single_list_expr(right, getattr(expr, 'right', None))
                left_is_null = isinstance(left, SQLNull) or (isinstance(left, SQLLiteral) and left.value is None)
                right_is_null = isinstance(right, SQLNull) or (isinstance(right, SQLLiteral) and right.value is None)
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
            if precision is not None:
                left_interval = left if self._is_fhir_interval_expression(left) else self._point_as_interval(left)
                right_interval = (
                    right_for_interval
                    if self._is_fhir_interval_expression(right_for_interval)
                    else self._point_as_interval(right_for_interval)
                )
                includes = SQLFunctionCall(
                    name="intervalIncludesPrecise",
                    args=[left_interval, right_interval, SQLLiteral(value=precision)],
                )
                same = self._interval_same_at_precision(left_interval, right_interval, precision)
                return SQLBinaryOp(operator="AND", left=includes, right=SQLUnaryOp(operator="NOT", operand=same))
            if right_is_interval:
                return SQLFunctionCall(name="intervalProperlyIncludes", args=[left, right])
            return SQLFunctionCall(name="intervalProperlyContains", args=[left, self._ensure_interval_varchar(right)])
        if operator == "properly included in":
            if self._is_list_operands(left, right, expr):
                left_is_list = self._is_single_list_expr(left, getattr(expr, 'left', None))
                right_is_list = self._is_single_list_expr(right, getattr(expr, 'right', None))
                left_is_null = isinstance(left, SQLNull) or (isinstance(left, SQLLiteral) and left.value is None)
                right_is_null = isinstance(right, SQLNull) or (isinstance(right, SQLLiteral) and right.value is None)
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
                same = self._interval_same_at_precision(left_interval, right_interval, precision)
                return SQLBinaryOp(operator="AND", left=included, right=SQLUnaryOp(operator="NOT", operand=same))
            left_is_interval = self._is_fhir_interval_expression(left)
            right_is_interval = self._is_fhir_interval_expression(right)
            if left_is_interval:
                l = self._unwrap_precision_wrapper(left)
                r = self._unwrap_precision_wrapper(right) if right_is_interval else right
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
            return SQLFunctionCall(name="intervalMeets", args=[left, right])
        if operator == "meets before":
            left = self._ensure_resource_to_interval(left, expr.left)
            right = self._ensure_resource_to_interval(right, expr.right)
            return SQLFunctionCall(name="intervalMeetsBefore", args=[left, right])
        if operator == "meets after":
            left = self._ensure_resource_to_interval(left, expr.left)
            right = self._ensure_resource_to_interval(right, expr.right)
            return SQLFunctionCall(name="intervalMeetsAfter", args=[left, right])
        if operator == "starts":
            return self._translate_starts_op(operator, left, right, expr)
        if operator == "ends":
            return self._translate_ends_op(operator, left, right, expr)
        if operator.startswith("same "):
            return self._translate_same_operator(operator, left, right)

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

        # Detect list context by checking if left translated to a subquery
        # BUT first check if it's an interval reference (CTE producing interval)
        if isinstance(left, SQLSubquery) and self._is_fhir_interval_expression(left):
            if self._is_fhir_interval_expression(right):
                # Interval includes interval
                return SQLFunctionCall(name="intervalIncludes", args=[left, right])
            # Interval contains point
            return SQLFunctionCall(
                name="intervalContains",
                args=[left, self._ensure_interval_varchar(right)],
            )
        if self._is_list_operands(left, right, expr):
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
                args=[left, self._ensure_interval_varchar(right)],
            )
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
        if isinstance(node, Identifier):
            if self.context.is_alias(node.name):
                return None
            info = self.context.get_code(node.name)
            if info is None:
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
            if bare == "Code" and fields.get("code"):
                return self._normalize_static_clinical_code(fields)
            if bare == "Concept":
                return fields
        return None

    def _normalize_static_clinical_code(self, value: dict[str, Any]) -> dict[str, Any]:
        code = {
            "code": value.get("code", ""),
            "system": self.context.codesystems.get(
                value.get("system", value.get("codesystem", "")),
                value.get("system", value.get("codesystem", "")),
            ),
        }
        if value.get("version") is not None:
            code["version"] = value.get("version")
        if value.get("display") is not None:
            code["display"] = value.get("display")
        return code

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


    def _translate_in_op(self, operator, left, right, expr, boolean_context) -> SQLExpression:
        """Extracted from _translate_binary_expression."""
        def _code_entries_from_ast(node) -> Optional[list[dict[str, Any]]]:
            if isinstance(node, Literal) and node.value is None:
                return []
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
                for element in node.elements:
                    value_expr = element.type
                    if isinstance(value_expr, Literal):
                        fields[element.name] = value_expr.value
                if bare == "Code" and fields.get("code"):
                    return [fields]
                if bare == "Concept" and isinstance(fields.get("codes"), list):
                    return [code for code in fields["codes"] if isinstance(code, dict)]
            return None

        def _string_code_from_ast(node) -> Optional[str]:
            if isinstance(node, Literal) and isinstance(node.value, str):
                return node.value
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

        # CQL §20.10: If the list argument is null, the result is null.
        if isinstance(right, SQLNull) or (isinstance(right, SQLLiteral) and right.value is None):
            return SQLNull()
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
            static_code_entries = _code_entries_from_ast(expr.left)
            if static_code_entries is not None:
                return _or_chain([
                    SQLFunctionCall(
                        name="in_valueset",
                        args=[_synthetic_code_resource(entry), SQLLiteral("code"), SQLLiteral(vs_url)],
                    )
                    for entry in static_code_entries
                ])
            static_string_code = _string_code_from_ast(expr.left)
            if static_string_code is not None:
                return SQLFunctionCall(
                    name="in_valueset",
                    args=[
                        _synthetic_code_resource({"system": "", "code": static_string_code}),
                        SQLLiteral("code"),
                        SQLLiteral(vs_url),
                    ],
                )
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

        if isinstance(expr.right, Identifier) and expr.right.name in self.context.codesystems:
            codesystem_url = self.context.codesystems[expr.right.name]
            static_code_entries = _code_entries_from_ast(expr.left)
            if static_code_entries is not None:
                return SQLLiteral(
                    value=any(
                        _normalize_code_entry(entry).get("system", "") == codesystem_url
                        for entry in static_code_entries
                    )
                )
            static_string_code = _string_code_from_ast(expr.left)
            if static_string_code is not None:
                return SQLLiteral(value=static_string_code != "")
            if (
                isinstance(left, SQLFunctionCall)
                and left.name in ("fhirpath_text", "fhirpath_date", "fhirpath_scalar", "fhirpath_json")
                and len(left.args) == 2
            ):
                resource_arg = left.args[0]
                path_arg = left.args[1]
                if isinstance(path_arg, SQLLiteral) and isinstance(path_arg.value, str):
                    escaped_system = codesystem_url.replace("'", "''")
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
                    point_str = SQLCast(expression=left, target_type="VARCHAR")
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
                    if not low_is_null and interval.low is not None:
                        op_low = ">=" if interval.low_closed else ">"
                        conditions.append(SQLBinaryOp(operator=op_low, left=left, right=low_sql))
                    if not high_is_null and interval.high is not None:
                        op_high = "<=" if interval.high_closed else "<"
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
                args=[right, self._ensure_interval_varchar(left)],
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
                    else_clause=SQLBinaryOp(operator="=", left=lv, right=rv),
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
            result = SQLFunctionCall(name="NOT", args=[result])

        return result


    def _translate_union_op(self, operator, left, right, expr) -> SQLExpression:
        """Extracted from _translate_binary_expression."""
        left_is_rows = isinstance(left, (SQLSelect, SQLSubquery, SQLUnion, SQLExcept, SQLIntersect))
        right_is_rows = isinstance(right, (SQLSelect, SQLSubquery, SQLUnion, SQLExcept, SQLIntersect))

        # CQL §19.31: Interval union — use intervalUnion UDF which returns
        # null when intervals do not overlap or meet.
        # Null propagation for intervals: §19.31 says null → null.
        if not left_is_rows and not right_is_rows:
            left_is_interval = self._is_fhir_interval_expression(left)
            right_is_interval = self._is_fhir_interval_expression(right)
            if left_is_interval and right_is_interval:
                return SQLFunctionCall(name="intervalUnion", args=[left, right])
            if (left_is_interval or right_is_interval) and (isinstance(left, SQLNull) or isinstance(right, SQLNull)):
                return SQLNull()

        # CQL §20.29: List union — null is treated as empty list.
        # Return the non-null operand instead of propagating null.
        if not left_is_rows and not right_is_rows:
            if isinstance(left, SQLNull) and isinstance(right, SQLNull):
                return SQLArray([])
            if isinstance(left, SQLNull):
                return right
            if isinstance(right, SQLNull):
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

        left = _as_subquery(left)
        right = _as_subquery(right)

        # Case 1: Both operands are subqueries (from retrieves or query expressions)
        if isinstance(left, SQLSubquery) and isinstance(right, SQLSubquery):
            operands = [left, right]
            use_distinct = not self._check_union_disjointness(operands)
            return SQLUnion(operands=operands, distinct=use_distinct)

        # Case 2: One operand is SQLUnion, other is subquery - flatten
        if isinstance(left, SQLUnion) and isinstance(right, SQLSubquery):
            operands = left.operands + [right]
            use_distinct = not self._check_union_disjointness(operands)
            return SQLUnion(operands=operands, distinct=use_distinct)
        if isinstance(left, SQLSubquery) and isinstance(right, SQLUnion):
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

    def _translate_intersect_op(self, operator, left, right, expr) -> SQLExpression:
        """Extracted from _translate_binary_expression."""
        if self._is_list_operands(left, right, expr):
            return SQLFunctionCall(name="CQLListIntersectEq", args=[left, right])
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
        return SQLFunctionCall(name="CQLListIntersectEq", args=[left, right])

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
            if extra_condition_ast:
                extra_sql = self.translate(extra_condition_ast, boolean_context=True)
                return SQLBinaryOp(operator="AND", left=overlaps_result, right=extra_sql)
            return overlaps_result

        # Try to decompose interval overlaps to simple date comparisons
        decomposed = self._try_decompose_interval_overlaps(left, right, expr)
        if decomposed is not None:
            return decomposed

        return SQLFunctionCall(name="intervalOverlaps", args=[left, right])

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
            overlap_check = SQLFunctionCall(name="intervalOverlaps", args=[left, interval_expr])
            left_end = SQLFunctionCall(
                name="COALESCE",
                args=[
                    self._ensure_date_cast(self._truncate_to_precision(left_end_raw_bound, precision)),
                    SQLCast(expression=SQLLiteral(value="9999-12-31"), target_type="DATE"),
                ],
            )
            right_end = SQLFunctionCall(
                name="COALESCE",
                args=[
                    self._ensure_date_cast(self._truncate_to_precision(right_end_raw_bound, precision)),
                    SQLCast(expression=SQLLiteral(value="9999-12-31"), target_type="DATE"),
                ],
            )
            ends_after = SQLBinaryOp(operator=">", left=left_end, right=right_end)
            result = SQLBinaryOp(operator="AND", left=overlap_check, right=ends_after)
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
            overlap_check = SQLFunctionCall(name="intervalOverlaps", args=[left, interval_expr])
            left_start = self._ensure_date_cast(self._truncate_to_precision(left_start_raw, precision))
            right_start = self._ensure_date_cast(self._truncate_to_precision(right_start_raw, precision))
            starts_before = SQLBinaryOp(operator="<", left=left_start, right=right_start)
            result = SQLBinaryOp(operator="AND", left=overlap_check, right=starts_before)
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
                right_translated = self.translate(inner_expr, usage=ExprUsage.SCALAR)
                if self._is_fhir_interval_expression(right_translated) or isinstance(right_translated, SQLInterval):
                    right_translated = SQLFunctionCall(name="intervalEnd", args=[right_translated])
                left_truncated = self._truncate_to_precision(interval_end, precision_str)
                right_truncated = self._truncate_to_precision(right_translated, precision_str)
                return SQLBinaryOp(operator="=", left=left_truncated, right=right_truncated)
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
        def _rounded(operand: SQLExpression) -> SQLExpression:
            decimal_operand = SQLCast(
                expression=operand,
                target_type="DECIMAL(38,8)",
            )
            return SQLFunctionCall(
                name="system.round",
                args=[decimal_operand, SQLLiteral(value=precision)],
            )

        result: SQLExpression = SQLBinaryOp(
            operator="=",
            left=_rounded(left),
            right=_rounded(right),
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

        # Gap 12: Check if either operand is a code reference
        code_info = None
        resource_expr = None

        list_result = self._translate_list_equivalence(expr, is_negated)
        if list_result is not None:
            return list_result

        if self._is_list_operands(left, right, expr):
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
                return self.context.get_code(operand_ast.name)
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
            system = code_info.get("codesystem", code_info.get("system", ""))
            return (
                self.context.codesystems.get(system, system),
                code_info.get("code", ""),
            )

        def _codes_equivalent(left_info, right_info):
            left_codes = _code_entries(left_info)
            right_codes = _code_entries(right_info)
            if not left_codes or not right_codes:
                return False
            left_keys = {_code_key(code) for code in left_codes}
            return any(_code_key(code) in left_keys for code in right_codes)

        # QA-010: When both sides are compile-time code references,
        # compare directly instead of routing through the terminology translator.
        _left_code = _resolve_code_ref(expr.left)
        _right_code = _resolve_code_ref(expr.right)
        if _left_code and _right_code:
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

        string_result = self._translate_string_equivalence(left, right, expr, is_negated)
        if string_result is not None:
            return string_result

        # CQL §12.2: Quantity equivalence — convert units and compare values.
        left_is_qty = _is_quantity_expression(left) or self._is_cql_quantity_expr(expr.left)
        right_is_qty = _is_quantity_expression(right) or self._is_cql_quantity_expr(expr.right)
        if left_is_qty or right_is_qty:
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
        if operator.startswith("starts ") and " or " in operator:
            return self._translate_complex_interval_temporal(operator, left, right, "start")
        if operator.startswith("ends ") and " or " in operator:
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
                if isinstance(e, SQLLiteral) and isinstance(e.value, (int, float)) and not isinstance(e.value, bool):
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
        if sql_op in ("+", "-", "*", "/", "%"):
            def _cast_if_fhirpath(expr):
                if isinstance(expr, SQLFunctionCall) and expr.name in ('fhirpath_text', 'fhirpath_scalar'):
                    number_projection = self._fhirpath_number_projection(expr)
                    if number_projection is not None:
                        return number_projection
                    # Handle Quantity JSON objects by extracting $.value first
                    trimmed = SQLFunctionCall(name="LTRIM", args=[expr])
                    is_json = SQLFunctionCall(name="starts_with", args=[trimmed, SQLLiteral(value="{")])
                    json_value = SQLFunctionCall(name="json_extract_string", args=[expr, SQLLiteral(value="$.value")])
                    return SQLCast(
                        expression=SQLCase(
                            when_clauses=[(is_json, json_value)],
                            else_clause=expr,
                        ),
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

            # When one operand is a numeric literal and the other is an
            # untyped identifier (e.g., a lambda parameter from
            # intervalEnd() which returns VARCHAR), CAST the identifier to
            # INTEGER so DuckDB arithmetic works.
            if _is_numeric(right) and isinstance(left, SQLIdentifier):
                left = SQLCast(expression=left, target_type="INTEGER", try_cast=True)
            elif _is_numeric(left) and isinstance(right, SQLIdentifier):
                right = SQLCast(expression=right, target_type="INTEGER", try_cast=True)

            # When one side is numeric and the other is a subquery or other
            # non-numeric expression (e.g. SELECT MAX(fhirpath_text(...))),
            # cast the non-numeric side to DOUBLE so DuckDB arithmetic works.
            if _is_numeric(right) and not _is_numeric(left) and not isinstance(left, (SQLIdentifier, SQLCast)):
                if isinstance(left, SQLSubquery):
                    left = SQLCast(expression=left, target_type="DOUBLE", try_cast=True)
            elif _is_numeric(left) and not _is_numeric(right) and not isinstance(right, (SQLIdentifier, SQLCast)):
                if isinstance(right, SQLSubquery):
                    right = SQLCast(expression=right, target_type="DOUBLE", try_cast=True)

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
                    trimmed = SQLFunctionCall(name="LTRIM", args=[expr])
                    is_json = SQLFunctionCall(name="starts_with", args=[trimmed, SQLLiteral(value="{")])
                    json_value = SQLFunctionCall(name="json_extract_string", args=[expr, SQLLiteral(value="$.value")])
                    return SQLCast(
                        expression=SQLCase(
                            when_clauses=[(is_json, json_value)],
                            else_clause=expr,
                        ),
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

        # CQL §16.4: division by zero returns null — wrap the divisor with NULLIF
        if sql_op == "/":
            right = SQLFunctionCall(name="NULLIF", args=[right, SQLLiteral(value=0)])

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
            escaped_url = url_expr.value.replace("'", "''")
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
        if sql_op in ("=", "!=") and isinstance(left, SQLArray) and isinstance(right, SQLArray):
            left_types = {type(e.value).__name__ for e in left.elements if isinstance(e, SQLLiteral)}
            right_types = {type(e.value).__name__ for e in right.elements if isinstance(e, SQLLiteral)}
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
        return self._maybe_wrap_audit_comparison(result, operator, left, right)


    def _resolve_valueset_identifier(self, ident_name: str) -> Optional[str]:
        """Resolve a valueset identifier to its canonical URL."""
        # Check direct valueset registry
        if ident_name in self.context.valuesets:
            return self.context.valuesets[ident_name]
        # Check included libraries
        if hasattr(self.context, 'includes'):
            for lib_name, lib in self.context.includes.items():
                if hasattr(lib, 'valuesets') and ident_name in lib.valuesets:
                    return lib.valuesets[ident_name]
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

        if operator == "is null":
            operand = self.translate(expr.operand, boolean_context=False)
            return SQLUnaryOp(operator="IS NULL", operand=operand, prefix=False)

        if operator == "is not null":
            operand = self.translate(expr.operand, boolean_context=False)
            return SQLUnaryOp(operator="IS NOT NULL", operand=operand, prefix=False)

        if operator == "is true":
            operand = self.translate(expr.operand, boolean_context=True)
            return SQLFunctionCall(name="IsTrue", args=[operand])

        if operator == "is false":
            operand = self.translate(expr.operand, boolean_context=True)
            return SQLFunctionCall(name="IsFalse", args=[operand])

        if operator == "is not true":
            operand = self.translate(expr.operand, boolean_context=True)
            return SQLUnaryOp(
                operator="NOT",
                operand=SQLFunctionCall(name="IsTrue", args=[operand]),
                prefix=True,
            )

        if operator == "is not false":
            operand = self.translate(expr.operand, boolean_context=True)
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
            return SQLFunctionCall(name="predecessorOf", args=[operand])

        if operator == "successor of":
            return SQLFunctionCall(name="successorOf", args=[operand])

        # Singleton from operator - extract single element from list
        if operator == "singleton from":
            return self._apply_singleton_from(operand)

        # Default: pass through
        return SQLUnaryOp(operator=operator, operand=operand, prefix=True)
