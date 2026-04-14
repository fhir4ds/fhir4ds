"""
Operator translation for CQL to SQL.

This module provides the OperatorTranslator class that translates
CQL operators to SQL with proper null handling and CQL semantics.
"""

from __future__ import annotations

from typing import Optional, TYPE_CHECKING

from ..translator.types import (
    PRECEDENCE,
    SQLAuditStruct,
    SQLBinaryOp,
    SQLCase,
    SQLCast,
    SQLExpression,
    SQLFunctionCall,
    SQLLiteral,
    SQLNull,
    SQLUnaryOp,
)

if TYPE_CHECKING:
    from ..translator.context import SQLTranslationContext

_AUDIT_MACRO_NAMES = frozenset({"audit_and", "audit_or", "audit_or_all", "audit_not", "audit_leaf"})


def _ensure_audit_struct(expr: SQLExpression) -> SQLExpression:
    """Wrap a plain boolean expression in audit_leaf() if not already an audit struct."""
    if isinstance(expr, SQLAuditStruct):
        return expr
    if isinstance(expr, SQLFunctionCall) and expr.name in _AUDIT_MACRO_NAMES:
        return expr
    return SQLFunctionCall(name="audit_leaf", args=[expr])


# CQL type to SQL type mapping for casts
CQL_TYPE_TO_SQL = {
    "String": "VARCHAR",
    "Integer": "INTEGER",
    "Decimal": "DOUBLE",
    "Boolean": "BOOLEAN",
    "Date": "DATE",
    "DateTime": "TIMESTAMP",
    "Time": "TIME",
    "Long": "BIGINT",
    "Real": "FLOAT",
    "Quantity": "VARCHAR",  # Stored as JSON
    "Concept": "VARCHAR",  # Stored as JSON
    "Code": "VARCHAR",
    "Any": "VARCHAR",
}


class OperatorTranslator:
    """
    Translates CQL operators to SQL expressions.

    Handles translation of:
    - Arithmetic operators: +, -, *, /, div, mod, ^ (power)
    - Comparison operators: =, <>, <, >, <=, >=, ~ (equivalence), !~ (non-equivalence)
    - Logical operators: and, or, not, xor, implies
    - Null handling: is null, is not null
    - Type operators: as (cast), is (type check)

    Special CQL comparison semantics:
    - String comparison is case-insensitive by default
    - ~ (equivalence) handles nulls specially - returns true if both null
    - !~ is non-equivalence
    """

    def __init__(self, context: SQLTranslationContext):
        """
        Initialize the operator translator.

        Args:
            context: The translation context for symbol resolution.
        """
        self.context = context

    def _infer_operand_type(self, expr: SQLExpression) -> Optional[str]:
        """Infer CQL type from SQL expression context."""
        if isinstance(expr, SQLLiteral):
            val = expr.value
            if isinstance(val, str) and val.startswith("'"):
                return "String"
            if isinstance(val, str) and val.replace('.', '', 1).lstrip('-').isdigit():
                return "Decimal" if '.' in val else "Integer"
        if isinstance(expr, SQLCast):
            type_map = {v: k for k, v in CQL_TYPE_TO_SQL.items()}
            return type_map.get(expr.target_type)
        if isinstance(expr, SQLFunctionCall):
            name_upper = expr.name.upper()
            if name_upper in ("FHIRPATH_TEXT", "LOWER", "UPPER", "CONCAT"):
                return "String"
            if name_upper in ("FHIRPATH_NUMBER", "COUNT", "SUM", "AVG"):
                return "Decimal"
            if name_upper in ("FHIRPATH_DATE", "DATE"):
                return "Date"
        return None

    def translate_binary_op(
        self,
        op: str,
        left: SQLExpression,
        right: SQLExpression,
        context: SQLTranslationContext,
    ) -> SQLExpression:
        """
        Translate a CQL binary operator to SQL.

        Args:
            op: The CQL operator string.
            left: The left operand SQL expression.
            right: The right operand SQL expression.
            context: The translation context.

        Returns:
            The SQL expression for the operation.
        """
        op_lower = op.lower().strip()

        # Arithmetic operators
        if op_lower == "+":
            left_type = self._infer_operand_type(left)
            right_type = self._infer_operand_type(right)

            # String concatenation
            if left_type == "String" or right_type == "String":
                return SQLBinaryOp(operator="||", left=left, right=right)

            # Default: numeric addition (also safe fallback for unknown types)
            return SQLBinaryOp(operator="+", left=left, right=right)

        if op_lower == "-":
            return SQLBinaryOp(operator="-", left=left, right=right)

        if op_lower == "*":
            return SQLBinaryOp(operator="*", left=left, right=right)

        if op_lower == "/":
            return SQLBinaryOp(operator="/", left=left, right=right)

        if op_lower == "div":
            # Integer division: FLOOR(x / y)
            div_expr = SQLBinaryOp(operator="/", left=left, right=right)
            return SQLFunctionCall(name="FLOOR", args=[div_expr])

        if op_lower == "mod":
            # Modulo: MOD(x, y) or x % y
            return SQLFunctionCall(name="MOD", args=[left, right])

        if op_lower == "^":
            # Power: POW(x, y)
            return SQLFunctionCall(name="POW", args=[left, right])

        # Comparison operators
        if op_lower == "=":
            return self._translate_equality(left, right)

        if op_lower in ("<>", "!="):
            return self._translate_inequality(left, right)

        if op_lower == "<":
            return SQLBinaryOp(operator="<", left=left, right=right)

        if op_lower == ">":
            return SQLBinaryOp(operator=">", left=left, right=right)

        if op_lower == "<=":
            return SQLBinaryOp(operator="<=", left=left, right=right)

        if op_lower == ">=":
            return SQLBinaryOp(operator=">=", left=left, right=right)

        # Equivalence operators
        if op_lower == "~":
            return self.translate_equivalence(left, right)

        if op_lower == "!~":
            return self.translate_non_equivalence(left, right)

        # Logical operators
        if op_lower == "and":
            if context.audit_mode and context.audit_expressions:
                return SQLFunctionCall(name="audit_and", args=[_ensure_audit_struct(left), _ensure_audit_struct(right)])
            return SQLBinaryOp(operator="AND", left=left, right=right)

        if op_lower == "or":
            if context.audit_mode and context.audit_expressions:
                macro = "audit_or_all" if context.audit_or_strategy == "all" else "audit_or"
                return SQLFunctionCall(name=macro, args=[_ensure_audit_struct(left), _ensure_audit_struct(right)])
            return SQLBinaryOp(operator="OR", left=left, right=right)

        if op_lower == "xor":
            # XOR: (x OR y) AND NOT (x AND y)
            or_expr = SQLBinaryOp(operator="OR", left=left, right=right)
            and_expr = SQLBinaryOp(operator="AND", left=left, right=right)
            not_and = SQLUnaryOp(operator="NOT", operand=and_expr, prefix=True)
            return SQLBinaryOp(operator="AND", left=or_expr, right=not_and)

        if op_lower == "implies":
            # A implies B = NOT A OR B
            not_left = SQLUnaryOp(operator="NOT", operand=left, prefix=True)
            return SQLBinaryOp(operator="OR", left=not_left, right=right)

        # String concatenation
        if op_lower == "&":
            return SQLBinaryOp(operator="||", left=left, right=right)

        # Default: pass through as binary op
        return SQLBinaryOp(operator=op, left=left, right=right)

    def translate_unary_op(
        self,
        op: str,
        operand: SQLExpression,
        context: SQLTranslationContext,
    ) -> SQLExpression:
        """
        Translate a CQL unary operator to SQL.

        Args:
            op: The CQL operator string.
            operand: The operand SQL expression.
            context: The translation context.

        Returns:
            The SQL expression for the operation.
        """
        op_lower = op.lower().strip()

        if op_lower == "not":
            if context.audit_mode and context.audit_expressions:
                return SQLFunctionCall(name="audit_not", args=[_ensure_audit_struct(operand)])
            return SQLUnaryOp(operator="NOT", operand=operand, prefix=True)

        if op_lower == "is null":
            return SQLUnaryOp(operator="IS NULL", operand=operand, prefix=False)

        if op_lower == "is not null":
            return SQLUnaryOp(operator="IS NOT NULL", operand=operand, prefix=False)

        if op_lower == "-":
            return SQLUnaryOp(operator="-", operand=operand, prefix=True)

        if op_lower == "+":
            # Unary plus is a no-op
            return operand

        if op_lower == "exists":
            # exists(x) = x IS NOT NULL
            return SQLUnaryOp(operator="IS NOT NULL", operand=operand, prefix=False)

        # Default: pass through
        return SQLUnaryOp(operator=op, operand=operand, prefix=True)

    def translate_equivalence(
        self,
        left: SQLExpression,
        right: SQLExpression,
    ) -> SQLExpression:
        """
        Translate CQL equivalence operator (~) to SQL.

        CQL equivalence semantics:
        - null ~ null = true
        - null ~ value = false
        - value ~ null = false
        - value ~ value = value = value

        SQL pattern:
        CASE WHEN x IS NULL AND y IS NULL THEN TRUE
             WHEN x IS NULL OR y IS NULL THEN FALSE
             ELSE x = y END

        Args:
            left: The left operand SQL expression.
            right: The right operand SQL expression.

        Returns:
            The SQL expression for equivalence comparison.
        """
        # Both null check
        left_is_null = SQLUnaryOp(operator="IS NULL", operand=left, prefix=False)
        right_is_null = SQLUnaryOp(operator="IS NULL", operand=right, prefix=False)
        both_null = SQLBinaryOp(operator="AND", left=left_is_null, right=right_is_null)

        # Either null check
        either_null = SQLBinaryOp(operator="OR", left=left_is_null, right=right_is_null)

        # Standard equality
        equality = SQLBinaryOp(operator="=", left=left, right=right)

        return SQLCase(
            when_clauses=[
                (both_null, SQLLiteral(value=True)),
                (either_null, SQLLiteral(value=False)),
            ],
            else_clause=equality,
        )

    def translate_non_equivalence(
        self,
        left: SQLExpression,
        right: SQLExpression,
    ) -> SQLExpression:
        """
        Translate CQL non-equivalence operator (!~) to SQL.

        Non-equivalence is the negation of equivalence.
        !~ is equivalent to NOT (x ~ y)

        Args:
            left: The left operand SQL expression.
            right: The right operand SQL expression.

        Returns:
            The SQL expression for non-equivalence comparison.
        """
        equiv = self.translate_equivalence(left, right)
        return SQLUnaryOp(operator="NOT", operand=equiv, prefix=True)

    def translate_type_cast(
        self,
        expr: SQLExpression,
        target_type: str,
    ) -> SQLExpression:
        """
        Translate a CQL type cast (as) to SQL.

        Args:
            expr: The expression to cast.
            target_type: The target CQL type name (e.g., "String", "Integer").

        Returns:
            The SQL CAST expression.
        """
        # Map CQL type to SQL type
        sql_type = CQL_TYPE_TO_SQL.get(target_type)

        if sql_type is None:
            # Unknown type - default to VARCHAR
            sql_type = "VARCHAR"

        # Handle special cases
        if target_type == "Boolean":
            # Boolean cast needs special handling for string inputs
            return SQLFunctionCall(
                name="CASE",
                args=[
                    SQLFunctionCall(name="LOWER", args=[SQLCast(expression=expr, target_type="VARCHAR")]),
                    SQLLiteral(value="'true'"),
                    SQLLiteral(value=True),
                    SQLLiteral(value="'false'"),
                    SQLLiteral(value=False),
                    SQLLiteral(value="'1'"),
                    SQLLiteral(value=True),
                    SQLLiteral(value="'0'"),
                    SQLLiteral(value=False),
                    SQLCast(expression=expr, target_type="BOOLEAN"),
                ],
            )

        if target_type == "DateTime":
            # DateTime cast from string
            return SQLFunctionCall(
                name="CAST",
                args=[expr],
            )

        return SQLCast(expression=expr, target_type=sql_type)

    def translate_type_check(
        self,
        expr: SQLExpression,
        type_name: str,
    ) -> SQLExpression:
        """
        Translate a CQL type check (is) to SQL.

        CQL type check: x is Quantity
        SQL pattern: x IS NOT NULL AND json_extract_string(x, '__type__') = 'Quantity'

        For FHIR resources stored as JSON, we check the __type__ field.

        Args:
            expr: The expression to check.
            type_name: The CQL type name to check against.

        Returns:
            The SQL expression for the type check.
        """

        # For primitive types, check if the value can be cast
        primitive_types = {"String", "Integer", "Decimal", "Boolean", "Date", "DateTime", "Time", "Long", "Real"}

        if type_name in primitive_types:
            # For primitives, just check not null
            return SQLUnaryOp(operator="IS NOT NULL", operand=expr, prefix=False)

        # For complex types stored as JSON, check the __type__ field
        # Using json_extract_string to get the type marker
        not_null = SQLUnaryOp(operator="IS NOT NULL", operand=expr, prefix=False)

        type_check = SQLFunctionCall(
            name="json_extract_string",
            args=[expr, SQLLiteral(value="__type__")],
        )

        type_match = SQLBinaryOp(
            operator="=",
            left=type_check,
            right=SQLLiteral(value=type_name),
        )

        return SQLBinaryOp(operator="AND", left=not_null, right=type_match)

    def _translate_equality(
        self,
        left: SQLExpression,
        right: SQLExpression,
    ) -> SQLExpression:
        """
        Translate CQL equality operator (=) to SQL.

        CQL equality with null handling:
        - null = null = null (not false)
        - null = value = null (not false)
        - value = value = value = value

        For most contexts, we use standard SQL equality.
        The caller can wrap with COALESCE if needed.

        Args:
            left: The left operand SQL expression.
            right: The right operand SQL expression.

        Returns:
            The SQL expression for equality comparison.
        """
        return SQLBinaryOp(operator="=", left=left, right=right)

    def _translate_inequality(
        self,
        left: SQLExpression,
        right: SQLExpression,
    ) -> SQLExpression:
        """
        Translate CQL inequality operator (<>) to SQL.

        Args:
            left: The left operand SQL expression.
            right: The right operand SQL expression.

        Returns:
            The SQL expression for inequality comparison.
        """
        return SQLBinaryOp(operator="<>", left=left, right=right)

    def translate_case_insensitive_comparison(
        self,
        left: SQLExpression,
        right: SQLExpression,
    ) -> SQLExpression:
        """
        Translate a case-insensitive string comparison.

        CQL string comparisons are case-insensitive by default.

        SQL pattern: LOWER(x) = LOWER(y)

        Args:
            left: The left operand SQL expression.
            right: The right operand SQL expression.

        Returns:
            The SQL expression for case-insensitive comparison.
        """
        left_lower = SQLFunctionCall(name="LOWER", args=[left])
        right_lower = SQLFunctionCall(name="LOWER", args=[right])
        return SQLBinaryOp(operator="=", left=left_lower, right=right_lower)

    def translate_safe_division(
        self,
        left: SQLExpression,
        right: SQLExpression,
    ) -> SQLExpression:
        """
        Translate safe division that handles divide-by-zero.

        SQL pattern:
        CASE WHEN y = 0 THEN NULL ELSE x / y END

        Args:
            left: The dividend SQL expression.
            right: The divisor SQL expression.

        Returns:
            The SQL expression for safe division.
        """
        zero_check = SQLBinaryOp(
            operator="=",
            left=right,
            right=SQLLiteral(value=0),
        )
        division = SQLBinaryOp(operator="/", left=left, right=right)

        return SQLCase(
            when_clauses=[(zero_check, SQLNull())],
            else_clause=division,
        )

    def translate_coalesced_comparison(
        self,
        op: str,
        left: SQLExpression,
        right: SQLExpression,
        default_left: SQLExpression = None,
        default_right: SQLExpression = None,
    ) -> SQLExpression:
        """
        Translate a comparison with COALESCE for null handling.

        Useful when you want null to compare as a specific default value.

        SQL pattern: COALESCE(x, default) op COALESCE(y, default)

        Args:
            op: The comparison operator.
            left: The left operand SQL expression.
            right: The right operand SQL expression.
            default_left: Default value for left if null.
            default_right: Default value for right if null.

        Returns:
            The SQL expression for coalesced comparison.
        """
        if default_left is None:
            default_left = SQLLiteral(value=False)
        if default_right is None:
            default_right = SQLLiteral(value=False)

        left_coalesced = SQLFunctionCall(name="COALESCE", args=[left, default_left])
        right_coalesced = SQLFunctionCall(name="COALESCE", args=[right, default_right])

        return SQLBinaryOp(operator=op, left=left_coalesced, right=right_coalesced)


__all__ = [
    "OperatorTranslator",
    "CQL_TYPE_TO_SQL",
]
