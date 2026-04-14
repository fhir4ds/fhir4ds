"""
Temporal pattern translator for CQL temporal operators.

This module provides the TemporalTranslator class for translating CQL temporal
operators to SQL expressions using CQL UDFs and native SQL patterns.

Supported CQL temporal operators:
- during, includes - interval membership
- overlaps, overlaps before, overlaps after - interval overlap
- before, after - ordering
- starts, ends - interval boundaries
- meets, meets before, meets after - adjacent intervals
- same day as, same hour as, etc. - precision-based equality
- on or before, on or after - inclusive comparisons

SQL Patterns:
| CQL Pattern                      | SQL Pattern                                      |
|----------------------------------|--------------------------------------------------|
| x during day of y                | DATE(x) BETWEEN DATE(START(y)) AND DATE(END(y))  |
| x same day as y                  | DATE(x) = DATE(y)                                |
| x on or before y                 | x <= y OR DATE(x) = DATE(y)                      |
| x on or after y                  | x >= y OR DATE(x) = DATE(y)                      |
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from ...translator.types import (
    SQLCast,
    SQLExpression,
    SQLBinaryOp,
    SQLFunctionCall,
    SQLCase,
    SQLLiteral,
    PRECEDENCE,
)

if TYPE_CHECKING:
    from ...translator.context import SQLTranslationContext


# Precision level mappings for date/time comparisons
PRECISION_LEVELS = {
    "year": 1,
    "month": 2,
    "week": 2,  # Week is treated similar to month for truncation
    "day": 3,
    "hour": 4,
    "minute": 5,
    "second": 6,
    "millisecond": 7,
    "millis": 7,
}

# SQL date truncation functions by precision
PRECISION_TRUNCATE_FUNCTIONS = {
    "year": "DATE_TRUNC('year', {})",
    "month": "DATE_TRUNC('month', {})",
    "week": "DATE_TRUNC('week', {})",
    "day": "DATE({})",
    "hour": "DATE_TRUNC('hour', {})",
    "minute": "DATE_TRUNC('minute', {})",
    "second": "DATE_TRUNC('second', {})",
    "millisecond": "DATE_TRUNC('millisecond', {})",
    "millis": "DATE_TRUNC('millisecond', {})",
}


class TemporalTranslator:
    """
    Translates CQL temporal operators to SQL expressions.

    This class handles the translation of temporal comparison operators
    in CQL, including interval membership, overlap, ordering, and
    precision-based comparisons.

    Example CQL:
        O.effective during day of Encounter.period
        O.effective same day as @2024-01-15
        O.effective on or before Encounter.period.start

    Generated SQL (conceptual):
        DATE(O.effective) BETWEEN DATE(START(Encounter.period)) AND DATE(END(Encounter.period))
        DATE(O.effective) = DATE(@2024-01-15)
        O.effective <= Encounter.period.start OR DATE(O.effective) = DATE(Encounter.period.start)
    """

    def __init__(self, context: SQLTranslationContext):
        """
        Initialize the temporal translator.

        Args:
            context: The translation context for symbol resolution.
        """
        self.context = context

    def translate_during(
        self,
        left: SQLExpression,
        right: SQLExpression,
        precision: Optional[str] = None,
        context: Optional[SQLTranslationContext] = None,
    ) -> SQLExpression:
        """
        Translate 'x during y' - interval membership.

        Checks if the left expression (point or interval) is within
        the right interval.

        Args:
            left: The SQL expression for the point or interval being tested.
            right: The SQL expression for the interval.
            precision: Optional precision modifier (e.g., 'day', 'hour').
            context: The translation context.

        Returns:
            SQL expression for the during check.

        CQL Examples:
            x during Interval[@2024-01-01, @2024-12-31]
            x during day of y
        """
        ctx = context or self.context

        if precision:
            # With precision: truncate both sides to the precision level
            truncate_fn = PRECISION_TRUNCATE_FUNCTIONS.get(precision.lower())
            if truncate_fn:
                # For precision-based during, we compare truncated values
                # left during day of right means DATE(left) is between dates of right interval
                left_truncated = SQLFunctionCall(
                    name="DATE" if precision.lower() == "day" else "DATE_TRUNC",
                    args=[SQLLiteral(precision.lower())] if precision.lower() != "day" else [] +
                          ([left] if precision.lower() == "day" else [SQLLiteral(precision.lower()), left]),
                )
                # Fix for day precision
                if precision.lower() == "day":
                    left_truncated = SQLCast(expression=left, target_type="DATE")

                # Get interval bounds and truncate them
                right_start = SQLFunctionCall(name="intervalStart", args=[right])
                right_end = SQLFunctionCall(name="intervalEnd", args=[right])

                start_truncated = SQLCast(expression=right_start, target_type="DATE")
                end_truncated = SQLCast(expression=right_end, target_type="DATE")

                # Build BETWEEN expression
                return SQLBinaryOp(
                    operator="BETWEEN",
                    left=left_truncated,
                    right=SQLFunctionCall(
                        name="__between_args__",
                        args=[start_truncated, end_truncated],
                    ),
                    precedence=PRECEDENCE["BETWEEN"],
                )
            # else: fall through to UDF

        # Use intervalContains UDF for general case
        return SQLFunctionCall(
            name="intervalContains",
            args=[right, left],
        )

    def translate_includes(
        self,
        left: SQLExpression,
        right: SQLExpression,
        precision: Optional[str] = None,
        context: Optional[SQLTranslationContext] = None,
    ) -> SQLExpression:
        """
        Translate 'x includes y' - interval inclusion.

        Checks if the left interval includes the right point or interval.

        Args:
            left: The SQL expression for the interval.
            right: The SQL expression for the point or interval being tested.
            precision: Optional precision modifier.
            context: The translation context.

        Returns:
            SQL expression for the includes check.
        """
        ctx = context or self.context

        if precision:
            # Precision-based includes - similar to during but reversed
            truncate_fn = PRECISION_TRUNCATE_FUNCTIONS.get(precision.lower())
            if truncate_fn and precision.lower() == "day":
                # For day precision, check if the date of right is within dates of left
                right_truncated = SQLCast(expression=right, target_type="DATE")

                left_start = SQLFunctionCall(name="intervalStart", args=[left])
                left_end = SQLFunctionCall(name="intervalEnd", args=[left])

                start_truncated = SQLCast(expression=left_start, target_type="DATE")
                end_truncated = SQLCast(expression=left_end, target_type="DATE")

                return SQLBinaryOp(
                    operator="BETWEEN",
                    left=right_truncated,
                    right=SQLFunctionCall(
                        name="__between_args__",
                        args=[start_truncated, end_truncated],
                    ),
                    precedence=PRECEDENCE["BETWEEN"],
                )

        # Use intervalContains UDF (reversed arguments from during)
        return SQLFunctionCall(
            name="intervalContains",
            args=[left, right],
        )

    def translate_overlaps(
        self,
        left: SQLExpression,
        right: SQLExpression,
        context: Optional[SQLTranslationContext] = None,
    ) -> SQLExpression:
        """
        Translate 'x overlaps y' - interval overlap.

        Checks if two intervals overlap (have any points in common).

        Args:
            left: The SQL expression for the first interval.
            right: The SQL expression for the second interval.
            context: The translation context.

        Returns:
            SQL expression for the overlaps check.
        """
        return SQLFunctionCall(
            name="intervalOverlaps",
            args=[left, right],
        )

    def translate_overlaps_before(
        self,
        left: SQLExpression,
        right: SQLExpression,
        context: Optional[SQLTranslationContext] = None,
    ) -> SQLExpression:
        """
        Translate 'x overlaps before y' - interval overlaps before.

        Checks if left interval overlaps right interval and starts before it.

        Args:
            left: The SQL expression for the first interval.
            right: The SQL expression for the second interval.
            context: The translation context.

        Returns:
            SQL expression for the overlaps before check.
        """
        # overlaps before: left overlaps right AND start of left < start of right
        overlaps_expr = SQLFunctionCall(
            name="intervalOverlaps",
            args=[left, right],
        )

        left_start = SQLFunctionCall(name="intervalStart", args=[left])
        right_start = SQLFunctionCall(name="intervalStart", args=[right])

        starts_before = SQLBinaryOp(
            operator="<",
            left=left_start,
            right=right_start,
        )

        return SQLBinaryOp(
            operator="AND",
            left=overlaps_expr,
            right=starts_before,
        )

    def translate_overlaps_after(
        self,
        left: SQLExpression,
        right: SQLExpression,
        context: Optional[SQLTranslationContext] = None,
    ) -> SQLExpression:
        """
        Translate 'x overlaps after y' - interval overlaps after.

        Checks if left interval overlaps right interval and starts after it.

        Args:
            left: The SQL expression for the first interval.
            right: The SQL expression for the second interval.
            context: The translation context.

        Returns:
            SQL expression for the overlaps after check.
        """
        # overlaps after: left overlaps right AND start of left > start of right
        overlaps_expr = SQLFunctionCall(
            name="intervalOverlaps",
            args=[left, right],
        )

        left_start = SQLFunctionCall(name="intervalStart", args=[left])
        right_start = SQLFunctionCall(name="intervalStart", args=[right])

        starts_after = SQLBinaryOp(
            operator=">",
            left=left_start,
            right=right_start,
        )

        return SQLBinaryOp(
            operator="AND",
            left=overlaps_expr,
            right=starts_after,
        )

    def translate_before(
        self,
        left: SQLExpression,
        right: SQLExpression,
        precision: Optional[str] = None,
        context: Optional[SQLTranslationContext] = None,
    ) -> SQLExpression:
        """
        Translate 'x before y' - temporal ordering.

        Checks if left occurs strictly before right.

        Args:
            left: The SQL expression for the first point/interval.
            right: The SQL expression for the second point/interval.
            precision: Optional precision modifier.
            context: The translation context.

        Returns:
            SQL expression for the before check.
        """
        ctx = context or self.context

        if precision:
            # For precision-based comparison, compare truncated values
            if precision.lower() in PRECISION_TRUNCATE_FUNCTIONS:
                left_truncated = self._truncate_to_precision(left, precision)
                right_truncated = self._truncate_to_precision(right, precision)
                return SQLBinaryOp(
                    operator="<",
                    left=left_truncated,
                    right=right_truncated,
                )

        # Standard comparison
        return SQLBinaryOp(
            operator="<",
            left=left,
            right=right,
        )

    def translate_after(
        self,
        left: SQLExpression,
        right: SQLExpression,
        precision: Optional[str] = None,
        context: Optional[SQLTranslationContext] = None,
    ) -> SQLExpression:
        """
        Translate 'x after y' - temporal ordering.

        Checks if left occurs strictly after right.

        Args:
            left: The SQL expression for the first point/interval.
            right: The SQL expression for the second point/interval.
            precision: Optional precision modifier.
            context: The translation context.

        Returns:
            SQL expression for the after check.
        """
        ctx = context or self.context

        if precision:
            if precision.lower() in PRECISION_TRUNCATE_FUNCTIONS:
                left_truncated = self._truncate_to_precision(left, precision)
                right_truncated = self._truncate_to_precision(right, precision)
                return SQLBinaryOp(
                    operator=">",
                    left=left_truncated,
                    right=right_truncated,
                )

        return SQLBinaryOp(
            operator=">",
            left=left,
            right=right,
        )

    def translate_same_as(
        self,
        left: SQLExpression,
        right: SQLExpression,
        precision: Optional[str] = None,
    ) -> SQLExpression:
        """
        Translate 'x same day as y' - precision-based equality.

        Checks if left and right are the same at the specified precision.

        Args:
            left: The SQL expression for the first value.
            right: The SQL expression for the second value.
            precision: The precision level (e.g., 'day', 'hour', 'month').

        Returns:
            SQL expression for the same-as comparison.

        CQL Examples:
            x same day as y  -> DATE(x) = DATE(y)
            x same hour as y -> DATE_TRUNC('hour', x) = DATE_TRUNC('hour', y)
        """
        if precision and precision.lower() in PRECISION_TRUNCATE_FUNCTIONS:
            left_truncated = self._truncate_to_precision(left, precision)
            right_truncated = self._truncate_to_precision(right, precision)
            return SQLBinaryOp(
                operator="=",
                left=left_truncated,
                right=right_truncated,
            )

        # Default: exact equality
        return SQLBinaryOp(
            operator="=",
            left=left,
            right=right,
        )

    def translate_on_or_before(
        self,
        left: SQLExpression,
        right: SQLExpression,
        precision: Optional[str] = None,
    ) -> SQLExpression:
        """
        Translate 'x on or before y' - inclusive comparison.

        Checks if left is on or before right, considering the precision.
        For datetime values, this includes both the direct comparison and
        the date equality check.

        Args:
            left: The SQL expression for the first value.
            right: The SQL expression for the second value.
            precision: Optional precision (defaults to 'day' for datetime).

        Returns:
            SQL expression for the on-or-before comparison.

        SQL Pattern:
            x on or before y -> x <= y OR DATE(x) = DATE(y)
        """
        # Direct comparison: left <= right
        direct_comparison = SQLBinaryOp(
            operator="<=",
            left=left,
            right=right,
        )

        # For datetime values, also check date equality
        # This handles the case where times are different but dates are the same
        if precision is None or precision.lower() == "day":
            left_date = SQLCast(expression=left, target_type="DATE")
            right_date = SQLCast(expression=right, target_type="DATE")

            date_equality = SQLBinaryOp(
                operator="=",
                left=left_date,
                right=right_date,
            )

            return SQLBinaryOp(
                operator="OR",
                left=direct_comparison,
                right=date_equality,
            )

        # For other precisions, use truncated comparison
        if precision and precision.lower() in PRECISION_TRUNCATE_FUNCTIONS:
            left_truncated = self._truncate_to_precision(left, precision)
            right_truncated = self._truncate_to_precision(right, precision)

            truncated_le = SQLBinaryOp(
                operator="<=",
                left=left_truncated,
                right=right_truncated,
            )

            return truncated_le

        return direct_comparison

    def translate_on_or_after(
        self,
        left: SQLExpression,
        right: SQLExpression,
        precision: Optional[str] = None,
    ) -> SQLExpression:
        """
        Translate 'x on or after y' - inclusive comparison.

        Checks if left is on or after right, considering the precision.
        For datetime values, this includes both the direct comparison and
        the date equality check.

        Args:
            left: The SQL expression for the first value.
            right: The SQL expression for the second value.
            precision: Optional precision (defaults to 'day' for datetime).

        Returns:
            SQL expression for the on-or-after comparison.

        SQL Pattern:
            x on or after y -> x >= y OR DATE(x) = DATE(y)
        """
        # Direct comparison: left >= right
        direct_comparison = SQLBinaryOp(
            operator=">=",
            left=left,
            right=right,
        )

        # For datetime values, also check date equality
        if precision is None or precision.lower() == "day":
            left_date = SQLCast(expression=left, target_type="DATE")
            right_date = SQLCast(expression=right, target_type="DATE")

            date_equality = SQLBinaryOp(
                operator="=",
                left=left_date,
                right=right_date,
            )

            return SQLBinaryOp(
                operator="OR",
                left=direct_comparison,
                right=date_equality,
            )

        # For other precisions, use truncated comparison
        if precision and precision.lower() in PRECISION_TRUNCATE_FUNCTIONS:
            left_truncated = self._truncate_to_precision(left, precision)
            right_truncated = self._truncate_to_precision(right, precision)

            truncated_ge = SQLBinaryOp(
                operator=">=",
                left=left_truncated,
                right=right_truncated,
            )

            return truncated_ge

        return direct_comparison

    def translate_starts(
        self,
        interval: SQLExpression,
        context: Optional[SQLTranslationContext] = None,
    ) -> SQLExpression:
        """
        Translate 'start of x' - get interval start.

        Returns the start boundary of an interval.

        Args:
            interval: The SQL expression for the interval.
            context: The translation context.

        Returns:
            SQL expression for the interval start.
        """
        return SQLFunctionCall(
            name="intervalStart",
            args=[interval],
        )

    def translate_ends(
        self,
        interval: SQLExpression,
        context: Optional[SQLTranslationContext] = None,
    ) -> SQLExpression:
        """
        Translate 'end of x' - get interval end.

        Returns the end boundary of an interval.

        Args:
            interval: The SQL expression for the interval.
            context: The translation context.

        Returns:
            SQL expression for the interval end.
        """
        return SQLFunctionCall(
            name="intervalEnd",
            args=[interval],
        )

    def translate_meets(
        self,
        left: SQLExpression,
        right: SQLExpression,
        context: Optional[SQLTranslationContext] = None,
    ) -> SQLExpression:
        """
        Translate 'x meets y' - adjacent intervals.

        Checks if two intervals are adjacent (end of left = start of right
        OR start of left = end of right).

        Args:
            left: The SQL expression for the first interval.
            right: The SQL expression for the second interval.
            context: The translation context.

        Returns:
            SQL expression for the meets check.
        """
        left_end = SQLFunctionCall(name="intervalEnd", args=[left])
        right_start = SQLFunctionCall(name="intervalStart", args=[right])

        left_start = SQLFunctionCall(name="intervalStart", args=[left])
        right_end = SQLFunctionCall(name="intervalEnd", args=[right])

        # meets: end of left = start of right OR start of left = end of right
        meets_before = SQLBinaryOp(
            operator="=",
            left=left_end,
            right=right_start,
        )

        meets_after = SQLBinaryOp(
            operator="=",
            left=left_start,
            right=right_end,
        )

        return SQLBinaryOp(
            operator="OR",
            left=meets_before,
            right=meets_after,
        )

    def translate_meets_before(
        self,
        left: SQLExpression,
        right: SQLExpression,
        context: Optional[SQLTranslationContext] = None,
    ) -> SQLExpression:
        """
        Translate 'x meets before y' - left interval ends where right starts.

        Checks if end of left interval equals start of right interval.

        Args:
            left: The SQL expression for the first interval.
            right: The SQL expression for the second interval.
            context: The translation context.

        Returns:
            SQL expression for the meets-before check.
        """
        left_end = SQLFunctionCall(name="intervalEnd", args=[left])
        right_start = SQLFunctionCall(name="intervalStart", args=[right])

        return SQLBinaryOp(
            operator="=",
            left=left_end,
            right=right_start,
        )

    def translate_meets_after(
        self,
        left: SQLExpression,
        right: SQLExpression,
        context: Optional[SQLTranslationContext] = None,
    ) -> SQLExpression:
        """
        Translate 'x meets after y' - left interval starts where right ends.

        Checks if start of left interval equals end of right interval.

        Args:
            left: The SQL expression for the first interval.
            right: The SQL expression for the second interval.
            context: The translation context.

        Returns:
            SQL expression for the meets-after check.
        """
        left_start = SQLFunctionCall(name="intervalStart", args=[left])
        right_end = SQLFunctionCall(name="intervalEnd", args=[right])

        return SQLBinaryOp(
            operator="=",
            left=left_start,
            right=right_end,
        )

    def translate_starts_on_or_before(
        self,
        left: SQLExpression,
        right: SQLExpression,
        context: Optional[SQLTranslationContext] = None,
    ) -> SQLExpression:
        """
        Translate 'x starts on or before y' - interval starts on or before.

        Checks if the start of left interval is on or before right.

        Args:
            left: The SQL expression for the interval.
            right: The SQL expression for the point/interval.
            context: The translation context.

        Returns:
            SQL expression for the starts-on-or-before check.
        """
        left_start = SQLFunctionCall(name="intervalStart", args=[left])
        return self.translate_on_or_before(left_start, right)

    def translate_starts_on_or_after(
        self,
        left: SQLExpression,
        right: SQLExpression,
        context: Optional[SQLTranslationContext] = None,
    ) -> SQLExpression:
        """
        Translate 'x starts on or after y' - interval starts on or after.

        Checks if the start of left interval is on or after right.

        Args:
            left: The SQL expression for the interval.
            right: The SQL expression for the point/interval.
            context: The translation context.

        Returns:
            SQL expression for the starts-on-or-after check.
        """
        left_start = SQLFunctionCall(name="intervalStart", args=[left])
        return self.translate_on_or_after(left_start, right)

    def translate_ends_on_or_before(
        self,
        left: SQLExpression,
        right: SQLExpression,
        context: Optional[SQLTranslationContext] = None,
    ) -> SQLExpression:
        """
        Translate 'x ends on or before y' - interval ends on or before.

        Checks if the end of left interval is on or before right.

        Args:
            left: The SQL expression for the interval.
            right: The SQL expression for the point/interval.
            context: The translation context.

        Returns:
            SQL expression for the ends-on-or-before check.
        """
        left_end = SQLFunctionCall(name="intervalEnd", args=[left])
        return self.translate_on_or_before(left_end, right)

    def translate_ends_on_or_after(
        self,
        left: SQLExpression,
        right: SQLExpression,
        context: Optional[SQLTranslationContext] = None,
    ) -> SQLExpression:
        """
        Translate 'x ends on or after y' - interval ends on or after.

        Checks if the end of left interval is on or after right.

        Args:
            left: The SQL expression for the interval.
            right: The SQL expression for the point/interval.
            context: The translation context.

        Returns:
            SQL expression for the ends-on-or-after check.
        """
        left_end = SQLFunctionCall(name="intervalEnd", args=[left])
        return self.translate_on_or_after(left_end, right)

    def _truncate_to_precision(
        self,
        expr: SQLExpression,
        precision: str,
    ) -> SQLExpression:
        """
        Truncate an expression to the specified precision.

        Args:
            expr: The SQL expression to truncate.
            precision: The precision level (e.g., 'day', 'hour', 'month').

        Returns:
            SQL expression for the truncated value.
        """
        precision_lower = precision.lower()

        if precision_lower == "day":
            return SQLCast(expression=expr, target_type="DATE")
        elif precision_lower in PRECISION_TRUNCATE_FUNCTIONS:
            return SQLFunctionCall(
                name="DATE_TRUNC",
                args=[SQLLiteral(precision_lower), expr],
            )
        else:
            # Unknown precision - return as-is
            return expr


__all__ = [
    "TemporalTranslator",
    "PRECISION_LEVELS",
    "PRECISION_TRUNCATE_FUNCTIONS",
]
