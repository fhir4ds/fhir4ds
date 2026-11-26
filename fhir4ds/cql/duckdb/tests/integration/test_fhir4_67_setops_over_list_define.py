"""FHIR4-67 — `intersect` / `except` over a value-projection query define.

A define whose body is a query with a ``return`` clause is a LIST: the CQL
Developer's Guide ("Queries") says *"If the query is plural, the result type is
a list whose element types are the type of the return expression."*  So

    define "Ids": ([Condition] C return C.id) X        // List<String>

and every set operation over it is the LIST overload from CQL 1.5 Appendix B
(§List Operators):

    intersect(left List<T>, right List<T>) List<T>
    except(left List<T>, right List<T>) List<T>
    union(left List<T>, right List<T>) List<T>

Such a define materializes as ``RowShape.PATIENT_MULTI_VALUE`` — ONE CTE row per
element.  ``union`` normalized its operands back to the full CTE scan, but
``intersect``/``except`` consumed each operand through the generic SCALAR
lookup:

    (SELECT sub.patient_id, sub.value FROM "Ids" AS sub
      WHERE sub.patient_id = sub.patient_id LIMIT 1)

so with Conditions c1/c2/c3 the operation saw ONE arbitrary element:

    "Ids" intersect "Other"      -> [] or ['c3']   (depends on row order!)
    "Ids" intersect { 'c2', 'zz' } -> BinderException:
                                      UNNEST() for correlated expressions is
                                      not supported yet
    { 'c2', 'zz' } intersect "Ids" -> BinderException: array_length(VARCHAR)

— a SILENT WRONG ANSWER for the define-vs-define shape (row order decided
whether the answer looked right) and a hard BinderException whenever a real list
met the scalar lookup.  Both engines answered identically wrong, so a parity
probe could not see it.

The fix materializes the whole per-patient element list for each operand — the
same gate the membership operators use (FHIR4-65 ``_multi_row_define_list`` /
CQL-19 ``_setop_operand_as_list``) — so the set operation is the LIST op, not a
correlated UNNEST of rows.  A ROW-shaped peer (a retrieve, a resource define)
keeps rows semantics, because the DQM resource-union guard depends on it.

The fixture is built so order luck cannot hide a bug: the expectations are
MULTI-element, one element is never the first/last row, one patient has no
Conditions at all, and one case must be empty even though both operands are
non-empty.
"""

from __future__ import annotations

import json
import re

import duckdb

from .wasm_runtime_helpers import no_python_connection

#: The defect's signature: a scalar consumption of the define's row CTE.
_LIMIT_ONE_CONSUMPTION = re.compile(
    r'FROM\s+"(?:Ids|NonC1)"\s+AS\s+sub\b[^)]*\bLIMIT\s+1\b', re.IGNORECASE
)

_LIBRARY = """library F67SetOps version '1.0.0'
using FHIR version '4.0.1'
include Common version '1.0.0' called Common
context Patient

// A value-projection query define: ONE CTE row per element.
define "Ids": ([Condition] C return C.id) X
// The same shape with its own WHERE — the card's reproducer.
define "NonC1": ([Condition] C where C.id != 'c1' return C.id) X
// A second element list that shares NO element with "Ids".
define "ObsIds": ([Observation] O return O.id) X

// ---- define vs define ---------------------------------------------------
define "BothIntersect": "Ids" intersect "NonC1"
define "BothExcept": "Ids" except "NonC1"
define "BothExceptRev": "NonC1" except "Ids"
define "DisjointIntersect": "Ids" intersect "ObsIds"
define "QualifiedIntersect": "Ids" intersect Common."SharedIds"
// union is the sibling operator: it already normalized its operands to the
// full CTE scan and must keep working (regression guard).
define "BothUnion": "Ids" union "NonC1"

// ---- define vs literal --------------------------------------------------
define "DefIntersectLit": "Ids" intersect { 'c2', 'zz' }
define "LitIntersectDef": { 'c2', 'zz', 'c9' } intersect "Ids"
define "DefExceptLit": "Ids" except { 'c2' }
define "LitExceptDef": { 'c2', 'zz' } except "Ids"
define "DefUnionLit": "Ids" union { 'zz' }

// ---- composition --------------------------------------------------------
define "Chained": ("Ids" intersect "NonC1") except { 'c2' }
define "InlineCount": Count("Ids" intersect "NonC1")
define "InlineHasC2": 'c2' in ("Ids" intersect "NonC1")
define "InlineHasC1": 'c1' in ("Ids" intersect "NonC1")
define "SetOpThenFirst": First("DefExceptLit")
define "SetOpThenLength": Length("BothIntersect")

// ---- null operands (CQL 1.5 App B: intersect null -> null, except null
//      -> the first list) --------------------------------------------------
define "IntersectNull": "Ids" intersect (null as List<String>)
define "ExceptNull": "Ids" except (null as List<String>)

define "Initial Population": exists (Patient)
define "Denominator": "Initial Population"
define "Numerator": "Initial Population"
"""

#: Included library declaring the same multi-row element define; the qualified
#: spelling is registered under its DOTTED name (`"Common.SharedIds"`).
_INCLUDED_LIBRARIES = {
    "Common": """library Common version '1.0.0'
using FHIR version '4.0.1'
context Patient

define "SharedIds": ([Condition] C return C.id) X
""",
}

_COLUMNS = {
    "Initial Population": "Initial Population",
    "BothIntersect": "BothIntersect",
    "BothExcept": "BothExcept",
    "BothExceptRev": "BothExceptRev",
    "DisjointIntersect": "DisjointIntersect",
    "QualifiedIntersect": "QualifiedIntersect",
    "BothUnion": "BothUnion",
    "DefIntersectLit": "DefIntersectLit",
    "LitIntersectDef": "LitIntersectDef",
    "DefExceptLit": "DefExceptLit",
    "LitExceptDef": "LitExceptDef",
    "DefUnionLit": "DefUnionLit",
    "Chained": "Chained",
    "InlineCount": "InlineCount",
    "InlineHasC2": "InlineHasC2",
    "InlineHasC1": "InlineHasC1",
    "SetOpThenFirst": "SetOpThenFirst",
    "SetOpThenLength": "SetOpThenLength",
    "IntersectNull": "IntersectNull",
    "ExceptNull": "ExceptNull",
}

#: p1 carries Conditions c1/c2/c3 plus one Observation; p2 carries NOTHING (the
#: empty-list projection); p3 carries a single Condition c9, so "shares no
#: element with Ids" is exercised on a patient whose list is non-empty.
_RESOURCES = [
    {"resourceType": "Patient", "id": "p1", "birthDate": "1980-01-01",
     "gender": "female"},
    {"resourceType": "Patient", "id": "p2", "birthDate": "1990-01-01",
     "gender": "male"},
    {"resourceType": "Patient", "id": "p3", "birthDate": "2000-01-01",
     "gender": "female"},
    {"resourceType": "Condition", "id": "c1", "subject": {"reference": "Patient/p1"}},
    {"resourceType": "Condition", "id": "c2", "subject": {"reference": "Patient/p1"}},
    {"resourceType": "Condition", "id": "c3", "subject": {"reference": "Patient/p1"}},
    {"resourceType": "Condition", "id": "c9", "subject": {"reference": "Patient/p3"}},
    {"resourceType": "Observation", "id": "o1", "status": "final",
     "subject": {"reference": "Patient/p1"},
     "code": {"coding": [{"system": "http://loinc.org", "code": "8867-4"}]}},
]


#: ``(label, sql, by_patient)`` per engine, built once per process.
_CACHE: list = []


def _connections():
    """Python-supplement and no-Python engines (both must answer the same)."""
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

    yield from ((_py(), "python"), (no_python_connection(), "no_python"))


def _translate(cql_text: str, con) -> str:
    from fhir4ds.cql.parser import parse_cql
    from fhir4ds.cql.translator.translator import CQLToSQLTranslator

    def library_loader(alias: str, version=None):
        text = _INCLUDED_LIBRARIES.get(alias)
        return parse_cql(text) if text is not None else None

    library = parse_cql(cql_text)
    translator = CQLToSQLTranslator(connection=con, library_loader=library_loader)
    translator.translate_library(library)
    return translator.translate_library_to_population_sql(
        library=library, output_columns=_COLUMNS,
    )


def _load(con) -> None:
    con.execute(
        "CREATE OR REPLACE TABLE resources (id VARCHAR, resourceType VARCHAR, "
        "resource JSON, patient_ref VARCHAR)"
    )
    for r in _RESOURCES:
        patient_ref = (r.get("subject") or {}).get("reference", "").split("/")[-1] or None
        con.execute(
            "INSERT INTO resources VALUES (?,?,?::JSON,?)",
            [r["id"], r["resourceType"], json.dumps(r), patient_ref],
        )


def _run_both_engines():
    """Yield ``(label, sql, by_patient)`` for each engine.

    Both engines and the whole result set are built ONCE per process: the
    fixture is static and identical for every test, and the no-Python engine has
    to LOAD the bundled C++ extension (expensive) for every connection.
    """
    if _CACHE:
        yield from _CACHE
        return
    for ctx, label in _connections():
        with ctx as con:
            # DuckDB 1.5.6 ENGINE BUG, not a lowering property: a correlated
            # `list()` aggregate over a `SELECT DISTINCT` CTE (every retrieve
            # CTE is one) intermittently returns a PARTIAL list when the plan
            # runs in parallel.  Minimal reproduction with no fhir4ds code:
            #
            #   WITH cte AS MATERIALIZED (SELECT DISTINCT patient_id, value
            #                              FROM raw),
            #        p   AS MATERIALIZED (SELECT DISTINCT ON (patient_id)
            #                              patient_id FROM pts)
            #   SELECT _pt.patient_id,
            #          COALESCE((SELECT list(_l.value) FROM cte AS _l
            #                     WHERE _l.patient_id = _pt.patient_id), [])
            #   FROM p AS _pt;         -- varies between runs at threads=8
            #
            # It affects every element-rows define materialization
            # (`_list_operator_full_list_source`, CQL-19/FHIR4-65), including
            # the pre-existing membership/First/IndexOf lowerings — this card
            # only makes it visible because list VALUES are compared instead of
            # booleans.  Pin the executor so the assertions below test the
            # LOWERING deterministically; the engine hazard is reported
            # separately.
            con.execute("SET threads=1")
            sql = _translate(_LIBRARY, con)
            # Keep DuckDB's default strictness: a shape defect must not be
            # masked by a harness flag (FHIR4-48/53 doctrine).
            con.execute("SET scalar_subquery_error_on_multiple_rows=true")
            _load(con)
            cursor = con.execute(sql)
            names = [d[0] for d in cursor.description]
            by_patient = {row[0]: dict(zip(names[1:], row[1:])) for row in cursor.fetchall()}
            _CACHE.append((label, sql, by_patient))
    yield from _CACHE


def _sorted(value):
    """Element order is unspecified by CQL (§Intersect/§Except: "no expectation
    that the order of the inputs will be preserved"), so compare as sets."""
    return sorted(value or [])


def test_intersect_over_two_multi_row_defines_uses_the_whole_lists():
    """The card's reproducer: `"Ids" intersect "Other"` (define vs define)."""
    for label, _sql, by_patient in _run_both_engines():
        assert set(by_patient) == {"p1", "p2", "p3"}, f"{label}: {sorted(by_patient)}"
        p1 = by_patient["p1"]
        # A one-row consumption can only produce ONE of these, and only by luck.
        assert _sorted(p1["BothIntersect"]) == ["c2", "c3"], (
            f"{label}: Ids intersect NonC1 must be exactly {{c2, c3}} — a "
            f"single-element or order-dependent answer means the operand was "
            f"truncated to one row; got {p1['BothIntersect']!r}"
        )
        # p3's single Condition IS in Ids, so its intersection is non-empty.
        assert _sorted(by_patient["p3"]["BothIntersect"]) == ["c9"], (
            f"{label}: p3 ∩ = {by_patient['p3']['BothIntersect']!r}, expected ['c9']"
        )
        # p2 has no Conditions at all.
        assert _sorted(by_patient["p2"]["BothIntersect"]) == [], (
            f"{label}: p2 has no Conditions, got {by_patient['p2']['BothIntersect']!r}"
        )
        # Element count is a set-size check independent of which elements.
        assert p1["SetOpThenLength"] == 2, (
            f"{label}: Length of the intersection must be 2, got "
            f"{p1['SetOpThenLength']!r}"
        )


def test_except_over_two_multi_row_defines_in_both_directions():
    """`except` is lowered separately — both directions must be the LIST op."""
    for label, _sql, by_patient in _run_both_engines():
        p1 = by_patient["p1"]
        assert _sorted(p1["BothExcept"]) == ["c1"], (
            f"{label}: Ids except NonC1 must be {{c1}}, got {p1['BothExcept']!r}"
        )
        assert _sorted(p1["BothExceptRev"]) == [], (
            f"{label}: NonC1 except Ids must be empty (NonC1 ⊂ Ids), got "
            f"{p1['BothExceptRev']!r}"
        )
        assert _sorted(by_patient["p3"]["BothExcept"]) == [], (
            f"{label}: p3's only id is in NonC1, so except must be empty, got "
            f"{by_patient['p3']['BothExcept']!r}"
        )
        assert _sorted(by_patient["p2"]["BothExcept"]) == [], (
            f"{label}: p2 has no Conditions"
        )
        # Consumers of the except result see the elements, not a nested list.
        assert p1["SetOpThenFirst"] in ("c1", None), (
            f"{label}: First of a one-element list must be that element (or "
            f"null on an empty list), got {p1['SetOpThenFirst']!r}"
        )


def test_intersect_of_disjoint_and_qualified_defines():
    """An empty intersection over non-empty operands, plus the qualified name."""
    for label, _sql, by_patient in _run_both_engines():
        p1 = by_patient["p1"]
        # Ids = {c1,c2,c3}, ObsIds = {o1}: both non-empty, no common element.
        assert _sorted(p1["DisjointIntersect"]) == [], (
            f"{label}: a disjoint intersection must be EMPTY, got "
            f"{p1['DisjointIntersect']!r}"
        )
        # Common."SharedIds" is the identical query, so the intersection is Ids.
        assert _sorted(p1["QualifiedIntersect"]) == ["c1", "c2", "c3"], (
            f"{label}: 'c1' in the qualified intersection means the "
            f"library-qualified define operand was truncated to one row; got "
            f"{p1['QualifiedIntersect']!r}"
        )
        assert _sorted(by_patient["p3"]["QualifiedIntersect"]) == ["c9"], (
            f"{label}: p3 ⊂ SharedIds"
        )


def test_union_over_multi_row_defines_still_works():
    """`union` already normalized its operands; keep it that way (regression)."""
    for label, _sql, by_patient in _run_both_engines():
        p1 = by_patient["p1"]
        assert _sorted(p1["BothUnion"]) == ["c1", "c2", "c3"], (
            f"{label}: Ids union NonC1 must be every id exactly once, got "
            f"{p1['BothUnion']!r}"
        )
        assert _sorted(by_patient["p3"]["BothUnion"]) == ["c9"], (
            f"{label}: p3 union = {by_patient['p3']['BothUnion']!r}"
        )


def test_define_against_literal_operands():
    """A define against a list LITERAL — the BinderException shapes."""
    for label, _sql, by_patient in _run_both_engines():
        p1 = by_patient["p1"]
        assert _sorted(p1["DefIntersectLit"]) == ["c2"], (
            f"{label}: Ids intersect {{c2, zz}} must be {{c2}}, got "
            f"{p1['DefIntersectLit']!r}"
        )
        assert _sorted(p1["LitIntersectDef"]) == ["c2"], (
            f"{label}: {{c2, zz, c9}} intersect Ids must be {{c2}}, got "
            f"{p1['LitIntersectDef']!r}"
        )
        assert _sorted(by_patient["p3"]["LitIntersectDef"]) == ["c9"], (
            f"{label}: p3's c9 IS in the literal, got "
            f"{by_patient['p3']['LitIntersectDef']!r}"
        )
        assert _sorted(p1["DefExceptLit"]) == ["c1", "c3"], (
            f"{label}: Ids except {{c2}} must be {{c1, c3}}, got "
            f"{p1['DefExceptLit']!r}"
        )
        assert _sorted(p1["LitExceptDef"]) == ["zz"], (
            f"{label}: {{c2, zz}} except Ids must be {{zz}}, got "
            f"{p1['LitExceptDef']!r}"
        )
        assert _sorted(by_patient["p3"]["LitExceptDef"]) == ["c2", "zz"], (
            f"{label}: p3's Ids is {{c9}}, so nothing is removed; got "
            f"{by_patient['p3']['LitExceptDef']!r}"
        )
        # union with a list literal must stay a FLAT list (no [[...]] nesting).
        assert _sorted(p1["DefUnionLit"]) == ["c1", "c2", "c3", "zz"], (
            f"{label}: Ids union {{zz}} must be a flat list, got "
            f"{p1['DefUnionLit']!r}"
        )


def test_chained_and_inline_consumers_of_a_set_operation():
    """The result feeds further operators inside the same definition."""
    for label, _sql, by_patient in _run_both_engines():
        p1 = by_patient["p1"]
        assert _sorted(p1["Chained"]) == ["c3"], (
            f"{label}: (Ids ∩ NonC1) except {{c2}} must be {{c3}}, got "
            f"{p1['Chained']!r}"
        )
        assert p1["InlineCount"] == 2, (
            f"{label}: Count of the intersection must be 2, got {p1['InlineCount']!r}"
        )
        assert p1["InlineHasC2"] is True, f"{label}: c2 IS in the intersection"
        assert p1["InlineHasC1"] is False, (
            f"{label}: c1 is NOT in the intersection (it is excluded by NonC1)"
        )


def test_null_operands_follow_the_list_signatures():
    """§Intersect: either null → null.  §Except: null second operand is empty."""
    for label, _sql, by_patient in _run_both_engines():
        p1 = by_patient["p1"]
        assert p1["IntersectNull"] is None, (
            f"{label}: intersect with a null list operand must be NULL, got "
            f"{p1['IntersectNull']!r}"
        )
        assert _sorted(p1["ExceptNull"]) == ["c1", "c2", "c3"], (
            f"{label}: except a null list must return the first list "
            f"unchanged, got {p1['ExceptNull']!r}"
        )


def test_no_limit_one_scalar_consumption_of_the_define():
    """The generated SQL must never scalarize a set-operation operand."""
    for label, sql, _by_patient in _run_both_engines():
        hit = _LIMIT_ONE_CONSUMPTION.search(sql)
        assert hit is None, (
            f"{label}: a set operation consumed the define's row CTE as a "
            f"scalar ({hit.group(0)[:120]!r}) — the LIST operand must be "
            f"materialized per patient, not truncated with LIMIT 1"
        )
        # Positive control: intersect/except reach the LIST macros over the
        # aggregated per-patient element lists, not a row-level SQL set op.
        for macro in ("CQLListIntersectEq", "CQLListExceptEq"):
            assert macro in sql, f"{label}: expected {macro} in the generated SQL"
        assert re.search(
            r'list\(_lst_src\.value\)\s+FROM\s+"(?:Ids|NonC1)"', sql, re.IGNORECASE
        ), f"{label}: expected the define's rows to be aggregated into a list"
        assert " INTERSECT " not in sql and " EXCEPT " not in sql, (
            f"{label}: set operations over value lists must not lower to a "
            f"row-level SQL set operation"
        )
