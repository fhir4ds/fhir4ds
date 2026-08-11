"""Parity tests for FHIRPath string search functions in DuckDB UDFs."""

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


def _all_public_outputs_with_valid(con: duckdb.DuckDBPyConnection, resource: str, expression: str):
    return con.execute(
        """
        SELECT
          fhirpath(?::JSON, ?),
          fhirpath_text(?::JSON, ?),
          fhirpath_json(?::JSON, ?),
          fhirpath_bool(?::JSON, ?),
          fhirpath_number(?::JSON, ?),
          fhirpath_is_valid(?)
        """,
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
            expression,
        ],
    ).fetchone()


def test_string_search_functions_match_cpp() -> None:
    resource = json.dumps(
        {
            "resourceType": "Patient",
            "s": "abcdef",
            "empty": "",
            "unicode": "café",
        }
    )
    expressions = [
        "s.indexOf('cd')",
        "s.indexOf('zz')",
        "s.indexOf('')",
        "empty.indexOf('a')",
        "s.substring(0)",
        "s.substring(2)",
        "s.substring(2, 3)",
        "s.substring(6)",
        "s.substring(0, 0)",
        "s.substring(99)",
        "s.substring(-1)",
        "s.substring(1, -1)",
        "s.substring(1, -4)",
        "s.startsWith('ab')",
        "s.startsWith('bc')",
        "s.startsWith('')",
        "s.endsWith('ef')",
        "s.endsWith('de')",
        "s.endsWith('')",
        "s.contains('cd')",
        "s.contains('zz')",
        "s.contains('')",
        "unicode.indexOf('é')",
        "unicode.substring(3, 1)",
    ]

    con = _connection()
    try:
        for expression in expressions:
            cpp = _all_public_outputs(con, resource, expression)
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


def test_string_search_invalid_types_match_python_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    resource = json.dumps(
        {
            "resourceType": "Patient",
            "s": "abc123",
            "num": 123,
            "flag": True,
            "arr": ["abc", "def"],
            "obj": {"code": "abc"},
        }
    )
    expressions = [
        "s.indexOf(123)",
        "s.indexOf(true)",
        "s.startsWith(123)",
        "s.startsWith(true)",
        "s.endsWith(123)",
        "s.contains(123)",
        "s.contains(true)",
        "s.substring('1')",
        "s.substring(1.5)",
        "s.substring(true)",
        "s.substring(1, '2')",
        "s.substring(1, 2.5)",
        "num.contains('2')",
        "flag.contains('r')",
        "obj.contains('code')",
        "arr.contains('b')",
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


def test_string_search_invalid_arity_matches_python_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    resource = json.dumps({"resourceType": "Patient", "s": "abcdef"})
    expressions = [
        "s.indexOf()",
        "s.indexOf('a', 'b')",
        "s.substring()",
        "s.substring(1, 2, 3)",
        "s.startsWith()",
        "s.startsWith('a', 'b')",
        "s.endsWith()",
        "s.endsWith('f', 'b')",
        "s.contains()",
        "s.contains('b', 'c')",
    ]

    native = _connection()
    fallback = _python_fallback_connection(monkeypatch)
    try:
        for expression in expressions:
            assert _all_public_outputs_with_valid(native, resource, expression) == (
                [],
                None,
                None,
                None,
                None,
                False,
            )
            assert _all_public_outputs_with_valid(fallback, resource, expression) == (
                [],
                None,
                None,
                None,
                None,
                False,
            )
    finally:
        native.close()
        fallback.close()


def test_string_search_constant_wrong_types_are_invalid_in_native_and_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    resource = json.dumps({"resourceType": "Patient"})
    expressions = [
        "'abc'.contains(1)",
        "'abc'.startsWith(1)",
        "'abc'.endsWith(1)",
        "1.indexOf('1')",
        "1.contains('1')",
        "'abc'.substring('1')",
        "'abc'.substring(1.5)",
        "'abc'.substring(1, '2')",
        "'abc'.substring(1, 2.5)",
    ]

    native = _connection()
    fallback = _python_fallback_connection(monkeypatch)
    try:
        for expression in expressions:
            assert _all_public_outputs_with_valid(native, resource, expression) == (
                [],
                None,
                None,
                None,
                None,
                False,
            )
            assert _all_public_outputs_with_valid(fallback, resource, expression) == (
                [],
                None,
                None,
                None,
                None,
                False,
            )
    finally:
        native.close()
        fallback.close()


def test_string_search_arguments_resolve_in_outer_focus(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    resource = json.dumps(
        {
            "resourceType": "Patient",
            "s": "abcdef",
            "term": "cd",
            "prefix": "ab",
            "suffix": "ef",
            "start": 2,
            "length": 3,
            "num": 123,
            "terms": ["a", "b"],
            "lens": [1, 2],
            "negLen": -4,
            "decLen": 1.5,
        }
    )
    expressions = [
        "s.indexOf(term)",
        "s.substring(start)",
        "s.substring(start, length)",
        "s.startsWith(prefix)",
        "s.endsWith(suffix)",
        "s.contains(term)",
        "s.indexOf(num)",
        "s.indexOf(terms)",
        "s.substring(1, lens)",
        "s.substring(1, negLen)",
        "s.substring(1, decLen)",
    ]

    native = _connection()
    fallback = _python_fallback_connection(monkeypatch)
    try:
        for expression in expressions:
            assert _all_public_outputs(native, resource, expression) == _all_public_outputs(
                fallback, resource, expression
            )
        assert _all_public_outputs(native, resource, "s.indexOf(term)")[4] == 2.0
        assert _all_public_outputs(native, resource, "s.substring(start, length)")[1] == "cde"
        assert _all_public_outputs(native, resource, "s.substring(1, negLen)")[1] == ""
        assert _all_public_outputs(native, resource, "s.startsWith(prefix)")[3] is True
        assert _all_public_outputs(native, resource, "s.endsWith(suffix)")[3] is True
        assert _all_public_outputs(native, resource, "s.contains(term)")[3] is True
    finally:
        native.close()
        fallback.close()


def test_string_search_literal_union_argument_validation_matches_native(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    resource = json.dumps({"resourceType": "Patient", "s": "abcdef"})
    cases = {
        "s.indexOf(('a'|'a'))": (["0"], "0", "[0]", False, 0.0, True),
        "s.indexOf(('a'|'b'))": ([], None, None, None, None, False),
        "s.substring((1|1))": (["bcdef"], "bcdef", '["bcdef"]', None, None, True),
        "s.substring((1|2))": ([], None, None, None, None, False),
        "s.substring(1, (1|1))": (["b"], "b", '["b"]', None, None, True),
        "s.substring(1, (1|2))": ([], None, None, None, None, False),
        "s.substring((1|1.0))": (["bcdef"], "bcdef", '["bcdef"]', None, None, True),
        "s.substring((1.0|1))": ([], None, None, None, None, False),
        "s.substring((1|1.0), (1|1.0))": (["b"], "b", '["b"]', None, None, True),
        "missing.indexOf(('a'|'b'))": ([], None, None, None, None, False),
        "missing.substring((1|2))": ([], None, None, None, None, False),
    }

    native = _connection()
    fallback = _python_fallback_connection(monkeypatch)
    try:
        for expression, expected in cases.items():
            assert _all_public_outputs_with_valid(native, resource, expression) == expected
            assert _all_public_outputs_with_valid(fallback, resource, expression) == expected
    finally:
        native.close()
        fallback.close()


def test_string_search_embedded_nul_byte_parity(monkeypatch: pytest.MonkeyPatch) -> None:
    """Regression test for FP-09 EXPLORER QA-001.

    JSON strings can validly contain U+0000 escaped as "\u0000" per RFC 8259 §7.
    FHIR R4 string datatype allows any Unicode character. The native C++
    extension previously truncated strings at embedded NUL bytes because
    yyjson_get_str() returns a NUL-terminated const char*, and
    std::string(const char*) construction stops at the first NUL. The fix
    uses yyjson_get_str() + yyjson_get_len() to preserve the full byte
    range. All §5.6 search functions (indexOf, substring, startsWith,
    endsWith, contains) plus length() must observe the same characters as
    the Python fallback.

    Note: expected strings containing U+0000 are built at runtime via
    chr(0) rather than written as Python string literals, because Python's
    parser rejects source files containing literal NUL bytes.
    """
    nul = chr(0)
    s_with_nul = "a" + nul + "b"  # 3 code points: 'a', U+0000, 'b'
    resource = json.dumps({"resourceType": "Patient", "s": s_with_nul})

    # Precompute the expected substring results that contain U+0000
    full_str = "a" + nul + "b"
    full_json = "[" + json.dumps(full_str) + "]"
    nul_json = "[" + json.dumps(nul) + "]"

    # Expression -> expected output tuple (canonical, text, json, bool, number, valid)
    cases = {
        # length counts code points: 3 (was wrongly 1 in native before fix)
        "s.length()": (["3"], "3", "[3]", None, 3.0, True),
        # indexOf finds 'a' at code-point index 0
        "s.indexOf('a')": (["0"], "0", "[0]", False, 0.0, True),
        # indexOf finds 'b' at code-point index 2 (was wrongly -1 in native before fix)
        "s.indexOf('b')": (["2"], "2", "[2]", None, 2.0, True),
        # indexOf of absent char returns -1
        "s.indexOf('x')": (["-1"], "-1", "[-1]", None, -1.0, True),
        # substring(0) returns full string 'a\\u0000b' as a String
        "s.substring(0)": ([full_str], full_str, full_json, None, None, True),
        # substring(0, 1) returns just 'a'
        "s.substring(0, 1)": (["a"], "a", '["a"]', None, None, True),
        # substring(1, 1) returns the NUL char (was wrongly {} in native before fix)
        "s.substring(1, 1)": ([nul], nul, nul_json, None, None, True),
        # substring(2) returns 'b'
        "s.substring(2)": (["b"], "b", '["b"]', None, None, True),
        # startsWith('a') is true
        "s.startsWith('a')": (["true"], "true", "[true]", True, None, True),
        # endsWith('b') is true (was wrongly false in native before fix)
        "s.endsWith('b')": (["true"], "true", "[true]", True, None, True),
        # contains('a') is true
        "s.contains('a')": (["true"], "true", "[true]", True, None, True),
        # contains('b') is true (was wrongly false in native before fix when NUL was the search target)
        "s.contains('b')": (["true"], "true", "[true]", True, None, True),
    }

    native = _connection()
    fallback = _python_fallback_connection(monkeypatch)
    try:
        for expression, expected in cases.items():
            assert _all_public_outputs_with_valid(native, resource, expression) == (
                expected[0],
                expected[1],
                expected[2],
                expected[3],
                expected[4],
                expected[5],
            ), f"native mismatch for {expression!r}"
            assert _all_public_outputs_with_valid(fallback, resource, expression) == (
                expected[0],
                expected[1],
                expected[2],
                expected[3],
                expected[4],
                expected[5],
            ), f"fallback mismatch for {expression!r}"
    finally:
        native.close()
        fallback.close()


def test_string_search_other_control_chars_preserved(monkeypatch: pytest.MonkeyPatch) -> None:
    """Regression test companion: confirm only U+0000 was the defect.

    Other control characters (U+0001, U+001F, U+0009) were always preserved
    correctly because they do not terminate std::string construction. This
    test guards against future regressions in the broader control-char space.
    """
    for ch in [chr(1), chr(0x1F), chr(9)]:
        s = "a" + ch + "b"
        resource = json.dumps({"resourceType": "Patient", "s": s})
        native = _connection()
        fallback = _python_fallback_connection(monkeypatch)
        try:
            for expression in [
                "s.length()",
                "s.indexOf('b')",
                "s.startsWith('a')",
                "s.endsWith('b')",
            ]:
                assert _all_public_outputs(native, resource, expression) == (
                    _all_public_outputs(fallback, resource, expression)
                ), f"control-char {ord(ch):04X} parity mismatch for {expression!r}"
            # Length must be 3 for all these inputs
            assert _all_public_outputs(native, resource, "s.length()")[4] == 3.0
        finally:
            native.close()
            fallback.close()
