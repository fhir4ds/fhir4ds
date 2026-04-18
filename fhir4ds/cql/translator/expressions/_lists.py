"""List, collection, and aggregate expression translations."""
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
    DistinctExpression,
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
)
from ...translator.expressions._utils import (
    BINARY_OPERATOR_MAP,
    UNARY_OPERATOR_MAP,
    _is_list_returning_sql,
    _list_has_order_by,
    _contains_sql_subquery,
    _ensure_scalar_body,
    _get_qicore_extension_fhirpath,
    _resolve_library_code_constant,
)

if TYPE_CHECKING:
    from ...translator.context import SQLTranslationContext

logger = logging.getLogger(__name__)

from ...translator.fhirpath_builder import (
    build_coding_exists_expr,
    build_where_return_expr,
    FHIRPathBuilder,
)

class ListsMixin:
    """Mixin providing list operations, method invocations, and aggregation."""
    def _translate_interval(self, interval: Interval, boolean_context: bool = False) -> SQLExpression:
        """Translate a CQL interval to SQL."""
        # Interval bounds are always scalar values.  Using SCALAR usage ensures
        # that definition references become correlated subqueries instead of
        # JOIN-alias references (j1.value) which would be invisible inside
        # nested subqueries.
        low = self.translate(interval.low, usage=ExprUsage.SCALAR) if interval.low else SQLNull()
        high = self.translate(interval.high, usage=ExprUsage.SCALAR) if interval.high else SQLNull()

        return SQLInterval(
            low=low,
            high=high,
            low_closed=interval.low_closed,
            high_closed=interval.high_closed,
        )

    def _translate_list_expression(self, lst: ListExpression, boolean_context: bool = False) -> SQLExpression:
        """Translate a CQL list to SQL array."""
        elements = [self.translate(e, boolean_context=False) for e in lst.elements]
        return SQLArray(elements=elements)

    def _infer_row_shape_for_expr(self, expr: Any) -> RowShape:
        """Helper to infer row shape from expression for conditional handling."""
        from ...parser.ast_nodes import Retrieve, Query

        # Check definition metadata if it's a named reference
        if hasattr(expr, 'name'):
            meta = self.context.definition_meta.get(expr.name)
            if meta:
                return meta.shape

        # Check for Identifier that references a definition
        if isinstance(expr, Identifier):
            meta = self.context.definition_meta.get(expr.name)
            if meta:
                return meta.shape

        # Check for Retrieve (always RESOURCE_ROWS)
        if isinstance(expr, Retrieve):
            return RowShape.RESOURCE_ROWS

        # Check for Query expressions (produce rows)
        if isinstance(expr, Query):
            return RowShape.RESOURCE_ROWS

        # Check for property access on RESOURCE_ROWS source
        if isinstance(expr, Property):
            return self._infer_row_shape_for_expr(expr.source)

        # Check for binary expressions that produce RESOURCE_ROWS
        if isinstance(expr, BinaryExpression):
            op = getattr(expr, 'operator', '').lower()
            if op in ('union', 'intersect', 'except'):
                return RowShape.RESOURCE_ROWS

        # Nested conditional
        if isinstance(expr, ConditionalExpression):
            then_shape = self._infer_row_shape_for_expr(expr.then_expr)
            else_shape = self._infer_row_shape_for_expr(expr.else_expr)
            if then_shape == RowShape.RESOURCE_ROWS or else_shape == RowShape.RESOURCE_ROWS:
                return RowShape.RESOURCE_ROWS
            return RowShape.PATIENT_SCALAR

        return RowShape.UNKNOWN

    def _translate_conditional_expression(self, expr: ConditionalExpression, boolean_context: bool = False) -> SQLExpression:
        """Translate a CQL conditional (if-then-else) expression to SQL CASE.

        Uses shape-aware strategy:
        - RESOURCE_ROWS branches: handled with COALESCE pattern to avoid UNION in scalar context
        - Scalar branches: standard CASE translation
        """
        # Infer shapes of branches to determine strategy
        then_shape = self._infer_row_shape_for_expr(expr.then_expr)
        else_shape = self._infer_row_shape_for_expr(expr.else_expr)

        # If either branch is RESOURCE_ROWS, use COALESCE pattern
        if then_shape == RowShape.RESOURCE_ROWS or else_shape == RowShape.RESOURCE_ROWS:
            return self._translate_conditional_with_coalesce(expr, boolean_context)

        # Otherwise safe to use standard CASE with JOINs
        return self._translate_conditional_with_case(expr, boolean_context)

    def _translate_conditional_with_case(
        self,
        expr: ConditionalExpression,
        boolean_context: bool
    ) -> SQLExpression:
        """Standard CASE translation for scalar branches."""
        condition = self.translate(expr.condition, boolean_context=True)
        then_expr = self.translate(expr.then_expr, boolean_context=boolean_context)
        else_expr = self.translate(expr.else_expr, boolean_context=boolean_context)

        # Handle SQLUnion in THEN clause - can't put UNION in scalar context
        if isinstance(then_expr, SQLUnion):
            # Convert to COALESCE of individual cases
            coalesce_args = []
            for operand in then_expr.operands:
                coalesce_args.append(SQLCase(
                    when_clauses=[(condition, operand)],
                    else_clause=SQLNull(),
                ))
            # Handle else_expr by adding it as another COALESCE arg
            if else_expr is not None and not isinstance(else_expr, SQLNull):
                coalesce_args.append(SQLCase(
                    when_clauses=[(SQLUnaryOp(operator="IS NULL", operand=condition, prefix=False), else_expr)],
                    else_clause=SQLNull(),
                ))
            return SQLFunctionCall(name="COALESCE", args=coalesce_args)

        # Ensure type compatibility across CASE branches.
        # CQL allows mixed-type if/then/else (e.g., if bool then 'str' else bool).
        # DuckDB requires all branches to have compatible types.
        then_is_str = isinstance(then_expr, SQLLiteral) and isinstance(then_expr.value, str)
        else_is_str = isinstance(else_expr, SQLLiteral) and isinstance(else_expr.value, str)
        if then_is_str and not else_is_str and not isinstance(else_expr, (SQLNull, SQLLiteral)):
            else_expr = SQLCast(expression=else_expr, target_type="VARCHAR")
        elif else_is_str and not then_is_str and not isinstance(then_expr, (SQLNull, SQLLiteral)):
            then_expr = SQLCast(expression=then_expr, target_type="VARCHAR")

        result = SQLCase(
            when_clauses=[(condition, then_expr)],
            else_clause=else_expr,
        )
        # Propagate Quantity type hint through CASE branches
        if getattr(then_expr, 'result_type', None) == "Quantity" or getattr(else_expr, 'result_type', None) == "Quantity":
            result.result_type = "Quantity"
        return result

    def _translate_conditional_with_coalesce(
        self,
        expr: ConditionalExpression,
        boolean_context: bool
    ) -> SQLExpression:
        """Use COALESCE pattern for RESOURCE_ROWS branches.

        For RESOURCE_ROWS branches, we translate each branch independently
        and use COALESCE to select the non-null result. This prevents issues
        with putting UNION/subquery results in scalar CASE context.
        """
        condition = self.translate(expr.condition, boolean_context=True)
        then_expr = self._ensure_scalar_for_case(
            self.translate(expr.then_expr, boolean_context=boolean_context))
        else_expr = self._ensure_scalar_for_case(
            self.translate(expr.else_expr, boolean_context=boolean_context))

        coalesce_args = []

        # Handle THEN expression
        if isinstance(then_expr, SQLUnion):
            # Multiple union operands - each gets its own CASE
            for operand in then_expr.operands:
                coalesce_args.append(SQLCase(
                    when_clauses=[(condition, self._ensure_scalar_for_case(operand))],
                    else_clause=SQLNull(),
                ))
        elif then_expr is not None and not isinstance(then_expr, SQLNull):
            coalesce_args.append(SQLCase(
                when_clauses=[(condition, self._ensure_scalar_for_case(then_expr))],
                else_clause=SQLNull(),
            ))

        # Handle ELSE expression (when condition is FALSE / NOT condition)
        _not_condition = SQLUnaryOp(operator="NOT", operand=condition)
        if isinstance(else_expr, SQLUnion):
            # For UNION in else, add operands directly (selected when condition is false)
            for operand in else_expr.operands:
                coalesce_args.append(SQLCase(
                    when_clauses=[(_not_condition, operand)],
                    else_clause=SQLNull(),
                ))
        elif else_expr is not None and not isinstance(else_expr, SQLNull):
            coalesce_args.append(SQLCase(
                when_clauses=[(_not_condition, self._ensure_scalar_for_case(else_expr))],
                else_clause=SQLNull(),
            ))

        if not coalesce_args:
            return SQLNull()

        if len(coalesce_args) == 1:
            return coalesce_args[0]

        return SQLFunctionCall(name="COALESCE", args=coalesce_args)

    @staticmethod
    def _ensure_scalar_for_case(sql_expr: SQLExpression) -> SQLExpression:
        """Ensure a SQL expression is scalar-safe for use in CASE branches.

        When a Query translates to a multi-column SELECT (patient_id, resource
        or SELECT *), it cannot appear in a scalar CASE branch.  Wrap it as
        a subquery that returns only the ``resource`` column.
        """
        inner = sql_expr
        if isinstance(inner, SQLSubquery):
            inner = inner.query

        if isinstance(inner, SQLSelect):
            cols = inner.columns
            if isinstance(cols, list):
                has_star = any(
                    (isinstance(c, SQLRaw) and c.sql.strip() == "*")
                    or (isinstance(c, SQLIdentifier) and c.name == "*")
                    for c in cols
                )
                if len(cols) > 1 or has_star:
                    inner_alias = "_scq"
                    return SQLSubquery(query=SQLSelect(
                        columns=[SQLQualifiedIdentifier(parts=[inner_alias, "resource"])],
                        from_clause=SQLAlias(
                            expr=SQLSubquery(query=inner) if not isinstance(sql_expr, SQLSubquery) else sql_expr,
                            alias=inner_alias,
                        ),
                    ))
        return sql_expr

    def _translate_case_expression(self, expr: CaseExpression, boolean_context: bool = False) -> SQLExpression:
        """Translate a CQL case expression to SQL CASE."""
        from ...translator.expressions._query import _demote_audit_struct_to_bool

        when_clauses = []

        for item in expr.case_items:
            condition = self.translate(item.when, boolean_context=True)
            condition = _demote_audit_struct_to_bool(condition)
            result = self.translate(item.then, boolean_context=boolean_context)
            when_clauses.append((condition, result))

        else_clause = None
        if expr.else_expr:
            else_clause = self.translate(expr.else_expr, boolean_context=boolean_context)

        comparand = None
        if expr.comparand:
            comparand = self.translate(expr.comparand, boolean_context=False)

        # Check if any when_clauses have SQLUnion as result - can't put UNION in scalar context
        has_union_result = any(isinstance(result, SQLUnion) for _, result in when_clauses)
        if has_union_result:
            # Convert to COALESCE of individual cases
            coalesce_args = []
            for cond, result in when_clauses:
                if isinstance(result, SQLUnion):
                    for operand in result.operands:
                        coalesce_args.append(SQLCase(
                            when_clauses=[(cond, operand)],
                            else_clause=SQLNull(),
                        ))
                else:
                    coalesce_args.append(SQLCase(
                        when_clauses=[(cond, result)],
                        else_clause=SQLNull(),
                    ))
            # Handle else_clause
            if else_clause is not None and not isinstance(else_clause, SQLNull):
                # For simplicity, just add else as another arg (will be selected if all others are NULL)
                if isinstance(else_clause, SQLUnion):
                    for operand in else_clause.operands:
                        coalesce_args.append(operand)
                else:
                    coalesce_args.append(else_clause)
            return SQLFunctionCall(name="COALESCE", args=coalesce_args)

        return SQLCase(
            when_clauses=when_clauses,
            else_clause=else_clause,
            operand=comparand,
        )

    def _translate_tuple_expression(self, tup: TupleExpression, boolean_context: bool = False) -> SQLExpression:
        """Translate a CQL tuple to SQL struct, wrapped as JSON for resource compatibility."""
        # Build a DuckDB struct using named argument syntax: struct_pack(name := value, ...)
        args = []
        for elem in tup.elements:
            name = elem.name
            value = self.translate(elem.type, boolean_context=False)
            # Narrow SELECT * subqueries: struct_pack fields are scalar so
            # multi-column subqueries must be reduced to the resource column.
            value = self._narrow_to_resource_column(value)
            args.append(SQLNamedArg(name=name, value=value))

        struct = SQLFunctionCall(name="struct_pack", args=args)
        # Wrap with to_json() so the result is a JSON string.
        # Downstream code accesses Tuple fields via fhirpath_text(resource, 'field')
        # which requires JSON input, not a DuckDB STRUCT.
        return SQLFunctionCall(name="to_json", args=[struct])

    def _translate_instance_expression(self, inst: InstanceExpression, boolean_context: bool = False) -> SQLExpression:
        """Translate a CQL instance expression to SQL."""
        if inst.type == "Interval":
            # Handle Interval[low, high] syntax
            low_elem = next((e for e in inst.elements if e.name == "low"), None)
            high_elem = next((e for e in inst.elements if e.name == "high"), None)
            low_closed_elem = next((e for e in inst.elements if e.name == "lowClosed"), None)
            high_closed_elem = next((e for e in inst.elements if e.name == "highClosed"), None)

            low = self.translate(low_elem.type, boolean_context=False) if low_elem else SQLNull()
            high = self.translate(high_elem.type, boolean_context=False) if high_elem else SQLNull()
            low_closed = True
            high_closed = True

            if low_closed_elem:
                closed_val = self.translate(low_closed_elem.type, boolean_context=False)
                if isinstance(closed_val, SQLLiteral) and isinstance(closed_val.value, bool):
                    low_closed = closed_val.value

            if high_closed_elem:
                closed_val = self.translate(high_closed_elem.type, boolean_context=False)
                if isinstance(closed_val, SQLLiteral) and isinstance(closed_val.value, bool):
                    high_closed = closed_val.value

            return SQLInterval(low=low, high=high, low_closed=low_closed, high_closed=high_closed)

        if inst.type == "Quantity":
            # Handle Quantity { value: 5, unit: 'mg' }
            value_elem = next((e for e in inst.elements if e.name == "value"), None)
            unit_elem = next((e for e in inst.elements if e.name == "unit"), None)

            value = 0.0
            unit = ""

            if value_elem:
                val_expr = self.translate(value_elem.type, boolean_context=False)
                if isinstance(val_expr, SQLLiteral):
                    value = float(val_expr.value) if not isinstance(val_expr.value, float) else val_expr.value

            if unit_elem:
                unit_expr = self.translate(unit_elem.type, boolean_context=False)
                if isinstance(unit_expr, SQLLiteral) and isinstance(unit_expr.value, str):
                    unit = unit_expr.value

            return self._translate_quantity(Quantity(value=value, unit=unit), boolean_context)

        # Generic instance - build struct
        args = []
        for elem in inst.elements:
            name = elem.name
            value = self.translate(elem.type, boolean_context=False)
            args.append(SQLNamedArg(name=name, value=value))

        return SQLFunctionCall(name="struct_pack", args=args)

    def _translate_method_invocation(self, expr: MethodInvocation, boolean_context: bool = False) -> SQLExpression:
        """Translate a CQL method invocation to SQL."""
        # Check if this is a library-qualified function call (e.g., QICoreCommon.ToInterval(X))
        # before translating the source as an expression
        if isinstance(expr.source, Identifier) and expr.source.name in self.context.includes:
            library_alias = expr.source.name
            func_name = expr.method
            # Delegate to function ref translation with library-qualified name
            from ...parser.ast_nodes import FunctionRef as CQLFunctionRef
            qualified_func = CQLFunctionRef(name=f"{library_alias}.{func_name}", arguments=expr.arguments)
            return self._translate_function_ref(qualified_func, boolean_context=boolean_context)

        source = self.translate(expr.source, boolean_context=False)
        method = expr.method
        args = [self.translate(arg, boolean_context=False) for arg in expr.arguments]

        # Handle common method invocations
        if method.lower() == "first":
            # DuckDB uses list_extract with 1-based indexing
            return SQLFunctionCall(name="list_extract", args=[source, SQLLiteral(value=1)])

        if method.lower() == "last":
            # DuckDB uses list_extract with -1 for last element
            return SQLFunctionCall(name="list_extract", args=[source, SQLLiteral(value=-1)])

        if method.lower() == "singletonfrom":
            # Singleton expects exactly one element - use list_extract
            return SQLFunctionCall(name="list_extract", args=[source, SQLLiteral(value=1)])

        if method.lower() == "count":
            return SQLFunctionCall(name="ARRAY_LENGTH", args=[source])

        if method.lower() == "distinct":
            return SQLFunctionCall(name="ARRAY_DISTINCT", args=[source])

        if method.lower() == "where":
            # where is handled by the query translator
            # For method form, treat as filter
            if args:
                return SQLFunctionCall(name="LIST_FILTER", args=[source, args[0]])
            return source

        if method.lower() == "select":
            if args:
                return SQLFunctionCall(name="LIST_SELECT", args=[source, args[0]])
            return source

        # FHIRCommon ext(element, url) -> extension.where(url='URL')
        # Returns JSON so subsequent .value/.valueCoding access can be flattened
        if method == "ext" and len(args) == 1:
            url_val = getattr(args[0], 'value', None)
            if url_val and isinstance(url_val, str):
                fhirpath_expr = f"extension.where(url='{url_val}')"
                return SQLFunctionCall(
                    name="fhirpath_json",
                    args=[source, SQLLiteral(value=fhirpath_expr)],
                )

        # Age methods
        if method.lower() in ("ageinyears", "ageinmonths", "ageindays"):
            return self._translate_age_function(method, [source])

        # toInterval(): converts choice-type values (Period, DateTime, etc.)
        # to an interval.  intervalStart/End UDFs natively parse Period JSON
        # and bare datetime strings, so for Period values we pass through
        # and for scalar datetimes we wrap in a point-interval.
        if method.lower() == "tointerval":
            # NULL guard: if the source value is NULL, toInterval() must
            # return NULL so that Coalesce(...) can fall through correctly.
            # Without this, intervalFromBounds(NULL, NULL, ...) returns a
            # non-NULL JSON object {"low":null,"high":null,...}.
            return SQLCase(
                when_clauses=[
                    (
                        SQLBinaryOp(
                            operator="IS",
                            left=source,
                            right=SQLNull(),
                        ),
                        SQLLiteral(value=None),
                    ),
                    (
                        SQLFunctionCall(
                            name="starts_with",
                            args=[
                                SQLFunctionCall(name="LTRIM", args=[source]),
                                SQLLiteral(value="{"),
                            ],
                        ),
                        source,
                    ),
                ],
                else_clause=SQLFunctionCall(
                    name="intervalFromBounds",
                    args=[source, source, SQLLiteral(value=True), SQLLiteral(value=True)],
                ),
            )

        # Handle references() BEFORE the fluent translator to avoid wrong
        # overload selection.  The CQL library defines 4 overloads of
        # references(); the overload resolver only matches on the first
        # parameter type and can pick references(Reference, Resource) when
        # references(Reference, String) is needed, causing
        # fhirpath_text(fhirpath_text(C.resource,'id'),'id') double-wrapping.
        # We handle all cases directly with proper AST construction.
        if method.lower() == "references":
            if args:
                arg = args[0]
                if isinstance(arg, SQLIdentifier):
                    # Arg is a resource alias — extract its id
                    id_expr = SQLFunctionCall(
                        name="fhirpath_text",
                        args=[SQLQualifiedIdentifier(parts=[arg.name, "resource"]), SQLLiteral(value="id")],
                    )
                elif isinstance(arg, SQLQualifiedIdentifier) and arg.parts[-1] == "resource":
                    # Arg is a resource column (e.g., QualifyingEncounter.resource) — extract id
                    id_expr = SQLFunctionCall(
                        name="fhirpath_text",
                        args=[arg, SQLLiteral(value="id")],
                    )
                elif (
                    isinstance(arg, SQLFunctionCall)
                    and arg.name == "fhirpath_text"
                    and len(arg.args) >= 2
                    and isinstance(arg.args[1], SQLLiteral)
                    and arg.args[1].value == "id"
                ):
                    # Already an id extraction — use directly
                    id_expr = arg
                else:
                    # Unknown expression — wrap in fhirpath_text to extract id safely
                    id_expr = SQLFunctionCall(
                        name="fhirpath_text",
                        args=[arg, SQLLiteral(value="id")],
                    )
                # CQL semantics: resource.id = Last(Split(reference.reference, '/'))
                # Extract reference URL from source, split on '/', take last segment
                ref_url = self._flatten_fhirpath_source(source, "reference", "fhirpath_text")
                last_segment = SQLFunctionCall(
                    name="LIST_EXTRACT",
                    args=[
                        SQLFunctionCall(name="STR_SPLIT", args=[ref_url, SQLLiteral(value="/")]),
                        SQLLiteral(value=-1),
                    ],
                )
                return SQLBinaryOp(operator="=", left=id_expr, right=last_segment)
            return SQLLiteral(value=True)

        # Try FluentFunctionTranslator FIRST for functions with dedicated AST builders
        # (prevalenceInterval, status filters, etc.) — these produce optimized SQL
        # that avoids problematic CQL constructs like type-checking.
        fluent_translator = self.context.fluent_translator

        # Get resource_type - first try to extract from source expression (AST),
        # then fall back to context (set during query translation)
        resource_type = self._infer_resource_type(expr.source)
        if resource_type is None:
            resource_type = getattr(self.context, 'resource_type', None)

        # Check if this is a known fluent function with a dedicated AST builder
        if fluent_translator.is_fluent_function(method, resource_type, self.context):
            try:
                return fluent_translator.translate_fluent_call(
                    resource_expr=source,
                    function_name=method,
                    args=args,
                    context=self.context,
                    resource_type=resource_type,
                )
            except NotImplementedError:
                pass  # No AST builder — fall through to inliner

        # Expand-then-translate: try shared FunctionInliner (CQL AST -> CQL AST)
        inliner = self.context.function_inliner
        if inliner:
            expanded_cql = inliner.expand_function(
                method, expr.source, expr.arguments
            )
            if expanded_cql is not None:
                return self.translate(expanded_cql)

        # Default: treat as fluent function call (fallback to function call)
        return SQLFunctionCall(name=method, args=[source] + args)

    def _translate_alias_ref(self, ref: AliasRef, boolean_context: bool = False) -> SQLExpression:
        """Translate an alias reference to SQL."""
        return SQLIdentifier(name=ref.name)

    def _translate_indexer_expression(self, expr: IndexerExpression, boolean_context: bool = False) -> SQLExpression:
        """Translate an indexer expression (array[i]) to SQL."""
        source = self.translate(expr.source, boolean_context=False)
        index = self.translate(expr.index, boolean_context=False)

        # DuckDB uses 1-based indexing, CQL uses 0-based
        adjusted_index = SQLCast(
            expression=SQLBinaryOp(
                operator="+",
                left=index,
                right=SQLLiteral(value=1),
            ),
            target_type="BIGINT",
        )

        # When the source is a JSON string (from json_extract_string, json_extract,
        # fhirpath, or fhirpath_text), convert it to a DuckDB list before calling
        # LIST_EXTRACT.  These UDFs return JSON array text which DuckDB cannot
        # index directly — it must first be parsed into a native list type.
        _json_string_funcs = {
            'json_extract_string', 'json_extract',
        }
        if isinstance(source, SQLFunctionCall) and source.name in _json_string_funcs:
            source = SQLFunctionCall(
                name="from_json",
                args=[source, SQLLiteral(value='["VARCHAR"]')],
            )
        elif isinstance(source, SQLFunctionCall) and source.name == 'fhirpath_text':
            # fhirpath_text returns a single value, not an array — switch to
            # fhirpath() which returns VARCHAR[] for proper indexing
            source = SQLFunctionCall(name='fhirpath', args=source.args)
        # fhirpath/fhirpath_json already return arrays — no conversion needed

        return SQLFunctionCall(name="LIST_EXTRACT", args=[source, adjusted_index])

    def _translate_skip_expression(self, node: SkipExpression, boolean_context: bool = False) -> SQLExpression:
        """Skip first N elements: list_slice(arr, n+1, array_length(arr))."""
        source = self.translate(node.source, boolean_context=False)
        count = self.translate(node.count, boolean_context=False)
        # DuckDB list_slice is 1-based, so skip(n) means start at n+1
        start_idx = SQLBinaryOp(
            operator="+",
            left=count,
            right=SQLLiteral(value=1),
        )
        length = SQLFunctionCall(name="ARRAY_LENGTH", args=[source])
        return SQLFunctionCall(name="LIST_SLICE", args=[source, start_idx, length])

    def _translate_take_expression(self, node: TakeExpression, boolean_context: bool = False) -> SQLExpression:
        """Take first N elements: list_slice(arr, 1, n)."""
        source = self.translate(node.source, boolean_context=False)
        count = self.translate(node.count, boolean_context=False)
        # DuckDB list_slice is 1-based, so take from 1 to n
        return SQLFunctionCall(name="LIST_SLICE", args=[source, SQLLiteral(value=1), count])

    def _translate_first_expression(self, node: FirstExpression, boolean_context: bool = False) -> SQLExpression:
        """Get first element using ROW_NUMBER() window function.

        Uses ROW_NUMBER() OVER (PARTITION BY patient_id ORDER BY ... ASC NULLS LAST, resource_id ASC)
        with deterministic tie-breaking to ensure consistent results.

        For simple list sources (not queries), falls back to list_extract.
        """
        # If source is a Query with sort, use window function for deterministic ordering
        if isinstance(node.source, Query):
            return self._translate_first_last_with_window(node.source, direction="ASC")

        # For non-Query sources, use list_extract (pre-sorted list)
        source = self.translate(node.source, boolean_context=False)
        return SQLFunctionCall(name="LIST_EXTRACT", args=[source, SQLLiteral(value=1)])

    def _translate_last_expression(self, node: LastExpression, boolean_context: bool = False) -> SQLExpression:
        """Get last element using ROW_NUMBER() window function.

        Uses ROW_NUMBER() OVER (PARTITION BY patient_id ORDER BY ... DESC NULLS LAST, resource_id ASC)
        with deterministic tie-breaking to ensure consistent results.

        For simple list sources (not queries), falls back to list_extract.
        """
        # If source is a Query with sort, use window function for deterministic ordering
        if isinstance(node.source, Query):
            return self._translate_first_last_with_window(node.source, direction="DESC")

        # For non-Query sources, use list_extract (pre-sorted list)
        source = self.translate(node.source, boolean_context=False)
        return SQLFunctionCall(name="LIST_EXTRACT", args=[source, SQLLiteral(value=-1)])

    def _translate_distinct_expression(self, node: DistinctExpression) -> SQLExpression:
        """Translate CQL prefix 'distinct expr' to DuckDB list_distinct.

        For definition references, builds a correlated subquery that collects
        values into a list and applies list_distinct.
        """
        from ...parser.ast_nodes import Identifier as CQLIdentifier

        if isinstance(node.source, CQLIdentifier):
            name = node.source.name
            meta = self.context.definition_meta.get(name)
            col = "value"
            if meta:
                col = meta.value_column or "value"
            _outer_pid = self.context.resource_alias or self.context.patient_alias or "p"
            # Build: list_distinct((SELECT COALESCE(LIST(cte.col), []) FROM cte WHERE cte.patient_id = outer.patient_id))
            # Wrap the SELECT in SQLSubquery inside SQLFunctionCall so the CTE builder
            # does not unwrap it (it only unwraps top-level SQLSubquery → SQLSelect).
            inner_select = SQLSelect(
                columns=[SQLFunctionCall(
                    name="COALESCE",
                    args=[
                        SQLFunctionCall(
                            name="LIST",
                            args=[SQLQualifiedIdentifier(parts=["_dq", col])]
                        ),
                        SQLArray(elements=[]),
                    ]
                )],
                from_clause=SQLAlias(
                    expr=SQLIdentifier(name=name, quoted=True),
                    alias="_dq",
                ),
                where=SQLBinaryOp(
                    operator="=",
                    left=SQLQualifiedIdentifier(parts=["_dq", "patient_id"]),
                    right=SQLQualifiedIdentifier(parts=[_outer_pid, "patient_id"]),
                ),
            )
            return SQLFunctionCall(
                name="list_distinct",
                args=[SQLSubquery(query=inner_select)]
            )

        # Generic fallback: translate source as list, apply list_distinct
        source = self.translate(node.source, usage=ExprUsage.LIST)
        if _is_list_returning_sql(source):
            return SQLFunctionCall(name="list_distinct", args=[source])
        return SQLFunctionCall(name="list_distinct",
                               args=[SQLFunctionCall(name="LIST", args=[source])])

    def _translate_first_last_with_window(self, query: Query, direction: str = "ASC") -> SQLExpression:
        """Translate First/Last on a Query using ROW_NUMBER() window function.

        Uses ROW_NUMBER() OVER (PARTITION BY patient_id ORDER BY ... direction NULLS LAST, resource_id ASC)
        with deterministic tie-breaking to ensure consistent results.

        Args:
            query: The CQL Query AST node with optional sort clause.
            direction: "ASC" for First, "DESC" for Last.

        Returns:
            SQLExpression representing the ranked subquery.

        Generated SQL pattern:
            SELECT patient_id, resource
            FROM (
                SELECT
                    patient_id,
                    resource,
                    ROW_NUMBER() OVER (PARTITION BY patient_id ORDER BY sort_col ASC NULLS LAST, resource_id ASC) AS rn
                FROM source
            ) ranked
            WHERE rn = 1
        """
        from ...translator.types import SQLWindowFunction, SQLAlias, SQLSubquery

        # Translate the source query to get the base SELECT
        # We need to wrap it with ROW_NUMBER window function
        source_sql = self.translate(query, boolean_context=False)

        # Extract computed columns from the translated source.
        # If the inner query has a return clause, these will be the computed
        # columns (e.g., date expressions) rather than just resource/*.
        inner_computed_cols = None
        if isinstance(source_sql, SQLSelect):
            inner_computed_cols = source_sql.columns
        elif isinstance(source_sql, SQLSubquery) and isinstance(source_sql.query, SQLSelect):
            inner_computed_cols = source_sql.query.columns

        # Determine the value column name from the source definition
        # If source is RESOURCE_ROWS (has_resource=True), use 'resource'
        # Otherwise use the definition's value_column (typically 'value')
        value_col_name = "resource"
        source_def_name = None
        from ...parser.ast_nodes import QuerySource, Identifier as CQLIdentifier
        src = query.source
        if isinstance(src, list) and len(src) == 1:
            src = src[0]
        if isinstance(src, QuerySource) and src.expression:
            src_expr = src.expression
            if isinstance(src_expr, CQLIdentifier):
                source_def_name = src_expr.name
        if source_def_name:
            source_meta = self.context.definition_meta.get(source_def_name)
            if source_meta and not source_meta.has_resource:
                value_col_name = source_meta.value_column or "value"
            elif source_meta is None:
                # Forward reference — meta not yet available.
                # Check the CQL definition's AST for a return clause.
                # If it has one, the CTE will project scalar 'value', not 'resource'.
                from ...parser.ast_nodes import (
                    Definition as CQLDefinition, Query as CQLQuery, FunctionRef,
                    BinaryExpression as CQLBinaryExpression,
                )
                if hasattr(self.context, '_definition_cql_asts'):
                    cql_ast = self.context._definition_cql_asts.get(source_def_name)
                    if isinstance(cql_ast, CQLQuery) and cql_ast.return_clause is not None:
                        value_col_name = "value"
                    elif isinstance(cql_ast, FunctionRef) and getattr(cql_ast, 'name', '') in ('First', 'Last'):
                        args = getattr(cql_ast, 'arguments', []) or []
                        if args and isinstance(args[0], CQLQuery) and args[0].return_clause is not None:
                            value_col_name = "value"
                    elif isinstance(cql_ast, CQLBinaryExpression) and cql_ast.operator in ('intersect', 'union', 'except'):
                        # intersect/union/except of queries with return clauses yields
                        # scalar 'value' column rows, not FHIR resource rows.
                        def _cql_operand_is_scalar(op: Any) -> bool:
                            if isinstance(op, CQLQuery) and op.return_clause is not None:
                                return True
                            if isinstance(op, CQLIdentifier):
                                op_meta = self.context.definition_meta.get(op.name)
                                if op_meta is not None:
                                    return not op_meta.has_resource
                                op_cql = self.context._definition_cql_asts.get(op.name)
                                if isinstance(op_cql, CQLQuery) and op_cql.return_clause is not None:
                                    return True
                            if isinstance(op, CQLBinaryExpression) and op.operator in ('intersect', 'union', 'except'):
                                return _cql_operand_is_scalar(op.left) and _cql_operand_is_scalar(op.right)
                            return False

                        if _cql_operand_is_scalar(cql_ast.left) and _cql_operand_is_scalar(cql_ast.right):
                            value_col_name = "value"

        # Detect whether the "resource" column actually contains FHIR JSON
        # resources or promoted scalar values (e.g., DateTime from a union of
        # scalar-returning defines where value was renamed to resource).
        source_is_json_resource = (value_col_name == "resource")
        if value_col_name == "resource" and source_def_name is None:
            # Source might be a union of scalar-returning defines.
            from ...parser.ast_nodes import BinaryExpression as CQLBinaryExpression
            src_node = query.source
            if isinstance(src_node, list) and len(src_node) == 1:
                src_node = src_node[0]
            if isinstance(src_node, QuerySource) and src_node.expression:
                src_bin = src_node.expression
                if isinstance(src_bin, CQLBinaryExpression) and src_bin.operator == "union":
                    operand_exprs = [src_bin.left, src_bin.right]
                    all_scalar = True
                    for op_expr in operand_exprs:
                        if isinstance(op_expr, CQLIdentifier):
                            op_meta = self.context.definition_meta.get(op_expr.name)
                            if op_meta is None or op_meta.has_resource:
                                all_scalar = False
                                break
                        else:
                            all_scalar = False
                            break
                    if all_scalar:
                        source_is_json_resource = False

        # Build ORDER BY for window function from query's sort clause
        window_order = []

        # Extract source alias for qualifying bare identifiers in sort expressions
        sort_source_alias = None
        if query.sort:
            from ...parser.ast_nodes import QuerySource
            source_node = query.source
            if isinstance(source_node, list) and len(source_node) == 1:
                source_node = source_node[0]
            if isinstance(source_node, QuerySource):
                sort_source_alias = source_node.alias
            else:
                sort_source_alias = getattr(source_node, 'alias', None)

        # Per design doc §9.4: NULLS LAST for ASC, NULLS FIRST for DESC
        if query.sort:
            for item in query.sort.by:
                if item.expression is None:
                    # CQL `sort asc` without expression means sort by the implicit result.
                    # Check outer query's return clause, or inner source's computed columns
                    sort_cols = None
                    if query.return_clause is not None and isinstance(source_sql, SQLSelect):
                        sort_cols = source_sql.columns
                    elif inner_computed_cols is not None:
                        sort_cols = inner_computed_cols
                    if sort_cols and len(sort_cols) > 0:
                        first_col = sort_cols[0]
                        is_passthrough = (
                            isinstance(first_col, SQLIdentifier)
                            and first_col.name in ("*", "resource")
                            and len(sort_cols) == 1
                        )
                        if not is_passthrough:
                            expr_sql = first_col
                        else:
                            continue
                    else:
                        # No return clause — sort by the value column
                        expr_sql = SQLIdentifier(name=value_col_name)
                else:
                    # In CQL sort clauses, bare identifiers are properties of the source.
                    # Qualify them with the source alias so they resolve correctly.
                    sort_expr = item.expression
                    # When the query has a return clause with a TupleExpression,
                    # sort identifiers may refer to tuple field names (e.g. "AuthorDate")
                    # rather than FHIR properties. Resolve them to the underlying expression.
                    sort_expr = self._resolve_sort_through_tuple_return(sort_expr, query)
                    if sort_source_alias:
                        sort_expr = self._qualify_sort_identifiers(sort_expr, sort_source_alias)
                    expr_sql = self.translate(sort_expr, boolean_context=False)
                # Use the specified direction (or default to parameter direction)
                # For LIMIT 1 approach: Last() needs reversed sort to get last element
                if item.direction:
                    item_dir = item.direction.upper()
                    # When direction is "DESC" (Last), reverse the explicit CQL sort
                    # because LIMIT 1 takes from the top: Last(sort asc) → ORDER BY DESC LIMIT 1
                    if direction == "DESC":
                        item_dir = "DESC" if item_dir == "ASC" else "ASC"
                else:
                    item_dir = direction
                # Add explicit NULLS ordering per design doc §9.4:
                # NULLS LAST for ASC, NULLS FIRST for DESC
                nulls_order = "NULLS FIRST" if item_dir == "DESC" else "NULLS LAST"
                window_order.append((expr_sql, f"{item_dir} {nulls_order}"))

        # Get the FROM clause from the source query
        from_clause = None
        where_sql = None

        # Check for list-returning expressions FIRST, before decomposing.
        # Backbone array queries produce (SELECT list(...) FROM UNNEST(...) ...)
        # which should use list_extract, not the window function path.
        if _is_list_returning_sql(source_sql):
            list_expr = source_sql
            # Apply sorting if the query has a sort clause, but only if the
            # inner list() aggregate doesn't already include ORDER BY (backbone
            # UNNEST queries produce list(x ORDER BY sort_key) directly).
            if query.sort and not _list_has_order_by(source_sql):
                # Use the CQL sort direction, not the First/Last direction.
                # First/Last is handled by list_extract index (1 or -1).
                sort_dir = query.sort.by[0].direction if query.sort.by else "asc"
                list_expr = SQLFunctionCall(
                    name="list_sort",
                    args=[list_expr, SQLLiteral(value=sort_dir.lower())],
                )
            idx = 1 if direction == "ASC" else -1
            return SQLFunctionCall(
                name="list_extract",
                args=[list_expr, SQLLiteral(value=idx)],
            )

        if isinstance(source_sql, SQLSelect):
            from_clause = source_sql.from_clause
            where_sql = source_sql.where
        elif isinstance(source_sql, SQLSubquery) and isinstance(source_sql.query, SQLSelect):
            from_clause = source_sql.query.from_clause
            where_sql = source_sql.query.where
        else:
            # source_sql is not a row-producing SELECT.  Check if it's a
            # list-returning expression — if so, First/Last should extract
            # the first/last element from the list.
            if _is_list_returning_sql(source_sql):
                list_expr = source_sql
                # Apply sorting if the query has a sort clause, but only if the
                # inner list() aggregate doesn't already include ORDER BY.
                if query.sort and not _list_has_order_by(source_sql):
                    # Use the CQL sort direction, not the First/Last direction.
                    sort_dir = query.sort.by[0].direction if query.sort.by else "asc"
                    list_expr = SQLFunctionCall(
                        name="list_sort",
                        args=[list_expr, SQLLiteral(value=sort_dir.lower())],
                    )
                idx = 1 if direction == "ASC" else -1
                return SQLFunctionCall(
                    name="list_extract",
                    args=[list_expr, SQLLiteral(value=idx)],
                )
            # collapse_intervals returns a JSON array string (VARCHAR),
            # not a DuckDB list.  Convert to list so First/Last can extract.
            if (
                isinstance(source_sql, SQLFunctionCall)
                and source_sql.name == "collapse_intervals"
            ):
                list_expr = SQLFunctionCall(
                    name="from_json",
                    args=[source_sql, SQLLiteral(value='["VARCHAR"]')],
                )
                idx = 1 if direction == "ASC" else -1
                return SQLFunctionCall(
                    name="list_extract",
                    args=[list_expr, SQLLiteral(value=idx)],
                )
            # Scalar values cannot be used as FROM clause sources.
            # First/Last on a scalar is identity — return the scalar directly.
            return source_sql

        # Add patient correlation: the subquery must be correlated to the outer
        # _patients CTE (alias "p") so each patient gets their own First/Last value.
        # Determine source alias from the FROM clause for qualification.
        src_alias = None
        if isinstance(from_clause, SQLAlias):
            src_alias = from_clause.alias

        # Add tie-breaker for deterministic ordering
        # Per design doc §9.4 and §7.1 - this guarantees deterministic ordering when multiple
        # rows share the same sort key value.
        # Must be added AFTER src_alias is known so we can qualify the resource column.
        if source_is_json_resource:
            # For actual FHIR RESOURCE_ROWS, use json_extract_string(alias.resource, '$.id')
            res_ref: SQLExpression = (
                SQLQualifiedIdentifier(parts=[src_alias, "resource"])
                if src_alias
                else SQLIdentifier(name="resource")
            )
            tie_breaker = SQLFunctionCall(
                name="json_extract_string",
                args=[res_ref, SQLLiteral(value="$.id")],
            )
            window_order.append((tie_breaker, "ASC NULLS LAST"))
        else:
            # For scalar values (including promoted scalars in "resource" column),
            # use the value column directly as tie-breaker
            tie_breaker = SQLIdentifier(name=value_col_name)
            window_order.append((tie_breaker, "ASC NULLS LAST"))

        patient_corr = SQLBinaryOp(
            left=SQLQualifiedIdentifier(parts=[src_alias, "patient_id"]) if src_alias else SQLIdentifier(name="patient_id"),
            operator="=",
            right=SQLQualifiedIdentifier(parts=["p", "patient_id"]),
        )
        if where_sql is not None:
            where_sql = SQLBinaryOp(left=where_sql, operator="AND", right=patient_corr)
        else:
            where_sql = patient_corr

        # Use ORDER BY ... LIMIT 1 instead of ROW_NUMBER window function
        # This avoids DuckDB's "correlated columns in window functions" error
        # when the ranked query is used as a scalar subquery
        order_by_clauses = []
        for expr_sql, dir_str in window_order:
            order_by_clauses.append((expr_sql, dir_str))

        # If the source query has computed columns (from a return clause on the
        # inner or outer query), use those columns in the result.
        result_columns = [SQLIdentifier(name=value_col_name)]
        # Check both the outer query's return clause and the inner source's columns
        # (the inner query may have a return clause that was already applied)
        cols_to_check = None
        if query.return_clause is not None and isinstance(source_sql, SQLSelect):
            cols_to_check = source_sql.columns
        elif inner_computed_cols is not None:
            cols_to_check = inner_computed_cols
        if cols_to_check:
            first_col = cols_to_check[0]
            is_passthrough = (
                isinstance(first_col, SQLIdentifier)
                and first_col.name in ("*", "resource")
                and len(cols_to_check) == 1
            )
            if not is_passthrough:
                result_columns = list(cols_to_check)

        result_select = SQLSelect(
            columns=result_columns,
            from_clause=from_clause,
            where=where_sql,
            order_by=order_by_clauses,
            limit=1,
        )

        result = SQLSubquery(query=result_select)

        # In audit mode, attach a twin subquery that returns the "winner" resource ID
        # from the same row (same WHERE/ORDER BY/LIMIT 1). This metadata flows through
        # CAST/fhirpath wrappers and is picked up by _maybe_wrap_audit_comparison().
        if getattr(self.context, "audit_mode", False) and source_is_json_resource:
            res_col = (
                SQLQualifiedIdentifier(parts=[src_alias, "resource"])
                if src_alias
                else SQLIdentifier(name="resource")
            )
            from ._operators import _build_resource_id_expr
            id_expr = _build_resource_id_expr(res_col)
            target_select = SQLSelect(
                columns=[id_expr],
                from_clause=from_clause,
                where=where_sql,
                order_by=order_by_clauses,
                limit=1,
            )
            result._audit_target = SQLSubquery(query=target_select)  # type: ignore[attr-defined]

        return result

    def _resolve_sort_through_tuple_return(self, sort_expr: Any, query: Any) -> Any:
        """Resolve sort identifiers through a tuple return clause.

        When a query has `return { Field: expr, ... } sort by Field`, the sort
        identifier 'Field' refers to the tuple field, not a FHIR property.
        This replaces it with the underlying expression from the tuple.
        """
        from ...parser.ast_nodes import (
            Identifier as CQLIdentifier,
            TupleExpression,
        )

        if not isinstance(sort_expr, CQLIdentifier):
            return sort_expr
        rc = getattr(query, "return_clause", None)
        if rc is None:
            return sort_expr
        ret_expr = getattr(rc, "expression", rc)
        if not isinstance(ret_expr, TupleExpression):
            return sort_expr
        for elem in ret_expr.elements:
            if elem.name == sort_expr.name:
                # elem.type holds the value expression (parser reuses type field)
                return elem.type
        return sort_expr

    def _qualify_sort_identifiers(self, expr: Any, alias: str) -> Any:
        """Qualify bare Identifiers in sort expressions with the source alias.

        In CQL sort clauses, bare identifiers like 'effective' refer to properties
        of the query source. This rewrites them as Property(source=Identifier(alias), path=name)
        so they translate correctly.
        """
        from ...parser.ast_nodes import Identifier as CQLIdentifier, Property, MethodInvocation, UnaryExpression

        if isinstance(expr, CQLIdentifier):
            # Bare identifier → property of the source alias
            if not self.context.is_alias(expr.name) and not self.context.lookup_symbol(expr.name):
                return Property(source=CQLIdentifier(name=alias), path=expr.name)
            return expr

        if isinstance(expr, MethodInvocation):
            # Qualify the source of the method invocation
            expr.source = self._qualify_sort_identifiers(expr.source, alias)
            return expr

        if isinstance(expr, UnaryExpression):
            # Qualify the operand
            expr.operand = self._qualify_sort_identifiers(expr.operand, alias)
            return expr

        if isinstance(expr, Property):
            if expr.source:
                expr.source = self._qualify_sort_identifiers(expr.source, alias)
            return expr

        return expr

    def _infer_resource_type(self, expr: Any) -> Optional[str]:
        """Infer the FHIR resource type from an expression.

        This is used to determine appropriate default sort columns for
        First()/Last() operations to ensure deterministic results,
        and for fluent function overload resolution.

        Args:
            expr: An AST expression node.

        Returns:
            The FHIR resource type name (e.g., "Condition", "Observation") or None.
        """
        from ...parser.ast_nodes import Retrieve, Identifier, AliasRef

        # Check if expression is a Retrieve (direct resource access)
        if hasattr(expr, "__class__") and expr.__class__.__name__ == "Retrieve":
            # Try different attribute names for resource type
            return getattr(expr, "type", None) or getattr(expr, "resource_type", None)

        # Check alias resource type mapping (populated during query translation)
        name = getattr(expr, "name", None)
        if name:
            alias_rts = getattr(self.context, '_alias_resource_types', {})
            alias_rt = alias_rts.get(name)
            if alias_rt:
                return alias_rt

        # Check if expression is an Identifier (reference to a definition)
        if isinstance(expr, Identifier) or (hasattr(expr, "name") and not hasattr(expr, "__class__")):
            if name:
                # Check definition metadata for type info
                meta = self.context.definition_meta.get(name)
                if meta and meta.cql_type and meta.cql_type.startswith("List<"):
                    # Extract inner type from List<Type>
                    return meta.cql_type[5:-1]

        return None

    @staticmethod
    def _extract_query_source_resource_type(query_node: Any) -> Optional[str]:
        """Extract the FHIR resource type from a query's source.

        Walks through QuerySource wrappers, Union/BinaryExpression, and Retrieves
        to find the resource/profile type (e.g., 'ConditionProblemsHealthConcerns').
        """
        def _get_retrieve_type(node: Any) -> Optional[str]:
            if node is None:
                return None
            cls_name = getattr(node, '__class__', type(None)).__name__
            if cls_name == 'Retrieve':
                return getattr(node, 'type', None) or getattr(node, 'resource_type', None)
            if cls_name == 'QuerySource':
                return _get_retrieve_type(getattr(node, 'expression', None))
            # BinaryExpression with operator='union'/'intersect'/'except'
            if cls_name == 'BinaryExpression':
                left = getattr(node, 'left', None)
                rt = _get_retrieve_type(left)
                if rt:
                    return rt
                return _get_retrieve_type(getattr(node, 'right', None))
            # Union/Intersect/Except AST nodes (if used)
            if cls_name in ('Union', 'Intersect', 'Except'):
                for op in (getattr(node, 'operands', None) or getattr(node, 'operand', None) or []):
                    if isinstance(op, list):
                        for o in op:
                            rt = _get_retrieve_type(o)
                            if rt:
                                return rt
                    else:
                        rt = _get_retrieve_type(op)
                        if rt:
                            return rt
            return None

        sources = query_node.source if isinstance(query_node.source, list) else [query_node.source]
        for src in sources:
            rt = _get_retrieve_type(src)
            if rt:
                return rt
        return None

    def _is_component_filter_query(self, expr: Any) -> bool:
        """Check if expression is a Query filtering on a component array.

        Detects patterns like:
            BPReading.component BPComponent
                where BPComponent.code ~ "Systolic blood pressure"
                return BPComponent.value as Quantity

        Args:
            expr: An AST expression node.

        Returns:
            True if this is a component filter query, False otherwise.
        """
        if not isinstance(expr, Query):
            return False
        if not expr.where:
            return False
        if not expr.return_clause:
            return False

        # Check if source is a QuerySource with property access on 'component'
        if isinstance(expr.source, QuerySource):
            source_expr = expr.source.expression
            if isinstance(source_expr, Property):
                # Check if the path contains 'component'
                path_lower = source_expr.path.lower()
                return 'component' in path_lower

        return False

    def _is_component_filter_query_no_return(self, expr: Any) -> bool:
        """Check if a Query filters a component array WITHOUT a return clause.

        Detects patterns like:
            (singleton from (X.component C where C.code ~ "Systolic")).value
        where the outer property access provides the implicit return path.
        """
        if not isinstance(expr, Query):
            return False
        if not expr.where:
            return False
        if isinstance(expr.source, QuerySource):
            source_expr = expr.source.expression
            if isinstance(source_expr, Property):
                return 'component' in source_expr.path.lower()
        return False

    def _translate_component_filter_with_outer_path(
        self, query: Query, outer_path: str
    ) -> SQLExpression:
        """Translate a component filter query using the outer property as return path.

        Handles: (singleton from (X.component C where C.code ~ "Systolic")).value
        The query has no return clause; ``outer_path`` (e.g. "value") becomes
        the return path appended to the component.where(...) FHIRPath.
        """
        source_expr = query.source.expression
        source_source = source_expr.source

        # Resolve the resource SQL for the source
        if isinstance(source_source, Identifier):
            source_name = source_source.name
            if self.context.is_alias(source_name):
                symbol = self.context.lookup_symbol(source_name)
                table_alias = getattr(symbol, 'table_alias', None) if symbol else None
                if table_alias:
                    resource_sql = SQLQualifiedIdentifier(parts=[table_alias, "resource"])
                else:
                    resource_sql = self.translate(source_source, boolean_context=False)
            else:
                resource_sql = self.translate(source_source, boolean_context=False)
        else:
            resource_sql = self.translate(source_source, boolean_context=False)

        # Build the where clause filter from the query
        where_expr = query.where.expression if hasattr(query.where, 'expression') else query.where
        code_value = self._extract_component_code_value(query)
        code_display = self._extract_code_display_from_where(where_expr)

        # Build FHIRPath filter
        if code_value:
            where_clause = FHIRPathBuilder.build_code_condition(code_value)
        elif code_display:
            where_clause = FHIRPathBuilder.build_display_condition(code_display)
        else:
            where_clause = "true"

        # Append any unit filters: (C.value as Quantity).unit = 'X'
        unit_filters = self._extract_unit_filters_from_where(where_expr)
        for fhir_path, literal_val in unit_filters:
            escaped = literal_val.replace("'", "\\'")
            where_clause += f" and {fhir_path} = '{escaped}'"

        # Map outer_path to FHIR element path
        return_path_mapping = {
            'value': 'valueQuantity.value',
            'valueQuantity': 'valueQuantity.value',
            'valueString': 'valueString',
            'valueInteger': 'valueInteger',
            'valueCodeableConcept': 'valueCodeableConcept',
        }
        return_path = return_path_mapping.get(outer_path, outer_path)

        base_path = source_expr.path  # "component"
        fhirpath_expr = build_where_return_expr(base_path, where_clause, return_path)

        # Determine function based on the outer path
        if outer_path in ('value', 'valueQuantity', 'valueInteger', 'valueDecimal'):
            func_name = "fhirpath_number"
        elif outer_path in ('valueDate', 'valueDateTime'):
            func_name = "fhirpath_date"
        elif outer_path in ('valueBoolean',):
            func_name = "fhirpath_bool"
        else:
            func_name = "fhirpath_number"  # default for component values

        result = SQLFunctionCall(
            name=func_name,
            args=[resource_sql, SQLLiteral(value=fhirpath_expr)],
        )
        if func_name == "fhirpath_date":
            result = SQLCast(expression=result, target_type="DATE")
        return result

    def _generate_component_fhirpath(
        self,
        query: Query,
        resource_sql: SQLExpression,
    ) -> SQLExpression:
        """Generate FHIRPath expression for filtered component access.

        Transforms a Query like:
            BPReading.component BPComponent
                where BPComponent.code ~ "Systolic blood pressure"
                return BPComponent.value as Quantity

        Into FHIRPath:
            fhirpath_number(resource, 'component.where(code.display = ''Systolic blood pressure'').valueQuantity.value')

        Args:
            query: The Query AST node with component filter.
            resource_sql: SQL expression for the source resource.

        Returns:
            SQL expression with fhirpath function call.
        """
        # Extract the base property path (e.g., "component")
        source_expr = query.source.expression
        base_path = source_expr.path  # e.g., "component"

        # Extract the code filter from where clause
        # Pattern: BPComponent.code ~ "Systolic blood pressure"
        where_expr = query.where.expression
        code_display = self._extract_code_display_from_where(where_expr)

        # Extract the return path (e.g., "value" -> "valueQuantity.value")
        return_expr = query.return_clause.expression
        return_path = self._extract_return_path(return_expr)

        # Determine the fhirpath function based on return type
        # Check if there's a type specifier in the return clause
        func_name = self._infer_fhirpath_func_from_return(query.return_clause)

        # Build the FHIRPath expression
        # component.where(code.display = 'Systolic blood pressure').valueQuantity.value
        if code_display:
            where_clause = FHIRPathBuilder.build_display_condition(code_display)
        else:
            where_clause = "true"

        # Append any unit filters: (C.value as Quantity).unit = 'X'
        unit_filters = self._extract_unit_filters_from_where(where_expr)
        for fhir_path, literal_val in unit_filters:
            escaped = literal_val.replace("'", "\\'")
            where_clause += f" and {fhir_path} = '{escaped}'"

        fhirpath_expr = build_where_return_expr(base_path, where_clause, return_path)

        # Generate the SQL function call
        result = SQLFunctionCall(
            name=func_name,
            args=[resource_sql, SQLLiteral(value=fhirpath_expr)],
        )
        # fhirpath_date returns VARCHAR; wrap in CAST to DATE
        if func_name == "fhirpath_date":
            result = SQLCast(expression=result, target_type="DATE")
        return result

    def _extract_code_display_from_where(self, where_expr: Any) -> Optional[str]:
        """Extract the display string from a where clause like 'C.code ~ "Systolic"'.

        Traverses AND expressions to find the embedded ~ condition.

        Args:
            where_expr: The where clause expression.

        Returns:
            The display string or None if not found.
        """
        # Handle BinaryExpression with ~ operator
        if isinstance(where_expr, BinaryExpression):
            if where_expr.operator == "~":
                # Left side: C.code (Property)
                # Right side: "Systolic blood pressure" (Literal or Identifier)
                right = where_expr.right
                if isinstance(right, Literal):
                    return str(right.value)
                elif isinstance(right, Identifier):
                    return right.name
            # Traverse AND expressions to find embedded ~ condition
            if where_expr.operator == "and":
                left_result = self._extract_code_display_from_where(where_expr.left)
                if left_result:
                    return left_result
                return self._extract_code_display_from_where(where_expr.right)

        return None

    def _extract_unit_filters_from_where(self, where_expr: Any) -> List[Tuple[str, str]]:
        """Extract ``(X.value as Quantity).unit = 'literal'`` conditions.

        Traverses AND expressions and returns a list of
        ``(fhir_path, literal_value)`` pairs.  For example,
        ``(C.value as Quantity).unit = '[hnsf\\'U]'`` yields
        ``("valueQuantity.unit", "[hnsf'U]")``.
        """
        results: List[Tuple[str, str]] = []
        if not isinstance(where_expr, BinaryExpression):
            return results
        if where_expr.operator == "and":
            results.extend(self._extract_unit_filters_from_where(where_expr.left))
            results.extend(self._extract_unit_filters_from_where(where_expr.right))
            return results
        if where_expr.operator != "=":
            return results
        left, right = where_expr.left, where_expr.right
        # Detect (X.value as Quantity).unit pattern
        if isinstance(left, Property) and left.path == "unit":
            src = left.source
            if isinstance(src, BinaryExpression) and src.operator == "as":
                type_spec = src.right
                if isinstance(type_spec, NamedTypeSpecifier) and type_spec.name == "Quantity":
                    # Right side must be a literal
                    if isinstance(right, Literal):
                        results.append(("valueQuantity.unit", str(right.value)))
        return results

    def _extract_quantity_numeric_value(self, qty_call: SQLFunctionCall) -> Optional[SQLExpression]:
        """Extract the numeric value from a parse_quantity() call.

        parse_quantity('{"value": 140.0, "unit": "mm[Hg]", ...}') → SQLLiteral(140.0)
        """
        if qty_call.args and isinstance(qty_call.args[0], SQLLiteral):
            try:
                qty_json = json.loads(qty_call.args[0].value)
                if isinstance(qty_json, dict) and "value" in qty_json:
                    return SQLLiteral(value=qty_json["value"])
            except (json.JSONDecodeError, TypeError):
                pass
        return None

    def _extract_component_code_value(self, query: Query) -> Optional[str]:
        """Return the LOINC-style code string from a component filter query.

        Inspects the where clause (``C.code ~ <ref>``) and resolves the
        right-hand side through the context's code registry so that a
        symbolic name like ``"Systolic blood pressure"`` is mapped back to
        its code value (e.g. ``"8480-6"``).

        Traverses AND expressions to find the embedded ~ condition.

        Returns:
            The code value string, or ``None`` if it cannot be determined.
        """
        if not query.where:
            return None
        where_expr = query.where.expression if hasattr(query.where, 'expression') else query.where
        return self._extract_code_value_from_expr(where_expr)

    def _extract_code_value_from_expr(self, where_expr: Any) -> Optional[str]:
        """Recursively extract code value from a where expression, traversing ANDs."""
        if not isinstance(where_expr, BinaryExpression):
            return None
        if where_expr.operator == "~":
            right = where_expr.right
            if isinstance(right, Literal):
                return str(right.value)
            if isinstance(right, Identifier):
                code_def = self.context.get_code(right.name)
                if code_def and "code" in code_def:
                    return code_def["code"]
            return None
        if where_expr.operator == "and":
            left_result = self._extract_code_value_from_expr(where_expr.left)
            if left_result:
                return left_result
            return self._extract_code_value_from_expr(where_expr.right)
        return None

    def _extract_return_path(self, return_expr: Any) -> str:
        """Extract the FHIRPath from a return expression like 'C.value'.

        Args:
            return_expr: The return clause expression.

        Returns:
            The FHIRPath for the return value.
        """
        # Handle BinaryExpression with 'as' operator (e.g., C.value as Quantity)
        if isinstance(return_expr, BinaryExpression) and return_expr.operator == 'as':
            inner_expr = return_expr.left
            if isinstance(inner_expr, Property):
                return self._extract_return_path(inner_expr)

        # Handle FunctionRef with 'as' operator (e.g., C.value as Quantity)
        if isinstance(return_expr, FunctionRef) and return_expr.name.lower() == 'as':
            if return_expr.arguments:
                # First argument is the actual expression
                inner_expr = return_expr.arguments[0]
                if isinstance(inner_expr, Property):
                    return self._extract_return_path(inner_expr)

        if isinstance(return_expr, Property):
            # Simple property like C.value
            path = return_expr.path
            # Map CQL property names to FHIRPath
            path_mapping = {
                'value': 'valueQuantity.value',
                'valueQuantity': 'valueQuantity.value',
                'valueString': 'valueString',
                'valueInteger': 'valueInteger',
                'valueDecimal': 'valueDecimal',
                'valueBoolean': 'valueBoolean',
                'valueDate': 'valueDate',
                'valueDateTime': 'valueDateTime',
                'valueTime': 'valueTime',
                'valueCodeableConcept': 'valueCodeableConcept',
            }
            return path_mapping.get(path, path)

        return "value"

    def _infer_fhirpath_func_from_return(self, return_clause: Any) -> str:
        """Infer the fhirpath function name from the return clause.

        Args:
            return_clause: The ReturnClause AST node.

        Returns:
            The fhirpath function name (fhirpath_number, fhirpath_text, etc.)
        """
        # Check for type specifier like "return C.value as Quantity"
        # The return expression might have type info
        expr = return_clause.expression

        # Check if there's an 'as' cast in the expression
        # This is often represented as a FunctionRef with name 'as'
        if isinstance(expr, FunctionRef) and expr.name.lower() == 'as':
            if expr.arguments:
                type_arg = expr.arguments[-1] if len(expr.arguments) > 1 else expr.arguments[0]
                if isinstance(type_arg, Identifier):
                    type_name = type_arg.name.lower()
                    if type_name in ('quantity', 'decimal', 'integer', 'int'):
                        return "fhirpath_number"
                    elif type_name in ('string', 'text'):
                        return "fhirpath_text"
                    elif type_name in ('date', 'datetime'):
                        return "fhirpath_date"
                    elif type_name in ('boolean', 'bool'):
                        return "fhirpath_bool"

        # Check the property path for hints
        if isinstance(expr, Property):
            path = expr.path.lower()
            if 'quantity' in path or 'value' in path:
                return "fhirpath_number"
            elif 'date' in path or 'time' in path:
                return "fhirpath_date"
            elif 'string' in path or 'text' in path:
                return "fhirpath_text"

        # Default to fhirpath_number for Quantity values (common case)
        return "fhirpath_number"

    def _apply_singleton_from(self, source: SQLExpression) -> SQLExpression:
        """Apply 'singleton from' semantics to source.

        CQL singleton from semantics: returns the element if there is exactly one,
        returns NULL if there are 0 or more than 1 elements.

        For subqueries over retrieve CTEs (SELECT * FROM "CTE") the LIST_EXTRACT
        pattern fails because the subquery returns multiple columns. In that case,
        rewrite to a cardinality-checking subquery:
            CASE WHEN (SELECT COUNT(*) FROM ...) = 1
                 THEN (SELECT resource FROM ... LIMIT 1)
                 ELSE NULL END

        For array/list expressions, use a similar pattern with array_length.
        """
        # Determine the inner SELECT (works for both SQLSelect and SQLSubquery)
        if isinstance(source, SQLSubquery) and isinstance(source.query, SQLSelect):
            inner = source.query
        elif isinstance(source, SQLSelect):
            inner = source
        else:
            inner = None

        if inner is not None:
            cols = inner.columns
            # For any subquery, use count/value pattern to check cardinality
            # Build count subquery
            count_query = SQLSelect(
                columns=[SQLFunctionCall(name="COUNT", args=[SQLIdentifier(name="*")])],
                from_clause=inner.from_clause,
                where=inner.where,
                joins=inner.joins,
                group_by=inner.group_by,
            )
            # Build value subquery: for SELECT *, narrow to resource column;
            # otherwise keep original columns
            if (cols and len(cols) == 1
                    and isinstance(cols[0], SQLIdentifier)
                    and cols[0].name == "*"):
                value_cols = [SQLIdentifier(name="resource")]
            else:
                value_cols = cols
            value_query = SQLSelect(
                columns=value_cols,
                from_clause=inner.from_clause,
                where=inner.where,
                joins=inner.joins,
                group_by=inner.group_by,
                order_by=inner.order_by,
                limit=1,
            )
            # Add patient_id correlation to prevent cross-patient data leakage
            # when singleton from references a CTE-backed retrieve
            count_query = self._add_patient_id_correlation_to_exists(count_query)
            value_query = self._add_patient_id_correlation_to_exists(value_query)
            return SQLCase(
                when_clauses=[
                    (
                        SQLBinaryOp(
                            operator="=",
                            left=SQLSubquery(query=count_query),
                            right=SQLLiteral(value=1),
                        ),
                        SQLSubquery(query=value_query),
                    )
                ],
                else_clause=SQLNull(),
            )

        # For fhirpath results (JSON strings), use JSON array functions
        if isinstance(source, SQLFunctionCall) and source.name in ('fhirpath_text', 'fhirpath_scalar'):
            return SQLCase(
                when_clauses=[
                    (
                        SQLBinaryOp(
                            operator="=",
                            left=SQLFunctionCall(name="json_array_length", args=[source]),
                            right=SQLLiteral(value=1),
                        ),
                        SQLFunctionCall(name="json_extract_string", args=[source, SQLLiteral(value='$[0]')]),
                    )
                ],
                else_clause=SQLNull(),
            )

        # For array/list expressions, use cardinality check with array_length
        # CASE WHEN array_length(source, 1) = 1 THEN source[1] ELSE NULL END
        return SQLCase(
            when_clauses=[
                (
                    SQLBinaryOp(
                        operator="=",
                        left=SQLFunctionCall(name="array_length", args=[source, SQLLiteral(value=1)]),
                        right=SQLLiteral(value=1),
                    ),
                    SQLFunctionCall(name="LIST_EXTRACT", args=[source, SQLLiteral(value=1)]),
                )
            ],
            else_clause=SQLNull(),
        )

    def _translate_singleton_expression(self, node: SingletonExpression, boolean_context: bool = False) -> SQLExpression:
        """Get single element: list_extract(arr, 1) or scalar subquery with LIMIT 1.

        Special handling for component filter queries:
            singleton from(BPReading.component C where C.code ~ "Systolic" return C.value)
        These are translated to FHIRPath .where() expressions.
        """
        # Check if source is a Query with where on component array
        if self._is_component_filter_query(node.source):
            return self._translate_component_filter_singleton(node.source)

        source = self.translate(node.source, boolean_context=False)
        return self._apply_singleton_from(source)

    def _translate_component_filter_singleton(self, query: Query) -> SQLExpression:
        """Translate a singleton from with component filter.

        When the component filter uses a well-known code (e.g. LOINC 8480-6
        for systolic BP), emit a direct precomputed-column reference instead
        of a nested FHIRPath call.  Unknown codes fall through to the
        FHIRPath-based translation.

        Handles patterns like:
            singleton from(BPReading.component C
                where C.code ~ "Systolic blood pressure"
                return C.value as Quantity
            )

        Args:
            query: The Query AST node with component filter.

        Returns:
            SQL expression – either a precomputed column or a fhirpath call.
        """
        # --- Translate via FHIRPath ---
        # Always use FHIRPath-based extraction for component values rather than
        # precomputed columns, because retrieve CTEs may not have component columns.
        # Get the source expression (e.g., BPReading.component)
        source_expr = query.source.expression
        source_source = source_expr.source  # e.g., BPReading (Identifier)

        # Translate the source to get the resource SQL
        # This could be an Identifier referencing a definition or alias
        if isinstance(source_source, Identifier):
            source_name = source_source.name

            # Check if this is an alias in the current scope
            if self.context.is_alias(source_name):
                symbol = self.context.lookup_symbol(source_name)
                table_alias = getattr(symbol, 'table_alias', None) if symbol else None
                if table_alias:
                    resource_sql = SQLQualifiedIdentifier(parts=[table_alias, "resource"])
                else:
                    # Fall back to translating the source
                    resource_sql = self.translate(source_source, boolean_context=False)
            else:
                # This is a definition reference - translate it
                resource_sql = self.translate(source_source, boolean_context=False)
        else:
            # Translate the source expression
            resource_sql = self.translate(source_source, boolean_context=False)

        # Generate the FHIRPath expression
        return self._generate_component_fhirpath(query, resource_sql)

    def _translate_any_expression(self, node: AnyExpression, boolean_context: bool = False) -> SQLExpression:
        """True if any element matches: use list_any with lambda."""
        source = self.translate(node.source, boolean_context=False)
        # Bind alias in context for condition evaluation
        alias = node.alias or "x"
        # Push alias scope for condition evaluation
        self.context.push_alias_scope(alias)
        try:
            condition = self.translate(node.condition, boolean_context=True)
        finally:
            self.context.pop_alias_scope()
        # Use list_any with lambda - condition SQL becomes the lambda body
        return SQLFunctionCall(name="LIST_ANY", args=[source, SQLLiteral(value=alias), condition])

    def _translate_all_expression(self, node: AllExpression, boolean_context: bool = False) -> SQLExpression:
        """True if all elements match: use list_all with lambda."""
        source = self.translate(node.source, boolean_context=False)
        # Bind alias in context for condition evaluation
        alias = node.alias or "x"
        # Push alias scope for condition evaluation
        self.context.push_alias_scope(alias)
        try:
            condition = self.translate(node.condition, boolean_context=True)
        finally:
            self.context.pop_alias_scope()
        # Use list_all with lambda - condition SQL becomes the lambda body
        return SQLFunctionCall(name="LIST_ALL", args=[source, SQLLiteral(value=alias), condition])

    def _translate_parameter_placeholder(self, placeholder: ParameterPlaceholder, boolean_context: bool = False) -> SQLExpression:
        """Translate a parameter placeholder to SQL.

        ParameterPlaceholder is used during function inlining to carry
        the substituted SQL expression for a function parameter.
        """
        return placeholder.sql_expr

    def _translate_exists_expression(self, node: ExistsExpression, usage: ExprUsage = ExprUsage.LIST) -> SQLExpression:
        """Handle: exists [Condition: "Diabetes"]

        The source should be translated with EXISTS context so that
        Retrieve expressions register JOINs instead of generating subqueries.
        """
        from ...translator.types import SQLUnion

        # For backward compatibility with old callers
        if isinstance(usage, bool):
            usage = ExprUsage.BOOLEAN if usage else ExprUsage.LIST

        # The source should be translated with EXISTS context
        # This allows nested Retrieves to register JOINs
        source = self.translate(node.source, usage=ExprUsage.EXISTS)

        # If source is already an EXISTS (from boolean_context handling), return it directly
        if isinstance(source, SQLExists):
            return source

        # If source is already a boolean expression (like array_length > 0), return directly
        if isinstance(source, SQLBinaryOp) and source.operator in (">", "<", "=", ">=", "<=", "<>", "!="):
            return source

        # If source is already a null-check or logical expression, it's already boolean
        if isinstance(source, SQLBinaryOp) and source.operator in ("IS NOT", "IS", "AND", "OR"):
            return source

        if isinstance(source, SQLUnaryOp) and source.operator.upper() in ("NOT", "IS NULL", "IS NOT NULL"):
            return source

        # If source is a boolean literal, return it directly (don't wrap FALSE/TRUE with IS NOT NULL)
        if isinstance(source, SQLLiteral) and isinstance(source.value, bool):
            return source

        # If source is a SQLCase (returns scalar), check IS NOT NULL
        if isinstance(source, SQLCase):
            # Optimization: CASE WHEN <cond> THEN <val> ELSE NULL END IS NOT NULL
            # simplifies to just <cond> when <cond> is already boolean.
            # This avoids referencing <val> (which may be a non-existent column
            # like E.type from a query-aliased property access).
            if (
                len(source.when_clauses) == 1
                and isinstance(source.else_clause, SQLNull)
            ):
                cond, _ = source.when_clauses[0]
                if isinstance(cond, SQLFunctionCall) and cond.name == "fhirpath_bool":
                    return cond
                if isinstance(cond, SQLBinaryOp) and cond.operator in ("AND", "OR", "=", "!=", "<>", "IS NOT", "IS"):
                    return cond
            return SQLBinaryOp(
                operator="IS NOT",
                left=source,
                right=SQLNull(),
            )

        # For SQLSubquery, use EXISTS pattern
        if isinstance(source, SQLSubquery):
            inner = source.query if isinstance(source.query, SQLSelect) else None
            if inner:
                inner = self._add_patient_id_correlation_to_exists(inner)
                inner = self._strip_aggregates_for_exists(inner)
                return SQLExists(subquery=SQLSubquery(query=inner))
            return SQLExists(subquery=source)

        # For SQLSelect (query expressions), wrap in EXISTS as subquery
        if isinstance(source, SQLSelect):
            source = self._add_patient_id_correlation_to_exists(source)
            source = self._strip_aggregates_for_exists(source)
            return SQLExists(subquery=SQLSubquery(query=source))

        # For SQLUnion, wrap in EXISTS
        if isinstance(source, SQLUnion):
            # EXISTS (SELECT ... UNION ALL SELECT ...)
            return SQLExists(subquery=SQLSubquery(query=source))

        # If source is a SQLIdentifier (could be a CTE reference), wrap in EXISTS
        if isinstance(source, SQLIdentifier):
            # Create a correlated EXISTS subquery for the CTE
            # Build correlation WHERE clause for patient context
            # Always correlate on patient_id. During translate_library(),
            # patient_alias is None; fall back to "p" which gets fixed up
            # later by replace_qualified_alias in translator.py.
            outer_alias = self.context.patient_alias or "p"
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

            # Use alias "sub" for the CTE to enable correlation
            cte_name = source.name
            exists_select = SQLSelect(
                columns=[SQLLiteral(value=1)],
                from_clause=SQLAlias(
                    expr=SQLIdentifier(name=cte_name, quoted=True),
                    alias="sub",
                ),
                where=correlation_where,
                # No LIMIT 1 - EXISTS stops at first match anyway
            )
            return SQLExists(subquery=SQLSubquery(query=exists_select))

        # For SQLArray (literal lists), use array_length > 0
        if isinstance(source, SQLArray):
            return SQLBinaryOp(
                operator=">",
                left=SQLFunctionCall(name="array_length", args=[source]),
                right=SQLLiteral(value=0),
            )

        # For list/array expressions (jsonConcat, list_filter), use array_length > 0
        # Use type checking instead of to_sql() to avoid issues with placeholders
        if isinstance(source, SQLFunctionCall):
            func_name_lower = source.name.lower()
            if func_name_lower == "jsonconcat" or func_name_lower == "list_filter":
                return SQLBinaryOp(
                    operator=">",
                    left=SQLFunctionCall(name="array_length", args=[source]),
                    right=SQLLiteral(value=0),
                )

        # For scalar JSON values (CASE expressions returning single resource), check IS NOT NULL
        if isinstance(source, SQLCase):
            return SQLBinaryOp(
                operator="IS NOT",
                left=source,
                right=SQLNull(),
            )

        # Default: use IS NOT NULL check for scalar values
        return SQLBinaryOp(
            operator="IS NOT",
            left=source,
            right=SQLNull(),
        )

    def _translate_aggregate_expression(self, node: AggregateExpression, boolean_context: bool = False) -> SQLExpression:
        """
        Handle: Sum([1, 2, 3]), GeometricMean(values), Product(values), Count(X)

        Translates aggregate expressions with shape-aware handling:
        - RESOURCE_ROWS: Use array_length for count, list aggregation for others
        - PATIENT_SCALAR/PATIENT_MULTI_VALUE: Apply aggregate function directly
        - UNKNOWN: Fall back to standard aggregate function
        """
        operator_lower = node.operator.lower()

        # Infer source shape to determine the appropriate translation strategy
        source_shape = self._infer_source_shape(node.source)

        # Translate source with LIST context to get all values
        source = self.translate(node.source, usage=ExprUsage.LIST)

        # Handle special aggregate functions that need custom SQL
        if operator_lower == "geometricmean":
            # GeometricMean: exp(avg(log(value))) for positive numbers
            # Using DuckDB's LOG function (natural logarithm)
            return SQLFunctionCall(
                name="EXP",
                args=[
                    SQLFunctionCall(
                        name="AVG",
                        args=[
                            SQLFunctionCall(name="LOG", args=[source])
                        ]
                    )
                ]
            )

        if operator_lower == "product":
            # Product: exp(sum(log(value))) for positive numbers
            # Using DuckDB's LOG function (natural logarithm)
            return SQLFunctionCall(
                name="EXP",
                args=[
                    SQLFunctionCall(
                        name="SUM",
                        args=[
                            SQLFunctionCall(name="LOG", args=[source])
                        ]
                    )
                ]
            )

        # Handle different aggregate functions based on source shape
        if operator_lower == "count":
            if source_shape == RowShape.RESOURCE_ROWS:
                # For RESOURCE_ROWS, count using array_length on the list result
                return SQLFunctionCall(
                    name="array_length",
                    args=[source],
                )
            else:
                # For UNKNOWN/PATIENT_SCALAR/PATIENT_MULTI_VALUE, use standard COUNT
                # This handles literal lists and other cases correctly
                func_name = node.operator.upper()
                return SQLFunctionCall(
                    name=func_name,
                    args=[source],
                )

        elif operator_lower in ('sum', 'avg', 'min', 'max'):
            # CQL aggregates operate on lists. When the source is an array literal
            # (e.g., Min({a, b})), use DuckDB's list scalar functions to avoid
            # SQL aggregate functions that are forbidden in WHERE clauses.
            if isinstance(source, SQLArray):
                list_func_map = {
                    'min': 'list_min',
                    'max': 'list_max',
                    'sum': 'list_sum',
                    'avg': 'list_avg',
                }
                return SQLFunctionCall(
                    name=list_func_map[operator_lower],
                    args=[source],
                )
            func_name = operator_lower.upper()
            # When source is a multi-row subquery (e.g., Min(from X return Y)),
            # wrap the aggregate in a scalar subquery so it doesn't leak an
            # SQL aggregate into a WHERE clause.
            inner = source
            if isinstance(inner, SQLSubquery):
                inner = inner.query
            if isinstance(inner, SQLSelect):
                if inner.columns:
                    first_col = inner.columns[0]
                    if not isinstance(first_col, SQLAlias):
                        inner.columns[0] = SQLAlias(expr=first_col, alias="_val")
                        col_ref = SQLIdentifier(name="_val")
                    else:
                        col_ref = SQLIdentifier(name=first_col.alias)
                else:
                    col_ref = SQLIdentifier(name="_val")
                return SQLSubquery(query=SQLSelect(
                    columns=[SQLFunctionCall(name=func_name, args=[col_ref])],
                    from_clause=SQLAlias(
                        expr=SQLSubquery(query=inner),
                        alias="_agg",
                    ),
                ))
            return SQLFunctionCall(
                name=func_name,
                args=[source],
            )

        # Standard aggregate functions (fallback)
        func_name = node.operator.upper()
        return SQLFunctionCall(name=func_name, args=[source])


