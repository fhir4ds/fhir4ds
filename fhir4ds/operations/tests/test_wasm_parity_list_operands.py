"""List operands on the engine the web apps run (FHIR4-72 hoist shape, pinned with WP-6).

FHIR4-72 found that TWO correlated ``list()`` aggregates in one SELECT come back partial at
``threads > 1``, so the translator hoists every aggregated operand of a list-BINARY operator
(``intersect``, ``except``, ``=``, ``~``, ``includes``, ...) into its own ``_cse_*`` value CTE.
That invariant is pinned on desktop by
``fhir4ds/cql/duckdb/tests/integration/test_fhir4_72_list_operand_determinism.py``, which also
keeps ONE inline operand for element membership (``x in list``). WP-6 changed membership
lowering (``contains`` / ``in`` over a resource-rows define now test every row) in the same
translator functions, so this file runs one library that carries BOTH shapes:

* the hoist invariant over the population SQL (desktop translation);
* the answers on real duckdb-wasm, and their stability across repetitions;
* the answers on desktop at the default thread count, across repetitions.

Skips with the other real-engine gates when chromium or the web ``node_modules`` are absent;
red under ``FHIR4DS_REQUIRE_WASM_PARITY=1`` and ``FHIR4DS_REQUIRE_WASM_REAL=1``. Runs WITHOUT
``scripts/capped.sh`` (chromium cannot start with a capped address space).
"""

from __future__ import annotations

import json
import re

import pytest

from fhir4ds.cql.duckdb.tests.integration import test_fhir4_72_list_operand_determinism as f72
from fhir4ds.operations.tests.wasm_parity.tier_c import _literal

#: FHIR4-72's two element-rows defines plus WP-6's membership over a resource-rows define.
_LIBRARY = f72._LIBRARY.replace(
    "define \"BothIncludes\": \"Ids\" properly includes \"NonC1\"",
    "\n".join(
        [
            "define \"BothIncludes\": \"Ids\" properly includes \"NonC1\"",
            "",
            "// WP-6: membership over a RESOURCE-ROWS define tests every row.",
            "define \"All\": [Condition] C",
            "define \"Active\": \"All\" C where C.id != 'c1'",
            "define \"Matched\": \"All\" C where \"Active\" contains C return C.id",
            "define \"MatchedByIn\": \"All\" C where C in \"Active\" return C.id",
        ]
    ),
)

_COLUMNS = {
    "Initial Population": "Initial Population",
    "BothIntersect": "BothIntersect",
    "BothEqual": "BothEqual",
    "BothIncludes": "BothIncludes",
    "Matched": "Matched",
    "MatchedByIn": "MatchedByIn",
    "OneContains": "OneContains",
}
_NAMES = [c for c in _COLUMNS if c != "Initial Population"]

#: Hand-derived from ``f72._RESOURCES``: p1 carries c1/c2/c3, p2 nothing, p3 c9.
_EXPECTED = {
    "p1": {
        "BothIntersect": ["c2", "c3"],
        "BothEqual": False,
        "BothIncludes": True,
        "Matched": ["c2", "c3"],
        "MatchedByIn": ["c2", "c3"],
        "OneContains": True,
    },
    "p2": {
        "BothIntersect": [],
        "BothEqual": True,
        "BothIncludes": False,
        "Matched": [],
        "MatchedByIn": [],
        "OneContains": False,
    },
    "p3": {
        "BothIntersect": ["c9"],
        "BothEqual": True,
        "BothIncludes": False,
        "Matched": ["c9"],
        "MatchedByIn": ["c9"],
        "OneContains": False,
    },
}

_DDL = (
    "CREATE OR REPLACE TABLE resources (id VARCHAR, resourceType VARCHAR, resource JSON, "
    "patient_ref VARCHAR)"
)
_REPETITIONS = 25
_DESKTOP_REPETITIONS = 300
_HOIST = re.compile(r'FROM "(_cse_[^"]+)"')
#: Element membership keeps ONE inline list operand by design (FHIR4-72 test file).
_ELEMENT_MEMBERSHIP = re.compile(r"CQLListContains\w*|CQLIndexOf\w*")


def _load_statements() -> list[tuple[str, str]]:
    rows = []
    for resource in f72._RESOURCES:
        patient_ref = (resource.get("subject") or {}).get("reference", "").split("/")[-1] or None
        values = (resource["id"], resource["resourceType"], json.dumps(resource), patient_ref)
        rows.append("(" + ", ".join(_literal(v) for v in values) + ")")
    return [
        ("ddl resources", _DDL),
        ("ins resources", "INSERT INTO resources VALUES " + ", ".join(rows)),
    ]


def _translate(con) -> str:
    from fhir4ds.cql.parser import parse_cql
    from fhir4ds.cql.translator.translator import CQLToSQLTranslator

    library = parse_cql(_LIBRARY)
    translator = CQLToSQLTranslator(connection=con)
    translator.translate_library(library)
    return translator.translate_library_to_population_sql(library=library, output_columns=_COLUMNS)


def _wrapped(sql: str) -> str:
    select = ", ".join(f'("{c}")::VARCHAR AS c{i}' for i, c in enumerate(_NAMES))
    return f"SELECT patient_id::VARCHAR AS _pid, {select} FROM ({sql}) AS _pop"


def _normal(text):
    """CQL list-operator element ORDER is unspecified — compare lists as sorted content."""
    if text is None:
        return None
    if text.startswith("["):
        inner = text[1:-1]
        return sorted(inner.split(", ")) if inner else []
    return text == "true" if text in ("true", "false") else text


def _answers(rows: list[dict]) -> dict:
    """Rows as the harness delivers them: every value is an Arrow ``[type, value]`` tag."""
    from fhir4ds.operations.tests.wasm_parity.real_engine import plain

    return {
        str(plain(row["_pid"])): {
            n: _normal(str(plain(row[f"c{i}"]))) for i, n in enumerate(_NAMES)
        }
        for row in rows
    }


@pytest.fixture(scope="module")
def loaded(wasm_desktop):
    """The session connection with this module's ``resources`` table; removed afterwards."""
    statements = _load_statements()
    for _label, text in statements:
        wasm_desktop.execute(text)
    try:
        yield statements
    finally:
        wasm_desktop.execute("DROP TABLE IF EXISTS resources")


def test_list_binary_operators_consume_only_materialized_operands(wasm_desktop):
    """No list-BINARY operator SELECT carries a correlated ``list()`` aggregate.

    A list macro re-expands its arguments textually, so a correlated ``list()`` aggregate left in
    an argument position is re-evaluated there and can come back partial (FHIR4-72). Each
    aggregated operand must be its own patient-scoped CTE holding exactly one ``list()``.
    Element membership (``x in list``) keeps its single inline operand by design.
    """
    bodies = f72._cte_bodies(_translate(wasm_desktop))
    assert bodies, "no CTEs found in the population SQL"
    binary, membership = [], []
    for name, body in bodies.items():
        if not re.search(r"CQLList\w+", body):
            continue
        (membership if _ELEMENT_MEMBERSHIP.search(body) else binary).append(name)
        for hoisted_name in set(_HOIST.findall(body)):
            hoisted = bodies.get(hoisted_name)
            assert hoisted is not None, f"{name!r}: dangling hoist {hoisted_name!r}"
            assert hoisted.count("list(") == 1, (
                f"{name!r}: hoisted operand {hoisted_name!r} must hold exactly one list() "
                f"aggregate: {hoisted!r}"
            )
            assert 'FROM "_patients" AS _pt' in hoisted, (
                f"{name!r}: hoisted operand {hoisted_name!r} is not patient-scoped: {hoisted!r}"
            )
    offenders = sorted(name for name in binary if "list(" in bodies[name])
    assert not offenders, (
        "list operator SELECT(s) still embed a correlated list() aggregate: "
        f"{offenders}; first body: {bodies[offenders[0]][:600]!r}"
    )
    # Both families are present, so the rule above was applied to something.
    assert {"BothIntersect", "BothEqual", "BothIncludes"} <= set(binary), binary
    assert "OneContains" in membership, membership


def test_membership_over_resource_rows_is_a_row_test_not_a_list_aggregate(wasm_desktop):
    """WP-6: ``contains`` / ``in`` over a resource-rows define compare ROWS, every row.

    Neither lowering may regress to the list-macro path (a correlated ``list()`` aggregate) nor
    keep the ``LIMIT 1`` that made only the plan's first row eligible.
    """
    bodies = f72._cte_bodies(_translate(wasm_desktop))
    for define in ("Matched", "MatchedByIn"):
        body = bodies[define]
        assert "list(" not in body, f"{define!r} lowers through a list() aggregate: {body!r}"
        assert "LIMIT 1" not in body, f"{define!r} still tests only the first row: {body!r}"
        assert 'FROM "All" AS C' in body and 'FROM "Active" AS sub' in body, body
        assert "sub.patient_id = C.patient_id" in body, body


def test_answers_are_stable_on_desktop_at_default_threads(wasm_desktop, loaded):
    """:_DESKTOP_REPETITIONS executions at the default thread count, ONE answer per patient."""
    configured = int(wasm_desktop.execute("SELECT current_setting('threads')").fetchone()[0])
    if configured < 2:  # never pin threads=1: the FHIR4-72 defect only exists in parallel
        wasm_desktop.execute("SET threads=4")
    sql = _wrapped(_translate(wasm_desktop))
    distinct = {
        json.dumps(
            _answers_by_row(wasm_desktop.execute(sql).fetchall()), sort_keys=True, default=str
        )
        for _ in range(_DESKTOP_REPETITIONS)
    }
    assert len(distinct) == 1, f"{_DESKTOP_REPETITIONS} executions gave {len(distinct)} answers"
    assert json.loads(next(iter(distinct))) == json.loads(json.dumps(_EXPECTED, default=str))


def _answers_by_row(rows) -> dict:
    return {
        str(row[0]): {n: _normal(str(v)) for n, v in zip(_NAMES, row[1:], strict=True)}
        for row in rows
    }


def test_answers_match_desktop_on_real_duckdb_wasm(wasm_desktop, wasm_real, loaded):
    """The same SQL on the real engine: desktop answers, identical across repetitions."""
    sql = _wrapped(_translate(wasm_desktop))
    desktop = _answers_by_row(wasm_desktop.execute(sql).fetchall())
    assert desktop == _EXPECTED, "desktop does not give the hand-derived answers"

    job = wasm_real.job(
        statements=loaded + [("population", sql)] * _REPETITIONS, hard_timeout_ms=120_000
    )
    results = job.get("results") or []
    assert len(results) == len(loaded) + _REPETITIONS, (
        f"engine returned {len(results)} results for {len(loaded) + _REPETITIONS} statements"
    )
    errors = [str(r.get("error") or "")[:200] for r in results if not r["ok"]]
    assert not errors, f"real engine errors: {errors[:3]}"
    runs = [_answers(r["rows"]) for r in results[len(loaded):]]
    distinct = {json.dumps(run, sort_keys=True) for run in runs}
    assert len(distinct) == 1, (
        f"{_REPETITIONS} repetitions on real duckdb-wasm produced {len(distinct)} distinct answers"
    )
    assert runs[0] == _EXPECTED, f"real duckdb-wasm differs from desktop: {runs[0]}"
