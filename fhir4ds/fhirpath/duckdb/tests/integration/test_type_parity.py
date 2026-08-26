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


def test_quantity_literal_fhir_profile_subtypes_reject_in_both_backends_fp15_skeptic(
    monkeypatch,
) -> None:
    """FP-15 SKEPTIC QA-001 (§6.3.1/§4.1.8).

    A literal Quantity such as `5 'mg'` is System.Quantity. The base `Quantity`
    type matches, but FHIR R4 profiles on Quantity (Age, Distance, Duration,
    Count, Money, SimpleQuantity) require specific UCUM unit categories and
    must NOT match for `mg` (mass). Native C++ previously short-circuited
    `target == Age || target == Duration` to true for any Quantity literal;
    surgical fix at evaluator.cpp:8845 removed Age/Duration from the
    over-permissive branch. This regression test guards against reintroduction.
    """
    resource = json.dumps({"resourceType": "Patient", "id": "p1"})
    # (expression, expected_native_value, expected_is_valid)
    # Note: `5 'mg' is SimpleQuantity` has a pre-existing parity drift
    # (native rejects SimpleQuantity as unknown type because it's missing
    # from the C++ fhirTypeIsA hierarchy table; fallback accepts it via
    # valid_fhir_types.json). That drift is out of FP-15 QA-001 scope.
    expectations = [
        ("5 'mg' is Quantity", "true", True),
        ("5 'mg' is Age", "false", True),
        ("5 'mg' is Duration", "false", True),
        ("5 'mg' is Distance", "false", True),
        ("5 'mg' is Count", "false", True),
        ("5 'mg' is Money", "false", True),
        # Sanity: System.Quantity still matches the Quantity literal
        ("5 'mg' is System.Quantity", "true", True),
        # Sanity: same predicate via the `is(type)` function form
        ("5 'mg'.is(Quantity)", "true", True),
        ("5 'mg'.is(Age)", "false", True),
        ("5 'mg'.is(Duration)", "false", True),
    ]

    native = _connection()
    fallback = _python_fallback_connection(monkeypatch)
    try:
        for expression, expected_value, expected_valid in expectations:
            native_row = native.execute(
                "SELECT fhirpath_text(?::JSON, ?), fhirpath_is_valid(?)",
                [resource, expression, expression],
            ).fetchone()
            fallback_row = fallback.execute(
                "SELECT fhirpath_text(?::JSON, ?), fhirpath_is_valid(?)",
                [resource, expression, expression],
            ).fetchone()
            # Parity invariant
            assert native_row == fallback_row, (
                f"parity drift for {expression!r}: "
                f"native={native_row} fallback={fallback_row}"
            )
            # Spec invariant
            assert native_row == (expected_value, expected_valid), (
                f"spec violation for {expression!r}: "
                f"expected={(expected_value, expected_valid)} actual={native_row}"
            )
    finally:
        native.close()
        fallback.close()


def test_is_as_type_specifier_form_parity_fp15_skeptic(monkeypatch) -> None:
    """FP-15 SKEPTIC H1: `is TypeSpecifier` and `is(type)` produce identical
    results across all tested type specifiers. Same for `as TypeSpecifier` vs
    `as(type)`. This guards the parser-level form parity invariants.
    """
    resource = json.dumps(
        {
            "resourceType": "Patient",
            "id": "p1",
            "active": True,
            "gender": "male",
            "birthDate": "2000-01-01",
            "name": [{"family": "Smith", "given": ["John"]}],
        }
    )
    observation_quantity = json.dumps(
        {
            "resourceType": "Observation",
            "status": "final",
            "valueQuantity": {"value": 42.5, "unit": "mg"},
        }
    )
    paired_cases = [
        # (resource, type_specifier_form, function_call_form)
        (resource, "Patient is Resource", "Patient.is(Resource)"),
        (resource, "Patient as Resource", "Patient.as(Resource)"),
        (resource, "Patient is Patient", "Patient.is(Patient)"),
        (resource, "Patient as Patient", "Patient.as(Patient)"),
        (resource, "Patient is DomainResource", "Patient.is(DomainResource)"),
        (resource, "active is FHIR.boolean", "active.is(FHIR.boolean)"),
        (resource, "active as FHIR.boolean", "active.as(FHIR.boolean)"),
        (resource, "gender is FHIR.string", "gender.is(FHIR.string)"),
        (resource, "gender as FHIR.string", "gender.as(FHIR.string)"),
        (resource, "id is FHIR.id", "id.is(FHIR.id)"),
        (resource, "birthDate is FHIR.date", "birthDate.is(FHIR.date)"),
        (resource, "Patient is Any", "Patient.is(Any)"),
        (resource, "Patient as Any", "Patient.as(Any)"),
        (observation_quantity,
         "Observation.valueQuantity is Quantity",
         "Observation.valueQuantity.is(Quantity)"),
        (observation_quantity,
         "Observation.valueQuantity as Quantity",
         "Observation.valueQuantity.as(Quantity)"),
    ]
    native = _connection()
    fallback = _python_fallback_connection(monkeypatch)
    try:
        for rsrc, keyword_form, function_form in paired_cases:
            native_keyword = _surfaces(native, rsrc, keyword_form)
            native_function = _surfaces(native, rsrc, function_form)
            fallback_keyword = _surfaces(fallback, rsrc, keyword_form)
            fallback_function = _surfaces(fallback, rsrc, function_form)
            # Form parity (keyword == function call) within each backend
            assert native_keyword == native_function, (
                f"native form drift: {keyword_form!r}={native_keyword} vs "
                f"{function_form!r}={native_function}"
            )
            assert fallback_keyword == fallback_function, (
                f"fallback form drift: {keyword_form!r}={fallback_keyword} vs "
                f"{function_form!r}={fallback_function}"
            )
            # Backend parity
            assert native_keyword == fallback_keyword, (
                f"backend drift for {keyword_form!r}: "
                f"native={native_keyword} fallback={fallback_keyword}"
            )
    finally:
        native.close()
        fallback.close()


def test_fhir_primitive_string_subtype_hierarchy_fp15_historian(monkeypatch) -> None:
    """FP-15 HISTORIAN iteration 1 (2026-06-29) QA-001.

    Per FHIR R4 (https://hl7.org/fhir/R4/datatypes.html) all primitive
    datatypes inherit DIRECTLY from Element, NOT from each other. `date` is
    NOT a subtype of `string`. Only id/code/uri/url/canonical/oid/uuid/markdown
    are valid string-subtypes. Native C++ previously treated any
    JSON-string-encoded primitive as a subtype of `string`; surgical fix at
    evaluator.cpp:8775-8819 restricts the `is FHIR.string` non-exact match
    to actual string-subtypes.
    """
    resource = json.dumps({
        "resourceType": "Patient",
        "id": "p1",
        "active": True,
        "gender": "female",
        "birthDate": "2000-01-01",
    })
    # (path, FHIR type, expected boolean)
    expectations = [
        # Valid string-subtypes — must return true
        ("Patient.id", "string", True),       # id is subtype of string
        ("Patient.gender", "string", True),   # code is subtype of string
        ("Patient.id", "id", True),
        ("Patient.gender", "code", True),
        # JSON-string primitives that are NOT string-subtypes — must return false
        ("Patient.birthDate", "string", False),  # THE FIX — date is NOT subtype of string
        ("Patient.birthDate", "date", True),     # but it IS date
        ("Patient.birthDate", "dateTime", False),
        # Boolean is JSON-bool-encoded; never was a string subtype
        ("Patient.active", "string", False),
        ("Patient.active", "boolean", True),
        # Negative: id is NOT a code (sibling)
        ("Patient.id", "code", False),
        ("Patient.gender", "id", False),
    ]
    native = _connection()
    fallback = _python_fallback_connection(monkeypatch)
    try:
        for path, fhir_type, expected in expectations:
            expression = f"{path} is FHIR.{fhir_type}"
            expected_json = f"[{str(expected).lower()}]"
            native_row = native.execute(
                "SELECT fhirpath_json(?::JSON, ?)", [resource, expression]
            ).fetchone()[0]
            fallback_row = fallback.execute(
                "SELECT fhirpath_json(?::JSON, ?)", [resource, expression]
            ).fetchone()[0]
            assert native_row == expected_json, (
                f"native wrong for {expression!r}: "
                f"got {native_row!r}, expected {expected_json!r}"
            )
            assert fallback_row == expected_json, (
                f"fallback wrong for {expression!r}: "
                f"got {fallback_row!r}, expected {expected_json!r}"
            )
            assert native_row == fallback_row, (
                f"backend drift for {expression!r}: "
                f"native={native_row!r} fallback={fallback_row!r}"
            )
    finally:
        native.close()
        fallback.close()


def test_choice_value_empty_input_is_returns_empty_fp15_historian(monkeypatch) -> None:
    """FP-15 HISTORIAN iteration 1 (2026-06-29) QA-002.

    Per FHIRPath §6.3.1: "In all other cases this operator returns the empty
    collection." Empty input collection is "all other cases" — `is` must
    return empty (not false) when the choice-type field is absent. Native C++
    was already correct; Python fallback `_resolve_choice_type_assertion`
    overrode the engine's correct empty result with [False]. Surgical fix at
    fhir4ds/fhirpath/duckdb/udf.py:1540-1580.
    """
    resource = json.dumps({"resourceType": "Observation", "status": "final"})
    expressions = [
        "Observation.value is Quantity",
        "Observation.value is Boolean",
        "Observation.value is Integer",
        "Observation.value.is(Quantity)",
        "Observation.value.is(Boolean)",
        "Observation.value.is(Integer)",
    ]
    native = _connection()
    fallback = _python_fallback_connection(monkeypatch)
    try:
        for expression in expressions:
            native_row = native.execute(
                "SELECT fhirpath_json(?::JSON, ?)", [resource, expression]
            ).fetchone()[0]
            fallback_row = fallback.execute(
                "SELECT fhirpath_json(?::JSON, ?)", [resource, expression]
            ).fetchone()[0]
            # Both backends must return empty (None from fhirpath_json for empty list)
            assert native_row is None, (
                f"native wrong for {expression!r}: expected empty, got {native_row!r}"
            )
            assert fallback_row is None, (
                f"fallback wrong for {expression!r}: expected empty, got {fallback_row!r}"
            )

        # Sanity: when value IS present, both backends return the right boolean
        present = json.dumps({
            "resourceType": "Observation",
            "valueQuantity": {"value": 5, "unit": "mg"},
        })
        for expression, expected in [
            ("Observation.value is Quantity", "[true]"),
            ("Observation.value is Boolean", "[false]"),
            ("Observation.value is String", "[false]"),
        ]:
            native_row = native.execute(
                "SELECT fhirpath_json(?::JSON, ?)", [present, expression]
            ).fetchone()[0]
            fallback_row = fallback.execute(
                "SELECT fhirpath_json(?::JSON, ?)", [present, expression]
            ).fetchone()[0]
            assert native_row == expected, (
                f"native sanity wrong for {expression!r}: "
                f"got {native_row!r}, expected {expected!r}"
            )
            assert fallback_row == expected, (
                f"fallback sanity wrong for {expression!r}: "
                f"got {fallback_row!r}, expected {expected!r}"
            )
    finally:
        native.close()
        fallback.close()


def test_simplequantity_type_specifier_valid_in_native_fp15_historian(
    monkeypatch,
) -> None:
    """FP-15 HISTORIAN iteration 1 (2026-06-29) QA-003.

    `SimpleQuantity` is a valid FHIR R4 profile on Quantity
    (https://hl7.org/fhir/R4/datatypes.html#SimpleQuantity). Native C++
    previously rejected it as an unknown type specifier because it was missing
    from the `fhirTypeIsA` hierarchy table. Surgical fix added
    `{"SimpleQuantity", "Quantity"}` at evaluator.cpp:1028-1030.
    """
    expressions = [
        "(5 'mg') is SimpleQuantity",
        "(5 'mg').is(SimpleQuantity)",
        "(5 'mg') as SimpleQuantity",
        "(5 'mg').as(SimpleQuantity)",
        "Observation.value is SimpleQuantity",
        "Observation.value as SimpleQuantity",
    ]
    resource = json.dumps({
        "resourceType": "Observation",
        "valueQuantity": {"value": 5, "unit": "mg"},
    })
    native = _connection()
    fallback = _python_fallback_connection(monkeypatch)
    try:
        for expression in expressions:
            native_valid = native.execute(
                "SELECT fhirpath_is_valid(?)", [expression]
            ).fetchone()[0]
            fallback_valid = fallback.execute(
                "SELECT fhirpath_is_valid(?)", [expression]
            ).fetchone()[0]
            assert native_valid is True, (
                f"native should accept {expression!r} as valid"
            )
            assert fallback_valid is True, (
                f"fallback should accept {expression!r} as valid"
            )
            native_row = native.execute(
                "SELECT fhirpath_json(?::JSON, ?)",
                [resource if "Observation" in expression else "{}", expression],
            ).fetchone()[0]
            fallback_row = fallback.execute(
                "SELECT fhirpath_json(?::JSON, ?)",
                [resource if "Observation" in expression else "{}", expression],
            ).fetchone()[0]
            assert native_row == fallback_row, (
                f"backend drift for {expression!r}: "
                f"native={native_row!r} fallback={fallback_row!r}"
            )
    finally:
        native.close()
        fallback.close()


def test_fhir_primitive_is_element_root_subtype_fp20_historian(
    monkeypatch,
) -> None:
    """FP-20 HISTORIAN iteration 1 (2026-06-30) QA-001.

    Per FHIR R4 (https://hl7.org/fhir/R4/datatypes.html) every primitive
    datatype (boolean, integer, decimal, string, date, dateTime, time,
    code, id, etc.) inherits from Element. So `<primitive-value> is Element`
    must return true. Native C++ previously returned false because the
    primitive-type branches in fn_isType returned strict equality without
    consulting the FHIR R4 primitive->Element hierarchy. Surgical fix at
    extensions/fhirpath/src/fhirpath/evaluator.cpp in the `is_fhir` block
    adds a fallthrough check: if `target == "Element"` and the effective
    type is a System primitive (Boolean/Integer/Decimal/String/Date/
    DateTime/Time), return true. The check is gated on `!exact` so that
    `as Element` continues to return empty (preserving Python fallback
    parity on the `as` operator).

    Spec citations: FHIRPath v2.0.0 §11 Type Safety, §6.3.1 ("is returns
    true if the type of the left operand is the type specified, or a
    subclass thereof"); FHIR R4 datatypes (primitives inherit from Element).
    """
    resource = json.dumps({
        "resourceType": "Patient",
        "id": "p1",
        "active": True,
        "gender": "male",
        "birthDate": "1974-12-25",
        "name": [{"family": "Smith", "given": ["John"]}],
        "valueInteger": 3,
        "valueDecimal": 1.5,
        "valueString": "hello",
        "valueBoolean": True,
        "valueDate": "2024-01-15",
        "valueDateTime": "2024-01-15T10:30:00Z",
        "valueTime": "10:30:00",
        "valueQuantity": {"value": 70, "code": "kg"},
    })
    # (expression, expected boolean)
    expectations = [
        # FHIR primitives - must return true for `is Element`
        ("valueInteger is Element", True),
        ("valueDecimal is Element", True),
        ("valueString is Element", True),
        ("valueBoolean is Element", True),
        ("valueDate is Element", True),
        ("valueDateTime is Element", True),
        ("valueTime is Element", True),
        ("valueQuantity is Element", True),  # Quantity also inherits from Element
        # FHIR primitive fields - must return true
        ("active is Element", True),
        ("birthDate is Element", True),
        ("gender is Element", True),
        ("id is Element", True),
        # Complex types - already work correctly via fhirTypeIsA
        ("name is Element", True),
        # Resources - must remain false (inherit from Resource, not Element)
        ("Patient is Element", False),
        ("%resource is Element", False),
        ("Patient is Resource", True),
        ("%resource is Resource", True),
        # `as Element` parity preserved (both empty/None in C++ and Python)
        # — do not assert the boolean result for `as`, just check no drift.
    ]
    native = _connection()
    fallback = _python_fallback_connection(monkeypatch)
    try:
        for expression, expected in expectations:
            expected_json = f"[{str(expected).lower()}]"
            native_row = native.execute(
                "SELECT fhirpath_json(?::JSON, ?)", [resource, expression]
            ).fetchone()[0]
            fallback_row = fallback.execute(
                "SELECT fhirpath_json(?::JSON, ?)", [resource, expression]
            ).fetchone()[0]
            assert native_row == expected_json, (
                f"native wrong for {expression!r}: "
                f"got {native_row!r}, expected {expected_json!r}"
            )
            assert fallback_row == expected_json, (
                f"fallback wrong for {expression!r}: "
                f"got {fallback_row!r}, expected {expected_json!r}"
            )
            assert native_row == fallback_row, (
                f"backend drift for {expression!r}: "
                f"native={native_row!r} fallback={fallback_row!r}"
            )
    finally:
        native.close()
        fallback.close()


def test_as_element_on_primitive_preserves_empty_parity_fp20_historian(
    monkeypatch,
) -> None:
    """FP-20 HISTORIAN iteration 1 (2026-06-30) QA-001 follow-up.

    The surgical fix for `is Element` is gated on `!exact` so that the
    `as`/`ofType` paths (which call fn_isType with exact=true for
    primitives) continue to return empty for `as Element`. This preserves
    Python fallback parity — both backends currently return empty for
    `as Element` on a FHIR primitive (Python's `as Element` returns
    empty even though `is Element` returns true). When Python's `as
    Element` is fixed to return the input, this gate should be removed.

    FP-15 HISTORIAN (2026-08-18): confirmed this gate is required, not
    temporary: official fixtures testFHIRPathAsFunction11/13 pin exact-match
    `as` for FHIR primitives (`gender.as(string)` -> EMPTY), so `as Element`
    on a primitive stays empty in both engines.
    """
    resource = json.dumps({
        "resourceType": "Patient",
        "id": "p1",
        "active": True,
        "valueInteger": 3,
    })
    expressions = [
        "valueInteger as Element",
        "active as Element",
    ]
    native = _connection()
    fallback = _python_fallback_connection(monkeypatch)
    try:
        for expression in ["valueInteger as Element", "active as Element"]:
            native_row = native.execute(
                "SELECT fhirpath_json(?::JSON, ?)", [resource, expression]
            ).fetchone()[0]
            fallback_row = fallback.execute(
                "SELECT fhirpath_json(?::JSON, ?)", [resource, expression]
            ).fetchone()[0]
            # Both must be empty (None/NULL): fixtures pin exact-match `as`
            assert native_row is None, (
                f"native should return NULL for {expression!r}, got {native_row!r}"
            )
            assert fallback_row is None, (
                f"fallback should return NULL for {expression!r}, got {fallback_row!r}"
            )
    finally:
        native.close()
        fallback.close()


def test_full_fhir_r4_resource_hierarchy_is_resource_domainresource_fp15_explorer(
    monkeypatch,
) -> None:
    """FP-15 EXPLORER QA-001 (§6.3.1 / FHIR R4 resource hierarchy).

    The Python fallback's model.type2Parent previously only contained a
    hand-curated ~22-resource subset, missing ~125 of 148 concrete FHIR R4
    resource types. `Account is Resource` and `Account is DomainResource`
    incorrectly returned false in fallback vs true in native.

    Fix: `build_fhir_model()` at fhir4ds/fhirpath/duckdb/fhir_model.py now
    layers the canonical R4 hierarchy from models/r4/type2Parent.json
    (209 entries) under the legacy generated hierarchy.
    """
    # (resource_type, is Resource?, is DomainResource?)
    test_resources = [
        ("Account", True, True),
        ("ActivityDefinition", True, True),
        ("AdverseEvent", True, True),
        ("AllergyIntolerance", True, True),
        ("Appointment", True, True),
        ("AppointmentResponse", True, True),
        ("AuditEvent", True, True),
        ("Basic", True, True),
        ("Binary", True, False),       # Resource not DomainResource
        ("BodyStructure", True, True),
        ("Bundle", True, False),       # Resource not DomainResource
        ("CapabilityStatement", True, True),
        ("CarePlan", True, True),
        ("CareTeam", True, True),
        ("CatalogEntry", True, True),
        ("ChargeItem", True, True),
        ("Claim", True, True),
        ("ClaimResponse", True, True),
        ("ClinicalImpression", True, True),
        ("CodeSystem", True, True),
        ("Communication", True, True),
        ("CommunicationRequest", True, True),
        ("CompartmentDefinition", True, True),
        ("Composition", True, True),
        ("ConceptMap", True, True),
        ("Condition", True, True),
        ("Consent", True, True),
        ("Contract", True, True),
        ("Coverage", True, True),
        ("CoverageEligibilityRequest", True, True),
        ("CoverageEligibilityResponse", True, True),
        ("DetectedIssue", True, True),
        ("Device", True, True),
        ("DeviceDefinition", True, True),
        ("DeviceMetric", True, True),
        ("DeviceRequest", True, True),
        ("DeviceUseStatement", True, True),
        ("DiagnosticReport", True, True),
        ("DocumentManifest", True, True),
        ("DocumentReference", True, True),
        ("EffectEvidenceSynthesis", True, True),
        ("Encounter", True, True),
        ("Endpoint", True, True),
        ("EnrollmentRequest", True, True),
        ("EnrollmentResponse", True, True),
        ("EpisodeOfCare", True, True),
        ("EventDefinition", True, True),
        ("Evidence", True, True),
        ("EvidenceVariable", True, True),
        ("ExampleScenario", True, True),
        ("ExplanationOfBenefit", True, True),
        ("FamilyMemberHistory", True, True),
        ("Flag", True, True),
        ("Goal", True, True),
        ("GraphDefinition", True, True),
        ("Group", True, True),
        ("GuidanceResponse", True, True),
        ("HealthcareService", True, True),
        ("ImagingStudy", True, True),
        ("Immunization", True, True),
        ("ImmunizationEvaluation", True, True),
        ("ImmunizationRecommendation", True, True),
        ("ImplementationGuide", True, True),
        ("InsurancePlan", True, True),
        ("Invoice", True, True),
        ("Library", True, True),
        ("Linkage", True, True),
        ("List", True, True),
        ("Location", True, True),
        ("Measure", True, True),
        ("MeasureReport", True, True),
        ("Media", True, True),
        ("Medication", True, True),
        ("MedicationAdministration", True, True),
        ("MedicationDispense", True, True),
        ("MedicationKnowledge", True, True),
        ("MedicationRequest", True, True),
        ("MedicationStatement", True, True),
        ("MedicinalProduct", True, True),
        ("MedicinalProductAuthorization", True, True),
        ("MedicinalProductContraindication", True, True),
        ("MedicinalProductIndication", True, True),
        ("MedicinalProductIngredient", True, True),
        ("MedicinalProductInteraction", True, True),
        ("MedicinalProductManufactured", True, True),
        ("MedicinalProductPackaged", True, True),
        ("MedicinalProductPharmaceutical", True, True),
        ("MedicinalProductUndesirableEffect", True, True),
        ("MessageDefinition", True, True),
        ("MessageHeader", True, True),
        ("MolecularSequence", True, True),
        ("NamingSystem", True, True),
        ("NutritionOrder", True, True),
        ("Observation", True, True),
        ("ObservationDefinition", True, True),
        ("OperationDefinition", True, True),
        ("OperationOutcome", True, True),
        ("Organization", True, True),
        ("OrganizationAffiliation", True, True),
        ("Parameters", True, False),   # Resource not DomainResource
        ("Patient", True, True),
        ("PaymentNotice", True, True),
        ("PaymentReconciliation", True, True),
        ("Person", True, True),
        ("PlanDefinition", True, True),
        ("Practitioner", True, True),
        ("PractitionerRole", True, True),
        ("Procedure", True, True),
        ("Provenance", True, True),
        ("Questionnaire", True, True),
        ("QuestionnaireResponse", True, True),
        ("RelatedPerson", True, True),
        ("RequestGroup", True, True),
        ("ResearchDefinition", True, True),
        ("ResearchElementDefinition", True, True),
        ("ResearchStudy", True, True),
        ("ResearchSubject", True, True),
        ("RiskAssessment", True, True),
        ("RiskEvidenceSynthesis", True, True),
        ("Schedule", True, True),
        ("SearchParameter", True, True),
        ("ServiceRequest", True, True),
        ("Slot", True, True),
        ("Specimen", True, True),
        ("SpecimenDefinition", True, True),
        ("StructureDefinition", True, True),
        ("StructureMap", True, True),
        ("Subscription", True, True),
        ("Substance", True, True),
        ("SubstanceNucleicAcid", True, True),
        ("SubstancePolymer", True, True),
        ("SubstanceProtein", True, True),
        ("SubstanceReferenceInformation", True, True),
        ("SubstanceSourceMaterial", True, True),
        ("SubstanceSpecification", True, True),
        ("SupplyDelivery", True, True),
        ("SupplyRequest", True, True),
        ("Task", True, True),
        ("TerminologyCapabilities", True, True),
        ("TestReport", True, True),
        ("TestScript", True, True),
        ("ValueSet", True, True),
        ("VerificationResult", True, True),
        ("VisionPrescription", True, True),
    ]

    native = _connection()
    fallback = _python_fallback_connection(monkeypatch)
    try:
        for resource_type, expect_resource, expect_domainresource in test_resources:
            resource = json.dumps({"resourceType": resource_type, "id": "x1"})
            for expr, expected in [
                (f"{resource_type} is Resource", expect_resource),
                (f"{resource_type} is DomainResource", expect_domainresource),
                (f"{resource_type} is {resource_type}", True),
                (f"{resource_type} is FHIR.{resource_type}", True),
            ]:
                n = native.execute(
                    "SELECT fhirpath_bool(?::JSON, ?)", [resource, expr]
                ).fetchone()[0]
                f = fallback.execute(
                    "SELECT fhirpath_bool(?::JSON, ?)", [resource, expr]
                ).fetchone()[0]
                assert n == f == expected, (
                    f"{expr}: native={n} fallback={f} expected={expected}"
                )
    finally:
        native.close()
        fallback.close()


def test_identifier_value_non_choice_field_fp15_explorer(monkeypatch) -> None:
    """FP-15 EXPLORER QA-003 (§6.3.1).

    `Identifier.value` is a FHIR `string` field, not a `value[x]` choice
    type. The Python fallback's trailing-choice-type-assertion wrapper
    previously overrode the engine's correct `is_fn` result with `[False]`
    for any `.value is X` expression where no choice-type field was
    populated on the parent — conflating `Identifier.value` with
    `Observation.value[x]`.

    Fix: `udf.py:_resolve_trailing_choice_type_assertion` now returns None
    (defer to engine) when no choice-type field is populated, instead of
    forcing [False]/[].
    """
    resource = json.dumps({
        "resourceType": "Patient",
        "identifier": [{"system": "http://x", "value": "abc"}],
    })
    expressions_and_expected = [
        ("Patient.identifier.first().value is FHIR.string", ["true"]),
        ("Patient.identifier.value is FHIR.string", ["true"]),
        ("Patient.identifier.first().value is System.String", ["false"]),
        ("Patient.identifier.first().value as FHIR.string", ["abc"]),
        ("Patient.identifier.first().value.ofType(string)", ["abc"]),
    ]

    native = _connection()
    fallback = _python_fallback_connection(monkeypatch)
    try:
        for expression, expected in expressions_and_expected:
            n_row = native.execute(
                "SELECT fhirpath(?::JSON, ?)", [resource, expression]
            ).fetchone()[0]
            f_row = fallback.execute(
                "SELECT fhirpath(?::JSON, ?)", [resource, expression]
            ).fetchone()[0]
            assert n_row == f_row == expected, (
                f"{expression}: native={n_row!r} fallback={f_row!r} expected={expected!r}"
            )
    finally:
        native.close()
        fallback.close()


def test_choice_type_assertion_unchanged_for_populated_choice_field_fp15_explorer(
    monkeypatch,
) -> None:
    """FP-15 EXPLORER QA-003 regression guard.

    The fix to `_resolve_trailing_choice_type_assertion` (return None when
    no choice-type field is populated) must NOT regress the existing
    behavior for genuine choice-type fields (Observation.value[x]).
    """
    obs_value_string = json.dumps({
        "resourceType": "Observation",
        "status": "final",
        "code": {"coding": [{"code": "x"}]},
        "valueString": "hello",
    })
    obs_empty = json.dumps({
        "resourceType": "Observation",
        "status": "final",
        "code": {"coding": [{"code": "x"}]},
    })

    cases = [
        (obs_value_string, "value is FHIR.string", ["true"]),
        (obs_value_string, "value is FHIR.integer", ["false"]),
        (obs_value_string, "value as FHIR.string", ["hello"]),
        # Empty input must propagate empty per §6.3.1
        # (FP-15 HISTORIAN iteration 1 (2026-06-29) QA-002 contract)
        (obs_empty, "value is FHIR.string", []),
        (obs_empty, "value as FHIR.string", []),
    ]

    native = _connection()
    fallback = _python_fallback_connection(monkeypatch)
    try:
        for resource, expression, expected in cases:
            n_row = native.execute(
                "SELECT fhirpath(?::JSON, ?)", [resource, expression]
            ).fetchone()[0]
            f_row = fallback.execute(
                "SELECT fhirpath(?::JSON, ?)", [resource, expression]
            ).fetchone()[0]
            assert n_row == f_row == expected, (
                f"{expression}: native={n_row!r} fallback={f_row!r} expected={expected!r}"
            )
    finally:
        native.close()
        fallback.close()



def test_temporal_field_type_specifiers_parity_fp02_explorer(monkeypatch) -> None:
    """FP-02 EXPLORER QA-002 (2026-08-16): §4.2 is/as + §6.3 field typing.

    The native lexical shape-sniffing branches were removed (``is`` operates
    on the operand's TYPE, not its lexical content — model-unknown date-shaped
    string fields are FHIR.string per type()), ``instant`` and ``dateTime``
    are sibling R4 primitives (canonical models/r4/type2Parent.json), and the
    canonical temporal field metadata (.issued -> instant, .authoredOn ->
    dateTime, .date -> dateTime) is aligned across both surfaces.
    """
    medication = json.dumps(
        {"resourceType": "MedicationRequest", "id": "m", "authoredOn": "2024-01-01T10:00:00"}
    )
    observation = json.dumps(
        {
            "resourceType": "Observation",
            "status": "final",
            "issued": "2020-01-01T10:00:00Z",
            "effectiveInstant": "2020-01-01T10:00:00Z",
        }
    )
    composition = json.dumps(
        {"resourceType": "Composition", "id": "c", "date": "2020-01-01T10:00:00Z"}
    )
    patient = json.dumps(
        {
            "resourceType": "Patient",
            "id": "p",
            "birthDate": "1974-12-25",
            "active": True,
            "bd": "1974-12-25",
            "dtm": "1974-12-25T10:00:00",
        }
    )

    cases = [
        # Real R4 dateTime field (MedicationRequest.authoredOn)
        (medication, "authoredOn is dateTime", "true"),
        (medication, "authoredOn is FHIR.dateTime", "true"),
        (medication, "authoredOn.type().name", "dateTime"),
        (medication, "authoredOn as dateTime", "2024-01-01T10:00:00"),
        (medication, "authoredOn is string", "false"),
        (medication, "authoredOn is date", "false"),
        (medication, "authoredOn is Element", "true"),
        # Real R4 instant field (Observation.issued): instant is NOT dateTime
        (observation, "issued is instant", "true"),
        (observation, "issued is dateTime", "false"),
        (observation, "issued.type().name", "instant"),
        (observation, "issued is Element", "true"),
        # Choice-typed instant
        (observation, "effectiveInstant is instant", "true"),
        (observation, "effectiveInstant is dateTime", "false"),
        (observation, "effectiveInstant.type().name", "instant"),
        # Real R4 dateTime field named `date` (Composition.date)
        (composition, "date is dateTime", "true"),
        (composition, "date.type().name", "dateTime"),
        # Model-unknown custom fields stay strings (no lexical sniffing)
        (patient, "bd is date", "false"),
        (patient, "bd is FHIR.date", "false"),
        (patient, "bd is string", "true"),
        (patient, "bd.type().name", "string"),
        (patient, "dtm is dateTime", "false"),
        (patient, "dtm is string", "true"),
        # Anchors: model-known fields and the FHIR-vs-System namespace split
        (patient, "birthDate is date", "true"),
        (patient, "birthDate is Date", "true"),
        (patient, "birthDate is string", "false"),
        (patient, "active is Boolean", "false"),
        (patient, "active is FHIR.boolean", "true"),
        (patient, "active is boolean", "true"),
    ]

    native = _connection()
    fallback = _python_fallback_connection(monkeypatch)
    try:
        for resource, expression, expected in cases:
            cpp = native.execute(
                "SELECT fhirpath_text(?::JSON, ?)", [resource, expression]
            ).fetchone()[0]
            py = fallback.execute(
                "SELECT fhirpath_text(?::JSON, ?)", [resource, expression]
            ).fetchone()[0]
            assert cpp == expected, f"{expression!r}: native={cpp!r} expected={expected!r}"
            assert py == expected, f"{expression!r}: fallback={py!r} expected={expected!r}"
            assert _surfaces(native, resource, expression) == _surfaces(
                fallback, resource, expression
            )
    finally:
        native.close()
        fallback.close()


# --- FP-15 fresh SKEPTIC launch (2026-08-18) ---


def _run_both(con, fb, resource: str, expression: str):
    native = con.execute(
        "SELECT fhirpath(?::JSON, ?)", [resource, expression]
    ).fetchone()[0]
    fallback = fb.execute(
        "SELECT fhirpath(?::JSON, ?)", [resource, expression]
    ).fetchone()[0]
    return native, fallback


_PARAMS_UUID = json.dumps(
    {
        "resourceType": "Parameters",
        "parameter": [
            {"name": "c", "valueUuid": "urn:uuid:c2e10e5e-0527-458f-b325-6bb6238f5d94"}
        ],
    }
)

_PATIENT_CONTAINED = json.dumps(
    {
        "resourceType": "Patient",
        "id": "p1",
        "contained": [{"resourceType": "Patient", "id": "c1", "gender": "female"}],
    }
)

_OBS_QTY = json.dumps(
    {
        "resourceType": "Observation",
        "status": "final",
        "valueQuantity": {"value": 5, "unit": "mg"},
    }
)


def test_uuid_oid_is_fhir_uri_subtype_parity_fp15_skeptic2(monkeypatch) -> None:
    """Official fixture testTypeA4: valueUuid is FHIR.uri // true (uuid->uri)."""
    con = _connection()
    fb = _python_fallback_connection(monkeypatch)
    params_oid = json.dumps(
        {
            "resourceType": "Parameters",
            "parameter": [{"name": "o", "valueOid": "1.2.3.4.5"}],
        }
    )
    for resource, expr, expected in [
        (_PARAMS_UUID, "parameter[0].value.is(FHIR.uri)", ["true"]),
        (_PARAMS_UUID, "parameter[0].value.is(FHIR.uuid)", ["true"]),
        (_PARAMS_UUID, "parameter[0].value.is(FHIR.string)", ["true"]),
        (params_oid, "parameter[0].value.is(FHIR.uri)", ["true"]),
        (params_oid, "parameter[0].value.is(FHIR.oid)", ["true"]),
    ]:
        native, fallback = _run_both(con, fb, resource, expr)
        assert native == expected, (expr, native)
        assert fallback == expected, (expr, fallback)


def test_literal_quantity_qualified_fhir_quantity_rejects_fp15_skeptic2(
    monkeypatch,
) -> None:
    """System.Quantity literal must not match explicitly FHIR-qualified Quantity."""
    patient = json.dumps({"resourceType": "Patient", "id": "p"})
    con = _connection()
    fb = _python_fallback_connection(monkeypatch)
    cases = [
        ("5 'mg' is FHIR.Quantity", ["false"]),
        ("5 'mg' is System.Quantity", ["true"]),
        ("5 'mg' is Quantity", ["true"]),  # unqualified: shared convention
        ("5 'mg' is Age", ["false"]),
        ("5 'mg' is Duration", ["false"]),
    ]
    for expr, expected in cases:
        native, fallback = _run_both(con, fb, patient, expr)
        assert native == expected, (expr, native)
        assert fallback == expected, (expr, fallback)


def test_contained_is_as_not_hijacked_by_choice_rescue_fp15_skeptic2(
    monkeypatch,
) -> None:
    """Resource.contained is not a choice type; is/as must reach the engine."""
    con = _connection()
    fb = _python_fallback_connection(monkeypatch)
    cases = [
        ("contained is Patient", ["true"]),
        ("contained.is(Patient)", ["true"]),
        ("contained as Patient", None),  # resource object; parity only
        ("contained.as(Patient).id", ["c1"]),
        ("(contained as Patient).gender", ["female"]),
        ("contained as Observation", []),
        ("contained is Observation", ["false"]),
    ]
    for expr, expected in cases:
        native, fallback = _run_both(con, fb, _PATIENT_CONTAINED, expr)
        assert native == fallback, (expr, native, fallback)
        if expected is not None:
            assert native == expected, (expr, native)
        else:
            assert native is not None and native != []


def test_type_specifier_function_invocation_is_syntax_error_fp15_skeptic2(
    monkeypatch,
) -> None:
    """`X is FHIR.Quantity.not()` is invalid grammar (typeSpecifier, not expr)."""
    con = _connection()
    fb = _python_fallback_connection(monkeypatch)
    for expr in [
        "valueQuantity is FHIR.Quantity.not()",
        "value as FHIR.Quantity.not()",
    ]:
        native = con.execute(
            "SELECT fhirpath(?::JSON, ?)", [_OBS_QTY, expr]
        ).fetchone()[0]
        fallback = fb.execute(
            "SELECT fhirpath(?::JSON, ?)", [_OBS_QTY, expr]
        ).fetchone()[0]
        assert native == fallback == [] or (native is None and fallback is None), expr
        assert con.execute("SELECT fhirpath_is_valid(?)", [expr]).fetchone()[0] is False
        assert (
            fb.execute("SELECT fhirpath_is_valid(?)", [expr]).fetchone()[0] is False
        )
    # Guard against false positives: valid is/as forms stay valid on both.
    for expr in [
        "(valueQuantity is FHIR.Quantity).not()",
        "value as Quantity",
        "value.as(FHIR.Quantity)",
        "5 is Integer",
        "'x'.is(String)",
    ]:
        assert (
            fb.execute("SELECT fhirpath_is_valid(?)", [expr]).fetchone()[0] is True
        ), expr
        assert (
            con.execute("SELECT fhirpath_is_valid(?)", [expr]).fetchone()[0] is True
        ), expr


def test_exported_is_as_helpers_string_specifiers_fp15_skeptic2() -> None:
    """typecheck.is_type/as_type must resolve unqualified string specifiers."""
    from fhir4ds.fhirpath.duckdb.functions import typecheck

    ctx: dict = {}
    assert typecheck.is_type(ctx, [1], "Integer") == [True]
    assert typecheck.is_type(ctx, [1], "System.Integer") == [True]
    assert typecheck.is_type(ctx, [1], "Decimal") == [False]
    assert typecheck.is_type(ctx, [True], "Boolean") == [True]
    assert typecheck.as_type(ctx, [5], "Integer") == [5]
    assert typecheck.as_type(ctx, ["a"], "Integer") == []
    assert typecheck.is_type(ctx, ["x"], "uri") == [False]
    patient = {"resourceType": "Patient", "id": "p"}
    assert typecheck.is_type(ctx, [patient], "Patient") == [True]
    assert typecheck.as_type(ctx, [patient], "Patient") == [patient]


def test_as_type_specifier_accepts_fhir_primitive_ancestors_fp15_historian(
    monkeypatch,
) -> None:
    """FP-15 HISTORIAN (2026-08-18): the `is`/`as` asymmetry on FHIR
    primitives is pinned by official fixtures — `is` is subtype-based
    (testFHIRPathIsFunction: `gender is string` TRUE, code <: string),
    while `as`/`ofType` are EXACT-match (testFHIRPathAsFunction11:
    `gender.as(string)` EMPTY; AsFunction12: `.as(code)` -> male). Both
    engines must implement this split identically."""
    patient = json.dumps(
        {
            "resourceType": "Patient",
            "id": "p1",
            "gender": "male",
            "active": True,
            "birthDate": "1974-12-25",
        }
    )
    params_code = json.dumps(
        {
            "resourceType": "Parameters",
            "parameter": [{"name": "b", "valueCode": "m"}],
        }
    )
    con = _connection()
    fb = _python_fallback_connection(monkeypatch)
    cases = [
        (patient, "gender is FHIR.string", ["true"]),   # is: subtype
        (patient, "(gender as FHIR.string) = 'male'", []),  # as: exact
        (patient, "gender.as(FHIR.string)", []),
        (patient, "(gender as code) = 'male'", ["true"]),   # as: exact match
        (patient, "(id as FHIR.id) = 'p1'", ["true"]),
        (patient, "(id as FHIR.string) = 'p1'", []),        # id <: string, as exact
        (patient, "active as FHIR.string", []),
        (_PARAMS_UUID, "parameter[0].value is FHIR.string", ["true"]),
        (_PARAMS_UUID, "parameter[0].value as FHIR.string", []),  # uuid <: uri <: string
        (_PARAMS_UUID, "parameter[0].value as FHIR.uri", []),
        (_PARAMS_UUID, "parameter[0].value.as(FHIR.uuid) = parameter[0].value", ["true"]),
        (params_code, "(parameter[0].value as FHIR.string) = 'm'", []),
        (params_code, "(parameter[0].value as code) = 'm'", ["true"]),
        # System-namespace `as` unaffected (flat, exact by construction)
        (patient, "(1 as Integer) = 1", ["true"]),
        (patient, "1 as String", []),
    ]
    for resource, expr, expected in cases:
        native, fallback = _run_both(con, fb, resource, expr)
        assert native == expected, (expr, native)
        assert fallback == expected, (expr, fallback)


def test_implicit_rules_typed_uri_both_engines_fp15_historian(monkeypatch) -> None:
    """FP-15 HISTORIAN QA-002: Patient.implicitRules is FHIR.uri (R4); the
    fallback must not fall through to value-shape string typing."""
    patient = json.dumps(
        {"resourceType": "Patient", "id": "p1", "implicitRules": "http://example.org/r"}
    )
    con = _connection()
    fb = _python_fallback_connection(monkeypatch)
    for expr, expected in [
        ("implicitRules is FHIR.uri", ["true"]),
        ("implicitRules.is(uri)", ["true"]),
        ("implicitRules.type().name", ["uri"]),
        ("implicitRules.type().namespace", ["FHIR"]),
        ("implicitRules is FHIR.string", ["true"]),  # uri <: string
        ("(implicitRules as FHIR.uri) = 'http://example.org/r'", ["true"]),
        ("implicitRules is FHIR.code", ["false"]),
        ("(implicitRules as FHIR.string) = 'http://example.org/r'", []),  # as exact
    ]:
        native, fallback = _run_both(con, fb, patient, expr)
        assert native == expected, (expr, native)
        assert fallback == expected, (expr, fallback)


def test_infix_is_as_chains_both_engines_fp15_explorer(monkeypatch) -> None:
    """FP-15 EXPLORER QA-001: the official FHIRPath grammar's typeExpression
    rule (`expression ('is' | 'as') typeSpecifier`) is left-recursive, so
    chained infix type specifiers such as `A as Resource is FHIR.Patient`
    are valid and must associate LEFT. The native parser previously consumed
    at most one typeSpecifier, yielding empty results while the Python
    fallback evaluated the chain."""
    patient = json.dumps(
        {
            "resourceType": "Patient",
            "id": "p1",
            "gender": "male",
            "contained": [
                {"resourceType": "Observation", "status": "final", "code": {"text": "t"}}
            ],
        }
    )
    con = _connection()
    fb = _python_fallback_connection(monkeypatch)
    for expr, expected in [
        ("Patient as Resource is FHIR.Patient", ["true"]),
        ("Patient as Resource is FHIR.Resource", ["true"]),
        ("Patient as Resource as Resource is FHIR.Patient", ["true"]),
        ("Patient is Resource is Boolean", ["true"]),
        ("contained[0] as Observation is FHIR.Observation", ["true"]),
        ("contained[0] as Observation as DomainResource is FHIR.Resource", ["true"]),
        ("(Patient as Resource).is(FHIR.Patient)", ["true"]),
        ("gender as code = 'male'", ["true"]),
        # exact-match `as` doctrine for FHIR primitives is preserved in chains
        ("gender as code as string", []),
    ]:
        native, fallback = _run_both(con, fb, patient, expr)
        assert native == expected, (expr, native)
        assert fallback == expected, (expr, fallback)


def test_recorded_and_last_updated_typed_instant_both_engines_fp15_explorer(
    monkeypatch,
) -> None:
    """FP-15 EXPLORER QA-002/QA-003: FHIR R4 types AuditEvent.recorded,
    Provenance.recorded, and Meta.lastUpdated as `instant` (not string, not
    dateTime — instant and dateTime are sibling primitives)."""
    audit = json.dumps(
        {
            "resourceType": "AuditEvent",
            "type": {"code": "rest"},
            "recorded": "2024-01-01T10:00:00.000Z",
            "agent": [{"who": {"display": "x"}}],
            "source": {"observer": {"display": "o"}},
        }
    )
    patient = json.dumps(
        {
            "resourceType": "Patient",
            "id": "p1",
            "meta": {"lastUpdated": "2024-01-01T10:00:00.000Z", "versionId": "2"},
        }
    )
    con = _connection()
    fb = _python_fallback_connection(monkeypatch)
    for resource, expr, expected in [
        (audit, "recorded is FHIR.instant", ["true"]),
        (audit, "recorded.is(instant)", ["true"]),
        (audit, "recorded is FHIR.dateTime", ["false"]),
        (audit, "recorded is FHIR.string", ["false"]),
        (patient, "meta.lastUpdated is FHIR.instant", ["true"]),
        (patient, "meta.lastUpdated is FHIR.dateTime", ["false"]),
        (patient, "meta.versionId is FHIR.id", ["true"]),
    ]:
        native, fallback = _run_both(con, fb, resource, expr)
        assert native == expected, (expr, native)
        assert fallback == expected, (expr, fallback)
