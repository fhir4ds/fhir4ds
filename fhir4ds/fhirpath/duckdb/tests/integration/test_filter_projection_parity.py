"""Parity tests for filtering/projection FHIRPath functions in DuckDB UDFs."""

from __future__ import annotations

import json

import duckdb
import pytest

from fhir4ds.fhirpath.duckdb import register_fhirpath
from fhir4ds.fhirpath.duckdb.udf import fhirpath_json_udf, fhirpath_scalar, fhirpath_text_udf


OBSERVATION = json.dumps(
    {
        "resourceType": "Observation",
        "id": "o",
        "valueInteger": 5,
    }
)

QUESTIONNAIRE = json.dumps(
    {
        "resourceType": "Questionnaire",
        "id": "q",
        "item": [
            {"linkId": "a", "item": [{"linkId": "a.1"}]},
            {"linkId": "b"},
        ],
    }
)

BUNDLE = json.dumps(
    {
        "resourceType": "Bundle",
        "entry": [
            {"resource": {"resourceType": "Patient", "id": "p1"}},
            {"resource": {"resourceType": "Observation", "id": "o1", "valueInteger": 7}},
        ],
    }
)

DUPLICATE_CHILDREN = json.dumps(
    {
        "resourceType": "Questionnaire",
        "item": [
            {
                "linkId": "root",
                "item": [
                    {"linkId": "same"},
                    {"linkId": "same"},
                ],
            }
        ],
    }
)


def _connection() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect(config={"allow_unsigned_extensions": True})
    register_fhirpath(con)
    return con


def _python_fallback_connection(monkeypatch: pytest.MonkeyPatch) -> duckdb.DuckDBPyConnection:
    monkeypatch.setattr(duckdb, "__version__", "0.0.0-forced-python-fallback")
    con = duckdb.connect(config={"allow_unsigned_extensions": True})
    assert register_fhirpath(con) is False
    return con


def _json_result(con: duckdb.DuckDBPyConnection, resource: str, expression: str):
    return con.execute(
        "SELECT fhirpath(?::JSON, ?), fhirpath_json(?::JSON, ?)",
        [resource, expression, resource, expression],
    ).fetchone()


def test_choice_type_oftype_matches_cpp() -> None:
    expression = "value.ofType(Integer)"

    con = _connection()
    try:
        cpp = con.execute(
            "SELECT fhirpath(?::JSON, ?), fhirpath_text(?::JSON, ?), fhirpath_json(?::JSON, ?)",
            [OBSERVATION, expression, OBSERVATION, expression, OBSERVATION, expression],
        ).fetchone()
        py = (
            fhirpath_scalar(OBSERVATION, expression),
            fhirpath_text_udf(OBSERVATION, expression),
            fhirpath_json_udf(OBSERVATION, expression),
        )
        assert cpp == py
    finally:
        con.close()


def test_oftype_matches_fhir_supertypes_in_native_and_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    cases = {
        "entry.resource.ofType(Resource).id": (["p1", "o1"], '["p1","o1"]'),
        "entry.resource.ofType(DomainResource).id": (["p1", "o1"], '["p1","o1"]'),
        "entry.resource.ofType(Patient).id": (["p1"], '["p1"]'),
    }

    native = _connection()
    fallback = _python_fallback_connection(monkeypatch)
    try:
        for expression, expected in cases.items():
            assert _json_result(native, BUNDLE, expression) == expected
            assert _json_result(fallback, BUNDLE, expression) == expected
    finally:
        native.close()
        fallback.close()


def test_oftype_missing_type_argument_invalid_in_native_and_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    expression = "entry.resource.ofType()"

    native = _connection()
    fallback = _python_fallback_connection(monkeypatch)
    try:
        assert native.execute("SELECT fhirpath_is_valid(?)", [expression]).fetchone() == (False,)
        assert fallback.execute("SELECT fhirpath_is_valid(?)", [expression]).fetchone() == (False,)
        assert _json_result(native, BUNDLE, expression) == ([], None)
        assert _json_result(fallback, BUNDLE, expression) == ([], None)
    finally:
        native.close()
        fallback.close()


def test_filter_projection_invalid_arity_matches_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    expressions = [
        "Patient.where()",
        "entry.where()",
        "entry.where(true, false).resource.id",
        "entry.select()",
        "entry.select(resource, fullUrl).count()",
        "entry.repeat()",
        "Patient.ofType('Patient').id",
    ]

    native = _connection()
    fallback = _python_fallback_connection(monkeypatch)
    try:
        for expression in expressions:
            assert native.execute("SELECT fhirpath_is_valid(?)", [expression]).fetchone() == (False,)
            assert fallback.execute("SELECT fhirpath_is_valid(?)", [expression]).fetchone() == (False,)
            assert _json_result(native, BUNDLE, expression) == ([], None)
            assert _json_result(fallback, BUNDLE, expression) == ([], None)
    finally:
        native.close()
        fallback.close()


def test_nested_choice_oftype_matches_native_and_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    expression = "entry.resource.ofType(Observation).value.ofType(Integer)"

    native = _connection()
    fallback = _python_fallback_connection(monkeypatch)
    try:
        expected = (["7"], "[7]")
        assert _json_result(native, BUNDLE, expression) == expected
        assert _json_result(fallback, BUNDLE, expression) == expected
    finally:
        native.close()
        fallback.close()


def test_index_context_is_scoped_for_filter_projection_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    cases = {
        "item.select(linkId) | $index": (["a", "b"], '["a","b"]'),
        "item.where($index = 0).linkId | $index": (["a"], '["a"]'),
        "item.repeat(iif($index = 0, item, {})).linkId": (["a.1"], '["a.1"]'),
    }

    native = _connection()
    fallback = _python_fallback_connection(monkeypatch)
    try:
        for expression, expected in cases.items():
            assert _json_result(native, QUESTIONNAIRE, expression) == expected
            assert _json_result(fallback, QUESTIONNAIRE, expression) == expected
    finally:
        native.close()
        fallback.close()


def test_where_define_variable_scope_does_not_leak_in_native() -> None:
    resource = json.dumps({"resourceType": "Patient", "a": [1, 2]})
    expression = "a.where(defineVariable('leak', $this).exists()).select(%leak)"

    native = _connection()
    try:
        assert _json_result(native, resource, expression) == ([], None)
    finally:
        native.close()


def test_repeat_returns_only_new_projection_results_in_native_and_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    cases = [
        (DUPLICATE_CHILDREN, "item.repeat(item).linkId", (["same"], '["same"]')),
        (DUPLICATE_CHILDREN, "item.repeat(item).isDistinct()", (["true"], "[true]")),
        (DUPLICATE_CHILDREN, "item.repeat($this).linkId", (["root"], '["root"]')),
        ("{}", "1.repeat(iif($this < 3, $this + 1, {}))", (["2", "3"], "[2,3]")),
        ("{}", "'a'.repeat($this)", (["a"], '["a"]')),
    ]

    native = _connection()
    fallback = _python_fallback_connection(monkeypatch)
    try:
        for resource, expression, expected in cases:
            assert _json_result(native, resource, expression) == expected
            assert _json_result(fallback, resource, expression) == expected
    finally:
        native.close()
        fallback.close()
