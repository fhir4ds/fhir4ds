"""Parity tests for FHIRPath string transform functions in DuckDB UDFs."""

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


def test_string_transform_functions_match_cpp() -> None:
    resource = json.dumps(
        {
            "resourceType": "Patient",
            "s": "Abc abc",
            "empty": "",
            "unicode": "café",
            "multiline": "a\nb",
            "digits": "abc123",
        }
    )
    expressions = [
        "s.upper()",
        "s.lower()",
        "unicode.upper()",
        "unicode.lower()",
        "s.length()",
        "empty.length()",
        "unicode.length()",
        "s.replace('abc','X')",
        "s.replace('','-')",
        "s.replace('z','X')",
        "empty.replace('','x')",
        "s.matches('^Abc')",
        "s.matches('abc$')",
        "s.matches('A.*c')",
        "multiline.matches('a.b')",
        "digits.matches('[a-z]+[0-9]+')",
        "s.replaceMatches('abc','X')",
        "s.replaceMatches('[A-Z]','x')",
        "s.replaceMatches('','-')",
        "s.toChars()",
        "empty.toChars()",
        "unicode.toChars()",
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
