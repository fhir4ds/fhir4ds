"""Parity tests for FHIRPath math functions in DuckDB UDFs."""

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


def test_math_functions_match_cpp() -> None:
    resource = json.dumps(
        {
            "resourceType": "Observation",
            "i": -5,
            "d": -2.5,
            "p": 2.5,
            "zero": 0,
            "one": 1,
        }
    )
    expressions = [
        "i.abs()",
        "d.abs()",
        "p.ceiling()",
        "d.ceiling()",
        "p.floor()",
        "d.floor()",
        "p.truncate()",
        "d.truncate()",
        "p.round()",
        "p.round(1)",
        "d.round()",
        "one.exp()",
        "one.ln()",
        "p.log(10)",
        "p.power(2)",
        "p.sqrt()",
        "zero.sqrt()",
        "d.sqrt()",
        "zero.ln()",
        "zero.log(10)",
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
