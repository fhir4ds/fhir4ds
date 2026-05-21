"""CQL conversion function parity checks."""

from __future__ import annotations

import json

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
        "StringFromTimeAlias": ("T10:30:00",),
        "QuantityStringFromAlias": ("5.0 'mg'",),
        "QuantityConvertFromAlias": ("5.0 'mg'",),
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
