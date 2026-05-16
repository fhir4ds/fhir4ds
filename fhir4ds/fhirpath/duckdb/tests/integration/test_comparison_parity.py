"""Parity tests for FHIRPath comparison operators."""

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


def test_comparison_operators_match_cpp() -> None:
    resource = json.dumps(
        {
            "resourceType": "Observation",
            "a": 1,
            "b": 2,
            "arr": [1, 2],
            "s": "abc",
            "s2": "def",
        }
    )
    expressions = [
        "a < b",
        "b > a",
        "a <= b",
        "a <= a",
        "b >= a",
        "a >= a",
        "a > b",
        "a < {}",
        "{} < a",
        "arr < b",
        "s < s2",
        "s > s2",
        "@2015-02-04 < @2015-02-05",
        "@2015-02-04 <= @2015-02-04",
        "@2015-02 < @2015-03",
        "@2015-02 < @2015",
        "@2015-02-04T10:00:00 < @2015-02-04T11:00:00",
        "@T10:00:00 < @T11:00:00",
        "1 'mg' < 2 'mg'",
        "1 'mg' < 0.002 'g'",
        "1 'mg' <= 0.001 'g'",
        "1 'mg' > 2 'mg'",
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
