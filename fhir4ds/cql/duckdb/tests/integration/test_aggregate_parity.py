"""CQL aggregate function parity checks."""

from __future__ import annotations

import math

import duckdb

from fhir4ds.cql.duckdb import register
from fhir4ds.cql.duckdb.extension import _register_python_supplements
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
    assert "mode" in translated["ModeList"].to_sql()
    assert "stddev_pop" in translated["PopulationStdDevList"].to_sql()
    assert "var_pop" in translated["PopulationVarianceList"].to_sql()
    assert "Product" in str(translated["ProductList"])
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
        ("SELECT GeometricMean([1, 4])", 2.0),
        ("SELECT Product([2, 3, 4])", 24.0),
        ("SELECT statisticalMedian([1.0, 2.0, 3.0])", 2.0),
        ("SELECT statisticalMode([1.0, 2.0, 2.0])", 2.0),
        ("SELECT statisticalStdDev([1.0, 2.0, 3.0])", 1.0),
        ("SELECT statisticalVariance([1.0, 2.0, 3.0])", 1.0),
    ]

    py = _python_only_connection()
    cpp = _cpp_connection()
    try:
        for sql, expected in cases:
            py_value = py.execute(sql).fetchone()[0]
            cpp_value = cpp.execute(sql).fetchone()[0]
            _assert_equal_or_close(cpp_value, py_value, sql)
            _assert_equal_or_close(py_value, expected, sql)
    finally:
        py.close()
        cpp.close()


def _assert_equal_or_close(actual, expected, context: str) -> None:
    if isinstance(expected, float):
        assert math.isclose(actual, expected, rel_tol=1e-12, abs_tol=1e-12), context
    else:
        assert actual == expected, context


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
