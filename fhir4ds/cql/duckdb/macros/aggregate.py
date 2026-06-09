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
    con.execute(
        "CREATE OR REPLACE MACRO Median(x) AS "
        f"CASE WHEN x IS NULL THEN NULL "
        f"WHEN NOT {numeric_list_guard} THEN error('CQL Median requires List<Decimal> source') "
        f"ELSE list_aggregate({numeric_list}, 'median') END"
    )
    con.execute(
        "CREATE OR REPLACE MACRO Mode(x) AS "
        "CQLListMode(x)"
    )
    con.execute(
        "CREATE OR REPLACE MACRO StdDev(x) AS "
        f"CASE WHEN x IS NULL THEN NULL "
        f"WHEN NOT {numeric_list_guard} THEN error('CQL StdDev requires List<Decimal> source') "
        f"ELSE list_aggregate({numeric_list}, 'stddev_samp') END"
    )
    con.execute(
        "CREATE OR REPLACE MACRO PopulationStdDev(x) AS "
        f"CASE WHEN x IS NULL THEN NULL "
        f"WHEN NOT {numeric_list_guard} THEN error('CQL PopulationStdDev requires List<Decimal> source') "
        f"ELSE list_aggregate({numeric_list}, 'stddev_pop') END"
    )
    con.execute(
        "CREATE OR REPLACE MACRO StdDevPop(x) AS "
        f"CASE WHEN x IS NULL THEN NULL "
        f"WHEN NOT {numeric_list_guard} THEN error('CQL StdDevPop requires List<Decimal> source') "
        f"ELSE list_aggregate({numeric_list}, 'stddev_pop') END"
    )
    con.execute(
        "CREATE OR REPLACE MACRO Variance(x) AS "
        f"CASE WHEN x IS NULL THEN NULL "
        f"WHEN NOT {numeric_list_guard} THEN error('CQL Variance requires List<Decimal> source') "
        f"ELSE list_aggregate({numeric_list}, 'var_samp') END"
    )
    con.execute(
        "CREATE OR REPLACE MACRO PopulationVariance(x) AS "
        f"CASE WHEN x IS NULL THEN NULL "
        f"WHEN NOT {numeric_list_guard} THEN error('CQL PopulationVariance requires List<Decimal> source') "
        f"ELSE list_aggregate({numeric_list}, 'var_pop') END"
    )
    con.execute(
        "CREATE OR REPLACE MACRO VarPop(x) AS "
        f"CASE WHEN x IS NULL THEN NULL "
        f"WHEN NOT {numeric_list_guard} THEN error('CQL VarPop requires List<Decimal> source') "
        f"ELSE list_aggregate({numeric_list}, 'var_pop') END"
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
