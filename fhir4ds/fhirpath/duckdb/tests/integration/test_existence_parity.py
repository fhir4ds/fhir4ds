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
