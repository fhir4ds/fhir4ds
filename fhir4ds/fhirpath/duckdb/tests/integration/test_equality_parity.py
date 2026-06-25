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


def test_primitive_root_this_equality_matches_cpp(monkeypatch) -> None:
    """Compound $this predicates over primitive JSON roots stay backend-aligned."""
    query = "SELECT fhirpath_json(?::JSON, ?), fhirpath_bool(?::JSON, ?)"
    params = ['"keep"', "$this = 'keep'", '"keep"', "$this = 'keep'"]

    native = _connection()
    fallback = _python_fallback_connection(monkeypatch)
    try:
        assert native.execute(query, params).fetchone() == ("[true]", True)
        assert fallback.execute(query, params).fetchone() == ("[true]", True)
    finally:
        native.close()
        fallback.close()


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
        "23 = 23 '1'",
        "23 != 23 '1'",
        "23 ~ 23 '1'",
        "23 !~ 23 '1'",
        "23 = 24 '1'",
        "23 != 24 '1'",
        "23 ~ 23.4 '1'",
        "23 !~ 23.4 '1'",
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
        "1 'cm' ~ 1 's'",
        "1 'cm' !~ 1 's'",
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
            "stringsB": ["GAMMA", "ALPHA\tBETA"],
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


def test_string_equivalence_normalizes_case_and_whitespace_without_collapse(monkeypatch) -> None:
    resource = json.dumps(
        {
            "resourceType": "Observation",
            "nbspLeft": "alpha\u00a0beta",
            "spaceRight": "ALPHA beta",
        }
    )
    expressions = {
        "'a  b' ~ 'a b'": False,
        "'a  b' !~ 'a b'": True,
        "' a' ~ 'a'": False,
        "' a' !~ 'a'": True,
        "'a\tb' ~ 'A b'": True,
        "nbspLeft ~ spaceRight": True,
        "'É' ~ 'é'": True,
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
        "1 year = 1 'a'": None,
        "1 year != 1 'a'": None,
        "1 month = 1 'mo'": None,
        "1 month != 1 'mo'": None,
        "1 year ~ 1 'a'": True,
        "1 year !~ 1 'a'": False,
        "1 'cm' ~ 1 's'": None,
        "1 'cm' !~ 1 's'": None,
        "1 year = 12 months": True,
        "1 'a' = 12 'mo'": True,
        "1 week = 1 'wk'": True,
        "7 days = 1 'wk'": True,
        "1 day = 1 'd'": True,
        "1 day != 1 'd'": False,
        "1 hour = 60 'min'": True,
        "1 minute = 60 's'": True,
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
        "(@2012 | @2013) = (@2012-01 | @2013)": None,
        "(@2012 | @2013) != (@2012-01 | @2013)": None,
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
            "objA": {"given": ["Alpha\tBeta"], "family": "SMITH"},
            "objB": {"family": "smith", "given": ["alpha beta"]},
            "arrA": [{"family": "SMITH"}, {"family": "Jones"}],
            "arrB": [{"family": "jones"}, {"family": "smith"}],
            "nestedA": {"coding": [{"code": "A"}, {"code": "B"}]},
            "nestedB": {"coding": [{"code": "b"}, {"code": "a"}]},
        }
    )
    expressions = {
        "objA ~ objB": True,
        "objA !~ objB": False,
        "arrA ~ arrB": True,
        "arrA !~ arrB": False,
        "nestedA ~ nestedB": True,
        "nestedA !~ nestedB": False,
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


def test_resource_quantity_multi_item_equivalence_uses_quantity_semantics(monkeypatch) -> None:
    resource = json.dumps(
        {
            "resourceType": "Observation",
            "valueQuantity": {
                "value": 185,
                "unit": "lbs",
                "code": "[lb_av]",
                "system": "http://unitsofmeasure.org",
            },
            "component": [
                {"valueQuantity": {"value": 1, "unit": "cm", "code": "cm"}},
                {"valueQuantity": {"value": 2, "unit": "cm", "code": "cm"}},
            ],
            "referenceRange": [
                {
                    "high": {"value": 0.02, "unit": "m", "code": "m"},
                },
                {
                    "high": {"value": 10, "unit": "mm", "code": "mm"},
                },
            ],
        }
    )

    native = _connection()
    fallback = _python_fallback_connection(monkeypatch)
    try:
        for expression, expected in {
            "Observation.value = 185 '[lb_av]'": True,
            "Observation.value != 185 'kg'": True,
            "Observation.value ~ 185 '[lb_av]'": True,
            "Observation.value ~ 83.9 'kg'": True,
            "Observation.value !~ 83.9 'kg'": False,
            "Observation.value ~ 185 'kg'": False,
            "Observation.value !~ 185 'kg'": True,
            "component.value ~ referenceRange.high": True,
            "component.value !~ referenceRange.high": False,
            "component.value = referenceRange.high": False,
            "(1 'cm' | 2 'cm') = (1 'g' | 2 'cm')": None,
            "(1 'cm' | 2 'cm') != (1 'g' | 2 'cm')": None,
        }.items():
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


def test_numeric_values_compare_with_unit_one_quantities(monkeypatch) -> None:
    resource = json.dumps(
        {
            "resourceType": "Observation",
            "component": [
                {
                    "valueQuantity": {
                        "value": 23,
                        "unit": "1",
                        "code": "1",
                        "system": "http://unitsofmeasure.org",
                    }
                },
                {
                    "valueQuantity": {
                        "value": 24,
                        "unit": "1",
                        "code": "1",
                        "system": "http://unitsofmeasure.org",
                    }
                },
            ],
        }
    )
    expressions = {
        "23 = 23 '1'": True,
        "23 != 23 '1'": False,
        "23 ~ 23 '1'": True,
        "23 !~ 23 '1'": False,
        "23 = 24 '1'": False,
        "23 != 24 '1'": True,
        "23 ~ 23.4 '1'": True,
        "23 !~ 23.4 '1'": False,
        "23 = 23 'cm'": None,
        "23 != 23 'cm'": None,
        "component[0].value = 23": True,
        "component[0].value != 23": False,
        "component[0].value ~ 23": True,
        "component[0].value !~ 23": False,
        "component.value = (23 | 24)": True,
        "component.value != (23 | 24)": False,
        "component.value ~ (24 | 23)": True,
        "component.value !~ (24 | 23)": False,
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


def test_large_json_numbers_compare_exactly_in_native_and_fallback(monkeypatch) -> None:
    resource = json.dumps(
        {
            "resourceType": "Observation",
            "a": 9007199254740992,
            "b": 9007199254740993,
            "objA": {"value": 9007199254740992},
            "objB": {"value": 9007199254740993},
            "arrA": [9007199254740992, 9007199254740994],
            "arrB": [9007199254740992, 9007199254740995],
        }
    )
    expressions = {
        "a = b": False,
        "a != b": True,
        "a ~ b": False,
        "a !~ b": True,
        "objA = objB": False,
        "objA != objB": True,
        "objA ~ objB": False,
        "objA !~ objB": True,
        "arrA = arrB": False,
        "arrA != arrB": True,
        "arrA ~ arrB": False,
        "arrA !~ arrB": True,
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


def test_decimal_equivalence_uses_half_up_tie_rounding(monkeypatch) -> None:
    native = _connection()
    fallback = _python_fallback_connection(monkeypatch)
    try:
        for expression, expected in {
            "1.25 ~ 1.2": False,
            "1.24 ~ 1.2": True,
            "(-1.25) ~ (-1.2)": False,
            "(-1.24) ~ (-1.2)": True,
        }.items():
            cpp = native.execute(
                "SELECT fhirpath(?::JSON, ?), fhirpath_bool(?::JSON, ?), fhirpath_json(?::JSON, ?)",
                ["{}", expression, "{}", expression, "{}", expression],
            ).fetchone()
            py = fallback.execute(
                "SELECT fhirpath(?::JSON, ?), fhirpath_bool(?::JSON, ?), fhirpath_json(?::JSON, ?)",
                ["{}", expression, "{}", expression, "{}", expression],
            ).fetchone()
            assert cpp == py
            assert cpp[1] is expected
    finally:
        native.close()
        fallback.close()


def test_complex_equality_recurses_into_decimal_and_quantity_children(monkeypatch) -> None:
    resource = json.dumps(
        {
            "resourceType": "Observation",
            "decObjA": {"value": 1.24},
            "decObjB": {"value": 1.2},
            "decObjTieA": {"value": 1.25},
            "decObjTieB": {"value": 1.2},
            "rangeA": {
                "high": {
                    "value": 1,
                    "unit": "cm",
                    "code": "cm",
                    "system": "http://unitsofmeasure.org",
                }
            },
            "rangeB": {
                "high": {
                    "value": 10,
                    "unit": "mm",
                    "code": "mm",
                    "system": "http://unitsofmeasure.org",
                }
            },
            "rangeBad": {
                "high": {
                    "value": 1,
                    "unit": "g",
                    "code": "g",
                    "system": "http://unitsofmeasure.org",
                }
            },
            "nestedA": {
                "coding": [{"code": "Alpha\tBeta", "rank": 1.24}, {"code": "Z", "rank": 2}],
                "dose": {
                    "value": 1,
                    "unit": "cm",
                    "code": "cm",
                    "system": "http://unitsofmeasure.org",
                },
            },
            "nestedB": {
                "dose": {
                    "value": 10,
                    "unit": "mm",
                    "code": "mm",
                    "system": "http://unitsofmeasure.org",
                },
                "coding": [{"rank": 2.0, "code": "z"}, {"rank": 1.2, "code": "alpha beta"}],
            },
        }
    )
    expressions = {
        "decObjA ~ decObjB": True,
        "decObjTieA ~ decObjTieB": False,
        "rangeA = rangeB": True,
        "rangeA != rangeB": False,
        "rangeA ~ rangeB": True,
        "rangeA !~ rangeB": False,
        "rangeA = rangeBad": None,
        "rangeA != rangeBad": None,
        "rangeA ~ rangeBad": None,
        "rangeA !~ rangeBad": None,
        "nestedA ~ nestedB": True,
        "nestedA !~ nestedB": False,
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
