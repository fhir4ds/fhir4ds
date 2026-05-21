"""Parity checks for the public fhir4ds.core DuckDB registration surface."""

from __future__ import annotations

import duckdb

from fhir4ds.core import register


def _cpp_connection() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect(config={"allow_unsigned_extensions": True})
    status = register(con)
    assert status == {"fhirpath_cpp": True, "cql_cpp": True}
    return con


def _python_fallback_connection(monkeypatch) -> duckdb.DuckDBPyConnection:
    monkeypatch.setattr(duckdb, "__version__", "0.0.0-forced-python-fallback")
    con = duckdb.connect(config={"allow_unsigned_extensions": True})
    status = register(con)
    assert status == {"fhirpath_cpp": False, "cql_cpp": False}
    return con


def test_core_register_conversion_checks_forced_python_fallback_matches_cpp(monkeypatch) -> None:
    expressions = [
        "SELECT ConvertsToBoolean('true')",
        "SELECT ConvertsToBoolean('1.0')",
        "SELECT ConvertsToBoolean('maybe')",
        "SELECT ConvertsToDate('2024-01-15')",
        "SELECT ConvertsToDate(2024)",
        "SELECT ConvertsToDate(TIMESTAMP '2024-01-15 10:30:00')",
        "SELECT ConvertsToDate('2024-02-30')",
        "SELECT ConvertsToDateTime('2024-01-15T10:30:00')",
        "SELECT ConvertsToDateTime(2024)",
        "SELECT ConvertsToDateTime('2024-01-01T25:00:00')",
        "SELECT ConvertsToDecimal('1.25')",
        "SELECT ConvertsToDecimal('1e2')",
        "SELECT ConvertsToDecimal('1.123456789')",
        "SELECT ConvertsToDecimal('1000000000000000000000000000000')",
        "SELECT ConvertsToDecimal(true)",
        "SELECT ConvertsToInteger('42')",
        "SELECT ConvertsToLong('9223372036854775807')",
        "SELECT ConvertsToQuantity(5)",
        "SELECT ConvertsToQuantity('5 ''mg''')",
        "SELECT ConvertsToQuantity('5 ''year''')",
        "SELECT ConvertsToQuantity('5 ''not-a-unit''')",
        "SELECT ConvertsToQuantity('.5 ''mg''')",
        "SELECT ConvertsToQuantity('5..5 ''mg''')",
        "SELECT ConvertsToQuantity('{\"value\":\"abc\",\"unit\":\"mg\"}')",
        "SELECT ConvertsToRatio('1.0 ''mg'':2.0 ''mg''')",
        "SELECT ConvertsToRatio('.5 ''mg'':2.0 ''mg''')",
        "SELECT ConvertsToRatio('1.0 ''not-a-unit'':2.0 ''mg''')",
        "SELECT ConvertsToString('abc')",
        "SELECT ConvertsToTime('T10:30:00')",
        "SELECT ConvertsToTime('T10:30:00Z')",
        "SELECT ConvertsToTime('T25:00:00')",
        "SELECT CanConvertQuantity('1000 ''mg''', 'g')",
        "SELECT ConvertQuantity('1000 ''mg''', 'g')",
        "SELECT ToDateTime('2024-01-15T10:30:00+05:00')",
        "SELECT ToDateTime('2024-01-15T10:30:00+99:99')",
        "SELECT ToTime('T10:30:00Z')",
        "SELECT ToQuantity(5)",
        "SELECT ToQuantity(ToRatio('10 ''mg'':2 ''mL'''))",
        "SELECT ToRatio('1.0 ''mg'':2.0 ''mg''')",
        "SELECT RatioToString(ToRatio('10 ''mg'':2 ''mL'''))",
    ]

    cpp = _cpp_connection()
    py = _python_fallback_connection(monkeypatch)
    try:
        for expression in expressions:
            assert cpp.execute(expression).fetchone() == py.execute(expression).fetchone()
    finally:
        cpp.close()
        py.close()
