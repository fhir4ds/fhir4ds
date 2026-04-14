"""
SQL pattern generators for CQL aggregation functions.

This module provides the AggregationTranslator class for translating
CQL aggregation constructs to DuckDB SQL.

Key patterns:
- First/Last: ORDER BY ... LIMIT 1
- Singleton from: subquery expecting single row
- Exists: EXISTS subquery
- Count/Sum/Avg/Min/Max: SQL aggregate functions

Reference: docs/PLAN-CQL-TO-SQL-TRANSLATOR.md
"""

from __future__ import annotations

from typing import TYPE_CHECKING, List, Optional, Union

from ...translator.context import ExprUsage
from ...parser.ast_nodes import (
    AggregateExpression,
    ExistsExpression,
    Expression,
    FirstExpression,
    LastExpression,
    Query,
    QuerySource,
    SortClause,
)
from ...translator.types import (
    PRECEDENCE,
    SQLExpression,
    SQLFunctionCall,
    SQLIdentifier,
    SQLLiteral,
    SQLSelect,
    SQLSubquery,
    SQLExists,
    SQLBinaryOp,
    SQLNull,
    SQLQualifiedIdentifier,
    SQLAlias,
    SQLWindowFunction,
)

if TYPE_CHECKING:
    from ...translator.context import SQLTranslationContext
    from ...translator.expressions import ExpressionTranslator


class AggregationTranslator:
    """
    Translates CQL aggregation expressions to SQL.

    Handles:
    - First/Last: ORDER BY ... LIMIT 1 patterns
    - Singleton from: Subquery expecting exactly one row
    - Exists: EXISTS subquery patterns
    - Aggregate functions: Count, Sum, Avg, Min, Max, Median, Mode

    Example SQL patterns:

        First with sort:
        SELECT O.resource FROM resources O
        WHERE O.resource_type = 'Observation'
        ORDER BY fhirpath_text(O.resource, 'effectiveDateTime') DESC
        LIMIT 1

        Singleton from:
        SELECT resource FROM (
          SELECT resource FROM resources WHERE ...
        ) LIMIT 1  -- expects exactly 1

        Exists:
        EXISTS (SELECT 1 FROM resources WHERE ...)

        Count:
        SELECT COUNT(*) FROM resources WHERE ...
    """

    # Supported aggregate functions mapped to SQL equivalents
    AGGREGATE_FUNCTIONS = {
        "count": "COUNT",
        "sum": "SUM",
        "avg": "AVG",
        "min": "MIN",
        "max": "MAX",
        "median": "MEDIAN",  # DuckDB supports MEDIAN
        "mode": "MODE",  # DuckDB supports MODE
        # Statistical functions
        "stddev": "STDDEV",
        "variance": "VARIANCE",
        "stdev": "STDDEV_SAMP",
        "stdevp": "STDDEV_POP",
        "var": "VAR_SAMP",
        "varp": "VAR_POP",
    }

    def __init__(self, context: SQLTranslationContext, expression_translator: ExpressionTranslator):
        """
        Initialize the aggregation translator.

        Args:
            context: The translation context for symbol resolution.
            expression_translator: The expression translator for nested expressions.
        """
        self.context = context
        self.expr_translator = expression_translator

    def translate_first(
        self,
        expr: FirstExpression,
        context: SQLTranslationContext,
        sort_clause: Optional[SortClause] = None,
    ) -> SQLExpression:
        """
        Translate a CQL First expression to SQL.

        First([Observation] O sort by effectiveDateTime desc)
        -> SELECT ... ORDER BY ... ASC LIMIT 1

        Args:
            expr: The FirstExpression AST node.
            context: The translation context.
            sort_clause: Optional sort clause from a query context.

        Returns:
            SQLExpression representing the First operation.
        """
        source = expr.source

        # If source is a Query with sort, we can use the ORDER BY
        if isinstance(source, Query):
            return self._translate_first_query(source, context)

        # If we have a sort clause, use it
        if sort_clause:
            return self._translate_first_with_sort(source, sort_clause, context)

        # Simple first - just get the first element
        # Use array slicing or first function
        source_sql = self.expr_translator.translate(source, usage=ExprUsage.LIST)

        # For DuckDB, use array slicing: arr[1] gets first element (1-indexed)
        return SQLFunctionCall(
            name="list_extract",
            args=[source_sql, SQLLiteral(value=1)],
        )

    def translate_last(
        self,
        expr: LastExpression,
        context: SQLTranslationContext,
        sort_clause: Optional[SortClause] = None,
    ) -> SQLExpression:
        """
        Translate a CQL Last expression to SQL.

        Last([Observation] O sort by effectiveDateTime desc)
        -> SELECT ... ORDER BY ... DESC LIMIT 1

        Args:
            expr: The LastExpression AST node.
            context: The translation context.
            sort_clause: Optional sort clause from a query context.

        Returns:
            SQLExpression representing the Last operation.
        """
        source = expr.source

        # If source is a Query with sort, we can use the ORDER BY (reversed)
        if isinstance(source, Query):
            return self._translate_last_query(source, context)

        # If we have a sort clause, use it (reversed)
        if sort_clause:
            return self._translate_last_with_sort(source, sort_clause, context)

        # Simple last - get the last element
        source_sql = self.expr_translator.translate(source, usage=ExprUsage.LIST)

        # Use array slicing with -1 or list functions
        # DuckDB: arr[array_length(arr)] or arr[-1]
        return SQLFunctionCall(
            name="list_extract",
            args=[
                source_sql,
                SQLFunctionCall(name="array_length", args=[source_sql]),
            ],
        )

    def translate_singleton_from(
        self,
        source: Expression,
        context: SQLTranslationContext,
    ) -> SQLExpression:
        """
        Translate a CQL singleton from expression to SQL.

        singleton from [...] -> expects exactly one element
        Per CQL semantics (design doc §6.2):
        - Returns NULL if collection is empty
        - Returns the single element if collection has exactly 1 element
        - Returns NULL if collection has more than 1 element (cardinality violation)

        Args:
            source: The source expression.
            context: The translation context.

        Returns:
            SQLExpression representing the singleton from operation.
        """
        from ...translator.types import SQLCase

        source_sql = self.expr_translator.translate(source, boolean_context=False)

        # Per CQL semantics: singleton from returns NULL when collection has != 1 element
        # Pattern: CASE WHEN array_length(arr) = 1 THEN arr[1] ELSE NULL END
        #
        # This handles:
        # - Empty list: array_length(arr) = 0, condition false -> NULL
        # - Single element: array_length(arr) = 1, condition true -> arr[1]
        # - Multiple elements: array_length(arr) > 1, condition false -> NULL

        length_check = SQLFunctionCall(name="array_length", args=[source_sql])

        return SQLCase(
            when_clauses=[
                (
                    SQLBinaryOp(
                        operator="=",
                        left=length_check,
                        right=SQLLiteral(value=1),
                        precedence=PRECEDENCE["="],
                    ),
                    SQLFunctionCall(
                        name="list_extract",
                        args=[source_sql, SQLLiteral(value=1)],
                    ),
                ),
            ],
            else_clause=SQLNull(),
        )

    def translate_exists(
        self,
        source: Expression,
        context: SQLTranslationContext,
    ) -> SQLExpression:
        """
        Translate a CQL exists expression to SQL.

        exists [...] -> EXISTS (SELECT 1 FROM ...)
        Or for lists: array_length(arr) > 0
        Or for scalar JSON: IS NOT NULL

        Args:
            source: The source expression.
            context: The translation context.

        Returns:
            SQLExpression representing the exists operation.
        """
        from ...translator.types import SQLCase, SQLNull

        source_sql = self.expr_translator.translate(source, usage=ExprUsage.EXISTS)

        # If source is a Query, wrap in EXISTS subquery
        if isinstance(source, Query):
            subquery = self._build_query_subquery(source, context, select_one=True)
            return SQLExists(subquery=subquery)

        # If already an EXISTS, return directly
        if isinstance(source_sql, SQLExists):
            return source_sql

        # If already a boolean comparison, return directly
        if isinstance(source_sql, SQLBinaryOp) and source_sql.operator in (">", "<", "=", ">=", "<=", "<>", "!="):
            return source_sql

        # If source is a CASE expression, check IS NOT NULL (scalar case)
        if isinstance(source_sql, SQLCase):
            return SQLBinaryOp(
                operator="IS NOT",
                left=source_sql,
                right=SQLNull(),
            )

        # Get the SQL string for pattern matching
        # Check if source contains a placeholder - if so, use default behavior
        from ..placeholder import contains_placeholder
        if contains_placeholder(source_sql):
            # Source has unresolved placeholder - use default IS NOT NULL check
            return SQLBinaryOp(
                operator="IS NOT",
                left=source_sql,
                right=SQLNull(),
            )

        # For list/array expressions (jsonConcat, list_filter), use array_length > 0
        from ..ast_utils import ast_is_list_operation
        if ast_is_list_operation(source_sql):
            length_check = SQLFunctionCall(name="array_length", args=[source_sql])
            return SQLBinaryOp(
                operator=">",
                left=length_check,
                right=SQLLiteral(value=0),
                precedence=PRECEDENCE[">"],
            )

        # For other scalar values, check IS NOT NULL
        return SQLBinaryOp(
            operator="IS NOT",
            left=source_sql,
            right=SQLNull(),
        )

    def translate_aggregate(
        self,
        agg_func: str,
        source: Expression,
        context: SQLTranslationContext,
        distinct: bool = False,
    ) -> SQLExpression:
        """
        Translate a CQL aggregate function to SQL.

        Count, Sum, Min, Max, Avg, Median, Mode

        Args:
            agg_func: The aggregate function name (count, sum, avg, etc.).
            source: The source expression.
            context: The translation context.
            distinct: Whether to use DISTINCT modifier.

        Returns:
            SQLExpression representing the aggregate operation.
        """
        func_upper = self.AGGREGATE_FUNCTIONS.get(agg_func.lower())
        if not func_upper:
            # Unknown aggregate function - pass through
            func_upper = agg_func.upper()

        source_sql = self.expr_translator.translate(source, usage=ExprUsage.LIST)

        # Special handling for COUNT(*)
        if func_upper == "COUNT" and self._should_count_star(source):
            return SQLFunctionCall(name="COUNT", args=[SQLLiteral(value="*")])

        # Build the aggregate function call
        agg_call = SQLFunctionCall(
            name=func_upper,
            args=[source_sql],
            distinct=distinct,
        )

        return agg_call

    def translate_aggregate_expression(
        self,
        expr: AggregateExpression,
        context: SQLTranslationContext,
    ) -> SQLExpression:
        """
        Translate a CQL AggregateExpression to SQL.

        Args:
            expr: The AggregateExpression AST node.
            context: The translation context.

        Returns:
            SQLExpression representing the aggregate operation.
        """
        return self.translate_aggregate(
            agg_func=expr.operator,
            source=expr.source,
            context=context,
        )

    # -------------------------------------------------------------------------
    # Private helper methods
    # -------------------------------------------------------------------------

    def _translate_first_query(
        self,
        query: Query,
        context: SQLTranslationContext,
    ) -> SQLExpression:
        """
        Translate First on a Query expression using window functions.

        Uses ROW_NUMBER() OVER (PARTITION BY patient_ref ORDER BY ...) to get
        one result per patient instead of one globally.
        """
        # Use window function for proper per-patient ordering
        return self._translate_most_recent(query, context, direction="ASC")

    def _translate_last_query(
        self,
        query: Query,
        context: SQLTranslationContext,
    ) -> SQLExpression:
        """
        Translate Last on a Query expression using window functions.

        Uses ROW_NUMBER() OVER (PARTITION BY patient_ref ORDER BY ...) to get
        one result per patient instead of one globally.
        """
        # Use window function for proper per-patient ordering
        return self._translate_most_recent(query, context, direction="DESC")

    def _translate_most_recent(
        self,
        query: Query,
        context: SQLTranslationContext,
        direction: str = "DESC",
    ) -> SQLExpression:
        """
        Generate window function for first/last/most recent patterns.

        Uses ROW_NUMBER() OVER (PARTITION BY patient_ref ORDER BY ...) to get
        one result per patient instead of one globally.

        Args:
            query: The CQL Query AST node.
            context: The translation context.
            direction: "ASC" for First/Earliest, "DESC" for Last/MostRecent/Latest

        Returns:
            SQLExpression representing the ranked subquery.

        Generated SQL pattern:
            SELECT patient_ref, resource
            FROM (
                SELECT
                    patient_ref,
                    resource,
                    ROW_NUMBER() OVER (PARTITION BY patient_ref ORDER BY effective_date DESC, resource->>'id' ASC) AS rn
                FROM observations
            ) ranked
            WHERE rn = 1
        """
        # Build the inner query (source of data)
        from_clause = self._build_from_clause(query.source, context)

        # Handle WHERE clause
        where_sql = None
        if query.where:
            where_sql = self.expr_translator.translate(query.where.expression, usage=ExprUsage.BOOLEAN)

        # Build ORDER BY for window function
        # Per design doc: use NULLS FIRST for DESC, NULLS LAST for ASC
        window_order = []
        if query.sort:
            for item in query.sort.by:
                expr_sql = self.expr_translator.translate(item.expression, boolean_context=False)
                # Use the specified direction (or default to parameter direction)
                if item.direction:
                    item_dir = item.direction.upper()
                else:
                    item_dir = direction
                # Add explicit NULLS ordering per design doc §9.4:
                # NULLS LAST for ASC, NULLS FIRST for DESC
                nulls_order = "NULLS FIRST" if item_dir == "DESC" else "NULLS LAST"
                window_order.append((expr_sql, f"{item_dir} {nulls_order}"))

        # Add tie-breaker: json_extract_string(resource, '$.id') ASC (ensures deterministic results)
        # Per design doc §9.4 and §7.1 - this guarantees deterministic ordering when multiple
        # rows share the same sort key value
        tie_breaker = SQLFunctionCall(
            name="json_extract_string",
            args=[
                SQLIdentifier(name="resource"),
                SQLLiteral(value="$.id"),
            ],
        )
        # Tie-breaker is always ASC NULLS LAST (resource IDs are never NULL, but be explicit)
        window_order.append((tie_breaker, "ASC NULLS LAST"))

        # Build ROW_NUMBER window function
        row_number = SQLWindowFunction(
            function="ROW_NUMBER",
            partition_by=[SQLIdentifier(name="patient_ref")],
            order_by=window_order,
        )

        # Build inner SELECT with window function
        inner_columns = [
            SQLIdentifier(name="patient_ref"),
            SQLIdentifier(name="resource"),
            SQLAlias(expr=row_number, alias="rn"),
        ]

        inner_select = SQLSelect(
            columns=inner_columns,
            from_clause=from_clause,
            where=where_sql,
        )

        # Build outer SELECT that filters rn = 1
        # Use SQLSubquery to keep inner_select as AST (don't call to_sql() during Phase 1)
        outer_select = SQLSelect(
            columns=[
                SQLIdentifier(name="patient_ref"),
                SQLIdentifier(name="resource"),
            ],
            from_clause=SQLAlias(expr=SQLSubquery(query=inner_select), alias="ranked"),
            where=SQLBinaryOp(
                operator="=",
                left=SQLIdentifier(name="rn"),
                right=SQLLiteral(value=1),
            ),
        )

        return SQLSubquery(query=outer_select)

    def _translate_first_with_sort(
        self,
        source: Expression,
        sort_clause: SortClause,
        context: SQLTranslationContext,
    ) -> SQLExpression:
        """Translate First with an explicit sort clause."""
        # Build ORDER BY from sort clause
        order_by = self._build_order_by(sort_clause, context, reverse=False)

        # Build a subquery with ORDER BY ... ASC LIMIT 1
        # This requires wrapping the source in a SELECT
        source_sql = self.expr_translator.translate(source, boolean_context=False)

        select = SQLSelect(
            columns=[SQLLiteral(value="*")],
            from_clause=source_sql if not isinstance(source_sql, SQLSelect) else None,
            order_by=order_by,
            limit=1,
        )

        return SQLSubquery(query=select)

    def _translate_last_with_sort(
        self,
        source: Expression,
        sort_clause: SortClause,
        context: SQLTranslationContext,
    ) -> SQLExpression:
        """Translate Last with an explicit sort clause."""
        # Build ORDER BY from sort clause (reversed)
        order_by = self._build_order_by(sort_clause, context, reverse=True)

        source_sql = self.expr_translator.translate(source, boolean_context=False)

        select = SQLSelect(
            columns=[SQLLiteral(value="*")],
            from_clause=source_sql if not isinstance(source_sql, SQLSelect) else None,
            order_by=order_by,
            limit=1,
        )

        return SQLSubquery(query=select)

    def _build_query_subquery(
        self,
        query: Query,
        context: SQLTranslationContext,
        order_direction: str = "ASC",
        limit: Optional[int] = None,
        select_one: bool = False,
    ) -> SQLSelect:
        """
        Build a SQLSelect subquery from a CQL Query.

        Args:
            query: The CQL Query AST node.
            context: The translation context.
            order_direction: Direction for ORDER BY ('ASC' or 'DESC').
            limit: Optional LIMIT value.
            select_one: If True, select literal 1 (for EXISTS).

        Returns:
            SQLSelect representing the subquery.
        """
        # Handle source(s)
        from_clause = self._build_from_clause(query.source, context)

        # Handle WHERE clause
        where_sql = None
        if query.where:
            where_sql = self.expr_translator.translate(query.where.expression, boolean_context=True)

        # Handle RETURN clause
        if select_one:
            columns: List[SQLExpression] = [SQLLiteral(value=1)]
        elif query.return_clause:
            columns = [self.expr_translator.translate(query.return_clause.expression, boolean_context=False)]
        else:
            columns = [SQLLiteral(value="*")]

        # Handle ORDER BY
        order_by = None
        if query.sort:
            order_by = self._build_order_by(
                query.sort,
                context,
                reverse=(order_direction == "DESC"),
            )

        return SQLSelect(
            columns=columns,
            from_clause=from_clause,
            where=where_sql,
            order_by=order_by,
            limit=limit,
        )

    def _build_from_clause(
        self,
        source: Union[QuerySource, List[QuerySource]],
        context: SQLTranslationContext,
    ) -> Optional[SQLExpression]:
        """Build FROM clause from query source(s)."""
        if isinstance(source, list):
            # Multiple sources - handle as JOIN
            if len(source) == 0:
                return None
            elif len(source) == 1:
                return self._build_single_from(source[0], context)
            else:
                # Cross join multiple sources
                # This is simplified - full implementation would handle proper joins
                return self._build_single_from(source[0], context)
        else:
            return self._build_single_from(source, context)

    def _build_single_from(
        self,
        source: QuerySource,
        context: SQLTranslationContext,
    ) -> SQLExpression:
        """Build FROM clause from a single query source."""
        # Translate the source expression
        source_sql = self.expr_translator.translate(source.expression, boolean_context=False)

        # Add alias if present
        if source.alias:
            if isinstance(source_sql, SQLIdentifier):
                return SQLQualifiedIdentifier(parts=[source_sql.name, source.alias])
            # For complex expressions, the alias is handled in the SQL generation
            return source_sql

        return source_sql

    def _build_order_by(
        self,
        sort_clause: SortClause,
        context: SQLTranslationContext,
        reverse: bool = False,
    ) -> List[tuple]:
        """
        Build ORDER BY list from a sort clause.

        Args:
            sort_clause: The SortClause AST node.
            context: The translation context.
            reverse: If True, reverse the sort directions.

        Returns:
            List of (expression, direction) tuples.
        """
        order_by = []

        for item in sort_clause.by:
            # Translate the sort expression
            expr_sql = self.expr_translator.translate(item.expression, boolean_context=False)

            # Determine direction
            if item.direction:
                direction = item.direction.upper()
            else:
                direction = "ASC"  # Default

            # Reverse if needed (for Last vs First)
            if reverse:
                direction = "DESC" if direction == "ASC" else "ASC"

            order_by.append((expr_sql, direction))

        return order_by

    def _should_count_star(self, source: Expression) -> bool:
        """
        Determine if COUNT(*) should be used instead of COUNT(expr).

        COUNT(*) is used when counting all rows, not specific values.
        """
        # For retrieve expressions and queries, use COUNT(*)
        from ...parser.ast_nodes import Retrieve, Query

        if isinstance(source, (Retrieve, Query)):
            return True

        return False


__all__ = [
    "AggregationTranslator",
]
