"""Parity tests for FHIRPath boolean logic operators."""

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


def test_boolean_logic_operators_match_cpp() -> None:
    resource = json.dumps(
        {
            "resourceType": "Patient",
            "t": True,
            "f": False,
            "arr": [True, False],
            "s": "x",
        }
    )
    expressions = [
        "t and t",
        "t and f",
        "f and t",
        "f and f",
        "t or f",
        "f or f",
        "t xor f",
        "t xor t",
        "t implies f",
        "f implies t",
        "t.not()",
        "f.not()",
        "{}.not()",
        "{} and t",
        "{} or t",
        "{} or f",
        "{} implies f",
        "t and {}",
        "f and {}",
        "arr and t",
        "s and t",
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
