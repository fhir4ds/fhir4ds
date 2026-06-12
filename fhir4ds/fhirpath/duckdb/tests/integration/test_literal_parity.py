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


def test_unicode_surrogate_pair_string_escapes_match_spec_and_backends() -> None:
    expression = r"'\uD834\uDD1E'"
    expected = "\U0001D11E"
    expected_row = ([expected], expected, json.dumps([expected], ensure_ascii=False, separators=(",", ":")), True)

    py = _python_fallback_connection()
    cpp = _connection()
    try:
        cpp_row = cpp.execute(
            "SELECT fhirpath(?::JSON, ?), fhirpath_text(?::JSON, ?), fhirpath_json(?::JSON, ?), fhirpath_is_valid(?)",
            [RESOURCE, expression, RESOURCE, expression, RESOURCE, expression, expression],
        ).fetchone()
        py_row = py.execute(
            "SELECT fhirpath(?::JSON, ?), fhirpath_text(?::JSON, ?), fhirpath_json(?::JSON, ?), fhirpath_is_valid(?)",
            [RESOURCE, expression, RESOURCE, expression, RESOURCE, expression, expression],
        ).fetchone()
        assert cpp_row == py_row == expected_row
    finally:
        cpp.close()
        py.close()


def test_unpaired_unicode_surrogate_string_escapes_are_invalid_in_both_backends() -> None:
    expressions = [
        r"'\uD834'",
        r"'\uDD1E'",
        r"'\uD834\u0041'",
        r"'\uD834x'",
    ]

    py = _python_fallback_connection()
    cpp = _connection()
    try:
        for expression in expressions:
            query = """
                SELECT
                    fhirpath(?::JSON, ?),
                    fhirpath_text(?::JSON, ?),
                    fhirpath_json(?::JSON, ?),
                    fhirpath_is_valid(?)
            """
            params = [
                RESOURCE,
                expression,
                RESOURCE,
                expression,
                RESOURCE,
                expression,
                expression,
            ]
            assert cpp.execute(query, params).fetchone() == ([], None, None, False)
            assert py.execute(query, params).fetchone() == ([], None, None, False)
    finally:
        cpp.close()
        py.close()


def test_double_backslash_string_escapes_match_spec_and_backends() -> None:
    cases = {
        r"'\\p'": r"\p",
        r"'slash\\end'": r"slash\end",
        r"'\u005Cp'": r"\p",
        r"'abc\'": "abc",
    }

    py = _python_fallback_connection()
    cpp = _connection()
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


def test_no_whitespace_quoted_quantity_literals_match_spec_and_backends() -> None:
    expression = "10'mg'"
    expected_row = (["10 'mg'"], "10 'mg'", '[{"value":10,"unit":"mg"}]', "10 'mg'", True)

    py = _python_fallback_connection()
    cpp = _connection()
    try:
        cpp_row = cpp.execute(
            "SELECT fhirpath(?::JSON, ?), fhirpath_text(?::JSON, ?), fhirpath_json(?::JSON, ?), fhirpath_quantity(?::JSON, ?), fhirpath_is_valid(?)",
            [RESOURCE, expression, RESOURCE, expression, RESOURCE, expression, RESOURCE, expression, expression],
        ).fetchone()
        py_row = py.execute(
            "SELECT fhirpath(?::JSON, ?), fhirpath_text(?::JSON, ?), fhirpath_json(?::JSON, ?), fhirpath_quantity(?::JSON, ?), fhirpath_is_valid(?)",
            [RESOURCE, expression, RESOURCE, expression, RESOURCE, expression, RESOURCE, expression, expression],
        ).fetchone()
        assert cpp_row == py_row == expected_row
    finally:
        cpp.close()
        py.close()


def test_quantity_literal_unit_escapes_and_empty_units_match_spec_and_backends() -> None:
    valid_expression = r"10'\u006Dg'"
    valid_expected = (["10 'mg'"], "10 'mg'", '[{"value":10,"unit":"mg"}]', "10 'mg'", True)
    invalid_expression = "1 ''"

    py = _python_fallback_connection()
    cpp = _connection()
    try:
        cpp_row = cpp.execute(
            "SELECT fhirpath(?::JSON, ?), fhirpath_text(?::JSON, ?), fhirpath_json(?::JSON, ?), fhirpath_quantity(?::JSON, ?), fhirpath_is_valid(?)",
            [
                RESOURCE,
                valid_expression,
                RESOURCE,
                valid_expression,
                RESOURCE,
                valid_expression,
                RESOURCE,
                valid_expression,
                valid_expression,
            ],
        ).fetchone()
        py_row = py.execute(
            "SELECT fhirpath(?::JSON, ?), fhirpath_text(?::JSON, ?), fhirpath_json(?::JSON, ?), fhirpath_quantity(?::JSON, ?), fhirpath_is_valid(?)",
            [
                RESOURCE,
                valid_expression,
                RESOURCE,
                valid_expression,
                RESOURCE,
                valid_expression,
                RESOURCE,
                valid_expression,
                valid_expression,
            ],
        ).fetchone()
        assert cpp_row == py_row == valid_expected

        cpp_invalid = cpp.execute(
            "SELECT fhirpath(?::JSON, ?), fhirpath_text(?::JSON, ?), fhirpath_json(?::JSON, ?), fhirpath_quantity(?::JSON, ?), fhirpath_is_valid(?)",
            [
                RESOURCE,
                invalid_expression,
                RESOURCE,
                invalid_expression,
                RESOURCE,
                invalid_expression,
                RESOURCE,
                invalid_expression,
                invalid_expression,
            ],
        ).fetchone()
        py_invalid = py.execute(
            "SELECT fhirpath(?::JSON, ?), fhirpath_text(?::JSON, ?), fhirpath_json(?::JSON, ?), fhirpath_quantity(?::JSON, ?), fhirpath_is_valid(?)",
            [
                RESOURCE,
                invalid_expression,
                RESOURCE,
                invalid_expression,
                RESOURCE,
                invalid_expression,
                RESOURCE,
                invalid_expression,
                invalid_expression,
            ],
        ).fetchone()
        assert cpp_invalid == py_invalid == ([], None, None, None, False)
    finally:
        cpp.close()
        py.close()


def test_type_specific_literal_wrappers_reject_wrong_literal_types() -> None:
    wrong_type_cases = [
        "true",
        "false",
        r"'text'",
        r"'\uD834\uDD1E'",
        "45",
        "0.1",
        "@2014",
        "@T14:34",
    ]
    typed_cases = {
        "@2014T": ("2014T", None),
        "@2014-01-25T14:34:28+09:00": ("2014-01-25T14:34:28+09:00", None),
        "10 'mg'": (None, "10 'mg'"),
        "4 days": (None, "4 days"),
    }

    py = _python_fallback_connection()
    cpp = _connection()
    try:
        for expression in wrong_type_cases:
            cpp_row = cpp.execute(
                "SELECT fhirpath_timestamp(?::JSON, ?), fhirpath_quantity(?::JSON, ?)",
                [RESOURCE, expression, RESOURCE, expression],
            ).fetchone()
            py_row = py.execute(
                "SELECT fhirpath_timestamp(?::JSON, ?), fhirpath_quantity(?::JSON, ?)",
                [RESOURCE, expression, RESOURCE, expression],
            ).fetchone()
            assert cpp_row == py_row == (None, None)

        for expression, expected in typed_cases.items():
            cpp_row = cpp.execute(
                "SELECT fhirpath_timestamp(?::JSON, ?), fhirpath_quantity(?::JSON, ?)",
                [RESOURCE, expression, RESOURCE, expression],
            ).fetchone()
            py_row = py.execute(
                "SELECT fhirpath_timestamp(?::JSON, ?), fhirpath_quantity(?::JSON, ?)",
                [RESOURCE, expression, RESOURCE, expression],
            ).fetchone()
            assert cpp_row == py_row == expected
    finally:
        cpp.close()
        py.close()


def test_year_zero_temporal_literals_are_invalid_in_both_backends() -> None:
    expressions = [
        "@0000",
        "@0000-01",
        "@0000-01-01",
        "@0000T",
        "@0000-01-01T00:00",
    ]

    py = _python_fallback_connection()
    cpp = _connection()
    try:
        for expression in expressions:
            cpp_row = cpp.execute(
                "SELECT fhirpath(?::JSON, ?), fhirpath_text(?::JSON, ?), fhirpath_json(?::JSON, ?), fhirpath_date(?::JSON, ?), fhirpath_timestamp(?::JSON, ?), fhirpath_is_valid(?)",
                [
                    RESOURCE,
                    expression,
                    RESOURCE,
                    expression,
                    RESOURCE,
                    expression,
                    RESOURCE,
                    expression,
                    RESOURCE,
                    expression,
                    expression,
                ],
            ).fetchone()
            py_row = py.execute(
                "SELECT fhirpath(?::JSON, ?), fhirpath_text(?::JSON, ?), fhirpath_json(?::JSON, ?), fhirpath_date(?::JSON, ?), fhirpath_timestamp(?::JSON, ?), fhirpath_is_valid(?)",
                [
                    RESOURCE,
                    expression,
                    RESOURCE,
                    expression,
                    RESOURCE,
                    expression,
                    RESOURCE,
                    expression,
                    RESOURCE,
                    expression,
                    expression,
                ],
            ).fetchone()
            assert cpp_row == py_row == ([], None, None, None, None, False)
    finally:
        cpp.close()
        py.close()


def test_invalid_timezone_suffixed_date_literals_are_invalid_in_both_backends() -> None:
    expressions = ["@2014Z", "@2014-01Z", "@2014-01-25Z", "@2014TZ"]

    py = _python_fallback_connection()
    cpp = _connection()
    try:
        for expression in expressions:
            assert cpp.execute("SELECT fhirpath_is_valid(?)", [expression]).fetchone() == (False,)
            assert py.execute("SELECT fhirpath_is_valid(?)", [expression]).fetchone() == (False,)
    finally:
        cpp.close()
        py.close()


def test_datetime_timezone_offset_bounds_match_spec_and_backends() -> None:
    valid_expressions = [
        "@2016-02-29T23:59:59.123+14:00",
        "@2016-02-29T23:59:59.123-14:00",
        "@2016-02-29T23:59:59.123+13:59",
    ]
    invalid_expressions = [
        "@2016-02-29T23:59:59.123+14:01",
        "@2016-02-29T23:59:59.123-14:01",
        "@2016-02-29T23:59:59.123+15:00",
        "@2016-02-29T23:59:59.123-15:00",
    ]

    py = _python_fallback_connection()
    cpp = _connection()
    try:
        for expression in valid_expressions:
            assert cpp.execute("SELECT fhirpath_is_valid(?)", [expression]).fetchone() == (True,)
            assert py.execute("SELECT fhirpath_is_valid(?)", [expression]).fetchone() == (True,)
        for expression in invalid_expressions:
            assert cpp.execute("SELECT fhirpath_is_valid(?)", [expression]).fetchone() == (False,)
            assert py.execute("SELECT fhirpath_is_valid(?)", [expression]).fetchone() == (False,)
    finally:
        cpp.close()
        py.close()


def test_integer_literal_range_matches_spec_and_backends() -> None:
    valid_cases = {
        "2147483647": ["2147483647"],
        "(-2147483648)": ["-2147483648"],
    }
    invalid_cases = ["2147483648", "(-2147483649)", "9223372036854775808"]

    py = _python_fallback_connection()
    cpp = _connection()
    try:
        for expression, expected in valid_cases.items():
            assert cpp.execute("SELECT fhirpath_is_valid(?)", [expression]).fetchone() == (True,)
            assert py.execute("SELECT fhirpath_is_valid(?)", [expression]).fetchone() == (True,)
            assert cpp.execute("SELECT fhirpath(?::JSON, ?)", [RESOURCE, expression]).fetchone() == (expected,)
            assert py.execute("SELECT fhirpath(?::JSON, ?)", [RESOURCE, expression]).fetchone() == (expected,)

        for expression in invalid_cases:
            assert cpp.execute("SELECT fhirpath_is_valid(?)", [expression]).fetchone() == (False,)
            assert py.execute("SELECT fhirpath_is_valid(?)", [expression]).fetchone() == (False,)
    finally:
        cpp.close()
        py.close()


def test_pathological_mixed_literal_chain_matches_backends() -> None:
    expression = "(true | false | 'x' | 1 | 1.0 | @2014 | @T14 | @2014T | 1 'mg').select($this.toString()).count()"
    expected = (["8"], "8", "[8]", 8.0, True)

    py = _python_fallback_connection()
    cpp = _connection()
    try:
        cpp_row = cpp.execute(
            "SELECT fhirpath(?::JSON, ?), fhirpath_text(?::JSON, ?), fhirpath_json(?::JSON, ?), fhirpath_number(?::JSON, ?), fhirpath_is_valid(?)",
            [RESOURCE, expression, RESOURCE, expression, RESOURCE, expression, RESOURCE, expression, expression],
        ).fetchone()
        py_row = py.execute(
            "SELECT fhirpath(?::JSON, ?), fhirpath_text(?::JSON, ?), fhirpath_json(?::JSON, ?), fhirpath_number(?::JSON, ?), fhirpath_is_valid(?)",
            [RESOURCE, expression, RESOURCE, expression, RESOURCE, expression, RESOURCE, expression, expression],
        ).fetchone()
        assert cpp_row == py_row == expected
    finally:
        cpp.close()
        py.close()


def test_datetime_integer_and_quantity_literals_match_python_fallback() -> None:
    expressions = [
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

    py = _python_fallback_connection()
    cpp = _connection()
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


def test_partial_datetime_time_components_require_full_date_in_both_backends() -> None:
    valid_expressions = ["@2014T", "@2014-01T", "@2014-01-25T", "@2014-01-25T14"]
    invalid_expressions = [
        "@2014T14",
        "@2014T14:30",
        "@2014T14:30:00Z",
        "@2014-01T14",
        "@2014-01T14:30",
        "@2014-01T14:30:00+09:00",
    ]

    py = _python_fallback_connection()
    cpp = _connection()
    try:
        for expression in valid_expressions:
            assert cpp.execute("SELECT fhirpath_is_valid(?)", [expression]).fetchone() == (True,)
            assert py.execute("SELECT fhirpath_is_valid(?)", [expression]).fetchone() == (True,)

        expected = ([], None, None, None, None, None, False)
        for expression in invalid_expressions:
            cpp_row = cpp.execute(
                "SELECT fhirpath(?::JSON, ?), fhirpath_text(?::JSON, ?), fhirpath_json(?::JSON, ?), fhirpath_date(?::JSON, ?), fhirpath_timestamp(?::JSON, ?), fhirpath_quantity(?::JSON, ?), fhirpath_is_valid(?)",
                [
                    RESOURCE,
                    expression,
                    RESOURCE,
                    expression,
                    RESOURCE,
                    expression,
                    RESOURCE,
                    expression,
                    RESOURCE,
                    expression,
                    RESOURCE,
                    expression,
                    expression,
                ],
            ).fetchone()
            py_row = py.execute(
                "SELECT fhirpath(?::JSON, ?), fhirpath_text(?::JSON, ?), fhirpath_json(?::JSON, ?), fhirpath_date(?::JSON, ?), fhirpath_timestamp(?::JSON, ?), fhirpath_quantity(?::JSON, ?), fhirpath_is_valid(?)",
                [
                    RESOURCE,
                    expression,
                    RESOURCE,
                    expression,
                    RESOURCE,
                    expression,
                    RESOURCE,
                    expression,
                    RESOURCE,
                    expression,
                    RESOURCE,
                    expression,
                    expression,
                ],
            ).fetchone()
            assert cpp_row == py_row == expected
    finally:
        cpp.close()
        py.close()


def test_malformed_temporal_literal_shapes_are_invalid_in_both_backends() -> None:
    expressions = ["@2014-1", "@2014-01-2", "@2014-01-25T14+09", "@T14:3"]

    py = _python_fallback_connection()
    cpp = _connection()
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
