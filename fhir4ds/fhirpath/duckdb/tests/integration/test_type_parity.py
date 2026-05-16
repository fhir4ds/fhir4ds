"""Parity tests for FHIRPath type operators."""

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


def test_type_operators_match_cpp() -> None:
    resource = json.dumps(
        {
            "resourceType": "Observation",
            "i": 1,
            "d": 1.5,
            "s": "abc",
            "b": True,
            "date": "2015-02-04",
            "dt": "2015-02-04T10:00:00",
            "arr": [1, 2],
        }
    )
    expressions = [
        "i is Integer",
        "d is Decimal",
        "s is String",
        "b is Boolean",
        "i is Decimal",
        "i.is(Integer)",
        "d.is(Decimal)",
        "s.is(String)",
        "b.is(Boolean)",
        "i.as(Integer)",
        "d.as(Decimal)",
        "s.as(String)",
        "b.as(Boolean)",
        "s.as(Integer)",
        "arr.is(Integer)",
        "arr.as(Integer)",
        "date.toDate() is Date",
        "dt.toDateTime() is DateTime",
        "5 'mg' is Quantity",
        "5 'mg'.is(Quantity)",
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
