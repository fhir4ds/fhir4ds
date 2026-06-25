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
