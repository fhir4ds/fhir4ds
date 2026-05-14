"""Parity tests for FHIRPath existence functions in DuckDB UDFs."""

from __future__ import annotations

import json

import duckdb

from fhir4ds.fhirpath.duckdb import register_fhirpath
from fhir4ds.fhirpath.duckdb.udf import (
    fhirpath_json_udf,
    fhirpath_number_udf,
    fhirpath_scalar,
    fhirpath_text_udf,
)


RESOURCE = json.dumps(
    {
        "resourceType": "Patient",
        "id": "p",
        "vals": [1, 2, 2, 3],
    }
)


def _connection() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect(config={"allow_unsigned_extensions": True})
    register_fhirpath(con)
    return con


def test_distinct_multi_result_number_singleton_guard_matches_cpp() -> None:
    expression = "vals.distinct()"

    con = _connection()
    try:
        cpp = con.execute(
            "SELECT fhirpath(?::JSON, ?), fhirpath_text(?::JSON, ?), fhirpath_json(?::JSON, ?), fhirpath_number(?::JSON, ?)",
            [RESOURCE, expression, RESOURCE, expression, RESOURCE, expression, RESOURCE, expression],
        ).fetchone()
        py = (
            fhirpath_scalar(RESOURCE, expression),
            fhirpath_text_udf(RESOURCE, expression),
            fhirpath_json_udf(RESOURCE, expression),
            fhirpath_number_udf(RESOURCE, expression),
        )
        assert cpp == py
    finally:
        con.close()
