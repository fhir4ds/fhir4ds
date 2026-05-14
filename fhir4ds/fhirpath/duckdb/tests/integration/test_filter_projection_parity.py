"""Parity tests for filtering/projection FHIRPath functions in DuckDB UDFs."""

from __future__ import annotations

import json

import duckdb

from fhir4ds.fhirpath.duckdb import register_fhirpath
from fhir4ds.fhirpath.duckdb.udf import fhirpath_json_udf, fhirpath_scalar, fhirpath_text_udf


OBSERVATION = json.dumps(
    {
        "resourceType": "Observation",
        "id": "o",
        "valueInteger": 5,
    }
)


def _connection() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect(config={"allow_unsigned_extensions": True})
    register_fhirpath(con)
    return con


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
