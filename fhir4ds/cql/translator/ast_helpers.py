"""
AST helper mixin for CQLToSQLTranslator.

This module contains methods responsible for AST inspection, manipulation,
join generation, scalar-subquery-to-join conversion,
CTE reference detection, and retrieve pattern normalisation during CQL-to-SQL
translation.
The ``ASTHelpersMixin`` class is intended to be used as a mixin with
``CQLToSQLTranslator`` and relies on attributes (``self._context``,
``self._retrieve_ctes``, etc.) initialised by the translator's ``__init__``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, List, Optional, Set, Tuple

from ..translator.types import (
    SQLAlias,
    SQLQualifiedIdentifier,
    SQLSelect,
)

if TYPE_CHECKING:
    from ..parser.ast_nodes import Expression
    from ..translator.types import (
        SQLExpression,
        SQLFunctionCall,
        SQLJoin,
        SQLSubquery,
        SQLUnion,
    )
    from ..translator.queries import CTEReference
    from ..translator.context import DefinitionMeta


class ASTHelpersMixin:
    """Mixin providing AST helper methods for CQLToSQLTranslator."""

    @staticmethod
    def _collect_defined_aliases(
        expr: "SQLExpression", _visited: Optional[Set[int]] = None
    ) -> Set[str]:
        """Collect all single-letter aliases defined in FROM/JOIN clauses of the AST.

        This walks the entire expression tree and finds SQLAlias nodes used as
        FROM clauses or JOIN tables, returning lowercase alias names.  This allows
        _has_unresolved_refs to distinguish between *defined* query aliases (valid)
        and *dangling* parameter references from failed inlining (invalid).
        """
        if _visited is None:
            _visited = set()
        eid = id(expr)
        if eid in _visited:
            return set()
        _visited.add(eid)

        aliases: Set[str] = set()

        # If this is a SELECT, its from_clause and joins define aliases
        if isinstance(expr, SQLSelect):
            if isinstance(expr.from_clause, SQLAlias) and expr.from_clause.alias:
                aliases.add(expr.from_clause.alias.lower())
            if expr.joins:
                for j in expr.joins:
                    if isinstance(j.table, SQLAlias) and j.table.alias:
                        aliases.add(j.table.alias.lower())

        # Recurse into all child nodes
        for attr_name in (
            'from_clause', 'where', 'columns', 'joins', 'query',
            'left', 'right', 'operand', 'operands', 'args', 'items',
            'body', 'expression', 'expr', 'conditions', 'else_clause',
            'order_by', 'group_by', 'having',
        ):
            child = getattr(expr, attr_name, None)
            if child is None:
                continue
            if isinstance(child, list):
                for item in child:
                    if hasattr(item, 'to_sql'):
                        aliases |= ASTHelpersMixin._collect_defined_aliases(
                            item, _visited
                        )
                    # Handle tuple items (CASE WHEN conditions)
                    elif isinstance(item, tuple):
                        for sub in item:
                            if hasattr(sub, 'to_sql'):
                                aliases |= ASTHelpersMixin._collect_defined_aliases(
                                    sub, _visited
                                )
            elif hasattr(child, 'to_sql'):
                aliases |= ASTHelpersMixin._collect_defined_aliases(
                    child, _visited
                )
            # Handle Join objects
            if attr_name == 'joins' and isinstance(child, list):
                for j in child:
                    if hasattr(j, 'on_condition') and j.on_condition and hasattr(j.on_condition, 'to_sql'):
                        aliases |= ASTHelpersMixin._collect_defined_aliases(
                            j.on_condition, _visited
                        )

        return aliases

    def _replace_patient_alias_in_condition(
        self, condition: "SQLExpression", old_alias: str, new_alias: str
    ) -> "SQLExpression":
        """Replace patient alias references in a JOIN ON condition."""
        from ..translator.types import SQLQualifiedIdentifier, SQLBinaryOp
        if isinstance(condition, SQLQualifiedIdentifier):
            if condition.parts and condition.parts[0] == old_alias:
                return SQLQualifiedIdentifier(parts=[new_alias] + condition.parts[1:])
            return condition
        if isinstance(condition, SQLBinaryOp):
            return SQLBinaryOp(
                operator=condition.operator,
                left=self._replace_patient_alias_in_condition(condition.left, old_alias, new_alias),
                right=self._replace_patient_alias_in_condition(condition.right, old_alias, new_alias),
            )
        return condition

    def _generate_joins_for_definition(self, name: str) -> Optional[List["SQLJoin"]]:
        """
        Generate JOIN clauses for a definition based on tracked CTE references.

        Uses the DefinitionMeta.tracked_refs which stores CTE references collected
        during expression translation (in translate_definition).

        Also adds JOIN to _patient_demographics when age functions are used.

        Args:
            name: The definition name.

        Returns:
            List of SQLJoin nodes, or None if no joins needed.
        """
        from ..translator.types import SQLJoin, SQLIdentifier, SQLBinaryOp, SQLQualifiedIdentifier

        joins = []

        # Get CTE references from DefinitionMeta (populated during translate_definition)
        meta = self._context.definition_meta.get(name)
        if meta and meta.tracked_refs:
            for key, ref in meta.tracked_refs.items():
                # ref is a CTEReference object with cte_name and alias attributes
                join = SQLJoin(
                    join_type="LEFT",
                    table=SQLIdentifier(name=ref.cte_name, quoted=True),
                    alias=ref.alias,
                    on_condition=SQLBinaryOp(
                        operator="=",
                        left=SQLQualifiedIdentifier(parts=[ref.alias, "patient_id"]),
                        right=SQLQualifiedIdentifier(parts=["p", "patient_id"]),
                    ),
                )
                joins.append(join)

        # NOTE: age calculations use correlated subqueries against
        # _patient_demographics (SELECT ... WHERE patient_id = ... LIMIT 1)
        # rather than a JOIN.  A LEFT JOIN here would be dead code and could
        # cause row fan-out when multiple Patient resources share the same
        # patient_ref (e.g., when test data for many measures is loaded
        # into a single DB).  We intentionally omit the demographics JOIN.

        return joins if joins else None

    def _can_use_join_for_scalar(
        self,
        meta: "DefinitionMeta",
        sql_ast: "SQLExpression",
        joins: Optional[List["SQLJoin"]],
    ) -> bool:
        """
        Check if a PATIENT_SCALAR expression can use LEFT JOIN instead of scalar subquery.

        We can use JOIN when:
        1. There are tracked CTE references (joins is not None/empty)
        2. The expression is a simple reference to a single CTE (not complex aggregation)
        3. The CTE has a value or resource column we can reference

        We CANNOT use JOIN when:
        1. No tracked refs (nothing to join)
        2. Expression is a complex aggregation (COUNT, SUM, etc.)
        3. Expression contains nested subqueries that can't be flattened
        4. Expression references multiple CTEs that would need complex join logic

        Args:
            meta: The DefinitionMeta for this definition.
            sql_ast: The translated SQL expression AST.
            joins: The list of JOINs generated from tracked_refs.

        Returns:
            True if we can use JOIN-based column reference, False for scalar subquery.
        """
        from ..translator.types import SQLFunctionCall, SQLSubquery, SQLSelect

        # No JOINs available - must use scalar subquery
        if not joins:
            return False

        # Check for complex aggregations that can't be flattened
        if self._contains_complex_aggregation(sql_ast):
            return False

        # Check for nested subqueries that reference other CTEs
        if self._contains_nested_cte_reference(sql_ast):
            return False

        # Single CTE reference - can use JOIN
        if len(joins) == 1:
            return True

        # Multiple JOINs - only use if expression is simple column reference
        # For now, be conservative and use scalar subquery for multiple JOINs
        # unless the expression is a direct reference to one of the JOINed tables
        return self._is_simple_join_reference(sql_ast, joins)

    def _get_join_column_for_scalar(
        self,
        meta: "DefinitionMeta",
        sql_ast: "SQLExpression",
    ) -> "SQLExpression":
        """
        Get the column expression to use from the JOINed CTE.

        When we convert a scalar subquery to a JOIN, we need to reference
        the appropriate column from the JOINed table instead of the original
        expression.

        Args:
            meta: The DefinitionMeta for this definition.
            sql_ast: The original SQL expression (used to determine column).

        Returns:
            SQLExpression referencing the JOINed table's column.
        """
        from ..translator.types import SQLQualifiedIdentifier, SQLFunctionCall

        # Get the first (and typically only) CTE reference
        if not meta.tracked_refs:
            # Fallback to original expression
            return sql_ast

        # Get the first tracked reference
        first_ref = next(iter(meta.tracked_refs.values()))

        # Determine which column to reference
        # For resource-bearing CTEs, use 'resource'
        # For scalar value CTEs, use 'value'
        # For FHIRPath function calls, extract the column from the function
        if isinstance(sql_ast, SQLFunctionCall):
            # Check if this is a fhirpath function extracting a value
            func_name = sql_ast.name.lower()
            if func_name.startswith("fhirpath_"):
                # The expression extracts a value via FHIRPath - use resource column
                # and let the FHIRPath function be applied to the JOINed table
                # Actually, we need to keep the FHIRPath call but update the source
                # to reference the JOIN alias
                return self._rewrite_fhirpath_source(sql_ast, first_ref.alias)

        # Default: reference the resource column from the JOINed CTE
        return SQLQualifiedIdentifier(parts=[first_ref.alias, "resource"])

    def _rewrite_fhirpath_source(
        self,
        func_call: "SQLFunctionCall",
        join_alias: str,
    ) -> "SQLExpression":
        """
        Rewrite a FHIRPath function call to use the JOIN alias as source.

        Args:
            func_call: The SQLFunctionCall (e.g., fhirpath_text).
            join_alias: The alias of the JOINed table.

        Returns:
            New SQLFunctionCall with updated source reference.
        """
        from ..translator.types import SQLFunctionCall, SQLQualifiedIdentifier

        if not func_call.args:
            return func_call

        # Replace the first argument (source) with reference to JOIN alias
        new_args = list(func_call.args)
        new_args[0] = SQLQualifiedIdentifier(parts=[join_alias, "resource"])

        return SQLFunctionCall(
            name=func_call.name,
            args=new_args,
            distinct=func_call.distinct,
        )

    def _contains_complex_aggregation(self, expr: "SQLExpression") -> bool:
        """
        Check if expression contains complex aggregation that can't be flattened to JOIN.

        Complex aggregations include: COUNT with DISTINCT, SUM, AVG, etc.
        Simple column references and FHIRPath extractions can be flattened.

        Args:
            expr: The SQL expression to check.

        Returns:
            True if expression contains complex aggregation.
        """
        from ..translator.types import SQLFunctionCall, SQLSubquery, SQLSelect

        if isinstance(expr, SQLFunctionCall):
            func_name = expr.name.upper()
            # These aggregations can't be flattened to a simple JOIN column
            if func_name in ("COUNT", "SUM", "AVG", "MIN", "MAX"):
                # But simple COUNT(*) on a single table can be converted to EXISTS check
                # For now, treat all aggregates as complex
                return True

            # Recursively check arguments
            for arg in expr.args:
                if self._contains_complex_aggregation(arg):
                    return True

        elif isinstance(expr, SQLSubquery):
            # Check inside subqueries
            return self._contains_complex_aggregation(expr.query)

        elif isinstance(expr, SQLSelect):
            # Check columns and WHERE clause
            for col in expr.columns:
                if self._contains_complex_aggregation(col):
                    return True
            if expr.where and self._contains_complex_aggregation(expr.where):
                return True

        return False

    def _contains_nested_cte_reference(self, expr: "SQLExpression") -> bool:
        """
        Check if expression contains nested subqueries that reference other CTEs.

        This helps identify expressions that can't be flattened to a simple JOIN.

        Args:
            expr: The SQL expression to check.

        Returns:
            True if expression contains nested CTE references.
        """
        from ..translator.types import SQLSubquery, SQLSelect, SQLIdentifier

        if isinstance(expr, SQLSubquery):
            if isinstance(expr.query, SQLSelect):
                # Check if subquery has its own FROM clause (references another CTE)
                if expr.query.from_clause is not None:
                    return True

        return False

    def _is_simple_join_reference(
        self,
        expr: "SQLExpression",
        joins: List["SQLJoin"],
    ) -> bool:
        """
        Check if expression is a simple reference to one of the JOINed tables.

        Args:
            expr: The SQL expression to check.
            joins: The list of JOINs.

        Returns:
            True if expression is a simple reference to a JOINed table.
        """
        from ..translator.types import SQLQualifiedIdentifier, SQLFunctionCall

        # Qualified identifier like "j1.resource" is a simple reference
        if isinstance(expr, SQLQualifiedIdentifier):
            alias = expr.parts[0] if expr.parts else None
            return any(j.alias == alias for j in joins)

        # FHIRPath function with simple source is also acceptable
        if isinstance(expr, SQLFunctionCall):
            if expr.args and isinstance(expr.args[0], SQLQualifiedIdentifier):
                alias = expr.args[0].parts[0] if expr.args[0].parts else None
                return any(j.alias == alias for j in joins)

        return False

    def _add_joins_from_tracked_refs(
        self,
        select: "SQLSelect",
        cte_refs: Dict[str, "CTEReference"],
        patient_alias: str = "p",
    ) -> "SQLSelect":
        """
        Add LEFT JOINs for tracked CTE references.

        When expressions call track_cte_reference(), they return direct alias references
        (e.g., j1.resource). This function generates the actual JOIN clauses.

        Args:
            select: The SQLSelect AST
            cte_refs: Dict of CTE name -> CTEReference (with alias)
            patient_alias: The patient table alias

        Returns:
            Modified SQLSelect with JOINs added
        """
        from ..translator.types import SQLSelect, SQLJoin, SQLIdentifier, SQLAlias, SQLBinaryOp, SQLQualifiedIdentifier

        # Determine which CTE (if any) is already the FROM clause.
        # We must not add a JOIN for a CTE that is already the main FROM table —
        # that would create a duplicate self-join reference.
        from_cte_name: Optional[str] = None
        if isinstance(select.from_clause, SQLIdentifier):
            from_cte_name = select.from_clause.name.strip('"')
        elif isinstance(select.from_clause, SQLAlias):
            if isinstance(select.from_clause.expr, SQLIdentifier):
                from_cte_name = select.from_clause.expr.name.strip('"')

        # Generate JOINs for each tracked CTE reference
        new_joins = list(select.joins or [])

        for _key, ref in cte_refs.items():
            # Skip if this CTE is already the FROM clause of the SELECT
            if from_cte_name is not None and from_cte_name == ref.cte_name.strip('"'):
                continue

            # Create LEFT JOIN for this CTE
            # Use the CTE name from the reference object
            join = SQLJoin(
                join_type="LEFT",
                table=SQLIdentifier(name=ref.cte_name, quoted=True),
                alias=ref.alias,
                on_condition=SQLBinaryOp(
                    operator="=",
                    left=SQLQualifiedIdentifier(parts=[ref.alias, "patient_id"]),
                    right=SQLQualifiedIdentifier(parts=[patient_alias, "patient_id"]),
                )
            )
            new_joins.append(join)

        return SQLSelect(
            columns=select.columns,
            from_clause=select.from_clause,
            joins=new_joins if new_joins else None,
            where=select.where,
            group_by=select.group_by,
            having=select.having,
            order_by=select.order_by,
            distinct=select.distinct,
            limit=select.limit,
        )

    def _convert_scalar_subqueries_to_joins_ast(
        self,
        select: "SQLSelect",
        cte_refs: Dict[str, "CTEReference"],
        patient_alias: str = "p",
    ) -> "SQLSelect":
        """
        Convert scalar subqueries in a SQLSelect to LEFT JOINs.

        This is the AST-based version of scalar subquery conversion, which
        operates directly on the AST rather than string manipulation.

        Args:
            select: The SQLSelect AST to transform
            cte_refs: Dict of CTE name -> CTEReference (with alias)
            patient_alias: The patient table alias (default "p")

        Returns:
            Modified SQLSelect with JOINs added and scalar subqueries replaced
        """
        from ..translator.types import SQLSelect

        new_columns = []
        new_joins = list(select.joins or [])

        for col in (select.columns or []):
            converted_col, join = self._convert_column_scalar_subquery(col, cte_refs, patient_alias)
            new_columns.append(converted_col)
            if join:
                new_joins.append(join)

        # Also process WHERE clause for scalar subqueries
        new_where = self._convert_where_scalar_subqueries(select.where, cte_refs, patient_alias, new_joins)

        return SQLSelect(
            columns=new_columns,
            from_clause=select.from_clause,
            joins=new_joins if new_joins else None,
            where=new_where,
            group_by=select.group_by,
            having=select.having,
            order_by=select.order_by,
            distinct=select.distinct,
            limit=select.limit,
        )

    def _convert_column_scalar_subquery(
        self,
        col: "SQLExpression",
        cte_refs: Dict[str, "CTEReference"],
        patient_alias: str,
    ) -> tuple:
        """
        Convert a scalar subquery column to a column reference + JOIN.

        Args:
            col: The column expression (may be a scalar subquery)
            cte_refs: Dict of CTE name -> CTEReference
            patient_alias: The patient table alias

        Returns:
            Tuple of (converted_column, optional_join)
        """
        from ..translator.types import (
            SQLSubquery, SQLSelect, SQLIdentifier,
            SQLQualifiedIdentifier, SQLJoin, SQLBinaryOp
        )

        # Handle aliased columns (tuple of expr, alias)
        if isinstance(col, tuple):
            expr, alias = col
            converted_expr, join = self._convert_column_scalar_subquery(expr, cte_refs, patient_alias)
            return (converted_expr, alias), join

        # Check if this column is a scalar subquery
        if isinstance(col, SQLSubquery):
            subquery = col.query
            if isinstance(subquery, SQLSelect) and isinstance(subquery.from_clause, SQLIdentifier):
                cte_name = subquery.from_clause.name.strip('"')

                # Check if this CTE is being tracked for JOIN conversion
                if cte_name in cte_refs:
                    ref = cte_refs[cte_name]

                    # Create JOIN
                    join = SQLJoin(
                        join_type="LEFT",
                        table=SQLIdentifier(name=subquery.from_clause.name, quoted=True),
                        alias=ref.alias,
                        on_condition=SQLBinaryOp(
                            operator="=",
                            left=SQLQualifiedIdentifier(parts=[ref.alias, "patient_id"]),
                            right=SQLQualifiedIdentifier(parts=[patient_alias, "patient_id"]),
                        )
                    )

                    # Replace subquery with column reference using metadata-aware column
                    dep_meta = self._context.definition_meta.get(cte_name) if hasattr(self, '_context') else None
                    if dep_meta is not None:
                        col_name = "resource" if dep_meta.has_resource else "value"
                    else:
                        # Forward reference: check CQL AST for return clause
                        col_name = "resource"
                        cql_asts = getattr(self._context, '_definition_cql_asts', {})
                        cql_ast = cql_asts.get(cte_name)
                        if cql_ast is not None:
                            from ..parser.ast_nodes import Query as CQLQuery, FunctionRef
                            if isinstance(cql_ast, CQLQuery) and cql_ast.return_clause is not None:
                                col_name = "value"
                            elif isinstance(cql_ast, FunctionRef) and getattr(cql_ast, 'name', '') in ('First', 'Last'):
                                args = getattr(cql_ast, 'arguments', []) or []
                                if args and isinstance(args[0], CQLQuery) and args[0].return_clause is not None:
                                    col_name = "value"
                    converted = SQLQualifiedIdentifier(parts=[ref.alias, col_name])

                    return (converted, join)

        # No conversion needed
        return (col, None)

    def _convert_where_scalar_subqueries(
        self,
        where: Optional["SQLExpression"],
        cte_refs: Dict[str, "CTEReference"],
        patient_alias: str,
        joins: List["SQLJoin"],
    ) -> Optional["SQLExpression"]:
        """
        Recursively convert scalar subqueries in WHERE clause.

        Args:
            where: The WHERE expression (may contain nested subqueries)
            cte_refs: Dict of CTE name -> CTEReference
            patient_alias: The patient table alias
            joins: List to append new JOINs to (modified in place)

        Returns:
            Modified WHERE expression with scalar subqueries replaced
        """
        from ..translator.types import (
            SQLSubquery, SQLSelect, SQLIdentifier,
            SQLQualifiedIdentifier, SQLJoin, SQLBinaryOp,
            SQLFunctionCall
        )

        if where is None:
            return None

        # Handle scalar subquery directly in WHERE
        if isinstance(where, SQLSubquery):
            subquery = where.query
            if isinstance(subquery, SQLSelect) and isinstance(subquery.from_clause, SQLIdentifier):
                cte_name = subquery.from_clause.name.strip('"')
                if cte_name in cte_refs:
                    ref = cte_refs[cte_name]
                    # Create JOIN
                    join = SQLJoin(
                        join_type="LEFT",
                        table=SQLIdentifier(name=subquery.from_clause.name, quoted=True),
                        alias=ref.alias,
                        on_condition=SQLBinaryOp(
                            operator="=",
                            left=SQLQualifiedIdentifier(parts=[ref.alias, "patient_id"]),
                            right=SQLQualifiedIdentifier(parts=[patient_alias, "patient_id"]),
                        )
                    )
                    joins.append(join)
                    # Replace subquery with "alias.resource IS NOT NULL" for boolean context
                    # In WHERE clause, we need a boolean expression
                    from ..translator.types import SQLUnaryOp
                    return SQLUnaryOp(
                        operator="IS NOT NULL",
                        operand=SQLQualifiedIdentifier(parts=[ref.alias, "resource"]),
                        prefix=False  # Postfix: operand IS NOT NULL
                    )

        # Recurse into binary operations (AND, OR, comparisons)
        if isinstance(where, SQLBinaryOp):
            left = self._convert_where_scalar_subqueries(where.left, cte_refs, patient_alias, joins)
            right = self._convert_where_scalar_subqueries(where.right, cte_refs, patient_alias, joins)
            return SQLBinaryOp(operator=where.operator, left=left, right=right)

        # Recurse into function calls (e.g., fhirpath_text(subquery, 'path'))
        if isinstance(where, SQLFunctionCall):
            new_args = []
            for arg in (where.args or []):
                converted = self._convert_where_scalar_subqueries(arg, cte_refs, patient_alias, joins)
                new_args.append(converted)
            return SQLFunctionCall(name=where.name, args=new_args, distinct=where.distinct)

        # Recurse into lists/tuples
        if isinstance(where, (list, tuple)):
            return type(where)(
                self._convert_where_scalar_subqueries(item, cte_refs, patient_alias, joins)
                for item in where
            )

        # No conversion needed for other types
        return where

    def _select_has_resource(self, select: "SQLSelect") -> bool:
        """
        Check if the SELECT's OUTPUT columns include one named 'resource'.

        Only checks output column names/aliases, NOT internal references
        to source table columns (e.g., Hospitalization.resource).
        For SELECT * from a known CTE, checks the source CTE's metadata.
        For SELECT * from a subquery/union, recurses into the source.

        Args:
            select: The SQLSelect AST to check.

        Returns:
            True if the SELECT produces a column named 'resource'.
        """
        from ..translator import ast_utils
        from ..translator.types import (
            SQLIdentifier, SQLAlias, SQLSelect as SQLSelectType,
            SQLSubquery, SQLUnion, SQLIntersect, SQLExcept,
        )

        # Check if the SELECT's output columns include one explicitly named 'resource'.
        # We must NOT match 'resource AS value' — that produces a 'value' output column.
        # So we check output column names/aliases only, not inner expression references.
        has_explicit_resource = False
        for col in (select.columns or []):
            if isinstance(col, SQLAlias):
                if col.alias and col.alias.lower() == "resource":
                    has_explicit_resource = True
                    break
            elif isinstance(col, tuple):
                _, alias = col
                if alias and alias.lower() == "resource":
                    has_explicit_resource = True
                    break
            elif isinstance(col, SQLIdentifier):
                if col.name.lower() == "resource":
                    has_explicit_resource = True
                    break
            elif isinstance(col, SQLQualifiedIdentifier):
                # e.g., alias.resource — output name is last part
                if col.parts and col.parts[-1].lower() == "resource":
                    has_explicit_resource = True
                    break
        if has_explicit_resource:
            return True

        # SELECT * inherits columns from the source — check source CTE meta
        if ast_utils.select_has_star(select) and select.from_clause:
            from_ref = select.from_clause
            if isinstance(from_ref, SQLAlias):
                from_ref = from_ref.expr
            if isinstance(from_ref, SQLIdentifier) and from_ref.quoted:
                ref_meta = self._context.definition_meta.get(from_ref.name)
                if ref_meta:
                    return ref_meta.has_resource
                # Retrieve CTEs (not in definition_meta) always have resource
                return True
            # SELECT * FROM (subquery) AS alias — recurse into the subquery
            if isinstance(from_ref, SQLSubquery) and isinstance(from_ref.query, SQLSelectType):
                return self._select_has_resource(from_ref.query)
            # SELECT * FROM (UNION) AS alias — check if union operands have resource
            if isinstance(from_ref, (SQLUnion, SQLIntersect, SQLExcept)):
                for op in (from_ref.operands or []):
                    inner = op
                    if isinstance(inner, SQLSubquery):
                        inner = inner.query
                    # Bare CTE reference: check definition_meta
                    if isinstance(inner, SQLIdentifier) and inner.quoted:
                        ref_meta = self._context.definition_meta.get(inner.name)
                        if ref_meta and ref_meta.has_resource:
                            return True
                        if not ref_meta:
                            # Retrieve CTEs not in definition_meta always have resource
                            return True
                        continue
                    if isinstance(inner, SQLSelectType):
                        if self._select_has_resource(inner):
                            return True
                # No operands had resource
                return False
        return False

    def _ensure_resource_column(self, sql_ast: "SQLSelect") -> "SQLSelect":
        """Ensure a RESOURCE_ROWS SQLSelect has a column named 'resource'.

        Tuple-returning queries produce ``to_json(struct_pack(...))`` as the
        data column.  Downstream code accesses it via ``alias.resource``, so if
        no column is already named ``resource`` we alias the first
        non-patient_id column.

        When the expression being aliased internally references a source column
        named ``resource`` (e.g. ``fhirpath_text(Payer.resource, ...)``),
        DuckDB raises "Column resource referenced before defined". In that case,
        use an intermediate alias and wrap in a subquery to isolate the scope.
        """
        from ..translator.types import (
            SQLAlias, SQLIdentifier, SQLQualifiedIdentifier, SQLSubquery,
        )
        from ..translator import ast_utils

        if ast_utils.select_has_column(sql_ast, "resource") or ast_utils.select_has_star(sql_ast):
            return sql_ast

        new_cols = []
        aliased = False
        needs_wrap = False
        for col in (sql_ast.columns or []):
            is_pid = False
            if isinstance(col, SQLIdentifier) and col.name == "patient_id":
                is_pid = True
            elif isinstance(col, SQLQualifiedIdentifier) and col.parts and col.parts[-1] == "patient_id":
                is_pid = True
            elif isinstance(col, SQLAlias) and col.alias == "patient_id":
                is_pid = True

            if is_pid or aliased:
                new_cols.append(col)
            else:
                # Unwrap existing SQLAlias to avoid double-aliasing
                inner_expr = col.expr if isinstance(col, SQLAlias) else col
                # Check if the expression references 'resource' from the source
                if ast_utils.ast_references_name(inner_expr, "resource"):
                    # Use intermediate alias to avoid DuckDB self-reference error
                    new_cols.append(SQLAlias(expr=inner_expr, alias="_resource_data"))
                    needs_wrap = True
                else:
                    new_cols.append(SQLAlias(expr=inner_expr, alias="resource"))
                aliased = True

        if not aliased:
            return sql_ast

        inner = SQLSelect(
            columns=new_cols,
            from_clause=sql_ast.from_clause,
            where=sql_ast.where,
            joins=sql_ast.joins,
            group_by=sql_ast.group_by,
            having=sql_ast.having,
            order_by=sql_ast.order_by,
            limit=sql_ast.limit,
            distinct=sql_ast.distinct,
        )

        if needs_wrap:
            # Ensure inner SELECT includes patient_id for the outer reference
            has_pid = any(
                (isinstance(c, SQLIdentifier) and c.name == "patient_id")
                or (isinstance(c, SQLQualifiedIdentifier) and c.column == "patient_id")
                or (isinstance(c, SQLAlias) and c.alias == "patient_id")
                for c in new_cols
            )
            if not has_pid:
                new_cols.insert(0, SQLIdentifier(name="patient_id"))
                inner = SQLSelect(
                    columns=new_cols,
                    from_clause=sql_ast.from_clause,
                    where=sql_ast.where,
                    joins=sql_ast.joins,
                    group_by=sql_ast.group_by,
                    having=sql_ast.having,
                    order_by=sql_ast.order_by,
                    limit=sql_ast.limit,
                    distinct=sql_ast.distinct,
                )
            # Wrap in outer SELECT that renames _resource_data → resource
            outer_cols = [
                SQLQualifiedIdentifier(parts=["_inner", "patient_id"]),
                SQLAlias(
                    expr=SQLQualifiedIdentifier(parts=["_inner", "_resource_data"]),
                    alias="resource",
                ),
            ]
            # Propagate _audit_item through the wrapping so it stays reachable
            for c in new_cols:
                alias_name = c.alias if isinstance(c, SQLAlias) else None
                col_name = c.name if isinstance(c, SQLIdentifier) else None
                if alias_name == "_audit_item" or col_name == "_audit_item":
                    outer_cols.append(SQLAlias(
                        expr=SQLQualifiedIdentifier(parts=["_inner", "_audit_item"]),
                        alias="_audit_item",
                    ))
                    break
            return SQLSelect(
                columns=outer_cols,
                from_clause=SQLAlias(
                    expr=SQLSubquery(query=inner),
                    alias="_inner",
                ),
            )

        return inner

    def _select_has_patient_id(self, select: "SQLSelect") -> bool:
        """
        Check if the SELECT has a patient_id column.

        Args:
            select: The SQLSelect AST to check.

        Returns:
            True if the SELECT includes a 'patient_id' column.
        """
        from ..translator import ast_utils
        # Check for explicit patient_id column or SELECT *
        return (ast_utils.select_has_column(select, "patient_id") or 
                ast_utils.select_has_star(select))

    def _union_has_column_mismatch(self, union: "SQLUnion") -> bool:
        """Check if a SQLUnion has operands with different column counts.

        This happens when a CQL union combines scalar CTEs (1 column)
        with resource-row CTEs (2 columns: patient_id, resource).
        """
        from ..translator.types import SQLSelect, SQLSubquery
        col_counts = set()
        for op in (union.operands or []):
            count = self._count_select_columns(op)
            if count is not None:
                col_counts.add(count)
        return len(col_counts) > 1

    def _count_select_columns(self, node) -> int | None:
        """Count the number of columns a SQL node produces."""
        from ..translator.types import SQLSelect, SQLSubquery, SQLIdentifier
        if isinstance(node, SQLSubquery):
            return self._count_select_columns(node.query)
        if isinstance(node, SQLSelect):
            if not node.columns:
                return None  # SELECT * — unknown
            # SELECT * represented as [SQLIdentifier(name="*")] is also unknown
            if (len(node.columns) == 1
                    and isinstance(node.columns[0], SQLIdentifier)
                    and node.columns[0].name == "*"):
                return None
            return len(node.columns)
        return None

    def _union_has_patient_id(self, union: "SQLUnion") -> bool:
        """Check if a SQLUnion's operands carry patient_id."""
        from ..translator.types import SQLSelect, SQLSubquery
        for op in (union.operands or []):
            inner = op
            if isinstance(inner, SQLSubquery):
                inner = inner.query
            if isinstance(inner, SQLSelect):
                if self._select_has_patient_id(inner):
                    return True
                # Also check if columns is empty (SELECT *) — assume it has patient_id
                if not inner.columns:
                    return True
        return False

    def _get_source_alias(self, select: "SQLSelect") -> Optional[str]:
        """
        Get the alias of the main source table in the FROM clause.

        Args:
            select: The SQLSelect AST to check.

        Returns:
            The alias of the source table, or None if not found.
        """
        from ..translator.types import SQLAlias, SQLIdentifier, SQLSubquery
        if select.from_clause is None:
            return None
        if isinstance(select.from_clause, SQLAlias):
            return select.from_clause.alias
        if isinstance(select.from_clause, SQLIdentifier):
            # No alias, just a table name - extract the name
            return select.from_clause.name
        if isinstance(select.from_clause, SQLSubquery):
            # Subquery in FROM clause - get the alias from the inner query
            inner = select.from_clause.query
            if isinstance(inner, SQLSelect):
                # Recursively check the inner query's FROM clause
                return self._get_source_alias(inner)
        return None

    def _is_ast_retrieve(self, select: "SQLSelect") -> bool:
        """
        Check if the SELECT is a retrieve from the resources table.

        Args:
            select: The SQLSelect AST to check.

        Returns:
            True if this is a SELECT ... FROM resources ...
        """
        from ..translator.types import SQLIdentifier

        if select.from_clause is None:
            return False

        # Check if FROM clause is 'resources'
        if isinstance(select.from_clause, SQLIdentifier):
            return select.from_clause.name.lower() == "resources"

        return False

    def _is_ast_boolean_expression(self, select: "SQLSelect") -> bool:
        """
        Check if the SELECT represents a boolean/exists expression.

        Args:
            select: The SQLSelect AST to check.

        Returns:
            True if this looks like a boolean expression.
        """
        from ..translator.types import SQLFunctionCall, SQLExists

        # Check if the SELECT has an EXISTS in WHERE clause
        if select.where is not None:
            # Use AST-based detection for EXISTS nodes
            from ..translator.ast_utils import ast_has_node_type
            if ast_has_node_type(select.where, SQLExists):
                return True

        # Check if columns contain EXISTS
        for col in (select.columns or []):
            if isinstance(col, tuple):
                expr, alias = col
                if isinstance(expr, SQLExists):
                    return True
            elif isinstance(col, SQLExists):
                return True

        return False

    def _detect_lateral_join_needs_ast(
        self,
        expr: "SQLExpression",
        existing_ctes: Dict[str, tuple],
    ) -> Optional[List["SQLJoin"]]:
        """
        Detect if an AST expression needs CROSS JOIN LATERAL for alias references.

        When an expression references query aliases (like ESRDEncounter) that
        aren't defined in the FROM clause, we need to add CROSS JOIN LATERAL
        to bind them to the CTE they reference.

        Args:
            expr: The SQL expression AST to analyze.
            existing_ctes: Dictionary of existing CTEs.

        Returns:
            List of SQLJoin nodes if lateral joins are needed, None otherwise.
        """
        from ..translator.types import (
            SQLQualifiedIdentifier, SQLJoin, SQLIdentifier
        )

        # Collect all qualified identifier prefixes (aliases)
        aliases_used = set()
        self._collect_aliases_from_ast(expr, aliases_used)

        # Check if any alias is a CTE reference that needs a lateral join
        lateral_joins = []
        for alias in aliases_used:
            # Check if this alias corresponds to a CTE name
            for cte_name, (quoted_name, has_resource) in existing_ctes.items():
                # Match alias to CTE name (could be exact or case-insensitive)
                if alias == cte_name or alias.lower() == cte_name.lower():
                    # Create CROSS JOIN LATERAL for this CTE
                    lateral_joins.append(SQLJoin(
                        join_type="CROSS",
                        table=SQLIdentifier(name=quoted_name, quoted=True),
                        alias=alias,
                        on_condition=None,  # LATERAL doesn't need ON
                    ))
                    break

        return lateral_joins if lateral_joins else None

    def _collect_aliases_from_ast(
        self,
        expr: "SQLExpression",
        aliases: set,
    ) -> None:
        """
        Collect alias prefixes from qualified identifiers in an AST expression.

        Args:
            expr: The SQL expression AST to analyze.
            aliases: Set to collect alias names into.
        """
        from ..translator.types import (
            SQLQualifiedIdentifier, SQLBinaryOp, SQLFunctionCall,
            SQLSelect, SQLSubquery, SQLExists
        )

        if isinstance(expr, SQLQualifiedIdentifier):
            if expr.parts:
                aliases.add(expr.parts[0])
        elif isinstance(expr, SQLBinaryOp):
            self._collect_aliases_from_ast(expr.left, aliases)
            self._collect_aliases_from_ast(expr.right, aliases)
        elif isinstance(expr, SQLFunctionCall):
            for arg in expr.args:
                self._collect_aliases_from_ast(arg, aliases)
        elif isinstance(expr, SQLSelect):
            for col in (expr.columns or []):
                if isinstance(col, tuple):
                    self._collect_aliases_from_ast(col[0], aliases)
                else:
                    self._collect_aliases_from_ast(col, aliases)
            if expr.where:
                self._collect_aliases_from_ast(expr.where, aliases)
            if expr.joins:
                for join in expr.joins:
                    if join.on_condition:
                        self._collect_aliases_from_ast(join.on_condition, aliases)
        elif isinstance(expr, SQLSubquery):
            self._collect_aliases_from_ast(expr.query, aliases)
        elif isinstance(expr, SQLExists):
            self._collect_aliases_from_ast(expr.subquery, aliases)

    def _get_valueset_alias(self, url: str) -> Optional[str]:
        """
        Get valueset name from URL via reverse lookup.

        Args:
            url: The valueset URL to look up.

        Returns:
            The valueset name/alias if found, None otherwise.
        """
        for name, vs_url in self._context.valuesets.items():
            if vs_url == url:
                return name
        return None

    def _extract_common_retrieves(
        self,
        definitions: Dict[str, SQLExpression]
    ) -> Tuple[Dict[str, SQLExpression], Dict[str, "SQLSelect"]]:
        """
        Find repeated retrieve patterns and extract to CTEs.

        Strategy:
        1. Walk all definitions, collect all SQLSubquery retrieves
        2. Normalize each retrieve to a pattern key (resourceType + valueset)
        3. For patterns appearing 2+ times, create a shared CTE
        4. Replace original subqueries with CTE references

        Args:
            definitions: Dictionary of definition names to SQL expressions.

        Returns:
            Tuple of (modified_definitions, retrieve_ctes)
        """
        from .types import SQLSubquery, SQLSelect, SQLIdentifier

        retrieve_patterns: Dict[str, List[Tuple[str, SQLExpression]]] = {}

        # Step 1: Collect all retrieves
        for def_name, expr in definitions.items():
            self._collect_retrieves(def_name, expr, retrieve_patterns)

        # Step 2: Create CTEs for repeated patterns
        retrieve_ctes: Dict[str, "SQLSelect"] = {}
        pattern_to_cte: Dict[str, str] = {}

        for pattern, occurrences in retrieve_patterns.items():
            if len(occurrences) >= 2:  # Only extract if used 2+ times
                cte_name = f"_retrieve_{len(retrieve_ctes)}"
                # Use first occurrence as template
                _, template_expr = occurrences[0]
                if isinstance(template_expr, SQLSubquery) and isinstance(template_expr.query, SQLSelect):
                    retrieve_ctes[cte_name] = template_expr.query
                    pattern_to_cte[pattern] = cte_name

        # Step 3: Replace subqueries with CTE references
        modified_definitions = dict(definitions)
        for def_name, expr in modified_definitions.items():
            modified_definitions[def_name] = self._replace_retrieves_with_cte_refs(
                expr, retrieve_patterns, pattern_to_cte
            )

        return modified_definitions, retrieve_ctes

    def _collect_retrieves(
        self,
        def_name: str,
        expr: SQLExpression,
        patterns: Dict[str, List[Tuple[str, SQLExpression]]]
    ) -> None:
        """
        Recursively collect all retrieve subqueries from an expression.

        Args:
            def_name: The definition name this expression belongs to.
            expr: The SQL expression to search.
            patterns: Dictionary to store patterns -> list of (def_name, expr) tuples.
        """
        from .types import SQLSubquery, SQLSelect, SQLFunctionCall, SQLBinaryOp, SQLUnion

        if isinstance(expr, SQLSubquery):
            pattern = self._normalize_retrieve_pattern(expr)
            if pattern:
                if pattern not in patterns:
                    patterns[pattern] = []
                patterns[pattern].append((def_name, expr))

        # Recurse into compound expressions
        if isinstance(expr, SQLFunctionCall):
            for arg in expr.args:
                self._collect_retrieves(def_name, arg, patterns)
        elif isinstance(expr, SQLBinaryOp):
            self._collect_retrieves(def_name, expr.left, patterns)
            self._collect_retrieves(def_name, expr.right, patterns)
        elif isinstance(expr, SQLUnion):
            for operand in expr.operands:
                self._collect_retrieves(def_name, operand, patterns)

    def _normalize_retrieve_pattern(self, subquery: "SQLSubquery") -> str:
        """
        Create a canonical key for a retrieve pattern.

        Format: "resourceType|valueset_url" or "resourceType|*" if no valueset

        Args:
            subquery: The SQLSubquery to normalize.

        Returns:
            A string pattern key for the retrieve.
        """
        from .types import SQLSelect, SQLBinaryOp, SQLFunctionCall, SQLLiteral

        if not isinstance(subquery.query, SQLSelect):
            return ""

        query = subquery.query
        if not query.where:
            return ""

        # Extract resourceType and valueset from WHERE clause using AST walking
        resource_type = self._extract_resourcetype_from_where(query.where)
        valueset_url = self._extract_valueset_from_where(query.where)

        if resource_type:
            return f"{resource_type}|{valueset_url or '*'}"
        return ""

    def _extract_resourcetype_from_where(self, where_expr: "SQLExpression") -> Optional[str]:
        """
        Extract resourceType value from WHERE clause AST.
        
        Looks for patterns like: WHERE resourceType = 'Patient'
        
        Args:
            where_expr: The WHERE clause expression to search
            
        Returns:
            The resourceType value if found (e.g., 'Patient'), None otherwise
        """
        from .types import SQLBinaryOp, SQLIdentifier, SQLLiteral
        
        if isinstance(where_expr, SQLBinaryOp):
            # Check for: resourceType = 'value'
            if where_expr.operator.upper() == '=':
                # Check if left side is resourceType identifier
                if isinstance(where_expr.left, SQLIdentifier) and where_expr.left.name.lower() == 'resourcetype':
                    # Extract literal value from right side
                    if isinstance(where_expr.right, SQLLiteral):
                        return str(where_expr.right.value)
                # Check if right side is resourceType identifier
                if isinstance(where_expr.right, SQLIdentifier) and where_expr.right.name.lower() == 'resourcetype':
                    # Extract literal value from left side
                    if isinstance(where_expr.left, SQLLiteral):
                        return str(where_expr.left.value)
            
            # Recursively check both sides (for AND conditions)
            if where_expr.operator.upper() == 'AND':
                left_result = self._extract_resourcetype_from_where(where_expr.left)
                if left_result:
                    return left_result
                return self._extract_resourcetype_from_where(where_expr.right)
        
        # Handle other expression types recursively if needed
        if hasattr(where_expr, 'left') and hasattr(where_expr, 'right'):
            left_result = self._extract_resourcetype_from_where(where_expr.left)
            if left_result:
                return left_result
            return self._extract_resourcetype_from_where(where_expr.right)
        
        return None

    def _extract_valueset_from_where(self, where_expr: "SQLExpression") -> Optional[str]:
        """
        Extract valueset URL from WHERE clause AST.
        
        Looks for patterns like: WHERE in_valueset(property, 'http://...')
        
        Args:
            where_expr: The WHERE clause expression to search
            
        Returns:
            The valueset URL if found, None otherwise
        """
        from .types import SQLBinaryOp, SQLFunctionCall, SQLLiteral
        
        if isinstance(where_expr, SQLFunctionCall):
            # Check for: in_valueset(property, 'url')
            if where_expr.name == 'in_valueset' and where_expr.args and len(where_expr.args) >= 2:
                # Second argument is typically the valueset URL
                url_arg = where_expr.args[1]
                if isinstance(url_arg, SQLLiteral):
                    return str(url_arg.value)
        
        # Recursively check binary operations (AND conditions)
        if isinstance(where_expr, SQLBinaryOp):
            left_result = self._extract_valueset_from_where(where_expr.left)
            if left_result:
                return left_result
            return self._extract_valueset_from_where(where_expr.right)
        
        # Recursively check other expressions with child nodes
        if hasattr(where_expr, 'left') and hasattr(where_expr, 'right'):
            left_result = self._extract_valueset_from_where(where_expr.left)
            if left_result:
                return left_result
            return self._extract_valueset_from_where(where_expr.right)
        
        if hasattr(where_expr, 'args'):  # For function calls
            for arg in where_expr.args:
                result = self._extract_valueset_from_where(arg)
                if result:
                    return result
        
        return None

    def _is_cte_reference(self, expr: "SQLExpression") -> bool:
        """Check if expression is a reference to a tracked CTE.

        A CTE reference is an expression that accesses a definition that
        has been translated to a CTE (not a direct resource table access).

        Args:
            expr: The SQL expression to check

        Returns:
            True if this expression references a CTE, False otherwise.
        """
        from ..translator.types import SQLSubquery, SQLIdentifier

        # Check if this is a subquery that references a CTE
        if isinstance(expr, SQLSubquery):
            # Check if the subquery's FROM clause references a CTE
            if hasattr(expr.query, 'from_clause'):
                from_clause = expr.query.from_clause
                if isinstance(from_clause, SQLIdentifier):
                    cte_name = from_clause.name
                    # Check if this CTE is being tracked
                    if self._context.query_builder:
                        # Normalize name (strip quotes)
                        normalized = cte_name.strip('"')
                        # cte_references uses tuple keys (cte_name, semantic_alias)
                        # Check if any key starts with this CTE name
                        for key in self._context.query_builder.cte_references:
                            if key[0] == normalized:
                                return True
                        return False
        return False

    def _find_cte_references(self, expr: SQLExpression, cte_names: Set[str]) -> Set[str]:
        """
        Find all CTE references in an SQLExpression AST.

        Args:
            expr: The SQL expression to traverse
            cte_names: Set of valid CTE names to look for

        Returns:
            Set of CTE names referenced in the expression
        """
        from ..translator.types import (
            SQLIdentifier, SQLQualifiedIdentifier, SQLSubquery, SQLSelect,
            SQLJoin, SQLBinaryOp, SQLFunctionCall
        )

        refs = set()

        def visit(node):
            if node is None:
                return
            if isinstance(node, SQLIdentifier):
                if node.name in cte_names or node.name.strip('"') in cte_names:
                    refs.add(node.name.strip('"'))
            elif isinstance(node, SQLQualifiedIdentifier):
                if node.parts and node.parts[0] in cte_names:
                    refs.add(node.parts[0])
            elif isinstance(node, SQLSubquery):
                if hasattr(node.query, 'from_clause'):
                    from_clause = node.query.from_clause
                    if isinstance(from_clause, SQLIdentifier):
                        name = from_clause.name.strip('"')
                        if name in cte_names:
                            refs.add(name)
                # Recurse into subquery
                visit(node.query)
            elif isinstance(node, SQLSelect):
                for col in (node.columns or []):
                    visit(col)
                visit(node.from_clause)
                for join in (node.joins or []):
                    visit(join)
                visit(node.where)
                visit(node.group_by)
                visit(node.having)
            elif isinstance(node, SQLJoin):
                visit(node.table)
                visit(node.on_condition)
            elif isinstance(node, SQLBinaryOp):
                visit(node.left)
                visit(node.right)
            elif isinstance(node, SQLFunctionCall):
                for arg in (node.args or []):
                    visit(arg)
            elif isinstance(node, (list, tuple)):
                for item in node:
                    visit(item)

        visit(expr)
        return refs

    def _get_cte_name_from_expression(self, expr: "SQLExpression") -> Optional[str]:
        """Extract CTE name from a CTE reference expression.

        Args:
            expr: The SQL expression (should be a CTE reference)

        Returns:
            CTE name if found, None otherwise.
        """
        from ..translator.types import SQLSubquery, SQLIdentifier

        if isinstance(expr, SQLSubquery) and hasattr(expr.query, 'from_clause'):
            from_clause = expr.query.from_clause
            if isinstance(from_clause, SQLIdentifier):
                return from_clause.name
        return None

    def _replace_retrieves_with_cte_refs(
        self,
        expr: SQLExpression,
        patterns: Dict[str, List[Tuple[str, SQLExpression]]],
        pattern_to_cte: Dict[str, str]
    ) -> SQLExpression:
        """
        Replace subqueries with CTE references where applicable.

        Args:
            expr: The SQL expression to transform.
            patterns: Dictionary of pattern -> occurrences.
            pattern_to_cte: Dictionary mapping patterns to CTE names.

        Returns:
            The transformed SQL expression with CTE references.
        """
        from .types import SQLSubquery, SQLSelect, SQLIdentifier, SQLFunctionCall, SQLBinaryOp, SQLUnion

        if isinstance(expr, SQLSubquery):
            pattern = self._normalize_retrieve_pattern(expr)
            if pattern in pattern_to_cte:
                cte_name = pattern_to_cte[pattern]
                # Return a reference to the CTE
                return SQLSubquery(query=SQLSelect(
                    columns=[SQLIdentifier(name="resource")],
                    from_clause=SQLIdentifier(name=cte_name)
                ))
            return expr

        # Recurse into compound expressions
        if isinstance(expr, SQLFunctionCall):
            new_args = [self._replace_retrieves_with_cte_refs(arg, patterns, pattern_to_cte) for arg in expr.args]
            return SQLFunctionCall(name=expr.name, args=new_args, distinct=expr.distinct)
        elif isinstance(expr, SQLBinaryOp):
            new_left = self._replace_retrieves_with_cte_refs(expr.left, patterns, pattern_to_cte)
            new_right = self._replace_retrieves_with_cte_refs(expr.right, patterns, pattern_to_cte)
            return SQLBinaryOp(operator=expr.operator, left=new_left, right=new_right)
        elif isinstance(expr, SQLUnion):
            new_operands = [self._replace_retrieves_with_cte_refs(op, patterns, pattern_to_cte) for op in expr.operands]
            return SQLUnion(operands=new_operands, distinct=expr.distinct)

        return expr

    def _is_quantity_ast_expr(self, node, let_map: dict, _depth: int = 0) -> bool:
        """Check if a CQL AST expression evaluates to a Quantity value."""
        from ..parser.ast_nodes import (
            BinaryExpression, Identifier, NamedTypeSpecifier,
            Quantity as QuantityLiteral, FunctionRef, Property,
        )
        if _depth > 6:
            return False
        if isinstance(node, QuantityLiteral):
            return True
        if isinstance(node, BinaryExpression) and node.operator == "as":
            ts = node.right
            if isinstance(ts, (NamedTypeSpecifier, Identifier)):
                if getattr(ts, "name", "") == "Quantity":
                    return True
        if isinstance(node, BinaryExpression) and node.operator in ("+", "-", "*", "/"):
            return (self._is_quantity_ast_expr(node.left, let_map, _depth + 1)
                    or self._is_quantity_ast_expr(node.right, let_map, _depth + 1))
        if isinstance(node, Identifier):
            # Check let-clause aliases
            if node.name in let_map:
                return self._is_quantity_ast_expr(let_map[node.name], let_map, _depth + 1)
        if isinstance(node, FunctionRef) and node.name in ("Max", "Min", "Sum", "Avg"):
            for arg in (node.arguments or []):
                if self._is_quantity_ast_expr(arg, let_map, _depth + 1):
                    return True
        if isinstance(node, Property) and node.source:
            # Property access on a Quantity destructures it (.value → Decimal,
            # .unit → String).  Do NOT mark these as Quantity.
            # Only recurse if path is empty (pass-through) — otherwise, property
            # access breaks the Quantity type.
            path = getattr(node, "path", "")
            if not path:
                return self._is_quantity_ast_expr(node.source, let_map, _depth + 1)
        return False


    # ------------------------------------------------------------------
    # Audit-mode helpers
    # ------------------------------------------------------------------

    def _collect_audit_evidence_exprs(self, name: str, sql_ast: "SQLExpression" = None) -> tuple:
        """
        Collect audit evidence from CTEs referenced in the expression.

        Two evidence strategies are used depending on the CTE type:

        1. Retrieve CTEs (``_audit_retrieve_cte_names``): LEFT JOIN the CTE and read
           its ``_audit_item`` column.  These CTEs carry a pre-built struct per row.

        2. RESOURCE_ROWS definition CTEs (``definition_meta`` with ``has_resource``):
           use a correlated subquery that collects a list of evidence structs directly
           from the CTE's ``resource`` column.  These CTEs do not have ``_audit_item``
           so the JOIN approach does not apply.

        Args:
            name: The definition name.
            sql_ast: The SQL expression AST to scan for CTE references.

        Returns:
            Tuple of (evidence_parts list, join_clauses list).
            - evidence_parts: mixed list of strings.  Strings starting with
              ``<SUBQUERY:`` encode the correlated-subquery evidence for a definition
              CTE; all other strings are ``"CTE_NAME"._audit_item`` JOIN expressions.
            - join_clauses: SQLJoin nodes for retrieve CTE LEFT JOINs.
        """
        from ..translator.types import SQLJoin, SQLIdentifier, SQLBinaryOp, SQLQualifiedIdentifier
        from ..translator.context import RowShape

        if sql_ast is None:
            return [], []

        # Retrieve CTEs carry _audit_item (built by retrieve_optimizer in Phase 2).
        retrieve_cte_names = getattr(self._context, '_audit_retrieve_cte_names', set())
        # Definition CTEs that were explicitly registered as having _audit_item passthrough.
        definition_cte_names = getattr(self._context, '_audit_definition_cte_names', set())
        all_audit_cte_names = retrieve_cte_names | definition_cte_names

        # Extract all quoted CTE identifiers referenced in the expression.
        cte_names: set = set()
        self._extract_cte_names_from_ast(sql_ast, cte_names)

        evidence_parts: list = []
        join_clauses: list = []

        for cte_name in sorted(cte_names):
            if cte_name == name:
                # Never reference the definition's own CTE to avoid circularity.
                continue

            if cte_name in all_audit_cte_names:
                # Strategy 1: retrieve/passthrough CTE → LEFT JOIN + _audit_item column.
                quoted = f'"{cte_name}"'
                evidence_parts.append(f'{quoted}._audit_item')
                join_clauses.append(SQLJoin(
                    join_type="LEFT",
                    table=SQLIdentifier(name=cte_name, quoted=True),
                    on_condition=SQLBinaryOp(
                        operator="=",
                        left=SQLQualifiedIdentifier(parts=[quoted, "patient_id"]),
                        right=SQLQualifiedIdentifier(parts=["p", "patient_id"]),
                    ),
                ))
                continue

            # Strategy 2: RESOURCE_ROWS definition CTE → correlated subquery.
            meta = self._context.definition_meta.get(cte_name)
            if (
                meta is not None
                and getattr(meta, 'has_resource', False)
                and getattr(meta, 'shape', None) == RowShape.RESOURCE_ROWS
            ):
                # Encode as a sentinel so _inject_audit_evidence can build the SQL.
                evidence_parts.append(f'<SUBQUERY:{cte_name}>')
                continue

            # Strategy 3: PATIENT_SCALAR non-boolean definition that transitively
            # depends on RESOURCE_ROWS CTEs (e.g. "Lowest Systolic Reading" →
            # "Qualifying Blood Pressures" → Observation retrieve CTE).
            # Use the pre-computed source_resource_ctes populated by CTEManager.
            if meta is not None and getattr(meta, 'source_resource_ctes', None):
                for src_cte in meta.source_resource_ctes:
                    sentinel = f'<SUBQUERY:{src_cte}>'
                    if sentinel not in evidence_parts:
                        evidence_parts.append(sentinel)

            # Strategy 4: PATIENT_SCALAR Boolean sub-definition → propagate its
            # audit evidence (including comparison values) to the parent definition.
            # When "Numerator" references "Has Diastolic BP < 90", this queries the
            # sub-definition's _cmp_result.evidence (for comparison defs with a
            # two-column pre-compute CTE) or _audit_result.evidence (for compound
            # Boolean defs that carry audit_and/or trees).  The sub-definition's
            # evidence items already have via chains from their own injection pass,
            # so the parent's via append extends the chain naturally.
            if (
                meta is not None
                and getattr(meta, 'shape', None) == RowShape.PATIENT_SCALAR
                and getattr(meta, 'cql_type', None) == "Boolean"
            ):
                precte_map = getattr(self, '_precte_name_map', {})
                comparison_prectes = getattr(self, '_comparison_prectes', set())
                if cte_name in precte_map and precte_map[cte_name] in comparison_prectes:
                    # Two-column pre-compute CTE: _cmp_result.evidence
                    evidence_parts.append(f'<CMP_EVIDENCE:{precte_map[cte_name]}>')
                else:
                    # Regular Boolean definition CTE: _audit_result.evidence
                    evidence_parts.append(f'<BOOL_EVIDENCE:{cte_name}>')

        return evidence_parts, join_clauses

    def _extract_cte_names_from_ast(self, expr: "SQLExpression", names: set) -> None:
        """Recursively extract quoted identifier names from an AST."""
        from ..translator.types import (
            SQLIdentifier, SQLBinaryOp, SQLFunctionCall, SQLQualifiedIdentifier,
            SQLUnaryOp, SQLCase, SQLExists, SQLSubquery, SQLSelect, SQLAlias,
        )
        if isinstance(expr, SQLIdentifier) and expr.quoted:
            names.add(expr.name)
        elif isinstance(expr, SQLQualifiedIdentifier):
            if expr.parts and expr.parts[0].startswith('"') and expr.parts[0].endswith('"'):
                names.add(expr.parts[0].strip('"'))
        elif isinstance(expr, SQLBinaryOp):
            self._extract_cte_names_from_ast(expr.left, names)
            self._extract_cte_names_from_ast(expr.right, names)
        elif isinstance(expr, SQLFunctionCall):
            for arg in (expr.args or []):
                self._extract_cte_names_from_ast(arg, names)
        elif isinstance(expr, SQLUnaryOp):
            self._extract_cte_names_from_ast(expr.operand, names)
        elif isinstance(expr, SQLCase):
            for when_expr, then_expr in (expr.when_clauses or []):
                self._extract_cte_names_from_ast(when_expr, names)
                self._extract_cte_names_from_ast(then_expr, names)
            if expr.else_clause:
                self._extract_cte_names_from_ast(expr.else_clause, names)
        elif isinstance(expr, SQLExists):
            self._extract_cte_names_from_ast(expr.subquery, names)
        elif isinstance(expr, SQLSubquery):
            self._extract_cte_names_from_ast(expr.query, names)
        elif isinstance(expr, SQLSelect):
            # Extract from FROM clause identifier (the CTE being queried)
            if expr.from_clause is not None:
                from_target = expr.from_clause
                if isinstance(from_target, SQLAlias):
                    from_target = from_target.expr
                if isinstance(from_target, SQLIdentifier) and from_target.quoted:
                    names.add(from_target.name)
                else:
                    self._extract_cte_names_from_ast(from_target, names)
            if expr.where is not None:
                self._extract_cte_names_from_ast(expr.where, names)

    def _inject_audit_evidence(
        self,
        expr: "SQLExpression",
        evidence_parts: list,
        definition_name: str = "",
    ) -> "SQLExpression":
        """
        Replace the outermost audit macro with a struct_pack that includes evidence.

        Two evidence strategies are supported (see ``_collect_audit_evidence_exprs``):

        1. ``"CTE"._audit_item`` — the CTE was LEFT-JOINed and carries a pre-built
           ``_audit_item`` struct per row.  Wrapped in ``list_value()`` with a NULL guard.

        2. ``<SUBQUERY:CTE_NAME>`` — the CTE is a RESOURCE_ROWS definition CTE without
           ``_audit_item``.  A correlated subquery aggregates evidence items directly
           from the CTE's ``resource`` column.

        When ``definition_name`` is provided, each evidence item's ``trace`` field is
        appended with the definition name to create a breadcrumb trail.
        """
        from ..translator.types import SQLRaw, SQLFunctionCall

        _audit_fn_names = {"audit_and", "audit_or", "audit_or_all", "audit_not", "audit_leaf"}

        # Build individual evidence list expressions, one per CTE.
        part_exprs: list[str] = []
        _evidence_alias_counter = 0
        for p in evidence_parts:
            if p.startswith('<SUBQUERY:'):
                cte_name = p[len('<SUBQUERY:'):-1]
                quoted = f'"{cte_name}"'
                # Extract resource type from CTE name (e.g., "Condition: Diabetes" → "Condition")
                resource_type = cte_name.split(":")[0].strip() if ":" in cte_name else cte_name
                escaped_cte = cte_name.replace("'", "''")
                # Friendly label for the "threshold" field: prefer the valueset/code alias part of
                # the CTE name (e.g. "Condition: Essential Hypertension" → "Essential Hypertension").
                # For definition CTEs without a ":" (e.g. "Essential Hypertension Diagnosis"),
                # use the definition name itself — this is more informative than the raw resourceType.
                if ": " in cte_name:
                    friendly_right = cte_name.split(": ", 1)[1].split(" (")[0]
                else:
                    friendly_right = cte_name
                escaped_right = friendly_right.replace("'", "''")
                # Correlated subquery: collect evidence structs from the resource column.
                # When no resources match, emit an 'absent' sentinel for care gap analysis.
                # Present evidence starts with trace=[cte_name] so that when the parent
                # definition appends its own name the full chain is preserved.
                part_exprs.append(
                    f"COALESCE("
                    f"(SELECT CASE WHEN count(*) = 0 THEN list_value(struct_pack("
                    f"target := '{resource_type}', "
                    f"attribute := CAST(NULL AS VARCHAR), "
                    f"value := CAST(NULL AS VARCHAR), "
                    f"operator := 'absent', "
                    f"threshold := \'{escaped_cte}\', "
                    f"trace := CAST([] AS VARCHAR[])"
                    f")) ELSE list(struct_pack("
                    f"target := COALESCE(fhirpath_text(_sub.resource, 'resourceType'), '') || '/' || COALESCE(fhirpath_text(_sub.resource, 'id'), ''), "
                    f"attribute := CAST(NULL AS VARCHAR), "
                    f"value := CAST(NULL AS VARCHAR), "
                    f"operator := 'exists', "
                    f"threshold := \'{escaped_right}\', "
                    f"trace := CAST(['{escaped_cte}'] AS VARCHAR[])"
                    f")) END FROM {quoted} AS _sub WHERE _sub.patient_id = p.patient_id), "
                    f"[])"
                )
            elif p.startswith('<CMP_EVIDENCE:'):
                # Strategy 4a: Two-column pre-compute CTE → _cmp_result.evidence
                # Propagates comparison evidence (actual, threshold, operator, attribute) from
                # sub-definitions like "Has Diastolic BP < 90" to parent definitions.
                precte_name = p[len('<CMP_EVIDENCE:'):-1]
                alias = f"__cmp_{_evidence_alias_counter}"
                _evidence_alias_counter += 1
                part_exprs.append(
                    f'COALESCE('
                    f'(SELECT {alias}._cmp_result.evidence '
                    f'FROM "{precte_name}" AS {alias} '
                    f'WHERE {alias}.patient_id = p.patient_id), '
                    f'[])'
                )
            elif p.startswith('<BOOL_EVIDENCE:'):
                # Strategy 4b: Regular Boolean definition CTE → _audit_result.evidence
                # Propagates evidence from compound Boolean sub-definitions.
                bool_cte = p[len('<BOOL_EVIDENCE:'):-1]
                alias = f"__bev_{_evidence_alias_counter}"
                _evidence_alias_counter += 1
                part_exprs.append(
                    f'COALESCE('
                    f'(SELECT {alias}._audit_result.evidence '
                    f'FROM "{bool_cte}" AS {alias} '
                    f'WHERE {alias}.patient_id = p.patient_id), '
                    f'[])'
                )
            else:
                # JOIN-based: CTE._audit_item column is already available.
                # When NULL (no matching row), emit an 'absent' sentinel.
                # Extract CTE name from the evidence part (format: "CTE_NAME"._audit_item)
                cte_ref = p.replace("._audit_item", "").strip('"')
                resource_type = cte_ref.split(":")[0].strip() if ":" in cte_ref else cte_ref
                escaped_ref = cte_ref.replace("'", "''")
                part_exprs.append(
                    f"CASE WHEN {p} IS NOT NULL THEN list_value({p}) "
                    f"ELSE list_value(struct_pack("
                    f"target := '{resource_type}', "
                    f"attribute := CAST(NULL AS VARCHAR), "
                    f"value := CAST(NULL AS VARCHAR), "
                    f"operator := 'absent', "
                    f"threshold := \'{escaped_ref}\', "
                    f"trace := CAST([] AS VARCHAR[])"
                    f")) END"
                )

        if not part_exprs:
            return expr

        if len(part_exprs) == 1:
            evidence_sql = part_exprs[0]
        else:
            evidence_sql = "list_concat(" + ", ".join(part_exprs) + ")"

        # Append definition name to each evidence item's trace field for breadcrumb trail
        if definition_name:
            escaped_name = definition_name.replace("'", "''")
            evidence_sql = (
                f"list_transform({evidence_sql}, _ev -> struct_pack("
                f"target := _ev.target, "
                f"attribute := _ev.attribute, "
                f"value := _ev.value, "
                f"operator := _ev.operator, "
                f"threshold := _ev.threshold, "
                f"trace := list_append(COALESCE(_ev.trace, CAST([] AS VARCHAR[])), '{escaped_name}')"
                f"))"
            )

        if isinstance(expr, SQLFunctionCall) and expr.name in _audit_fn_names:
            expr_sql = expr.to_sql()
            return SQLRaw(
                f"struct_pack(result := ({expr_sql}).result, "
                f"evidence := list_concat(COALESCE(({expr_sql}).evidence, []), {evidence_sql}))"
            )

        if isinstance(expr, SQLRaw):
            # Handle _flatten_audit_tree output: struct_pack(result := ..., evidence := ...)
            raw = expr.raw_sql
            ev_marker = ', evidence :='
            ev_idx = raw.find(ev_marker)
            if ev_idx != -1 and 'struct_pack(result :=' in raw[:ev_idx + 1]:
                pre = raw[:ev_idx]
                after = raw[ev_idx + len(ev_marker):]
                # Find the closing ')' of the outermost struct_pack via paren-depth tracking.
                depth = 0
                close_idx = len(after)
                for i, c in enumerate(after):
                    if c == '(':
                        depth += 1
                    elif c == ')':
                        if depth == 0:
                            close_idx = i
                            break
                        depth -= 1
                inner_ev = after[:close_idx]
                return SQLRaw(
                    f"{pre}{ev_marker} list_concat(COALESCE({inner_ev}, []), {evidence_sql}))"
                )
            # Handle SQLRaw containing an audit function call (e.g. after pre-compute
            # name substitution converted a SQLFunctionCall to SQLRaw).
            for fn in _audit_fn_names:
                if raw.startswith(f'{fn}('):
                    return SQLRaw(
                        f"struct_pack(result := ({raw}).result, "
                        f"evidence := list_concat(COALESCE(({raw}).evidence, []), {evidence_sql}))"
                    )

        return expr
