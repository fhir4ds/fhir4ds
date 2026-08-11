"""Parity tests for FHIRPath conversion functions in DuckDB UDFs."""

from __future__ import annotations

import json

import duckdb

from fhir4ds.fhirpath.duckdb import register_fhirpath
from fhir4ds.fhirpath.duckdb.udf import (
    fhirpath_bool_udf,
    fhirpath_is_valid_udf,
    fhirpath_json_udf,
    fhirpath_number_udf,
    fhirpath_scalar,
    fhirpath_text_udf,
)


RESOURCE = json.dumps({"resourceType": "Patient", "id": "p"})


def _connection() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect(config={"allow_unsigned_extensions": True})
    register_fhirpath(con)
    return con


def test_decimal_string_does_not_convert_to_integer() -> None:
    cases = {
        "'1.0'.toInteger()": ([], None, None, None),
        "1.0.toInteger()": ([], None, None, None),
        "0.0.toInteger()": ([], None, None, None),
        "' 1'.toInteger()": ([], None, None, None),
        "'1 '.toInteger()": ([], None, None, None),
        "'+1'.toInteger()": (["1"], "1", "[1]", True),
        "1.0.convertsToInteger()": (["false"], "false", "[false]", False),
        "0.0.convertsToInteger()": (["false"], "false", "[false]", False),
        "' 1'.convertsToInteger()": (["false"], "false", "[false]", False),
        "'1 '.convertsToInteger()": (["false"], "false", "[false]", False),
        "'+1'.convertsToInteger()": (["true"], "true", "[true]", True),
    }

    con = _connection()
    try:
        for expression, expected in cases.items():
            cpp = con.execute(
                "SELECT fhirpath(?::JSON, ?), fhirpath_text(?::JSON, ?), fhirpath_json(?::JSON, ?), fhirpath_bool(?::JSON, ?)",
                [RESOURCE, expression, RESOURCE, expression, RESOURCE, expression, RESOURCE, expression],
            ).fetchone()
            py = (
                fhirpath_scalar(RESOURCE, expression),
                fhirpath_text_udf(RESOURCE, expression),
                fhirpath_json_udf(RESOURCE, expression),
                fhirpath_bool_udf(RESOURCE, expression),
            )
            assert cpp == py
            assert cpp == expected
    finally:
        con.close()


def test_out_of_range_integer_literals_are_row_resilient_in_fallback(monkeypatch) -> None:
    expressions = [
        "2147483648.toInteger()",
        "2147483648.convertsToInteger()",
        "-2147483649.toInteger()",
        "-2147483649.convertsToInteger()",
    ]
    expected = ([], None, None, None, None, False)
    query = """
        SELECT
            fhirpath(?::JSON, ?),
            fhirpath_json(?::JSON, ?),
            fhirpath_text(?::JSON, ?),
            fhirpath_number(?::JSON, ?),
            fhirpath_bool(?::JSON, ?),
            fhirpath_is_valid(?)
    """

    con = _connection()
    monkeypatch.setattr(duckdb, "__version__", "0.0.0-forced-python-fallback")
    fallback = _connection()
    try:
        for expression in expressions:
            params = [
                RESOURCE,
                expression,
                RESOURCE,
                expression,
                RESOURCE,
                expression,
                RESOURCE,
                expression,
                RESOURCE,
                expression,
                expression,
            ]
            assert con.execute(query, params).fetchone() == expected
            assert fallback.execute(query, params).fetchone() == expected
    finally:
        con.close()
        fallback.close()


def test_boolean_and_integer_converts_reject_arguments(monkeypatch) -> None:
    resource = json.dumps(
        {
            "resourceType": "Observation",
            "strTrue": "true",
            "strInt": "1",
        }
    )
    expressions = [
        "'true'.convertsToBoolean(2)",
        "'1'.convertsToInteger(2)",
        "convertsToBoolean(strTrue)",
        "convertsToInteger(strInt)",
    ]

    con = _connection()
    monkeypatch.setattr(duckdb, "__version__", "0.0.0-forced-python-fallback")
    fallback = _connection()
    try:
        for expression in expressions:
            params = [resource, expression, resource, expression, expression]
            query = """
                SELECT fhirpath(?::JSON, ?), fhirpath_json(?::JSON, ?), fhirpath_is_valid(?)
            """
            assert con.execute(query, params).fetchone() == ([], None, False)
            assert fallback.execute(query, params).fetchone() == ([], None, False)
    finally:
        con.close()
        fallback.close()


def test_fp06_iif_and_conversion_signature_edges_match_python_fallback() -> None:
    resource = json.dumps(
        {
            "resourceType": "Observation",
            "strYes": "yes",
            "strInt": "1",
        }
    )
    invalid_expressions = [
        "iif(true)",
        "iif(true, 'yes', 'no', 'extra')",
        "iif(1|2, 'yes', 'no')",
        "true.toBoolean(1)",
        "'1'.toInteger(2)",
        "strYes.convertsToBoolean(1)",
        "'1'.convertsToInteger(2)",
        "(true|false).toBoolean()",
        "(1|2).toInteger()",
        "(true|false).convertsToBoolean()",
        "(1|2).convertsToInteger()",
    ]
    valid_lazy_expressions = {
        "iif(true, 'safe', (1|2).toInteger())": (["safe"], '["safe"]', True),
        "iif(false, (1|2).toInteger(), 'safe')": (["safe"], '["safe"]', True),
        "iif({}, 'yes', 'no')": (["no"], '["no"]', True),
        "iif(0, 'yes', 'no')": (["yes"], '["yes"]', True),
        "iif(0.0, 'yes', 'no')": (["yes"], '["yes"]', True),
        "iif(0.toInteger(), 'yes', 'no')": (["yes"], '["yes"]', True),
    }

    con = _connection()
    try:
        for expression in invalid_expressions:
            cpp = con.execute(
                "SELECT fhirpath(?::JSON, ?), fhirpath_json(?::JSON, ?), fhirpath_is_valid(?)",
                [resource, expression, resource, expression, expression],
            ).fetchone()
            py = (
                fhirpath_scalar(resource, expression),
                fhirpath_json_udf(resource, expression),
                fhirpath_is_valid_udf(expression),
            )
            assert cpp == py == ([], None, False), expression

        for expression, expected in valid_lazy_expressions.items():
            cpp = con.execute(
                "SELECT fhirpath(?::JSON, ?), fhirpath_json(?::JSON, ?), fhirpath_is_valid(?)",
                [resource, expression, resource, expression, expression],
            ).fetchone()
            py = (
                fhirpath_scalar(resource, expression),
                fhirpath_json_udf(resource, expression),
                fhirpath_is_valid_udf(expression),
            )
            assert cpp == py == expected, expression
    finally:
        con.close()


def test_fp06_explorer_iif_conversion_edges_match_forced_fallback(monkeypatch) -> None:
    resource = json.dumps({"resourceType": "Patient", "id": "p"})
    cases = {
        "iif('1'.convertsToInteger(), 'T', 'F')": (["T"], '["T"]', True),
        "iif('+1'.convertsToInteger(), '+1'.toInteger(), 'bad')": (["1"], "[1]", True),
        "-1.convertsToInteger()": ([], None, False),
        "(-1).convertsToInteger()": (["true"], "[true]", True),
        "('b'|'a').sort(-$this)": (["b", "a"], '["b","a"]', True),
    }

    con = _connection()
    monkeypatch.setattr(duckdb, "__version__", "0.0.0-forced-python-fallback")
    fallback = _connection()
    try:
        for expression, expected in cases.items():
            params = [resource, expression, resource, expression, expression]
            query = "SELECT fhirpath(?::JSON, ?), fhirpath_json(?::JSON, ?), fhirpath_is_valid(?)"
            assert con.execute(query, params).fetchone() == expected
            assert fallback.execute(query, params).fetchone() == expected
    finally:
        con.close()
        fallback.close()


def test_date_datetime_and_decimal_conversion_match_cpp() -> None:
    resource = json.dumps(
        {
            "resourceType": "Patient",
            "d": "2015-02-04",
            "ym": "2015-02",
            "dt": "2015-02-04T14:34:28",
            "bool": True,
            "i": 1,
        }
    )
    expressions = ["dt.toDate()", "d.toDateTime()", "ym.toDateTime()", "bool.toDecimal()", "i.toDecimal()"]

    con = _connection()
    try:
        for expression in expressions:
            cpp = con.execute(
                "SELECT fhirpath(?::JSON, ?), fhirpath_text(?::JSON, ?), fhirpath_json(?::JSON, ?), fhirpath_number(?::JSON, ?)",
                [resource, expression, resource, expression, resource, expression, resource, expression],
            ).fetchone()
            py = (
                fhirpath_scalar(resource, expression),
                fhirpath_text_udf(resource, expression),
                fhirpath_json_udf(resource, expression),
                fhirpath_number_udf(resource, expression),
            )
            assert cpp == py
    finally:
        con.close()


def test_fhir_decimal_primitive_to_decimal_matches_fallback_fp07_skeptic() -> None:
    """FP-07 SKEPTIC regression: native C++ `fn_toDecimal` previously skipped
    `effectiveType(val)==Decimal` for JsonVal-wrapped FHIR decimal primitives,
    returning empty. The fix promotes FHIR-backed decimals just like Integer.

    Spec: FHIRPath §5.5.6 toDecimal().
    """
    resource = json.dumps({"resourceType": "Observation", "valueDecimal": 1.5})
    expressions = [
        "Observation.valueDecimal.toDecimal()",
        "Observation.valueDecimal.convertsToDecimal()",
        "Observation.valueDecimal.toDecimal().toString()",
    ]

    con = _connection()
    try:
        for expression in expressions:
            cpp = con.execute(
                "SELECT fhirpath(?::JSON, ?), fhirpath_text(?::JSON, ?), fhirpath_json(?::JSON, ?)",
                [resource, expression, resource, expression, resource, expression],
            ).fetchone()
            py = (
                fhirpath_scalar(resource, expression),
                fhirpath_text_udf(resource, expression),
                fhirpath_json_udf(resource, expression),
            )
            assert cpp == py, f"{expression}: cpp={cpp} py={py}"
    finally:
        con.close()


def test_string_to_decimal_preserves_precision_fp07_skeptic() -> None:
    """FP-07 SKEPTIC regression: native C++ parsed String→Decimal via
    `std::stod` (binary64), losing precision. The fix preserves the source
    digit text and normalizes it (drop leading '+', collapse leading zeros).

    Spec: FHIRPath §5.5.6 toDecimal() + §4.1.4 Decimal precision.
    """
    resource = json.dumps({"resourceType": "Patient"})
    cases = {
        "'3.14159265'.toDecimal().toString()": "3.14159265",
        "'0.1'.toDecimal().toString()": "0.1",
        "'123.45'.toDecimal().toString()": "123.45",
        "'123456789.123456789'.toDecimal().toString()": "123456789.123456789",
        "'+5'.toDecimal().toString()": "5.0",
        "'00'.toDecimal().toString()": "0.0",
    }

    con = _connection()
    try:
        for expression, expected_text in cases.items():
            cpp = con.execute(
                "SELECT fhirpath(?::JSON, ?), fhirpath_text(?::JSON, ?)",
                [resource, expression, resource, expression],
            ).fetchone()
            py = (
                fhirpath_scalar(resource, expression),
                fhirpath_text_udf(resource, expression),
            )
            assert cpp == py, f"{expression}: cpp={cpp} py={py}"
            assert cpp[1] == expected_text, f"{expression}: expected {expected_text!r}, got {cpp[1]!r}"
    finally:
        con.close()


def test_fhir_integer_primitive_to_decimal_preserves_exact_text_fp07_historian() -> None:
    """FP-07 HISTORIAN regression: native C++ `fn_toDecimal` Integer
    effective-type branch (for JsonVal-wrapped FHIR integer primitives)
    routed through `getNumericValue` (double), losing precision above 2^53
    and producing scientific notation in `toString()`. The fix preserves
    canonical JSON integer text via `source_text` so downstream
    `toString()`/equality/comparison observe exact digits.

    Spec: FHIRPath §5.5.6 toDecimal() Integer/Long promotion,
          §4.1.4 fixed-precision decimal formats,
          §5.5.8 Decimal toString uses decimal digit notation (not scientific).
    """
    resource = json.dumps(
        {
            "resourceType": "Observation",
            "id": "fp07-historian-int",
            "longMax": 9223372036854775807,
            "longMin": -9223372036854775808,
            "bigJsInt": 9007199254740993,
            "smallInt": 42,
            "zeroInt": 0,
        }
    )
    # All inputs are JSON integers; toDecimal() must promote to Decimal
    # while preserving the exact integer digits (no scientific notation,
    # no precision loss above 2^53).
    cases = {
        "longMax.toDecimal().toString()": "9223372036854775807.0",
        "longMin.toDecimal().toString()": "-9223372036854775808.0",
        "bigJsInt.toDecimal().toString()": "9007199254740993.0",
        "smallInt.toDecimal().toString()": "42.0",
        "zeroInt.toDecimal().toString()": "0.0",
    }

    con = _connection()
    try:
        for expression, expected_text in cases.items():
            cpp = con.execute(
                "SELECT fhirpath(?::JSON, ?), fhirpath_text(?::JSON, ?)",
                [resource, expression, resource, expression],
            ).fetchone()
            py = (
                fhirpath_scalar(resource, expression),
                fhirpath_text_udf(resource, expression),
            )
            assert cpp == py, f"{expression}: cpp={cpp} py={py}"
            assert cpp[1] == expected_text, (
                f"{expression}: expected {expected_text!r}, got {cpp[1]!r}"
            )
    finally:
        con.close()


def test_unicode_digit_string_to_decimal_rejects_non_ascii_fp07_explorer() -> None:
    """FP-07 EXPLORER regression: Python fallback `numRegex`/`longDecimalStringRegex`
    used `\\d` which is Unicode-aware in Python's `re` module and matches non-ASCII
    Unicode digit code points (full-width U+FF10-U+FF19, Arabic-Indic U+0660-U+0669,
    Devanagari U+0966-U+096F, etc.). Native C++ `isFHIRPathDecimalString` correctly
    uses `std::isdigit` (ASCII-only), so the same input produced different results
    in the two paths.

    Spec: FHIRPath §5.5.6 toDecimal()/convertsToDecimal() regex
          `(\\+|-)?\\d+(\\.\\d+)?`. The ANTLR grammar DIGIT fragment is
          `[0-9]` (ASCII only), so the spec-text `\\d` means ASCII digits,
          not Unicode digits.

    The fix replaces `\\d` with explicit `[0-9]` in `numRegex`,
    `longDecimalStringRegex`, and `intRegex` (FP-06 §5.5.3 sibling same bug class).
    """
    resource = json.dumps({"resourceType": "Patient"})

    # Each expression MUST evaluate to empty/None in both native and fallback,
    # and convertsTo* MUST return false. The Unicode-digit input is rejected.
    cases = [
        # Full-width digits U+FF10-U+FF19
        "'1.５'.toDecimal()",
        "'1.５'.convertsToDecimal()",
        "'１２３'.toDecimal()",
        "'１２L'.toDecimal()",
        # Arabic-Indic digits U+0660-U+0669
        "'٤٥٦'.toDecimal()",
        # Devanagari digits U+0966-U+096F
        "'१२३'.toDecimal()",
        # Same bug class in §5.5.3 toInteger (sibling fix in same regex file)
        "'４２'.toInteger()",
        "'４ｂ'.convertsToInteger()",
    ]

    con = _connection()
    try:
        for expression in cases:
            cpp = con.execute(
                "SELECT fhirpath_json(?::JSON, ?), fhirpath_is_valid(?)",
                [resource, expression, expression],
            ).fetchone()
            py = (
                fhirpath_json_udf(resource, expression),
                None,  # validity not used for python UDF comparison here
            )
            # Native result must be empty/None (or false for convertsTo*)
            cpp_result = cpp[0]
            assert cpp_result is None or cpp_result in ("[]", "[false]"), (
                f"{expression}: native result should be empty/false, got {cpp_result!r}"
            )
            # Python fallback must agree with native
            assert py[0] == cpp_result, (
                f"{expression}: cpp={cpp_result!r} py={py[0]!r}"
            )
    finally:
        con.close()


def test_decimal_string_regex_edges_match_python_fallback(monkeypatch) -> None:
    resource = json.dumps(
        {
            "resourceType": "Observation",
            "plus": "+1.5",
            "exp": "1e2",
            "trailingDot": "1.",
            "leadingDot": ".1",
            "signedLeadingDot": "-.1",
            "space": " 1",
        }
    )
    cases = {
        "plus.toDecimal()": (["1.5"], "1.5", "[1.5]", 1.5, None),
        "exp.toDecimal()": ([], None, None, None, None),
        "trailingDot.toDecimal()": ([], None, None, None, None),
        "leadingDot.toDecimal()": ([], None, None, None, None),
        "signedLeadingDot.toDecimal()": ([], None, None, None, None),
        "space.toDecimal()": ([], None, None, None, None),
        "exp.convertsToDecimal()": (["false"], "false", "[false]", None, False),
        "trailingDot.convertsToDecimal()": (["false"], "false", "[false]", None, False),
        "leadingDot.convertsToDecimal()": (["false"], "false", "[false]", None, False),
        "signedLeadingDot.convertsToDecimal()": (["false"], "false", "[false]", None, False),
        "space.convertsToDecimal()": (["false"], "false", "[false]", None, False),
    }

    con = _connection()
    monkeypatch.setattr(duckdb, "__version__", "0.0.0-forced-python-fallback")
    fallback = _connection()
    try:
        for expression, expected in cases.items():
            cpp = con.execute(
                "SELECT fhirpath(?::JSON, ?), fhirpath_text(?::JSON, ?), fhirpath_json(?::JSON, ?), fhirpath_number(?::JSON, ?), fhirpath_bool(?::JSON, ?)",
                [
                    resource,
                    expression,
                    resource,
                    expression,
                    resource,
                    expression,
                    resource,
                    expression,
                    resource,
                    expression,
                ],
            ).fetchone()
            py = fallback.execute(
                "SELECT fhirpath(?::JSON, ?), fhirpath_text(?::JSON, ?), fhirpath_json(?::JSON, ?), fhirpath_number(?::JSON, ?), fhirpath_bool(?::JSON, ?)",
                [
                    resource,
                    expression,
                    resource,
                    expression,
                    resource,
                    expression,
                    resource,
                    expression,
                    resource,
                    expression,
                ],
            ).fetchone()
            assert cpp == py
            assert cpp == expected
    finally:
        con.close()
        fallback.close()


def test_date_string_timezone_suffixes_do_not_convert_to_date(monkeypatch) -> None:
    resource = json.dumps({"resourceType": "Patient", "id": "p"})
    expressions = [
        "'2015Z'.toDate()",
        "'2015-02Z'.toDate()",
        "'2015-02-04Z'.toDate()",
        "'2015-02-04+05:00'.toDate()",
        "'2015-02-04-05:00'.toDate()",
        "'2015-02-04+05'.toDate()",
        "'2015Z'.convertsToDate()",
        "'2015-02Z'.convertsToDate()",
        "'2015-02-04Z'.convertsToDate()",
        "'2015-02-04+05:00'.convertsToDate()",
        "'2015-02-04-05:00'.convertsToDate()",
        "'2015-02-04+05'.convertsToDate()",
    ]

    con = _connection()
    monkeypatch.setattr(duckdb, "__version__", "0.0.0-forced-python-fallback")
    fallback = _connection()
    try:
        for expression in expressions:
            cpp = con.execute(
                "SELECT fhirpath(?::JSON, ?), fhirpath_text(?::JSON, ?), fhirpath_json(?::JSON, ?), fhirpath_bool(?::JSON, ?)",
                [resource, expression, resource, expression, resource, expression, resource, expression],
            ).fetchone()
            py = fallback.execute(
                "SELECT fhirpath(?::JSON, ?), fhirpath_text(?::JSON, ?), fhirpath_json(?::JSON, ?), fhirpath_bool(?::JSON, ?)",
                [resource, expression, resource, expression, resource, expression, resource, expression],
            ).fetchone()
            assert cpp == py
            if expression.endswith(".toDate()"):
                assert cpp == ([], None, None, None)
            else:
                assert cpp == (["false"], "false", "[false]", False)
    finally:
        con.close()
        fallback.close()


def test_date_datetime_conversions_reject_invalid_native_coercions(monkeypatch) -> None:
    resource = json.dumps(
        {
            "resourceType": "Observation",
            "yearInt": 2015,
            "badDtHour": "2015-02-04T99",
            "badDtText": "2015-02-04Tbogus",
        }
    )
    cases = {
        "yearInt.toDate()": ([], None, None, None, None, None),
        "yearInt.toDateTime()": ([], None, None, None, None, None),
        "yearInt.convertsToDate()": (["false"], "false", "[false]", False, None, None),
        "yearInt.convertsToDateTime()": (["false"], "false", "[false]", False, None, None),
        "badDtHour.toDate()": ([], None, None, None, None, None),
        "badDtHour.convertsToDate()": (["false"], "false", "[false]", False, None, None),
        "badDtText.toDate()": ([], None, None, None, None, None),
        "badDtText.convertsToDate()": (["false"], "false", "[false]", False, None, None),
    }

    con = _connection()
    monkeypatch.setattr(duckdb, "__version__", "0.0.0-forced-python-fallback")
    fallback = _connection()
    try:
        for expression, expected in cases.items():
            cpp = con.execute(
                "SELECT fhirpath(?::JSON, ?), fhirpath_text(?::JSON, ?), fhirpath_json(?::JSON, ?), fhirpath_bool(?::JSON, ?), fhirpath_date(?::JSON, ?), fhirpath_timestamp(?::JSON, ?)",
                [
                    resource,
                    expression,
                    resource,
                    expression,
                    resource,
                    expression,
                    resource,
                    expression,
                    resource,
                    expression,
                    resource,
                    expression,
                ],
            ).fetchone()
            py = fallback.execute(
                "SELECT fhirpath(?::JSON, ?), fhirpath_text(?::JSON, ?), fhirpath_json(?::JSON, ?), fhirpath_bool(?::JSON, ?), fhirpath_date(?::JSON, ?), fhirpath_timestamp(?::JSON, ?)",
                [
                    resource,
                    expression,
                    resource,
                    expression,
                    resource,
                    expression,
                    resource,
                    expression,
                    resource,
                    expression,
                    resource,
                    expression,
                ],
            ).fetchone()
            assert cpp == py
            assert cpp == expected
    finally:
        con.close()
        fallback.close()


def test_fp07_converters_reject_arguments_in_native_and_fallback(monkeypatch) -> None:
    resource = json.dumps({"resourceType": "Observation", "id": "fp07"})
    expressions = [
        "'1'.toDecimal(2)",
        "'2015'.toDate(2)",
        "'2015'.toDateTime(2)",
        "'1'.convertsToDecimal(2)",
        "'2015'.convertsToDate(2)",
        "'2015'.convertsToDateTime(2)",
        "'2015'.toDate('yyyy','MM')",
        "'2015'.toDateTime('yyyy','MM')",
        "'2015'.convertsToDate('yyyy','MM')",
        "'2015'.convertsToDateTime('yyyy','MM')",
    ]

    con = _connection()
    monkeypatch.setattr(duckdb, "__version__", "0.0.0-forced-python-fallback")
    fallback = _connection()
    try:
        for expression in expressions:
            query = "SELECT fhirpath(?::JSON, ?), fhirpath_json(?::JSON, ?), fhirpath_is_valid(?)"
            params = [resource, expression, resource, expression, expression]
            assert con.execute(query, params).fetchone() == ([], None, False)
            assert fallback.execute(query, params).fetchone() == ([], None, False)
    finally:
        con.close()
        fallback.close()


def test_fp07_temporal_format_argument_conversions_match_native_and_fallback(monkeypatch) -> None:
    resource = json.dumps(
        {
            "resourceType": "Observation",
            "dateText": "15-01-2024",
            "dateBasic": "20240115",
            "dateMonth": "2024-01",
            "dateFmt": "dd-MM-yyyy",
            "dtText": "15-01-2024 23:30:05.123",
            "dtTz": "2024/01/15 23:30:05 -0500",
            "dtFmt": "yyyy/MM/dd HH:mm:ss Z",
            "bogusFmt": "bogus",
            "items": [
                {
                    "dateText": "15-01-2024",
                    "dateFmt": "dd-MM-yyyy",
                    "dtTz": "2024/01/15 23:30:05 -0500",
                    "dtFmt": "yyyy/MM/dd HH:mm:ss Z",
                }
            ],
        }
    )
    cases = {
        "dateText.toDate('dd-MM-yyyy')": (
            ["2024-01-15"],
            "2024-01-15",
            '["2024-01-15"]',
            None,
            "2024-01-15",
            None,
            True,
        ),
        "dateText.convertsToDate('dd-MM-yyyy')": (
            ["true"],
            "true",
            "[true]",
            True,
            None,
            None,
            True,
        ),
        "dateBasic.toDate('yyyyMMdd')": (
            ["2024-01-15"],
            "2024-01-15",
            '["2024-01-15"]',
            None,
            "2024-01-15",
            None,
            True,
        ),
        "dateMonth.toDate('yyyy-MM')": (
            ["2024-01"],
            "2024-01",
            '["2024-01"]',
            None,
            "2024-01",
            None,
            True,
        ),
        "dtText.toDateTime('dd-MM-yyyy HH:mm:ss.SSS')": (
            ["2024-01-15T23:30:05.123"],
            "2024-01-15T23:30:05.123",
            '["2024-01-15T23:30:05.123"]',
            None,
            "2024-01-15",
            "2024-01-15T23:30:05.123",
            True,
        ),
        "dtText.convertsToDateTime('dd-MM-yyyy HH:mm:ss.SSS')": (
            ["true"],
            "true",
            "[true]",
            True,
            None,
            None,
            True,
        ),
        "dtTz.toDateTime('yyyy/MM/dd HH:mm:ss Z')": (
            ["2024-01-15T23:30:05-05:00"],
            "2024-01-15T23:30:05-05:00",
            '["2024-01-15T23:30:05-05:00"]',
            None,
            "2024-01-15",
            "2024-01-15T23:30:05-05:00",
            True,
        ),
        "dateText.toDate(dateFmt)": (
            ["2024-01-15"],
            "2024-01-15",
            '["2024-01-15"]',
            None,
            "2024-01-15",
            None,
            True,
        ),
        "dtTz.toDateTime(dtFmt)": (
            ["2024-01-15T23:30:05-05:00"],
            "2024-01-15T23:30:05-05:00",
            '["2024-01-15T23:30:05-05:00"]',
            None,
            "2024-01-15",
            "2024-01-15T23:30:05-05:00",
            True,
        ),
        "items.select(dateText.toDate(dateFmt))": (
            ["2024-01-15"],
            "2024-01-15",
            '["2024-01-15"]',
            None,
            "2024-01-15",
            None,
            True,
        ),
        "items.select(dtTz.toDateTime(dtFmt))": (
            ["2024-01-15T23:30:05-05:00"],
            "2024-01-15T23:30:05-05:00",
            '["2024-01-15T23:30:05-05:00"]',
            None,
            "2024-01-15",
            "2024-01-15T23:30:05-05:00",
            True,
        ),
        "@2015-02-04.toDateTime(bogusFmt)": (
            ["2015-02-04T"],
            "2015-02-04T",
            '["2015-02-04T"]',
            None,
            "2015-02-04",
            "2015-02-04T",
            True,
        ),
    }

    con = _connection()
    monkeypatch.setattr(duckdb, "__version__", "0.0.0-forced-python-fallback")
    fallback = _connection()
    try:
        for expression, expected in cases.items():
            query = """
                SELECT fhirpath(?::JSON, ?), fhirpath_text(?::JSON, ?),
                       fhirpath_json(?::JSON, ?), fhirpath_bool(?::JSON, ?),
                       fhirpath_date(?::JSON, ?), fhirpath_timestamp(?::JSON, ?),
                       fhirpath_is_valid(?)
            """
            params = [
                resource,
                expression,
                resource,
                expression,
                resource,
                expression,
                resource,
                expression,
                resource,
                expression,
                resource,
                expression,
                expression,
            ]
            assert con.execute(query, params).fetchone() == expected
            assert fallback.execute(query, params).fetchone() == expected
    finally:
        con.close()
        fallback.close()


def test_fp07_temporal_literal_conversions_match_native_and_fallback(monkeypatch) -> None:
    cases = {
        "@2015.toDate()": (["2015"], "2015", "2015", None, True),
        "@2015-02-04.toDateTime()": (["2015-02-04T"], "2015-02-04T", "2015-02-04", "2015-02-04T", True),
        "@2015-02-04T14.toDate()": (["2015-02-04"], "2015-02-04", "2015-02-04", None, True),
        "@2015-02-04T14.toDateTime()": (["2015-02-04T14"], "2015-02-04T14", "2015-02-04", "2015-02-04T14", True),
        "@2015-02-04.toDateTime('bogus')": (["2015-02-04T"], "2015-02-04T", "2015-02-04", "2015-02-04T", True),
        "@2015-02-04.toDate('bogus')": (["2015-02-04"], "2015-02-04", "2015-02-04", None, True),
    }

    con = _connection()
    monkeypatch.setattr(duckdb, "__version__", "0.0.0-forced-python-fallback")
    fallback = _connection()
    try:
        for expression, expected in cases.items():
            query = """
                SELECT fhirpath(?::JSON, ?), fhirpath_text(?::JSON, ?),
                       fhirpath_date(?::JSON, ?), fhirpath_timestamp(?::JSON, ?),
                       fhirpath_is_valid(?)
            """
            params = [
                RESOURCE,
                expression,
                RESOURCE,
                expression,
                RESOURCE,
                expression,
                RESOURCE,
                expression,
                expression,
            ]
            assert con.execute(query, params).fetchone() == expected
            assert fallback.execute(query, params).fetchone() == expected
    finally:
        con.close()
        fallback.close()


def test_fp07_decimal_rejects_temporal_and_multi_item_edges(monkeypatch) -> None:
    cases = {
        "@2015.toDecimal()": ([], None, None, None, True),
        "@2015.convertsToDecimal()": (["false"], "false", "[false]", False, True),
        "42L.toDecimal()": (["42.0"], "42.0", "[42.0]", None, True),
        "42L.convertsToDecimal()": (["true"], "true", "[true]", True, True),
        "'42L'.toDecimal()": (["42.0"], "42.0", "[42.0]", None, True),
        "'42L'.convertsToDecimal()": (["true"], "true", "[true]", True, True),
        "'+42L'.toDecimal()": (["42.0"], "42.0", "[42.0]", None, True),
        "'-42L'.toDecimal()": (["-42.0"], "-42.0", "[-42.0]", None, True),
        "'1LL'.toDecimal()": ([], None, None, None, True),
        "'1.0L'.toDecimal()": ([], None, None, None, True),
        "'1l'.toDecimal()": ([], None, None, None, True),
        "2147483648L.toDecimal()": (["2147483648.0"], "2147483648.0", "[2147483648.0]", None, True),
        "2147483648L.convertsToDecimal()": (["true"], "true", "[true]", True, True),
        "9223372036854775807L.toDecimal()": (
            ["9223372036854775807.0"],
            "9223372036854775807.0",
            "[9223372036854775807.0]",
            None,
            True,
        ),
        "9223372036854775807L.convertsToDecimal()": (["true"], "true", "[true]", True, True),
        "(-9223372036854775808L).toDecimal()": (
            ["-9223372036854775808.0"],
            "-9223372036854775808.0",
            "[-9223372036854775808.0]",
            None,
            True,
        ),
        "(-9223372036854775808L).convertsToDecimal()": (["true"], "true", "[true]", True, True),
        "9223372036854775808L.toDecimal()": ([], None, None, None, False),
        "2147483648LL.toDecimal()": ([], None, None, None, False),
        "1.0L.toDecimal()": ([], None, None, None, False),
        "1l.toDecimal()": ([], None, None, None, False),
        "(1|2).toDecimal()": ([], None, None, None, False),
    }

    con = _connection()
    monkeypatch.setattr(duckdb, "__version__", "0.0.0-forced-python-fallback")
    fallback = _connection()
    try:
        for expression, expected in cases.items():
            query = """
                SELECT fhirpath(?::JSON, ?), fhirpath_text(?::JSON, ?),
                       fhirpath_json(?::JSON, ?), fhirpath_bool(?::JSON, ?),
                       fhirpath_is_valid(?)
            """
            params = [
                RESOURCE,
                expression,
                RESOURCE,
                expression,
                RESOURCE,
                expression,
                RESOURCE,
                expression,
                expression,
            ]
            assert con.execute(query, params).fetchone() == expected
            assert fallback.execute(query, params).fetchone() == expected
    finally:
        con.close()
        fallback.close()


def test_quantity_string_and_time_conversion_match_cpp() -> None:
    resource = json.dumps(
        {
            "resourceType": "Observation",
            "s": "abc",
            "t": "14:30:00",
            "tshort": "14:30",
            "badT": "25:00:00",
            "n": 5,
            "d": 1.5,
            "q": {"value": 5, "unit": "mg"},
            "qstr": "5 mg",
            "badQ": "abc mg",
            "date": "2015-02-04",
        }
    )
    expressions = [
        "n.toQuantity()",
        "d.toQuantity()",
        "qstr.toQuantity()",
        "badQ.toQuantity()",
        "n.toQuantity('mg')",
        "qstr.convertsToQuantity()",
        "q.toString()",
        "q.convertsToString()",
        "t.toTime()",
        "tshort.toTime()",
        "badT.toTime()",
    ]

    con = _connection()
    try:
        for expression in expressions:
            cpp = con.execute(
                "SELECT fhirpath(?::JSON, ?), fhirpath_text(?::JSON, ?), fhirpath_json(?::JSON, ?), fhirpath_bool(?::JSON, ?), fhirpath_number(?::JSON, ?)",
                [resource, expression, resource, expression, resource, expression, resource, expression, resource, expression],
            ).fetchone()
            py = (
                fhirpath_scalar(resource, expression),
                fhirpath_text_udf(resource, expression),
                fhirpath_json_udf(resource, expression),
                fhirpath_bool_udf(resource, expression),
                fhirpath_number_udf(resource, expression),
            )
            assert cpp == py
    finally:
        con.close()


def test_time_conversion_preserves_partial_precision(monkeypatch) -> None:
    resource = json.dumps(
        {
            "resourceType": "Observation",
            "hourVal": "14",
            "minuteVal": "14:34",
            "secondVal": "14:34:28",
        }
    )
    cases = {
        "hourVal.toTime()": (["14"], "14", '["14"]'),
        "minuteVal.toTime()": (["14:34"], "14:34", '["14:34"]'),
        "secondVal.toTime()": (["14:34:28"], "14:34:28", '["14:34:28"]'),
        "'14:34'.toTime().toString()": (["14:34"], "14:34", '["14:34"]'),
        "@T14:34.toString()": (["14:34"], "14:34", '["14:34"]'),
    }

    con = _connection()
    try:
        cpp_results = {
            expression: con.execute(
                "SELECT fhirpath(?::JSON, ?), fhirpath_text(?::JSON, ?), fhirpath_json(?::JSON, ?)",
                [resource, expression, resource, expression, resource, expression],
            ).fetchone()
            for expression in cases
        }
    finally:
        con.close()

    monkeypatch.setattr(duckdb, "__version__", "0.0.0-forced-python-fallback")
    fallback = _connection()
    try:
        for expression, expected in cases.items():
            py = fallback.execute(
                "SELECT fhirpath(?::JSON, ?), fhirpath_text(?::JSON, ?), fhirpath_json(?::JSON, ?)",
                [resource, expression, resource, expression, resource, expression],
            ).fetchone()
            assert cpp_results[expression] == py
            assert cpp_results[expression] == expected
    finally:
        fallback.close()


def test_bool_wrapper_rejects_string_conversion_numeric_text(monkeypatch) -> None:
    resource = json.dumps({"resourceType": "Observation", "num": 1, "strNum": "1"})
    cases = {
        "num": True,
        "strNum": None,
        "num.toString()": None,
        "strNum.toBoolean()": True,
    }

    con = _connection()
    try:
        cpp_results = {
            expression: con.execute(
                "SELECT fhirpath_bool(?::JSON, ?)",
                [resource, expression],
            ).fetchone()
            for expression in cases
        }
    finally:
        con.close()

    monkeypatch.setattr(duckdb, "__version__", "0.0.0-forced-python-fallback")
    fallback = _connection()
    try:
        for expression, expected in cases.items():
            py = fallback.execute(
                "SELECT fhirpath_bool(?::JSON, ?)",
                [resource, expression],
            ).fetchone()
            assert cpp_results[expression] == py
            assert cpp_results[expression] == (expected,)
    finally:
        fallback.close()


def test_quantity_string_parser_edges_match_python_fallback(monkeypatch) -> None:
    resource = json.dumps({"resourceType": "Observation", "id": "o"})
    cases = {
        "'1 wk'.convertsToQuantity()": (["false"], "false", "[false]", False, None),
        "'1 wk'.toQuantity()": ([], None, None, None, None),
        "' 1'.convertsToQuantity()": (["false"], "false", "[false]", False, None),
        "' 1'.toQuantity()": ([], None, None, None, None),
        r"'1 \'mg'.convertsToQuantity()": (["false"], "false", "[false]", False, None),
        r"'1 \'mg'.toQuantity()": ([], None, None, None, None),
        r"'1 \'\''.convertsToQuantity()": (["false"], "false", "[false]", False, None),
        r"'1 \'\''.toQuantity()": ([], None, None, None, None),
    }

    con = _connection()
    monkeypatch.setattr(duckdb, "__version__", "0.0.0-forced-python-fallback")
    fallback = _connection()
    try:
        for expression, expected in cases.items():
            cpp = con.execute(
                "SELECT fhirpath(?::JSON, ?), fhirpath_text(?::JSON, ?), fhirpath_json(?::JSON, ?), fhirpath_bool(?::JSON, ?), fhirpath_quantity(?::JSON, ?)",
                [resource, expression, resource, expression, resource, expression, resource, expression, resource, expression],
            ).fetchone()
            py = fallback.execute(
                "SELECT fhirpath(?::JSON, ?), fhirpath_text(?::JSON, ?), fhirpath_json(?::JSON, ?), fhirpath_bool(?::JSON, ?), fhirpath_quantity(?::JSON, ?)",
                [resource, expression, resource, expression, resource, expression, resource, expression, resource, expression],
            ).fetchone()
            assert cpp == py
            assert cpp == expected
    finally:
        con.close()
        fallback.close()


def test_quantity_conversion_unit_argument_matches_python_fallback(monkeypatch) -> None:
    resource = json.dumps({"resourceType": "Observation", "id": "o"})
    cases = {
        "1.convertsToQuantity('kg')": (["false"], False, "[false]", None),
        "1.convertsToQuantity('1')": (["true"], True, "[true]", None),
        r"'1 \'kg\''.convertsToQuantity('kg')": (["true"], True, "[true]", None),
        r"'1 \'kg\''.convertsToQuantity('g')": (["true"], True, "[true]", None),
        r"'1 \'kg\''.convertsToQuantity('s')": (["false"], False, "[false]", None),
        r"'1 \'kg\''.toQuantity('g')": (["1000 'g'"], None, '[{"value":1000,"unit":"g"}]', "1000 'g'"),
    }

    con = _connection()
    monkeypatch.setattr(duckdb, "__version__", "0.0.0-forced-python-fallback")
    fallback = _connection()
    try:
        for expression, expected in cases.items():
            cpp = con.execute(
                "SELECT fhirpath(?::JSON, ?), fhirpath_bool(?::JSON, ?), fhirpath_json(?::JSON, ?), fhirpath_quantity(?::JSON, ?)",
                [resource, expression, resource, expression, resource, expression, resource, expression],
            ).fetchone()
            py = fallback.execute(
                "SELECT fhirpath(?::JSON, ?), fhirpath_bool(?::JSON, ?), fhirpath_json(?::JSON, ?), fhirpath_quantity(?::JSON, ?)",
                [resource, expression, resource, expression, resource, expression, resource, expression],
            ).fetchone()
            assert cpp == py
            assert cpp == expected
    finally:
        con.close()
        fallback.close()


def test_quantity_conversion_dynamic_unit_argument_uses_outer_context(monkeypatch) -> None:
    resource = json.dumps(
        {
            "resourceType": "Observation",
            "valueQuantity": {
                "value": 5,
                "unit": "mg",
                "system": "http://unitsofmeasure.org",
                "code": "mg",
            },
            "targetUnit": "g",
            "badTargetUnit": "s",
            "quantityText": "1 'kg'",
            "items": [
                {"quantityText": "1 'kg'", "targetUnit": "g"},
                {"quantityText": "1000 'mg'", "targetUnit": "g"},
            ],
        }
    )
    cases = {
        "value.toQuantity(targetUnit)": (
            ["0.005 'g'"],
            "0.005 'g'",
            '[{"value":0.005,"unit":"g"}]',
            None,
            "0.005 'g'",
            True,
        ),
        "value.convertsToQuantity(targetUnit)": (["true"], "true", "[true]", True, None, True),
        "value.convertsToQuantity(badTargetUnit)": (["false"], "false", "[false]", False, None, True),
        "quantityText.toQuantity(targetUnit)": (
            ["1000 'g'"],
            "1000 'g'",
            '[{"value":1000,"unit":"g"}]',
            None,
            "1000 'g'",
            True,
        ),
        "quantityText.convertsToQuantity(targetUnit)": (["true"], "true", "[true]", True, None, True),
        "items.select(quantityText.toQuantity(targetUnit))": (
            ["1000 'g'", "1 'g'"],
            "1000 'g'",
            '[{"value":1000,"unit":"g"},{"value":1,"unit":"g"}]',
            None,
            "1000 'g'",
            True,
        ),
        "items.select(quantityText.convertsToQuantity(targetUnit))": (
            ["true", "true"],
            "true",
            "[true,true]",
            True,
            None,
            True,
        ),
    }
    query = """
        SELECT
          fhirpath(?::JSON, ?),
          fhirpath_text(?::JSON, ?),
          fhirpath_json(?::JSON, ?),
          fhirpath_bool(?::JSON, ?),
          fhirpath_quantity(?::JSON, ?),
          fhirpath_is_valid(?)
    """

    con = _connection()
    monkeypatch.setattr(duckdb, "__version__", "0.0.0-forced-python-fallback")
    fallback = _connection()
    try:
        for expression, expected in cases.items():
            params = [
                resource,
                expression,
                resource,
                expression,
                resource,
                expression,
                resource,
                expression,
                resource,
                expression,
                expression,
            ]
            assert con.execute(query, params).fetchone() == expected
            assert fallback.execute(query, params).fetchone() == expected
    finally:
        con.close()
        fallback.close()


def test_quantity_to_string_uses_plain_decimal_not_scientific_notation(monkeypatch) -> None:
    resource = json.dumps(
        {
            "resourceType": "Observation",
            "smallQuantityText": "1 'mg'",
            "largeQuantityText": "1000000000000000 'g'",
            "items": [
                {"quantityText": "2 'm'", "targetUnit": "cm"},
                {"quantityText": "1 'mg'", "targetUnit": "kg"},
            ],
        }
    )
    cases = {
        "smallQuantityText.toQuantity('kg').toString()": (
            ["0.000001 'kg'"],
            "0.000001 'kg'",
            '["0.000001 \'kg\'"]',
            True,
        ),
        "largeQuantityText.toQuantity().toString()": (
            ["1000000000000000 'g'"],
            "1000000000000000 'g'",
            '["1000000000000000 \'g\'"]',
            True,
        ),
        "items.select(quantityText.toQuantity(targetUnit).toString())": (
            ["200 'cm'", "0.000001 'kg'"],
            "200 'cm'",
            '["200 \'cm\'","0.000001 \'kg\'"]',
            True,
        ),
    }
    query = """
        SELECT
          fhirpath(?::JSON, ?),
          fhirpath_text(?::JSON, ?),
          fhirpath_json(?::JSON, ?),
          fhirpath_is_valid(?)
    """

    con = _connection()
    monkeypatch.setattr(duckdb, "__version__", "0.0.0-forced-python-fallback")
    fallback = _connection()
    try:
        for expression, expected in cases.items():
            params = [
                resource,
                expression,
                resource,
                expression,
                resource,
                expression,
                expression,
            ]
            cpp = con.execute(query, params).fetchone()
            py = fallback.execute(query, params).fetchone()
            assert cpp == py
            assert cpp == expected
    finally:
        con.close()
        fallback.close()


def test_resource_quantity_conversion_surfaces_match_python_fallback(monkeypatch) -> None:
    resource = json.dumps(
        {
            "resourceType": "Observation",
            "valueQuantity": {
                "value": 5,
                "unit": "mg",
                "system": "http://unitsofmeasure.org",
                "code": "mg",
            },
            "invalidQuantity": {
                "value": "abc",
                "unit": "mg",
                "system": "http://unitsofmeasure.org",
                "code": "mg",
            },
        }
    )
    cases = {
        "value.toQuantity()": (["5 'mg'"], "5 'mg'", None, "5 'mg'", True),
        "value.convertsToQuantity()": (["true"], "true", True, None, True),
        "value.toQuantity('g')": (["0.005 'g'"], "0.005 'g'", None, "0.005 'g'", True),
        "value.convertsToQuantity('g')": (["true"], "true", True, None, True),
        "value.toString()": (["5 'mg'"], "5 'mg'", None, None, True),
        "value.convertsToString()": (["true"], "true", True, None, True),
        "invalidQuantity.toQuantity()": ([], None, None, None, True),
        "invalidQuantity.convertsToQuantity()": (["false"], "false", False, None, True),
    }
    query = """
        SELECT
          fhirpath(?::JSON, ?),
          fhirpath_text(?::JSON, ?),
          fhirpath_bool(?::JSON, ?),
          fhirpath_quantity(?::JSON, ?),
          fhirpath_is_valid(?)
    """

    con = _connection()
    monkeypatch.setattr(duckdb, "__version__", "0.0.0-forced-python-fallback")
    fallback = _connection()
    try:
        for expression, expected in cases.items():
            params = [
                resource,
                expression,
                resource,
                expression,
                resource,
                expression,
                resource,
                expression,
                expression,
            ]
            cpp = con.execute(query, params).fetchone()
            py = fallback.execute(query, params).fetchone()
            assert cpp == py
            assert cpp == expected
    finally:
        con.close()
        fallback.close()


def test_json_decimal_to_string_uses_plain_decimal_not_scientific_notation(monkeypatch) -> None:
    resource = json.dumps(
        {
            "resourceType": "Observation",
            "smallDecimal": 0.000001,
            "largeDecimal": 1000000000000000.0,
        }
    )
    cases = {
        "smallDecimal.toString()": (["0.000001"], "0.000001", "[\"0.000001\"]", None, True),
        "largeDecimal.toString()": (
            ["1000000000000000.0"],
            "1000000000000000.0",
            "[\"1000000000000000.0\"]",
            None,
            True,
        ),
        "9223372036854775807L.toQuantity().toString()": (
            ["9223372036854775807 '1'"],
            "9223372036854775807 '1'",
            "[\"9223372036854775807 '1'\"]",
            None,
            True,
        ),
    }
    query = """
        SELECT
          fhirpath(?::JSON, ?),
          fhirpath_text(?::JSON, ?),
          fhirpath_json(?::JSON, ?),
          fhirpath_bool(?::JSON, ?),
          fhirpath_is_valid(?)
    """

    con = _connection()
    monkeypatch.setattr(duckdb, "__version__", "0.0.0-forced-python-fallback")
    fallback = _connection()
    try:
        for expression, expected in cases.items():
            params = [
                resource,
                expression,
                resource,
                expression,
                resource,
                expression,
                resource,
                expression,
                expression,
            ]
            cpp = con.execute(query, params).fetchone()
            py = fallback.execute(query, params).fetchone()
            assert cpp == py
            assert cpp == expected
    finally:
        con.close()
        fallback.close()


def test_fp08_conversion_signatures_and_singleton_errors_match_fallback(monkeypatch) -> None:
    resource = json.dumps(
        {
            "resourceType": "Observation",
            "s": "abc",
            "time_min": "14:30",
        }
    )
    valid_expressions = [
        "s.toString()",
        "time_min.toTime()",
        "1.toQuantity('1')",
        "1.convertsToQuantity('1')",
        "s.convertsToString()",
        "time_min.convertsToTime()",
    ]
    invalid_expressions = [
        "s.toString(1)",
        "time_min.toTime(1)",
        "1.toQuantity('1','g')",
        "1.convertsToQuantity('1','g')",
        "1.toQuantity(1)",
        "1.convertsToQuantity(1)",
        "1.toQuantity(('1'|'g'))",
        "1.convertsToQuantity(('1'|'g'))",
        "s.convertsToString(1)",
        "time_min.convertsToTime(1)",
        "convertsToString(s)",
        "convertsToTime(time_min)",
        "(1|2).toString()",
        "(1|2).convertsToQuantity()",
    ]
    query = """
        SELECT
          fhirpath(?::JSON, ?),
          fhirpath_text(?::JSON, ?),
          fhirpath_json(?::JSON, ?),
          fhirpath_bool(?::JSON, ?),
          fhirpath_quantity(?::JSON, ?),
          fhirpath_is_valid(?)
    """

    con = _connection()
    monkeypatch.setattr(duckdb, "__version__", "0.0.0-forced-python-fallback")
    fallback = _connection()
    try:
        for expression in valid_expressions:
            params = [
                resource,
                expression,
                resource,
                expression,
                resource,
                expression,
                resource,
                expression,
                resource,
                expression,
                expression,
            ]
            cpp = con.execute(query, params).fetchone()
            py = fallback.execute(query, params).fetchone()
            assert cpp == py
            assert cpp[-1] is True

        for expression in invalid_expressions:
            params = [
                resource,
                expression,
                resource,
                expression,
                resource,
                expression,
                resource,
                expression,
                resource,
                expression,
                expression,
            ]
            expected = ([], None, None, None, None, False)
            assert con.execute(query, params).fetchone() == expected
            assert fallback.execute(query, params).fetchone() == expected
    finally:
        con.close()
        fallback.close()


def test_fp08_to_time_time_literal_passthrough_matches_fallback_fp08_skeptic(monkeypatch) -> None:
    """FP-08 SKEPTIC QA-001 (HIGH): §5.5.9 toTime() Time-literal passthrough.

    Per spec: "If the input collection contains a single item, this function
    will return a single time if: the item is a Time [or] the item is a String
    and is convertible to a Time." Python fallback `to_time()` previously
    failed Time-literal passthrough because `nodes.FP_Time(value)` returns
    None for non-str inputs.
    """
    resource = json.dumps({"resourceType": "Patient", "id": "p1"})
    expressions = [
        ("@T10:30.toTime().toString()", ["10:30"]),
        ("@T10:30:30.toTime().toString()", ["10:30:30"]),
        ("@T14:30:14.toTime().toString()", ["14:30:14"]),
        ("@T14:30:14.559.toTime().toString()", ["14:30:14.559"]),
        ("@T10:30.convertsToTime()", ["true"]),
        ("@T14:30:14.559.convertsToTime()", ["true"]),
    ]

    con = _connection()
    monkeypatch.setattr(duckdb, "__version__", "0.0.0-forced-python-fallback")
    fallback = _connection()
    try:
        for expression, expected_json in expressions:
            query = "SELECT fhirpath(?::JSON, ?), fhirpath_text(?::JSON, ?), fhirpath_is_valid(?)"
            params = [resource, expression, resource, expression, expression]
            cpp = con.execute(query, params).fetchone()
            py = fallback.execute(query, params).fetchone()
            assert cpp == py, f"native vs fallback mismatch on {expression}: {cpp} vs {py}"
            assert cpp[0] == expected_json, f"wrong result on {expression}: got {cpp[0]}, want {expected_json}"
            assert cpp[2] is True
    finally:
        con.close()
        fallback.close()


def test_fp08_to_quantity_rejects_trailing_junk_after_keyword_fp08_skeptic(monkeypatch) -> None:
    """FP-08 SKEPTIC QA-002 (MEDIUM): §5.5.7 toQuantity() trailing junk.

    Native `fn_toQuantity` String-bare-keyword path previously accepted
    trailing junk after a calendar duration keyword by capturing the entire
    substr as unit_str. Per spec regex, after the keyword the string must
    end. Both paths must now reject.
    """
    resource = json.dumps({"resourceType": "Patient", "id": "p1"})
    invalid_expressions = [
        "'4 days extra'.toQuantity()",
        "'4 day extra'.toQuantity()",
        "'4 year extra'.toQuantity()",
        "'4 d extra'.toQuantity()",
        "'4 days '.toQuantity()",
        "'4 days '.convertsToQuantity()",
    ]

    con = _connection()
    monkeypatch.setattr(duckdb, "__version__", "0.0.0-forced-python-fallback")
    fallback = _connection()
    try:
        for expression in invalid_expressions:
            query = "SELECT fhirpath(?::JSON, ?), fhirpath_is_valid(?)"
            params = [resource, expression, expression]
            cpp = con.execute(query, params).fetchone()
            py = fallback.execute(query, params).fetchone()
            assert cpp == py, f"native vs fallback mismatch on {expression}: {cpp} vs {py}"
            if expression.endswith("convertsToQuantity()"):
                assert cpp[0] == ["false"], f"expected [false] for {expression}, got {cpp[0]}"
            else:
                assert cpp[0] == [], f"expected empty for {expression}, got {cpp[0]}"
            assert cpp[1] is True  # valid expression, just empty/false result
    finally:
        con.close()
        fallback.close()


def test_fp08_to_time_rejects_trailing_colon_fp08_skeptic(monkeypatch) -> None:
    """FP-08 SKEPTIC QA-003 (MEDIUM): §5.5.9 toTime() trailing colon.

    Native `fn_toTime` previously accepted malformed time strings with
    trailing `:` because parseTimeParts consumed the separator without
    verifying 2 trailing digits. Per spec format `hh:mm:ss.fff`, the colon
    must be followed by exactly 2 digits.
    """
    resource = json.dumps({"resourceType": "Patient", "id": "p1"})
    invalid_expressions = [
        "'10:'.toTime()",
        "'10:30:'.toTime()",
        "'10:'.convertsToTime()",
        "'10:30:'.convertsToTime()",
    ]

    con = _connection()
    monkeypatch.setattr(duckdb, "__version__", "0.0.0-forced-python-fallback")
    fallback = _connection()
    try:
        for expression in invalid_expressions:
            query = "SELECT fhirpath(?::JSON, ?), fhirpath_is_valid(?)"
            params = [resource, expression, expression]
            cpp = con.execute(query, params).fetchone()
            py = fallback.execute(query, params).fetchone()
            assert cpp == py, f"native vs fallback mismatch on {expression}: {cpp} vs {py}"
            if expression.endswith("convertsToTime()"):
                # convertsToTime returns [false]
                assert cpp[0] == ["false"], f"expected [false] for {expression}, got {cpp[0]}"
            else:
                # toTime returns empty
                assert cpp[0] == [], f"expected empty for {expression}, got {cpp[0]}"
            assert cpp[1] is True
    finally:
        con.close()
        fallback.close()


def test_fp08_to_quantity_rejects_bare_alpha_non_keyword_fp08_skeptic(monkeypatch) -> None:
    """FP-08 SKEPTIC QA-004 (LOW): §5.5.7 toQuantity() bare-alpha rejection.

    Python fallback `to_quantity()` previously accepted ANY bare alpha
    sequence as a unit (e.g. '0xFF', '5 abc'). Per spec examples, the `time`
    regex group is for calendar duration keywords only; UCUM codes must be
    single-quoted.
    """
    resource = json.dumps({"resourceType": "Patient", "id": "p1"})
    invalid_expressions = [
        "'0xFF'.toQuantity()",
        "'5 abc'.toQuantity()",
        "'5 foo'.toQuantity()",
        "'0xFF'.convertsToQuantity()",
        "'5 abc'.convertsToQuantity()",
    ]

    con = _connection()
    monkeypatch.setattr(duckdb, "__version__", "0.0.0-forced-python-fallback")
    fallback = _connection()
    try:
        for expression in invalid_expressions:
            query = "SELECT fhirpath(?::JSON, ?), fhirpath_is_valid(?)"
            params = [resource, expression, expression]
            cpp = con.execute(query, params).fetchone()
            py = fallback.execute(query, params).fetchone()
            assert cpp == py, f"native vs fallback mismatch on {expression}: {cpp} vs {py}"
            if expression.endswith("convertsToQuantity()"):
                assert cpp[0] == ["false"], f"expected [false] for {expression}, got {cpp[0]}"
            else:
                assert cpp[0] == [], f"expected empty for {expression}, got {cpp[0]}"
            assert cpp[1] is True
    finally:
        con.close()
        fallback.close()


def test_string_decimal_to_quantity_preserves_precision_fp08_historian(monkeypatch) -> None:
    """FP-08 HISTORIAN QA-001 (MEDIUM): §5.5.7/§4.1.4/§5.5.8 String-decimal
    toQuantity precision preservation.

    Native `fn_toQuantity` String-decimal branch previously stripped the
    `.0` from `'0.0'.toQuantity().toString()` returning `"0 '1'"` instead
    of `"0.0 '1'"`. Per §5.5.7 the String value parses as Decimal; per
    §4.1.4 implementations should use fixed-precision decimal formats; per
    §5.5.8 Quantity toString format `(-)?#0.0#` requires at least one
    fractional digit. The fix sets `source_text` from the parsed numeric
    substring (with Python-Decimal-style normalization: drop leading '+',
    collapse leading zeros).
    """
    resource = json.dumps({"resourceType": "Patient", "id": "p1"})
    cases = [
        # (expression, expected_text)
        ("'0.0'.toQuantity().toString()", "0.0 '1'"),
        ("'5.5'.toQuantity().toString()", "5.5 '1'"),
        ("'-5.5'.toQuantity().toString()", "-5.5 '1'"),
        ("'+5'.toQuantity().toString()", "5 '1'"),  # leading + normalized away
        ("'00.5'.toQuantity().toString()", "0.5 '1'"),  # leading zeros collapsed
        ("'3.14159265'.toQuantity().toString()", "3.14159265 '1'"),
    ]
    con = _connection()
    monkeypatch.setattr(duckdb, "__version__", "0.0.0-forced-python-fallback")
    fallback = _connection()
    try:
        for expression, expected in cases:
            query = "SELECT fhirpath_text(?::JSON, ?), fhirpath_is_valid(?)"
            params = [resource, expression, expression]
            cpp = con.execute(query, params).fetchone()
            py = fallback.execute(query, params).fetchone()
            assert cpp == py, f"native vs fallback mismatch on {expression}: {cpp} vs {py}"
            assert cpp[0] == expected, f"expected {expected!r} for {expression}, got {cpp[0]!r}"
            assert cpp[1] is True
    finally:
        con.close()
        fallback.close()


def test_string_to_time_rejects_dot_separator_fp08_historian(monkeypatch) -> None:
    """FP-08 HISTORIAN QA-002 (MEDIUM): §5.5.9 toTime() dot separator rejection.

    Python fallback `FP_Time('"10.30"')` previously parsed `'10.30'` as a
    partial HH=`'10'` because the regex `(?:\\.([0-9]+))?` accepted `.30`
    as a fraction even when minute and second were absent. Per §5.5.9
    format `hh:mm:ss.fff`, a fraction requires preceding hour, minute, AND
    second. Native C++ correctly rejected; the fix adds a strict
    fraction-without-minute/second rejection in `FP_Time.__new__`.
    """
    resource = json.dumps({"resourceType": "Patient", "id": "p1"})
    invalid_expressions = [
        "'10.30'.toTime()",
        "'10.30'.convertsToTime()",
        "'10:30.5'.toTime()",  # fraction without seconds
        "'10:30.5'.convertsToTime()",
    ]
    con = _connection()
    monkeypatch.setattr(duckdb, "__version__", "0.0.0-forced-python-fallback")
    fallback = _connection()
    try:
        for expression in invalid_expressions:
            query = "SELECT fhirpath(?::JSON, ?), fhirpath_is_valid(?)"
            params = [resource, expression, expression]
            cpp = con.execute(query, params).fetchone()
            py = fallback.execute(query, params).fetchone()
            assert cpp == py, f"native vs fallback mismatch on {expression}: {cpp} vs {py}"
            if expression.endswith("convertsToTime()"):
                assert cpp[0] == ["false"], f"expected [false] for {expression}, got {cpp[0]}"
            else:
                assert cpp[0] == [], f"expected empty for {expression}, got {cpp[0]}"
            assert cpp[1] is True
    finally:
        con.close()
        fallback.close()


def test_unicode_digit_string_to_quantity_rejects_non_ascii_fp08_explorer(monkeypatch) -> None:
    """FP-08 EXPLORER QA-001 (HIGH): §5.5.7 toQuantity() Unicode-digit regex.

    Python fallback `quantity_regex` at misc.py:374 used `\\d` which is
    Unicode-aware in Python's `re` module, accepting full-width digits
    U+FF10-U+FF19, Arabic-Indic U+0660-U+0669, Devanagari U+0966-U+096F,
    etc. Native C++ uses `std::isdigit((unsigned char)...)` (ASCII-only)
    per the ANTLR grammar DIGIT fragment `[0-9]`. The asymmetry produced
    `'１０'.toQuantity()` returning empty in native vs `["10 '1'"]` in
    fallback. Same Python-re-Unicode trap as FP-07 EXPLORER (numRegex/
    intRegex/longDecimalStringRegex) — the `quantity_regex` was the
    explicitly-noted out-of-scope sibling that §5.5.7 now owns.
    """
    resource = json.dumps({"resourceType": "Patient", "id": "p1"})
    invalid_expressions = [
        "'０１２'.toQuantity()",  # full-width 012
        "'１０'.toQuantity()",  # full-width 10
        "'１０.５'.toQuantity()",  # full-width 10.5
        "'٠١٢'.toQuantity()",  # Arabic-Indic 012
        "'०१२'.toQuantity()",  # Devanagari 123
        "'０１２'.convertsToQuantity()",
        "'１０'.convertsToQuantity()",
    ]

    con = _connection()
    monkeypatch.setattr(duckdb, "__version__", "0.0.0-forced-python-fallback")
    fallback = _connection()
    try:
        for expression in invalid_expressions:
            query = "SELECT fhirpath(?::JSON, ?), fhirpath_is_valid(?)"
            params = [resource, expression, expression]
            cpp = con.execute(query, params).fetchone()
            py = fallback.execute(query, params).fetchone()
            assert cpp == py, f"native vs fallback mismatch on {expression}: {cpp} vs {py}"
            if expression.endswith("convertsToQuantity()"):
                assert cpp[0] == ["false"], f"expected [false] for {expression}, got {cpp[0]}"
            else:
                assert cpp[0] == [], f"expected empty for {expression}, got {cpp[0]}"
            assert cpp[1] is True
    finally:
        con.close()
        fallback.close()


def test_case_sensitive_calendar_keyword_to_quantity_fp08_explorer(monkeypatch) -> None:
    """FP-08 EXPLORER QA-002 (MEDIUM): §5.5.7/§8.7 case-sensitive calendar keywords.

    Python fallback `to_quantity()` previously accepted uppercase/mixed-case
    calendar duration keywords (`'1 YEAR'`, `'1 Year'`, `'1 DAYS'`) via an
    `elif time.lower()` branch. FHIRPath is case-sensitive per §8.7 and §8.5
    defines keywords as lowercase only. Native `isBareDurationKeyword` at
    evaluator.cpp:1869-1875 already does case-sensitive lookup; the fix
    removes the lowercasing branch from `to_quantity()`.
    """
    resource = json.dumps({"resourceType": "Patient", "id": "p1"})
    invalid_expressions = [
        "'1 YEAR'.toQuantity()",
        "'1 Year'.toQuantity()",
        "'1 YEARS'.toQuantity()",
        "'1 DAYS'.toQuantity()",
        "'1 Day'.toQuantity()",
        "'1 YEAR'.convertsToQuantity()",
        "'1 DAYS'.convertsToQuantity()",
    ]
    valid_expressions = [
        "'1 year'.toQuantity()",
        "'1 years'.toQuantity()",
        "'1 day'.toQuantity()",
        "'1 days'.toQuantity()",
    ]

    con = _connection()
    monkeypatch.setattr(duckdb, "__version__", "0.0.0-forced-python-fallback")
    fallback = _connection()
    try:
        for expression in invalid_expressions:
            query = "SELECT fhirpath(?::JSON, ?), fhirpath_is_valid(?)"
            params = [resource, expression, expression]
            cpp = con.execute(query, params).fetchone()
            py = fallback.execute(query, params).fetchone()
            assert cpp == py, f"native vs fallback mismatch on {expression}: {cpp} vs {py}"
            if expression.endswith("convertsToQuantity()"):
                assert cpp[0] == ["false"], f"expected [false] for {expression}, got {cpp[0]}"
            else:
                assert cpp[0] == [], f"expected empty for {expression}, got {cpp[0]}"
            assert cpp[1] is True
        for expression in valid_expressions:
            query = "SELECT fhirpath(?::JSON, ?), fhirpath_is_valid(?)"
            params = [resource, expression, expression]
            cpp = con.execute(query, params).fetchone()
            py = fallback.execute(query, params).fetchone()
            assert cpp == py, f"native vs fallback mismatch on {expression}: {cpp} vs {py}"
            assert len(cpp[0]) == 1, f"expected single result for {expression}, got {cpp[0]}"
            assert cpp[1] is True
    finally:
        con.close()
        fallback.close()


def test_converted_quantity_value_preserves_decimal_precision_fp08_explorer(monkeypatch) -> None:
    """FP-08 EXPLORER QA-003 (HIGH): §5.5.7/§4.1.4/§4.1.8 converted Quantity .value.

    Native C++ `convertQuantityUnit` at evaluator.cpp:1882-1901 computed
    `out.quantity_value = from_base_value / to_base_factor` via `double`
    arithmetic, producing IEEE 754 binary64 drift that leaked when the
    converted value was materialized as Decimal via `.value` (e.g.
    `(5 'mg').toQuantity('g').value` returned `0.0050000000000000001`
    instead of `0.005`). The fix sets `out.source_text` to the shortest
    round-trip representation of the converted double, mirroring the
    Python fallback's `Decimal(str(value)) * factor` approach. Spec
    citations: §5.5.7 toQuantity unit conversion; §4.1.4 fixed-precision
    decimal formats; §4.1.8 Quantity.value is Decimal. Same binary64-drift
    bug class as FP-07 SKEPTIC/HISTORIAN/EXPLORER (fn_toDecimal) and
    FP-08 HISTORIAN (String-decimal toQuantity) — conversion-arithmetic
    path was the missed sibling.
    """
    resource = json.dumps({"resourceType": "Patient", "id": "p1"})
    # (expression, expected_value)
    cases = [
        ("(5 'mg').toQuantity('g').value", "0.005"),
        ("(-5 'mg').toQuantity('g').value", "-0.005"),
        ("(5.5 'mg').toQuantity('g').value", "0.0055"),
        ("(0.5 'mg').toQuantity('g').value", "0.0005"),
        ("(3 'cm').toQuantity('m').value", "0.03"),
        ("(3 'cm').toQuantity('m').toString()", "0.03 'm'"),
        ("(5 'mg').toQuantity('g').toString()", "0.005 'g'"),
        ("(1 'm').toQuantity('cm').toString()", "100 'cm'"),
        ("(1 'm').toQuantity('mm').toString()", "1000 'mm'"),
        ("(1 'min').toQuantity('s').toString()", "60 's'"),
        ("(1 'h').toQuantity('min').toString()", "60 'min'"),
        ("(7 'd').toQuantity('wk').toString()", "1 'wk'"),
        ("(1000 'g').toQuantity('kg').toString()", "1 'kg'"),
        ("(5 'kg').toQuantity('g').toString()", "5000 'g'"),
        ("(-5 'mg').toQuantity('g').toString()", "-0.005 'g'"),
    ]

    con = _connection()
    monkeypatch.setattr(duckdb, "__version__", "0.0.0-forced-python-fallback")
    fallback = _connection()
    try:
        for expression, expected in cases:
            query = "SELECT fhirpath_text(?::JSON, ?), fhirpath_is_valid(?)"
            params = [resource, expression, expression]
            cpp = con.execute(query, params).fetchone()
            py = fallback.execute(query, params).fetchone()
            assert cpp == py, f"native vs fallback mismatch on {expression}: {cpp} vs {py}"
            assert cpp[0] == expected, f"expected {expected!r} for {expression}, got {cpp[0]!r}"
            assert cpp[1] is True
    finally:
        con.close()
        fallback.close()



def test_arithmetic_result_quantity_conversion_uses_decimal_not_binary64_fp08_skeptic(
    monkeypatch,
) -> None:
    """FP-08 SKEPTIC (2026-06-28): native Quantity arithmetic produces
    binary64 noise (e.g. 0.1 + 0.2 = 0.30000000000000004) which then
    propagated through toQuantity(unit) as 300.00000000000006 'mg'.
    The Python fallback uses Decimal-exact arithmetic so it produced
    300 'mg'. The surgical fix in convertQuantityUnit caps the
    shortest-round-trip search at precision 15 (IEEE 754 double's
    guaranteed-unique significant digits) so binary64 noise in the
    16th/17th digits is dropped at the §5.5.7 conversion boundary.

    Spec citations: §5.5.7 toQuantity unit conversion, §4.1.4
    System.Decimal ("rational number with implicit precision" - not
    binary64 noise), §4.1.8 Quantity value is Decimal.
    """
    resource = json.dumps({"resourceType": "Patient", "id": "p1"})
    # (expression, expected_value)
    cases = [
        # Direct arithmetic then convert
        ("(0.1 'g' + 0.2 'g').toQuantity('mg')", "300 'mg'"),
        ("(0.1 'g' + 0.2 'g').toQuantity('mg').toString()", "300 'mg'"),
        ("(0.1 'g' + 0.2 'g').toQuantity('mg').value", "300.0"),
        # Multiply then convert
        ("(3 'g' * 0.1).toQuantity('mg')", "300 'mg'"),
        ("(3 'g' * 0.1).toQuantity('mg').toString()", "300 'mg'"),
        # Subtraction then convert
        ("(0.3 'g' - 0.1 'g').toQuantity('mg')", "200 'mg'"),
        # Direct literal still works (no regression)
        ("(0.3 'g').toQuantity('mg')", "300 'mg'"),
        ("(0.3 'g').toQuantity('mg').value", "300.0"),
        ("(0.1 'g').toQuantity('mg').value", "100.0"),
    ]

    con = _connection()
    monkeypatch.setattr(duckdb, "__version__", "0.0.0-forced-python-fallback")
    fallback = _connection()
    try:
        for expression, expected in cases:
            query = "SELECT fhirpath_text(?::JSON, ?), fhirpath_is_valid(?)"
            params = [resource, expression, expression]
            cpp = con.execute(query, params).fetchone()
            py = fallback.execute(query, params).fetchone()
            assert cpp == py, f"native vs fallback mismatch on {expression}: {cpp!r} vs {py!r}"
            assert cpp[0] == expected, f"expected {expected!r} for {expression}, got {cpp[0]!r}"
            assert cpp[1] is True
    finally:
        con.close()
        fallback.close()


def test_offset_temperature_cross_conversion_rejects_in_both_backends_fp08_explorer(
    monkeypatch,
) -> None:
    """FP-08 EXPLORER (2026-06-28): Native convertQuantityUnit at
    extensions/fhirpath/src/fhirpath/evaluator.cpp produced arithmetically
    wrong values for offset-based temperature cross-conversions
    (Cel <-> [degF], etc.) because the UCUM table at
    extensions/fhirpath/src/include/shared/ucum_units.hpp:108-109 marks
    `[degF]` with a sentinel factor of -1.0 ("sentinel: handled specially
    by caller") but no special offset-handling branch existed in
    convertQuantityUnit. Native thus computed (1 * 1.0) / -1.0 = -1 for
    `(1 'Cel').toQuantity('[degF]')`, returning `-1 '[degF]'` while the
    Python fallback correctly returned empty (it has no entries for these
    units in any conversion group). Spec citations: FHIRPath §5.5.7
    toQuantity(unit) "according to the unit conversion rules specified by
    UCUM"; §5.5.7 MAY clause "Implementations ... may return empty when
    the `unit` argument is used and it is different than the input
    quantity unit." UCUM defines temperature conversions with affine
    offsets (degF = degC * 9/5 + 32), not multiplicative factors, so the
    sentinel approach is incorrect without special offset handling.
    Surgical fix adds an `isOffsetTemperatureUnit` early-return guard in
    convertQuantityUnit so any cross-unit temperature conversion returns
    empty, mirroring the Python fallback. Same-unit passthrough
    (`1 'Cel'.toQuantity('Cel')`) still works via the earlier identity
    check in convertQuantityUnit.
    """
    resource = json.dumps({"resourceType": "Patient", "id": "p1"})
    cases = [
        # All offset-temperature cross-conversions must reject in both paths
        ("(1 'Cel').toQuantity('[degF]')", None),
        ("(1 'Cel').toQuantity('[degF]').toString()", None),
        ("(1 'Cel').convertsToQuantity('[degF]')", "false"),
        ("(100 '[degF]').toQuantity('Cel')", None),
        ("(100 '[degF]').convertsToQuantity('Cel')", "false"),
        # Sanity: same-unit temperature passthrough still works
        ("(25 'Cel').toQuantity('Cel').toString()", "25 'Cel'"),
    ]

    con = _connection()
    monkeypatch.setattr(duckdb, "__version__", "0.0.0-forced-python-fallback")
    fallback = _connection()
    try:
        for expression, expected in cases:
            query = "SELECT fhirpath_text(?::JSON, ?), fhirpath_is_valid(?)"
            params = [resource, expression, expression]
            cpp = con.execute(query, params).fetchone()
            py = fallback.execute(query, params).fetchone()
            assert cpp == py, (
                f"native vs fallback mismatch on {expression}: {cpp!r} vs {py!r}"
            )
            if expected is None:
                assert cpp[0] is None, (
                    f"expected empty for {expression}, got {cpp[0]!r}"
                )
            else:
                assert cpp[0] == expected, (
                    f"expected {expected!r} for {expression}, got {cpp[0]!r}"
                )
    finally:
        con.close()
        fallback.close()


def test_calendar_vs_ucum_duration_group_separation_fp08_explorer(
    monkeypatch,
) -> None:
    """FP-08 EXPLORER (2026-06-28): Native convertQuantityUnit converted
    calendar durations to UCUM durations across category boundaries
    (e.g. `1 year.toQuantity('s')` -> `31556952 's'`), producing values
    that were arithmetically defensible but spec-category-wrong. The
    Python fallback's `conv_unit_to` separates time-valued units into
    discrete groups (`_year_month_conversion_factor` for years/months;
    `_weeks_days_and_time` for weeks/days/hours/minutes/seconds/
    milliseconds) and rejects cross-group conversions. FHIRPath §4.1.8
    and §6.1 distinguish calendar durations from UCUM definite durations:
    `1 year = 1 'a'` is false (different categories above the second
    precision). The native's flat UCUM table shared the same base unit
    ('s') for both, so conversion silently succeeded with a fixed
    mean-tropical-year approximation that contradicts the spec's
    variable-length calendar semantics. Surgical fix adds
    `isYearMonthDurationUnit` and `isWeeksDaysTimeDurationUnit` helpers
    plus an early-return guard in convertQuantityUnit that rejects
    cross-group conversions. Within-group conversions still work:
    `1 year -> 'a'`, `1 second -> 's'`, `1 year -> 12 months`.
    """
    resource = json.dumps({"resourceType": "Patient", "id": "p1"})
    # (expression, expected_text_or_None_for_empty)
    cases = [
        # Cross-category conversions must reject in both paths
        ("(1 year).toQuantity('s')", None),
        ("(1 year).toQuantity('s').toString()", None),
        ("(1 year).convertsToQuantity('s')", "false"),
        ("(1 year).toQuantity('ms')", None),
        ("(1 month).toQuantity('s')", None),
        ("(1 month).toQuantity('min')", None),
        # Reverse direction: UCUM -> calendar cross-category also rejects
        ("(1 's').toQuantity('year')", None),
        ("(1 's').convertsToQuantity('year')", "false"),
        # Within-group conversions still work
        ("(1 year).toQuantity('a').toString()", "1 'a'"),
        ("(1 month).toQuantity('mo').toString()", "1 'mo'"),
        ("(1 year).toQuantity('month').toString()", "12 month"),
        ("(1 second).toQuantity('s').toString()", "1 's'"),
        ("(1 day).toQuantity('h').toString()", "24 'h'"),
        # Incompatible dimensions (mass vs time) still reject
        ("(5 'g').toQuantity('s')", None),
        ("(5 'g').convertsToQuantity('s')", "false"),
    ]

    con = _connection()
    monkeypatch.setattr(duckdb, "__version__", "0.0.0-forced-python-fallback")
    fallback = _connection()
    try:
        for expression, expected in cases:
            query = "SELECT fhirpath_text(?::JSON, ?), fhirpath_is_valid(?)"
            params = [resource, expression, expression]
            cpp = con.execute(query, params).fetchone()
            py = fallback.execute(query, params).fetchone()
            assert cpp == py, (
                f"native vs fallback mismatch on {expression}: {cpp!r} vs {py!r}"
            )
            if expected is None:
                assert cpp[0] is None, (
                    f"expected empty for {expression}, got {cpp[0]!r}"
                )
            else:
                assert cpp[0] == expected, (
                    f"expected {expected!r} for {expression}, got {cpp[0]!r}"
                )
    finally:
        con.close()
        fallback.close()
