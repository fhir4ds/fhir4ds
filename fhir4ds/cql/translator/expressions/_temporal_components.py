"""Date component extraction and constructor translations for CQL to SQL.

Handles DateTime(), Date(), Time() constructors and date component extraction
(year from X, month from X, etc.).
"""
from __future__ import annotations

import calendar
import math
from typing import List, Optional

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

    _DUCKDB_INTEGER_TYPES = (
        "TINYINT",
        "SMALLINT",
        "INTEGER",
        "BIGINT",
        "HUGEINT",
        "UTINYINT",
        "USMALLINT",
        "UINTEGER",
        "UBIGINT",
        "UHUGEINT",
    )
    _DUCKDB_FLOAT_TYPES = ("FLOAT", "DOUBLE", "REAL")

    def _chain_conditions(self, operator: str, conditions: List[SQLExpression]) -> SQLExpression:
        if not conditions:
            return SQLLiteral(True)
        result = conditions[0]
        for condition in conditions[1:]:
            result = SQLBinaryOp(operator=operator, left=result, right=condition)
        return result

    def _duckdb_type_is(self, expression: SQLExpression, type_names: tuple[str, ...]) -> SQLExpression:
        type_expr = SQLFunctionCall(name="typeof", args=[expression])
        conditions = [
            SQLBinaryOp(operator="=", left=type_expr, right=SQLLiteral(type_name))
            for type_name in type_names
        ]
        return self._chain_conditions("OR", conditions)

    def _duckdb_type_starts_with(self, expression: SQLExpression, prefix: str) -> SQLExpression:
        return SQLBinaryOp(
            operator="LIKE",
            left=SQLFunctionCall(name="typeof", args=[expression]),
            right=SQLLiteral(f"{prefix}%"),
        )

    def _integer_component_value(self, expression: SQLExpression) -> tuple[SQLExpression, SQLExpression]:
        return (
            SQLCast(expression=expression, target_type="INTEGER", try_cast=True),
            self._duckdb_type_is(expression, self._DUCKDB_INTEGER_TYPES),
        )

    def _decimal_component_value(self, expression: SQLExpression) -> tuple[SQLExpression, SQLExpression]:
        numeric_type = self._chain_conditions(
            "OR",
            [
                self._duckdb_type_is(expression, self._DUCKDB_INTEGER_TYPES + self._DUCKDB_FLOAT_TYPES),
                self._duckdb_type_starts_with(expression, "DECIMAL"),
            ],
        )
        return SQLCast(expression=expression, target_type="DOUBLE", try_cast=True), numeric_type

    def _validated_temporal_constructor(
        self,
        expression: SQLExpression,
        component: str,
        guard: SQLExpression | None = None,
    ) -> SQLExpression:
        """Return constructor output only when the temporal parser accepts it."""
        component_value = SQLFunctionCall(
            name="dateComponent",
            args=[expression, SQLLiteral(component)],
        )
        condition = SQLBinaryOp(operator="IS NOT", left=component_value, right=SQLNull())
        if guard is not None:
            condition = SQLBinaryOp(operator="AND", left=guard, right=condition)
        return SQLCase(
            when_clauses=[
                (condition, expression)
            ],
            else_clause=SQLNull(),
        )

    def _bounded_component(self, expression: SQLExpression, minimum: int, maximum: int) -> SQLExpression:
        return SQLBinaryOp(
            operator="AND",
            left=SQLBinaryOp(operator=">=", left=expression, right=SQLLiteral(minimum)),
            right=SQLBinaryOp(operator="<=", left=expression, right=SQLLiteral(maximum)),
        )

    def _is_static_null_component(self, expression: SQLExpression) -> bool:
        if isinstance(expression, SQLNull):
            return True
        if isinstance(expression, SQLLiteral) and expression.value is None:
            return True
        if isinstance(expression, SQLCast):
            return self._is_static_null_component(expression.expression)
        return False

    def _validated_time_constructor(
        self,
        expression: SQLExpression,
        component: str,
        hour: SQLExpression,
        minute: SQLExpression,
        second: SQLExpression,
        millisecond: SQLExpression,
        guard: SQLExpression | None = None,
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
        if guard is not None:
            range_check = SQLBinaryOp(operator="AND", left=guard, right=range_check)
        validated = self._validated_temporal_constructor(expression, component)
        return SQLCase(
            when_clauses=[(range_check, validated)],
            else_clause=SQLNull(),
        )

    def _time_component_constructor(self, args: List[SQLExpression]) -> SQLExpression:
        """Translate Time(hour[, minute[, second[, millisecond]]]) component construction."""
        hour_expr = args[0]
        minute_expr = args[1] if len(args) > 1 else None
        second_expr = args[2] if len(args) > 2 else None
        millisecond_expr = args[3] if len(args) > 3 else None

        hour, hour_guard = self._integer_component_value(hour_expr)

        def _is_null(expr: SQLExpression) -> SQLExpression:
            return SQLBinaryOp(operator="IS", left=expr, right=SQLNull())

        def _is_not_null(expr: SQLExpression) -> SQLExpression:
            return SQLBinaryOp(operator="IS NOT", left=expr, right=SQLNull())

        def _required_component(
            expr: SQLExpression,
            value: SQLExpression,
            guard: SQLExpression,
            minimum: int,
            maximum: int,
        ) -> SQLExpression:
            return self._chain_conditions(
                "AND",
                [
                    guard,
                    _is_not_null(expr),
                    self._bounded_component(value, minimum, maximum),
                ],
            )

        def _optional_component(
            expr: SQLExpression,
            minimum: int,
            maximum: int,
        ) -> tuple[SQLExpression, SQLExpression, SQLExpression, SQLExpression]:
            value, guard = self._integer_component_value(expr)
            present = _required_component(expr, value, guard, minimum, maximum)
            absent = _is_null(expr)
            return value, guard, present, absent

        hour_present = _required_component(hour_expr, hour, hour_guard, 0, 23)
        minute = SQLLiteral(value=0)
        second = SQLLiteral(value=0)
        millisecond = SQLLiteral(value=0)
        minute_present = SQLLiteral(value=False)
        second_present = SQLLiteral(value=False)
        millisecond_present = SQLLiteral(value=False)
        minute_absent = SQLLiteral(value=True)
        second_absent = SQLLiteral(value=True)
        millisecond_absent = SQLLiteral(value=True)

        if minute_expr is not None:
            minute, _minute_guard, minute_present, minute_absent = _optional_component(minute_expr, 0, 59)
        if second_expr is not None:
            second, _second_guard, second_present, second_absent = _optional_component(second_expr, 0, 59)
        if millisecond_expr is not None:
            millisecond, _millisecond_guard, millisecond_present, millisecond_absent = _optional_component(
                millisecond_expr, 0, 999
            )

        def _validated_candidate(
            condition: SQLExpression,
            component: str,
            fmt: str,
            fmt_args: List[SQLExpression],
        ) -> tuple[SQLExpression, SQLExpression]:
            candidate = SQLFunctionCall(name="printf", args=[SQLLiteral(fmt), *fmt_args])
            return condition, self._validated_temporal_constructor(candidate, component)

        hour_condition = self._chain_conditions(
            "AND",
            [hour_present, minute_absent, second_absent, millisecond_absent],
        )
        when_clauses: list[tuple[SQLExpression, SQLExpression]] = [
            _validated_candidate(hour_condition, "hour", "T%02d", [hour])
        ]

        if len(args) >= 2:
            minute_condition = self._chain_conditions(
                "AND",
                [hour_present, minute_present, second_absent, millisecond_absent],
            )
            when_clauses.append(
                _validated_candidate(minute_condition, "minute", "T%02d:%02d", [hour, minute])
            )

        if len(args) >= 3:
            second_condition = self._chain_conditions(
                "AND",
                [hour_present, minute_present, second_present, millisecond_absent],
            )
            when_clauses.append(
                _validated_candidate(second_condition, "second", "T%02d:%02d:%02d", [hour, minute, second])
            )

        if len(args) >= 4:
            millisecond_condition = self._chain_conditions(
                "AND",
                [hour_present, minute_present, second_present, millisecond_present],
            )
            when_clauses.append(
                _validated_candidate(
                    millisecond_condition,
                    "millisecond",
                    "T%02d:%02d:%02d.%03d",
                    [hour, minute, second, millisecond],
                )
            )

        return SQLCase(
            when_clauses=when_clauses,
            else_clause=SQLNull(),
        )

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
            # CQL 1.5 §8.16: "At least one component must be specified" —
            # a lone null literal is an unsatisfied constructor, which
            # evaluates to null (same convention as Time(null, null) and
            # the spec's own TimeInvalid example), not a translation crash.
            if raw_arg.value is None:
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
        Date/time components are Integer; timezoneOffset is Decimal hours.

        Emits VARCHAR ISO 8601 strings preserving precision based on the number
        of provided components.  When all args are integer literals, we can
        build the string at compile time.  Otherwise, we use printf() to
        build it at runtime.
        """
        if not args:
            return SQLNull()

        args = list(args)
        # CQL §22.5: trailing null components are the sanctioned partial
        # form ("hour may be null, but then minute, second, and millisecond
        # must all be null"). Strip trailing static nulls — including any
        # that sit below a specified timezoneOffset — before precision is
        # decided; a static-null timezoneOffset is treated as unspecified.
        timezone_arg = None
        if len(args) > 7:
            timezone_arg = args[7]
            args = args[:7]
        if timezone_arg is not None and self._is_static_null_component(timezone_arg):
            timezone_arg = None
        while len(args) > 1 and self._is_static_null_component(args[-1]):
            args.pop()
        # CQL §22.5: "no component may be specified at a precision below an
        # unspecified precision" — a static null left ABOVE a specified
        # component (e.g. DateTime(2012, 1, 1, 12, null, 0, 0, -7), the
        # spec's DateInvalid example) is rejected at translation time.
        # An all-null argument list (DateTime(null), the official
        # DateTimeNull fixture) evaluates to null instead.
        _seen_unspecified = False
        for component in args[:min(len(args), 7)]:
            if self._is_static_null_component(component):
                _seen_unspecified = True
            elif _seen_unspecified:
                raise ValueError(
                    "DateTime constructor components may not be specified below "
                    "an unspecified (null) component"
                )

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

        def _literal_timezone_offset(arg: SQLExpression) -> tuple[bool, float | None]:
            """Return (is_static, value) for literal DateTime timezone offsets."""
            if isinstance(arg, SQLLiteral):
                if isinstance(arg.value, bool) or not isinstance(arg.value, (int, float)):
                    raise ValueError("DateTime timezoneOffset must be a Decimal value")
                return True, float(arg.value)
            if isinstance(arg, SQLUnaryOp) and arg.operator == '-':
                inner = arg.operand
                if isinstance(inner, SQLLiteral):
                    if isinstance(inner.value, bool) or not isinstance(inner.value, (int, float)):
                        raise ValueError("DateTime timezoneOffset must be a Decimal value")
                    return True, -float(inner.value)
            return False, None

        timezone_is_static = True
        if timezone_arg is not None:
            timezone_is_static, _ = _literal_timezone_offset(timezone_arg)

        # Check if all provided date/time args are integer literals — if so,
        # emit a compile-time ISO 8601 string literal preserving precision.
        # A dynamic timezoneOffset still needs the runtime path.
        all_literal = all(
            isinstance(a, SQLLiteral) and isinstance(a.value, int) and not isinstance(a.value, bool)
            for a in args[:min(len(args), 7)]
        )
        if all_literal and timezone_is_static:
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
            if timezone_arg is not None:
                _, tz_val = _literal_timezone_offset(timezone_arg)
                if tz_val is None:
                    raise ValueError("DateTime timezoneOffset must be a Decimal value")
                if not math.isfinite(tz_val) or tz_val < -14 or tz_val > 14:
                    raise ValueError(f"Invalid DateTime timezone offset {tz_val}")
                sign = '+' if tz_val >= 0 else '-'
                total_minutes = int(round(abs(tz_val) * 60))
                if total_minutes > 14 * 60:
                    raise ValueError(f"Invalid DateTime timezone offset {tz_val}")
                tz_h = total_minutes // 60
                tz_m = total_minutes % 60
                iso += f"{sign}{tz_h:02d}:{tz_m:02d}"

            return SQLLiteral(value=iso)

        # Non-literal args: fall back to runtime printf()
        if len(args) == 1:
            year, year_guard = self._integer_component_value(args[0])
            candidate = SQLFunctionCall(
                name="printf",
                args=[SQLLiteral('%04dT'), year],
            )
            return self._validated_temporal_constructor(candidate, "year", year_guard)

        # Build runtime string using printf — use AST nodes (not SQLRaw with
        # .to_sql()) to avoid premature placeholder resolution (CQL §22.26).
        year, year_guard = self._integer_component_value(args[0])
        month, month_guard = self._integer_component_value(args[1] if len(args) > 1 else SQLLiteral(value=1))
        day, day_guard = self._integer_component_value(args[2] if len(args) > 2 else SQLLiteral(value=1))

        # Determine format based on number of args for correct precision
        if len(args) == 2:
            component_guard = self._chain_conditions("AND", [year_guard, month_guard])
            candidate = SQLFunctionCall(
                name="printf",
                args=[SQLLiteral('%04d-%02dT'), year, month],
            )
            return self._validated_temporal_constructor(candidate, "month", component_guard)
        if len(args) == 3:
            component_guard = self._chain_conditions("AND", [year_guard, month_guard, day_guard])
            candidate = SQLFunctionCall(
                name="printf",
                args=[SQLLiteral('%04d-%02d-%02dT'), year, month, day],
            )
            return self._validated_temporal_constructor(candidate, "day", component_guard)

        hour, hour_guard = self._integer_component_value(args[3] if len(args) > 3 else SQLLiteral(value=0))
        minute, minute_guard = self._integer_component_value(args[4] if len(args) > 4 else SQLLiteral(value=0))
        second, second_guard = self._integer_component_value(args[5] if len(args) > 5 else SQLLiteral(value=0))

        if len(args) <= 6:
            n = len(args)
            if n == 4:
                component_guard = self._chain_conditions("AND", [year_guard, month_guard, day_guard, hour_guard])
                candidate = SQLFunctionCall(
                    name="printf",
                    args=[SQLLiteral('%04d-%02d-%02dT%02d'), year, month, day, hour],
                )
                return self._validated_temporal_constructor(candidate, "hour", component_guard)
            if n == 5:
                component_guard = self._chain_conditions(
                    "AND", [year_guard, month_guard, day_guard, hour_guard, minute_guard]
                )
                candidate = SQLFunctionCall(
                    name="printf",
                    args=[SQLLiteral('%04d-%02d-%02dT%02d:%02d'), year, month, day, hour, minute],
                )
                return self._validated_temporal_constructor(candidate, "minute", component_guard)
            component_guard = self._chain_conditions(
                "AND", [year_guard, month_guard, day_guard, hour_guard, minute_guard, second_guard]
            )
            candidate = SQLFunctionCall(
                name="printf",
                args=[SQLLiteral('%04d-%02d-%02dT%02d:%02d:%02d'), year, month, day, hour, minute, second],
            )
            return self._validated_temporal_constructor(candidate, "second", component_guard)

        # 7+ args: milliseconds
        millisecond, millisecond_guard = self._integer_component_value(args[6])
        component_guard = self._chain_conditions(
            "AND",
            [year_guard, month_guard, day_guard, hour_guard, minute_guard, second_guard, millisecond_guard],
        )
        base_call = SQLFunctionCall(
            name="printf",
            args=[SQLLiteral('%04d-%02d-%02dT%02d:%02d:%02d.%03d'), year, month, day, hour, minute, second, millisecond],
        )

        if timezone_arg is not None:
            tz_offset_double, tz_guard = self._decimal_component_value(timezone_arg)
            abs_tz = SQLFunctionCall(
                name="ABS",
                args=[tz_offset_double],
            )
            total_minutes = SQLCast(
                SQLFunctionCall(
                    name="system.round",
                    args=[
                        SQLBinaryOp(
                            operator="*",
                            left=abs_tz,
                            right=SQLLiteral(value=60),
                        )
                    ],
                ),
                "INTEGER",
            )
            tz_hour = SQLCast(
                SQLFunctionCall(
                    name="FLOOR",
                    args=[
                        SQLBinaryOp(
                            operator="/",
                            left=total_minutes,
                            right=SQLLiteral(value=60),
                        )
                    ],
                ),
                "INTEGER",
            )
            tz_minute = SQLCast(
                SQLBinaryOp(
                    operator="%",
                    left=total_minutes,
                    right=SQLLiteral(value=60),
                ),
                "INTEGER",
            )
            sign = SQLCase(
                when_clauses=[(
                    SQLBinaryOp(operator="<", left=tz_offset_double, right=SQLLiteral(value=0)),
                    SQLLiteral(value="-"),
                )],
                else_clause=SQLLiteral(value="+"),
            )
            tz_str = SQLFunctionCall(
                name="printf",
                args=[SQLLiteral('%s%02d:%02d'), sign, tz_hour, tz_minute],
            )
            candidate = SQLBinaryOp(operator="||", left=base_call, right=tz_str)
            range_check = SQLBinaryOp(
                operator="AND",
                left=self._chain_conditions("AND", [component_guard, tz_guard]),
                right=SQLBinaryOp(
                    operator="AND",
                    left=SQLBinaryOp(operator="<=", left=abs_tz, right=SQLLiteral(value=14)),
                    right=SQLBinaryOp(operator="<=", left=total_minutes, right=SQLLiteral(value=14 * 60)),
                ),
            )
            return SQLCase(
                when_clauses=[(
                    range_check,
                    self._validated_temporal_constructor(candidate, "millisecond"),
                )],
                else_clause=SQLNull(),
            )

        return self._validated_temporal_constructor(base_call, "millisecond", component_guard)

    def _translate_date_constructor(self, args: List[SQLExpression]) -> SQLExpression:
        """Translate a Date constructor.

        CQL §22.26: Date(year, month?, day?) — all Integer components.
        Emits VARCHAR ISO 8601 date strings preserving precision.
        """
        if not args:
            return SQLNull()

        args = list(args)
        # CQL §22.26: trailing null components are the sanctioned partial
        # form ("month may be null, but then day must also be null").
        while len(args) > 1 and self._is_static_null_component(args[-1]):
            args.pop()

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
            # CQL date from DateTime is represented by the parser as a one-arg
            # date function. Keep that extraction path distinct from the
            # multi-component Date constructor.
            if isinstance(year, SQLLiteral) and isinstance(year.value, str) and len(year.value) > 4:
                normalized = year.value.replace(" ", "T")
                if normalized.startswith("T"):
                    return SQLNull()
                return SQLLiteral(value=normalized.split("T", 1)[0])
            source = self._unwrap_interval_case(year)
            normalized = SQLFunctionCall(
                name="REPLACE",
                args=[SQLCast(source, "VARCHAR"), SQLLiteral(' '), SQLLiteral('T')],
            )
            return SQLFunctionCall(
                name="ToDate",
                args=[normalized],
            )

        year, year_guard = self._integer_component_value(args[0])
        month, month_guard = self._integer_component_value(args[1] if len(args) > 1 else SQLLiteral(value=1))
        day, day_guard = self._integer_component_value(args[2] if len(args) > 2 else SQLLiteral(value=1))

        if len(args) == 2:
            component_guard = self._chain_conditions("AND", [year_guard, month_guard])
            candidate = SQLFunctionCall(
                name="printf",
                args=[SQLLiteral('%04d-%02d'), year, month],
            )
            return self._validated_temporal_constructor(candidate, "month", component_guard)
        component_guard = self._chain_conditions("AND", [year_guard, month_guard, day_guard])
        candidate = SQLFunctionCall(
            name="printf",
            args=[SQLLiteral('%04d-%02d-%02d'), year, month, day],
        )
        return self._validated_temporal_constructor(candidate, "day", component_guard)

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

        # Handle 'time from X' — extract the Time portion of a DateTime value.
        # Mirrors the `time from` dateTimeComponent grammar form via the same
        # extraction shape the one-arg Time() conversion path uses.
        if component_lower == 'time':
            return self._translate_time_constructor([
                SQLCast(operand, "VARCHAR"),
            ])

        # Handle 'date from X' - extract date portion (first 10 chars of ISO string)
        if component_lower == 'date':
            operand = self._unwrap_interval_case(operand)
            normalized = SQLFunctionCall(
                name="REPLACE",
                args=[SQLCast(operand, "VARCHAR"), SQLLiteral(' '), SQLLiteral('T')],
            )
            return SQLFunctionCall(
                name="ToDate",
                args=[normalized],
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
            return SQLFunctionCall(
                name="dateComponent",
                args=[
                    SQLCast(operand, "VARCHAR"),
                    SQLLiteral(component_lower),
                ],
            )

        # Fallback for unknown components
        return SQLFunctionCall(name="Year", args=[operand])

    # CQL 1.5 dateTimeComponent accessors valid on temporal-typed sources.
    # `week` is a duration precision, not a component, and is excluded.
    _TEMPORAL_COMPONENT_PATHS = frozenset({
        'year', 'month', 'day', 'hour', 'minute', 'second', 'millisecond',
        'date', 'time', 'timezoneoffset',
    })

    def _static_source_cql_type(self, source) -> str:
        """Standalone static CQL type resolution for temporal/complex literals.

        The full ``_infer_cql_type`` machinery lives on the library-level
        translator, not on the ExpressionTranslator mixin stack; expression
        contexts only need the literal/function-ref subset resolved here.
        """
        from ...parser.ast_nodes import FunctionRef as _FunctionRef
        if isinstance(source, DateTimeLiteral):
            value = str(getattr(source, "value", "") or "")
            if value.startswith("T"):
                return "Time"
            return "DateTime" if "T" in value else "Date"
        if isinstance(source, TimeLiteral):
            return "Time"
        if isinstance(source, _FunctionRef):
            name = (getattr(source, "name", "") or "").lower()
            if name == "totime":
                return "Time"
            if name == "todate":
                return "Date"
            if name == "todatetime":
                return "DateTime"
            if name == "toratio":
                return "Ratio"
        return "Any"

    def _translate_temporal_component_property(self, prop) -> Optional[SQLExpression]:
        """Route ``<temporal>.month``-style property access through dateComponent.

        CQL 1.5 §09-b (Date and Time Component From) defines BOTH the
        ``month from X`` form and the ``X.month`` property accessor for the
        same component extraction. Property access on temporal values must
        not lower to FHIRPath text navigation (which returns SQL null for
        bare ISO string literals).
        """
        path = (getattr(prop, 'path', None) or '').lower()
        if path not in self._TEMPORAL_COMPONENT_PATHS:
            return None
        source = getattr(prop, 'source', None)
        if source is None:
            return None
        source_type = self._static_source_cql_type(source)
        if source_type not in ('Date', 'DateTime', 'Time'):
            # Define aliases of temporal literals resolve through their
            # definition AST chains (CQL-03 QA-002 inlining makes the
            # operand translation a literal again).
            from ...parser.ast_nodes import Identifier as _Identifier
            if not isinstance(source, _Identifier) or self.context.is_alias(source.name):
                return None
            if not self._is_static_temporal_definition(source):
                return None
        node = DateComponent(component=path, operand=source)
        return self._translate_date_component(node)
