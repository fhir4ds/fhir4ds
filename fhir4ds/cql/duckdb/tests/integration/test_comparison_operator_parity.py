"""CQL comparison operator parity checks."""

from __future__ import annotations

import json

import duckdb

from fhir4ds.cql.duckdb import register
from fhir4ds.cql.duckdb.extension import _register_python_supplements
from fhir4ds.cql.parser import parse_expression
from fhir4ds.cql.parser.ast_nodes import BinaryExpression
from fhir4ds.cql.translator import translate_cql


def _python_only_connection() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect(config={"allow_unsigned_extensions": True})
    _register_python_supplements(con, cpp_loaded=False, include_fhirpath=True)
    return con


def _cpp_connection() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect(config={"allow_unsigned_extensions": True})
    register(con, include_fhirpath=True)
    return con


def test_cql_comparison_expressions_parse_and_translate() -> None:
    operators = {
        "5 = 5": "=",
        "5 != 6": "!=",
        "5 < 6": "<",
        "5 <= 5": "<=",
        "6 > 5": ">",
        "6 >= 6": ">=",
        "'abc' ~ 'abc'": "~",
        "'abc' !~ 'def'": "!~",
        "5 between 1 and 10": "between",
    }
    for expression, operator in operators.items():
        parsed = parse_expression(expression)
        assert isinstance(parsed, BinaryExpression)
        assert parsed.operator == operator

    cql = """library Comparisons version '1.0.0'
using FHIR version '4.0.1'
context Patient
define BetweenCheck: 5 between 1 and 10
define QuantityEq: 1 'h' = 60 'min'
define DateBefore: @2024-01 before @2024-02
"""
    translated = translate_cql(cql)

    between_sql = str(translated["BetweenCheck"])
    assert "operator='>='" in between_sql
    assert "operator='<='" in between_sql

    quantity_sql = str(translated["QuantityEq"])
    assert "quantity_compare" in quantity_sql
    assert "value='=='" in quantity_sql

    date_sql = str(translated["DateBefore"])
    assert "cqlBefore" in date_sql


def test_cql_comparison_duckdb_surface_matches_cpp_registration() -> None:
    expressions = [
        (
            "SELECT quantityCompare('{\"value\":1,\"code\":\"h\"}', "
            "'{\"value\":60,\"code\":\"min\"}', '==')"
        ),
        (
            "SELECT quantityCompare('{\"value\":1,\"code\":\"h\"}', "
            "'{\"value\":30,\"code\":\"min\"}', '>')"
        ),
        (
            "SELECT quantityCompare('{\"value\":1,\"code\":\"kg\"}', "
            "'{\"value\":1000,\"code\":\"g\"}', '<=')"
        ),
        (
            "SELECT quantityCompare('{\"value\":1,\"code\":\"kg\"}', "
            "'{\"value\":1,\"code\":\"m\"}', '<')"
        ),
        "SELECT dateTimeSameAs('2024-01-15', '2024-01-20', 'month')",
        "SELECT dateTimeSameOrBefore('2024-01-15', '2024-01-20', 'day')",
        "SELECT dateTimeSameOrAfter('2024-02', '2024-01', 'month')",
        "SELECT fhirpath_bool('{\"resourceType\":\"Patient\",\"age\":5}'::JSON, 'age = 5')",
        "SELECT fhirpath_bool('{\"resourceType\":\"Patient\",\"age\":5}'::JSON, 'age != 6')",
        "SELECT fhirpath_bool('{\"resourceType\":\"Patient\",\"age\":5}'::JSON, 'age >= 5')",
        "SELECT fhirpath_bool('{\"resourceType\":\"Patient\",\"age\":5}'::JSON, 'age <= 5')",
    ]

    py = _python_only_connection()
    cpp = _cpp_connection()
    try:
        for expression in expressions:
            assert cpp.execute(expression).fetchone() == py.execute(expression).fetchone()
    finally:
        py.close()
        cpp.close()


def test_cql_comparison_semantic_edge_cases_match_cpp_and_python() -> None:
    cql = """library ComparisonEdges version '1.0.0'
using FHIR version '4.0.1'
context Patient
define QuantityBetweenCompatible: 1 'm' between 50 'cm' and 150 'cm'
define QuantityBetweenOutside: 1 'm' between 150 'cm' and 200 'cm'
define QuantityBetweenIncompatible: 1 'm' between 1 's' and 2 's'
define DateTimeBetweenImprecise: @2012-01-01 between @2012-01-01T12 and @2012-01-02T12
define DecimalEquivalentLeastPrecision: 3.54 ~ 3.5
define DecimalNotEquivalentLeastPrecision: 3.54 !~ 3.5
define QuantityDecimalEquivalentLeastPrecision: 1.24 'mg' ~ 1.2 'mg'
define QuantityDecimalNotEquivalentLeastPrecision: 1.26 'mg' !~ 1.2 'mg'
define CalendarDefiniteDurationEqual: 1 year = 365 days
define CalendarDefiniteDurationEquivalent: 1 year ~ 365 days
define StringEquivalentCase: 'John Doe' ~ 'john doe'
define StringNotEquivalentCase: 'John Doe' !~ 'john doe'
define StringEquivalentWhitespace: 'a b' ~ 'a\tb'
define ListStringEquivalentCase: {'ABC'} ~ {'abc'}
define ListMixedEquivalentFalse: {1, 2, 3} ~ {'1', '2', '3'}
define TupleStringEquivalentCase: Tuple { x: 'ABC' } ~ Tuple { x: 'abc' }
"""
    translated = translate_cql(cql)
    expected = {
        "QuantityBetweenCompatible": True,
        "QuantityBetweenOutside": False,
        "QuantityBetweenIncompatible": None,
        "DateTimeBetweenImprecise": None,
        "DecimalEquivalentLeastPrecision": True,
        "DecimalNotEquivalentLeastPrecision": False,
        "QuantityDecimalEquivalentLeastPrecision": True,
        "QuantityDecimalNotEquivalentLeastPrecision": True,
        "CalendarDefiniteDurationEqual": None,
        "CalendarDefiniteDurationEquivalent": True,
        "StringEquivalentCase": True,
        "StringNotEquivalentCase": False,
        "StringEquivalentWhitespace": True,
        "ListStringEquivalentCase": True,
        "ListMixedEquivalentFalse": False,
        "TupleStringEquivalentCase": True,
    }

    py = _python_only_connection()
    cpp = _cpp_connection()
    try:
        for name, expected_value in expected.items():
            sql = "SELECT " + translated[name].to_sql()
            assert cpp.execute(sql).fetchone() == (expected_value,)
            assert py.execute(sql).fetchone() == (expected_value,)
    finally:
        py.close()
        cpp.close()


def test_cql_quantity_compare_duration_semantics_match_cpp_and_python() -> None:
    py = _python_only_connection()
    cpp = _cpp_connection()
    expressions = {
        (
            "SELECT quantityCompare('{\"value\":1,\"unit\":\"year\"}', "
            "'{\"value\":365,\"unit\":\"day\"}', '==')"
        ): None,
        (
            "SELECT quantityCompare('{\"value\":1,\"unit\":\"year\"}', "
            "'{\"value\":365,\"unit\":\"day\"}', '~')"
        ): True,
        (
            "SELECT quantityCompare('{\"value\":1,\"unit\":\"month\"}', "
            "'{\"value\":30,\"unit\":\"day\"}', '~')"
        ): True,
        (
            "SELECT quantityCompare('{\"value\":1,\"unit\":\"year\"}', "
            "'{\"value\":365,\"unit\":\"day\"}', '>')"
        ): None,
        (
            "SELECT quantityCompare('{\"value\":1.24,\"unit\":\"mg\"}', "
            "'{\"value\":1.2,\"unit\":\"mg\"}', '~')"
        ): True,
        (
            "SELECT quantityCompare('{\"value\":1.26,\"unit\":\"mg\"}', "
            "'{\"value\":1.2,\"unit\":\"mg\"}', '!~')"
        ): True,
    }
    try:
        for sql, expected in expressions.items():
            assert cpp.execute(sql).fetchone() == (expected,)
            assert py.execute(sql).fetchone() == (expected,)
    finally:
        py.close()
        cpp.close()


def test_cql_dynamic_fhir_comparison_edges_match_cpp_and_python() -> None:
    cql = """library DynamicComparisonEdges version '1.0.0'
using FHIR version '4.0.1'
context Patient
define FhirIntegerBetween: O.value between 4 and 6
define FhirQuantityBetween: O.value between 50 'cm' and 150 'cm'
define FhirQuantityEqual: O.value = 1 'm'
define FhirStringEquivalent: O.value ~ 'hello world'
"""
    translated = translate_cql(cql)
    cases = [
        (
            "FhirIntegerBetween",
            {"resourceType": "Observation", "valueInteger": 5},
            True,
        ),
        (
            "FhirIntegerBetween",
            {"resourceType": "Observation", "valueString": "5"},
            None,
        ),
        (
            "FhirQuantityBetween",
            {"resourceType": "Observation", "valueQuantity": {"value": 1, "code": "m"}},
            True,
        ),
        (
            "FhirQuantityEqual",
            {"resourceType": "Observation", "valueQuantity": {"value": 100, "code": "cm"}},
            True,
        ),
        (
            "FhirStringEquivalent",
            {"resourceType": "Observation", "valueString": "Hello\tWorld"},
            True,
        ),
    ]

    py = _python_only_connection()
    cpp = _cpp_connection()
    try:
        for name, resource, expected in cases:
            sql = f"SELECT {translated[name].to_sql()} FROM (SELECT ?::JSON AS O)"
            resource_text = json.dumps(resource)
            assert py.execute(sql, [resource_text]).fetchone() == (expected,)
            assert cpp.execute(sql, [resource_text]).fetchone() == (expected,)
    finally:
        py.close()
        cpp.close()


def test_cql_internal_tuple_numeric_text_comparison_matches_cpp_and_python() -> None:
    cql = """library TupleNumericTextComparison version '1.0.0'
using FHIR version '4.0.1'
context Patient
define TupleDayFilter:
  (Tuple {
    days: {
      Tuple { dayNumber: '1' },
      Tuple { dayNumber: '2' }
    }
  }.days) D
    where D.dayNumber > 1
    return D.dayNumber
"""
    translated = translate_cql(cql)
    sql = "SELECT " + translated["TupleDayFilter"].to_sql()

    assert "fhirpath_number" not in translated["TupleDayFilter"].to_sql()

    py = _python_only_connection()
    cpp = _cpp_connection()
    try:
        assert py.execute(sql).fetchone() == (["2"],)
        assert cpp.execute(sql).fetchone() == (["2"],)
    finally:
        py.close()
        cpp.close()
