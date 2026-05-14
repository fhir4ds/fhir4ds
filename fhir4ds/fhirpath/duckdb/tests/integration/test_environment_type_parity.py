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
