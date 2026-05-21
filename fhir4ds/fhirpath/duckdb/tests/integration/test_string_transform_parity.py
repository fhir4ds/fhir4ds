"""Parity tests for FHIRPath string transform functions in DuckDB UDFs."""

from __future__ import annotations

import json

import duckdb
import pytest

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


def _python_fallback_connection(monkeypatch: pytest.MonkeyPatch) -> duckdb.DuckDBPyConnection:
    monkeypatch.setattr(duckdb, "__version__", "0.0.0-forced-python-fallback")
    con = duckdb.connect(config={"allow_unsigned_extensions": True})
    assert register_fhirpath(con) is False
    return con


def _all_public_outputs(con: duckdb.DuckDBPyConnection, resource: str, expression: str):
    return con.execute(
        "SELECT fhirpath(?::JSON, ?), fhirpath_text(?::JSON, ?), fhirpath_json(?::JSON, ?), fhirpath_bool(?::JSON, ?), fhirpath_number(?::JSON, ?)",
        [resource, expression, resource, expression, resource, expression, resource, expression, resource, expression],
    ).fetchone()


def test_string_transform_functions_match_cpp() -> None:
    resource = json.dumps(
        {
            "resourceType": "Patient",
            "s": "Abc abc",
            "empty": "",
            "unicode": "café",
            "accent": "é",
            "emoji": "😀",
            "sharp": "Straße",
            "sigma": "Σςσ",
            "multiline": "a\nb",
            "digits": "abc123",
        }
    )
    expressions = [
        "s.upper()",
        "s.lower()",
        "unicode.upper()",
        "unicode.lower()",
        "accent.matches('.')",
        "accent.replaceMatches('.', 'x')",
        "emoji.matches('.')",
        "emoji.replaceMatches('.', 'x')",
        "sharp.upper()",
        "sharp.upper().length()",
        "sigma.upper()",
        "sigma.lower().upper()",
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


def test_string_transform_invalid_types_match_python_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    resource = json.dumps(
        {
            "resourceType": "Patient",
            "s": "Abc abc",
            "num": 123,
            "flag": True,
            "arr": ["abc", "def"],
        }
    )
    expressions = [
        "num.matches('123')",
        "flag.matches('true')",
        "s.matches(123)",
        "s.replace(123,'x')",
        "s.replace('b',123)",
        "num.replaceMatches('2','x')",
        "flag.replaceMatches('true','x')",
        "s.replaceMatches(123,'x')",
        "s.replaceMatches('b',123)",
        "num.toChars()",
        "flag.toChars()",
        "s.matches('(a+)+')",
        "s.replaceMatches('(a|aa)+','x')",
    ]

    native = _connection()
    fallback = _python_fallback_connection(monkeypatch)
    try:
        for expression in expressions:
            assert _all_public_outputs(native, resource, expression) == _all_public_outputs(
                fallback, resource, expression
            )
    finally:
        native.close()
        fallback.close()
