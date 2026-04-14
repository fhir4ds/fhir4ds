"""
Join pattern translator for CQL With/Without clauses.

This module provides the JoinTranslator class for translating CQL With/Without
clauses to SQL EXISTS/NOT EXISTS subqueries.

CQL Syntax:
    with [Resource] alias such that condition
    without [Resource] alias such that condition

SQL Pattern:
    -- With clause
    AND EXISTS (
        SELECT 1 FROM resources B
        WHERE B.resource_type = 'Resource'
          AND B.patient_ref = A.patient_ref
          AND /* such that condition */
    )

    -- Without clause
    AND NOT EXISTS (
        SELECT 1 FROM resources B
        WHERE B.resource_type = 'Resource'
          AND B.patient_ref = A.patient_ref
          AND /* such that condition */
    )
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from ...parser.ast_nodes import (
    Expression,
    Property,
    Identifier,
    AliasRef,
    BinaryExpression,
    Retrieve,
    WithClause,
)
from ...translator.types import (
    SQLExists,
    SQLSelect,
    SQLSubquery,
    SQLExpression,
    SQLLiteral,
    SQLIdentifier,
    SQLQualifiedIdentifier,
    SQLBinaryOp,
    SQLFunctionCall,
    SQLUnaryOp,
    SQLAlias,
    SQLNull,
)

if TYPE_CHECKING:
    from ...translator.context import SQLTranslationContext


class JoinTranslator:
    """
    Translates CQL With/Without clauses to SQL EXISTS/NOT EXISTS subqueries.

    The JoinTranslator handles the translation of CQL relationship clauses
    (with/without) that define existence constraints between the main query
    source and related resources.

    Example CQL:
        [Observation] O
            with [Condition] C such that C.subject = O.subject
            without [Encounter] E such that E.status = 'finished'

    Generated SQL:
        SELECT O.resource FROM resources O
        WHERE O.resource_type = 'Observation'
          AND EXISTS (
            SELECT 1 FROM resources C
            WHERE C.resource_type = 'Condition'
              AND C.subject = O.subject
          )
          AND NOT EXISTS (
            SELECT 1 FROM resources E
            WHERE E.resource_type = 'Encounter'
              AND E.status = 'finished'
          )
    """

    def __init__(self, context: SQLTranslationContext):
        """
        Initialize the join translator.

        Args:
            context: The translation context for symbol resolution.
        """
        self.context = context

    def translate_with_clause(
        self,
        with_clause: WithClause,
        context: SQLTranslationContext,
        outer_alias: str,
    ) -> SQLExpression:
        """
        Translate a CQL 'with' clause to SQL EXISTS subquery.

        Args:
            with_clause: The WithClause AST node.
            context: The translation context.
            outer_alias: The alias of the outer query source.

        Returns:
            AST node for the EXISTS subquery.
        """
        inner_alias = with_clause.alias

        # Build the inner subquery
        inner_sql = self._build_exists_subquery(
            with_clause=with_clause,
            context=context,
            outer_alias=outer_alias,
            inner_alias=inner_alias,
            negated=False,
        )

        return inner_sql

    def translate_without_clause(
        self,
        without_clause: WithClause,
        context: SQLTranslationContext,
        outer_alias: str,
    ) -> SQLExpression:
        """
        Translate a CQL 'without' clause to SQL NOT EXISTS subquery.

        Args:
            without_clause: The WithClause AST node (with is_without=True).
            context: The translation context.
            outer_alias: The alias of the outer query source.

        Returns:
            AST node for the NOT EXISTS subquery.
        """
        inner_alias = without_clause.alias

        # Build the inner subquery with negation
        inner_sql = self._build_exists_subquery(
            with_clause=without_clause,
            context=context,
            outer_alias=outer_alias,
            inner_alias=inner_alias,
            negated=True,
        )

        return inner_sql

    def _build_exists_subquery(
        self,
        with_clause: WithClause,
        context: SQLTranslationContext,
        outer_alias: str,
        inner_alias: str,
        negated: bool,
    ) -> SQLExpression:
        """
        Build an EXISTS or NOT EXISTS subquery for a with/without clause.

        Args:
            with_clause: The WithClause AST node.
            context: The translation context.
            outer_alias: The alias of the outer query source.
            inner_alias: The alias for the inner query source.
            negated: If True, generate NOT EXISTS; otherwise EXISTS.

        Returns:
            AST node for the (NOT) EXISTS subquery.
        """
        # Get the inner source expression (typically a Retrieve)
        inner_source = with_clause.expression

        # Build the FROM clause for the inner query
        from_clause = self._build_inner_from_clause(inner_source, inner_alias, context)

        # Build the WHERE conditions for the inner query
        where_conditions = []

        # Add resource_type filter if it's a Retrieve
        if isinstance(inner_source, Retrieve):
            resource_type = inner_source.type
            where_conditions.append(
                SQLBinaryOp(
                    operator="=",
                    left=SQLQualifiedIdentifier(parts=[inner_alias, "resource_type"]),
                    right=SQLLiteral(value=resource_type),
                )
            )

            # Add terminology filter if present
            if inner_source.terminology:
                terminology_expr = self._translate_terminology_filter(
                    inner_source, inner_alias, context
                )
                if terminology_expr:
                    where_conditions.append(terminology_expr)

        # Add implicit patient context join if in Patient context
        if context.is_patient_context():
            patient_join = self._build_patient_context_join(
                outer_alias, inner_alias, context
            )
            if patient_join:
                where_conditions.append(patient_join)

        # Translate the "such that" condition
        such_that_expr = self._build_such_that_condition(
            condition=with_clause.such_that,
            outer_alias=outer_alias,
            inner_alias=inner_alias,
            context=context,
        )
        if such_that_expr:
            where_conditions.append(such_that_expr)

        # Combine WHERE conditions using AST
        where_clause = None
        if where_conditions:
            where_clause = where_conditions[0]
            for cond in where_conditions[1:]:
                where_clause = SQLBinaryOp(
                    operator="AND",
                    left=where_clause,
                    right=cond,
                )

        # Build the EXISTS subquery using AST nodes
        exists_select = SQLSelect(
            columns=[SQLLiteral(value=1)],
            from_clause=from_clause,
            where=where_clause,
        )

        exists_node = SQLExists(subquery=SQLSubquery(query=exists_select))

        if negated:
            return SQLUnaryOp(
                operator="NOT",
                operand=exists_node,
                prefix=True,
            )
        return exists_node

    def _build_inner_from_clause(
        self,
        inner_source: Expression,
        inner_alias: str,
        context: SQLTranslationContext,
    ) -> SQLExpression:
        """
        Build the FROM clause for the inner subquery.

        Args:
            inner_source: The source expression (typically Retrieve).
            inner_alias: The alias for the inner source.
            context: The translation context.

        Returns:
            AST node for the FROM clause.
        """
        return SQLAlias(
            expr=SQLIdentifier(name="resources"),
            alias=inner_alias,
            implicit_alias=True,
        )

    def _build_such_that_condition(
        self,
        condition: Expression,
        outer_alias: str,
        inner_alias: str,
        context: SQLTranslationContext,
    ) -> Optional[SQLExpression]:
        """
        Build the SQL condition for the "such that" clause.

        This method translates the CQL condition expression to SQL,
        properly qualifying identifier references with the appropriate
        table alias (outer or inner).

        Args:
            condition: The such_that condition expression.
            outer_alias: The alias of the outer query source.
            inner_alias: The alias of the inner query source.
            context: The translation context.

        Returns:
            SQLExpression node for the condition, or None.
        """
        if condition is None:
            return None

        return self._translate_condition_with_aliases(
            condition, outer_alias, inner_alias, context
        )

    def _translate_condition_with_aliases(
        self,
        expr: Expression,
        outer_alias: str,
        inner_alias: str,
        context: SQLTranslationContext,
    ) -> SQLExpression:
        """
        Translate a condition expression with proper alias qualification.

        Args:
            expr: The expression to translate.
            outer_alias: The outer query alias.
            inner_alias: The inner query alias.
            context: The translation context.

        Returns:
            SQLExpression node for the translated condition.
        """
        if expr is None:
            return SQLNull()

        # Handle binary expressions (most common for conditions)
        if isinstance(expr, BinaryExpression):
            return self._translate_binary_condition(
                expr, outer_alias, inner_alias, context
            )

        # Handle property access
        if isinstance(expr, Property):
            return self._translate_property_condition(
                expr, outer_alias, inner_alias, context
            )

        # Handle simple identifiers (alias references)
        if isinstance(expr, (Identifier, AliasRef)):
            return self._translate_identifier_condition(
                expr, outer_alias, inner_alias, context
            )

        # Fallback: try to translate as a general expression
        return self._translate_general_expression(expr, context)

    def _translate_binary_condition(
        self,
        expr: BinaryExpression,
        outer_alias: str,
        inner_alias: str,
        context: SQLTranslationContext,
    ) -> SQLExpression:
        """
        Translate a binary expression condition.

        Args:
            expr: The BinaryExpression to translate.
            outer_alias: The outer query alias.
            inner_alias: The inner query alias.
            context: The translation context.

        Returns:
            SQLExpression node for the binary condition.
        """
        left_expr = self._translate_condition_operand(
            expr.left, outer_alias, inner_alias, context
        )
        right_expr = self._translate_condition_operand(
            expr.right, outer_alias, inner_alias, context
        )

        operator = self._map_operator(expr.operator)

        return SQLBinaryOp(
            operator=operator,
            left=left_expr,
            right=right_expr,
        )

    def _translate_condition_operand(
        self,
        operand: Expression,
        outer_alias: str,
        inner_alias: str,
        context: SQLTranslationContext,
    ) -> SQLExpression:
        """
        Translate an operand in a condition expression.

        Args:
            operand: The operand expression.
            outer_alias: The outer query alias.
            inner_alias: The inner query alias.
            context: The translation context.

        Returns:
            SQLExpression node for the operand.
        """
        if operand is None:
            return SQLNull()

        # Handle property access
        if isinstance(operand, Property):
            return self._translate_property_operand(
                operand, outer_alias, inner_alias, context
            )

        # Handle identifiers/alias references
        if isinstance(operand, (Identifier, AliasRef)):
            name = operand.name if isinstance(operand, Identifier) else operand.name

            # Check if it's a known alias
            if name == outer_alias:
                return SQLQualifiedIdentifier(parts=[name, "resource"])
            elif name == inner_alias:
                return SQLQualifiedIdentifier(parts=[name, "resource"])

            # Check symbol table for the identifier
            symbol = context.lookup_symbol(name)
            if symbol:
                if symbol.symbol_type == "alias":
                    return SQLQualifiedIdentifier(parts=[name, "resource"])
                # Prefer ast_expr (typed AST node) over sql_expr
                if symbol.ast_expr is not None and isinstance(symbol.ast_expr, SQLExpression):
                    return symbol.ast_expr
                elif symbol.sql_expr:
                    if isinstance(symbol.sql_expr, SQLExpression):
                        return symbol.sql_expr
                    else:
                        raise ValueError(
                            f"Symbol '{name}' has sql_expr of type {type(symbol.sql_expr).__name__} "
                            f"instead of SQLExpression. Upstream code should set ast_expr or "
                            f"use SQLExpression for sql_expr. Value: {symbol.sql_expr!r}"
                        )

            # Check if it's a let variable
            if name in context.let_variables:
                let_val = context.let_variables[name]
                if isinstance(let_val, SQLExpression):
                    return let_val
                raise ValueError(
                    f"Let variable '{name}' has value of type {type(let_val).__name__} "
                    f"instead of SQLExpression. Upstream code should store SQLExpression "
                    f"values in let_variables. Value: {let_val!r}"
                )

            # Default: treat as a string literal value
            return SQLLiteral(value=name)

        # Handle literals
        if isinstance(operand, type(None)):
            return SQLNull()

        # Check for Literal-like objects with a value attribute
        if hasattr(operand, 'value'):
            value = operand.value
            if value is None:
                return SQLNull()
            elif isinstance(value, str):
                return SQLLiteral(value=value)
            elif isinstance(value, bool):
                return SQLLiteral(value=value)
            else:
                return SQLLiteral(value=value)

        # Fallback: translate as general expression
        return self._translate_general_expression(operand, context)

    def _translate_property_operand(
        self,
        prop: Property,
        outer_alias: str,
        inner_alias: str,
        context: SQLTranslationContext,
    ) -> SQLExpression:
        """
        Translate a property access operand.

        Args:
            prop: The Property expression.
            outer_alias: The outer query alias.
            inner_alias: The inner query alias.
            context: The translation context.

        Returns:
            SQLExpression node for the property access.
        """
        path = prop.path
        source = prop.source

        # Determine the source alias
        source_alias = None
        if source is not None:
            if isinstance(source, (Identifier, AliasRef)):
                source_name = source.name
                if source_name == outer_alias:
                    source_alias = outer_alias
                elif source_name == inner_alias:
                    source_alias = inner_alias
                else:
                    source_alias = source_name
        else:
            # Implicit source - use outer alias by default
            source_alias = outer_alias

        # Build fhirpath call using AST
        resource_col = SQLQualifiedIdentifier(parts=[source_alias, "resource"]) if source_alias else SQLIdentifier(name="resource")
        escaped_path = path.replace("'", "''")
        return SQLFunctionCall(
            name="fhirpath_text",
            args=[resource_col, SQLLiteral(value=escaped_path)],
        )

    def _translate_property_condition(
        self,
        prop: Property,
        outer_alias: str,
        inner_alias: str,
        context: SQLTranslationContext,
    ) -> SQLExpression:
        """
        Translate a property access as a boolean condition.

        Args:
            prop: The Property expression.
            outer_alias: The outer query alias.
            inner_alias: The inner query alias.
            context: The translation context.

        Returns:
            SQLExpression node for the property condition.
        """
        # Property in boolean context - check if it exists/truthy
        path = prop.path
        source = prop.source

        # Determine source alias
        source_alias = None
        if source is not None:
            if isinstance(source, (Identifier, AliasRef)):
                source_name = source.name
                if source_name == outer_alias:
                    source_alias = outer_alias
                elif source_name == inner_alias:
                    source_alias = inner_alias
        else:
            source_alias = outer_alias

        resource_col = SQLQualifiedIdentifier(parts=[source_alias, "resource"]) if source_alias else SQLIdentifier(name="resource")
        escaped_path = path.replace("'", "''")

        # Use fhirpath_bool for boolean context
        return SQLFunctionCall(
            name="fhirpath_bool",
            args=[resource_col, SQLLiteral(value=escaped_path)],
        )

    def _translate_identifier_condition(
        self,
        ident: Expression,
        outer_alias: str,
        inner_alias: str,
        context: SQLTranslationContext,
    ) -> SQLExpression:
        """
        Translate an identifier as a condition.

        Args:
            ident: The Identifier or AliasRef expression.
            outer_alias: The outer query alias.
            inner_alias: The inner query alias.
            context: The translation context.

        Returns:
            SQLExpression node for the identifier condition.
        """
        name = ident.name if isinstance(ident, Identifier) else ident.name

        # Check if it's an alias reference
        if name == outer_alias or name == inner_alias:
            return SQLBinaryOp(
                operator="IS NOT",
                left=SQLQualifiedIdentifier(parts=[name, "resource"]),
                right=SQLNull(),
            )

        # Look up in symbol table
        symbol = context.lookup_symbol(name)
        if symbol:
            if symbol.symbol_type == "alias":
                return SQLBinaryOp(
                    operator="IS NOT",
                    left=SQLQualifiedIdentifier(parts=[name, "resource"]),
                    right=SQLNull(),
                )

        # Default
        return SQLIdentifier(name=name)

    def _translate_general_expression(
        self,
        expr: Expression,
        context: SQLTranslationContext,
    ) -> SQLExpression:
        """
        Translate a general expression using the expression translator.

        Args:
            expr: The expression to translate.
            context: The translation context.

        Returns:
            SQLExpression node for the expression.
        """
        # Import here to avoid circular imports
        from ...translator.expressions import ExpressionTranslator

        translator = ExpressionTranslator(context)
        sql_expr = translator.translate(expr, boolean_context=False)
        return sql_expr

    def _translate_terminology_filter(
        self,
        retrieve: Retrieve,
        alias: str,
        context: SQLTranslationContext,
    ) -> Optional[SQLExpression]:
        """
        Build the terminology filter for a Retrieve.

        Args:
            retrieve: The Retrieve expression.
            alias: The table alias.
            context: The translation context.

        Returns:
            SQLExpression node for the terminology filter, or None.
        """
        if not retrieve.terminology:
            return None

        terminology = retrieve.terminology
        property_path = retrieve.terminology_property or "code"

        # Translate the terminology expression
        terminology_expr = self._translate_general_expression(terminology, context)

        # Build the terminology filter using FHIRPath
        escaped_path = property_path.replace("'", "''")

        # For value sets, use the member_of function
        return SQLFunctionCall(
            name="fhirpath_member_of",
            args=[
                SQLQualifiedIdentifier(parts=[alias, "resource"]),
                SQLLiteral(value=escaped_path),
                terminology_expr,
            ],
        )

    def _build_patient_context_join(
        self,
        outer_alias: str,
        inner_alias: str,
        context: SQLTranslationContext,
    ) -> Optional[SQLExpression]:
        """
        Build the implicit patient context join condition.

        In Patient context, resources are implicitly joined on patient reference.

        Args:
            outer_alias: The outer query alias.
            inner_alias: The inner query alias.
            context: The translation context.

        Returns:
            SQLExpression node for the patient join condition, or None.
        """
        # The standard pattern for FHIR resources is joining on patient reference
        # This could be subject, patient, or other reference depending on resource type
        # For simplicity, we use a common pattern

        # Get the patient ID column for the outer query
        outer_subject_ref = SQLFunctionCall(
            name="fhirpath_text",
            args=[SQLQualifiedIdentifier(parts=[outer_alias, "resource"]), SQLLiteral(value="subject.reference")],
        )
        inner_subject_ref = SQLFunctionCall(
            name="fhirpath_text",
            args=[SQLQualifiedIdentifier(parts=[inner_alias, "resource"]), SQLLiteral(value="subject.reference")],
        )
        outer_patient_ref = SQLFunctionCall(
            name="fhirpath_text",
            args=[SQLQualifiedIdentifier(parts=[outer_alias, "resource"]), SQLLiteral(value="patient.reference")],
        )
        inner_patient_ref = SQLFunctionCall(
            name="fhirpath_text",
            args=[SQLQualifiedIdentifier(parts=[inner_alias, "resource"]), SQLLiteral(value="patient.reference")],
        )

        # Build COALESCE-based approach for flexibility
        outer_coalesce = SQLFunctionCall(name="COALESCE", args=[outer_subject_ref, outer_patient_ref])
        inner_coalesce = SQLFunctionCall(name="COALESCE", args=[inner_subject_ref, inner_patient_ref])

        return SQLBinaryOp(
            operator="=",
            left=outer_coalesce,
            right=inner_coalesce,
        )

    def _map_operator(self, operator: str) -> str:
        """
        Map a CQL operator to SQL.

        Args:
            operator: The CQL operator.

        Returns:
            The corresponding SQL operator.
        """
        operator_map = {
            "=": "=",
            "!=": "!=",
            "<>": "!=",
            "<": "<",
            "<=": "<=",
            ">": ">",
            ">=": ">=",
            "and": "AND",
            "or": "OR",
            "not": "NOT",
            "is": "IS",
            "is not": "IS NOT",
            "like": "LIKE",
            "in": "IN",
        }

        return operator_map.get(operator.lower(), operator)


__all__ = ["JoinTranslator"]
