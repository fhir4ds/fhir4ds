"""Parity tests for FHIRPath extension() handling in DuckDB UDFs."""

from __future__ import annotations

import json

import duckdb

from fhir4ds.fhirpath.duckdb import register_fhirpath
from fhir4ds.fhirpath.duckdb.udf import fhirpath_json_udf, fhirpath_scalar, fhirpath_text_udf


def _connection() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect(config={"allow_unsigned_extensions": True})
    register_fhirpath(con)
    return con


def test_standalone_extension_value_matches_python_fallback() -> None:
    resource = json.dumps(
        {
            "resourceType": "Patient",
            "extension": [
                {
                    "url": "u",
                    "valueString": "x",
                }
            ],
        }
    )
    expression = "extension('u').value"

    con = _connection()
    try:
        cpp = con.execute(
            "SELECT fhirpath(?::JSON, ?), fhirpath_text(?::JSON, ?), fhirpath_json(?::JSON, ?)",
            [resource, expression, resource, expression, resource, expression],
        ).fetchone()
        py = (
            fhirpath_scalar(resource, expression),
            fhirpath_text_udf(resource, expression),
            fhirpath_json_udf(resource, expression),
        )
        assert cpp == py
        assert cpp == (["x"], "x", '["x"]')
    finally:
        con.close()
