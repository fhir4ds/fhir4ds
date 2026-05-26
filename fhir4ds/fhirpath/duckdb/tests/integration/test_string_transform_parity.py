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


def _all_outputs_with_valid(con: duckdb.DuckDBPyConnection, resource: str, expression: str):
    return con.execute(
        "SELECT fhirpath(?::JSON, ?), fhirpath_text(?::JSON, ?), fhirpath_json(?::JSON, ?), fhirpath_bool(?::JSON, ?), fhirpath_number(?::JSON, ?), fhirpath_is_valid(?)",
        [resource, expression, resource, expression, resource, expression, resource, expression, resource, expression, expression],
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
            "latin_ext": "ČŽŠ",
            "latin_ext_lower": "čžš",
            "turkish_upper": "İSTANBUL",
            "turkish_lower": "ıstanbul",
            "greek_accent_lower": "άέήίόύώ",
            "greek_accent_upper": "ΆΈΉΊΌΎΏ",
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
        "latin_ext.lower()",
        "latin_ext_lower.upper()",
        "turkish_upper.lower()",
        "turkish_lower.upper()",
        "greek_accent_lower.upper()",
        "greek_accent_upper.lower()",
        "s.length()",
        "empty.length()",
        "unicode.length()",
        "s.replace('abc','X')",
        "s.replace('','-')",
        "s.replace('z','X')",
        "empty.replace('z','x')",
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
        "arr.length()",
        "123.upper()",
        "123.replace('2','x')",
        "num.toChars()",
        "flag.toChars()",
        "s.matches('(a+)+')",
        "s.matches('[invalid')",
        "s.replaceMatches('(a|aa)+','x')",
        "s.replaceMatches('[invalid','x')",
        "'abc'.matches('(a+)+')",
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


def test_string_transform_dynamic_arguments_match_python_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    resource = json.dumps(
        {
            "resourceType": "Patient",
            "s": "Abc abc",
            "pattern": "abc",
            "sub": "X",
            "regex": "[a-z]+",
        }
    )
    expressions = [
        ("s.replace(pattern, sub)", (["Abc X"], "Abc X", '["Abc X"]', None, None)),
        ("s.matches(regex)", (["false"], "false", "[false]", False, None)),
        ("s.replaceMatches(regex, sub)", (["AX X"], "AX X", '["AX X"]', None, None)),
    ]

    native = _connection()
    fallback = _python_fallback_connection(monkeypatch)
    try:
        for expression, expected in expressions:
            assert _all_public_outputs(native, resource, expression) == expected
            assert _all_public_outputs(fallback, resource, expression) == expected
    finally:
        native.close()
        fallback.close()


def test_string_transform_invalid_signatures_and_regex_validation_match_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    resource = json.dumps({"resourceType": "Patient", "s": "Abc abc"})
    overlong_pattern = "a" * 1001
    expressions = [
        "s.upper(1)",
        "s.lower(1)",
        "s.replace('a')",
        "s.replace('a', 'b', 'c')",
        "s.matches()",
        "s.matches('a', 'b')",
        "s.replaceMatches('a')",
        "s.replaceMatches('a', 'b', 'c')",
        "s.length(1)",
        "s.toChars(1)",
        "s.replace(123, 'x')",
        "s.replace('a', 123)",
        "s.matches('(a+)+')",
        "s.replaceMatches('(a|aa)+', 'x')",
        "s.matches('[invalid')",
        "s.replaceMatches('[invalid', 'x')",
        f"s.matches('{overlong_pattern}')",
        f"s.replaceMatches('{overlong_pattern}', 'x')",
    ]

    native = _connection()
    fallback = _python_fallback_connection(monkeypatch)
    try:
        for expression in expressions:
            expected = ([], None, None, None, None, False)
            assert _all_outputs_with_valid(native, resource, expression) == expected
            assert _all_outputs_with_valid(fallback, resource, expression) == expected
    finally:
        native.close()
        fallback.close()
