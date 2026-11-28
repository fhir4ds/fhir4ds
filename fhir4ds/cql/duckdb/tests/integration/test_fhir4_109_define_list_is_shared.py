"""FHIR4-109 — a define's materialized LIST is evaluated once, whatever consumes it.

The card's gate (`test_fhir4_109_define_is_one_value.py`) pins the defect on an
ELEMENT-ROWS define (``define Ids: ([Condition] C return C.id) X``, one CTE row
per element) and on the value-column aggregate. The same defect exists on every
OTHER shape that materializes a define's rows into a per-patient list, because
``list()`` over a CTE whose row order is undefined (the retrieve CTE is
``SELECT DISTINCT …``) may return a different PERMUTATION at each evaluation
site — so two POSITIONAL consumers silently disagree:

* a RESOURCE define (``define Obs: [Condition]``, one row per resource), whose
  list is built with ``list(sub.resource)`` by the Indexer / First / Last /
  Length paths;
* the AGGREGATE path (``Count``/``Sum``/…), which builds its own copy of the
  element-rows aggregate (``_element_rows_define_list``) — CMS117 aggregates two
  such defines twice each in the corpus;
* ``First``/``Last`` over a resource define, a fourth copy.

All of them now resolve to ONE ``_cse_deflist_…`` value CTE per define
(``OperatorsMixin._share_define_list``), so these tests assert BOTH halves:
the mechanism (one aggregate, one shared CTE referenced by every consumer) and
the value under repetition at the default thread count — never ``SET
threads=1``, which is exactly what hides this class.
"""

from __future__ import annotations

import json
import re
from contextlib import contextmanager

import pytest

from .wasm_runtime_helpers import no_python_connection

#: Repetitions. One translation, many executions: each execution re-plans the
#: SAME SQL, so this samples the thread race rather than the translator.
_RUNS = 150

_RESOURCES = [
    {"resourceType": "Patient", "id": "p1"},
    {"resourceType": "Patient", "id": "p2"},
    *[
        {"resourceType": "Condition", "id": cid, "subject": {"reference": "Patient/p1"}}
        for cid in ("c1", "c2", "c3")
    ],
]


@contextmanager
def _python_connection():
    import duckdb

    from fhir4ds.cql.duckdb.extension import _register_python_supplements

    con = duckdb.connect()
    _register_python_supplements(con, cpp_loaded=False, include_fhirpath=True)
    try:
        yield con
    finally:
        con.close()


def _connections():
    yield from ((_python_connection(), "python"), (no_python_connection(), "no_python"))


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


_PREAMBLE = """library F109Shared version '1.0.0'
using FHIR version '4.0.1'
context Patient

"""

_COLUMNS_FIVE = {name: name for name in ("A", "B", "I0", "I1", "I2")}

_EPILOGUE = """
define "Initial Population": exists (Patient)
define "Denominator": "Initial Population"
define "Numerator": "Initial Population"
"""


def _run(cql_body: str, columns: dict[str, str]):
    """Translate + execute once per engine; return (label, sql, rows) per engine."""
    from fhir4ds.cql.parser import parse_cql
    from fhir4ds.cql.translator.translator import CQLToSQLTranslator

    library = parse_cql(_PREAMBLE + cql_body + _EPILOGUE)
    for ctx, label in _connections():
        with ctx as con:
            _load(con)
            translator = CQLToSQLTranslator(connection=con)
            translator.translate_library(library)
            sql = translator.translate_library_to_population_sql(
                library=library, output_columns=columns
            )
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
            yield label, sql, rows


def _shared_cte_names(sql: str) -> list[str]:
    return sorted(set(re.findall(r'FROM "(_cse_deflist_[^"]+)"', sql)))


def test_resource_define_list_is_materialized_once():
    """`define Obs: [Condition]` indexed from two definitions must agree."""
    body = (
        'define "Obs": [Condition]\n'
        'define "A": "Obs"[0].id\n'
        'define "B": "Obs"[0].id\n'
        'define "I0": "Obs"[0].id\n'
        'define "I1": "Obs"[1].id\n'
        'define "I2": "Obs"[2].id\n'
    )
    for label, sql, rows in _run(body, _COLUMNS_FIVE):
        shared = _shared_cte_names(sql)
        assert len(shared) == 1, (
            f"{label}: the resource define's list must be materialized ONCE and "
            f"shared; found {shared}"
        )
        assert sql.count("list(sub.resource)") == 1, (
            f"{label}: {sql.count('list(sub.resource)')} copies of the resource "
            "list aggregate — one evaluation per define is the invariant"
        )
        for run_index, row in enumerate(rows):
            p1 = row["p1"]
            assert p1["A"] == p1["B"], (
                f"{label}: execution {run_index} of {_RUNS}: two consumers of the "
                f"same define disagreed ({p1['A']!r} vs {p1['B']!r})"
            )
            assert sorted([p1["I0"], p1["I1"], p1["I2"]]) == ["c1", "c2", "c3"], (
                f"{label}: execution {run_index}: indexing 0..2 of a 3-element "
                f"define gave {[p1['I0'], p1['I1'], p1['I2']]}"
            )
            assert row["p2"]["I0"] is None, f"{label}: p2 has no Conditions"


def test_resource_define_first_last_reads_the_same_list():
    """Two positional readers of one resource define cannot disagree."""
    body = (
        'define "Obs": [Condition]\n'
        'define "A": First("Obs").id\n'
        'define "B": First("Obs").id\n'
        'define "I0": First("Obs").id\n'
        'define "I1": First("Obs").id\n'
        'define "I2": First("Obs").id\n'
    )
    for label, sql, rows in _run(body, _COLUMNS_FIVE):
        assert len(_shared_cte_names(sql)) == 1, (
            f"{label}: First over a resource define must read the shared list"
        )
        for run_index, row in enumerate(rows):
            p1 = row["p1"]
            values = {p1["A"], p1["B"], p1["I0"], p1["I1"], p1["I2"]}
            assert len(values) == 1, (
                f"{label}: execution {run_index} of {_RUNS}: First returned "
                f"{sorted(v for v in values if v)} from the same define"
            )
            assert next(iter(values)) in {"c1", "c2", "c3"}, f"{label}: {p1}"


def test_aggregate_and_list_consumers_share_one_materialization():
    """The AGGREGATE path and the list-operator path are the same evaluation.

    `Count("Ids")` and `First("Ids")` used to build two separate aggregates over
    the same element-rows define (CMS117 measures 4 aggregates for 2 defines).
    """
    body = (
        'define "Ids": ([Condition] C return C.id) X\n'
        'define "A": First("Ids")\n'
        'define "B": First("Ids")\n'
        'define "I0": First("Ids")\n'
        'define "I1": First("Ids")\n'
        'define "I2": First("Ids")\n'
        'define "Counted": Count("Ids")\n'
    )
    for label, sql, rows in _run(body, {**_COLUMNS_FIVE, "Counted": "Counted"}):
        assert sql.count("list(_lst_src.value)") == 1, (
            f"{label}: the element-rows define's list aggregate appears "
            f"{sql.count('list(_lst_src.value)')} times; the aggregate path and "
            "the list-operator path must share ONE evaluation"
        )
        assert len(_shared_cte_names(sql)) == 1, f"{label}: {_shared_cte_names(sql)}"
        for run_index, row in enumerate(rows):
            p1 = row["p1"]
            assert p1["Counted"] == 3, f"{label}: p1 Count = {p1['Counted']!r}"
            values = {p1["A"], p1["B"], p1["I0"], p1["I1"], p1["I2"]}
            assert len(values) == 1, (
                f"{label}: execution {run_index} of {_RUNS}: First consumers "
                f"disagreed: {sorted(v for v in values if v)}"
            )
            assert row["p2"]["Counted"] == 0, f"{label}: p2 Count = {row['p2']['Counted']!r}"


def test_row_scoped_consumers_keep_their_inline_aggregate():
    """A ROW-scoped operand is NOT hoisted — it could not bind under `_patients`.

    `_share_define_list` reuses FHIR4-72's hoistability rule: every free alias
    root must be `_pt`. An aggregate written INSIDE a query is correlated to the
    query's own alias (`Count("Ids")` inside `([Condition] C return …)` becomes
    `… WHERE _lst_src.patient_id = C.patient_id`), so hoisting it into a
    `FROM "_patients"` value CTE would reference an alias that does not exist
    there. The row-scoped aggregate therefore keeps its inline evaluation while
    a patient-scoped consumer of the SAME define in the same library still gets
    the shared CTE — both behaviours are pinned here so neither can drift.
    """
    body = (
        'define "Ids": ([Condition] C return C.id) X\n'
        'define "Counted": Count("Ids")\n'
        'define "Nested": (([Condition] C return Count("Ids")) D) E\n'
    )
    for label, sql, _rows in _run(body, {"Counted": "Counted", "Nested": "Nested"}):
        assert len(_shared_cte_names(sql)) == 1, (
            f"{label}: the patient-scoped Count must read the shared define list: "
            f"{_shared_cte_names(sql)}"
        )
        # One aggregate in the shared CTE, one inline row-scoped aggregate.
        assert sql.count("list(_lst_src.value)") == 2, (
            f"{label}: expected exactly one shared + one row-scoped aggregate, "
            f"got {sql.count('list(_lst_src.value)')}"
        )
        assert "= C.patient_id" in sql, (
            f"{label}: the row-scoped aggregate lost its query-alias correlation"
        )


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
