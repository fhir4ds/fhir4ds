"""Parity tests for FHIRPath operator/null semantics in DuckDB UDFs."""

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


RESOURCE = json.dumps(
    {
        "resourceType": "Patient",
        "id": "p",
        "active": True,
        "gender": "female",
        "zero": 0,
        "boolText": "false",
        "name": [{"given": ["Ann", "Beth"], "family": "Smith"}],
    }
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


def _all_udfs(con: duckdb.DuckDBPyConnection, resource: str, expression: str):
    return con.execute(
        """
        SELECT
            fhirpath(?::JSON, ?),
            fhirpath_text(?::JSON, ?),
            fhirpath_json(?::JSON, ?),
            fhirpath_bool(?::JSON, ?),
            fhirpath_number(?::JSON, ?)
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
        ],
    ).fetchone()


def test_decimal_json_and_iif_empty_criterion_match_python_fallback() -> None:
    expressions = ["6 / 2", "iif({}, 1, 2)"]

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


def test_empty_collection_rhs_after_literal_operator_matches_python_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    expressions = ["'x' & {}", "'x' + {}"]

    cpp = _connection()
    py = _python_fallback_connection(monkeypatch)
    try:
        for expression in expressions:
            assert _all_udfs(cpp, RESOURCE, expression) == _all_udfs(py, RESOURCE, expression)
    finally:
        cpp.close()
        py.close()


def test_boolean_singleton_evaluation_matches_python_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    expressions = [
        "active and gender",
        "true and gender",
        "zero and true",
        "true and zero",
        "boolText and true",
        "gender or false",
        "gender xor false",
        "gender implies false",
        "false implies gender",
        "gender.not()",
        "iif(gender, 1, 2)",
    ]

    cpp = _connection()
    py = _python_fallback_connection(monkeypatch)
    try:
        for expression in expressions:
            assert _all_udfs(cpp, RESOURCE, expression) == _all_udfs(py, RESOURCE, expression)
    finally:
        cpp.close()
        py.close()


def test_python_fallback_scalar_uses_singleton_boolean_rules() -> None:
    cases = {
        "true and gender": (["true"], "true", "[true]", True, None),
        "zero and true": (["true"], "true", "[true]", True, None),
        "true and zero": (["true"], "true", "[true]", True, None),
        "boolText and true": (["true"], "true", "[true]", True, None),
        "gender.not()": (["false"], "false", "[false]", False, None),
        "iif(gender, 'yes', 'no')": (["yes"], "yes", '["yes"]', None, None),
    }

    for expression, expected in cases.items():
        assert (
            fhirpath_scalar(RESOURCE, expression),
            fhirpath_text_udf(RESOURCE, expression),
            fhirpath_json_udf(RESOURCE, expression),
            fhirpath_bool_udf(RESOURCE, expression),
            fhirpath_number_udf(RESOURCE, expression),
        ) == expected


def test_iif_rejects_multi_item_input_in_public_udfs(monkeypatch: pytest.MonkeyPatch) -> None:
    expression = "('a'|'b').iif(true, 'yes', 'no')"

    cpp = _connection()
    py = _python_fallback_connection(monkeypatch)
    try:
        assert _all_udfs(cpp, RESOURCE, expression) == ([], None, None, None, None)
        assert _all_udfs(cpp, RESOURCE, expression) == _all_udfs(py, RESOURCE, expression)
    finally:
        cpp.close()
        py.close()


def test_type_operators_bind_tighter_than_union_in_native_and_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cases = {
        "1 | 2 is Integer": (["1", "true"], "[1,true]", True),
        "1 | 'a' as String": (["1", "a"], '[1,"a"]', True),
    }

    cpp = _connection()
    py = _python_fallback_connection(monkeypatch)
    try:
        for expression, expected in cases.items():
            query = """
                SELECT fhirpath(?::JSON, ?), fhirpath_json(?::JSON, ?), fhirpath_is_valid(?)
            """
            params = [RESOURCE, expression, RESOURCE, expression, expression]
            assert cpp.execute(query, params).fetchone() == expected
            assert py.execute(query, params).fetchone() == expected
    finally:
        cpp.close()
        py.close()


def test_native_trim_rejects_multi_item_input_like_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    expression = "name.given.trim()"

    cpp = _connection()
    py = _python_fallback_connection(monkeypatch)
    try:
        assert _all_udfs(cpp, RESOURCE, expression) == ([], None, None, None, None)
        assert _all_udfs(cpp, RESOURCE, expression) == _all_udfs(py, RESOURCE, expression)
    finally:
        cpp.close()
        py.close()


def test_unary_operators_enforce_singleton_after_dot_precedence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cases = {
        "-7.combine(3)": ([], None, None, None, None, False),
        "+7.combine(3)": ([], None, None, None, None, False),
        "(-7).combine(3)": (["-7", "3"], "-7", "[-7,3]", None, None, True),
    }

    cpp = _connection()
    py = _python_fallback_connection(monkeypatch)
    try:
        for expression, expected in cases.items():
            query = """
                SELECT
                    fhirpath(?::JSON, ?),
                    fhirpath_text(?::JSON, ?),
                    fhirpath_json(?::JSON, ?),
                    fhirpath_bool(?::JSON, ?),
                    fhirpath_number(?::JSON, ?),
                    fhirpath_is_valid(?)
            """
            params = [
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
            ]
            assert cpp.execute(query, params).fetchone() == expected
            assert py.execute(query, params).fetchone() == expected
    finally:
        cpp.close()
        py.close()


def test_unknown_function_invocation_is_row_resilient_in_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    expression = "unknownFunction()"
    expected = ([], None, None, None, None, False)

    cpp = _connection()
    py = _python_fallback_connection(monkeypatch)
    try:
        query = """
            SELECT
                fhirpath(?::JSON, ?),
                fhirpath_text(?::JSON, ?),
                fhirpath_json(?::JSON, ?),
                fhirpath_bool(?::JSON, ?),
                fhirpath_number(?::JSON, ?),
                fhirpath_is_valid(?)
        """
        params = [
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
        ]
        assert cpp.execute(query, params).fetchone() == expected
        assert py.execute(query, params).fetchone() == expected
    finally:
        cpp.close()
        py.close()


@pytest.mark.parametrize(
    ("expression", "valid"),
    [
        # FP-02 SKEPTIC QA-001 (2026-08-16): §6.8 precedence — arithmetic
        # operators (#04/#05) bind tighter than '|' union (#07), so these
        # parse as `(1 + 2) | 3` etc. and MUST report valid in both the
        # native extension and the Python fallback validity precheck.
        ("1 + 2 | 3", True),
        ("1 | 2 + 3", True),
        ("'a' | 'b' & 'c'", True),
        ("2 * 3 | 4", True),
        ("3 | 4 + 5", True),
        ("1 + 1 | 2", True),
        ("0 + 1 | 2", True),
        ("-1 | 2", True),
        ("1 div 2 | 3", True),
        ("1 mod 2 | 3", True),
        # Parenthesized multi-item operands of math operators stay invalid.
        ("(1 | 2) + 3", False),
        ("1 + (2 | 3)", False),
        ("(1 | 2) * 3", False),
        # Multi-item operands of comparisons stay invalid (singleton rule).
        ("1 < 2 | 3", False),
        ("(1|2) < 3", False),
    ],
)
def test_union_precedence_validity_matches_native_fp02_skeptic(
    expression: str,
    valid: bool,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cpp = _connection()
    py = _python_fallback_connection(monkeypatch)
    try:
        query = "SELECT fhirpath_is_valid(?), fhirpath(?::JSON, ?)"
        params = [expression, RESOURCE, expression]
        cpp_row = cpp.execute(query, params).fetchone()
        py_row = py.execute(query, params).fetchone()
        assert cpp_row[0] is valid, f"{expression!r}: native is_valid={cpp_row[0]}"
        assert py_row[0] is valid, f"{expression!r}: fallback is_valid={py_row[0]}"
        assert cpp_row[1] == py_row[1], f"{expression!r}: eval divergence"
    finally:
        cpp.close()
        py.close()


@pytest.mark.parametrize(
    ("expression", "valid"),
    [
        # FP-02 SKEPTIC QA-002 (2026-08-16): unary +/- on non-numeric
        # literals is an execution type error (§6.8 syntax is valid; §6.6
        # signals at evaluation), matching the binary classification of
        # `'a' - 'b'`. Singleton violations stay invalid.
        ("-'a'", True),
        ("+'a'", True),
        ("'a' - 'b'", True),
        ("(1 | 2).not()", False),
    ],
)
def test_unary_type_error_validity_classification_fp02_skeptic(
    expression: str,
    valid: bool,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cpp = _connection()
    py = _python_fallback_connection(monkeypatch)
    try:
        for con in (cpp, py):
            got = con.execute("SELECT fhirpath_is_valid(?)", [expression]).fetchone()[0]
            assert got is valid, f"{expression!r}: is_valid={got} expected={valid}"
    finally:
        cpp.close()
        py.close()


@pytest.mark.parametrize(
    "expression",
    [
        # FP-02 EXPLORER QA-001 (2026-08-16): sum/min/max/avg are NOT
        # FHIRPath N1/R4 functions. The native extension treats them as
        # unknown functions -> empty/NULL, and fhirpath_is_valid rejects
        # them; the Python fallback registry must not evaluate expressions
        # its own validator rejects ({}.sum() -> 0 even violated the
        # spec-wide empty-input convention).
        "{}.sum()",
        "nums.sum()",
        "nums.min()",
        "nums.max()",
        "nums.avg()",
        "dups.sum()",
        "nums.sum() = 3",
        "(1 | 2).sum()",
    ],
)
def test_non_spec_aggregate_functions_parity_fp02_explorer(
    expression: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    resource = json.dumps(
        {"resourceType": "Patient", "id": "p", "nums": [1, 2], "dups": [1, 2, 1]}
    )
    cpp = _connection()
    py = _python_fallback_connection(monkeypatch)
    try:
        query = "SELECT fhirpath(?::JSON, ?), fhirpath_is_valid(?)"
        params = [resource, expression, expression]
        cpp_row = cpp.execute(query, params).fetchone()
        py_row = py.execute(query, params).fetchone()
        assert cpp_row == py_row == ([], False), f"{expression!r}: {cpp_row} vs {py_row}"
    finally:
        cpp.close()
        py.close()


@pytest.mark.parametrize(
    ("expression", "valid"),
    [
        # FP-02 EXPLORER QA-003 (2026-08-16): §6.2 omits Boolean from the
        # orderable types, so boolean-vs-boolean ordering is an execution
        # type error of the SAME class as mixed-type ordering (`1 > true`),
        # which must classify as valid per the is_valid doctrine.
        ("true > false", True),
        ("false < true", True),
        ("true >= false", True),
        ("true <= false", True),
        ("1 > true", True),
        ("'a' > 1", True),
        ("true > 1", True),
        ("true > 'a'", True),
        ("@2014-01-01 < 'a'", True),
    ],
)
def test_ordering_type_error_validity_classification_fp02_explorer(
    expression: str,
    valid: bool,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cpp = _connection()
    py = _python_fallback_connection(monkeypatch)
    try:
        for con in (cpp, py):
            got = con.execute("SELECT fhirpath_is_valid(?)", [expression]).fetchone()[0]
            assert got is valid, f"{expression!r}: is_valid={got} expected={valid}"
    finally:
        cpp.close()
        py.close()


@pytest.mark.parametrize(
    ("expression", "valid"),
    [
        # FP-05 SKEPTIC QA-001 (2026-08-17): §5.3 subsetting argument type
        # errors (indexer `[i]`, skip(num), take(num) require Integer) are
        # execution type errors of the same class as `'a' - 'b'` — the
        # expression grammar is valid and the mismatch signals at
        # evaluation, so fhirpath_is_valid must report True. Singleton /
        # multi-item argument violations stay invalid (doctrine).
        ("(1|2|3).skip('x')", True),
        ("(1|2|3).skip(1.5)", True),
        ("(1|2|3).skip(true)", True),
        ("(1|2|3).take('x')", True),
        ("(1|2|3).take(1.5)", True),
        ("(1|2|3)[1.5]", True),
        ("(1|2|3)['1']", True),
        ("'abc'['x']", True),
        # Singleton/multi-item violations remain invalid.
        ("(1|2|3).skip(1|2)", False),
        ("(1|2|3).take(1|2)", False),
        ("(1|2|3)[1|2]", False),
        ("(1|2).single()", False),
        # Sanity: valid subsetting forms.
        ("(1|2|3).skip(1)", True),
        ("(1|2|3).take(2)", True),
        ("(1|2|3)[0]", True),
    ],
)
def test_subsetting_argument_type_error_validity_classification_fp05_skeptic(
    expression: str,
    valid: bool,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cpp = _connection()
    py = _python_fallback_connection(monkeypatch)
    try:
        for con in (cpp, py):
            got = con.execute("SELECT fhirpath_is_valid(?)", [expression]).fetchone()[0]
            assert got is valid, f"{expression!r}: is_valid={got} expected={valid}"
    finally:
        cpp.close()
        py.close()
