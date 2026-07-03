"""CQL conversion function parity checks."""

from __future__ import annotations

import json

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


def _install_patient_fixture(con: duckdb.DuckDBPyConnection) -> None:
    con.execute(
        """
        CREATE TABLE resources (
            patient_ref VARCHAR,
            resourceType VARCHAR,
            id VARCHAR,
            resource JSON
        )
        """
    )
    con.execute(
        """
        INSERT INTO resources VALUES
        ('p1', 'Patient', 'p1', '{"resourceType":"Patient","id":"p1"}'::JSON)
        """
    )


def test_cql_conversion_expressions_parse_and_translate() -> None:
    for expression in [
        "ToBoolean('true')",
        "ToInteger('42')",
        "ToLong('9223372036854775807')",
        "ToRatio('{\"numerator\":{\"value\":1},\"denominator\":{\"value\":2}}')",
        "ToQuantity('5 mg')",
        "ToConcept('{\"code\":\"x\"}')",
    ]:
        parsed = parse_expression(expression)
        assert isinstance(parsed, FunctionRef)

    cql = """library Conversions version '1.0.0'
using FHIR version '4.0.1'
context Patient
define L: ToLong('9223372036854775807')
define R: ToRatio('{"numerator":{"value":1},"denominator":{"value":2}}')
define RS: ToString(ToRatio('10 ''mg'':2 ''mL'''))
"""
    translated = translate_cql(cql)
    assert "ToLong" in str(translated["L"])
    assert "ToRatio" in str(translated["R"])
    assert "RatioToString" in str(translated["RS"])


def test_cql_conversion_duckdb_surface_matches_cpp_registration() -> None:
    ratio = '{"numerator":{"value":1,"unit":"mg"},"denominator":{"value":2,"unit":"mL"}}'
    expressions = [
        "SELECT ToString(123)",
        "SELECT ToString([1, 2])",
        "SELECT ToString({'a': 1})",
        "SELECT ToString(json_object('a', 1))",
        "SELECT ToBoolean('true')",
        "SELECT ToInteger('42')",
        "SELECT ToDecimal('1.25')::VARCHAR",
        "SELECT ToDecimal(true)::VARCHAR",
        "SELECT ToDecimal('1e2')",
        "SELECT ToDecimal('.5')",
        "SELECT ToDecimal('1.123456789')",
        "SELECT ToDecimal('1000000000000000000000000000000')",
        "SELECT ToDate('2024-01-15')::VARCHAR",
        "SELECT ToDate(TIMESTAMP '2024-01-15 10:30:00')::VARCHAR",
        "SELECT ToDateTime('2024-01-15T10:30:00')::VARCHAR",
        "SELECT ToTime('T10:30:00')::VARCHAR",
        "SELECT ToQuantity(5)",
        "SELECT ToQuantity('5.5 ''cm''')",
        "SELECT ToQuantity('5 ''year''')",
        "SELECT ToQuantity('5 ''not-a-unit''')",
        "SELECT ToQuantity('.5 ''cm''')",
        "SELECT ToQuantity('5 cm')",
        "SELECT ToQuantity(ToRatio('10 ''mg'':2 ''mL'''))",
        "SELECT ToRatio('1 ''not-a-unit'':2 ''mg''')",
        "SELECT RatioToString(ToRatio('10 ''mg'':2 ''mL'''))",
        "SELECT ToLong('9223372036854775807')",
        "SELECT ToLong('9223372036854775808')",
        f"SELECT ToRatio('{ratio}')",
        "SELECT ToRatio('not json')",
        "SELECT ToConcept('{\"code\":\"x\",\"system\":\"s\"}')",
        "SELECT ToConcept('[{\"code\":\"x\"},{\"code\":\"y\"}]')",
        "SELECT ToConcept('\"x\"')",
        "SELECT ToConcept('123')",
    ]

    py = _python_only_connection()
    cpp = _cpp_connection()
    try:
        for expression in expressions:
            assert cpp.execute(expression).fetchone() == py.execute(expression).fetchone()
    finally:
        py.close()
        cpp.close()


def test_cql_tostring_ratio_uses_ratio_text() -> None:
    cql = """library RatioString version '1.0.0'
using FHIR version '4.0.1'
context Patient
define RatioString: ToString(ToRatio('10 ''mg'':2 ''mL'''))
"""
    translated = translate_cql(cql)
    sql = f"SELECT {translated['RatioString'].to_sql()}"

    py = _python_only_connection()
    cpp = _cpp_connection()
    try:
        assert py.execute(sql).fetchone() == ("10.0 'mg':2.0 'mL'",)
        assert cpp.execute(sql).fetchone() == ("10.0 'mg':2.0 'mL'",)
    finally:
        py.close()
        cpp.close()


def test_cql_tostring_rejects_structural_values() -> None:
    cql = """library StructuralString version '1.0.0'
using FHIR version '4.0.1'
context Patient
define ListString: ToString({1, 2})
define TupleString: ToString(Tuple { a: 1 })
define IntervalString: ToString(Interval[1, 2])
define IntervalConvertString: convert Interval[1, 2] to String
define ScalarString: ToString(5)
"""
    translated = translate_cql(cql)
    expected = {
        "ListString": None,
        "TupleString": None,
        "IntervalString": None,
        "IntervalConvertString": None,
        "ScalarString": "5",
    }

    py = _python_only_connection()
    cpp = _cpp_connection()
    try:
        for name, expected_value in expected.items():
            sql = f"SELECT {translated[name].to_sql()}"
            assert py.execute(sql).fetchone() == (expected_value,), name
            assert cpp.execute(sql).fetchone() == (expected_value,), name
    finally:
        py.close()
        cpp.close()


def test_cql_tostring_rejects_concept_values() -> None:
    cql = """library ClinicalString version '1.0.0'
using FHIR version '4.0.1'
context Patient
define ConceptValue: ToConcept(Code { code: 'x', system: 's' })
define ConceptString: ToString(ConceptValue)
define ConceptStringable: ConvertsToString(ConceptValue)
define ConceptConvertString: convert ConceptValue to String
define QuantityStringable: ConvertsToString(5 'mg')
"""
    translated = translate_cql(cql)
    expected = {
        "ConceptString": None,
        "ConceptStringable": False,
        "ConceptConvertString": None,
        "QuantityStringable": True,
    }

    py = _python_only_connection()
    cpp = _cpp_connection()
    try:
        for name, expected_value in expected.items():
            sql = f"SELECT {translated[name].to_sql()}"
            assert py.execute(sql).fetchone() == (expected_value,), name
            assert cpp.execute(sql).fetchone() == (expected_value,), name
    finally:
        py.close()
        cpp.close()


def test_cql_conversion_static_definition_aliases_execute_standalone() -> None:
    cql = """library ConversionAliases version '1.0.0'
using FHIR version '4.0.1'
context Patient
define StringAlias: '5'
define BooleanStringAlias: 'true'
define DateAlias: @2024-01-01
define TimeAlias: @T10:30:00
define QuantityAlias: 5 'mg'
define RatioAlias: ToRatio('10 ''mg'':2 ''mL''')
define IntegerFromStringAlias: ToInteger(StringAlias)
define IntegerConvertFromStringAlias: convert StringAlias to Integer
define BooleanFromStringAlias: ToBoolean(BooleanStringAlias)
define StringFromDateAlias: ToString(DateAlias)
define StringFromTimeAlias: ToString(TimeAlias)
define QuantityStringFromAlias: ToString(QuantityAlias)
define QuantityConvertFromAlias: convert QuantityAlias to String
define RatioStringFromAlias: ToString(RatioAlias)
define RatioConvertFromAlias: convert RatioAlias to String
define MultiCodeConcept: convert { Code { code: 'x', system: 's' }, Code { code: 'y', system: 's' } } to Concept
"""
    translated = translate_cql(cql)
    expected = {
        "IntegerFromStringAlias": (5,),
        "IntegerConvertFromStringAlias": (5,),
        "BooleanFromStringAlias": (True,),
        "StringFromDateAlias": ("2024-01-01",),
        "StringFromTimeAlias": ("10:30:00",),
        "QuantityStringFromAlias": ("5 'mg'",),
        "QuantityConvertFromAlias": ("5 'mg'",),
        "RatioStringFromAlias": ("10.0 'mg':2.0 'mL'",),
        "RatioConvertFromAlias": ("10.0 'mg':2.0 'mL'",),
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

        concept_sql = translated["MultiCodeConcept"].to_sql()
        assert "CAST(json_object" in concept_sql
        py_concept = json.loads(py.execute(f"SELECT {concept_sql}").fetchone()[0])
        cpp_concept = json.loads(cpp.execute(f"SELECT {concept_sql}").fetchone()[0])
        assert cpp_concept == py_concept == {
            "codes": [
                {"code": "x", "system": "s"},
                {"code": "y", "system": "s"},
            ]
        }
    finally:
        py.close()
        cpp.close()


def test_cql_tostring_quantity_aliases_use_quantity_text_in_population_sql() -> None:
    cql = """library QuantityAliasString version '1.0.0'
using FHIR version '4.0.1'
parameter QuantityText String default '5 ''mg'''
context Patient
define function MakeQuantity(S String): ToQuantity(S)
define QuantityAlias: ToQuantity(QuantityText)
define QuantityAliasString: ToString(QuantityAlias)
define QuantityAliasConvertString: convert QuantityAlias to String
define FunctionQuantityAlias: MakeQuantity('5 ''mg''')
define FunctionQuantityAliasString: ToString(FunctionQuantityAlias)
define DirectFunctionQuantityString: ToString(MakeQuantity('5 ''mg'''))
define QuantityAliasIsQuantity: QuantityAlias is Quantity
"""
    sql = CQLToSQLTranslator().translate_library_to_population_sql(
        parse_cql(cql),
        output_columns={
            "quantity_alias_string": "QuantityAliasString",
            "quantity_alias_convert_string": "QuantityAliasConvertString",
            "function_quantity_alias_string": "FunctionQuantityAliasString",
            "direct_function_quantity_string": "DirectFunctionQuantityString",
            "quantity_alias_is_quantity": "QuantityAliasIsQuantity",
        },
    )

    py = _python_only_connection()
    cpp = _cpp_connection()
    try:
        for con in (py, cpp):
            _install_patient_fixture(con)
        expected = (
            "p1",
            "5 'mg'",
            "5 'mg'",
            "5 'mg'",
            "5 'mg'",
            True,
        )
        assert py.execute(sql).fetchone() == expected
        assert cpp.execute(sql).fetchone() == expected
    finally:
        py.close()
        cpp.close()


def test_cql_tostring_decimal_trims_trailing_zeros_per_spec_cql07_historian() -> None:
    """CQL 1.5.3 §ToString Table 9-G defines Decimal format as (-)?#0.0# and
    mandates that "The result of any ToString must be round-trippable back to
    the source value." DuckDB's CAST(decimal AS VARCHAR) emits all declared
    scale digits (e.g., DECIMAL(38,8) renders 0.1 as '0.10000000'), violating
    both rules. The ToString macro must trim trailing zeros while preserving
    at least one fractional digit.
    """
    expressions = [
        # (sql, expected_string)
        ("SELECT ToString(CAST(0.1 AS DECIMAL(38,8)))", "0.1"),
        ("SELECT ToString(CAST(0 AS DECIMAL(38,8)))", "0.0"),
        ("SELECT ToString(CAST(100 AS DECIMAL(38,8)))", "100.0"),
        ("SELECT ToString(CAST(-3.14 AS DECIMAL(38,8)))", "-3.14"),
        ("SELECT ToString(CAST(1.5 AS DECIMAL(38,8)))", "1.5"),
        ("SELECT ToString(CAST(-0.5 AS DECIMAL(38,8)))", "-0.5"),
        ("SELECT ToString(CAST(0.00000001 AS DECIMAL(38,8)))", "0.00000001"),
        ("SELECT ToString(CAST(123456789.12345678 AS DECIMAL(38,8)))", "123456789.12345678"),
        # Through the CQL translator surface (ToString composed with ToDecimal)
        ("SELECT ToString(ToDecimal('3.14'))", "3.14"),
        ("SELECT ToString(ToDecimal('0'))", "0.0"),
        ("SELECT ToString(ToDecimal('5'))", "5.0"),
        ("SELECT ToString(ToDecimal('-3.14'))", "-3.14"),
        ("SELECT ToString(ToDecimal('0.00000001'))", "0.00000001"),
    ]
    py = _python_only_connection()
    cpp = _cpp_connection()
    try:
        for sql, expected in expressions:
            py_result = py.execute(sql).fetchone()[0]
            cpp_result = cpp.execute(sql).fetchone()[0]
            assert py_result == expected, f"PY {sql}: {py_result!r} != {expected!r}"
            assert cpp_result == expected, f"CPP {sql}: {cpp_result!r} != {expected!r}"
    finally:
        py.close()
        cpp.close()


def test_cql_tostring_decimal_round_trips_per_spec_cql07_historian() -> None:
    """CQL §ToString: "The result of any ToString must be round-trippable
    back to the source value." Verify ToDecimal(ToString(x)) preserves the
    value for all Decimal inputs.
    """
    cql = """library RoundTrip version '1.0.0'
using FHIR version '4.0.1'
context Patient
define FromZero: ToDecimal(ToString(ToDecimal('0')))
define FromPi: ToDecimal(ToString(ToDecimal('3.14')))
define FromNeg: ToDecimal(ToString(ToDecimal('-2.5')))
define FromSmall: ToDecimal(ToString(ToDecimal('0.00000001')))
define FromInt: ToDecimal(ToString(ToDecimal('42')))
"""
    translated = translate_cql(cql)
    expected = {
        "FromZero": "0.00000000",
        "FromPi": "3.14000000",
        "FromNeg": "-2.50000000",
        "FromSmall": "0.00000001",
        "FromInt": "42.00000000",
    }
    py = _python_only_connection()
    cpp = _cpp_connection()
    try:
        for name, expected_value in expected.items():
            sql = f"SELECT {translated[name].to_sql()}::VARCHAR"
            assert py.execute(sql).fetchone()[0] == expected_value, name
            assert cpp.execute(sql).fetchone()[0] == expected_value, name
    finally:
        py.close()
        cpp.close()
