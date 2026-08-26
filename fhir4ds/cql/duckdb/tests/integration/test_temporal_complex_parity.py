"""CQL temporal and complex type parity checks."""

from __future__ import annotations

import json

import duckdb
import pytest

from fhir4ds.cql.duckdb import register
from fhir4ds.cql.duckdb.extension import _register_python_supplements
from fhir4ds.cql.parser import parse_cql, parse_expression
from fhir4ds.cql.parser.ast_nodes import DateTimeLiteral, FunctionRef, Quantity
from fhir4ds.cql.translator import CQLToSQLTranslator

from .wasm_runtime_helpers import no_python_connection


def _python_only_connection() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect(config={"allow_unsigned_extensions": True})
    _register_python_supplements(con, cpp_loaded=False, include_fhirpath=True)
    return con


def _cpp_connection() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect(config={"allow_unsigned_extensions": True})
    register(con, include_fhirpath=True)
    return con


def _translated_definition_sql(expression: str) -> str:
    cql = f"library CQL03Explorer version '1.0'\ndefine Result: {expression}\n"
    return CQLToSQLTranslator().translate_library_to_sql(parse_cql(cql))


def test_cql_temporal_and_complex_literals_parse() -> None:
    date = parse_expression("@2024-01-15")
    datetime = parse_expression("@2024-01-15T10:30:00")
    time = parse_expression("@T10:30:00")
    quantity = parse_expression("5.5 'mg'")
    datetime_ctor = parse_expression("DateTime(2024, 1, 15)")
    time_ctor = parse_expression("Time(10, 30, 0)")

    assert isinstance(date, DateTimeLiteral)
    assert date.value == "2024-01-15"
    assert isinstance(datetime, DateTimeLiteral)
    assert datetime.value == "2024-01-15T10:30:00"
    assert isinstance(time, DateTimeLiteral)
    assert time.value == "T10:30:00"
    assert isinstance(quantity, Quantity)
    assert quantity.value == 5.5
    assert quantity.unit == "mg"
    assert isinstance(datetime_ctor, FunctionRef)
    assert datetime_ctor.name == "DateTime"
    assert isinstance(time_ctor, FunctionRef)
    assert time_ctor.name == "Time"


def test_cql_temporal_quantity_ratio_duckdb_surface_matches_cpp_registration() -> None:
    ratio = (
        '{"numerator":{"value":10,"unit":"mg"},'
        '"denominator":{"value":4,"unit":"mL"}}'
    )
    ratio_code_units = (
        '{"numerator":{"value":5,"code":"mg"},'
        '"denominator":{"value":1,"code":"mL"}}'
    )

    expressions = [
        "SELECT ToDate('2024-01-15')::VARCHAR",
        "SELECT ToDate('2014-01')::VARCHAR",
        "SELECT ToDate('2014-01-01T12:30:00')::VARCHAR",
        "SELECT ToDateTime('2024-01-15T10:30:00')::VARCHAR",
        "SELECT ToDateTime('2024-01')::VARCHAR",
        "SELECT ToDateTime('2024-01-15T10:30:00+05:00')::VARCHAR",
        "SELECT ToTime('T10:30:00')::VARCHAR",
        "SELECT ToQuantity(5)",
        "SELECT ToQuantity(0.1)",
        "SELECT ToQuantity('5.5 ''cm''')",
        "SELECT ToQuantity('5')",
        "SELECT ToQuantity('999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999')",
        "SELECT ToQuantity('5 cm')",
        "SELECT ToQuantity(ToRatio('10 ''mg'':2 ''mL'''))",
        "SELECT parse_quantity('{\"value\":2.5,\"unit\":\"kg\"}')",
        "SELECT quantityValue('{\"value\":140,\"code\":\"mm[Hg]\"}')",
        "SELECT quantityUnit('{\"value\":140,\"unit\":\"mmHg\"}')",
        (
            "SELECT quantityCompare('{\"value\":1,\"code\":\"h\"}', "
            "'{\"value\":30,\"code\":\"min\"}', '>')"
        ),
        f"SELECT ratioNumeratorValue('{ratio}')",
        f"SELECT ratioDenominatorValue('{ratio}')",
        f"SELECT ratioValue('{ratio}')",
        f"SELECT ratioNumeratorUnit('{ratio_code_units}')",
        f"SELECT ratioDenominatorUnit('{ratio_code_units}')",
        "SELECT ratioValue('{\"numerator\":{\"value\":5},\"denominator\":{\"value\":0}}')",
    ]

    py = _python_only_connection()
    cpp = _cpp_connection()
    try:
        for expression in expressions:
            assert cpp.execute(expression).fetchone() == py.execute(expression).fetchone()
    finally:
        py.close()
        cpp.close()


def test_cql_temporal_complex_negative_boundaries_match_spec_and_backend_parity() -> None:
    expressions = {
        "SELECT ConvertsToDate('2024-13-01')": False,
        "SELECT ConvertsToDate('2024-02-30')": False,
        "SELECT ToDate('2024-02-30')": None,
        "SELECT ConvertsToDateTime('2024-01-01T25:00:00')": False,
        "SELECT ConvertsToDateTime('2024-01-01T10:00:00+99:99')": False,
        "SELECT ConvertsToDateTime('2024-01-01T10:00:00+14:01')": False,
        "SELECT ToDateTime('2024-01-01T10:00:00+99:99')": None,
        "SELECT ToDateTime('2024-01-01T10:00:00+14:01')": None,
        "SELECT ConvertsToTime('T25:00:00')": False,
        "SELECT ConvertsToTime('T10:00:00+14:01')": False,
        # CQL Time values are transported with the leading T marker (same
        # convention as Time literals/TimeOfDay) so component extraction and
        # precision comparisons parse consistently (CQL-03 EXPLORER QA-006).
        "SELECT ToTime('T10:00:00Z')": "T10:00:00",
        "SELECT ToTime('T10:00:00+14:01')": None,
        "SELECT ConvertsToQuantity('5..5 ''cm''')": False,
        "SELECT ConvertsToQuantity('{\"value\":\"abc\",\"unit\":\"mg\"}')": False,
        "SELECT ConvertsToQuantity('{\"value\":\"5\",\"unit\":\"mg\"}')": False,
        "SELECT ToQuantity('5..5 ''cm''')": None,
        "SELECT ToQuantity(true)": None,
        "SELECT ToQuantity('{\"numerator\":{\"value\":\"10\",\"unit\":\"mg\"},\"denominator\":{\"value\":2,\"unit\":\"mL\"}}')": None,
        "SELECT ConvertsToRatio('1.0 ''mg'':2.0 ''mg''')": True,
        "SELECT ConvertsToRatio('{\"numerator\":{},\"denominator\":{}}')": False,
        "SELECT ConvertsToRatio('{\"numerator\":{\"value\":\"1\",\"unit\":\"mg\"},\"denominator\":{\"value\":2,\"unit\":\"mg\"}}')": False,
        "SELECT ToRatio('{\"numerator\":{},\"denominator\":{}}')": None,
        "SELECT ToRatio('{\"numerator\":{\"value\":\"1\",\"unit\":\"mg\"},\"denominator\":{\"value\":2,\"unit\":\"mg\"}}')": None,
        "SELECT ratioValue('{\"numerator\":{\"value\":\"abc\"},\"denominator\":{\"value\":2}}')": None,
        "SELECT ratioValue('{\"numerator\":{\"value\":\"1\",\"unit\":\"mg\"},\"denominator\":{\"value\":2,\"unit\":\"mg\"}}')": None,
        "SELECT ratioDenominatorValue('{\"numerator\":{\"value\":1},\"denominator\":{\"value\":\"abc\"}}')": None,
        "SELECT ratioNumeratorUnit('{\"numerator\":{\"unit\":\"mg\"},\"denominator\":{\"value\":1,\"unit\":\"mL\"}}')": None,
        "SELECT ratioDenominatorUnit('{\"numerator\":{\"value\":1,\"unit\":\"mg\"},\"denominator\":{\"unit\":\"mL\"}}')": None,
    }

    py = _python_only_connection()
    cpp = _cpp_connection()
    try:
        for expression, expected in expressions.items():
            py_result = py.execute(expression).fetchone()[0]
            cpp_result = cpp.execute(expression).fetchone()[0]
            assert py_result == expected, expression
            assert cpp_result == expected, expression
    finally:
        py.close()
        cpp.close()


def test_cql_ratio_malformed_component_unit_helpers_match_no_python_cpp() -> None:
    expressions = [
        "SELECT ratioNumeratorUnit('{\"numerator\":5,\"denominator\":{\"value\":1}}')",
        "SELECT ratioDenominatorUnit('{\"numerator\":{\"value\":5},\"denominator\":5}')",
    ]

    py = _python_only_connection()
    cpp = _cpp_connection()
    try:
        with no_python_connection() as no_py:
            for expression in expressions:
                assert py.execute(expression).fetchone() == (None,)
                assert cpp.execute(expression).fetchone() == (None,)
                assert no_py.execute(expression).fetchone() == (None,)
    finally:
        py.close()
        cpp.close()


def test_translated_temporal_conversions_use_spec_aware_duckdb_surface() -> None:
    cases = {
        "ToDate('2014-01')": "2014-01",
        "ToDate('2024-02-30')": None,
        "ToDateTime('2014')": "2014",
        "ToDateTime('2024-02-30')": None,
        "ToDateTime('2024-01-01T00:00:00+14:01')": None,
        "ToTime('T00:00:00+14:01')": None,
        "convert '2014-01' to Date": "2014-01",
        "convert '2014' to DateTime": "2014",
        "convert '{\"value\":\"5\",\"unit\":\"mg\"}' to Quantity": None,
        "convert '{\"numerator\":{\"value\":\"1\",\"unit\":\"mg\"},\"denominator\":{\"value\":2,\"unit\":\"mg\"}}' to Ratio": None,
    }

    py = _python_only_connection()
    cpp = _cpp_connection()
    try:
        for expression, expected in cases.items():
            sql = _translated_definition_sql(expression)
            py_result = py.execute(sql).fetchone()[0]
            cpp_result = cpp.execute(sql).fetchone()[0]
            assert py_result == expected, expression
            assert cpp_result == expected, expression
    finally:
        py.close()
        cpp.close()


def test_datetime_constructor_timezone_offset_rounds_and_rejects_non_decimal_literals() -> None:
    cases = {
        "DateTime(2024, 1, 1, 0, 0, 0, 0, 13.5)": "2024-01-01T00:00:00.000+13:30",
        "DateTime(2024, 1, 1, 0, 0, 0, 0, 13.999)": "2024-01-01T00:00:00.000+14:00",
        "DateTime(2024, 1, 1, 0, 0, 0, 0, -13.999)": "2024-01-01T00:00:00.000-14:00",
        "DateTime(2024, 1, 1, 0, 0, 0, 0, 14.0)": "2024-01-01T00:00:00.000+14:00",
    }

    py = _python_only_connection()
    cpp = _cpp_connection()
    try:
        for expression, expected in cases.items():
            sql = _translated_definition_sql(expression)
            assert py.execute(sql).fetchone() == (expected,), expression
            assert cpp.execute(sql).fetchone() == (expected,), expression
    finally:
        py.close()
        cpp.close()


def test_temporal_constructors_reject_non_integer_expression_components() -> None:
    invalid_static_expressions = [
        "Date(2024, 1 = 1, 1)",
        "DateTime(2024, 1 = 1, 1)",
        "Time(1 = 1, 0, 0)",
        "Time('1' + '0', 0, 0)",
        "DateTime(2024, 1, 1, 0, 0, 0, 0, 1 = 1)",
        "DateTime(2024, 1, 1, 0, 0, 0, 0, '1' + '0')",
    ]
    for expression in invalid_static_expressions:
        with pytest.raises(ValueError):
            _translated_definition_sql(expression)

    py = _python_only_connection()
    cpp = _cpp_connection()
    try:
        for expression in [
            "Time(Coalesce(null as String, '10'), 0, 0)",
            "DateTime(2024, 1, 1, 0, 0, 0, 0, Coalesce(null as String, '10'))",
        ]:
            sql = _translated_definition_sql(expression)
            assert py.execute(sql).fetchone() == (None,)
            assert cpp.execute(sql).fetchone() == (None,)
    finally:
        py.close()
        cpp.close()

    for expression in [
        "DateTime(2024, 1, 1, 0, 0, 0, 0, true)",
        "DateTime(2024, 1, 1, 0, 0, 0, 0, '1')",
        "DateTime(2024, 1, 1, 0, 0, 0, 0, 14.001)",
        "DateTime(2024, 1, 1, 0, 0, 0, 0, -14.001)",
    ]:
        with pytest.raises(ValueError):
            _translated_definition_sql(expression)

    py = _python_only_connection()
    cpp = _cpp_connection()
    try:
        expression = "SELECT ToRatio('1.0 ''mg'':2.0 ''mg''')"
        py_result = py.execute(expression).fetchone()[0]
        cpp_result = cpp.execute(expression).fetchone()[0]
        assert py_result == cpp_result
        assert '"numerator"' in py_result and '"denominator"' in py_result

        quantity_expression = "SELECT ToQuantity(ToRatio('10 ''mg'':2 ''mL'''))"
        py_quantity = json.loads(py.execute(quantity_expression).fetchone()[0])
        cpp_quantity = json.loads(cpp.execute(quantity_expression).fetchone()[0])
        assert py_quantity == cpp_quantity
        assert py_quantity["value"] == 5.0
        assert py_quantity["unit"] == "mg/mL"
    finally:
        py.close()
        cpp.close()


def test_cql_temporal_equivalence_normalizes_timezone_per_spec() -> None:
    """CQL §Equivalent (Date, DateTime, Time): the comparison is performed
    in the same way as it is for equality, except that precision-mismatch
    returns false (rather than null). For DateTimes with different timezone
    offsets but the same instant, the equivalence must be True (same as =).

    Regression: previously the ~ operator used raw VARCHAR string comparison
    and did not normalize timezone offsets, so
    @2024-01-01T10:00:00+00:00 ~ @2024-01-01T12:00:00+02:00 returned False
    while = returned True.
    """
    cases = {
        # Same instant, different TZ offsets: ~ must match = (True)
        "@2024-01-01T10:00:00+00:00 ~ @2024-01-01T12:00:00+02:00": True,
        "@2024-01-01T10:00:00+00:00 !~ @2024-01-01T12:00:00+02:00": False,
        # Different instants: False
        "@2024-01-01T10:00:00+00:00 ~ @2024-01-01T10:00:00+05:00": False,
        # Same literal form: True
        "@2024-01-01T10:00:00+00:00 ~ @2024-01-01T10:00:00+00:00": True,
        # Precision-mismatch equivalence: False (not NULL) per spec
        "@2014 ~ @2014-01": False,
        "@2012-01-01 ~ @2012-01-01T12": False,
        # Same precision: True
        "@2014-01-15 ~ @2014-01-15": True,
        "@2014-01-15 ~ @2014-01-16": False,
    }

    py = _python_only_connection()
    cpp = _cpp_connection()
    try:
        for expression, expected in cases.items():
            sql = _translated_definition_sql(expression)
            assert py.execute(sql).fetchone() == (expected,), expression
            assert cpp.execute(sql).fetchone() == (expected,), expression
    finally:
        py.close()
        cpp.close()


def test_cql_negative_ratio_literal_propagates_sign_into_numerator() -> None:
    """CQL §Types/Ratio + §ToString RatioOverload example uses a negative-
    numerator Ratio literal: `-0.1 'mg':0.1 'mg'`. Previously the parser
    consumed the leading `-` as a unary negation of the WHOLE Ratio (which
    has no negation operator), causing a DuckDB Binder Error. After the
    fix, the sign is propagated into the numerator.

    Regression: parse_expression("-0.1 'mg':0.1 'mg'") previously returned
    UnaryExpression('-', FunctionRef("ToRatio", [Literal("0.1 'mg':0.1 'mg'")]));
    now returns FunctionRef("ToRatio", [Literal("-0.1 'mg':0.1 'mg'")]).
    """
    from fhir4ds.cql.parser import parse_expression
    from fhir4ds.cql.parser.ast_nodes import FunctionRef, UnaryExpression

    # Decimal Quantity with units, negative numerator
    ast = parse_expression("-0.1 'mg':0.1 'mg'")
    assert isinstance(ast, FunctionRef), type(ast).__name__
    assert ast.name == "ToRatio"
    assert len(ast.arguments) == 1
    literal = ast.arguments[0]
    assert literal.value == "-0.1 'mg':0.1 'mg'", literal.value

    # Integer Ratio, negative numerator
    ast2 = parse_expression("-5:5")
    assert isinstance(ast2, FunctionRef), type(ast2).__name__
    assert ast2.arguments[0].value == "-5 '1':5 '1'", ast2.arguments[0].value

    # Regression: positive Ratio literal must still parse correctly
    ast3 = parse_expression("1:8")
    assert isinstance(ast3, FunctionRef)
    assert ast3.arguments[0].value == "1 '1':8 '1'", ast3.arguments[0].value

    # Regression: standalone negative Quantity uses UnaryExpression path
    ast4 = parse_expression("-5 'mg'")
    assert isinstance(ast4, UnaryExpression)
    assert ast4.operator == "-"

    # Regression: standalone negative Integer
    ast5 = parse_expression("-5")
    assert isinstance(ast5, UnaryExpression)
    assert ast5.operator == "-"

    # End-to-end execution: negative Ratio runs without Binder Error
    py = _python_only_connection()
    cpp = _cpp_connection()
    try:
        sql = _translated_definition_sql("-0.1 'mg':0.1 'mg'")
        py_result = json.loads(py.execute(sql).fetchone()[0])
        cpp_result = json.loads(cpp.execute(sql).fetchone()[0])
        assert py_result == cpp_result
        assert py_result["numerator"]["value"] == -0.1
        assert py_result["denominator"]["value"] == 0.1
    finally:
        py.close()
        cpp.close()


def test_cql_quantity_json_value_is_always_decimal_per_spec() -> None:
    """CQL §Types/Quantity: structured type Quantity { value Decimal,
    unit String }. Integer-valued Quantity literals must serialize `value`
    as Decimal/float on BOTH backends, never as Integer. Without this the
    Python fallback diverges from the native C++ UDF for literals like
    `5 'mg'` or `1 year` (Python emits `"value":5`, native emits
    `"value":5.0`).
    """
    cases = [
        "5 'mg'",
        "1 year",
        "10 'cm'",
        "1 'wk'",
        "12 months",
        "1 day",
        "1 hour",
    ]

    py = _python_only_connection()
    cpp = _cpp_connection()
    try:
        for expression in cases:
            sql = _translated_definition_sql(expression)
            py_result = json.loads(py.execute(sql).fetchone()[0])
            cpp_result = json.loads(cpp.execute(sql).fetchone()[0])
            # `value` must be float on both backends
            assert isinstance(py_result["value"], float), (expression, py_result)
            assert isinstance(cpp_result["value"], float), (expression, cpp_result)
            # Cross-backend parity
            assert py_result == cpp_result, (expression, py_result, cpp_result)
    finally:
        py.close()
        cpp.close()


def test_cql_quantity_compound_unit_arithmetic_reduces_per_spec() -> None:
    """CQL §Divide: "12 'cm2' / 3 'cm' ... the result will have a unit of
    'cm'". CQL §Multiply: "12 'cm' * 3 'cm' -> cm2". Native C++ UDFs must
    reduce compound units via exponent arithmetic, matching the Python
    fallback (which uses a UCUM library).

    Regression: previously the native C++ backend emitted raw `cm2/cm`,
    `meter * meter`, `m3/m2`, etc. for compound-unit arithmetic, while the
    Python fallback correctly reduced to canonical UCUM forms.
    """
    cases = [
        # (expression, expected_unit_substring)
        ("12 'cm2' / 3 'cm'", '"unit":"cm"'),
        ("10 'm' * 2 'm'", '"unit":"m2"'),
        ("6 'm3' / 2 'm2'", '"unit":"m"'),
        ("6 'm3' / 2 'm'", '"unit":"m2"'),
        ("5 'cm' * 3 'cm'", '"unit":"cm2"'),
    ]

    py = _python_only_connection()
    cpp = _cpp_connection()
    try:
        for expression, expected_unit_substring in cases:
            sql = _translated_definition_sql(expression)
            py_result = py.execute(sql).fetchone()[0]
            cpp_result = cpp.execute(sql).fetchone()[0]
            assert expected_unit_substring in py_result, (expression, py_result)
            assert expected_unit_substring in cpp_result, (expression, cpp_result)
            # Cross-backend parity
            assert py_result == cpp_result, (expression, py_result, cpp_result)
    finally:
        py.close()
        cpp.close()


def test_cql_temporal_arithmetic_boundary_overflow_remains_invalid_per_official_conformance() -> None:
    """CQL official conformance suite (CqlDateTimeOperatorsTest.xml)
    declares `DateTime(2005, 10, 10) + 8000 years` and
    `DateTime(2005, 10, 10) - 2005 years` as `invalid="true"` — the
    expected behavior is a translation/evaluation error, not SQL NULL.

    This confirms CQL-11 SKEPTIC AGENTS.md note: "translated static
    temporal boundary underflow/overflow remains invalid for official
    CQL conformance." Although CQL §Add prose says "If the result cannot
    be represented, the result is null", the official test suite marks
    such cases as invalid expressions.

    CQL-03 EXPLORER QA-003 initially proposed returning NULL for runtime
    boundary overflow, but verification against the official suite showed
    this regresses DateTimeAddInvalidYears / DateTimeSubtractInvalidYears.
    The current behavior (Python ValueError that surfaces as a DuckDB
    InvalidInputException) is therefore INTENDED — it preserves official
    conformance. Both surfaces (cpp and py) raise consistently.

    Regression: ensure non-overflow arithmetic still works on both surfaces.
    """
    sane_cases = [
        ("@2024-01-15 + 1 year", "2025-01-15"),
        ("@2024-01-15 + 1 month", "2024-02-15"),
        ("@9999-12-31 + 0 years", "9999-12-31"),  # zero delta OK
        ("@0001-01-01 - 0 days", "0001-01-01"),
    ]

    py = _python_only_connection()
    cpp = _cpp_connection()
    try:
        for expression, expected_prefix in sane_cases:
            sql = _translated_definition_sql(expression)
            py_result = py.execute(sql).fetchone()[0]
            cpp_result = cpp.execute(sql).fetchone()[0]
            assert py_result is not None and py_result.startswith(expected_prefix), (
                expression,
                py_result,
            )
            assert cpp_result is not None and cpp_result.startswith(expected_prefix), (
                expression,
                cpp_result,
            )
    finally:
        py.close()
        cpp.close()


def test_cql_ratio_literal_with_negative_denominator_parses_per_spec() -> None:
    """CQL §Types/Ratio: both numerator and denominator are Quantity
    components, and Quantity values are signed Decimals. Negative
    denominators are valid.

    Regression coverage for CQL-03 EXPLORER QA-002: the parser previously
    raised `ParseError: Unexpected literal type: TokenType.MINUS` for
    Ratio literals with a negative denominator like `1:-8` or
    `1 'mg':-8 'mg'`. The HISTORIAN CQL-03 fix only handled leading-minus
    numerators (`-1:8`); negative denominators (MINUS appearing after
    COLON) fell through. Both surfaces must produce identical Ratio JSON
    including the negative denominator value.
    """
    cases = [
        ("1:-8", -8),
        ("-1:-8", -8),
        ("1 'mg':-8 'mg'", -8),
        ("5:-0", 0),  # negative zero denominator
        ("-0:-0", 0),
        ("-1.5 'mg':-2.5 'mg'", -2.5),
        ("1:+8", 8),  # explicit plus
        ("1:8", 8),  # positive control
        ("-1:8", 8),  # negative numerator (HISTORIAN-covered)
    ]

    py = _python_only_connection()
    cpp = _cpp_connection()
    try:
        for expression, expected_denominator_value in cases:
            sql = _translated_definition_sql(expression)
            py_result = json.loads(py.execute(sql).fetchone()[0])
            cpp_result = json.loads(cpp.execute(sql).fetchone()[0])
            assert py_result["denominator"]["value"] == expected_denominator_value, (
                expression,
                py_result,
            )
            assert cpp_result["denominator"]["value"] == expected_denominator_value, (
                expression,
                cpp_result,
            )
            assert py_result == cpp_result, (expression, py_result, cpp_result)
    finally:
        py.close()
        cpp.close()


def test_cql_cross_unit_temperature_comparison_returns_correct_boolean_per_spec() -> None:
    """CQL §Equal (Quantity): "comparison is performed in the same way as
    for equality, except that ... the values are compared after converting
    to a common unit." Cross-unit temperature comparison (Cel vs [degF])
    requires non-linear conversion (degF = degC * 9/5 + 32) which pint
    refuses with "Ambiguous operation with offset unit".

    Regression coverage for CQL-03 EXPLORER QA-001: the Python fallback
    previously returned None for cross-unit temperature comparisons
    because pint's offset-unit conversion fails. The native C++ UDF
    handles the conversion internally. Both backends must return correct
    True/False for canonical temperatures (0degC = 32degF, 100degC =
    212degF).

    NOTE: native C++ has a known binary64 precision limitation for
    non-canonical temperatures (e.g., 1degC = 33.8degF may return False
    due to floating-point rounding in the single-step Cel conversion).
    This test focuses on canonical temperatures that round cleanly.
    """
    canonical_cases = [
        ("0 'Cel' = 32 '[degF]'", True),
        ("100 'Cel' = 212 '[degF]'", True),
        ("37 'Cel' = 98.6 '[degF]'", True),
        ("0 'Cel' ~ 32 '[degF]'", True),
        ("100 'Cel' ~ 212 '[degF]'", True),
        ("32 '[degF]' = 0 'Cel'", True),
        ("212 '[degF]' = 100 'Cel'", True),
        ("1 'Cel' = 1 'Cel'", True),
        ("1 'Cel' = 2 'Cel'", False),
        ("1 'Cel' < 2 'Cel'", True),
        ("1 'Cel' > 2 'Cel'", False),
        ("1 'Cel' = 1 'mg'", None),  # incompatible units
    ]

    py = _python_only_connection()
    cpp = _cpp_connection()
    try:
        for expression, expected in canonical_cases:
            sql = _translated_definition_sql(expression)
            py_result = py.execute(sql).fetchone()[0]
            cpp_result = cpp.execute(sql).fetchone()[0]
            assert py_result == expected, (expression, "py", py_result, "expected", expected)
            assert cpp_result == expected, (expression, "cpp", cpp_result, "expected", expected)
    finally:
        py.close()
        cpp.close()


def test_cql_cross_unit_cel_kelvin_comparison_returns_correct_boolean_per_spec() -> None:
    """CQL §Equal/§Equivalent (Quantity): cross-unit temperature comparison
    Cel<->K (Kelvin) requires non-linear affine conversion (K = Cel + 273.15).

    Regression coverage for CQL-09 EXPLORER QA-002: the native C++ UCUM
    table previously did not include `K`, so Cel<->K cross-unit comparisons
    returned None (incompatible units) while the Python fallback (pint +
    `_compare_offset_temperature`) explicitly handled Cel<->K via Kelvin
    affine conversion. Parity drift on 3 canonical cases. Fix: added `K`
    entry to `extensions/cql/src/include/shared/ucum_units.hpp` and
    extended `to_base`/`from_base` in `extensions/cql/src/cql/quantity.cpp`
    with the affine Kelvin<->Celsius conversion (matching the existing
    Cel<->degF handling).

    NOTE: same binary64 precision limitation as Cel<->degF - non-canonical
    temperatures (e.g., 1 'Cel' = 274.15 'K' may return False due to
    floating-point rounding). This test focuses on canonical temperatures
    that round cleanly.
    """
    canonical_cases = [
        ("0 'Cel' = 273.15 'K'", True),
        ("0 'Cel' ~ 273.15 'K'", True),
        ("273.15 'K' = 0 'Cel'", True),
        ("100 'Cel' = 373.15 'K'", True),
        ("0 'Cel' between 272 'K' and 274 'K'", True),
        ("0 'Cel' > 272 'K'", True),
        ("0 'Cel' < 274 'K'", True),
        ("0 'Cel' = 272 'K'", False),
        ("1 'K' = 1 'K'", True),  # same-unit short-circuit
        ("1 'K' > 0 'K'", True),
        ("1 'K' = 1 'mg'", None),  # genuinely incompatible units
    ]

    py = _python_only_connection()
    cpp = _cpp_connection()
    try:
        for expression, expected in canonical_cases:
            sql = _translated_definition_sql(expression)
            py_result = py.execute(sql).fetchone()[0]
            cpp_result = cpp.execute(sql).fetchone()[0]
            assert py_result == expected, (expression, "py", py_result, "expected", expected)
            assert cpp_result == expected, (expression, "cpp", cpp_result, "expected", expected)
    finally:
        py.close()
        cpp.close()


def test_cql_malformed_temporal_literals_rejected_at_lex_time_per_spec() -> None:
    """CQL 1.5 grammar defines strict zero-padded DATE/TIME/DATETIME shapes.

    Malformed literals must raise LexerError rather than silently lexing into
    garbage DateTimeLiteral values (e.g. ``@2024-01-15.year`` previously
    evaluated to the string ``2024-01-15.year``).
    """
    import pytest

    from fhir4ds.cql.errors import CQLError, LexerError, ParseError
    from fhir4ds.cql.parser import parse_expression

    valid = [
        "@2020",
        "@2020-01",
        "@2020-01-01",
        "@T14",
        "@T14:30",
        "@T14:30:22",
        "@T14:30:22.123",
        "@2020-01-01T",
        "@2020-01-01T14",
        "@2020-01-01T14:30",
        "@2020-01-01T14:30:22Z",
        "@2020-01-01T14:30:22+02:00",
        "@2020-01-01T14:30:22.5-05:30",
        "@2020-02-29",
        "@2020-01-01T14:30:22+14:00",
    ]
    for literal in valid:
        assert parse_expression(literal) is not None, literal

    malformed = [
        "@T24:00",  # hour out of range
        "@T14:60",  # minute out of range
        "@T14:30:60",  # second out of range
        "@T14:30:22+02:00",  # Time literals carry no timezone offset
        "@2024-13-01",  # month out of range
        "@2024-00-01",  # month zero
        "@2024-02-30",  # impossible calendar date
        "@2019-02-29",  # non-leap Feb 29
        "@2024-1-1",  # unpadded month/day
        "@2024-01-1",  # unpadded day
        "@24-01-01",  # year must be 4 digits
        "@2024-01-15.year",  # trailing junk swallowed into the literal
        "@2024-01-15.abc",
        "@T14:30:22.abc",
        "@2024-01-15T25:00:00",  # hour out of range
        "@2024-01-15T10:30:22+02",  # offset must be hh:mm
    ]
    for literal in malformed:
        with pytest.raises((ParseError, LexerError)):
            parse_expression(literal)


def test_cql_invalid_unit_quantity_comparison_returns_null_per_spec() -> None:
    """CQL 1.5 §Equal (Quantity): invalid (non-UCUM) units yield null.

    The native C++ same-unit fast path previously compared values without
    validating the unit, returning True/False for unknown units like 'xyz'
    instead of null. Equivalent (~) wraps the null as false per the spec's
    always-boolean equivalent contract.
    """
    cases = [
        ("5 'xyz' = 5 'xyz'", None),
        ("5 'xyz' = 6 'xyz'", None),
        ("5 'xyz' ~ 5 'xyz'", False),
        ("5 'mg' = 5 'mg'", True),
        ("5 'mg' ~ 5 'mg'", True),
        ("100 'cm' = 1 'm'", True),
        ("1 year = 1 year", True),
        ("5 = 5", True),
    ]

    py = _python_only_connection()
    cpp = _cpp_connection()
    try:
        for expression, expected in cases:
            sql = _translated_definition_sql(expression)
            py_result = py.execute(sql).fetchone()[0]
            cpp_result = cpp.execute(sql).fetchone()[0]
            assert py_result == expected, (expression, "py", py_result)
            assert cpp_result == expected, (expression, "cpp", cpp_result)
    finally:
        py.close()
        cpp.close()


def test_cql_ucum_structural_validity_same_code_compare_per_spec() -> None:
    """CQL 1.5 §Equal (Quantity): same-code comparison requires a VALID UCUM
    code, judged by the UCUM case-sensitive grammar — not by local conversion
    table membership (native) or pint's case-insensitive parsing (fallback).

    CQL-03 HISTORIAN QA-001: metric-prefixed symbols ('Mg', 'MG', 'ML'),
    supplement symbols ('G' gauss, 'l' liter), power-of-ten terms
    ('10*3/uL', '10^6'), and exponent-suffixed symbols ('cm3', 'km2') are
    valid UCUM and must compare; bare prefixes ('M', 'u') and unknown codes
    ('xyz') are invalid UCUM and must yield null on BOTH backends.
    """
    cases = [
        ("5 'G' = 5 'G'", True),  # gauss
        ("5 'Mg' = 5 'Mg'", True),  # megagram
        ("5 'MG' < 6 'MG'", True),  # megagauss
        ("5 'dag' = 5 'dag'", True),  # deka-gram (two-char prefix)
        ("5 'Gg' = 5 'Gg'", True),  # gigagram
        ("2 '10*3/uL' = 2 '10*3/uL'", True),  # UCUM power prefix
        ("1 '10^6' = 1 '10^6'", True),
        ("1 'cm3' = 1 'cm3'", True),  # exponent-suffixed symbol
        ("5 'm3' = 5 'm3'", True),
        ("2 'km2' = 2 'km2'", True),
        ("1 'm20' = 1 'm20'", None),  # two exponent digits: not UCUM grammar
        ("1 'cm0' = 1 'cm0'", None),  # exponent must be 1-9
        ("5 'M' = 5 'M'", None),  # bare mega prefix: invalid UCUM
        ("5 'u' = 5 'u'", None),  # bare micro prefix: invalid UCUM
        ("5 'M' ~ 5 'M'", False),  # equivalent wraps null as false
    ]
    py = _python_only_connection()
    cpp = _cpp_connection()
    try:
        for expression, expected in cases:
            sql = _translated_definition_sql(expression)
            py_result = py.execute(sql).fetchone()[0]
            cpp_result = cpp.execute(sql).fetchone()[0]
            assert py_result == expected, (expression, "py", py_result)
            assert cpp_result == expected, (expression, "cpp", cpp_result)
    finally:
        py.close()
        cpp.close()


def test_cql_ratio_tuple_selector_compares_as_ratio_per_spec() -> None:
    """CQL 1.5 §Types Ratio: the Ratio { numerator: X, denominator: Y }
    constructor produces a Ratio whose equality is component-wise Quantity
    equality and whose equivalence compares the represented value.

    CQL-03 HISTORIAN QA-002: the tuple selector previously emitted generic
    json_object scalars, so identical Ratios compared null and equivalent
    ratios compared false. Integer components implicitly convert to
    unit-'1' quantities per the constructor signature.
    """
    cases = [
        ("Ratio { numerator: 1 'mg', denominator: 2 'mg' } = Ratio { numerator: 1 'mg', denominator: 2 'mg' }", True),
        ("Ratio { numerator: 1, denominator: 2 } = Ratio { numerator: 1, denominator: 2 }", True),
        ("Ratio { numerator: 1, denominator: 2 } = 1:2", True),
        ("Ratio { numerator: 1, denominator: 2 } ~ 1:2", True),
        ("Ratio { numerator: 1 'mg', denominator: 2 'mg' } = 1 'mg':2 'mg'", True),
        ("Ratio { numerator: 1 'mg', denominator: 2 'mg' } ~ 2 'mg':4 'mg'", True),
        ("Ratio { numerator: 1, denominator: 2 } = Ratio { numerator: 1, denominator: 3 }", False),
        ("Ratio { numerator: 1 'mg', denominator: 2 'mg' } = 2 'mg':4 'mg'", False),
        # null component propagates per §Equal null semantics
        ("Ratio { numerator: null, denominator: 2 'mg' } = Ratio { numerator: null, denominator: 2 'mg' }", None),
        ("Ratio { }.numerator", None),
    ]
    py = _python_only_connection()
    cpp = _cpp_connection()
    try:
        for expression, expected in cases:
            sql = _translated_definition_sql(expression)
            py_result = py.execute(sql).fetchone()[0]
            cpp_result = cpp.execute(sql).fetchone()[0]
            assert py_result == expected, (expression, "py", py_result)
            assert cpp_result == expected, (expression, "cpp", cpp_result)
        # Accessors still resolve on the folded constructor JSON.
        accessor_sql = _translated_definition_sql(
            "Ratio { numerator: 1 'mg', denominator: 2 'mg' }.numerator.value"
        )
        for con in (py, cpp):
            assert float(con.execute(accessor_sql).fetchone()[0]) == 1.0
    finally:
        py.close()
        cpp.close()


def test_cql_min_max_value_fold_to_spec_constants_per_spec() -> None:
    """CQL 1.5 Appendix B-A: MinValue(T)/MaxValue(T) fold to compile-time
    constants instead of passing an untranslated call into SQL (which
    surfaced as a DuckDB Catalog Error at execution).

    CQL-03 HISTORIAN QA-003.
    """
    from fhir4ds.cql.errors import TranslationError

    cases = [
        ("MinValue(Date) < @2024-01-01", True),
        ("MaxValue(Date) > @2024-01-01", True),
        ("MaxValue(Date) = @9999-12-31", True),
        ("MinValue(DateTime) <= MaxValue(DateTime)", True),
        ("MinValue(Date) < MinValue(DateTime)", True),
        ("MinValue(Time) < @T12:00:00", True),
        ("MaxValue(Time) > @T12:00:00", True),
        ("ToString(MinValue(Date))", "0001-01-01"),
        ("ToString(MaxValue(Time))", "23:59:59.999"),
        ("MinValue(Integer)", -2147483648),
        ("MaxValue(Long)", 9223372036854775807),
    ]
    py = _python_only_connection()
    cpp = _cpp_connection()
    try:
        for expression, expected in cases:
            sql = _translated_definition_sql(expression)
            py_result = py.execute(sql).fetchone()[0]
            cpp_result = cpp.execute(sql).fetchone()[0]
            assert py_result == expected, (expression, "py", py_result)
            assert cpp_result == expected, (expression, "cpp", cpp_result)
        # Types without spec constants fail fast with a typed error instead
        # of silent SQL passthrough.
        with pytest.raises(TranslationError):
            _translated_definition_sql("MinValue(String)")
    finally:
        py.close()
        cpp.close()


def test_cql03_explorer_temporal_component_property_accessors_dual_backend() -> None:
    """CQL 1.5 §09-b (Date and Time Component From): the property accessor
    form ``X.month`` is the same operator as ``month from X`` and must route
    through dateComponent, not FHIRPath text navigation. Temporal-literal
    define aliases must inline (CQL-03 EXPLORER QA-001/QA-002)."""

    cases = {
        "(@2024-06-15).month": 6,
        "(@2024).year": 2024,
        "(@2024-06).month": 6,
        "(@2024-06).day": None,
        "(@T14:30).hour": 14,
        "(@T14).hour": 14,
        "(@T14).minute": None,
        "ToTime('T14').hour": 14,
        "(@2024-01-01T12:30:45).second": 45,
        "(@2024-01-01T12:30:45.123).millisecond": 123,
        "time from @2024-06-15T12:30:00": "T12:30:00",
    }
    alias_cases = {
        "library CQL03E2 version '1.0'\ndefine D: @2024-06-15\ndefine Result: D.month\n": 6,
        "library CQL03E2 version '1.0'\ndefine D: @2024-06\ndefine Result: D.month\n": 6,
        "library CQL03E2 version '1.0'\ndefine T: @T14:30\ndefine Result: T.hour\n": 14,
    }

    py = _python_only_connection()
    cpp = _cpp_connection()
    try:
        for expression, expected in cases.items():
            sql = _translated_definition_sql(expression)
            assert py.execute(sql).fetchone() == (expected,), expression
            assert cpp.execute(sql).fetchone() == (expected,), expression
        for library, expected in alias_cases.items():
            sql = CQLToSQLTranslator().translate_library_to_sql(parse_cql(library))
            assert py.execute(sql).fetchone() == (expected,), library
            assert cpp.execute(sql).fetchone() == (expected,), library
    finally:
        py.close()
        cpp.close()


def test_cql03_explorer_timezoneoffset_property_accessor_per_spec() -> None:
    """CQL 1.5 cql.g4 lists 'timezoneoffset' as a dateTimeComponent AND a
    keywordIdentifier: ``(@2024-01-01T12:00:00+02:00).timezoneOffset`` must
    parse and extract the Decimal-hours offset (CQL-03 EXPLORER QA-005)."""

    cases = {
        "(@2024-01-01T12:00:00+02:00).timezoneOffset": 2.0,
        "(@2024-01-01T12:00:00-02:30).timezoneOffset": -2.5,
        "(@2024-01-01T12:00:00Z).timezoneOffset": 0.0,
        "(@2024-01-01T12:00:00+02:00).timezoneoffset": 2.0,
    }

    py = _python_only_connection()
    cpp = _cpp_connection()
    try:
        for expression, expected in cases.items():
            sql = _translated_definition_sql(expression)
            assert py.execute(sql).fetchone() == (expected,), expression
            assert cpp.execute(sql).fetchone() == (expected,), expression
    finally:
        py.close()
        cpp.close()


def test_cql03_explorer_seconds_milliseconds_combined_precision_equality() -> None:
    """CQL 1.5 (DateTime/Time types, §Equal): seconds and milliseconds are
    combined and represented as a single Decimal precision for comparison;
    unspecified milliseconds are treated as 0, so ``.0 = no-ms`` is TRUE and
    ``.5 = no-ms`` is FALSE (spec-pinned examples). Minute-precision
    mismatch with fractional seconds stays uncertain (null).
    (CQL-03 EXPLORER QA-003)."""

    cases = {
        "@T10:00:00.0 = @T10:00:00": True,
        "@T10:00:00.5 = @T10:00:00": False,
        "@2024-11-15T12:30:00.0 = @2024-11-15T12:30:00": True,
        "@2024-11-15T12:30:00.5 = @2024-11-15T12:30:00": False,
        "@2024-11-15T12:30:00.5 = @2024-11-15T12:30": None,
        "@T10:00:00.5 > @T10:00:00": True,
        "@T10:00:00.0 < @T10:00:00": False,
        "@T10:00:00.500 = @T10:00:00.5": True,
    }

    py = _python_only_connection()
    cpp = _cpp_connection()
    try:
        for expression, expected in cases.items():
            sql = _translated_definition_sql(expression)
            assert py.execute(sql).fetchone() == (expected,), expression
            assert cpp.execute(sql).fetchone() == (expected,), expression
    finally:
        py.close()
        cpp.close()


def test_cql03_explorer_ratio_accessor_quantity_arithmetic() -> None:
    """CQL 1.5 §Ratio: .numerator/.denominator are Quantity values and must
    participate in Quantity ± Quantity arithmetic (CQL-03 EXPLORER QA-004)."""

    numerator_sql = _translated_definition_sql(
        "ToRatio('10 ''mg'':2 ''mL''').numerator + 5 'mg'"
    )
    denominator_sql = _translated_definition_sql(
        "ToRatio('10 ''mg'':2 ''mL''').denominator + 3 'mL'"
    )

    py = _python_only_connection()
    cpp = _cpp_connection()
    try:
        for sql, expected in (
            (numerator_sql, {"value": 15.0, "unit": "mg"}),
            (denominator_sql, {"value": 5.0, "unit": "mL"}),
        ):
            py_value = json.loads(py.execute(sql).fetchone()[0])
            cpp_value = json.loads(cpp.execute(sql).fetchone()[0])
            for value in (py_value, cpp_value):
                assert value["value"] == expected["value"], value
                assert (value.get("unit") or value.get("code")) == expected["unit"], value
    finally:
        py.close()
        cpp.close()
