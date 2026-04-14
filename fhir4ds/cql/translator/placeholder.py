"""
Placeholder implementation for retrieve optimization.

This module provides the RetrievePlaceholder class and resolution logic
for deferring retrieve resolution until CTEs are built.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

from .types import (
    SQLExpression, SQLIdentifier, SQLNull, SQLFunctionCall, SQLLiteral,
    SQLSelect, SQLLambda, SQLCase, SQLBinaryOp, SQLUnaryOp, SQLList,
    SQLSubquery, SQLUnion, SQLCast, SQLAlias, SQLJoin, SQLArray, SQLExists,
    SQLInterval, SQLIntersect, SQLExcept, SQLWindowFunction, SQLNamedArg,
    SQLExtract, SQLStructFieldAccess,
)


class UnresolvedPlaceholderError(Exception):
    """
    Raised when a placeholder cannot be resolved to a CTE.

    This indicates a bug in the translator - all placeholders should
    have corresponding CTEs created during Phase 2.
    """
    pass


@dataclass
class RetrievePlaceholder(SQLExpression):
    """
    Placeholder for a retrieve expression that will be resolved to a CTE reference.

    Used during Phase 1 translation to defer retrieve resolution until CTEs are built.
    Each placeholder represents a retrieve like: [Condition: "Diabetes"]

    Attributes:
        resource_type: FHIR resource type (e.g., "Condition", "Observation")
        valueset: ValueSet name or URL (optional, None for [Condition] without filter)
        profile_url: Optional FHIR profile URL for profile-specific columns
                     (e.g., "http://hl7.org/fhir/us/core/StructureDefinition/us-core-blood-pressure")

    The key() property returns a tuple that uniquely identifies this retrieve
    and is used to look up the corresponding CTE.
    """
    resource_type: str
    valueset: Optional[str] = None
    profile_url: Optional[str] = None
    code_property: Optional[str] = None
    precedence: int = 10  # PRIMARY precedence

    @property
    def key(self) -> Tuple[str, Optional[str], Optional[str]]:
        """
        Unique key for this retrieve.

        Two retrieves with the same resource_type, valueset, and profile_url will have
        the same key and share the same CTE.

        Returns:
            Tuple of (resource_type, valueset, profile_url)
        """
        return (self.resource_type, self.valueset, self.profile_url)

    def to_sql(self) -> str:
        """
        Should never be called - placeholders must be resolved first.

        Raises:
            RuntimeError: Always, with helpful message
        """
        raise RuntimeError(
            f"Unresolved retrieve placeholder: {self.resource_type}"
            f"{f' with valueset {self.valueset}' if self.valueset else ''}"
            f"{f' with profile {self.profile_url}' if self.profile_url else ''}\n"
            f"This is a bug - all placeholders must be resolved before SQL generation.\n"
            f"Key: {self.key}"
        )

    def __repr__(self) -> str:
        return f"RetrievePlaceholder({self.resource_type!r}, {self.valueset!r}, {self.profile_url!r})"

    def __hash__(self) -> int:
        return hash((self.resource_type, self.valueset, self.profile_url))

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, RetrievePlaceholder):
            return False
        return (self.resource_type == other.resource_type and
                self.valueset == other.valueset and
                self.profile_url == other.profile_url)


def resolve_placeholders(
    ast: SQLExpression,
    cte_name_map: Dict[Tuple[str, Optional[str], Optional[str]], str]
) -> SQLExpression:
    """
    Walk AST and replace all placeholders with CTE references.

    Recursively transforms the AST, replacing each RetrievePlaceholder
    with an SQLIdentifier referencing the corresponding CTE.

    Args:
        ast: SQL AST possibly containing placeholders
        cte_name_map: Map of retrieve key → CTE name
                      Key is (resource_type, valueset, profile_url)

    Returns:
        Transformed AST with all placeholders resolved

    Raises:
        UnresolvedPlaceholderError: If a placeholder has no corresponding CTE

    Example:
        Input AST contains:
            RetrievePlaceholder("Condition", "Diabetes", None)

        cte_name_map = {
            ("Condition", "Diabetes", None): "Condition: Diabetes"
        }

        Output AST contains:
            SQLIdentifier("Condition: Diabetes", quoted=True)
    """
    if isinstance(ast, RetrievePlaceholder):
        # Base case: resolve this placeholder
        cte_name = cte_name_map.get(ast.key)

        if cte_name is None:
            # Debug logging for key mismatch diagnosis
            logger.debug(
                f"Placeholder key not found in CTE name map:\n"
                f"  Placeholder key: {ast.key}\n"
                f"  Available keys: {list(cte_name_map.keys())}"
            )
            raise UnresolvedPlaceholderError(
                f"Cannot resolve retrieve placeholder:\n"
                f"  Resource Type: {ast.resource_type}\n"
                f"  ValueSet: {ast.valueset}\n"
                f"  Key: {ast.key}\n"
                f"\n"
                f"Available CTEs: {list(cte_name_map.values())}\n"
                f"\n"
                f"This is a bug in the translator - all retrieves should have CTEs.\n"
                f"Make sure Phase 2 created a CTE for this retrieve."
            )

        # Return CTE reference
        return SQLIdentifier(cte_name, quoted=True)

    # Recursive cases: transform children
    if isinstance(ast, SQLFunctionCall):
        return SQLFunctionCall(
            name=ast.name,
            args=[resolve_placeholders(arg, cte_name_map) for arg in ast.args],
            distinct=ast.distinct
        )

    elif isinstance(ast, SQLLambda):
        return SQLLambda(
            param=ast.param,
            body=resolve_placeholders(ast.body, cte_name_map)
        )

    elif isinstance(ast, SQLSelect):
        # Resolve all components
        resolved_columns = []
        for col in ast.columns:
            if isinstance(col, tuple):
                resolved_columns.append((
                    resolve_placeholders(col[0], cte_name_map),
                    col[1]
                ))
            else:
                resolved_columns.append(resolve_placeholders(col, cte_name_map))

        resolved_joins = None
        if ast.joins:
            resolved_joins = []
            for join in ast.joins:
                if isinstance(join, SQLJoin):
                    resolved_joins.append(SQLJoin(
                        join_type=join.join_type,
                        table=resolve_placeholders(join.table, cte_name_map),
                        alias=join.alias,
                        on_condition=resolve_placeholders(join.on_condition, cte_name_map) if join.on_condition else None
                    ))
                else:
                    resolved_joins.append(join)

        return SQLSelect(
            columns=resolved_columns,
            from_clause=resolve_placeholders(ast.from_clause, cte_name_map) if ast.from_clause else None,
            joins=resolved_joins,
            where=resolve_placeholders(ast.where, cte_name_map) if ast.where else None,
            group_by=[resolve_placeholders(g, cte_name_map) for g in ast.group_by] if ast.group_by else None,
            having=resolve_placeholders(ast.having, cte_name_map) if ast.having else None,
            order_by=ast.order_by,
            distinct=ast.distinct,
            limit=ast.limit
        )

    elif isinstance(ast, SQLBinaryOp):
        return SQLBinaryOp(
            operator=ast.operator,
            left=resolve_placeholders(ast.left, cte_name_map),
            right=resolve_placeholders(ast.right, cte_name_map)
        )

    elif isinstance(ast, SQLUnaryOp):
        return SQLUnaryOp(
            operator=ast.operator,
            operand=resolve_placeholders(ast.operand, cte_name_map),
            prefix=ast.prefix
        )

    elif isinstance(ast, SQLCase):
        resolved_when = [
            (resolve_placeholders(cond, cte_name_map), resolve_placeholders(result, cte_name_map))
            for cond, result in ast.when_clauses
        ]
        return SQLCase(
            when_clauses=resolved_when,
            else_clause=resolve_placeholders(ast.else_clause, cte_name_map) if ast.else_clause else None,
            operand=resolve_placeholders(ast.operand, cte_name_map) if ast.operand else None
        )

    elif isinstance(ast, SQLList):
        return SQLList(
            items=[resolve_placeholders(item, cte_name_map) for item in ast.items]
        )

    elif isinstance(ast, SQLArray):
        return SQLArray(
            elements=[resolve_placeholders(elem, cte_name_map) for elem in ast.elements]
        )

    elif isinstance(ast, SQLAlias):
        return SQLAlias(
            expr=resolve_placeholders(ast.expr, cte_name_map),
            alias=ast.alias
        )

    elif isinstance(ast, SQLSubquery):
        return SQLSubquery(
            query=resolve_placeholders(ast.query, cte_name_map)
        )

    elif isinstance(ast, SQLUnion):
        return SQLUnion(
            operands=[resolve_placeholders(op, cte_name_map) for op in ast.operands],
            distinct=ast.distinct
        )

    elif isinstance(ast, SQLCast):
        return SQLCast(
            expression=resolve_placeholders(ast.expression, cte_name_map),
            target_type=ast.target_type,
            try_cast=ast.try_cast,
        )

    elif isinstance(ast, SQLExists):
        return SQLExists(
            subquery=resolve_placeholders(ast.subquery, cte_name_map)
        )

    elif isinstance(ast, SQLInterval):
        return SQLInterval(
            low=resolve_placeholders(ast.low, cte_name_map) if ast.low else None,
            high=resolve_placeholders(ast.high, cte_name_map) if ast.high else None,
            low_closed=ast.low_closed,
            high_closed=ast.high_closed,
        )

    elif isinstance(ast, SQLIntersect):
        return SQLIntersect(
            operands=[resolve_placeholders(op, cte_name_map) for op in ast.operands]
        )

    elif isinstance(ast, SQLExcept):
        return SQLExcept(
            operands=[resolve_placeholders(op, cte_name_map) for op in ast.operands]
        )

    elif isinstance(ast, SQLWindowFunction):
        return SQLWindowFunction(
            function=ast.function,
            function_args=[resolve_placeholders(a, cte_name_map) for a in ast.function_args],
            partition_by=[resolve_placeholders(p, cte_name_map) for p in ast.partition_by],
            order_by=[(resolve_placeholders(expr, cte_name_map), direction) for expr, direction in ast.order_by],
            frame_clause=ast.frame_clause,
        )

    elif isinstance(ast, SQLNamedArg):
        return SQLNamedArg(
            name=ast.name,
            value=resolve_placeholders(ast.value, cte_name_map) if ast.value else None,
        )

    elif isinstance(ast, SQLExtract):
        return SQLExtract(
            extract_field=ast.extract_field,
            source=resolve_placeholders(ast.source, cte_name_map) if ast.source else None,
        )

    elif isinstance(ast, SQLStructFieldAccess):
        return SQLStructFieldAccess(
            expr=resolve_placeholders(ast.expr, cte_name_map),
            field_name=ast.field_name,
        )

    # Handle DeferredTemplateSubstitution - resolve placeholders in stored expressions
    # This type is imported locally to avoid circular imports
    if hasattr(ast, '_resource_expr') and hasattr(ast, '_args'):
        # This is a DeferredTemplateSubstitution - resolve in its expressions
        from ..translator.fluent_functions import DeferredTemplateSubstitution
        return DeferredTemplateSubstitution(
            template=ast._template,
            resource_expr=resolve_placeholders(ast._resource_expr, cte_name_map),
            args=[resolve_placeholders(arg, cte_name_map) for arg in ast._args],
            func_def=ast._func_def,
            substitutor=ast._substitutor,
        )

    # For nodes without placeholders, return as-is
    return ast


def find_all_placeholders(ast: SQLExpression) -> List[RetrievePlaceholder]:
    """
    Find all placeholder instances in an AST.

    Used to verify all placeholders are resolved.

    Args:
        ast: SQL AST to search

    Returns:
        List of all placeholder instances found
    """
    placeholders: List[RetrievePlaceholder] = []

    def walk(node):
        if node is None:
            return
        if isinstance(node, RetrievePlaceholder):
            placeholders.append(node)
        elif isinstance(node, SQLFunctionCall):
            for arg in node.args:
                walk(arg)
        elif isinstance(node, SQLLambda):
            walk(node.body)
        elif isinstance(node, SQLSelect):
            for col in node.columns:
                if isinstance(col, tuple):
                    walk(col[0])
                else:
                    walk(col)
            if node.from_clause:
                walk(node.from_clause)
            if node.joins:
                for join in node.joins:
                    if isinstance(join, SQLJoin):
                        walk(join.table)
                        if join.on_condition:
                            walk(join.on_condition)
            if node.where:
                walk(node.where)
            if node.group_by:
                for g in node.group_by:
                    walk(g)
            if node.having:
                walk(node.having)
        elif isinstance(node, SQLBinaryOp):
            walk(node.left)
            walk(node.right)
        elif isinstance(node, SQLUnaryOp):
            walk(node.operand)
        elif isinstance(node, SQLCase):
            for cond, result in node.when_clauses:
                walk(cond)
                walk(result)
            if node.else_clause:
                walk(node.else_clause)
            if node.operand:
                walk(node.operand)
        elif isinstance(node, SQLList):
            for item in node.items:
                walk(item)
        elif isinstance(node, SQLArray):
            for elem in node.elements:
                walk(elem)
        elif isinstance(node, SQLAlias):
            walk(node.expr)
        elif isinstance(node, SQLSubquery):
            walk(node.query)
        elif isinstance(node, SQLUnion):
            for op in node.operands:
                walk(op)
        elif isinstance(node, SQLCast):
            walk(node.expression)
        elif isinstance(node, SQLExists):
            walk(node.subquery)
        elif isinstance(node, SQLInterval):
            if node.low:
                walk(node.low)
            if node.high:
                walk(node.high)
        elif isinstance(node, SQLIntersect):
            for op in node.operands:
                walk(op)
        elif isinstance(node, SQLExcept):
            for op in node.operands:
                walk(op)
        elif isinstance(node, SQLWindowFunction):
            for a in node.function_args:
                walk(a)
            for p in node.partition_by:
                walk(p)
            for expr, _ in node.order_by:
                walk(expr)
        elif isinstance(node, SQLNamedArg):
            if node.value:
                walk(node.value)
        elif isinstance(node, SQLExtract):
            if node.source:
                walk(node.source)
        elif isinstance(node, SQLStructFieldAccess):
            walk(node.expr)
        # Handle DeferredTemplateSubstitution - walk stored expressions
        elif hasattr(node, '_resource_expr'):
            walk(node._resource_expr)
            if hasattr(node, '_args'):
                for arg in node._args:
                    walk(arg)

    walk(ast)

    # Debug logging for union CTE issue diagnosis
    if placeholders:
        logger.debug(
            f"Found {len(placeholders)} placeholders: "
            f"{[p.key for p in placeholders]}"
        )

    return placeholders


def contains_placeholder(ast: SQLExpression) -> bool:
    """
    Check if an AST contains any placeholders.

    Used to guard to_sql() calls during Phase 1 translation.

    Args:
        ast: SQL AST to check

    Returns:
        True if the AST contains any RetrievePlaceholder instances
    """
    return len(find_all_placeholders(ast)) > 0


__all__ = [
    "UnresolvedPlaceholderError",
    "RetrievePlaceholder",
    "resolve_placeholders",
    "find_all_placeholders",
    "contains_placeholder",
]
