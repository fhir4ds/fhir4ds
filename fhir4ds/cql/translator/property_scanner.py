"""
Property scanner for retrieve optimization.

This module walks SQL AST to find all FHIRPath property accesses.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Set

from .types import (
    SQLExpression,
    SQLFunctionCall,
    SQLSelect,
    SQLLambda,
    SQLCase,
    SQLBinaryOp,
    SQLUnaryOp,
    SQLList,
    SQLLiteral,
    SQLIdentifier,
    SQLAlias,
    SQLSubquery,
    SQLJoin,
    SQLUnion,
    SQLCast,
    SQLNull,
    SQLArray,
    SQLQualifiedIdentifier,
)


@dataclass
class PropertyAccess:
    """
    Information about a property access in the AST.

    Attributes:
        property_path: FHIRPath expression (e.g., "onsetDateTime", "verificationStatus.coding.code")
        fhirpath_function: Function used (e.g., "fhirpath_text", "fhirpath_date")
        location: Optional context about where this access occurred (for debugging)
    """
    property_path: str
    fhirpath_function: str
    location: str = ""

    def __hash__(self):
        return hash(self.property_path)

    def __eq__(self, other):
        if not isinstance(other, PropertyAccess):
            return False
        return self.property_path == other.property_path


def scan_ast_for_properties(ast: SQLExpression) -> Set[PropertyAccess]:
    """
    Walk SQL AST to find all FHIRPath property accesses.

    Looks for SQLFunctionCall nodes with names like:
    - fhirpath_text(resource, 'property')
    - fhirpath_date(resource, 'property')
    - fhirpath_bool(resource, 'property')
    - etc.

    Args:
        ast: Root SQL AST node to scan

    Returns:
        Set of PropertyAccess objects found in the AST

    Example:
        ast = SQLFunctionCall(
            name="fhirpath_date",
            args=[SQLIdentifier("r"), SQLLiteral("onsetDateTime")]
        )
        properties = scan_ast_for_properties(ast)
        # Returns: {PropertyAccess("onsetDateTime", "fhirpath_date")}
    """
    properties: Set[PropertyAccess] = set()

    def walk(node: SQLExpression, depth: int = 0) -> None:
        """
        Recursively walk AST node and collect property accesses.

        Args:
            node: Current AST node
            depth: Recursion depth (for debugging)
        """
        if node is None:
            return

        # Check for fhirpath_* function calls
        if isinstance(node, SQLFunctionCall):
            if node.name.startswith("fhirpath_"):
                # Extract property path from second argument
                if len(node.args) >= 2:
                    property_arg = node.args[1]
                    if isinstance(property_arg, SQLLiteral):
                        properties.add(PropertyAccess(
                            property_path=str(property_arg.value),
                            fhirpath_function=node.name,
                            location=f"depth_{depth}"
                        ))

            # Recurse into function arguments
            for arg in node.args:
                walk(arg, depth + 1)

        # Walk lambda body
        elif isinstance(node, SQLLambda):
            walk(node.body, depth + 1)

        # Walk SELECT components
        elif isinstance(node, SQLSelect):
            # Walk column expressions
            for col in node.columns:
                if isinstance(col, tuple):
                    # (expr, alias) tuple
                    walk(col[0], depth + 1)
                else:
                    walk(col, depth + 1)

            # Walk FROM clause
            if node.from_clause:
                walk(node.from_clause, depth + 1)

            # Walk JOINs
            if node.joins:
                for join in node.joins:
                    if isinstance(join, SQLJoin):
                        walk(join.table, depth + 1)
                        if join.on_condition:
                            walk(join.on_condition, depth + 1)

            # Walk WHERE clause
            if node.where:
                walk(node.where, depth + 1)

            # Walk GROUP BY
            if node.group_by:
                for expr in node.group_by:
                    walk(expr, depth + 1)

            # Walk HAVING
            if node.having:
                walk(node.having, depth + 1)

        # Walk CASE expression
        elif isinstance(node, SQLCase):
            # Walk each WHEN condition and result
            for condition, result in node.when_clauses:
                walk(condition, depth + 1)
                walk(result, depth + 1)

            # Walk ELSE clause
            if node.else_clause:
                walk(node.else_clause, depth + 1)

            # Walk operand if present (simple CASE)
            if node.operand:
                walk(node.operand, depth + 1)

        # Walk binary operations
        elif isinstance(node, SQLBinaryOp):
            walk(node.left, depth + 1)
            walk(node.right, depth + 1)

        # Walk unary operations
        elif isinstance(node, SQLUnaryOp):
            walk(node.operand, depth + 1)

        # Walk list elements
        elif isinstance(node, SQLList):
            for item in node.items:
                walk(item, depth + 1)

        # Walk array elements
        elif isinstance(node, SQLArray):
            for elem in node.elements:
                walk(elem, depth + 1)

        # Walk alias
        elif isinstance(node, SQLAlias):
            walk(node.expr, depth + 1)

        # Walk subquery
        elif isinstance(node, SQLSubquery):
            walk(node.query, depth + 1)

        # Walk union
        elif isinstance(node, SQLUnion):
            for operand in node.operands:
                walk(operand, depth + 1)

        # Walk cast
        elif isinstance(node, SQLCast):
            walk(node.expression, depth + 1)

        # SQLIdentifier, SQLLiteral, SQLNull, SQLQualifiedIdentifier - no children to walk

    # Start walking from root
    walk(ast)
    return properties
