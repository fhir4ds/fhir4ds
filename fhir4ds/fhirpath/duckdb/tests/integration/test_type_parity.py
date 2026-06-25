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


def test_empty_input_is_returns_false_as_returns_empty(monkeypatch) -> None:
    # FHIRPath §5.1: empty-collection propagation requires is() to return
    # the empty collection when the input is empty, regardless of the type
    # argument. Native C++ fn_isType and Python is_fn must agree.
    resource = json.dumps({"resourceType": "Patient"})
    expectations = {
        "missing is Integer": ([], None, None, True),
        "missing.is(Integer)": ([], None, None, True),
        "missing as Integer": ([], None, None, True),
        "missing.as(Integer)": ([], None, None, True),
    }

    native = _connection()
    fallback = _python_fallback_connection(monkeypatch)
    try:
        for expression, expected in expectations.items():
            native_row = native.execute(
                "SELECT fhirpath(?::JSON, ?), fhirpath_text(?::JSON, ?), fhirpath_bool(?::JSON, ?), fhirpath_is_valid(?)",
                [resource, expression, resource, expression, resource, expression, expression],
            ).fetchone()
            fallback_row = fallback.execute(
                "SELECT fhirpath(?::JSON, ?), fhirpath_text(?::JSON, ?), fhirpath_bool(?::JSON, ?), fhirpath_is_valid(?)",
                [resource, expression, resource, expression, resource, expression, expression],
            ).fetchone()
            assert native_row == fallback_row == expected

        observation = json.dumps({"resourceType": "Observation", "status": "final"})
        for expression in [
            "Observation.issued is instant",
            "Observation.issued.is(instant)",
        ]:
            native_row = native.execute(
                "SELECT fhirpath(?::JSON, ?), fhirpath_text(?::JSON, ?), fhirpath_bool(?::JSON, ?), fhirpath_is_valid(?)",
                [observation, expression, observation, expression, observation, expression, expression],
            ).fetchone()
            fallback_row = fallback.execute(
                "SELECT fhirpath(?::JSON, ?), fhirpath_text(?::JSON, ?), fhirpath_bool(?::JSON, ?), fhirpath_is_valid(?)",
                [observation, expression, observation, expression, observation, expression, expression],
            ).fetchone()
            assert native_row == fallback_row == ([], None, None, True)
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
        "missing.ofType(NoSuchType)",
        "Patient.gender.ofType(string1)",
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


def test_system_any_is_root_type_for_is_and_as(monkeypatch) -> None:
    resource = json.dumps(
        {
            "resourceType": "Patient",
            "id": "pat-1",
            "active": True,
            "name": [{"family": "Smith"}],
        }
    )
    expressions = [
        "1 is System.Any",
        "1.is(System.Any)",
        "1.as(System.Any).exists()",
        "true is System.Any",
        "'abc' is System.Any",
        "@2015 is System.Any",
        "5 'mg' is System.Any",
        "Patient is System.Any",
        "Patient.as(System.Any).exists()",
        "active is System.Any",
        "active.as(System.Any).exists()",
        "name.first() is System.Any",
        "name.first().as(System.Any).exists()",
    ]

    native = _connection()
    fallback = _python_fallback_connection(monkeypatch)
    try:
        for expression in expressions:
            assert _surfaces(native, resource, expression) == _surfaces(
                fallback, resource, expression
            )
            assert native.execute(
                "SELECT fhirpath_bool(?::JSON, ?), fhirpath_is_valid(?)",
                [resource, expression, expression],
            ).fetchone() == (True, True)
            assert fallback.execute(
                "SELECT fhirpath_bool(?::JSON, ?), fhirpath_is_valid(?)",
                [resource, expression, expression],
            ).fetchone() == (True, True)
    finally:
        native.close()
        fallback.close()


def test_choice_primitive_as_capitalized_type_chains_match_native(monkeypatch) -> None:
    resource = json.dumps({"resourceType": "Observation", "valueInteger": 5})
    expressions = [
        "value.as(Integer).exists()",
        "(value as Integer).exists()",
        "valueInteger.as(Integer).exists()",
        "(valueInteger as Integer).exists()",
    ]
    explicit_system_controls = [
        "value.as(System.Integer).exists()",
        "valueInteger.as(System.Integer).exists()",
    ]

    native = _connection()
    fallback = _python_fallback_connection(monkeypatch)
    try:
        for expression in expressions:
            assert _surfaces(native, resource, expression) == _surfaces(
                fallback, resource, expression
            )
            assert native.execute(
                "SELECT fhirpath_bool(?::JSON, ?), fhirpath_is_valid(?)",
                [resource, expression, expression],
            ).fetchone() == (True, True)
            assert fallback.execute(
                "SELECT fhirpath_bool(?::JSON, ?), fhirpath_is_valid(?)",
                [resource, expression, expression],
            ).fetchone() == (True, True)

        for expression in explicit_system_controls:
            assert _surfaces(native, resource, expression) == _surfaces(
                fallback, resource, expression
            )
            assert native.execute(
                "SELECT fhirpath_bool(?::JSON, ?), fhirpath_is_valid(?)",
                [resource, expression, expression],
            ).fetchone() == (False, True)
            assert fallback.execute(
                "SELECT fhirpath_bool(?::JSON, ?), fhirpath_is_valid(?)",
                [resource, expression, expression],
            ).fetchone() == (False, True)
    finally:
        native.close()
        fallback.close()


def test_oftype_any_and_nested_choice_primitives_match_native(monkeypatch) -> None:
    resource = json.dumps(
        {
            "resourceType": "Observation",
            "arr": [1, "a", True],
            "component": [
                {"valueInteger": 5},
                {"valueString": "five"},
                {"valueQuantity": {"value": 10, "unit": "mg", "code": "mg"}},
            ],
        }
    )
    expressions = {
        "arr.ofType(Any).count() = 3": True,
        "arr.ofType(System.Any).count() = 3": True,
        "component.value.ofType(Integer).count() = 1": True,
        "component.value.ofType(String).count() = 1": True,
        "component.value.ofType(Quantity).count() = 1": True,
    }

    native = _connection()
    fallback = _python_fallback_connection(monkeypatch)
    try:
        for expression, expected_bool in expressions.items():
            assert _surfaces(native, resource, expression) == _surfaces(
                fallback, resource, expression
            )
            assert native.execute(
                "SELECT fhirpath_bool(?::JSON, ?), fhirpath_is_valid(?)",
                [resource, expression, expression],
            ).fetchone() == (expected_bool, True)
            assert fallback.execute(
                "SELECT fhirpath_bool(?::JSON, ?), fhirpath_is_valid(?)",
                [resource, expression, expression],
            ).fetchone() == (expected_bool, True)
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
        lazy_branch = "iif(true, 'ok', unknownFunction())"
        assert native.execute("SELECT fhirpath_is_valid(?)", [lazy_branch]).fetchone() == (False,)
        assert fallback.execute("SELECT fhirpath_is_valid(?)", [lazy_branch]).fetchone() == (False,)
        assert fhirpath_is_valid_udf(lazy_branch) is False
        string_literal = "'unknownFunction()'.trace('label')"
        assert native.execute("SELECT fhirpath_is_valid(?)", [string_literal]).fetchone() == (True,)
        assert fallback.execute("SELECT fhirpath_is_valid(?)", [string_literal]).fetchone() == (True,)
        assert fhirpath_is_valid_udf(string_literal) is True
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


def test_choice_type_assertion_after_resource_oftype_matches_fallback(monkeypatch) -> None:
    resource = json.dumps(
        {
            "resourceType": "Bundle",
            "entry": [
                {
                    "resource": {
                        "resourceType": "Observation",
                        "id": "obs",
                        "valueInteger": 5,
                    }
                }
            ],
        }
    )
    expressions = [
        "entry.resource.ofType(Observation).value.is(Integer)",
        "entry.resource.ofType(Observation).value.as(Integer)",
    ]
    native = _connection()
    fallback = _python_fallback_connection(monkeypatch)
    try:
        for expression in expressions:
            assert _surfaces(native, resource, expression) == _surfaces(
                fallback, resource, expression
            )
        assert native.execute(
            "SELECT fhirpath_bool(?::JSON, 'entry.resource.ofType(Observation).value.is(Integer)')",
            [resource],
        ).fetchone() == (True,)
        assert fallback.execute(
            "SELECT fhirpath_bool(?::JSON, 'entry.resource.ofType(Observation).value.is(Integer)')",
            [resource],
        ).fetchone() == (True,)
        assert native.execute(
            "SELECT fhirpath_text(?::JSON, 'entry.resource.ofType(Observation).value.as(Integer)')",
            [resource],
        ).fetchone() == ("5",)
        assert fallback.execute(
            "SELECT fhirpath_text(?::JSON, 'entry.resource.ofType(Observation).value.as(Integer)')",
            [resource],
        ).fetchone() == ("5",)
    finally:
        native.close()
        fallback.close()


def test_valid_r4_resource_type_specifiers_match_fallback(monkeypatch) -> None:
    resource = json.dumps(
        {
            "resourceType": "Bundle",
            "entry": [
                {
                    "resource": {
                        "resourceType": "CodeSystem",
                        "id": "cs",
                        "status": "active",
                        "content": "complete",
                    }
                },
                {
                    "resource": {
                        "resourceType": "QuestionnaireResponse",
                        "id": "qr",
                        "status": "completed",
                    }
                },
                {
                    "resource": {
                        "resourceType": "Binary",
                        "id": "bin",
                        "contentType": "text/plain",
                    }
                },
                {
                    "resource": {
                        "resourceType": "Parameters",
                        "id": "params",
                        "parameter": [{"name": "n", "valueInteger": 7}],
                    }
                },
            ],
        }
    )
    expressions = {
        "entry.resource.ofType(CodeSystem).id": ["cs"],
        "entry.resource.ofType(QuestionnaireResponse).id": ["qr"],
        "entry.resource.ofType(Binary).id": ["bin"],
        "entry.resource.ofType(Parameters).id": ["params"],
        "entry.resource.ofType(CodeSystem).single() is DomainResource": ["true"],
        "entry.resource.ofType(Binary).single() is Resource": ["true"],
        "entry.resource.ofType(Parameters).single().as(Resource).id": ["params"],
    }
    native = _connection()
    fallback = _python_fallback_connection(monkeypatch)
    try:
        for expression, expected in expressions.items():
            assert _surfaces(native, resource, expression) == _surfaces(
                fallback, resource, expression
            )
            assert native.execute(
                "SELECT fhirpath(?::JSON, ?), fhirpath_is_valid(?)",
                [resource, expression, expression],
            ).fetchone() == (expected, True)
            assert fallback.execute(
                "SELECT fhirpath(?::JSON, ?), fhirpath_is_valid(?)",
                [resource, expression, expression],
            ).fetchone() == (expected, True)
    finally:
        native.close()
        fallback.close()
