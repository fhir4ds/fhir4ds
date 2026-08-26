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


def test_iso8601_week_date_literals_are_invalid_in_both_backends() -> None:
    """FHIRPath §4.1.5: "Week dates and ordinal dates are not allowed."

    Native C++ rejects ISO 8601 week-date forms directly in the lexer. The
    Python fallback must report the same validity signal via
    ``fhirpath_is_valid`` and return row-resilient empty results from the
    public UDFs. The underlying fhirpathpy parser accepts these tokens, so
    the static precheck in the fallback is the source of truth.
    """
    expressions = [
        "@2015-W01-1",
        "@2015-W01",
        "@2015-W53-7",
        "@2015-W",
        "@2015-W00",
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


def test_valid_calendar_duration_keywords_remain_valid_after_week_date_fix() -> None:
    """The week-date precheck must not affect ``week``/``weeks`` Quantity units.

    Regression guard: the temporal-token scanner was extended to include ``W``
    so it can recognize ISO 8601 week dates. The Quantity literals ``1 week``
    and ``4 weeks`` use the calendar-duration keyword spelled with lowercase
    ``w`` and must remain valid.
    """
    expressions = ["1 week", "4 weeks", "52 weeks", "0 weeks", "1 year", "2 days"]

    py = _python_fallback_connection()
    cpp = _connection()
    try:
        for expression in expressions:
            assert cpp.execute("SELECT fhirpath_is_valid(?)", [expression]).fetchone() == (True,)
            assert py.execute("SELECT fhirpath_is_valid(?)", [expression]).fetchone() == (True,)
    finally:
        cpp.close()
        py.close()


def test_quantity_literal_member_access_matches_backends() -> None:
    """Quantity literals expose ``.value`` (Decimal) and ``.unit`` (String).

    FHIRPath §4.1.8 defines a Quantity as having a ``value`` component of type
    Decimal and a ``unit`` element of type String. Resource-backed FHIR
    ``Quantity`` JSON objects already expose ``value``/``unit``/``code``/
    ``system`` through the regular JSON member-access path in both backends,
    but Quantity literals (``5 'mg'``) previously lost member access in native
    C++ (silent empty) and produced wrong values in the forced Python fallback
    (every key returned the value). This guard ensures Quantity literals expose
    ``value`` and ``unit`` consistently across native and fallback, and that
    ``.code``/``.system`` return empty (literals carry no UCUM/namespace
    metadata per §4.1.8).
    """
    cases = [
        # (expression, native_expected, fallback_expected)
        ("5 'mg'.value", "5.0", "5.0"),
        ("5 'mg'.unit", "'mg'", "'mg'"),
        ("5.5 'mg'.value", "5.5", "5.5"),
        ("5.5 'mg'.unit", "'mg'", "'mg'"),
        ("1 year.value", "1.0", "1.0"),
        ("1 year.unit", "year", "year"),
    ]
    empty_member_cases = [
        # §4.1.8: literals expose only value+unit; code/system are not present.
        "5 'mg'.code",
        "5 'mg'.system",
    ]

    py = _python_fallback_connection()
    cpp = _connection()
    try:
        for expression, _, _ in cases:
            assert cpp.execute("SELECT fhirpath_is_valid(?)", [expression]).fetchone() == (True,)
            assert py.execute("SELECT fhirpath_is_valid(?)", [expression]).fetchone() == (True,)
            cpp_text = cpp.execute(
                "SELECT fhirpath_text(?::JSON, ?)",
                [RESOURCE, expression],
            ).fetchone()[0]
            py_text = py.execute(
                "SELECT fhirpath_text(?::JSON, ?)",
                [RESOURCE, expression],
            ).fetchone()[0]
            assert cpp_text == py_text, (
                f"{expression}: native={cpp_text!r} fallback={py_text!r}"
            )
        for expression in empty_member_cases:
            # Both backends must agree these members are absent on literals.
            cpp_result = cpp.execute(
                "SELECT fhirpath(?::JSON, ?), fhirpath_is_valid(?)",
                [RESOURCE, expression, expression],
            ).fetchone()
            py_result = py.execute(
                "SELECT fhirpath(?::JSON, ?), fhirpath_is_valid(?)",
                [RESOURCE, expression, expression],
            ).fetchone()
            assert cpp_result == py_result, (
                f"{expression}: native={cpp_result!r} fallback={py_result!r}"
            )
    finally:
        cpp.close()
        py.close()


def test_quantity_literal_value_and_unit_member_equality() -> None:
    """Quantity-literal member values participate in equality like ordinary values.

    Regression guard: after restoring member access on Quantity literals,
    ``5 'mg'.value = 5`` and ``5 'mg'.value = 5.0`` must both return true
    (Decimal trailing-zero equality per §6.1.1), and ``5 'mg'.unit = 'mg'``
    must compare the bare UCUM unit text against the literal string. The unit
    member returns the bare UCUM code (``mg``) or calendar duration keyword
    (``year``) — matching the §5.5.8 Quantity toString shape for each unit kind.
    """
    cases = [
        ("5 'mg'.value = 5", True),
        ("5 'mg'.value = 5.0", True),
        ("5 'mg'.unit = 'mg'", True),
        ("1 year.unit = 'year'", True),
    ]

    py = _python_fallback_connection()
    cpp = _connection()
    try:
        for expression, expected in cases:
            assert cpp.execute("SELECT fhirpath_is_valid(?)", [expression]).fetchone() == (True,)
            cpp_bool = cpp.execute(
                "SELECT fhirpath_bool(?::JSON, ?)",
                [RESOURCE, expression],
            ).fetchone()[0]
            py_bool = py.execute(
                "SELECT fhirpath_bool(?::JSON, ?)",
                [RESOURCE, expression],
            ).fetchone()[0]
            assert cpp_bool == py_bool == expected, (
                f"{expression}: native={cpp_bool!r} fallback={py_bool!r} expected={expected!r}"
            )
    finally:
        cpp.close()
        py.close()



def test_quoted_calendar_keyword_quantity_equality_fp01_skeptic() -> None:
    """§4.1.8: a quoted calendar duration keyword is the same quantity as the bare form.

    FHIRPath §4.1.8 (Time-valued Quantities) defines `'year'`, `'month'`, ... as
    the unit representation of the calendar duration keywords, singular or
    plural. So `1 'month' = 1 month` must be true, while mixing calendar
    year/month with UCUM `'a'`/`'mo'` stays not-comparable (empty) exactly like
    the bare-keyword form — pinned EMPTY by the official R4 fixtures
    (`'1 'a''.toQuantity() = 1 year`, FP-01 HISTORIAN QA-001 2026-08-16),
    which outrank the N1/master §6.1.1 prose saying false. Below seconds the
    keyword and UCUM unit are equal by definition.
    """
    cases: list[tuple[str, bool | None]] = [
        ("1 'month' = 1 month", True),
        ("1 'year' = 1 year", True),
        ("2 'days' = 2 days", True),
        ("1 'day' = 1 day", True),
        ("1 'millisecond' = 1 millisecond", True),
        ("1 'month' = 1 'mo'", None),
        ("1 'year' = 1 'a'", None),
        ("1 'week' = 1 'wk'", True),
        ("1 'second' = 1 's'", True),
        ("4 'year' ~ 4 years", True),
        ("1 'month' ~ 1 'mo'", True),
    ]

    py = _python_fallback_connection()
    cpp = _connection()
    try:
        for expression, expected in cases:
            assert cpp.execute("SELECT fhirpath_is_valid(?)", [expression]).fetchone() == (True,)
            cpp_bool = cpp.execute("SELECT fhirpath_bool(?::JSON, ?)", [RESOURCE, expression]).fetchone()[0]
            py_bool = py.execute("SELECT fhirpath_bool(?::JSON, ?)", [RESOURCE, expression]).fetchone()[0]
            assert cpp_bool == py_bool == expected, (
                f"{expression}: native={cpp_bool!r} fallback={py_bool!r} expected={expected!r}"
            )
    finally:
        cpp.close()
        py.close()


def test_quoted_calendar_keyword_temporal_arithmetic_parity_fp01_skeptic() -> None:
    """§4.1.8 + §6.7: quoted calendar keywords work in date/time arithmetic.

    `@2015-02-04 + 2 'days'` is the same expression as `+ 2 days` because the
    quoted keyword is the unit representation of the calendar duration, so both
    backends must evaluate it (previously the Python fallback raised an
    invalid-unit error for quoted plural keywords).
    """
    cases = [
        ("@2015-02-04 + 2 'days'", "2015-02-06"),
        ("@2015 + 1 'years'", "2016"),
        ("@T14:34:28 + 30 'minutes'", "15:04:28"),
        ("@2015-02-04 + 1 'week'", "2015-02-11"),
    ]

    py = _python_fallback_connection()
    cpp = _connection()
    try:
        for expression, expected in cases:
            assert cpp.execute("SELECT fhirpath_is_valid(?)", [expression]).fetchone() == (True,)
            assert py.execute("SELECT fhirpath_is_valid(?)", [expression]).fetchone() == (True,)
            cpp_text = cpp.execute("SELECT fhirpath_text(?::JSON, ?)", [RESOURCE, expression]).fetchone()[0]
            py_text = py.execute("SELECT fhirpath_text(?::JSON, ?)", [RESOURCE, expression]).fetchone()[0]
            assert cpp_text == py_text == expected, (
                f"{expression}: native={cpp_text!r} fallback={py_text!r} expected={expected!r}"
            )
    finally:
        cpp.close()
        py.close()


def test_month_year_vs_days_ordering_parity_fp01_skeptic() -> None:
    """§5.5.7 + §6.2: calendar month/year vs days ordering uses the spec factors.

    FHIRPath N1 §5.5.7 defines calendar duration conversion factors for
    unanchored calculations: 1 month = 30 days, 1 year = 365 days (and
    1 year = 12 months). So `1 month > 30 days` is false (they are equal),
    `1 month > 29 days` is true, `1 year > 364 days` is true while
    `1 year > 365 days` is false. Mixed calendar-vs-UCUM year/month pairs
    (`1 'mo' > 29 days`, `1 year > 1 'a'`) stay empty in both backends per
    §6.2; a calendar year/month keyword against a UCUM week/day/time code
    compares through the factors because `30 'd'` is exactly 30 days.
    """
    cases: list[tuple[str, bool | None]] = [
        ("1 month > 29 days", True),
        ("1 month > 30 days", False),
        ("1 month > 31 days", False),
        ("1 month >= 30 days", True),
        ("1 year > 364 days", True),
        ("1 year > 365 days", False),
        ("1 year > 366 days", False),
        ("1 year < 366 days", True),
        ("2 months > 59 days", True),
        ("2 months > 60 days", False),
        ("1 month > 29 'd'", True),
        ("1 year > 1 'a'", None),
        ("1 'mo' > 29 days", None),
        ("1 'mo' > 29 'd'", True),
    ]

    py = _python_fallback_connection()
    cpp = _connection()
    try:
        for expression, expected in cases:
            cpp_bool = cpp.execute("SELECT fhirpath_bool(?::JSON, ?)", [RESOURCE, expression]).fetchone()[0]
            py_bool = py.execute("SELECT fhirpath_bool(?::JSON, ?)", [RESOURCE, expression]).fetchone()[0]
            assert cpp_bool == py_bool == expected, (
                f"{expression}: native={cpp_bool!r} fallback={py_bool!r} expected={expected!r}"
            )
    finally:
        cpp.close()
        py.close()


def test_calendar_conversion_factor_equality_parity_fp01_skeptic() -> None:
    """§5.5.7 + §6.1.1: unanchored calendar equality applies the spec factors.

    `1 month = 30 days` and `1 year = 365 days` are true per the §5.5.7
    conversion factors (previously false in both backends, which converted
    calendar month/year through UCUM mean-duration seconds). Year↔month
    pairs keep the month-based rule (`1 year = 12 months`), and mixed
    calendar-vs-UCUM year/month pairs stay empty per §6.1.1 as pinned by
    the official R4 toQuantity fixtures (FP-01 HISTORIAN QA-001 2026-08-16).
    """
    cases: list[tuple[str, bool | None]] = [
        ("1 month = 30 days", True),
        ("1 year = 365 days", True),
        ("2 months = 60 days", True),
        ("1 month = 29 days", False),
        ("1 year = 364 days", False),
        ("1 year = 12 months", True),
        ("1 'a' = 12 'mo'", True),
        ("1 month = 30 'd'", True),
        ("1 month = 1 'mo'", None),
        ("1 year = 1 'a'", None),
        ("1 'mo' = 29 days", False),
        ("1 year ~ 1 'a'", True),
        ("1 month ~ 30 days", True),
        ("7 days = 1 'wk'", True),
        ("1 second = 1 's'", True),
    ]

    py = _python_fallback_connection()
    cpp = _connection()
    try:
        for expression, expected in cases:
            cpp_bool = cpp.execute("SELECT fhirpath_bool(?::JSON, ?)", [RESOURCE, expression]).fetchone()[0]
            py_bool = py.execute("SELECT fhirpath_bool(?::JSON, ?)", [RESOURCE, expression]).fetchone()[0]
            assert cpp_bool == py_bool == expected, (
                f"{expression}: native={cpp_bool!r} fallback={py_bool!r} expected={expected!r}"
            )
        # distinct()/membership coalesce §5.5.7-equal calendar quantities
        # in both engines (same `=` equality semantics).
        for expression, expected in [
            ("(1 month | 30 days).count()", "1"),
            ("30 days in (1 month | 2 months)", "true"),
        ]:
            cpp_row = cpp.execute("SELECT fhirpath_text(?::JSON, ?)", [RESOURCE, expression]).fetchone()[0]
            py_row = py.execute("SELECT fhirpath_text(?::JSON, ?)", [RESOURCE, expression]).fetchone()[0]
            assert cpp_row == py_row == expected, (
                f"{expression}: native={cpp_row!r} fallback={py_row!r} expected={expected!r}"
            )
    finally:
        cpp.close()
        py.close()


def test_quoted_calendar_keyword_quantity_display_and_json_fp01_skeptic() -> None:
    """Quoted calendar keyword quantities display like the bare keyword form.

    `4 'year'` renders as `4 year` (native behavior; the quoted keyword is the
    calendar duration, not a UCUM unit) and serializes to JSON with the bare
    keyword unit, in both backends.
    """
    cases = [
        ("4 'year'", "4 year", '{"value":4,"unit":"year"}'),
        ("1 'years'", "1 years", '{"value":1,"unit":"years"}'),
        ("2.5 'days'", "2.5 days", '{"value":2.5,"unit":"days"}'),
    ]

    py = _python_fallback_connection()
    cpp = _connection()
    try:
        for expression, expected_text, expected_json in cases:
            cpp_row = cpp.execute(
                "SELECT fhirpath_text(?::JSON, ?), fhirpath_json(?::JSON, ?)",
                [RESOURCE, expression, RESOURCE, expression],
            ).fetchone()
            py_row = py.execute(
                "SELECT fhirpath_text(?::JSON, ?), fhirpath_json(?::JSON, ?)",
                [RESOURCE, expression, RESOURCE, expression],
            ).fetchone()
            assert cpp_row == py_row == (expected_text, f"[{expected_json}]"), (
                f"{expression}: native={cpp_row!r} fallback={py_row!r}"
            )
    finally:
        cpp.close()
        py.close()


def test_quantity_json_value_precision_mask_parity_fp01_skeptic() -> None:
    """Quantity JSON values use the native precision-15 mask in both backends."""
    expression = "3.141592653589793236 'mg'"
    expected = '{"value":3.14159265358979,"unit":"mg"}'

    py = _python_fallback_connection()
    cpp = _connection()
    try:
        cpp_json = cpp.execute("SELECT fhirpath_json(?::JSON, ?)", [RESOURCE, expression]).fetchone()[0]
        py_json = py.execute("SELECT fhirpath_json(?::JSON, ?)", [RESOURCE, expression]).fetchone()[0]
        assert cpp_json == py_json == f"[{expected}]"
    finally:
        cpp.close()
        py.close()


def test_decimal_negative_zero_display_parity_fp01_skeptic() -> None:
    """§4.1.4: unary negation of decimal zero renders as 0.0 in both backends.

    The official R4 test suite requires `-0.0034.highBoundary(1)` -> `0.0`
    (the unary minus applies to the zero-valued boundary result), so unary
    negation of a decimal zero must normalize to positive zero. The native
    C++ unary-minus branch previously rendered `-0.0` from the authored
    source text; it now applies the same zero-sign normalization as the
    Python fallback (whose Decimal unary minus normalizes -0.0 to 0.0).
    Equality is unaffected (`-0.0 = 0.0` // true).
    """
    py = _python_fallback_connection()
    cpp = _connection()
    try:
        for expression, expected_text, expected_bool in [
            ("-0.0", "0.0", None),
            ("-0.0 = 0.0", None, True),
            ("-1.5", "-1.5", None),
            ("-0.0 'mg'", "0.0 'mg'", None),
        ]:
            cpp_text = cpp.execute("SELECT fhirpath_text(?::JSON, ?)", [RESOURCE, expression]).fetchone()[0]
            py_text = py.execute("SELECT fhirpath_text(?::JSON, ?)", [RESOURCE, expression]).fetchone()[0]
            cpp_bool = cpp.execute("SELECT fhirpath_bool(?::JSON, ?)", [RESOURCE, expression]).fetchone()[0]
            py_bool = py.execute("SELECT fhirpath_bool(?::JSON, ?)", [RESOURCE, expression]).fetchone()[0]
            if expected_text is not None:
                assert cpp_text == py_text == expected_text, (
                    f"{expression}: native={cpp_text!r} fallback={py_text!r} expected={expected_text!r}"
                )
            if expected_bool is not None:
                assert cpp_bool == py_bool == expected_bool, (
                    f"{expression}: native={cpp_bool!r} fallback={py_bool!r} expected={expected_bool!r}"
                )
    finally:
        cpp.close()
        py.close()


def test_mixed_calendar_ucum_year_month_equality_is_empty_fp01_historian() -> None:
    """Official R4 fixtures pin mixed calendar-vs-UCUM year/month quantity
    equality to EMPTY: testStringQuantityYearLiteralToQuantity
    (`'1 'a''.toQuantity() = 1 year`) and the 'mo' analog carry no <output>
    element in tests-fhir-r4.xml, which the conformance harness reads as
    "expected empty".

    FP-01 HISTORIAN QA-001 (2026-08-16): the N1/master §6.1.1 prose says
    these pairs are "unequal" (`1 year = 1 'a'` // false), which conflicts
    with the official suite; per the QA-005 precedent (official fixtures
    outrank spec prose), the empty behavior is authoritative. This test
    guards against re-introducing the prose-literal `false`, which broke
    2 official conformance tests when attempted.
    """
    py = _python_fallback_connection()
    cpp = _connection()
    try:
        for expression, expected_bool in [
            # Official fixture forms (escaped-quote string literals):
            ("'1 \\'a\\''.toQuantity() = 1 year", None),
            ("'1 \\'mo\\''.toQuantity() = 1 month", None),
            ("'1 day'.toQuantity() = 1 'd'", True),
            # Literal-operand equivalents of the same mixed class:
            ("1 year = 1 'a'", None),
            ("1 month = 1 'mo'", None),
            ("1 'year' = 1 'a'", None),
            ("1 year = 12 'mo'", None),
            # §6.2 ordering stays empty for the same mixed pairs:
            ("1 year > 1 'a'", None),
            ("1 month >= 1 'mo'", None),
            # §6.1.2 equivalence stays true:
            ("1 year ~ 1 'a'", True),
            ("1 month ~ 1 'mo'", True),
            # Guards that must NOT change:
            ("1 second = 1 's'", True),          # §4.1.8 table: second = 1 's'
            ("1 millisecond = 1 'ms'", True),    # §4.1.8 table: ms = 1 'ms'
            ("1 month = 30 days", True),         # §5.5.7 factor equality
            ("1 year = 12 months", True),
            ("7 days = 1 'wk'", True),           # official R4 testQuantity6
            ("1 'a' = 365 days", False),         # UCUM mean year vs calendar days
            ("1 'mo' = 29 days", False),
        ]:
            cpp_bool = cpp.execute("SELECT fhirpath_bool(?::JSON, ?)", [RESOURCE, expression]).fetchone()[0]
            py_bool = py.execute("SELECT fhirpath_bool(?::JSON, ?)", [RESOURCE, expression]).fetchone()[0]
            assert cpp_bool == py_bool == expected_bool, (
                f"{expression}: native={cpp_bool!r} fallback={py_bool!r} expected={expected_bool!r}"
            )
        # Collections semantics: empty `=` equality means mixed
        # calendar/UCUM year-month items are distinct in a union (§6.4).
        for expression, expected in [
            ("(1 'month' | 1 'mo').count()", "2"),
            ("(1 'year' | 1 year | 12 months).count()", "1"),
        ]:
            cpp_res = cpp.execute("SELECT fhirpath(?::JSON, ?)", [RESOURCE, expression]).fetchone()[0]
            py_res = py.execute("SELECT fhirpath(?::JSON, ?)", [RESOURCE, expression]).fetchone()[0]
            assert cpp_res == py_res == [expected], (
                f"{expression}: native={cpp_res!r} fallback={py_res!r} expected=[{expected}]"
            )
    finally:
        cpp.close()
        py.close()


def test_time_arithmetic_results_render_without_leading_t_fp01_historian() -> None:
    """§5.5.1 toString() representation table renders Time as hh:mm:ss.fff
    with no leading `T` (the `T` belongs only to the @T literal syntax).
    Time-literal + time-valued-quantity arithmetic results previously leaked
    the `T` marker (`T15:04:28`) and, in the Python fallback, degraded to a
    plain String value.
    """
    py = _python_fallback_connection()
    cpp = _connection()
    try:
        for expression, expected_text in [
            ("(@T14:34:28 + 30 'minutes').toString()", "15:04:28"),
            ("@T14:34:28 + 30 'minutes'", "15:04:28"),
            ("@T14:34:28 + 90 'seconds'", "14:35:58"),
            ("@T14:34:28 + 1 'hour'", "15:34:28"),
            ("@T14:34:28.123 + 1 'milliseconds'", "14:34:28.124"),
            ("@T14:34:28 - 28 'minutes'", "14:06:28"),
            # §6.7: partial time + more precise quantity converts the
            # quantity to the operand precision (30 min -> 0 hours).
            ("@T14 + 30 'minutes'", "14"),
            ("@T14 + 90 'minutes'", "15"),
        ]:
            cpp_text = cpp.execute("SELECT fhirpath_text(?::JSON, ?)", [RESOURCE, expression]).fetchone()[0]
            py_text = py.execute("SELECT fhirpath_text(?::JSON, ?)", [RESOURCE, expression]).fetchone()[0]
            assert cpp_text == py_text == expected_text, (
                f"{expression}: native={cpp_text!r} fallback={py_text!r} expected={expected_text!r}"
            )
        # The result remains a Time value: equal to the corresponding Time
        # literal, and NOT equal to a plain String (§5.5: String->Time is
        # Explicit-only, so Time = String is empty).
        for expression, expected_bool in [
            ("(@T14:34:28 + 30 'minutes') = @T15:04:28", True),
            ("(@T14:34:28 + 30 'minutes') = 'T15:04:28'", None),
            ("(@T14:34:28 + 30 'minutes') = '15:04:28'", None),
        ]:
            cpp_res = cpp.execute("SELECT fhirpath_bool(?::JSON, ?)", [RESOURCE, expression]).fetchone()[0]
            py_res = py.execute("SELECT fhirpath_bool(?::JSON, ?)", [RESOURCE, expression]).fetchone()[0]
            assert cpp_res == py_res == expected_bool, (
                f"{expression}: native={cpp_res!r} fallback={py_res!r} expected={expected_bool!r}"
            )
    finally:
        cpp.close()
        py.close()


def test_time_literal_vs_plain_string_equality_is_empty_fp01_historian() -> None:
    """§5.5 conversion table: String -> Time is Explicit-only, so a Time
    literal compared with a plain (untyped) String is empty per §6.1.1.
    The native engine already behaved this way; the Python fallback used to
    coerce time-shaped strings. Date/DateTime-vs-plain-string coercion is
    unchanged in both engines (a shared JSON-convenience convention).
    """
    py = _python_fallback_connection()
    cpp = _connection()
    try:
        for expression, expected_bool in [
            ("@T14:34:28 = '14:34:28'", None),
            ("'14:34:28' = @T14:34:28", None),
            ("@T14:34:28 = '14:35:28'", None),
            # Unchanged conventions:
            ("@2015-02-04 = '2015-02-04'", True),
            ("'2015-02-04' = @2015-02-04", True),
            ("@2015-02-04T14:34:28 = '2015-02-04T14:34:28'", True),
            ("@2015-02-04 = '2015-02-05'", False),
        ]:
            cpp_res = cpp.execute("SELECT fhirpath_bool(?::JSON, ?)", [RESOURCE, expression]).fetchone()[0]
            py_res = py.execute("SELECT fhirpath_bool(?::JSON, ?)", [RESOURCE, expression]).fetchone()[0]
            assert cpp_res == py_res == expected_bool, (
                f"{expression}: native={cpp_res!r} fallback={py_res!r} expected={expected_bool!r}"
            )
    finally:
        cpp.close()
        py.close()
