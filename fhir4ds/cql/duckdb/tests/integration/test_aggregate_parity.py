"""CQL aggregate function parity checks."""

from __future__ import annotations

import math
from decimal import Decimal

import duckdb
import pytest

from fhir4ds.cql.duckdb import register
from fhir4ds.cql.duckdb.extension import _register_python_supplements
from fhir4ds.cql.duckdb.tests.integration.wasm_runtime_helpers import no_python_connection
from fhir4ds.cql.errors import TranslationError
from fhir4ds.cql.parser import parse_expression
from fhir4ds.cql.parser.ast_nodes import FunctionRef
from fhir4ds.cql.translator import translate_cql


def _python_only_connection() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect(config={"allow_unsigned_extensions": True})
    _register_python_supplements(con, cpp_loaded=False, include_fhirpath=True)
    return con


def _cpp_connection() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect(config={"allow_unsigned_extensions": True})
    register(con, include_fhirpath=True)
    return con


def test_cql_aggregate_expressions_parse_and_translate() -> None:
    for expression in [
        "AllTrue({true,true})",
        "AnyTrue({false,true})",
        "Avg({1,2,3})",
        "Count({1,2,null})",
        "GeometricMean({1,4})",
        "Max({1,2,3})",
        "Min({1,2,3})",
        "Median({1,2,3})",
        "Mode({1,2,2})",
        "PopulationStdDev({1,2,3})",
        "PopulationVariance({1,2,3})",
        "Product({2,3,4})",
        "StdDev({1,2,3})",
        "Sum({1,2,3})",
        "Variance({1,2,3})",
    ]:
        assert isinstance(parse_expression(expression), FunctionRef)

    translated = translate_cql(_cql_aggregate_library())
    assert "logicalAllTrue" in str(translated["AllTrueList"])
    assert "logicalAnyTrue" in str(translated["AnyTrueList"])
    assert "avg" in translated["AvgList"].to_sql().lower() or "cqlDivide" in translated["AvgList"].to_sql()
    assert "list_filter" in str(translated["CountList"])
    assert "GeometricMean" in str(translated["GeometricMeanList"])
    assert "list_max" in str(translated["MaxList"])
    assert "list_min" in str(translated["MinList"])
    assert "median" in translated["MedianList"].to_sql()
    assert "CQLListMode" in translated["ModeList"].to_sql()
    assert "stddev_pop" in translated["PopulationStdDevList"].to_sql()
    assert "var_pop" in translated["PopulationVarianceList"].to_sql()
    assert "product" in translated["ProductList"].to_sql()
    assert "stddev_samp" in translated["StdDevList"].to_sql()
    assert "sum" in translated["SumList"].to_sql()
    assert "var_samp" in translated["VarianceList"].to_sql()


def test_cql_aggregate_translated_sql_matches_cpp_registration() -> None:
    translated = translate_cql(_cql_aggregate_library())
    expected = {
        "AllTrueList": True,
        "AnyTrueList": True,
        "AvgList": 2.0,
        "CountList": 2,
        "GeometricMeanList": 2.0,
        "MaxList": 3,
        "MinList": 1,
        "MedianList": 2.0,
        "ModeList": 2,
        "PopulationStdDevList": math.sqrt(2 / 3),
        "PopulationVarianceList": 2 / 3,
        "ProductList": 24.0,
        "StdDevList": 1.0,
        "SumList": 6.0,
        "VarianceList": 1.0,
    }

    py = _python_only_connection()
    cpp = _cpp_connection()
    try:
        for name, expr in translated.items():
            sql = f"SELECT {expr.to_sql()}"
            py_value = py.execute(sql).fetchone()[0]
            cpp_value = cpp.execute(sql).fetchone()[0]
            _assert_equal_or_close(cpp_value, py_value, name)
            _assert_equal_or_close(py_value, expected[name], name)
    finally:
        py.close()
        cpp.close()


def test_cql_aggregate_direct_surface_matches_cpp_registration() -> None:
    cases = [
        ("SELECT logicalAllTrue('[true,true]')", True),
        ("SELECT logicalAnyTrue('[false,true]')", True),
        ("SELECT AllTrue([true, NULL, true])", True),
        ("SELECT AllTrue([true, NULL, false])", False),
        ("SELECT AnyTrue([false, NULL])", False),
        ("SELECT AnyTrue([false, NULL, true])", True),
        ("SELECT GeometricMean([1, 4])", 2.0),
        ("SELECT Product([2, 3, 4])", 24.0),
        ("SELECT Median([1.0, NULL, 3.0])", 2.0),
        ("SELECT Mode([1.0, 1.0, 2.0, 2.0])", None),
        ("SELECT StdDev([1.0, 2.0, 3.0])", 1.0),
        ("SELECT Variance([1.0, 2.0, 3.0])", 1.0),
        ("SELECT PopulationStdDev([1.0, 2.0, 3.0])", math.sqrt(2 / 3)),
        ("SELECT PopulationVariance([1.0, 2.0, 3.0])", 2 / 3),
        ("SELECT statisticalMedian([1.0, 2.0, 3.0])", 2.0),
        ("SELECT statisticalMode([1.0, 2.0, 2.0])", 2.0),
        ("SELECT statisticalMode([1.0, 1.0, 2.0, 2.0])", None),
        ("SELECT CQLListMode([1.0, 2.0, 2.0])", 2.0),
        ("SELECT CQLListMode([1.0, 1.0, 2.0, 2.0])", None),
        ("SELECT CQLListMode(['a', 'b', 'b'])", "b"),
        ("SELECT CQLListMode(['a', 'a', 'b', 'b'])", None),
        ("SELECT statisticalStdDev([1.0, 2.0, 3.0])", 1.0),
        ("SELECT statisticalVariance([1.0, 2.0, 3.0])", 1.0),
    ]

    py = _python_only_connection()
    cpp = _cpp_connection()
    try:
        with no_python_connection() as no_py:
            for sql, expected in cases:
                py_value = py.execute(sql).fetchone()[0]
                cpp_value = cpp.execute(sql).fetchone()[0]
                no_py_value = no_py.execute(sql).fetchone()[0]
                _assert_equal_or_close(cpp_value, py_value, sql)
                _assert_equal_or_close(no_py_value, py_value, sql)
                _assert_equal_or_close(py_value, expected, sql)
    finally:
        py.close()
        cpp.close()


def test_cql_aggregate_rejects_static_invalid_element_types() -> None:
    invalid_definitions = [
        "define BadAllTrue: AllTrue({1, 2})",
        "define BadAnyTrue: AnyTrue({'true', 'false'})",
        "define BadAvg: Avg({'1', '2'})",
        "define BadMedian: Median({'1', '2'})",
        "define BadStdDev: StdDev({'1', '2'})",
        "define BadProduct: Product({'2', '3'})",
        "define BadGeometricMean: GeometricMean({'2', '3'})",
        "define BadAllTrueNestedList: AllTrue({{1, 2}})",
        "define BadAvgFunctionReturn: Avg({ToString(5)})",
        "define BadAvgDateTimeConstructor: Avg({DateTime(2012, 1, 1)})",
        "define BadAllTrueDateConstructor: AllTrue({Date(2012, 1, 1)})",
        "define BadMinTuple: Min({Tuple { a: 1 }, Tuple { a: 2 }})",
        "define BadQueryAllTrueInteger: AllTrue((from { 1, 2 } I return I))",
        "define BadQueryAnyTrueString: AnyTrue((from { 'true', 'false' } S return S))",
        "define BadQueryAvgString: Avg((from { '1', '2' } S return S))",
        "define BadQuerySumDateTime: Sum((from { @2012-01-01T00:00:00 } D return D))",
        "define BadQueryMedianTime: Median((from { @T10:00, @T11:00 } T return T))",
        "define BadQueryMinTuple: Min((from { Tuple { a: 1 }, Tuple { a: 2 } } T return T))",
    ]

    for definition in invalid_definitions:
        with pytest.raises(TranslationError):
            translate_cql(
                f"""library BadAggregateTypes version '1.0.0'
using FHIR version '4.0.1'
context Patient
{definition}
"""
            )


def test_cql_aggregate_direct_surface_rejects_string_numeric_coercion() -> None:
    cases = [
        "SELECT Median(['1', '2'])",
        "SELECT StdDev(['1', '2'])",
        "SELECT Variance(['1', '2'])",
        "SELECT PopulationStdDev(['1', '2'])",
        "SELECT PopulationVariance(['1', '2'])",
        "SELECT Product(['2', '3'])",
        "SELECT GeometricMean(['2', '8'])",
    ]

    py = _python_only_connection()
    cpp = _cpp_connection()
    try:
        with no_python_connection() as no_py:
            for con in (py, cpp, no_py):
                for sql in cases:
                    with pytest.raises(Exception):
                        con.execute(sql).fetchone()
    finally:
        py.close()
        cpp.close()


def test_cql_geometric_mean_zero_and_query_lists_follow_product_formula() -> None:
    translated = translate_cql(
        """library GeometricMeanZero version '1.0.0'
using FHIR version '4.0.1'
context Patient
define DirectZero: GeometricMean({0.0, 4.0})
define QueryZero: GeometricMean((from {0.0, 4.0} D return D))
define QueryNonZero: GeometricMean((from {1.0, 4.0} D return D))
define QueryAllNull: GeometricMean((from {null as Decimal, null as Decimal} D return D))
"""
    )
    expected = {
        "DirectZero": 0.0,
        "QueryZero": 0.0,
        "QueryNonZero": 2.0,
        "QueryAllNull": None,
    }

    py = _python_only_connection()
    cpp = _cpp_connection()
    try:
        with no_python_connection() as no_py:
            for name, expr in translated.items():
                sql = f"SELECT {expr.to_sql()}"
                py_value = py.execute(sql).fetchone()[0]
                cpp_value = cpp.execute(sql).fetchone()[0]
                no_py_value = no_py.execute(sql).fetchone()[0]
                _assert_equal_or_close(cpp_value, py_value, name)
                _assert_equal_or_close(no_py_value, py_value, name)
                _assert_equal_or_close(py_value, expected[name], name)
    finally:
        py.close()
        cpp.close()


def test_cql_aggregate_query_sources_and_mode_ties_are_list_semantics() -> None:
    translated = translate_cql(
        """library AggregateQuerySources version '1.0.0'
using FHIR version '4.0.1'
context Patient
define QueryAllTrueNullOnly: AllTrue((from { null as Boolean, null as Boolean } B return B))
define QueryAllTrueEmpty: AllTrue((from { false, null as Boolean } B where B is null return B))
define QueryAnyTrueNullOnly: AnyTrue((from { null as Boolean, null as Boolean } B return B))
define QueryAnyTrueEmpty: AnyTrue((from { true, null as Boolean } B where B is null return B))
define QueryCountNullOnly: Count((from { null as Integer, null as Integer } I return I))
define QueryCountNonNull: Count((from { 1, null as Integer, 2 } I return I))
define QueryAvgWithNull: Avg((from { 1.0, null as Decimal, 3.0 } D return D))
define QueryMedianWithNull: Median((from { 1.0, null as Decimal, 3.0 } D return D))
define QueryProductZero: Product((from { 2.0, 0.0, null as Decimal, 4.0 } D return D))
define ModeTieList: Mode({ 2.0, 2.0, 8.0, 8.0 })
define QueryModeTie: Mode((from { 2.0, 2.0, 8.0, 8.0 } D return D))
define ListDateMax: Max({ @2012-12-31, @2013-01-01, @2012-01-01 })
define QueryDateMax: Max((from { @2012-12-31, @2013-01-01, @2012-01-01 } D return D))
define ListDateMin: Min({ @2012-12-31, @2013-01-01, @2012-01-01 })
define QueryDateMin: Min((from { @2012-12-31, @2013-01-01, @2012-01-01 } D return D))
define ListStringMax: Max({ 'b', 'a', 'c' })
define QueryStringMax: Max((from { 'b', 'a', 'c' } S return S))
define ListTimeMin: Min({ @T12:00, @T10:00, @T11:00 })
define QueryTimeMin: Min((from { @T12:00, @T10:00, @T11:00 } T return T))
"""
    )
    expected = {
        "QueryAllTrueNullOnly": True,
        "QueryAllTrueEmpty": True,
        "QueryAnyTrueNullOnly": False,
        "QueryAnyTrueEmpty": False,
        "QueryCountNullOnly": 0,
        "QueryCountNonNull": 2,
        "QueryAvgWithNull": 2.0,
        "QueryMedianWithNull": 2.0,
        "QueryProductZero": 0.0,
        "ModeTieList": None,
        "QueryModeTie": None,
        "ListDateMax": "2013-01-01",
        "QueryDateMax": "2013-01-01",
        "ListDateMin": "2012-01-01",
        "QueryDateMin": "2012-01-01",
        "ListStringMax": "c",
        "QueryStringMax": "c",
        "ListTimeMin": "T10:00",
        "QueryTimeMin": "T10:00",
    }

    py = _python_only_connection()
    cpp = _cpp_connection()
    try:
        with no_python_connection() as no_py:
            for name, expr in translated.items():
                sql = f"SELECT {expr.to_sql()}"
                py_value = py.execute(sql).fetchone()[0]
                cpp_value = cpp.execute(sql).fetchone()[0]
                no_py_value = no_py.execute(sql).fetchone()[0]
                _assert_equal_or_close(cpp_value, py_value, name)
                _assert_equal_or_close(no_py_value, py_value, name)
                _assert_equal_or_close(py_value, expected[name], name)
    finally:
        py.close()
        cpp.close()


def test_cql_list_accumulator_aggregate_supports_hedis_episode_dedup() -> None:
    translated = translate_cql(
        """library HedisEpisodeDedup version '1.0.0'
using FHIR version '4.0.1'
context Patient
define EmptyEpisodes:
  (from ({} as List<Date>) E
    sort by E
    aggregate R starting ({} as List<Date>):
      if Count(R) = 0 then { E }
      else if difference in days between Last(R) and E > 31 then R union { E }
      else R)
define DedupEpisodes:
  (from { @2025-02-02, @2025-01-01, @2025-02-01, @2025-01-01 } E
    sort by E
    aggregate R starting ({} as List<Date>):
      if Count(R) = 0 then { E }
      else if difference in days between Last(R) and E > 31 then R union { E }
      else R)
define DedupCount:
  Count((from { @2025-02-02, @2025-01-01, @2025-02-01, @2025-01-01 } E
    sort by E
    aggregate R starting ({} as List<Date>):
      if Count(R) = 0 then { E }
      else if difference in days between Last(R) and E > 31 then R union { E }
      else R))
"""
    )
    expected = {
        "EmptyEpisodes": [],
        "DedupEpisodes": ["2025-01-01", "2025-02-02"],
        "DedupCount": 2,
    }

    py = _python_only_connection()
    cpp = _cpp_connection()
    try:
        with no_python_connection() as no_py:
            for name, expr in translated.items():
                sql = f"SELECT {expr.to_sql()}"
                py_value = py.execute(sql).fetchone()[0]
                cpp_value = cpp.execute(sql).fetchone()[0]
                no_py_value = no_py.execute(sql).fetchone()[0]
                assert py_value == expected[name], name
                assert cpp_value == py_value, name
                assert no_py_value == py_value, name
    finally:
        py.close()
        cpp.close()


def test_cql_quantity_aggregate_translation_is_unit_aware_across_surfaces() -> None:
    translated = translate_cql(_cql_quantity_aggregate_library())

    py = _python_only_connection()
    cpp = _cpp_connection()
    try:
        with no_python_connection() as no_py:
            for name, expr in translated.items():
                if name == "QuantityList":
                    continue
                sql = f"SELECT {expr.to_sql()}"
                py_value = py.execute(sql).fetchone()[0]
                cpp_value = cpp.execute(sql).fetchone()[0]
                no_py_value = no_py.execute(sql).fetchone()[0]
                _assert_quantity_equal(cpp_value, py_value, name)
                _assert_quantity_equal(no_py_value, py_value, name)

            _assert_quantity_close(
                py.execute(f"SELECT {translated['QuantitySumMixed'].to_sql()}").fetchone()[0],
                2000.0,
                "mg",
            )
            _assert_quantity_close(
                py.execute(f"SELECT {translated['QuantityAvgMixed'].to_sql()}").fetchone()[0],
                1000.0,
                "mg",
            )
            _assert_quantity_close(
                py.execute(f"SELECT {translated['QuantityMinMixed'].to_sql()}").fetchone()[0],
                1500.0,
                "mg",
            )
            _assert_quantity_close(
                py.execute(f"SELECT {translated['QuantityMaxMixed'].to_sql()}").fetchone()[0],
                2.0,
                "g",
            )
            _assert_quantity_close(
                py.execute(f"SELECT {translated['QuantityMedianMixed'].to_sql()}").fetchone()[0],
                2000.0,
                "mg",
            )
            _assert_quantity_close(
                py.execute(f"SELECT {translated['QuantityStdDevMixed'].to_sql()}").fetchone()[0],
                1000.0,
                "mg",
            )
            _assert_quantity_close(
                py.execute(f"SELECT {translated['QuantityPopulationVarianceMixed'].to_sql()}").fetchone()[0],
                666666.6666666666,
                "mg",
            )
            _assert_quantity_close(
                py.execute(f"SELECT {translated['QuantityProductSameUnit'].to_sql()}").fetchone()[0],
                6.0,
                "mg",
            )
            _assert_quantity_close(
                py.execute(f"SELECT {translated['QuantityNamedSumMixed'].to_sql()}").fetchone()[0],
                2000.0,
                "mg",
            )
            _assert_quantity_close(
                py.execute(f"SELECT {translated['QuantityNamedAvgMixed'].to_sql()}").fetchone()[0],
                1000.0,
                "mg",
            )
    finally:
        py.close()
        cpp.close()


def _assert_equal_or_close(actual, expected, context: str) -> None:
    if isinstance(expected, float):
        # CQL-01 doctrine: translated aggregates return exact DECIMAL(38,8)
        # results (cqlDivide / TRY_CAST narrowing), so irrational results such
        # as PopulationStdDev({1,2,3}) are rounded at scale 8.
        assert math.isclose(actual, expected, rel_tol=1e-7, abs_tol=1e-7), context
    else:
        assert actual == expected, context


def _quantity_payload(value: str) -> dict:
    import json

    return json.loads(value)


def _assert_quantity_equal(actual: str | None, expected: str | None, context: str) -> None:
    if expected is None:
        assert actual is None, context
        return
    assert actual is not None, context
    actual_payload = _quantity_payload(actual)
    expected_payload = _quantity_payload(expected)
    assert (actual_payload.get("unit") or actual_payload.get("code")) == (
        expected_payload.get("unit") or expected_payload.get("code")
    ), context
    assert math.isclose(
        float(actual_payload["value"]),
        float(expected_payload["value"]),
        rel_tol=1e-9,
        abs_tol=1e-9,
    ), context


def _assert_quantity_close(actual: str | None, value: float, unit: str) -> None:
    assert actual is not None
    payload = _quantity_payload(actual)
    assert (payload.get("unit") or payload.get("code")) == unit
    assert math.isclose(float(payload["value"]), value, rel_tol=1e-9, abs_tol=1e-9)


def _cql_aggregate_library() -> str:
    return """library Aggregate1 version '1.0.0'
using FHIR version '4.0.1'
context Patient
define AllTrueList: AllTrue({true,true})
define AnyTrueList: AnyTrue({false,true})
define AvgList: Avg({1,2,3})
define CountList: Count({1,2,null})
define GeometricMeanList: GeometricMean({1,4})
define MaxList: Max({1,2,3})
define MinList: Min({1,2,3})
define MedianList: Median({1,2,3})
define ModeList: Mode({1,2,2})
define PopulationStdDevList: PopulationStdDev({1,2,3})
define PopulationVarianceList: PopulationVariance({1,2,3})
define ProductList: Product({2,3,4})
define StdDevList: StdDev({1,2,3})
define SumList: Sum({1,2,3})
define VarianceList: Variance({1,2,3})
"""


def _cql_quantity_aggregate_library() -> str:
    return """library QuantityAggregate1 version '1.0.0'
using FHIR version '4.0.1'
context Patient
define QuantityList: {1 'g', 1000 'mg'}
define QuantitySumMixed: Sum({1 'g', 1000 'mg'})
define QuantityAvgMixed: Avg({1 'g', 1000 'mg'})
define QuantityMinMixed: Min({2 'g', 1500 'mg'})
define QuantityMaxMixed: Max({2 'g', 1500 'mg'})
define QuantityMedianMixed: Median({1 'g', 2000 'mg', 3 'g'})
define QuantityStdDevMixed: StdDev({1 'g', 2000 'mg', 3 'g'})
define QuantityPopulationVarianceMixed: PopulationVariance({1 'g', 2000 'mg', 3 'g'})
define QuantityProductSameUnit: Product({2 'mg', 3 'mg'})
define QuantityNamedSumMixed: Sum(QuantityList)
define QuantityNamedAvgMixed: Avg(QuantityList)
"""


# ---------------------------------------------------------------------------
# CQL-20 SKEPTIC iteration: aggregates over query-derived / rows-define /
# dynamic operands (end-to-end population SQL; py == cpp == no-python).
# ---------------------------------------------------------------------------

_CQL20_RESOURCES_SQL = """
CREATE TABLE IF NOT EXISTS resources (id VARCHAR, resourceType VARCHAR, resource JSON, patient_ref VARCHAR);
DELETE FROM resources;
INSERT INTO resources VALUES
('P1','Patient','{"resourceType":"Patient","id":"P1","active":true,"name":[{"family":"Chalmers","given":["Peter","James"]},{"family":"Gray","given":["Kim"]}]}',NULL),
('P2','Patient','{"resourceType":"Patient","id":"P2","active":true}',NULL),
('O1','Observation','{"resourceType":"Observation","id":"O1","status":"final","code":{"coding":[{"system":"http://loinc.org","code":"29463-7"}]},"subject":{"reference":"Patient/P1"},"effectiveDateTime":"2024-01-02T00:00:00","valueQuantity":{"value":120,"unit":"mg"}}','P1'),
('O2','Observation','{"resourceType":"Observation","id":"O2","status":"preliminary","code":{"coding":[{"system":"http://loinc.org","code":"29463-7"}]},"subject":{"reference":"Patient/P1"},"effectiveDateTime":"2024-01-05T00:00:00","valueQuantity":{"value":80,"unit":"mg"}}','P1'),
('O3','Observation','{"resourceType":"Observation","id":"O3","status":"final","code":{"coding":[{"system":"http://loinc.org","code":"8867-4"}]},"subject":{"reference":"Patient/P2"},"effectiveDateTime":"2024-02-01T00:00:00","valueQuantity":{"value":60,"unit":"mg"}}','P2')
"""

_CQL20_DYNAMIC_HEADER = """library Cql20AggDynamic version '1.0.0'
using FHIR version '4.0.1'
context Patient
define G: Patient.name.given
define Vals: (from [Observation] O return O.value as Quantity)
define Dates: (from [Observation] O return O.effective as dateTime)
define Nums: (from { 1.0, 2.0, null as Decimal, 5.0 } X return X)
"""


def _run_cql20_population_case(cql: str) -> dict:
    from fhir4ds.cql.parser import parse_cql
    from fhir4ds.cql.translator.translator import CQLToSQLTranslator

    sql = CQLToSQLTranslator().translate_library_to_population_sql(
        parse_cql(cql), output_columns={"R": "R"}
    )
    py = _python_only_connection()
    cpp = _cpp_connection()
    no_py_cm = no_python_connection()
    no_py = no_py_cm.__enter__()
    try:
        results = {}
        for label, con in (("py", py), ("cpp", cpp), ("nopy", no_py)):
            con.execute(_CQL20_RESOURCES_SQL)
            results[label] = con.execute(sql).fetchall()
        return results
    finally:
        no_py_cm.__exit__(None, None, None)
        py.close()
        cpp.close()


def _quantity_value(raw) -> float | None:
    import json as _json

    if raw is None:
        return None
    return float(_json.loads(raw)["value"])


@pytest.mark.parametrize(
    "expr,expected_p1,expected_p2,quantity",
    [
        # QA-001/QA-002: query-derived Quantity define aggregates see ALL rows
        ("Count(Vals)", 2, 1, False),
        ("Sum(Vals)", 200.0, 60.0, True),
        ("Avg(Vals)", 100.0, 60.0, True),
        ("Min(Vals)", 80.0, 60.0, True),
        ("Max(Vals)", 120.0, 60.0, True),
        ("Median(Vals)", 100.0, 60.0, True),
        ("Variance(Vals)", 800.0, None, True),
        ("PopulationVariance(Vals)", 400.0, 0.0, True),
        ("Product(Vals)", 9600.0, 60.0, True),
        # QA-003: FHIR choice-cast dateTime defines accept Min/Max
        ("Min(Dates)", "2024-01-02T00:00:00", "2024-02-01T00:00:00", False),
        ("Max(Dates)", "2024-01-05T00:00:00", "2024-02-01T00:00:00", False),
        ("Count(Dates)", 2, 1, False),
        # QA-004: boolean aggregates over retrieve-backed query sources
        ("AllTrue((from [Observation] O return O.status = 'final'))", False, True, False),
        ("AnyTrue((from [Observation] O return O.status = 'final'))", True, True, False),
        # QA-005: Mode over dynamic multi-valued field (all-unique -> tie -> null)
        ("Mode(Patient.name.given)", None, None, False),
        # element-rows numeric define: all rows, nulls ignored
        ("Count(Nums)", 3, 3, False),
        ("Sum(Nums)", 8.0, 8.0, False),
        ("Min(Nums)", 1.0, 1.0, False),
        ("Max(Nums)", 5.0, 5.0, False),
    ],
)
def test_cql20_dynamic_operand_aggregates_end_to_end(expr, expected_p1, expected_p2, quantity) -> None:
    cql = _CQL20_DYNAMIC_HEADER + "define R: " + expr + "\n"
    results = _run_cql20_population_case(cql)
    assert results["cpp"] == results["py"], expr
    assert results["nopy"] == results["py"], expr
    values = {pid: value for pid, value in results["py"]}
    if quantity:
        got_p1 = _quantity_value(values.get("P1"))
        got_p2 = _quantity_value(values.get("P2"))
    else:
        got_p1, got_p2 = values.get("P1"), values.get("P2")
        if isinstance(got_p1, float):
            got_p1 = round(got_p1, 6)
        if isinstance(got_p2, float):
            got_p2 = round(got_p2, 6)
        if isinstance(expected_p1, float):
            expected_p1 = round(expected_p1, 6)
        if isinstance(expected_p2, float):
            expected_p2 = round(expected_p2, 6)
    assert got_p1 == expected_p1, expr
    assert got_p2 == expected_p2, expr


def test_cql20_product_integer_list_is_integer_typed() -> None:
    """CQL Appendix B Product(List<Integer>) Integer — typed result width."""
    translated = translate_cql(
        """library ProductIntType version '1.0.0'
using FHIR version '4.0.1'
context Patient
define R: Product({1, 2, 3, 4})
"""
    )
    sql = f"SELECT {translated['R'].to_sql()}"
    py = _python_only_connection()
    cpp = _cpp_connection()
    try:
        py_value = py.execute(sql).fetchone()[0]
        cpp_value = cpp.execute(sql).fetchone()[0]
        assert py_value == 24
        assert isinstance(py_value, int)
        assert cpp_value == py_value
    finally:
        py.close()
        cpp.close()


def test_cql20_datetime_cast_query_min_max_translate_and_execute() -> None:
    """`O.effective as dateTime` lists accept Min/Max end-to-end (QA-003)."""
    cql = (
        _CQL20_DYNAMIC_HEADER
        + "define R: Min((from [Observation] O return O.effective as dateTime))\n"
    )
    results = _run_cql20_population_case(cql)
    assert results["cpp"] == results["py"]
    values = dict(results["py"])
    assert values["P1"] == "2024-01-02T00:00:00"
    assert values["P2"] == "2024-02-01T00:00:00"


def test_cql20_dynamic_numeric_query_aggregates_are_exact_typed() -> None:
    """CQL-20 HISTORIAN QA-001: numeric-returning queries aggregate through
    the exact-typed list lowering (CQL 1.5 §2.3 Decimal is exact; Appendix B
    Sum(List<Integer>) -> Integer), not the DOUBLE row aggregate."""
    for expr, expected_p1, type_check in [
        ("Sum((from [Observation] O return O.valueQuantity.value as Integer))", 200, lambda v: isinstance(v, int)),
        ("Product((from [Observation] O return O.valueQuantity.value as Integer))", 9600, lambda v: isinstance(v, int)),
        ("Sum((from [Observation] O return ToDecimal(O.valueQuantity.value)))", 200, lambda v: isinstance(v, Decimal)),
    ]:
        cql = _CQL20_DYNAMIC_HEADER + "define R: " + expr + "\n"
        results = _run_cql20_population_case(cql)
        assert results["cpp"] == results["py"], expr
        assert results["nopy"] == results["py"], expr
        values = dict(results["py"])
        assert values["P1"] == expected_p1 and type_check(values["P1"]), expr
        assert values["P2"] == 60 and type_check(values["P2"]), expr


def test_cql20_dynamic_decimal_sum_is_exact_not_floating_point() -> None:
    """CQL 1.5 §2.3: Decimal is exact — dynamic Decimal-element Sum of
    {0.1, 0.2} must equal 0.3, not a DOUBLE artifact (QA-001)."""
    translated = translate_cql(
        """library DynExactSum version '1.0.0'
using FHIR version '4.0.1'
context Patient
define R: Sum((from { 0.1, 0.2 } D return D + 0.0))
"""
    )
    sql = f"SELECT {translated['R'].to_sql()}"
    py = _python_only_connection()
    cpp = _cpp_connection()
    try:
        py_value = py.execute(sql).fetchone()[0]
        cpp_value = cpp.execute(sql).fetchone()[0]
        assert py_value == Decimal("0.3")
        assert cpp_value == py_value
    finally:
        py.close()
        cpp.close()


def test_cql20_dynamic_boolean_operand_aggregates_raise_typed_error() -> None:
    """CQL-20 HISTORIAN QA-002: dynamically derived Boolean operands are
    rejected at translation with the typed CQL error, not a raw engine
    binder error."""
    for definition in [
        "define BadDynSum: Sum(Dates is null)",
        "define BadDynMedian: Median(Dates is null)",
        "define BadDynProduct: Product(G is null)",
    ]:
        with pytest.raises(TranslationError):
            translate_cql(
                f"""library BadDynamicAggTypes version '1.0.0'
using FHIR version '4.0.1'
context Patient
define Dates: (from [Observation] O return O.effective as dateTime)
define G: Patient.name.given
{definition}
"""
            )


def test_cql20_statistical_aggregates_are_exact_at_large_decimal_magnitudes() -> None:
    """CQL-20 EXPLORER QA-001: Variance/StdDev/Median over large DECIMAL(38,8)
    values must not lose the sub-centesimal deviations to a DOUBLE cast.

    CQL 1.5 Appendix B Decimal carries >= 28 significant digits; the shifted
    (deviation-from-anchor) lowering keeps the arithmetic exact where DOUBLE
    produced 0.00020024 / 100000000000.02000896 artifacts."""
    translated = translate_cql(
        """library StatExact version '1.0.0'
using FHIR version '4.0.1'
context Patient
define VarLarge: Variance({ 100000000000.01, 100000000000.03 })
define PopVarLarge: PopulationVariance({ 100000000000.01, 100000000000.03 })
define StdDevLarge: StdDev({ 100000000000.01, 100000000000.03 })
define MedianLargeOdd: Median({ 100000000000.01, 100000000000.03, 100000000000.02 })
define MedianLargeEven: Median({ 100000000000.01, 100000000000.02, 100000000000.03, 100000000000.04 })
define MedianNegativePair: Median({ -100000000000.03, -100000000000.01 })
define VarianceNegativePair: Variance({ -100000000000.03, -100000000000.01 })
define VarianceAllEqual: Variance({ 7.0, 7.0, 7.0 })
"""
    )
    expected = {
        "VarLarge": Decimal("0.00020000"),
        "PopVarLarge": Decimal("0.00010000"),
        "StdDevLarge": Decimal("0.01414214"),
        "MedianLargeOdd": Decimal("100000000000.02000000"),
        "MedianLargeEven": Decimal("100000000000.02500000"),
        "MedianNegativePair": Decimal("-100000000000.02000000"),
        "VarianceNegativePair": Decimal("0.00020000"),
        "VarianceAllEqual": Decimal("0E-8"),
    }
    py = _python_only_connection()
    cpp = _cpp_connection()
    no_py_cm = no_python_connection()
    no_py = no_py_cm.__enter__()
    try:
        for name, expr in translated.items():
            sql = f"SELECT {expr.to_sql()}"
            for label, con in (("py", py), ("cpp", cpp), ("nopy", no_py)):
                value = con.execute(sql).fetchone()[0]
                assert value == expected[name], (name, label, value, expected[name])
    finally:
        no_py_cm.__exit__(None, None, None)
        py.close()
        cpp.close()


def test_cql20_statistical_macro_direct_surface_is_exact_for_decimal_lists() -> None:
    """CQL-20 EXPLORER QA-001: the Variance/Median SQL macros (used by the
    direct SQL surface and dynamic sources) use the shifted exact-decimal
    form for DECIMAL lists."""
    py = _python_only_connection()
    cpp = _cpp_connection()
    no_py_cm = no_python_connection()
    no_py = no_py_cm.__enter__()
    try:
        cases = [
            (
                "SELECT Variance([TRY_CAST(100000000000.01 AS DECIMAL(38,8)), "
                "TRY_CAST(100000000000.03 AS DECIMAL(38,8))])",
                Decimal("0.00020000"),
            ),
            (
                "SELECT PopulationVariance([TRY_CAST(100000000000.01 AS DECIMAL(38,8)), "
                "TRY_CAST(100000000000.03 AS DECIMAL(38,8))])",
                Decimal("0.00010000"),
            ),
            (
                "SELECT Median([TRY_CAST(100000000000.01 AS DECIMAL(38,8)), "
                "TRY_CAST(100000000000.02 AS DECIMAL(38,8)), "
                "TRY_CAST(100000000000.03 AS DECIMAL(38,8))])",
                Decimal("100000000000.02000000"),
            ),
            ("SELECT Variance([5.0::DECIMAL(38,8)])", None),
            ("SELECT Variance([]::DECIMAL(38,8)[])", None),
        ]
        for sql, want in cases:
            for label, con in (("py", py), ("cpp", cpp), ("nopy", no_py)):
                got = con.execute(sql).fetchone()[0]
                # The macro surface returns DOUBLE (callers cast to the CQL
                # Decimal type); compare numerically.
                got_cmp = None if got is None else Decimal(str(got))
                want_cmp = None if want is None else Decimal(str(want))
                assert got_cmp == want_cmp, (sql, label, got, want)
    finally:
        no_py_cm.__exit__(None, None, None)
        py.close()
        cpp.close()
