"""CQL Message/error behavior parity checks."""

from __future__ import annotations

import pytest
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


def test_cql_message_expressions_parse_and_translate() -> None:
    for expression in [
        "Message('src', false, 'code', 'Error', 'message')",
        "Message('src', true, 'code', 'Warning', 'message')",
        "Message('src', true, 'code', 'Error', 'message')",
        "Message('src', null, 'code', 'Error', 'message')",
        "Message('src', 1 = 2, 'code', 'Error', 'message')",
    ]:
        assert isinstance(parse_expression(expression), FunctionRef)

    translated = translate_cql(_cql_message_library())
    assert translated["FalseCondition"].to_sql() == "'src'"
    assert translated["WarningCondition"].to_sql() == "'src'"
    assert "CQLMessage" in translated["ErrorCondition"].to_sql()
    assert translated["NullCondition"].to_sql() == "'src'"
    assert "CASE WHEN" in translated["ExpressionFalseCondition"].to_sql()


def test_cql_message_translated_sql_matches_cpp_registration() -> None:
    translated = translate_cql(_cql_message_library())
    expected = {
        "FalseCondition": "src",
        "WarningCondition": "src",
        "NullCondition": "src",
        "ExpressionFalseCondition": "src",
    }

    py = _python_only_connection()
    cpp = _cpp_connection()
    try:
        for name, expected_value in expected.items():
            sql = f"SELECT {translated[name].to_sql()}"
            assert py.execute(sql).fetchone() == (expected_value,), name
            assert cpp.execute(sql).fetchone() == (expected_value,), name

        for con in (py, cpp):
            with pytest.raises(duckdb.Error):
                con.execute(f"SELECT {translated['ErrorCondition'].to_sql()}").fetchone()
    finally:
        py.close()
        cpp.close()


def test_cql_message_direct_surface_matches_cpp_registration() -> None:
    cases = [
        ("SELECT CQLMessage('src', false, 'code', 'Error', 'message')", ("src",)),
        ("SELECT CQLMessage('src', NULL, 'code', 'Error', 'message')", ("src",)),
        ("SELECT CQLMessage('src', true, 'code', 'Warning', 'message')", ("src",)),
        ("SELECT CQLMessage('src', 'false', 'code', 'Error', 'message')", ("src",)),
    ]

    py = _python_only_connection()
    cpp = _cpp_connection()
    try:
        for sql, expected in cases:
            assert py.execute(sql).fetchone() == expected
            assert cpp.execute(sql).fetchone() == expected

        for con in (py, cpp):
            with pytest.raises(duckdb.Error):
                con.execute("SELECT CQLMessage('src', true, 'E001', 'Error', 'boom')").fetchone()
    finally:
        py.close()
        cpp.close()


def _cql_message_library() -> str:
    return """library MessageOps version '1.0.0'
using FHIR version '4.0.1'
context Patient
define FalseCondition: Message('src', false, 'code', 'Error', 'message')
define WarningCondition: Message('src', true, 'code', 'Warning', 'message')
define ErrorCondition: Message('src', true, 'code', 'Error', 'message')
define NullCondition: Message('src', null, 'code', 'Error', 'message')
define ExpressionFalseCondition: Message('src', 1 = 2, 'code', 'Error', 'message')
"""
