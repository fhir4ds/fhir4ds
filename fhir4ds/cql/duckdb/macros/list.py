"""
CQL List functions as DuckDB SQL macros.

Tier 1 implementation - zero Python overhead.

IMPORTANT: DuckDB uses 1-based indexing for arrays.
These macros implement CQL list semantics with proper NULL handling.

Note: Uses 'system.' prefix to reference built-in functions and avoid
infinite recursion when macro name matches the function name.
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import duckdb


def registerListMacros(con: "duckdb.DuckDBPyConnection") -> None:
    """
    Register list function macros (Tier 1).

    Registers native DuckDB SQL macros for CQL list functions:
    - First(list) - Get first element, NULL if empty or NULL input
    - Last(list) - Get last element, NULL if empty or NULL input
    - Skip(list, n) - Skip first n elements
    - Take(list, n) - Take first n elements
    - Distinct(list) - Remove duplicates

    Note: Uses system. prefix to avoid shadowing DuckDB built-ins.
    """
    # ============================================
    # First - Get first element of list
    # Returns NULL if list is NULL or empty
    # ============================================
    con.execute(
        "CREATE MACRO IF NOT EXISTS First(lst) AS "
        "CASE WHEN lst IS NULL OR system.array_length(lst) = 0 THEN NULL ELSE lst[1] END"
    )

    # ============================================
    # Last - Get last element of list
    # Returns NULL if list is NULL or empty
    # ============================================
    con.execute(
        "CREATE MACRO IF NOT EXISTS Last(lst) AS "
        "CASE WHEN lst IS NULL OR system.array_length(lst) = 0 THEN NULL ELSE lst[-1] END"
    )

    # ============================================
    # Skip - Skip first n elements
    # Returns full list for NULL n, empty list for negative or n >= length.
    # ============================================
    integer_count_types = (
        "'TINYINT', 'SMALLINT', 'INTEGER', 'BIGINT', 'HUGEINT', "
        "'UTINYINT', 'USMALLINT', 'UINTEGER', 'UBIGINT', 'UHUGEINT'"
    )
    con.execute(
        "CREATE OR REPLACE MACRO Skip(lst, n) AS "
        "CASE WHEN lst IS NULL THEN NULL "
        "WHEN n IS NULL THEN lst "
        f"WHEN typeof(n) NOT IN ({integer_count_types}) "
        "THEN error('CQL Skip count must be Integer') "
        "WHEN n < 0 THEN lst[1:0] "
        "WHEN n >= system.array_length(lst) THEN lst[1:0] "
        "ELSE lst[n + 1:] END"
    )

    # ============================================
    # Take - Take first n elements
    # Returns full list if n > length, handles gracefully
    # DuckDB slicing is inclusive: [1:n] returns elements at positions 1 through n
    # ============================================
    con.execute(
        "CREATE OR REPLACE MACRO Take(lst, n) AS "
        "CASE WHEN lst IS NULL THEN NULL "
        f"WHEN n IS NOT NULL AND typeof(n) NOT IN ({integer_count_types}) "
        "THEN error('CQL Take count must be Integer') "
        "WHEN n IS NULL OR n <= 0 THEN lst[1:0] "
        "ELSE lst[1:n] END"
    )

    # ============================================
    # CQL list equality helpers. DuckDB's built-in list_contains/list_intersect
    # do not implement CQL's null-equal set semantics, and Quantity values are
    # transported as JSON strings that require quantityCompare for equality.
    # ============================================
    con.execute(
        "CREATE OR REPLACE MACRO CQLClinicalCodeSystem(_code_json) AS "
        "COALESCE(json_extract_string(_code_json, '$.system'), "
        "json_extract_string(_code_json, '$.codesystem'))"
    )
    con.execute(
        "CREATE OR REPLACE MACRO CQLClinicalValueKind(_clinical_value) AS "
        "CASE WHEN TRY_CAST(CAST(_clinical_value AS VARCHAR) AS JSON) IS NULL THEN NULL "
        "WHEN json_type(TRY_CAST(CAST(_clinical_value AS VARCHAR) AS JSON), '$.codes') = 'ARRAY' "
        "THEN 'Concept' "
        "WHEN json_extract_string(TRY_CAST(CAST(_clinical_value AS VARCHAR) AS JSON), '$.code') IS NOT NULL "
        "AND json_type(TRY_CAST(CAST(_clinical_value AS VARCHAR) AS JSON), '$.value') IS NULL "
        "THEN 'Code' "
        "ELSE NULL END"
    )
    con.execute(
        "CREATE OR REPLACE MACRO CQLClinicalValueHasShape(_clinical_value) AS "
        "CQLClinicalValueKind(_clinical_value) IS NOT NULL"
    )
    con.execute(
        "CREATE OR REPLACE MACRO CQLIntervalValueHasShape(_interval_value) AS "
        "CASE WHEN TRY_CAST(CAST(_interval_value AS VARCHAR) AS JSON) IS NULL THEN FALSE "
        "WHEN json_type(TRY_CAST(CAST(_interval_value AS VARCHAR) AS JSON), '$.lowClosed') = 'BOOLEAN' "
        "AND json_type(TRY_CAST(CAST(_interval_value AS VARCHAR) AS JSON), '$.highClosed') = 'BOOLEAN' "
        "AND (json_type(TRY_CAST(CAST(_interval_value AS VARCHAR) AS JSON), '$.low') IS NOT NULL "
        "OR json_type(TRY_CAST(CAST(_interval_value AS VARCHAR) AS JSON), '$.high') IS NOT NULL) "
        "THEN TRUE ELSE FALSE END"
    )
    con.execute(
        "CREATE OR REPLACE MACRO CQLClinicalCodeEqual(left_code, right_code) AS "
        "CASE "
        "WHEN CQLClinicalValueKind(left_code) != 'Code' "
        "OR CQLClinicalValueKind(right_code) != 'Code' THEN FALSE "
        "WHEN (json_extract_string(TRY_CAST(CAST(left_code AS VARCHAR) AS JSON), '$.code') IS NULL) "
        "OR (json_extract_string(TRY_CAST(CAST(right_code AS VARCHAR) AS JSON), '$.code') IS NULL) THEN FALSE "
        "WHEN ((CQLClinicalCodeSystem(TRY_CAST(CAST(left_code AS VARCHAR) AS JSON)) IS NOT NULL) <> "
        "(CQLClinicalCodeSystem(TRY_CAST(CAST(right_code AS VARCHAR) AS JSON)) IS NOT NULL)) THEN NULL "
        "WHEN ((json_type(TRY_CAST(CAST(left_code AS VARCHAR) AS JSON), '$.display') IS NOT NULL) <> "
        "(json_type(TRY_CAST(CAST(right_code AS VARCHAR) AS JSON), '$.display') IS NOT NULL)) THEN NULL "
        "WHEN ((json_type(TRY_CAST(CAST(left_code AS VARCHAR) AS JSON), '$.version') IS NOT NULL) <> "
        "(json_type(TRY_CAST(CAST(right_code AS VARCHAR) AS JSON), '$.version') IS NOT NULL)) THEN NULL "
        "WHEN json_extract_string(TRY_CAST(CAST(left_code AS VARCHAR) AS JSON), '$.code') IS DISTINCT FROM "
        "json_extract_string(TRY_CAST(CAST(right_code AS VARCHAR) AS JSON), '$.code') THEN FALSE "
        "WHEN CQLClinicalCodeSystem(TRY_CAST(CAST(left_code AS VARCHAR) AS JSON)) IS DISTINCT FROM "
        "CQLClinicalCodeSystem(TRY_CAST(CAST(right_code AS VARCHAR) AS JSON)) THEN FALSE "
        "WHEN json_type(TRY_CAST(CAST(left_code AS VARCHAR) AS JSON), '$.display') IS NOT NULL "
        "AND json_extract_string(TRY_CAST(CAST(left_code AS VARCHAR) AS JSON), '$.display') IS DISTINCT FROM "
        "json_extract_string(TRY_CAST(CAST(right_code AS VARCHAR) AS JSON), '$.display') THEN FALSE "
        "WHEN json_type(TRY_CAST(CAST(left_code AS VARCHAR) AS JSON), '$.version') IS NOT NULL "
        "AND json_extract_string(TRY_CAST(CAST(left_code AS VARCHAR) AS JSON), '$.version') IS DISTINCT FROM "
        "json_extract_string(TRY_CAST(CAST(right_code AS VARCHAR) AS JSON), '$.version') THEN FALSE "
        "ELSE TRUE END"
    )
    con.execute(
        "CREATE OR REPLACE MACRO CQLClinicalConceptCodesEqual(left_concept, right_concept) AS "
        "CASE "
        "WHEN json_array_length(json_extract(TRY_CAST(CAST(left_concept AS VARCHAR) AS JSON), '$.codes')) "
        "!= json_array_length(json_extract(TRY_CAST(CAST(right_concept AS VARCHAR) AS JSON), '$.codes')) "
        "THEN FALSE "
        "WHEN EXISTS (SELECT 1 "
        "FROM json_each(TRY_CAST(CAST(left_concept AS VARCHAR) AS JSON), '$.codes') AS _left_each "
        "JOIN json_each(TRY_CAST(CAST(right_concept AS VARCHAR) AS JSON), '$.codes') AS _right_each "
        "ON TRY_CAST(_left_each.key AS BIGINT) = TRY_CAST(_right_each.key AS BIGINT) "
        "WHERE CQLClinicalCodeEqual(TRY_CAST(_left_each.value AS JSON), "
        "TRY_CAST(_right_each.value AS JSON)) IS FALSE) THEN FALSE "
        "WHEN EXISTS (SELECT 1 "
        "FROM json_each(TRY_CAST(CAST(left_concept AS VARCHAR) AS JSON), '$.codes') AS _left_each "
        "JOIN json_each(TRY_CAST(CAST(right_concept AS VARCHAR) AS JSON), '$.codes') AS _right_each "
        "ON TRY_CAST(_left_each.key AS BIGINT) = TRY_CAST(_right_each.key AS BIGINT) "
        "WHERE CQLClinicalCodeEqual(TRY_CAST(_left_each.value AS JSON), "
        "TRY_CAST(_right_each.value AS JSON)) IS NULL) THEN NULL "
        "ELSE TRUE END"
    )
    con.execute(
        "CREATE OR REPLACE MACRO CQLClinicalValueEqual(left_value, right_value) AS "
        "CASE "
        "WHEN CQLClinicalValueKind(left_value) IS NULL "
        "OR CQLClinicalValueKind(right_value) IS NULL THEN FALSE "
        "WHEN CQLClinicalValueKind(left_value) != CQLClinicalValueKind(right_value) THEN FALSE "
        "WHEN CQLClinicalValueKind(left_value) = 'Code' "
        "THEN CQLClinicalCodeEqual(left_value, right_value) "
        "WHEN ((json_type(TRY_CAST(CAST(left_value AS VARCHAR) AS JSON), '$.display') IS NOT NULL) <> "
        "(json_type(TRY_CAST(CAST(right_value AS VARCHAR) AS JSON), '$.display') IS NOT NULL)) THEN NULL "
        "WHEN json_type(TRY_CAST(CAST(left_value AS VARCHAR) AS JSON), '$.display') IS NOT NULL "
        "AND json_extract_string(TRY_CAST(CAST(left_value AS VARCHAR) AS JSON), '$.display') IS DISTINCT FROM "
        "json_extract_string(TRY_CAST(CAST(right_value AS VARCHAR) AS JSON), '$.display') THEN FALSE "
        "ELSE CQLClinicalConceptCodesEqual(left_value, right_value) END"
    )
    con.execute(
        "CREATE OR REPLACE MACRO CQLListElementEqual(left_value, right_value) AS "
        "CASE "
        "WHEN left_value IS NULL AND right_value IS NULL THEN TRUE "
        "WHEN left_value IS NULL OR right_value IS NULL THEN FALSE "
        "WHEN CQLClinicalValueHasShape(left_value) AND CQLClinicalValueHasShape(right_value) "
        "THEN CQLClinicalValueEqual(left_value, right_value) "
        "WHEN CQLClinicalValueHasShape(left_value) OR CQLClinicalValueHasShape(right_value) "
        "THEN FALSE "
        "WHEN CQLIntervalValueHasShape(left_value) AND CQLIntervalValueHasShape(right_value) "
        "THEN intervalEquals(CAST(left_value AS VARCHAR), CAST(right_value AS VARCHAR)) "
        "WHEN CQLIntervalValueHasShape(left_value) OR CQLIntervalValueHasShape(right_value) "
        "THEN FALSE "
        "WHEN starts_with(ltrim(CAST(left_value AS VARCHAR)), '{') "
        "AND starts_with(ltrim(CAST(right_value AS VARCHAR)), '{') "
        "AND system.contains(CAST(left_value AS VARCHAR), '\"value\"') "
        "AND system.contains(CAST(left_value AS VARCHAR), '\"unit\"') "
        "AND system.contains(CAST(right_value AS VARCHAR), '\"value\"') "
        "AND system.contains(CAST(right_value AS VARCHAR), '\"unit\"') "
        "THEN quantityCompare(CAST(left_value AS VARCHAR), "
        "CAST(right_value AS VARCHAR), '==') "
        "WHEN typeof(left_value) != typeof(right_value) "
        "AND (system.contains(typeof(left_value), 'INT') "
        "OR starts_with(typeof(left_value), 'DECIMAL') "
        "OR typeof(left_value) IN ('FLOAT', 'DOUBLE')) "
        "AND (system.contains(typeof(right_value), 'INT') "
        "OR starts_with(typeof(right_value), 'DECIMAL') "
        "OR typeof(right_value) IN ('FLOAT', 'DOUBLE')) "
        "THEN COALESCE(TRY_CAST(left_value AS DECIMAL(38,8)) = "
        "TRY_CAST(right_value AS DECIMAL(38,8)), FALSE) "
        "WHEN typeof(left_value) != typeof(right_value) THEN FALSE "
        "WHEN left_value = right_value THEN TRUE "
        "ELSE FALSE END"
    )
    con.execute(
        "CREATE OR REPLACE MACRO CQLListContainsEq(lst, elem) AS "
        "CASE WHEN lst IS NULL THEN FALSE "
        "WHEN elem IS NULL THEN system.array_length(lst) != list_count(lst) "
        "WHEN EXISTS (SELECT 1 FROM UNNEST(COALESCE(lst, [])) AS _cql_contains_u(_cql_contains_item) "
        "WHERE CQLListElementEqual(_cql_contains_item, elem) IS TRUE) THEN TRUE "
        "WHEN EXISTS (SELECT 1 FROM UNNEST(COALESCE(lst, [])) AS _cql_contains_u(_cql_contains_item) "
        "WHERE CQLListElementEqual(_cql_contains_item, elem) IS NULL) THEN NULL "
        "ELSE FALSE END"
    )
    con.execute(
        "CREATE OR REPLACE MACRO CQLListTemporalElementEqual(left_value, right_value) AS "
        "CASE "
        "WHEN left_value IS NULL AND right_value IS NULL THEN TRUE "
        "WHEN left_value IS NULL OR right_value IS NULL THEN FALSE "
        "ELSE cqlDateTimeEqual(CAST(left_value AS VARCHAR), CAST(right_value AS VARCHAR)) END"
    )
    con.execute(
        "CREATE OR REPLACE MACRO CQLListContainsTemporalEq(lst, elem) AS "
        "CASE WHEN lst IS NULL THEN FALSE "
        "WHEN elem IS NULL THEN system.array_length(lst) != list_count(lst) "
        "WHEN EXISTS (SELECT 1 FROM UNNEST(COALESCE(lst, [])) AS _cql_contains_u(_cql_contains_item) "
        "WHERE CQLListTemporalElementEqual(_cql_contains_item, elem) IS TRUE) THEN TRUE "
        "WHEN EXISTS (SELECT 1 FROM UNNEST(COALESCE(lst, [])) AS _cql_contains_u(_cql_contains_item) "
        "WHERE CQLListTemporalElementEqual(_cql_contains_item, elem) IS NULL) THEN NULL "
        "ELSE FALSE END"
    )
    con.execute(
        "CREATE OR REPLACE MACRO CQLListDistinctEq(lst) AS "
        "CASE WHEN lst IS NULL THEN NULL "
        "ELSE COALESCE((SELECT list(_cql_distinct_item ORDER BY _cql_distinct_pos) "
        "FROM (SELECT _cql_distinct_item, _cql_distinct_pos "
        "FROM (SELECT unnest(lst) AS _cql_distinct_item, "
        "generate_subscripts(lst, 1) AS _cql_distinct_pos) _cql_distinct_items "
        "WHERE NOT EXISTS (SELECT 1 FROM (SELECT unnest(lst) AS _cql_prev_item, "
        "generate_subscripts(lst, 1) AS _cql_prev_pos) _cql_prev "
        "WHERE _cql_prev_pos < _cql_distinct_pos "
        "AND CQLListElementEqual(_cql_prev_item, _cql_distinct_item))) _cql_distinct), "
        "lst[1:0]) END"
    )
    con.execute(
        "CREATE OR REPLACE MACRO CQLListExceptEq(left_lst, right_lst) AS "
        "CASE WHEN left_lst IS NULL THEN NULL "
        "WHEN right_lst IS NULL THEN CQLListDistinctEq(left_lst) "
        "ELSE COALESCE((SELECT list(_cql_except_item ORDER BY _cql_except_pos) "
        "FROM (SELECT unnest(CQLListDistinctEq(left_lst)) AS _cql_except_item, "
        "generate_subscripts(CQLListDistinctEq(left_lst), 1) AS _cql_except_pos) "
        "_cql_except_items "
        "WHERE NOT CQLListContainsEq(right_lst, _cql_except_item)), left_lst[1:0]) END"
    )
    # Temporal-aware variant: same shape as CQLListExceptEq but uses the
    # temporal contains variant so same-instant DateTimes with different
    # timezones are recognized as set-equal (CQL §Except uses equality
    # semantics, and §Equal (DateTime) compares by normalized instant).
    con.execute(
        "CREATE OR REPLACE MACRO CQLListExceptTemporalEq(left_lst, right_lst) AS "
        "CASE WHEN left_lst IS NULL THEN NULL "
        "WHEN right_lst IS NULL THEN CQLListDistinctEq(left_lst) "
        "ELSE COALESCE((SELECT list(_cql_except_item ORDER BY _cql_except_pos) "
        "FROM (SELECT unnest(CQLListDistinctEq(left_lst)) AS _cql_except_item, "
        "generate_subscripts(CQLListDistinctEq(left_lst), 1) AS _cql_except_pos) "
        "_cql_except_items "
        "WHERE NOT CQLListContainsTemporalEq(right_lst, _cql_except_item)), left_lst[1:0]) END"
    )
    con.execute(
        "CREATE OR REPLACE MACRO CQLListIntersectEq(left_lst, right_lst) AS "
        "CASE WHEN left_lst IS NULL OR right_lst IS NULL THEN NULL "
        "ELSE COALESCE((SELECT list(_cql_intersect_item ORDER BY _cql_intersect_pos) "
        "FROM (SELECT unnest(CQLListDistinctEq(left_lst)) AS _cql_intersect_item, "
        "generate_subscripts(CQLListDistinctEq(left_lst), 1) AS _cql_intersect_pos) "
        "_cql_intersect_items "
        "WHERE CQLListContainsEq(right_lst, _cql_intersect_item)), left_lst[1:0]) END"
    )
    # Temporal-aware variant: same shape as CQLListIntersectEq but uses the
    # temporal contains variant so same-instant DateTimes with different
    # timezones are recognized as common (CQL §Intersect uses equality
    # semantics, and §Equal (DateTime) compares by normalized instant).
    con.execute(
        "CREATE OR REPLACE MACRO CQLListIntersectTemporalEq(left_lst, right_lst) AS "
        "CASE WHEN left_lst IS NULL OR right_lst IS NULL THEN NULL "
        "ELSE COALESCE((SELECT list(_cql_intersect_item ORDER BY _cql_intersect_pos) "
        "FROM (SELECT unnest(CQLListDistinctEq(left_lst)) AS _cql_intersect_item, "
        "generate_subscripts(CQLListDistinctEq(left_lst), 1) AS _cql_intersect_pos) "
        "_cql_intersect_items "
        "WHERE CQLListContainsTemporalEq(right_lst, _cql_intersect_item)), left_lst[1:0]) END"
    )
    con.execute(
        "CREATE OR REPLACE MACRO CQLListHasAllEq(left_lst, right_lst) AS "
        "CASE WHEN left_lst IS NULL OR right_lst IS NULL THEN NULL "
        "WHEN EXISTS (SELECT 1 FROM UNNEST(COALESCE(right_lst, [])) AS _cql_has_all_u(_cql_has_all_item) "
        "WHERE CQLListContainsEq(left_lst, _cql_has_all_item) IS FALSE) THEN FALSE "
        "WHEN EXISTS (SELECT 1 FROM UNNEST(COALESCE(right_lst, [])) AS _cql_has_all_u(_cql_has_all_item) "
        "WHERE CQLListContainsEq(left_lst, _cql_has_all_item) IS NULL) THEN NULL "
        "ELSE TRUE END"
    )
    con.execute(
        "CREATE OR REPLACE MACRO CQLListHasAllTemporalEq(left_lst, right_lst) AS "
        "CASE WHEN left_lst IS NULL OR right_lst IS NULL THEN NULL "
        "WHEN EXISTS (SELECT 1 FROM UNNEST(COALESCE(right_lst, [])) AS _cql_has_all_u(_cql_has_all_item) "
        "WHERE CQLListContainsTemporalEq(left_lst, _cql_has_all_item) IS FALSE) THEN FALSE "
        "WHEN EXISTS (SELECT 1 FROM UNNEST(COALESCE(right_lst, [])) AS _cql_has_all_u(_cql_has_all_item) "
        "WHERE CQLListContainsTemporalEq(left_lst, _cql_has_all_item) IS NULL) THEN NULL "
        "ELSE TRUE END"
    )
    con.execute(
        "CREATE OR REPLACE MACRO CQLListEqualEq(left_lst, right_lst) AS "
        "CASE WHEN left_lst IS NULL OR right_lst IS NULL THEN NULL "
        "WHEN system.array_length(left_lst) != system.array_length(right_lst) THEN FALSE "
        "WHEN EXISTS (SELECT 1 "
        "FROM (SELECT unnest(left_lst) AS _cql_equal_l, "
        "generate_subscripts(left_lst, 1) AS _cql_equal_pos) _cql_equal_left "
        "JOIN (SELECT unnest(right_lst) AS _cql_equal_r, "
        "generate_subscripts(right_lst, 1) AS _cql_equal_pos) _cql_equal_right "
        "USING (_cql_equal_pos) "
        "WHERE CQLListElementEqual(_cql_equal_l, _cql_equal_r) IS FALSE) THEN FALSE "
        "WHEN EXISTS (SELECT 1 "
        "FROM (SELECT unnest(left_lst) AS _cql_equal_l, "
        "generate_subscripts(left_lst, 1) AS _cql_equal_pos) _cql_equal_left "
        "JOIN (SELECT unnest(right_lst) AS _cql_equal_r, "
        "generate_subscripts(right_lst, 1) AS _cql_equal_pos) _cql_equal_right "
        "USING (_cql_equal_pos) "
        "WHERE CQLListElementEqual(_cql_equal_l, _cql_equal_r) IS NULL) THEN NULL "
        "ELSE TRUE END"
    )
    con.execute(
        "CREATE OR REPLACE MACRO CQLListEqualTemporalEq(left_lst, right_lst) AS "
        "CASE WHEN left_lst IS NULL OR right_lst IS NULL THEN NULL "
        "WHEN system.array_length(left_lst) != system.array_length(right_lst) THEN FALSE "
        "WHEN EXISTS (SELECT 1 "
        "FROM (SELECT unnest(left_lst) AS _cql_equal_l, "
        "generate_subscripts(left_lst, 1) AS _cql_equal_pos) _cql_equal_left "
        "JOIN (SELECT unnest(right_lst) AS _cql_equal_r, "
        "generate_subscripts(right_lst, 1) AS _cql_equal_pos) _cql_equal_right "
        "USING (_cql_equal_pos) "
        "WHERE CQLListTemporalElementEqual(_cql_equal_l, _cql_equal_r) IS FALSE) THEN FALSE "
        "WHEN EXISTS (SELECT 1 "
        "FROM (SELECT unnest(left_lst) AS _cql_equal_l, "
        "generate_subscripts(left_lst, 1) AS _cql_equal_pos) _cql_equal_left "
        "JOIN (SELECT unnest(right_lst) AS _cql_equal_r, "
        "generate_subscripts(right_lst, 1) AS _cql_equal_pos) _cql_equal_right "
        "USING (_cql_equal_pos) "
        "WHERE CQLListTemporalElementEqual(_cql_equal_l, _cql_equal_r) IS NULL) THEN NULL "
        "ELSE TRUE END"
    )
    con.execute(
        "CREATE OR REPLACE MACRO CQLClinicalValueEquivalent(left_value, right_value) AS "
        "CASE WHEN NOT CQLClinicalValueHasShape(left_value) "
        "OR NOT CQLClinicalValueHasShape(right_value) THEN FALSE "
        "ELSE COALESCE((SELECT COUNT(*) > 0 "
        "FROM ("
        "SELECT TRY_CAST(CAST(left_value AS VARCHAR) AS JSON) AS _left_code "
        "WHERE json_extract_string(TRY_CAST(CAST(left_value AS VARCHAR) AS JSON), '$.code') IS NOT NULL "
        "AND json_type(TRY_CAST(CAST(left_value AS VARCHAR) AS JSON), '$.value') IS NULL "
        "UNION ALL "
        "SELECT TRY_CAST(_left_each.value AS JSON) AS _left_code "
        "FROM json_each(TRY_CAST(CAST(left_value AS VARCHAR) AS JSON), '$.codes') AS _left_each "
        "WHERE json_extract_string(TRY_CAST(_left_each.value AS JSON), '$.code') IS NOT NULL "
        "AND json_type(TRY_CAST(_left_each.value AS JSON), '$.value') IS NULL"
        ") _left_codes "
        "CROSS JOIN ("
        "SELECT TRY_CAST(CAST(right_value AS VARCHAR) AS JSON) AS _right_code "
        "WHERE json_extract_string(TRY_CAST(CAST(right_value AS VARCHAR) AS JSON), '$.code') IS NOT NULL "
        "AND json_type(TRY_CAST(CAST(right_value AS VARCHAR) AS JSON), '$.value') IS NULL "
        "UNION ALL "
        "SELECT TRY_CAST(_right_each.value AS JSON) AS _right_code "
        "FROM json_each(TRY_CAST(CAST(right_value AS VARCHAR) AS JSON), '$.codes') AS _right_each "
        "WHERE json_extract_string(TRY_CAST(_right_each.value AS JSON), '$.code') IS NOT NULL "
        "AND json_type(TRY_CAST(_right_each.value AS JSON), '$.value') IS NULL"
        ") _right_codes "
        "WHERE json_extract_string(_left_code, '$.code') IS NOT DISTINCT FROM "
        "json_extract_string(_right_code, '$.code') "
        "AND CQLClinicalCodeSystem(_left_code) IS NOT DISTINCT FROM "
        "CQLClinicalCodeSystem(_right_code)), FALSE) END"
    )
    con.execute(
        "CREATE OR REPLACE MACRO CQLListElementEquivalent(left_value, right_value) AS "
        "CASE "
        "WHEN left_value IS NULL AND right_value IS NULL THEN TRUE "
        "WHEN left_value IS NULL OR right_value IS NULL THEN FALSE "
        "WHEN CQLClinicalValueEquivalent(left_value, right_value) THEN TRUE "
        "WHEN CQLClinicalValueHasShape(left_value) OR CQLClinicalValueHasShape(right_value) "
        "THEN FALSE "
        "WHEN CQLIntervalValueHasShape(left_value) AND CQLIntervalValueHasShape(right_value) "
        "THEN intervalEquivalent(CAST(left_value AS VARCHAR), CAST(right_value AS VARCHAR)) "
        "WHEN CQLIntervalValueHasShape(left_value) OR CQLIntervalValueHasShape(right_value) "
        "THEN FALSE "
        "WHEN starts_with(ltrim(CAST(left_value AS VARCHAR)), '{') "
        "AND starts_with(ltrim(CAST(right_value AS VARCHAR)), '{') "
        "AND system.contains(CAST(left_value AS VARCHAR), '\"value\"') "
        "AND system.contains(CAST(left_value AS VARCHAR), '\"unit\"') "
        "AND system.contains(CAST(right_value AS VARCHAR), '\"value\"') "
        "AND system.contains(CAST(right_value AS VARCHAR), '\"unit\"') "
        "THEN COALESCE(quantityCompare(CAST(left_value AS VARCHAR), "
        "CAST(right_value AS VARCHAR), '=='), FALSE) "
        "WHEN typeof(left_value) = 'VARCHAR' AND typeof(right_value) = 'VARCHAR' "
        "THEN trim(regexp_replace(lower(CAST(left_value AS VARCHAR)), '\\s+', ' ', 'g')) = "
        "trim(regexp_replace(lower(CAST(right_value AS VARCHAR)), '\\s+', ' ', 'g')) "
        "ELSE CQLListElementEqual(left_value, right_value) END"
    )
    con.execute(
        "CREATE OR REPLACE MACRO CQLListEquivalentEq(left_lst, right_lst) AS "
        "CASE WHEN left_lst IS NULL AND right_lst IS NULL THEN TRUE "
        "WHEN left_lst IS NULL OR right_lst IS NULL THEN FALSE "
        "WHEN system.array_length(left_lst) != system.array_length(right_lst) THEN FALSE "
        "ELSE COALESCE((SELECT bool_and(CQLListElementEquivalent(_cql_equiv_l, _cql_equiv_r)) "
        "FROM (SELECT unnest(left_lst) AS _cql_equiv_l, "
        "generate_subscripts(left_lst, 1) AS _cql_equiv_pos) _cql_equiv_left "
        "JOIN (SELECT unnest(right_lst) AS _cql_equiv_r, "
        "generate_subscripts(right_lst, 1) AS _cql_equiv_pos) _cql_equiv_right "
        "USING (_cql_equiv_pos)), TRUE) END"
    )

    # ============================================
    # Distinct - Remove duplicates from list (CQL §10.2)
    # Preserves original order and retains one null if any.
    # ============================================
    con.execute(
        'CREATE OR REPLACE MACRO "Distinct"(lst) AS '
        "CQLListDistinctEq(lst)"
    )

    # ============================================
    # Tail - All elements except the first (CQL §20.25)
    # Returns empty list if list has 0 or 1 element
    # ============================================
    con.execute(
        "CREATE MACRO IF NOT EXISTS Tail(lst) AS "
        "CASE WHEN lst IS NULL THEN NULL "
        "WHEN system.array_length(lst) <= 1 THEN lst[1:0] "
        "ELSE lst[2:] END"
    )

    # ============================================
    # IndexOf - Find position of element in list (CQL §20.12)
    # Returns 0-based index, or -1 if not found
    # CQL: if either argument is null, result is null
    # Named CQLIndexOf to avoid conflict with C++ FHIRPath extension's IndexOf
    # ============================================
    con.execute(
        "CREATE OR REPLACE MACRO CQLIndexOf(lst, elem) AS "
        "CASE WHEN lst IS NULL OR elem IS NULL THEN NULL "
        "WHEN EXISTS (SELECT 1 "
        "FROM (SELECT unnest(lst) AS _cql_index_item, "
        "generate_subscripts(lst, 1) AS _cql_index_pos) _cql_index_items "
        "WHERE CQLListElementEqual(_cql_index_item, elem) IS TRUE) "
        "THEN (SELECT MIN(_cql_index_pos) - 1 "
        "FROM (SELECT unnest(lst) AS _cql_index_item, "
        "generate_subscripts(lst, 1) AS _cql_index_pos) _cql_index_items "
        "WHERE CQLListElementEqual(_cql_index_item, elem) IS TRUE) "
        "WHEN EXISTS (SELECT 1 "
        "FROM (SELECT unnest(lst) AS _cql_index_item, "
        "generate_subscripts(lst, 1) AS _cql_index_pos) _cql_index_items "
        "WHERE CQLListElementEqual(_cql_index_item, elem) IS NULL) THEN NULL "
        "ELSE -1 END"
    )
    # Temporal-aware variant: same shape as CQLIndexOf but uses
    # CQLListTemporalElementEqual so DateTimes with different timezone
    # offsets are compared by normalized instant, and precision-mismatched
    # DateTimes correctly yield NULL (uncertain equality) rather than -1.
    # CQL §IndexOf uses equality semantics.
    con.execute(
        "CREATE OR REPLACE MACRO CQLIndexOfTemporal(lst, elem) AS "
        "CASE WHEN lst IS NULL OR elem IS NULL THEN NULL "
        "WHEN EXISTS (SELECT 1 "
        "FROM (SELECT unnest(lst) AS _cql_index_item, "
        "generate_subscripts(lst, 1) AS _cql_index_pos) _cql_index_items "
        "WHERE CQLListTemporalElementEqual(_cql_index_item, elem) IS TRUE) "
        "THEN (SELECT MIN(_cql_index_pos) - 1 "
        "FROM (SELECT unnest(lst) AS _cql_index_item, "
        "generate_subscripts(lst, 1) AS _cql_index_pos) _cql_index_items "
        "WHERE CQLListTemporalElementEqual(_cql_index_item, elem) IS TRUE) "
        "WHEN EXISTS (SELECT 1 "
        "FROM (SELECT unnest(lst) AS _cql_index_item, "
        "generate_subscripts(lst, 1) AS _cql_index_pos) _cql_index_items "
        "WHERE CQLListTemporalElementEqual(_cql_index_item, elem) IS NULL) THEN NULL "
        "ELSE -1 END"
    )

    # ============================================
    # Combine - CQL §20.4: concatenate a list of strings into one string
    # Combine(source List<String>) → String
    # Combine(source List<String>, separator String) → String
    # ============================================
    con.execute(
        "CREATE OR REPLACE MACRO Combine(lst) AS "
        "CASE WHEN typeof(lst) NOT IN ('VARCHAR[]', '\"NULL\"[]', '\"NULL\"') "
        "THEN error('CQL Combine requires List<String> source') "
        "WHEN lst IS NULL THEN NULL "
        "WHEN system.array_length(list_filter(lst, x -> x IS NOT NULL)) = 0 THEN NULL "
        "ELSE system.array_to_string(list_filter(lst, x -> x IS NOT NULL), '') END"
    )
    con.execute(
        "CREATE OR REPLACE MACRO CombineSep(lst, sep) AS "
        "CASE WHEN typeof(lst) NOT IN ('VARCHAR[]', '\"NULL\"[]', '\"NULL\"') "
        "THEN error('CQL Combine requires List<String> source') "
        "WHEN typeof(sep) NOT IN ('VARCHAR', '\"NULL\"') "
        "THEN error('CQL Combine separator must be String') "
        "WHEN lst IS NULL THEN NULL "
        "WHEN system.array_length(list_filter(lst, x -> x IS NOT NULL)) = 0 THEN NULL "
        "ELSE system.array_to_string(list_filter(lst, x -> x IS NOT NULL), COALESCE(sep, '')) END"
    )

    numeric_list_guard = (
        "("
        "typeof(lst) IN ("
        "'TINYINT[]', 'SMALLINT[]', 'INTEGER[]', 'BIGINT[]', 'HUGEINT[]', "
        "'UTINYINT[]', 'USMALLINT[]', 'UINTEGER[]', 'UBIGINT[]', 'UHUGEINT[]', "
        "'FLOAT[]', 'DOUBLE[]', '\"NULL\"[]'"
        ") OR (starts_with(typeof(lst), 'DECIMAL(') AND ends_with(typeof(lst), '[]'))"
        ")"
    )
    numeric_values = (
        "list_filter("
        "list_transform(lst, _v -> TRY_CAST(_v AS DOUBLE)), "
        "_v -> _v IS NOT NULL"
        ")"
    )

    # ============================================
    # Product - CQL §20.22: multiply all elements in a list
    # Uses list_aggregate with 'product'; casts elements to DOUBLE first
    # ============================================
    con.execute(
        "CREATE OR REPLACE MACRO Product(lst) AS "
        "CASE WHEN lst IS NULL THEN NULL "
        f"WHEN NOT {numeric_list_guard} THEN error('CQL Product requires numeric List source') "
        f"ELSE list_aggregate({numeric_values}, 'product') END"
    )

    # GeometricMean - CQL aggregate over positive numeric values
    con.execute(
        "CREATE OR REPLACE MACRO GeometricMean(lst) AS "
        "CASE WHEN lst IS NULL THEN NULL "
        f"WHEN NOT {numeric_list_guard} THEN error('CQL GeometricMean requires List<Decimal> source') "
        f"WHEN system.array_length({numeric_values}) = 0 THEN NULL "
        f"WHEN list_min({numeric_values}) < 0 THEN NULL "
        f"WHEN list_min({numeric_values}) = 0 THEN 0.0 "
        f"ELSE system.exp(list_aggregate(list_transform({numeric_values}, _v -> system.ln(_v)), 'avg')) END"
    )

    # CQL Mode returns a single statistical mode. If no non-null mode exists
    # or multiple values are tied for most frequent, return NULL.
    con.execute(
        "CREATE MACRO IF NOT EXISTS CQLListMode(lst) AS "
        "CASE WHEN lst IS NULL THEN NULL ELSE ("
        "SELECT CASE WHEN COUNT(*) = 1 THEN MIN(_value) ELSE NULL END "
        "FROM ("
        "SELECT _value, COUNT(*) AS _count "
        "FROM (SELECT UNNEST(list_filter(lst, _v -> _v IS NOT NULL)) AS _value) _items "
        "GROUP BY _value"
        ") _counts "
        "WHERE _count = ("
        "SELECT MAX(_count) FROM ("
        "SELECT _value, COUNT(*) AS _count "
        "FROM (SELECT UNNEST(list_filter(lst, _v -> _v IS NOT NULL)) AS _value) _max_items "
        "GROUP BY _value"
        ") _max_counts"
        ")"
        ") END"
    )

    # ============================================
    # Descendents - CQL §20.4: returns null for null input
    #
    # Phase 3 (medterm4ds subsumption) status:
    #   This identity macro is preserved UNCHANGED so that conformance tests
    #   that exercise ``descendents`` without a populated closure table
    #   continue to pass byte-for-byte (INV-1: zero regression). When a
    #   caller runs ``build_closure_table(...)`` and sets
    #   ``closure_table_loaded=True`` on the translation context, the
    #   translator intercepts ``Descendents(Code)`` in
    #   ``_translate_function_ref`` and emits a SQL list pulled from the
    #   ``terminology_closure`` table — this macro is NOT consulted in that
    #   path. The macro continues to handle the structural-traversal form
    #   ``(null).descendents()`` for null input.
    # ============================================
    con.execute(
        "CREATE MACRO IF NOT EXISTS descendents(x) AS "
        "CASE WHEN x IS NULL THEN NULL ELSE x END"
    )


__all__ = ["registerListMacros"]
