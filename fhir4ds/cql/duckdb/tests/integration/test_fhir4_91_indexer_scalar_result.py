"""FHIR4-91 — an indexer over a list-valued source is a SCALAR, not a one-element list.

CQL 1.5 §17.6 ``Indexer(source List<T>, index Integer) T`` returns ONE element, so a
navigation over an indexed source is a scalar navigation:

    "Rows"[1].id      -- the id of the SECOND resource, a String
    [Condition][1].id -- the same, over an inline retrieve

Both spellings answered a ONE-ELEMENT LIST (``['c2']``) instead of ``'c2'``.  The indexer is
not the wrap site: ``X[i]`` lowers to ``LIST_EXTRACT(<per-patient list>, i+1)``, a single
value.  The wrap is introduced on the WAY OUT, at define materialisation and at two list
promotions that key on the node NAME alone:

* the navigation ``.id`` lowers to the scalar accessor ``fhirpath_text(<element>, 'id')``;
* ``translator.py`` treats ANY define whose body is a bare 2-arg ``fhirpath_text`` as a
  multi-valued FHIR property (the CQL-18 HISTORIAN heuristic) and rewrites it to the list
  projection ``from_json(fhirpath(...), '["VARCHAR"]')``, filing the define ``List<Any>``
  with ``DefinitionMeta.stores_list_value``;
* ``_promote_fhirpath_text_list`` (CQL-18/19) did the same for list-operator operands, so
  ``Length("Rows"[1].id)`` was the LIST length (1) instead of the String length (2);
* the FHIR4-72 hoist additionally moved the operand into a value CTE typed ``List<Any>``,
  and ``_is_list_typed_ast`` claimed the navigation as a list OPERAND, so
  ``"Rows"[1].id = 'c2'`` became a LIST comparison over a VARCHAR
  (``BinderException: array_length(VARCHAR)``).

Why it matters beyond cosmetics: a one-element list where CQL says a scalar silently changes
what a downstream comparison does.

The referees that must hold at the same time — and did not before the fix:

* ``"Rows"[1].id = <that id>`` is TRUE as a SCALAR comparison (it was a BinderException);
* ``Count({ "Rows"[1].id })`` = 1;
* the projected column has the SHAPE of a scalar (DuckDB type ``VARCHAR``, not
  ``VARCHAR[]``) — a value-only assertion passes on the wrapped form, which is how this hid.

The CONSUMER half of the card (added after the first, PARTIAL fix): the projected value was
scalar but the define's META was not — ``DefinitionMeta.cql_type`` stayed ``Any`` with
``has_resource`` True (and, before that, ``List<Any>`` with ``stores_list_value``), so every
consumer that consults the META still measured a list:

    Length(<alias of X[0]>)   = 1        -- the list length, not the String length
    Length([Condition][0].id) = 2        -- the inline spelling was already right

``_list_operator_source_is_retrieve_shaped`` treats a ``has_resource`` define as a rows source
and ``_list_operator_full_list_source`` then materializes its value column as a per-patient
list, so the alias answered a one-element list even though its column held one String. The
define therefore has to be typed as its ELEMENT (``String`` here) — that is the layer that
decides, and these tests assert the consumer side, not just the projection.

A genuine list source must keep yielding lists: ``"Rows"`` itself, ``First("Rows")`` (one
resource), ``Nums`` stored lists, ``Flatten``.
"""

from __future__ import annotations

import json
import re

import duckdb

from fhir4ds.cql import translate_cql
from fhir4ds.cql.parser import parse_cql
from fhir4ds.cql.translator.translator import CQLToSQLTranslator

from .wasm_runtime_helpers import no_python_connection

_PREAMBLE = """library F91 version '1.0.0'
using FHIR version '4.0.1'
context Patient

define "Rows": [Condition]
define "Single": [Condition] C where C.id = 'c2'
define "Lit": ({'c2'}) X
define "Given": { 'Joel', 'Ann' }
define "Nums": {10, 20, 30}
"""

_EPILOGUE = """
define "Initial Population": exists (Patient)
define "Denominator": "Initial Population"
define "Numerator": true
"""

#: consumer name -> CQL expression.  Indexed navigations are the card; the rest are the
#: "a genuine list stays a list" guards that the fix must not flatten.
#
#: ROW ORDER IS NOT A CQL GUARANTEE (FHIR4-70/81 doctrine): `"Rows"[1]` picks "the second row"
#: of whatever order the engine produced, and the `"Rows"` CTE and the inline `[Condition]`
#: retrieve materialize DIFFERENT subqueries, so the two spellings legitimately disagree on
#: WHICH element index 1 is.  Anything needing a fixed expected value therefore indexes
#: `"Single"`, a one-element source, where index 0 is the only element.
_CONSUMERS = {
    # the two spellings of the card — asserted order-independently (membership + shape)
    "RowsIdx": '"Rows"[1].id',
    "RetrieveIdx": '[Condition][1].id',
    # the same class, other single-element selectors (FHIR4-70 recorded First/Last too)
    "FirstRows": 'First("Rows").id',
    "LastRows": 'Last("Rows").id',
    # single-element source: index 0 is the only element, so the expected value is fixed
    "SingleIdx": '"Single"[0].id',
    "SingleEq": '"Single"[0].id = \'c2\'',
    "SingleEqWrong": '"Single"[0].id = \'zzz\'',
    "CountOfSingleIdx": 'Count({ "Single"[0].id })',
    "SingleIdxLength": 'Length("Single"[0].id)',
    # the same scalar consumers over the ORDER-DEPENDENT list, asserted only for cardinality
    "CountOfRowsIdx": 'Count({ "Rows"[1].id })',
    # CONSUMER SIDE (partial-fix gap): the alias of a single-element navigation must measure
    # like the value it holds, not like a one-element list.
    "LitIdx": '"Lit"[0]',
    "G0": '"Given"[0]',
    "LitAliasLength": 'Length("LitIdx")',
    "GivenAliasLength": 'Length("G0")',
    "LitInlineLength": 'Length("Lit"[0])',
    "GivenInlineLength": 'Length("Given"[0])',
    "LitAliasFirst": 'First({ "LitIdx" })',
    "LitAliasLast": 'Last({ "LitIdx" })',
    "LitAliasSingleton": 'singleton from { "LitIdx" }',
    "LitAliasDistinctCount": 'Count(Distinct({ "LitIdx" }))',
    "LitAliasIndexOf": 'IndexOf({ "LitIdx" }, \'c2\')',
    "LitAliasCount": 'Count({ "LitIdx" })',
    "LitAliasEq": '"LitIdx" = \'c2\'',
    "GivenAliasEq": '"G0" = \'Joel\'',
    "LitAliasToUpper": 'Upper("LitIdx")',
    # genuine list sources
    "RowsItself": '"Rows"',
    "NumsItself": 'Nums',
    "NumsIdx": 'Nums[1]',
    "NumsFlatten": 'Flatten({ Nums })',
    "FirstRowsWhole": 'First("Rows")',
    "RowsCount": 'Count("Rows")',
}

_RESOURCES = [
    {"resourceType": "Patient", "id": "p1", "gender": "female"},
    {"resourceType": "Patient", "id": "p2", "gender": "male"},
    {"resourceType": "Condition", "id": "c2", "subject": {"reference": "Patient/p1"}},
    {"resourceType": "Condition", "id": "c1", "subject": {"reference": "Patient/p1"}},
    {"resourceType": "Condition", "id": "c3", "subject": {"reference": "Patient/p1"}},
]

_IDS = {"c1", "c2", "c3"}

#: The defect's signature in the emitted SQL: a list construction around the navigation.
_LIST_CONSTRUCTION = re.compile(r"from_json\(\s*fhirpath\(", re.IGNORECASE)


def _library_text() -> str:
    return (
        _PREAMBLE
        + "".join(f'define "{name}": {expr}\n' for name, expr in _CONSUMERS.items())
        + _EPILOGUE
    )


def _load(con) -> None:
    con.execute(
        "CREATE OR REPLACE TABLE resources (id VARCHAR, resourceType VARCHAR, "
        "resource JSON, patient_ref VARCHAR)"
    )
    for resource in _RESOURCES:
        patient_ref = (resource.get("subject") or {}).get("reference", "").split("/")[-1] or None
        con.execute(
            "INSERT INTO resources VALUES (?,?,?::JSON,?)",
            [resource["id"], resource["resourceType"], json.dumps(resource), patient_ref],
        )


def _run_both_engines():
    """Yield ``(label, by_patient, column_types, translator)`` for the whole library."""
    from contextlib import contextmanager

    from fhir4ds.cql.duckdb.extension import _register_python_supplements

    @contextmanager
    def _py():
        con = duckdb.connect()
        _register_python_supplements(con, cpp_loaded=False, include_fhirpath=True)
        try:
            yield con
        finally:
            con.close()

    cql_text = _library_text()
    for ctx, label in ((_py(), "python"), (no_python_connection(), "no_python")):
        with ctx as con:
            library = parse_cql(cql_text)
            translator = CQLToSQLTranslator(connection=con)
            translator.translate_library(library)
            sql = translator.translate_library_to_population_sql(
                library=library,
                output_columns={name: name for name in _CONSUMERS},
            )
            # Keep DuckDB's default strictness: a shape defect must not be masked by a
            # harness flag (FHIR4-48/53 doctrine).
            con.execute("SET scalar_subquery_error_on_multiple_rows=true")
            _load(con)
            cursor = con.execute(sql)
            names = [d[0] for d in cursor.description]
            types = {d[0]: str(d[1]) for d in cursor.description}
            by_patient = {
                row[0]: dict(zip(names[1:], row[1:], strict=True))
                for row in cursor.fetchall()
            }
            yield label, by_patient, types, translator


def test_an_indexed_navigation_is_a_scalar_value():
    """``"Rows"[1].id`` and ``[Condition][1].id`` answer an id, not a one-element list.

    Which ELEMENT index 1 is depends on row order (not a CQL guarantee, and the two spellings
    materialize different subqueries), so the two are asserted for SHAPE and MEMBERSHIP; the
    fixed-value assertions below index the one-element ``"Single"`` source instead.
    """
    for label, by_patient, _types, _translator in _run_both_engines():
        p1 = by_patient["p1"]
        for column in ("RowsIdx", "RetrieveIdx"):
            value = p1[column]
            assert isinstance(value, str), (
                f"{label}: {column} = {value!r}; CQL Indexer returns one element, "
                f"so the navigation over it is a String, not a list"
            )
            assert value in _IDS, f"{label}: {column} = {value!r}, expected a Condition id"
            assert len(value) == 2, (
                f"{label}: {column} = {value!r} looks like a character slice of one element"
            )
        # The one-element source: index 0 is deterministic, so the value is exact.
        assert p1["SingleIdx"] == "c2", f"{label}: \"Single\"[0].id = {p1['SingleIdx']!r}"
        # No Conditions: the indexed navigation is null (not an empty list).
        assert by_patient["p2"]["RowsIdx"] is None, label
        assert by_patient["p2"]["SingleIdx"] is None, label


def test_the_indexer_projection_has_the_shape_of_a_scalar():
    """REFEREE (shape): the projected column is ``VARCHAR``, not a list type.

    A value-only assertion passes on the wrapped form (``['c2']`` unwrapped by a helper is
    the same character data) — the shape is what hid the defect, so assert the SQL shape and
    the resulting DuckDB column type.
    """
    defs = translate_cql(_library_text())
    for name in ("RowsIdx", "RetrieveIdx", "FirstRows", "LastRows"):
        sql = defs[name].to_sql()
        assert not _LIST_CONSTRUCTION.search(sql), (
            f"{name}: define materialisation rewrapped a scalar navigation as a list "
            f"projection: {sql}"
        )
        assert "fhirpath_text(" in sql, f"{name}: expected the scalar accessor, got {sql}"

    for label, _by_patient, types, translator in _run_both_engines():
        for column in ("RowsIdx", "RetrieveIdx", "FirstRows", "LastRows"):
            assert types[column].upper().startswith("VARCHAR"), (
                f"{label}: projected type of {column} is {types[column]}; a scalar "
                f"navigation must project one VARCHAR, not a list"
            )
            meta = translator.context.definition_meta[column]
            assert meta.stores_list_value is False, (
                f"{label}: {column} is marked stores_list_value — the scalar navigation was "
                f"rewrapped as a whole element list"
            )
            assert not str(meta.cql_type).startswith("List<"), (
                f"{label}: {column} is typed {meta.cql_type}"
            )


def test_a_scalar_comparison_over_an_indexed_navigation_is_true():
    """REFEREE: ``<indexed navigation> = <that id>`` is TRUE — a String comparison.

    A one-element list compared to a String is either a LIST comparison (BinderException over
    a VARCHAR) or false, never TRUE.
    """
    for label, by_patient, _types, _translator in _run_both_engines():
        p1 = by_patient["p1"]
        assert p1["SingleEq"] is True, (
            f"{label}: \"Single\"[0].id = 'c2' = {p1['SingleEq']!r}; the indexed "
            f"navigation is a SCALAR String, so this is a String comparison that is TRUE"
        )
        # A wrong id is FALSE, not null: the comparison really ran.
        assert p1["SingleEqWrong"] is False, (
            f"{label}: \"Single\"[0].id = 'zzz' = {p1['SingleEqWrong']!r}"
        )
        # The order-dependent spelling still compares as a scalar, whatever element it picked.
        assert p1["RowsIdx"] in _IDS, label


def test_a_singleton_wrapper_of_an_indexed_navigation_is_one_element():
    """REFEREE: ``Count({ <indexed navigation> })`` = 1 — a scalar wrapped once."""
    for label, by_patient, _types, _translator in _run_both_engines():
        for column, expr in (
            ("CountOfSingleIdx", 'Count({ "Single"[0].id })'),
            ("CountOfRowsIdx", 'Count({ "Rows"[1].id })'),
        ):
            assert by_patient["p1"][column] == 1, (
                f"{label}: {expr} = {by_patient['p1'][column]!r}"
            )


def test_the_indexed_navigation_is_a_string_not_a_list_of_characters():
    """``Length(<indexed navigation>)`` is the length of the TWO-character id."""
    for label, by_patient, _types, _translator in _run_both_engines():
        assert by_patient["p1"]["SingleIdxLength"] == 2, (
            f"{label}: Length(\"Single\"[0].id) = {by_patient['p1']['SingleIdxLength']!r}; "
            f"an id is 2 characters, so this is a String length (2), not a list length (1)"
        )


def test_the_single_element_selectors_share_the_scalar_shape():
    """``First``/``Last`` are the same class of single-element source (FHIR4-70 recorded)."""
    for label, by_patient, types, _translator in _run_both_engines():
        p1 = by_patient["p1"]
        for column in ("FirstRows", "LastRows"):
            value = p1[column]
            assert isinstance(value, str) and value in _IDS, (
                f"{label}: {column} = {value!r}; a resource selected by First/Last then "
                f"navigated with .id is a String"
            )
            assert types[column].upper().startswith("VARCHAR"), label


def test_a_single_element_navigation_define_is_typed_as_its_element():
    """CONSUMER SIDE: the define's META is the element type, not a list and not a resource.

    The first (partial) fix made the projected VALUE scalar while
    ``DefinitionMeta.cql_type`` stayed ``Any`` — and ``Any`` is treated as a resource type
    (``has_resource=True``), which is enough for ``_list_operator_full_list_source`` to
    materialize the define's value column as a per-patient LIST. Hence
    ``Length(<alias>)`` answered 1 while ``Length(<inline>)`` answered 2.
    """
    expected = {"LitIdx": "String", "G0": "String", "RowsIdx": "Any"}
    for label, _by_patient, _types, translator in _run_both_engines():
        for name, want in expected.items():
            meta = translator.context.definition_meta[name]
            assert meta.stores_list_value is False, label
            assert not str(meta.cql_type).startswith("List<"), (
                f"{label}: {name} is typed {meta.cql_type}; a single-element navigation holds "
                f"ONE value"
            )
            if want != "Any":
                assert str(meta.cql_type) == want, (
                    f"{label}: {name} cql_type = {meta.cql_type!r}, expected {want!r} "
                    f"(the element's CQL type)"
                )
            assert meta.has_resource is False, (
                f"{label}: {name} claims has_resource=True, so list consumers treat it as a "
                f"rows source"
            )
            assert meta.value_column == "value", f"{label}: {name} value column {meta.value_column}"


def test_a_define_alias_of_a_single_element_navigation_measures_like_its_value():
    """REFEREE (consumer): ``Length(<alias>)`` = ``Length(<inline>)`` = the String length."""
    for label, by_patient, _types, _translator in _run_both_engines():
        p1 = by_patient["p1"]
        assert p1["LitIdx"] == "c2" and p1["G0"] == "Joel", (
            f"{label}: LitIdx = {p1['LitIdx']!r}, G0 = {p1['G0']!r}"
        )
        assert p1["LitInlineLength"] == 2, f"{label}: Length(\"Lit\"[0]) = {p1['LitInlineLength']!r}"
        assert p1["LitAliasLength"] == 2, (
            f"{label}: Length(\"LitIdx\") = {p1['LitAliasLength']!r}; it must equal the "
            f"inline spelling ({p1['LitInlineLength']!r}), not the one-element list length"
        )
        assert p1["GivenInlineLength"] == 4, label
        assert p1["GivenAliasLength"] == 4, (
            f"{label}: Length(\"G0\") = {p1['GivenAliasLength']!r} vs inline "
            f"{p1['GivenInlineLength']!r}"
        )


def test_the_other_list_consumers_of_the_alias_treat_it_as_one_value():
    """``First``/``Last``/``singleton from``/``Distinct``/``IndexOf``/``Count``/``=``/``Upper``.

    Each is the LIST form over a one-element list literal ``{ <alias> }``, so a scalar alias
    has to behave exactly like the same literal built from the inline navigation.
    """
    for label, by_patient, _types, _translator in _run_both_engines():
        p1 = by_patient["p1"]
        assert p1["LitAliasFirst"] == "c2", f"{label}: First = {p1['LitAliasFirst']!r}"
        assert p1["LitAliasLast"] == "c2", f"{label}: Last = {p1['LitAliasLast']!r}"
        assert p1["LitAliasSingleton"] == "c2", (
            f"{label}: singleton from = {p1['LitAliasSingleton']!r}"
        )
        assert p1["LitAliasDistinctCount"] == 1, (
            f"{label}: Count(Distinct({{alias}})) = {p1['LitAliasDistinctCount']!r}"
        )
        assert p1["LitAliasIndexOf"] == 0, (
            f"{label}: IndexOf = {p1['LitAliasIndexOf']!r}; the list is ['c2'] so 'c2' is at 0"
        )
        assert p1["LitAliasCount"] == 1, f"{label}: Count = {p1['LitAliasCount']!r}"
        assert p1["LitAliasEq"] is True, (
            f"{label}: \"LitIdx\" = 'c2' = {p1['LitAliasEq']!r}; a String comparison"
        )
        assert p1["GivenAliasEq"] is True, label
        assert p1["LitAliasToUpper"] == "C2", (
            f"{label}: Upper(\"LitIdx\") = {p1['LitAliasToUpper']!r}; a String operator"
        )


def test_a_genuine_list_source_keeps_its_list():
    """REFEREE: the fix must not flatten a real list."""
    defs = translate_cql(_library_text())
    # The resource define is still a row CTE relation (list of resources per patient).
    assert defs["Rows"].to_sql().strip() == '"Condition"', defs["Rows"].to_sql()

    for label, by_patient, types, translator in _run_both_engines():
        p1 = by_patient["p1"]
        # A resource-row list keeps one entry per resource (the getResourceKey form).
        assert {entry.split("/")[-1] for entry in p1["RowsItself"]} == _IDS, (
            f"{label}: Rows itself: {p1['RowsItself']!r}"
        )
        assert p1["NumsItself"] == [10, 20, 30], (
            f"{label}: Nums itself = {p1['NumsItself']!r}"
        )
        assert p1["NumsIdx"] == 20, f"{label}: Nums[1] = {p1['NumsIdx']!r}"
        assert p1["NumsFlatten"] == [10, 20, 30], f"{label}: Flatten = {p1['NumsFlatten']!r}"
        assert p1["RowsCount"] == 3, f"{label}: Count(Rows) = {p1['RowsCount']!r}"
        assert "[]" in types["RowsItself"] or "LIST" in types["RowsItself"].upper(), (
            f"{label}: Rows itself projected as {types['RowsItself']}"
        )
        # First("Rows") is ONE RESOURCE: its projection keeps the whole Condition.
        whole = p1["FirstRowsWhole"]
        assert isinstance(whole, str) and '"resourceType": "Condition"' in whole, (
            f"{label}: First(Rows) = {p1['FirstRowsWhole']!r}"
        )
        # A real list define keeps its stored-list metadata.
        meta = translator.context.definition_meta["Nums"]
        assert meta.stores_list_value is True and str(meta.cql_type).startswith("List<"), (
            f"{label}: Nums metadata = {meta.cql_type}/{meta.stores_list_value}"
        )
