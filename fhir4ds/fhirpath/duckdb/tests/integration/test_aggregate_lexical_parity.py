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


def _fallback_connection(monkeypatch) -> duckdb.DuckDBPyConnection:
    monkeypatch.setattr(duckdb, "__version__", "0.0.0-forced-python-fallback")
    con = duckdb.connect()
    assert register_fhirpath(con) is False
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
            "back`tick": "bt",
            "line\nbreak": "lb",
            "omegaΩ": "unicode",
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
        "/* leading block */ id",
        "// leading line\nid",
        "`class`",
        "`div`",
        r"`back\`tick`",
        r"`line\nbreak`",
        r"`omega\u03A9`",
        "true",
        "false",
        "active = true",
        "'a' = 'a'",
        "'a' = 'A'",
        "'('",
        "'['",
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


def test_invalid_case_sensitive_quantity_unit_is_not_prefix_parsed(monkeypatch) -> None:
    con = _connection()
    fallback = _fallback_connection(monkeypatch)
    try:
        assert con.execute("SELECT fhirpath_is_valid('1 Month')").fetchone() == (False,)
        assert fallback.execute("SELECT fhirpath_is_valid('1 Month')").fetchone() == (False,)
    finally:
        con.close()
        fallback.close()


def test_no_whitespace_calendar_quantity_literals_match_cpp(monkeypatch) -> None:
    con = _connection()
    fallback = _fallback_connection(monkeypatch)
    try:
        for expression in ["1month", "1months", "1millisecond", "1year + 2months"]:
            native = con.execute(
                "SELECT fhirpath(?::JSON, ?), fhirpath_json(?::JSON, ?), fhirpath_is_valid(?)",
                ["{}", expression, "{}", expression, expression],
            ).fetchone()
            py = fallback.execute(
                "SELECT fhirpath(?::JSON, ?), fhirpath_json(?::JSON, ?), fhirpath_is_valid(?)",
                ["{}", expression, "{}", expression, expression],
            ).fetchone()
            assert native == py, expression
    finally:
        con.close()
        fallback.close()


def test_aggregate_scope_restoration_matches_cpp(monkeypatch) -> None:
    resource = json.dumps({"resourceType": "Patient", "id": "p"})
    expressions = [
        "(1|2).aggregate($this+$total, 0) + $total",
        "(1|2).aggregate($this+$total, 0) + $index",
        "(1|2).aggregate($this+$total, 0).combine($total)",
        "(1|2).aggregate($this+$total, 0).combine($index)",
        "(1|2).aggregate($this+$total, 0).combine($this)",
    ]

    con = _connection()
    fallback = _fallback_connection(monkeypatch)
    try:
        for expression in expressions:
            native = con.execute(
                "SELECT fhirpath(?::JSON, ?), fhirpath_json(?::JSON, ?), fhirpath_text(?::JSON, ?), fhirpath_is_valid(?)",
                [resource, expression, resource, expression, resource, expression, expression],
            ).fetchone()
            py = fallback.execute(
                "SELECT fhirpath(?::JSON, ?), fhirpath_json(?::JSON, ?), fhirpath_text(?::JSON, ?), fhirpath_is_valid(?)",
                [resource, expression, resource, expression, resource, expression, expression],
            ).fetchone()
            assert native == py, expression
    finally:
        con.close()
        fallback.close()
