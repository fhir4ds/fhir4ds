"""CQL temporal and complex type parity checks."""

from __future__ import annotations

import duckdb

from fhir4ds.cql.duckdb import register
from fhir4ds.cql.duckdb.extension import _register_python_supplements
from fhir4ds.cql.parser import parse_expression
from fhir4ds.cql.parser.ast_nodes import DateTimeLiteral, FunctionRef, Quantity


def _python_only_connection() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect(config={"allow_unsigned_extensions": True})
    _register_python_supplements(con, cpp_loaded=False, include_fhirpath=True)
    return con


def _cpp_connection() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect(config={"allow_unsigned_extensions": True})
    register(con, include_fhirpath=True)
    return con


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
        "SELECT ToDateTime('2024-01-15T10:30:00')::VARCHAR",
        "SELECT ToTime('T10:30:00')::VARCHAR",
        "SELECT ToQuantity('5.5 ''cm''')",
        "SELECT ToQuantity('5')",
        "SELECT ToQuantity('5 cm')",
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
