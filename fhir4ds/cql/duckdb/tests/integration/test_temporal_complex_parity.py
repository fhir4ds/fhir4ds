"""CQL temporal and complex type parity checks."""

from __future__ import annotations

import json

import duckdb

from fhir4ds.cql.duckdb import register
from fhir4ds.cql.duckdb.extension import _register_python_supplements
from fhir4ds.cql.parser import parse_cql, parse_expression
from fhir4ds.cql.parser.ast_nodes import DateTimeLiteral, FunctionRef, Quantity
from fhir4ds.cql.translator import CQLToSQLTranslator

from .wasm_runtime_helpers import no_python_connection


def _python_only_connection() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect(config={"allow_unsigned_extensions": True})
    _register_python_supplements(con, cpp_loaded=False, include_fhirpath=True)
    return con


def _cpp_connection() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect(config={"allow_unsigned_extensions": True})
    register(con, include_fhirpath=True)
    return con


def _translated_definition_sql(expression: str) -> str:
    cql = f"library CQL03Explorer version '1.0'\ndefine Result: {expression}\n"
    return CQLToSQLTranslator().translate_library_to_sql(parse_cql(cql))


def test_cql_temporal_and_complex_literals_parse() -> None:
    date = parse_expression("@2024-01-15")
    datetime = parse_expression("@2024-01-15T10:30:00")
    time = parse_expression("@T10:30:00")
    quantity = parse_expression("5.5 'mg'")
    datetime_ctor = parse_expression("DateTime(2024, 1, 15)")
    time_ctor = parse_expression("Time(10, 30, 0)")

    assert isinstance(date, DateTimeLiteral)
    assert date.value == "2024-01-15"
    assert isinstance(datetime, DateTimeLiteral)
    assert datetime.value == "2024-01-15T10:30:00"
    assert isinstance(time, DateTimeLiteral)
    assert time.value == "T10:30:00"
    assert isinstance(quantity, Quantity)
    assert quantity.value == 5.5
    assert quantity.unit == "mg"
    assert isinstance(datetime_ctor, FunctionRef)
    assert datetime_ctor.name == "DateTime"
    assert isinstance(time_ctor, FunctionRef)
    assert time_ctor.name == "Time"


def test_cql_temporal_quantity_ratio_duckdb_surface_matches_cpp_registration() -> None:
    ratio = (
        '{"numerator":{"value":10,"unit":"mg"},'
        '"denominator":{"value":4,"unit":"mL"}}'
    )
    ratio_code_units = (
        '{"numerator":{"value":5,"code":"mg"},'
        '"denominator":{"value":1,"code":"mL"}}'
    )

    expressions = [
        "SELECT ToDate('2024-01-15')::VARCHAR",
        "SELECT ToDate('2014-01')::VARCHAR",
        "SELECT ToDate('2014-01-01T12:30:00')::VARCHAR",
        "SELECT ToDateTime('2024-01-15T10:30:00')::VARCHAR",
        "SELECT ToDateTime('2024-01')::VARCHAR",
        "SELECT ToDateTime('2024-01-15T10:30:00+05:00')::VARCHAR",
        "SELECT ToTime('T10:30:00')::VARCHAR",
        "SELECT ToQuantity(5)",
        "SELECT ToQuantity(0.1)",
        "SELECT ToQuantity('5.5 ''cm''')",
        "SELECT ToQuantity('5')",
        "SELECT ToQuantity('999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999')",
        "SELECT ToQuantity('5 cm')",
        "SELECT ToQuantity(ToRatio('10 ''mg'':2 ''mL'''))",
        "SELECT parse_quantity('{\"value\":2.5,\"unit\":\"kg\"}')",
        "SELECT quantityValue('{\"value\":140,\"code\":\"mm[Hg]\"}')",
        "SELECT quantityUnit('{\"value\":140,\"unit\":\"mmHg\"}')",
        (
            "SELECT quantityCompare('{\"value\":1,\"code\":\"h\"}', "
            "'{\"value\":30,\"code\":\"min\"}', '>')"
        ),
        f"SELECT ratioNumeratorValue('{ratio}')",
        f"SELECT ratioDenominatorValue('{ratio}')",
        f"SELECT ratioValue('{ratio}')",
        f"SELECT ratioNumeratorUnit('{ratio_code_units}')",
        f"SELECT ratioDenominatorUnit('{ratio_code_units}')",
        "SELECT ratioValue('{\"numerator\":{\"value\":5},\"denominator\":{\"value\":0}}')",
    ]

    py = _python_only_connection()
    cpp = _cpp_connection()
    try:
        for expression in expressions:
            assert cpp.execute(expression).fetchone() == py.execute(expression).fetchone()
    finally:
        py.close()
        cpp.close()


def test_cql_temporal_complex_negative_boundaries_match_spec_and_backend_parity() -> None:
    expressions = {
        "SELECT ConvertsToDate('2024-13-01')": False,
        "SELECT ConvertsToDate('2024-02-30')": False,
        "SELECT ToDate('2024-02-30')": None,
        "SELECT ConvertsToDateTime('2024-01-01T25:00:00')": False,
        "SELECT ConvertsToDateTime('2024-01-01T10:00:00+99:99')": False,
        "SELECT ToDateTime('2024-01-01T10:00:00+99:99')": None,
        "SELECT ConvertsToTime('T25:00:00')": False,
        "SELECT ToTime('T10:00:00Z')": "10:00:00",
        "SELECT ConvertsToQuantity('5..5 ''cm''')": False,
        "SELECT ConvertsToQuantity('{\"value\":\"abc\",\"unit\":\"mg\"}')": False,
        "SELECT ToQuantity('5..5 ''cm''')": None,
        "SELECT ToQuantity(true)": None,
        "SELECT ConvertsToRatio('1.0 ''mg'':2.0 ''mg''')": True,
        "SELECT ConvertsToRatio('{\"numerator\":{},\"denominator\":{}}')": False,
        "SELECT ToRatio('{\"numerator\":{},\"denominator\":{}}')": None,
        "SELECT ratioValue('{\"numerator\":{\"value\":\"abc\"},\"denominator\":{\"value\":2}}')": None,
        "SELECT ratioDenominatorValue('{\"numerator\":{\"value\":1},\"denominator\":{\"value\":\"abc\"}}')": None,
    }

    py = _python_only_connection()
    cpp = _cpp_connection()
    try:
        for expression, expected in expressions.items():
            py_result = py.execute(expression).fetchone()[0]
            cpp_result = cpp.execute(expression).fetchone()[0]
            assert py_result == expected, expression
            assert cpp_result == expected, expression
    finally:
        py.close()
        cpp.close()


def test_cql_ratio_malformed_component_unit_helpers_match_no_python_cpp() -> None:
    expressions = [
        "SELECT ratioNumeratorUnit('{\"numerator\":5,\"denominator\":{\"value\":1}}')",
        "SELECT ratioDenominatorUnit('{\"numerator\":{\"value\":5},\"denominator\":5}')",
    ]

    py = _python_only_connection()
    cpp = _cpp_connection()
    try:
        with no_python_connection() as no_py:
            for expression in expressions:
                assert py.execute(expression).fetchone() == (None,)
                assert cpp.execute(expression).fetchone() == (None,)
                assert no_py.execute(expression).fetchone() == (None,)
    finally:
        py.close()
        cpp.close()


def test_translated_temporal_conversions_use_spec_aware_duckdb_surface() -> None:
    cases = {
        "ToDate('2014-01')": "2014-01",
        "ToDate('2024-02-30')": None,
        "ToDateTime('2014')": "2014",
        "ToDateTime('2024-02-30')": None,
        "convert '2014-01' to Date": "2014-01",
        "convert '2014' to DateTime": "2014",
    }

    py = _python_only_connection()
    cpp = _cpp_connection()
    try:
        for expression, expected in cases.items():
            sql = _translated_definition_sql(expression)
            py_result = py.execute(sql).fetchone()[0]
            cpp_result = cpp.execute(sql).fetchone()[0]
            assert py_result == expected, expression
            assert cpp_result == expected, expression
    finally:
        py.close()
        cpp.close()

    py = _python_only_connection()
    cpp = _cpp_connection()
    try:
        expression = "SELECT ToRatio('1.0 ''mg'':2.0 ''mg''')"
        py_result = py.execute(expression).fetchone()[0]
        cpp_result = cpp.execute(expression).fetchone()[0]
        assert py_result == cpp_result
        assert '"numerator"' in py_result and '"denominator"' in py_result

        quantity_expression = "SELECT ToQuantity(ToRatio('10 ''mg'':2 ''mL'''))"
        py_quantity = json.loads(py.execute(quantity_expression).fetchone()[0])
        cpp_quantity = json.loads(cpp.execute(quantity_expression).fetchone()[0])
        assert py_quantity == cpp_quantity
        assert py_quantity["value"] == 5.0
        assert py_quantity["unit"] == "mg/mL"
    finally:
        py.close()
        cpp.close()
