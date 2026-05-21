"""Parity tests for FHIRPath literal handling in DuckDB UDFs."""

from __future__ import annotations

import json

import duckdb

from fhir4ds.fhirpath.duckdb import register_fhirpath
from fhir4ds.fhirpath.duckdb.udf import fhirpath_json_udf, fhirpath_scalar, fhirpath_text_udf


RESOURCE = '{"resourceType":"Patient","id":"p"}'


def _connection() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect(config={"allow_unsigned_extensions": True})
    register_fhirpath(con)
    return con


def _python_fallback_connection() -> duckdb.DuckDBPyConnection:
    original_version = duckdb.__version__
    duckdb.__version__ = "0.0.0-forced-python-fallback"
    try:
        con = duckdb.connect(config={"allow_unsigned_extensions": True})
        assert register_fhirpath(con) is False
        return con
    finally:
        duckdb.__version__ = original_version


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
    expressions = [
        r"'O\'Connor'",
        r"'a\`b'",
        r"'a\"b'",
        r"'bad\x'",
        r"'\u00E9'",
        r"'\u03A9'",
    ]

    con = _connection()
    try:
        for expression in expressions:
            cpp = con.execute("SELECT fhirpath(?::JSON, ?)", [RESOURCE, expression]).fetchone()[0]
            assert cpp == fhirpath_scalar(RESOURCE, expression)
    finally:
        con.close()


def test_unicode_hex_letter_string_escapes_match_spec() -> None:
    cases = {r"'\u00E9'": "\u00e9", r"'\u03A9'": "\u03a9"}

    con = _connection()
    try:
        for expression, expected in cases.items():
            cpp = con.execute(
                "SELECT fhirpath(?::JSON, ?), fhirpath_text(?::JSON, ?), fhirpath_json(?::JSON, ?)",
                [RESOURCE, expression, RESOURCE, expression, RESOURCE, expression],
            ).fetchone()
            py = (
                fhirpath_scalar(RESOURCE, expression),
                fhirpath_text_udf(RESOURCE, expression),
                fhirpath_json_udf(RESOURCE, expression),
            )
            assert cpp == py == ([expected], expected, f'["{expected}"]')
    finally:
        con.close()


def test_double_backslash_string_escapes_match_spec_and_backends() -> None:
    cases = {
        r"'\\p'": r"\p",
        r"'slash\\end'": r"slash\end",
        r"'\u005Cp'": r"\p",
        r"'abc\'": "abc",
    }

    cpp = _connection()
    py = _python_fallback_connection()
    try:
        for expression, expected in cases.items():
            expected_row = ([expected], expected, json.dumps([expected], separators=(",", ":")))
            cpp_row = cpp.execute(
                "SELECT fhirpath(?::JSON, ?), fhirpath_text(?::JSON, ?), fhirpath_json(?::JSON, ?)",
                [RESOURCE, expression, RESOURCE, expression, RESOURCE, expression],
            ).fetchone()
            py_row = py.execute(
                "SELECT fhirpath(?::JSON, ?), fhirpath_text(?::JSON, ?), fhirpath_json(?::JSON, ?)",
                [RESOURCE, expression, RESOURCE, expression, RESOURCE, expression],
            ).fetchone()
            assert cpp_row == py_row == expected_row
    finally:
        cpp.close()
        py.close()


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


def test_partial_datetime_timezone_offsets_match_python_fallback() -> None:
    cases = {
        "@2014-01-25T14Z": (["2014-01-25T14Z"], "2014-01-25T14Z", '["2014-01-25T14Z"]'),
        "@2014-01-25T14+09:00": (
            ["2014-01-25T14+09:00"],
            "2014-01-25T14+09:00",
            '["2014-01-25T14+09:00"]',
        ),
        "@2014-01-25T14:30Z": (
            ["2014-01-25T14:30Z"],
            "2014-01-25T14:30Z",
            '["2014-01-25T14:30Z"]',
        ),
        "@2014-01-25T14:30+09:00": (
            ["2014-01-25T14:30+09:00"],
            "2014-01-25T14:30+09:00",
            '["2014-01-25T14:30+09:00"]',
        ),
        "@2014-01-25T14+99:99": ([], None, None),
        "@2014-01-25T14:30+99:99": ([], None, None),
    }

    cpp = _connection()
    py = _python_fallback_connection()
    try:
        for expression, expected in cases.items():
            cpp_row = cpp.execute(
                "SELECT fhirpath(?::JSON, ?), fhirpath_text(?::JSON, ?), fhirpath_json(?::JSON, ?)",
                [RESOURCE, expression, RESOURCE, expression, RESOURCE, expression],
            ).fetchone()
            py_row = py.execute(
                "SELECT fhirpath(?::JSON, ?), fhirpath_text(?::JSON, ?), fhirpath_json(?::JSON, ?)",
                [RESOURCE, expression, RESOURCE, expression, RESOURCE, expression],
            ).fetchone()
            assert cpp_row == py_row == expected
    finally:
        cpp.close()
        py.close()


def test_malformed_temporal_literal_shapes_are_invalid_in_both_backends() -> None:
    expressions = ["@2014-1", "@2014-01-2", "@2014-01-25T14+09", "@T14:3"]

    cpp = _connection()
    py = _python_fallback_connection()
    try:
        for expression in expressions:
            cpp_result = cpp.execute("SELECT fhirpath_is_valid(?)", [expression]).fetchone()
            py_result = py.execute("SELECT fhirpath_is_valid(?)", [expression]).fetchone()
            assert cpp_result == py_result == (False,)
    finally:
        cpp.close()
        py.close()


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
