"""
AST introspection utilities for SQL expression analysis.

This module provides helper functions for querying SQL AST structure without
calling .to_sql() or using regex/string manipulation. All functions operate
purely on the AST node graph using isinstance() checks and property access.

Design principle: Enable AST-based decision making instead of string-based SQL inspection.
"""

import re
from typing import Optional, Set, Any
from ..translator.types import (
    SQLExpression,
    SQLSelect,
    SQLIdentifier,
    SQLQualifiedIdentifier,
    SQLAlias,
    SQLBinaryOp,
    SQLFunctionCall,
    SQLExists,
    SQLRaw,
    SQLSubquery,
    SQLUnaryOp,
    SQLCase,
    SQLCast,
    SQLArray,
    SQLList,
    SQLLambda,
    SQLJoin,
    SQLUnion,
    SQLIntersect,
    SQLExcept,
    SQLWindowFunction,
    SQLExtract,
    SQLNamedArg,
    SQLLiteral,
    SQLNull,
    SQLInterval,
    SQLIntervalLiteral,
    SQLParameterRef,
    SQLStructFieldAccess,
)

# Function names that represent list operations returning array results.
LIST_OPERATION_FUNCTIONS: frozenset[str] = frozenset({'list_filter', 'jsonconcat', 'list_apply', 'unnest', 'list_aggr'})


def camel_to_snake(name: str) -> str:
    """Convert camelCase to snake_case."""
    return re.sub(r'(?<!^)(?=[A-Z])', '_', name).lower()


def select_has_column(select: SQLSelect, name: str) -> bool:
    """
    Check if a SELECT statement has a column with the given name.
    
    Args:
        select: The SQLSelect node to inspect
        name: The column name to search for (case-insensitive)
        
    Returns:
        True if the SELECT has a column matching the name
        
    Examples:
        SELECT patient_id, resource FROM t1  → select_has_column(s, "patient_id") = True
        SELECT * FROM t1                     → select_has_column(s, "patient_id") = False (use select_has_star)
        SELECT p.patient_id AS pid FROM t1   → select_has_column(s, "patient_id") = True
    """
    if not select.columns:
        return False
    
    name_lower = name.lower()
    
    for col in select.columns:
        # Handle tuple format: (expr, alias)
        if isinstance(col, tuple):
            expr, alias = col
            if alias and alias.lower() == name_lower:
                return True
            # Also check the expression itself
            if _expr_references_name(expr, name_lower):
                return True
        # Handle SQLAlias: expr AS alias
        elif isinstance(col, SQLAlias):
            if col.alias and col.alias.lower() == name_lower:
                return True
            if _expr_references_name(col.expr, name_lower):
                return True
        # Handle raw SQLExpression
        else:
            if _expr_references_name(col, name_lower):
                return True
    
    return False


def _expr_references_name(expr: SQLExpression, name: str) -> bool:
    """Helper: Check if an expression references a specific name."""
    if isinstance(expr, SQLIdentifier):
        return expr.name.lower() == name
    elif isinstance(expr, SQLQualifiedIdentifier):
        # Check both full path and last segment
        # e.g., "t1.patient_id" matches "patient_id"
        return (
            ".".join(expr.parts).lower() == name
            or (expr.parts and expr.parts[-1].lower() == name)
        )
    elif isinstance(expr, SQLFunctionCall):
        # Check if function returns a column with this name
        # e.g., fhirpath_text(resource, 'patient_id') doesn't match "patient_id"
        # Only direct column refs match
        return False
    return False


def select_has_star(select: SQLSelect) -> bool:
    """
    Check if a SELECT statement uses wildcard (*).
    
    Args:
        select: The SQLSelect node to inspect
        
    Returns:
        True if SELECT * is present
        
    Examples:
        SELECT * FROM t1       → True
        SELECT t1.* FROM t1    → True
        SELECT patient_id FROM t1 → False
    """
    if not select.columns:
        return False
    
    for col in select.columns:
        # Handle tuple format
        if isinstance(col, tuple):
            expr, _ = col
        elif isinstance(col, SQLAlias):
            expr = col.expr
        else:
            expr = col
        
        # Check for * identifier
        if isinstance(expr, SQLIdentifier) and expr.name == "*":
            return True
        # Check for qualified.* (e.g., t1.*)
        if isinstance(expr, SQLQualifiedIdentifier):
            if expr.parts and expr.parts[-1] == "*":
                return True
    
    return False


def ast_has_node_type(expr: SQLExpression, cls: type) -> bool:
    """
    Recursively check if an expression tree contains a node of the given type.
    
    Args:
        expr: The root expression to search
        cls: The class type to search for (e.g., SQLExists, SQLFunctionCall)
        
    Returns:
        True if a node of type `cls` is found anywhere in the tree
        
    Examples:
        WHERE EXISTS (SELECT ...) → ast_has_node_type(where, SQLExists) = True
        WHERE x = 5               → ast_has_node_type(where, SQLExists) = False
    """
    if isinstance(expr, cls):
        return True
    
    # Import SQLExists and SQLSubquery at runtime to avoid circular imports
    from ..translator.types import SQLExists, SQLSubquery
    
    # Recursively check children based on expression type
    if isinstance(expr, SQLExists):
        return ast_has_node_type(expr.subquery, cls)
    
    elif isinstance(expr, SQLSubquery):
        return ast_has_node_type(expr.query, cls)
    
    elif isinstance(expr, SQLSelect):
        # Check all sub-expressions in SELECT
        if expr.columns:
            for col in expr.columns:
                if isinstance(col, tuple):
                    if ast_has_node_type(col[0], cls):
                        return True
                elif ast_has_node_type(col, cls):
                    return True
        if expr.where and ast_has_node_type(expr.where, cls):
            return True
        if expr.joins:
            for join in expr.joins:
                if join.on_condition and ast_has_node_type(join.on_condition, cls):
                    return True
        if expr.group_by:
            for gb in expr.group_by:
                if ast_has_node_type(gb, cls):
                    return True
        if expr.having and ast_has_node_type(expr.having, cls):
            return True
        if expr.order_by:
            for ob in expr.order_by:
                # order_by is (expr, direction)
                if isinstance(ob, tuple) and ast_has_node_type(ob[0], cls):
                    return True
    
    elif isinstance(expr, SQLFunctionCall):
        if expr.args:
            for arg in expr.args:
                if ast_has_node_type(arg, cls):
                    return True
    
    elif isinstance(expr, SQLAlias):
        return ast_has_node_type(expr.expr, cls)
    
    elif hasattr(expr, 'operands'):  # SQLBinaryOp, SQLUnion
        for operand in expr.operands:
            if ast_has_node_type(operand, cls):
                return True
    
    elif hasattr(expr, 'left') and hasattr(expr, 'right'):  # Binary operations
        if ast_has_node_type(expr.left, cls):
            return True
        if ast_has_node_type(expr.right, cls):
            return True
    
    elif hasattr(expr, 'operand'):  # Unary operations
        return ast_has_node_type(expr.operand, cls)
    
    return False


def extract_fhirpath_from_ast(expr: SQLExpression) -> Optional[str]:
    """
    Extract FHIRPath string from a SQLFunctionCall(name='fhirpath_*') node.
    
    Args:
        expr: The SQL expression to inspect
        
    Returns:
        The FHIRPath string if found, else None
        
    Examples:
        fhirpath_text(resource, 'status')     → 'status'
        fhirpath_date(r.resource, 'onset')    → 'onset'
        COALESCE(fhirpath_date(...), NULL)    → Extracts from first arg
    """
    if isinstance(expr, SQLFunctionCall):
        # Direct fhirpath call
        if expr.name and expr.name.startswith('fhirpath_'):
            # Second argument is the path (first is resource)
            if expr.args and len(expr.args) >= 2:
                path_arg = expr.args[1]
                # Extract literal value
                if hasattr(path_arg, 'value'):
                    return str(path_arg.value)
        
        # COALESCE of multiple fhirpath calls
        if expr.name == 'COALESCE' and expr.args:
            paths = []
            for arg in expr.args:
                path = extract_fhirpath_from_ast(arg)
                if path:
                    paths.append(path)
            # Return comma-separated for COALESCE (caller can split)
            return ", ".join(paths) if paths else None
    
    elif isinstance(expr, SQLAlias):
        return extract_fhirpath_from_ast(expr.expr)
    
    return None


def infer_sql_type_from_ast(expr: SQLExpression) -> str:
    """
    Infer SQL type from AST node (e.g., fhirpath_date → DATE).
    
    Args:
        expr: The SQL expression to inspect
        
    Returns:
        SQL type string: DATE, TIMESTAMP, BOOLEAN, VARCHAR, etc.
        
    Examples:
        fhirpath_date(...)     → "DATE"
        fhirpath_bool(...)     → "BOOLEAN"
        fhirpath_quantity(...) → "VARCHAR"
        fhirpath_text(...)     → "VARCHAR"
        COUNT(*)               → "INTEGER"
    """
    if isinstance(expr, SQLFunctionCall):
        name = expr.name.lower() if expr.name else ""
        
        # FHIRPath function type mapping
        if name == 'fhirpath_date':
            return "DATE"
        elif name == 'fhirpath_datetime':
            return "TIMESTAMP"
        elif name == 'fhirpath_bool' or name == 'fhirpath_boolean':
            return "BOOLEAN"
        elif name == 'fhirpath_integer':
            return "INTEGER"
        elif name == 'fhirpath_decimal':
            return "DOUBLE"
        elif name.startswith('fhirpath_'):
            # Default for fhirpath_text, fhirpath_quantity, etc.
            return "VARCHAR"
        
        # Aggregate functions
        if name in ('count', 'sum'):
            return "INTEGER"
        elif name in ('avg', 'median', 'stddev'):
            return "DOUBLE"
        
        # COALESCE inherits type from first non-null arg
        if name == 'coalesce' and expr.args:
            return infer_sql_type_from_ast(expr.args[0])
    
    elif isinstance(expr, SQLAlias):
        return infer_sql_type_from_ast(expr.expr)
    
    # Default
    return "VARCHAR"


def ast_has_correlated_ref(expr: SQLExpression, alias: str) -> bool:
    """
    Check if expression references a correlated alias (e.g., r.resource).
    
    Args:
        expr: The SQL expression to search
        alias: The table alias to check for (e.g., "r")
        
    Returns:
        True if expression contains a reference to the alias
        
    Examples:
        r.resource                  → ast_has_correlated_ref(expr, "r") = True
        fhirpath_text(r.resource, 'status') → ast_has_correlated_ref(expr, "r") = True
        t1.patient_id               → ast_has_correlated_ref(expr, "r") = False
    """
    alias_lower = alias.lower()
    
    if isinstance(expr, SQLQualifiedIdentifier):
        # Check if first part of qualified name matches alias
        if expr.parts and expr.parts[0].lower() == alias_lower:
            return True
    
    elif isinstance(expr, SQLFunctionCall):
        # Check all function arguments
        if expr.args:
            for arg in expr.args:
                if ast_has_correlated_ref(arg, alias):
                    return True
    
    elif isinstance(expr, SQLSelect):
        # Check columns, WHERE, etc.
        if expr.columns:
            for col in expr.columns:
                if isinstance(col, tuple):
                    if ast_has_correlated_ref(col[0], alias):
                        return True
                elif ast_has_correlated_ref(col, alias):
                    return True
        if expr.where and ast_has_correlated_ref(expr.where, alias):
            return True
    
    elif isinstance(expr, SQLAlias):
        return ast_has_correlated_ref(expr.expr, alias)
    
    elif hasattr(expr, 'left') and hasattr(expr, 'right'):
        return (ast_has_correlated_ref(expr.left, alias) or
                ast_has_correlated_ref(expr.right, alias))
    
    elif hasattr(expr, 'operand'):
        return ast_has_correlated_ref(expr.operand, alias)
    
    return False


def ast_has_patient_id_correlation(expr: SQLExpression, outer_alias: str) -> bool:
    """
    Check if expression contains a specific patient_id correlation to the outer alias.
    
    Unlike ast_has_correlated_ref which matches any reference, this specifically
    looks for `X.patient_id = outer_alias.patient_id` patterns.
    """
    alias_lower = outer_alias.lower()

    if isinstance(expr, SQLBinaryOp):
        if expr.operator == "=":
            # Check for pattern: X.patient_id = outer.patient_id
            left_match = (
                isinstance(expr.left, SQLQualifiedIdentifier)
                and len(expr.left.parts) == 2
                and expr.left.parts[1].lower() == "patient_id"
                and expr.left.parts[0].lower() == alias_lower
            )
            right_match = (
                isinstance(expr.right, SQLQualifiedIdentifier)
                and len(expr.right.parts) == 2
                and expr.right.parts[1].lower() == "patient_id"
                and expr.right.parts[0].lower() == alias_lower
            )
            if left_match or right_match:
                return True
        # Recurse into AND/OR
        if hasattr(expr, 'left') and hasattr(expr, 'right'):
            return (ast_has_patient_id_correlation(expr.left, outer_alias) or
                    ast_has_patient_id_correlation(expr.right, outer_alias))
    
    return False


def ast_references_name(expr: SQLExpression, name: str, _visited: Optional[Set[int]] = None) -> bool:
    """
    Walk the entire AST tree and check if any SQLIdentifier/SQLQualifiedIdentifier
    references the given name.
    
    Unlike select_has_column() which only checks column lists, this function
    recursively traverses all child nodes in the AST including WHERE clauses,
    JOIN conditions, function arguments, and subqueries.
    
    Args:
        expr: The root expression to search
        name: The identifier name to search for (case-insensitive)
        _visited: Internal set for cycle detection (do not pass)
        
    Returns:
        True if the name is found as an identifier anywhere in the tree
        
    Examples:
        SELECT * WHERE patient_id = 5           → ast_references_name(expr, "patient_id") = True
        SELECT * WHERE r.resource IS NOT NULL   → ast_references_name(expr, "resource") = True
        SELECT COUNT(*) FROM t1                  → ast_references_name(expr, "patient_id") = False
        fhirpath_text(r.resource, 'code')       → ast_references_name(expr, "resource") = True
        
    Note:
        Function calls like fhirpath_text() contain arguments but don't "reference"
        string literals. However, this function does check the actual identifier
        arguments (resource, table.column, etc.) within function calls.
    """
    # Initialize visited set for cycle detection
    if _visited is None:
        _visited = set()
    
    # Check for cycles (prevent infinite recursion on circular AST references)
    expr_id = id(expr)
    if expr_id in _visited:
        return False
    _visited.add(expr_id)
    
    name_lower = name.lower()
    
    # Direct identifier match
    if isinstance(expr, SQLIdentifier):
        return expr.name.lower() == name_lower
    
    # Qualified identifier match (e.g., t1.resource or r.patient_id)
    if isinstance(expr, SQLQualifiedIdentifier):
        # Check both full path and individual parts
        full_path = ".".join(expr.parts).lower()
        if full_path == name_lower:
            return True
        # Check individual parts (last segment)
        if expr.parts and expr.parts[-1].lower() == name_lower:
            return True
        # Check all parts in case name is "t1.resource"
        if name_lower in [p.lower() for p in expr.parts]:
            return True
        return False
    
    # Recursively check function call arguments
    if isinstance(expr, SQLFunctionCall):
        if expr.args:
            for arg in expr.args:
                if ast_references_name(arg, name, _visited):
                    return True
        return False
    
    # Recursively check named arguments (e.g., struct_pack(name := value))
    from ..translator.types import SQLNamedArg
    if isinstance(expr, SQLNamedArg):
        return ast_references_name(expr.value, name, _visited)

    # Recursively check aliased expressions
    if isinstance(expr, SQLAlias):
        return ast_references_name(expr.expr, name, _visited)
    
    # Recursively check SELECT statements (columns, WHERE, JOINs, etc.)
    if isinstance(expr, SQLSelect):
        # Check columns
        if expr.columns:
            for col in expr.columns:
                if isinstance(col, tuple):
                    if ast_references_name(col[0], name, _visited):
                        return True
                elif ast_references_name(col, name, _visited):
                    return True
        
        # Check WHERE clause
        if expr.where and ast_references_name(expr.where, name, _visited):
            return True
        
        # Check FROM clause
        if expr.from_clause and ast_references_name(expr.from_clause, name, _visited):
            return True
        
        # Check JOINs (both table and condition)
        if expr.joins:
            for join in expr.joins:
                if join.table and ast_references_name(join.table, name, _visited):
                    return True
                if join.on_condition and ast_references_name(join.on_condition, name, _visited):
                    return True
        
        # Check GROUP BY
        if expr.group_by:
            for gb in expr.group_by:
                if ast_references_name(gb, name, _visited):
                    return True
        
        # Check HAVING
        if expr.having and ast_references_name(expr.having, name, _visited):
            return True
        
        # Check ORDER BY
        if expr.order_by:
            for ob in expr.order_by:
                if isinstance(ob, tuple):
                    if ast_references_name(ob[0], name, _visited):
                        return True
                elif ast_references_name(ob, name, _visited):
                    return True
        
        return False
    
    # Recursively check EXISTS/subqueries
    from ..translator.types import SQLExists, SQLSubquery
    if isinstance(expr, SQLExists):
        if expr.subquery:
            return ast_references_name(expr.subquery, name, _visited)
        return False
    
    if isinstance(expr, SQLSubquery):
        if expr.query:
            return ast_references_name(expr.query, name, _visited)
        return False
    
    # Recursively check binary operations
    if hasattr(expr, 'left') and hasattr(expr, 'right'):
        return (ast_references_name(expr.left, name, _visited) or
                ast_references_name(expr.right, name, _visited))
    
    # Recursively check unary operations
    if hasattr(expr, 'operand'):
        return ast_references_name(expr.operand, name, _visited)
    
    # Recursively check n-ary operations (UNION, etc.)
    if hasattr(expr, 'operands'):
        for operand in expr.operands:
            if ast_references_name(operand, name, _visited):
                return True
    
    return False


def collect_cte_references(expr: SQLExpression, _visited: Optional[Set[int]] = None) -> Set[str]:
    """
    # Initialize visited set for cycle detection
    if _visited is None:
        _visited = set()
    
    # Check for cycles
    expr_id = id(expr)
    if expr_id in _visited:
        return set()
    _visited.add(expr_id)
    
    Walk the AST tree and collect all quoted SQLIdentifier names that are
    CTE (Common Table Expression) references.
    
    CTE references are typically quoted identifiers that match CTE names defined
    in WITH clauses. This function identifies potential CTE references by finding
    quoted identifiers in the expression tree.
    
    Args:
        expr: The root expression to search
        
    Returns:
        A set of CTE names (quoted identifiers) found in the tree
        
    Examples:
        WITH cte1 AS (...) SELECT * FROM "cte1"        → {"cte1"}
        SELECT * FROM "cte1" JOIN "cte2"                → {"cte1", "cte2"}
        SELECT * FROM resource WHERE id IN ("id_ref")   → {"id_ref"} (note: named ref)
        SELECT resource, patient_id FROM t1             → {} (unquoted, not CTE ref)
        
    Note:
        Only quoted identifiers are considered CTE references because:
        - CTE names in ANSI SQL may require quoting when they conflict with keywords
        - The presence of quotes indicates they are intentional references
        - Unquoted identifiers are typically table names or columns
    """
    cte_refs: Set[str] = set()
    
    # Direct quoted identifier
    if isinstance(expr, SQLIdentifier):
        if expr.quoted:
            cte_refs.add(expr.name)
        return cte_refs
    
    # Qualified identifier: check parts that are quoted
    if isinstance(expr, SQLQualifiedIdentifier):
        # In qualified identifiers, if parts are quoted, collect them
        # Usually the first part would be the CTE reference if it's a CTE
        if expr.parts:
            # For qualified identifiers, typically the first part might be a CTE
            # But we need to look at the actual structure
            # Add all parts that look like they could be CTEs
            for part in expr.parts:
                # Note: SQLQualifiedIdentifier doesn't track per-part quoting
                # So we collect based on context
                pass
        return cte_refs
    
    # Recursively check function call arguments
    if isinstance(expr, SQLFunctionCall):
        if expr.args:
            for arg in expr.args:
                cte_refs.update(collect_cte_references(arg, _visited))
        return cte_refs
    
    # Recursively check aliased expressions
    if isinstance(expr, SQLAlias):
        return collect_cte_references(expr.expr, _visited)
    
    # Recursively check SELECT statements
    if isinstance(expr, SQLSelect):
        # Check columns
        if expr.columns:
            for col in expr.columns:
                if isinstance(col, tuple):
                    cte_refs.update(collect_cte_references(col[0], _visited))
                else:
                    cte_refs.update(collect_cte_references(col, _visited))
        
        # Check FROM clause (this is where CTE refs appear)
        if expr.from_clause:
            cte_refs.update(collect_cte_references(expr.from_clause, _visited))
        
        # Check WHERE clause
        if expr.where:
            cte_refs.update(collect_cte_references(expr.where, _visited))
        
        # Check JOINs
        if expr.joins:
            for join in expr.joins:
                if join.table:
                    cte_refs.update(collect_cte_references(join.table, _visited))
                if join.on_condition:
                    cte_refs.update(collect_cte_references(join.on_condition, _visited))
        
        # Check GROUP BY
        if expr.group_by:
            for gb in expr.group_by:
                cte_refs.update(collect_cte_references(gb, _visited))
        
        # Check HAVING
        if expr.having:
            cte_refs.update(collect_cte_references(expr.having, _visited))
        
        # Check ORDER BY
        if expr.order_by:
            for ob in expr.order_by:
                if isinstance(ob, tuple):
                    cte_refs.update(collect_cte_references(ob[0], _visited))
                else:
                    cte_refs.update(collect_cte_references(ob, _visited))
        
        return cte_refs
    
    # Recursively check EXISTS/subqueries
    from ..translator.types import SQLExists, SQLSubquery
    if isinstance(expr, SQLExists):
        if expr.subquery:
            return collect_cte_references(expr.subquery, _visited)
        return cte_refs
    
    if isinstance(expr, SQLSubquery):
        if expr.query:
            return collect_cte_references(expr.query, _visited)
        return cte_refs
    
    # Recursively check binary operations
    if hasattr(expr, 'left') and hasattr(expr, 'right'):
        cte_refs.update(collect_cte_references(expr.left, _visited))
        cte_refs.update(collect_cte_references(expr.right, _visited))
        return cte_refs
    
    # Recursively check unary operations
    if hasattr(expr, 'operand'):
        return collect_cte_references(expr.operand, _visited)
    
    # Recursively check n-ary operations (UNION, etc.)
    if hasattr(expr, 'operands'):
        for operand in expr.operands:
            cte_refs.update(collect_cte_references(operand, _visited))
        return cte_refs
    
    return cte_refs


def is_fhirpath_call(expr: SQLExpression) -> bool:
    """
    Check if the given expression is a SQLFunctionCall with a name starting
    with "fhirpath_".
    
    This is a simple type and name check useful for identifying FHIRPath
    function calls in the AST.
    
    Args:
        expr: The SQL expression to check
        
    Returns:
        True if expr is a SQLFunctionCall with name starting with "fhirpath_"
        
    Examples:
        fhirpath_text(resource, 'code')       → True
        fhirpath_date(r.resource, 'onset')    → True
        fhirpath_quantity(resource, 'value')  → True
        COUNT(*)                               → False
        COALESCE(fhirpath_text(...), NULL)    → False (COALESCE is not fhirpath)
        resource                               → False (not a function call)
    """
    if not isinstance(expr, SQLFunctionCall):
        return False
    
    if not expr.name:
        return False
    
    return expr.name.startswith("fhirpath_")


def ast_is_list_operation(expr: SQLExpression) -> bool:
    """
    Check if the given expression is a list operation that needs extraction.
    
    List operations include: list_filter, jsonConcat, list_apply
    These return array results and may need array_extract() for scalar use.
    
    Args:
        expr: The SQL expression to check
        
    Returns:
        True if expr is a list operation function call
        
    Examples:
        list_filter(array, condition)  → True
        jsonConcat(array1, array2)     → True
        list_apply(array, function)    → True
        COALESCE(x, y)                 → False
        COUNT(*)                       → False
    """
    if not isinstance(expr, SQLFunctionCall):
        return False
    
    if not expr.name:
        return False
    
    return expr.name.lower() in LIST_OPERATION_FUNCTIONS


def ast_is_case_with_union(expr: SQLExpression) -> bool:
    """
    Check if an expression is a CASE statement with UNION operations in branches.
    
    This pattern is problematic in scalar context and indicates a structural issue.
    
    Args:
        expr: The SQL expression to check
        
    Returns:
        True if expr is a CASE-WHEN with SQLUnion in any branch
    """
    from ..translator.types import SQLCase, SQLUnion
    
    if not isinstance(expr, SQLCase):
        return False
    
    # Check each WHEN/THEN branch
    if expr.when_clauses:
        for when_expr, then_expr in expr.when_clauses:
            if ast_has_node_type(then_expr, SQLUnion):
                return True
    
    # Check ELSE clause
    if expr.else_clause and ast_has_node_type(expr.else_clause, SQLUnion):
        return True
    
    return False


def ast_is_boolean_result(expr: SQLExpression) -> bool:
    """
    Check if an expression produces a boolean result.
    
    Boolean expressions include comparisons (> 0, = 0, etc.) that don't need extraction.
    
    Args:
        expr: The SQL expression to check
        
    Returns:
        True if expr is a comparison that produces boolean
    """
    from ..translator.types import SQLBinaryOp
    
    if not isinstance(expr, SQLBinaryOp):
        return False
    
    # Check if operator is a comparison
    comparison_ops = {'>', '>=', '<', '<=', '=', '!=', '<>', 'AND', 'OR'}
    return expr.operator.upper() in comparison_ops


def is_simple_identifier(expr: SQLExpression) -> bool:
    """
    Check if an expression is a simple identifier (no dots, no function calls).
    
    Used in A-3 to replace string checks like '.' not in resource_sql.
    
    Args:
        expr: The SQL expression to check
        
    Returns:
        True if expr is SQLIdentifier or SQLAlias wrapping SQLIdentifier
        
    Examples:
        SQLIdentifier("table1") → True
        SQLAlias(SQLIdentifier("t"), "alias") → True
        SQLQualifiedIdentifier(["t", "resource"]) → False (has dot)
        SQLFunctionCall("COUNT", ...) → False (is function)
    """
    if isinstance(expr, SQLIdentifier):
        return True
    if isinstance(expr, SQLAlias) and isinstance(expr.expr, SQLIdentifier):
        return True
    return False


def ast_is_function_call(expr: SQLExpression) -> bool:
    """
    Check if an expression is a function call.
    
    Args:
        expr: The SQL expression to check
        
    Returns:
        True if expr is SQLFunctionCall
    """
    return isinstance(expr, SQLFunctionCall)


def infer_fhirpath_type_from_ast(expr: SQLExpression) -> str:
    """
    Extract the type suffix from a fhirpath function call.
    
    Replaces string manipulation like: source_sql.name.split('_')[1]
    Used in A-4 to eliminate regex/string checks in expressions.py.
    
    Args:
        expr: The SQL expression to check
        
    Returns:
        Type string ('text', 'date', 'bool', 'quantity', etc.) or 'text' as default
        
    Examples:
        SQLFunctionCall("fhirpath_text", ...) → "text"
        SQLFunctionCall("fhirpath_date", ...) → "date"
        SQLFunctionCall("fhirpath_bool", ...) → "bool"
        SQLIdentifier("patient") → "text" (fallback)
    """
    if isinstance(expr, SQLFunctionCall) and expr.name and expr.name.startswith('fhirpath_'):
        # Extract type from fhirpath_TYPE
        parts = expr.name.split('_')
        if len(parts) >= 2:
            return parts[1]
    return 'text'


def ast_get_name(expr: SQLExpression) -> Optional[str]:
    """
    Extract a table/alias name from an AST node without calling .to_sql().

    Returns a plain string identifier suitable for use in
    SQLQualifiedIdentifier parts (e.g. building ``[name, "resource"]``).

    Args:
        expr: The SQL expression to inspect

    Returns:
        The extracted name string, or None if no name can be determined

    Examples:
        SQLIdentifier("t1")                     → "t1"
        SQLAlias(SQLIdentifier("t1"), "alias1")  → "alias1"
        SQLQualifiedIdentifier(["schema","t1"])  → "schema"
        SQLRaw('"MyTable"')                      → "MyTable"
        SQLRaw('func(x)')                        → None
    """
    if isinstance(expr, SQLIdentifier):
        return expr.name
    if isinstance(expr, SQLAlias):
        return expr.alias
    if isinstance(expr, SQLQualifiedIdentifier):
        return expr.parts[0] if expr.parts else None
    if isinstance(expr, SQLRaw):
        raw = expr.raw_sql
        # Quoted identifier like '"MyTable"'
        if raw.startswith('"') and raw.endswith('"'):
            return raw[1:-1]
        # Simple unquoted identifier (no parens, no spaces)
        if '(' not in raw and ' ' not in raw:
            return raw
        return None
    return None


def replace_qualified_alias(
    expr: SQLExpression, old_alias: str, new_alias: str
) -> SQLExpression:
    """Recursively replace a table alias in all SQLQualifiedIdentifier nodes.

    Walks the entire SQL AST and replaces any
    ``SQLQualifiedIdentifier(parts=[old_alias, ...])`` with
    ``SQLQualifiedIdentifier(parts=[new_alias, ...])``.

    This is used to fix RESOURCE_ROWS CTEs where correlated subqueries
    reference ``p.patient_id`` but the enclosing CTE uses a different
    FROM alias (e.g. ``AdolescentMed``).

    The function is non-destructive — it returns new AST nodes rather
    than mutating the originals.
    """
    if expr is None:
        return None  # type: ignore[return-value]

    # --- Leaf nodes that never contain children ---
    if isinstance(expr, (SQLLiteral, SQLNull, SQLParameterRef, SQLIntervalLiteral)):
        return expr

    if isinstance(expr, SQLRaw):
        # SQLRaw contains literal SQL text.  Audit mode code (e.g.,
        # _flatten_audit_tree, _inject_audit_evidence) produces SQLRaw nodes
        # that may embed stale "p.patient_id" references.  Do a targeted
        # text replacement so RESOURCE_ROWS CTEs get the correct alias.
        old_ref = f"{old_alias}.patient_id"
        if old_ref in expr.raw_sql:
            new_sql = expr.raw_sql.replace(old_ref, f"{new_alias}.patient_id")
            return SQLRaw(raw_sql=new_sql)
        return expr

    if isinstance(expr, SQLIdentifier):
        return expr

    # --- The target node type ---
    if isinstance(expr, SQLQualifiedIdentifier):
        if expr.parts and expr.parts[0] == old_alias:
            return SQLQualifiedIdentifier(parts=[new_alias] + list(expr.parts[1:]))
        return expr

    # --- Composite nodes ---
    if isinstance(expr, SQLBinaryOp):
        return SQLBinaryOp(
            operator=expr.operator,
            left=replace_qualified_alias(expr.left, old_alias, new_alias),
            right=replace_qualified_alias(expr.right, old_alias, new_alias),
        )

    if isinstance(expr, SQLUnaryOp):
        return SQLUnaryOp(
            operator=expr.operator,
            operand=replace_qualified_alias(expr.operand, old_alias, new_alias),
            prefix=expr.prefix,
        )

    if isinstance(expr, SQLFunctionCall):
        new_args = [replace_qualified_alias(a, old_alias, new_alias) for a in expr.args] if expr.args else expr.args
        return SQLFunctionCall(
            name=expr.name,
            args=new_args,
            distinct=expr.distinct,
        )

    if isinstance(expr, SQLAlias):
        return SQLAlias(
            expr=replace_qualified_alias(expr.expr, old_alias, new_alias),
            alias=expr.alias,
        )

    if isinstance(expr, SQLCast):
        return SQLCast(
            expression=replace_qualified_alias(expr.expression, old_alias, new_alias),
            target_type=expr.target_type,
            try_cast=expr.try_cast,
        )

    if isinstance(expr, SQLCase):
        new_whens = []
        for w in (expr.when_clauses or []):
            new_whens.append((
                replace_qualified_alias(w[0], old_alias, new_alias),
                replace_qualified_alias(w[1], old_alias, new_alias),
            ))
        new_else = replace_qualified_alias(expr.else_clause, old_alias, new_alias) if expr.else_clause else None
        return SQLCase(
            operand=replace_qualified_alias(expr.operand, old_alias, new_alias) if expr.operand else None,
            when_clauses=new_whens,
            else_clause=new_else,
        )

    if isinstance(expr, SQLSubquery):
        return SQLSubquery(
            query=replace_qualified_alias(expr.query, old_alias, new_alias),
        )

    if isinstance(expr, SQLExists):
        return SQLExists(
            subquery=replace_qualified_alias(expr.subquery, old_alias, new_alias),
        )

    if isinstance(expr, SQLSelect):
        new_cols = [replace_qualified_alias(c, old_alias, new_alias) for c in expr.columns] if expr.columns else expr.columns
        new_from = replace_qualified_alias(expr.from_clause, old_alias, new_alias) if expr.from_clause else None
        new_where = replace_qualified_alias(expr.where, old_alias, new_alias) if expr.where else None
        new_joins = None
        if expr.joins:
            new_joins = []
            for j in expr.joins:
                new_joins.append(SQLJoin(
                    join_type=j.join_type,
                    table=replace_qualified_alias(j.table, old_alias, new_alias),
                    alias=j.alias,
                    on_condition=replace_qualified_alias(j.on_condition, old_alias, new_alias) if j.on_condition else None,
                ))
        new_gb = [replace_qualified_alias(g, old_alias, new_alias) for g in expr.group_by] if expr.group_by else expr.group_by
        new_having = replace_qualified_alias(expr.having, old_alias, new_alias) if expr.having else None
        new_ob = [replace_qualified_alias(o, old_alias, new_alias) for o in expr.order_by] if expr.order_by else expr.order_by
        return SQLSelect(
            columns=new_cols,
            from_clause=new_from,
            where=new_where,
            joins=new_joins,
            group_by=new_gb,
            having=new_having,
            order_by=new_ob,
            distinct=expr.distinct,
            limit=expr.limit,
        )

    if isinstance(expr, SQLArray):
        return SQLArray(
            elements=[replace_qualified_alias(e, old_alias, new_alias) for e in expr.elements] if expr.elements else expr.elements,
        )

    if isinstance(expr, SQLList):
        return SQLList(
            items=[replace_qualified_alias(e, old_alias, new_alias) for e in expr.items] if expr.items else expr.items,
        )

    if isinstance(expr, SQLLambda):
        return SQLLambda(
            param=expr.param,
            body=replace_qualified_alias(expr.body, old_alias, new_alias),
        )

    if isinstance(expr, SQLInterval):
        return SQLInterval(
            low=replace_qualified_alias(expr.low, old_alias, new_alias) if expr.low else None,
            high=replace_qualified_alias(expr.high, old_alias, new_alias) if expr.high else None,
            low_closed=expr.low_closed,
            high_closed=expr.high_closed,
        )

    if isinstance(expr, SQLExtract):
        return SQLExtract(
            extract_field=expr.extract_field,
            source=replace_qualified_alias(expr.source, old_alias, new_alias),
        )

    if isinstance(expr, SQLNamedArg):
        return SQLNamedArg(
            name=expr.name,
            value=replace_qualified_alias(expr.value, old_alias, new_alias),
        )

    if isinstance(expr, SQLUnion):
        return SQLUnion(
            operands=[replace_qualified_alias(op, old_alias, new_alias) for op in expr.operands],
            distinct=expr.distinct,
        )

    if isinstance(expr, SQLIntersect):
        return SQLIntersect(
            operands=[replace_qualified_alias(op, old_alias, new_alias) for op in expr.operands],
        )

    if isinstance(expr, SQLExcept):
        return SQLExcept(
            operands=[replace_qualified_alias(op, old_alias, new_alias) for op in expr.operands],
        )

    if isinstance(expr, SQLWindowFunction):
        new_args = [replace_qualified_alias(a, old_alias, new_alias) for a in expr.function_args] if expr.function_args else expr.function_args
        new_pb = [replace_qualified_alias(p, old_alias, new_alias) for p in expr.partition_by] if expr.partition_by else expr.partition_by
        new_ob = [(replace_qualified_alias(o[0], old_alias, new_alias), o[1]) for o in expr.order_by] if expr.order_by else expr.order_by
        return SQLWindowFunction(
            function=expr.function,
            function_args=new_args,
            partition_by=new_pb,
            order_by=new_ob,
            frame_clause=expr.frame_clause,
        )

    if isinstance(expr, SQLStructFieldAccess):
        new_inner = replace_qualified_alias(expr.expr, old_alias, new_alias)
        if new_inner is not expr.expr:
            return SQLStructFieldAccess(expr=new_inner, field_name=expr.field_name)
        return expr

    # Fallback: return unchanged for any unknown node type
    return expr

