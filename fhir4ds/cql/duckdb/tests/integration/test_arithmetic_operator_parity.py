"""CQL arithmetic operator parity checks."""

from __future__ import annotations

import duckdb
import pytest

from fhir4ds.cql.duckdb import register
from fhir4ds.cql.duckdb.extension import _register_python_supplements
from fhir4ds.cql.parser import parse_expression
from fhir4ds.cql.parser.ast_nodes import BinaryExpression, FunctionRef
from fhir4ds.cql.translator import translate_cql


def _python_only_connection() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect(config={"allow_unsigned_extensions": True})
    _register_python_supplements(con, cpp_loaded=False, include_fhirpath=True)
    return con


def _cpp_connection() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect(config={"allow_unsigned_extensions": True})
    register(con, include_fhirpath=True)
    return con


def test_cql_arithmetic_expressions_parse_and_translate() -> None:
    for expression in [
        "Abs(-5)",
        "Ceiling(2.1)",
        "Floor(2.9)",
        "Exp(0)",
        "Ln(1)",
        "Log(100, 10)",
        "HighBoundary(@2024, 8)",
        "LowBoundary(@2024, 8)",
    ]:
        parsed = parse_expression(expression)
        assert isinstance(parsed, FunctionRef)

    for expression, operator in [("1 + 2", "+"), ("4 / 2", "/")]:
        parsed = parse_expression(expression)
        assert isinstance(parsed, BinaryExpression)
        assert parsed.operator == operator

    cql = """library Arithmetic version '1.0.0'
using FHIR version '4.0.1'
context Patient
define AddCheck: 1 + 2
define DivideCheck: 4 / 2
define QuantityAdd: 1 'g' + 500 'mg'
define ExpCheck: Exp(0)
define LnCheck: Ln(1)
define LogCheck: Log(100, 10)
define HighCheck: HighBoundary(@2024, 8)
define LowCheck: LowBoundary(@2024, 8)
"""
    translated = translate_cql(cql)

    assert "operator='+'" in str(translated["AddCheck"])
    assert "NULLIF" in str(translated["DivideCheck"])
    assert "quantity_add" in str(translated["QuantityAdd"])
    assert "mathExp" in str(translated["ExpCheck"])
    assert "CAST" in translated["ExpCheck"].to_sql()
    assert "mathLn" in str(translated["LnCheck"])
    assert "CAST" in translated["LnCheck"].to_sql()
    assert "system.log" in str(translated["LogCheck"])
    assert "HighBoundary" in str(translated["HighCheck"])
    assert "LowBoundary" in str(translated["LowCheck"])


def test_cql_arithmetic_duckdb_surface_matches_cpp_registration() -> None:
    expressions = [
        "SELECT Abs(-5)",
        "SELECT Ceiling(2.1)",
        "SELECT Floor(2.9)",
        "SELECT Exp(0)::VARCHAR",
        "SELECT Ln(1)::VARCHAR",
        "SELECT Log(100)::VARCHAR",
        "SELECT mathAbs('-5')",
        "SELECT mathCeiling('2.1')",
        "SELECT mathFloor('2.9')",
        "SELECT mathExp('0')",
        "SELECT mathLn('1')",
        "SELECT mathLn('-1')",
        "SELECT mathLog('100','10')",
        "SELECT mathLog('-1','10')",
        "SELECT mathLog('100','1')",
        "SELECT mathExp(CAST(0 AS VARCHAR))",
        "SELECT mathLn(CAST(1 AS VARCHAR))",
        "SELECT TRY(system.log(10, 100))::VARCHAR",
        "SELECT HighBoundary('2024', 8)",
        "SELECT LowBoundary('2024', 8)",
        "SELECT HighBoundary('2024-02', 8)",
        "SELECT LowBoundary('2024-02', 8)",
        (
            "SELECT quantityAdd('{\"value\":1,\"code\":\"g\"}', "
            "'{\"value\":500,\"code\":\"mg\"}')"
        ),
        (
            "SELECT quantityDivide('{\"value\":10,\"code\":\"m\"}', "
            "'{\"value\":2,\"code\":\"s\"}')"
        ),
    ]

    py = _python_only_connection()
    cpp = _cpp_connection()
    try:
        for expression in expressions:
            assert cpp.execute(expression).fetchone() == py.execute(expression).fetchone()

        for expression in ["SELECT mathExp('1000')", "SELECT mathLn('0')"]:
            with pytest.raises(duckdb.Error):
                py.execute(expression).fetchone()
            with pytest.raises(duckdb.Error):
                cpp.execute(expression).fetchone()
    finally:
        py.close()
        cpp.close()
