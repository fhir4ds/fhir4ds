"""Parity checks that force the Python DuckDB fallback registration path."""

from __future__ import annotations

import json

import duckdb

from fhir4ds.fhirpath.duckdb import register_fhirpath


RESOURCE = json.dumps(
    {
        "resourceType": "Patient",
        "id": "p",
        "active": True,
        "yearDate": "1990",
        "monthDate": "1990-06",
        "fullDate": "1990-06-15",
        "dateTimeValue": "1990-06-15T10:30:00Z",
        "badMonth": "1990-13",
        "badDay": "2023-02-29",
        "word": "true",
        "decimalText": "3.14",
    }
)


def _cpp_connection() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect(config={"allow_unsigned_extensions": True})
    assert register_fhirpath(con) is True
    return con


def _python_fallback_connection(monkeypatch) -> duckdb.DuckDBPyConnection:
    monkeypatch.setattr(duckdb, "__version__", "0.0.0-forced-python-fallback")
    con = duckdb.connect(config={"allow_unsigned_extensions": True})
    assert register_fhirpath(con) is False
    return con


def test_fhirpath_date_forced_python_fallback_matches_cpp(monkeypatch) -> None:
    cases = {
        "yearDate": "1990",
        "monthDate": "1990-06",
        "fullDate": "1990-06-15",
        "dateTimeValue": "1990-06-15",
        "badMonth": None,
        "badDay": None,
        "word": None,
        "decimalText": None,
        "true": None,
        "'true'": None,
        "3.14": None,
        "@2015-02": "2015-02",
        "@2015-02-04": "2015-02-04",
        "@2015-02-04T14:34:28": "2015-02-04",
        "@2015T": None,
        "@2015-02T": None,
    }

    cpp = _cpp_connection()
    py = _python_fallback_connection(monkeypatch)
    try:
        for expression, expected in cases.items():
            cpp_result = cpp.execute(
                "SELECT fhirpath_date(?::JSON, ?)", [RESOURCE, expression]
            ).fetchone()
            py_result = py.execute(
                "SELECT fhirpath_date(?::JSON, ?)", [RESOURCE, expression]
            ).fetchone()
            assert cpp_result == py_result == (expected,), expression
    finally:
        cpp.close()
        py.close()
