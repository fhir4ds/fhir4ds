"""
Inference mixin for CQLToSQLTranslator.

This module contains methods responsible for type inference, cardinality
inference, row-shape inference, topological sorting of definitions, and
resource-column detection during CQL-to-SQL translation.
The ``InferenceMixin`` class is intended to be used as a mixin with
``CQLToSQLTranslator`` and relies on attributes (``self._context``,
``self._retrieve_ctes``, etc.) initialised by the translator's ``__init__``.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Set

_logger = logging.getLogger(__name__)

from ..errors import TranslationError
from ..parser.ast_nodes import (
    Definition,
    Expression,
    FunctionDefinition,
    FunctionRef,
    Library,
    MethodInvocation,
)
from ..translator.types import (
    CTEDefinition,
    SQLSelect,
)

if TYPE_CHECKING:
    from ..translator.types import SQLExpression


class InferenceMixin:
    """Mixin providing inference methods for CQLToSQLTranslator."""

    def _topological_sort_ast_definitions(self, library: Library) -> List[Definition]:
        """
        Sort Definition AST nodes in dependency order before translation.

        This ensures that definitions are translated in an order where
        dependencies come before dependents, preventing forward reference
        issues during translation.

        Args:
            library: The parsed CQL library AST.

        Returns:
            List of Definition AST nodes in dependency order.

        Raises:
            TranslationError: If a cyclic dependency is detected.
        """
        from collections import deque

        # Collect all definition nodes
        definitions = [
            stmt for stmt in library.statements if isinstance(stmt, Definition)
        ]

        if not definitions:
            return []

        # Build name set and mapping
        def_names = {d.name for d in definitions}
        name_to_def = {d.name: d for d in definitions}

        # Build dependency graph: name -> set of names it depends on
        dependencies: Dict[str, Set[str]] = {}
        for defn in definitions:
            deps = self._extract_definition_dependencies(defn.expression, def_names)
            dependencies[defn.name] = deps

        # Kahn's algorithm for topological sort
        # Calculate in-degree (number of dependencies each definition has)
        in_degree = {name: len(deps) for name, deps in dependencies.items()}

        # Build reverse adjacency (what depends on this)
        dependents: Dict[str, List[str]] = {name: [] for name in def_names}
        for name, deps in dependencies.items():
            for dep in deps:
                if dep in dependents:
                    dependents[dep].append(name)

        # Start with definitions that have no dependencies
        queue = deque([name for name, degree in in_degree.items() if degree == 0])
        result_names = []

        while queue:
            # Sort queue for deterministic output (convert to list, sort, convert back)
            sorted_queue = sorted(queue)
            queue = deque(sorted_queue)
            current = queue.popleft()
            result_names.append(current)

            # Reduce in-degree for dependents
            for dependent in dependents[current]:
                in_degree[dependent] -= 1
                if in_degree[dependent] == 0:
                    queue.append(dependent)

        # Check for cycles
        if len(result_names) != len(def_names):
            remaining = def_names - set(result_names)
            raise TranslationError(
                f"Cyclic dependency detected among definitions: {remaining}"
            )

        # Return Definition objects in sorted order
        return [name_to_def[name] for name in result_names]

    def _topological_sort_definitions(
        self, library: Library, definitions: Dict[str, SQLExpression]
    ) -> List[str]:
        """
        Sort definitions in dependency order using topological sort.

        Definitions that reference other definitions must come after
        their dependencies.

        Args:
            library: The parsed CQL library AST.
            definitions: Dictionary of definition names to SQL expressions.

        Returns:
            List of definition names in dependency order.
        """
        # Build dependency graph
        dependencies: Dict[str, Set[str]] = {}
        definition_names = set(definitions.keys())

        # Collect function bodies for transitive dependency detection.
        # When a definition calls a function, we must also trace through
        # the function body to find definition references introduced by inlining.
        function_bodies: Dict[str, Expression] = {}
        for statement in library.statements:
            if isinstance(statement, FunctionDefinition) and statement.expression:
                function_bodies[statement.name] = statement.expression
        # Also collect from included libraries
        for lib_alias, lib_info in self._context.includes.items():
            if hasattr(lib_info, 'functions'):
                for fname, fdef in lib_info.functions.items():
                    if hasattr(fdef, 'expression') and fdef.expression:
                        function_bodies[fname] = fdef.expression
                        function_bodies[f"{lib_alias}.{fname}"] = fdef.expression

        # Extract dependencies from each definition's expression
        for statement in library.statements:
            if isinstance(statement, Definition):
                name = statement.name
                deps = self._extract_definition_dependencies(
                    statement.expression, definition_names,
                    function_bodies=function_bodies,
                )
                dependencies[name] = deps

        # Kahn's algorithm for topological sort
        # Calculate in-degree (number of definitions that depend on each)
        in_degree: Dict[str, int] = {name: 0 for name in definition_names}
        for name, deps in dependencies.items():
            for dep in deps:
                if dep in in_degree:
                    in_degree[name] += 1

        # Build reverse adjacency (what depends on this)
        dependents: Dict[str, List[str]] = {name: [] for name in definition_names}
        for name, deps in dependencies.items():
            for dep in deps:
                if dep in dependents:
                    dependents[dep].append(name)

        # Start with definitions that have no dependencies
        queue = [name for name, degree in in_degree.items() if degree == 0]
        result = []

        while queue:
            # Sort queue for deterministic output
            queue.sort()
            current = queue.pop(0)
            result.append(current)

            # Reduce in-degree for dependents
            for dependent in dependents[current]:
                in_degree[dependent] -= 1
                if in_degree[dependent] == 0:
                    queue.append(dependent)

        # Check for cycles (should not happen with valid CQL)
        if len(result) != len(definition_names):
            # Return in declaration order as fallback
            result = []
            for statement in library.statements:
                if isinstance(statement, Definition):
                    result.append(statement.name)

        return result

    def _extract_definition_dependencies(
        self, expr: Expression, definition_names: Set[str],
        function_bodies: Optional[Dict[str, Expression]] = None,
        _visited_functions: Optional[Set[str]] = None,
    ) -> Set[str]:
        """
        Extract definition names referenced in an expression.

        Also traces through function bodies to detect transitive dependencies
        introduced by function inlining (e.g., a function that references
        a definition not directly visible in the caller's AST).

        Args:
            expr: The expression to analyze.
            definition_names: Set of all valid definition names.
            function_bodies: Map of function names to their body expressions.
            _visited_functions: Guard against infinite recursion in function bodies.

        Returns:
            Set of definition names referenced in the expression.
        """
        deps = set()
        if function_bodies is None:
            function_bodies = {}
        if _visited_functions is None:
            _visited_functions = set()

        from ..parser.ast_nodes import Identifier, QualifiedIdentifier

        if isinstance(expr, Identifier):
            if expr.name in definition_names:
                deps.add(expr.name)
        elif isinstance(expr, QualifiedIdentifier):
            # Could be a qualified reference like Library.Definition
            if len(expr.parts) == 1 and expr.parts[0] in definition_names:
                deps.add(expr.parts[0])
            elif len(expr.parts) == 2 and expr.parts[1] in definition_names:
                # Library.Definition reference
                deps.add(expr.parts[1])

        # Trace through function bodies for transitive dependencies
        if isinstance(expr, FunctionRef) and function_bodies:
            func_name = expr.name
            # Try both unqualified and qualified names
            body = function_bodies.get(func_name)
            if body is None and '.' in func_name:
                body = function_bodies.get(func_name.split('.', 1)[1])
            if body is not None and func_name not in _visited_functions:
                _visited_functions.add(func_name)
                deps.update(self._extract_definition_dependencies(
                    body, definition_names, function_bodies, _visited_functions,
                ))

        # Also trace fluent function calls (MethodInvocation)
        if isinstance(expr, MethodInvocation) and function_bodies:
            method_name = expr.method
            body = function_bodies.get(method_name)
            if body is not None and method_name not in _visited_functions:
                _visited_functions.add(method_name)
                deps.update(self._extract_definition_dependencies(
                    body, definition_names, function_bodies, _visited_functions,
                ))

        # Recursively check child expressions
        for child in self._get_child_expressions(expr):
            deps.update(self._extract_definition_dependencies(
                child, definition_names, function_bodies, _visited_functions,
            ))

        return deps

    def _get_child_expressions(self, expr: Expression) -> List[Expression]:
        """
        Get child expressions from an AST node.

        Args:
            expr: The expression to get children from.

        Returns:
            List of child expressions.
        """
        children = []

        # Common attributes that may contain single Expression values
        expr_attrs = [
            'left', 'right', 'operand', 'operand_left', 'operand_right',
            'source', 'condition', 'then_expr', 'else_expr',
            'low', 'high', 'expression', 'when', 'then',
            'where',  # Query where clause
            'return_clause',  # Query return clause
            'sort',  # Query sort clause
            'aggregate',  # Query aggregate clause
            'such_that',  # WithClause such_that
            'initializer',  # AggregateExpression initializer
            'index',  # IndexerExpression index
            'count',  # Skip/TakeExpression count
        ]

        for attr in expr_attrs:
            if hasattr(expr, attr):
                value = getattr(expr, attr)
                if value is not None:
                    if isinstance(value, Expression):
                        children.append(value)
                    elif hasattr(value, 'expression'):
                        # Handle AST nodes like WhereClause, ReturnClause, SortClause
                        # that have an expression attribute but are not Expression instances
                        child_expr = getattr(value, 'expression')
                        if child_expr is not None and isinstance(child_expr, Expression):
                            children.append(child_expr)

        # Attributes that contain lists of expressions or AST nodes with expressions
        list_attrs = [
            'arguments', 'elements',  # Function arguments, list elements
            'with_clauses', 'let_clauses', 'relationships',  # Query clauses
        ]

        for attr in list_attrs:
            if hasattr(expr, attr):
                value = getattr(expr, attr)
                if value is not None:
                    if isinstance(value, list):
                        for item in value:
                            if isinstance(item, Expression):
                                children.append(item)
                            elif hasattr(item, 'expression'):
                                # Handle AST nodes like QuerySource, WithClause, LetClause
                                child_expr = getattr(item, 'expression')
                                if isinstance(child_expr, Expression):
                                    children.append(child_expr)
                                # Also check for such_that in WithClause
                                if hasattr(item, 'such_that'):
                                    such_that = getattr(item, 'such_that')
                                    if isinstance(such_that, Expression):
                                        children.append(such_that)

        # Handle Query.source specially - can be QuerySource or list of QuerySource
        # QuerySource is an ASTNode with an expression attribute, not an Expression
        if hasattr(expr, 'source'):
            source = getattr(expr, 'source')
            if source is not None:
                if isinstance(source, Expression):
                    children.append(source)
                elif hasattr(source, 'expression'):
                    # QuerySource or similar AST node
                    child_expr = getattr(source, 'expression')
                    if isinstance(child_expr, Expression):
                        children.append(child_expr)
                elif isinstance(source, list):
                    for item in source:
                        if isinstance(item, Expression):
                            children.append(item)
                        elif hasattr(item, 'expression'):
                            child_expr = getattr(item, 'expression')
                            if isinstance(child_expr, Expression):
                                children.append(child_expr)

        return children

    def _infer_row_shape(self, ast_node: Any, _visited: set | None = None) -> "RowShape":
        """
        Infer the row shape of an expression from its AST.

        Determines what an expression produces in terms of rows per patient:
        - PATIENT_SCALAR: Exactly 1 row per patient (boolean, number, string)
        - RESOURCE_ROWS: Many rows per patient (one per resource)
        - UNKNOWN: Forward reference or complex expression

        Args:
            ast_node: The AST node to analyze.
            _visited: Set of definition names already visited (cycle guard).

        Returns:
            RowShape enum value indicating the row shape.
        """
        from ..translator.context import RowShape
        from ..parser.ast_nodes import (
            Retrieve, ExistsExpression, FirstExpression, LastExpression,
            SingletonExpression, FunctionRef, Property, BinaryExpression,
            ConditionalExpression, UnaryExpression, Identifier, Query,
            MethodInvocation, QualifiedIdentifier, Literal, Interval,
            ListExpression, DistinctExpression,
        )

        if ast_node is None:
            return RowShape.UNKNOWN

        if _visited is None:
            _visited = set()

        # Literal values (true, false, 42, 'hello') are patient-independent scalars
        if isinstance(ast_node, Literal):
            return RowShape.PATIENT_SCALAR

        # Interval expressions are scalar values (one interval per patient)
        if isinstance(ast_node, Interval):
            return RowShape.PATIENT_SCALAR

        # CQL list literals are scalar collection values: one list per patient.
        if isinstance(ast_node, ListExpression):
            return RowShape.PATIENT_SCALAR

        # Retrieve always produces RESOURCE_ROWS
        if isinstance(ast_node, Retrieve):
            return RowShape.RESOURCE_ROWS

        # Existence check produces scalar boolean
        if isinstance(ast_node, ExistsExpression):
            return RowShape.PATIENT_SCALAR

        if isinstance(ast_node, DistinctExpression):
            source_shape = self._infer_row_shape(ast_node.source, _visited)
            if source_shape == RowShape.PATIENT_SCALAR:
                return RowShape.PATIENT_SCALAR
            return source_shape

        # First/Last/singleton produce scalar (single resource or value)
        if isinstance(ast_node, (FirstExpression, LastExpression, SingletonExpression)):
            return RowShape.PATIENT_SCALAR

        # Aggregate functions produce scalar
        if isinstance(ast_node, FunctionRef):
            func_name = ast_node.name.lower() if hasattr(ast_node, 'name') else ''
            if func_name in ('count', 'sum', 'avg', 'min', 'max', 'allaretrue',
                            'anyistrue', 'allarefalse', 'anyisfalse'):
                return RowShape.PATIENT_SCALAR
            # First/Last/Singleton functions produce scalar (single value)
            if func_name in ('first', 'last', 'singleton', 'singletonfrom'):
                return RowShape.PATIENT_SCALAR
            if func_name in ('flatten', 'distinct'):
                return RowShape.PATIENT_SCALAR
            # Constructor functions that produce scalar values
            if func_name in ('datetime', 'date', 'time', 'now', 'today', 'timeofdayvalue',
                            'tointeger', 'todecimal', 'tostring', 'toboolean',
                            'tolong', 'todate', 'todatetime', 'totime',
                            'toquantity', 'toratio', 'toconcept',
                            'abs', 'ceiling', 'floor', 'truncate', 'round',
                            'length', 'indexof', 'substring', 'lower', 'upper',
                            'combine', 'concatenate'):
                return RowShape.PATIENT_SCALAR
            # distinct(X) preserves shape of argument
            if func_name == 'distinct' and ast_node.arguments:
                return self._infer_row_shape(ast_node.arguments[0], _visited)

        # MethodInvocation (fluent functions like .isProcedurePerformed()) inherits source shape
        if isinstance(ast_node, MethodInvocation):
            return self._infer_row_shape(ast_node.source, _visited)

        # Property access on RESOURCE_ROWS produces PATIENT_MULTI_VALUE (projection)
        if isinstance(ast_node, Property):
            # Library-qualified definition references like CQMCommon."Inpatient Encounter"
            # are parsed as Property(source=Identifier("CQMCommon"), path="Inpatient Encounter").
            # Resolve using the prefixed name in definition_meta.
            if isinstance(ast_node.source, Identifier) and ast_node.path:
                prefixed = f"{ast_node.source.name}.{ast_node.path}"
                meta = self._context.definition_meta.get(prefixed)
                if meta:
                    return meta.shape
                if hasattr(self._context, 'expression_definitions'):
                    ast_def = self._context.expression_definitions.get(prefixed)
                    if ast_def is not None:
                        if prefixed in _visited:
                            return RowShape.UNKNOWN
                        _visited.add(prefixed)
                        return self._infer_row_shape(ast_def, _visited)
            source_shape = self._infer_row_shape(ast_node.source, _visited)
            if source_shape == RowShape.RESOURCE_ROWS:
                return RowShape.PATIENT_MULTI_VALUE
            return source_shape

        # Binary expressions
        if isinstance(ast_node, BinaryExpression):
            op = getattr(ast_node, 'operator', '').lower()

            # Comparison and temporal operators produce scalar boolean
            if op in ('=', '!=', '<>', '<', '>', '<=', '>=',
                      'and', 'or', 'xor', 'implies',
                      'on or before', 'on or after', 'before', 'after',
                      'starts', 'ends', 'during', 'overlaps', 'in',
                      '~', '!~', 'equivalent', 'not equivalent',
                      'same or before', 'same or after',
                      'includes', 'included in',
                      'properly includes', 'properly included in',
                      'meets', 'meets before', 'meets after',
                      'contains', 'precision of'):
                return RowShape.PATIENT_SCALAR
            # Precision-qualified same operators: "same or before month of", etc.
            if op.startswith('same '):
                return RowShape.PATIENT_SCALAR

            # Set operations: shape depends on operand shapes
            if op in ('union', 'intersect', 'except'):
                left_shape = self._infer_row_shape(ast_node.left, _visited)
                right_shape = self._infer_row_shape(ast_node.right, _visited)
                # If either side is RESOURCE_ROWS, result is RESOURCE_ROWS
                if left_shape == RowShape.RESOURCE_ROWS or right_shape == RowShape.RESOURCE_ROWS:
                    return RowShape.RESOURCE_ROWS
                # If either side is PATIENT_MULTI_VALUE, result is PATIENT_MULTI_VALUE
                if left_shape == RowShape.PATIENT_MULTI_VALUE or right_shape == RowShape.PATIENT_MULTI_VALUE:
                    return RowShape.PATIENT_MULTI_VALUE
                # Scalar CQL list set operators produce a scalar list value.
                left_type = self._infer_cql_type(ast_node.left)
                right_type = self._infer_cql_type(ast_node.right)
                if left_type.startswith("List<") or right_type.startswith("List<"):
                    return RowShape.PATIENT_SCALAR
                return RowShape.RESOURCE_ROWS

            if op in ('+', '-', '*', '/', 'div', 'mod'):
                return RowShape.PATIENT_SCALAR

        # Conditional: if either branch is RESOURCE_ROWS, result is RESOURCE_ROWS
        if isinstance(ast_node, ConditionalExpression):
            then_shape = self._infer_row_shape(ast_node.then_expr, _visited)
            else_shape = self._infer_row_shape(ast_node.else_expr, _visited)
            if then_shape == RowShape.RESOURCE_ROWS or else_shape == RowShape.RESOURCE_ROWS:
                return RowShape.RESOURCE_ROWS
            return RowShape.PATIENT_SCALAR

        # Unary NOT produces scalar boolean
        if isinstance(ast_node, UnaryExpression):
            op = getattr(ast_node, 'operator', '').lower()
            if op in ('not', 'is null', 'is not null'):
                return RowShape.PATIENT_SCALAR

        # Check if it's an identifier referencing a known definition
        if isinstance(ast_node, Identifier):
            meta = self._context.definition_meta.get(ast_node.name)
            if meta:
                return meta.shape
            if hasattr(self._context, 'expression_definitions'):
                ast_def = self._context.expression_definitions.get(ast_node.name)
                if ast_def is not None:
                    if ast_node.name in _visited:
                        return RowShape.UNKNOWN
                    _visited.add(ast_node.name)
                    return self._infer_row_shape(ast_def, _visited)

        # Library-qualified reference (e.g., CQMCommon."Inpatient Encounter")
        if isinstance(ast_node, QualifiedIdentifier) and ast_node.parts:
            prefixed_name = ".".join(ast_node.parts)
            meta = self._context.definition_meta.get(prefixed_name)
            if meta:
                return meta.shape
            # Try without prefix (first part is library alias)
            if len(ast_node.parts) >= 2:
                short_name = ".".join(ast_node.parts[1:])
                meta = self._context.definition_meta.get(short_name)
                if meta:
                    return meta.shape
            if hasattr(self._context, 'expression_definitions'):
                ast_def = self._context.expression_definitions.get(prefixed_name)
                if ast_def is not None:
                    if prefixed_name in _visited:
                        return RowShape.UNKNOWN
                    _visited.add(prefixed_name)
                    return self._infer_row_shape(ast_def, _visited)

        # Query with return clause: shape depends on what's returned
        # Query without return clause inherits shape from source
        if isinstance(ast_node, Query):
            if ast_node.return_clause:
                from ..parser.ast_nodes import TupleExpression
                ret_expr = ast_node.return_clause.expression
                if isinstance(ret_expr, TupleExpression):
                    # Tuple returns produce multi-field rows that downstream
                    # code accesses with fhirpath_text(resource, 'field').
                    # Classify as RESOURCE_ROWS so the CTE stores
                    # (patient_id, resource) with JSON data.
                    return RowShape.RESOURCE_ROWS
                if isinstance(ret_expr, Identifier):
                    sources = ast_node.source if isinstance(ast_node.source, list) else [ast_node.source]
                    for source in sources:
                        if hasattr(source, "alias") and source.alias == ret_expr.name:
                            source_expr = getattr(source, "expression", source)
                            return self._infer_row_shape(source_expr, _visited)
                if self._query_return_expr_is_resource(ast_node, ret_expr, _visited):
                    return RowShape.RESOURCE_ROWS
                return RowShape.PATIENT_MULTI_VALUE
            # Without return clause, shape comes from source
            if ast_node.source:
                if isinstance(ast_node.source, list) and ast_node.source:
                    return self._infer_row_shape(ast_node.source[0].expression, _visited)
                elif hasattr(ast_node.source, 'expression'):
                    return self._infer_row_shape(ast_node.source.expression, _visited)
            return RowShape.RESOURCE_ROWS  # Default for queries

        # Default: unknown
        return RowShape.UNKNOWN

    def _cte_has_resource_column(self, cte: CTEDefinition) -> bool:
        """
        Check if CTE includes a resource column.

        Args:
            cte: The CTE definition to check.

        Returns:
            True if the CTE includes a 'resource' column, False otherwise.
        """
        if hasattr(cte, 'columns') and cte.columns:
            return 'resource' in [c.lower() for c in cte.columns]
        # Check query AST for resource column
        from ..translator import ast_utils
        if hasattr(cte, 'query') and isinstance(cte.query, SQLSelect):
            return ast_utils.select_has_column(cte.query, "resource")
        return False

    def _cte_has_resource_column_ast(self, ast) -> bool:
        """
        Check if an AST expression includes a resource column by walking the AST.

        This is used during Phase 1 translation when to_sql() cannot be called
        because placeholders haven't been resolved yet.

        Args:
            ast: The SQL AST to check.

        Returns:
            True if the AST includes a 'resource' column reference.
        """
        from ..translator.types import (
            SQLSelect, SQLAlias, SQLIdentifier, SQLFunctionCall,
            SQLBinaryOp, SQLCase, SQLSubquery, SQLUnion, SQLCast,
            SQLLambda, SQLList, SQLArray, SQLJoin
        )
        from ..translator.placeholder import RetrievePlaceholder

        if ast is None:
            return False

        # RetrievePlaceholder always produces a resource column
        if isinstance(ast, RetrievePlaceholder):
            return True

        # DeferredTemplateSubstitution wraps a retrieve — resource column present
        if hasattr(ast, '_resource_expr'):
            return True

        # Check if this is an identifier named 'resource'
        if isinstance(ast, SQLIdentifier):
            if ast.name.lower() == 'resource':
                return True
            # Check for column references like "table.resource"
            if '.' in ast.name and ast.name.lower().endswith('.resource'):
                return True
            return False

        # Check SQLAlias for resource column
        if isinstance(ast, SQLAlias):
            if ast.alias and ast.alias.lower() == 'resource':
                return True
            return self._cte_has_resource_column_ast(ast.expr)

        # Check SQLSelect columns
        if isinstance(ast, SQLSelect):
            for col in ast.columns:
                if isinstance(col, tuple):
                    # (expr, alias) tuple
                    if col[1] and col[1].lower() == 'resource':
                        return True
                    if self._cte_has_resource_column_ast(col[0]):
                        return True
                elif isinstance(col, SQLAlias):
                    if col.alias and col.alias.lower() == 'resource':
                        return True
                    if self._cte_has_resource_column_ast(col.expr):
                        return True
                elif self._cte_has_resource_column_ast(col):
                    return True
            # Check from_clause, joins, etc.
            if ast.from_clause and self._cte_has_resource_column_ast(ast.from_clause):
                return True
            if ast.joins:
                for join in ast.joins:
                    if self._cte_has_resource_column_ast(join):
                        return True
            if ast.where and self._cte_has_resource_column_ast(ast.where):
                return True
            return False

        # Check SQLFunctionCall arguments
        if isinstance(ast, SQLFunctionCall):
            for arg in ast.args:
                if self._cte_has_resource_column_ast(arg):
                    return True
            return False

        # Check SQLBinaryOp
        if isinstance(ast, SQLBinaryOp):
            return (self._cte_has_resource_column_ast(ast.left) or
                    self._cte_has_resource_column_ast(ast.right))

        # Check SQLCase
        if isinstance(ast, SQLCase):
            for cond, result in ast.when_clauses:
                if self._cte_has_resource_column_ast(cond) or self._cte_has_resource_column_ast(result):
                    return True
            if ast.else_clause and self._cte_has_resource_column_ast(ast.else_clause):
                return True
            return False

        # Check SQLSubquery
        if isinstance(ast, SQLSubquery):
            return self._cte_has_resource_column_ast(ast.query)

        # Check SQLUnion
        if isinstance(ast, SQLUnion):
            for op in ast.operands:
                if self._cte_has_resource_column_ast(op):
                    return True
            return False

        # Check SQLCast
        if isinstance(ast, SQLCast):
            return self._cte_has_resource_column_ast(ast.expression)

        # Check SQLLambda
        if isinstance(ast, SQLLambda):
            return self._cte_has_resource_column_ast(ast.body)

        # Check SQLList
        if isinstance(ast, SQLList):
            for item in ast.items:
                if self._cte_has_resource_column_ast(item):
                    return True
            return False

        # Check SQLArray
        if isinstance(ast, SQLArray):
            for elem in ast.elements:
                if self._cte_has_resource_column_ast(elem):
                    return True
            return False

        # Check SQLJoin
        if isinstance(ast, SQLJoin):
            if self._cte_has_resource_column_ast(ast.table):
                return True
            if ast.on_condition and self._cte_has_resource_column_ast(ast.on_condition):
                return True
            return False

        return False

    def _detect_quantity_fields(self, ast_node) -> Optional[set]:
        """Detect tuple field names that carry Quantity values.

        Inspects return clauses with ``TupleExpression`` and checks each
        element's expression for ``as Quantity`` casts (directly or through
        let-clause aliases).  Returns a set of field names, or ``None``
        if the definition doesn't have a Tuple return clause.
        """
        from ..parser.ast_nodes import (
            Query, TupleExpression, BinaryExpression,
            Identifier, NamedTypeSpecifier, Quantity as QuantityLiteral,
        )
        if not isinstance(ast_node, Query):
            return None
        if not ast_node.return_clause:
            return None
        ret_expr = ast_node.return_clause.expression
        if not isinstance(ret_expr, TupleExpression):
            return None
        # Build let-clause lookup for this query
        let_map: dict = {}
        for lc in (ast_node.let_clauses or []):
            if hasattr(lc, 'alias') and hasattr(lc, 'expression'):
                let_map[lc.alias] = lc.expression
        qty_fields: set = set()
        for elem in ret_expr.elements:
            name = elem.name if hasattr(elem, 'name') else None
            # TupleElement uses .type for the value expression
            expr = elem.type if hasattr(elem, 'type') else None
            if not name or not expr:
                continue
            if self._is_quantity_ast_expr(expr, let_map):
                qty_fields.add(name)
        return qty_fields if qty_fields else None

    @staticmethod
    def _property_chain_parts(ast_node: Any) -> tuple[Optional[str], list[str]]:
        """Return the root identifier and property path parts for a chain."""
        from ..parser.ast_nodes import Identifier, Property

        parts: list[str] = []
        current = ast_node
        while isinstance(current, Property):
            parts.append(current.path)
            current = current.source
        if isinstance(current, Identifier):
            parts.reverse()
            return current.name, parts
        return None, []

    @staticmethod
    def _fhir_type_to_cql_type(fhir_type: Optional[str]) -> Optional[str]:
        if not fhir_type:
            return None
        return {
            "boolean": "Boolean",
            "integer": "Integer",
            "positiveInt": "Integer",
            "unsignedInt": "Integer",
            "integer64": "Long",
            "decimal": "Decimal",
            "string": "String",
            "code": "String",
            "id": "String",
            "markdown": "String",
            "oid": "String",
            "uri": "String",
            "url": "String",
            "uuid": "String",
            "canonical": "String",
            "base64Binary": "String",
            "date": "Date",
            "dateTime": "DateTime",
            "instant": "DateTime",
            "time": "Time",
            "Quantity": "Quantity",
            "Ratio": "Ratio",
            "CodeableConcept": "Concept",
            "Coding": "Code",
        }.get(fhir_type)

    def _infer_fhir_property_type(self, resource_type: str, path: str) -> Optional[str]:
        """Infer CQL type for a FHIR property path from schema metadata."""
        schema = getattr(self._context, "fhir_schema", None)
        if schema is None:
            return None
        cql_type = self._fhir_type_to_cql_type(schema.get_element_type(resource_type, path))
        if cql_type is not None:
            return cql_type

        if "." not in path:
            return None
        head, tail = path.split(".", 1)
        if schema.get_element_type(resource_type, head) == "Quantity":
            return {
                "value": "Decimal",
                "unit": "String",
                "system": "String",
                "code": "String",
                "comparator": "String",
            }.get(tail)
        return None

    def _infer_query_return_property_type(self, query: Any, return_expr: Any) -> Optional[str]:
        """Infer property return type for simple aliased FHIR retrieve queries."""
        from ..parser.ast_nodes import QuerySource, Retrieve

        sources = query.source
        if not isinstance(sources, list):
            sources = [sources]
        alias_resource_types: dict[str, str] = {}
        for source in sources:
            if (
                isinstance(source, QuerySource)
                and source.alias
                and isinstance(source.expression, Retrieve)
            ):
                alias_resource_types[source.alias] = source.expression.type

        root_name, path_parts = self._property_chain_parts(return_expr)
        if not root_name or not path_parts:
            return None
        resource_type = alias_resource_types.get(root_name)
        if not resource_type:
            return None
        return self._infer_fhir_property_type(resource_type, ".".join(path_parts))

    def _is_fhir_resource_type(self, cql_type: Optional[str]) -> bool:
        """Return True when a CQL type name denotes a FHIR resource/profile."""
        if not cql_type:
            return False
        type_name = str(cql_type).strip()
        if type_name.startswith("List<") and type_name.endswith(">"):
            type_name = type_name[len("List<"):-1].strip()
        bare = type_name.split(".")[-1] if "." in type_name else type_name
        if bare == "Resource":
            return True

        registry = getattr(self._context, "profile_registry", None)
        if registry is not None and registry.resolve_named_profile(bare) is not None:
            return True

        schema = getattr(self._context, "fhir_schema", None)
        return bool(schema is not None and bare in getattr(schema, "resources", {}))

    def _definition_ast(self, name: str) -> Any:
        cql_asts = getattr(self._context, "_definition_cql_asts", {})
        ast_node = cql_asts.get(name)
        if ast_node is not None:
            return ast_node
        expr_defs = getattr(self._context, "expression_definitions", {})
        ast_def = expr_defs.get(name)
        if ast_def is None:
            return None
        return ast_def.expression if hasattr(ast_def, "expression") else ast_def

    def _query_alias_sources(self, query: Any) -> dict[str, Any]:
        from ..parser.ast_nodes import QuerySource

        sources = query.source if isinstance(query.source, list) else [query.source]
        alias_sources: dict[str, Any] = {}
        for source in sources:
            if isinstance(source, QuerySource) and source.alias:
                alias_sources[source.alias] = source.expression
        return alias_sources

    def _definition_tuple_field_type(
        self,
        definition_name: str,
        field_name: str,
        visited: Set[str],
    ) -> Optional[str]:
        """Infer the type of a tuple field returned by a named definition."""
        from ..parser.ast_nodes import FunctionRef, Identifier, Query, TupleExpression

        key = f"{definition_name}.{field_name}"
        if key in visited:
            return None
        visited.add(key)

        ast_node = self._definition_ast(definition_name)
        if ast_node is None:
            return None

        if isinstance(ast_node, Identifier):
            return self._definition_tuple_field_type(ast_node.name, field_name, visited)

        if isinstance(ast_node, FunctionRef) and ast_node.name.lower() in ("first", "last"):
            args = getattr(ast_node, "arguments", []) or []
            if args:
                ast_node = args[0]

        if not isinstance(ast_node, Query) or ast_node.return_clause is None:
            return None

        ret_expr = ast_node.return_clause.expression
        if not isinstance(ret_expr, TupleExpression):
            return None

        alias_sources = self._query_alias_sources(ast_node)
        for element in ret_expr.elements:
            if getattr(element, "name", None) != field_name:
                continue
            field_expr = getattr(element, "type", None)
            return self._infer_expr_type_in_query(field_expr, alias_sources, visited)
        return None

    def _infer_expr_type_in_query(
        self,
        expr: Any,
        alias_sources: dict[str, Any],
        visited: Set[str],
    ) -> str:
        """Infer a CQL type for an expression with query aliases in scope."""
        from ..parser.ast_nodes import Identifier, Property, Retrieve

        if isinstance(expr, Retrieve):
            return getattr(expr, "type", "Resource") or "Resource"

        if isinstance(expr, Identifier):
            source_expr = alias_sources.get(expr.name)
            if source_expr is not None:
                return self._infer_expr_type_in_query(source_expr, {}, visited)
            meta = self._context.definition_meta.get(expr.name)
            if meta and meta.cql_type and meta.cql_type != "Any":
                return meta.cql_type
            if expr.name not in visited:
                ast_node = self._definition_ast(expr.name)
                if ast_node is not None:
                    visited.add(expr.name)
                    return self._infer_cql_type(ast_node)
            return self._infer_cql_type(expr)

        if isinstance(expr, Property) and isinstance(expr.source, Identifier):
            source_expr = alias_sources.get(expr.source.name)
            if source_expr is not None:
                source_type = self._infer_expr_type_in_query(source_expr, {}, visited)
                if self._is_fhir_resource_type(source_type):
                    fhir_type = self._infer_fhir_property_type(
                        source_type[5:-1] if source_type.startswith("List<") else source_type,
                        expr.path,
                    )
                    if fhir_type:
                        return fhir_type
                if isinstance(source_expr, Identifier):
                    tuple_type = self._definition_tuple_field_type(
                        source_expr.name,
                        expr.path,
                        visited,
                    )
                    if tuple_type:
                        return tuple_type
            return self._infer_cql_type(expr)

        return self._infer_cql_type(expr)

    def _query_return_expr_is_resource(
        self,
        query: Any,
        return_expr: Any,
        visited: Set[str],
    ) -> bool:
        """Return True if a query return expression should be materialized as resource."""
        from ..parser.ast_nodes import Identifier, Property, TupleExpression

        if isinstance(return_expr, TupleExpression):
            return True

        alias_sources = self._query_alias_sources(query)

        if isinstance(return_expr, Identifier):
            for let_clause in getattr(query, "let_clauses", []) or []:
                if getattr(let_clause, "alias", None) == return_expr.name:
                    return self._is_fhir_resource_type(
                        self._infer_expr_type_in_query(let_clause.expression, alias_sources, visited)
                    )
            source_expr = alias_sources.get(return_expr.name)
            if source_expr is not None:
                return self._is_fhir_resource_type(
                    self._infer_expr_type_in_query(source_expr, {}, visited)
                )

        if isinstance(return_expr, Property) and isinstance(return_expr.source, Identifier):
            source_expr = alias_sources.get(return_expr.source.name)
            if isinstance(source_expr, Identifier):
                field_type = self._definition_tuple_field_type(
                    source_expr.name,
                    return_expr.path,
                    visited,
                )
                if field_type and self._is_fhir_resource_type(field_type):
                    return True

        return self._is_fhir_resource_type(
            self._infer_expr_type_in_query(return_expr, alias_sources, visited)
        )

    @staticmethod
    def _static_numeric_literal_value(ast_node: Any) -> int | float | None:
        from ..parser.ast_nodes import Literal, UnaryExpression

        if isinstance(ast_node, Literal) and isinstance(ast_node.value, (int, float)) and not isinstance(ast_node.value, bool):
            return ast_node.value
        if isinstance(ast_node, UnaryExpression) and ast_node.operator in {"+", "-"}:
            inner = InferenceMixin._static_numeric_literal_value(ast_node.operand)
            if inner is None:
                return None
            return -inner if ast_node.operator == "-" else inner
        return None

    def _infer_cql_type(self, ast_node: Any) -> str:
        """
        Infer the CQL type of an expression.

        Args:
            ast_node: The AST node to analyze.

        Returns:
            CQL type string (e.g., "Boolean", "Integer", "List<Condition>").
        """
        from ..parser.ast_nodes import (
            Retrieve, ExistsExpression, FunctionRef, Literal,
            BinaryExpression, Property, UnaryExpression, Identifier,
            FirstExpression, LastExpression, ConditionalExpression,
            DurationBetween, DifferenceBetween, Interval, CodeSelector,
            InstanceExpression, ListExpression, Quantity, DateTimeLiteral,
            TimeLiteral, DistinctExpression, TupleExpression,
        )

        if ast_node is None:
            return "Any"

        if isinstance(ast_node, CodeSelector):
            return "Code"

        if isinstance(ast_node, InstanceExpression):
            type_name = getattr(ast_node, "type", "")
            bare = type_name.split(".")[-1] if "." in type_name else type_name
            if bare in {
                "Code",
                "Concept",
                "ValueSet",
                "CodeSystem",
                "Vocabulary",
                "Quantity",
                "Ratio",
            }:
                return bare

        if isinstance(ast_node, Quantity):
            return "Quantity"

        if isinstance(ast_node, DateTimeLiteral):
            value = str(getattr(ast_node, "value", "") or "")
            if value.startswith("T"):
                return "Time"
            return "DateTime" if "T" in value else "Date"

        if isinstance(ast_node, TimeLiteral):
            return "Time"

        # DurationBetween / DifferenceBetween return Integer (years/months/days/etc. between)
        if isinstance(ast_node, (DurationBetween, DifferenceBetween)):
            return "Integer"

        # Retrieve returns List<ResourceType>
        if isinstance(ast_node, Retrieve):
            resource_type = getattr(ast_node, 'type', 'Resource')
            return f"List<{resource_type}>"

        # Exists returns Boolean
        if isinstance(ast_node, ExistsExpression):
            return "Boolean"

        if isinstance(ast_node, DistinctExpression):
            return self._infer_cql_type(ast_node.source)

        # Literals
        if isinstance(ast_node, Literal):
            explicit_type = getattr(ast_node, "type", None)
            if explicit_type:
                bare_type = str(explicit_type).split(".")[-1]
                if bare_type in {"Boolean", "Integer", "Long", "Decimal", "String"}:
                    return bare_type
            value = ast_node.value
            if isinstance(value, bool):
                return "Boolean"
            elif isinstance(value, int):
                return "Integer"
            elif isinstance(value, float):
                return "Decimal"
            elif isinstance(value, str):
                return "String"
            return "Any"

        if isinstance(ast_node, ListExpression):
            element_types = [
                element_type
                for element_type in (self._infer_cql_type(element) for element in ast_node.elements)
                if element_type != "Any"
            ]
            if not element_types:
                return "List<Any>"
            first_type = element_types[0]
            if all(element_type == first_type for element_type in element_types):
                return f"List<{first_type}>"
            return "List<Any>"

        if isinstance(ast_node, TupleExpression):
            fields = []
            for element in ast_node.elements:
                field_type = self._infer_cql_type(element.type)
                fields.append(f"{element.name}: {field_type}")
            return "Tuple{" + ", ".join(fields) + "}"

        # Interval expressions
        if isinstance(ast_node, Interval):
            point_type = "Any"
            if ast_node.low is not None:
                point_type = self._infer_cql_type(ast_node.low)
            elif ast_node.high is not None:
                point_type = self._infer_cql_type(ast_node.high)
            if point_type == "Any":
                _logger.warning(
                    "Could not infer point type for Interval expression — "
                    "defaulting to Interval<Any>. This may affect SQL generation."
                )
            return f"Interval<{point_type}>"

        # First/Last returns element type of source
        if isinstance(ast_node, (FirstExpression, LastExpression)):
            source_type = self._infer_cql_type(ast_node.source)
            if source_type.startswith("List<"):
                return source_type[5:-1]  # Extract inner type
            return "Any"

        # Function calls
        if isinstance(ast_node, FunctionRef):
            func_name = ast_node.name.lower() if hasattr(ast_node, 'name') else ''
            if func_name == 'count':
                return "Integer"
            elif func_name == 'indexof':
                return "Integer"
            elif func_name in ('sum', 'product', 'min', 'max'):
                if ast_node.arguments:
                    source_type = self._infer_cql_type(ast_node.arguments[0])
                    if source_type == "List<Long>":
                        return "Long"
                if func_name in ('min', 'max'):
                    return "Any"
                return "Decimal"
            elif func_name == 'avg':
                return "Decimal"
            elif func_name in ('abs',):
                if ast_node.arguments:
                    arg_type = self._infer_cql_type(ast_node.arguments[0])
                    if arg_type in {"Integer", "Long", "Decimal", "Quantity"}:
                        return arg_type
                return "Any"
            elif func_name in ('power',):
                arg_types = [self._infer_cql_type(arg) for arg in ast_node.arguments]
                if arg_types and all(arg_type in {"Integer", "Long"} for arg_type in arg_types):
                    exponent = ast_node.arguments[1] if len(ast_node.arguments) > 1 else None
                    if self._static_numeric_literal_value(exponent) is not None and self._static_numeric_literal_value(exponent) < 0:
                        return "Decimal"
                    if "Long" in arg_types:
                        return "Long"
                return "Decimal"
            elif func_name in ('minimum', 'maximum'):
                if ast_node.arguments and isinstance(ast_node.arguments[0], Identifier):
                    type_name = ast_node.arguments[0].name.split(".")[-1]
                    if type_name in {"Integer", "Long", "Decimal", "Date", "DateTime", "Time"}:
                        return type_name
                return "Any"
            elif func_name in ('first', 'last'):
                # Returns element type of source
                if ast_node.arguments:
                    source_type = self._infer_cql_type(ast_node.arguments[0])
                    if source_type.startswith("List<"):
                        return source_type[5:-1]  # Extract inner type
                return "Any"
            elif func_name == 'date':
                return "Date"
            elif func_name in ('datetime', 'now', 'today'):
                return "DateTime"
            elif func_name == 'time':
                return "Time"
            elif func_name == 'distinct':
                if ast_node.arguments:
                    return self._infer_cql_type(ast_node.arguments[0])
                return "List<Any>"
            elif func_name == 'flatten':
                if ast_node.arguments:
                    source_type = self._infer_cql_type(ast_node.arguments[0])
                    if source_type.startswith("List<List<") and source_type.endswith(">>"):
                        return f"List<{source_type[10:-2]}>"
                    if source_type.startswith("List<"):
                        return "List<Any>"
                return "List<Any>"
            elif func_name in {
                "toboolean",
                "tointeger",
                "tolong",
                "todecimal",
                "tostring",
                "todate",
                "todatetime",
                "totime",
                "toquantity",
                "toratio",
                "toconcept",
            }:
                return {
                    "toboolean": "Boolean",
                    "tointeger": "Integer",
                    "tolong": "Long",
                    "todecimal": "Decimal",
                    "tostring": "String",
                    "todate": "Date",
                    "todatetime": "DateTime",
                    "totime": "Time",
                    "toquantity": "Quantity",
                    "toratio": "Ratio",
                    "toconcept": "Concept",
                }[func_name]
            else:
                func_info = self.context.get_function(ast_node.name)
                if func_info and func_info.expression is not None:
                    return self._infer_cql_type(func_info.expression)

        # Binary comparisons and temporal operators return Boolean
        if isinstance(ast_node, BinaryExpression):
            op = getattr(ast_node, 'operator', '').lower()
            # "duration in X between" is parsed as BinaryExpression(op='in',
            # left=Identifier('duration'), right=DurationBetween(...)).
            # This is a duration computation, not a membership test — return Integer.
            if (op == 'in'
                    and isinstance(ast_node.left, Identifier)
                    and ast_node.left.name.lower() == 'duration'
                    and isinstance(ast_node.right, DurationBetween)):
                return "Integer"
            if op in ('=', '!=', '<>', '<', '>', '<=', '>=',
                      'and', 'or', 'xor', 'implies',
                      'on or before', 'on or after', 'before', 'after',
                      'starts', 'ends', 'during', 'overlaps', 'in',
                      '~', '!~', 'equivalent', 'not equivalent',
                      'same or before', 'same or after',
                      'includes', 'included in',
                      'properly includes', 'properly included in',
                      'meets', 'meets before', 'meets after',
                      'contains', 'is'):
                return "Boolean"
            # Precision-qualified same operators: "same or before month of", etc.
            if op.startswith('same '):
                return "Boolean"
            # intersect/union/except preserve the element type
            if op in ('intersect', 'union', 'except'):
                left_type = self._infer_cql_type(ast_node.left)
                if left_type != "Any":
                    return left_type
                return self._infer_cql_type(ast_node.right)
            if op in ('+', '-'):
                left_type = self._infer_cql_type(ast_node.left)
                right_type = self._infer_cql_type(ast_node.right)
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
            if op in ('*', '/', 'div', 'mod', '^'):
                left_type = self._infer_cql_type(ast_node.left)
                right_type = self._infer_cql_type(ast_node.right)
                if left_type == "Quantity" or right_type == "Quantity":
                    return "Quantity"
                if "Decimal" in (left_type, right_type) or op == '/':
                    return "Decimal"
                if "Long" in (left_type, right_type):
                    return "Long"
                if "Integer" in (left_type, right_type):
                    return "Integer"
                return "Any"
            # "as" cast: type is the target type specifier
            if op == 'as':
                from ..parser.ast_nodes import NamedTypeSpecifier
                ts = ast_node.right
                if isinstance(ts, NamedTypeSpecifier):
                    type_name = getattr(ts, 'name', None)
                    if type_name:
                        bare_type = type_name.split(".")[-1]
                        source_type = self._infer_cql_type(ast_node.left)
                        if bare_type == "Any":
                            return source_type
                        if bare_type == "Vocabulary" and source_type in {"ValueSet", "CodeSystem"}:
                            return source_type
                        return type_name
                elif isinstance(ts, Identifier):
                    bare_type = ts.name.split(".")[-1]
                    source_type = self._infer_cql_type(ast_node.left)
                    if bare_type == "Any":
                        return source_type
                    if bare_type == "Vocabulary" and source_type in {"ValueSet", "CodeSystem"}:
                        return source_type
                    return ts.name
            if op == 'convert':
                from ..parser.ast_nodes import NamedTypeSpecifier
                ts = ast_node.right
                source_type = self._infer_cql_type(ast_node.left)
                if isinstance(ts, NamedTypeSpecifier):
                    type_name = getattr(ts, 'name', None)
                    if type_name:
                        bare_type = type_name.split(".")[-1]
                        if bare_type == "Any":
                            return source_type
                        return type_name
                elif isinstance(ts, Identifier):
                    bare_type = ts.name.split(".")[-1]
                    if bare_type == "Any":
                        return source_type
                    return ts.name

        # Unary NOT returns Boolean; "singleton from" extracts element type
        if isinstance(ast_node, UnaryExpression):
            op = getattr(ast_node, 'operator', '').lower()
            if op in ('not', 'is null', 'is not null'):
                return "Boolean"
            if op in ('+', '-', 'predecessor of', 'successor of'):
                return self._infer_cql_type(ast_node.operand)
            if op == 'singleton from':
                operand_type = self._infer_cql_type(ast_node.operand)
                if operand_type.startswith("List<"):
                    return operand_type[5:-1]
                return operand_type

        # Conditional propagates branch types (if consistent)
        if isinstance(ast_node, ConditionalExpression):
            then_type = self._infer_cql_type(ast_node.then_expr)
            else_type = self._infer_cql_type(ast_node.else_expr)
            if then_type == else_type:
                return then_type
            return "Any"

        # Property access — resolve library-qualified definition references
        if isinstance(ast_node, Property):
            if (
                isinstance(ast_node.source, Identifier)
                and ast_node.source.name == "Patient"
                and ast_node.path == "birthDate"
            ):
                return "Date"
            if isinstance(ast_node.source, Identifier) and ast_node.path:
                prefixed = f"{ast_node.source.name}.{ast_node.path}"
                meta = self._context.definition_meta.get(prefixed)
                if meta:
                    return meta.cql_type
                if hasattr(self._context, 'expression_definitions'):
                    ast_def = self._context.expression_definitions.get(prefixed)
                    if ast_def is not None:
                        return self._infer_cql_type(ast_def)
            return "Any"

        # Check if it's an identifier referencing a known definition
        if isinstance(ast_node, Identifier):
            if ast_node.name in self._context.valuesets:
                return "ValueSet"
            if ast_node.name in self._context.codesystems:
                return "CodeSystem"
            code_info = self._context.codes.get(ast_node.name)
            if code_info:
                return "Concept" if code_info.get("is_concept") else "Code"
            meta = self._context.definition_meta.get(ast_node.name)
            if meta:
                return meta.cql_type
            param_info = self._context.parameters.get(ast_node.name)
            if param_info and getattr(param_info, "cql_type", None):
                return str(param_info.cql_type)
            # Forward ref: check CQL AST for type hints.
            # The cql_ast represents the EXPRESSION of the definition, so infer
            # its type directly (it already represents the full definition type,
            # e.g., a BinaryExpression(intersect) of queries returns List<Date>).
            if hasattr(self._context, '_definition_cql_asts'):
                cql_ast = self._context._definition_cql_asts.get(ast_node.name)
                if cql_ast is not None:
                    inferred = self._infer_cql_type(cql_ast)
                    if inferred != "Any":
                        return inferred

        # Query node: infer type from return clause or source
        from ..parser.ast_nodes import Query, QuerySource, ReturnClause
        if isinstance(ast_node, Query):
            if ast_node.return_clause is not None:
                rc_expr = ast_node.return_clause.expression if isinstance(ast_node.return_clause, ReturnClause) else ast_node.return_clause
                if isinstance(rc_expr, Identifier):
                    sources = ast_node.source if isinstance(ast_node.source, list) else [ast_node.source]
                    for source in sources:
                        if isinstance(source, QuerySource) and source.alias == rc_expr.name:
                            source_type = self._infer_cql_type(source.expression)
                            if source_type.startswith("List<"):
                                return source_type
                            if source_type != "Any":
                                return f"List<{source_type}>"
                property_return_type = self._infer_query_return_property_type(ast_node, rc_expr)
                if property_return_type is not None:
                    return f"List<{property_return_type}>"
                return_type = self._infer_cql_type(rc_expr)
                if return_type != "Any":
                    return f"List<{return_type}>"
            # No return clause: type is same as source
            src = ast_node.source
            if isinstance(src, list) and len(src) == 1:
                src = src[0]
            from ..parser.ast_nodes import QuerySource
            if isinstance(src, QuerySource) and src.expression:
                return self._infer_cql_type(src.expression)

        return "Any"

    def _infer_cardinality(self, ast_node: Any) -> str:
        """
        Infer cardinality: 0..1, 1, or 0..*

        Args:
            ast_node: The AST node to analyze.

        Returns:
            Cardinality string.
        """
        from ..parser.ast_nodes import ExistsExpression
        from ..translator.context import RowShape

        shape = self._infer_row_shape(ast_node)

        if shape == RowShape.RESOURCE_ROWS:
            return "0..*"
        elif shape == RowShape.PATIENT_SCALAR:
            # Check if it's guaranteed to have a value
            if isinstance(ast_node, ExistsExpression):
                return "1"  # exists always returns true or false
            return "0..1"
        else:
            return "0..*"
