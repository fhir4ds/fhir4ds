"""Date component extraction and constructor translations for CQL to SQL.

Handles DateTime(), Date(), Time() constructors and date component extraction
(year from X, month from X, etc.).
"""
from __future__ import annotations

from typing import List

from ...parser.ast_nodes import DateComponent
from ...translator.types import (
    SQLBinaryOp,
    SQLCase,
    SQLCast,
    SQLExpression,
    SQLFunctionCall,
    SQLLiteral,
    SQLNull,
    SQLRaw,
    SQLUnaryOp,
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
        All components are Integer.

        Emits VARCHAR ISO 8601 strings preserving precision based on the number
        of provided components.  When all args are integer literals, we can
        build the string at compile time.  Otherwise, we use printf() to
        build it at runtime.
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

        # Check if all provided args are integer literals — if so, emit a
        # compile-time ISO 8601 string literal preserving precision.
        all_literal = all(isinstance(a, SQLLiteral) and isinstance(a.value, (int, float)) for a in args[:min(len(args), 7)])
        if all_literal and len(args) <= 8:
            vals = [int(a.value) for a in args[:min(len(args), 7)]]
            n = len(vals)
            if n == 1:
                iso = f"{vals[0]:04d}"
            elif n == 2:
                iso = f"{vals[0]:04d}-{vals[1]:02d}"
            elif n == 3:
                iso = f"{vals[0]:04d}-{vals[1]:02d}-{vals[2]:02d}"
            elif n == 4:
                iso = f"{vals[0]:04d}-{vals[1]:02d}-{vals[2]:02d}T{vals[3]:02d}"
            elif n == 5:
                iso = f"{vals[0]:04d}-{vals[1]:02d}-{vals[2]:02d}T{vals[3]:02d}:{vals[4]:02d}"
            elif n == 6:
                iso = f"{vals[0]:04d}-{vals[1]:02d}-{vals[2]:02d}T{vals[3]:02d}:{vals[4]:02d}:{vals[5]:02d}"
            else:
                iso = f"{vals[0]:04d}-{vals[1]:02d}-{vals[2]:02d}T{vals[3]:02d}:{vals[4]:02d}:{vals[5]:02d}.{vals[6]:03d}"

            # Handle timezone offset (8th arg) — may be SQLLiteral(+N) or
            # SQLUnaryOp('-', SQLLiteral(N)) for negative offsets.
            if len(args) > 7:
                tz_val = None
                tz_arg = args[7]
                if isinstance(tz_arg, SQLLiteral) and isinstance(tz_arg.value, (int, float)):
                    tz_val = float(tz_arg.value)
                elif isinstance(tz_arg, SQLUnaryOp) and tz_arg.operator == '-':
                    inner = tz_arg.operand
                    if isinstance(inner, SQLLiteral) and isinstance(inner.value, (int, float)):
                        tz_val = -float(inner.value)
                if tz_val is not None:
                    sign = '+' if tz_val >= 0 else '-'
                    abs_h = abs(tz_val)
                    tz_h = int(abs_h)
                    tz_m = int((abs_h - tz_h) * 60)
                    iso += f"{sign}{tz_h:02d}:{tz_m:02d}"

            return SQLLiteral(value=iso)

        # Non-literal args: fall back to runtime printf()
        if len(args) == 1:
            year = args[0]
            if isinstance(year, SQLLiteral) and isinstance(year.value, int):
                return SQLLiteral(value=f"{year.value:04d}")
            # Non-integer single arg: pass through as-is (already a date/datetime/string)
            return year

        # Build runtime string using printf — use AST nodes (not SQLRaw with
        # .to_sql()) to avoid premature placeholder resolution (CQL §22.26).
        year = args[0]
        month = args[1] if len(args) > 1 else SQLLiteral(value=1)
        day = args[2] if len(args) > 2 else SQLLiteral(value=1)

        # Determine format based on number of args for correct precision
        if len(args) == 2:
            return SQLFunctionCall(
                name="printf",
                args=[SQLLiteral('%04d-%02d'), year, month],
            )
        if len(args) == 3:
            return SQLFunctionCall(
                name="printf",
                args=[SQLLiteral('%04d-%02d-%02d'), year, month, day],
            )

        hour = args[3] if len(args) > 3 else SQLLiteral(value=0)
        minute = args[4] if len(args) > 4 else SQLLiteral(value=0)
        second = args[5] if len(args) > 5 else SQLLiteral(value=0)

        if len(args) <= 6:
            n = len(args)
            if n == 4:
                return SQLFunctionCall(
                    name="printf",
                    args=[SQLLiteral('%04d-%02dT%02d'), year, month, day, hour],
                )
            if n == 5:
                return SQLFunctionCall(
                    name="printf",
                    args=[SQLLiteral('%04d-%02d-%02dT%02d:%02d'), year, month, day, hour, minute],
                )
            return SQLFunctionCall(
                name="printf",
                args=[SQLLiteral('%04d-%02d-%02dT%02d:%02d:%02d'), year, month, day, hour, minute, second],
            )

        # 7+ args: milliseconds
        millisecond = args[6]
        base_call = SQLFunctionCall(
            name="printf",
            args=[SQLLiteral('%04d-%02d-%02dT%02d:%02d:%02d.%03d'), year, month, day, hour, minute, second, millisecond],
        )

        if len(args) > 7:
            tz_offset = args[7]
            tz_str = SQLFunctionCall(
                name="printf",
                args=[SQLLiteral('%+03.0f:00'), SQLCast(tz_offset, "DOUBLE")],
            )
            return SQLBinaryOp(operator="||", left=base_call, right=tz_str)

        return base_call

    def _translate_date_constructor(self, args: List[SQLExpression]) -> SQLExpression:
        """Translate a Date constructor.

        CQL §22.26: Date(year, month?, day?) — all Integer components.
        Emits VARCHAR ISO 8601 date strings preserving precision.
        """
        if not args:
            return SQLNull()

        all_literal = all(isinstance(a, SQLLiteral) and isinstance(a.value, int) for a in args)
        if all_literal:
            vals = [a.value for a in args]
            n = len(vals)
            if n == 1:
                return SQLLiteral(value=f"{vals[0]:04d}")
            elif n == 2:
                return SQLLiteral(value=f"{vals[0]:04d}-{vals[1]:02d}")
            else:
                return SQLLiteral(value=f"{vals[0]:04d}-{vals[1]:02d}-{vals[2]:02d}")

        if len(args) == 1:
            year = args[0]
            if isinstance(year, SQLLiteral) and isinstance(year.value, int):
                return SQLLiteral(value=f"{year.value:04d}")
            # CQL §22.6: date from DateTime — extract date portion.
            # When the parser emits FunctionRef(name='date', args=[datetime_expr]),
            # treat 1-arg non-integer call as "date from X" extraction.
            if isinstance(year, SQLLiteral) and isinstance(year.value, str) and len(year.value) > 4:
                # DateTime/Date literal: extract first 10 chars (YYYY-MM-DD)
                return SQLLiteral(value=year.value[:10])
            # Non-literal expression: use LEFT() to extract date portion.
            # Build AST nodes (not SQLRaw with .to_sql()) to avoid premature
            # placeholder resolution — CQL §22.6.
            return SQLFunctionCall(
                name="LEFT",
                args=[
                    SQLFunctionCall(
                        name="REPLACE",
                        args=[SQLCast(year, "VARCHAR"), SQLLiteral(' '), SQLLiteral('T')],
                    ),
                    SQLLiteral(10),
                ],
            )

        year = args[0]
        month = args[1] if len(args) > 1 else SQLLiteral(value=1)
        day = args[2] if len(args) > 2 else SQLLiteral(value=1)

        if len(args) == 2:
            return SQLFunctionCall(
                name="printf",
                args=[SQLLiteral('%04d-%02d'), year, month],
            )
        return SQLFunctionCall(
            name="printf",
            args=[SQLLiteral('%04d-%02d-%02d'), year, month, day],
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
        """Handle: year from @2024-01-15, date from dateTime, timezoneoffset from dateTime.

        CQL §22.6: Component extraction from partial-precision datetimes
        returns null when the component is not specified.  We extract
        components via SUBSTRING on the VARCHAR ISO 8601 representation
        to correctly handle partial-precision values.
        """
        operand = self.translate(node.operand, boolean_context=False)
        component_lower = node.component.lower()

        # Handle timezoneoffset — extract offset from datetime string via UDF
        if component_lower == 'timezoneoffset':
            return SQLFunctionCall(
                name="cqlTimezoneOffset",
                args=[SQLCast(expression=operand, target_type="VARCHAR")],
            )

        # Handle 'date from X' - extract date portion (first 10 chars of ISO string)
        if component_lower == 'date':
            return SQLFunctionCall(
                name="LEFT",
                args=[
                    SQLFunctionCall(
                        name="REPLACE",
                        args=[SQLCast(operand, "VARCHAR"), SQLLiteral(' '), SQLLiteral('T')],
                    ),
                    SQLLiteral(10),
                ],
            )

        # Map component names to (start_position, length, min_string_length)
        # for SUBSTRING extraction from ISO 8601 VARCHAR strings.
        # min_string_length: minimum input string length for this component to exist
        component_positions = {
            'year':        (1, 4, 4),    # YYYY
            'month':       (6, 2, 7),    # YYYY-MM
            'day':         (9, 2, 10),   # YYYY-MM-DD
            'hour':        (12, 2, 13),  # YYYY-MM-DDTHH
            'minute':      (15, 2, 16),  # YYYY-MM-DDTHH:MM
            'second':      (18, 2, 19),  # YYYY-MM-DDTHH:MM:SS
            'millisecond': (21, 3, 23),  # YYYY-MM-DDTHH:MM:SS.mmm
        }

        pos_info = component_positions.get(component_lower)
        if pos_info:
            start, length, min_len = pos_info
            # Normalize space→T and extract; return NULL if string too short
            # (component not specified per CQL §22.6).
            # Use SUBSTR (not Substring) to avoid conflict with CQL Substring macro.
            # CQL Time values look like 'T23:20:15.555' — different positions than DateTime.
            # Build AST nodes to avoid premature placeholder resolution.
            replace_expr = SQLFunctionCall(
                name="REPLACE",
                args=[SQLCast(operand, "VARCHAR"), SQLLiteral(' '), SQLLiteral('T')],
            )
            len_expr = SQLFunctionCall(name="LENGTH", args=[replace_expr])

            # Time-specific component positions
            time_positions = {
                'hour':        (2, 2, 3),    # THH
                'minute':      (5, 2, 6),    # THH:MM
                'second':      (8, 2, 9),    # THH:MM:SS
                'millisecond': (11, 3, 13),  # THH:MM:SS.mmm
            }

            time_pos = time_positions.get(component_lower)
            if time_pos:
                t_start, t_length, t_min_len = time_pos
                # If first char is 'T' → CQL Time value; use Time positions.
                # DateTimes never start with 'T' (they start with a year digit).
                first_char = SQLFunctionCall(name="SUBSTR", args=[replace_expr, SQLLiteral(1), SQLLiteral(1)])
                is_time = SQLBinaryOp(operator="=", left=first_char, right=SQLLiteral('T'))
                time_extract = SQLCast(
                    SQLFunctionCall(name="SUBSTR", args=[replace_expr, SQLLiteral(t_start), SQLLiteral(t_length)]),
                    "INTEGER",
                )
                time_branch = SQLCase(
                    when_clauses=[(
                        SQLBinaryOp(operator=">=", left=len_expr, right=SQLLiteral(t_min_len)),
                        time_extract,
                    )],
                    else_clause=SQLNull(),
                )
                dt_extract = SQLCast(
                    SQLFunctionCall(name="SUBSTR", args=[replace_expr, SQLLiteral(start), SQLLiteral(length)]),
                    "INTEGER",
                )
                dt_branch = SQLCase(
                    when_clauses=[(
                        SQLBinaryOp(operator=">=", left=len_expr, right=SQLLiteral(min_len)),
                        dt_extract,
                    )],
                    else_clause=SQLNull(),
                )
                return SQLCase(
                    when_clauses=[(is_time, time_branch)],
                    else_clause=dt_branch,
                )
            else:
                # year/month/day — only applicable to DateTime/Date, not Time
                dt_extract = SQLCast(
                    SQLFunctionCall(name="SUBSTR", args=[replace_expr, SQLLiteral(start), SQLLiteral(length)]),
                    "INTEGER",
                )
                return SQLCase(
                    when_clauses=[(
                        SQLBinaryOp(operator=">=", left=len_expr, right=SQLLiteral(min_len)),
                        dt_extract,
                    )],
                    else_clause=SQLNull(),
                )

        # Fallback for unknown components
        return SQLFunctionCall(name="Year", args=[operand])
