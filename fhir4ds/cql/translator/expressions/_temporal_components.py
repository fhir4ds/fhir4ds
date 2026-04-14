"""Date component extraction and constructor translations for CQL to SQL.

Handles DateTime(), Date(), Time() constructors and date component extraction
(year from X, month from X, etc.).
"""
from __future__ import annotations

from typing import List

from ...parser.ast_nodes import DateComponent
from ...translator.types import (
    SQLCast,
    SQLExpression,
    SQLFunctionCall,
    SQLLiteral,
    SQLNull,
)


class DateComponentMixin:
    """Date component extraction and constructor translations for CQL to SQL.

    Intended to be mixed into ExpressionTranslator.  All methods assume
    ``self`` has ``translate``, ``context``, and the other helpers available
    on ExpressionTranslator.
    """

    def _translate_datetime_constructor(self, args: List[SQLExpression]) -> SQLExpression:
        """Translate a DateTime constructor."""
        if not args:
            return SQLNull()

        # Build a timestamp from components
        # DateTime(year, month, day, hour, minute, second, millisecond)
        if len(args) >= 3:
            year = args[0]
            month = args[1] if len(args) > 1 else SQLLiteral(value=1)
            day = args[2] if len(args) > 2 else SQLLiteral(value=1)
            hour = args[3] if len(args) > 3 else SQLLiteral(value=0)
            minute = args[4] if len(args) > 4 else SQLLiteral(value=0)
            second = args[5] if len(args) > 5 else SQLLiteral(value=0)

            # Use make_timestamp function
            return SQLFunctionCall(
                name="make_timestamp",
                args=[year, month, day, hour, minute, second],
            )

        return args[0] if args else SQLNull()

    def _translate_date_constructor(self, args: List[SQLExpression]) -> SQLExpression:
        """Translate a Date constructor."""
        if not args:
            return SQLNull()

        if len(args) >= 3:
            year = args[0]
            month = args[1]
            day = args[2]

            return SQLFunctionCall(
                name="make_date",
                args=[year, month, day],
            )

        # Single argument: either Date(year_only) or an edge case.
        # Return as-is; "date from X" is handled by _translate_date_component.
        return args[0] if args else SQLNull()
        """Translate a Time constructor."""
        if not args:
            return SQLNull()

        if len(args) >= 2:
            hour = args[0]
            minute = args[1]
            second = args[2] if len(args) > 2 else SQLLiteral(value=0)

            return SQLFunctionCall(
                name="make_time",
                args=[hour, minute, second],
            )

        return args[0] if args else SQLNull()

    def _translate_date_component(self, node: DateComponent, boolean_context: bool = False) -> SQLExpression:
        """Handle: year from @2024-01-15, date from dateTime, timezoneoffset from dateTime"""
        component_map = {
            'year': 'Year',
            'month': 'Month',
            'day': 'Day',
            'hour': 'Hour',
            'minute': 'Minute',
            'second': 'Second',
            'millisecond': 'Millisecond',
            'timezoneoffset': None,  # Handled specially below
        }
        operand = self.translate(node.operand, boolean_context=False)
        component_lower = node.component.lower()

        # Handle timezoneoffset specially - return 0 as placeholder
        # NOTE: DuckDB doesn't expose timezone offsets from FHIR dateTime values.
        # A custom UDF would be needed for proper implementation.
        if component_lower == 'timezoneoffset':
            # Return 0 as placeholder (timezone handling varies by implementation)
            return SQLLiteral(value=0)

        # Handle 'date from X' - extract date portion from datetime
        if component_lower == 'date':
            return SQLCast(expression=operand, target_type="DATE")

        func_name = component_map.get(component_lower, 'Year')
        return SQLFunctionCall(name=func_name, args=[operand])
