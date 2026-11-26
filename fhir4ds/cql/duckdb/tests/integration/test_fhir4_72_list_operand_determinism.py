"""FHIR4-72 — TWO correlated ``list()`` operands in ONE SELECT are non-deterministic.

DuckDB 1.5.x mis-executes a projection that carries **two** correlated
``list()`` aggregates: each operand of a list-binary operator lowers to

    COALESCE((SELECT list(_lst_src.value) FROM "<Def>" AS _lst_src
               WHERE _lst_src.patient_id = _pt.patient_id), [])

and at ``threads > 1`` one of the two intermittently yields a PARTIAL list (or
nothing). It is SILENT: the defect is a list VALUE, so a truncated operand
reads as a smaller answer instead of an error, and a boolean derived from it
(Q3 "=  Q3", Q3 "properly includes" Q3) simply flips.

Measured on the FHIR4-67/70 lowering with this fixture (3000 executions of one
translated population SQL, patients p1={c1,c2,c3}, p2=empty, p3={c9}):

    two correlated list() operands in one SELECT   threads=8 ->  63/3000 wrong
                                                   threads=4 -> 376/3000 wrong
    ONE correlated list() operand                  threads=8 ->   0/3000 wrong
                                                   threads=4 ->   0/3000 wrong
    each operand hoisted into its own CTE          threads=8 ->   0/3000 wrong
                                                   threads=4 ->   0/3000 wrong

The trigger is the OPERAND COUNT. ``DISTINCT``, distinct inner aliases and
``AS MATERIALIZED`` make no difference. Fewer threads is WORSE, so a small CI
runner is the worst case — and plain ``duckdb.connect()`` defaults to the core
count (32 on the DQM host), which means every DQM gate run executes inside the
window.

The fix (FHIR4-72) evaluates each aggregated operand ONCE in its own
``_cse_*`` value CTE and passes a correlated value lookup to the operator, so
the operator SELECT contains no correlated list aggregate at all. These tests
pin BOTH halves: the emitted shape, and the result under repetition at the
DEFAULT thread count — never ``SET threads=1``, which is exactly what hides
this defect.
"""

from __future__ import annotations

import json
import re
from contextlib import contextmanager

import duckdb

from .wasm_runtime_helpers import no_python_connection

#: Repetitions. Each execution re-plans and re-runs the SAME SQL, so this is a
#: race sampler, not a benchmark. 250 is ~4x the sample that already surfaced
#: 63/3000 wrong at threads=8 while keeping the suite fast.
_RUNS = 250

_LIBRARY = """library F72Determinism version '1.0.0'
using FHIR version '4.0.1'
context Patient

// Two element-rows defines — ONE CTE row per element.
define "Ids": ([Condition] C return C.id) X
define "NonC1": ([Condition] C where C.id != 'c1' return C.id) X

// Two-operand list operators: each LOWERS to a two-correlated-list SELECT.
define "BothIntersect": "Ids" intersect "NonC1"
define "BothExcept": "Ids" except "NonC1"
define "BothEqual": "Ids" = "NonC1"
define "BothEquivalent": "NonC1" ~ "NonC1"
define "BothIncludes": "Ids" properly includes "NonC1"

// ONE list operand: safe before and after the fix (regression guard).
define "OneContains": 'c1' in "Ids"
define "OneIntersectLit": "Ids" intersect { 'c2', 'zz' }

define "Initial Population": exists (Patient)
define "Denominator": "Initial Population"
define "Numerator": "Initial Population"
"""

_COLUMNS = {
    "Initial Population": "Initial Population",
    "BothIntersect": "BothIntersect",
    "BothExcept": "BothExcept",
    "BothEqual": "BothEqual",
    "BothEquivalent": "BothEquivalent",
    "BothIncludes": "BothIncludes",
    "OneContains": "OneContains",
    "OneIntersectLit": "OneIntersectLit",
}

#: p1 carries c1/c2/c3, p2 carries NOTHING (the empty-list projection), p3
#: carries a single c9 — so "shares no element with Ids" is exercised on a
#: patient whose own list is non-empty.
_RESOURCES = [
    {"resourceType": "Patient", "id": "p1", "gender": "female"},
    {"resourceType": "Patient", "id": "p2", "gender": "male"},
    {"resourceType": "Patient", "id": "p3", "gender": "female"},
    {"resourceType": "Condition", "id": "c1", "subject": {"reference": "Patient/p1"}},
    {"resourceType": "Condition", "id": "c2", "subject": {"reference": "Patient/p1"}},
    {"resourceType": "Condition", "id": "c3", "subject": {"reference": "Patient/p1"}},
    {"resourceType": "Condition", "id": "c9", "subject": {"reference": "Patient/p3"}},
]

#: The CQL answers, derived by hand from the fixture (sizes 3/2/1/0/0).
_EXPECTED = {
    "p1": {
        "BothIntersect": ["c2", "c3"],
        "BothExcept": ["c1"],
        "BothEqual": False,
        "BothEquivalent": True,
        "BothIncludes": True,
        "OneContains": True,
        "OneIntersectLit": ["c2"],
    },
    "p2": {
        "BothIntersect": [],
        "BothExcept": [],
        "BothEqual": True,
        "BothEquivalent": True,
        "BothIncludes": False,
        "OneContains": False,
        "OneIntersectLit": [],
    },
    "p3": {
        "BothIntersect": ["c9"],
        "BothExcept": [],
        "BothEqual": True,
        "BothEquivalent": True,
        "BothIncludes": False,
        "OneContains": False,
        "OneIntersectLit": [],
    },
}

#: ``"<name>" AS MATERIALIZED (\n<body>\n),`` or ``"<name>" AS (\n<body>\n),``
_CTE_BODY = re.compile(
    r'"([^"]+)" AS (?:MATERIALIZED )?\(\n(.*?)\n\),?\n', re.DOTALL
)


def _cte_bodies(sql: str) -> dict:
    return {match.group(1): match.group(2) for match in _CTE_BODY.finditer(sql)}


def _connections():
    """Python-supplement and no-Python (C++-only) engines, both exercised."""
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


def _translate(con) -> str:
    from fhir4ds.cql.parser import parse_cql
    from fhir4ds.cql.translator.translator import CQLToSQLTranslator

    library = parse_cql(_LIBRARY)
    translator = CQLToSQLTranslator(connection=con)
    translator.translate_library(library)
    return translator.translate_library_to_population_sql(
        library=library, output_columns=_COLUMNS
    )


def _load(con) -> None:
    con.execute(
        "CREATE OR REPLACE TABLE resources (id VARCHAR, resourceType VARCHAR, "
        "resource JSON, patient_ref VARCHAR)"
    )
    for resource in _RESOURCES:
        patient_ref = (
            (resource.get("subject") or {}).get("reference", "").split("/")[-1] or None
        )
        con.execute(
            "INSERT INTO resources VALUES (?,?,?::JSON,?)",
            [resource["id"], resource["resourceType"], json.dumps(resource), patient_ref],
        )


#: ``(label, sql, blocks, results)`` per engine, built once per process.
_CACHE: list = []


def _run_both_engines():
    """Yield ``(label, sql, cte_bodies, rows)`` for each engine.

    ``rows`` is a LIST of ``{patient_id: {column: value}}`` — one entry per
    execution — so the caller can assert that every repetition agrees.
    """
    if _CACHE:
        yield from _CACHE
        return
    for ctx, label in _connections():
        with ctx as con:
            # NEVER pin threads=1: the defect only exists in parallel
            # execution, and pinning it is what made it invisible.
            configured = con.execute("SELECT current_setting('threads')").fetchone()[0]
            if int(configured) < 2:
                # Single-core runner: still exercise the parallel path.
                con.execute(f"SET threads={4}")
            con.execute("SET scalar_subquery_error_on_multiple_rows=true")
            sql = _translate(con)
            _load(con)
            names = None
            rows = []
            for _ in range(_RUNS):
                cursor = con.execute(sql)
                if names is None:
                    names = [column[0] for column in cursor.description]
                rows.append(
                    {
                        row[0]: dict(zip(names[1:], row[1:]))
                        for row in cursor.fetchall()
                    }
                )
            _CACHE.append((label, sql, _cte_bodies(sql), rows))
    yield from _CACHE


def _sorted_value(value):
    """CQL list-operator element ORDER is unspecified — compare as sets."""
    return sorted(value or [])


def _normalize(value):
    return _sorted_value(value) if isinstance(value, list) else value


def _canonical(rows) -> set:
    """Order-insensitive fingerprint of one execution's per-patient results.

    CQL list-operator element ORDER is unspecified (§Intersect/§Except: "no
    expectation that the order of the inputs will be preserved") and the
    underlying query has no ORDER BY, so only the CONTENT is a determinism
    property — sorting the lists keeps this a detector for truncation, not for
    row-order luck.
    """
    fingerprints = set()
    for patient_id, row in rows.items():
        normalized = {column: _normalize(value) for column, value in row.items()}
        fingerprints.add(json.dumps([patient_id, normalized], sort_keys=True, default=str))
    return fingerprints


def test_list_macro_arguments_carry_no_correlated_list_aggregate():
    """The lowering invariant the determinism below depends on.

    A list macro re-expands its arguments textually (``CQLListEqualEq``
    mentions ``left_lst`` in ``array_length`` twice and again inside two
    nested ``EXISTS (… unnest(left_lst) …)`` subqueries), so a correlated
    ``list()`` aggregate left in an argument position is RE-EVALUATED there and
    intermittently comes back partial. It must be materialized first — for a
    SINGLE aggregated operand too (measured: `Ids intersect { 'c2','zz' }` was
    88/3000 wrong at threads=8 and 560/3000 at threads=4 with the aggregate
    inline, 0/3000 hoisted).
    """
    macro_defines = (
        "BothIntersect", "BothExcept", "BothEqual", "BothEquivalent",
        "BothIncludes", "OneIntersectLit",
    )
    for label, _sql, bodies, _rows in _run_both_engines():
        for define in macro_defines:
            body = bodies.get(define)
            assert body is not None, f"{label}: missing CTE for {define!r}"
            operators = re.findall(r"CQLList\w+", body)
            assert operators, (
                f"{label}: {define!r} does not dispatch to a list-binary macro: {body!r}"
            )
            # The operator SELECT must NOT carry an inline correlated list()
            # aggregate — those live in the per-operand `_cse_` CTEs.
            assert "list(" not in body, (
                f"{label}: {define!r} still embeds a correlated list() aggregate "
                f"in the operator SELECT (FHIR4-72 hazard): {body!r}"
            )
            referenced = set(re.findall(r'FROM "(_cse_[^"]+)"', body))
            assert referenced, f"{label}: {define!r} has no hoisted operand: {body!r}"
            for cte_name in referenced:
                hoisted = bodies.get(cte_name)
                assert hoisted is not None, f"{label}: dangling hoist {cte_name!r}"
                assert hoisted.count("list(") == 1, (
                    f"{label}: hoisted operand {cte_name!r} must hold exactly one "
                    f"list() aggregate: {hoisted!r}"
                )
                # ... and it must be the per-patient evaluation, so the value
                # is a property of the PATIENT, not of the surrounding row.
                assert 'FROM "_patients" AS _pt' in hoisted, (
                    f"{label}: hoisted operand {cte_name!r} is not patient-scoped: "
                    f"{hoisted!r}"
                )


def test_two_operand_list_operators_are_deterministic_at_default_threads():
    """The card: N executions, ONE distinct result per patient, exact content."""
    for label, _sql, _bodies, rows in _run_both_engines():
        assert len(rows) == _RUNS, f"{label}: collected {len(rows)} executions"

        # Exactly ONE distinct result keyed by patient_id across every
        # repetition — the whole point of the card.
        distinct = {tuple(sorted(_canonical(row))) for row in rows}
        assert len(distinct) == 1, (
            f"{label}: {_RUNS} executions at default threads produced "
            f"{len(distinct)} DISTINCT result sets (a truncated correlated "
            f"list() operand answers differently from run to run)"
        )

        for patient_id, expected in _EXPECTED.items():
            got = rows[0][patient_id]
            for column, want in expected.items():
                if isinstance(want, list):
                    assert _sorted_value(got[column]) == want, (
                        f"{label}: {patient_id}.{column} = {got[column]!r}, "
                        f"expected {want!r}"
                    )
                else:
                    assert got[column] is want, (
                        f"{label}: {patient_id}.{column} = {got[column]!r}, "
                        f"expected {want!r}"
                    )


def test_in_contains_keep_their_single_inline_list_operand():
    """`in`/`contains` were measured CLEAN in both forms — do not re-shape them.

    `CQLListContainsEq(<inline correlated aggregate>, 'c1')` returned the same
    answer in 3000/3000 executions at threads=4 and threads=8, so its lowering
    keeps the inline aggregate (no value CTE, no SQL churn on the membership
    surface that real measures use).
    """
    for label, _sql, bodies, rows in _run_both_engines():
        body = bodies.get("OneContains")
        assert body is not None, f"{label}: missing CTE for 'OneContains'"
        assert "list(" in body, (
            f"{label}: 'in' should keep its single correlated list() operand: {body!r}"
        )
        assert "_cse_" not in body, (
            f"{label}: 'in' must not hoist its list operand: {body!r}"
        )
        assert rows[0]["p1"]["OneContains"] is True


def test_intersect_content_is_not_truncated_by_repetition():
    """The card's headline symptom: a len-1 or empty answer for p1."""
    for label, _sql, _bodies, rows in _run_both_engines():
        for run_index, row in enumerate(rows):
            value = row["p1"]["BothIntersect"]
            assert _sorted_value(value) == ["c2", "c3"], (
                f"{label}: execution {run_index} of {_RUNS} returned p1 "
                f"intersect = {value!r} (expected the 2-element ['c2', 'c3']; an "
                f"empty or 1-element answer is a truncated correlated list() "
                f"operand, FHIR4-72)"
            )
