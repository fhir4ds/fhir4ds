"""Parity tests for FHIRPath arithmetic operators in DuckDB UDFs."""

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


def test_arithmetic_operators_match_cpp() -> None:
    resource = json.dumps(
        {
            "resourceType": "Observation",
            "a": 6,
            "b": 3,
            "c": 2.5,
            "zero": 0,
            "s": "hi",
        }
    )
    expressions = [
        "a + b",
        "a - b",
        "a * b",
        "a / b",
        "a div b",
        "a mod b",
        "a / zero",
        "a div zero",
        "a mod zero",
        "c + b",
        "c * b",
        "s & b",
        "{} & s",
        "s & {}",
        "1 'mg' + 2 'mg'",
        "2 'mg' - 1 'mg'",
        "2 'mg' * 3",
        "2 'mg' / 2",
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


def test_temporal_arithmetic_match_cpp() -> None:
    resource = json.dumps({"resourceType": "Observation"})
    expressions = [
        "@2015-02-04 + 1 day",
        "@2015-02-04 - 1 day",
        "@2015-02-04T10:00:00 + 2 hours",
        "@2015-02-04T10:00:00 - 30 minutes",
        "@T10:00:00 + 1 hour",
        "@T10:00:00 - 30 minutes",
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
