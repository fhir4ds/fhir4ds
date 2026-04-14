"""
Interval pattern translator for CQL interval operations.

This module provides the IntervalTranslator class for translating CQL interval
constructs and operations to DuckDB SQL.

CQL Interval Syntax:
    Interval[low, high]   - closed interval (inclusive on both ends)
    Interval(low, high]   - open on low, closed on high
    Interval[low, high)   - closed on low, open on high (most common for dates)
    Interval(low, high)   - open interval (exclusive on both ends)

Interval Operations:
    start of I            - get the start point of the interval
    end of I              - get the end point of the interval
    width of I            - calculate the width (end - start)
    contains(I, point)    - check if point is in interval
    properly includes(I1, I2) - check if I1 strictly contains I2
    overlaps(I1, I2)      - check if intervals overlap

SQL Pattern (DuckDB):
    -- Interval construction (as struct)
    {'low': start_val, 'high': end_val, 'lowClosed': true, 'highClosed': false}

    -- start of / end of
    interval.low
    interval.high

    -- width (UDF)
    interval_width(interval)

    -- contains (UDF)
    interval_contains(interval, point)

    -- overlaps (UDF)
    interval_overlaps(left, right)
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from ...translator.types import (
    SQLExpression,
    SQLInterval,
    SQLLiteral,
    SQLFunctionCall,
    SQLBinaryOp,
    SQLCase,
    PRECEDENCE,
)

if TYPE_CHECKING:
    from ...translator.context import SQLTranslationContext


class IntervalTranslator:
    """
    Translates CQL interval constructs to DuckDB SQL.

    The IntervalTranslator handles the translation of CQL interval literals
    and operations to their DuckDB SQL equivalents using struct representation.

    Interval JSON format:
        {
            "low": "2026-01-01T00:00:00Z",
            "high": "2026-12-31T23:59:59Z",
            "lowClosed": true,
            "highClosed": false
        }

    Example CQL:
        Interval[2026-01-01, 2026-12-31]
        start of MeasurementPeriod
        contains(Interval[1, 10], 5)

    Generated SQL:
        {'low': '2026-01-01', 'high': '2026-12-31', 'lowClosed': true, 'highClosed': true}
        MeasurementPeriod.low
        interval_contains({'low': 1, 'high': 10, 'lowClosed': true, 'highClosed': true}, 5)
    """

    def __init__(self, context: SQLTranslationContext):
        """
        Initialize the interval translator.

        Args:
            context: The translation context for symbol resolution.
        """
        self.context = context

    def construct_interval(
        self,
        low: SQLExpression,
        high: SQLExpression,
        low_closed: bool,
        high_closed: bool,
        context: SQLTranslationContext,
    ) -> SQLExpression:
        """
        Construct a SQL interval struct from bounds.

        Creates a DuckDB struct representing a CQL interval with the
        specified bounds and openness/closedness.

        Args:
            low: SQL expression for the low bound.
            high: SQL expression for the high bound.
            low_closed: True if low bound is inclusive ([), False if exclusive (().
            high_closed: True if high bound is inclusive (]), False if exclusive ()).
            context: The translation context.

        Returns:
            SQLInterval expression representing the interval.
        """
        return SQLInterval(
            low=low,
            high=high,
            low_closed=low_closed,
            high_closed=high_closed,
        )

    def construct_closed_interval(
        self,
        low: SQLExpression,
        high: SQLExpression,
        context: SQLTranslationContext,
    ) -> SQLExpression:
        """
        Construct a closed interval [low, high].

        Args:
            low: SQL expression for the low bound.
            high: SQL expression for the high bound.
            context: The translation context.

        Returns:
            SQLInterval expression with both bounds closed.
        """
        return self.construct_interval(low, high, True, True, context)

    def construct_open_low_interval(
        self,
        low: SQLExpression,
        high: SQLExpression,
        context: SQLTranslationContext,
    ) -> SQLExpression:
        """
        Construct an interval open on low (low, high].

        Args:
            low: SQL expression for the low bound.
            high: SQL expression for the high bound.
            context: The translation context.

        Returns:
            SQLInterval expression with low open, high closed.
        """
        return self.construct_interval(low, high, False, True, context)

    def construct_open_high_interval(
        self,
        low: SQLExpression,
        high: SQLExpression,
        context: SQLTranslationContext,
    ) -> SQLExpression:
        """
        Construct an interval open on high [low, high).

        This is the most common pattern for date ranges in CQL.

        Args:
            low: SQL expression for the low bound.
            high: SQL expression for the high bound.
            context: The translation context.

        Returns:
            SQLInterval expression with low closed, high open.
        """
        return self.construct_interval(low, high, True, False, context)

    def construct_open_interval(
        self,
        low: SQLExpression,
        high: SQLExpression,
        context: SQLTranslationContext,
    ) -> SQLExpression:
        """
        Construct a fully open interval (low, high).

        Args:
            low: SQL expression for the low bound.
            high: SQL expression for the high bound.
            context: The translation context.

        Returns:
            SQLInterval expression with both bounds open.
        """
        return self.construct_interval(low, high, False, False, context)

    def translate_start_of(
        self,
        interval: SQLExpression,
    ) -> SQLExpression:
        """
        Translate 'start of interval' to SQL.

        In CQL, 'start of I' returns the starting point of the interval,
        regardless of whether the interval is open or closed on the low end.

        For struct representation, this extracts the 'low' field.

        Args:
            interval: SQL expression representing the interval.

        Returns:
            SQLFunctionCall to extract the low bound.
        """
        # Access the 'low' field from the interval struct
        # Using struct extraction syntax: interval.low
        # In DuckDB, we can use struct extraction or json_extract_string
        return SQLFunctionCall(
            name="struct_extract",
            args=[interval, SQLLiteral("low")],
        )

    def translate_end_of(
        self,
        interval: SQLExpression,
    ) -> SQLExpression:
        """
        Translate 'end of interval' to SQL.

        In CQL, 'end of I' returns the ending point of the interval,
        regardless of whether the interval is open or closed on the high end.

        For struct representation, this extracts the 'high' field.

        Args:
            interval: SQL expression representing the interval.

        Returns:
            SQLFunctionCall to extract the high bound.
        """
        return SQLFunctionCall(
            name="struct_extract",
            args=[interval, SQLLiteral("high")],
        )

    def translate_width_of(
        self,
        interval: SQLExpression,
    ) -> SQLExpression:
        """
        Translate 'width of interval' to SQL.

        In CQL, 'width of I' returns the difference between the end
        and start of the interval: end - start.

        For DuckDB, we can either:
        1. Use a UDF: interval_width(interval)
        2. Compute inline: struct_extract(interval, 'high') - struct_extract(interval, 'low')

        We use a UDF for consistency with other interval operations and
        to handle type-specific width calculations (e.g., date differences).

        Args:
            interval: SQL expression representing the interval.

        Returns:
            SQLFunctionCall for interval_width UDF.
        """
        return SQLFunctionCall(
            name="intervalWidth",
            args=[interval],
        )

    def translate_contains(
        self,
        interval: SQLExpression,
        point: SQLExpression,
    ) -> SQLExpression:
        """
        Translate 'contains(interval, point)' to SQL.

        In CQL, 'contains(I, P)' returns true if point P is within
        the interval I, respecting the openness/closedness of bounds.

        For [low, high]: low <= P <= high
        For (low, high]: low < P <= high
        For [low, high): low <= P < high
        For (low, high): low < P < high

        Args:
            interval: SQL expression representing the interval.
            point: SQL expression for the point to test.

        Returns:
            SQLFunctionCall for interval_contains UDF.
        """
        return SQLFunctionCall(
            name="interval_contains",
            args=[interval, point],
        )

    def translate_in_interval(
        self,
        point: SQLExpression,
        interval: SQLExpression,
    ) -> SQLExpression:
        """
        Translate 'point in interval' to SQL.

        In CQL, 'P in I' is equivalent to 'contains(I, P)' but with
        the operands reversed.

        Args:
            point: SQL expression for the point to test.
            interval: SQL expression representing the interval.

        Returns:
            SQLFunctionCall for interval_contains UDF.
        """
        return self.translate_contains(interval, point)

    def translate_properly_includes(
        self,
        left: SQLExpression,
        right: SQLExpression,
    ) -> SQLExpression:
        """
        Translate 'properly includes(left, right)' to SQL.

        In CQL, 'properly includes(A, B)' returns true if interval A
        strictly contains interval B (i.e., B is a proper subset of A).

        This means:
        - A.start < B.start (strictly less, considering closedness)
        - A.end > B.end (strictly greater, considering closedness)

        Args:
            left: SQL expression for the containing interval (A).
            right: SQL expression for the contained interval (B).

        Returns:
            SQLFunctionCall for interval_properly_includes UDF.
        """
        return SQLFunctionCall(
            name="interval_properly_includes",
            args=[left, right],
        )

    def translate_includes(
        self,
        left: SQLExpression,
        right: SQLExpression,
    ) -> SQLExpression:
        """
        Translate 'includes(left, right)' to SQL.

        In CQL, 'includes(A, B)' returns true if interval A contains
        interval B (B is a subset of A, possibly equal).

        Args:
            left: SQL expression for the containing interval (A).
            right: SQL expression for the contained interval (B).

        Returns:
            SQLFunctionCall for interval_includes UDF.
        """
        return SQLFunctionCall(
            name="interval_includes",
            args=[left, right],
        )

    def translate_overlaps_expr(
        self,
        left: SQLExpression,
        right: SQLExpression,
    ) -> SQLExpression:
        """
        Translate 'overlaps(left, right)' to SQL.

        In CQL, 'overlaps(A, B)' returns true if the intervals A and B
        share any points in common.

        For closed intervals: max(A.start, B.start) <= min(A.end, B.end)
        With open/closed bounds, this becomes more complex.

        Args:
            left: SQL expression for the first interval.
            right: SQL expression for the second interval.

        Returns:
            SQLFunctionCall for interval_overlaps UDF.
        """
        return SQLFunctionCall(
            name="interval_overlaps",
            args=[left, right],
        )

    def translate_overlaps_before(
        self,
        left: SQLExpression,
        right: SQLExpression,
    ) -> SQLExpression:
        """
        Translate 'overlaps before(left, right)' to SQL.

        In CQL, 'A overlaps before B' means A overlaps with B and
        A starts before B.

        Args:
            left: SQL expression for the first interval.
            right: SQL expression for the second interval.

        Returns:
            SQLFunctionCall for interval_overlaps_before UDF.
        """
        return SQLFunctionCall(
            name="interval_overlaps_before",
            args=[left, right],
        )

    def translate_overlaps_after(
        self,
        left: SQLExpression,
        right: SQLExpression,
    ) -> SQLExpression:
        """
        Translate 'overlaps after(left, right)' to SQL.

        In CQL, 'A overlaps after B' means A overlaps with B and
        A starts after B.

        Args:
            left: SQL expression for the first interval.
            right: SQL expression for the second interval.

        Returns:
            SQLFunctionCall for interval_overlaps_after UDF.
        """
        return SQLFunctionCall(
            name="interval_overlaps_after",
            args=[left, right],
        )

    def translate_before(
        self,
        left: SQLExpression,
        right: SQLExpression,
    ) -> SQLExpression:
        """
        Translate 'before(left, right)' to SQL.

        In CQL, 'A before B' means interval A ends before interval B starts.

        Args:
            left: SQL expression for the first interval.
            right: SQL expression for the second interval.

        Returns:
            SQLFunctionCall for interval_before UDF.
        """
        return SQLFunctionCall(
            name="interval_before",
            args=[left, right],
        )

    def translate_after(
        self,
        left: SQLExpression,
        right: SQLExpression,
    ) -> SQLExpression:
        """
        Translate 'after(left, right)' to SQL.

        In CQL, 'A after B' means interval A starts after interval B ends.

        Args:
            left: SQL expression for the first interval.
            right: SQL expression for the second interval.

        Returns:
            SQLFunctionCall for interval_after UDF.
        """
        return SQLFunctionCall(
            name="interval_after",
            args=[left, right],
        )

    def translate_meets(
        self,
        left: SQLExpression,
        right: SQLExpression,
    ) -> SQLExpression:
        """
        Translate 'meets(left, right)' to SQL.

        In CQL, 'A meets B' means interval A ends exactly where B starts.

        Args:
            left: SQL expression for the first interval.
            right: SQL expression for the second interval.

        Returns:
            SQLFunctionCall for interval_meets UDF.
        """
        return SQLFunctionCall(
            name="interval_meets",
            args=[left, right],
        )

    def translate_meets_before(
        self,
        left: SQLExpression,
        right: SQLExpression,
    ) -> SQLExpression:
        """
        Translate 'meets before(left, right)' to SQL.

        In CQL, 'A meets before B' means A's end meets B's start.

        Args:
            left: SQL expression for the first interval.
            right: SQL expression for the second interval.

        Returns:
            SQLFunctionCall for interval_meets_before UDF.
        """
        return SQLFunctionCall(
            name="interval_meets_before",
            args=[left, right],
        )

    def translate_meets_after(
        self,
        left: SQLExpression,
        right: SQLExpression,
    ) -> SQLExpression:
        """
        Translate 'meets after(left, right)' to SQL.

        In CQL, 'A meets after B' means A's start meets B's end.

        Args:
            left: SQL expression for the first interval.
            right: SQL expression for the second interval.

        Returns:
            SQLFunctionCall for interval_meets_after UDF.
        """
        return SQLFunctionCall(
            name="interval_meets_after",
            args=[left, right],
        )

    def translate_starts(
        self,
        left: SQLExpression,
        right: SQLExpression,
    ) -> SQLExpression:
        """
        Translate 'starts(left, right)' to SQL.

        In CQL, 'A starts B' means interval A starts at the same point as B,
        but may end before B.

        Args:
            left: SQL expression for the first interval.
            right: SQL expression for the second interval.

        Returns:
            SQLFunctionCall for interval_starts UDF.
        """
        return SQLFunctionCall(
            name="interval_starts",
            args=[left, right],
        )

    def translate_ends(
        self,
        left: SQLExpression,
        right: SQLExpression,
    ) -> SQLExpression:
        """
        Translate 'ends(left, right)' to SQL.

        In CQL, 'A ends B' means interval A ends at the same point as B,
        but may start after B.

        Args:
            left: SQL expression for the first interval.
            right: SQL expression for the second interval.

        Returns:
            SQLFunctionCall for interval_ends UDF.
        """
        return SQLFunctionCall(
            name="interval_ends",
            args=[left, right],
        )

    def translate_union(
        self,
        left: SQLExpression,
        right: SQLExpression,
    ) -> SQLExpression:
        """
        Translate interval union to SQL.

        In CQL, 'A union B' returns the smallest interval that contains
        both A and B (if they overlap or meet).

        Args:
            left: SQL expression for the first interval.
            right: SQL expression for the second interval.

        Returns:
            SQLFunctionCall for interval_union UDF.
        """
        return SQLFunctionCall(
            name="interval_union",
            args=[left, right],
        )

    def translate_intersect(
        self,
        left: SQLExpression,
        right: SQLExpression,
    ) -> SQLExpression:
        """
        Translate interval intersect to SQL.

        In CQL, 'A intersect B' returns the interval representing the
        intersection of A and B, or null if they don't overlap.

        Args:
            left: SQL expression for the first interval.
            right: SQL expression for the second interval.

        Returns:
            SQLFunctionCall for interval_intersect UDF.
        """
        return SQLFunctionCall(
            name="interval_intersect",
            args=[left, right],
        )

    def translate_except(
        self,
        left: SQLExpression,
        right: SQLExpression,
    ) -> SQLExpression:
        """
        Translate interval except to SQL.

        In CQL, 'A except B' returns the parts of A that are not in B.
        This can result in null (if B contains A) or an interval.

        Args:
            left: SQL expression for the first interval.
            right: SQL expression for the second interval.

        Returns:
            SQLFunctionCall for interval_except UDF.
        """
        return SQLFunctionCall(
            name="interval_except",
            args=[left, right],
        )

    def translate_collapse(
        self,
        intervals: SQLExpression,
    ) -> SQLExpression:
        """
        Translate interval collapse to SQL.

        In CQL, 'collapse list<Interval<T>>' merges overlapping or adjacent
        intervals into a minimal set of disjoint intervals.

        This is a complex operation that requires:
        1. Sorting intervals by start point
        2. Merging overlapping/adjacent intervals
        3. Returning the resulting list of intervals

        For DuckDB, this requires a custom UDF or window function pattern.

        Args:
            intervals: SQL expression for the list of intervals to collapse.

        Returns:
            SQLFunctionCall for collapse_intervals UDF.

        NOTE (REM-27): collapse_intervals UDF is not yet implemented in the DuckDB extension.
        Not blocking CMS165 or other current measures. The UDF should:
        - Accept a list of interval structs
        - Sort by interval.low
        - Merge overlapping/adjacent intervals
        - Return a list of collapsed interval structs
        """
        return SQLFunctionCall(
            name="collapse_intervals",
            args=[intervals],
        )

    def translate_expand(
        self,
        interval: SQLExpression,
        per: Optional[SQLExpression] = None,
    ) -> SQLExpression:
        """
        Translate interval expand to SQL.

        In CQL, 'expand I per Q' expands an interval into a list of
        points spaced by the quantity Q.

        Args:
            interval: SQL expression for the interval.
            per: Optional SQL expression for the expansion granularity.

        Returns:
            SQLFunctionCall for interval_expand UDF.
        """
        args = [interval]
        if per is not None:
            args.append(per)
        return SQLFunctionCall(
            name="interval_expand",
            args=args,
        )

    def translate_size(
        self,
        interval: SQLExpression,
    ) -> SQLExpression:
        """
        Translate 'size of interval' to SQL.

        In CQL, 'size of I' returns the number of discrete values in the
        interval (for integer/quantity intervals). For continuous intervals
        like DateTime, this may return the width.

        Note: In many cases, size is equivalent to width.

        Args:
            interval: SQL expression representing the interval.

        Returns:
            SQLFunctionCall for interval_size UDF.
        """
        return SQLFunctionCall(
            name="interval_size",
            args=[interval],
        )


# Convenience functions for direct use without instantiating the class

def construct_interval(
    low: SQLExpression,
    high: SQLExpression,
    low_closed: bool,
    high_closed: bool,
    context: SQLTranslationContext,
) -> SQLExpression:
    """
    Convenience function to construct an interval.

    Args:
        low: SQL expression for the low bound.
        high: SQL expression for the high bound.
        low_closed: True if low bound is inclusive.
        high_closed: True if high bound is inclusive.
        context: The translation context.

    Returns:
        SQLInterval expression representing the interval.
    """
    return SQLInterval(
        low=low,
        high=high,
        low_closed=low_closed,
        high_closed=high_closed,
    )


def translate_start_of(interval: SQLExpression) -> SQLExpression:
    """Convenience function for start of interval."""
    return SQLFunctionCall(
        name="struct_extract",
        args=[interval, SQLLiteral("low")],
    )


def translate_end_of(interval: SQLExpression) -> SQLExpression:
    """Convenience function for end of interval."""
    return SQLFunctionCall(
        name="struct_extract",
        args=[interval, SQLLiteral("high")],
    )


def translate_width_of(interval: SQLExpression) -> SQLExpression:
    """Convenience function for width of interval."""
    return SQLFunctionCall(
        name="intervalWidth",
        args=[interval],
    )


def translate_contains(interval: SQLExpression, point: SQLExpression) -> SQLExpression:
    """Convenience function for interval contains point."""
    return SQLFunctionCall(
        name="interval_contains",
        args=[interval, point],
    )


def translate_overlaps_expr(left: SQLExpression, right: SQLExpression) -> SQLExpression:
    """Convenience function for interval overlaps."""
    return SQLFunctionCall(
        name="interval_overlaps",
        args=[left, right],
    )


def translate_collapse(intervals: SQLExpression) -> SQLExpression:
    """
    Convenience function for collapsing a list of intervals.

    In CQL, 'collapse list<Interval<T>>' merges overlapping or adjacent
    intervals into a minimal set of disjoint intervals.

    Args:
        intervals: SQL expression for the list of intervals to collapse.

    Returns:
        SQLFunctionCall for collapse_intervals UDF.
    """
    return SQLFunctionCall(
        name="collapse_intervals",
        args=[intervals],
    )


def translate_expand(
    interval: SQLExpression,
    per: Optional[SQLExpression] = None,
) -> SQLExpression:
    """
    Convenience function for expanding an interval into a list of points.

    In CQL, 'expand I per Q' expands an interval into a list of
    points spaced by the quantity Q.

    Args:
        interval: SQL expression for the interval.
        per: Optional SQL expression for the expansion granularity.

    Returns:
        SQLFunctionCall for interval_expand UDF.
    """
    args = [interval]
    if per is not None:
        args.append(per)
    return SQLFunctionCall(
        name="interval_expand",
        args=args,
    )


__all__ = [
    "IntervalTranslator",
    "construct_interval",
    "translate_start_of",
    "translate_end_of",
    "translate_width_of",
    "translate_contains",
    "translate_overlaps_expr",
    "translate_collapse",
    "translate_expand",
]
