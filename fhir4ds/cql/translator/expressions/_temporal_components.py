"""Date component extraction and constructor translations for CQL to SQL.

Handles DateTime(), Date(), Time() constructors and date component extraction
(year from X, month from X, etc.).
"""
from __future__ import annotations

from typing import List

from ...parser.ast_nodes import DateComponent
from ...translator.types import (
    SQLBinaryOp,
    SQLCast,
    SQLExpression,
    SQLFunctionCall,
    SQLLiteral,
    SQLNull,
    SQLRaw,
)


class DateComponentMixin:
    """Date component extraction and constructor translations for CQL to SQL.

    Intended to be mixed into ExpressionTranslator.  All methods assume
    ``self`` has ``translate``, ``context``, and the other helpers available
    on ExpressionTranslator.
    """

    def _translate_datetime_constructor(self, args: List[SQLExpression]) -> SQLExpression:
        """Translate a DateTime constructor.

        CQL §22.5: DateTime(year, month?, day?, hour?, minute?, second?, millisecond?, timezoneOffset?)
        All components are Integer.  When a single non-literal arg is supplied it
        is typically a date/datetime expression routed here via ToDateTime — cast
        to TIMESTAMP instead of wrapping in make_timestamp which expects integers.
        """
        if not args:
            return SQLNull()

        # Validate year bounds (1-9999) for literal year values
        year_arg = args[0]
        if isinstance(year_arg, SQLLiteral) and isinstance(year_arg.value, int):
            if year_arg.value < 1 or year_arg.value > 9999:
                raise ValueError(
                    f"The year {year_arg.value} falls outside the accepted "
                    f"bounds of 0001-9999"
                )

        if len(args) == 1:
            year = args[0]
            if isinstance(year, SQLLiteral) and isinstance(year.value, int):
                return SQLFunctionCall(
                    name="make_timestamp",
                    args=[year, SQLLiteral(value=1), SQLLiteral(value=1),
                          SQLLiteral(value=0), SQLLiteral(value=0), SQLLiteral(value=0)],
                )
            # Non-integer single arg: pass through as-is (already a date/datetime/string)
            return year

        # Pad missing components with defaults
        year = args[0]
        month = args[1] if len(args) > 1 else SQLLiteral(value=1)
        day = args[2] if len(args) > 2 else SQLLiteral(value=1)
        hour = args[3] if len(args) > 3 else SQLLiteral(value=0)
        minute = args[4] if len(args) > 4 else SQLLiteral(value=0)
        second = args[5] if len(args) > 5 else SQLLiteral(value=0)

        # CQL §22.5: Handle optional millisecond component (7th arg).
        # DuckDB make_timestamp accepts fractional seconds, so combine
        # second + millisecond/1000.0 into the seconds parameter.
        if len(args) > 6:
            millisecond = args[6]
            second = SQLBinaryOp(
                operator="+",
                left=SQLCast(expression=second, target_type="DOUBLE"),
                right=SQLBinaryOp(
                    operator="/",
                    left=SQLCast(expression=millisecond, target_type="DOUBLE"),
                    right=SQLLiteral(value=1000.0),
                ),
            )

        # CQL §22.5: Handle optional 8th arg — timezoneOffset (decimal hours).
        # Append the offset string so downstream UDFs can parse it timezone-aware.
        ts_expr = SQLFunctionCall(
            name="make_timestamp",
            args=[year, month, day, hour, minute, second],
        )
        if len(args) > 7:
            tz_offset = args[7]
            # Build: CAST(make_timestamp(...) AS VARCHAR) || printf('%+03.0f:00', CAST(offset AS DOUBLE))
            return SQLRaw(
                f"(CAST({ts_expr.to_sql()} AS VARCHAR) || printf('%+03.0f:00', CAST({tz_offset.to_sql()} AS DOUBLE)))"
            )

        return ts_expr

    def _translate_date_constructor(self, args: List[SQLExpression]) -> SQLExpression:
        """Translate a Date constructor.

        CQL §22.26: Date(year, month?, day?) — all Integer components.
        When a single non-literal arg is supplied it is typically a
        date/datetime expression routed here via ToDate — cast to DATE
        instead of wrapping in make_date which expects integers.
        """
        if not args:
            return SQLNull()

        if len(args) == 1:
            year = args[0]
            if isinstance(year, SQLLiteral) and isinstance(year.value, int):
                return SQLFunctionCall(
                    name="make_date",
                    args=[year, SQLLiteral(value=1), SQLLiteral(value=1)],
                )
            # Non-integer single arg: pass through as-is (already a date/datetime/string)
            return year

        year = args[0]
        month = args[1] if len(args) > 1 else SQLLiteral(value=1)
        day = args[2] if len(args) > 2 else SQLLiteral(value=1)

        return SQLFunctionCall(
            name="make_date",
            args=[year, month, day],
        )

    def _translate_time_constructor(self, args: List[SQLExpression]) -> SQLExpression:
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
