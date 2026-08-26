"""CQL Message/error behavior parity checks."""

from __future__ import annotations

import pytest
import duckdb

from fhir4ds.cql.duckdb import register
from fhir4ds.cql.duckdb.extension import _register_python_supplements
from fhir4ds.cql.parser import parse_cql, parse_expression
from fhir4ds.cql.parser.ast_nodes import FunctionRef
from fhir4ds.cql.translator import CQLToSQLTranslator, translate_cql
from fhir4ds.cql.duckdb.tests.integration.wasm_runtime_helpers import no_python_connection
from fhir4ds.cql.errors import TranslationError


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
    assert translated["ParameterSeverity"].to_sql() == "'src'"
    assert "getvariable('unresolvederrorlevel')" in translated["BareIdentifierSeverity"].to_sql()
    assert "CQLMessage" in translated["ErrorCondition"].to_sql()
    assert translated["NullCondition"].to_sql() == "'src'"
    assert "CQLMessage" in translated["ExpressionFalseCondition"].to_sql()


def test_cql_message_rejects_statically_invalid_signature_operands() -> None:
    invalid_cases = [
        ("define BadConditionInteger: Message('src', 1, 'E', 'Error', 'boom')", "condition argument must be Boolean"),
        ("define BadConditionString: Message('src', 'true', 'E', 'Error', 'boom')", "condition argument must be Boolean"),
        ("define BadSeverityInteger: Message('src', true, 'E', 5, 'boom')", "severity argument must be String"),
        ("define BadSeverityBoolean: Message('src', true, 'E', true, 'boom')", "severity argument must be String"),
        ("define BadMessageInteger: Message('src', true, 'E', 'Warning', 5)", "message argument must be String"),
        ("define BadMessageBoolean: Message('src', true, 'E', 'Warning', false)", "message argument must be String"),
    ]
    for definition, expected_error in invalid_cases:
        with pytest.raises(TranslationError, match=expected_error):
            translate_cql(
                f"""library BadMessage version '1.0.0'
using FHIR version '4.0.1'
context Patient
{definition}
"""
            )


def test_cql_message_accepts_integer_code_token_per_spec() -> None:
    """CQL §13.1: 'code ... is a token (like a string or integer)'."""
    for definition in [
        "define IntCode: Message('src', false, 5, 'Warning', 'boom')",
        "define LongCode: Message('src', false, 5L, 'Warning', 'boom')",
        "define DecimalCode: Message('src', false, 5.0, 'Warning', 'boom')",
    ]:
        translated = translate_cql(
            f"""library IntCodeLib version '1.0.0'
using FHIR version '4.0.1'
context Patient
{definition}
"""
        )
        name = definition.split(":")[0].split()[-1]
        assert translated[name].to_sql() == "'src'", name


def test_cql_message_rejects_more_than_five_arguments_per_spec_cql22_historian() -> None:
    """CQL §13.1 Message signature is fixed at 5 args (source, condition,
    code, severity, message). More than 5 args must be rejected rather than
    silently truncated.
    """
    for definition in [
        "define AritySix: Message('src', true, 'C', 'Error', 'm', 'extra')",
        "define AritySeven: Message('src', true, 'C', 'Error', 'm', 'extra', 'more')",
    ]:
        with pytest.raises(TranslationError, match="at most 5 arguments"):
            translate_cql(
                f"""library TooManyArgs version '1.0.0'
using FHIR version '4.0.1'
context Patient
{definition}
"""
            )


def test_cql_message_accepts_four_argument_form_per_spec_cql22_historian() -> None:
    """CQL §13.1: 'If no severity is supplied, a default severity of Message
    is assumed.' The 4-arg form (no severity) must translate and return source.
    """
    translated = translate_cql(
        """library FourArg version '1.0.0'
using FHIR version '4.0.1'
context Patient
define FourArgTrue: Message('src', true, 'C', 'm')
define FourArgFalse: Message('src', false, 'C', 'm')
"""
    )
    assert translated["FourArgTrue"].to_sql() == "'src'"
    assert translated["FourArgFalse"].to_sql() == "'src'"


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


def test_cql_message_no_python_runtime_surface() -> None:
    translated = translate_cql(
        """library MessageNoPython version '1.0.0'
using FHIR version '4.0.1'
context Patient
define FalseCondition: Message(5, false, 'E', 'Error', 'boom')
define WarningCondition: Message(5, true, 'W', 'Warning', 'warn')
define TraceCondition: Message({1, 2, 3}, true, 'T', 'Trace', 'trace')
define ErrorCondition: Message(5, true, 'E', 'Error', 'boom')
"""
    )

    with no_python_connection() as con:
        assert con.execute("SELECT CQLMessage('src', false, 'E', 'Error', 'boom')").fetchone() == ("src",)
        assert con.execute("SELECT CQLMessage('src', NULL, 'E', 'Error', 'boom')").fetchone() == ("src",)
        assert con.execute("SELECT CQLMessage('src', true, 'W', 'Warning', 'warn')").fetchone() == ("src",)
        assert con.execute("SELECT typeof(CQLMessage(5, false, 'E', 'Error', 'boom'))").fetchone() == ("INTEGER",)
        with pytest.raises(duckdb.Error):
            con.execute("SELECT CQLMessage('src', true, 'E', 'Error', 'boom')").fetchone()

        assert con.execute(f"SELECT {translated['FalseCondition'].to_sql()}").fetchone() == (5,)
        assert con.execute(f"SELECT {translated['WarningCondition'].to_sql()}").fetchone() == (5,)
        assert con.execute(f"SELECT {translated['TraceCondition'].to_sql()}").fetchone() == ([1, 2, 3],)
        with pytest.raises(duckdb.Error):
            con.execute(f"SELECT {translated['ErrorCondition'].to_sql()}").fetchone()


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


def test_cql_message_integer_code_runtime_raises_per_spec() -> None:
    """CQL §13.1: 'code ... is a token (like a string or integer)'.

    Integer code with Error severity must raise at runtime on both the
    Python-fallback and C++-backed connections, with the integer code
    stringified into the error message.
    """
    translated = translate_cql(
        """library MessageIntCode version '1.0.0'
using FHIR version '4.0.1'
context Patient
define IntCodeError: Message('src', true, 42, 'Error', 'boom')
define IntCodePassthrough: Message('src', false, 42, 'Warning', 'warn')
"""
    )

    py = _python_only_connection()
    cpp = _cpp_connection()
    try:
        for con in (py, cpp):
            # False condition + Warning severity: integer code passes through
            # unchanged; result equals source.
            assert con.execute(
                f"SELECT {translated['IntCodePassthrough'].to_sql()}"
            ).fetchone() == ("src",)
            # True condition + Error severity: integer code is stringified
            # into the runtime error message ("42: boom").
            with pytest.raises(duckdb.Error) as exc_info:
                con.execute(f"SELECT {translated['IntCodeError'].to_sql()}").fetchone()
            assert "42" in str(exc_info.value)
            assert "boom" in str(exc_info.value)
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


def test_cql_message_runtime_parameter_severity_in_population_sql() -> None:
    library = parse_cql(
        """library MessageRuntimeParameter version '1.0.0'
using FHIR version '4.0.1'
parameter ErrorLevelParameter String default 'Warning'
context Patient
define R: Message('src', true, 'E', ErrorLevelParameter, 'boom')
"""
    )
    sql_default = CQLToSQLTranslator().translate_library_to_population_sql(
        library,
        output_columns={"R": "R"},
    )
    sql_error = CQLToSQLTranslator().translate_library_to_population_sql(
        library,
        output_columns={"R": "R"},
        parameters={"ErrorLevelParameter": "Error"},
    )

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
            assert con.execute(sql_default).fetchall() == [("p1", "src")]
            with pytest.raises(duckdb.Error):
                con.execute(sql_error).fetchall()
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


def test_cql_message_where_clause_in_navigation_query_applies_per_element_cql22_explorer() -> None:
    """CQL 1.5 §9 (Query where) + Appendix B (Message): the WHERE clause of a
    query over a multi-valued navigation source (`Patient.name N where ...
    return N.given`) must filter per element. Previously the where clause was
    silently discarded, returning unfiltered lists for every patient and
    swallowing Error-severity Message raises.
    """
    translated = translate_cql(
        """library NavQueryMessage version '1.0.0'
using FHIR version '4.0.1'
context Patient
define PlainWhere: Patient.name N where First(N.given) = 'Ann' return N.given
define MsgWarn: Patient.name N where Message(true, First(N.given) = 'Ann', 'F', 'Warning', 'note') return N.given
define MsgError: Patient.name N where Message(true, First(N.given) = 'Ann', 'F', 'Error', 'first given not Ann') return N.given
"""
    )
    assert "list_filter" in translated["MsgError"].to_sql()
    assert "CQLMessage" in translated["MsgError"].to_sql()

    def _setup(con):
        con.execute("CREATE TABLE patients (patient_id VARCHAR, patient_resource VARCHAR)")
        con.execute(
            "INSERT INTO patients VALUES ('p1', ?)",
            ['{"resourceType":"Patient","id":"p1","name":[{"given":["Ann","Marie"]},{"given":["Bob"]}]}'],
        )
        con.execute(
            "INSERT INTO patients VALUES ('p2', ?)",
            ['{"resourceType":"Patient","id":"p2","name":[{"given":["Zoe"]}]}'],
        )

    py = _python_only_connection()
    cpp = _cpp_connection()
    try:
        for con in (py, cpp):
            _setup(con)
            rows = con.execute(
                f"SELECT patient_id, ({translated['PlainWhere'].to_sql()}) AS v FROM patients _pt ORDER BY patient_id"
            ).fetchall()
            # p2 has no name whose first given is 'Ann' -> empty; p1 keeps only
            # the matching element (scalar per-element projection).
            assert rows[0][0] == "p1" and rows[0][1] is not None and "Ann" in rows[0][1]
            assert rows[1] == ("p2", []), rows
            # Warning severity passes through (no filtering, no raise)
            warn = con.execute(
                f"SELECT ({translated['MsgWarn'].to_sql()}) FROM patients _pt WHERE patient_id = 'p2'"
            ).fetchone()
            assert warn is not None
            # Error severity raises at execution on the non-matching element
            with pytest.raises(duckdb.Error, match="first given not Ann"):
                con.execute(
                    f"SELECT ({translated['MsgError'].to_sql()}) FROM patients _pt WHERE patient_id = 'p1'"
                ).fetchone()
    finally:
        py.close()
        cpp.close()
