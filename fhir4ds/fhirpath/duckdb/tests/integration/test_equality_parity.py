"""Parity tests for FHIRPath equality and equivalence operators."""

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


def test_equality_and_equivalence_match_cpp() -> None:
    resource = json.dumps(
        {
            "resourceType": "Observation",
            "a": 1,
            "b": 1.0,
            "c": 2,
            "s": "abc",
            "s2": "ABC",
            "empty": "",
            "arr": [1, 2],
        }
    )
    expressions = [
        "a = b",
        "a = c",
        "a != c",
        "a != b",
        "s = s",
        "s = s2",
        "s ~ s2",
        "s !~ s2",
        "empty ~ {}",
        "{} = {}",
        "{} != {}",
        "{} ~ {}",
        "{} !~ {}",
        "'abc' = 'abc'",
        "'abc' != 'ABC'",
        "'abc' ~ 'ABC'",
        "'abc' !~ 'ABC'",
        "@2015-02-04 = @2015-02-04",
        "@2015-02-04 = @2015-02",
        "@2015-02-04 ~ @2015-02-04T00:00:00",
        "1 'mg' = 1 'mg'",
        "1 'mg' = 0.001 'g'",
        "1 'mg' ~ 0.001 'g'",
        "1 'mg' != 2 'mg'",
        "arr = 1",
        "arr != 1",
        "arr ~ 1",
        "arr !~ 1",
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


def test_multi_item_equivalence_uses_item_equivalence_in_native_and_fallback(monkeypatch) -> None:
    resource = json.dumps(
        {
            "resourceType": "Observation",
            "stringsA": ["alpha beta", "Gamma"],
            "stringsB": [" gamma ", "ALPHA\tBETA"],
        }
    )
    expressions = {
        "(1 'mg' | 2 'mg') ~ (0.002 'g' | 0.001 'g')": True,
        "(1 'mg' | 2 'mg') !~ (0.002 'g' | 0.001 'g')": False,
        "(1 year | 1 second) ~ (1 'a' | 1 's')": True,
        "stringsA ~ stringsB": True,
        "stringsA !~ stringsB": False,
    }

    native = _connection()
    fallback = _python_fallback_connection(monkeypatch)
    try:
        for expression, expected in expressions.items():
            cpp = native.execute(
                "SELECT fhirpath(?::JSON, ?), fhirpath_bool(?::JSON, ?), fhirpath_json(?::JSON, ?)",
                [resource, expression, resource, expression, resource, expression],
            ).fetchone()
            py = fallback.execute(
                "SELECT fhirpath(?::JSON, ?), fhirpath_bool(?::JSON, ?), fhirpath_json(?::JSON, ?)",
                [resource, expression, resource, expression, resource, expression],
            ).fetchone()
            assert cpp == py
            assert cpp[1] is expected
    finally:
        native.close()
        fallback.close()


def test_calendar_duration_equality_shape_in_forced_python_fallback(monkeypatch) -> None:
    resource = "{}"
    expressions = {
        "1 year = 1 'a'": False,
        "1 year != 1 'a'": True,
        "1 day = 1 'd'": False,
        "1 day != 1 'd'": True,
        "1 second = 1 's'": True,
        "1 millisecond = 1 'ms'": True,
    }

    native = _connection()
    fallback = _python_fallback_connection(monkeypatch)
    try:
        for expression, expected in expressions.items():
            cpp = native.execute(
                "SELECT fhirpath(?::JSON, ?), fhirpath_bool(?::JSON, ?), fhirpath_json(?::JSON, ?)",
                [resource, expression, resource, expression, resource, expression],
            ).fetchone()
            py = fallback.execute(
                "SELECT fhirpath(?::JSON, ?), fhirpath_bool(?::JSON, ?), fhirpath_json(?::JSON, ?)",
                [resource, expression, resource, expression, resource, expression],
            ).fetchone()
            assert cpp == py
            assert cpp[1] is expected
    finally:
        native.close()
        fallback.close()


def test_multi_item_datetime_equality_uses_singleton_temporal_semantics(monkeypatch) -> None:
    resource = "{}"
    expressions = {
        "(@2012 | @2013) = (@2012 | @2014)": False,
        "(@2012 | @2013) != (@2012 | @2014)": True,
        "(@2017-11-05T01:30:00.0-04:00 | @2012) = (@2017-11-05T00:30:00.0-05:00 | @2012)": True,
        "(@2012-01-01T10:30:31.0 | @2012) = (@2012-01-01T10:30:31 | @2012)": True,
        "(@2012-01-01T10:30:31.1 | @2012) = (@2012-01-01T10:30:31 | @2012)": False,
    }

    native = _connection()
    fallback = _python_fallback_connection(monkeypatch)
    try:
        for expression, expected in expressions.items():
            cpp = native.execute(
                "SELECT fhirpath(?::JSON, ?), fhirpath_bool(?::JSON, ?), fhirpath_json(?::JSON, ?)",
                [resource, expression, resource, expression, resource, expression],
            ).fetchone()
            py = fallback.execute(
                "SELECT fhirpath(?::JSON, ?), fhirpath_bool(?::JSON, ?), fhirpath_json(?::JSON, ?)",
                [resource, expression, resource, expression, resource, expression],
            ).fetchone()
            assert cpp == py
            assert cpp[1] is expected
    finally:
        native.close()
        fallback.close()


def test_date_and_partial_datetime_are_not_same_type_in_native_and_fallback(monkeypatch) -> None:
    resource = "{}"
    expressions = {
        "@2012 = @2012T": None,
        "@2012 != @2012T": None,
        "@2012 ~ @2012T": False,
        "@2012 !~ @2012T": True,
        "@2012-01 = @2012-01T": None,
        "@2012-01 != @2012-01T": None,
        "@2012-01 ~ @2012-01T": False,
        "@2012-01 !~ @2012-01T": True,
        "(@2012 | @2013) = (@2012T | @2013T)": None,
        "(@2012 | @2013) != (@2012T | @2013T)": None,
        "(@2012 | @2013) ~ (@2012T | @2013T)": False,
        "(@2012 | @2013) !~ (@2012T | @2013T)": True,
    }

    native = _connection()
    fallback = _python_fallback_connection(monkeypatch)
    try:
        for expression, expected in expressions.items():
            cpp = native.execute(
                "SELECT fhirpath(?::JSON, ?), fhirpath_bool(?::JSON, ?), fhirpath_json(?::JSON, ?)",
                [resource, expression, resource, expression, resource, expression],
            ).fetchone()
            py = fallback.execute(
                "SELECT fhirpath(?::JSON, ?), fhirpath_bool(?::JSON, ?), fhirpath_json(?::JSON, ?)",
                [resource, expression, resource, expression, resource, expression],
            ).fetchone()
            assert cpp == py
            assert cpp[1] is expected
    finally:
        native.close()
        fallback.close()


def test_complex_equivalence_recurses_through_child_equivalence(monkeypatch) -> None:
    resource = json.dumps(
        {
            "resourceType": "Patient",
            "objA": {"given": ["Alpha  Beta"], "family": "SMITH"},
            "objB": {"family": "smith", "given": [" alpha beta "]},
            "arrA": [{"family": "SMITH"}, {"family": "Jones"}],
            "arrB": [{"family": "jones"}, {"family": "smith"}],
        }
    )
    expressions = {
        "objA ~ objB": True,
        "objA !~ objB": False,
        "arrA ~ arrB": True,
        "arrA !~ arrB": False,
    }

    native = _connection()
    fallback = _python_fallback_connection(monkeypatch)
    try:
        for expression, expected in expressions.items():
            cpp = native.execute(
                "SELECT fhirpath(?::JSON, ?), fhirpath_bool(?::JSON, ?), fhirpath_json(?::JSON, ?)",
                [resource, expression, resource, expression, resource, expression],
            ).fetchone()
            py = fallback.execute(
                "SELECT fhirpath(?::JSON, ?), fhirpath_bool(?::JSON, ?), fhirpath_json(?::JSON, ?)",
                [resource, expression, resource, expression, resource, expression],
            ).fetchone()
            assert cpp == py
            assert cpp[1] is expected
    finally:
        native.close()
        fallback.close()
