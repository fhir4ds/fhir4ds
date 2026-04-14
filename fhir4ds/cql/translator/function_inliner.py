"""
Function inliner for CQL to SQL translation.

This module provides the FunctionInliner class that performs macro-style
expansion of CQL function calls by replacing them with their body expressions
after parameter substitution.

Key features:
- Macro-style expansion: Replace function calls with function body
- Parameter substitution: Replace parameter names with argument expressions
- Library name prefixing: Prefix functions with library name to avoid collisions
- Cycle detection: Detect and error on recursive function calls

Translation process:
    CQL:
      define function "Double"(x Integer): x * 2
      define function "Quadruple"(x Integer): Double(Double(x))
      define result: Quadruple(5)

    Process:
      1. Build call graph: Quadruple -> Double -> Double
      2. Detect cycles (error if found)
      3. Inline recursively: Double(Double(5)) -> Double(5 * 2) -> (5 * 2) * 2

    SQL:
      SELECT (5 * 2) * 2 AS result  -- = 20
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Set, Tuple

from ..parser.ast_nodes import (
    AliasRef,
    BinaryExpression,
    CaseExpression,
    CaseItem,
    ConditionalExpression,
    DateComponent,
    DateTimeLiteral,
    DifferenceBetween,
    DurationBetween,
    Expression,
    FunctionDefinition,
    FunctionRef,
    Identifier,
    IndexerExpression,
    InstanceExpression,
    Interval,
    ListExpression,
    Literal,
    MethodInvocation,
    Property,
    QualifiedIdentifier,
    Quantity,
    TimeLiteral,
    TupleElement,
    TupleExpression,
    UnaryExpression,
)
from ..translator.types import SQLExpression

if TYPE_CHECKING:
    from ..translator.context import SQLTranslationContext


class TranslationError(Exception):
    """Exception raised for translation errors."""

    pass


@dataclass
class FunctionDef:
    """
    Represents a CQL function definition for inlining.

    Attributes:
        name: The function name (may include library prefix).
        library_name: The library this function belongs to.
        parameters: List of (name, type) tuples for parameters.
        return_type: The return type of the function.
        body: The function body expression (AST node).
        fluent: Whether this is a fluent function.
    """

    name: str
    library_name: Optional[str] = None
    parameters: List[Tuple[str, Optional[str]]] = field(default_factory=list)
    return_type: Optional[str] = None
    body: Optional[Expression] = None
    fluent: bool = False


class FunctionInliner:
    """
    Performs macro-style inlining of CQL function calls.

    This class handles:
    1. Building call graphs to detect recursive functions
    2. Substituting parameters with argument expressions
    3. Recursively inlining nested function calls

    Example:
        inliner = FunctionInliner(context)
        inliner.register_function("Double", func_def)

        # Inline Double(5) -> 5 * 2
        result = inliner.inline_function("Double", [SQLLiteral(5)], context)
    """

    def __init__(self, context: SQLTranslationContext, max_inline_depth: int = 20):
        """
        Initialize the function inliner.

        Args:
            context: The translation context for symbol resolution.
            max_inline_depth: Maximum nesting depth for function inlining.
        """
        self.context = context
        self.max_inline_depth = max_inline_depth
        self._functions: Dict[str, FunctionDef] = {}
        self._call_graph: Dict[str, Set[str]] = {}
        self._inlining_stack: List[str] = []  # Track current inlining chain

    def register_function(self, func_def: FunctionDef) -> None:
        """
        Register a function definition for inlining.

        Args:
            func_def: The function definition to register.
        """
        key = self._make_function_key(func_def.name, func_def.library_name)
        self._functions[key] = func_def
        # Invalidate call graph cache
        self._call_graph.clear()

    def register_function_from_ast(self, func_def: FunctionDefinition, library_name: Optional[str] = None) -> None:
        """
        Register a function from its AST definition.

        Args:
            func_def: The FunctionDefinition AST node.
            library_name: Optional library name prefix.
        """
        parameters = []
        for param in func_def.parameters:
            param_type = None
            if param.type:
                # Extract type name from TypeSpecifier
                param_type = getattr(param.type, "name", str(param.type))
            parameters.append((param.name, param_type))

        return_type = None
        if func_def.return_type:
            return_type = getattr(func_def.return_type, "name", str(func_def.return_type))

        registered_func = FunctionDef(
            name=func_def.name,
            library_name=library_name,
            parameters=parameters,
            return_type=return_type,
            body=func_def.expression,
            fluent=func_def.fluent,
        )
        self.register_function(registered_func)

    def get_function(self, name: str, library_name: Optional[str] = None) -> Optional[FunctionDef]:
        """
        Get a registered function by name.

        Args:
            name: The function name.
            library_name: Optional library name.

        Returns:
            The function definition, or None if not found.
        """
        key = self._make_function_key(name, library_name)
        return self._functions.get(key)

    def inline_function(
        self,
        func_name: str,
        args: List[SQLExpression],
        context: SQLTranslationContext,
        library_name: Optional[str] = None,
    ) -> SQLExpression:
        """
        Inline a function call by replacing it with the function body.

        This performs macro-style expansion:
        1. Look up the function definition
        2. Build parameter substitution map from arguments
        3. Substitute parameters in the function body
        4. Recursively inline any nested function calls
        5. Translate the resulting expression to SQL

        Args:
            func_name: The name of the function to inline.
            args: The list of argument SQL expressions.
            context: The translation context.
            library_name: Optional library name for the function.

        Returns:
            The inlined SQL expression.

        Raises:
            TranslationError: If the function is not found or has a cycle.
        """
        key = self._make_function_key(func_name, library_name)

        # Check for recursive calls
        if key in self._inlining_stack:
            cycle_path = self._inlining_stack + [key]
            cycle_str = " -> ".join(cycle_path)
            raise TranslationError(f"Cycle detected in function calls: {cycle_str}")

        # Look up function
        func_def = self._functions.get(key)
        if func_def is None:
            raise TranslationError(f"Function not found: {key}")

        if func_def.body is None:
            raise TranslationError(f"Function has no body: {key}")

        # Build parameter substitution map
        param_map: Dict[str, SQLExpression] = {}
        for i, (param_name, _) in enumerate(func_def.parameters):
            if i < len(args):
                param_map[param_name] = args[i]

        # Push to inlining stack
        self._inlining_stack.append(key)

        try:
            # Isolate scope for external library functions so caller aliases don't leak in
            if library_name:
                context.push_scope()
                context.scopes[-1].barrier = True
            try:
                # Substitute parameters in the body and inline nested calls
                inlined_body = self.inline_function_body(func_def.body, param_map, context, library_name)
                return inlined_body
            finally:
                if library_name:
                    context.pop_scope()
        finally:
            # Pop from inlining stack
            self._inlining_stack.pop()

    def inline_function_body(
        self,
        body: Expression,
        param_map: Dict[str, SQLExpression],
        context: SQLTranslationContext,
        current_library: Optional[str] = None,
    ) -> SQLExpression:
        """
        Inline a function body by substituting parameters and inlining nested calls.

        This recursively processes the AST:
        1. Substitute parameter references with argument expressions
        2. Prefix definition references with library name (for cross-library inlining)
        3. Recursively inline any nested function calls
        4. Translate the result to SQL

        Args:
            body: The function body expression (AST node).
            param_map: Map from parameter names to SQL expressions.
            context: The translation context.
            current_library: The current library name for name resolution.

        Returns:
            The inlined and translated SQL expression.
        """
        # First, substitute parameters in the AST
        substituted_body = self._substitute_parameters(body, param_map)

        # Prefix definition references from external library with library alias
        if current_library:
            lib_info = context.includes.get(current_library)
            if lib_info:
                lib_defs = set(lib_info.definitions.keys())
                substituted_body = self._prefix_library_refs(
                    substituted_body, current_library, lib_defs, param_map
                )

        # Then, recursively inline any function calls
        inlined_body = self._inline_nested_calls(substituted_body, context, current_library)

        # Finally, translate to SQL
        # Import here to avoid circular dependency
        from ..translator.expressions import ExpressionTranslator

        translator = ExpressionTranslator(context)
        return translator.translate(inlined_body)

    def _prefix_library_refs(
        self,
        expr: Expression,
        library_alias: str,
        library_defs: set,
        param_map: Dict[str, SQLExpression],
    ) -> Expression:
        """Prefix definition references from an external library with the library alias.
        
        When a function from library AHA references definition "Outpatient Encounter",
        the CTE is named "AHA.Outpatient Encounter". This method renames Identifier
        nodes to match the prefixed CTE name.
        """
        if expr is None:
            return expr

        from ..translator.function_inliner import ParameterPlaceholder
        if isinstance(expr, ParameterPlaceholder):
            return expr

        # Rename identifiers that match library definitions (but not parameters)
        if isinstance(expr, Identifier):
            if expr.name in library_defs and expr.name not in param_map:
                return QualifiedIdentifier(parts=[library_alias, expr.name])
            return expr

        # Recurse into Property source
        if isinstance(expr, Property):
            new_source = self._prefix_library_refs(expr.source, library_alias, library_defs, param_map) if expr.source else None
            return Property(source=new_source, path=expr.path)

        # Recurse into BinaryExpression
        if isinstance(expr, BinaryExpression):
            new_left = self._prefix_library_refs(expr.left, library_alias, library_defs, param_map)
            new_right = self._prefix_library_refs(expr.right, library_alias, library_defs, param_map)
            return BinaryExpression(operator=expr.operator, left=new_left, right=new_right)

        # Recurse into UnaryExpression
        if isinstance(expr, UnaryExpression):
            new_operand = self._prefix_library_refs(expr.operand, library_alias, library_defs, param_map)
            return UnaryExpression(operator=expr.operator, operand=new_operand)

        # Recurse into ExistsExpression
        from ..parser.ast_nodes import (
            ExistsExpression, Query, QuerySource, WhereClause, ReturnClause,
            WithClause, LetClause
        )
        if isinstance(expr, ExistsExpression):
            return ExistsExpression(source=self._prefix_library_refs(expr.source, library_alias, library_defs, param_map))

        # Recurse into Query
        if isinstance(expr, Query):
            # Prefix query sources
            if isinstance(expr.source, list):
                new_sources = []
                for src in expr.source:
                    new_src_expr = self._prefix_library_refs(src.expression, library_alias, library_defs, param_map) if src.expression else None
                    new_sources.append(QuerySource(alias=src.alias, expression=new_src_expr))
            else:
                new_src_expr = self._prefix_library_refs(expr.source.expression, library_alias, library_defs, param_map) if expr.source.expression else None
                new_sources = QuerySource(alias=expr.source.alias, expression=new_src_expr)

            new_where = None
            if expr.where:
                new_where = WhereClause(expression=self._prefix_library_refs(expr.where.expression, library_alias, library_defs, param_map))

            new_return = None
            if expr.return_clause:
                new_return = ReturnClause(expression=self._prefix_library_refs(expr.return_clause.expression, library_alias, library_defs, param_map))

            new_withs = []
            for w in expr.with_clauses:
                new_w_expr = self._prefix_library_refs(w.expression, library_alias, library_defs, param_map)
                new_w_st = self._prefix_library_refs(w.such_that, library_alias, library_defs, param_map) if w.such_that else None
                new_withs.append(WithClause(
                    alias=w.alias, expression=new_w_expr, such_that=new_w_st,
                    is_without=getattr(w, 'is_without', False),
                ))

            new_lets = []
            for let in expr.let_clauses:
                new_let_expr = self._prefix_library_refs(let.expression, library_alias, library_defs, param_map)
                new_lets.append(LetClause(alias=let.alias, expression=new_let_expr))

            return Query(
                source=new_sources, where=new_where, return_clause=new_return,
                sort=expr.sort, let_clauses=new_lets, with_clauses=new_withs,
                relationships=expr.relationships, aggregate=expr.aggregate,
            )

        # Recurse into FunctionRef
        if isinstance(expr, FunctionRef):
            new_args = [self._prefix_library_refs(a, library_alias, library_defs, param_map) for a in expr.arguments]
            return FunctionRef(name=expr.name, arguments=new_args)

        # Recurse into MethodInvocation
        if isinstance(expr, MethodInvocation):
            new_source = self._prefix_library_refs(expr.source, library_alias, library_defs, param_map)
            new_args = [self._prefix_library_refs(a, library_alias, library_defs, param_map) for a in expr.arguments]
            return MethodInvocation(source=new_source, method=expr.method, arguments=new_args)

        # Recurse into ConditionalExpression
        if isinstance(expr, ConditionalExpression):
            return ConditionalExpression(
                condition=self._prefix_library_refs(expr.condition, library_alias, library_defs, param_map),
                then_expr=self._prefix_library_refs(expr.then_expr, library_alias, library_defs, param_map),
                else_expr=self._prefix_library_refs(expr.else_expr, library_alias, library_defs, param_map),
            )

        # Recurse into CaseExpression
        if isinstance(expr, CaseExpression):
            new_items = [
                CaseItem(
                    when=self._prefix_library_refs(item.when, library_alias, library_defs, param_map),
                    then=self._prefix_library_refs(item.then, library_alias, library_defs, param_map),
                ) for item in expr.case_items
            ]
            new_else = self._prefix_library_refs(expr.else_expr, library_alias, library_defs, param_map) if expr.else_expr else None
            return CaseExpression(case_items=new_items, else_expr=new_else, comparand=expr.comparand)

        # Recurse into ListExpression
        if isinstance(expr, ListExpression):
            return ListExpression(elements=[self._prefix_library_refs(e, library_alias, library_defs, param_map) for e in expr.elements])

        return expr

    def _substitute_parameters(
        self,
        expr: Expression,
        param_map: Dict[str, SQLExpression],
    ) -> Expression:
        """
        Substitute parameter references in an expression with argument expressions.

        This creates a new AST with parameter references replaced by
        placeholder expressions that will be translated to SQL later.

        Note: Since we need to produce SQL expressions, we create
        ParameterPlaceholder nodes that the expression translator
        will recognize and substitute.

        Args:
            expr: The expression to process.
            param_map: Map from parameter names to SQL expressions.

        Returns:
            A new expression with parameters substituted.
        """
        if expr is None:
            return expr

        expr_type = type(expr).__name__

        # Handle identifier (potential parameter reference)
        if isinstance(expr, Identifier):
            if expr.name in param_map:
                # Create a placeholder that carries the SQL expression
                return ParameterPlaceholder(name=expr.name, sql_expr=param_map[expr.name])
            return expr

        # Handle qualified identifier
        if isinstance(expr, QualifiedIdentifier):
            return expr  # Qualified identifiers are not parameters

        # Handle property access
        if isinstance(expr, Property):
            new_source = self._substitute_parameters(expr.source, param_map) if expr.source else None
            return Property(source=new_source, path=expr.path)

        # Handle function reference (call)
        if isinstance(expr, FunctionRef):
            new_args = [self._substitute_parameters(arg, param_map) for arg in expr.arguments]
            return FunctionRef(name=expr.name, arguments=new_args)

        # Handle method invocation
        if isinstance(expr, MethodInvocation):
            new_source = self._substitute_parameters(expr.source, param_map)
            new_args = [self._substitute_parameters(arg, param_map) for arg in expr.arguments]
            return MethodInvocation(source=new_source, method=expr.method, arguments=new_args)

        # Handle binary expression
        if isinstance(expr, BinaryExpression):
            new_left = self._substitute_parameters(expr.left, param_map)
            new_right = self._substitute_parameters(expr.right, param_map)
            return BinaryExpression(operator=expr.operator, left=new_left, right=new_right)

        # Handle unary expression
        if isinstance(expr, UnaryExpression):
            new_operand = self._substitute_parameters(expr.operand, param_map)
            return UnaryExpression(operator=expr.operator, operand=new_operand)

        # Handle conditional expression
        if isinstance(expr, ConditionalExpression):
            new_condition = self._substitute_parameters(expr.condition, param_map)
            new_then = self._substitute_parameters(expr.then_expr, param_map)
            new_else = self._substitute_parameters(expr.else_expr, param_map)
            return ConditionalExpression(condition=new_condition, then_expr=new_then, else_expr=new_else)

        # Handle case expression
        if isinstance(expr, CaseExpression):
            new_items = [
                CaseItem(
                    when=self._substitute_parameters(item.when, param_map),
                    then=self._substitute_parameters(item.then, param_map),
                )
                for item in expr.case_items
            ]
            new_else = self._substitute_parameters(expr.else_expr, param_map) if expr.else_expr else None
            new_comparand = self._substitute_parameters(expr.comparand, param_map) if expr.comparand else None
            return CaseExpression(case_items=new_items, else_expr=new_else, comparand=new_comparand)

        # Handle list expression
        if isinstance(expr, ListExpression):
            new_elements = [self._substitute_parameters(e, param_map) for e in expr.elements]
            return ListExpression(elements=new_elements)

        # Handle tuple expression
        if isinstance(expr, TupleExpression):
            new_elements = [
                type("TupleElement", (), {
                    "name": e.name,
                    "type": self._substitute_parameters(e.type, param_map) if hasattr(e, "type") else e
                })()
                for e in expr.elements
            ]
            return TupleExpression(elements=new_elements)

        # Handle interval
        if isinstance(expr, Interval):
            new_low = self._substitute_parameters(expr.low, param_map) if expr.low else None
            new_high = self._substitute_parameters(expr.high, param_map) if expr.high else None
            return Interval(low=new_low, high=new_high, low_closed=expr.low_closed, high_closed=expr.high_closed)

        # Handle instance expression
        if isinstance(expr, InstanceExpression):
            new_elements = [
                type("TupleElement", (), {
                    "name": e.name,
                    "type": self._substitute_parameters(e.type, param_map) if hasattr(e, "type") else e
                })()
                for e in expr.elements
            ]
            return InstanceExpression(type=expr.type, elements=new_elements)

        # Handle indexer expression
        if isinstance(expr, IndexerExpression):
            new_source = self._substitute_parameters(expr.source, param_map)
            new_index = self._substitute_parameters(expr.index, param_map)
            return IndexerExpression(source=new_source, index=new_index)

        # Handle alias reference
        if isinstance(expr, AliasRef):
            if expr.name in param_map:
                return ParameterPlaceholder(name=expr.name, sql_expr=param_map[expr.name])
            return expr

        # Handle ExistsExpression
        from ..parser.ast_nodes import (
            ExistsExpression, FirstExpression, LastExpression, DistinctExpression,
            Query, QuerySource, WhereClause, ReturnClause,
            SortClause, SortByItem, LetClause, WithClause, AggregateClause
        )
        if isinstance(expr, ExistsExpression):
            new_source = self._substitute_parameters(expr.source, param_map)
            return ExistsExpression(source=new_source)

        if isinstance(expr, FirstExpression):
            new_source = self._substitute_parameters(expr.source, param_map)
            return FirstExpression(source=new_source)

        if isinstance(expr, LastExpression):
            new_source = self._substitute_parameters(expr.source, param_map)
            return LastExpression(source=new_source)

        if isinstance(expr, DistinctExpression):
            new_source = self._substitute_parameters(expr.source, param_map)
            return DistinctExpression(source=new_source)

        if isinstance(expr, Query):
            # Substitute in source(s)
            if isinstance(expr.source, list):
                new_sources = []
                for src in expr.source:
                    new_src_expr = self._substitute_parameters(src.expression, param_map) if src.expression else None
                    new_sources.append(QuerySource(alias=src.alias, expression=new_src_expr))
            else:
                new_src_expr = self._substitute_parameters(expr.source.expression, param_map) if expr.source.expression else None
                new_sources = QuerySource(alias=expr.source.alias, expression=new_src_expr)

            # Substitute in where clause
            new_where = None
            if expr.where:
                new_where_expr = self._substitute_parameters(expr.where.expression, param_map)
                new_where = WhereClause(expression=new_where_expr)

            # Substitute in return clause
            new_return = None
            if expr.return_clause:
                new_return_expr = self._substitute_parameters(expr.return_clause.expression, param_map)
                new_return = ReturnClause(expression=new_return_expr)

            # Substitute in sort clause
            new_sort = None
            if expr.sort:
                new_sort_items = []
                for item in expr.sort.by:
                    new_sort_expr = self._substitute_parameters(item.expression, param_map) if item.expression else None
                    new_sort_items.append(SortByItem(direction=item.direction, expression=new_sort_expr))
                new_sort = SortClause(by=new_sort_items)

            # Substitute in let clauses
            new_lets = []
            for let in expr.let_clauses:
                new_let_expr = self._substitute_parameters(let.expression, param_map)
                new_lets.append(LetClause(alias=let.alias, expression=new_let_expr))

            # Substitute in with clauses
            new_withs = []
            for with_c in expr.with_clauses:
                new_with_expr = self._substitute_parameters(with_c.expression, param_map)
                new_such_that = self._substitute_parameters(with_c.such_that, param_map) if with_c.such_that else None
                new_withs.append(WithClause(
                    alias=with_c.alias,
                    expression=new_with_expr,
                    such_that=new_such_that,
                    is_without=getattr(with_c, 'is_without', False),
                ))

            # Substitute in aggregate clause
            new_aggregate = None
            if expr.aggregate:
                new_agg_expr = self._substitute_parameters(expr.aggregate.expression, param_map)
                new_agg_start = self._substitute_parameters(expr.aggregate.starting, param_map) if expr.aggregate.starting else None
                new_aggregate = AggregateClause(
                    identifier=expr.aggregate.identifier,
                    expression=new_agg_expr,
                    starting=new_agg_start,
                    distinct=expr.aggregate.distinct,
                    all_=expr.aggregate.all_
                )

            return Query(
                source=new_sources,
                where=new_where,
                return_clause=new_return,
                sort=new_sort,
                let_clauses=new_lets,
                with_clauses=new_withs,
                relationships=expr.relationships,
                aggregate=new_aggregate
            )

        # Literals and other terminal expressions are returned as-is
        if isinstance(expr, (Literal, Quantity, DateTimeLiteral, TimeLiteral)):
            return expr

        if isinstance(expr, DifferenceBetween):
            new_left = self._substitute_parameters(expr.operand_left, param_map)
            new_right = self._substitute_parameters(expr.operand_right, param_map)
            return DifferenceBetween(precision=expr.precision, operand_left=new_left, operand_right=new_right)

        if isinstance(expr, DurationBetween):
            new_left = self._substitute_parameters(expr.operand_left, param_map)
            new_right = self._substitute_parameters(expr.operand_right, param_map)
            return DurationBetween(precision=expr.precision, operand_left=new_left, operand_right=new_right)

        if isinstance(expr, DateComponent):
            new_operand = self._substitute_parameters(expr.operand, param_map)
            return DateComponent(component=expr.component, operand=new_operand)

        # For any other expression type, return as-is
        return expr

    def _inline_nested_calls(
        self,
        expr: Expression,
        context: SQLTranslationContext,
        current_library: Optional[str] = None,
    ) -> Expression:
        """
        Recursively inline nested function calls in an expression.

        This traverses the AST looking for FunctionRef nodes that reference
        registered user-defined functions and inlines them.

        Args:
            expr: The expression to process.
            context: The translation context.
            current_library: The current library name.

        Returns:
            The expression with nested calls inlined.
        """
        if expr is None:
            return expr

        # Handle function reference - check if it's a user-defined function
        if isinstance(expr, FunctionRef):
            func_name = expr.name

            # Check if it's qualified (Library.Function)
            library_name = None
            if "." in func_name:
                parts = func_name.split(".", 1)
                library_name = parts[0]
                func_name = parts[1]

            key = self._make_function_key(func_name, library_name)

            # If it's a registered user function, inline it
            if key in self._functions:
                func_def = self._functions[key]

                # Recursively process arguments first
                processed_args = [
                    self._inline_nested_calls(arg, context, current_library)
                    for arg in expr.arguments
                ]

                # Build parameter map from processed arguments
                param_map: Dict[str, SQLExpression] = {}
                for i, (param_name, _) in enumerate(func_def.parameters):
                    if i < len(processed_args):
                        # The argument may be a ParameterPlaceholder carrying a SQL expression
                        arg = processed_args[i]
                        if isinstance(arg, ParameterPlaceholder):
                            param_map[param_name] = arg.sql_expr
                        else:
                            # Translate the argument to SQL
                            from ..translator.expressions import ExpressionTranslator

                            translator = ExpressionTranslator(context)
                            param_map[param_name] = translator.translate(arg)

                # Check for recursion
                if key in self._inlining_stack:
                    cycle_path = self._inlining_stack + [key]
                    cycle_str = " -> ".join(cycle_path)
                    raise TranslationError(f"Cycle detected in function calls: {cycle_str}")

                # Push to stack and inline
                self._inlining_stack.append(key)
                try:
                    if func_def.body:
                        # Substitute parameters in body
                        substituted_body = self._substitute_parameters(func_def.body, param_map)
                        # Recursively inline any nested calls
                        return self._inline_nested_calls(substituted_body, context, library_name)
                finally:
                    self._inlining_stack.pop()

            # Not a user function - process arguments recursively
            new_args = [self._inline_nested_calls(arg, context, current_library) for arg in expr.arguments]
            return FunctionRef(name=expr.name, arguments=new_args)

        # Handle method invocation
        if isinstance(expr, MethodInvocation):
            new_source = self._inline_nested_calls(expr.source, context, current_library)
            new_args = [self._inline_nested_calls(arg, context, current_library) for arg in expr.arguments]
            return MethodInvocation(source=new_source, method=expr.method, arguments=new_args)

        # Handle property access
        if isinstance(expr, Property):
            new_source = self._inline_nested_calls(expr.source, context, current_library) if expr.source else None
            return Property(source=new_source, path=expr.path)

        # Handle binary expression
        if isinstance(expr, BinaryExpression):
            new_left = self._inline_nested_calls(expr.left, context, current_library)
            new_right = self._inline_nested_calls(expr.right, context, current_library)
            return BinaryExpression(operator=expr.operator, left=new_left, right=new_right)

        # Handle unary expression
        if isinstance(expr, UnaryExpression):
            new_operand = self._inline_nested_calls(expr.operand, context, current_library)
            return UnaryExpression(operator=expr.operator, operand=new_operand)

        # Handle conditional expression
        if isinstance(expr, ConditionalExpression):
            new_condition = self._inline_nested_calls(expr.condition, context, current_library)
            new_then = self._inline_nested_calls(expr.then_expr, context, current_library)
            new_else = self._inline_nested_calls(expr.else_expr, context, current_library)
            return ConditionalExpression(condition=new_condition, then_expr=new_then, else_expr=new_else)

        # Handle case expression
        if isinstance(expr, CaseExpression):
            new_items = [
                CaseItem(
                    when=self._inline_nested_calls(item.when, context, current_library),
                    then=self._inline_nested_calls(item.then, context, current_library),
                )
                for item in expr.case_items
            ]
            new_else = self._inline_nested_calls(expr.else_expr, context, current_library) if expr.else_expr else None
            new_comparand = self._inline_nested_calls(expr.comparand, context, current_library) if expr.comparand else None
            return CaseExpression(case_items=new_items, else_expr=new_else, comparand=new_comparand)

        # Handle list expression
        if isinstance(expr, ListExpression):
            new_elements = [self._inline_nested_calls(e, context, current_library) for e in expr.elements]
            return ListExpression(elements=new_elements)

        # Handle interval
        if isinstance(expr, Interval):
            new_low = self._inline_nested_calls(expr.low, context, current_library) if expr.low else None
            new_high = self._inline_nested_calls(expr.high, context, current_library) if expr.high else None
            return Interval(low=new_low, high=new_high, low_closed=expr.low_closed, high_closed=expr.high_closed)

        # Handle indexer expression
        if isinstance(expr, IndexerExpression):
            new_source = self._inline_nested_calls(expr.source, context, current_library)
            new_index = self._inline_nested_calls(expr.index, context, current_library)
            return IndexerExpression(source=new_source, index=new_index)

        # Handle exists expression
        from ..parser.ast_nodes import ExistsExpression
        if isinstance(expr, ExistsExpression):
            new_source = self._inline_nested_calls(expr.source, context, current_library)
            return ExistsExpression(source=new_source)

        if isinstance(expr, DifferenceBetween):
            new_left = self._inline_nested_calls(expr.operand_left, context, current_library)
            new_right = self._inline_nested_calls(expr.operand_right, context, current_library)
            return DifferenceBetween(precision=expr.precision, operand_left=new_left, operand_right=new_right)

        if isinstance(expr, DurationBetween):
            new_left = self._inline_nested_calls(expr.operand_left, context, current_library)
            new_right = self._inline_nested_calls(expr.operand_right, context, current_library)
            return DurationBetween(precision=expr.precision, operand_left=new_left, operand_right=new_right)

        if isinstance(expr, DateComponent):
            new_operand = self._inline_nested_calls(expr.operand, context, current_library)
            return DateComponent(component=expr.component, operand=new_operand)

        # For other expression types, return as-is
        return expr

    def build_call_graph(self) -> Dict[str, Set[str]]:
        """
        Build a call graph of all registered functions.

        The call graph maps function names to the set of functions they call.

        Returns:
            A dictionary mapping function names to sets of called function names.
        """
        if self._call_graph:
            return self._call_graph

        for key, func_def in self._functions.items():
            if func_def.body:
                called_functions = self._extract_called_functions(func_def.body)
                self._call_graph[key] = called_functions
            else:
                self._call_graph[key] = set()

        return self._call_graph

    def _extract_called_functions(self, expr: Expression) -> Set[str]:
        """
        Extract the set of user-defined functions called in an expression.

        Args:
            expr: The expression to analyze.

        Returns:
            Set of function keys that are called in the expression.
        """
        called = set()

        if expr is None:
            return called

        if isinstance(expr, FunctionRef):
            func_name = expr.name
            library_name = None

            # Check for qualified name
            if "." in func_name:
                parts = func_name.split(".", 1)
                library_name = parts[0]
                func_name = parts[1]

            key = self._make_function_key(func_name, library_name)

            # Only include if it's a registered user function
            if key in self._functions:
                called.add(key)

            # Recurse into arguments
            for arg in expr.arguments:
                called.update(self._extract_called_functions(arg))

        elif isinstance(expr, MethodInvocation):
            called.update(self._extract_called_functions(expr.source))
            for arg in expr.arguments:
                called.update(self._extract_called_functions(arg))

        elif isinstance(expr, Property):
            if expr.source:
                called.update(self._extract_called_functions(expr.source))

        elif isinstance(expr, BinaryExpression):
            called.update(self._extract_called_functions(expr.left))
            called.update(self._extract_called_functions(expr.right))

        elif isinstance(expr, UnaryExpression):
            called.update(self._extract_called_functions(expr.operand))

        elif isinstance(expr, ConditionalExpression):
            called.update(self._extract_called_functions(expr.condition))
            called.update(self._extract_called_functions(expr.then_expr))
            called.update(self._extract_called_functions(expr.else_expr))

        elif isinstance(expr, CaseExpression):
            for item in expr.case_items:
                called.update(self._extract_called_functions(item.when))
                called.update(self._extract_called_functions(item.then))
            if expr.else_expr:
                called.update(self._extract_called_functions(expr.else_expr))
            if expr.comparand:
                called.update(self._extract_called_functions(expr.comparand))

        elif isinstance(expr, ListExpression):
            for elem in expr.elements:
                called.update(self._extract_called_functions(elem))

        elif isinstance(expr, Interval):
            if expr.low:
                called.update(self._extract_called_functions(expr.low))
            if expr.high:
                called.update(self._extract_called_functions(expr.high))

        elif isinstance(expr, IndexerExpression):
            called.update(self._extract_called_functions(expr.source))
            called.update(self._extract_called_functions(expr.index))

        return called

    def detect_cycles(self) -> List[List[str]]:
        """
        Detect cycles in the function call graph.

        Returns:
            A list of cycles found, where each cycle is a list of function names.
        """
        call_graph = self.build_call_graph()
        cycles = []
        visited = set()
        rec_stack = []

        def dfs(node: str) -> None:
            visited.add(node)
            rec_stack.append(node)

            for neighbor in call_graph.get(node, set()):
                if neighbor not in visited:
                    dfs(neighbor)
                elif neighbor in rec_stack:
                    # Found a cycle
                    cycle_start = rec_stack.index(neighbor)
                    cycle = rec_stack[cycle_start:] + [neighbor]
                    cycles.append(cycle)

            rec_stack.pop()

        for node in call_graph:
            if node not in visited:
                dfs(node)

        return cycles

    def check_for_cycles(self) -> None:
        """
        Check for cycles in the function call graph.

        Raises:
            TranslationError: If a cycle is detected.
        """
        cycles = self.detect_cycles()
        if cycles:
            cycle_strs = []
            for cycle in cycles:
                cycle_str = " -> ".join(cycle)
                cycle_strs.append(cycle_str)
            raise TranslationError(f"Cycle detected in function calls: {cycle_strs[0]}")

    # ------------------------------------------------------------------
    # Expand-then-Translate: Pure CQL AST expansion (no SQL translation)
    # ------------------------------------------------------------------

    def expand_function(
        self,
        func_name: str,
        receiver_expr: Expression,
        args: List[Expression],
        library_name: Optional[str] = None,
    ) -> Optional[Expression]:
        """
        Expand a fluent function call by substituting parameters in its body.

        Returns expanded CQL AST (not SQL). Translation happens separately
        in the caller via ExpressionTranslator.translate().

        Args:
            func_name: The fluent function name.
            receiver_expr: The CQL AST for the receiver (first fluent param).
            args: The CQL AST arguments (excluding the receiver).
            library_name: Optional library name prefix.

        Returns:
            Expanded CQL AST, or None if the function is not found.
        """
        key = self._make_function_key(func_name, library_name)

        # Also try without library prefix (common for unqualified calls)
        func_def = self._functions.get(key)
        if func_def is None and library_name is None:
            # Search all registered functions for a match by name
            for k, fd in self._functions.items():
                if k == func_name or k.endswith(f".{func_name}"):
                    func_def = fd
                    key = k
                    break

        if func_def is None or func_def.body is None:
            return None

        # Depth limit check
        if len(self._inlining_stack) >= self.max_inline_depth:
            return None

        # Cycle detection using shared _inlining_stack
        if key in self._inlining_stack:
            raise TranslationError(
                f"Cycle detected: {' -> '.join(self._inlining_stack + [key])}"
            )

        # Build parameter map: CQL AST -> CQL AST
        param_map: Dict[str, Expression] = {}
        for i, (param_name, _) in enumerate(func_def.parameters):
            if i == 0 and func_def.fluent:
                param_map[param_name] = receiver_expr
            elif func_def.fluent:
                arg_idx = i - 1
                if arg_idx < len(args):
                    param_map[param_name] = args[arg_idx]
            else:
                if i < len(args):
                    param_map[param_name] = args[i]

        self._inlining_stack.append(key)
        try:
            substituted = self._substitute_parameters_cql(func_def.body, param_map)
            # Prefix library references if from an external library
            if func_def.library_name:
                lib_info = self.context.includes.get(func_def.library_name)
                if lib_info:
                    lib_defs = set(lib_info.definitions.keys())
                    substituted = self._prefix_library_refs(
                        substituted, func_def.library_name, lib_defs, {}
                    )
            expanded = self._inline_nested_calls_cql(substituted, func_def.library_name)
            return expanded
        finally:
            self._inlining_stack.pop()

    def _substitute_parameters_cql(
        self,
        expr: Expression,
        param_map: Dict[str, Expression],
    ) -> Expression:
        """
        Substitute parameter references with CQL AST expressions.

        Unlike _substitute_parameters() which creates ParameterPlaceholder
        nodes carrying SQL, this replaces Identifier/AliasRef nodes with the
        CQL argument expressions directly.
        """
        if expr is None:
            return expr

        if isinstance(expr, Identifier):
            if expr.name in param_map:
                return param_map[expr.name]
            return expr

        if isinstance(expr, AliasRef):
            if expr.name in param_map:
                return param_map[expr.name]
            return expr

        if isinstance(expr, QualifiedIdentifier):
            return expr

        if isinstance(expr, Property):
            new_source = self._substitute_parameters_cql(expr.source, param_map) if expr.source else None
            return Property(source=new_source, path=expr.path)

        if isinstance(expr, FunctionRef):
            new_args = [self._substitute_parameters_cql(arg, param_map) for arg in expr.arguments]
            return FunctionRef(name=expr.name, arguments=new_args)

        if isinstance(expr, MethodInvocation):
            new_source = self._substitute_parameters_cql(expr.source, param_map)
            new_args = [self._substitute_parameters_cql(arg, param_map) for arg in expr.arguments]
            return MethodInvocation(source=new_source, method=expr.method, arguments=new_args)

        if isinstance(expr, BinaryExpression):
            new_left = self._substitute_parameters_cql(expr.left, param_map)
            new_right = self._substitute_parameters_cql(expr.right, param_map)
            return BinaryExpression(operator=expr.operator, left=new_left, right=new_right)

        if isinstance(expr, UnaryExpression):
            new_operand = self._substitute_parameters_cql(expr.operand, param_map)
            return UnaryExpression(operator=expr.operator, operand=new_operand)

        if isinstance(expr, ConditionalExpression):
            new_condition = self._substitute_parameters_cql(expr.condition, param_map)
            new_then = self._substitute_parameters_cql(expr.then_expr, param_map)
            new_else = self._substitute_parameters_cql(expr.else_expr, param_map)
            return ConditionalExpression(condition=new_condition, then_expr=new_then, else_expr=new_else)

        if isinstance(expr, CaseExpression):
            new_items = [
                CaseItem(
                    when=self._substitute_parameters_cql(item.when, param_map),
                    then=self._substitute_parameters_cql(item.then, param_map),
                )
                for item in expr.case_items
            ]
            new_else = self._substitute_parameters_cql(expr.else_expr, param_map) if expr.else_expr else None
            new_comparand = self._substitute_parameters_cql(expr.comparand, param_map) if expr.comparand else None
            return CaseExpression(case_items=new_items, else_expr=new_else, comparand=new_comparand)

        if isinstance(expr, ListExpression):
            new_elements = [self._substitute_parameters_cql(e, param_map) for e in expr.elements]
            return ListExpression(elements=new_elements)

        if isinstance(expr, Interval):
            new_low = self._substitute_parameters_cql(expr.low, param_map) if expr.low else None
            new_high = self._substitute_parameters_cql(expr.high, param_map) if expr.high else None
            return Interval(low=new_low, high=new_high, low_closed=expr.low_closed, high_closed=expr.high_closed)

        if isinstance(expr, IndexerExpression):
            new_source = self._substitute_parameters_cql(expr.source, param_map)
            new_index = self._substitute_parameters_cql(expr.index, param_map)
            return IndexerExpression(source=new_source, index=new_index)

        from ..parser.ast_nodes import (
            ExistsExpression, FirstExpression, LastExpression, DistinctExpression,
            Query, QuerySource, WhereClause, ReturnClause,
            SortClause, SortByItem, LetClause, WithClause, AggregateClause,
        )

        if isinstance(expr, ExistsExpression):
            return ExistsExpression(source=self._substitute_parameters_cql(expr.source, param_map))

        if isinstance(expr, FirstExpression):
            return FirstExpression(source=self._substitute_parameters_cql(expr.source, param_map))

        if isinstance(expr, LastExpression):
            return LastExpression(source=self._substitute_parameters_cql(expr.source, param_map))

        if isinstance(expr, DistinctExpression):
            return DistinctExpression(source=self._substitute_parameters_cql(expr.source, param_map))

        if isinstance(expr, Query):
            if isinstance(expr.source, list):
                new_sources = []
                for src in expr.source:
                    new_src_expr = self._substitute_parameters_cql(src.expression, param_map) if src.expression else None
                    new_sources.append(QuerySource(alias=src.alias, expression=new_src_expr))
            else:
                new_src_expr = self._substitute_parameters_cql(expr.source.expression, param_map) if expr.source.expression else None
                new_sources = QuerySource(alias=expr.source.alias, expression=new_src_expr)

            new_where = None
            if expr.where:
                new_where = WhereClause(expression=self._substitute_parameters_cql(expr.where.expression, param_map))

            new_return = None
            if expr.return_clause:
                new_return = ReturnClause(expression=self._substitute_parameters_cql(expr.return_clause.expression, param_map))

            new_sort = None
            if expr.sort:
                new_sort_items = [
                    SortByItem(direction=item.direction, expression=self._substitute_parameters_cql(item.expression, param_map) if item.expression else None)
                    for item in expr.sort.by
                ]
                new_sort = SortClause(by=new_sort_items)

            new_lets = []
            for let in expr.let_clauses:
                new_let_expr = self._substitute_parameters_cql(let.expression, param_map)
                new_lets.append(LetClause(alias=let.alias, expression=new_let_expr))

            new_withs = []
            for with_c in expr.with_clauses:
                new_with_expr = self._substitute_parameters_cql(with_c.expression, param_map)
                new_such_that = self._substitute_parameters_cql(with_c.such_that, param_map) if with_c.such_that else None
                new_withs.append(WithClause(
                    alias=with_c.alias, expression=new_with_expr, such_that=new_such_that,
                    is_without=getattr(with_c, 'is_without', False),
                ))

            new_aggregate = None
            if expr.aggregate:
                new_agg_expr = self._substitute_parameters_cql(expr.aggregate.expression, param_map)
                new_agg_start = self._substitute_parameters_cql(expr.aggregate.starting, param_map) if expr.aggregate.starting else None
                new_aggregate = AggregateClause(
                    identifier=expr.aggregate.identifier, expression=new_agg_expr,
                    starting=new_agg_start, distinct=expr.aggregate.distinct,
                    all_=expr.aggregate.all_,
                )

            return Query(
                source=new_sources, where=new_where, return_clause=new_return,
                sort=new_sort, let_clauses=new_lets, with_clauses=new_withs,
                relationships=expr.relationships, aggregate=new_aggregate,
            )

        if isinstance(expr, (Literal, Quantity, DateTimeLiteral, TimeLiteral)):
            return expr

        if isinstance(expr, DifferenceBetween):
            new_left = self._substitute_parameters_cql(expr.operand_left, param_map)
            new_right = self._substitute_parameters_cql(expr.operand_right, param_map)
            return DifferenceBetween(precision=expr.precision, operand_left=new_left, operand_right=new_right)

        if isinstance(expr, DurationBetween):
            new_left = self._substitute_parameters_cql(expr.operand_left, param_map)
            new_right = self._substitute_parameters_cql(expr.operand_right, param_map)
            return DurationBetween(precision=expr.precision, operand_left=new_left, operand_right=new_right)

        if isinstance(expr, DateComponent):
            new_operand = self._substitute_parameters_cql(expr.operand, param_map)
            return DateComponent(component=expr.component, operand=new_operand)

        if isinstance(expr, TupleExpression):
            new_elements = [
                TupleElement(
                    name=e.name,
                    type=self._substitute_parameters_cql(e.type, param_map),
                )
                for e in expr.elements
            ]
            return TupleExpression(elements=new_elements)

        if isinstance(expr, InstanceExpression):
            new_elements = [
                TupleElement(
                    name=e.name,
                    type=self._substitute_parameters_cql(e.type, param_map),
                )
                for e in expr.elements
            ]
            return InstanceExpression(type=expr.type, elements=new_elements)

        return expr

    def _inline_nested_calls_cql(
        self,
        expr: Expression,
        current_library: Optional[str] = None,
    ) -> Expression:
        """
        Recursively expand nested function calls in a CQL AST.

        Unlike _inline_nested_calls() which translates to SQL,
        this returns pure CQL AST with all registered functions expanded.
        """
        if expr is None:
            return expr

        if isinstance(expr, FunctionRef):
            func_name = expr.name
            library_name = None
            if "." in func_name:
                parts = func_name.split(".", 1)
                library_name = parts[0]
                func_name = parts[1]

            key = self._make_function_key(func_name, library_name)

            if key in self._functions:
                func_def = self._functions[key]
                processed_args = [
                    self._inline_nested_calls_cql(arg, current_library)
                    for arg in expr.arguments
                ]

                param_map: Dict[str, Expression] = {}
                for i, (param_name, _) in enumerate(func_def.parameters):
                    if i < len(processed_args):
                        param_map[param_name] = processed_args[i]

                if key in self._inlining_stack:
                    raise TranslationError(
                        f"Cycle detected: {' -> '.join(self._inlining_stack + [key])}"
                    )

                if len(self._inlining_stack) >= self.max_inline_depth:
                    return expr

                self._inlining_stack.append(key)
                try:
                    if func_def.body:
                        substituted = self._substitute_parameters_cql(func_def.body, param_map)
                        return self._inline_nested_calls_cql(substituted, library_name)
                finally:
                    self._inlining_stack.pop()

            new_args = [self._inline_nested_calls_cql(arg, current_library) for arg in expr.arguments]
            return FunctionRef(name=expr.name, arguments=new_args)

        if isinstance(expr, MethodInvocation):
            new_source = self._inline_nested_calls_cql(expr.source, current_library)
            new_args = [self._inline_nested_calls_cql(arg, current_library) for arg in expr.arguments]
            # Check if this method is a registered fluent function
            method = expr.method
            for k, fd in self._functions.items():
                if (k == method or k.endswith(f".{method}")) and fd.fluent:
                    expanded = self.expand_function(method, new_source, new_args)
                    if expanded is not None:
                        return expanded
                    break
            return MethodInvocation(source=new_source, method=expr.method, arguments=new_args)

        if isinstance(expr, Property):
            new_source = self._inline_nested_calls_cql(expr.source, current_library) if expr.source else None
            return Property(source=new_source, path=expr.path)

        if isinstance(expr, BinaryExpression):
            new_left = self._inline_nested_calls_cql(expr.left, current_library)
            new_right = self._inline_nested_calls_cql(expr.right, current_library)
            return BinaryExpression(operator=expr.operator, left=new_left, right=new_right)

        if isinstance(expr, UnaryExpression):
            new_operand = self._inline_nested_calls_cql(expr.operand, current_library)
            return UnaryExpression(operator=expr.operator, operand=new_operand)

        if isinstance(expr, ConditionalExpression):
            new_condition = self._inline_nested_calls_cql(expr.condition, current_library)
            new_then = self._inline_nested_calls_cql(expr.then_expr, current_library)
            new_else = self._inline_nested_calls_cql(expr.else_expr, current_library)
            return ConditionalExpression(condition=new_condition, then_expr=new_then, else_expr=new_else)

        if isinstance(expr, CaseExpression):
            new_items = [
                CaseItem(
                    when=self._inline_nested_calls_cql(item.when, current_library),
                    then=self._inline_nested_calls_cql(item.then, current_library),
                )
                for item in expr.case_items
            ]
            new_else = self._inline_nested_calls_cql(expr.else_expr, current_library) if expr.else_expr else None
            new_comparand = self._inline_nested_calls_cql(expr.comparand, current_library) if expr.comparand else None
            return CaseExpression(case_items=new_items, else_expr=new_else, comparand=new_comparand)

        if isinstance(expr, ListExpression):
            new_elements = [self._inline_nested_calls_cql(e, current_library) for e in expr.elements]
            return ListExpression(elements=new_elements)

        if isinstance(expr, Interval):
            new_low = self._inline_nested_calls_cql(expr.low, current_library) if expr.low else None
            new_high = self._inline_nested_calls_cql(expr.high, current_library) if expr.high else None
            return Interval(low=new_low, high=new_high, low_closed=expr.low_closed, high_closed=expr.high_closed)

        if isinstance(expr, IndexerExpression):
            new_source = self._inline_nested_calls_cql(expr.source, current_library)
            new_index = self._inline_nested_calls_cql(expr.index, current_library)
            return IndexerExpression(source=new_source, index=new_index)

        from ..parser.ast_nodes import ExistsExpression
        if isinstance(expr, ExistsExpression):
            return ExistsExpression(source=self._inline_nested_calls_cql(expr.source, current_library))

        if isinstance(expr, DifferenceBetween):
            new_left = self._inline_nested_calls_cql(expr.operand_left, current_library)
            new_right = self._inline_nested_calls_cql(expr.operand_right, current_library)
            return DifferenceBetween(precision=expr.precision, operand_left=new_left, operand_right=new_right)

        if isinstance(expr, DurationBetween):
            new_left = self._inline_nested_calls_cql(expr.operand_left, current_library)
            new_right = self._inline_nested_calls_cql(expr.operand_right, current_library)
            return DurationBetween(precision=expr.precision, operand_left=new_left, operand_right=new_right)

        if isinstance(expr, DateComponent):
            new_operand = self._inline_nested_calls_cql(expr.operand, current_library)
            return DateComponent(component=expr.component, operand=new_operand)

        if isinstance(expr, TupleExpression):
            new_elements = [
                TupleElement(
                    name=e.name,
                    type=self._inline_nested_calls_cql(e.type, current_library),
                )
                for e in expr.elements
            ]
            return TupleExpression(elements=new_elements)

        if isinstance(expr, InstanceExpression):
            new_elements = [
                TupleElement(
                    name=e.name,
                    type=self._inline_nested_calls_cql(e.type, current_library),
                )
                for e in expr.elements
            ]
            return InstanceExpression(type=expr.type, elements=new_elements)

        return expr

    def _make_function_key(self, name: str, library_name: Optional[str] = None) -> str:
        """
        Create a unique key for a function.

        Args:
            name: The function name.
            library_name: Optional library name.

        Returns:
            A unique key string.
        """
        if library_name:
            return f"{library_name}.{name}"
        return name


@dataclass
class ParameterPlaceholder(Expression):
    """
    Placeholder expression for substituted parameters.

    This is used during function inlining to carry SQL expressions
    through the AST substitution process. When the expression
    translator encounters this node, it returns the stored SQL expression.

    Attributes:
        name: The original parameter name.
        sql_expr: The SQL expression to substitute.
    """

    name: str
    sql_expr: SQLExpression


__all__ = [
    "FunctionInliner",
    "FunctionDef",
    "ParameterPlaceholder",
    "TranslationError",
]
