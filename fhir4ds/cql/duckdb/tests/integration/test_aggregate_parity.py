"""CQL aggregate function parity checks."""

from __future__ import annotations

import math

import duckdb

from fhir4ds.cql.duckdb import register
from fhir4ds.cql.duckdb.extension import _register_python_supplements
from fhir4ds.cql.duckdb.tests.integration.wasm_runtime_helpers import no_python_connection
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
    assert "avg" in translated["AvgList"].to_sql()
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
        assert math.isclose(actual, expected, rel_tol=1e-12, abs_tol=1e-12), context
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
