"""Parity tests for FHIRPath conversion functions in DuckDB UDFs."""

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


RESOURCE = json.dumps({"resourceType": "Patient", "id": "p"})


def _connection() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect(config={"allow_unsigned_extensions": True})
    register_fhirpath(con)
    return con


def test_decimal_string_does_not_convert_to_integer() -> None:
    expression = "'1.0'.toInteger()"

    con = _connection()
    try:
        cpp = con.execute(
            "SELECT fhirpath(?::JSON, ?), fhirpath_text(?::JSON, ?), fhirpath_json(?::JSON, ?)",
            [RESOURCE, expression, RESOURCE, expression, RESOURCE, expression],
        ).fetchone()
        py = (
            fhirpath_scalar(RESOURCE, expression),
            fhirpath_text_udf(RESOURCE, expression),
            fhirpath_json_udf(RESOURCE, expression),
        )
        assert cpp == py
        assert cpp == ([], None, None)
    finally:
        con.close()


def test_date_datetime_and_decimal_conversion_match_cpp() -> None:
    resource = json.dumps(
        {
            "resourceType": "Patient",
            "d": "2015-02-04",
            "ym": "2015-02",
            "dt": "2015-02-04T14:34:28",
            "bool": True,
            "i": 1,
        }
    )
    expressions = ["dt.toDate()", "d.toDateTime()", "ym.toDateTime()", "bool.toDecimal()", "i.toDecimal()"]

    con = _connection()
    try:
        for expression in expressions:
            cpp = con.execute(
                "SELECT fhirpath(?::JSON, ?), fhirpath_text(?::JSON, ?), fhirpath_json(?::JSON, ?), fhirpath_number(?::JSON, ?)",
                [resource, expression, resource, expression, resource, expression, resource, expression],
            ).fetchone()
            py = (
                fhirpath_scalar(resource, expression),
                fhirpath_text_udf(resource, expression),
                fhirpath_json_udf(resource, expression),
                fhirpath_number_udf(resource, expression),
            )
            assert cpp == py
    finally:
        con.close()


def test_quantity_string_and_time_conversion_match_cpp() -> None:
    resource = json.dumps(
        {
            "resourceType": "Observation",
            "s": "abc",
            "t": "14:30:00",
            "tshort": "14:30",
            "badT": "25:00:00",
            "n": 5,
            "d": 1.5,
            "q": {"value": 5, "unit": "mg"},
            "qstr": "5 mg",
            "badQ": "abc mg",
            "date": "2015-02-04",
        }
    )
    expressions = [
        "n.toQuantity()",
        "d.toQuantity()",
        "qstr.toQuantity()",
        "badQ.toQuantity()",
        "n.toQuantity('mg')",
        "qstr.convertsToQuantity()",
        "q.toString()",
        "q.convertsToString()",
        "t.toTime()",
        "tshort.toTime()",
        "badT.toTime()",
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
