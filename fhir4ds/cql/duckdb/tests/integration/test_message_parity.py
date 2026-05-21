"""CQL Message/error behavior parity checks."""

from __future__ import annotations

import pytest
import duckdb

from fhir4ds.cql.duckdb import register
from fhir4ds.cql.duckdb.extension import _register_python_supplements
from fhir4ds.cql.parser import parse_cql, parse_expression
from fhir4ds.cql.parser.ast_nodes import FunctionRef
from fhir4ds.cql.translator import CQLToSQLTranslator, translate_cql


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
    assert "CQLMessage" in translated["IdentifierSeverity"].to_sql()
    assert "CQLMessage" in translated["IdentifierWarning"].to_sql()
    assert "CQLMessage" in translated["ParameterSeverity"].to_sql()
    assert "getvariable('unresolvederrorlevel')" in translated["BareIdentifierSeverity"].to_sql()
    assert "CQLMessage" in translated["ErrorCondition"].to_sql()
    assert translated["NullCondition"].to_sql() == "'src'"
    assert "CQLMessage" in translated["ExpressionFalseCondition"].to_sql()


def test_cql_message_translated_sql_matches_cpp_registration() -> None:
    translated = translate_cql(_cql_message_library())
    expected = {
        "FalseCondition": "src",
        "WarningCondition": "src",
        "ParameterSeverity": "src",
        "BareIdentifierSeverity": "src",
        "NullCondition": "src",
        "ExpressionFalseCondition": "src",
    }

    py = _python_only_connection()
    cpp = _cpp_connection()
    try:
        for name, expected_value in expected.items():
            sql = f"SELECT {translated[name].to_sql()}"
            if name == "ParameterSeverity":
                py.execute("SELECT setvariable('errorlevelparameter', 'Warning')")
                cpp.execute("SELECT setvariable('errorlevelparameter', 'Warning')")
            if name == "BareIdentifierSeverity":
                py.execute("SELECT setvariable('unresolvederrorlevel', 'Warning')")
                cpp.execute("SELECT setvariable('unresolvederrorlevel', 'Warning')")
            assert py.execute(sql).fetchone() == (expected_value,), name
            assert cpp.execute(sql).fetchone() == (expected_value,), name

        py.execute("SELECT setvariable('errorlevelparameter', 'Error')")
        cpp.execute("SELECT setvariable('errorlevelparameter', 'Error')")
        py.execute("SELECT setvariable('unresolvederrorlevel', 'Error')")
        cpp.execute("SELECT setvariable('unresolvederrorlevel', 'Error')")
        for con in (py, cpp):
            with pytest.raises(duckdb.Error):
                con.execute(f"SELECT {translated['ErrorCondition'].to_sql()}").fetchone()
            with pytest.raises(duckdb.Error):
                con.execute(f"SELECT {translated['IdentifierSeverity'].to_sql()}").fetchone()
            with pytest.raises(duckdb.Error):
                con.execute(f"SELECT {translated['ParameterSeverity'].to_sql()}").fetchone()
            with pytest.raises(duckdb.Error):
                con.execute(f"SELECT {translated['BareIdentifierSeverity'].to_sql()}").fetchone()
    finally:
        py.close()
        cpp.close()


def test_cql_message_direct_surface_matches_cpp_registration() -> None:
    cases = [
        ("SELECT CQLMessage('src', false, 'code', 'Error', 'message')", ("src",)),
        ("SELECT CQLMessage('src', NULL, 'code', 'Error', 'message')", ("src",)),
        ("SELECT CQLMessage('src', true, 'code', 'Warning', 'message')", ("src",)),
        ("SELECT CQLMessage('src', 'false', 'code', 'Error', 'message')", ("src",)),
        ("SELECT CQLMessage(5, false, 'code', 'Warning', 'message')", (5,)),
        ("SELECT CQLMessage(TRUE, false, 'code', 'Warning', 'message')", (True,)),
        ("SELECT typeof(CQLMessage(5, false, 'code', 'Warning', 'message'))", ("INTEGER",)),
        ("SELECT typeof(CQLMessage(TRUE, false, 'code', 'Warning', 'message'))", ("BOOLEAN",)),
    ]

    py = _python_only_connection()
    cpp = _cpp_connection()
    try:
        for sql, expected in cases:
            assert py.execute(sql).fetchone() == expected
            assert cpp.execute(sql).fetchone() == expected

        for con in (py, cpp):
            for sql in [
                "SELECT CQLMessage('src', true, 'E001', 'Error', 'boom')",
                "SELECT CQLMessage('src', true, NULL, 'Error', 'boom')",
                "SELECT CQLMessage('src', true, 'E001', 'Error', NULL)",
                "SELECT CQLMessage('src', true, NULL, 'Error', NULL)",
            ]:
                with pytest.raises(duckdb.Error):
                    con.execute(sql).fetchone()
    finally:
        py.close()
        cpp.close()


def test_cql_message_null_code_or_message_still_raises_in_translated_sql() -> None:
    translated = translate_cql(
        """library MessageNullText version '1.0.0'
using FHIR version '4.0.1'
context Patient
define NullCode: Message('src', true, null as String, 'Error', 'boom')
define NullMessage: Message('src', true, 'E001', 'Error', null as String)
define NullCodeAndMessage: Message('src', true, null as String, 'Error', null as String)
"""
    )

    py = _python_only_connection()
    cpp = _cpp_connection()
    try:
        for con in (py, cpp):
            for name in ("NullCode", "NullMessage", "NullCodeAndMessage"):
                with pytest.raises(duckdb.Error):
                    con.execute(f"SELECT {translated[name].to_sql()}").fetchone()
    finally:
        py.close()
        cpp.close()


def test_cql_message_definition_severity_raises_in_population_sql() -> None:
    sql = CQLToSQLTranslator().translate_library_to_population_sql(
        parse_cql(
            """library MessagePopulation version '1.0.0'
using FHIR version '4.0.1'
context Patient
define ErrorLevel: 'Error'
define R: Message('src', true, 'E', ErrorLevel, 'boom')
"""
        ),
        output_columns={"R": "R"},
    )
    assert "CQLMessage" in sql

    py = _python_only_connection()
    cpp = _cpp_connection()
    try:
        for con in (py, cpp):
            con.execute("CREATE TABLE resources(resourceType VARCHAR, id VARCHAR, patient_ref VARCHAR, resource VARCHAR)")
            con.execute(
                """
                INSERT INTO resources VALUES
                ('Patient', 'p1', 'p1', '{"resourceType":"Patient","id":"p1"}')
                """
            )
            with pytest.raises(duckdb.Error):
                con.execute(sql).fetchall()
    finally:
        py.close()
        cpp.close()


def _cql_message_library() -> str:
    return """library MessageOps version '1.0.0'
using FHIR version '4.0.1'
parameter ErrorLevelParameter String default 'Warning'
context Patient
define ErrorLevel: 'Error'
define WarningLevel: 'Warning'
define FalseCondition: Message('src', false, 'code', 'Error', 'message')
define WarningCondition: Message('src', true, 'code', 'Warning', 'message')
define IdentifierSeverity: Message('src', true, 'code', ErrorLevel, 'message')
define IdentifierWarning: Message('src', true, 'code', WarningLevel, 'message')
define ParameterSeverity: Message('src', true, 'code', ErrorLevelParameter, 'message')
define BareIdentifierSeverity: Message('src', true, 'code', UnresolvedErrorLevel, 'message')
define ErrorCondition: Message('src', true, 'code', 'Error', 'message')
define NullCondition: Message('src', null, 'code', 'Error', 'message')
define ExpressionFalseCondition: Message('src', 1 = 2, 'code', 'Error', 'message')
"""
