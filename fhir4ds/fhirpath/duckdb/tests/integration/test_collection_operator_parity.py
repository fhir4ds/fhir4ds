"""Parity tests for FHIRPath collection operators."""

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


def test_collection_operators_match_cpp() -> None:
    resource = json.dumps(
        {
            "resourceType": "Observation",
            "a": [1, 2],
            "b": [2, 3],
            "one": 1,
            "objs": [{"id": "a"}, {"id": "b"}],
        }
    )
    expressions = [
        "a | b",
        "a.combine(b)",
        "a.combine(b, true)",
        "a.combine(b, false)",
        "a.union(b)",
        "one in a",
        "3 in a",
        "a contains one",
        "a contains 3",
        "{} in a",
        "a contains {}",
        "a in one",
        "one contains a",
        "objs.id | objs.id",
        "objs.id contains 'a'",
        "'a' in objs.id",
    ]

    con = _connection()
    try:
        for expression in expressions:
            cpp = con.execute(
                "SELECT fhirpath(?::JSON, ?), fhirpath_text(?::JSON, ?), fhirpath_json(?::JSON, ?), fhirpath_bool(?::JSON, ?), fhirpath_number(?::JSON, ?)",
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


def test_combine_preserve_order_optional_argument_matches_python_fallback(monkeypatch) -> None:
    resource = json.dumps(
        {
            "resourceType": "Observation",
            "a": ["zero", "one"],
            "b": ["two", "three"],
            "ints": [1],
        }
    )
    cases = {
        "a.combine(b, true)": (["zero", "one", "two", "three"], '["zero","one","two","three"]', True),
        "a.combine(b, false)": (["zero", "one", "two", "three"], '["zero","one","two","three"]', True),
        "a.combine(b, {})": ([], None, True),
        "a.combine(b, ints)": ([], None, True),
        "a.combine(b, 'true')": ([], None, False),
        "a.combine(b, 1)": ([], None, False),
        "a.combine(b, true | false)": ([], None, False),
        "a.combine(b, true, false)": ([], None, False),
    }

    cpp = _connection()
    py = _python_fallback_connection(monkeypatch)
    try:
        for expression, expected in cases.items():
            query = (
                "SELECT fhirpath(?::JSON, ?), fhirpath_json(?::JSON, ?), "
                "fhirpath_is_valid(?)"
            )
            params = [resource, expression, resource, expression, expression]
            assert cpp.execute(query, params).fetchone() == expected, expression
            assert py.execute(query, params).fetchone() == expected, expression
    finally:
        cpp.close()
        py.close()


def test_subsetting_integer_arguments_reject_non_integers_in_both_backends(monkeypatch) -> None:
    resource = json.dumps(
        {
            "resourceType": "Observation",
            "a": ["zero", "one", "two"],
        }
    )
    invalid_expressions = [
        "a['1']",
        "a[true]",
        "a[1.0]",
        "a[1.9]",
        "a.skip('1')",
        "a.skip(true)",
        "a.skip(1.9)",
        "a.take('1')",
        "a.take(true)",
        "a.take(1.9)",
    ]

    cpp = _connection()
    py = _python_fallback_connection(monkeypatch)
    try:
        assert cpp.execute("SELECT fhirpath(?::JSON, ?)", [resource, "a[1]"]).fetchone() == (
            ["one"],
        )
        assert py.execute("SELECT fhirpath(?::JSON, ?)", [resource, "a[1]"]).fetchone() == (
            ["one"],
        )
        for expression in invalid_expressions:
            assert cpp.execute(
                "SELECT fhirpath(?::JSON, ?), fhirpath_json(?::JSON, ?)",
                [resource, expression, resource, expression],
            ).fetchone() == ([], None), expression
            assert py.execute(
                "SELECT fhirpath(?::JSON, ?), fhirpath_json(?::JSON, ?)",
                [resource, expression, resource, expression],
            ).fetchone() == ([], None), expression
    finally:
        cpp.close()
        py.close()


def test_subsetting_and_combining_exact_arity_in_both_backends(monkeypatch) -> None:
    resource = json.dumps(
        {
            "resourceType": "Observation",
            "a": ["zero", "one", "two"],
            "b": ["two", "three"],
            "ints": [1],
        }
    )
    invalid_expressions = [
        "a.first(0)",
        "a.last(0)",
        "a.single(0)",
        "a.tail(0)",
        "a.skip()",
        "a.take()",
        "a.skip(1, 2)",
        "a.take(1, 2)",
        "a.combine()",
        "a.union()",
        "a.intersect()",
        "a.exclude()",
        "a.union(b, ints)",
        "a.intersect(b, ints)",
        "a.exclude(b, ints)",
    ]

    cpp = _connection()
    py = _python_fallback_connection(monkeypatch)
    try:
        for expression in invalid_expressions:
            assert cpp.execute(
                "SELECT fhirpath(?::JSON, ?), fhirpath_json(?::JSON, ?), fhirpath_is_valid(?)",
                [resource, expression, resource, expression, expression],
            ).fetchone() == ([], None, False), expression
            assert py.execute(
                "SELECT fhirpath(?::JSON, ?), fhirpath_json(?::JSON, ?), fhirpath_is_valid(?)",
                [resource, expression, resource, expression, expression],
            ).fetchone() == ([], None, False), expression
    finally:
        cpp.close()
        py.close()


def test_subsetting_empty_count_arguments_are_valid_in_both_backends(monkeypatch) -> None:
    resource = json.dumps(
        {
            "resourceType": "Observation",
            "a": ["zero", "one", "two"],
        }
    )
    expressions = [
        "a.skip({})",
        "a.take({})",
    ]

    cpp = _connection()
    py = _python_fallback_connection(monkeypatch)
    try:
        for expression in expressions:
            assert cpp.execute(
                "SELECT fhirpath(?::JSON, ?), fhirpath_json(?::JSON, ?), fhirpath_is_valid(?)",
                [resource, expression, resource, expression, expression],
            ).fetchone() == ([], None, True), expression
            assert py.execute(
                "SELECT fhirpath(?::JSON, ?), fhirpath_json(?::JSON, ?), fhirpath_is_valid(?)",
                [resource, expression, resource, expression, expression],
            ).fetchone() == ([], None, True), expression
    finally:
        cpp.close()
        py.close()


def test_membership_singleton_errors_are_resilient_in_public_duckdb_udfs(monkeypatch) -> None:
    resource = json.dumps(
        {
            "resourceType": "Observation",
            "a": [1, 2],
            "one": 1,
        }
    )
    invalid_expressions = [
        "a in one",
        "one contains a",
    ]

    cpp = _connection()
    py = _python_fallback_connection(monkeypatch)
    try:
        for expression in invalid_expressions:
            assert cpp.execute(
                "SELECT fhirpath(?::JSON, ?), fhirpath_json(?::JSON, ?), fhirpath_bool(?::JSON, ?)",
                [resource, expression, resource, expression, resource, expression],
            ).fetchone() == ([], None, None)
            assert py.execute(
                "SELECT fhirpath(?::JSON, ?), fhirpath_json(?::JSON, ?), fhirpath_bool(?::JSON, ?)",
                [resource, expression, resource, expression, resource, expression],
            ).fetchone() == ([], None, None)
    finally:
        cpp.close()
        py.close()


def test_membership_literal_union_singleton_errors_in_both_validators(monkeypatch) -> None:
    resource = json.dumps(
        {
            "resourceType": "Observation",
            "arr": [1, 2],
            "dates": ["2012", "2013"],
        }
    )
    invalid_expressions = [
        "(1 | 2) in arr",
        "arr contains (1 | 2)",
        "(@2012 | @2013) in dates",
        "dates contains ('2012' | '2013')",
    ]
    valid_expressions = [
        "(1 | 1) in arr",
        "(1 | 1.0) in arr",
        "(1 | {}) in arr",
        "{} in arr",
        "arr contains (1 | 1)",
        "arr contains (1 | 1.0)",
        "arr contains (1 | {})",
        "arr contains {}",
    ]

    cpp = _connection()
    py = _python_fallback_connection(monkeypatch)
    try:
        for expression in invalid_expressions:
            assert cpp.execute(
                "SELECT fhirpath(?::JSON, ?), fhirpath_json(?::JSON, ?), fhirpath_bool(?::JSON, ?), fhirpath_is_valid(?)",
                [resource, expression, resource, expression, resource, expression, expression],
            ).fetchone() == ([], None, None, False), expression
            assert py.execute(
                "SELECT fhirpath(?::JSON, ?), fhirpath_json(?::JSON, ?), fhirpath_bool(?::JSON, ?), fhirpath_is_valid(?)",
                [resource, expression, resource, expression, resource, expression, expression],
            ).fetchone() == ([], None, None, False), expression
        for expression in valid_expressions:
            assert cpp.execute("SELECT fhirpath_is_valid(?)", [expression]).fetchone() == (
                True,
            ), expression
            assert py.execute("SELECT fhirpath_is_valid(?)", [expression]).fetchone() == (
                True,
            ), expression
    finally:
        cpp.close()
        py.close()


def test_intersect_uses_fhirpath_equality_for_quantities_in_both_backends(monkeypatch) -> None:
    resource = json.dumps({"resourceType": "Observation"})
    expression = "(1 'cm').intersect(10 'mm').count()"

    cpp = _connection()
    py = _python_fallback_connection(monkeypatch)
    try:
        assert cpp.execute(
            "SELECT fhirpath(?::JSON, ?), fhirpath_json(?::JSON, ?)",
            [resource, expression, resource, expression],
        ).fetchone() == (["1"], "[1]")
        assert py.execute(
            "SELECT fhirpath(?::JSON, ?), fhirpath_json(?::JSON, ?)",
            [resource, expression, resource, expression],
        ).fetchone() == (["1"], "[1]")
    finally:
        cpp.close()
        py.close()


def test_set_operators_use_numeric_equality_for_json_ints_and_reals(monkeypatch) -> None:
    resource = json.dumps(
        {
            "resourceType": "Observation",
            "int": [1],
            "real": [1.0],
        }
    )
    expectations = {
        "int = real": (["true"], "[true]"),
        "int.union(real).count()": (["1"], "[1]"),
        "int.intersect(real).count()": (["1"], "[1]"),
        "int.exclude(real).count()": (["0"], "[0]"),
    }

    cpp = _connection()
    py = _python_fallback_connection(monkeypatch)
    try:
        for expression, expected in expectations.items():
            assert (
                cpp.execute(
                    "SELECT fhirpath(?::JSON, ?), fhirpath_json(?::JSON, ?)",
                    [resource, expression, resource, expression],
                ).fetchone()
                == expected
            )
            assert (
                py.execute(
                    "SELECT fhirpath(?::JSON, ?), fhirpath_json(?::JSON, ?)",
                    [resource, expression, resource, expression],
                ).fetchone()
                == expected
            )
    finally:
        cpp.close()
        py.close()


def test_membership_and_contains_use_temporal_equality_in_both_backends(monkeypatch) -> None:
    resource = json.dumps({"resourceType": "Observation"})
    expectations = {
        "@2012 in @2012": (["true"], "[true]", True),
        "@2012 contains @2012": (["true"], "[true]", True),
        "@T10:30:31.0 in @T10:30:31": (["true"], "[true]", True),
        "@T10:30:31 contains @T10:30:31.0": (["true"], "[true]", True),
        "@2012-01-01T10:30:00+00:00 in @2012-01-01T10:30:00Z": (["true"], "[true]", True),
        "@2012-01-01T10:30:00Z contains @2012-01-01T10:30:00+00:00": (["true"], "[true]", True),
        "@2012 in (@2012 | @2013)": (["true"], "[true]", True),
        "(@2012 | @2013) contains @2012": (["true"], "[true]", True),
    }

    cpp = _connection()
    py = _python_fallback_connection(monkeypatch)
    try:
        for expression, expected in expectations.items():
            assert (
                cpp.execute(
                    "SELECT fhirpath(?::JSON, ?), fhirpath_json(?::JSON, ?), fhirpath_bool(?::JSON, ?)",
                    [resource, expression, resource, expression, resource, expression],
                ).fetchone()
                == expected
            )
            assert (
                py.execute(
                    "SELECT fhirpath(?::JSON, ?), fhirpath_json(?::JSON, ?), fhirpath_bool(?::JSON, ?)",
                    [resource, expression, resource, expression, resource, expression],
                ).fetchone()
                == expected
            )
    finally:
        cpp.close()
        py.close()


def test_collection_operators_use_quantity_equality_for_fhir_quantity_paths(monkeypatch) -> None:
    resource = json.dumps(
        {
            "resourceType": "Observation",
            "valueQuantity": {
                "value": 1,
                "system": "http://unitsofmeasure.org",
                "code": "cm",
            },
            "component": [
                {
                    "valueQuantity": {
                        "value": 10,
                        "system": "http://unitsofmeasure.org",
                        "code": "mm",
                    }
                }
            ],
        }
    )
    expectations = {
        "value = component.value": (["true"], "[true]", True),
        "value in component.value": (["true"], "[true]", True),
        "component.value contains value": (["true"], "[true]", True),
        "value.union(component.value).count()": (["1"], "[1]", True),
        "(value | component.value).count()": (["1"], "[1]", True),
        "1 'cm' in component.value": (["true"], "[true]", True),
        "component.value contains 1 'cm'": (["true"], "[true]", True),
        "component.value.union(1 'cm').count()": (["1"], "[1]", True),
    }

    cpp = _connection()
    py = _python_fallback_connection(monkeypatch)
    try:
        for expression, expected in expectations.items():
            assert (
                cpp.execute(
                    "SELECT fhirpath(?::JSON, ?), fhirpath_json(?::JSON, ?), fhirpath_bool(?::JSON, ?)",
                    [resource, expression, resource, expression, resource, expression],
                ).fetchone()
                == expected
            )
            assert (
                py.execute(
                    "SELECT fhirpath(?::JSON, ?), fhirpath_json(?::JSON, ?), fhirpath_bool(?::JSON, ?)",
                    [resource, expression, resource, expression, resource, expression],
                ).fetchone()
                == expected
            )
    finally:
        cpp.close()
        py.close()
