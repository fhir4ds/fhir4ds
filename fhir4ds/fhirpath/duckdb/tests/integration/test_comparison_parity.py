"""Parity tests for FHIRPath comparison operators."""

from __future__ import annotations

import json

import duckdb

from fhir4ds.fhirpath.duckdb import register_fhirpath
from fhir4ds.fhirpath.duckdb.udf import (
    fhirpath_bool_udf,
    fhirpath_json_udf,
    fhirpath_number_udf,
    fhirpath_scalar,
    fhirpath_text_udf,
)


def _connection() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect(config={"allow_unsigned_extensions": True})
    register_fhirpath(con)
    return con


def _python_fallback_connection(monkeypatch) -> duckdb.DuckDBPyConnection:
    monkeypatch.setattr(duckdb, "__version__", "0.0.0-forced-python-fallback")
    con = duckdb.connect(config={"allow_unsigned_extensions": True})
    assert register_fhirpath(con) is False
    return con


def test_comparison_operators_match_cpp() -> None:
    resource = json.dumps(
        {
            "resourceType": "Observation",
            "a": 1,
            "b": 2,
            "arr": [1, 2],
            "s": "abc",
            "s2": "def",
        }
    )
    expressions = [
        "a < b",
        "b > a",
        "a <= b",
        "a <= a",
        "b >= a",
        "a >= a",
        "a > b",
        "a < {}",
        "{} < a",
        "arr < b",
        "s < s2",
        "s > s2",
        "@2015-02-04 < @2015-02-05",
        "@2015-02-04 <= @2015-02-04",
        "@2015-02 < @2015-03",
        "@2015-02 < @2015",
        "@2015-02-04T10:00:00 < @2015-02-04T11:00:00",
        "@T10:00:00 < @T11:00:00",
        "1 'mg' < 2 'mg'",
        "1 'mg' < 0.002 'g'",
        "1 'mg' <= 0.001 'g'",
        "1 'mg' > 2 'mg'",
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


def test_string_comparisons_do_not_implicitly_numeric_coerce_in_fallback(monkeypatch) -> None:
    resource = json.dumps(
        {
            "resourceType": "Observation",
            "strnum": "10",
            "strnum2": "2",
        }
    )
    cases = {
        "'10' < '2'": (["true"], "[true]", True),
        "'10' > '2'": (["false"], "[false]", False),
        "'10' > 2": ([], None, None),
        "2 < '10'": ([], None, None),
        "strnum < strnum2": (["true"], "[true]", True),
        "strnum > 2": ([], None, None),
    }

    native = _connection()
    fallback = _python_fallback_connection(monkeypatch)
    try:
        for expression, expected in cases.items():
            native_result = native.execute(
                "SELECT fhirpath(?::JSON, ?), fhirpath_json(?::JSON, ?), fhirpath_bool(?::JSON, ?)",
                [resource, expression, resource, expression, resource, expression],
            ).fetchone()
            fallback_result = fallback.execute(
                "SELECT fhirpath(?::JSON, ?), fhirpath_json(?::JSON, ?), fhirpath_bool(?::JSON, ?)",
                [resource, expression, resource, expression, resource, expression],
            ).fetchone()
            assert native_result == fallback_result == expected, expression
    finally:
        native.close()
        fallback.close()


def test_valid_empty_result_expressions_keep_is_valid_parity(monkeypatch) -> None:
    expressions = [
        "'10' > 2",
        "'x' + 1",
        "true < 1",
    ]

    native = _connection()
    fallback = _python_fallback_connection(monkeypatch)
    try:
        for expression in expressions:
            native_result = native.execute(
                "SELECT fhirpath('{}'::JSON, ?), fhirpath_is_valid(?)",
                [expression, expression],
            ).fetchone()
            fallback_result = fallback.execute(
                "SELECT fhirpath('{}'::JSON, ?), fhirpath_is_valid(?)",
                [expression, expression],
            ).fetchone()
            assert native_result == fallback_result == ([], True), expression

        invalid_expressions = [
            "1 is NoSuchType",
            "(1|2) is Integer",
            "1.is()",
        ]
        for expression in invalid_expressions:
            native_result = native.execute(
                "SELECT fhirpath_is_valid(?)", [expression]
            ).fetchone()
            fallback_result = fallback.execute(
                "SELECT fhirpath_is_valid(?)", [expression]
            ).fetchone()
            assert native_result == fallback_result == (False,), expression
    finally:
        native.close()
        fallback.close()


def test_time_only_values_are_not_ordered_against_dates_or_datetimes(monkeypatch) -> None:
    resource = json.dumps({"resourceType": "Observation"})
    cases = [
        "@2018-01-01 < @T10:00:00",
        "@T10:00:00 > @2018-01-01",
        "@2018-01-01T00:00:00 < @T10:00:00",
        "@T10:00:00 >= @2018-01-01T00:00:00",
    ]

    native = _connection()
    fallback = _python_fallback_connection(monkeypatch)
    try:
        for expression in cases:
            native_result = native.execute(
                "SELECT fhirpath(?::JSON, ?), fhirpath_json(?::JSON, ?), fhirpath_bool(?::JSON, ?), fhirpath_is_valid(?)",
                [resource, expression, resource, expression, resource, expression, expression],
            ).fetchone()
            fallback_result = fallback.execute(
                "SELECT fhirpath(?::JSON, ?), fhirpath_json(?::JSON, ?), fhirpath_bool(?::JSON, ?), fhirpath_is_valid(?)",
                [resource, expression, resource, expression, resource, expression, expression],
            ).fetchone()
            assert native_result == fallback_result == ([], None, None, True), expression
    finally:
        native.close()
        fallback.close()


def test_one_sided_datetime_timezone_policy_matches_native(monkeypatch) -> None:
    resource = json.dumps({"resourceType": "Observation"})
    cases = {
        "@2017-11-05T01:30:00.0-04:00 < @2017-11-05T01:30:00.0": (["false"], "[false]", False, True),
        "@2017-11-05T01:30:00.0-04:00 > @2017-11-05T01:30:00.0": (["false"], "[false]", False, True),
        "@2017-11-05T01:30:00.0-04:00 <= @2017-11-05T01:30:00.0": (["true"], "[true]", True, True),
        "@2017-11-05T01:30:00.0-04:00 >= @2017-11-05T01:30:00.0": (["true"], "[true]", True, True),
    }

    native = _connection()
    fallback = _python_fallback_connection(monkeypatch)
    try:
        for expression, expected in cases.items():
            native_result = native.execute(
                "SELECT fhirpath(?::JSON, ?), fhirpath_json(?::JSON, ?), fhirpath_bool(?::JSON, ?), fhirpath_is_valid(?)",
                [resource, expression, resource, expression, resource, expression, expression],
            ).fetchone()
            fallback_result = fallback.execute(
                "SELECT fhirpath(?::JSON, ?), fhirpath_json(?::JSON, ?), fhirpath_bool(?::JSON, ?), fhirpath_is_valid(?)",
                [resource, expression, resource, expression, resource, expression, expression],
            ).fetchone()
            assert native_result == fallback_result == expected, expression
    finally:
        native.close()
        fallback.close()


def test_resource_backed_datetime_timezone_comparisons_match_native(monkeypatch) -> None:
    resource = json.dumps(
        {
            "resourceType": "Observation",
            "effectiveDateTime": "2015-02-04T10:00:00+01:00",
            "issued": "2015-02-04T09:30:00Z",
        }
    )
    cases = {
        "effectiveDateTime < issued": (["true"], "[true]", True, True),
        "effectiveDateTime > issued": (["false"], "[false]", False, True),
        "effectiveDateTime <= issued": (["true"], "[true]", True, True),
        "effectiveDateTime >= issued": (["false"], "[false]", False, True),
    }

    native = _connection()
    fallback = _python_fallback_connection(monkeypatch)
    try:
        for expression, expected in cases.items():
            native_result = native.execute(
                "SELECT fhirpath(?::JSON, ?), fhirpath_json(?::JSON, ?), fhirpath_bool(?::JSON, ?), fhirpath_is_valid(?)",
                [resource, expression, resource, expression, resource, expression, expression],
            ).fetchone()
            fallback_result = fallback.execute(
                "SELECT fhirpath(?::JSON, ?), fhirpath_json(?::JSON, ?), fhirpath_bool(?::JSON, ?), fhirpath_is_valid(?)",
                [resource, expression, resource, expression, resource, expression, expression],
            ).fetchone()
            assert native_result == fallback_result == expected, expression
    finally:
        native.close()
        fallback.close()


def test_fhir_quantity_path_comparisons_match_python_fallback(monkeypatch) -> None:
    resource = json.dumps(
        {
            "resourceType": "Observation",
            "valueQuantity": {
                "value": 4,
                "unit": "m",
                "code": "m",
                "system": "http://unitsofmeasure.org",
            },
            "component": [
                {
                    "valueQuantity": {
                        "value": 4,
                        "unit": "cm",
                        "code": "cm",
                        "system": "http://unitsofmeasure.org",
                    }
                }
            ],
        }
    )
    cases = {
        "value > component.value": (["true"], "[true]", True),
        "value <= component.value": (["false"], "[false]", False),
        "valueQuantity > component.valueQuantity": (["true"], "[true]", True),
        "valueQuantity <= component.valueQuantity": (["false"], "[false]", False),
    }

    native = _connection()
    fallback = _python_fallback_connection(monkeypatch)
    try:
        for expression, expected in cases.items():
            native_result = native.execute(
                "SELECT fhirpath(?::JSON, ?), fhirpath_json(?::JSON, ?), fhirpath_bool(?::JSON, ?)",
                [resource, expression, resource, expression, resource, expression],
            ).fetchone()
            fallback_result = fallback.execute(
                "SELECT fhirpath(?::JSON, ?), fhirpath_json(?::JSON, ?), fhirpath_bool(?::JSON, ?)",
                [resource, expression, resource, expression, resource, expression],
            ).fetchone()
            assert native_result == fallback_result == expected, expression
    finally:
        native.close()
        fallback.close()


def test_fhir_quantity_unit_only_path_comparisons_match_python_fallback(monkeypatch) -> None:
    resource = json.dumps(
        {
            "resourceType": "Observation",
            "valueQuantity": {
                "value": 4,
                "unit": "m",
            },
            "component": [
                {
                    "valueQuantity": {
                        "value": 4,
                        "unit": "cm",
                    }
                }
            ],
        }
    )

    native = _connection()
    fallback = _python_fallback_connection(monkeypatch)
    try:
        native_result = native.execute(
            "SELECT fhirpath(?::JSON, ?), fhirpath_json(?::JSON, ?), fhirpath_bool(?::JSON, ?)",
            [
                resource,
                "valueQuantity > component.valueQuantity",
                resource,
                "valueQuantity > component.valueQuantity",
                resource,
                "valueQuantity > component.valueQuantity",
            ],
        ).fetchone()
        fallback_result = fallback.execute(
            "SELECT fhirpath(?::JSON, ?), fhirpath_json(?::JSON, ?), fhirpath_bool(?::JSON, ?)",
            [
                resource,
                "valueQuantity > component.valueQuantity",
                resource,
                "valueQuantity > component.valueQuantity",
                resource,
                "valueQuantity > component.valueQuantity",
            ],
        ).fetchone()
        assert native_result == fallback_result == (["true"], "[true]", True)
    finally:
        native.close()
        fallback.close()


def test_large_exact_numeric_and_quantity_comparisons_match_python_fallback(monkeypatch) -> None:
    resource = json.dumps(
        {
            "resourceType": "Observation",
            "bigA": 9007199254740992,
            "bigB": 9007199254740993,
            "valueQuantity": {
                "value": 9007199254740992,
                "unit": "mg",
                "code": "mg",
                "system": "http://unitsofmeasure.org",
            },
            "component": [
                {
                    "valueQuantity": {
                        "value": 9007199254740993,
                        "unit": "mg",
                        "code": "mg",
                        "system": "http://unitsofmeasure.org",
                    }
                }
            ],
        }
    )
    cases = {
        "9223372036854775806L < 9223372036854775807L": (["true"], "[true]", True, True),
        "9223372036854775807L <= 9223372036854775806L": (["false"], "[false]", False, True),
        "9007199254740992.0 < 9007199254740993.0": (["true"], "[true]", True, True),
        "bigA < bigB": (["true"], "[true]", True, True),
        "9007199254740992 'mg' < 9007199254740993 'mg'": (["true"], "[true]", True, True),
        "valueQuantity < component.valueQuantity": (["true"], "[true]", True, True),
    }

    native = _connection()
    fallback = _python_fallback_connection(monkeypatch)
    try:
        for expression, expected in cases.items():
            native_result = native.execute(
                "SELECT fhirpath(?::JSON, ?), fhirpath_json(?::JSON, ?), fhirpath_bool(?::JSON, ?), fhirpath_is_valid(?)",
                [resource, expression, resource, expression, resource, expression, expression],
            ).fetchone()
            fallback_result = fallback.execute(
                "SELECT fhirpath(?::JSON, ?), fhirpath_json(?::JSON, ?), fhirpath_bool(?::JSON, ?), fhirpath_is_valid(?)",
                [resource, expression, resource, expression, resource, expression, expression],
            ).fetchone()
            assert native_result == fallback_result == expected, expression
    finally:
        native.close()
        fallback.close()


def test_boolean_comparison_is_not_ordered(monkeypatch) -> None:
    resource = json.dumps(
        {
            "resourceType": "Observation",
            "truth": True,
            "falsity": False,
        }
    )
    cases = {
        "true > false": ([], None, None, False),
        "truth > falsity": ([], None, None, True),
    }

    native = _connection()
    fallback = _python_fallback_connection(monkeypatch)
    try:
        for expression, expected in cases.items():
            native_result = native.execute(
                "SELECT fhirpath(?::JSON, ?), fhirpath_json(?::JSON, ?), fhirpath_bool(?::JSON, ?), fhirpath_is_valid(?)",
                [resource, expression, resource, expression, resource, expression, expression],
            ).fetchone()
            fallback_result = fallback.execute(
                "SELECT fhirpath(?::JSON, ?), fhirpath_json(?::JSON, ?), fhirpath_bool(?::JSON, ?), fhirpath_is_valid(?)",
                [resource, expression, resource, expression, resource, expression, expression],
            ).fetchone()
            assert native_result == fallback_result == expected, expression
    finally:
        native.close()
        fallback.close()


def test_comparison_singleton_errors_match_for_literal_multi_item_operands(monkeypatch) -> None:
    resource = json.dumps({"resourceType": "Observation", "arr": [1, 2], "b": 3})
    cases = {
        "(1 | 2) < 3": ([], None, None, False),
        "1 < (2 | 3)": ([], None, None, False),
        "arr < b": ([], None, None, True),
    }

    native = _connection()
    fallback = _python_fallback_connection(monkeypatch)
    try:
        for expression, expected in cases.items():
            native_result = native.execute(
                "SELECT fhirpath(?::JSON, ?), fhirpath_json(?::JSON, ?), fhirpath_bool(?::JSON, ?), fhirpath_is_valid(?)",
                [resource, expression, resource, expression, resource, expression, expression],
            ).fetchone()
            fallback_result = fallback.execute(
                "SELECT fhirpath(?::JSON, ?), fhirpath_json(?::JSON, ?), fhirpath_bool(?::JSON, ?), fhirpath_is_valid(?)",
                [resource, expression, resource, expression, resource, expression, expression],
            ).fetchone()
            assert native_result == fallback_result == expected, expression
    finally:
        native.close()
        fallback.close()


def test_calendar_duration_ucum_duration_comparisons_above_seconds_are_empty(monkeypatch) -> None:
    resource = json.dumps({"resourceType": "Observation"})
    cases = {
        "1 year > 1 'a'": ([], None, None, True),
        "1 month <= 1 'mo'": ([], None, None, True),
        "1 week > 1 'wk'": ([], None, None, True),
        "1 day > 1 'd'": ([], None, None, True),
        "1 hour > 1 'h'": ([], None, None, True),
        "1 minute > 1 'min'": ([], None, None, True),
        "10 seconds > 1 's'": (["true"], "[true]", True, True),
        "10 milliseconds > 1 'ms'": (["true"], "[true]", True, True),
    }

    native = _connection()
    fallback = _python_fallback_connection(monkeypatch)
    try:
        for expression, expected in cases.items():
            native_result = native.execute(
                "SELECT fhirpath(?::JSON, ?), fhirpath_json(?::JSON, ?), fhirpath_bool(?::JSON, ?), fhirpath_is_valid(?)",
                [resource, expression, resource, expression, resource, expression, expression],
            ).fetchone()
            fallback_result = fallback.execute(
                "SELECT fhirpath(?::JSON, ?), fhirpath_json(?::JSON, ?), fhirpath_bool(?::JSON, ?), fhirpath_is_valid(?)",
                [resource, expression, resource, expression, resource, expression, expression],
            ).fetchone()
            assert native_result == fallback_result == expected, expression
    finally:
        native.close()
        fallback.close()


def test_equality_vs_comparison_precedence_matches_backends(monkeypatch) -> None:
    """FHIRPath §6.8 operator precedence: comparison (#08) binds tighter than
    equality (#09). Expressions like ``5 > 3 = true`` MUST parse as
    ``(5 > 3) = true``. Native C++ previously inverted this precedence; both
    backends must now agree with the spec.
    """
    resource = json.dumps({"resourceType": "Observation", "a": 5, "b": 3, "active": True})
    cases = {
        # Unparenthesized mixed comparison+equality
        "5 > 3 = true": (["true"], "[true]", True, True),
        "5 > 3 = false": (["false"], "[false]", False, True),
        "5 < 3 = true": (["false"], "[false]", False, True),
        "5 < 3 = false": (["true"], "[true]", True, True),
        "1 < 2 = true": (["true"], "[true]", True, True),
        "1 > 0 = true": (["true"], "[true]", True, True),
        "5 >= 5 = true": (["true"], "[true]", True, True),
        "5 <= 5 = true": (["true"], "[true]", True, True),
        # All four equality operators at #09
        "5 > 3 ~ true": (["true"], "[true]", True, True),
        "5 > 3 != false": (["true"], "[true]", True, True),
        "5 > 3 !~ false": (["true"], "[true]", True, True),
        # Symmetric: equality on the left, comparison on the right
        "true = 5 > 3": (["true"], "[true]", True, True),
        # Parenthesized controls (must still match)
        "(5 > 3) = true": (["true"], "[true]", True, True),
        "true = (5 > 3)": (["true"], "[true]", True, True),
        # Lone comparison (unchanged behavior)
        "5 > 3": (["true"], "[true]", True, True),
        "5 < 3": (["false"], "[false]", False, True),
    }

    native = _connection()
    fallback = _python_fallback_connection(monkeypatch)
    try:
        for expression, expected in cases.items():
            native_result = native.execute(
                "SELECT fhirpath(?::JSON, ?), fhirpath_json(?::JSON, ?), fhirpath_bool(?::JSON, ?), fhirpath_is_valid(?)",
                [resource, expression, resource, expression, resource, expression, expression],
            ).fetchone()
            fallback_result = fallback.execute(
                "SELECT fhirpath(?::JSON, ?), fhirpath_json(?::JSON, ?), fhirpath_bool(?::JSON, ?), fhirpath_is_valid(?)",
                [resource, expression, resource, expression, resource, expression, expression],
            ).fetchone()
            assert native_result == fallback_result == expected, expression
    finally:
        native.close()
        fallback.close()


def test_cross_unit_temperature_comparison_returns_empty_in_both_backends_fp14_skeptic(
    monkeypatch,
) -> None:
    """FP-14 SKEPTIC (2026-06-29): Native C++ §6.2 comparison operator path
    at extensions/fhirpath/src/fhirpath/evaluator.cpp:7539-7559 previously
    lacked the isOffsetTemperatureUnit guard that FP-13 HISTORIAN added to
    the §6.1 equality path at 5 sites. The UCUM table at
    extensions/fhirpath/src/include/shared/ucum_units.hpp:108-109 marks
    `[degF]` with sentinel factor -1.0 ("sentinel: handled specially by
    caller") but the §6.2 comparison path computed
    (val * from_base_factor) / to_base_factor without offset handling,
    producing arithmetically wrong Boolean results.

    This test verifies the fix: cross-unit temperature comparisons must
    return empty (NULL) in both native and fallback, NOT a wrong Boolean.
    Per spec §6.2: "Attempting to operate on quantities with invalid units
    will result in empty (`{ }`)." + "Implementations are not required to
    fully support operations on units, but they must at least respect
    units, recognizing when units differ." UCUM defines temperature
    conversions with affine offsets (degF = degC * 9/5 + 32), not
    multiplicative factors.

    Same-unit passthrough (1 'Cel' < 2 'Cel') still works correctly via
    the existing fast-path that compares decimal text representations.
    Mirrors the FP-13 HISTORIAN equality regression
    `test_cross_unit_temperature_equality_returns_empty_in_both_backends_fp13_historian`.
    """
    resource = json.dumps({"resourceType": "Patient", "id": "p1"})
    cases = [
        # All cross-unit temperature comparison operators return empty
        ("1 'Cel' < 33.8 '[degF]'", None),
        ("1 'Cel' > 33.8 '[degF]'", None),
        ("1 'Cel' <= 33.8 '[degF]'", None),
        ("1 'Cel' >= 33.8 '[degF]'", None),
        # Reverse argument order — same defect, must also return empty
        ("33.8 '[degF]' < 1 'Cel'", None),
        ("33.8 '[degF]' > 1 'Cel'", None),
        ("100 '[degF]' < 37.8 'Cel'", None),
        ("100 '[degF]' > 37.8 'Cel'", None),
        # Kelvin is also an offset temperature unit
        ("1 'Cel' < 274.15 'K'", None),
        ("1 'Cel' > 274.15 'K'", None),
        ("274.15 'K' < 1 'Cel'", None),
        ("1 'Cel' < 1 'Cel'", False),    # same-unit sanity — strict less-than is False
        ("1 'Cel' <= 1 'Cel'", True),    # same-unit sanity — less-or-equal is True
        ("1 'Cel' > 0 'Cel'", True),     # same-unit sanity — different magnitudes
        ("1 'Cel' >= 1 'Cel'", True),    # same-unit sanity — equal magnitudes
    ]

    native = _connection()
    fallback = _python_fallback_connection(monkeypatch)
    try:
        for expression, expected in cases:
            query = "SELECT fhirpath_bool(?::JSON, ?), fhirpath_json(?::JSON, ?)"
            params = [resource, expression, resource, expression]
            cpp = native.execute(query, params).fetchone()
            py = fallback.execute(query, params).fetchone()
            assert cpp == py, (
                f"native vs fallback mismatch on {expression!r}: "
                f"native={cpp!r} vs fallback={py!r}"
            )
            assert cpp[0] is expected, (
                f"wrong result for {expression!r}: expected {expected}, "
                f"got native={cpp[0]!r}"
            )
    finally:
        native.close()
        fallback.close()


def test_decimal_arithmetic_feeding_comparison_preserves_adjacent_integers_fp14_explorer(
    monkeypatch,
) -> None:
    """FP-14 EXPLORER (2026-06-29): Native Decimal +/- arithmetic at
    evaluator.cpp ~7800+ used binary64 `double` and lost precision for
    integer-valued operands above 2^53. The §6.2 comparison path then
    compared two equal binary64 values and returned false instead of
    true.

    Reproducer: `(2).power(53) < (2).power(53) + 1` returned False in
    native vs True in fallback. Root cause: Decimal arithmetic path
    lacked the integer-text fast-path that Quantity arithmetic has
    (via normalizeQuantityArithmeticSourceText). The surgical fix
    added tryIntegerArithmeticText helper that mirrors the FP-11
    EXPLORER powerIntegerExactText pattern for +/-/* on integer-valued
    Decimal operands.
    """
    resource = json.dumps({"resourceType": "Observation"})
    cases = [
        # (expression, expected_bool_result)
        # Adjacent-integers above 2^53 boundary via arithmetic.
        ("(2).power(53) < (2).power(53) + 1", True),
        ("(2).power(53) > (2).power(53) - 1", True),  # arith result is 2^53-1 = 9007199254740991
        ("(2).power(53) <= (2).power(53) + 1", True),
        ("(2).power(53) >= (2).power(53) + 1", False),
        ("(2).power(63) < (2).power(63) + 1", True),
        ("(2).power(63) > (2).power(63) - 1", True),
        # The arithmetic result text itself
        ("(2).power(53) + 1", None),  # json output, no bool
        ("(2).power(63) + 1", None),
        # Direct Decimal-literal arithmetic at 2^53 boundary
        ("9007199254740992.0 + 1.0 = 9007199254740993.0", True),
        ("9007199254740992.0 + 1.0 < 9007199254740993.0", False),  # equal
        ("9007199254740992.0 + 1.0 > 9007199254740993.0", False),  # equal
        ("9007199254740992.0 + 2.0 < 9007199254740993.0", False),
        ("9007199254740992.0 + 2.0 > 9007199254740993.0", True),
        ("9007199254740993.0 - 1.0 < 9007199254740992.0", False),  # equal
        ("9007199254740993.0 - 2.0 < 9007199254740992.0", True),
        ("9007199254740993.0 - 1.0 > 9007199254740991.0", True),
        # Multiplication producing large Decimal
        ("(2).power(40) * 2 < (2).power(41) + 1", True),
        # Adjacent integers above 2^53 via subtraction
        ("(2).power(54) - 1 < (2).power(54)", True),
        ("(2).power(54) - 1 > (2).power(54) - 2", True),
        # Decimal-with-zero-fraction arithmetic
        ("9007199254740992.000 + 1.000 = 9007199254740993.0", True),
    ]
    native = _connection()
    fallback = _python_fallback_connection(monkeypatch)
    try:
        for expression, expected_bool in cases:
            query = "SELECT fhirpath_bool(?::JSON, ?), fhirpath_json(?::JSON, ?)"
            params = [resource, expression, resource, expression]
            cpp = native.execute(query, params).fetchone()
            py = fallback.execute(query, params).fetchone()
            assert cpp == py, (
                f"native vs fallback mismatch on {expression!r}: "
                f"native={cpp!r} vs fallback={py!r}"
            )
            if expected_bool is not None:
                assert cpp[0] is expected_bool, (
                    f"wrong bool result for {expression!r}: expected {expected_bool}, "
                    f"got native={cpp[0]!r}"
                )
    finally:
        native.close()
        fallback.close()
