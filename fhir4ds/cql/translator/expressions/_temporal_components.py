"""Date component extraction and constructor translations for CQL to SQL.

Handles DateTime(), Date(), Time() constructors and date component extraction
(year from X, month from X, etc.).
"""
from __future__ import annotations

import calendar
from typing import List

from ...parser.ast_nodes import DateComponent, DateTimeLiteral, Literal, TimeLiteral
from ...translator.context import ExprUsage
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

    def _validated_temporal_constructor(self, expression: SQLExpression, component: str) -> SQLExpression:
        """Return constructor output only when the temporal parser accepts it."""
        component_value = SQLFunctionCall(
            name="dateComponent",
            args=[expression, SQLLiteral(component)],
        )
        return SQLCase(
            when_clauses=[
                (
                    SQLBinaryOp(operator="IS NOT", left=component_value, right=SQLNull()),
                    expression,
                )
            ],
            else_clause=SQLNull(),
        )

    def _bounded_component(self, expression: SQLExpression, minimum: int, maximum: int) -> SQLExpression:
        return SQLBinaryOp(
            operator="AND",
            left=SQLBinaryOp(operator=">=", left=expression, right=SQLLiteral(minimum)),
            right=SQLBinaryOp(operator="<=", left=expression, right=SQLLiteral(maximum)),
        )

    def _validated_time_constructor(
        self,
        expression: SQLExpression,
        component: str,
        hour: SQLExpression,
        minute: SQLExpression,
        second: SQLExpression,
        millisecond: SQLExpression,
    ) -> SQLExpression:
        """Return Time constructor output only when all provided fields are in range."""
        range_check = SQLBinaryOp(
            operator="AND",
            left=SQLBinaryOp(
                operator="AND",
                left=self._bounded_component(hour, 0, 23),
                right=self._bounded_component(minute, 0, 59),
            ),
            right=SQLBinaryOp(
                operator="AND",
                left=self._bounded_component(second, 0, 59),
                right=self._bounded_component(millisecond, 0, 999),
            ),
        )
        validated = self._validated_temporal_constructor(expression, component)
        return SQLCase(
            when_clauses=[(range_check, validated)],
            else_clause=SQLNull(),
        )

    def _time_component_constructor(self, args: List[SQLExpression]) -> SQLExpression:
        """Translate Time(hour[, minute[, second[, millisecond]]]) component construction."""
        hour = args[0]
        minute = args[1] if len(args) > 1 else SQLLiteral(value=0)
        second = args[2] if len(args) > 2 else SQLLiteral(value=0)
        millisecond = args[3] if len(args) > 3 else SQLLiteral(value=0)

        if len(args) == 1:
            candidate = SQLFunctionCall(
                name="printf",
                args=[SQLLiteral('T%02d'), hour],
            )
            return self._validated_time_constructor(candidate, "hour", hour, minute, second, millisecond)
        if len(args) == 2:
            candidate = SQLFunctionCall(
                name="printf",
                args=[SQLLiteral('T%02d:%02d'), hour, minute],
            )
            return self._validated_time_constructor(candidate, "minute", hour, minute, second, millisecond)
        if len(args) == 3:
            candidate = SQLFunctionCall(
                name="printf",
                args=[SQLLiteral('T%02d:%02d:%02d'), hour, minute, second],
            )
            return self._validated_time_constructor(candidate, "second", hour, minute, second, millisecond)
        candidate = SQLFunctionCall(
            name="printf",
            args=[SQLLiteral('T%02d:%02d:%02d.%03d'), hour, minute, second, millisecond],
        )
        return self._validated_time_constructor(candidate, "millisecond", hour, minute, second, millisecond)

    def _translate_time_pre(self, func, translator=None) -> SQLExpression | None:
        """Disambiguate one-argument Time(hour) from `time from <temporal>` extraction."""
        if len(getattr(func, "arguments", []) or []) != 1:
            return None

        raw_arg = func.arguments[0]
        if isinstance(raw_arg, Literal):
            if isinstance(raw_arg.value, int) and not isinstance(raw_arg.value, bool):
                return self._time_component_constructor([
                    self.translate(raw_arg, usage=ExprUsage.SCALAR)
                ])
            raise ValueError("Time constructor components must be Integer values")

        if isinstance(raw_arg, DateComponent) and raw_arg.component.lower() != "timezoneoffset":
            return self._time_component_constructor([
                self.translate(raw_arg, usage=ExprUsage.SCALAR)
            ])

        if isinstance(raw_arg, (DateTimeLiteral, TimeLiteral)):
            if func.name == "time":
                return None
            raise ValueError("Time constructor components must be Integer values")

        if func.name != "time":
            return self._time_component_constructor([
                self.translate(raw_arg, usage=ExprUsage.SCALAR)
            ])

        return None

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

        for component in args[:min(len(args), 7)]:
            if isinstance(component, SQLLiteral) and (
                not isinstance(component.value, int) or isinstance(component.value, bool)
            ):
                raise ValueError("DateTime constructor components must be Integer values")

        # Validate year bounds (1-9999) for literal year values
        year_arg = args[0]
        if isinstance(year_arg, SQLLiteral) and isinstance(year_arg.value, int):
            if year_arg.value < 1 or year_arg.value > 9999:
                raise ValueError(
                    f"The year {year_arg.value} falls outside the accepted "
                    f"bounds of 0001-9999"
                )

        def _validate_literal_components(vals: list[int]) -> None:
            year = vals[0]
            if year < 1 or year > 9999:
                raise ValueError(
                    f"The year {year} falls outside the accepted bounds of 0001-9999"
                )
            if len(vals) >= 2 and not 1 <= vals[1] <= 12:
                raise ValueError(f"Invalid DateTime month {vals[1]}")
            if len(vals) >= 3:
                max_day = calendar.monthrange(year, vals[1])[1]
                if not 1 <= vals[2] <= max_day:
                    raise ValueError(f"Invalid DateTime day {vals[2]}")
            if len(vals) >= 4 and not 0 <= vals[3] <= 23:
                raise ValueError(f"Invalid DateTime hour {vals[3]}")
            if len(vals) >= 5 and not 0 <= vals[4] <= 59:
                raise ValueError(f"Invalid DateTime minute {vals[4]}")
            if len(vals) >= 6 and not 0 <= vals[5] <= 59:
                raise ValueError(f"Invalid DateTime second {vals[5]}")
            if len(vals) >= 7 and not 0 <= vals[6] <= 999:
                raise ValueError(f"Invalid DateTime millisecond {vals[6]}")

        # Check if all provided args are integer literals — if so, emit a
        # compile-time ISO 8601 string literal preserving precision.
        all_literal = all(
            isinstance(a, SQLLiteral) and isinstance(a.value, int) and not isinstance(a.value, bool)
            for a in args[:min(len(args), 7)]
        )
        if all_literal and len(args) <= 8:
            vals = [int(a.value) for a in args[:min(len(args), 7)]]
            _validate_literal_components(vals)
            n = len(vals)
            if n == 1:
                iso = f"{vals[0]:04d}T"
            elif n == 2:
                iso = f"{vals[0]:04d}-{vals[1]:02d}T"
            elif n == 3:
                iso = f"{vals[0]:04d}-{vals[1]:02d}-{vals[2]:02d}T"
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
                    if tz_val < -14 or tz_val > 14:
                        raise ValueError(f"Invalid DateTime timezone offset {tz_val}")
                    sign = '+' if tz_val >= 0 else '-'
                    abs_h = abs(tz_val)
                    tz_h = int(abs_h)
                    tz_m = round((abs_h - tz_h) * 60)
                    iso += f"{sign}{tz_h:02d}:{tz_m:02d}"

            return SQLLiteral(value=iso)

        # Non-literal args: fall back to runtime printf()
        if len(args) == 1:
            year = args[0]
            candidate = SQLFunctionCall(
                name="printf",
                args=[SQLLiteral('%04dT'), year],
            )
            return self._validated_temporal_constructor(candidate, "year")

        # Build runtime string using printf — use AST nodes (not SQLRaw with
        # .to_sql()) to avoid premature placeholder resolution (CQL §22.26).
        year = args[0]
        month = args[1] if len(args) > 1 else SQLLiteral(value=1)
        day = args[2] if len(args) > 2 else SQLLiteral(value=1)

        # Determine format based on number of args for correct precision
        if len(args) == 2:
            candidate = SQLFunctionCall(
                name="printf",
                args=[SQLLiteral('%04d-%02dT'), year, month],
            )
            return self._validated_temporal_constructor(candidate, "month")
        if len(args) == 3:
            candidate = SQLFunctionCall(
                name="printf",
                args=[SQLLiteral('%04d-%02d-%02dT'), year, month, day],
            )
            return self._validated_temporal_constructor(candidate, "day")

        hour = args[3] if len(args) > 3 else SQLLiteral(value=0)
        minute = args[4] if len(args) > 4 else SQLLiteral(value=0)
        second = args[5] if len(args) > 5 else SQLLiteral(value=0)

        if len(args) <= 6:
            n = len(args)
            if n == 4:
                candidate = SQLFunctionCall(
                    name="printf",
                    args=[SQLLiteral('%04d-%02d-%02dT%02d'), year, month, day, hour],
                )
                return self._validated_temporal_constructor(candidate, "hour")
            if n == 5:
                candidate = SQLFunctionCall(
                    name="printf",
                    args=[SQLLiteral('%04d-%02d-%02dT%02d:%02d'), year, month, day, hour, minute],
                )
                return self._validated_temporal_constructor(candidate, "minute")
            candidate = SQLFunctionCall(
                name="printf",
                args=[SQLLiteral('%04d-%02d-%02dT%02d:%02d:%02d'), year, month, day, hour, minute, second],
            )
            return self._validated_temporal_constructor(candidate, "second")

        # 7+ args: milliseconds
        millisecond = args[6]
        base_call = SQLFunctionCall(
            name="printf",
            args=[SQLLiteral('%04d-%02d-%02dT%02d:%02d:%02d.%03d'), year, month, day, hour, minute, second, millisecond],
        )

        if len(args) > 7:
            tz_offset = args[7]
            abs_tz = SQLFunctionCall(
                name="ABS",
                args=[SQLCast(tz_offset, "DOUBLE")],
            )
            tz_hour = SQLCast(
                SQLFunctionCall(name="FLOOR", args=[abs_tz]),
                "INTEGER",
            )
            tz_minute = SQLCast(
                SQLFunctionCall(
                    name="system.round",
                    args=[
                        SQLBinaryOp(
                            operator="*",
                            left=SQLBinaryOp(
                                operator="-",
                                left=abs_tz,
                                right=SQLFunctionCall(name="FLOOR", args=[abs_tz]),
                            ),
                            right=SQLLiteral(value=60),
                        )
                    ],
                ),
                "INTEGER",
            )
            sign = SQLCase(
                when_clauses=[(
                    SQLBinaryOp(operator="<", left=SQLCast(tz_offset, "DOUBLE"), right=SQLLiteral(value=0)),
                    SQLLiteral(value="-"),
                )],
                else_clause=SQLLiteral(value="+"),
            )
            tz_str = SQLFunctionCall(
                name="printf",
                args=[SQLLiteral('%s%02d:%02d'), sign, tz_hour, tz_minute],
            )
            candidate = SQLBinaryOp(operator="||", left=base_call, right=tz_str)
            return self._validated_temporal_constructor(candidate, "millisecond")

        return self._validated_temporal_constructor(base_call, "millisecond")

    def _translate_date_constructor(self, args: List[SQLExpression]) -> SQLExpression:
        """Translate a Date constructor.

        CQL §22.26: Date(year, month?, day?) — all Integer components.
        Emits VARCHAR ISO 8601 date strings preserving precision.
        """
        if not args:
            return SQLNull()

        for component in args if len(args) > 1 else []:
            if isinstance(component, SQLLiteral) and (
                not isinstance(component.value, int) or isinstance(component.value, bool)
            ):
                raise ValueError("Date constructor components must be Integer values")

        all_literal = all(isinstance(a, SQLLiteral) and isinstance(a.value, int) and not isinstance(a.value, bool) for a in args)
        if all_literal:
            vals = [a.value for a in args]
            year = vals[0]
            if year < 1 or year > 9999:
                raise ValueError(f"The year {year} falls outside the accepted bounds of 0001-9999")
            if len(vals) >= 2 and not 1 <= vals[1] <= 12:
                raise ValueError(f"Invalid Date month {vals[1]}")
            if len(vals) >= 3:
                max_day = calendar.monthrange(year, vals[1])[1]
                if not 1 <= vals[2] <= max_day:
                    raise ValueError(f"Invalid Date day {vals[2]}")
            n = len(vals)
            if n == 1:
                return SQLLiteral(value=f"{vals[0]:04d}")
            elif n == 2:
                return SQLLiteral(value=f"{vals[0]:04d}-{vals[1]:02d}")
            else:
                return SQLLiteral(value=f"{vals[0]:04d}-{vals[1]:02d}-{vals[2]:02d}")

        if len(args) == 1:
            year = args[0]
            if isinstance(year, SQLLiteral) and (
                not isinstance(year.value, (int, str)) or isinstance(year.value, bool)
            ):
                raise ValueError("Date constructor components must be Integer values")
            if isinstance(year, SQLLiteral) and isinstance(year.value, int):
                if year.value < 1 or year.value > 9999:
                    raise ValueError(
                        f"The year {year.value} falls outside the accepted bounds of 0001-9999"
                    )
                return SQLLiteral(value=f"{year.value:04d}")
            # CQL §22.6: date from DateTime — extract date portion.
            # When the parser emits FunctionRef(name='date', args=[datetime_expr]),
            # treat 1-arg non-integer call as "date from X" extraction.
            if isinstance(year, SQLLiteral) and isinstance(year.value, str) and len(year.value) > 4:
                normalized = year.value.replace(" ", "T")
                if normalized.startswith("T"):
                    return SQLNull()
                return SQLLiteral(value=normalized.split("T", 1)[0])
            # Non-literal expression: extract the date portion up to T.
            # Build AST nodes (not SQLRaw with .to_sql()) to avoid premature
            # placeholder resolution — CQL §22.6.
            source = SQLFunctionCall(
                name="REPLACE",
                args=[SQLCast(year, "VARCHAR"), SQLLiteral(' '), SQLLiteral('T')],
            )
            t_pos = SQLFunctionCall(name="STRPOS", args=[source, SQLLiteral('T')])
            return SQLCase(
                when_clauses=[
                    (SQLBinaryOp(operator="=", left=t_pos, right=SQLLiteral(1)), SQLNull()),
                    (
                        SQLBinaryOp(operator=">", left=t_pos, right=SQLLiteral(1)),
                        SQLFunctionCall(
                            name="LEFT",
                            args=[
                                source,
                                SQLBinaryOp(operator="-", left=t_pos, right=SQLLiteral(1)),
                            ],
                        ),
                    ),
                ],
                else_clause=source,
            )

        year = args[0]
        month = args[1] if len(args) > 1 else SQLLiteral(value=1)
        day = args[2] if len(args) > 2 else SQLLiteral(value=1)

        if len(args) == 2:
            candidate = SQLFunctionCall(
                name="printf",
                args=[SQLLiteral('%04d-%02d'), year, month],
            )
            return self._validated_temporal_constructor(candidate, "month")
        candidate = SQLFunctionCall(
            name="printf",
            args=[SQLLiteral('%04d-%02d-%02d'), year, month, day],
        )
        return self._validated_temporal_constructor(candidate, "day")

    def _translate_time_constructor(self, args: List[SQLExpression]) -> SQLExpression:
        """Translate a Time constructor."""
        if not args:
            return SQLNull()

        if len(args) >= 2:
            return self._time_component_constructor(args)

        source = SQLFunctionCall(
            name="REPLACE",
            args=[SQLCast(args[0], "VARCHAR"), SQLLiteral(' '), SQLLiteral('T')],
        )
        t_pos = SQLFunctionCall(name="STRPOS", args=[source, SQLLiteral('T')])
        is_time = SQLBinaryOp(
            operator="=",
            left=SQLFunctionCall(name="SUBSTR", args=[source, SQLLiteral(1), SQLLiteral(1)]),
            right=SQLLiteral('T'),
        )
        has_datetime_time = SQLBinaryOp(
            operator="AND",
            left=SQLBinaryOp(operator=">", left=t_pos, right=SQLLiteral(0)),
            right=SQLBinaryOp(
                operator=">",
                left=SQLFunctionCall(name="LENGTH", args=[source]),
                right=t_pos,
            ),
        )
        return SQLCase(
            when_clauses=[
                (is_time, source),
                (
                    has_datetime_time,
                    SQLBinaryOp(
                        operator="||",
                        left=SQLLiteral("T"),
                        right=SQLFunctionCall(
                            name="SUBSTR",
                            args=[
                                source,
                                SQLBinaryOp(operator="+", left=t_pos, right=SQLLiteral(1)),
                            ],
                        ),
                    ),
                ),
            ],
            else_clause=SQLNull(),
        )

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
            source = SQLFunctionCall(
                name="REPLACE",
                args=[SQLCast(operand, "VARCHAR"), SQLLiteral(' '), SQLLiteral('T')],
            )
            t_pos = SQLFunctionCall(name="STRPOS", args=[source, SQLLiteral('T')])
            return SQLCase(
                when_clauses=[
                    (SQLBinaryOp(operator="=", left=t_pos, right=SQLLiteral(1)), SQLNull()),
                    (
                        SQLBinaryOp(operator=">", left=t_pos, right=SQLLiteral(1)),
                        SQLFunctionCall(
                            name="LEFT",
                            args=[
                                source,
                                SQLBinaryOp(operator="-", left=t_pos, right=SQLLiteral(1)),
                            ],
                        ),
                    ),
                ],
                else_clause=source,
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
