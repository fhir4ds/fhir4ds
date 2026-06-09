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
        "1'cm':2'cm' = 1'cm':2'cm'": "=",
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
        "SELECT ratioCompare(ToRatio('100 ''cm'':1 ''m'''), ToRatio('1 ''m'':1 ''m'''), '==')",
        "SELECT ratioCompare(ToRatio('1 ''mg'':8 ''mg'''), ToRatio('2 ''mg'':16 ''mg'''), '~')",
        "SELECT ratioCompare(ToRatio('1 ''mg'':8 ''mg'''), ToRatio('2 ''mg'':16 ''mg'''), '!~')",
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
define RatioLiteralEqual: 1'cm':2'cm' = 1'cm':2'cm'
define RatioLiteralNotEqualNumerator: 1'cm':2'cm' = 1.1'cm':2'cm'
define RatioLiteralEquivalent: 1'cm':2'cm' ~ 1'cm':2'cm'
define RatioLiteralNotEquivalentDenominator: 1'cm':2'cm' ~ 1'cm':3'cm'
define BetweenNullLowHighFalse: 5 between (null as Integer) and 4
define QuantityBetweenNullLowHighFalse: 1 'm' between (null as Quantity) and 0 'cm'
define StringBetweenNullLowHighFalse: 'b' between (null as String) and 'a'
define IntervalBetweenInclusive: Interval[1, 2] between 1 and 3
define IntervalBetweenOutside: Interval[1, 4] between 1 and 3
define DateTimeBetweenImprecise: @2012-01-01 between @2012-01-01T12 and @2012-01-02T12
define DecimalEquivalentLeastPrecision: 3.54 ~ 3.5
define DecimalNotEquivalentLeastPrecision: 3.54 !~ 3.5
define DecimalEquivalentHalfUnitBoundary: 1.5 ~ 1.55
define DecimalEquivalentTrailingZeroPrecision: 1.50 ~ 1.55
define QuantityDecimalEquivalentLeastPrecision: 1.24 'mg' ~ 1.2 'mg'
define QuantityDecimalNotEquivalentLeastPrecision: 1.26 'mg' !~ 1.2 'mg'
define CalendarDefiniteDurationEqual: 1 year = 365 days
define CalendarDefiniteDurationEquivalent: 1 year ~ 365 days
define RatioEqualUnitConverted: ToRatio('100 ''cm'':1 ''m''') = ToRatio('1 ''m'':1 ''m''')
define RatioEquivalentSameValue: ToRatio('1 ''mg'':8 ''mg''') ~ ToRatio('2 ''mg'':16 ''mg''')
define RatioNotEquivalentSameValue: ToRatio('1 ''mg'':8 ''mg''') !~ ToRatio('2 ''mg'':16 ''mg''')
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
        "RatioLiteralEqual": True,
        "RatioLiteralNotEqualNumerator": False,
        "RatioLiteralEquivalent": True,
        "RatioLiteralNotEquivalentDenominator": False,
        "BetweenNullLowHighFalse": None,
        "QuantityBetweenNullLowHighFalse": None,
        "StringBetweenNullLowHighFalse": None,
        "IntervalBetweenInclusive": True,
        "IntervalBetweenOutside": False,
        "DateTimeBetweenImprecise": None,
        "DecimalEquivalentLeastPrecision": True,
        "DecimalNotEquivalentLeastPrecision": False,
        "DecimalEquivalentHalfUnitBoundary": True,
        "DecimalEquivalentTrailingZeroPrecision": True,
        "QuantityDecimalEquivalentLeastPrecision": True,
        "QuantityDecimalNotEquivalentLeastPrecision": True,
        "CalendarDefiniteDurationEqual": None,
        "CalendarDefiniteDurationEquivalent": True,
        "RatioEqualUnitConverted": True,
        "RatioEquivalentSameValue": True,
        "RatioNotEquivalentSameValue": False,
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


def test_cql_unsupported_ordered_structural_comparisons_are_null() -> None:
    cql = """library UnsupportedOrderedComparisonEdges version '1.0.0'
using FHIR version '4.0.1'
context Patient
define RatioGreaterUnsupported:
  ToRatio('1 ''mg'':8 ''mg''') > ToRatio('2 ''mg'':16 ''mg''')
define RatioLessUnsupported:
  ToRatio('1 ''mg'':8 ''mg''') < ToRatio('2 ''mg'':16 ''mg''')
define RatioBetweenUnsupported:
  ToRatio('1 ''mg'':8 ''mg''') between ToRatio('1 ''mg'':9 ''mg''') and ToRatio('1 ''mg'':7 ''mg''')
define ListGreaterUnsupported: {1, 2} > {1, 1}
define TupleGreaterUnsupported: Tuple { Id: 2 } > Tuple { Id: 1 }
define IntervalGreaterUnsupported: Interval[1, 2] > Interval[0, 1]
define QuantityGreaterStillSupported: 1 'm' > 50 'cm'
define StringGreaterStillSupported: 'b' > 'a'
"""
    translated = translate_cql(cql)
    expected = {
        "RatioGreaterUnsupported": None,
        "RatioLessUnsupported": None,
        "RatioBetweenUnsupported": None,
        "ListGreaterUnsupported": None,
        "TupleGreaterUnsupported": None,
        "IntervalGreaterUnsupported": None,
        "QuantityGreaterStillSupported": True,
        "StringGreaterStillSupported": True,
    }

    py = _python_only_connection()
    cpp = _cpp_connection()
    try:
        for name, expected_value in expected.items():
            sql = "SELECT " + translated[name].to_sql()
            assert cpp.execute(sql).fetchone() == (expected_value,)
            assert py.execute(sql).fetchone() == (expected_value,)

        direct_ratio_compare = (
            "SELECT ratioCompare(ToRatio('1 ''mg'':8 ''mg'''), "
            "ToRatio('2 ''mg'':16 ''mg'''), '>')"
        )
        assert cpp.execute(direct_ratio_compare).fetchone() == (None,)
        assert py.execute(direct_ratio_compare).fetchone() == (None,)
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


def test_cql_tuple_comparison_uses_semantic_element_equality() -> None:
    cql = """library TupleSemanticComparison version '1.0.0'
using FHIR version '4.0.1'
context Patient
define TupleQuantityEqualUnitConverted:
  Tuple { q: 1 'g' } = Tuple { q: 1000 'mg' }
define TupleQuantityNotEqualUnitConverted:
  Tuple { q: 1 'g' } != Tuple { q: 1000 'mg' }
define TupleQuantityIncompatibleEqual:
  Tuple { q: 1 'g' } = Tuple { q: 1 'cm' }
define TupleRatioEqualUnitConverted:
  Tuple { r: ToRatio('100 ''cm'':1 ''m''') } = Tuple { r: ToRatio('1 ''m'':1 ''m''') }
define TupleRatioEquivalentSameValue:
  Tuple { r: ToRatio('1 ''mg'':8 ''mg''') } ~ Tuple { r: ToRatio('2 ''mg'':16 ''mg''') }
"""
    translated = translate_cql(cql)
    assert "quantity_compare" in translated["TupleQuantityEqualUnitConverted"].to_sql()
    assert "ratioCompare" in translated["TupleRatioEqualUnitConverted"].to_sql()

    expected = {
        "TupleQuantityEqualUnitConverted": True,
        "TupleQuantityNotEqualUnitConverted": False,
        "TupleQuantityIncompatibleEqual": None,
        "TupleRatioEqualUnitConverted": True,
        "TupleRatioEquivalentSameValue": True,
    }

    py = _python_only_connection()
    cpp = _cpp_connection()
    try:
        for name, expected_value in expected.items():
            sql = "SELECT " + translated[name].to_sql()
            assert py.execute(sql).fetchone() == (expected_value,)
            assert cpp.execute(sql).fetchone() == (expected_value,)
    finally:
        py.close()
        cpp.close()


def test_cql_static_tuple_query_and_singleton_comparisons_preserve_value_types() -> None:
    cql = """library QueryTupleSemanticComparison version '1.0.0'
using FHIR version '4.0.1'
context Patient
define SingletonQuantityEqualUnitConverted:
  singleton from { 1 'g' } = 1000 'mg'
define QueryQuantityBetweenUnitConverted:
  ({ Tuple { q: 1 'm' } }) T
    where T.q between 50 'cm' and 150 'cm'
    return T.q
define QueryQuantityEqualUnitConverted:
  ({ Tuple { q: 1 'g' } }) T
    where T.q = 1000 'mg'
    return T.q
define QueryRatioEqualUnitConverted:
  ({ Tuple { r: ToRatio('100 ''cm'':1 ''m''') } }) T
    where T.r = ToRatio('1 ''m'':1 ''m''')
    return T.r
define IntersectBetween:
  (Interval[1, 5] intersect Interval[2, 3]) between 1 and 4
define UnionBetween:
  (Interval[1, 2] union Interval[2, 4]) between 1 and 4
"""
    translated = translate_cql(cql)
    assert "quantity_compare" in translated["SingletonQuantityEqualUnitConverted"].to_sql()
    assert "quantity_compare" in translated["QueryQuantityEqualUnitConverted"].to_sql()
    assert "ratioCompare" in translated["QueryRatioEqualUnitConverted"].to_sql()

    py = _python_only_connection()
    cpp = _cpp_connection()
    try:
        for name in ("SingletonQuantityEqualUnitConverted", "IntersectBetween", "UnionBetween"):
            sql = "SELECT " + translated[name].to_sql()
            assert py.execute(sql).fetchone() == (True,)
            assert cpp.execute(sql).fetchone() == (True,)

        for name, expected_unit in {
            "QueryQuantityBetweenUnitConverted": "m",
            "QueryQuantityEqualUnitConverted": "g",
        }.items():
            sql = "SELECT " + translated[name].to_sql()
            for con in (py, cpp):
                value = con.execute(sql).fetchone()[0]
                parsed = json.loads(value[0] if isinstance(value, list) else value)
                assert (parsed.get("unit") or parsed.get("code")) == expected_unit

        sql = "SELECT " + translated["QueryRatioEqualUnitConverted"].to_sql()
        for con in (py, cpp):
            value = con.execute(sql).fetchone()[0]
            parsed = json.loads(value[0] if isinstance(value, list) else value)
            assert parsed["numerator"]["unit"] == "cm"
            assert parsed["denominator"]["unit"] == "m"
    finally:
        py.close()
        cpp.close()
