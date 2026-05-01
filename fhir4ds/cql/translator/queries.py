"""
Query translation for CQL to SQL.

This module provides the QueryTranslator class that translates
CQL Query expressions to SQL SELECT statements using DuckDB.

Reference: https://cql.hl7.org/05-languagesource.html#query
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Dict, List, Optional, Set, Tuple, Union

from ..parser.ast_nodes import (
    AliasRef,
    BinaryExpression,
    Expression,
    Identifier,
    LetClause,
    Property,
    Query,
    QuerySource,
    Retrieve,
    ReturnClause,
    SortClause,
    SortByItem,
    WhereClause,
    WithClause,
)
from ..translator.types import (
    CTEDefinition,
    PRECEDENCE,
    SQLAlias,
    SQLBinaryOp,
    SQLCast,
    SQLExpression,
    SQLFunctionCall,
    SQLIdentifier,
    SQLJoin,
    SQLLiteral,
    SQLQualifiedIdentifier,
    SQLSelect,
    SQLSubquery,
    SQLExists,
    SQLUnaryOp,
)
from ..translator.context import ExprUsage, RowShape

if TYPE_CHECKING:
    from ..translator.context import SQLTranslationContext
    from ..translator.expressions import ExpressionTranslator




@dataclass
class CTEReference:
    """
    Tracks a reference to a CTE that may need to be joined.

    Extended to include usage context for context-aware translation.
    Supports multiple usages and self-joins.
    """
    cte_name: str
    semantic_alias: str              # CQL alias (E1, E2 for self-joins)
    alias: str                       # SQL alias (j1, j2, etc.)
    usages: Set[ExprUsage] = field(default_factory=set)
    shape: RowShape = RowShape.UNKNOWN
    patient_correlated: bool = True

    # For inter-resource correlation (with...such that)
    correlates_to_alias: Optional[str] = None
    additional_predicates: List["SQLExpression"] = field(default_factory=list)

    @property
    def can_use_distinct(self) -> bool:
        """DISTINCT only safe if ALL usages are EXISTS/BOOLEAN."""
        return self.usages.issubset({ExprUsage.EXISTS, ExprUsage.BOOLEAN})

    @property
    def needs_full_cte(self) -> bool:
        """Needs full CTE (not DISTINCT) if any usage requires resource/value."""
        return ExprUsage.SCALAR in self.usages or ExprUsage.LIST in self.usages


class SQLQueryBuilder:
    """
    Helper class for building SQL queries with proper JOIN tracking.

    Tracks CTE references and converts scalar subqueries to JOINs for
    better query performance (avoids O(n^2) correlated subquery behavior).

    Example transformation:
        Before (slow):
            SELECT p.patient_id,
                   fhirpath_text((SELECT sq.resource FROM _sq_14 sq WHERE sq.patient_ref = p.patient_id), 'status')
            FROM patients p

        After (fast):
            SELECT p.patient_id, fhirpath_text(j1.resource, 'status')
            FROM patients p
            LEFT JOIN _sq_14 j1 ON j1.patient_ref = p.patient_id
    """

    def __init__(self, context: Optional["SQLTranslationContext"] = None):
        """
        Initialize the query builder.

        Args:
            context: Optional translation context for emitting warnings.
        """
        self.cte_references: Dict[Tuple[str, str], CTEReference] = {}
        self.join_counter = 0
        self._use_aggregation_strategy = False
        self._context = context

    def validate_joins(self) -> List[str]:
        """
        Check for Cartesian fanout risk.
        Returns list of warning messages.
        """
        warnings = []

        # Find all RESOURCE_ROWS references that need full CTE (not DISTINCT)
        resource_row_refs = [
            ref for ref in self.cte_references.values()
            if ref.shape == RowShape.RESOURCE_ROWS and ref.needs_full_cte
        ]

        if len(resource_row_refs) > 1:
            names = [r.cte_name for r in resource_row_refs]
            warning_msg = (
                f"Multiple RESOURCE_ROWS CTEs JOINed in same scope: {names}. "
                f"This may cause incorrect row multiplication."
            )
            warnings.append(f"CARTESIAN_FANOUT: {warning_msg}")

            # Emit warning to context if available
            if self._context is not None:
                self._context.warnings.add_performance(
                    message=warning_msg,
                    suggestion="Consider using exists() or Count() to avoid row multiplication"
                )

            self._use_aggregation_strategy = True

        return warnings

    def track_cte_reference(
        self,
        cte_name: str,
        semantic_alias: Optional[str] = None,
        usage: ExprUsage = ExprUsage.SCALAR,
        shape: RowShape = RowShape.UNKNOWN,
    ) -> str:
        """
        Track CTE reference, accumulating usages. Returns SQL alias.

        Args:
            cte_name: Name of the CTE being referenced
            semantic_alias: CQL alias (E1, E2 for self-joins)
            usage: How this reference will be used (SCALAR, BOOLEAN, EXISTS)
            shape: The RowShape of the CTE

        Returns:
            The SQL alias to use for this CTE reference
        """
        # Key by (cte_name, semantic_alias) to support self-joins
        key = (cte_name, semantic_alias or cte_name)

        if key in self.cte_references:
            # Add to existing usages - don't overwrite
            self.cte_references[key].usages.add(usage)
            # Update shape if we have better information
            if shape != RowShape.UNKNOWN:
                self.cte_references[key].shape = shape
            return self.cte_references[key].alias
        else:
            self.join_counter += 1
            alias = f"j{self.join_counter}"
            self.cte_references[key] = CTEReference(
                cte_name=cte_name,
                semantic_alias=semantic_alias or cte_name,
                alias=alias,
                usages={usage},
                shape=shape,
            )
            return alias
    
    def generate_joins(self, patient_alias: str = "_pt") -> List[SQLJoin]:
        """
        Generate JOIN clauses for all tracked CTE references.

        Args:
            patient_alias: Alias for the patients table

        Returns:
            List of SQLJoin objects
        """
        # Check for fanout risk first
        self.validate_joins()

        joins = []
        for ref in self.cte_references.values():
            join = SQLJoin(
                join_type="LEFT",
                table=SQLIdentifier(name=ref.cte_name),
                alias=ref.alias,
                on_condition=SQLBinaryOp(
                    operator="=",
                    left=SQLQualifiedIdentifier(parts=[ref.alias, "patient_id"]),
                    right=SQLQualifiedIdentifier(parts=[patient_alias, "patient_id"]),
                ),
            )
            joins.append(join)
        return joins
    
    def get_column_reference(
        self, cte_name: str, column: str = "resource", semantic_alias: Optional[str] = None
    ) -> SQLQualifiedIdentifier:
        """
        Get a column reference for a tracked CTE.

        Args:
            cte_name: Name of the CTE
            column: Column name (default: "resource")
            semantic_alias: CQL alias for self-join disambiguation

        Returns:
            Qualified identifier (e.g., "j1.resource")
        """
        key = (cte_name, semantic_alias or cte_name)
        ref = self.cte_references.get(key)
        if ref:
            return SQLQualifiedIdentifier(parts=[ref.alias, column])
        return SQLQualifiedIdentifier(parts=[cte_name, column])
    
    def has_references(self) -> bool:
        """Check if any CTE references have been tracked."""
        return len(self.cte_references) > 0
    
    def clear(self) -> None:
        """Clear all tracked references."""
        self.cte_references.clear()
        self.join_counter = 0

    def get_cte_reference(
        self, cte_name: str, semantic_alias: Optional[str] = None
    ) -> Optional["CTEReference"]:
        """Get CTE reference if tracked, None otherwise.

        Args:
            cte_name: The CTE name (may include quotes, e.g., '"Condition"')
            semantic_alias: CQL alias for self-join disambiguation

        Returns:
            CTEReference if the CTE is being JOINed, None otherwise.
        """
        # Normalize name (strip quotes if present)
        normalized = cte_name.strip('"')
        key = (normalized, semantic_alias or normalized)
        return self.cte_references.get(key)


class QueryTranslator:
    """
    Translates CQL Query expressions to SQL SELECT statements.

    CQL queries follow this general pattern:
        [Source] Alias
            let Var: Expression
            where Condition
            return Expression
            sort by Direction

    Key functionality:
    - Query with Where: [Condition] C where C.verified = true -> SELECT with WHERE
    - Let clause: let BP = First([...]) -> CTE or inline subquery
    - Return clause: return C.resource -> SELECT list
    - Multi-source queries: from [A], [B] where ... -> CROSS JOIN or INNER JOIN

    SQL Patterns:
    - Basic: SELECT ... FROM resources WHERE resource_type = 'X' AND patient_ref = $patient_id
    - With alias: Add alias to FROM clause, use in WHERE
    - Let clause: Generate CTE or inline subquery
    - Sort: ORDER BY ... ASC/DESC
    """

    def __init__(self, context: SQLTranslationContext, expr_translator: ExpressionTranslator):
        """
        Initialize the query translator.

        Args:
            context: The translation context for symbol resolution.
            expr_translator: The expression translator for nested expressions.
        """
        self.context = context
        self.expr_translator = expr_translator

    def translate_query(self, query: Query, boolean_context: bool = False) -> SQLExpression:
        """
        Translate a CQL Query expression to SQL.

        Args:
            query: The CQL Query AST node.
            boolean_context: Whether the result will be used in a boolean context.

        Returns:
            The SQL expression representing the query.
        """
        # Normalize source to always be a list
        sources = query.source if isinstance(query.source, list) else [query.source]

        # Track CTEs for let clauses
        ctes: List[CTEDefinition] = []

        # Process let clauses first (generate CTEs)
        if query.let_clauses:
            let_ctes = self._translate_let_clauses(query.let_clauses, sources)
            ctes.extend(let_ctes)

        # Build the main query
        # Translate the primary source
        primary_source = sources[0]
        from_clause, where_conditions = self._translate_source(primary_source)

        # Handle multi-source queries (CROSS JOIN pattern)
        for additional_source in sources[1:]:
            additional_from, additional_where = self._translate_source(additional_source)
            # For multi-source, we use CROSS JOIN (or comma syntax)
            from_clause = SQLBinaryOp(
                operator="CROSS JOIN",
                left=from_clause,
                right=additional_from,
                precedence=PRECEDENCE["PRIMARY"],
            )
            where_conditions.extend(additional_where)

        # Add with clause conditions (EXISTS/NOT EXISTS subqueries)
        if query.with_clauses:
            for with_clause in query.with_clauses:
                with_condition = self._translate_with_clause(with_clause, primary_source.alias)
                where_conditions.append(with_condition)

        # Translate where clause
        if query.where:
            where_sql = self._translate_where(query.where, primary_source.alias)
            if where_sql:
                where_conditions.append(where_sql)

        # Combine all WHERE conditions
        where_clause = None
        if where_conditions:
            where_clause = where_conditions[0]
            for cond in where_conditions[1:]:
                where_clause = SQLBinaryOp(
                    operator="AND",
                    left=where_clause,
                    right=cond,
                    precedence=PRECEDENCE["AND"],
                )

        # Translate return clause
        select_columns = []
        if query.return_clause:
            return_sql = self._translate_return(query.return_clause, primary_source.alias)
            select_columns.append(SQLAlias(expr=return_sql, alias="value"))
        else:
            # Default: select the resource from the primary source
            select_columns.append(
                SQLQualifiedIdentifier(parts=[primary_source.alias, "resource"])
            )

        # Translate sort clause
        order_by = None
        if query.sort:
            order_by = self._translate_sort(query.sort, primary_source.alias)

        # Build the SELECT statement
        select = SQLSelect(
            columns=select_columns,
            from_clause=from_clause,
            where=where_clause,
            order_by=order_by,
        )

        # If we have CTEs, wrap in a WITH clause
        if ctes:
            # For now, return the select with CTEs tracked separately
            # The main translator will assemble the WITH clause
            for cte in ctes:
                self.context.add_cte(cte)

        # In boolean context, we need to check existence
        if boolean_context:
            # Return EXISTS (SELECT 1 FROM ...)
            exists_select = SQLSelect(
                columns=[SQLLiteral(value=1)],
                from_clause=from_clause,
                where=where_clause,
                limit=1,
            )
            return SQLExists(subquery=SQLSubquery(query=exists_select))

        return select

    def _translate_source(
        self, source: QuerySource
    ) -> tuple[SQLExpression, List[SQLExpression]]:
        """
        Translate a query source to SQL FROM clause.

        Args:
            source: The QuerySource AST node.

        Returns:
            A tuple of (from_clause, where_conditions).
        """
        alias = source.alias
        expr = source.expression
        where_conditions: List[SQLExpression] = []

        # Push the alias onto the scope
        self.context.push_scope()
        self.context.add_alias(alias)

        # Handle Retrieve expressions (FHIR resource queries)
        if isinstance(expr, Retrieve):
            return self._translate_retrieve_source(expr, alias, where_conditions)

        # Handle identifier references (existing definitions)
        if isinstance(expr, Identifier):
            return self._translate_identifier_source(expr, alias, where_conditions)

        # Handle property access (nested queries)
        if isinstance(expr, Property):
            return self._translate_property_source(expr, alias, where_conditions)

        # Default: treat as a subquery or table reference
        source_sql = self.expr_translator.translate(expr, boolean_context=False)

        # Store the source SQL with the alias for complex expressions
        # This allows property access on the alias to use the stored expression
        from .types import SQLExpression
        if source_sql and not isinstance(source_sql, (SQLIdentifier, SQLQualifiedIdentifier)):
            # Complex expression - store as AST object (not SQL string) during Phase 1
            # This avoids calling to_sql() on expressions that may contain placeholders
            self.context.add_alias(alias, ast_expr=source_sql)

        return source_sql, where_conditions

    def _translate_retrieve_source(
        self, retrieve: Retrieve, alias: str, where_conditions: List[SQLExpression]
    ) -> tuple[SQLExpression, List[SQLExpression]]:
        """
        Translate a Retrieve expression to SQL FROM clause.

        Args:
            retrieve: The Retrieve AST node.
            alias: The alias for this source.
            where_conditions: List to append additional WHERE conditions.

        Returns:
            A tuple of (from_clause, where_conditions).
        """
        resource_type = retrieve.type

        # Set resource context for property access
        self.context.set_resource_context(alias, resource_type)

        # Base FROM clause: resources table with alias
        # Quote alias to handle reserved words like NULL, TRUE, FALSE
        quoted_alias = f'"{alias}"' if alias.upper() in (
            "NULL", "TRUE", "FALSE", "SELECT", "FROM", "WHERE",
            "AND", "OR", "NOT", "IN", "IS", "LIKE", "BETWEEN",
            "EXISTS", "CASE", "WHEN", "THEN", "ELSE", "END",
            "JOIN", "LEFT", "RIGHT", "INNER", "OUTER", "ON",
            "GROUP", "BY", "HAVING", "ORDER", "ASC", "DESC",
            "LIMIT", "OFFSET", "UNION", "INTERSECT", "EXCEPT",
            "DISTINCT", "ALL", "AS", "WITH", "RECURSIVE"
        ) else alias
        from_clause = SQLIdentifier(name=f"resources AS {quoted_alias}")

        # Add resource type filter
        type_condition = SQLBinaryOp(
            operator="=",
            left=SQLQualifiedIdentifier(parts=[alias, "resource_type"]),
            right=SQLLiteral(value=resource_type),
            precedence=PRECEDENCE["="],
        )
        where_conditions.append(type_condition)

        # Add patient context filter if in Patient context
        if self.context.is_patient_context():
            patient_condition = SQLBinaryOp(
                operator="=",
                left=SQLQualifiedIdentifier(parts=[alias, "patient_ref"]),
                right=SQLCast(
                    expression=SQLFunctionCall(
                        name="getvariable",
                        args=[SQLLiteral(value="patient_id")],
                    ),
                    target_type="VARCHAR",
                ),
                precedence=PRECEDENCE["="],
            )
            where_conditions.append(patient_condition)

        # Handle terminology filter (e.g., [Condition: "Diabetes"])
        if retrieve.terminology:
            terminology_condition = self._translate_terminology_filter(
                retrieve.terminology, alias, retrieve.terminology_property
            )
            if terminology_condition:
                where_conditions.append(terminology_condition)

        return from_clause, where_conditions

    def _translate_identifier_source(
        self, ident: Identifier, alias: str, where_conditions: List[SQLExpression]
    ) -> tuple[SQLExpression, List[SQLExpression]]:
        """
        Translate an identifier source to SQL FROM clause.

        Args:
            ident: The Identifier AST node.
            alias: The alias for this source.
            where_conditions: List to append additional WHERE conditions.

        Returns:
            A tuple of (from_clause, where_conditions).
        """
        name = ident.name

        # Check if this references a known definition
        symbol = self.context.lookup_symbol(name)
        if symbol and symbol.symbol_type == "definition":
            # Reference to a previously defined expression
            # This becomes a subquery or CTE reference
            return SQLIdentifier(name=name), where_conditions

        # Check if this is a resource type name (fallback to Retrieve)
        # Query the schema registry for loaded resource types instead of hardcoding
        fhir_types = set(self.context.fhir_schema.resources.keys()) if self.context.fhir_schema else set()

        if name in fhir_types:
            # Treat as a retrieve
            retrieve = Retrieve(type=name)
            return self._translate_retrieve_source(retrieve, alias, where_conditions)

        # Default: treat as a table/CTE reference
        # Quote alias to handle reserved words like NULL, TRUE, FALSE
        quoted_alias = f'"{alias}"' if alias.upper() in (
            "NULL", "TRUE", "FALSE", "SELECT", "FROM", "WHERE",
            "AND", "OR", "NOT", "IN", "IS", "LIKE", "BETWEEN",
            "EXISTS", "CASE", "WHEN", "THEN", "ELSE", "END",
            "JOIN", "LEFT", "RIGHT", "INNER", "OUTER", "ON",
            "GROUP", "BY", "HAVING", "ORDER", "ASC", "DESC",
            "LIMIT", "OFFSET", "UNION", "INTERSECT", "EXCEPT",
            "DISTINCT", "ALL", "AS", "WITH", "RECURSIVE"
        ) else alias
        return SQLIdentifier(name=f"{name} AS {quoted_alias}"), where_conditions

    def _translate_property_source(
        self, prop: Property, alias: str, where_conditions: List[SQLExpression]
    ) -> tuple[SQLExpression, List[SQLExpression]]:
        """
        Translate a property source to SQL FROM clause.

        This handles cases like:
            (Patient.children) C

        Args:
            prop: The Property AST node.
            alias: The alias for this source.
            where_conditions: List to append additional WHERE conditions.

        Returns:
            A tuple of (from_clause, where_conditions).
        """
        # Translate the property access as the source
        source_sql = self.expr_translator.translate(prop, boolean_context=False)

        # Check if source_sql is already a query and handle appropriately
        if isinstance(source_sql, (SQLSelect, SQLSubquery)):
            subquery = SQLSelect(
                columns=[SQLIdentifier(name="*")],
                from_clause=SQLSubquery(source_sql) if isinstance(source_sql, SQLSelect) else source_sql,
            )
        else:
            subquery = SQLSelect(columns=[source_sql])
        return SQLSubquery(query=subquery), where_conditions

    def _translate_terminology_filter(
        self, terminology: Expression, alias: str, property_name: Optional[str]
    ) -> Optional[SQLExpression]:
        """
        Translate a terminology filter to SQL WHERE condition.

        Args:
            terminology: The terminology expression (valueset reference, code, etc.).
            alias: The source alias.
            property_name: The property to filter on (default: 'code').

        Returns:
            The SQL condition for the terminology filter.
        """
        # Default property is 'code'
        prop = property_name or "code"

        # Translate the terminology reference
        term_sql = self.expr_translator.translate(terminology, boolean_context=False)

        # Build the condition: alias.code in valueset or alias.code = code
        # For value sets, we use the fhirpath_valueset UDF
        if isinstance(term_sql, SQLLiteral) and isinstance(term_sql.value, str):
            # Check if it's a URL (value set reference)
            if term_sql.value.startswith("http"):
                return SQLFunctionCall(
                    name="fhirpath_in_valueset",
                    args=[
                        SQLQualifiedIdentifier(parts=[alias, "resource"]),
                        SQLLiteral(value=prop),
                        term_sql,
                    ],
                )

        # Default: equality check on the property
        return SQLBinaryOp(
            operator="=",
            left=SQLFunctionCall(
                name="fhirpath_text",
                args=[
                    SQLQualifiedIdentifier(parts=[alias, "resource"]),
                    SQLLiteral(value=prop),
                ],
            ),
            right=term_sql,
            precedence=PRECEDENCE["="],
        )

    def _translate_where(
        self, where_clause: WhereClause, primary_alias: str
    ) -> Optional[SQLExpression]:
        """
        Translate a where clause to SQL.

        Args:
            where_clause: The WhereClause AST node.
            primary_alias: The primary source alias for context.

        Returns:
            The SQL WHERE condition.
        """
        # Set the resource context for property resolution
        old_alias = self.context.resource_alias
        self.context.set_resource_context(
            primary_alias, self.context.resource_type or ""
        )

        try:
            # CRITICAL: The condition must be translated with BOOLEAN context.
            # This is a truth test - we need to know if the condition is true.
            condition_sql = self.expr_translator.translate(
                where_clause.expression,
                usage=ExprUsage.BOOLEAN
            )
            return condition_sql
        finally:
            # Restore previous context
            if old_alias:
                self.context.set_resource_context(
                    old_alias, self.context.resource_type or ""
                )
            else:
                self.context.clear_resource_context()

    def _translate_let_clauses(
        self, let_clauses: List[LetClause], sources: List[QuerySource]
    ) -> List[CTEDefinition]:
        """
        Translate let clauses to CTEs.

        Args:
            let_clauses: List of LetClause AST nodes.
            sources: The query sources for context.

        Returns:
            List of CTEDefinition objects.
        """
        ctes = []

        for let_clause in let_clauses:
            alias = let_clause.alias
            expr = let_clause.expression

            # Translate the expression
            expr_sql = self.expr_translator.translate(expr, boolean_context=False)

            # Create a CTE for the let variable
            cte_name = self.context.generate_cte_name(f"let_{alias}")
            cte_select = SQLSelect(
                columns=[(expr_sql, alias)],
            )

            cte = CTEDefinition(
                name=cte_name,
                query=cte_select,
                columns=[alias],
            )
            ctes.append(cte)

            # Register the let variable in context
            self.context.let_variables[alias] = cte_name
            self.context.add_symbol(alias, "let", cte_name)

        return ctes

    def _translate_return(
        self, return_clause: ReturnClause, primary_alias: str
    ) -> SQLExpression:
        """
        Translate a return clause to SQL SELECT column.

        Args:
            return_clause: The ReturnClause AST node.
            primary_alias: The primary source alias for context.

        Returns:
            The SQL expression for the SELECT column.
        """
        # Set the resource context for property resolution
        old_alias = self.context.resource_alias
        self.context.set_resource_context(
            primary_alias, self.context.resource_type or ""
        )

        try:
            # Translate the return expression
            return self.expr_translator.translate(return_clause.expression, boolean_context=False)
        finally:
            # Restore previous context
            if old_alias:
                self.context.set_resource_context(
                    old_alias, self.context.resource_type or ""
                )
            else:
                self.context.clear_resource_context()

    def _translate_sort(
        self, sort_clause: SortClause, primary_alias: str
    ) -> List[tuple]:
        """
        Translate a sort clause to SQL ORDER BY.

        Args:
            sort_clause: The SortClause AST node.
            primary_alias: The primary source alias for context.

        Returns:
            List of (expression, direction) tuples for ORDER BY.
        """
        order_by = []

        # Set the resource context for property resolution
        old_alias = self.context.resource_alias
        self.context.set_resource_context(
            primary_alias, self.context.resource_type or ""
        )

        try:
            for item in sort_clause.by:
                direction = item.direction.upper() if item.direction else "ASC"

                if item.expression:
                    # Translate the sort expression
                    sort_expr = self.expr_translator.translate(
                        item.expression, boolean_context=False
                    )
                else:
                    # Default: sort by resource
                    sort_expr = SQLQualifiedIdentifier(parts=[primary_alias, "resource"])

                order_by.append((sort_expr, direction))

        finally:
            # Restore previous context
            if old_alias:
                self.context.set_resource_context(
                    old_alias, self.context.resource_type or ""
                )
            else:
                self.context.clear_resource_context()

        return order_by

    def _translate_with_clause(
        self, with_clause: WithClause, primary_alias: str
    ) -> SQLExpression:
        """
        Translate a with/without clause to SQL EXISTS/NOT EXISTS.

        For union sources in 'without' clauses, generates multiple NOT EXISTS
        clauses (one per union branch) for better query optimization.

        Args:
            with_clause: The WithClause AST node.
            primary_alias: The primary source alias for correlation.

        Returns:
            The SQL EXISTS or NOT EXISTS expression (or combined expressions for unions).
        """
        # Build a subquery for the with clause
        alias = with_clause.alias
        expr = with_clause.expression
        such_that = with_clause.such_that

        # Check if this is a union expression and we need multiple NOT EXISTS
        if with_clause.is_without and self._is_union_expression(expr):
            # For 'without' with union source, generate multiple NOT EXISTS clauses
            return self._translate_without_union(
                expr, alias, such_that, primary_alias, with_clause.is_without
            )

        # Push scope for the with clause alias
        self.context.push_scope()
        self.context.add_alias(alias)

        try:
            # Translate the source expression
            if isinstance(expr, Retrieve):
                from_clause, where_conditions = self._translate_retrieve_source(
                    expr, alias, []
                )
            else:
                source_sql = self.expr_translator.translate(expr, boolean_context=False)
                from_clause = source_sql
                where_conditions = []

            # Translate the such_that condition
            if such_that:
                such_that_sql = self.expr_translator.translate(such_that, boolean_context=True)
                where_conditions.append(such_that_sql)

            # Combine WHERE conditions
            where_clause = None
            if where_conditions:
                where_clause = where_conditions[0]
                for cond in where_conditions[1:]:
                    where_clause = SQLBinaryOp(
                        operator="AND",
                        left=where_clause,
                        right=cond,
                        precedence=PRECEDENCE["AND"],
                    )

            # Build the EXISTS subquery
            exists_select = SQLSelect(
                columns=[SQLLiteral(value=1)],
                from_clause=from_clause,
                where=where_clause,
            )

            if with_clause.is_without:
                # NOT EXISTS for 'without'
                return SQLUnaryOp(
                    operator="NOT",
                    operand=SQLExists(subquery=SQLSubquery(query=exists_select)),
                    prefix=True,
                )
            else:
                # EXISTS for 'with'
                return SQLExists(subquery=SQLSubquery(query=exists_select))

        finally:
            self.context.pop_scope()

    def _is_union_expression(self, expr: Expression) -> bool:
        """
        Check if an expression is a union (or contains unions).

        Args:
            expr: The expression to check.

        Returns:
            True if the expression is a union.
        """
        if isinstance(expr, BinaryExpression):
            return expr.operator.lower() == "union"
        return False

    def _flatten_union_branches(self, expr: Expression) -> List[Expression]:
        """
        Flatten a nested union expression into a list of branches.

        Args:
            expr: The potentially nested union expression.

        Returns:
            List of all union branch expressions.
        """
        branches = []
        if isinstance(expr, BinaryExpression) and expr.operator.lower() == "union":
            # Recursively flatten left and right
            branches.extend(self._flatten_union_branches(expr.left))
            branches.extend(self._flatten_union_branches(expr.right))
        else:
            # Base case: not a union, it's a branch
            branches.append(expr)
        return branches

    def _translate_without_union(
        self,
        union_expr: Expression,
        alias: str,
        such_that: Optional[Expression],
        primary_alias: str,
        is_without: bool,
    ) -> SQLExpression:
        """
        Translate a 'without' clause with union source to multiple NOT EXISTS clauses.

        For CQL: without (A union B union C) X such that condition
        Generate SQL: AND NOT EXISTS (SELECT 1 FROM A ...) AND NOT EXISTS (SELECT 1 FROM B ...) AND NOT EXISTS (SELECT 1 FROM C ...)

        Args:
            union_expr: The union expression.
            alias: The alias for the union branches.
            such_that: The such_that condition.
            primary_alias: The primary source alias.
            is_without: Whether this is a 'without' clause.

        Returns:
            Combined SQL NOT EXISTS expressions.
        """
        # Flatten all union branches
        branches = self._flatten_union_branches(union_expr)

        # Generate NOT EXISTS for each branch
        exists_expressions = []
        for i, branch in enumerate(branches):
            # Use unique alias per branch to avoid collisions
            branch_alias = f"{alias}_{i}" if len(branches) > 1 else alias

            # Push scope for this branch
            self.context.push_scope()
            self.context.add_alias(branch_alias)

            try:
                # Translate the branch source
                if isinstance(branch, Retrieve):
                    from_clause, where_conditions = self._translate_retrieve_source(
                        branch, branch_alias, []
                    )
                else:
                    source_sql = self.expr_translator.translate(branch, boolean_context=False)
                    from_clause = source_sql
                    where_conditions = []

                # Translate the such_that condition (if present)
                # Need to replace alias references with the branch alias
                if such_that:
                    # For multi-branch, we need to ensure the such_that uses the branch alias
                    such_that_sql = self._translate_such_that_with_branch_alias(
                        such_that, primary_alias, branch_alias, alias
                    )
                    where_conditions.append(such_that_sql)

                # Combine WHERE conditions
                where_clause = None
                if where_conditions:
                    where_clause = where_conditions[0]
                    for cond in where_conditions[1:]:
                        where_clause = SQLBinaryOp(
                            operator="AND",
                            left=where_clause,
                            right=cond,
                            precedence=PRECEDENCE["AND"],
                        )

                # Build the EXISTS subquery
                exists_select = SQLSelect(
                    columns=[SQLLiteral(value=1)],
                    from_clause=from_clause,
                    where=where_clause,
                )

                if is_without:
                    # NOT EXISTS for 'without'
                    exists_expr = SQLUnaryOp(
                        operator="NOT",
                        operand=SQLExists(subquery=SQLSubquery(query=exists_select)),
                        prefix=True,
                    )
                else:
                    # EXISTS for 'with'
                    exists_expr = SQLExists(subquery=SQLSubquery(query=exists_select))

                exists_expressions.append(exists_expr)

            finally:
                self.context.pop_scope()

        # Combine all NOT EXISTS with AND
        if len(exists_expressions) == 1:
            return exists_expressions[0]

        combined = exists_expressions[0]
        for expr in exists_expressions[1:]:
            combined = SQLBinaryOp(
                operator="AND",
                left=combined,
                right=expr,
                precedence=PRECEDENCE["AND"],
            )

        return combined

    def _translate_such_that_with_branch_alias(
        self,
        such_that: Expression,
        primary_alias: str,
        branch_alias: str,
        original_alias: str,
    ) -> SQLExpression:
        """
        Translate such_that condition, replacing references to the original alias
        with the branch alias.

        Args:
            such_that: The such_that condition expression.
            primary_alias: The primary source alias.
            branch_alias: The branch-specific alias.
            original_alias: The original alias to replace.

        Returns:
            The translated SQL expression.
        """
        # For now, translate normally - the alias substitution happens
        # automatically because we pushed the branch_alias to the scope
        return self.expr_translator.translate(such_that, boolean_context=True)


__all__ = [
    "QueryTranslator",
]
