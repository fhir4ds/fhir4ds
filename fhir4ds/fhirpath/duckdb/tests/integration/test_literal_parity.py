"""Parity tests for FHIRPath literal handling in DuckDB UDFs."""

from __future__ import annotations

import duckdb

from fhir4ds.fhirpath.duckdb import register_fhirpath
from fhir4ds.fhirpath.duckdb.udf import fhirpath_json_udf, fhirpath_scalar, fhirpath_text_udf


RESOURCE = '{"resourceType":"Patient","id":"p"}'


def _connection() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect(config={"allow_unsigned_extensions": True})
    register_fhirpath(con)
    return con


def test_literal_time_outputs_match_python_fallback() -> None:
    expressions = ["@T14", "@T14:34", "@T14:34:28"]

    con = _connection()
    try:
        for expression in expressions:
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
    finally:
        con.close()


def test_invalid_date_and_time_literals_match_python_fallback() -> None:
    expressions = ["@2015-13", "@2015-02-30", "@T24:00", "@T23:60", "@T23:59:60"]

    con = _connection()
    try:
        for expression in expressions:
            cpp = con.execute("SELECT fhirpath(?::JSON, ?)", [RESOURCE, expression]).fetchone()[0]
            assert cpp == fhirpath_scalar(RESOURCE, expression)
            assert cpp == []
    finally:
        con.close()


def test_string_escape_outputs_match_python_fallback() -> None:
    expressions = [r"'O\'Connor'", r"'a\`b'", r"'a\"b'", r"'bad\x'"]

    con = _connection()
    try:
        for expression in expressions:
            cpp = con.execute("SELECT fhirpath(?::JSON, ?)", [RESOURCE, expression]).fetchone()[0]
            assert cpp == fhirpath_scalar(RESOURCE, expression)
    finally:
        con.close()


def test_datetime_integer_and_quantity_literals_match_python_fallback() -> None:
    expressions = [
        "2147483648",
        "@2015T",
        "@2015-02T",
        "@2015-02-04T",
        "@2015-02-04T14",
        "@2015-02-04T14:34",
        "@2015-02-04T14:34:28",
        "@2015-02-04T14:34:28+09:00",
        "@2015-13-04T14:34:28",
        "@2015-02-30T14:34:28",
        "@2015-02-04T24:00:00",
        "10 'mg'",
        "4 days",
        "0.5 'mg'",
    ]

    con = _connection()
    try:
        for expression in expressions:
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
    finally:
        con.close()


def test_malformed_literal_edges_match_python_fallback() -> None:
    expressions = [
        r"'short \u005'",
        r"'badhex \u00G1'",
        "@T01:02:03.1234",
        "@2015-02-04T14:34:28+09:99",
        "@2015-02-04T14:34:28-25:00",
    ]

    con = _connection()
    try:
        for expression in expressions:
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
    finally:
        con.close()
