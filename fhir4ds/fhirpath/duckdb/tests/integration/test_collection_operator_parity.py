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
