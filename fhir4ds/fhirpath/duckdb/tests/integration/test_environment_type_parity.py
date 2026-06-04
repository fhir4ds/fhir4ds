"""Parity tests for FHIRPath environment variables and type reflection."""

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


def test_environment_and_type_reflection_match_cpp() -> None:
    resource = json.dumps(
        {
            "resourceType": "Patient",
            "id": "p1",
            "active": True,
            "birthDate": "1974-12-25",
            "name": [{"family": "Smith", "given": ["John"]}],
            "managingOrganization": {"reference": "Organization/o1"},
            "valueInteger": 3,
        }
    )
    expressions = [
        "%ucum",
        "%ucum = 'http://unitsofmeasure.org'",
        "%resource.resourceType",
        "%context.id",
        "%rootResource.resourceType",
        "1.type().namespace",
        "1.type().name",
        "'x'.type().namespace",
        "'x'.type().name",
        "true.type().namespace",
        "true.type().name",
        "active.type().namespace",
        "active.type().name",
        "Patient.type().namespace",
        "Patient.type().name",
        "name.type().name",
        "name.given.type().name",
        "active is boolean",
        "active is Boolean",
        "active is System.Boolean",
        "active is FHIR.boolean",
        "1 is Integer",
        "1 is integer",
        "1 as Integer",
        "active.as(boolean)",
        "active.as(Boolean)",
        "Patient.ofType(Patient).type().name",
        "Patient.ofType(FHIR.Patient).type().name",
        "Patient.ofType(System.Patient).empty()",
        "1 | true",
        "name.as(HumanName).family",
        "managingOrganization.type().name",
        "managingOrganization.is(Reference)",
        "managingOrganization.as(Reference).reference",
        "(1|2).type().name",
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


def test_environment_variable_edges_match_cpp(monkeypatch) -> None:
    resource = json.dumps({"resourceType": "Patient", "id": "p1"})
    expressions = [
        "%`vs-administrative-gender`",
        "%'vs-administrative-gender'",
        "%`ext-patient-birthTime`",
        "%unknown",
        "%`unknown-var`",
        "%`vs-foo`",
        "%`ext-foo`",
        "%factory",
        "%terminologies",
    ]

    con = _connection()
    monkeypatch.setattr(duckdb, "__version__", "0.0.0-forced-python-fallback")
    fallback = duckdb.connect(config={"allow_unsigned_extensions": True})
    assert register_fhirpath(fallback) is False
    try:
        for expression in expressions:
            cpp = con.execute(
                "SELECT fhirpath(?::JSON, ?), fhirpath_text(?::JSON, ?), fhirpath_json(?::JSON, ?), fhirpath_is_valid(?)",
                [resource, expression, resource, expression, resource, expression, expression],
            ).fetchone()
            py = fallback.execute(
                "SELECT fhirpath(?::JSON, ?), fhirpath_text(?::JSON, ?), fhirpath_json(?::JSON, ?), fhirpath_is_valid(?)",
                [resource, expression, resource, expression, resource, expression, expression],
            ).fetchone()
            assert cpp == py, expression

        assert con.execute("SELECT fhirpath_is_valid('%unknown')").fetchone() == (False,)
        assert fallback.execute("SELECT fhirpath_is_valid('%unknown')").fetchone() == (False,)
        for expression in ["%`vs-foo`", "%`ext-foo`", "%factory", "%terminologies"]:
            assert con.execute("SELECT fhirpath_is_valid(?)", [expression]).fetchone() == (False,)
            assert fallback.execute("SELECT fhirpath_is_valid(?)", [expression]).fetchone() == (False,)
    finally:
        con.close()
        fallback.close()


def test_external_constants_allow_hidden_tokens_after_percent(monkeypatch) -> None:
    """FHIRPath formal grammar hides whitespace/comments after '%'."""
    resource = json.dumps({"resourceType": "Patient", "id": "p1"})
    cases = {
        "% 'ucum'": (["http://unitsofmeasure.org"], "http://unitsofmeasure.org", True),
        "%\t'ucum'": (["http://unitsofmeasure.org"], "http://unitsofmeasure.org", True),
        "%/*grammar*/'ucum'": (["http://unitsofmeasure.org"], "http://unitsofmeasure.org", True),
        "%//grammar\n'ucum'": (["http://unitsofmeasure.org"], "http://unitsofmeasure.org", True),
        "%\r\nloinc": (["http://loinc.org"], "http://loinc.org", True),
        "%\n`context`.id": (["p1"], "p1", True),
        "% `vs-administrative-gender`": (
            ["http://hl7.org/fhir/ValueSet/administrative-gender"],
            "http://hl7.org/fhir/ValueSet/administrative-gender",
            True,
        ),
        "% 'unknown'": ([], None, False),
    }

    con = _connection()
    monkeypatch.setattr(duckdb, "__version__", "0.0.0-forced-python-fallback")
    fallback = duckdb.connect(config={"allow_unsigned_extensions": True})
    assert register_fhirpath(fallback) is False
    try:
        for expression, expected in cases.items():
            cpp = con.execute(
                "SELECT fhirpath(?::JSON, ?), fhirpath_text(?::JSON, ?), fhirpath_is_valid(?)",
                [resource, expression, resource, expression, expression],
            ).fetchone()
            py = fallback.execute(
                "SELECT fhirpath(?::JSON, ?), fhirpath_text(?::JSON, ?), fhirpath_is_valid(?)",
                [resource, expression, resource, expression, expression],
            ).fetchone()
            assert cpp == py == expected, expression
    finally:
        con.close()
        fallback.close()


def test_define_variable_scope_matches_cpp(monkeypatch) -> None:
    resource = json.dumps(
        {
            "resourceType": "Patient",
            "id": "p1",
            "name": [{"family": "Smith"}, {"family": "Jones"}],
            "a": [1, 2],
        }
    )
    expressions = [
        "defineVariable('x', id).select(%x)",
        "name.defineVariable('x', family).select(%x)",
        "name.select(defineVariable('x', family).select(%x))",
        "defineVariable('x', id).defineVariable('x', name.family).select(%x)",
        "defineVariable('context', id)",
        "a.where(defineVariable('leak', $this).exists()).select(%leak)",
        "a.aggregate(defineVariable('leak', $this).exists(), false).combine(%leak)",
    ]

    con = _connection()
    monkeypatch.setattr(duckdb, "__version__", "0.0.0-forced-python-fallback")
    fallback = duckdb.connect(config={"allow_unsigned_extensions": True})
    assert register_fhirpath(fallback) is False
    try:
        for expression in expressions:
            cpp = con.execute(
                "SELECT fhirpath(?::JSON, ?), fhirpath_text(?::JSON, ?), fhirpath_json(?::JSON, ?), fhirpath_bool(?::JSON, ?), fhirpath_number(?::JSON, ?), fhirpath_is_valid(?)",
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
                    expression,
                ],
            ).fetchone()
            py = fallback.execute(
                "SELECT fhirpath(?::JSON, ?), fhirpath_text(?::JSON, ?), fhirpath_json(?::JSON, ?), fhirpath_bool(?::JSON, ?), fhirpath_number(?::JSON, ?), fhirpath_is_valid(?)",
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
                    expression,
                ],
            ).fetchone()
            assert cpp == py, expression

        assert con.execute(
            "SELECT fhirpath_json(?::JSON, ?)",
            [resource, "name.select(defineVariable('x', family).select(%x))"],
        ).fetchone() == ('["Smith","Jones"]',)
        assert fallback.execute(
            "SELECT fhirpath_json(?::JSON, ?)",
            [resource, "name.select(defineVariable('x', family).select(%x))"],
        ).fetchone() == ('["Smith","Jones"]',)
    finally:
        con.close()
        fallback.close()


def test_backbone_element_type_checks_match_cpp(monkeypatch) -> None:
    resource = json.dumps(
        {
            "resourceType": "Patient",
            "contact": [
                {
                    "relationship": [{"text": "friend"}],
                    "name": {"family": "Jones"},
                    "gender": "female",
                }
            ],
        }
    )
    expressions = [
        "contact.type().name",
        "contact.is(BackboneElement)",
        "contact.is(Element)",
        "contact.as(BackboneElement).name.family",
        "contact.as(Element).name.family",
        "contact.ofType(BackboneElement).name.family",
    ]

    con = _connection()
    monkeypatch.setattr(duckdb, "__version__", "0.0.0-forced-python-fallback")
    fallback = duckdb.connect(config={"allow_unsigned_extensions": True})
    assert register_fhirpath(fallback) is False
    try:
        for expression in expressions:
            cpp = con.execute(
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
            py = fallback.execute(
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
            assert cpp == py, expression

        assert con.execute(
            "SELECT fhirpath_text(?::JSON, 'contact.as(BackboneElement).name.family')",
            [resource],
        ).fetchone() == ("Jones",)
    finally:
        con.close()
        fallback.close()


def test_uri_reference_and_media_type_shapes_match_cpp(monkeypatch) -> None:
    resources_and_expressions = [
        (
            {
                "resourceType": "Questionnaire",
                "url": "http://example.org/q",
                "version": "2026-05",
                "subjectType": ["Patient"],
            },
            [
                "Questionnaire.url.type().name",
                "Questionnaire.url.is(uri)",
                "Questionnaire.url.is(string)",
                "Questionnaire.version.type().name",
                "Questionnaire.subjectType.type().name",
                "Questionnaire.subjectType.is(code)",
                "Questionnaire.subjectType.is(string)",
            ],
        ),
        (
            {
                "resourceType": "Parameters",
                "parameter": [
                    {"name": "u", "valueUri": "urn:uuid:11111111-1111-1111-1111-111111111111"},
                    {"name": "s", "valueString": "abc"},
                ],
            },
            [
                "Parameters.parameter[0].value.type().name",
                "Parameters.parameter[0].value.is(uri)",
                "Parameters.parameter[0].value.is(string)",
                "Parameters.parameter[1].value.type().name",
            ],
        ),
        (
            {
                "resourceType": "DocumentReference",
                "content": [
                    {
                        "attachment": {
                            "contentType": "text/plain; charset=utf-8",
                            "url": "http://example.org/doc.txt",
                        }
                    }
                ],
            },
            [
                "DocumentReference.content.attachment.type().name",
                "DocumentReference.content.attachment.contentType.type().name",
                "DocumentReference.content.attachment.contentType.is(code)",
                "DocumentReference.content.attachment.contentType.is(string)",
                "DocumentReference.content.attachment.url.is(uri)",
            ],
        ),
    ]

    con = _connection()
    monkeypatch.setattr(duckdb, "__version__", "0.0.0-forced-python-fallback")
    fallback = duckdb.connect(config={"allow_unsigned_extensions": True})
    assert register_fhirpath(fallback) is False
    try:
        for resource_obj, expressions in resources_and_expressions:
            resource = json.dumps(resource_obj)
            for expression in expressions:
                cpp = con.execute(
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
                py = fallback.execute(
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
                assert cpp == py, expression

        assert con.execute(
            "SELECT fhirpath_text(?::JSON, 'DocumentReference.content.attachment.contentType.type().name')",
            [json.dumps(resources_and_expressions[2][0])],
        ).fetchone() == ("code",)
        assert con.execute(
            "SELECT fhirpath_text(?::JSON, 'Questionnaire.subjectType.type().name')",
            [json.dumps(resources_and_expressions[0][0])],
        ).fetchone() == ("code",)
    finally:
        con.close()
        fallback.close()


def test_quantity_value_type_reflection_matches_cpp(monkeypatch) -> None:
    """Quantity.value remains a decimal after fallback path navigation."""
    resource = json.dumps(
        {
            "resourceType": "Observation",
            "valueQuantity": {
                "value": 120.5,
                "unit": "mmHg",
                "system": "http://unitsofmeasure.org",
                "code": "mm[Hg]",
            },
        }
    )
    expressions = [
        "valueQuantity.value.type().name",
        "(valueQuantity.value).type().name",
        "value.ofType(Quantity).value.type().name",
        "(value.ofType(Quantity).value).type().name",
    ]

    con = _connection()
    monkeypatch.setattr(duckdb, "__version__", "0.0.0-forced-python-fallback")
    fallback = duckdb.connect(config={"allow_unsigned_extensions": True})
    assert register_fhirpath(fallback) is False
    try:
        for expression in expressions:
            cpp = con.execute(
                "SELECT fhirpath(?::JSON, ?), fhirpath_text(?::JSON, ?)",
                [resource, expression, resource, expression],
            ).fetchone()
            py = fallback.execute(
                "SELECT fhirpath(?::JSON, ?), fhirpath_text(?::JSON, ?)",
                [resource, expression, resource, expression],
            ).fetchone()
            assert cpp == py == (["decimal"], "decimal"), expression
    finally:
        con.close()
        fallback.close()


def test_json_decimal_precision_boundaries_match_cpp_and_fallback(monkeypatch) -> None:
    """JSON-authored decimal scale feeds precision and boundary functions."""
    resource = json.dumps(
        {
            "resourceType": "Observation",
            "id": "o1",
            "valueQuantity": {"value": 1.0},
        }
    )
    expressions = {
        "value.ofType(Quantity).value.precision()": (["1"], "1", "[1]", 1.0),
        "value.ofType(Quantity).value.lowBoundary()": (
            ["0.95000000"],
            "0.95000000",
            "[0.95000000]",
            0.95,
        ),
        "value.ofType(Quantity).value.highBoundary()": (
            ["1.05000000"],
            "1.05000000",
            "[1.05000000]",
            1.05,
        ),
    }

    con = _connection()
    monkeypatch.setattr(duckdb, "__version__", "0.0.0-forced-python-fallback")
    fallback = duckdb.connect(config={"allow_unsigned_extensions": True})
    assert register_fhirpath(fallback) is False
    try:
        for expression, expected in expressions.items():
            query = (
                "SELECT fhirpath(?::JSON, ?), fhirpath_text(?::JSON, ?), "
                "fhirpath_json(?::JSON, ?), fhirpath_number(?::JSON, ?)"
            )
            params = [
                resource,
                expression,
                resource,
                expression,
                resource,
                expression,
                resource,
                expression,
            ]
            assert con.execute(query, params).fetchone() == expected, expression
            assert fallback.execute(query, params).fetchone() == expected, expression
    finally:
        con.close()
        fallback.close()


def test_json_temporal_boundaries_and_root_where_match_cpp_and_fallback(monkeypatch) -> None:
    """FHIR primitive metadata drives boundary functions and root-level where()."""
    cases = [
        (
            {"resourceType": "Patient", "id": "p1", "birthDate": "1970-06"},
            {
                "birthDate.lowBoundary()": (["1970-06-01"], "1970-06-01"),
                "birthDate.highBoundary()": (["1970-06-30"], "1970-06-30"),
            },
        ),
        (
            {"resourceType": "Observation", "id": "o1", "valueDateTime": "2010-10-10"},
            {
                "value.ofType(dateTime).lowBoundary()": (
                    ["2010-10-10T00:00:00.000+14:00"],
                    "2010-10-10T00:00:00.000+14:00",
                ),
                "value.ofType(dateTime).highBoundary()": (
                    ["2010-10-10T23:59:59.999-12:00"],
                    "2010-10-10T23:59:59.999-12:00",
                ),
            },
        ),
        (
            {"resourceType": "Observation", "id": "o2", "valueTime": "12:34"},
            {
                "value.ofType(time).lowBoundary()": (["12:34:00.000"], "12:34:00.000"),
                "value.ofType(time).highBoundary()": (["12:34:59.999"], "12:34:59.999"),
            },
        ),
        (
            {"resourceType": "Observation", "id": "o3", "valueInteger": 12},
            {"where(value.ofType(integer) > 11).exists()": (["true"], "true")},
        ),
    ]

    con = _connection()
    monkeypatch.setattr(duckdb, "__version__", "0.0.0-forced-python-fallback")
    fallback = duckdb.connect(config={"allow_unsigned_extensions": True})
    assert register_fhirpath(fallback) is False
    try:
        for resource_dict, expressions in cases:
            resource = json.dumps(resource_dict)
            for expression, expected in expressions.items():
                query = "SELECT fhirpath(?::JSON, ?), fhirpath_text(?::JSON, ?)"
                params = [resource, expression, resource, expression]
                assert con.execute(query, params).fetchone() == expected, expression
                assert fallback.execute(query, params).fetchone() == expected, expression
    finally:
        con.close()
        fallback.close()


def test_type_reflection_rejects_arguments_in_cpp_and_fallback(monkeypatch) -> None:
    """FHIRPath N1 §10.2 reflection defines type() with no arguments."""
    resource = json.dumps({"resourceType": "Patient", "id": "p1"})
    expressions = [
        "type(false)",
        "type(false, true)",
        "1.type(false)",
        "1.type(false, true)",
    ]

    con = _connection()
    monkeypatch.setattr(duckdb, "__version__", "0.0.0-forced-python-fallback")
    fallback = duckdb.connect(config={"allow_unsigned_extensions": True})
    assert register_fhirpath(fallback) is False
    try:
        for expression in expressions:
            cpp = con.execute(
                "SELECT fhirpath(?::JSON, ?), fhirpath_text(?::JSON, ?), fhirpath_json(?::JSON, ?), fhirpath_is_valid(?)",
                [resource, expression, resource, expression, resource, expression, expression],
            ).fetchone()
            py = fallback.execute(
                "SELECT fhirpath(?::JSON, ?), fhirpath_text(?::JSON, ?), fhirpath_json(?::JSON, ?), fhirpath_is_valid(?)",
                [resource, expression, resource, expression, resource, expression, expression],
            ).fetchone()
            assert cpp == py == ([], None, None, False), expression
    finally:
        con.close()
        fallback.close()


def test_define_variable_rejects_invalid_call_shapes_in_cpp_and_fallback(monkeypatch) -> None:
    """FHIRPath §9 environment variables require a valid defineVariable name."""
    resource = json.dumps({"resourceType": "Patient", "id": "p1", "active": True})
    expressions = [
        "defineVariable()",
        "defineVariable(1)",
        "defineVariable(true, id)",
        "defineVariable({}, id)",
        "defineVariable('x', id, active)",
    ]

    con = _connection()
    monkeypatch.setattr(duckdb, "__version__", "0.0.0-forced-python-fallback")
    fallback = duckdb.connect(config={"allow_unsigned_extensions": True})
    assert register_fhirpath(fallback) is False
    try:
        for expression in expressions:
            cpp = con.execute(
                "SELECT fhirpath(?::JSON, ?), fhirpath_text(?::JSON, ?), fhirpath_json(?::JSON, ?), fhirpath_is_valid(?)",
                [resource, expression, resource, expression, resource, expression, expression],
            ).fetchone()
            py = fallback.execute(
                "SELECT fhirpath(?::JSON, ?), fhirpath_text(?::JSON, ?), fhirpath_json(?::JSON, ?), fhirpath_is_valid(?)",
                [resource, expression, resource, expression, resource, expression, expression],
            ).fetchone()
            assert cpp == py == ([], None, None, False), expression
    finally:
        con.close()
        fallback.close()
