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
