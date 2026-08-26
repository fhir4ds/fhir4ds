"""
CQL Aggregate functions as DuckDB SQL macros.

Tier 1 implementation - zero Python overhead.

Note: Count, Sum, Min, Max, Avg are intentionally NOT registered as macros.
DuckDB already provides these as built-in aggregates; registering macros
for them shadows the built-ins and breaks COUNT(DISTINCT x), FILTER clauses,
and window function syntax.
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import duckdb


def registerAggregateMacros(con: "duckdb.DuckDBPyConnection") -> None:
    """
    Register aggregate function macros (Tier 1).

    Registers native DuckDB SQL macros for CQL aggregate functions:
    - Statistical: Median, Mode, StdDev, Variance
    - Boolean: AllTrue, AnyTrue, AllFalse, AnyFalse

    Note: Count, Sum, Min, Max, Avg are NOT registered as macros because
    DuckDB already provides these as built-in aggregates with identical
    semantics. Registering macros for them shadows the built-ins and breaks
    COUNT(DISTINCT x), SUM(x) FILTER (...), window functions, etc.
    """
    # ============================================
    # Statistical list aggregates.
    #
    # CQL aggregate functions take List<T> arguments. Translated query-form
    # aggregates call DuckDB row aggregates with the system.* prefix when they
    # need row aggregation, so these public names can keep CQL list semantics.
    # ============================================
    numeric_list_guard = (
        "("
        "typeof(x) IN ("
        "'TINYINT[]', 'SMALLINT[]', 'INTEGER[]', 'BIGINT[]', 'HUGEINT[]', "
        "'UTINYINT[]', 'USMALLINT[]', 'UINTEGER[]', 'UBIGINT[]', 'UHUGEINT[]', "
        "'FLOAT[]', 'DOUBLE[]', '\"NULL\"[]'"
        ") OR (starts_with(typeof(x), 'DECIMAL(') AND ends_with(typeof(x), '[]'))"
        ")"
    )
    numeric_list = (
        "list_filter("
        "list_transform(x, _v -> TRY_CAST(_v AS DOUBLE)), "
        "_v -> _v IS NOT NULL"
        ")"
    )
    # Decimal-exact shifted formulation (CQL 1.5 Appendix B: Decimal carries at
    # least 28 significant digits; casting large DECIMAL(38,8) values to DOUBLE
    # destroys sub-centesimal deviations and corrupts variance/median results).
    # Variance/StdDev are shift-invariant: subtracting the first non-null
    # element (exact DECIMAL arithmetic) before the DOUBLE aggregate keeps the
    # deviations small and exact. Median is recomposed as v0 + median(devs).
    decimal_list_guard = (
        "(starts_with(typeof(x), 'DECIMAL(') AND ends_with(typeof(x), '[]'))"
    )
    decimal_non_null = "list_filter(x, _v -> _v IS NOT NULL)"
    decimal_anchor = f"({decimal_non_null}[1])"
    decimal_devs = (
        "list_transform("
        f"list_transform({decimal_non_null}, _v -> _v - {decimal_anchor}), "
        "_v -> TRY_CAST(_v AS DOUBLE)"
        ")"
    )

    def _statistical_macro(name: str, duckdb_agg: str) -> str:
        if duckdb_agg == "median":
            decimal_path = (
                "CASE WHEN len({nn}) = 0 THEN NULL "
                "ELSE TRY_CAST(({anchor}) AS DECIMAL(38, 8)) "
                "+ TRY_CAST(list_aggregate({devs}, 'median') AS DECIMAL(38, 8)) END"
            ).format(nn=decimal_non_null, anchor=decimal_anchor, devs=decimal_devs)
        else:
            decimal_path = f"list_aggregate({decimal_devs}, '{duckdb_agg}')"
        return (
            f"CASE WHEN x IS NULL THEN NULL "
            f"WHEN NOT {numeric_list_guard} THEN error('CQL {name} requires List<Decimal> source') "
            f"WHEN {decimal_list_guard} THEN {decimal_path} "
            f"ELSE list_aggregate({numeric_list}, '{duckdb_agg}') END"
        )

    con.execute(
        "CREATE OR REPLACE MACRO Median(x) AS " + _statistical_macro("Median", "median")
    )
    con.execute(
        "CREATE OR REPLACE MACRO Mode(x) AS "
        "CQLListMode(x)"
    )
    con.execute(
        "CREATE OR REPLACE MACRO StdDev(x) AS " + _statistical_macro("StdDev", "stddev_samp")
    )
    con.execute(
        "CREATE OR REPLACE MACRO PopulationStdDev(x) AS "
        + _statistical_macro("PopulationStdDev", "stddev_pop")
    )
    con.execute(
        "CREATE OR REPLACE MACRO StdDevPop(x) AS " + _statistical_macro("StdDevPop", "stddev_pop")
    )
    con.execute(
        "CREATE OR REPLACE MACRO Variance(x) AS " + _statistical_macro("Variance", "var_samp")
    )
    con.execute(
        "CREATE OR REPLACE MACRO PopulationVariance(x) AS "
        + _statistical_macro("PopulationVariance", "var_pop")
    )
    con.execute(
        "CREATE OR REPLACE MACRO VarPop(x) AS " + _statistical_macro("VarPop", "var_pop")
    )

    # ============================================
    # Boolean aggregates
    # ============================================
    con.execute(
        "CREATE MACRO IF NOT EXISTS AllTrue(x) AS "
        "CASE WHEN x IS NULL THEN true "
        "ELSE COALESCE(list_bool_and(list_filter(x, _v -> _v IS NOT NULL)), true) END"
    )
    con.execute(
        "CREATE MACRO IF NOT EXISTS AnyTrue(x) AS "
        "CASE WHEN x IS NULL THEN false "
        "ELSE COALESCE(list_bool_or(list_filter(x, _v -> _v IS NOT NULL)), false) END"
    )
    con.execute(
        "CREATE MACRO IF NOT EXISTS AllFalse(x) AS "
        "CASE WHEN x IS NULL THEN true "
        "ELSE COALESCE(NOT list_bool_or(list_filter(x, _v -> _v IS NOT NULL)), true) END"
    )
    con.execute(
        "CREATE MACRO IF NOT EXISTS AnyFalse(x) AS "
        "CASE WHEN x IS NULL THEN false "
        "ELSE COALESCE(NOT list_bool_and(list_filter(x, _v -> _v IS NOT NULL)), false) END"
    )


__all__ = ["registerAggregateMacros"]
