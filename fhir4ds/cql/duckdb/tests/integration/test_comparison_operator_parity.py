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


def test_cql_incompatible_primitive_equality_returns_null_not_runtime_error() -> None:
    """CQL §9 Equal signature is =<T>(left T, right T); comparing operands of
    incompatible primitive types (e.g. String vs Integer) has no defined value.

    Previously the translator emitted raw DuckDB `x = y` SQL that raised a
    ConversionException at execution. The fix mirrors the existing
    `_static_equivalence_incompatible` guard used by `~` and lowers the
    comparison to NULL for CQL's three-valued logic.
    """
    cql = """library IncompatibleEquality version '1.0.0'
using FHIR version '4.0.1'
context Patient
define EqStringVsInt: 'foo' = 5
define NeStringVsInt: 'foo' <> 5
define EqStringVsBool: 'foo' = true
define EqIntVsBool: 1 = true
"""
    translated = translate_cql(cql)
    expected = {
        "EqStringVsInt": None,
        "NeStringVsInt": None,
        "EqStringVsBool": None,
        "EqIntVsBool": None,
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


def test_cql_incompatible_primitive_ordered_comparison_returns_null_not_runtime_error() -> None:
    """CQL §9 Greater/Less/GreaterOrEqual/LessOrEqual/Between signatures are
    >T(left T, right T) etc.; comparing operands of incompatible primitive
    types (e.g. String vs Integer) has no defined value.

    Regression coverage for CQL-09 EXPLORER QA-001: the prior SKEPTIC fix
    only added the `_static_equivalence_incompatible` guard for `=`/`!=`/`<>`.
    EXPLORER confirmed the same DuckDB ConversionException leak affects the
    ordered-comparison operators (`<`, `<=`, `>`, `>=`) and `between`. Both
    backends must now return NULL instead of raising.
    """
    cql = """library IncompatibleOrdered version '1.0.0'
using FHIR version '4.0.1'
context Patient
define StrGtInt: 'foo' > 5
define StrLtInt: 'foo' < 5
define StrGeInt: 'foo' >= 5
define StrLeInt: 'foo' <= 5
define StrBetween: 'foo' between 1 and 5
define BoolGtStr: true > 'foo'
define BoolLtStr: true < 'foo'
define IntLtBool: 5 < false
define IntGtBool: 5 > false
define IntBetweenStr: 5 between 'a' and 'b'
define StrBetweenStrBound: 'a' between 1 and 'z'
define BoolBetween: true between 1 and 5
"""
    translated = translate_cql(cql)
    expected = {
        "StrGtInt": None,
        "StrLtInt": None,
        "StrGeInt": None,
        "StrLeInt": None,
        "StrBetween": None,
        "BoolGtStr": None,
        "BoolLtStr": None,
        "IntLtBool": None,
        "IntGtBool": None,
        "IntBetweenStr": None,
        "StrBetweenStrBound": None,
        "BoolBetween": None,
    }
    py = _python_only_connection()
    cpp = _cpp_connection()
    try:
        for name, expected_value in expected.items():
            sql = "SELECT " + translated[name].to_sql()
            assert cpp.execute(sql).fetchone() == (expected_value,), (
                name,
                "cpp",
                cpp.execute(sql).fetchone(),
                "expected",
                expected_value,
            )
            assert py.execute(sql).fetchone() == (expected_value,), (
                name,
                "py",
                py.execute(sql).fetchone(),
                "expected",
                expected_value,
            )
    finally:
        py.close()
        cpp.close()


def test_cql_chained_binary_equality_emits_parenthesized_sql() -> None:
    """CQL grammar supports nested binary equality (left-associative). The
    CQL parser correctly accepts `((1 = 1) = true) = ((2 = 2) = true)`.

    Regression coverage for CQL-09 EXPLORER QA-003: the translator previously
    emitted `SELECT 1 = 1 = TRUE = 2 = 2 = TRUE` which DuckDB rejects with
    `ParserException: syntax error at or near "="`. DuckDB comparison
    operators are non-associative and require parens for chains. Fix added
    a `_child_parent_precedence` helper on `SQLBinaryOp` that passes
    `self.precedence + 1` to children when the operator is non-associative
    (=, !=, <>, <, <=, >, >=, LIKE, IN, etc.) so they parenthesize.
    """
    cql = """library ChainedEquality version '1.0.0'
using FHIR version '4.0.1'
context Patient
define ChainEq: ((1 = 1) = true) = ((2 = 2) = true)
define NestedNeq: (1 != 2) != (3 != 4)
define NestedGtChain: (1 > 0) = (2 > 1)
"""
    translated = translate_cql(cql)
    expected = {
        "ChainEq": True,
        "NestedNeq": False,
        "NestedGtChain": True,
    }
    py = _python_only_connection()
    cpp = _cpp_connection()
    try:
        for name, expected_value in expected.items():
            sql = "SELECT " + translated[name].to_sql()
            # The SQL must be valid DuckDB syntax (no parser exception).
            assert cpp.execute(sql).fetchone() == (expected_value,), (
                name,
                "cpp",
                cpp.execute(sql).fetchone(),
                "expected",
                expected_value,
            )
            assert py.execute(sql).fetchone() == (expected_value,), (
                name,
                "py",
                py.execute(sql).fetchone(),
                "expected",
                expected_value,
            )
        # Explicit assertion on the SQL shape for ChainEq to lock the fix:
        # the comparison operators must be parenthesized.
        chain_sql = translated["ChainEq"].to_sql()
        assert chain_sql.count("(") >= 4 and chain_sql.count(")") >= 4, (
            "ChainEq SQL must parenthesize nested comparisons: ",
            chain_sql,
        )
    finally:
        py.close()
        cpp.close()


def test_cql_null_uncertainty_preserved_in_list_and_interval_equality() -> None:
    """CQL 1.5 §9.4 Equal: one-sided null operands must yield null (uncertain).

    List equality: null elements are considered equal to null, but a null
    element versus a known value is uncertain (null), not false. Interval
    equality via Start/End: a one-sided null bound is unknown, so the
    comparison is null. Equivalent (~) must stay never-null (false).
    """
    cql = """library NullUncertainComparison version '1.0.0'
context Unfiltered
define ListNullElementEqual: { 1, null } = { 1, 2 }
define ListNullElementBothNullEqual: { 1, null } = { 1, null }
define ListNullElementEquivalent: { 1, null } ~ { 1, 2 }
define ListContainsUncertain: 5 in { 1, null }
define IntervalNullLowEqual: Interval[null, 3] = Interval[1, 3]
define IntervalNullHighEqual: Interval[1, 3] = Interval[1, null]
define IntervalBothNullBoundsEqual: Interval[null, 3] = Interval[null, 3]
define IntervalNullLowEquivalent: Interval[null, 3] ~ Interval[1, 3]
define IntervalNullLowNotEqual: Interval[null, 3] != Interval[1, 3]
"""
    translated = translate_cql(cql)
    expected = {
        "ListNullElementEqual": None,
        "ListNullElementBothNullEqual": True,
        "ListNullElementEquivalent": False,
        "ListContainsUncertain": False,  # pinned contains doctrine: one-sided null element is NOT contained
        "IntervalNullLowEqual": None,
        "IntervalNullHighEqual": None,
        "IntervalBothNullBoundsEqual": True,
        "IntervalNullLowEquivalent": False,
        "IntervalNullLowNotEqual": None,
    }
    py = _python_only_connection()
    cpp = _cpp_connection()
    try:
        for name, expected_value in expected.items():
            sql = "SELECT " + translated[name].to_sql()
            assert py.execute(sql).fetchone() == (expected_value,), (
                name, "py", py.execute(sql).fetchone(), "expected", expected_value,
            )
            assert cpp.execute(sql).fetchone() == (expected_value,), (
                name, "cpp", cpp.execute(sql).fetchone(), "expected", expected_value,
            )
    finally:
        py.close()
        cpp.close()


def test_cql_null_uncertainty_preserved_in_composite_list_elements() -> None:
    """CQL 1.5 §9.4 Equal: uncertainty must propagate through composite elements.

    Nested-list elements recurse into list equality, so an uncertain inner
    element makes the outer comparison null, not false. Tuple elements inside
    lists compare field-wise with = semantics, so a one-sided null field is
    uncertain (null). Tuple field order is irrelevant; numeric fields compare
    with trailing-zero/trailing-.x equality; missing-field tuples are unequal.
    """
    cql = """library CompositeUncertainComparison version '1.0.0'
context Unfiltered
define NestedListUncertainEqual: { { 1, null }, { 2 } } = { { 1, 2 }, { 2 } }
define NestedListKnownEqual: { { 1, null }, { 2 } } = { { 1, null }, { 2 } }
define NestedListKnownUnequal: { { 1, 2 } } = { { 1, 3 } }
define NestedListLengthMismatch: { { 1 }, { 2 } } = { { 1 } }
define NestedListNumericTrailingZeros: { { 1.0 }, { 2 } } = { { 1 }, { 2 } }
define NestedListNotEqualPropagates: { { 1, null }, { 2 } } != { { 1, 2 }, { 2 } }
define NestedTemporalPrecisionEqual: { { @2024-01-01T10 } } = { { @2024-01-01T10:00 } }
define TupleInListUncertainEqual: { Tuple { a: 1, b: null } } = { Tuple { a: 1, b: 2 } }
define TupleInListKnownEqual: { Tuple { a: 1 } } = { Tuple { a: 1 } }
define TupleInListBothNullEqual: { Tuple { a: null } } = { Tuple { a: null } }
define TupleInListKnownUnequal: { Tuple { a: 1 } } = { Tuple { a: 2 } }
define TupleInListNumericEqual: { Tuple { a: 1.0 } } = { Tuple { a: 1 } }
define TupleInListMissingFieldUnequal: { Tuple { a: 1 } } = { Tuple { a: 1, b: 2 } }
"""
    translated = translate_cql(cql)
    expected = {
        "NestedListUncertainEqual": None,
        "NestedListKnownEqual": True,
        "NestedListKnownUnequal": False,
        "NestedListLengthMismatch": False,
        "NestedListNumericTrailingZeros": True,
        "NestedListNotEqualPropagates": None,
        "NestedTemporalPrecisionEqual": True,
        "TupleInListUncertainEqual": None,
        "TupleInListKnownEqual": True,
        "TupleInListBothNullEqual": True,
        "TupleInListKnownUnequal": False,
        "TupleInListNumericEqual": True,
        "TupleInListMissingFieldUnequal": False,
    }
    py = _python_only_connection()
    cpp = _cpp_connection()
    try:
        for name, expected_value in expected.items():
            sql = "SELECT " + translated[name].to_sql()
            assert py.execute(sql).fetchone() == (expected_value,), (
                name, "py", py.execute(sql).fetchone(), "expected", expected_value,
            )
            assert cpp.execute(sql).fetchone() == (expected_value,), (
                name, "cpp", cpp.execute(sql).fetchone(), "expected", expected_value,
            )
    finally:
        py.close()
        cpp.close()


def test_cql_bare_numeric_vs_quantity_promotes_unit_aware() -> None:
    """CQL 1.5 Table 9-E: Integer/Long/Decimal implicitly convert to Quantity
    with default unit '1'. A bare numeric literal compared against a STATIC
    Quantity literal must be promoted and compared unit-aware: incompatible
    units yield null for =/!=/</<=/>/>= (§9.5 Equal) and false for ~/!~
    (§9.7 Equivalent never null), instead of dropping the unit and comparing
    raw values (or raising a binder error for ~). Dynamic FHIR-sourced
    quantities intentionally keep the numeric path (FHIRHelpers unit
    Coalesce(code, unit, '1') admits non-UCUM display strings; official
    eCQM fixtures pin numeric comparison there — CMS72/CMS190 'INR.value as
    Quantity > 3.5' with unit display "0"). Regression for CQL-09 EXPLORER
    QA-001/QA-002."""
    cql = """library BareNumericQuantity version '1.0.0'
using FHIR version '4.0.1'
context Patient
define EqualIncompatibleUnits: 1 = 1 'm'
define EqualIncompatibleUnitsRight: 1 'm' = 1
define NotEqualIncompatibleUnits: 1 != 1 'm'
define LessIncompatibleUnits: 1 < 2 'm'
define GreaterIncompatibleUnits: 2 > 1 'm'
define EqualMassIncompatible: 1 = 1 'g'
define EqualUnityUnit: 1 = 1 '1'
define EqualUnityUnitExisting: 1 '1' = 1
define LessUnityUnit: 0 < 1 '1'
define GreaterUnityUnit: 2 > 1 '1'
define EquivalentIncompatibleUnits: 1 ~ 1 'm'
define NotEquivalentIncompatibleUnits: 1 !~ 1 'm'
define EquivalentIncompatibleUnitsRight: 1 'm' ~ 1
define EquivalentUnityUnit: 1.5 ~ 1.5 '1'
define EquivalentExistingUnity: 1 '1' ~ 1
define QuantityEqualUnchanged: 100 'cm' = 1 'm'
define QuantityEquivalentUnchanged: 100 'cm' ~ 1 'm'
define QuantityEqualIncompatibleUnchanged: 1 'm' = 1 'g'
"""
    translated = translate_cql(cql)
    expected = {
        "EqualIncompatibleUnits": None,
        "EqualIncompatibleUnitsRight": None,
        "NotEqualIncompatibleUnits": None,
        "LessIncompatibleUnits": None,
        "GreaterIncompatibleUnits": None,
        "EqualMassIncompatible": None,
        "EqualUnityUnit": True,
        "EqualUnityUnitExisting": True,
        "LessUnityUnit": True,
        "GreaterUnityUnit": True,
        "EquivalentIncompatibleUnits": False,
        "NotEquivalentIncompatibleUnits": True,
        "EquivalentIncompatibleUnitsRight": False,
        "EquivalentUnityUnit": True,
        "EquivalentExistingUnity": True,
        "QuantityEqualUnchanged": True,
        "QuantityEquivalentUnchanged": True,
        "QuantityEqualIncompatibleUnchanged": None,
    }

    py = _python_only_connection()
    cpp = _cpp_connection()
    try:
        for name, expected_value in expected.items():
            sql = "SELECT " + translated[name].to_sql()
            assert cpp.execute(sql).fetchone() == (expected_value,), name
            assert py.execute(sql).fetchone() == (expected_value,), name
    finally:
        py.close()
        cpp.close()
