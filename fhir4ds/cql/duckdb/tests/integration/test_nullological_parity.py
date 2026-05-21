"""CQL nullological operator parity checks."""

from __future__ import annotations

import json
from datetime import date

import duckdb
import pytest

from fhir4ds.cql.duckdb import register
from fhir4ds.cql.duckdb.extension import _register_python_supplements
from fhir4ds.cql.errors import TranslationError
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


def test_cql_nullological_expressions_parse_and_translate() -> None:
    for expression in ["Coalesce(null, 'x')", "IsNull(null)", "IsTrue(true)", "IsFalse(false)"]:
        parsed = parse_expression(expression)
        assert isinstance(parsed, FunctionRef)

    cql = """library Nulls version '1.0.0'
using FHIR version '4.0.1'
context Patient
define C: Coalesce(null, 'x')
define T: IsTrue(true)
"""
    translated = translate_cql(cql)
    assert "COALESCE" in str(translated["C"]) or "Coalesce" in str(translated["C"])
    assert "IsTrue" in str(translated["T"])


def test_cql_nullological_duckdb_surface_matches_cpp_registration() -> None:
    expressions = [
        'SELECT "Coalesce"(NULL, \'world\')',
        'SELECT "Coalesce"(NULL, NULL, \'world\')',
        'SELECT "Coalesce"(\'first\', \'second\')',
        'SELECT "Coalesce"(NULL, NULL, DATE \'2020-01-02\')',
        'SELECT "Coalesce"(NULL, NULL, TIMESTAMP \'2012-05-18 00:00:00\')',
        'SELECT "Coalesce"([NULL, 5])',
        'SELECT "Coalesce"([])',
        'SELECT "Coalesce"([NULL, NULL])',
        'SELECT "IsNull"(NULL)',
        'SELECT "IsNull"(1)',
        'SELECT "IsTrue"(true)',
        'SELECT "IsTrue"(false)',
        'SELECT "IsTrue"(NULL)',
        'SELECT "IsTrue"(CAST(NULL AS BOOLEAN))',
        'SELECT "IsTrue"(1)',
        'SELECT "IsTrue"(\'true\')',
        'SELECT "IsFalse"(false)',
        'SELECT "IsFalse"(true)',
        'SELECT "IsFalse"(NULL)',
        'SELECT "IsFalse"(CAST(NULL AS BOOLEAN))',
        'SELECT "IsFalse"(0)',
        'SELECT "IsFalse"(\'false\')',
        'SELECT logicalCoalesce(\'[null, null, "5"]\')',
        'SELECT logicalCoalesce(\'[null, true, false]\')',
        'SELECT logicalCoalesce(\'[null, {"x": 1}]\')',
        "SELECT logicalCoalesce('[]')",
        "SELECT logicalCoalesce(NULL)",
    ]

    py = _python_only_connection()
    cpp = _cpp_connection()
    try:
        for expression in expressions:
            assert cpp.execute(expression).fetchone() == py.execute(expression).fetchone()
    finally:
        py.close()
        cpp.close()


def test_cql_nullological_static_definition_aliases_execute_standalone() -> None:
    cql = """library NullAliases version '1.0.0'
using FHIR version '4.0.1'
context Patient
define StringAlias: 'x'
define BoolAlias: true
define FalseAlias: false
define NullAlias: null
define CoalesceStringAlias: Coalesce(null, StringAlias)
define CoalesceListAliases: Coalesce({NullAlias, StringAlias})
define DateTimeCoalesce: Coalesce(null, null, DateTime(2012, 5, 18))
define DateTimeListCoalesce: Coalesce({null, null, DateTime(2012, 5, 18)})
define TrueAliasCheck: IsTrue(BoolAlias)
define FalseAliasCheck: IsFalse(FalseAlias)
define NullAliasCheck: IsNull(NullAlias)
"""
    translated = translate_cql(cql)
    expected = {
        "CoalesceStringAlias": ("x",),
        "CoalesceListAliases": ("x",),
        "DateTimeCoalesce": ("2012-05-18T",),
        "DateTimeListCoalesce": ("2012-05-18T",),
        "TrueAliasCheck": (True,),
        "FalseAliasCheck": (True,),
        "NullAliasCheck": (True,),
    }

    py = _python_only_connection()
    cpp = _cpp_connection()
    try:
        for name, expected_result in expected.items():
            sql = translated[name].to_sql()
            assert "_pt.patient_id" not in sql
            py_result = py.execute(f"SELECT {sql}").fetchone()
            cpp_result = cpp.execute(f"SELECT {sql}").fetchone()
            assert py_result == expected_result, name
            assert cpp_result == expected_result, name

        assert py.execute('SELECT "IsTrue"(1)').fetchone() == (False,)
        assert py.execute('SELECT "IsTrue"(\'true\')').fetchone() == (False,)
        assert py.execute('SELECT "IsTrue"(CAST(NULL AS BOOLEAN))').fetchone() == (False,)
        assert py.execute('SELECT "IsFalse"(0)').fetchone() == (False,)
        assert py.execute('SELECT "IsFalse"(\'false\')').fetchone() == (False,)
        assert py.execute('SELECT "IsFalse"(CAST(NULL AS BOOLEAN))').fetchone() == (False,)
        assert py.execute('SELECT "Coalesce"(NULL, NULL, \'world\')').fetchone() == ("world",)
        assert py.execute('SELECT "Coalesce"(NULL, NULL, DATE \'2020-01-02\')').fetchone() == (date(2020, 1, 2),)
        assert py.execute('SELECT "Coalesce"(NULL, NULL, TIMESTAMP \'2012-05-18 00:00:00\')').fetchone() == ("2012-05-18T00:00:00",)
        assert py.execute('SELECT "Coalesce"([NULL, 5])').fetchone() == (5,)
        assert py.execute('SELECT "Coalesce"([])').fetchone() == (None,)
        assert py.execute('SELECT "Coalesce"([NULL, NULL])').fetchone() == (None,)
        assert py.execute('SELECT logicalCoalesce(\'[null, {"x": 1}]\')').fetchone() == ('{"x":1}',)
    finally:
        py.close()
        cpp.close()


def test_cql_infix_is_true_false_rejects_sql_truthiness() -> None:
    cql = """library NullTruthiness version '1.0.0'
using FHIR version '4.0.1'
context Patient
define NumIsTrue: 1 is true
define ZeroIsFalse: 0 is false
define StrIsTrue: 'true' is true
define BoolIsTrue: true is true
define BoolIsFalse: false is false
define NotTrueOnFalse: false is not true
define NotFalseOnTrue: true is not false
"""
    translated = translate_cql(cql)
    expected = {
        "NumIsTrue": (False,),
        "ZeroIsFalse": (False,),
        "StrIsTrue": (False,),
        "BoolIsTrue": (True,),
        "BoolIsFalse": (True,),
        "NotTrueOnFalse": (True,),
        "NotFalseOnTrue": (True,),
    }

    py = _python_only_connection()
    cpp = _cpp_connection()
    try:
        for name, expected_result in expected.items():
            sql = translated[name].to_sql()
            assert " IS TRUE" not in sql
            assert " IS FALSE" not in sql
            assert py.execute(f"SELECT {sql}").fetchone() == expected_result, name
            assert cpp.execute(f"SELECT {sql}").fetchone() == expected_result, name
    finally:
        py.close()
        cpp.close()


def test_cql_coalesce_rejects_invalid_scalar_arities_but_allows_list() -> None:
    invalid_bodies = [
        "define X: Coalesce()",
        "define X: Coalesce(1)",
        "define X: Coalesce(null, null, null, null, null, 1)",
    ]
    for body in invalid_bodies:
        cql = f"""library BadCoalesce version '1.0.0'
using FHIR version '4.0.1'
context Patient
{body}
"""
        with pytest.raises(TranslationError, match="Coalesce scalar overload"):
            translate_cql(cql)

    valid_cql = """library GoodCoalesce version '1.0.0'
using FHIR version '4.0.1'
context Patient
define EmptyList: Coalesce({})
define ListValue: Coalesce({null, 'x'})
define FiveScalar: Coalesce(null, null, null, null, 'y')
"""
    translated = translate_cql(valid_cql)
    expected = {
        "EmptyList": (None,),
        "ListValue": ("x",),
        "FiveScalar": ("y",),
    }
    py = _python_only_connection()
    cpp = _cpp_connection()
    try:
        for name, expected_result in expected.items():
            sql = translated[name].to_sql()
            assert py.execute(f"SELECT {sql}").fetchone() == expected_result, name
            assert cpp.execute(f"SELECT {sql}").fetchone() == expected_result, name
    finally:
        py.close()
        cpp.close()


def test_cql_is_true_false_preserves_dynamic_fhir_boolean_values() -> None:
    cql = """library DynamicNullTruthiness version '1.0.0'
using FHIR version '4.0.1'
context Patient
define ActiveInfix: Patient.active is true
define ActiveFunc: IsTrue(Patient.active)
define NotActiveInfix: Patient.active is false
define NotActiveFunc: IsFalse(Patient.active)
"""
    population_sql = CQLToSQLTranslator().translate_library_to_population_sql(
        parse_cql(cql),
        output_columns={
            "active_infix": "ActiveInfix",
            "active_func": "ActiveFunc",
            "not_active_infix": "NotActiveInfix",
            "not_active_func": "NotActiveFunc",
        },
    )
    assert "fhirpath_bool" in population_sql
    assert " IS TRUE" not in population_sql
    assert " IS FALSE" not in population_sql

    patient = json.dumps({"resourceType": "Patient", "id": "p1", "active": True})
    py = _python_only_connection()
    cpp = _cpp_connection()
    try:
        for con in (py, cpp):
            con.execute(
                "CREATE TABLE resources (id VARCHAR, resourceType VARCHAR, resource JSON, patient_ref VARCHAR)"
            )
            con.execute("INSERT INTO resources VALUES ('p1', 'Patient', ?::JSON, 'p1')", [patient])
            assert con.execute(population_sql).fetchone() == ("p1", True, True, False, False)
    finally:
        py.close()
        cpp.close()
