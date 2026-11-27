"""FHIR4-86 — an aggregate over a DEFINE source iterates the define's elements.

The readable way to write a fold is over a define:

    define "L": {1, 2, 3, 4, 5, 6}
    define "R": "L" N aggregate A starting 0.5: A + 1

The inlined form of the same fold answered 6.5, while the define form was a Binder Error
(``Referenced table "N" not found``): the fold treated EVERY definition CTE as a
``(patient_id, resource)`` rows table, so a stored-list define was read through a
``.resource`` column it does not have. A definition CTE holds one of three shapes and the
``DefinitionMeta`` says which — see ``_fold_source_element_sql``.

Values only, never binding: the assertions are the numbers the CQL means.
"""

from __future__ import annotations

import json
from contextlib import contextmanager
from decimal import Decimal

import duckdb
import pytest

from fhir4ds.cql.duckdb.tests.integration.wasm_runtime_helpers import no_python_connection

#: p1 has six list elements, two given names and two conditions.
_DATA = {
    "p1": (["A", "B"], ["c1", "c2"]),
}

_HEAD = """library F86 version '1.0.0'
using FHIR version '4.0.1'
context Patient
define "Initial Population": exists (Patient)
define "Denominator": "Initial Population"
define "Numerator": "Initial Population"
"""


@contextmanager
def _python_connection():
    from fhir4ds.cql.duckdb.extension import _register_python_supplements

    con = duckdb.connect()
    _register_python_supplements(con, cpp_loaded=False, include_fhirpath=True)
    try:
        yield con
    finally:
        con.close()


def _engines():
    """Python supplements and the C++-only engine: the lowering must hold on both."""
    for build in (_python_connection, no_python_connection):
        with build() as con:
            yield con


def _load(con) -> None:
    con.execute(
        "CREATE OR REPLACE TABLE resources (id VARCHAR, resourceType VARCHAR, resource JSON, "
        "patient_ref VARCHAR)"
    )
    rows = [
        (
            pid,
            "Patient",
            {
                "resourceType": "Patient",
                "id": pid,
                "name": [{"given": names, "family": "F"}],
            },
            pid,
        )
        for pid, (names, _) in _DATA.items()
    ]
    for pid, (_, conditions) in _DATA.items():
        rows += [
            (
                cid,
                "Condition",
                {
                    "resourceType": "Condition",
                    "id": cid,
                    "subject": {"reference": f"Patient/{pid}"},
                },
                pid,
            )
            for cid in conditions
        ]
    for rid, rtype, resource, pid in rows:
        con.execute(
            "INSERT INTO resources VALUES (?,?,?::JSON,?)",
            [rid, rtype, json.dumps(resource), pid],
        )


def _translate(con, definitions: str, expression: str) -> str:
    from fhir4ds.cql.parser import parse_cql
    from fhir4ds.cql.translator.translator import CQLToSQLTranslator

    library = parse_cql(_HEAD + definitions + f'define "D": {expression}\n')
    translator = CQLToSQLTranslator(connection=con, library_loader=lambda *a: None)
    translator.translate_library(library)
    return translator.translate_library_to_population_sql(
        library=library,
        output_columns={"Initial Population": "Initial Population", "D": "D"},
    )


def _answer(con, definitions: str, expression: str):
    """(value, SQL type) the definition answers for p1 through the population SQL."""
    sql = _translate(con, definitions, expression)
    _load(con)
    cursor = con.execute(sql)
    names = [column[0] for column in cursor.description]
    rows = cursor.fetchall()
    assert len(rows) == 1, rows
    typed = con.execute(
        f"SELECT (D), typeof((D)) FROM ({sql}) AS _pop"
    ).fetchone()
    return typed[0], typed[1]


_LIST = 'define "L": {1, 2, 3, 4, 5, 6}\n'
_NAMES = 'define "L": Patient.name.given\n'
_LIST_QUERY = 'define "L": ({10, 20, 30}) N return N\n'
_ELEMENT_QUERY = 'define "L": [Condition] C return C.id\n'
_RESOURCES = 'define "L": [Condition]\n'

#: (id, definitions, expression, expected answer for p1)
_CASES = [
    # ── The reported shape: a static list define, with the card's Decimal start ────────────
    ("StoredListDecimalStart", _LIST, '"L" N aggregate A starting 0.5: A + 1', Decimal("6.5")),
    ("StoredListIntegralStart", _LIST, '"L" N aggregate A starting 0: A + N', 21),
    # A fold without a starting value reads the same elements.
    ("StoredListNoStart", _LIST, '"L" N aggregate A: Coalesce(A, 0) + 1', 6),
    # A fold without a starting value still honours the query's WHERE over the elements.
    ("StoredListNoStartFiltered", _LIST, '"L" N where N > 3 aggregate A: Coalesce(A, 0) + 1', 3),
    ("StoredListFiltered", _LIST, '"L" N where N > 3 aggregate A starting 0: A + N', 15),
    # ── A navigation define is a stored list of its per-patient values ─────────────────────
    ("NavigationDefine", _NAMES, '"L" N aggregate A starting 0: A + 1', 2),
    # ── A query define stored as ONE list value ───────────────────────────────────────────
    ("ListValuedQueryDefine", _LIST_QUERY, '"L" N aggregate A starting 0: A + N', 60),
    # ── A query define stored as one VALUE ROW per element ────────────────────────────────
    ("ValueRowsQueryDefine", _ELEMENT_QUERY, '"L" N aggregate A starting 0: A + 1', 2),
    # ── A resource-rows define was the one shape that already worked; keep it working ─────
    ("ResourceRowsDefine", _RESOURCES, '"L" N aggregate A starting 0: A + 1', 2),
]

_TYPES = {"Decimal": "DECIMAL(38,8)"}


@pytest.mark.parametrize(
    ("definitions", "expression", "expected"),
    [(c[1], c[2], c[3]) for c in _CASES],
    ids=[c[0] for c in _CASES],
)
def test_a_fold_over_a_define_iterates_the_defines_elements(definitions, expression, expected):
    for con in _engines():
        value, sql_type = _answer(con, definitions, expression)
        if isinstance(expected, Decimal):
            assert isinstance(value, Decimal) and value == expected, (
                f"answered {value!r} ({sql_type})"
            )
            assert sql_type == _TYPES["Decimal"], f"SQL type {sql_type}"
        else:
            assert value == expected, f"answered {value!r} ({sql_type})"


def test_the_stored_list_source_is_the_defines_value_column_not_a_resource_column():
    """The fold must not read a `resource` column off a define that has none."""
    for con in _engines():
        sql = _translate(con, _LIST, '"L" N aggregate A starting 0.5: A + 1')
        assert 'list_transform(list(' not in sql, sql[sql.index("WITH RECURSIVE") :][:600]
        assert '"L"."value"' in sql, sql[sql.index("WITH RECURSIVE") :][:600]
