"""Function reference translation: built-in CQL functions and aggregation."""
from __future__ import annotations

import json
import logging
import re as _re
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple, Union

from ...parser.ast_nodes import (
    AggregateExpression,
    AliasRef,
    AllExpression,
    AnyExpression,
    BinaryExpression,
    CaseExpression,
    CaseItem,
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
    Literal,
    MethodInvocation,
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
    UnaryExpression,
)
from ...translator.context import ExprUsage, RowShape, DefinitionMeta
from ...translator.function_inliner import ParameterPlaceholder
from ...translator.placeholder import RetrievePlaceholder
from ...translator.types import (
    PRECEDENCE,
    SQLAlias,
    SQLArray,
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
    SQLLambda2,
)
from ...translator.expressions._utils import (
    BINARY_OPERATOR_MAP,
    UNARY_OPERATOR_MAP,
    _coerce_query_rows_to_list,
    _is_list_returning_sql,
    _contains_sql_subquery,
    _ensure_scalar_body,
    escape_fhirpath_string_literal,
    _get_qicore_extension_fhirpath,
    _resolve_library_code_constant,
)
from ...translator.expressions._operators import (
    _ensure_parse_quantity,
    _infer_static_numeric_type,
    _is_patient_id_correlation,
    _is_quantity_expression,
    _is_ratio_expression,
    _static_numeric_value,
    _static_type_supports_string_conversion,
)
from ...errors import TranslationError

if TYPE_CHECKING:
    from ...translator.context import SQLTranslationContext

logger = logging.getLogger(__name__)

_UNCERTAIN_NUMERIC_HELPERS = {
    "cqlDurationBetween",
    "cqlDifferenceBetween",
    "cqlUncertainAdd",
    "cqlUncertainSubtract",
    "cqlUncertainMultiply",
}


def _casts_from_uncertain_numeric(expr: SQLExpression) -> bool:
    """Return true for scalar-or-interval helpers used in numeric contexts."""
    while isinstance(expr, SQLCast):
        expr = expr.expression
    if (
        isinstance(expr, SQLFunctionCall)
        and expr.name.upper() in ("TRUNC", "TRUNCATE", "ROUND", "FLOOR", "CEIL", "CEILING", "ABS")
        and expr.args
    ):
        return _casts_from_uncertain_numeric(expr.args[0])
    return isinstance(expr, SQLFunctionCall) and expr.name in _UNCERTAIN_NUMERIC_HELPERS


def _numeric_arg_for_uncertain_helper(expr: SQLExpression) -> SQLExpression:
    if _casts_from_uncertain_numeric(expr):
        return SQLCast(expression=expr, target_type="DOUBLE", try_cast=True)
    return expr


def _static_datetime_component_type(node: Any) -> Optional[str]:
    def _normalize_type_name(name: Optional[str]) -> Optional[str]:
        if name is None:
            return None
        return name.split(".")[-1]

    if isinstance(node, Literal):
        if isinstance(node.value, bool):
            return "Boolean"
        return _normalize_type_name(getattr(node, "type", None))
    if isinstance(node, Quantity):
        return "Quantity"
    if isinstance(node, DateTimeLiteral):
        return "Time" if str(node.value).startswith("T") else "DateTime"
    if isinstance(node, DateComponent):
        return "Decimal" if node.component.lower() == "timezoneoffset" else "Integer"
    if isinstance(node, UnaryExpression) and node.operator in {"+", "-"}:
        return _static_datetime_component_type(node.operand)
    if isinstance(node, UnaryExpression) and node.operator.lower() == "not":
        return "Boolean"
    if isinstance(node, BinaryExpression) and node.operator == "as":
        type_spec = getattr(node, "right", None)
        if isinstance(type_spec, NamedTypeSpecifier):
            return _normalize_type_name(type_spec.name)
    if isinstance(node, BinaryExpression):
        op_lower = node.operator.lower()
        if op_lower in {
            "=",
            "!=",
            "<>",
            "<",
            "<=",
            ">",
            ">=",
            "~",
            "!~",
            "and",
            "or",
            "xor",
            "implies",
            "in",
            "contains",
            "included in",
            "includes",
            "properly includes",
            "properly included in",
        }:
            return "Boolean"
        left_type = _static_datetime_component_type(node.left)
        right_type = _static_datetime_component_type(node.right)
        if left_type is None or right_type is None:
            return None
        if node.operator == "&" or (node.operator == "+" and left_type == right_type == "String"):
            return "String"
        if node.operator == "div" and left_type == right_type == "Integer":
            return "Integer"
        if node.operator == "mod" and left_type == right_type == "Integer":
            return "Integer"
        if node.operator in {"+", "-", "*"} and left_type == right_type == "Integer":
            return "Integer"
        if node.operator in {"+", "-", "*", "/", "^", "div", "mod"} and "Decimal" in {left_type, right_type}:
            return "Decimal"
    if isinstance(node, FunctionRef):
        function_type = {
            "tointeger": "Integer",
            "tolong": "Long",
            "todecimal": "Decimal",
            "tostring": "String",
            "toboolean": "Boolean",
            "todate": "Date",
            "todatetime": "DateTime",
            "totime": "Time",
            "toquantity": "Quantity",
            "toratio": "Ratio",
            "date": "Date",
            "datetime": "DateTime",
            "time": "Time",
        }.get(node.name.lower())
        return function_type
    return None


def _reject_non_integer_temporal_components(name: str, arg_nodes: list[Any]) -> None:
    if name == "Date":
        component_nodes = arg_nodes
    elif name == "DateTime":
        component_nodes = arg_nodes[:7]
    elif name == "Time" and len(arg_nodes) >= 2:
        component_nodes = arg_nodes[:4]
    else:
        return
    for node in component_nodes:
        static_type = _static_datetime_component_type(node)
        if static_type is not None and static_type != "Integer":
            raise ValueError(f"{name} constructor components must be Integer values")
    if name == "DateTime" and len(arg_nodes) > 7:
        static_type = _static_datetime_component_type(arg_nodes[7])
        if static_type is not None and static_type not in {"Integer", "Decimal"}:
            raise ValueError("DateTime timezoneOffset must be a Decimal value")

from ...translator.component_codes import get_code_to_column_mapping
from ...translator.fhirpath_builder import (
    build_coding_exists_expr,
    build_where_return_expr,
    FHIRPathBuilder,
)

class FunctionsMixin:
    """Mixin providing function reference, exists, and age translations."""

    def _translate_structural_traversal_arg(self, node: Any) -> SQLExpression:
        """Translate Children()/Descendants() inputs with static primitive tags."""
        if isinstance(node, TupleExpression):
            args: list[SQLExpression] = []
            for elem in node.elements:
                args.append(SQLLiteral(value=elem.name))
                args.append(self._translate_structural_traversal_value(elem.type))
            return SQLFunctionCall(name="json_object", args=args)
        return self.translate(node, usage=ExprUsage.SCALAR)

    def _translate_structural_traversal_value(self, node: Any) -> SQLExpression:
        if isinstance(node, TupleExpression):
            return self._translate_structural_traversal_arg(node)
        if isinstance(node, ListExpression):
            return SQLArray(
                elements=[
                    self._translate_structural_traversal_value(element)
                    for element in node.elements
                ]
            )
        static_type = self._static_structural_type_name(node)
        if static_type in {"Long", "Date", "DateTime", "Time"}:
            return SQLFunctionCall(
                name="json_object",
                args=[
                    SQLLiteral(value="__fhir4ds_cql_type"),
                    SQLLiteral(value=static_type),
                    SQLLiteral(value="value"),
                    self.translate(node, usage=ExprUsage.SCALAR),
                ],
            )
        return self.translate(node, usage=ExprUsage.SCALAR)

    @staticmethod
    def _is_list_typed_ast(node) -> bool:
        """Check if a CQL AST node is typed as a list (e.g., ``null as List<Any>``)."""
        from ...parser.ast_nodes import BinaryExpression
        # ``null as List<X>`` parses as BinaryExpression(operator='as', right=TypeSpecifier)
        if isinstance(node, BinaryExpression) and getattr(node, 'operator', '') == 'as':
            ts = getattr(node, 'right', None)
            if ts is not None:
                ts_str = str(ts).lower()
                if 'list' in ts_str:
                    return True
        return False

    @staticmethod
    def _type_spec_name(type_spec) -> Optional[str]:
        """Return a compact CQL type name from a parsed type specifier."""
        if type_spec is None:
            return None
        if hasattr(type_spec, "name"):
            return str(type_spec.name).split(".")[-1]
        if hasattr(type_spec, "element_type"):
            return FunctionsMixin._type_spec_name(type_spec.element_type)
        text = str(type_spec)
        for known in (
            "Boolean", "Integer", "Long", "Decimal", "Quantity", "String",
            "DateTime", "Date", "Time", "Code", "Concept", "Interval", "Tuple",
        ):
            if known.lower() in text.lower():
                return known
        return None

    def _static_list_element_types(self, node) -> Optional[set[str]]:
        """Infer static element types for simple list expressions and aliases.

        This intentionally stays conservative: unknown dynamic sources return
        None and remain runtime-checked by the existing SQL/helper surfaces.
        """
        from ...parser.ast_nodes import BinaryExpression as ASTBinaryExpression

        def _from_cql_type(cql_type: str | None) -> Optional[set[str]]:
            if not cql_type:
                return None
            text = str(cql_type)
            if text.startswith("List<") and text.endswith(">"):
                inner = text[5:-1].split(".")[-1]
                return {inner}
            return None

        def _function_return_type(func: FunctionRef) -> Optional[str]:
            name = (func.name or "").lower()
            conversion_returns = {
                "toboolean": "Boolean",
                "tointeger": "Integer",
                "tolong": "Long",
                "todecimal": "Decimal",
                "todate": "Date",
                "todatetime": "DateTime",
                "totime": "Time",
                "toquantity": "Quantity",
                "toconcept": "Concept",
                "tostring": "String",
                "quantitytostring": "String",
                "ratiotostring": "String",
                "date": "Date",
                "datetime": "DateTime",
                "time": "Time",
                "quantity": "Quantity",
            }
            if name in conversion_returns:
                return conversion_returns[name]
            if name.startswith("convertsto") or name in {"canconvertquantity"}:
                return "Boolean"
            scalar_returns = {
                "count": "Integer",
                "length": "Integer",
                "precision": "Integer",
                "abs": None,
                "ceiling": "Integer",
                "floor": "Integer",
                "round": "Decimal",
                "sqrt": "Decimal",
                "ln": "Decimal",
                "exp": "Decimal",
                "log": "Decimal",
                "power": "Decimal",
            }
            if name in scalar_returns:
                return scalar_returns[name]
            return None

        def _element_type(element) -> Optional[str]:
            if isinstance(element, Literal):
                if element.value is None:
                    return "Null"
                if element.type:
                    return str(element.type).split(".")[-1]
                if isinstance(element.value, bool):
                    return "Boolean"
                if isinstance(element.value, int):
                    return "Integer"
                if isinstance(element.value, float):
                    return "Decimal"
                if isinstance(element.value, str):
                    return "String"
                return None
            if isinstance(element, ListExpression):
                return "List"
            if isinstance(element, TupleExpression):
                return "Tuple"
            if isinstance(element, Interval):
                return "Interval"
            if isinstance(element, InstanceExpression):
                return str(element.type).split(".")[-1]
            if isinstance(element, Quantity):
                return "Quantity"
            if isinstance(element, TimeLiteral):
                return "Time"
            if isinstance(element, DateTimeLiteral):
                value = str(element.value)
                return "DateTime" if "T" in value else "Date"
            if isinstance(element, FunctionRef):
                return _function_return_type(element)
            if isinstance(element, ASTBinaryExpression) and getattr(element, "operator", "") == "as":
                right = getattr(element, "right", None)
                left = getattr(element, "left", None)
                target_name = self._type_spec_name(right)
                if isinstance(left, Literal) and left.value is None:
                    return target_name or "Null"
                if target_name == "Any":
                    return _element_type(left)
                return target_name or _element_type(left)
            return None

        if isinstance(node, Identifier):
            meta = self.context.definition_meta.get(node.name)
            inferred = _from_cql_type(str(getattr(meta, "cql_type", "") or ""))
            if inferred:
                return inferred
            symbol = self.context.lookup_symbol(node.name)
            symbol_expr = getattr(symbol, "ast_expr", None) if symbol else None
            if symbol_expr is not None and symbol_expr is not node:
                return self._static_list_element_types(symbol_expr)
            definition_ast = getattr(self.context, "_definition_cql_asts", {}).get(node.name)
            if definition_ast is not None and definition_ast is not node:
                return self._static_list_element_types(definition_ast)

        if isinstance(node, ASTBinaryExpression) and getattr(node, "operator", "") == "as":
            right = getattr(node, "right", None)
            if hasattr(right, "element_type"):
                element_name = self._type_spec_name(right.element_type)
                return {element_name} if element_name else None
            if isinstance(getattr(node, "left", None), Literal) and node.left.value is None:
                type_name = self._type_spec_name(right)
                return {type_name} if type_name else {"Null"}
            return self._static_list_element_types(getattr(node, "left", None))

        if isinstance(node, Query):
            sources = node.source if isinstance(node.source, list) else [node.source]
            alias_types: dict[str, Optional[set[str]]] = {}
            source_expr_types: list[Optional[set[str]]] = []
            for source in sources:
                if isinstance(source, QuerySource):
                    source_types = self._static_list_element_types(source.expression)
                    source_expr_types.append(source_types)
                    if source.alias:
                        alias_types[source.alias] = source_types

            if node.return_clause is not None:
                returned = node.return_clause.expression
                if isinstance(returned, AliasRef):
                    return alias_types.get(returned.name)
                if isinstance(returned, Identifier) and returned.name in alias_types:
                    return alias_types.get(returned.name)
                returned_type = _element_type(returned)
                return {returned_type} if returned_type else None

            if len(source_expr_types) == 1:
                return source_expr_types[0]
            return None

        if not isinstance(node, ListExpression):
            return None

        types: set[str] = set()
        for element in node.elements:
            element_type = _element_type(element)
            if element_type:
                types.add(element_type)
                continue
            return None
        return types

    def _validate_static_aggregate_argument(self, name: str, arg) -> None:
        """Fail fast for statically invalid CQL aggregate list element types."""
        lower = name.lower()
        element_types = self._static_list_element_types(arg)
        if not element_types:
            return

        concrete = {t for t in element_types if t not in {"Null", "Any", "None"}}
        if not concrete:
            return

        numeric = {"Integer", "Long", "Decimal"}
        numeric_or_quantity = numeric | {"Quantity"}

        if lower in {"alltrue", "anytrue", "allfalse", "anyfalse"}:
            if not concrete <= {"Boolean"}:
                raise TranslationError(f"{name} requires List<Boolean> source")
            return

        if lower == "geometricmean":
            if not concrete <= numeric:
                raise TranslationError(f"{name} requires List<Decimal> source")
            return

        if lower in {"avg", "median", "stddev", "stddevpop", "populationstddev", "variance", "populationvariance"}:
            if not (concrete <= numeric or concrete == {"Quantity"}):
                raise TranslationError(f"{name} requires List<Decimal> or List<Quantity> source")
            return

        if lower in {"sum", "product"}:
            if not (concrete <= numeric or concrete == {"Quantity"}):
                raise TranslationError(f"{name} requires numeric or Quantity list source")
            return

        if lower in {"min", "max"}:
            supported = numeric_or_quantity | {"Date", "DateTime", "Time", "String"}
            if not concrete <= supported:
                raise TranslationError(f"{name} does not support List<{', '.join(sorted(concrete))}> source")

    def _unwrap_list_source(self, arg):
        """Unwrap a potential list argument for aggregate handling.

        Returns the underlying expression if *arg* is a ``ListExpression``,
        a type-cast wrapping one (``{…} as List<T>``), a ``FunctionRef`` to
        ``flatten``, or a ``BinaryExpression`` with ``union``/``except``/
        ``intersect`` operator.  Returns ``None`` when *arg* is not a
        recognisable list source.
        """
        from ...parser.ast_nodes import ListExpression, FunctionRef as ASTFunctionRef, BinaryExpression as ASTBinaryExpression
        if isinstance(arg, ListExpression):
            return arg
        if self._is_list_typed_ast(arg):
            return getattr(arg, 'left', None)
        if isinstance(arg, ASTFunctionRef) and (arg.name or '').lower() in (
            'flatten', 'collapse', 'expand', 'children', 'descendants'
        ):
            return arg
        if isinstance(arg, ASTBinaryExpression) and getattr(arg, 'operator', '') in ('union', 'except', 'intersect'):
            return arg
        return None

    def _wrap_list_aggregate(
        self, agg_func: str, source_sql: SQLExpression
    ) -> Optional[SQLExpression]:
        """Wrap a LIST-translated SQL expression with an aggregate function.

        Returns an SQLSubquery containing ``SELECT agg_func(col) FROM (source)``,
        or ``None`` if the source shape cannot be wrapped.
        """
        inner_query = source_sql
        if isinstance(inner_query, SQLSubquery):
            inner_query = inner_query.query
        if isinstance(inner_query, SQLSelect):
            # Alias the first column so we can reference it in the aggregate
            if inner_query.columns:
                first_col = inner_query.columns[0]
                if not isinstance(first_col, SQLAlias):
                    inner_query.columns[0] = SQLAlias(expr=first_col, alias="_val")
                    col_ref = SQLIdentifier(name="_val")
                else:
                    col_ref = SQLIdentifier(name=first_col.alias)
            else:
                col_ref = SQLIdentifier(name="_val")

            # Inject patient correlation when the inner query sources from a
            # CTE/retrieve (which contains all patients' rows) and we are
            # inside a patient-scoped context. List-literal query sources are
            # SELECT subqueries without patient_id and must not be correlated.
            def _is_cte_backed(expr):
                if isinstance(expr, SQLAlias):
                    return _is_cte_backed(expr.expr)
                if isinstance(expr, SQLIdentifier) and expr.quoted:
                    return True
                if isinstance(expr, RetrievePlaceholder):
                    return True
                if isinstance(expr, SQLUnion):
                    return True
                if isinstance(expr, SQLSubquery):
                    inner = expr.query
                    if isinstance(inner, SQLSelect) and inner.from_clause:
                        return _is_cte_backed(inner.from_clause)
                    if isinstance(inner, SQLUnion):
                        return True
                return False

            _outer_pid = self.context.resource_alias or self.context.patient_alias or "_pt"
            _src_alias = None
            _fc = inner_query.from_clause
            if isinstance(_fc, SQLAlias):
                _src_alias = _fc.alias
            if _src_alias and _is_cte_backed(_fc):
                _corr = SQLBinaryOp(
                    operator="=",
                    left=SQLQualifiedIdentifier(parts=[_src_alias, "patient_id"]),
                    right=SQLQualifiedIdentifier(parts=[_outer_pid, "patient_id"]),
                )
                _existing_where = inner_query.where
                _new_where = (
                    SQLBinaryOp(operator="AND", left=_existing_where, right=_corr)
                    if _existing_where else _corr
                )
                inner_query = SQLSelect(
                    columns=inner_query.columns,
                    from_clause=inner_query.from_clause,
                    where=_new_where,
                    joins=inner_query.joins,
                    group_by=inner_query.group_by,
                    having=inner_query.having,
                    order_by=inner_query.order_by,
                    limit=inner_query.limit,
                    distinct=inner_query.distinct,
                )

            # For numeric-only aggregates, wrap the column in TRY_CAST(... AS
            # DOUBLE) to handle VARCHAR sources (e.g., cqlDurationBetween
            # returns VARCHAR). MIN/MAX are intentionally excluded because CQL
            # supports Date, DateTime, Time, and String signatures for them.
            agg_col = col_ref
            agg_key = agg_func.lower()
            if agg_key in {
                "sum", "avg", "median", "system.median",
                "stddev_samp", "stddev_pop", "var_samp", "var_pop",
                "system.stddev_samp", "system.stddev_pop",
                "system.var_samp", "system.var_pop",
                "system.product",
            }:
                agg_col = SQLCast(expression=col_ref, target_type="DOUBLE", try_cast=True)

            aggregate_expr: SQLExpression = SQLFunctionCall(name=agg_func, args=[agg_col])
            if agg_key == "bool_and":
                aggregate_expr = SQLFunctionCall(
                    name="COALESCE",
                    args=[aggregate_expr, SQLLiteral(value=True)],
                )
            elif agg_key == "bool_or":
                aggregate_expr = SQLFunctionCall(
                    name="COALESCE",
                    args=[aggregate_expr, SQLLiteral(value=False)],
                )
            elif agg_key == "mode":
                aggregate_expr = SQLFunctionCall(
                    name="CQLListMode",
                    args=[SQLFunctionCall(name="LIST", args=[col_ref])],
                )

            result = SQLSubquery(query=SQLSelect(
                columns=[aggregate_expr],
                from_clause=SQLAlias(
                    expr=SQLSubquery(query=inner_query),
                    alias="_agg",
                ),
            ))

            # In audit mode, for MIN/MAX, attach _audit_target using arg_min/arg_max
            # to identify the winning resource.
            if (getattr(self.context, 'audit_mode', False)
                    and agg_func in ('MIN', 'MAX')
                    and _src_alias):
                target_subq = self._build_minmax_audit_target(
                    inner_query, _src_alias, agg_func, col_ref,
                )
                if target_subq is not None:
                    result._audit_target = target_subq

            return result
        else:
            # Source translated to a list expression (e.g., list_transform)
            # rather than a row-producing SELECT.  Use DuckDB list aggregate
            # functions to avoid SQL aggregate leaks.
            if not _is_list_returning_sql(source_sql):
                if agg_func in ("bool_or", "bool_and"):
                    return source_sql
                # Not a list and not a SELECT — cannot aggregate safely.
                # Return None so the caller can fall back.
                return None
            _list_agg_map = {
                "SUM": "list_sum", "MIN": "list_min", "MAX": "list_max",
                "AVG": "list_avg", "COUNT": "list_count",
                "bool_or": "list_bool_or", "bool_and": "list_bool_and",
            }
            list_func = _list_agg_map.get(agg_func)
            if list_func:
                return SQLFunctionCall(name=list_func, args=[source_sql])
            # Fallback for less common aggregates: unnest into subquery
            return SQLSubquery(query=SQLSelect(
                columns=[SQLFunctionCall(name=agg_func, args=[SQLIdentifier(name="_val")])],
                from_clause=SQLAlias(
                    expr=SQLFunctionCall(name="unnest", args=[source_sql]),
                    alias="_val",
                ),
            ))

    @staticmethod
    def _is_quantity_sql_array(source_sql: SQLExpression) -> bool:
        """Return true when a translated list literal contains Quantity JSON."""
        return isinstance(source_sql, SQLArray) and any(
            isinstance(element, SQLFunctionCall) and element.name == "parse_quantity"
            for element in source_sql.elements
        )

    @staticmethod
    def _non_null_quantity_list(source_sql: SQLExpression) -> SQLExpression:
        return SQLFunctionCall(
            name="list_filter",
            args=[
                source_sql,
                SQLLambda(
                    param="__q",
                    body=SQLUnaryOp(
                        operator="IS NOT NULL",
                        operand=SQLIdentifier(name="__q"),
                        prefix=False,
                    ),
                ),
            ],
        )

    @staticmethod
    def _quantity_list_count(filtered: SQLExpression) -> SQLExpression:
        return SQLFunctionCall(name="len", args=[filtered])

    @staticmethod
    def _quantity_list_sum(filtered: SQLExpression) -> SQLExpression:
        return SQLFunctionCall(
            name="list_reduce",
            args=[
                filtered,
                SQLLambda2(
                    params=["__acc", "__item"],
                    body=SQLFunctionCall(
                        name="quantityAdd",
                        args=[
                            SQLIdentifier(name="__acc"),
                            SQLIdentifier(name="__item"),
                        ],
                    ),
                ),
            ],
        )

    @staticmethod
    def _quantity_list_minmax(filtered: SQLExpression, op: str) -> SQLExpression:
        comparison = SQLFunctionCall(
            name="quantityCompare",
            args=[
                SQLIdentifier(name="__item"),
                SQLIdentifier(name="__acc"),
                SQLLiteral(value=op),
            ],
        )
        return SQLFunctionCall(
            name="list_reduce",
            args=[
                filtered,
                SQLLambda2(
                    params=["__acc", "__item"],
                    body=SQLCase(
                        when_clauses=[
                            (comparison, SQLIdentifier(name="__item")),
                            (
                                SQLUnaryOp(
                                    operator="IS NULL",
                                    operand=comparison,
                                    prefix=False,
                                ),
                                SQLNull(),
                            ),
                        ],
                        else_clause=SQLIdentifier(name="__acc"),
                    ),
                ),
            ],
        )

    @staticmethod
    def _quantity_numeric_values(
        filtered: SQLExpression,
        unit_expr: SQLExpression,
    ) -> SQLExpression:
        converted = SQLFunctionCall(
            name="quantityConvert",
            args=[SQLIdentifier(name="__q"), unit_expr],
        )
        return SQLFunctionCall(
            name="list_transform",
            args=[
                filtered,
                SQLLambda(
                    param="__q",
                    body=SQLCast(
                        expression=SQLFunctionCall(
                            name="json_extract_string",
                            args=[converted, SQLLiteral(value="$.value")],
                        ),
                        target_type="DOUBLE",
                        try_cast=True,
                    ),
                ),
            ],
        )

    @staticmethod
    def _quantity_json(value_expr: SQLExpression, unit_expr: SQLExpression) -> SQLExpression:
        return SQLCast(
            expression=SQLFunctionCall(
                name="json_object",
                args=[
                    SQLLiteral(value="value"),
                    SQLCast(expression=value_expr, target_type="DOUBLE"),
                    SQLLiteral(value="unit"),
                    unit_expr,
                    SQLLiteral(value="code"),
                    unit_expr,
                    SQLLiteral(value="system"),
                    SQLLiteral(value="http://unitsofmeasure.org"),
                ],
            ),
            target_type="VARCHAR",
        )

    def _translate_quantity_list_aggregate(
        self,
        name: str,
        source_sql: SQLExpression,
    ) -> Optional[SQLExpression]:
        """Translate Quantity list aggregates through unit-aware helpers."""
        if not self._is_quantity_sql_array(source_sql):
            return None

        filtered = self._non_null_quantity_list(source_sql)
        count = self._quantity_list_count(filtered)
        empty = SQLBinaryOp(operator="=", left=count, right=SQLLiteral(value=0))
        sum_expr = self._quantity_list_sum(filtered)
        sum_is_null = SQLUnaryOp(operator="IS NULL", operand=sum_expr, prefix=False)
        lower = name.lower()

        if lower == "sum":
            return SQLCase(
                when_clauses=[(empty, SQLNull()), (sum_is_null, SQLNull())],
                else_clause=sum_expr,
            )

        if lower == "avg":
            divisor = SQLFunctionCall(
                name="ToQuantity",
                args=[SQLCast(expression=count, target_type="DOUBLE")],
            )
            avg_expr = SQLFunctionCall(
                name="quantityDivide",
                args=[sum_expr, divisor],
            )
            return SQLCase(
                when_clauses=[
                    (empty, SQLNull()),
                    (SQLUnaryOp(operator="IS NULL", operand=avg_expr, prefix=False), SQLNull()),
                ],
                else_clause=avg_expr,
            )

        if lower in ("min", "max"):
            op = "<" if lower == "min" else ">"
            result = self._quantity_list_minmax(filtered, op)
            return SQLCase(
                when_clauses=[
                    (empty, SQLNull()),
                    (SQLUnaryOp(operator="IS NULL", operand=result, prefix=False), SQLNull()),
                ],
                else_clause=result,
            )

        aggregate_name = {
            "median": "median",
            "mode": "mode",
            "stddev": "stddev_samp",
            "stddevpop": "stddev_pop",
            "populationstddev": "stddev_pop",
            "variance": "var_samp",
            "populationvariance": "var_pop",
            "product": "product",
        }.get(lower)
        if aggregate_name is None:
            return None

        unit_expr = SQLFunctionCall(name="quantityUnit", args=[sum_expr])
        numeric_values = self._quantity_numeric_values(filtered, unit_expr)
        aggregate = SQLFunctionCall(
            name="list_aggregate",
            args=[numeric_values, SQLLiteral(value=aggregate_name)],
        )
        return SQLCase(
            when_clauses=[
                (empty, SQLNull()),
                (sum_is_null, SQLNull()),
                (SQLUnaryOp(operator="IS NULL", operand=aggregate, prefix=False), SQLNull()),
            ],
            else_clause=self._quantity_json(aggregate, unit_expr),
        )

    def _build_minmax_audit_target(
        self,
        inner_query: "SQLSelect",
        src_alias: str,
        agg_func: str,
        col_ref: "SQLIdentifier",
    ) -> "Optional[SQLExpression]":
        """Build an audit target subquery for MIN/MAX using arg_min/arg_max.

        Returns a SQLSubquery that uses ``arg_min(_rid, _val)`` (for MIN) or
        ``arg_max(_rid, _val)`` (for MAX) to identify the winning resource.
        Returns None if the inner query's FROM clause doesn't reference a
        RESOURCE_ROWS CTE with a ``resource`` column.
        """
        # Detect CTE name from the inner query's FROM clause
        from_clause = inner_query.from_clause
        if isinstance(from_clause, SQLAlias):
            from_inner = from_clause.expr
        else:
            from_inner = from_clause
        cte_name = None
        if isinstance(from_inner, SQLIdentifier):
            cte_name = from_inner.name
        elif isinstance(from_inner, SQLRaw):
            cte_name = from_inner.raw_sql.strip().strip('"')
        if not cte_name:
            return None

        # Check definition_meta for resource column
        meta = self.context.definition_meta.get(cte_name)
        if not meta or not getattr(meta, 'has_resource', False):
            return None

        # Build a twin inner query with _rid column for resource ID
        from ._operators import _build_resource_id_expr
        res_col = SQLQualifiedIdentifier(parts=[src_alias, "resource"])
        rid_expr = _build_resource_id_expr(res_col)
        twin_cols = list(inner_query.columns or []) + [
            SQLAlias(expr=rid_expr, alias="_rid"),
        ]
        twin_inner = SQLSelect(
            columns=twin_cols,
            from_clause=inner_query.from_clause,
            where=inner_query.where,
            joins=inner_query.joins,
            group_by=inner_query.group_by,
            having=inner_query.having,
            order_by=inner_query.order_by,
            limit=inner_query.limit,
            distinct=inner_query.distinct,
        )

        # Use arg_min for MIN, arg_max for MAX
        arg_func = "arg_min" if agg_func == "MIN" else "arg_max"
        rid_ref = SQLIdentifier(name="_rid")
        return SQLSubquery(query=SQLSelect(
            columns=[SQLFunctionCall(name=arg_func, args=[rid_ref, col_ref])],
            from_clause=SQLAlias(
                expr=SQLSubquery(query=twin_inner),
                alias="_agg",
            ),
        ))

    @staticmethod
    def _extract_innermost_query(node: Any) -> Optional[Any]:
        """Walk through wrapper Query nodes to find the one with a real WHERE.

        CQL ``(from X where Y).prop`` parses as
        ``Property(source=Query(source=QuerySource(expr=Query(source=..., where=...))))``.
        This method traverses the wrapper layers and returns the innermost
        Query that actually carries a ``where`` clause or a named alias.
        """
        from ...parser.ast_nodes import Query as CQLQuery, QuerySource
        cur = node
        while isinstance(cur, CQLQuery):
            # If this query has a WHERE or named alias, it's the real one.
            if getattr(cur, 'where', None) is not None:
                return cur
            if cur.source and getattr(cur.source, 'alias', None):
                return cur
            # Otherwise, descend into the source's expression.
            if cur.source and isinstance(cur.source, QuerySource):
                inner = cur.source.expression
                if isinstance(inner, CQLQuery):
                    cur = inner
                    continue
            break
        return cur if isinstance(cur, CQLQuery) else None

    def _build_property_aggregate(
        self,
        agg_func: str,
        inner_sql: SQLExpression,
        prop_path: str,
    ) -> Optional[SQLExpression]:
        """Build ``SELECT agg(json_extract_string(resource, '$.prop')) FROM (inner)``."""
        inner_query = inner_sql
        if isinstance(inner_query, SQLSubquery):
            inner_query = inner_query.query
        if not isinstance(inner_query, SQLSelect):
            return None

        # Determine the source alias used in the inner query's FROM clause.
        _src_alias = None
        _fc = inner_query.from_clause
        if isinstance(_fc, SQLAlias):
            _src_alias = _fc.alias

        # Build the property extraction column.
        res_ref = (
            SQLQualifiedIdentifier(parts=[_src_alias, "resource"])
            if _src_alias
            else SQLIdentifier(name="resource")
        )
        prop_col = SQLFunctionCall(
            name="json_extract_string",
            args=[res_ref, SQLLiteral(value=f"$.{prop_path}")],
        )
        prop_select = SQLSelect(
            columns=[SQLAlias(expr=prop_col, alias="_val")],
            from_clause=inner_query.from_clause,
            where=inner_query.where,
            joins=inner_query.joins,
            group_by=inner_query.group_by,
            having=inner_query.having,
            order_by=inner_query.order_by,
            limit=inner_query.limit,
            distinct=inner_query.distinct,
        )

        # Inject patient correlation.
        _outer_pid = self.context.resource_alias or self.context.patient_alias or "_pt"
        if _src_alias:
            _corr = SQLBinaryOp(
                operator="=",
                left=SQLQualifiedIdentifier(parts=[_src_alias, "patient_id"]),
                right=SQLQualifiedIdentifier(parts=[_outer_pid, "patient_id"]),
            )
            existing_where = prop_select.where
            new_where = (
                SQLBinaryOp(operator="AND", left=existing_where, right=_corr)
                if existing_where else _corr
            )
            prop_select = SQLSelect(
                columns=prop_select.columns,
                from_clause=prop_select.from_clause,
                where=new_where,
                joins=prop_select.joins,
                group_by=prop_select.group_by,
                having=prop_select.having,
                order_by=prop_select.order_by,
                limit=prop_select.limit,
                distinct=prop_select.distinct,
            )

        col_ref = SQLIdentifier(name="_val")
        return SQLSubquery(query=SQLSelect(
            columns=[SQLFunctionCall(name=agg_func, args=[col_ref])],
            from_clause=SQLAlias(
                expr=SQLSubquery(query=prop_select),
                alias="_agg",
            ),
        ))

    def _translate_function_ref(self, func: FunctionRef, boolean_context: bool = False) -> SQLExpression:
        """Translate a CQL function call to SQL via the function registry."""
        from ...translator.function_registry import (
            SimpleRename, ParameterizedTranslation, PreTranslateStrategy,
        )
        name = func.name
        arity = len(func.arguments) if func.arguments else 0
        bare_lower = name.rsplit(".", 1)[-1].lower() if "." in name else name.lower()

        # Special handling for First/Last with Query args — must check BEFORE
        # translating args so we can use window functions for deterministic ordering
        if name.lower() in ("first", "last") and func.arguments:
            arg = func.arguments[0]
            if isinstance(arg, Query):
                if self._is_list_typed_ast(arg):
                    source = _coerce_query_rows_to_list(self.translate(arg, usage=ExprUsage.LIST))
                    return SQLFunctionCall(
                        name="LIST_EXTRACT",
                        args=[source, SQLLiteral(value=1 if name.lower() == "first" else -1)],
                    )
                direction = "ASC" if name.lower() == "first" else "DESC"
                return self._translate_first_last_with_window(arg, direction=direction)

        # Step 1: Check for pre-translate strategies (aggregates on Queries, maximum/minimum)
        function_registry = self._get_function_registry()
        pre_strategy = function_registry.get_pre_translate(name, arity)
        if pre_strategy is not None:
            result = pre_strategy.translator(func, self)
            if result is not None:
                return result
            # Fall through if pre-translate returns None (not applicable)

        if name.lower() == "children" and len(func.arguments) == 1:
            arg = self._translate_structural_traversal_arg(func.arguments[0])
            return SQLFunctionCall(name="cqlChildren", args=[arg])

        if name.lower() == "descendants" and len(func.arguments) == 1:
            arg = self._translate_structural_traversal_arg(func.arguments[0])
            return SQLFunctionCall(name="cqlDescendants", args=[arg])

        # Phase 3 (medterm4ds subsumption): CQL §20.4 ``Descendents(Code)`` —
        # when a closure table is loaded AND the argument statically resolves
        # to a code reference, emit a SQL list of (system, code) pairs pulled
        # from the closure table. When no closure table is loaded, fall
        # through to the existing identity macro (preserves the byte-identical
        # baseline — INV-1).
        if (
            name.lower() == "descendents"
            and len(func.arguments) == 1
            and getattr(self.context, "closure_table_loaded", False)
        ):
            list_result = self._translate_descendents_closure(func.arguments[0])
            if list_result is not None:
                return list_result

        # Step 2: Translate arguments. Literal/static definition aliases used
        # as conversion inputs should keep their scalar expression shape instead
        # of becoming patient-correlated CTE lookups.
        arg_nodes = list(func.arguments)
        if bare_lower == "combine" and arg_nodes:
            self._validate_static_string_list_operand(arg_nodes[0], "Combine")
            if len(arg_nodes) > 1:
                self._validate_static_string_operand(arg_nodes[1], "Combine")
        elif bare_lower == "concatenate":
            for arg_node in arg_nodes:
                self._validate_static_string_operand(arg_node, "Concatenate")
        elif bare_lower in {"lower", "upper"} and arg_nodes:
            self._validate_static_string_operand(arg_nodes[0], name)
        elif bare_lower in {
            "endswith",
            "startswith",
            "matches",
            "positionof",
            "lastpositionof",
            "split",
            "splitonmatches",
        }:
            for arg_node in arg_nodes[:2]:
                self._validate_static_string_operand(arg_node, name)
        elif bare_lower == "replacematches":
            for arg_node in arg_nodes[:3]:
                self._validate_static_string_operand(arg_node, name)
        elif bare_lower == "substring" and arg_nodes:
            self._validate_static_string_operand(arg_nodes[0], "Substring")
        elif bare_lower == "indexer" and arg_nodes:
            self._validate_static_string_operand(arg_nodes[0], "Indexer")
        elif bare_lower == "message":
            self._validate_message_signature_args(arg_nodes)
        elif bare_lower in {"skip", "take"} and len(arg_nodes) >= 2:
            count_type = self._infer_static_cql_type_for_logical_operand(arg_nodes[1])
            normalized_count_type = (count_type or "Any").split(".")[-1]
            if normalized_count_type not in {"Any", "Integer"}:
                raise TranslationError(
                    f"CQL {name} count argument must be Integer; got {count_type}"
                )
        if bare_lower in {"first", "last", "length", "tail", "skip", "take", "singletonfrom"} and arg_nodes:
            source_node = self._definition_ast_for_identifier(arg_nodes[0])
            if source_node is not None and self._is_list_typed_ast(source_node):
                arg_nodes[0] = source_node
        static_inline_functions = {
            "canconvertquantity",
            "coalesce",
            "convertquantity",
            "convertstoboolean",
            "convertstodate",
            "convertstodatetime",
            "convertstodecimal",
            "convertstointeger",
            "convertstolong",
            "convertstoquantity",
            "convertstoratio",
            "convertstostring",
            "convertstotime",
            "isfalse",
            "isnotnull",
            "isnull",
            "istrue",
            "toboolean",
            "toconcept",
            "todate",
            "todatetime",
            "todecimal",
            "tointeger",
            "tolong",
            "toquantity",
            "toratio",
            "tostring",
            "totime",
        }
        if name.lower() in static_inline_functions:
            for idx, arg_node in enumerate(arg_nodes):
                source_node = self._static_conversion_source_node(arg_node)
                if source_node is not None:
                    arg_nodes[idx] = source_node
        if name.lower() == "coalesce" and len(arg_nodes) == 1:
            source_node = self._definition_ast_for_identifier(arg_nodes[0])
            if isinstance(source_node, Query):
                arg_nodes[0] = source_node
        if name.lower() in {"istrue", "isfalse"} and len(arg_nodes) == 1:
            args = [self.translate(arg_nodes[0], usage=ExprUsage.SCALAR, boolean_context=True)]
        elif bare_lower in {"first", "last", "length", "tail", "skip", "take", "singletonfrom"} and arg_nodes and self._is_list_typed_ast(arg_nodes[0]):
            args = [_coerce_query_rows_to_list(self.translate(arg_nodes[0], usage=ExprUsage.LIST))]
            args.extend(self.translate(arg, usage=ExprUsage.SCALAR) for arg in arg_nodes[1:])
        else:
            _reject_non_integer_temporal_components(name, arg_nodes)
            args = [self.translate(arg, usage=ExprUsage.SCALAR) for arg in arg_nodes]

        # CQL ToString(Ratio) must use the round-trippable ratio text form,
        # not the implementation JSON used internally for Ratio values.
        if name.lower() in {"tostring", "convertstostring"} and len(args) == 1:
            static_source = self._static_structural_type_name(func.arguments[0])
            if name.lower() == "convertstostring":
                if not _static_type_supports_string_conversion(static_source):
                    return SQLLiteral(value=False)
            elif (
                static_source == "Quantity"
                or _is_quantity_expression(args[0])
                or self._is_cql_quantity_expr(func.arguments[0])
            ):
                return SQLFunctionCall(
                    name="QuantityToString",
                    args=[_ensure_parse_quantity(args[0])],
                )
            elif static_source == "Ratio" or _is_ratio_expression(args[0]):
                return SQLFunctionCall(name="RatioToString", args=args)
            elif not _static_type_supports_string_conversion(static_source):
                return SQLNull()

        # Step 2a: CQL Round — half-up semantics via custom macros
        # 1-arg → Round(x), 2-arg → RoundTo(x, precision)
        if name == "Round":
            if args:
                number_arg = self._fhirpath_number_projection(args[0])
                if number_arg is not None:
                    args = [number_arg, *args[1:]]
                else:
                    args = [_numeric_arg_for_uncertain_helper(args[0]), *args[1:]]
            if len(args) == 1:
                return SQLFunctionCall(name="Round", args=args)
            elif len(args) == 2:
                return SQLFunctionCall(name="RoundTo", args=args)

        if name == "Truncate" and len(args) == 1:
            number_arg = self._fhirpath_number_projection(args[0])
            if number_arg is not None:
                args = [number_arg]
            else:
                args = [_numeric_arg_for_uncertain_helper(args[0])]
            return SQLFunctionCall(name="Truncate", args=args)

        # Step 2a2: ToConcept — ensure argument is VARCHAR for the UDF
        # If argument is a struct_pack (legacy), wrap in to_json()
        # json_object() already returns VARCHAR, no wrapping needed
        if name == "ToConcept" and len(args) == 1:
            arg = args[0]
            if isinstance(arg, SQLArray):
                return SQLFunctionCall(
                    name="ToConceptFromList",
                    args=[
                        SQLArray(
                            elements=[
                                SQLCast(expression=item, target_type="VARCHAR")
                                for item in arg.elements
                            ]
                        )
                    ],
                )
            if isinstance(arg, SQLFunctionCall) and arg.name == "struct_pack":
                arg = SQLFunctionCall(name="to_json", args=[arg])
            return SQLFunctionCall(name="ToConcept", args=[arg])

        # Step 2b: Quantity-aware routing for numeric functions
        # CQL Abs/Negate on Quantity must use UDF, not SQL ABS() macro
        if name == "Abs" and len(args) == 1:
            raw_arg = func.arguments[0]
            # CQL §16 Abs: "If the result of taking the absolute value of the
            # input cannot be represented (e.g. Abs(minimum Integer)), the
            # result is null." Detect both literal-spelled forms
            # (-(-2147483648) / -(-9223372036854775808L)) and FunctionRef
            # forms (minimum Integer / minimum Long). Without this guard,
            # Abs(minimum Integer) lowers to TRY(system.abs(-2147483648)),
            # which DuckDB evaluates to 2147483648 (a valid BIGINT after
            # auto-promotion) instead of NULL.
            if (
                isinstance(raw_arg, UnaryExpression)
                and raw_arg.operator == "-"
                and isinstance(raw_arg.operand, Literal)
                and not isinstance(raw_arg.operand.value, bool)
                and (
                    (raw_arg.operand.type == "Integer" and raw_arg.operand.value == 2147483648)
                    or (raw_arg.operand.type == "Long" and raw_arg.operand.value == 9223372036854775808)
                )
            ):
                return SQLNull()
            if (
                isinstance(raw_arg, FunctionRef)
                and raw_arg.name == "minimum"
                and len(raw_arg.arguments) == 1
                and isinstance(raw_arg.arguments[0], (Identifier, NamedTypeSpecifier))
                and str(getattr(raw_arg.arguments[0], "name", "")).split(".")[-1].lower()
                in {"integer", "long"}
            ):
                return SQLNull()
            if _is_quantity_expression(args[0]) or self._is_cql_quantity_expr(func.arguments[0]):
                return SQLFunctionCall(name="quantityAbs", args=[_ensure_parse_quantity(args[0])])

        # Step 2c: CQL Length — polymorphic over String and List
        # CQL §20.16: Length on list returns count, null list → 0
        # CQL §17.5: Length on string returns char count, null string → null
        if name == "Length" and len(args) == 1:
            raw_arg = func.arguments[0]
            is_list = _is_list_returning_sql(args[0]) or self._is_list_typed_ast(raw_arg)
            if is_list:
                return SQLFunctionCall(
                    name="COALESCE",
                    args=[
                        SQLFunctionCall(name="array_length", args=args),
                        SQLLiteral(0),
                    ],
                )

        # Step 2c2: CQL Size — polymorphic over List and Interval
        # Size(list)     → number of elements, null list → 0  (CQL §12.4)
        # Size(interval) → interval width via interval_size UDF (CQL §19.18)
        if name == "Size" and len(args) == 1:
            raw_arg = func.arguments[0]
            if isinstance(raw_arg, Interval):
                return SQLFunctionCall(name="interval_size", args=args)
            # CQL-17 SKEPTIC QA-001: Statically-typed-aware dispatch.
            # The Interval AST check above only catches literal Interval[...]
            # operands. Operands such as `null as Interval<Integer>` parse to
            # a BinaryExpression(operator='as', ..., right=IntervalTypeSpecifier)
            # and must also route to interval_size, otherwise they fall through
            # to the List Size branch (COALESCE(array_length, 0)) which
            # silently returns 0 instead of null per CQL §19.18
            # ("If the argument is null, the result is null").
            operand_type = self._static_structural_type_name(raw_arg)
            if operand_type and operand_type.startswith("Interval<"):
                return SQLFunctionCall(name="interval_size", args=args)
            return SQLFunctionCall(
                name="COALESCE",
                args=[
                    SQLFunctionCall(name="array_length", args=args),
                    SQLLiteral(0),
                    ],
                )

        if name in {"HighBoundary", "LowBoundary"} and args:
            boundary_call = SQLFunctionCall(name=name, args=args)
            source_type = self._bare_cql_type_name(
                self._static_structural_type_name(func.arguments[0])
            )
            if source_type in {"Integer", "Long", "Decimal"}:
                return SQLCast(
                    expression=SQLCast(
                        expression=boundary_call,
                        target_type="VARCHAR",
                    ),
                    target_type="DOUBLE",
                    try_cast=True,
                )
            return boundary_call

        if name.lower() == "indexof" and len(args) == 2:
            if any(
                isinstance(arg, SQLNull) or (isinstance(arg, SQLLiteral) and arg.value is None)
                for arg in args
            ):
                return SQLNull()
            def _query_rows_as_index_list(source: SQLSelect) -> SQLExpression:
                if not source.columns:
                    return SQLArray([])
                first_col = source.columns[0]
                if isinstance(first_col, tuple):
                    first_expr = first_col[0]
                elif isinstance(first_col, SQLAlias):
                    first_expr = first_col.expr
                else:
                    first_expr = first_col
                value_alias = "__cql_indexof_value"
                projected = SQLSelect(
                    columns=[SQLAlias(expr=first_expr, alias=value_alias)],
                    from_clause=source.from_clause,
                    joins=source.joins,
                    where=source.where,
                    group_by=source.group_by,
                    having=source.having,
                    order_by=source.order_by,
                    limit=source.limit,
                    distinct=source.distinct,
                )
                value_ref = SQLQualifiedIdentifier(parts=["_cql_indexof_source", value_alias])
                return SQLSubquery(query=SQLSelect(
                    columns=[SQLFunctionCall(
                        name="COALESCE",
                        args=[
                            SQLFunctionCall(name="list", args=[value_ref]),
                            SQLArray(elements=[]),
                        ],
                    )],
                    from_clause=SQLAlias(
                        expr=SQLSubquery(query=projected),
                        alias="_cql_indexof_source",
                    ),
                ))

            index_args = list(args)
            source_arg = index_args[0]
            if isinstance(source_arg, SQLSubquery) and isinstance(source_arg.query, SQLSelect):
                index_args[0] = _query_rows_as_index_list(source_arg.query)
            elif isinstance(source_arg, SQLSelect):
                index_args[0] = _query_rows_as_index_list(source_arg)
            # Dispatch to the temporal-aware IndexOf variant when the list and
            # element are both temporal-typed (Date/DateTime/Time). Mirrors the
            # existing _list_contains_call dispatch for Contains/In. CQL §IndexOf
            # uses equality semantics, so timezone-normalized DateTimes and
            # precision-mismatched comparisons must reach cqlDateTimeEqual.
            list_arg = index_args[0]
            elem_arg = index_args[1]
            list_ast = func.arguments[0] if len(func.arguments) >= 1 else None
            elem_ast = func.arguments[1] if len(func.arguments) >= 2 else None
            if (
                hasattr(self, "_use_temporal_list_contains")
                and list_ast is not None
                and elem_ast is not None
                and self._use_temporal_list_contains(list_ast, elem_ast)
            ):
                return SQLFunctionCall(name="CQLIndexOfTemporal", args=[list_arg, elem_arg])
            return SQLFunctionCall(name="CQLIndexOf", args=index_args)

        # Step 3: Check registry for simple renames and parameterized translations
        strategy = function_registry.get(name, arity)
        if isinstance(strategy, SimpleRename):
            return SQLFunctionCall(name=strategy.sql_name, args=args)
        if isinstance(strategy, ParameterizedTranslation):
            return strategy.translator(args, self.context)

        # Step 4: Non-fluent library-qualified functions with fluent AST builders
        _NONFLUENT_TO_FLUENT = {"ToPrevalenceInterval": "prevalenceInterval"}
        bare_name = name.rsplit(".", 1)[-1] if "." in name else name
        fluent_name = _NONFLUENT_TO_FLUENT.get(bare_name)
        if fluent_name and func.arguments:
            fluent_translator = self.context.fluent_translator
            if fluent_translator:
                resource_arg = self.translate(func.arguments[0])
                extra_args = [self.translate(a) for a in func.arguments[1:]]
                arg_resource_type = self._infer_resource_type(func.arguments[0])
                try:
                    return fluent_translator.translate_fluent_call(
                        resource_expr=resource_arg,
                        function_name=fluent_name,
                        args=extra_args,
                        context=self.context,
                        resource_type=arg_resource_type,
                    )
                except NotImplementedError:
                    pass

        # Step 4.5: Check if this is a promoted function call (non-fluent style)
        # For non-fluent calls like FunctionName(alias, ...) where alias maps to a
        # promoted source CTE, use the function promotion CTE lookup instead of inlining.
        if func.arguments and isinstance(func.arguments[0], Identifier):
            _promoted = self._try_promoted_function_lookup(name, func.arguments[0])
            if _promoted is not None:
                return _promoted

        # Step 5: Try function inliner for library-defined functions
        inliner = self.context.function_inliner
        if inliner:
            expanded_cql = inliner.expand_function(name, None, func.arguments)
            if expanded_cql is not None:
                return self.translate(expanded_cql)

        # Step 6: Collapse/Expand (need access to both raw CQL and translated args)
        if name.lower() == "collapse" and args:
            return self._translate_collapse(func, args)
        if name.lower() == "expand" and func.arguments:
            result = self._translate_expand(func)
            if result is not None:
                return result

        # Step 6.5: FHIRCommon ext(element, url) → fhirpath_text(element, "extension.where(url='URL')")
        if bare_name == "ext" and len(args) == 2:
            url_arg = args[1]
            url_val = getattr(url_arg, 'value', None) if hasattr(url_arg, 'value') else None
            if url_val and isinstance(url_val, str):
                escaped_url = escape_fhirpath_string_literal(url_val)
                fhirpath_expr = f"extension.where(url='{escaped_url}')"
                return SQLFunctionCall(
                    name="fhirpath_text",
                    args=[args[0], SQLLiteral(fhirpath_expr)],
                )

        # Step 6.6: Combine with separator → CombineSep macro
        # DuckDB doesn't support macro overloading, so 2-arg Combine needs
        # to use the CombineSep macro instead.
        if bare_name == "Combine" and args:
            def _query_rows_as_list(source: SQLSelect) -> SQLExpression:
                if not source.columns:
                    return SQLNull()
                first_col = source.columns[0]
                if isinstance(first_col, tuple):
                    first_expr = first_col[0]
                elif isinstance(first_col, SQLAlias):
                    first_expr = first_col.expr
                else:
                    first_expr = first_col
                value_alias = "__cql_combine_value"
                projected = SQLSelect(
                    columns=[SQLAlias(expr=first_expr, alias=value_alias)],
                    from_clause=source.from_clause,
                    joins=source.joins,
                    where=source.where,
                    group_by=source.group_by,
                    having=source.having,
                    order_by=source.order_by,
                    limit=source.limit,
                    distinct=source.distinct,
                )
                value_ref = SQLQualifiedIdentifier(parts=["_cql_combine_source", value_alias])
                return SQLSubquery(query=SQLSelect(
                    columns=[SQLFunctionCall(name="list", args=[value_ref])],
                    from_clause=SQLAlias(
                        expr=SQLSubquery(query=projected),
                        alias="_cql_combine_source",
                    ),
                ))

            combine_args = list(args)
            source_arg = combine_args[0]
            if isinstance(source_arg, SQLSubquery) and isinstance(source_arg.query, SQLSelect):
                combine_args[0] = _query_rows_as_list(source_arg.query)
            elif isinstance(source_arg, SQLSelect):
                combine_args[0] = _query_rows_as_list(source_arg)
            if len(combine_args) == 2:
                return SQLFunctionCall(name="CombineSep", args=combine_args)
            if len(combine_args) == 1:
                return SQLFunctionCall(name="Combine", args=combine_args)

        # Step 7: Fallback — pass through as function call
        _inlining_lib = getattr(self.context, '_current_inlining_library', None)
        if _inlining_lib is None:
            msg = (
                f"Unknown CQL function '{name}' passed through to SQL verbatim. "
                "This will likely cause a DuckDB error at execution time. "
                "Check that the function name is spelled correctly and that all "
                "required library includes are present."
            )
            logger.debug(msg)
        else:
            logger.debug("Function '%s' from inlined library '%s' passed through to SQL", name, _inlining_lib)
        return SQLFunctionCall(name=name, args=args)

    # ------------------------------------------------------------------
    # Phase 3 (medterm4ds subsumption): closure-aware Descendents(Code).
    # ------------------------------------------------------------------
    def _translate_descendents_closure(self, code_arg_node) -> Optional[SQLExpression]:
        """Emit a SQL list literal of descendant (system, code) pairs.

        Returns ``None`` when ``code_arg_node`` does not statically resolve
        to a code reference (caller falls back to the identity macro).

        The returned SQL selects from ``terminology_closure`` and shapes the
        output as a list of JSON structs so it composes with the rest of the
        CQL ``Code`` / ``Concept`` machinery. Reflexive rows (the seed itself
        being a descendant of itself) are inserted by the closure builder, so
        the seed code is always present in the result set.
        """
        from ...translator.expressions._operators import (
            _operand_is_type_specifier,
        )

        if _operand_is_type_specifier(code_arg_node):
            return None

        # Reuse the inline code-ref resolver from _operators.
        code_info = self._resolve_code_ref_inline(code_arg_node)
        if not code_info:
            return None
        entries = self._code_entries_static(code_info)
        if not entries:
            return None

        from ...duckdb.udf.system_resolver import SystemResolver
        from ..types import SQLRaw

        # Build a UNION ALL of SELECTs across every seed code (Concept fan-out).
        # Each branch returns descendant (system, code) pairs from the closure
        # table; the outer query wraps them into a JSON list.
        parts: list[str] = []
        for entry in entries:
            sys_url = entry.get("codesystem", "") or entry.get("system", "")
            sys_n = SystemResolver.normalize(sys_url) or sys_url
            code = entry.get("code", "")
            # Use SQLLiteral.to_sql() for proper single-quote escaping (matches
            # the pattern in _translate_code_is_op). Defense-in-depth: avoids
            # the fragile manual chr(39)+chr(39) f-string pattern.
            sys_sql = SQLLiteral(value=sys_n).to_sql()
            code_sql = SQLLiteral(value=code).to_sql()
            parts.append(
                "SELECT _tc.descendant_system AS system, _tc.descendant_code AS code "
                "FROM terminology_closure _tc "
                f"WHERE _tc.ancestor_system = {sys_sql} "
                f"AND _tc.ancestor_code = {code_sql}"
            )
        union = " UNION ALL ".join(parts)
        # Wrap into a list of structs to match the CQL ``list<Code>`` shape.
        sql = (
            "(SELECT list(struct_pack(system := _d.system, code := _d.code)) "
            f"FROM ({union}) _d)"
        )
        return SQLRaw(raw_sql=sql)

    # ── Aggregate pre-translate strategy ──────────────────────────────────
    def _translate_aggregate_pre(self, func: FunctionRef, translator) -> Optional[SQLExpression]:
        """Pre-translate strategy for CQL aggregate functions on Query sources.

        Returns a SQL expression if the aggregate applies to a Query/FunctionRef/
        Property-on-Query, or None to fall through to standard arg translation.
        """
        _CQL_AGG_TO_SQL = {
            "anytrue": "bool_or",
            "alltrue": "bool_and",
            "anyfalse": "bool_and",   # AnyFalse = NOT AllTrue → uses bool_and with NOT
            "allfalse": "bool_or",    # AllFalse = NOT AnyTrue → uses bool_or with NOT
            "min": "MIN",
            "max": "MAX",
            "sum": "SUM",
            "avg": "AVG",
            "count": "COUNT",
            "median": "system.median",
            "mode": "MODE",
            "stddev": "system.stddev_samp",
            "stddevpop": "system.stddev_pop",
            "variance": "system.var_samp",
            "populationstddev": "system.stddev_pop",
            "populationvariance": "system.var_pop",
            "product": "system.product",
        }
        name = func.name
        if not func.arguments:
            return None
        from ...parser.ast_nodes import Query as CQLQuery, ListExpression, Retrieve, DistinctExpression
        arg = func.arguments[0]
        self._validate_static_aggregate_argument(name, arg)

        if name.lower() == "geometricmean":
            usage = ExprUsage.LIST if isinstance(arg, (CQLQuery, FunctionRef)) else ExprUsage.SCALAR
            source_sql = self.translate(arg, usage=usage)
            if isinstance(source_sql, (SQLSelect, SQLSubquery)):
                source_sql = _coerce_query_rows_to_list(source_sql)
            if isinstance(source_sql, SQLArray) or _is_list_returning_sql(source_sql):
                return SQLFunctionCall(name="GeometricMean", args=[source_sql])

        agg_func = _CQL_AGG_TO_SQL.get(name.lower())
        if agg_func is None:
            return None
        # CQL §20.3-20.4: AllFalse/AnyFalse negate their base aggregate
        _negate_result = name.lower() in ("allfalse", "anyfalse")

        def _maybe_negate(expr: SQLExpression) -> SQLExpression:
            """Wrap with NOT for AllFalse/AnyFalse (CQL §20.3-20.4)."""
            if _negate_result:
                return SQLUnaryOp(operator="NOT", operand=expr)
            return expr

        # Named scalar list definitions keep their CQL list type in metadata,
        # but translating the identifier directly in aggregate context produces
        # a scalar CTE lookup. Inline literal Quantity lists here so the
        # unit-aware aggregate path is preserved.
        if isinstance(arg, Identifier):
            symbol = self.context.lookup_symbol(arg.name)
            symbol_expr = getattr(symbol, "ast_expr", None) if symbol else None
            if (
                symbol_expr is not None
                and (
                    _is_list_returning_sql(symbol_expr)
                    or (
                        isinstance(symbol_expr, SQLQualifiedIdentifier)
                        and len(symbol_expr.parts) == 2
                        and symbol_expr.parts[1] == "__acc"
                    )
                )
            ):
                source_sql = self.translate(arg, usage=ExprUsage.SCALAR)
                if name.lower() == "count":
                    filtered = SQLFunctionCall(
                        name="list_filter",
                        args=[source_sql, SQLLambda(param="_v", body=SQLUnaryOp(
                            operator="IS NOT NULL",
                            operand=SQLIdentifier(name="_v"),
                            prefix=False,
                        ))],
                    )
                    return SQLFunctionCall(name="len", args=[filtered])
                list_func = {
                    "min": "list_min",
                    "max": "list_max",
                    "sum": "list_sum",
                    "avg": "list_avg",
                }.get(name.lower())
                if list_func is not None:
                    return SQLFunctionCall(name=list_func, args=[source_sql])

            meta = self.context.definition_meta.get(arg.name)
            cql_type = str(getattr(meta, "cql_type", "") or "")
            if cql_type == "List<Quantity>":
                definition_ast = getattr(self.context, "_definition_cql_asts", {}).get(arg.name)
                if definition_ast is not None:
                    source_sql = self.translate(definition_ast, usage=ExprUsage.SCALAR)
                    quantity_result = self._translate_quantity_list_aggregate(name, source_sql)
                    if quantity_result is not None:
                        return quantity_result

        # Retrieve sources (e.g. Count([Encounter])) need a correlated subquery
        # because the Retrieve translates to a RetrievePlaceholder that Phase 3
        # resolves to a CTE reference.  _wrap_list_aggregate cannot handle
        # placeholders, so we build the subquery directly.
        if isinstance(arg, Retrieve):
            placeholder = self.translate(arg, usage=ExprUsage.LIST)
            agg_col = (
                SQLFunctionCall(name=agg_func, args=[SQLIdentifier(name="*")])
                if agg_func == "COUNT"
                else SQLFunctionCall(name=agg_func, args=[SQLQualifiedIdentifier(parts=["_agg_src", "resource"])])
            )
            _outer_pid = self.context.resource_alias or self.context.patient_alias or "_pt"
            correlated = SQLSubquery(query=SQLSelect(
                columns=[agg_col],
                from_clause=SQLAlias(expr=placeholder, alias="_agg_src"),
                where=SQLBinaryOp(
                    operator="=",
                    left=SQLQualifiedIdentifier(parts=["_agg_src", "patient_id"]),
                    right=SQLQualifiedIdentifier(parts=[_outer_pid, "patient_id"]),
                ),
            ))
            return _maybe_negate(correlated)

        # Aggregate on distinct(query) — e.g., Count(distinct(query)) (CMS117).
        # Translate the inner query and wrap with COUNT(DISTINCT col) instead of
        # letting DistinctExpression produce list_distinct(LIST(...)) which puts
        # an aggregate inside WHERE clauses and breaks DuckDB.
        if isinstance(arg, DistinctExpression) and isinstance(arg.source, CQLQuery):
            source_sql = self.translate(arg.source, usage=ExprUsage.LIST)
            result = self._wrap_list_aggregate(agg_func, source_sql)
            if result is not None:
                # Inject DISTINCT into the aggregate function
                if isinstance(result, SQLSubquery) and isinstance(result.query, SQLSelect):
                    for i, col in enumerate(result.query.columns):
                        if isinstance(col, SQLFunctionCall) and col.name == agg_func:
                            result.query.columns[i] = SQLFunctionCall(
                                name=col.name, args=col.args, distinct=True
                            )
                return _maybe_negate(result)

        # Aggregate on distinct(list literal) — e.g., Count(distinct {1,1,2,3}).
        # Use scalar list_distinct + len instead of SQL COUNT aggregate to avoid
        # missing GROUP BY errors.
        if isinstance(arg, DistinctExpression) and isinstance(arg.source, ListExpression):
            source_sql = self.translate(arg.source, usage=ExprUsage.SCALAR)
            if isinstance(source_sql, SQLArray):
                distinct_list = SQLFunctionCall(name="list_distinct", args=[source_sql])
                if name.lower() == "count":
                    filtered = SQLFunctionCall(
                        name="list_filter",
                        args=[distinct_list, SQLLambda(param="_v", body=SQLUnaryOp(
                            operator="IS NOT NULL",
                            operand=SQLIdentifier(name="_v"),
                            prefix=False,
                        ))],
                    )
                    return SQLFunctionCall(name="len", args=[filtered])
                # For other aggregates (Sum, Min, Max, etc.) on distinct list literals
                _list_agg_fn = {
                    "sum": "list_sum", "min": "list_min", "max": "list_max",
                    "avg": "list_avg",
                }.get(name.lower())
                if _list_agg_fn:
                    return SQLFunctionCall(name=_list_agg_fn, args=[distinct_list])

        # Aggregate on distinct(union/except/intersect) — Count(distinct (X union Y)).
        from ...parser.ast_nodes import BinaryExpression as _ASTBinExpr
        if isinstance(arg, DistinctExpression) and isinstance(arg.source, _ASTBinExpr):
            if getattr(arg.source, 'operator', '') in ('union', 'except', 'intersect'):
                source_sql = self.translate(arg.source, usage=ExprUsage.SCALAR)
                if _is_list_returning_sql(source_sql):
                    distinct_list = SQLFunctionCall(name="list_distinct", args=[source_sql])
                    if name.lower() == "count":
                        filtered = SQLFunctionCall(
                            name="list_filter",
                            args=[distinct_list, SQLLambda(param="_v", body=SQLUnaryOp(
                                operator="IS NOT NULL",
                                operand=SQLIdentifier(name="_v"),
                                prefix=False,
                            ))],
                        )
                        return SQLFunctionCall(name="len", args=[filtered])
                    _list_agg_fn = {
                        "sum": "list_sum", "min": "list_min", "max": "list_max",
                        "avg": "list_avg",
                    }.get(name.lower())
                    if _list_agg_fn:
                        return SQLFunctionCall(name=_list_agg_fn, args=[distinct_list])

        if isinstance(arg, CQLQuery):
            source_sql = self.translate(arg, usage=ExprUsage.LIST)
            result = self._wrap_list_aggregate(agg_func, source_sql)
            if result is not None:
                return _maybe_negate(result)
        # FunctionRef that expands to a Query
        if isinstance(arg, FunctionRef):
            source_sql = self.translate(arg, usage=ExprUsage.LIST)
            result = self._wrap_list_aggregate(agg_func, source_sql)
            if result is not None:
                return _maybe_negate(result)
        # Property-on-Query: Min((from X where Y).prop)
        if (
            name.lower() in ("min", "max", "sum", "avg", "count")
            and self._arg_involves_query(arg)
            and isinstance(arg, Property)
        ):
            inner_query_node = self._extract_innermost_query(arg.source)
            if inner_query_node is not None:
                inner_sql = self.translate(inner_query_node, usage=ExprUsage.LIST)
                result = self._build_property_aggregate(agg_func, inner_sql, arg.path)
                if result is not None:
                    return result
            scalar = self.translate(arg, usage=ExprUsage.SCALAR)
            return SQLSubquery(query=SQLSelect(
                columns=[SQLFunctionCall(name=agg_func, args=[scalar])],
            ))
        # AnyTrue/AllTrue/AnyFalse/AllFalse with non-query source (list literals)
        # CQL §20.1-20.4: these aggregate boolean lists into a single boolean.
        _BOOL_AGG_UDF = {
            "alltrue": "logicalAllTrue",
            "anytrue": "logicalAnyTrue",
            "allfalse": "logicalAllFalse",
            "anyfalse": "logicalAnyFalse",
        }
        if name.lower() in _BOOL_AGG_UDF:
            scalar = self.translate(arg, usage=ExprUsage.SCALAR)
            return SQLFunctionCall(name=_BOOL_AGG_UDF[name.lower()], args=[scalar])
        # Min/Max on list literals (including type-cast lists — CQL §20.11-20.12)
        if name.lower() in ("min", "max"):
            _list_src = self._unwrap_list_source(arg)
            if _list_src is not None:
                source_sql = self.translate(_list_src, usage=ExprUsage.SCALAR)
                if isinstance(source_sql, SQLArray) or _is_list_returning_sql(source_sql):
                    quantity_result = self._translate_quantity_list_aggregate(name, source_sql)
                    if quantity_result is not None:
                        return quantity_result
                    list_func = "list_min" if name.lower() == "min" else "list_max"
                    return SQLFunctionCall(name=list_func, args=[source_sql])

        # Count/Sum/Avg/StdDev/Variance/Product on list sources — use DuckDB list functions
        _list_src = self._unwrap_list_source(arg)
        if _list_src is not None:
            source_sql = self.translate(_list_src, usage=ExprUsage.SCALAR)
            # JSON-returning list functions (collapse_intervals, expand) need json_array_length
            _JSON_LIST_FUNCS = {"collapse_intervals", "expand"}
            _is_json_list = isinstance(source_sql, SQLFunctionCall) and source_sql.name in _JSON_LIST_FUNCS
            if _is_json_list:
                if name.lower() == "count":
                    return SQLFunctionCall(name="json_array_length", args=[source_sql])
                # Other aggregates on JSON interval lists are not meaningful
                return None
            if isinstance(source_sql, SQLArray) or _is_list_returning_sql(source_sql):
                quantity_result = self._translate_quantity_list_aggregate(name, source_sql)
                if quantity_result is not None:
                    return quantity_result
                if name.lower() == "count":
                    # CQL §20.5: Count returns number of non-null elements
                    filtered = SQLFunctionCall(
                        name="list_filter",
                        args=[source_sql, SQLLambda(param="_v", body=SQLUnaryOp(
                            operator="IS NOT NULL",
                            operand=SQLIdentifier(name="_v"),
                            prefix=False,
                        ))],
                    )
                    return SQLFunctionCall(name="len", args=[filtered])
                _list_agg = {
                    "sum": "sum", "avg": "avg", "median": "median",
                    "mode": "mode", "stddev": "stddev_samp",
                    "stddevpop": "stddev_pop", "populationstddev": "stddev_pop",
                    "variance": "var_samp", "populationvariance": "var_pop",
                    "product": "product",
                }.get(name.lower())
                if _list_agg:
                    # Mode works on any type; numeric aggregates need DOUBLE cast
                    if _list_agg == "mode":
                        return SQLFunctionCall(name="CQLListMode", args=[source_sql])
                    cast_source = SQLFunctionCall(
                        name="list_transform",
                        args=[source_sql, SQLLambda(param="_v", body=SQLCast(
                            expression=SQLIdentifier(name="_v"),
                            target_type="DOUBLE",
                            try_cast=True,
                        ))],
                    )
                    return SQLFunctionCall(
                        name="list_aggregate",
                        args=[cast_source, SQLLiteral(value=_list_agg)],
                    )

        return None  # Fall through to standard translation

    # ── Parameterized function handlers ───────────────────────────────────

    def _translate_coalesce(self, args: list) -> SQLExpression:
        """Translate CQL Coalesce with type compatibility handling.

        CQL §22.6: Coalesce returns the first non-null argument.
        When called with a single list argument, returns the first non-null element.
        """
        def _coalesce_query_list(source: SQLSelect) -> SQLSubquery:
            if not source.columns:
                return SQLSubquery(query=SQLSelect(columns=[SQLNull()], limit=1))
            first_col = source.columns[0]
            if isinstance(first_col, tuple):
                first_expr = first_col[0]
            elif isinstance(first_col, SQLAlias):
                first_expr = first_col.expr
            else:
                first_expr = first_col
            value_alias = "__cql_coalesce_value"
            projected = SQLSelect(
                columns=[SQLAlias(expr=first_expr, alias=value_alias)],
                from_clause=source.from_clause,
                joins=source.joins,
                where=source.where,
                group_by=source.group_by,
                having=source.having,
                order_by=source.order_by,
                limit=source.limit,
                distinct=source.distinct,
            )
            value_ref = SQLQualifiedIdentifier(parts=["_cql_coalesce_source", value_alias])
            return SQLSubquery(query=SQLSelect(
                columns=[value_ref],
                from_clause=SQLAlias(
                    expr=SQLSubquery(query=projected),
                    alias="_cql_coalesce_source",
                ),
                where=SQLUnaryOp(operator="IS NOT NULL", operand=value_ref, prefix=False),
                limit=1,
            ))

        # Single list argument: reduce to first non-null element
        if len(args) == 1 and isinstance(args[0], SQLArray):
            # Expand list elements into COALESCE arguments
            args = args[0].elements
        elif len(args) == 1 and _is_list_returning_sql(args[0]):
            return SQLFunctionCall(name="Coalesce", args=args)
        elif len(args) == 1 and isinstance(args[0], SQLSubquery) and isinstance(args[0].query, SQLSelect):
            return _coalesce_query_list(args[0].query)
        elif len(args) == 1 and isinstance(args[0], SQLSelect):
            return _coalesce_query_list(args[0])
        elif len(args) < 2 or len(args) > 5:
            raise TranslationError(
                "Coalesce scalar overload requires 2 to 5 arguments; "
                "use Coalesce({ ... }) for list input"
            )

        # Empty argument list → null
        if not args:
            return SQLLiteral(value=None)

        # Always cast fhirpath_date() (returns DATE) to VARCHAR for type
        # compatibility — CQL datetime literals are now VARCHAR ISO 8601 strings.
        # This avoids "Cannot mix VARCHAR and DATE in COALESCE" errors.
        def _needs_varchar_cast(a):
            if isinstance(a, SQLFunctionCall):
                fn = (a.name or "").lower()
                if fn == "fhirpath_date":
                    return True
            if isinstance(a, SQLCast) and a.target_type == "DATE":
                return True
            return False

        if any(_needs_varchar_cast(a) for a in args):
            args = [
                SQLCast(expression=a, target_type="VARCHAR") if _needs_varchar_cast(a) else a
                for a in args
            ]

        def _is_boolean_expr(a):
            if isinstance(a, SQLLiteral) and isinstance(a.value, bool):
                return True
            if isinstance(a, SQLFunctionCall) and a.name in ("fhirpath_bool", "IsTrue", "IsFalse"):
                return True
            if isinstance(a, SQLBinaryOp) and a.operator in {"=", "!=", "<>", "<", "<=", ">", ">=", "AND", "OR", "XOR"}:
                return True
            return False

        if any(_is_boolean_expr(a) for a in args):
            def _cast_to_boolean(a):
                if isinstance(a, SQLFunctionCall) and a.name in ("fhirpath_text", "fhirpath_scalar"):
                    return SQLFunctionCall(name="fhirpath_bool", args=a.args)
                return a
            args = [_cast_to_boolean(a) for a in args]

        def _is_numeric_expr(a):
            if isinstance(a, SQLFunctionCall) and (a.name or "").upper() == "TRY" and a.args:
                return _is_numeric_expr(a.args[0])
            if isinstance(a, SQLCast) and a.target_type == "DOUBLE":
                return True
            if isinstance(a, SQLBinaryOp) and a.operator in ("+", "-", "*", "/"):
                return True
            if isinstance(a, SQLLiteral) and not isinstance(a.value, bool) and isinstance(a.value, (int, float)):
                return True
            return False

        if any(_is_numeric_expr(a) for a in args):
            def _cast_to_double(a):
                if _is_numeric_expr(a):
                    return a
                if isinstance(a, SQLFunctionCall) and a.name in ('fhirpath_text', 'fhirpath_scalar'):
                    trimmed = SQLFunctionCall(name="LTRIM", args=[a])
                    is_json = SQLFunctionCall(name="starts_with", args=[trimmed, SQLLiteral(value="{")])
                    json_value = SQLFunctionCall(name="json_extract_string", args=[a, SQLLiteral(value="$.value")])
                    return SQLCast(
                        expression=SQLCase(
                            when_clauses=[(is_json, json_value)],
                            else_clause=a,
                        ),
                        target_type="DOUBLE",
                        try_cast=True,
                    )
                if isinstance(a, (SQLIdentifier, SQLQualifiedIdentifier)):
                    return SQLCast(expression=a, target_type="DOUBLE", try_cast=True)
                return a
            args = [_cast_to_double(a) for a in args]

        return SQLFunctionCall(name="COALESCE", args=args)

    def _translate_count(self, args: list) -> SQLExpression:
        """Translate CQL Count to SQL."""
        if args and isinstance(args[0], SQLFunctionCall) and args[0].name in ('fhirpath_text', 'fhirpath_scalar'):
            return SQLFunctionCall(name="json_array_length", args=args)

        use_distinct = False
        if args and isinstance(args[0], SQLFunctionCall) and args[0].name in ('ARRAY_DISTINCT', 'distinct'):
            args = args[0].args
            use_distinct = True

        # list_distinct(subquery) from _translate_distinct_expression —
        # use len() to count elements of the already-deduplicated list.
        # This avoids wrapping with COUNT() which breaks when the inner
        # subquery contains LIST() aggregates (e.g., in WHERE clauses).
        if args and isinstance(args[0], SQLFunctionCall) and args[0].name == 'list_distinct':
            return SQLFunctionCall(name="len", args=args)

        if args and _is_list_returning_sql(args[0]):
            return SQLFunctionCall(name="len", args=args)

        if args and not use_distinct:
            inner = args[0]
            if isinstance(inner, SQLSubquery) and isinstance(inner.query, SQLSelect):
                inner_sel = inner.query
                if inner_sel.from_clause:
                    count_select = SQLSelect(
                        columns=[SQLFunctionCall(name="COUNT", args=[SQLIdentifier(name="*")])],
                        from_clause=inner_sel.from_clause,
                        joins=inner_sel.joins,
                        where=inner_sel.where,
                    )
                    return SQLSubquery(query=count_select)

        if use_distinct:
            inner = args[0] if args else None
            if isinstance(inner, SQLSubquery) and isinstance(inner.query, SQLSelect):
                inner_sel = inner.query
                if inner_sel.from_clause:
                    count_select = SQLSelect(
                        columns=[SQLFunctionCall(name="COUNT", args=[SQLIdentifier(name="*")])],
                        from_clause=SQLSelect(
                            columns=inner_sel.columns if inner_sel.columns else [SQLIdentifier(name="*")],
                            from_clause=inner_sel.from_clause,
                            joins=inner_sel.joins,
                            where=inner_sel.where,
                            distinct=True,
                        ),
                    )
                    return SQLSubquery(query=count_select)
            func_name = "system.main.count"
            return SQLFunctionCall(name=func_name, args=args, distinct=use_distinct)

        return SQLFunctionCall(name="COUNT", args=args, distinct=False)

    def _translate_exists_func(self, args: list) -> SQLExpression:
        """Translate CQL exists() function."""
        if len(args) >= 1:
            return self._translate_exists(args[0], negated=False)
        self.context.warnings.add_semantics(
            message="exists() called without arguments, using FALSE fallback",
            suggestion="Check that the source expression resolves to a valid CTE",
        )
        return SQLLiteral(value=False)

    def _translate_not_exists_func(self, args: list) -> SQLExpression:
        """Translate CQL not exists() function."""
        if len(args) >= 1:
            return self._translate_exists(args[0], negated=True)
        return SQLLiteral(value=False)

    def _translate_substring(self, args: list) -> SQLExpression:
        """Translate CQL Substring (0-indexed) to SQL SUBSTRING (1-indexed).

        Uses ``system.substring`` to bypass the CQL ``Substring`` macro which
        only accepts 2 arguments.

        CQL §17.7: If startIndex < 0 or > Length(string), the result is null.
        """
        if len(args) >= 2:
            start_index = SQLBinaryOp(operator="+", left=args[1], right=SQLLiteral(value=1))
            if len(args) >= 3:
                substr = SQLFunctionCall(name="system.substring", args=[args[0], start_index, args[2]])
            else:
                substr = SQLFunctionCall(name="system.substring", args=[args[0], start_index])
            invalid_start = SQLBinaryOp(left=args[1], operator="<", right=SQLLiteral(value=0))
            past_end = SQLBinaryOp(
                left=args[1],
                operator=">=",
                right=SQLFunctionCall(name="system.length", args=[args[0]]),
            )
            condition = SQLBinaryOp(operator="OR", left=invalid_start, right=past_end)
            if len(args) >= 3:
                condition = SQLBinaryOp(
                    operator="OR",
                    left=condition,
                    right=SQLBinaryOp(left=args[2], operator="<", right=SQLLiteral(value=0)),
                )
            return SQLCase(when_clauses=[(condition, SQLNull())], else_clause=substr)
        return args[0] if args else SQLNull()

    def _translate_startswith(self, args: list) -> SQLExpression:
        """Translate CQL StartsWith."""
        if len(args) >= 2:
            return SQLFunctionCall(name="StartsWith", args=[args[0], args[1]])
        return SQLLiteral(value=False)

    def _translate_endswith(self, args: list) -> SQLExpression:
        """Translate CQL EndsWith."""
        if len(args) >= 2:
            return SQLFunctionCall(name="EndsWith", args=[args[0], args[1]])
        return SQLLiteral(value=False)

    def _translate_contains_func(self, args: list) -> SQLExpression:
        """Translate CQL Contains function (string) to SQL strpos."""
        if len(args) >= 2:
            return SQLBinaryOp(
                operator=">",
                left=SQLFunctionCall(name="strpos", args=[args[0], args[1]]),
                right=SQLLiteral(value=0),
            )
        return SQLLiteral(value=False)

    def _translate_positionof(self, args: list) -> SQLExpression:
        """Translate CQL PositionOf (0-based) to DuckDB strpos (1-based)."""
        if len(args) >= 2:
            strpos_result = SQLFunctionCall(name="strpos", args=[args[1], args[0]])
            return SQLCase(
                when_clauses=[(
                    SQLBinaryOp(operator="=", left=strpos_result, right=SQLLiteral(value=0)),
                    SQLLiteral(value=-1),
                )],
                else_clause=SQLBinaryOp(operator="-", left=strpos_result, right=SQLLiteral(value=1)),
            )
        return SQLLiteral(value=-1)

    def _translate_lastpositionof(self, args: list) -> SQLExpression:
        """Translate CQL LastPositionOf (0-based) using the registered macro."""
        if len(args) >= 2:
            # Use the registered LastPositionOf macro (handles null, 0-based)
            return SQLFunctionCall(name="LastPositionOf", args=[args[0], args[1]])
        return SQLLiteral(value=-1)

    def _translate_abs(self, args: list) -> SQLExpression:
        """Translate CQL Abs through TRY so overflow returns null."""
        if not args:
            return SQLNull()
        return SQLFunctionCall(
            name="TRY",
            args=[SQLFunctionCall(name="system.abs", args=[args[0]])],
        )

    def _translate_log(self, args: list) -> SQLExpression:
        """Translate CQL Log(value, base).

        CQL §16.11: Returns null for invalid inputs (negative, base=1).
        Uses ``system.log`` with DuckDB's base-first argument order and wraps in
        TRY() to return null on out-of-range errors.
        """
        if len(args) != 2:
            raise TranslationError("CQL Log requires exactly two arguments: Log(value, base)")
        # CQL: Log(value, base) → DuckDB: TRY(system.log(base, value))
        return SQLFunctionCall(name="TRY", args=[
            SQLFunctionCall(name="system.log", args=[args[1], args[0]])
        ])

    def _translate_exp(self, args: list) -> SQLExpression:
        """Translate CQL Exp through the parity-aligned math UDF."""
        if not args:
            return SQLNull()
        return SQLCast(
            expression=SQLFunctionCall(name="mathExp", args=[
                SQLCast(expression=args[0], target_type="VARCHAR")
            ]),
            target_type="DOUBLE",
            try_cast=True,
        )

    def _translate_ln(self, args: list) -> SQLExpression:
        """Translate CQL Ln (§16.12) through the parity-aligned math UDF."""
        if not args:
            return SQLNull()
        return SQLCast(
            expression=SQLFunctionCall(name="mathLn", args=[
                SQLCast(expression=args[0], target_type="VARCHAR")
            ]),
            target_type="DOUBLE",
            try_cast=True,
        )

    def _translate_power(self, args: list) -> SQLExpression:
        """Translate CQL Power through the parity-aligned math UDF.

        Fallback when the pre-translate hook could not determine operand
        types (e.g. dynamic operands). Uses DOUBLE which is the most
        permissive numeric type; overflow checks are not applied.
        """
        if len(args) != 2:
            return SQLNull()
        left_arg = self._fhirpath_number_projection(args[0]) or args[0]
        right_arg = self._fhirpath_number_projection(args[1]) or args[1]
        return SQLCast(
            expression=SQLFunctionCall(name="mathPower", args=[
                SQLCast(expression=left_arg, target_type="VARCHAR"),
                SQLCast(expression=right_arg, target_type="VARCHAR"),
            ]),
            target_type="DOUBLE",
            try_cast=True,
        )

    def _translate_power_pre(self, func: FunctionRef, translator) -> Optional[SQLExpression]:
        """Pre-translate CQL Power(Integer/Long/Decimal, Integer/Long/Decimal).

        CQL §16 Power signatures:
          ^(Integer, Integer) Integer
          ^(Long, Long) Long
          ^(Decimal, Decimal) Decimal
        "If the result of the operation cannot be represented, the result
        is null."

        The infix `^` translator at `_operators.py` already applies
        type-specific casting; this hook brings the function form
        ``Power(left, right)`` to parity. Without this hook, the function
        form always emits ``TRY_CAST(mathPower(...) AS DOUBLE)``, which
        silently lets Integer and Decimal overflows through (e.g.
        ``Power(2, 100) = 1.27e30`` should be NULL because Integer max
        is 2^31-1).

        Returns None to fall through to the generic rename-based dispatch
        (which calls ``_translate_power``) when operand types cannot be
        statically determined.
        """
        if not func.arguments or len(func.arguments) != 2:
            return None
        left_cql_type = _infer_static_numeric_type(func.arguments[0])
        right_cql_type = _infer_static_numeric_type(func.arguments[1])
        operand_types = {left_cql_type, right_cql_type} - {None}
        if not operand_types:
            # Dynamic operands — fall back to DOUBLE emission.
            return None
        # Translate operands to SQL.
        left_sql = self.translate(func.arguments[0], usage=ExprUsage.SCALAR)
        right_sql = self.translate(func.arguments[1], usage=ExprUsage.SCALAR)
        left_arg = self._fhirpath_number_projection(left_sql) or left_sql
        right_arg = self._fhirpath_number_projection(right_sql) or right_sql
        power_core = SQLFunctionCall(name="mathPower", args=[
            SQLCast(expression=left_arg, target_type="VARCHAR"),
            SQLCast(expression=right_arg, target_type="VARCHAR"),
        ])
        # Decimal takes precedence per spec implicit conversion rules;
        # otherwise Integer/Long stays integral. Same logic as infix `^`.
        if "Decimal" in operand_types or "Quantity" in operand_types:
            target_sql_type = "DECIMAL(38, 8)"
        elif "Long" in operand_types:
            target_sql_type = "BIGINT"
        elif operand_types == {"Integer"}:
            # Per official HL7 CQL conformance suite
            # (CqlArithmeticFunctionsTest.xml::Power2ToNeg2),
            # Power(2, -2) = 0.25 — Integer operand signature but the
            # reference implementation promotes to Decimal when the
            # exponent is negative (result is fractional). Statically
            # detect negative exponents and use DECIMAL so the result is
            # not truncated to 0 by TRY_CAST(AS INTEGER).
            right_value = _static_numeric_value(func.arguments[1])
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

    def _translate_scalar_min(self, args: list) -> SQLExpression:
        """Translate CQL scalar Min (2-arg) to DuckDB LEAST."""
        return SQLFunctionCall(name="LEAST", args=args)

    def _translate_scalar_max(self, args: list) -> SQLExpression:
        """Translate CQL scalar Max (2-arg) to DuckDB GREATEST."""
        return SQLFunctionCall(name="GREATEST", args=args)

    def _translate_simple_aggregate(self, sql_name: str, args: list) -> SQLExpression:
        """Translate a simple CQL aggregate (Sum, Avg) to SQL."""
        return SQLFunctionCall(name=sql_name, args=args)

    def _translate_first(self, args: list) -> SQLExpression:
        """Translate CQL First to DuckDB LIST_EXTRACT(list, 1)."""
        if args:
            return SQLFunctionCall(name="LIST_EXTRACT", args=[args[0], SQLLiteral(value=1)])
        return SQLNull()

    def _translate_last(self, args: list) -> SQLExpression:
        """Translate CQL Last to DuckDB LIST_EXTRACT(list, -1)."""
        if args:
            return SQLFunctionCall(name="LIST_EXTRACT", args=[args[0], SQLLiteral(value=-1)])
        return SQLNull()

    def _translate_singletonfrom(self, args: list) -> SQLExpression:
        """Translate CQL SingletonFrom."""
        if args:
            return self._apply_singleton_from(args[0])
        return SQLNull()

    def _translate_message(self, args: list) -> SQLExpression:
        """Translate CQL Message (§22.15) — return source or raise on Error severity.

        Message(source, condition, code, severity, message) — if severity is
        the literal 'Error', raise at runtime via the CQLMessage UDF.
        """
        if not args:
            return SQLNull()
        if len(args) < 5:
            return args[0]

        source, condition, _, severity, _ = args[:5]
        if isinstance(condition, SQLLiteral) and condition.value is False:
            return source
        if isinstance(condition, SQLNull):
            return source
        if isinstance(severity, SQLIdentifier):
            severity = SQLParameterRef(name=severity.name)
            args = [source, condition, args[2], severity, args[4]]
        if isinstance(severity, SQLLiteral) and str(severity.value).lower() != 'error':
            return source

        return SQLFunctionCall(name="CQLMessage", args=args[:5])

    def _validate_message_signature_args(self, arg_nodes: list) -> None:
        """Reject statically invalid CQL Message operands before SQL lowering.

        Per CQL v1.5.3 Appendix B §13.1: "The code provides a coded
        representation of the error. Note that this is a token (like a string
        or integer), not a terminology Code." The ``code`` slot therefore
        accepts any scalar token (String, Integer, Long, Decimal, Boolean,
        Date, DateTime, Time) — the runtime CQLMessage macro CASTs the value
        to VARCHAR. ``severity`` and ``message`` remain String per spec.

        Per the fixed 5-arg signature
        ``Message(source T, condition Boolean, code String, severity String,
        message String) T``, more than 5 operands is an authoring error and
        must be rejected rather than silently truncated.
        """
        if len(arg_nodes) > 5:
            raise TranslationError(
                f"CQL Message accepts at most 5 arguments (source, condition, "
                f"code, severity, message); got {len(arg_nodes)}"
            )
        if len(arg_nodes) >= 2:
            condition_type = self._infer_static_cql_type_for_logical_operand(arg_nodes[1])
            normalized = str(condition_type or "Any").replace("System.", "")
            if not (
                normalized in {"Any", "Boolean"}
                or (normalized.startswith("Choice<") and "Boolean" in normalized)
            ):
                raise TranslationError(
                    f"CQL Message condition argument must be Boolean; got {condition_type}"
                )

        # code (index 2): spec calls this "a token (like a string or integer)".
        # Any statically-known scalar is acceptable; runtime CAST handles
        # stringification. We only reject List-typed operands because they
        # cannot be tokenized into a single coded value.
        if len(arg_nodes) > 2 and not self._is_static_string_operand(arg_nodes[2]):
            code_type = self._infer_static_cql_type_for_logical_operand(arg_nodes[2])
            code_normalized = str(code_type or "Any").replace("System.", "")
            if code_normalized.startswith("List<") or code_normalized == "List":
                raise TranslationError(
                    f"CQL Message code argument must be a scalar token; got {code_type}"
                )

        for index, label in ((3, "severity"), (4, "message")):
            if len(arg_nodes) <= index:
                continue
            if self._is_static_string_operand(arg_nodes[index]):
                continue
            arg_type = self._infer_static_cql_type_for_logical_operand(arg_nodes[index])
            raise TranslationError(
                f"CQL Message {label} argument must be String; got {arg_type}"
            )

    def _translate_quantity_constructor(self, args: list) -> SQLExpression:
        """Translate CQL Quantity(value, unit) constructor."""
        if len(args) >= 2:
            value_arg = args[0]
            unit_arg = args[1]
            if isinstance(value_arg, SQLFunctionCall) and value_arg.name in ('fhirpath_text', 'fhirpath_scalar'):
                value_arg = SQLCast(expression=value_arg, target_type="DOUBLE", try_cast=True)
            return SQLFunctionCall(
                name="parse_quantity",
                args=[SQLFunctionCall(
                    name="json_object",
                    args=[
                        SQLLiteral(value="value"), value_arg,
                        SQLLiteral(value="unit"), unit_arg,
                        SQLLiteral(value="system"), SQLLiteral(value="http://unitsofmeasure.org"),
                    ],
                )],
            )
        return SQLNull()

    def _translate_maximum_func(self, args: list) -> SQLExpression:
        """Translate CQL maximum(Type) — max value for a type (parameterized path)."""
        return SQLNull()

    def _translate_minimum_func(self, args: list) -> SQLExpression:
        """Translate CQL minimum(Type) — min value for a type (parameterized path)."""
        return SQLNull()

    def _translate_maximum_pre(self, func: FunctionRef, translator) -> Optional[SQLExpression]:
        """Pre-translate CQL maximum(Type) — needs raw CQL AST for type name."""
        _MAX_VALUES = {
            "datetime": "9999-12-31T23:59:59.999Z",
            "date": "9999-12-31",
            "time": "T23:59:59.999",
            "integer": 2147483647,
            "long": 9223372036854775807,
            "decimal": ("99999999999999999999.99999999", "decimal"),
            "quantity": ("99999999999999999999.99999999", "quantity"),
        }
        if func.arguments:
            type_arg = func.arguments[0]
            if isinstance(type_arg, (NamedTypeSpecifier, Identifier)):
                raw_type_name = type_arg.name
                type_name = raw_type_name.split(".")[-1].lower()
                val = _MAX_VALUES.get(type_name)
                if val is not None:
                    if isinstance(val, tuple) and val[1] == "decimal":
                        return SQLLiteral(value=val[0], raw_sql=val[0])
                    if isinstance(val, tuple) and val[1] == "quantity":
                        result = SQLFunctionCall(
                            name="json_object",
                            args=[
                                SQLLiteral(value="value"),
                                SQLCast(
                                    expression=SQLLiteral(value=val[0]),
                                    target_type="DECIMAL(38,8)",
                                ),
                                SQLLiteral(value="unit"),
                                SQLLiteral(value="1"),
                                SQLLiteral(value="code"),
                                SQLLiteral(value="1"),
                                SQLLiteral(value="system"),
                                SQLLiteral(value="http://unitsofmeasure.org"),
                            ],
                        )
                        result.result_type = "Quantity"
                        return result
                    return SQLLiteral(value=val)
                raise ValueError(f"The Maximum operator is not defined for type {raw_type_name}")
        return SQLNull()

    def _translate_minimum_pre(self, func: FunctionRef, translator) -> Optional[SQLExpression]:
        """Pre-translate CQL minimum(Type) — needs raw CQL AST for type name."""
        _MIN_VALUES = {
            "datetime": "0001-01-01T00:00:00.000Z",
            "date": "0001-01-01",
            "time": "T00:00:00.000",
            "integer": -2147483648,
            "long": -9223372036854775808,
            "decimal": ("-99999999999999999999.99999999", "decimal"),
            "quantity": ("-99999999999999999999.99999999", "quantity"),
        }
        if func.arguments:
            type_arg = func.arguments[0]
            if isinstance(type_arg, (NamedTypeSpecifier, Identifier)):
                raw_type_name = type_arg.name
                type_name = raw_type_name.split(".")[-1].lower()
                val = _MIN_VALUES.get(type_name)
                if val is not None:
                    if isinstance(val, tuple) and val[1] == "decimal":
                        return SQLLiteral(value=val[0], raw_sql=val[0])
                    if isinstance(val, tuple) and val[1] == "quantity":
                        result = SQLFunctionCall(
                            name="json_object",
                            args=[
                                SQLLiteral(value="value"),
                                SQLCast(
                                    expression=SQLLiteral(value=val[0]),
                                    target_type="DECIMAL(38,8)",
                                ),
                                SQLLiteral(value="unit"),
                                SQLLiteral(value="1"),
                                SQLLiteral(value="code"),
                                SQLLiteral(value="1"),
                                SQLLiteral(value="system"),
                                SQLLiteral(value="http://unitsofmeasure.org"),
                            ],
                        )
                        result.result_type = "Quantity"
                        return result
                    return SQLLiteral(value=val)
                raise ValueError(f"The Minimum operator is not defined for type {raw_type_name}")
        return SQLNull()

    def _translate_precision_pre(self, func, translator) -> "Optional[SQLExpression]":
        """Pre-translate CQL Precision() — preserve raw Decimal trailing zeros.

        CQL §22.24: Precision returns the number of digits of precision.
        For Decimal literals, trailing zeros are significant:
        Precision(1.58700) = 5, not 3.
        """
        from ...parser.ast_nodes import Literal as _ASTLiteral
        if func.arguments:
            arg = func.arguments[0]
            # Decimal literal with raw_str: pass the raw string to preserve
            # trailing zeros that Python float() would strip.
            if (isinstance(arg, _ASTLiteral)
                    and getattr(arg, 'type', None) == 'Decimal'
                    and getattr(arg, 'raw_str', None)):
                return SQLFunctionCall(
                    name="CQLPrecision",
                    args=[SQLLiteral(value=arg.raw_str)],
                )
        # Fall through: let the normal rename handle it
        return None

    @staticmethod
    def _collapse_interval_point_kind(arg: object) -> str | None:
        candidate = arg
        if isinstance(candidate, ListExpression):
            interval_elements = [
                element for element in candidate.elements
                if isinstance(element, Interval)
            ]
            if not interval_elements:
                return None
            candidate = interval_elements[0]
        if not isinstance(candidate, Interval):
            return None
        bounds = [candidate.low, candidate.high]
        if any(isinstance(bound, Quantity) for bound in bounds):
            return "quantity"
        if any(isinstance(bound, (DateTimeLiteral, TimeLiteral)) for bound in bounds):
            return "temporal"
        if any(
            isinstance(bound, Literal)
            and (
                bound.type in {"Integer", "Long", "Decimal"}
                or isinstance(bound.value, (int, float))
            )
            for bound in bounds
        ):
            return "numeric"
        return None

    @staticmethod
    def _collapse_per_incompatible(arg: object, per: object) -> bool:
        if not isinstance(per, Quantity):
            return False
        kind = FunctionsMixin._collapse_interval_point_kind(arg)
        if kind is None:
            return False
        unit = (per.unit or "").strip().lower()
        default_unit = unit in {"", "1"}
        temporal_units = {
            "year", "years", "a",
            "month", "months", "mo",
            "week", "weeks", "wk",
            "day", "days", "d",
            "hour", "hours", "h",
            "minute", "minutes", "min",
            "second", "seconds", "s",
            "millisecond", "milliseconds", "ms",
        }
        if kind == "numeric":
            return not default_unit
        if kind == "temporal":
            return unit not in temporal_units
        if kind == "quantity":
            return default_unit or unit in temporal_units
        return False

    def _translate_collapse(self, func: FunctionRef, args: list) -> SQLExpression:
        """Translate CQL Collapse to collapse_intervals UDF."""
        if len(func.arguments) > 1 and self._collapse_per_incompatible(func.arguments[0], func.arguments[1]):
            return SQLNull()
        arg = args[0]
        if (
            isinstance(arg, SQLQualifiedIdentifier)
            and len(arg.parts) == 2
            and self.context.query_builder
        ):
            alias_name, col_name = arg.parts
            for (cte_name, _), ref in self.context.query_builder.cte_references.items():
                if ref.alias == alias_name:
                    outer_pid = (
                        self.context.resource_alias
                        or self.context.patient_alias
                        or "_pt"
                    )
                    arg = SQLSubquery(query=SQLSelect(
                        columns=[SQLFunctionCall(
                            name="json_group_array",
                            args=[SQLIdentifier(name=col_name)],
                        )],
                        from_clause=SQLAlias(
                            expr=SQLIdentifier(name=cte_name, quoted=True),
                            alias="_collapse_sub",
                        ),
                        where=SQLBinaryOp(
                            operator="=",
                            left=SQLQualifiedIdentifier(parts=["_collapse_sub", "patient_id"]),
                            right=SQLQualifiedIdentifier(parts=[outer_pid, "patient_id"]),
                        ),
                    ))
                    break
        if len(args) > 1:
            expand_arg = arg
            if isinstance(expand_arg, SQLSubquery):
                expand_arg = SQLFunctionCall(
                    name="from_json",
                    args=[expand_arg, SQLLiteral(value='["VARCHAR"]')],
                )
            elif not isinstance(expand_arg, SQLArray) and not (
                isinstance(expand_arg, SQLFunctionCall)
                and expand_arg.name
                and expand_arg.name.startswith("list_")
            ) and not _is_list_returning_sql(expand_arg):
                expand_arg = SQLFunctionCall(name="list_value", args=[expand_arg])
            arg = SQLFunctionCall(name="expand", args=[expand_arg, args[1]])
            return SQLFunctionCall(name="collapse_intervals", args=[arg])
        if _is_list_returning_sql(arg):
            arg = SQLFunctionCall(name="to_json", args=[arg])
        return SQLFunctionCall(name="collapse_intervals", args=[arg])

    def _translate_expand(self, func: FunctionRef) -> Optional[SQLExpression]:
        """Translate CQL Expand.

        For integer list-of-intervals with a single element, uses DuckDB's
        native ``generate_series`` + ``list_transform`` for efficient expansion
        that returns a proper DuckDB list (compatible with UNNEST).

        For single-interval overloads, routes to ``expand_points`` UDFs.
        For other list-of-intervals (dates, etc.), routes to ``expand`` UDFs.

        CQL §19.25.
        """
        if not func.arguments:
            return None

        first_arg = self.translate(func.arguments[0], usage=ExprUsage.SCALAR)

        from ...parser.ast_nodes import Interval as CQLInterval, ListExpression, Literal
        ast_arg = func.arguments[0]
        if isinstance(ast_arg, Literal) and ast_arg.value is None:
            return SQLNull()
        is_single_interval = isinstance(ast_arg, CQLInterval)

        if is_single_interval:
            # Single-interval overload → expand_points UDF (accepts VARCHAR)
            fn_name = "expand_points" if len(func.arguments) > 1 else "expand_points1"
            if len(func.arguments) > 1:
                per_arg = self.translate(func.arguments[1], usage=ExprUsage.SCALAR)
                return SQLFunctionCall(name=fn_name, args=[first_arg, per_arg])
            return SQLFunctionCall(name=fn_name, args=[first_arg])

        # List-of-intervals: check for integer interval optimization.
        # { Interval[low, high] } with no per → generate_series for DuckDB list.
        if (
            isinstance(ast_arg, ListExpression)
            and len(ast_arg.elements) == 1
            and isinstance(ast_arg.elements[0], CQLInterval)
            and len(func.arguments) == 1
        ):
            interval_elem = ast_arg.elements[0]
            low_sql = self.translate(interval_elem.low, usage=ExprUsage.SCALAR)
            high_sql = self.translate(interval_elem.high, usage=ExprUsage.SCALAR)
            # Adjust for open bounds: integer [1, 10) → generate_series(1, 9)
            if not interval_elem.low_closed:
                low_sql = SQLBinaryOp(operator="+", left=low_sql, right=SQLLiteral(value=1))
            if not interval_elem.high_closed:
                high_sql = SQLBinaryOp(operator="-", left=high_sql, right=SQLLiteral(value=1))
            # Ensure integer type for generate_series (cqlDurationBetween returns VARCHAR)
            low_sql = SQLCast(expression=low_sql, target_type="INTEGER", try_cast=True)
            high_sql = SQLCast(expression=high_sql, target_type="INTEGER", try_cast=True)
            series = SQLFunctionCall(name="generate_series", args=[low_sql, high_sql])
            lambda_param = SQLIdentifier(name="x")
            lambda_body = SQLFunctionCall(
                name="intervalFromBounds",
                args=[
                    SQLCast(expression=lambda_param, target_type="VARCHAR"),
                    SQLCast(expression=SQLIdentifier(name="x"), target_type="VARCHAR"),
                    SQLLiteral(value=True),
                    SQLLiteral(value=True),
                ],
            )
            return SQLFunctionCall(
                name="list_transform",
                args=[series, SQLLambda(param="x", body=lambda_body)],
            )

        # General list-of-intervals → expand UDF (accepts VARCHAR[])
        from ...translator.types import SQLArray
        if not isinstance(first_arg, SQLArray) and not (
            isinstance(first_arg, SQLFunctionCall)
            and first_arg.name
            and first_arg.name.startswith("list_")
        ):
            first_arg = SQLFunctionCall(name="list_value", args=[first_arg])
        fn_name = "expand" if len(func.arguments) > 1 else "expand1"

        if len(func.arguments) > 1:
            per_arg = self.translate(func.arguments[1], usage=ExprUsage.SCALAR)
            return SQLFunctionCall(name=fn_name, args=[first_arg, per_arg])
        return SQLFunctionCall(name=fn_name, args=[first_arg])

    def _translate_type_conversion(self, name: str, args: List[SQLExpression]) -> SQLExpression:
        """Translate a CQL type conversion function."""
        name_lower = name.lower()
        type_map = {
            "toboolean": "BOOLEAN",
            "tostring": "VARCHAR",
            "tointeger": "INTEGER",
            "todecimal": "DOUBLE",
            "todate": "DATE",
            "todatetime": "TIMESTAMP",
            "totime": "TIME",
        }

        target_type = type_map.get(name_lower)
        if target_type and args:
            # ToTime needs special handling — use the macro which strips 'T' prefix
            if name_lower == "totime":
                return SQLFunctionCall("ToTime", args)
            # ToString(Quantity): CQL §22.31 — format as "<value> '<unit>'"
            if name_lower == "tostring":
                arg = args[0]
                arg_sql = arg.to_sql() if hasattr(arg, 'to_sql') else str(arg)
                if _is_ratio_expression(arg) or 'ToRatio' in arg_sql:
                    return SQLFunctionCall("RatioToString", args)
                if 'parse_quantity' in arg_sql or 'Quantity' in arg_sql:
                    return SQLFunctionCall("QuantityToString", args)
                return SQLFunctionCall("ToString", args)
            if name_lower in ('todatetime', 'todate'):
                macro_name = "ToDateTime" if name_lower == "todatetime" else "ToDate"
                return SQLFunctionCall(macro_name, args)
            if name_lower in ("toboolean", "tointeger", "todecimal"):
                macro_name = {
                    "toboolean": "ToBoolean",
                    "tointeger": "ToInteger",
                    "todecimal": "ToDecimal",
                }[name_lower]
                return SQLFunctionCall(name=macro_name, args=args)
            # Use TRY_CAST to avoid Conversion Errors.
            return SQLCast(expression=args[0], target_type=target_type, try_cast=True)

        return args[0] if args else SQLNull()

    def _translate_exists(self, source: SQLExpression, negated: bool = False) -> SQLExpression:
        """Translate an exists expression."""
        if negated:
            return SQLUnaryOp(operator="IS NULL", operand=source, prefix=False)
        return SQLUnaryOp(operator="IS NOT NULL", operand=source, prefix=False)

    def _build_correlated_exists(self, cte_name: str) -> SQLExpression:
        """
        Build a correlated EXISTS subquery for a CTE reference.

        In population context, EXISTS subqueries must correlate the CTE's patient_id
        with the outer query's patient context to avoid cross-patient data leakage.

        Args:
            cte_name: The name of the CTE to reference.

        Returns:
            SQLExists with correlated WHERE clause if in population context,
            otherwise a simple EXISTS.
        """
        # Build the subquery: SELECT 1 FROM "CTE" sub WHERE sub.patient_id = outer.patient_id
        # Always correlate on patient_id. During translate_library(),
        # patient_alias is None; fall back to "_pt" which gets fixed up
        # later by replace_qualified_alias in translator.py.
        outer_alias = self.context.patient_alias or "_pt"
        if self.context.current_patient_id:
            correlation_where = SQLBinaryOp(
                operator="=",
                left=SQLQualifiedIdentifier(parts=["sub", "patient_id"]),
                right=SQLLiteral(value=self.context.current_patient_id),
            )
        else:
            correlation_where = SQLBinaryOp(
                operator="=",
                left=SQLQualifiedIdentifier(parts=["sub", "patient_id"]),
                right=SQLQualifiedIdentifier(parts=[outer_alias, "patient_id"]),
            )

        # Use SQLAlias for the FROM clause to enable correlation detection
        # Note: No LIMIT 1 - EXISTS stops at first match anyway
        exists_select = SQLSelect(
            columns=[SQLLiteral(value=1)],
            from_clause=SQLAlias(
                expr=SQLIdentifier(name=cte_name, quoted=True),
                alias="sub",
            ),
            where=correlation_where,
        )

        return SQLExists(subquery=SQLSubquery(query=exists_select))

    @staticmethod
    def _strip_aggregates_for_exists(select: "SQLSelect") -> "SQLSelect":
        """Replace aggregate columns with ``SELECT 1`` for EXISTS subqueries.

        Aggregate functions like ``list()`` always produce exactly one output
        row even when the input set is empty.  This breaks ``NOT EXISTS``
        checks because the subquery returns a row regardless of input.
        Since EXISTS only needs to know whether any rows match, we can
        safely replace aggregate column lists with a literal ``1``.
        """
        _AGGREGATE_NAMES = frozenset({"list", "count", "sum", "avg", "min", "max",
                                       "string_agg", "array_agg", "group_concat"})
        if not isinstance(select, SQLSelect) or not select.columns:
            return select
        has_aggregate = False
        for col in select.columns:
            expr = col.expr if isinstance(col, SQLAlias) else col
            if isinstance(expr, SQLFunctionCall) and expr.name.lower() in _AGGREGATE_NAMES:
                has_aggregate = True
                break
        if has_aggregate:
            return SQLSelect(
                columns=[SQLLiteral(value=1)],
                from_clause=select.from_clause,
                joins=select.joins,
                where=select.where,
                group_by=select.group_by,
                having=select.having,
                order_by=select.order_by,
                limit=select.limit,
                distinct=select.distinct,
            )
        return select

    def _add_patient_id_correlation_to_exists(self, select: "SQLSelect") -> "SQLSelect":
        """Add patient_id correlation to an EXISTS subquery's inner SELECT.

        When an ``exists`` wraps a query whose FROM clause is backed by a CTE
        (or UNION of CTEs), the inner query must be correlated with the outer
        query's patient context to prevent cross-patient data leakage.

        The ``with/such that`` code-path already adds this correlation
        (see ``_translate_query``).  This helper covers the ``exists(query)``
        code-path which previously did not.
        """
        from ...translator.placeholder import RetrievePlaceholder

        # Determine the outer alias to correlate against
        outer_alias = self.context.resource_alias or self.context.patient_alias
        if not outer_alias and self.context.is_patient_context():
            # translate_library() builds patient-scalar CTE bodies before the
            # surrounding FROM _patients AS _pt wrapper exists.  Use the same
            # deferred alias expected by cte_manager so scalar subqueries such
            # as singleton-from(query) are still correlated per patient.
            outer_alias = "_pt"
        if not outer_alias:
            return select

        # Extract inner alias from FROM clause
        from_clause = select.from_clause
        if not isinstance(from_clause, SQLAlias):
            return select
        inner_alias = from_clause.alias
        if not inner_alias or inner_alias == outer_alias:
            return select

        # Check if the FROM source is CTE-backed (has patient_id column)
        def _is_cte_backed(expr):
            if isinstance(expr, SQLAlias):
                return _is_cte_backed(expr.expr)
            if isinstance(expr, SQLIdentifier) and expr.quoted:
                return True
            if isinstance(expr, RetrievePlaceholder):
                return True
            if isinstance(expr, SQLUnion):
                return True
            if isinstance(expr, SQLSubquery):
                inner = expr.query
                if isinstance(inner, SQLSelect) and inner.from_clause:
                    return _is_cte_backed(inner.from_clause)
                if isinstance(inner, SQLUnion):
                    return True
            return False

        if not _is_cte_backed(from_clause):
            return select

        # Check if patient_id correlation is already present (avoid duplicates)
        def _has_patient_id_corr(where_expr):
            if isinstance(where_expr, SQLBinaryOp):
                if where_expr.operator == "=":
                    left_str = _qual_id_str(where_expr.left)
                    right_str = _qual_id_str(where_expr.right)
                    if left_str and right_str:
                        if "patient_id" in left_str and "patient_id" in right_str:
                            return True
                if where_expr.operator == "AND":
                    return _has_patient_id_corr(where_expr.left) or _has_patient_id_corr(where_expr.right)
            return False

        def _qual_id_str(expr):
            if isinstance(expr, SQLQualifiedIdentifier):
                return ".".join(str(p) for p in expr.parts)
            return None

        if select.where and _has_patient_id_corr(select.where):
            return select

        # Add: inner_alias.patient_id = outer_alias.patient_id
        patient_corr = SQLBinaryOp(
            left=SQLQualifiedIdentifier(parts=[inner_alias, "patient_id"]),
            operator="=",
            right=SQLQualifiedIdentifier(parts=[outer_alias, "patient_id"]),
        )
        new_where = (
            SQLBinaryOp(left=select.where, operator="AND", right=patient_corr)
            if select.where
            else patient_corr
        )
        return SQLSelect(
            columns=select.columns,
            from_clause=select.from_clause,
            where=new_where,
            joins=getattr(select, 'joins', None),
            group_by=getattr(select, 'group_by', None),
            having=getattr(select, 'having', None),
            order_by=getattr(select, 'order_by', None),
            limit=getattr(select, 'limit', None),
            distinct=getattr(select, 'distinct', None),
        )

    def _get_operand_resource_type(self, operand: SQLExpression) -> Optional[str]:
        """Extract resource type from a union operand if determinable."""
        if isinstance(operand, RetrievePlaceholder):
            return operand.resource_type
        if isinstance(operand, SQLSubquery):
            inner = operand.query if hasattr(operand, 'query') else None
            if isinstance(inner, RetrievePlaceholder):
                return inner.resource_type
            if isinstance(inner, SQLSelect) and inner.from_clause:
                from_clause = inner.from_clause
                if isinstance(from_clause, SQLIdentifier) and from_clause.quoted:
                    name = from_clause.name
                    if ":" in name:
                        return name.split(":")[0].strip()
        if isinstance(operand, SQLIdentifier) and operand.quoted:
            name = operand.name
            if ":" in name:
                return name.split(":")[0].strip()
        return None

    def _check_union_disjointness(self, operands: List[SQLExpression]) -> bool:
        """Check if all union operands reference different resource types."""
        resource_types = [self._get_operand_resource_type(op) for op in operands]
        all_known = all(rt is not None for rt in resource_types)
        if not all_known or len(resource_types) < 2:
            return False
        return len(set(resource_types)) == len(resource_types)

    def _extract_subqueries_from_union(self, expr: SQLExpression) -> List[SQLExpression]:
        """
        Recursively extract subqueries from nested jsonConcat expressions.

        Args:
            expr: SQL expression that might be jsonConcat with subquery args

        Returns:
            List of SQLSubquery objects found, or empty list if not extractable
        """
        if isinstance(expr, SQLSubquery):
            return [expr]

        if isinstance(expr, SQLFunctionCall) and expr.name.lower() == "jsonconcat":
            left_subs = self._extract_subqueries_from_union(expr.args[0]) if len(expr.args) > 0 else []
            right_subs = self._extract_subqueries_from_union(expr.args[1]) if len(expr.args) > 1 else []
            return left_subs + right_subs

        if isinstance(expr, SQLUnion):
            # Already a union, extract all subquery operands
            result = []
            for op in expr.operands:
                if isinstance(op, SQLSubquery):
                    result.append(op)
            return result

        # Wrap row-producing set operations (INTERSECT, EXCEPT) in a
        # subquery so they can participate in UNION composition.
        # Normalize operands: strip patient_id correlation added by
        # SCALAR-context translation, since in UNION context each branch
        # must produce ALL rows independently.
        if isinstance(expr, (SQLIntersect, SQLExcept)):
            normalized_ops = [self._normalize_set_operand_for_union(op) for op in expr.operands]
            return [SQLSubquery(query=type(expr)(operands=normalized_ops))]

        return []  # Cannot extract - not a union-compatible expression

    @staticmethod
    def _normalize_set_operand_for_union(op: SQLExpression) -> SQLExpression:
        """Strip patient_id correlation from a set operation operand.

        When ExpressionRefs are translated in SCALAR context, they gain
        ``WHERE sub.patient_id = <alias>.patient_id``.  In UNION context
        that correlation is invalid (there is no outer ``FROM _patients``).
        This helper widens the subquery to ``SELECT * FROM "CTE"`` and
        removes the correlation filter.
        """
        if isinstance(op, SQLSubquery) and isinstance(op.query, SQLSelect):
            inner = op.query
            where = inner.where
            if where is not None and _is_patient_id_correlation(where):
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
        return op

    def _translate_age_function(self, name: str, args: List[SQLExpression]) -> SQLExpression:
        """Translate AgeInYears/AgeInMonths/etc. using calendar-duration macros.

        Uses the demographics CTE to access Patient.birthDate and the
        YearsBetween/MonthsBetween/DaysBetween macros for CQL-compliant
        calendar duration semantics (CQL §2.3, §18.4).
        """
        name_lower = name.lower()

        # Map to calendar-duration macro names
        macro_map = {
            "ageinyears": "YearsBetween",
            "ageinmonths": "MonthsBetween",
            "ageinweeks": "WeeksBetween",
            "ageindays": "DaysBetween",
            "ageinhours": "HoursBetween",
            "ageinminutes": "MinutesBetween",
            "ageinseconds": "SecondsBetween",
        }

        macro_name = macro_map.get(name_lower, "YearsBetween")

        if args:
            birth_date = args[0]
        else:
            # Use the current Patient columns folded into _patients.
            self.context._needs_demographics = True
            _outer_pid = self.context.resource_alias or self.context.patient_alias or "_pt"
            if _outer_pid == "_pt":
                birth_date = SQLQualifiedIdentifier(parts=["_pt", "birth_date"])
            else:
                birth_date = SQLSubquery(query=SQLSelect(
                    columns=[SQLQualifiedIdentifier(parts=["_pd", "birth_date"])],
                    from_clause=SQLAlias(
                        expr=SQLIdentifier(name="_patients"),
                        alias="_pd",
                    ),
                    where=SQLBinaryOp(
                        operator="=",
                        left=SQLQualifiedIdentifier(parts=["_pd", "patient_id"]),
                        right=SQLQualifiedIdentifier(parts=[_outer_pid, "patient_id"]),
                    ),
                    limit=1,
                ))

        if name_lower in ("ageinhours", "ageinminutes", "ageinseconds"):
            current_reference: SQLExpression = SQLRaw(
                "STRFTIME(CURRENT_TIMESTAMP, '%Y-%m-%dT%H:%M:%S')"
            )
        else:
            current_reference = SQLCast(
                expression=SQLFunctionCall(name="CURRENT_DATE", args=[]),
                target_type="VARCHAR",
            )

        return SQLFunctionCall(
            name=macro_name,
            args=[birth_date, current_reference],
        )

    def _translate_age_at_function(self, name: str, args: List[SQLExpression]) -> SQLExpression:
        """
        Translate age calculation functions with explicit as_of date.

        These functions call DuckDB UDFs directly:
        - AgeInYearsAt(patient_resource, as_of_date)
        - AgeInMonthsAt(patient_resource, as_of_date)
        - AgeInDaysAt(patient_resource, as_of_date)

        In population mode this function uses birthday-aware age calculation
        from current Patient columns folded into the _patients CTE.
        """
        # Map function names to UDF names (proper casing)
        udf_name_map = {
            "ageinyearsat": "AgeInYearsAt",
            "ageinmonthsat": "AgeInMonthsAt",
            "ageinweeksat": "AgeInWeeksAt",
            "ageindaysat": "AgeInDaysAt",
            "ageinhoursat": "AgeInHoursAt",
            "ageinminutesat": "AgeInMinutesAt",
            "ageinsecondsat": "AgeInSecondsAt",
        }

        udf_name = udf_name_map.get(name.lower(), "AgeInYearsAt")

        # Args should be (patient_resource, as_of_date)
        # If only one arg provided, assume it's the as_of_date and use current resource
        if len(args) == 1:
            # Use current Patient columns folded into _patients for birthday-aware
            # age calculation.
            self.context._needs_demographics = True
            calc_udf_map = {
                "ageinyearsat": "CalculateAgeInYearsAt",
                "ageinmonthsat": "CalculateAgeInMonthsAt",
                "ageinweeksat": "CalculateAgeInWeeksAt",
                "ageindaysat": "CalculateAgeInDaysAt",
                "ageinhoursat": "CalculateAgeInHoursAt",
                "ageinminutesat": "CalculateAgeInMinutesAt",
                "ageinsecondsat": "CalculateAgeInSecondsAt",
            }
            calc_udf_name = calc_udf_map.get(name.lower(), "CalculateAgeInYearsAt")

            _outer_pid = self.context.resource_alias or self.context.patient_alias or "_pt"
            if _outer_pid == "_pt":
                birth_date = SQLQualifiedIdentifier(parts=["_pt", "birth_date"])
            else:
                birth_date = SQLSubquery(query=SQLSelect(
                    columns=[SQLQualifiedIdentifier(parts=["_pd", "birth_date"])],
                    from_clause=SQLAlias(
                        expr=SQLIdentifier(name="_patients"),
                        alias="_pd",
                    ),
                    where=SQLBinaryOp(
                        operator="=",
                        left=SQLQualifiedIdentifier(parts=["_pd", "patient_id"]),
                        right=SQLQualifiedIdentifier(parts=[_outer_pid, "patient_id"]),
                    ),
                    limit=1,
                ))
            return SQLFunctionCall(
                name=calc_udf_name,
                args=[
                    SQLCast(expression=birth_date, target_type="VARCHAR"),
                    SQLCast(expression=args[0], target_type="VARCHAR"),
                ],
            )
        elif len(args) >= 2:
            patient_resource = args[0]
            as_of_date = args[1]
        else:
            return SQLNull()

        return SQLFunctionCall(name=udf_name, args=[patient_resource, as_of_date])
