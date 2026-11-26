"""Unit tests for the reference-bundle generator (WP-1): classification and rendering.

No engine and no node are needed here; the desktop and browser inputs are faked.
The end-to-end rules (reference file == generator output, real-browser catalog
freshness) live in ``test_wasm_parity_step0.py`` (T8) and ``test_wasm_parity_tier_b.py`` (B7).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from fhir4ds.operations.tests.wasm_parity import macro_bundle as mb

BROWSER = frozenset({"abs", "list_filter", "list_bool_and", "json_extract_string", "cqldatetimeequal"})


def macro(name: str, body: str, *params: str) -> mb.Macro:
    return mb.Macro(name, params or ("x",), body)


def test_emitted_macros_follow_dependency_order():
    macros = {
        "top": macro("Top", "bottom(x) + 1"),
        "bottom": macro("Bottom", "abs(x)"),
        "alone": macro("Alone", "list_filter(x, lambda v: abs(v))"),
    }
    cls = mb.classify(macros, BROWSER)
    assert cls.emitted == ("alone", "bottom", "top")  # alphabetical among the ready ones
    assert cls.blocked == {} and cls.native == () and cls.helpers == ()


def test_helper_backed_macro_the_browser_answers_natively_is_not_emitted():
    macros = {
        "highboundary": macro("HighBoundary", "__fhir4ds_py_highboundary(x, 2)"),
        "__cql_to_date": macro("__cql_to_date", "__fhir4ds_py_todate(x)"),
        "todate": macro("ToDate", "__cql_to_date(x)"),
    }
    cls = mb.classify(macros, BROWSER | {"highboundary", "todate"})
    assert cls.emitted == ()
    assert cls.native == ("highboundary", "todate")
    # ``__cql_to_date`` is blocked, but it is a helper: no emitted macro needs it.
    assert cls.helpers == ("__cql_to_date",) and cls.blocked == {}


def test_helper_backed_macro_without_a_native_counterpart_is_blocked_and_names_the_helper():
    macros = {"setvariable": macro("SetVariable", "_setvariable_impl(name, value)", "name", "value")}
    cls = mb.classify(macros, BROWSER)
    assert cls.emitted == () and cls.native == ()
    assert cls.blocked == {"setvariable": frozenset({"_setvariable_impl"})}


def test_a_macro_that_calls_a_blocked_macro_is_blocked_by_it():
    macros = {
        "setvariable": macro("SetVariable", "_setvariable_impl(name, value)", "name", "value"),
        "caller": macro("Caller", "setvariable('a', 1)"),
    }
    cls = mb.classify(macros, BROWSER)
    assert set(cls.blocked) == {"setvariable", "caller"}
    assert cls.blocked["caller"] == frozenset({"setvariable"})


def test_calling_a_natively_answered_macro_does_not_block_the_caller():
    # ``ToDate`` is helper-backed but the browser answers it natively, so a macro that
    # calls it is still portable.
    macros = {
        "todate": macro("ToDate", "__fhir4ds_py_todate(x)"),
        "user": macro("User", "todate(x)"),
    }
    cls = mb.classify(macros, BROWSER | {"todate"})
    assert cls.emitted == ("user",) and cls.blocked == {}


def test_self_reference_is_not_a_dependency():
    cls = mb.classify({"abs": macro("Abs", "TRY(abs(x))")}, BROWSER)
    assert cls.emitted == ("abs",)


def test_an_unresolvable_name_blocks_the_macro():
    cls = mb.classify({"m": macro("M", "no_such_function(x)")}, BROWSER)
    assert cls.emitted == () and cls.blocked == {"m": frozenset({"no_such_function"})}


@pytest.mark.parametrize(
    ("body", "expected"),
    [
        (
            'CASE WHEN (x IS NULL) THEN NULL WHEN (y IN (1, 2)) THEN CAST(x AS DECIMAL(38, 8)) '
            "ELSE TRY_CAST(COALESCE(x, 0) AS INTEGER) END",
            frozenset(),
        ),
        ("CASE WHEN EXISTS (SELECT 1 FROM t WHERE a) THEN (SELECT (min(p)) FROM t) END", {"min"}),
        (
            "SELECT COALESCE(lst, main.list_value()) AS _cql_contains_l FROM t "
            "AS _cql_contains_t, unnest(x) AS _cql_contains_u(_cql_contains_item) WHERE b",
            {"list_value", "unnest"},
        ),
        ("list_filter(x, lambda _v: (_v IS NOT NULL))", {"list_filter"}),
    ],
)
def test_sql_syntax_and_alias_columns_are_not_calls(body: str, expected: frozenset[str]):
    assert mb.referenced_names(body) == frozenset(expected)


def test_calls_are_found_in_plain_and_quoted_form():
    body = 'CASE WHEN ("system".array_length(x) != list_count(x)) THEN CQLListElementEqual(a, b) END'
    assert mb.referenced_names(body) == frozenset({"array_length", "list_count", "cqllistelementequal"})


def test_keyword_names_are_quoted_and_builtin_names_replaced():
    plain = mb.Macro("Abs", ("x",), "TRY(abs(x))")
    keyword = mb.Macro("And", ("a", "b"), "a AND b", reserved=True)
    builtin = mb.Macro("Round", ("x",), "floor(x + 0.5)", builtin=True)
    assert mb._statement(plain) == "CREATE MACRO IF NOT EXISTS Abs(x) AS TRY(abs(x))"
    assert mb._statement(keyword) == 'CREATE MACRO IF NOT EXISTS "And"(a, b) AS a AND b'
    assert mb._statement(builtin) == "CREATE OR REPLACE MACRO Round(x) AS floor(x + 0.5)"


def test_declared_parameter_defaults_survive_generation():
    sliced = mb.Macro("Slice", ("lst", "start", "the_end"), "list_slice(lst, 1, 2)",
                      parameter_text="lst, start := 0, the_end := NULL")
    assert mb._statement(sliced) == (
        "CREATE MACRO IF NOT EXISTS Slice(lst, start := 0, the_end := NULL) AS list_slice(lst, 1, 2)"
    )


def _render(overlay=("CREATE MACRO IF NOT EXISTS \"Coalesce\"(a, b) AS COALESCE(a, b)",)) -> str:
    order = ("bottom", "top")
    macros = {
        "bottom": macro("Bottom", "abs(x)"),
        "top": macro("Top", 'bottom(x) + len(\'a"b\')'),
        "resolve": mb.Macro("resolve", ("ref",), "SELECT 1 AS r"),
    }
    return mb.render(order, macros, overlay, macros["resolve"])


def test_rendered_module_keeps_the_contract_exports_and_round_trips_strings():
    text = _render()
    assert "export const RESOLVE_MACRO_SQL" in text
    assert "export const REGISTERED_MACRO_NAMES: string[]" in text
    assert "export async function registerCQLMacros(conn: any): Promise<void>" in text
    assert "const CQL_MACRO_SQL = [" in text
    lines = [line for line in text.splitlines() if line.startswith('  "CREATE')]
    statements = [json.loads(line.rstrip(",")) for line in lines]
    assert statements == [
        "CREATE MACRO IF NOT EXISTS Bottom(x) AS abs(x)",
        'CREATE MACRO IF NOT EXISTS Top(x) AS bottom(x) + len(\'a"b\')',
        'CREATE MACRO IF NOT EXISTS "Coalesce"(a, b) AS COALESCE(a, b)',
    ]
    assert text.startswith("// GENERATED FILE")


def test_an_overlay_statement_cannot_duplicate_a_generated_macro():
    with pytest.raises(mb.BundleError, match="duplicates a generated macro"):
        _render(overlay=("CREATE MACRO IF NOT EXISTS Bottom(x) AS abs(x)",))


def test_boolean_constant_spellings_are_one_definition():
    assert mb.surfaces.normalize_definition("a IS NOT DISTINCT FROM CAST('t' AS BOOLEAN)") == (
        "a IS NOT DISTINCT FROM true"
    )
    assert mb.surfaces.normalize_definition("x THEN\n  CAST('f' AS BOOLEAN)") == "x THEN false"


class TestProblems:
    @pytest.fixture
    def generated(self) -> mb.Generated:
        return mb.Generated("the generated text", mb.Classification((), (), {}, ()), ())

    @pytest.fixture
    def reference(self, monkeypatch, tmp_path) -> Path:
        path = tmp_path / "cql-macros.ts"
        monkeypatch.setattr(mb, "REFERENCE_TS_MACRO_FILE", path)
        return path

    def test_a_hand_edit_of_the_reference_file_is_reported(self, generated, reference, monkeypatch):
        reference.write_text("the generated text with a hand edit")
        monkeypatch.setattr(mb, "load_overlay", lambda: ())
        assert mb.problems(generated) == [
            f"{reference} differs from the generator's output (hand edit, or a macro changed "
            "without regeneration); run `python -m "
            "fhir4ds.operations.tests.wasm_parity.macro_bundle --write`"
        ]

    def test_an_untouched_reference_file_has_no_problems(self, generated, reference, monkeypatch):
        reference.write_text("the generated text")
        monkeypatch.setattr(mb, "load_overlay", lambda: ())
        assert mb.problems(generated) == []

    def test_an_overlay_body_for_a_macro_the_generator_emits_is_reported(
        self, reference, monkeypatch
    ):
        generated = mb.Generated("t", mb.Classification(("abs",), (), {}, ()), ())
        reference.write_text("t")
        monkeypatch.setattr(mb, "load_overlay", lambda: ("CREATE MACRO IF NOT EXISTS Abs(x) AS 1",))
        (problem,) = mb.problems(generated)
        assert problem == (
            "overlay statement 'abs' is not a blocked or approved browser-only macro; "
            "delete it, the generator emits this macro"
        )

    def test_a_blocked_macro_and_the_approved_browser_only_macro_may_be_hand_written(
        self, reference, monkeypatch
    ):
        blocked = {"setvariable": frozenset({"_setvariable_impl"})}
        generated = mb.Generated("t", mb.Classification((), (), blocked, ()), ())
        reference.write_text("t")
        monkeypatch.setattr(
            mb,
            "load_overlay",
            lambda: (
                "CREATE MACRO IF NOT EXISTS SetVariable(name, value) AS NULL",
                'CREATE MACRO IF NOT EXISTS "Coalesce"(a, b) AS COALESCE(a, b)',
            ),
        )
        assert mb.problems(generated) == []


def test_parameter_list_parsing_keeps_defaults_and_nested_parentheses():
    statement = (
        'CREATE OR REPLACE MACRO Slice(lst, start := 0, the_end := NULL) AS '
        "CASE WHEN lst IS NULL THEN NULL ELSE list_slice(lst, least(start, 3), the_end) END"
    )
    assert mb.statement_name(statement) == "Slice"
    assert mb._parameter_text(statement) == "lst, start := 0, the_end := NULL"
    assert mb._split_params("a, b := coalesce(1, 2), c := 'x, y'") == [
        "a",
        "b := coalesce(1, 2)",
        "c := 'x, y'",
    ]


def test_statement_name_rejects_text_that_is_not_a_macro():
    with pytest.raises(mb.BundleError, match="not a macro statement"):
        mb.statement_name("SELECT 1")
