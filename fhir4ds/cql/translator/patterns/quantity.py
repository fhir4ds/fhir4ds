"""
SQL pattern generators for CQL Quantity operations.

This module provides the QuantityTranslator class for translating
CQL Quantity constructs to DuckDB SQL.

Quantity representation uses FHIR Quantity JSON format:
{
    "value": 140.0,
    "unit": "mm[Hg]",
    "system": "http://unitsofmeasure.org",
    "code": "mm[Hg]"
}

Key patterns:
- Quantity construction: JSON object construction
- Comparison: quantity_compare UDF
- Arithmetic: quantity_add/subtract/multiply/divide UDFs
- Value extraction: json_extract
- Unit conversion: quantity_convert UDF

Reference: docs/PLAN-CQL-TO-SQL-TRANSLATOR.md
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from ...translator.types import (
    PRECEDENCE,
    SQLExpression,
    SQLFunctionCall,
    SQLLiteral,
    SQLBinaryOp,
    SQLCase,
    SQLNull,
)

if TYPE_CHECKING:
    from ...translator.context import SQLTranslationContext


# UCUM system URL for units of measure
UCUM_SYSTEM = "http://unitsofmeasure.org"


class QuantityTranslator:
    """
    Translates CQL Quantity expressions to SQL.

    Handles:
    - Quantity construction from literal values
    - Quantity comparison (<, <=, >, >=, =, <>)
    - Quantity arithmetic (+, -, *, /)
    - Value extraction from quantities
    - Unit conversion where possible

    Example SQL patterns:

        Quantity construction:
        {'value': 140.0, 'unit': 'mm[Hg]', 'system': 'http://unitsofmeasure.org', 'code': 'mm[Hg]'}

        Quantity comparison:
        quantity_compare(q1, q2, '<')
        quantity_compare(q1, q2, '<=')

        Quantity arithmetic:
        quantity_add(q1, q2)
        quantity_subtract(q1, q2)
        quantity_multiply(q, scalar)
        quantity_divide(q, scalar)

        Value extraction:
        json_extract(q, '$.value')

        Unit conversion:
        quantity_convert(q, 'g')
    """

    # Supported comparison operators
    COMPARISON_OPERATORS = {"<", "<=", ">", ">=", "=", "<>", "!="}

    # Supported arithmetic operators
    ARITHMETIC_OPERATORS = {"+", "-", "*", "/"}

    def __init__(self, context: SQLTranslationContext):
        """
        Initialize the quantity translator.

        Args:
            context: The translation context for symbol resolution.
        """
        self.context = context

    def construct_quantity(
        self,
        value: float,
        unit: str,
        system: str = UCUM_SYSTEM,
        code: Optional[str] = None,
    ) -> SQLExpression:
        """
        Construct a Quantity literal in SQL.

        Creates a JSON object representation of a FHIR Quantity.

        Args:
            value: The numeric value.
            unit: The unit string (e.g., 'mm[Hg]', 'mg', 'kg').
            system: The unit system URL (default: UCUM).
            code: The unit code (defaults to unit if not specified).

        Returns:
            SQLExpression representing the quantity as a JSON struct.

        Example:
            construct_quantity(140.0, 'mm[Hg]')
            -> {'value': 140.0, 'unit': 'mm[Hg]', 'system': '...', 'code': 'mm[Hg]'}
        """
        if code is None:
            code = unit

        # Build DuckDB struct literal for the quantity
        # DuckDB uses: {'key': value, ...} syntax for structs
        return SQLFunctionCall(
            name="struct_pack",
            args=[
                SQLLiteral(value="value"),
                SQLLiteral(value=value),
                SQLLiteral(value="unit"),
                SQLLiteral(value=unit),
                SQLLiteral(value="system"),
                SQLLiteral(value=system),
                SQLLiteral(value="code"),
                SQLLiteral(value=code),
            ],
        )

    def construct_quantity_from_expressions(
        self,
        value_expr: SQLExpression,
        unit_expr: SQLExpression,
        system_expr: Optional[SQLExpression] = None,
        code_expr: Optional[SQLExpression] = None,
    ) -> SQLExpression:
        """
        Construct a Quantity from SQL expressions.

        Use this when the value/unit are not literals but expressions.

        Args:
            value_expr: SQL expression for the value.
            unit_expr: SQL expression for the unit.
            system_expr: SQL expression for the system (default: UCUM).
            code_expr: SQL expression for the code (default: unit).

        Returns:
            SQLExpression representing the quantity construction.
        """
        if system_expr is None:
            system_expr = SQLLiteral(value=UCUM_SYSTEM)

        if code_expr is None:
            code_expr = unit_expr

        # Use struct_pack for dynamic construction
        return SQLFunctionCall(
            name="struct_pack",
            args=[
                SQLLiteral(value="value"),
                value_expr,
                SQLLiteral(value="unit"),
                unit_expr,
                SQLLiteral(value="system"),
                system_expr,
                SQLLiteral(value="code"),
                code_expr,
            ],
        )

    def translate_comparison(
        self,
        left: SQLExpression,
        right: SQLExpression,
        op: str,
        context: SQLTranslationContext,
    ) -> SQLExpression:
        """
        Translate a Quantity comparison to SQL.

        Uses the quantity_compare UDF for comparison operations.
        If units are incompatible, comparison returns NULL.

        Args:
            left: Left quantity expression.
            right: Right quantity expression.
            op: Comparison operator ('<', '<=', '>', '>=', '=', '<>').
            context: The translation context.

        Returns:
            SQLExpression representing the comparison.

        Example:
            translate_comparison(q1, q2, '<')
            -> quantity_compare(q1, q2, '<')
        """
        # Normalize operator
        if op == "!=":
            op = "<>"

        if op not in self.COMPARISON_OPERATORS:
            raise ValueError(f"Unsupported comparison operator: {op}")

        # Use quantity_compare UDF
        # The UDF handles unit conversion and returns NULL for incompatible units
        return SQLFunctionCall(
            name="quantity_compare",
            args=[left, right, SQLLiteral(value=op)],
        )

    def translate_arithmetic(
        self,
        left: SQLExpression,
        right: SQLExpression,
        op: str,
        context: SQLTranslationContext,
    ) -> SQLExpression:
        """
        Translate Quantity arithmetic to SQL.

        For addition/subtraction: both operands must be quantities.
        For multiplication/division: one operand is quantity, other is scalar.

        Args:
            left: Left operand (quantity or scalar).
            right: Right operand (quantity or scalar).
            op: Arithmetic operator ('+', '-', '*', '/').
            context: The translation context.

        Returns:
            SQLExpression representing the arithmetic operation.

        Example:
            translate_arithmetic(q1, q2, '+')
            -> quantity_add(q1, q2)

            translate_arithmetic(q, 2.0, '*')
            -> quantity_multiply(q, 2.0)
        """
        if op not in self.ARITHMETIC_OPERATORS:
            raise ValueError(f"Unsupported arithmetic operator: {op}")

        # Map operators to UDF names
        udf_map = {
            "+": "quantity_add",
            "-": "quantity_subtract",
            "*": "quantity_multiply",
            "/": "quantity_divide",
        }

        udf_name = udf_map[op]

        return SQLFunctionCall(
            name=udf_name,
            args=[left, right],
        )

    def translate_value_extraction(
        self,
        quantity: SQLExpression,
    ) -> SQLExpression:
        """
        Extract the value from a Quantity.

        Args:
            quantity: The quantity expression.

        Returns:
            SQLExpression that extracts the value.

        Example:
            translate_value_extraction(q)
            -> q.value  (or json_extract(q, '$.value') for JSON)
        """
        # For DuckDB structs, use dot notation
        # If quantity is a struct, we can use struct_extract or dot access
        return SQLFunctionCall(
            name="struct_extract",
            args=[quantity, SQLLiteral(value="value")],
        )

    def translate_unit_extraction(
        self,
        quantity: SQLExpression,
    ) -> SQLExpression:
        """
        Extract the unit from a Quantity.

        Args:
            quantity: The quantity expression.

        Returns:
            SQLExpression that extracts the unit.
        """
        return SQLFunctionCall(
            name="struct_extract",
            args=[quantity, SQLLiteral(value="unit")],
        )

    def translate_code_extraction(
        self,
        quantity: SQLExpression,
    ) -> SQLExpression:
        """
        Extract the code from a Quantity.

        Args:
            quantity: The quantity expression.

        Returns:
            SQLExpression that extracts the code.
        """
        return SQLFunctionCall(
            name="struct_extract",
            args=[quantity, SQLLiteral(value="code")],
        )

    def translate_unit_conversion(
        self,
        quantity: SQLExpression,
        target_unit: str,
    ) -> SQLExpression:
        """
        Convert a Quantity to a different unit.

        Uses the quantity_convert UDF for unit conversion.
        Returns NULL if conversion is not possible.

        Args:
            quantity: The quantity expression.
            target_unit: The target unit to convert to.

        Returns:
            SQLExpression representing the converted quantity.

        Example:
            translate_unit_conversion(q, 'g')
            -> quantity_convert(q, 'g')
        """
        return SQLFunctionCall(
            name="quantity_convert",
            args=[quantity, SQLLiteral(value=target_unit)],
        )

    def translate_quantity_to_decimal(
        self,
        quantity: SQLExpression,
    ) -> SQLExpression:
        """
        Convert a Quantity to a decimal by extracting its value.

        This is used when a quantity needs to be used in a numeric context.

        Args:
            quantity: The quantity expression.

        Returns:
            SQLExpression that extracts and converts the value to decimal.
        """
        # Extract value and cast to appropriate numeric type
        value_expr = self.translate_value_extraction(quantity)
        return SQLFunctionCall(
            name="CAST",
            args=[value_expr, SQLLiteral(value="DOUBLE")],
        )

    def translate_quantity_equals(
        self,
        left: SQLExpression,
        right: SQLExpression,
        context: SQLTranslationContext,
    ) -> SQLExpression:
        """
        Translate Quantity equality comparison.

        For quantities, equality considers both value and unit.
        Two quantities are equal if they have the same value after
        conversion to a common unit.

        Args:
            left: Left quantity expression.
            right: Right quantity expression.
            context: The translation context.

        Returns:
            SQLExpression representing the equality check.
        """
        return self.translate_comparison(left, right, "=", context)

    def translate_quantity_not_equals(
        self,
        left: SQLExpression,
        right: SQLExpression,
        context: SQLTranslationContext,
    ) -> SQLExpression:
        """
        Translate Quantity inequality comparison.

        Args:
            left: Left quantity expression.
            right: Right quantity expression.
            context: The translation context.

        Returns:
            SQLExpression representing the inequality check.
        """
        return self.translate_comparison(left, right, "<>", context)

    def translate_between(
        self,
        quantity: SQLExpression,
        low: SQLExpression,
        high: SQLExpression,
        context: SQLTranslationContext,
    ) -> SQLExpression:
        """
        Translate a Quantity between expression.

        Checks if quantity is >= low and <= high.

        Args:
            quantity: The quantity to check.
            low: Low bound quantity.
            high: High bound quantity.
            context: The translation context.

        Returns:
            SQLExpression representing the between check.
        """
        # quantity >= low AND quantity <= high
        low_check = self.translate_comparison(quantity, low, ">=", context)
        high_check = self.translate_comparison(quantity, high, "<=", context)

        return SQLBinaryOp(
            operator="AND",
            left=low_check,
            right=high_check,
            precedence=PRECEDENCE["AND"],
        )

    def translate_quantity_in_units(
        self,
        quantity: SQLExpression,
        units: list[str],
        context: SQLTranslationContext,
    ) -> SQLExpression:
        """
        Check if a quantity's unit is in a list of units.

        Args:
            quantity: The quantity expression.
            units: List of unit strings to check.
            context: The translation context.

        Returns:
            SQLExpression representing the unit membership check.
        """
        unit_expr = self.translate_unit_extraction(quantity)

        # Build: unit IN ('unit1', 'unit2', ...)
        unit_literals = [SQLLiteral(value=u) for u in units]

        # Use array_contains for DuckDB
        return SQLFunctionCall(
            name="list_contains",
            args=[
                SQLFunctionCall(
                    name="list_value",
                    args=unit_literals,
                ),
                unit_expr,
            ],
        )

    def translate_scale_quantity(
        self,
        quantity: SQLExpression,
        scalar: SQLExpression,
    ) -> SQLExpression:
        """
        Scale a quantity by a scalar value.

        This is a convenience method for quantity * scalar.

        Args:
            quantity: The quantity expression.
            scalar: The scalar value expression.

        Returns:
            SQLExpression representing the scaled quantity.
        """
        return SQLFunctionCall(
            name="quantity_multiply",
            args=[quantity, scalar],
        )

    def translate_divide_by_scalar(
        self,
        quantity: SQLExpression,
        scalar: SQLExpression,
    ) -> SQLExpression:
        """
        Divide a quantity by a scalar value.

        Args:
            quantity: The quantity expression.
            scalar: The scalar value expression.

        Returns:
            SQLExpression representing the divided quantity.
        """
        return SQLFunctionCall(
            name="quantity_divide",
            args=[quantity, scalar],
        )

    def translate_negate(
        self,
        quantity: SQLExpression,
    ) -> SQLExpression:
        """
        Negate a quantity (multiply by -1).

        Args:
            quantity: The quantity expression.

        Returns:
            SQLExpression representing the negated quantity.
        """
        return self.translate_scale_quantity(quantity, SQLLiteral(value=-1))

    def translate_abs(
        self,
        quantity: SQLExpression,
    ) -> SQLExpression:
        """
        Get the absolute value of a quantity.

        Args:
            quantity: The quantity expression.

        Returns:
            SQLExpression representing the absolute quantity.
        """
        # Extract value, apply abs, reconstruct quantity
        value_expr = self.translate_value_extraction(quantity)
        abs_value = SQLFunctionCall(name="abs", args=[value_expr])

        # Reconstruct quantity with absolute value
        unit_expr = self.translate_unit_extraction(quantity)
        code_expr = self.translate_code_extraction(quantity)

        return self.construct_quantity_from_expressions(
            value_expr=abs_value,
            unit_expr=unit_expr,
            code_expr=code_expr,
        )

    def translate_round(
        self,
        quantity: SQLExpression,
        precision: Optional[int] = None,
    ) -> SQLExpression:
        """
        Round a quantity's value.

        Args:
            quantity: The quantity expression.
            precision: Number of decimal places (default 0).

        Returns:
            SQLExpression representing the rounded quantity.
        """
        value_expr = self.translate_value_extraction(quantity)

        if precision is not None:
            rounded_value = SQLFunctionCall(
                name="round",
                args=[value_expr, SQLLiteral(value=precision)],
            )
        else:
            rounded_value = SQLFunctionCall(name="round", args=[value_expr])

        unit_expr = self.translate_unit_extraction(quantity)
        code_expr = self.translate_code_extraction(quantity)

        return self.construct_quantity_from_expressions(
            value_expr=rounded_value,
            unit_expr=unit_expr,
            code_expr=code_expr,
        )

    def translate_floor(
        self,
        quantity: SQLExpression,
    ) -> SQLExpression:
        """
        Get the floor of a quantity's value.

        Args:
            quantity: The quantity expression.

        Returns:
            SQLExpression representing the quantity with floored value.
        """
        value_expr = self.translate_value_extraction(quantity)
        floor_value = SQLFunctionCall(name="floor", args=[value_expr])

        unit_expr = self.translate_unit_extraction(quantity)
        code_expr = self.translate_code_extraction(quantity)

        return self.construct_quantity_from_expressions(
            value_expr=floor_value,
            unit_expr=unit_expr,
            code_expr=code_expr,
        )

    def translate_ceiling(
        self,
        quantity: SQLExpression,
    ) -> SQLExpression:
        """
        Get the ceiling of a quantity's value.

        Args:
            quantity: The quantity expression.

        Returns:
            SQLExpression representing the quantity with ceilinged value.
        """
        value_expr = self.translate_value_extraction(quantity)
        ceil_value = SQLFunctionCall(name="ceiling", args=[value_expr])

        unit_expr = self.translate_unit_extraction(quantity)
        code_expr = self.translate_code_extraction(quantity)

        return self.construct_quantity_from_expressions(
            value_expr=ceil_value,
            unit_expr=unit_expr,
            code_expr=code_expr,
        )


__all__ = [
    "QuantityTranslator",
    "UCUM_SYSTEM",
]
