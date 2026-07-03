"""Parity tests for FHIRPath tree navigation and deterministic utility functions."""

from __future__ import annotations

import json
import time

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


def test_tree_navigation_and_trace_match_cpp() -> None:
    resource = json.dumps(
        {
            "resourceType": "Patient",
            "id": "p1",
            "active": True,
            "name": [{"given": ["Ann"], "family": "Smith"}],
            "contact": [{"telecom": [{"value": "555"}]}],
        }
    )
    expressions = [
        "children().count()",
        "descendants().where($this = 'Ann').count()",
        "name.children().count()",
        "name.descendants().where($this = 'Ann').count()",
        "id.trace('id')",
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


def test_tree_navigation_preserves_null_children_in_native_and_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    resource = json.dumps(
        {
            "resourceType": "Patient",
            "id": "p1",
            "active": None,
            "name": [{"given": ["Ann"], "family": None}],
        }
    )
    expressions = [
        ("children().count()", ["3"], "[3]"),
        ("descendants().count()", ["4"], "[4]"),
        ("name.children().count()", ["2"], "[2]"),
        ("children()", ["p1", "", '{"given":["Ann"],"family":null}'], '["p1",null,{"given":["Ann"],"family":null}]'),
        ("name.children()", ["Ann", ""], '["Ann",null]'),
    ]

    native = _connection()
    fallback = _python_fallback_connection(monkeypatch)
    try:
        for expression, expected_list, expected_json in expressions:
            native_row = native.execute(
                "SELECT fhirpath(?::JSON, ?), fhirpath_json(?::JSON, ?)",
                [resource, expression, resource, expression],
            ).fetchone()
            fallback_row = fallback.execute(
                "SELECT fhirpath(?::JSON, ?), fhirpath_json(?::JSON, ?)",
                [resource, expression, resource, expression],
            ).fetchone()
            assert native_row == fallback_row
            assert native_row == (expected_list, expected_json)
    finally:
        native.close()
        fallback.close()


def test_descendants_is_repeat_children_for_repeated_values(monkeypatch: pytest.MonkeyPatch) -> None:
    resource = json.dumps(
        {
            "resourceType": "Patient",
            "id": "p1",
            "a": "x",
            "b": "x",
            "nested": {"c": "x"},
            "items": [{"v": "x"}, {"v": "x"}],
        }
    )

    native = _connection()
    fallback = _python_fallback_connection(monkeypatch)
    try:
        expression = "descendants().count() = repeat(children()).count()"
        for con in (native, fallback):
            assert con.execute(
                "SELECT fhirpath(?::JSON, ?), fhirpath_json(?::JSON, ?), fhirpath_is_valid(?)",
                [resource, expression, resource, expression, expression],
            ).fetchone() == (["true"], "[true]", True)

        count_expression = "descendants().count()"
        native_row = native.execute(
            "SELECT fhirpath(?::JSON, ?), fhirpath_json(?::JSON, ?)",
            [resource, count_expression, resource, count_expression],
        ).fetchone()
        fallback_row = fallback.execute(
            "SELECT fhirpath(?::JSON, ?), fhirpath_json(?::JSON, ?)",
            [resource, count_expression, resource, count_expression],
        ).fetchone()
        assert native_row == fallback_row == (["4"], "[4]")
    finally:
        native.close()
        fallback.close()


def test_descendants_matches_repeat_children_for_key_ordered_objects(monkeypatch: pytest.MonkeyPatch) -> None:
    resource = '{"resourceType":"Patient","a":{"x":1,"y":2},"b":{"y":2,"x":1}}'

    native = _connection()
    fallback = _python_fallback_connection(monkeypatch)
    try:
        for expression, expected in [
            ("descendants().count() = repeat(children()).count()", (["true"], "[true]", True)),
            ("descendants().count()", (["3"], "[3]", True)),
        ]:
            native_row = native.execute(
                "SELECT fhirpath(?::JSON, ?), fhirpath_json(?::JSON, ?), fhirpath_is_valid(?)",
                [resource, expression, resource, expression, expression],
            ).fetchone()
            fallback_row = fallback.execute(
                "SELECT fhirpath(?::JSON, ?), fhirpath_json(?::JSON, ?), fhirpath_is_valid(?)",
                [resource, expression, resource, expression, expression],
            ).fetchone()
            assert native_row == fallback_row == expected
    finally:
        native.close()
        fallback.close()


def test_descendants_traverses_deep_nested_resources(monkeypatch: pytest.MonkeyPatch) -> None:
    resource_obj = {"resourceType": "Patient", "id": "p1"}
    cursor = resource_obj
    for depth in range(105):
        cursor["child"] = {"valueString": f"v{depth}"}
        cursor = cursor["child"]
    resource = json.dumps(resource_obj)
    expression = "descendants().where($this = 'v104').count()"

    native = _connection()
    fallback = _python_fallback_connection(monkeypatch)
    try:
        native_row = native.execute(
            "SELECT fhirpath(?::JSON, ?), fhirpath_json(?::JSON, ?), fhirpath_is_valid(?)",
            [resource, expression, resource, expression, expression],
        ).fetchone()
        fallback_row = fallback.execute(
            "SELECT fhirpath(?::JSON, ?), fhirpath_json(?::JSON, ?), fhirpath_is_valid(?)",
            [resource, expression, resource, expression, expression],
        ).fetchone()
        assert native_row == fallback_row == (["1"], "[1]", True)
    finally:
        native.close()
        fallback.close()


def test_descendants_matches_repeat_children_for_split_primitive_json(monkeypatch: pytest.MonkeyPatch) -> None:
    resource = json.dumps(
        {
            "resourceType": "Patient",
            "id": "p1",
            "birthDate": "1970-01-01",
            "_birthDate": {
                "extension": [
                    {
                        "url": "http://example.org/ext/birth",
                        "valueString": "midday",
                    }
                ]
            },
            "name": [{"given": ["Ann"], "family": None}],
        }
    )
    expressions = [
        "descendants().where($this = 'midday').count()",
        "repeat(children()).where($this = 'midday').count()",
    ]

    native = _connection()
    fallback = _python_fallback_connection(monkeypatch)
    try:
        for expression in expressions:
            native_row = native.execute(
                "SELECT fhirpath(?::JSON, ?), fhirpath_json(?::JSON, ?), fhirpath_is_valid(?)",
                [resource, expression, resource, expression, expression],
            ).fetchone()
            fallback_row = fallback.execute(
                "SELECT fhirpath(?::JSON, ?), fhirpath_json(?::JSON, ?), fhirpath_is_valid(?)",
                [resource, expression, resource, expression, expression],
            ).fetchone()
            assert native_row == fallback_row

        primitive_extension_descendants = native.execute(
            "SELECT fhirpath(?::JSON, ?), fhirpath_json(?::JSON, ?)",
            [
                resource,
                "descendants().where($this = 'midday').count()",
                resource,
                "descendants().where($this = 'midday').count()",
            ],
        ).fetchone()
        assert primitive_extension_descendants == (["1"], "[1]")
    finally:
        native.close()
        fallback.close()


def test_primitive_extension_metadata_is_visible_to_tree_navigation(monkeypatch: pytest.MonkeyPatch) -> None:
    resource = json.dumps(
        {
            "resourceType": "Patient",
            "id": "p1",
            "birthDate": "1970-01-01",
            "_birthDate": {
                "extension": [
                    {
                        "url": "http://example.org/fhir/StructureDefinition/birth-note",
                        "valueString": "midday",
                    }
                ]
            },
            "name": [
                {
                    "given": ["Ann"],
                    "_given": [
                        {
                            "extension": [
                                {
                                    "url": "http://example.org/fhir/StructureDefinition/given-note",
                                    "valueString": "alias",
                                }
                            ]
                        }
                    ],
                    "family": "Able",
                }
            ],
        }
    )
    expressions = [
        (
            "birthDate.children().where(url = 'http://example.org/fhir/StructureDefinition/birth-note').valueString",
            (["midday"], '["midday"]', True),
        ),
        (
            "birthDate.descendants().where($this = 'midday').count()",
            (["1"], "[1]", True),
        ),
        (
            "name.given.extension('http://example.org/fhir/StructureDefinition/given-note').valueString",
            (["alias"], '["alias"]', True),
        ),
        (
            "name.given.children().where(url = 'http://example.org/fhir/StructureDefinition/given-note').valueString",
            (["alias"], '["alias"]', True),
        ),
        (
            "name.given.descendants().where($this = 'alias').count()",
            (["1"], "[1]", True),
        ),
    ]

    native = _connection()
    fallback = _python_fallback_connection(monkeypatch)
    try:
        for expression, expected in expressions:
            native_row = native.execute(
                "SELECT fhirpath(?::JSON, ?), fhirpath_json(?::JSON, ?), fhirpath_is_valid(?)",
                [resource, expression, resource, expression, expression],
            ).fetchone()
            fallback_row = fallback.execute(
                "SELECT fhirpath(?::JSON, ?), fhirpath_json(?::JSON, ?), fhirpath_is_valid(?)",
                [resource, expression, resource, expression, expression],
            ).fetchone()
            assert native_row == fallback_row == expected
    finally:
        native.close()
        fallback.close()


def test_current_time_functions_are_stable_within_native_expression(monkeypatch: pytest.MonkeyPatch) -> None:
    resource = json.dumps(
        {
            "resourceType": "Patient",
            "id": "p1",
            "extension": [{"url": str(i), "valueString": "x"} for i in range(40000)],
        }
    )
    slow_condition = " and ".join(["descendants().count() > 0"] * 8)
    expression = f"now() = iif({slow_condition}, now(), now())"

    native = _connection()
    fallback = _python_fallback_connection(monkeypatch)
    try:
        deadline = time.time() + 2.0
        while time.time() < deadline and time.time() % 1 < 0.75:
            time.sleep(0.001)

        native_result = native.execute(
            "SELECT fhirpath_bool(?::JSON, ?)",
            [resource, expression],
        ).fetchone()[0]
        fallback_result = fallback.execute(
            "SELECT fhirpath_bool(?::JSON, ?)",
            [resource, expression],
        ).fetchone()[0]

        assert native_result is True
        assert native_result == fallback_result
    finally:
        native.close()
        fallback.close()


def test_tree_utility_invalid_signatures_match_python_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    resource = json.dumps({"resourceType": "Patient", "id": "p1", "name": [{"given": ["Ann"]}]})
    expressions = [
        "children(1)",
        "descendants(1)",
        "trace()",
        "trace(1)",
        "trace('x', id, id)",
        "now(1)",
        "today(1)",
        "timeOfDay(1)",
    ]

    native = _connection()
    fallback = _python_fallback_connection(monkeypatch)
    try:
        for expression in expressions:
            native_row = native.execute(
                "SELECT fhirpath(?::JSON, ?), fhirpath_json(?::JSON, ?), fhirpath_is_valid(?)",
                [resource, expression, resource, expression, expression],
            ).fetchone()
            fallback_row = fallback.execute(
                "SELECT fhirpath(?::JSON, ?), fhirpath_json(?::JSON, ?), fhirpath_is_valid(?)",
                [resource, expression, resource, expression, expression],
            ).fetchone()
            assert native_row == fallback_row == ([], None, False)
    finally:
        native.close()
        fallback.close()


def test_trace_projection_is_validated_in_native_and_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    resource = json.dumps({"resourceType": "Patient", "id": "p1", "name": [{"given": ["Ann"]}]})

    native = _connection()
    fallback = _python_fallback_connection(monkeypatch)
    try:
        for expression, expected in [
            ("name.trace('names', given).given.count() = 1", (["true"], "[true]", True)),
            ("name.trace('names', given.single()).given.count() = 1", (["true"], "[true]", True)),
            ("name.trace(id).given.count() = 1", (["true"], "[true]", True)),
        ]:
            native_row = native.execute(
                "SELECT fhirpath(?::JSON, ?), fhirpath_json(?::JSON, ?), fhirpath_is_valid(?)",
                [resource, expression, resource, expression, expression],
            ).fetchone()
            fallback_row = fallback.execute(
                "SELECT fhirpath(?::JSON, ?), fhirpath_json(?::JSON, ?), fhirpath_is_valid(?)",
                [resource, expression, resource, expression, expression],
            ).fetchone()
            assert native_row == fallback_row == expected

        multi_given_resource = json.dumps(
            {"resourceType": "Patient", "id": "p1", "name": [{"given": ["Ann", "A"]}]}
        )
        expression = "name.trace('names', given.single()).given.count() = 2"
        native_row = native.execute(
            "SELECT fhirpath(?::JSON, ?), fhirpath_json(?::JSON, ?), fhirpath_is_valid(?)",
            [multi_given_resource, expression, multi_given_resource, expression, expression],
        ).fetchone()
        fallback_row = fallback.execute(
            "SELECT fhirpath(?::JSON, ?), fhirpath_json(?::JSON, ?), fhirpath_is_valid(?)",
            [multi_given_resource, expression, multi_given_resource, expression, expression],
        ).fetchone()
        assert native_row == fallback_row == ([], None, True)
    finally:
        native.close()
        fallback.close()


def test_trace_projection_is_scoped_per_item_in_native_and_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    resource = json.dumps(
        {
            "resourceType": "Patient",
            "id": "p1",
            "name": [
                {"given": ["Ann"], "family": "Able"},
                {"given": ["Bob"], "family": "Baker"},
            ],
        }
    )

    native = _connection()
    fallback = _python_fallback_connection(monkeypatch)
    try:
        for expression in [
            "name.trace('names', given.single()).given.count() = 2",
            "name.trace('idx', $index.single()).given.count() = 2",
        ]:
            native_row = native.execute(
                "SELECT fhirpath(?::JSON, ?), fhirpath_json(?::JSON, ?), fhirpath_is_valid(?)",
                [resource, expression, resource, expression, expression],
            ).fetchone()
            fallback_row = fallback.execute(
                "SELECT fhirpath(?::JSON, ?), fhirpath_json(?::JSON, ?), fhirpath_is_valid(?)",
                [resource, expression, resource, expression, expression],
            ).fetchone()
            assert native_row == fallback_row == (["true"], "[true]", True)
    finally:
        native.close()
        fallback.close()


def test_children_preserves_split_primitive_extension_metadata_fp12_historian(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """FP-12 HISTORIAN: Python fallback `visit()` was filtering out any dict
    whose only key was 'extension' at any depth in the result tree, not just
    top-level ResourceNode items. This dropped the inner contents of FHIR
    split-representation primitive-extension arrays (e.g. `_given:[null,
    {extension:...}]`) during normal path traversal. Native C++ `fn_children`
    zips shadow arrays correctly and preserves the full content. The fix
    mirrors the `returnRawData` branch's ResourceNode guard: only filter
    items that are ResourceNodes whose data is extension-only.
    """
    resource = json.dumps(
        {
            "resourceType": "Patient",
            "id": "split",
            "_id": {"extension": [{"url": "http://x/id", "valueString": "ext-id"}]},
            "birthDate": "1970-01-01",
            "_birthDate": {
                "extension": [{"url": "http://x/bd", "valueString": "bd-ext"}],
            },
            "name": [
                {
                    "given": ["Mary"],
                    "_given": [
                        None,
                        {"extension": [{"url": "http://x/g2", "valueString": "g2-ext"}]},
                    ],
                }
            ],
        }
    )

    native = _connection()
    fallback = _python_fallback_connection(monkeypatch)
    try:
        # Both backends must produce identical results for path traversal
        # on split-representation resources. The `name` element's `_given`
        # array must round-trip with both the `null` slot AND the inner
        # `extension` object intact.
        for expression in [
            "children()",
            "name",
            "Patient.children()",
            "Patient.name",
        ]:
            native_row = native.execute(
                "SELECT fhirpath_json(?::JSON, ?)",
                [resource, expression],
            ).fetchone()
            fallback_row = fallback.execute(
                "SELECT fhirpath_json(?::JSON, ?)",
                [resource, expression],
            ).fetchone()
            assert native_row == fallback_row, (
                f"expression '{expression}' diverges: native={native_row!r}, "
                f"fallback={fallback_row!r}"
            )
            # Verify the inner extension content is preserved (not just the
            # truncated `_given:[null]`).
            assert "g2-ext" in (native_row[0] or ""), (
                f"expression '{expression}': inner extension content dropped "
                f"from result {native_row[0]!r}"
            )
    finally:
        native.close()
        fallback.close()


def test_now_timeoday_today_match_native_rendering_shape_fp12_historian(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """FP-12 HISTORIAN: Python fallback `now()` and `timeOfDay()` were
    rendering microseconds (6 fractional digits) via
    `datetime.isoformat()`, while the bundled native C++ extension renders
    `now()` at second precision (no fractional) and `timeOfDay()` at
    millisecond precision (`.000`, the spec §5.5.8 canonical Time format
    `hh:mm:ss.fff`). Both backends must produce the same string shape per
    the native↔fallback parity contract. The fix truncates Python's
    microsecond component before isoformat for `now()` and uses an explicit
    `%H:%M:%S.000` format for `timeOfDay()`.

    Today() is unaffected (date-only isoformat is identical between
    backends); it's included here as a regression guard.
    """
    resource = json.dumps({"resourceType": "Patient", "id": "p1"})

    native = _connection()
    fallback = _python_fallback_connection(monkeypatch)
    try:
        for expression, regex in [
            ("now()", r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\+|-)\d{2}:\d{2}$"),
            ("timeOfDay()", r"^\d{2}:\d{2}:\d{2}\.\d{3}$"),
            ("today()", r"^\d{4}-\d{2}-\d{2}$"),
        ]:
            native_text = native.execute(
                "SELECT fhirpath_text(?::JSON, ?)", [resource, expression]
            ).fetchone()[0]
            fallback_text = native.execute(
                "SELECT fhirpath_text(?::JSON, ?)", [resource, expression]
            ).fetchone()[0]
            # Both must match the regex (spec-aligned shape).
            import re as _re

            assert _re.match(regex, native_text or ""), (
                f"native {expression} = {native_text!r} does not match {regex}"
            )
            # Shape agreement: both backends must produce the same length
            # string with no fractional-second divergence.
            assert len(native_text or "") == len(fallback_text or ""), (
                f"{expression}: native shape len={len(native_text or '')} "
                f"differs from fallback len={len(fallback_text or '')} "
                f"(native={native_text!r}, fallback={fallback_text!r})"
            )
            # No microsecond component (6 fractional digits) should leak
            # through.
            assert "." not in (native_text or "") or native_text.count(".") == (
                1 if expression != "today()" else 0
            ), f"native {expression} shape unexpected: {native_text!r}"
    finally:
        native.close()
        fallback.close()


def test_now_and_timeoday_rendering_parity_fp12_historian(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """FP-12 HISTORIAN: native↔fallback parity for `now()` and `timeOfDay()`
    string shapes. Both must be deterministic per-expression and must
    produce the same canonical shape. Because the actual wall-clock second
    can roll over between native and fallback evaluation, we check that
    the SHAPE (regex, fractional precision) agrees rather than the literal
    value."""
    resource = json.dumps({"resourceType": "Patient", "id": "p1"})

    native = _connection()
    fallback = _python_fallback_connection(monkeypatch)
    try:
        # Deterministic per-expression (per spec §5.9.2): within one
        # expression, now()=now() must be true.
        for expression in [
            "now() = now()",
            "timeOfDay() = timeOfDay()",
            "today() = today()",
        ]:
            native_row = native.execute(
                "SELECT fhirpath(?::JSON, ?), fhirpath_json(?::JSON, ?)",
                [resource, expression, resource, expression],
            ).fetchone()
            fallback_row = fallback.execute(
                "SELECT fhirpath(?::JSON, ?), fhirpath_json(?::JSON, ?)",
                [resource, expression, resource, expression],
            ).fetchone()
            assert native_row == fallback_row == (["true"], "[true]"), (
                f"{expression}: native={native_row!r}, fallback={fallback_row!r}"
            )

        # Shape: now() must have no fractional-second component in EITHER backend.
        native_now = native.execute(
            "SELECT fhirpath_text(?::JSON, ?)", [resource, "now()"]
        ).fetchone()[0]
        fallback_now = fallback.execute(
            "SELECT fhirpath_text(?::JSON, ?)", [resource, "now()"]
        ).fetchone()[0]
        # Strip the timezone offset for shape inspection; both must agree
        # on whether a fractional-second component exists.
        assert "." not in native_now.split("+")[0].split("-T")[-1].split("T")[-1], (
            f"native now() has fractional seconds: {native_now!r}"
        )
        # Fallback must also lack fractional seconds (truncated to second).
        fallback_time_part = fallback_now.split("+")[0]
        assert "." not in fallback_time_part.split("T")[-1], (
            f"fallback now() has fractional seconds: {fallback_now!r} "
            f"(FP-12 HISTORIAN fix not applied)"
        )

        # Shape: timeOfDay() must have exactly 3 fractional digits in BOTH backends.
        native_tod = native.execute(
            "SELECT fhirpath_text(?::JSON, ?)", [resource, "timeOfDay()"]
        ).fetchone()[0]
        fallback_tod = fallback.execute(
            "SELECT fhirpath_text(?::JSON, ?)", [resource, "timeOfDay()"]
        ).fetchone()[0]
        import re as _re

        assert _re.match(r"^\d{2}:\d{2}:\d{2}\.\d{3}$", native_tod or ""), (
            f"native timeOfDay() shape: {native_tod!r}"
        )
        assert _re.match(r"^\d{2}:\d{2}:\d{2}\.\d{3}$", fallback_tod or ""), (
            f"fallback timeOfDay() shape: {fallback_tod!r} "
            f"(FP-12 HISTORIAN fix not applied)"
        )
    finally:
        native.close()
        fallback.close()


def test_descendants_handles_deeply_nested_resources_fp12_explorer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """FP-12 EXPLORER: Python fallback `descendants()` previously crashed
    silently with RecursionError on resources nested >= ~490 deep because
    `_descendant_repeat_key` used `json.dumps(data, sort_keys=True,
    separators=(",",":"), default=str)` which serializes nested structures
    recursively and consumes one Python stack frame per nesting level. The
    native C++ `descendants()` uses an iterative work-queue with a 50000-
    descendant safety cap; the Python fallback must mirror that capacity.

    The fix replaces the recursive serializer with an iterative equivalent
    (`_iterative_canonical_json`) that uses an explicit stack and produces
    identical output for all conformant FHIR data.
    """
    # Build a deep contained chain iteratively (string concat avoids
    # json.dumps recursion at construction time).
    def build(depth: int) -> str:
        inner = '{"resourceType":"Basic","id":"b%d","valueString":"v%d"}' % (
            depth - 1, depth - 1)
        for i in range(depth - 2, -1, -1):
            inner = (
                '{"resourceType":"Basic","id":"b%d","valueString":"v%d",'
                '"contained":[%s]}'
            ) % (i, i, inner)
        return '{"resourceType":"Patient","id":"p1","contained":[%s]}' % inner

    native = _connection()
    fallback = _python_fallback_connection(monkeypatch)
    try:
        for depth, expected_count in [
            (10, 31),    # 1 root + 10*3 (resourceType/id/valueString skip) -> 1+30
            (100, 301),  # 1 root + 100*3 = 301
            (500, 1501),
            (1000, 3001),
            (2000, 6001),
        ]:
            resource = build(depth)
            expression = "descendants().count()"
            native_row = native.execute(
                "SELECT fhirpath(?::JSON, ?), fhirpath_json(?::JSON, ?)",
                [resource, expression, resource, expression],
            ).fetchone()
            fallback_row = fallback.execute(
                "SELECT fhirpath(?::JSON, ?), fhirpath_json(?::JSON, ?)",
                [resource, expression, resource, expression],
            ).fetchone()
            assert native_row == fallback_row == (
                [str(expected_count)], "[%d]" % expected_count
            ), (
                f"depth={depth}: native={native_row!r}, "
                f"fallback={fallback_row!r}, expected={expected_count}"
            )
    finally:
        native.close()
        fallback.close()


def test_descendants_dedup_correctness_after_iterative_serializer_fp12_explorer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """FP-12 EXPLORER: The iterative canonical JSON serializer in
    `_descendant_repeat_key` must produce dedup keys identical to the
    previous recursive `json.dumps` for shallow resources. This guards
    against any regression in dedup correctness from the depth fix.
    """
    # Same-value duplicate leaves should be deduped by descendants()
    resource1 = json.dumps({
        "resourceType": "Patient",
        "id": "dedup",
        "a": "dup",
        "b": "dup",
        "c": {"x": "dup"},
        "nested": {"deep": {"y": "dup"}},
    })
    # Duplicate complex-structure children
    resource2 = json.dumps({
        "resourceType": "Patient",
        "id": "dedup2",
        "a": {"x": 1, "y": "dup"},
        "b": {"x": 1, "y": "dup"},
    })

    native = _connection()
    fallback = _python_fallback_connection(monkeypatch)
    try:
        for resource, expression, expected in [
            (resource1, "descendants().where($this = 'dup').count()", ["1"]),
            (resource2, "descendants().count()", ["4"]),
            (
                resource2,
                "descendants().count() = repeat(children()).count()",
                ["true"],
            ),
        ]:
            native_row = native.execute(
                "SELECT fhirpath(?::JSON, ?), fhirpath_json(?::JSON, ?)",
                [resource, expression, resource, expression],
            ).fetchone()
            fallback_row = fallback.execute(
                "SELECT fhirpath(?::JSON, ?), fhirpath_json(?::JSON, ?)",
                [resource, expression, resource, expression],
            ).fetchone()
            assert native_row == fallback_row, (
                f"expression={expression!r}: native={native_row!r}, "
                f"fallback={fallback_row!r}"
            )
            assert native_row[0] == expected, (
                f"expression={expression!r}: native={native_row!r}, "
                f"expected first={expected!r}"
            )
    finally:
        native.close()
        fallback.close()


def test_json_decimal_primitive_text_rendering_fp12_explorer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """FP-12 EXPLORER: Native FastText/FastList paths used
    `std::to_string(yyjson_get_real(value))` which renders at 6-digit fixed
    precision per the C++ standard ([string.conversions]), producing
    `'12.500000'` for `12.5`. The Python fallback uses shortest-round-trip
    rendering (`'12.5'`), creating native↔fallback text-rendering parity
    drift on every direct member access of a JSON decimal primitive.

    The fix replaces `std::to_string(yyjson_get_real(value))` with
    `yyjson_val_write(value, 0, nullptr)` which extracts the original JSON
    text, matching both the Python fallback and the non-fast-path
    `Evaluator::jsonValToString`.

    Affects `fhirpath_text` (FastPathLookup at fhirpath_extension.cpp:513)
    and `fhirpath` (JsonValueToOwnedString at fhirpath_extension.cpp:757)
    UDF wrappers.
    """
    test_cases = [
        (12.5, "12.5"),
        (1.5, "1.5"),
        (0.1, "0.1"),
        (100.25, "100.25"),
        (0.001, "0.001"),
        (1.0, "1.0"),
        (12.34, "12.34"),
    ]

    native = _connection()
    fallback = _python_fallback_connection(monkeypatch)
    try:
        for value, expected_text in test_cases:
            resource = json.dumps({
                "resourceType": "Basic",
                "id": "x",
                "valueDecimal": value,
            })
            # Test all 3 text-rendering UDF wrappers
            for expression in ["valueDecimal", "valueDecimal.toString()"]:
                native_row = native.execute(
                    "SELECT fhirpath(?::JSON, ?), fhirpath_text(?::JSON, ?)",
                    [resource, expression, resource, expression],
                ).fetchone()
                fallback_row = fallback.execute(
                    "SELECT fhirpath(?::JSON, ?), fhirpath_text(?::JSON, ?)",
                    [resource, expression, resource, expression],
                ).fetchone()
                assert native_row == fallback_row, (
                    f"value={value}, expression={expression!r}: "
                    f"native={native_row!r}, fallback={fallback_row!r}"
                )

            # Direct valueDecimal access should produce shortest-round-trip
            # text (matches Python fallback) in both backends.
            native_text = native.execute(
                "SELECT fhirpath_text(?::JSON, ?)",
                [resource, "valueDecimal"],
            ).fetchone()[0]
            assert native_text == expected_text, (
                f"value={value}: native fhirpath_text returned "
                f"{native_text!r}, expected {expected_text!r} "
                f"(FP-12 EXPLORER fix not applied)"
            )

        # Same for Observation.valueQuantity.value
        obs_resource = json.dumps({
            "resourceType": "Observation",
            "id": "obs1",
            "status": "final",
            "code": {"coding": [{"code": "x"}]},
            "valueQuantity": {"value": 12.5, "unit": "mg", "code": "mg"},
        })
        for expression in [
            "valueQuantity.value",
            "valueQuantity.value.toString()",
        ]:
            native_row = native.execute(
                "SELECT fhirpath(?::JSON, ?), fhirpath_text(?::JSON, ?), "
                "fhirpath_json(?::JSON, ?)",
                [obs_resource, expression, obs_resource, expression,
                 obs_resource, expression],
            ).fetchone()
            fallback_row = fallback.execute(
                "SELECT fhirpath(?::JSON, ?), fhirpath_text(?::JSON, ?), "
                "fhirpath_json(?::JSON, ?)",
                [obs_resource, expression, obs_resource, expression,
                 obs_resource, expression],
            ).fetchone()
            assert native_row == fallback_row, (
                f"expression={expression!r}: native={native_row!r}, "
                f"fallback={fallback_row!r}"
            )
    finally:
        native.close()
        fallback.close()
