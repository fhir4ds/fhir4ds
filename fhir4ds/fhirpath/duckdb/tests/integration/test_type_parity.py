"""Parity tests for FHIRPath type operators."""

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


def _connection() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect(config={"allow_unsigned_extensions": True})
    register_fhirpath(con)
    return con


def _python_fallback_connection(monkeypatch) -> duckdb.DuckDBPyConnection:
    monkeypatch.setattr(duckdb, "__version__", "0.0.0-forced-python-fallback")
    con = duckdb.connect(config={"allow_unsigned_extensions": True})
    assert register_fhirpath(con) is False
    return con


def _surfaces(con: duckdb.DuckDBPyConnection, resource: str, expression: str):
    return con.execute(
        "SELECT fhirpath(?::JSON, ?), fhirpath_text(?::JSON, ?), fhirpath_json(?::JSON, ?), fhirpath_bool(?::JSON, ?), fhirpath_is_valid(?)",
        [
            resource,
            expression,
            resource,
            expression,
            resource,
            expression,
            resource,
            expression,
            expression,
        ],
    ).fetchone()


def test_type_operators_match_cpp() -> None:
    resource = json.dumps(
        {
            "resourceType": "Observation",
            "i": 1,
            "d": 1.5,
            "s": "abc",
            "b": True,
            "date": "2015-02-04",
            "dt": "2015-02-04T10:00:00",
            "arr": [1, 2],
        }
    )
    expressions = [
        "i is Integer",
        "d is Decimal",
        "s is String",
        "b is Boolean",
        "i is Decimal",
        "i.is(Integer)",
        "d.is(Decimal)",
        "s.is(String)",
        "b.is(Boolean)",
        "i.as(Integer)",
        "d.as(Decimal)",
        "s.as(String)",
        "b.as(Boolean)",
        "s.as(Integer)",
        "arr.is(Integer)",
        "arr.as(Integer)",
        "date.toDate() is Date",
        "dt.toDateTime() is DateTime",
        "5 'mg' is Quantity",
        "5 'mg'.is(Quantity)",
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


def test_type_operator_supertypes_match_python_fallback(monkeypatch) -> None:
    resource = json.dumps(
        {
            "resourceType": "Patient",
            "name": [{"family": "Smith", "given": ["John"]}],
            "gender": "male",
        }
    )
    expressions = [
        "Patient is Resource",
        "Patient as Resource",
        "Patient is DomainResource",
        "Patient as DomainResource",
        "name.first() is Element",
        "name.first() as Element",
        "name.first() is HumanName",
        "name.first() as HumanName",
        "gender is string",
        "gender as string",
        "gender is code",
        "gender as code",
    ]

    native = _connection()
    fallback = _python_fallback_connection(monkeypatch)
    try:
        for expression in expressions:
            assert _surfaces(native, resource, expression) == _surfaces(
                fallback, resource, expression
            )
    finally:
        native.close()
        fallback.close()


def test_type_specifier_errors_match_python_fallback(monkeypatch) -> None:
    resource = json.dumps({"resourceType": "Patient", "arr": [1, 2]})
    expressions = [
        "1 is NoSuchType",
        "1.is(NoSuchType)",
        "1 as NoSuchType",
        "1.as(NoSuchType)",
        "arr is Integer",
        "arr.is(Integer)",
        "arr as Integer",
        "arr.as(Integer)",
        "1.is()",
        "1.as()",
    ]

    native = _connection()
    fallback = _python_fallback_connection(monkeypatch)
    try:
        for expression in expressions:
            assert _surfaces(native, resource, expression) == _surfaces(
                fallback, resource, expression
            )
    finally:
        native.close()
        fallback.close()


def test_qualified_type_specifiers_resolve_within_declared_model(monkeypatch) -> None:
    resource = json.dumps({"resourceType": "Patient", "active": True})
    expressions = [
        "active is FHIR.Boolean",
        "active.is(FHIR.Boolean)",
        "active as FHIR.Boolean",
        "active.as(FHIR.Boolean)",
        "1 is FHIR.Integer",
        "1.is(FHIR.Integer)",
        "1 as FHIR.Integer",
        "1.as(FHIR.Integer)",
    ]

    native = _connection()
    fallback = _python_fallback_connection(monkeypatch)
    try:
        for expression in expressions:
            assert _surfaces(native, resource, expression) == _surfaces(
                fallback, resource, expression
            )
            assert fhirpath_is_valid_udf(expression) is False
    finally:
        native.close()
        fallback.close()


def test_official_r4_system_qualified_fhir_type_remains_non_matching(monkeypatch) -> None:
    resource = json.dumps({"resourceType": "Patient", "active": True})
    expressions = [
        "Patient.is(System.Patient).not()",
        "Patient is System.Patient",
        "Patient as System.Patient",
    ]

    native = _connection()
    fallback = _python_fallback_connection(monkeypatch)
    try:
        for expression in expressions:
            assert _surfaces(native, resource, expression) == _surfaces(
                fallback, resource, expression
            )
            assert fhirpath_is_valid_udf(expression) is True
    finally:
        native.close()
        fallback.close()


def test_malformed_type_expressions_are_invalid_in_python_fallback() -> None:
    for expression in ["1 is", "1 as", "1.is()", "1.as()", "1 is NoSuchType"]:
        assert fhirpath_is_valid_udf(expression) is False


def test_unknown_function_is_invalid_in_native_and_fallback(monkeypatch) -> None:
    native = _connection()
    fallback = _python_fallback_connection(monkeypatch)
    try:
        assert native.execute("SELECT fhirpath_is_valid('foo()')").fetchone() == (False,)
        assert fallback.execute("SELECT fhirpath_is_valid('foo()')").fetchone() == (False,)
        assert fhirpath_is_valid_udf("foo()") is False
        assert native.execute("SELECT fhirpath_is_valid('1.lowBoundary()')").fetchone() == (True,)
        assert fallback.execute("SELECT fhirpath_is_valid('1.lowBoundary()')").fetchone() == (True,)
        assert fhirpath_is_valid_udf("1.lowBoundary()") is True
    finally:
        native.close()
        fallback.close()


def test_sql_on_fhir_key_functions_match_python_fallback(monkeypatch) -> None:
    resource = json.dumps(
        {
            "resourceType": "Observation",
            "id": "obs-1",
            "subject": {"reference": "Patient/pat-1"},
        }
    )
    expressions = [
        "getResourceKey()",
        "subject.getReferenceKey()",
        "subject.getReferenceKey(Patient)",
        "subject.getReferenceKey(Observation)",
        "subject.getReferenceKey(NoSuchType)",
    ]

    native = _connection()
    fallback = _python_fallback_connection(monkeypatch)
    try:
        for expression in expressions:
            assert _surfaces(native, resource, expression) == _surfaces(
                fallback, resource, expression
            )
            expected_valid = expression != "subject.getReferenceKey(NoSuchType)"
            assert native.execute("SELECT fhirpath_is_valid(?)", [expression]).fetchone() == (
                expected_valid,
            )
            assert fallback.execute("SELECT fhirpath_is_valid(?)", [expression]).fetchone() == (
                expected_valid,
            )
    finally:
        native.close()
        fallback.close()


def test_choice_type_assertion_public_surfaces_match_fallback(monkeypatch) -> None:
    resource = json.dumps({"resourceType": "Observation", "valueInteger": 5})
    expressions = [
        "value.is(Integer)",
        "Observation.value.is(Integer)",
        "value.as(Integer)",
    ]
    native = _connection()
    fallback = _python_fallback_connection(monkeypatch)
    try:
        for expression in expressions:
            assert _surfaces(native, resource, expression) == _surfaces(
                fallback, resource, expression
            )
    finally:
        native.close()
        fallback.close()
