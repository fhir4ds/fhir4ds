"""Parity tests for FHIRPath string search functions in DuckDB UDFs."""

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


def test_string_search_functions_match_cpp() -> None:
    resource = json.dumps(
        {
            "resourceType": "Patient",
            "s": "abcdef",
            "empty": "",
            "unicode": "café",
        }
    )
    expressions = [
        "s.indexOf('cd')",
        "s.indexOf('zz')",
        "s.indexOf('')",
        "empty.indexOf('a')",
        "s.substring(0)",
        "s.substring(2)",
        "s.substring(2, 3)",
        "s.substring(0, 0)",
        "s.substring(99)",
        "s.substring(-1)",
        "s.substring(1, -1)",
        "s.startsWith('ab')",
        "s.startsWith('bc')",
        "s.startsWith('')",
        "s.endsWith('ef')",
        "s.endsWith('de')",
        "s.endsWith('')",
        "s.contains('cd')",
        "s.contains('zz')",
        "s.contains('')",
        "unicode.indexOf('é')",
        "unicode.substring(3, 1)",
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
