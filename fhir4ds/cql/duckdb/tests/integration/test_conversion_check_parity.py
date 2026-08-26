"""CQL conversion-check UDF parity checks."""

from __future__ import annotations

import duckdb
import pytest

from fhir4ds.cql.duckdb import register
from fhir4ds.cql.duckdb.extension import _register_python_supplements
from fhir4ds.cql.duckdb.macros import conversion as conversion_macros
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


def test_cql_conversion_check_expressions_parse_and_translate() -> None:
    for expression in [
        "ConvertsToBoolean('true')",
        "ConvertsToInteger('42')",
        "ConvertsToLong('9223372036854775807')",
        "ConvertsToRatio('{\"numerator\":{\"value\":1},\"denominator\":{\"value\":2}}')",
        "CanConvertQuantity('1000 mg', 'g')",
        "ConvertQuantity('1000 mg', 'g')",
    ]:
        parsed = parse_expression(expression)
        assert isinstance(parsed, FunctionRef)

    cql = """library ConversionChecks version '1.0.0'
using FHIR version '4.0.1'
context Patient
define B: ConvertsToBoolean('true')
define I: ConvertsToInteger('42')
define Q: CanConvertQuantity('1000 mg', 'g')
"""
    translated = translate_cql(cql)
    assert "ConvertsToBoolean" in str(translated["B"])
    assert "ConvertsToInteger" in str(translated["I"])
    assert "CanConvertQuantity" in str(translated["Q"])


def test_cql_conversion_check_duckdb_surface_matches_cpp_registration() -> None:
    ratio = '{"numerator":{"value":1,"unit":"mg"},"denominator":{"value":2,"unit":"mL"}}'
    expressions = [
        "SELECT ConvertsToBoolean('true')",
        "SELECT ConvertsToBoolean('maybe')",
        "SELECT ConvertsToDate('2024-01-15')",
        "SELECT ConvertsToDateTime('2024-01-15T10:30:00')",
        "SELECT ConvertsToDecimal('1.25')",
        "SELECT ConvertsToDecimal('NaN')",
        "SELECT ConvertsToInteger('42')",
        "SELECT ConvertsToInteger('2147483648')",
        "SELECT ConvertsToLong('9223372036854775807')",
        "SELECT ConvertsToQuantity(5)",
        "SELECT ConvertsToQuantity('5 ''mg''')",
        "SELECT ConvertsToQuantity('5 ''year''')",
        "SELECT ConvertsToQuantity('5 ''not-a-unit''')",
        "SELECT ConvertsToQuantity('5 mg')",
        "SELECT ConvertsToQuantity('{\"value\":\"abc\",\"unit\":\"mg\"}')",
        "SELECT ConvertsToQuantity('{\"numerator\":{\"value\":10,\"unit\":\"mg\"},\"denominator\":{\"value\":2,\"unit\":\"mL\"}}')",
        f"SELECT ConvertsToRatio('{ratio}')",
        "SELECT ConvertsToRatio('1 ''not-a-unit'':2 ''mg''')",
        "SELECT ConvertsToString('abc')",
        "SELECT ConvertsToString([1, 2])",
        "SELECT ConvertsToString({'a': 1})",
        "SELECT ConvertsToString(json_object('a', 1))",
        "SELECT ConvertsToTime('T10:30:00')",
        "SELECT CanConvertQuantity('1000 ''mg''', 'g')",
        "SELECT ConvertQuantity('1000 ''mg''', 'g')",
    ]

    py = _python_only_connection()
    cpp = _cpp_connection()
    try:
        for expression in expressions:
            assert cpp.execute(expression).fetchone() == py.execute(expression).fetchone()
    finally:
        py.close()
        cpp.close()


def test_cql_conversion_check_spec_boundaries_match_cpp_registration() -> None:
    cases = [
        ("SELECT ConvertsToBoolean('1.0')", False),
        ("SELECT ConvertsToBoolean(' 1')", False),
        ("SELECT ConvertsToBoolean(1.0)", True),
        ("SELECT ConvertsToDecimal('1e2')", False),
        ("SELECT ConvertsToDecimal(' 1')", False),
        ("SELECT ConvertsToDecimal('1.')", False),
        ("SELECT ConvertsToDecimal('.5')", False),
        ("SELECT ConvertsToDecimal('1.12345678')", True),
        # CQL 1.5 App. B: ConvertsToDecimal mirrors ToDecimal, which ROUNDS
        # excess fractional scale (CQL-01 doctrine) — QA-002.
        ("SELECT ConvertsToDecimal('1.123456789')", True),
        ("SELECT ConvertsToDecimal('0.0000000001')", True),
        ("SELECT ConvertsToDecimal('1000000000000000000000000000000')", False),
        ("SELECT ConvertsToDecimal(true)", True),
        ("SELECT ConvertsToDate(2024)", False),
        ("SELECT ConvertsToDateTime(2024)", False),
        ("SELECT ConvertsToDate(TIMESTAMP '2024-01-15 10:30:00')", True),
        ("SELECT ConvertsToQuantity('.5 ''mg''')", False),
        ("SELECT ConvertsToQuantity('1.123456789 ''mg''')", False),
        ("SELECT ConvertsToQuantity('1000000000000000000000000000000 ''mg''')", False),
        ("SELECT ConvertsToQuantity('5 ''not-a-unit''')", False),
        ("SELECT ConvertsToQuantity('{\"value\":1e100,\"unit\":\"mg\"}')", False),
        ("SELECT ConvertsToQuantity('{\"value\":5,\"unit\":\"not-a-unit\"}')", False),
        ("SELECT ConvertsToQuantity('{\"numerator\":{\"value\":10,\"unit\":\"mg\"},\"denominator\":{\"value\":2,\"unit\":\"mL\"}}')", True),
        ("SELECT ConvertsToString([1, 2])", False),
        ("SELECT ConvertsToString({'a': 1})", False),
        ("SELECT ConvertsToString(json_object('a', 1))", False),
        ("SELECT ToQuantity('1.123456789 ''mg''')", None),
        ("SELECT ToQuantity('1000000000000000000000000000000 ''mg''')", None),
        ("SELECT ConvertQuantity('{\"value\":1e100,\"unit\":\"mg\"}', 'g')", None),
        ("SELECT ConvertsToRatio('.5 ''mg'':2 ''mg''')", False),
        ("SELECT ConvertsToRatio('1.123456789 ''mg'':2 ''mg''')", False),
        ("SELECT ConvertsToRatio('1000000000000000000000000000000 ''mg'':2 ''mg''')", False),
        ("SELECT ConvertsToRatio('1 ''not-a-unit'':2 ''mg''')", False),
        ("SELECT ConvertsToRatio('{\"numerator\":{\"value\":1e100,\"unit\":\"mg\"},\"denominator\":{\"value\":2,\"unit\":\"mg\"}}')", False),
        ("SELECT ToRatio('1.123456789 ''mg'':2 ''mg''')", None),
        ("SELECT ToRatio('1000000000000000000000000000000 ''mg'':2 ''mg''')", None),
        ("SELECT ToRatio('{\"numerator\":{\"value\":1e100,\"unit\":\"mg\"},\"denominator\":{\"value\":2,\"unit\":\"mg\"}}')", None),
        ("SELECT parse_quantity('{\"value\":0.6733333333333333,\"unit\":\"mg/dL\"}') IS NOT NULL", True),
    ]

    py = _python_only_connection()
    cpp = _cpp_connection()
    try:
        for expression, expected in cases:
            assert py.execute(expression).fetchone() == (expected,)
            assert cpp.execute(expression).fetchone() == (expected,)
    finally:
        py.close()
        cpp.close()


def test_cql_converts_to_string_rejects_structural_values() -> None:
    cql = """library ConversionChecksStructuralString version '1.0.0'
using FHIR version '4.0.1'
context Patient
define ListStringable: ConvertsToString({1, 2})
define TupleStringable: ConvertsToString(Tuple { a: 1 })
define QuantityStringable: ConvertsToString(5 'mg')
define QuantityFromString: ToQuantity('-0.1 ''mg''')
define RatioValue: ToRatio('1.0 ''mg'':2.0 ''mg''')
define QuantityAliasStringable: ConvertsToString(QuantityFromString)
define RatioAliasStringable: ConvertsToString(RatioValue)
define QuantityAliasConvertable: ConvertsToQuantity(QuantityFromString)
define RatioAliasConvertable: ConvertsToRatio(RatioValue)
"""
    translated = translate_cql(cql)
    expected = {
        "ListStringable": False,
        "TupleStringable": False,
        "QuantityStringable": True,
        "QuantityAliasStringable": True,
        "RatioAliasStringable": True,
        "QuantityAliasConvertable": True,
        "RatioAliasConvertable": True,
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


def test_cql_conversion_private_helper_registration_does_not_swallow_unexpected_errors() -> None:
    class BrokenConnection:
        def create_function(self, name, fn, null_handling=None):
            raise RuntimeError("synthetic registration failure")

    class DuplicateConnection:
        def create_function(self, name, fn, null_handling=None):
            raise duckdb.CatalogException("Function already exists")

    with pytest.raises(RuntimeError, match="synthetic registration failure"):
        conversion_macros._create_private_function(BrokenConnection(), "__broken", lambda value: value)

    conversion_macros._create_private_function(DuplicateConnection(), "__duplicate", lambda value: value)


def test_cql_conversion_check_rejects_unicode_digits_per_spec_cql06_explorer() -> None:
    """CQL spec format strings use ASCII digit placeholders ``0`` and ``#``.

    The CQL grammar's lexer only accepts ASCII digits ``[0-9]`` for numeric
    literals, and the conversion operator format strings
    (``(+|-)?#0(.0#)?`` for ToDecimal/ToQuantity,
    ``(+|-)?#0`` for ToInteger/ToLong, ``YYYY``/``MM``/``DD``/``hh``/``mm``/``ss``
    for ToDate/ToDateTime/ToTime) inherit the ASCII-digit requirement.

    Python's ``\\d`` regex character class and ``int()``/``Decimal()``
    constructors accept Unicode decimal digits (Arabic-Indic ``\\u0660-9``,
    Devanagari ``\\u0966-9``, full-width ``\\uFF10-9``, etc.), so they would
    incorrectly return ``True`` for inputs like ``'\\u0661\\u0662\\u0663'``
    that should be rejected per CQL §Formatting Strings.

    Reproducer for CQL-06 EXPLORER (HIGH severity, ASCII-digit guard).
    """
    cases = [
        # ConvertsToInteger — Arabic-Indic digits (Middle East clinical data)
        ("SELECT ConvertsToInteger('١٢٣')", False),  # '١٢٣'
        ("SELECT ConvertsToInteger('१२३')", False),  # '१२३' Devanagari
        ("SELECT ConvertsToInteger('１２３')", False),  # '１２３' full-width
        # ConvertsToLong
        ("SELECT ConvertsToLong('١٢٣')", False),
        # ConvertsToDecimal
        ("SELECT ConvertsToDecimal('１２.３４')", False),  # '１２.３４'
        ("SELECT ConvertsToDecimal('١.٥')", False),  # '١.٥'
        # ConvertsToDate — Arabic-Indic year/month/day
        ("SELECT ConvertsToDate('٢٠٢٤-٠١-٠١')", False),  # '٢٠٢٤-٠١-٠١'
        # ConvertsToDateTime — full-width digits
        ("SELECT ConvertsToDateTime('٢٠٢٤-٠١-٠١T١٢:٣٠')", False),
        # ConvertsToTime — Devanagari
        ("SELECT ConvertsToTime('१२:३०')", False),  # '१२:३०'
        # Sanity: ASCII digits still accepted
        ("SELECT ConvertsToInteger('123')", True),
        ("SELECT ConvertsToDecimal('12.34')", True),
        ("SELECT ConvertsToDate('2024-01-01')", True),
        ("SELECT ConvertsToTime('12:30')", True),
    ]

    py = _python_only_connection()
    cpp = _cpp_connection()
    try:
        for expression, expected in cases:
            assert py.execute(expression).fetchone() == (expected,), expression
            assert cpp.execute(expression).fetchone() == (expected,), expression
    finally:
        py.close()
        cpp.close()


def test_cql_converts_to_quantity_does_not_leak_pint_assertion_error_cql06_explorer() -> None:
    """Quantity unit validation must return False, not raise, on bad units.

    Pint's internal parser raises ``AssertionError`` for some malformed unit
    strings (e.g. the single-codepoint degree-Celsius ``\\u2103``). The
    ``_is_valid_quantity_unit`` helper in ``udf/quantity.py`` previously
    caught only ``UndefinedUnitError``, ``ValueError``, and ``TypeError``,
    so the assertion leaked through the public ``ConvertsToQuantity`` /
    ``ConvertsToRatio`` / ``ConvertQuantity`` / ``CanConvertQuantity``
    surface, violating the CQL §ConvertsToQuantity contract
    ("If the input string is not formatted correctly ... the result is false").

    Reproducer for CQL-06 EXPLORER (MEDIUM severity, defensive programming).
    """
    # Use DuckDB's e-escape string syntax to embed Unicode literals without
    # shell-escape or SQL-quote ambiguity. The pattern "5 '<UNIT>'" with
    # <UNIT> = U+2103 is what triggers pint's AssertionError.
    celsius_unit = "℃"
    cases = [
        # Single-codepoint degree-Celsius triggers pint internal assertion
        ("SELECT ConvertsToQuantity(?)", [f"5 '{celsius_unit}'"]),
        # ConvertQuantity / CanConvertQuantity must also not raise
        ("SELECT CanConvertQuantity(?, 'g')", [f"5 '{celsius_unit}'"]),
        # ConvertsToRatio path with bad unit in numerator
        ("SELECT ConvertsToRatio(?)", [f"5 '{celsius_unit}':1 'mg'"]),
    ]
    py = _python_only_connection()
    cpp = _cpp_connection()
    try:
        for sql, params in cases:
            # Must complete without raising; result is False (bad unit).
            py_row = py.execute(sql, params).fetchone()
            cpp_row = cpp.execute(sql, params).fetchone()
            assert py_row == cpp_row, sql
            assert py_row[0] is False, sql
    finally:
        py.close()
        cpp.close()


def test_cql_to_quantity_accepts_bare_calendar_duration_keywords_cql06_skeptic() -> None:
    """CQL 1.5 Appendix B §ToQuantity: the unit designator may be a
    "case-sensitive UCUM unit of measure or calendar duration keyword,
    singular or plural", and Table 9-G's round-trip rule (``ToString(4 days)``
    results in ``4 days``) requires ToQuantity to parse bare calendar
    duration keywords. Bare non-calendar UCUM units (``5 mg``) must remain
    rejected: UCUM units appear as a quoted string literal.

    Reproducer for CQL-06 SKEPTIC (HIGH severity, calendar keyword grammar).
    """
    cases = [
        ("SELECT ConvertsToQuantity('5 years')", True),
        ("SELECT ConvertsToQuantity('5 year')", True),
        ("SELECT ConvertsToQuantity('4 days')", True),
        ("SELECT ConvertsToQuantity('12 months')", True),
        ("SELECT ConvertsToQuantity('5 weeks')", True),
        ("SELECT ConvertsToQuantity('1 hours')", True),
        ("SELECT ConvertsToQuantity('30 minutes')", True),
        ("SELECT ConvertsToQuantity('3 millisecond')", True),
        ("SELECT ConvertsToQuantity('5 milliseconds')", True),
        ("SELECT ToQuantity('5 years') IS NOT NULL", True),
        # Bare UCUM / unknown / wrong-case tokens stay rejected
        ("SELECT ConvertsToQuantity('5 mg')", False),
        ("SELECT ConvertsToQuantity('5 Years')", False),
        ("SELECT ConvertsToQuantity('5 mgx')", False),
        # Ratio quantities use the same grammar on both sides of the ':'
        ("SELECT ConvertsToRatio('5 years:2 days')", True),
        ("SELECT ConvertsToRatio('5 years:2 mg')", False),
        ("SELECT ToRatio('5 years:2 days') IS NOT NULL", True),
    ]

    py = _python_only_connection()
    cpp = _cpp_connection()
    try:
        for expression, expected in cases:
            assert py.execute(expression).fetchone() == (expected,), expression
            assert cpp.execute(expression).fetchone() == (expected,), expression
    finally:
        py.close()
        cpp.close()


def test_cql_to_string_renders_calendar_duration_keywords_bare_cql06_historian() -> None:
    """CQL 1.5 Appendix B §ToString (Table 9-G): the Quantity string format is
    ``(-)?#0.0# (('<unit>')|(<unit>))`` — calendar duration keywords render as
    a bare keyword ("``ToString(4 days)`` results in the string value
    ``4 days`` (i.e. not ``4 'd'``)"), while UCUM units render quoted.
    Round-trip through ToQuantity must hold on both backends.

    Reproducer for CQL-06 HISTORIAN (HIGH severity, ToString calendar-unit form).
    """
    cases = [
        # Calendar-duration units: bare keyword, round-trippable
        ("ToString(4 days)", "4 day"),
        ("ToString(12 months)", "12 month"),
        ("ToString(5 minutes)", "5 minute"),
        # UCUM units stay quoted
        ("ToString(5 'cm')", "5 'cm'"),
        ("ToString(-0.1 'mg')", "-0.1 'mg'"),
        ("ToString(1.5 'a')", "1.5 'a'"),
        # Unitless decimal literal renders per the decimal ToString rule
        ("ToString(1.5)", "1.5"),
        # Round-trips
        ("ToQuantity(ToString(4 days))", '{"value":4,"unit":"day","code":"day","system":"http://unitsofmeasure.org"}'),
        ("ToQuantity(ToString(5 'cm'))", '{"value":5,"unit":"cm","code":"cm","system":"http://unitsofmeasure.org"}'),
    ]

    py = _python_only_connection()
    cpp = _cpp_connection()
    try:
        for expression, expected in cases:
            cql = f"library T\ncontext Patient\ndefine X: {expression}"
            sql = translate_cql(cql)["X"].to_sql()
            assert py.execute(f"SELECT ({sql})").fetchone() == (expected,), expression
            assert cpp.execute(f"SELECT ({sql})").fetchone() == (expected,), expression
    finally:
        py.close()
        cpp.close()


def test_cql_converts_to_decimal_and_time_mirror_to_functions_cql06_explorer() -> None:
    """CQL 1.5 Appendix B: ConvertsToX must return true for every value
    ToX accepts. ToDecimal ROUNDS excess fractional scale (CQL-01 doctrine),
    so ConvertsToDecimal must accept any fractional digit count (QA-002).
    The CQL Time type carries no retained timezone component, but the
    official cql-tests fixtures (CqlTypeOperatorsTest ToTime2/3/4) accept a
    trailing timezone marker on input and normalize it away — fixtures
    outrank spec prose (QA-003 reclassified INTENDED per fixture evidence).
    """
    cases = [
        ("ConvertsToDecimal('1.123456789')", True),
        ("ConvertsToDecimal('0.0000000001')", True),
        ("ConvertsToDecimal('1.')", False),
        ("ConvertsToDecimal('.5')", False),
        ("ConvertsToDecimal('1e2')", False),
        ("ConvertsToTime('12:00:00Z')", True),
        ("ConvertsToTime('12:00:00+05:00')", True),
        ("ConvertsToTime('12:00:00+99:00')", False),
        ("ConvertsToTime('12:00:00')", True),
        ("ConvertsToTime('T12:00:00.123')", True),
        ("ToTime('12:00:00+05:00')", "T12:00:00"),
        ("ToTime('T14:30:00.0+05:30')", "T14:30:00.0"),
        ("ToTime('12:00:00')", "T12:00:00"),
    ]

    py = _python_only_connection()
    cpp = _cpp_connection()
    try:
        for expression, expected in cases:
            cql = f"library T\ncontext Patient\ndefine X: {expression}"
            sql = translate_cql(cql)["X"].to_sql()
            assert py.execute(f"SELECT ({sql})").fetchone() == (expected,), expression
            assert cpp.execute(f"SELECT ({sql})").fetchone() == (expected,), expression
    finally:
        py.close()
        cpp.close()


def test_cql_fhir_primitive_value_accessor_yields_system_scalar_cql06_explorer() -> None:
    """CQL 1.5 §09-b data-model access: a `.value` segment following a
    FHIR-primitive-typed path is the FHIR-to-System value accessor (the
    canonical FHIRHelpers pattern) and must evaluate to the primitive's
    System value, not to an (empty) FHIRPath `.value` navigation (QA-001).
    """
    from fhir4ds.cql.parser import parse_cql
    from fhir4ds.cql.translator import CQLToSQLTranslator

    library = parse_cql(
        """library T version '1.0.0'
using FHIR version '4.0.1'
context Patient
define BD: [Patient] P return P.birthDate.value
define Gen: [Patient] P return P.gender.value
define StV: [Observation] O return O.status.value
define CastV: [Observation] O return (O.value as FHIR.string).value
define ObsInt: Count([Observation] O where ConvertsToInteger((O.value as FHIR.string).value))
define ObsSum: Sum([Observation] O where ConvertsToInteger((O.value as FHIR.string).value) return ToInteger((O.value as FHIR.string).value))
"""
    )
    columns = ["BD", "Gen", "StV", "CastV", "ObsInt", "ObsSum"]
    sql = CQLToSQLTranslator().translate_library_to_population_sql(
        library, output_columns={c: c for c in columns}
    )
    for factory in (_python_only_connection, _cpp_connection):
        con = factory()
        try:
            con.execute(
                "CREATE TABLE resources (patient_ref VARCHAR, resourceType VARCHAR,"
                " id VARCHAR, resource JSON)"
            )
            con.execute(
                "INSERT INTO resources VALUES"
                " ('p1','Patient','p1','{\"resourceType\":\"Patient\",\"id\":\"p1\","
                "\"birthDate\":\"1980-01-01\",\"gender\":\"male\"}'::JSON),"
                " ('p1','Observation','o1','{\"resourceType\":\"Observation\",\"id\":\"o1\","
                "\"status\":\"final\",\"subject\":{\"reference\":\"Patient/p1\"},"
                "\"valueString\":\"42\"}'::JSON),"
                " ('p1','Observation','o2','{\"resourceType\":\"Observation\",\"id\":\"o2\","
                "\"status\":\"final\",\"subject\":{\"reference\":\"Patient/p1\"},"
                "\"valueString\":\"high\"}'::JSON)"
            )
            row = con.execute(sql).fetchone()
            assert row[1] == ["1980-01-01"], row
            assert row[2] == ["male"], row
            assert row[3] == ["final", "final"], row
            assert sorted(row[4]) == ["42", "high"], row
            assert row[5] == 1 and row[6] == 42, row
        finally:
            con.close()
