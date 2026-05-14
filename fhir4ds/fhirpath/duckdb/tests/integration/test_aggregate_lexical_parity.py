"""Parity tests for FHIRPath aggregate and lexical behavior in DuckDB UDFs."""

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


def test_aggregate_and_lexical_forms_match_cpp() -> None:
    resource = json.dumps(
        {
            "resourceType": "Patient",
            "id": "p1",
            "active": True,
            "value": 3,
            "class": "vip",
            "div": 7,
            "a": [1, 2, 3],
        }
    )
    expressions = [
        "(1|2|3).aggregate($this+$total, 0)",
        "(1|2|3).aggregate($this+$total)",
        "(1|2|3).aggregate(iif($total.empty(), $this, $this+$total))",
        "a.aggregate($this+$total, 0)",
        "  id  ",
        "id/* block */",
        "id // line comment",
        "`class`",
        "`div`",
        "true",
        "false",
        "active = true",
        "'a' = 'a'",
        "'a' = 'A'",
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
