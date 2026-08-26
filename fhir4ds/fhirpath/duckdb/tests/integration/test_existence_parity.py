"""Parity tests for FHIRPath existence functions in DuckDB UDFs."""

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


RESOURCE = json.dumps(
    {
        "resourceType": "Patient",
        "id": "p",
        "vals": [1, 2, 2, 3],
    }
)


def _connection() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect(config={"allow_unsigned_extensions": True})
    register_fhirpath(con)
    return con


def _python_fallback_connection(monkeypatch) -> duckdb.DuckDBPyConnection:
    monkeypatch.setattr(duckdb, "__version__", "0.0.0-forced-python-fallback")
    con = duckdb.connect(config={"allow_unsigned_extensions": True})
    assert register_fhirpath(con) is False
    return con


def test_distinct_multi_result_number_singleton_guard_matches_cpp() -> None:
    expression = "vals.distinct()"

    con = _connection()
    try:
        cpp = con.execute(
            "SELECT fhirpath(?::JSON, ?), fhirpath_text(?::JSON, ?), fhirpath_json(?::JSON, ?), fhirpath_number(?::JSON, ?)",
            [RESOURCE, expression, RESOURCE, expression, RESOURCE, expression, RESOURCE, expression],
        ).fetchone()
        py = (
            fhirpath_scalar(RESOURCE, expression),
            fhirpath_text_udf(RESOURCE, expression),
            fhirpath_json_udf(RESOURCE, expression),
            fhirpath_number_udf(RESOURCE, expression),
        )
        assert cpp == py
    finally:
        con.close()


def test_criteria_functions_expose_index_in_native_and_fallback(monkeypatch) -> None:
    resource = json.dumps({"resourceType": "Patient", "a": [10, 20, 30]})
    expressions = [
        "a.exists($index = 1)",
        "a.all($index < 3)",
        "a.all($index < 2)",
    ]

    native = _connection()
    fallback = _python_fallback_connection(monkeypatch)
    try:
        for expression in expressions:
            cpp = native.execute(
                "SELECT fhirpath(?::JSON, ?), fhirpath_json(?::JSON, ?), fhirpath_bool(?::JSON, ?)",
                [resource, expression, resource, expression, resource, expression],
            ).fetchone()
            py = fallback.execute(
                "SELECT fhirpath(?::JSON, ?), fhirpath_json(?::JSON, ?), fhirpath_bool(?::JSON, ?)",
                [resource, expression, resource, expression, resource, expression],
            ).fetchone()
            assert cpp == py
    finally:
        native.close()
        fallback.close()


def test_all_criteria_restores_index_context_in_fallback(monkeypatch) -> None:
    resource = json.dumps({"resourceType": "Patient", "a": [1, 2]})
    expression = "a.all($this > 0) | $index"
    expected = (["true"], "[true]", True)

    native = _connection()
    fallback = _python_fallback_connection(monkeypatch)
    try:
        cpp = native.execute(
            "SELECT fhirpath(?::JSON, ?), fhirpath_json(?::JSON, ?), fhirpath_bool(?::JSON, ?)",
            [resource, expression, resource, expression, resource, expression],
        ).fetchone()
        py = fallback.execute(
            "SELECT fhirpath(?::JSON, ?), fhirpath_json(?::JSON, ?), fhirpath_bool(?::JSON, ?)",
            [resource, expression, resource, expression, resource, expression],
        ).fetchone()
        direct = (
            fhirpath_scalar(resource, expression),
            fhirpath_json_udf(resource, expression),
            fhirpath_bool_udf(resource, expression),
        )
        assert cpp == py == direct == expected
    finally:
        native.close()
        fallback.close()


def test_boolean_aggregates_reject_non_boolean_collections_like_fallback(monkeypatch) -> None:
    resource = json.dumps(
        {
            "resourceType": "Patient",
            "strings": ["true", "false", "x"],
        }
    )
    expressions = [
        "strings.allTrue()",
        "strings.anyTrue()",
        "strings.allFalse()",
        "strings.anyFalse()",
    ]

    native = _connection()
    fallback = _python_fallback_connection(monkeypatch)
    try:
        for expression in expressions:
            cpp = native.execute(
                "SELECT fhirpath(?::JSON, ?), fhirpath_text(?::JSON, ?), fhirpath_json(?::JSON, ?), fhirpath_bool(?::JSON, ?)",
                [resource, expression, resource, expression, resource, expression, resource, expression],
            ).fetchone()
            py = fallback.execute(
                "SELECT fhirpath(?::JSON, ?), fhirpath_text(?::JSON, ?), fhirpath_json(?::JSON, ?), fhirpath_bool(?::JSON, ?)",
                [resource, expression, resource, expression, resource, expression, resource, expression],
            ).fetchone()
            direct = (
                fhirpath_scalar(resource, expression),
                fhirpath_text_udf(resource, expression),
                fhirpath_json_udf(resource, expression),
                fhirpath_bool_udf(resource, expression),
            )
            assert cpp == py == direct == ([], None, None, None)
    finally:
        native.close()
        fallback.close()


def test_criteria_functions_reject_non_boolean_results_like_fallback(monkeypatch) -> None:
    resource = json.dumps(
        {
            "resourceType": "Patient",
            "name": [{"given": ["Ann", "Beth"]}],
            "nums": [1, 2],
        }
    )
    expressions = [
        "name.exists(given)",
        "name.all(given)",
        "nums.exists($this)",
        "nums.all($this)",
    ]

    native = _connection()
    fallback = _python_fallback_connection(monkeypatch)
    try:
        for expression in expressions:
            cpp = native.execute(
                "SELECT fhirpath(?::JSON, ?), fhirpath_json(?::JSON, ?), fhirpath_bool(?::JSON, ?)",
                [resource, expression, resource, expression, resource, expression],
            ).fetchone()
            py = fallback.execute(
                "SELECT fhirpath(?::JSON, ?), fhirpath_json(?::JSON, ?), fhirpath_bool(?::JSON, ?)",
                [resource, expression, resource, expression, resource, expression],
            ).fetchone()
            direct = (
                fhirpath_scalar(resource, expression),
                fhirpath_json_udf(resource, expression),
                fhirpath_bool_udf(resource, expression),
            )
            assert cpp == py == direct == ([], None, None)
    finally:
        native.close()
        fallback.close()


def test_exists_criteria_validates_later_items_before_exists_result(monkeypatch) -> None:
    resource = json.dumps(
        {
            "resourceType": "Patient",
            "nested": [
                {"flags": [True]},
                {"flags": [False, True]},
            ],
        }
    )
    expression = "nested.exists(flags)"

    native = _connection()
    fallback = _python_fallback_connection(monkeypatch)
    try:
        cpp = native.execute(
            "SELECT fhirpath(?::JSON, ?), fhirpath_json(?::JSON, ?), fhirpath_bool(?::JSON, ?)",
            [resource, expression, resource, expression, resource, expression],
        ).fetchone()
        py = fallback.execute(
            "SELECT fhirpath(?::JSON, ?), fhirpath_json(?::JSON, ?), fhirpath_bool(?::JSON, ?)",
            [resource, expression, resource, expression, resource, expression],
        ).fetchone()
        direct = (
            fhirpath_scalar(resource, expression),
            fhirpath_json_udf(resource, expression),
            fhirpath_bool_udf(resource, expression),
        )
        assert cpp == py == direct == ([], None, None)
    finally:
        native.close()
        fallback.close()


def test_parenthesized_logical_operators_are_valid_in_criteria(monkeypatch) -> None:
    resource = json.dumps({"resourceType": "Patient", "a": [1, 2, 3]})
    expression = "a.all(($this > 0) and ($index < 3))"

    native = _connection()
    fallback = _python_fallback_connection(monkeypatch)
    try:
        cpp = native.execute(
            "SELECT fhirpath(?::JSON, ?), fhirpath_json(?::JSON, ?), fhirpath_bool(?::JSON, ?), fhirpath_is_valid(?)",
            [resource, expression, resource, expression, resource, expression, expression],
        ).fetchone()
        py = fallback.execute(
            "SELECT fhirpath(?::JSON, ?), fhirpath_json(?::JSON, ?), fhirpath_bool(?::JSON, ?), fhirpath_is_valid(?)",
            [resource, expression, resource, expression, resource, expression, expression],
        ).fetchone()
        assert cpp == py == (["true"], "[true]", True, True)
    finally:
        native.close()
        fallback.close()


def test_existence_helpers_reject_invalid_arity_in_native_and_fallback(monkeypatch) -> None:
    resource = json.dumps(
        {
            "resourceType": "Patient",
            "active": True,
            "name": [{"family": "Smith"}, {"family": "Jones"}],
            "telecom": [],
        }
    )
    expressions = [
        "name.empty(true)",
        "name.count(true)",
        "name.distinct(true)",
        "name.isDistinct(true)",
        "active.hasValue(true)",
        "active.allTrue(false)",
        "active.anyTrue(false)",
        "active.allFalse(false)",
        "active.anyFalse(false)",
        "name.exists(family = 'Smith', family = 'Jones')",
        "name.all()",
        "name.all(family.exists(), family = 'Smith')",
        "name.subsetOf()",
        "name.subsetOf(name, telecom)",
        "name.supersetOf()",
        "name.supersetOf(name, telecom)",
    ]

    native = _connection()
    fallback = _python_fallback_connection(monkeypatch)
    try:
        for expression in expressions:
            cpp = native.execute(
                "SELECT fhirpath_is_valid(?), fhirpath(?::JSON, ?), fhirpath_json(?::JSON, ?), fhirpath_bool(?::JSON, ?)",
                [expression, resource, expression, resource, expression, resource, expression],
            ).fetchone()
            py = fallback.execute(
                "SELECT fhirpath_is_valid(?), fhirpath(?::JSON, ?), fhirpath_json(?::JSON, ?), fhirpath_bool(?::JSON, ?)",
                [expression, resource, expression, resource, expression, resource, expression],
            ).fetchone()
            assert cpp == py == (False, [], None, None)
    finally:
        native.close()
        fallback.close()


def test_boolean_aggregates_validate_full_collection_before_short_circuit(monkeypatch) -> None:
    expressions = [
        "true.combine('x').anyTrue()",
        "false.combine('x').anyFalse()",
        "false.combine('x').allTrue()",
        "true.combine('x').allFalse()",
    ]

    native = _connection()
    fallback = _python_fallback_connection(monkeypatch)
    try:
        for expression in expressions:
            cpp = native.execute(
                "SELECT fhirpath(?::JSON, ?), fhirpath_json(?::JSON, ?), fhirpath_bool(?::JSON, ?)",
                ["{}", expression, "{}", expression, "{}", expression],
            ).fetchone()
            py = fallback.execute(
                "SELECT fhirpath(?::JSON, ?), fhirpath_json(?::JSON, ?), fhirpath_bool(?::JSON, ?)",
                ["{}", expression, "{}", expression, "{}", expression],
            ).fetchone()
            direct = (
                fhirpath_scalar("{}", expression),
                fhirpath_json_udf("{}", expression),
                fhirpath_bool_udf("{}", expression),
            )
            assert cpp == py == direct == ([], None, None)
    finally:
        native.close()
        fallback.close()


def test_distinct_uses_fhirpath_equality_for_numeric_literals(monkeypatch) -> None:
    expressions = [
        "1.combine(1.0).distinct().count()",
        "1.combine(1.0).isDistinct()",
    ]

    native = _connection()
    fallback = _python_fallback_connection(monkeypatch)
    try:
        for expression in expressions:
            cpp = native.execute(
                "SELECT fhirpath(?::JSON, ?), fhirpath_json(?::JSON, ?), fhirpath_bool(?::JSON, ?)",
                ["{}", expression, "{}", expression, "{}", expression],
            ).fetchone()
            py = fallback.execute(
                "SELECT fhirpath(?::JSON, ?), fhirpath_json(?::JSON, ?), fhirpath_bool(?::JSON, ?)",
                ["{}", expression, "{}", expression, "{}", expression],
            ).fetchone()
            assert cpp == py

        assert native.execute(
            "SELECT fhirpath(?::JSON, ?), fhirpath_bool(?::JSON, ?)",
            ["{}", "1.combine(1.0).distinct().count() = 1", "{}", "1.combine(1.0).isDistinct().not()"],
        ).fetchone() == (["true"], True)
    finally:
        native.close()
        fallback.close()


def test_distinct_uses_structural_equality_for_complex_json(monkeypatch) -> None:
    resource = json.dumps(
        {
            "resourceType": "Patient",
            "objs": [{"a": 1, "b": 2}, {"b": 2, "a": 1}],
        }
    )
    expressions = [
        "objs.distinct().count()",
        "objs.isDistinct()",
        "objs.first().subsetOf(objs.last())",
        "objs.first() = objs.last()",
    ]

    native = _connection()
    fallback = _python_fallback_connection(monkeypatch)
    try:
        for expression in expressions:
            cpp = native.execute(
                "SELECT fhirpath(?::JSON, ?), fhirpath_json(?::JSON, ?), fhirpath_bool(?::JSON, ?)",
                [resource, expression, resource, expression, resource, expression],
            ).fetchone()
            py = fallback.execute(
                "SELECT fhirpath(?::JSON, ?), fhirpath_json(?::JSON, ?), fhirpath_bool(?::JSON, ?)",
                [resource, expression, resource, expression, resource, expression],
            ).fetchone()
            assert cpp == py

        assert native.execute(
            "SELECT fhirpath(?::JSON, ?), fhirpath_bool(?::JSON, ?)",
            [resource, "objs.distinct().count() = 1", resource, "objs.isDistinct().not()"],
        ).fetchone() == (["true"], True)
    finally:
        native.close()
        fallback.close()


def test_membership_and_distinct_use_quantity_equality_for_compatible_units(monkeypatch) -> None:
    expressions = [
        "(1 'cm').subsetOf(10 'mm')",
        "(1 'cm').supersetOf(10 'mm')",
        "(1 'cm').combine(10 'mm').distinct().count()",
        "(1 'cm').combine(10 'mm').isDistinct()",
    ]

    native = _connection()
    fallback = _python_fallback_connection(monkeypatch)
    try:
        for expression in expressions:
            cpp = native.execute(
                "SELECT fhirpath(?::JSON, ?), fhirpath_json(?::JSON, ?), fhirpath_bool(?::JSON, ?)",
                ["{}", expression, "{}", expression, "{}", expression],
            ).fetchone()
            py = fallback.execute(
                "SELECT fhirpath(?::JSON, ?), fhirpath_json(?::JSON, ?), fhirpath_bool(?::JSON, ?)",
                ["{}", expression, "{}", expression, "{}", expression],
            ).fetchone()
            assert cpp == py

        assert native.execute(
            "SELECT fhirpath_bool(?::JSON, ?), fhirpath_bool(?::JSON, ?), fhirpath_bool(?::JSON, ?)",
            [
                "{}",
                "(1 'cm').subsetOf(10 'mm')",
                "{}",
                "(1 'cm').combine(10 'mm').distinct().count() = 1",
                "{}",
                "(1 'cm').combine(10 'mm').isDistinct().not()",
            ],
        ).fetchone() == (True, True, True)
    finally:
        native.close()
        fallback.close()


def test_set_comparison_arguments_use_scoped_focus_in_native_and_fallback(monkeypatch) -> None:
    resource = json.dumps(
        {
            "resourceType": "Patient",
            "groups": [
                {"left": [1, 2], "right": [1, 2, 3]},
                {"left": [1, 4], "right": [1, 2, 3]},
            ],
        }
    )
    expressions = {
        "groups.select(left.subsetOf(right))": (["true", "false"], "[true,false]", True),
        "groups.exists(left.subsetOf(right))": (["true"], "[true]", True),
        "groups.all(right.supersetOf(left))": (["false"], "[false]", False),
        "groups.exists(right.supersetOf(left).not())": (["true"], "[true]", True),
        "groups.select(right.supersetOf(left))": (["true", "false"], "[true,false]", True),
    }

    native = _connection()
    fallback = _python_fallback_connection(monkeypatch)
    try:
        for expression, expected in expressions.items():
            cpp = native.execute(
                "SELECT fhirpath(?::JSON, ?), fhirpath_json(?::JSON, ?), fhirpath_bool(?::JSON, ?)",
                [resource, expression, resource, expression, resource, expression],
            ).fetchone()
            py = fallback.execute(
                "SELECT fhirpath(?::JSON, ?), fhirpath_json(?::JSON, ?), fhirpath_bool(?::JSON, ?)",
                [resource, expression, resource, expression, resource, expression],
            ).fetchone()
            assert cpp == py == expected
    finally:
        native.close()
        fallback.close()


def test_bare_exists_no_arg_matches_count_gt_zero_in_native_and_fallback(monkeypatch) -> None:
    """FHIRPath §5.1.2: no-arg ``exists()`` is equivalent to ``count() > 0``.

    Previously native C++ silently returned an empty collection ``[]`` for
    the bare form (without a source) while the forced Python fallback
    returned ``[true]`` on a non-empty focus. This case locks down the fix
    across both backends and on empty/non-empty/criteria forms.
    """
    resource = json.dumps({"resourceType": "Patient", "vals": [1, 2, 3]})

    expressions = {
        # Bare no-source no-arg form must mirror count() > 0.
        # Tuple is (fhirpath list, fhirpath_json, fhirpath_bool).
        "exists()": (["true"], "[true]", True),
        "{}.exists()": (["false"], "[false]", False),
        "(1).exists()": (["true"], "[true]", True),
        "(1 | 2).exists()": (["true"], "[true]", True),
        # Resource-backed method form must keep working
        "vals.exists()": (["true"], "[true]", True),
        "vals.exists($this > 2)": (["true"], "[true]", True),
        "vals.exists($this > 10)": (["false"], "[false]", False),
        # No-arg form on missing resource path returns false (not empty)
        "missing.exists()": (["false"], "[false]", False),
    }

    native = _connection()
    fallback = _python_fallback_connection(monkeypatch)
    try:
        for expression, expected in expressions.items():
            cpp = native.execute(
                "SELECT fhirpath(?::JSON, ?), fhirpath_json(?::JSON, ?), fhirpath_bool(?::JSON, ?)",
                [resource, expression, resource, expression, resource, expression],
            ).fetchone()
            py = fallback.execute(
                "SELECT fhirpath(?::JSON, ?), fhirpath_json(?::JSON, ?), fhirpath_bool(?::JSON, ?)",
                [resource, expression, resource, expression, resource, expression],
            ).fetchone()
            assert cpp == py == expected, expression
    finally:
        native.close()


def test_criteria_comparison_type_error_parity_fp03_skeptic(monkeypatch) -> None:
    """FP-03 SKEPTIC QA-001 (2026-08-16): §6.2 comparison type errors must
    signal an evaluation error, not degrade to an empty result.

    Native C++ used to return ``{}`` for incompatible comparison operand
    types. Masked at the UDF top level (error and empty both surface as
    NULL) but decisive inside iteration functions: ``all()``/``exists()``/
    ``where()``/``select()`` criteria and ``iif`` criteria converted the
    empty criteria result into false/no-match, silently producing wrong
    Booleans and collections (``mixed.all($this > 0)`` → false,
    ``mixed.exists($this > 0)`` → true) while the Python fallback errored
    to empty per §6.2 ("the evaluator will throw an error if the types
    differ").
    """
    resource = json.dumps({"resourceType": "Patient", "mixed": [1, "a"], "t": True})

    empty_result_expressions = [
        # §6.2 type-error criteria inside §5.1 iteration functions
        "mixed.all($this > 0)",
        "mixed.all($this < 5)",
        "mixed.exists($this > 0)",
        "mixed.exists($this < 5)",
        "mixed.where($this > 0)",
        "mixed.select($this > 0)",
        "iif('a' > 0, 1, 2)",
        "iif(1 > t, 1, 2)",
        # Top-level type-mismatch comparisons stay empty (wrapper converts
        # the §6.2 evaluation error to an empty result for row resilience)
        "'a' < 1",
        "1 < t",
        "t > f",
        "'a' > t",
    ]
    spec_empty_expressions = [
        # Spec-mandated empty comparison results that must NOT become errors
        "@2018-03 < @2018-03-01",
        "@T10 < @T10:30",
        "1 year > 1 'a'",
        "1 'Cel' < 33.8 '[degF]'",
        "1 'cm' < 1 's'",
    ]
    value_expressions = {
        # Healthy comparisons keep evaluating
        "mixed.all($this = 1)": (["false"], "[false]", False),
        "mixed.exists($this = 1)": (["true"], "[true]", True),
        "nums_ok.all($this > 0)": (["true"], "[true]", True),
    }
    resource = json.dumps({"resourceType": "Patient", "mixed": [1, "a"], "t": True, "nums_ok": [3, 4]})

    from fhir4ds.fhirpath.duckdb.udf import fhirpath_is_valid_udf

    native = _connection()
    fallback = _python_fallback_connection(monkeypatch)
    try:
        for expression in empty_result_expressions + spec_empty_expressions:
            cpp = native.execute(
                "SELECT fhirpath(?::JSON, ?), fhirpath_json(?::JSON, ?), fhirpath_bool(?::JSON, ?)",
                [resource, expression, resource, expression, resource, expression],
            ).fetchone()
            py = fallback.execute(
                "SELECT fhirpath(?::JSON, ?), fhirpath_json(?::JSON, ?), fhirpath_bool(?::JSON, ?)",
                [resource, expression, resource, expression, resource, expression],
            ).fetchone()
            assert cpp == py == ([], None, None), expression
        for expression, expected in value_expressions.items():
            cpp = native.execute(
                "SELECT fhirpath(?::JSON, ?), fhirpath_json(?::JSON, ?), fhirpath_bool(?::JSON, ?)",
                [resource, expression, resource, expression, resource, expression],
            ).fetchone()
            py = fallback.execute(
                "SELECT fhirpath(?::JSON, ?), fhirpath_json(?::JSON, ?), fhirpath_bool(?::JSON, ?)",
                [resource, expression, resource, expression, resource, expression],
            ).fetchone()
            assert cpp == py == expected, expression
        for expression in empty_result_expressions:
            # Execution type errors are valid expressions (FP-02 QA-002 /
            # FP-03 QA-001 doctrine) on both surfaces.
            assert fhirpath_is_valid_udf(expression) is True, expression
    finally:
        native.close()
        fallback.close()


def test_time_string_ordering_not_coerced_parity_fp03_skeptic(monkeypatch) -> None:
    """FP-03 SKEPTIC QA-002 (2026-08-16): time-shaped plain strings are not
    implicitly coerced against ``@T...`` Time literals for ordering.

    Per the §5.5 conversion table String→Time is Explicit-only, matching the
    pinned Time-vs-String equality convention (FP-01 QA-003). The Python
    fallback's comparison typecheck used to coerce ``'10:00'`` into an
    ``FP_Time`` for ordering (``'10:00' < @T10:30`` → true) while the native
    engine signaled the §6.2 type error (empty). Date/DateTime-shaped string
    ordering coercion is a shared convention in both engines and stays.
    """
    resource = json.dumps({"resourceType": "Patient"})

    empty_expressions = [
        "@T10:30 < '10:00'",
        "'10:00' < @T10:30",
        "@T10:30 < '10:30'",
        "'10:00' < @2018-01-01",
        "@T10 < 'a'",
    ]
    value_expressions = {
        # Date/DateTime-shaped string ordering coercion stays shared.
        "'2018-01-01' < @2018-03-01": (["true"], "[true]", True),
        "@2018-03-01 < '2019-01-01'": (["true"], "[true]", True),
        "'2018' < '2019'": (["true"], "[true]", True),
        # Time-vs-Time literal ordering unchanged.
        "@T10:30:00 < @T10:30:01": (["true"], "[true]", True),
    }

    native = _connection()
    fallback = _python_fallback_connection(monkeypatch)
    try:
        for expression in empty_expressions:
            cpp = native.execute(
                "SELECT fhirpath(?::JSON, ?), fhirpath_json(?::JSON, ?), fhirpath_bool(?::JSON, ?)",
                [resource, expression, resource, expression, resource, expression],
            ).fetchone()
            py = fallback.execute(
                "SELECT fhirpath(?::JSON, ?), fhirpath_json(?::JSON, ?), fhirpath_bool(?::JSON, ?)",
                [resource, expression, resource, expression, resource, expression],
            ).fetchone()
            assert cpp == py == ([], None, None), expression
        for expression, expected in value_expressions.items():
            cpp = native.execute(
                "SELECT fhirpath(?::JSON, ?), fhirpath_json(?::JSON, ?), fhirpath_bool(?::JSON, ?)",
                [resource, expression, resource, expression, resource, expression],
            ).fetchone()
            py = fallback.execute(
                "SELECT fhirpath(?::JSON, ?), fhirpath_json(?::JSON, ?), fhirpath_bool(?::JSON, ?)",
                [resource, expression, resource, expression, resource, expression],
            ).fetchone()
            assert cpp == py == expected, expression
    finally:
        native.close()
        fallback.close()
        fallback.close()

