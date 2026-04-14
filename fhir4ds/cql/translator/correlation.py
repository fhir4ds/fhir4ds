"""
Correlation and Patient ID mixin for CQLToSQLTranslator.

This module contains methods responsible for correlating subqueries with
patient context and adding patient_id columns during CQL-to-SQL translation.
The ``CorrelationMixin`` class is intended to be used as a mixin with
``CQLToSQLTranslator`` and relies on attributes (``self._context``, etc.)
initialised by the translator's ``__init__``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Dict, List, Optional

if TYPE_CHECKING:
    from ..translator.types import SQLExpression, SQLSelect, SQLUnion, SQLJoin
    from ..translator.context import DefinitionMeta

from ..translator.types import (
    SQLAlias,
    SQLIdentifier,
    SQLNull,
    SQLQualifiedIdentifier,
    SQLRaw,
)
from ..translator.ast_utils import ast_has_patient_id_correlation


class CorrelationMixin:
    """Mixin providing correlation and patient ID methods for CQLToSQLTranslator."""

    def _add_patient_id_to_union(self, union: "SQLUnion") -> "SQLUnion":
        """Add patient_id to each operand in a RESOURCE_ROWS union.

        When status filter wraps a retrieve CTE with SELECT resource FROM ...,
        patient_id gets stripped. This method rewrites each operand by finding
        the innermost SELECT that only has 'resource' and adding 'patient_id'.
        """
        from ..translator.types import (
            SQLSelect, SQLSubquery, SQLIdentifier, SQLAlias, SQLUnion as SQLUnionType
        )
        new_operands = []
        for op in (union.operands or []):
            rewritten = self._add_patient_id_recursive(op)
            new_operands.append(rewritten)
        return SQLUnionType(operands=new_operands, distinct=union.distinct)

    def _add_patient_id_recursive(self, node):
        """Recursively find and fix SELECT that's missing patient_id."""
        from ..translator.types import (
            SQLSelect, SQLSubquery, SQLIdentifier, SQLAlias
        )
        if isinstance(node, SQLSubquery):
            return SQLSubquery(query=self._add_patient_id_recursive(node.query))

        if isinstance(node, SQLSelect):
            # Check if this SELECT already has patient_id
            if self._select_has_patient_id(node):
                return node
            # If columns is empty or SELECT * (single '*' identifier), fix FROM instead
            is_star = (not node.columns) or (
                len(node.columns) == 1
                and isinstance(node.columns[0], SQLIdentifier)
                and node.columns[0].name == '*'
            )
            if is_star and node.from_clause:
                # SELECT * - propagates everything from FROM
                # Fix the FROM clause instead
                if node.from_clause:
                    new_from = self._add_patient_id_recursive(node.from_clause)
                    return SQLSelect(
                        columns=node.columns,
                        from_clause=new_from,
                        where=node.where,
                        joins=node.joins,
                        group_by=node.group_by,
                        having=node.having,
                        order_by=node.order_by,
                        distinct=node.distinct,
                        limit=node.limit,
                    )
                return node
            # Has explicit columns without patient_id - add it
            # But only if the source has patient_id (i.e., FROM a retrieve CTE)
            new_cols = [SQLIdentifier(name="patient_id")] + list(node.columns)
            return SQLSelect(
                columns=new_cols,
                from_clause=node.from_clause,
                where=node.where,
                joins=node.joins,
                group_by=node.group_by,
                having=node.having,
                order_by=node.order_by,
                distinct=node.distinct,
                limit=node.limit,
            )

        if isinstance(node, SQLAlias):
            return SQLAlias(
                expr=self._add_patient_id_recursive(node.expr),
                alias=node.alias,
            )

        return node

    def _wrap_ast_with_patient_id(
        self,
        select: "SQLSelect",
        dep_cte: str,
        dep_has_resource: bool,
        existing_ctes: Dict[str, tuple],
    ) -> tuple:
        """
        Wrap an AST SELECT with patient_id from a dependent CTE.

        This method now uses the AST-based approach when DefinitionMeta is available,
        falling back to string-based logic only when necessary.

        Args:
            select: The SQLSelect AST to wrap.
            dep_cte: The CTE name this depends on (quoted).
            dep_has_resource: Whether the dependency CTE has a resource column.
            existing_ctes: Dictionary of existing CTEs.

        Returns:
            Tuple of (SQLExpression AST, has_resource boolean).
        """
        from ..translator.context import DefinitionMeta

        # Try to get DefinitionMeta for the dependency CTE
        # Strip quotes from dep_cte to get the definition name
        dep_name = dep_cte.strip('"')
        dep_meta = self._context.definition_meta.get(dep_name)

        if dep_meta is not None:
            # Use the new AST-based approach
            wrapped_ast = self._wrap_dependent_ast_with_patient_id(
                select, dep_cte, dep_meta, existing_ctes
            )
            has_resource = dep_meta.has_resource or dep_meta.shape.value == 2  # RESOURCE_ROWS
            return (wrapped_ast, has_resource)

        # Fallback: Create a minimal DefinitionMeta for backward compatibility
        # This handles cases where metadata wasn't recorded during Phase 1
        from ..translator.context import RowShape
        fallback_meta = DefinitionMeta(
            name=dep_name,
            shape=RowShape.RESOURCE_ROWS if dep_has_resource else RowShape.PATIENT_SCALAR,
            has_resource=dep_has_resource,
        )
        wrapped_ast = self._wrap_dependent_ast_with_patient_id(
            select, dep_cte, fallback_meta, existing_ctes
        )
        return (wrapped_ast, dep_has_resource)

    def _modify_ast_retrieve_with_patient_id(self, select: "SQLSelect") -> tuple:
        """
        Modify a retrieve SELECT AST to include patient_id.

        Args:
            select: The SQLSelect AST to modify.

        Returns:
            Tuple of (SQLExpression AST, True for has_resource).
        """
        # Check if patient_ref AS patient_id is already in columns
        has_patient_id = False
        for col in (select.columns or []):
            if isinstance(col, tuple):
                expr, alias = col
                if alias and alias.lower() == 'patient_id':
                    has_patient_id = True
                    break

        if not has_patient_id:
            # Add patient_ref AS patient_id to the columns
            patient_col = (
                SQLQualifiedIdentifier(parts=["r", "patient_ref"]),
                "patient_id"
            )
            if select.columns is None:
                select.columns = []
            # Insert at the beginning
            select.columns.insert(0, patient_col)

        # Ensure the FROM clause uses alias 'r' - fix via AST construction, not string replacement
        if select.from_clause is not None:
            # Check if from_clause is already aliased as 'r'
            if isinstance(select.from_clause, SQLIdentifier):
                # It's just "resources", wrap it with SQLAlias
                select.from_clause = SQLAlias(
                    expr=select.from_clause,
                    alias="r"
                )
            elif isinstance(select.from_clause, SQLRaw):
                # Legacy raw SQL — check if already aliased via AST inspection
                raw = select.from_clause.raw_sql.strip()
                if not isinstance(select.from_clause, SQLAlias):
                    select.from_clause = SQLAlias(
                        expr=SQLIdentifier(name=raw),
                        alias="r"
                    )

        return (select, True)

    def _wrap_ast_boolean_with_patient_id(self, select: "SQLSelect", existing_ctes: Dict[str, tuple]) -> tuple:
        """
        Wrap a boolean SELECT AST with patient_id.

        Args:
            select: The SQLSelect AST to wrap.
            existing_ctes: Dictionary of existing CTEs.

        Returns:
            Tuple of (SQLExpression AST, False for has_resource).
        """
        from ..translator.types import SQLIdentifier

        # If the SELECT already has FROM _patients and JOINs (from scalar subquery conversion),
        # don't wrap it again - just ensure patient_id is in columns and return the SQL directly
        if select.from_clause and isinstance(select.from_clause, SQLIdentifier):
            if select.from_clause.name.lower() == "_patients" and select.joins:
                # Already has proper FROM/JOIN structure - return as-is if patient_id present
                if self._select_has_patient_id(select):
                    return (select, False)

        # Use the new AST-based approach - it handles the wrapping without string conversion
        # The definition meta may be None for boolean expressions that don't have their own CTE
        wrapped_ast = self._wrap_boolean_ast_with_patient_id_v2(select, None, existing_ctes)
        return (wrapped_ast, False)

    # =========================================================================
    # AST-Based Wrapping Methods (Phase 2 CTE Construction)
    # =========================================================================
    # These methods operate on SQLExpression AST nodes and use DefinitionMeta
    # for routing decisions, following the design in DESIGN-CONTEXT-AWARE-TRANSLATION_V2.md
    # section 3.3. They do NOT call to_sql() mid-pipeline.

    def _wrap_dependent_ast_with_patient_id(
        self,
        sql_ast: "SQLExpression",
        dep_cte: str,
        dep_meta: Optional["DefinitionMeta"],
        existing_ctes: Dict[str, tuple],
    ) -> "SQLSelect":
        """
        Wrap a SQL AST expression that depends on another CTE to include patient_id.

        This is the AST-based version of _wrap_dependent_sql_with_patient_id that
        operates on SQLExpression nodes and uses DefinitionMeta for routing decisions.
        It does NOT call to_sql() mid-pipeline.

        Args:
            sql_ast: The SQL expression AST to wrap (e.g., SQLBinaryOp, SQLSelect).
            dep_cte: The CTE name this depends on (quoted).
            dep_meta: The DefinitionMeta for the dependency CTE (may be None).
            existing_ctes: Dictionary of existing CTEs.

        Returns:
            SQLSelect AST node with patient_id included.

        Reference:
            docs/DESIGN-CONTEXT-AWARE-TRANSLATION_V2.md section 3.3
        """
        from ..translator.context import RowShape
        from ..translator.types import (
            SQLSelect, SQLAlias, SQLIdentifier, SQLQualifiedIdentifier,
            SQLBinaryOp, SQLSubquery, SQLNull
        )

        # Determine if the dependency has a resource column
        dep_has_resource = False
        dep_shape = RowShape.UNKNOWN
        if dep_meta is not None:
            dep_has_resource = dep_meta.has_resource
            dep_shape = dep_meta.shape

        # Build: SELECT d.patient_id[, d.resource] FROM dep_cte d WHERE <expr>
        # Use 'd' as the alias for the dependent CTE

        columns: List["SQLExpression"] = [
            SQLQualifiedIdentifier(parts=["d", "patient_id"])
        ]

        # Include resource column if dependency has it
        if dep_has_resource:
            columns.append(SQLQualifiedIdentifier(parts=["d", "resource"]))

        # Build the WHERE clause
        # If sql_ast is a SELECT, wrap it in parentheses via SQLSubquery
        where_expr: Optional["SQLExpression"]
        if isinstance(sql_ast, SQLSelect):
            where_expr = SQLSubquery(query=sql_ast)
        else:
            where_expr = sql_ast

        # Correlate EXISTS subqueries with the outer patient context (using alias 'd')
        # This is the AST equivalent of _correlate_exists_with_patient
        where_expr = self._correlate_exists_ast(where_expr, outer_alias="d")

        # Replace patient_resource references (AST version)
        where_expr = self._replace_patient_resource_ast(where_expr, outer_alias="d")

        return SQLSelect(
            columns=columns,
            from_clause=SQLAlias(
                expr=SQLIdentifier(name=dep_cte, quoted=True),
                alias="d",
            ),
            where=where_expr,
        )

    def _wrap_boolean_ast_with_patient_id_v2(
        self,
        sql_ast: "SQLExpression",
        meta: Optional["DefinitionMeta"],
        existing_ctes: Dict[str, tuple],
    ) -> "SQLSelect":
        """
        Wrap a boolean SQL AST expression to return patient_id.

        This is the AST-based version of _wrap_boolean_sql_with_patient_id that
        operates on SQLExpression nodes and uses DefinitionMeta for routing decisions.
        It does NOT call to_sql() mid-pipeline.

        For boolean definitions (like Initial Population), we want:
        SELECT p.patient_id FROM _patients p WHERE (boolean condition)

        Args:
            sql_ast: The SQL expression AST to wrap (should be boolean-like).
            meta: The DefinitionMeta for this definition (may be None).
            existing_ctes: Dictionary of existing CTEs.

        Returns:
            SQLSelect AST node with patient_id included.

        Reference:
            docs/DESIGN-CONTEXT-AWARE-TRANSLATION_V2.md section 3.3
        """
        from ..translator.context import RowShape
        from ..translator.types import (
            SQLSelect, SQLAlias, SQLIdentifier, SQLQualifiedIdentifier,
            SQLBinaryOp, SQLSubquery
        )

        # Build: SELECT p.patient_id FROM _patients AS p WHERE <expr>

        # Build the WHERE clause
        # If sql_ast is a SELECT, wrap it in parentheses via SQLSubquery
        where_expr: Optional["SQLExpression"]
        if isinstance(sql_ast, SQLSelect):
            where_expr = SQLSubquery(query=sql_ast)
        else:
            where_expr = sql_ast

        # Correlate EXISTS subqueries with the outer patient context (using alias 'p')
        where_expr = self._correlate_exists_ast(where_expr, outer_alias="p")

        # Replace patient_resource references (AST version)
        where_expr = self._replace_patient_resource_ast(where_expr, outer_alias="p")

        # Check if we need CROSS JOIN LATERAL for alias references
        # This handles cases where the expression references query aliases
        lateral_joins = self._detect_lateral_join_needs_ast(where_expr, existing_ctes)

        joins = lateral_joins if lateral_joins else None

        return SQLSelect(
            columns=[SQLQualifiedIdentifier(parts=["p", "patient_id"])],
            from_clause=SQLAlias(
                expr=SQLIdentifier(name="_patients", quoted=False),
                alias="p",
            ),
            where=where_expr,
            joins=joins,
        )

    def _correlate_exists_ast(
        self,
        expr: "SQLExpression",
        outer_alias: str = "p",
    ) -> "SQLExpression":
        """
        Correlate EXISTS subqueries in an AST expression with the outer patient context.

        This walks the AST and modifies EXISTS subqueries that reference CTEs to
        include a correlation condition on patient_id.

        Args:
            expr: The SQL expression AST to process.
            outer_alias: The alias of the outer table with patient_id (e.g., 'p' or 'd').

        Returns:
            Modified SQL expression AST with correlated EXISTS subqueries.
        """
        from ..translator.types import (
            SQLSelect, SQLExists, SQLSubquery, SQLBinaryOp, SQLUnaryOp,
            SQLQualifiedIdentifier, SQLIdentifier, SQLAlias, SQLLiteral,
            SQLUnion, SQLIntersect, SQLExcept,
        )
        from ..translator.context import RowShape

        if isinstance(expr, SQLExists):
            # Process the subquery inside EXISTS
            subquery = expr.subquery
            # Defensively handle cases where subquery is a SQLUnion (not wrapped in SQLSubquery)
            if isinstance(subquery, (SQLUnion, SQLIntersect, SQLExcept)):
                # Wrap the set operation properly and re-process
                return self._correlate_exists_ast(
                    SQLExists(subquery=SQLSubquery(query=subquery)), outer_alias
                )
            if isinstance(subquery, SQLSubquery) and isinstance(subquery.query, (SQLUnion, SQLIntersect, SQLExcept)):
                # EXISTS wrapping a set operation: add patient_id correlation
                # by converting to EXISTS(SELECT 1 FROM (...) AS _u WHERE _u.patient_id = outer.patient_id)
                correlation = SQLBinaryOp(
                    operator="=",
                    left=SQLQualifiedIdentifier(parts=["_u", "patient_id"]),
                    right=SQLQualifiedIdentifier(parts=[outer_alias, "patient_id"]),
                )
                exists_select = SQLSelect(
                    columns=[SQLLiteral(value=1)],
                    from_clause=SQLAlias(
                        expr=SQLSubquery(query=subquery.query),
                        alias="_u",
                    ),
                    where=correlation,
                )
                return SQLExists(subquery=SQLSubquery(query=exists_select))
            if isinstance(subquery, SQLSubquery) and isinstance(subquery.query, SQLSelect):
                inner_select = subquery.query
                # Check if the inner SELECT references a CTE (FROM clause is an identifier or alias)
                from_identifier = None
                from_alias = None
                if isinstance(inner_select.from_clause, SQLIdentifier):
                    from_identifier = inner_select.from_clause.name
                elif isinstance(inner_select.from_clause, SQLAlias) and isinstance(inner_select.from_clause.expr, SQLIdentifier):
                    from_identifier = inner_select.from_clause.expr.name
                    from_alias = inner_select.from_clause.alias
                elif isinstance(inner_select.from_clause, SQLAlias) and isinstance(
                    inner_select.from_clause.expr, (SQLSubquery, SQLUnion, SQLIntersect, SQLExcept)
                ):
                    # FROM clause is a subquery/set operation with alias
                    # (e.g., (SELECT ... UNION SELECT ...) AS HIVDiagnosis)
                    from_alias = inner_select.from_clause.alias
                    if from_alias:
                        from_identifier = from_alias

                if from_identifier is not None:
                    # Use the alias if present, otherwise the CTE name
                    ref_name = from_alias or from_identifier
                    # Check if patient_id correlation already exists
                    # Use specific patient_id check (not general ref check) to
                    # distinguish real correlation from cross-scope property access
                    has_patient_id_corr = False
                    if inner_select.where is not None:
                        if ast_has_patient_id_correlation(inner_select.where, outer_alias):
                            has_patient_id_corr = True

                    # Recurse into WHERE to correlate nested EXISTS
                    # using ref_name as the new outer_alias
                    processed_where = inner_select.where
                    if processed_where is not None:
                        processed_where = self._correlate_exists_ast(processed_where, ref_name)

                    if not has_patient_id_corr:
                        correlation = SQLBinaryOp(
                            operator="=",
                            left=SQLQualifiedIdentifier(parts=[ref_name, "patient_id"]),
                            right=SQLQualifiedIdentifier(parts=[outer_alias, "patient_id"]),
                        )
                        new_where = SQLBinaryOp(
                            operator="AND",
                            left=correlation,
                            right=processed_where,
                        ) if processed_where is not None else correlation
                    else:
                        new_where = processed_where

                    # Non-boolean PATIENT_SCALAR CTEs always emit a row
                    # per patient (with NULL value for non-matches).
                    # Add value IS NOT NULL so EXISTS only matches patients
                    # that actually have data.
                    _cte_name = from_identifier
                    _def_meta = self._context.definition_meta.get(_cte_name)
                    if (_def_meta
                            and _def_meta.shape == RowShape.PATIENT_SCALAR
                            and _def_meta.cql_type != "Boolean"):
                        _val_col = _def_meta.value_column or "resource"
                        _not_null = SQLBinaryOp(
                            operator="IS NOT",
                            left=SQLQualifiedIdentifier(parts=[ref_name, _val_col]),
                            right=SQLNull(),
                        )
                        new_where = SQLBinaryOp(
                            operator="AND",
                            left=new_where,
                            right=_not_null,
                        ) if new_where is not None else _not_null

                    inner_select = SQLSelect(
                        columns=inner_select.columns,
                        from_clause=inner_select.from_clause,
                        joins=inner_select.joins,
                        where=new_where,
                        group_by=inner_select.group_by,
                        having=inner_select.having,
                        order_by=inner_select.order_by,
                        limit=None,  # No LIMIT in EXISTS
                        distinct=inner_select.distinct,
                    )
                    return SQLExists(subquery=SQLSubquery(query=inner_select))
            return expr

        elif isinstance(expr, SQLBinaryOp):
            from ..translator.types import SQLNull as _SQLNull
            # IS NOT NULL / IS NULL on a subquery: "select IS NOT null" is represented as
            # SQLBinaryOp("IS NOT", select, SQLNull) — convert to EXISTS / NOT EXISTS.
            if expr.operator.upper() in ("IS NOT", "IS") and isinstance(expr.right, _SQLNull):
                operand = expr.left
                if isinstance(operand, SQLSelect):
                    operand = SQLSubquery(query=operand)
                if isinstance(operand, SQLSubquery):
                    exists_expr = self._correlate_exists_ast(operand, outer_alias)
                    if expr.operator.upper() == "IS":  # IS NULL → NOT EXISTS
                        return SQLUnaryOp(operator="NOT", operand=exists_expr, prefix=True)
                    return exists_expr  # IS NOT NULL → EXISTS

            # Check if this is a comparison operator with a scalar subquery operand
            # Comparison operators should keep scalar subqueries as-is (with correlation)
            # rather than converting them to EXISTS
            is_comparison = expr.operator in ("<", ">", "<=", ">=", "=", "<>", "!=")

            if is_comparison:
                # For comparisons, process operands but DON'T convert scalar subqueries to EXISTS
                # A scalar subquery in a comparison should remain a scalar subquery
                left = self._correlate_scalar_subquery(expr.left, outer_alias)
                right = self._correlate_scalar_subquery(expr.right, outer_alias)
                return SQLBinaryOp(operator=expr.operator, left=left, right=right)
            else:
                # For other binary operators (AND, OR, etc.), recursively process normally
                return SQLBinaryOp(
                    operator=expr.operator,
                    left=self._correlate_exists_ast(expr.left, outer_alias),
                    right=self._correlate_exists_ast(expr.right, outer_alias),
                )

        elif isinstance(expr, SQLSubquery):
            # Handle subquery that references a CTE - convert to EXISTS
            # This handles cases like (SELECT * FROM "Initial Population") in WHERE clause
            # where the subquery is used as a boolean (not in a comparison)
            if isinstance(expr.query, (SQLUnion, SQLIntersect, SQLExcept)):
                # Subquery wrapping a set operation: delegate to the set-operation handler
                return self._correlate_exists_ast(expr.query, outer_alias)
            if isinstance(expr.query, SQLSelect):
                inner_select = expr.query
                # Check if the inner SELECT references a CTE (FROM clause is identifier or aliased identifier)
                cte_name = None
                cte_alias = None
                if isinstance(inner_select.from_clause, SQLIdentifier):
                    cte_name = inner_select.from_clause.name
                elif isinstance(inner_select.from_clause, SQLAlias) and isinstance(inner_select.from_clause.expr, SQLIdentifier):
                    cte_name = inner_select.from_clause.expr.name
                    cte_alias = inner_select.from_clause.alias

                if cte_name is not None:
                    # Use existing alias if present, or generate one
                    ref_name = cte_alias or "sub"
                    # Convert to EXISTS with correlation
                    correlation = SQLBinaryOp(
                        operator="=",
                        left=SQLQualifiedIdentifier(parts=[ref_name, "patient_id"]),
                        right=SQLQualifiedIdentifier(parts=[outer_alias, "patient_id"]),
                    )
                    from_clause = inner_select.from_clause if cte_alias else SQLAlias(
                        expr=SQLIdentifier(name=cte_name, quoted=True),
                        alias="sub",
                    )
                    # Combine correlation with existing WHERE condition
                    if inner_select.where is not None:
                        new_where = SQLBinaryOp(
                            operator="AND",
                            left=correlation,
                            right=inner_select.where,
                        )
                    else:
                        new_where = correlation
                    exists_select = SQLSelect(
                        columns=[SQLLiteral(value=1)],
                        from_clause=from_clause,
                        joins=inner_select.joins,
                        where=new_where,
                        limit=1,
                    )
                    return SQLExists(subquery=SQLSubquery(query=exists_select))
            return expr

        elif isinstance(expr, SQLSelect):
            # A bare SELECT used in a boolean context (e.g., as an OR branch) should
            # be converted to EXISTS(correlated subquery) when it references a CTE.
            cte_name = None
            cte_alias = None
            if isinstance(expr.from_clause, SQLIdentifier):
                cte_name = expr.from_clause.name
            elif isinstance(expr.from_clause, SQLAlias) and isinstance(expr.from_clause.expr, SQLIdentifier):
                cte_name = expr.from_clause.expr.name
                cte_alias = expr.from_clause.alias

            if cte_name is not None:
                # Delegate to SQLSubquery handler which converts to EXISTS
                return self._correlate_exists_ast(SQLSubquery(query=expr), outer_alias)

            # Fallback: process WHERE clause of nested SELECT (complex FROM clause)
            if expr.where is not None:
                return SQLSelect(
                    columns=expr.columns,
                    from_clause=expr.from_clause,
                    joins=expr.joins,
                    where=self._correlate_exists_ast(expr.where, outer_alias),
                    group_by=expr.group_by,
                    having=expr.having,
                    order_by=expr.order_by,
                    limit=expr.limit,
                    distinct=expr.distinct,
                )
            return expr

        elif isinstance(expr, SQLUnaryOp):
            # IS NOT NULL / IS NULL on a subquery used as a boolean condition:
            # Convert `subquery IS NOT NULL` → EXISTS(correlated subquery)
            # Convert `subquery IS NULL`     → NOT EXISTS(correlated subquery)
            # This fixes the pattern generated by included library OR expressions.
            if not expr.prefix and expr.operator.upper() in ("IS NOT NULL", "IS NULL"):
                operand = expr.operand
                if isinstance(operand, SQLSelect):
                    operand = SQLSubquery(query=operand)
                if isinstance(operand, SQLSubquery):
                    exists_expr = self._correlate_exists_ast(operand, outer_alias)
                    # If recursive call didn't convert to EXISTS (complex FROM clause),
                    # wrap directly — correlation may already be embedded in nested query
                    if isinstance(exists_expr, (SQLSubquery, SQLSelect)):
                        exists_expr = SQLExists(subquery=exists_expr if isinstance(exists_expr, SQLSubquery) else SQLSubquery(query=exists_expr))
                    if expr.operator.upper() == "IS NULL":
                        return SQLUnaryOp(operator="NOT", operand=exists_expr, prefix=True)
                    return exists_expr
            # Prefix NOT: recurse into the operand to correlate inner EXISTS
            if expr.prefix and expr.operator.upper() == "NOT":
                correlated_operand = self._correlate_exists_ast(expr.operand, outer_alias)
                return SQLUnaryOp(operator="NOT", operand=correlated_operand, prefix=True)
            return expr

        elif isinstance(expr, (SQLUnion, SQLIntersect, SQLExcept)):
            # A set operation (UNION/INTERSECT/EXCEPT) used as a boolean expression.
            # Wrap the entire set operation in EXISTS with patient_id correlation.
            # Without this, the UNION lands at the statement level:
            #   SELECT ... WHERE <left> UNION <right>   ← parsed as two statements
            # Instead produce:
            #   SELECT ... WHERE EXISTS (SELECT 1 FROM (...UNION...) AS _u WHERE _u.patient_id = p.patient_id)
            correlation = SQLBinaryOp(
                operator="=",
                left=SQLQualifiedIdentifier(parts=["_u", "patient_id"]),
                right=SQLQualifiedIdentifier(parts=[outer_alias, "patient_id"]),
            )
            exists_select = SQLSelect(
                columns=[SQLLiteral(value=1)],
                from_clause=SQLAlias(
                    expr=SQLSubquery(query=expr),
                    alias="_u",
                ),
                where=correlation,
            )
            return SQLExists(subquery=SQLSubquery(query=exists_select))

        return expr

    def _correlate_scalar_subquery(
        self,
        expr: "SQLExpression",
        outer_alias: str = "p",
    ) -> "SQLExpression":
        """
        Add patient_id correlation to scalar subqueries without converting to EXISTS.

        This is used for scalar subqueries in comparison contexts (e.g., <, >, =, etc.)
        where the subquery must return a value to compare, not a boolean.

        Args:
            expr: The SQL expression AST to process.
            outer_alias: The alias of the outer table with patient_id (e.g., 'p' or 'd').

        Returns:
            Modified SQL expression AST with correlated scalar subqueries.
        """
        from ..translator.types import (
            SQLSelect, SQLSubquery, SQLBinaryOp,
            SQLQualifiedIdentifier, SQLIdentifier, SQLAlias
        )

        if isinstance(expr, SQLSubquery):
            if isinstance(expr.query, SQLSelect):
                inner_select = expr.query
                # Check if the inner SELECT references a CTE (FROM clause is an identifier)
                if isinstance(inner_select.from_clause, SQLIdentifier):
                    cte_name = inner_select.from_clause.name
                    # Add correlation condition to the subquery
                    correlation = SQLBinaryOp(
                        operator="=",
                        left=SQLQualifiedIdentifier(parts=["sub", "patient_id"]),
                        right=SQLQualifiedIdentifier(parts=[outer_alias, "patient_id"]),
                    )
                    # Add the alias to the FROM clause and correlation to WHERE
                    new_where = correlation
                    if inner_select.where is not None:
                        new_where = SQLBinaryOp(
                            operator="AND",
                            left=correlation,
                            right=inner_select.where,
                        )
                    correlated_select = SQLSelect(
                        columns=inner_select.columns,
                        from_clause=SQLAlias(
                            expr=SQLIdentifier(name=cte_name, quoted=True),
                            alias="sub",
                        ),
                        where=new_where,
                        group_by=inner_select.group_by,
                        having=inner_select.having,
                        order_by=inner_select.order_by,
                        limit=inner_select.limit,
                        distinct=inner_select.distinct,
                    )
                    return SQLSubquery(query=correlated_select)
            return expr

        return expr

    def _replace_patient_resource_ast(
        self,
        expr: "SQLExpression",
        outer_alias: str = "p",
    ) -> "SQLExpression":
        """
        Replace getvariable('patient_resource') references in an AST expression.

        This transforms getvariable('patient_resource') calls into correlated subqueries
        that fetch the Patient resource for the current patient.

        Args:
            expr: The SQL expression AST to process.
            outer_alias: The alias of the outer table with patient_id.

        Returns:
            Modified SQL expression AST with patient_resource references replaced.
        """
        from ..translator.types import (
            SQLSelect, SQLFunctionCall, SQLBinaryOp, SQLQualifiedIdentifier,
            SQLIdentifier, SQLLiteral, SQLSubquery
        )

        if isinstance(expr, SQLFunctionCall):
            # Check for getvariable('patient_resource')
            if expr.name.lower() == "getvariable" and len(expr.args) >= 1:
                first_arg = expr.args[0]
                if isinstance(first_arg, SQLLiteral) and isinstance(first_arg.value, str):
                    if first_arg.value.lower() == "patient_resource":
                        # Replace with correlated subquery
                        return SQLSubquery(
                            query=SQLSelect(
                                columns=[SQLIdentifier(name="resource")],
                                from_clause=SQLIdentifier(name="resources"),
                                where=SQLBinaryOp(
                                    operator="AND",
                                    left=SQLBinaryOp(
                                        operator="=",
                                        left=SQLIdentifier(name="resourceType"),
                                        right=SQLLiteral(value="Patient"),
                                    ),
                                    right=SQLBinaryOp(
                                        operator="=",
                                        left=SQLQualifiedIdentifier(parts=["resources", "patient_ref"]),
                                        right=SQLQualifiedIdentifier(parts=[outer_alias, "patient_id"]),
                                    ),
                                ),
                                limit=1,
                            )
                        )
            # Recursively process function arguments
            return SQLFunctionCall(
                name=expr.name,
                args=[self._replace_patient_resource_ast(arg, outer_alias) for arg in expr.args],
                distinct=expr.distinct,
            )

        elif isinstance(expr, SQLBinaryOp):
            # Recursively process operands
            return SQLBinaryOp(
                operator=expr.operator,
                left=self._replace_patient_resource_ast(expr.left, outer_alias),
                right=self._replace_patient_resource_ast(expr.right, outer_alias),
            )

        elif isinstance(expr, SQLSelect):
            # Process WHERE clause of nested SELECT
            new_where = self._replace_patient_resource_ast(expr.where, outer_alias) if expr.where else None
            if new_where != expr.where:
                return SQLSelect(
                    columns=expr.columns,
                    from_clause=expr.from_clause,
                    joins=expr.joins,
                    where=new_where,
                    group_by=expr.group_by,
                    having=expr.having,
                    order_by=expr.order_by,
                    limit=expr.limit,
                    distinct=expr.distinct,
                )
            return expr

        return expr
