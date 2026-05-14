"""CQL arithmetic operator part 2 parity checks."""

from __future__ import annotations

import duckdb

from fhir4ds.cql.duckdb import register
from fhir4ds.cql.duckdb.extension import _register_python_supplements
from fhir4ds.cql.parser import parse_expression
from fhir4ds.cql.parser.ast_nodes import BinaryExpression, FunctionRef, UnaryExpression
from fhir4ds.cql.translator import translate_cql


def _python_only_connection() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect(config={"allow_unsigned_extensions": True})
    _register_python_supplements(con, cpp_loaded=False, include_fhirpath=True)
    return con


def _cpp_connection() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect(config={"allow_unsigned_extensions": True})
    register(con, include_fhirpath=True)
    return con


def test_cql_arithmetic_part2_expressions_parse_and_translate() -> None:
    for expression in [
        "maximum Integer",
        "minimum Integer",
        "Precision(1.2300)",
        "Power(2, 3)",
        "Round(3.456, 2)",
        "Truncate(3.7)",
    ]:
        parsed = parse_expression(expression)
        assert isinstance(parsed, FunctionRef)

    for expression, operator in [("5 mod 2", "mod"), ("5 * 2", "*"), ("10 div 3", "div")]:
        parsed = parse_expression(expression)
        assert isinstance(parsed, BinaryExpression)
        assert parsed.operator == operator

    for expression, operator in [
        ("-5", "-"),
        ("predecessor of @2024-01-15", "predecessor of"),
        ("successor of @2024-01-15", "successor of"),
    ]:
        parsed = parse_expression(expression)
        assert isinstance(parsed, UnaryExpression)
        assert parsed.operator == operator

    cql = """library Arithmetic2 version '1.0.0'
using FHIR version '4.0.1'
context Patient
define MaxInt: maximum Integer
define MinInt: minimum Integer
define ModCheck: 5 mod 2
define QuantityMod: 10 'mg' mod 3 'mg'
define MultiplyCheck: 5 * 2
define QuantityMultiply: 5 'm' * 3 's'
define NegateCheck: -5
define QuantityNegate: -(5 'mg')
define PrecisionCheck: Precision(1.2300)
define PredCheck: predecessor of @2024-01-15
define PowerCheck: Power(2, 3)
define RoundCheck: Round(3.456, 2)
define SubtractCheck: 5 - 2
define QuantitySubtract: 10 'mg' - 3 'mg'
define SuccCheck: successor of @2024-01-15
define TruncateCheck: Truncate(3.7)
define DivCheck: 10 div 3
define QuantityDivCheck: 10 'mg' div 3 'mg'
"""
    translated = translate_cql(cql)

    assert translated["MaxInt"].to_sql() == "2147483647"
    assert translated["MinInt"].to_sql() == "-2147483648"
    assert "operator='%'" in str(translated["ModCheck"])
    assert "quantityModulo" in str(translated["QuantityMod"])
    assert "operator='*'" in str(translated["MultiplyCheck"])
    assert "quantityMultiply" in str(translated["QuantityMultiply"])
    assert "operator='-'" in str(translated["NegateCheck"])
    assert "quantityNegate" in str(translated["QuantityNegate"])
    assert "CQLPrecision" in str(translated["PrecisionCheck"])
    assert "'1.2300'" in translated["PrecisionCheck"].to_sql()
    assert "predecessorOf" in str(translated["PredCheck"])
    assert "POW" in str(translated["PowerCheck"])
    assert "RoundTo" in str(translated["RoundCheck"])
    assert "operator='-'" in str(translated["SubtractCheck"])
    assert "quantity_subtract" in str(translated["QuantitySubtract"])
    assert "successorOf" in str(translated["SuccCheck"])
    assert "Truncate" in str(translated["TruncateCheck"])
    assert "TRUNC" in str(translated["DivCheck"])
    assert "quantityTruncatedDivide" in str(translated["QuantityDivCheck"])


def test_cql_arithmetic_part2_duckdb_surface_matches_cpp_registration() -> None:
    expressions = [
        "SELECT Round(3.456)::VARCHAR",
        "SELECT RoundTo(3.456, 2)::VARCHAR",
        "SELECT Power(2, 3)::VARCHAR",
        "SELECT Truncate(3.7)::VARCHAR",
        "SELECT Mod(5, 2)",
        "SELECT Div(10, 3)",
        "SELECT mathRound('2.5','0')",
        "SELECT mathRound('-2.5','0')",
        "SELECT mathRound('3.456','2')",
        "SELECT mathPower('2','10')",
        "SELECT mathPower('4','0.5')",
        "SELECT mathPower('-2','3')",
        "SELECT mathPower('-2','0.5')",
        "SELECT mathTruncate('2.9')",
        "SELECT mathTruncate('-2.9')",
        "SELECT CQLPrecision('2024-01-15T10:30:45.100')",
        "SELECT CQLPrecision('1.2300')",
        "SELECT predecessorOf('2024-01-15')",
        "SELECT successorOf('2024-01-15')",
        (
            "SELECT quantitySubtract('{\"value\":10,\"code\":\"mg\"}', "
            "'{\"value\":3,\"code\":\"mg\"}')"
        ),
        (
            "SELECT quantityMultiply('{\"value\":5,\"code\":\"m\"}', "
            "'{\"value\":3,\"code\":\"s\"}')"
        ),
        "SELECT quantityNegate('{\"value\":5,\"code\":\"mg\"}')",
        "SELECT quantityAbs('{\"value\":-5,\"code\":\"mg\"}')",
        (
            "SELECT quantityModulo('{\"value\":10,\"code\":\"mg\"}', "
            "'{\"value\":3,\"code\":\"mg\"}')"
        ),
        (
            "SELECT quantityTruncatedDivide('{\"value\":10,\"code\":\"mg\"}', "
            "'{\"value\":3,\"code\":\"mg\"}')"
        ),
    ]

    py = _python_only_connection()
    cpp = _cpp_connection()
    try:
        for expression in expressions:
            assert cpp.execute(expression).fetchone() == py.execute(expression).fetchone()
    finally:
        py.close()
        cpp.close()
