"""CQL nullological operator parity checks."""

from __future__ import annotations

import json
from datetime import date

from decimal import Decimal

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


def test_cql_boolean_coalesce_remains_boolean_for_predicates() -> None:
    cql = """library BooleanCoalesce version '1.0.0'
using FHIR version '4.0.1'
context Patient
define ScalarFalse: Coalesce(null as Boolean, false) is false
define ScalarTrue: Coalesce(null as Boolean, true) is true
define ListFalse: Coalesce({null as Boolean, false, true}) is false
define ListTrue: Coalesce({null as Boolean, true, false}) is true
define StringTrueIsNotBoolean: Coalesce(null as String, 'true') is true
define NumberOneIsNotBoolean: Coalesce(null as Integer, 1) is true
"""
    translated = translate_cql(cql)
    expected = {
        "ScalarFalse": (True,),
        "ScalarTrue": (True,),
        "ListFalse": (True,),
        "ListTrue": (True,),
        "StringTrueIsNotBoolean": (False,),
        "NumberOneIsNotBoolean": (False,),
    }

    direct_queries = {
        'SELECT "Coalesce"(NULL, false)': (False,),
        'SELECT "Coalesce"(NULL, true)': (True,),
        'SELECT "Coalesce"([NULL::BOOLEAN, false])': (False,),
        'SELECT "IsFalse"("Coalesce"([NULL::BOOLEAN, false]))': (True,),
        'SELECT "IsTrue"("Coalesce"([NULL::BOOLEAN, true]))': (True,),
        'SELECT "IsTrue"("Coalesce"(NULL, \'true\'))': (False,),
        'SELECT "IsTrue"("Coalesce"(NULL, 1))': (False,),
    }

    py = _python_only_connection()
    cpp = _cpp_connection()
    try:
        for name, expected_result in expected.items():
            sql = translated[name].to_sql()
            assert py.execute(f"SELECT {sql}").fetchone() == expected_result, name
            assert cpp.execute(f"SELECT {sql}").fetchone() == expected_result, name
        for sql, expected_result in direct_queries.items():
            assert py.execute(sql).fetchone() == expected_result, sql
            assert cpp.execute(sql).fetchone() == expected_result, sql
    finally:
        py.close()
        cpp.close()


def test_cql_coalesce_quantity_results_use_quantity_comparison() -> None:
    cql = """library QuantityCoalesce version '1.0.0'
using FHIR version '4.0.1'
context Patient
define LiteralQuantity: Coalesce({null as Quantity, 5 'mg'}) = 5 'mg'
define QueryQuantity: Coalesce((from {null as Quantity, 5 'mg'} Q return Q)) = 5 'mg'
define QueryQuantityConverted: Coalesce((from {null as Quantity, 5000 'mg'} Q return Q)) = 5 'g'
"""
    translated = translate_cql(cql)
    expected = {
        "LiteralQuantity": (True,),
        "QueryQuantity": (True,),
        "QueryQuantityConverted": (True,),
    }
    py = _python_only_connection()
    cpp = _cpp_connection()
    try:
        for name, expected_result in expected.items():
            sql = translated[name].to_sql()
            assert "quantity_compare" in sql
            assert py.execute(f"SELECT {sql}").fetchone() == expected_result, name
            assert cpp.execute(f"SELECT {sql}").fetchone() == expected_result, name
    finally:
        py.close()
        cpp.close()


def test_cql_quantity_value_after_coalesce_is_numeric() -> None:
    cql = """library QuantityValueCoalesce version '1.0.0'
using FHIR version '4.0.1'
context Patient
define function IndexQuantity(): Coalesce(null as Quantity, 5 'mg')
define QuantityValueRatio: IndexQuantity().value / 0.9
define QuantityValueMin: Min({IndexQuantity().value / 0.9, 1}) = 1
"""
    translated = translate_cql(cql)
    expected = {
        "QuantityValueRatio": (Decimal("5.55555556"),),  # CQL-01 exact DECIMAL(38,8) division via cqlDivide
        "QuantityValueMin": (True,),
    }
    py = _python_only_connection()
    cpp = _cpp_connection()
    try:
        for name, expected_result in expected.items():
            sql = translated[name].to_sql()
            if name == "QuantityValueMin":
                assert "list_min" in sql
            assert py.execute(f"SELECT {sql}").fetchone() == expected_result, name
            assert cpp.execute(f"SELECT {sql}").fetchone() == expected_result, name
    finally:
        py.close()
        cpp.close()


def test_cql_coalesce_rejects_invalid_scalar_arities_but_allows_list() -> None:
    invalid_bodies = [
        "define X: Coalesce()",
        "define X: Coalesce(1)",
        # CQL 1.5 §Coalesce: arguments must be implicitly castable to a
        # common type; String and Integer are not — rejected in BOTH orders.
        "define X: Coalesce(null, 1, 'x')",
        "define X: Coalesce(null, 'x', 1)",
    ]
    for body in invalid_bodies[:2]:
        cql = f"""library BadCoalesce version '1.0.0'
using FHIR version '4.0.1'
context Patient
{body}
"""
        with pytest.raises(TranslationError, match="Coalesce scalar overload"):
            translate_cql(cql)
    for body in invalid_bodies[2:]:
        cql = f"""library BadCoalesce version '1.0.0'
using FHIR version '4.0.1'
context Patient
{body}
"""
        with pytest.raises(TranslationError, match="implicitly castable"):
            translate_cql(cql)

    # CQL 1.5 §Coalesce: scalar invocation is variadic with no upper bound.
    valid_cql = """library GoodCoalesce version '1.0.0'
using FHIR version '4.0.1'
context Patient
define EmptyList: Coalesce({})
define ListValue: Coalesce({null, 'x'})
define FiveScalar: Coalesce(null, null, null, null, 'y')
define SixScalar: Coalesce(null, null, null, null, null, 1)
define NineScalar: Coalesce(null, null, null, null, null, null, null, null, 2)
"""
    translated = translate_cql(valid_cql)
    expected = {
        "EmptyList": (None,),
        "ListValue": ("x",),
        "FiveScalar": ("y",),
        "SixScalar": (1,),
        "NineScalar": (2,),
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


def test_cql_coalesce_single_query_list_overload_returns_first_non_null() -> None:
    cql = """library QueryListCoalesce version '1.0.0'
using FHIR version '4.0.1'
context Patient
define StringQuery: (from {null as String, 'x'} V return V)
define QueryListValue: Coalesce(StringQuery)
define InlineQueryListValue: Coalesce((from {null as String, 'y'} V return V))
"""
    translated = translate_cql(cql)
    expected = {
        "QueryListValue": ("x",),
        "InlineQueryListValue": ("y",),
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


def test_cql_direct_coalesce_rejects_invalid_scalar_arities() -> None:
    invalid = [
        'SELECT "Coalesce"(1)',
        'SELECT "Coalesce"(NULL)',
    ]
    py = _python_only_connection()
    cpp = _cpp_connection()
    try:
        for con in (py, cpp):
            for sql in invalid:
                with pytest.raises(Exception, match="Coalesce scalar overload"):
                    con.execute(sql).fetchone()
            assert con.execute('SELECT "Coalesce"([NULL, 5])').fetchone() == (5,)
            assert con.execute('SELECT "Coalesce"(NULL, NULL)').fetchone() == (None,)
            assert con.execute('SELECT "Coalesce"(NULL, NULL, NULL, NULL, 5)').fetchone() == (5,)
            # Variadic scalar overload has no upper bound (CQL 1.5 §Coalesce).
            assert con.execute('SELECT "Coalesce"(NULL, NULL, NULL, NULL, NULL, 6)').fetchone() == (6,)
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
define ActiveDefaultFalse: Coalesce(Patient.active, false) is false
define ActiveDefaultTrue: Coalesce(Patient.active, true) is true
"""
    population_sql = CQLToSQLTranslator().translate_library_to_population_sql(
        parse_cql(cql),
        output_columns={
            "active_infix": "ActiveInfix",
            "active_func": "ActiveFunc",
            "not_active_infix": "NotActiveInfix",
            "not_active_func": "NotActiveFunc",
            "active_default_false": "ActiveDefaultFalse",
            "active_default_true": "ActiveDefaultTrue",
        },
    )
    assert "fhirpath_bool" in population_sql
    assert " IS TRUE" not in population_sql
    assert " IS FALSE" not in population_sql

    patients = [
        ("pfalse", {"resourceType": "Patient", "id": "pfalse", "active": False}),
        ("pmissing", {"resourceType": "Patient", "id": "pmissing"}),
        ("ptrue", {"resourceType": "Patient", "id": "ptrue", "active": True}),
    ]
    expected_rows = [
        ("pfalse", False, False, True, True, True, False),
        ("pmissing", False, False, False, False, True, True),
        ("ptrue", True, True, False, False, False, True),
    ]
    py = _python_only_connection()
    cpp = _cpp_connection()
    try:
        for con in (py, cpp):
            con.execute(
                "CREATE TABLE resources (id VARCHAR, resourceType VARCHAR, resource JSON, patient_ref VARCHAR)"
            )
            for patient_id, patient in patients:
                con.execute(
                    "INSERT INTO resources VALUES (?, 'Patient', ?::JSON, ?)",
                    [patient_id, json.dumps(patient), patient_id],
                )
            assert con.execute(population_sql).fetchall() == expected_rows
    finally:
        py.close()
        cpp.close()


def test_cql_infix_nullological_inlines_static_define_aliases_cql08_skeptic() -> None:
    """CQL-08 SKEPTIC: infix `is true`/`is false`/`is null` must inline static
    `define` aliases the same way the function-call forms (`IsTrue`, `IsFalse`,
    `IsNull`) already do.

    Spec citation: CQL v1.5.3 Developer's Guide — Nullological Operators and
    Translation Semantics Table 6-F (`is true` → `IsTrue`, `is false` →
    `IsFalse`, `is null` → `IsNull`). The infix and function-call forms are
    semantically equivalent; their generated SQL must therefore be identical
    when the operand is a top-level `define` alias wrapping a static literal.
    """
    cql = """library InfixInline version '1.0.0'
using FHIR version '4.0.1'
context Patient
define BoolAlias: true
define StrAlias: 'hello'
define InfixIsTrue: BoolAlias is true
define InfixIsFalse: BoolAlias is false
define InfixIsNull: BoolAlias is null
define InfixIsNotTrue: BoolAlias is not true
define InfixIsNotFalse: BoolAlias is not false
define FuncIsTrue: IsTrue(BoolAlias)
define FuncIsFalse: IsFalse(BoolAlias)
define FuncIsNull: IsNull(BoolAlias)
define StrInfixIsNull: StrAlias is null
define StrInfixIsNotNull: StrAlias is not null
"""
    translated = translate_cql(cql)

    # Function-call forms must continue to inline the alias.
    assert translated["FuncIsTrue"].to_sql() == "IsTrue(TRUE)"
    assert translated["FuncIsFalse"].to_sql() == "IsFalse(TRUE)"
    assert translated["FuncIsNull"].to_sql() == "IsNull(TRUE)"

    # Infix forms must match the function-call forms after the CQL-08 SKEPTIC
    # fix. Before the fix, each infix form emitted an EXISTS subquery against
    # a non-existent table named after the alias.
    assert translated["InfixIsTrue"].to_sql() == "IsTrue(TRUE)"
    assert translated["InfixIsFalse"].to_sql() == "IsFalse(TRUE)"
    assert translated["InfixIsNull"].to_sql() == "TRUE IS NULL"
    assert translated["InfixIsNotTrue"].to_sql() == "NOT IsTrue(TRUE)"
    assert translated["InfixIsNotFalse"].to_sql() == "NOT IsFalse(TRUE)"

    # Non-Boolean scalar aliases must also inline for null-test operators.
    assert translated["StrInfixIsNull"].to_sql() == "'hello' IS NULL"
    assert translated["StrInfixIsNotNull"].to_sql() == "'hello' IS NOT NULL"

    # Execution parity between Python fallback and native C++ registration.
    py = _python_only_connection()
    cpp = _cpp_connection()
    expected = {
        "InfixIsTrue": (True,),
        "InfixIsFalse": (False,),
        "InfixIsNull": (False,),
        "InfixIsNotTrue": (False,),
        "InfixIsNotFalse": (True,),
        "StrInfixIsNull": (False,),
        "StrInfixIsNotNull": (True,),
    }
    try:
        for name, expected_result in expected.items():
            sql = translated[name].to_sql()
            py_result = py.execute(f"SELECT {sql}").fetchone()
            cpp_result = cpp.execute(f"SELECT {sql}").fetchone()
            assert py_result == expected_result, name
            assert cpp_result == expected_result, name
    finally:
        py.close()
        cpp.close()



def test_cql_coalesce_variadic_over_fhir_boolean_defaults_cql08() -> None:
    """CQL-08 SKEPTIC (2026-08-20): the scalar Coalesce overload is variadic
    with no upper bound (CQL 1.5 §Coalesce — "first non-null expression among
    two or more"). A six-argument Coalesce over a dynamic FHIR Boolean field
    with a static null tail must translate (population context) and the static
    tail must execute on both backends.
    """
    cql = """library VariadicCoalesce version '1.0.0'
using FHIR version '4.0.1'
context Patient
define ActiveDefault: Coalesce(Patient.active, null, null, null, null, false)
define AllNullTail: Coalesce(null, null, null, null, null, null)
define NumericSix: Coalesce(null, null, null, null, null, 7)
"""
    translated = translate_cql(cql)
    active_sql = translated["ActiveDefault"].to_sql()
    assert "COALESCE" in active_sql
    assert "fhirpath_bool" in active_sql

    py = _python_only_connection()
    cpp = _cpp_connection()
    try:
        for con in (py, cpp):
            null_sql = translated["AllNullTail"].to_sql()
            numeric_sql = translated["NumericSix"].to_sql()
            assert con.execute(f"SELECT {null_sql}").fetchone() == (None,)
            assert con.execute(f"SELECT {numeric_sql}").fetchone() == (7,)
    finally:
        py.close()
        cpp.close()


def test_cql_coalesce_nested_static_type_guard_cql08_historian() -> None:
    """CQL-08 HISTORIAN QA-002: a nested Coalesce call must propagate its
    static return type (the first non-null argument's type per CQL 1.5
    §Coalesce) so that a String/numeric family mix inside nested Coalesce
    arguments is rejected at translation with the same typed TranslationError
    as the flat form — instead of leaking a raw DuckDB binder error at
    execution time."""
    header = "library NestedCoalesce version '1.0.0'\nusing FHIR version '4.0.1'\ncontext Patient\n"
    rejected = [
        "Coalesce(1, Coalesce(null, 'a'))",
        "Coalesce(Coalesce(null, 'a'), 1)",
        "Coalesce(1, Coalesce(null as String))",
    ]
    for expr in rejected:
        with pytest.raises(TranslationError, match="implicitly castable"):
            translate_cql(header + f"define X:\n  {expr}\n")

    accepted = {
        "Coalesce(1, Coalesce(null, 2))": 1,
        "Coalesce(null, Coalesce(null, 'a'))": "a",
        "Coalesce(Coalesce(null, null), 5)": 5,
        "Coalesce('a', Coalesce(null, 'b'))": "a",
    }
    translated = translate_cql(
        header
        + "\n".join(f"define D{i}:\n  {expr}" for i, expr in enumerate(accepted))
    )
    py = _python_only_connection()
    cpp = _cpp_connection()
    try:
        for i, expected in enumerate(accepted.values()):
            sql = f"SELECT {translated[f'D{i}'].to_sql()}"
            assert py.execute(sql).fetchone() == (expected,)
            assert cpp.execute(sql).fetchone() == (expected,)
    finally:
        py.close()
        cpp.close()


def test_cql_to_integer_long_reject_decimal_cql08_historian() -> None:
    """CQL-08 HISTORIAN QA-001: CQL 1.5 Appendix B Table 9-E defines no
    Decimal->Integer/Long conversion (ToInteger overloads: Boolean/String/
    Long; ToLong: Boolean/String). Decimal inputs yield null/false on BOTH
    the native and Python-fallback registration surfaces; the spec's
    truncation behavior belongs to the separate Truncate operator."""
    header = "library DecReject version '1.0.0'\nusing FHIR version '4.0.1'\ncontext Patient\n"
    translated = translate_cql(
        header
        + "\n".join(
            [
                "define TI: ToInteger(1.5)",
                "define TINeg: ToInteger(-1.5)",
                "define TL: ToLong(2.5)",
                "define CTI: CanConvert(1.5, Integer)",
                "define CTL: CanConvert(2.5, Long)",
                "define ConvTI: convert 2.7 to Integer",
                "define TIString: ToInteger('1.5')",
                "define TIValid: ToInteger('-25')",
            ]
        )
    )
    expected = {
        "TI": None,
        "TINeg": None,
        "TL": None,
        "CTI": False,
        "CTL": False,
        "ConvTI": None,
        "TIString": None,
        "TIValid": -25,
    }
    py = _python_only_connection()
    cpp = _cpp_connection()
    try:
        for name, value in expected.items():
            sql = f"SELECT {translated[name].to_sql()}"
            assert py.execute(sql).fetchone() == (value,), name
            assert cpp.execute(sql).fetchone() == (value,), name
    finally:
        py.close()
        cpp.close()


def test_cql_is_null_over_query_valued_lists_fixture_semantics_cql08_explorer() -> None:
    """CQL-08 EXPLORER pin: query-valued `is (not) null` is EXISTENTIAL.

    Strict Appendix B reading (a List, even empty, is never null) would make
    `(query) is not null` a constant true — but official eCQM content
    (CMS2/CMS771/CMS130, ecqm-content-qicore-2025) uses the idiom
    `( "Most Recent X" Q where ... ) is not null` as a NON-EMPTINESS test,
    and the DQM conformance fixtures encode that expectation. Fixtures
    outrank spec prose, so query operands keep row-presence semantics:
    IS NOT NULL over the lowered scalar subquery. The literal-list path
    stays strict-spec (IsNull({}) is false, IsNull({null}) is false,
    IsNull(null as List<T>) is true). Both registration surfaces agree."""
    header = "library NullQuery version '1.0.0'\nusing FHIR version '4.0.1'\ncontext Patient\n"
    translated = translate_cql(
        header
        + "\n".join(
            [
                "define EmptyQueryIsNull: IsNull((from {} D return D))",
                "define FilteredEmptyIsNotNull: (from { 1, 2, 3 } D where D > (null as Integer) return D) is not null",
                "define FilteredEmptyIsNull: (from { 1, 2, 3 } D where D > (null as Integer) return D) is null",
                "define ScalarNullIsNull: IsNull(null)",
                "define NullElemListIsNull: IsNull({ null as Integer })",
                "define EmptyListLiteralIsNull: IsNull({})",
                "define NullListIsNull: IsNull(null as List<Integer>)",
            ]
        )
    )
    expected = {
        "EmptyQueryIsNull": True,           # fixture semantics: empty query -> null
        "FilteredEmptyIsNotNull": False,    # no rows -> "is not null" false (eCQM idiom)
        "FilteredEmptyIsNull": True,
        "ScalarNullIsNull": True,
        "NullElemListIsNull": False,        # strict-spec literal-list path
        "EmptyListLiteralIsNull": False,
        "NullListIsNull": True,
    }
    py = _python_only_connection()
    cpp = _cpp_connection()
    try:
        for name, value in expected.items():
            sql = f"SELECT {translated[name].to_sql()}"
            assert py.execute(sql).fetchone() == (value,), name
            assert cpp.execute(sql).fetchone() == (value,), name
    finally:
        py.close()
        cpp.close()
