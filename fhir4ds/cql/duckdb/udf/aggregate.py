"""
Statistical aggregate UDFs for CQL.

Implements Median, Mode, StdDev, Variance per CQL specification.
"""
from __future__ import annotations
from typing import TYPE_CHECKING, Any, List

if TYPE_CHECKING:
    import duckdb


def median(values: List[Any]) -> float | None:
    """Calculate median of numeric values.

    Per CQL spec: Returns the median of the values in the list.
    For empty list or all nulls, returns null.
    """
    if not values:
        return None
    sorted_vals = sorted([v for v in values if v is not None])
    n = len(sorted_vals)
    if n == 0:
        return None
    mid = n // 2
    if n % 2 == 0:
        return (sorted_vals[mid - 1] + sorted_vals[mid]) / 2
    return float(sorted_vals[mid])


def mode(values: List[Any]) -> Any:
    """Return most frequent value.

    Per CQL spec: Returns the mode (most frequent) of the values.
    For empty list, returns null.
    """
    if not values:
        return None
    from collections import Counter
    counter = Counter([v for v in values if v is not None])
    if not counter:
        return None
    return counter.most_common(1)[0][0]


def stddev(values: List[Any]) -> float | None:
    """Calculate sample standard deviation.

    Per CQL spec: Returns the sample standard deviation.
    For fewer than 2 non-null values, returns null.
    """
    import statistics
    non_null = [v for v in values if v is not None]
    if len(non_null) < 2:
        return None
    try:
        return statistics.stdev(non_null)
    except statistics.StatisticsError:
        return None


def variance(values: List[Any]) -> float | None:
    """Calculate sample variance.

    Per CQL spec: Returns the sample variance.
    For fewer than 2 non-null values, returns null.
    """
    import statistics
    non_null = [v for v in values if v is not None]
    if len(non_null) < 2:
        return None
    try:
        return statistics.variance(non_null)
    except statistics.StatisticsError:
        return None


def registerAggregateUdfs(con: "duckdb.DuckDBPyConnection") -> None:
    """Register statistical aggregate UDFs with DuckDB connection."""
    con.create_function(
        "statisticalMedian",
        median,
        return_type=float,
        null_handling="special"
    )
    con.create_function(
        "statisticalMode",
        mode,
        return_type=float,
        null_handling="special"
    )
    con.create_function(
        "statisticalStdDev",
        stddev,
        return_type=float,
        null_handling="special"
    )
    con.create_function(
        "statisticalVariance",
        variance,
        return_type=float,
        null_handling="special"
    )
