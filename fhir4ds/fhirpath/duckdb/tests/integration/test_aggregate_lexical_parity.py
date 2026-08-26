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


def test_aggregate_init_expression_uses_outer_focus_like_fallback(monkeypatch) -> None:
    resource = json.dumps({"resourceType": "Patient", "seed": 10, "a": [1, 2, 3]})
    expressions = {
        "a.aggregate($total + $this, seed)": (["16"], "[16]", "16", True),
        "{}.aggregate($this + $total, seed)": (["10"], "[10]", "10", True),
    }

    con = _connection()
    fallback = _fallback_connection(monkeypatch)
    try:
        for expression, expected in expressions.items():
            native = con.execute(
                "SELECT fhirpath(?::JSON, ?), fhirpath_json(?::JSON, ?), fhirpath_text(?::JSON, ?), fhirpath_is_valid(?)",
                [resource, expression, resource, expression, resource, expression, expression],
            ).fetchone()
            py = fallback.execute(
                "SELECT fhirpath(?::JSON, ?), fhirpath_json(?::JSON, ?), fhirpath_text(?::JSON, ?), fhirpath_is_valid(?)",
                [resource, expression, resource, expression, resource, expression, expression],
            ).fetchone()
            assert native == expected
            assert native == py
    finally:
        con.close()
        fallback.close()


def test_aggregate_arity_matches_fallback(monkeypatch) -> None:
    resource = json.dumps({"resourceType": "Patient", "a": [1, 2, 3]})
    invalid_expressions = [
        "a.aggregate()",
        "a.aggregate($this, 0, 1)",
        "aggregate()",
        "aggregate($this, {}, {})",
    ]

    con = _connection()
    fallback = _fallback_connection(monkeypatch)
    try:
        for expression in invalid_expressions:
            native = con.execute(
                "SELECT fhirpath(?::JSON, ?), fhirpath_json(?::JSON, ?), fhirpath_is_valid(?)",
                [resource, expression, resource, expression, expression],
            ).fetchone()
            py = fallback.execute(
                "SELECT fhirpath(?::JSON, ?), fhirpath_json(?::JSON, ?), fhirpath_is_valid(?)",
                [resource, expression, resource, expression, expression],
            ).fetchone()
            assert native == ([], None, False)
            assert native == py
    finally:
        con.close()
        fallback.close()


def test_reserved_keywords_and_strict_whitespace_match_fallback(monkeypatch) -> None:
    resource = json.dumps({"resourceType": "Patient", "div": "d", "mod": "m"})
    valid_delimited = {
        "`div`": (["d"], "d", True),
        "`mod`": (["m"], "m", True),
    }
    invalid_expressions = [
        "div",
        "mod",
        "1\f+\f2",
        "1\v+\v2",
    ]

    con = _connection()
    fallback = _fallback_connection(monkeypatch)
    try:
        for expression, expected in valid_delimited.items():
            native = con.execute(
                "SELECT fhirpath(?::JSON, ?), fhirpath_text(?::JSON, ?), fhirpath_is_valid(?)",
                [resource, expression, resource, expression, expression],
            ).fetchone()
            py = fallback.execute(
                "SELECT fhirpath(?::JSON, ?), fhirpath_text(?::JSON, ?), fhirpath_is_valid(?)",
                [resource, expression, resource, expression, expression],
            ).fetchone()
            assert native == expected
            assert native == py

        for expression in invalid_expressions:
            assert con.execute("SELECT fhirpath_is_valid(?)", [expression]).fetchone() == (False,)
            assert fallback.execute("SELECT fhirpath_is_valid(?)", [expression]).fetchone() == (False,)
    finally:
        con.close()
        fallback.close()


def test_pathological_expression_depth_does_not_silently_return_empty_fp19_explorer(
    monkeypatch,
) -> None:
    """FP-19 EXPLORER QA-001 (2026-06-30): pathological-depth expressions
    must evaluate correctly in the Python fallback, not silently return
    empty due to Python ``RecursionError``.

    Without the ``_eval_with_recursion_budget`` wrapper in
    ``fhir4ds/fhirpath/duckdb/udf.py``, the recursive ``do_eval`` evaluator
    hits Python's default recursion limit at ~250 syntactic markers, and
    the row-resilient UDF wrapper swallows the resulting
    ``FHIRPathEvaluationError`` as empty. Native C++ has no such limit.

    Reproducer (pre-fix):
    - ``(1 | 2 | ... | 500).aggregate($this + $total, 0)`` returned
      ``125250`` (native) vs ``None`` (fallback).
    - ``(((((...((1))...)))))`` 300-deep returned ``1`` (native) vs
      ``None`` (fallback).
    """
    resource = json.dumps({"resourceType": "Patient", "id": "fp19-deep"})

    # 500-element union aggregate — must return 125250 in both backends
    big_union_500 = " | ".join(str(i) for i in range(1, 501))
    aggregate_expr = f"({big_union_500}).aggregate($this + $total, 0)"

    # 300-deep parenthesization — must return 1 in both backends
    deep_parens_300 = "(" * 300 + "1" + ")" * 300

    # 300-deep not() chain via method invocation — must return same Boolean
    # in both backends (parity is the requirement; the value depends on
    # parity of nesting).
    deep_not_300 = "true" + ".not()" * 300

    con = _connection()
    fallback = _fallback_connection(monkeypatch)
    try:
        # Aggregate over 500-element union
        native_agg = con.execute(
            "SELECT fhirpath_text(?::JSON, ?)", [resource, aggregate_expr]
        ).fetchone()[0]
        fallback_agg = fallback.execute(
            "SELECT fhirpath_text(?::JSON, ?)", [resource, aggregate_expr]
        ).fetchone()[0]
        assert native_agg == "125250", f"native aggregate sum: {native_agg}"
        assert fallback_agg == "125250", f"fallback aggregate sum: {fallback_agg}"

        # Validity check on pathological-depth expression
        native_valid = con.execute(
            "SELECT fhirpath_is_valid(?)", [aggregate_expr]
        ).fetchone()[0]
        fallback_valid = fallback.execute(
            "SELECT fhirpath_is_valid(?)", [aggregate_expr]
        ).fetchone()[0]
        assert native_valid is True, f"native validity: {native_valid}"
        assert fallback_valid is True, f"fallback validity: {fallback_valid}"

        # Deep parenthesization
        native_parens = con.execute(
            "SELECT fhirpath_text(?::JSON, ?)", [resource, deep_parens_300]
        ).fetchone()[0]
        fallback_parens = fallback.execute(
            "SELECT fhirpath_text(?::JSON, ?)", [resource, deep_parens_300]
        ).fetchone()[0]
        assert native_parens == "1", f"native deep parens: {native_parens}"
        assert fallback_parens == "1", f"fallback deep parens: {fallback_parens}"

        # Deep not() chain — 300 is even, so result is true
        native_not = con.execute(
            "SELECT fhirpath_bool(?::JSON, ?)", [resource, deep_not_300]
        ).fetchone()[0]
        fallback_not = fallback.execute(
            "SELECT fhirpath_bool(?::JSON, ?)", [resource, deep_not_300]
        ).fetchone()[0]
        assert native_not == fallback_not, (
            f"deep not() divergence: native={native_not}, fallback={fallback_not}"
        )
        assert native_not in (True, False), f"deep not() result: {native_not}"
    finally:
        con.close()
        fallback.close()


def test_incompatible_arithmetic_errors_abort_parents_fp19_explorer(
    monkeypatch,
) -> None:
    """FP-19 EXPLORER QA-001: N1 §6.6 — incompatible-type arithmetic operands
    signal an error that aborts parent expressions. Previously the native
    evaluator degraded the arithmetic to an empty collection, so parents kept
    evaluating: `(1+'x') | 99` returned ['99'] natively but [] on the fallback.
    """
    resource = json.dumps({"resourceType": "Patient", "id": "p1", "o": {"k": 1}})
    expressions = [
        "(1+'x') | 99",
        "99 | (1+'x')",
        "(1+true) | 99",
        "(1+o) | 99",
        "('a'-'b') | 99",
        "(1|'x').aggregate($this+$total, 0).count()",
        "(1|2).aggregate($this+'x', 0) | 99",
    ]
    con = _connection()
    fallback = _fallback_connection(monkeypatch)
    try:
        for expression in expressions:
            native = con.execute(
                "SELECT fhirpath(?::JSON, ?)", [resource, expression]
            ).fetchone()[0]
            fb = fallback.execute(
                "SELECT fhirpath(?::JSON, ?)", [resource, expression]
            ).fetchone()[0]
            assert native == fb == [], (
                f"{expression}: native={native}, fallback={fb}"
            )
        # Top-level incompatible arithmetic is empty on both, and is_valid
        # accepts it as an execution type error (parity).
        native_valid = con.execute("SELECT fhirpath_is_valid(?)", ["1+'x'"]).fetchone()[0]
        fallback_valid = fallback.execute(
            "SELECT fhirpath_is_valid(?)", ["1+'x'"]
        ).fetchone()[0]
        assert native_valid is fallback_valid is True
    finally:
        con.close()
        fallback.close()


def test_mixed_unit_quantity_sum_uses_most_granular_unit_fp19_explorer(
    monkeypatch,
) -> None:
    """FP-19 EXPLORER QA-002: N1 §6.6.3 — different-unit quantity arithmetic
    converts to the most granular input unit (3 'm' + 3 'cm' // 303 'cm').
    Previously the native evaluator returned the canonical base unit
    (3.5 'wk' + 2 'd' -> 2289600 's') diverging from the fallback's 26.5 'd'.
    """
    resource = json.dumps({"resourceType": "Patient", "id": "p1"})
    expressions = [
        ("1 'cm' + 1 'm'", "101 'cm'"),
        ("1 'm' + 1 'cm'", "101 'cm'"),
        ("3 'm' + 3 'cm'", "303 'cm'"),
        ("3.5 'wk' + 2 'd'", "26.5 'd'"),
        ("3.5 'wk' - 2 'd'", "22.5 'd'"),
    ]
    con = _connection()
    fallback = _fallback_connection(monkeypatch)
    try:
        for expression, expected in expressions:
            native = con.execute(
                "SELECT fhirpath_text(?::JSON, ?)", [resource, expression]
            ).fetchone()[0]
            fb = fallback.execute(
                "SELECT fhirpath_text(?::JSON, ?)", [resource, expression]
            ).fetchone()[0]
            assert native == fb == expected, (
                f"{expression}: native={native}, fallback={fb}, expected={expected}"
            )
    finally:
        con.close()
        fallback.close()
