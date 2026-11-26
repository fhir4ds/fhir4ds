"""WP-6 — ``sort by`` over resource rows breaks ties by the resource id.

CQL 1.5 ``sort by`` sorts "by the sort expression" and says nothing about rows
whose sort expression is equal, so DuckDB's query plan decides their order. The
SAME translated SQL returned two MedicationRequests of CMS136 (US-Core 2025)
that share an authored date in source order on desktop and in the other order
on duckdb-wasm; an order-dependent ``aggregate`` then built different
medication intervals in the browser than on desktop.

The translator already breaks such ties for First/Last over a sorted query
(``_lists.py``, ``json_extract_string(<alias>.resource, '$.id')``). This file
pins that a row-producing ``sort by`` over resource rows gets the same key:

- the sort expression, then the resource id, then the resource text (so the
  rule is total even when two rows share an id);
- never together with ``DISTINCT`` (DuckDB rejects an ORDER BY on a column that
  is not projected) and never for a literal-list source (``list_sort``).
"""

from __future__ import annotations

import json
from contextlib import contextmanager

import duckdb
import pytest

from .wasm_runtime_helpers import no_python_connection

_TIE_BREAK = (
    "json_extract_string(M.resource, '$.id') ASC NULLS LAST, "
    "CAST(M.resource AS VARCHAR) ASC NULLS LAST"
)

_CQL = """
library TieBreak version '1.0'
using FHIR version '4.0.1'
context Patient
define "Meds": [MedicationRequest] M sort by M.authoredOn
define "Ids": "Meds" M return M.id
define "FirstId": First("Meds").id
define "LastId": Last("Meds").id
"""

_CQL_VIA_DEFINE = """
library TieBreakViaDefine version '1.0'
using FHIR version '4.0.1'
context Patient
define "All": [MedicationRequest]
define "Meds": "All" M sort by M.authoredOn
"""

_CQL_DISTINCT = """
library TieBreakDistinct version '1.0'
using FHIR version '4.0.1'
context Patient
define "Statuses": [MedicationRequest] M
  sort by M.authoredOn return distinct M.status
"""

_CQL_LIST_SOURCE = """
library TieBreakList version '1.0'
using FHIR version '4.0.1'
context Patient
define "Sorted": {3, 1, 2} C sort by C
"""

#: Three requests share one authored date. Their ids are in NO order relative to
#: the insertion order, so source order and id order disagree: an engine that
#: keeps insertion order among ties answers ``m-c, m-b, m-a``.
_SAME_DAY_IDS = ("m-c", "m-b", "m-a")
_AUTHORED_ON = "2026-01-02"


def _request(request_id: str, patient_id: str) -> dict:
    return {
        "resourceType": "MedicationRequest",
        "id": request_id,
        "status": "active",
        "intent": "order",
        "medicationCodeableConcept": {"text": "atomoxetine"},
        "subject": {"reference": f"Patient/{patient_id}"},
        "authoredOn": _AUTHORED_ON,
    }


def _patient(patient_id: str) -> dict:
    return {"resourceType": "Patient", "id": patient_id}


def _translate(cql_text: str, con, columns: dict[str, str]) -> str:
    from fhir4ds.cql.parser import parse_cql
    from fhir4ds.cql.translator.translator import CQLToSQLTranslator

    library = parse_cql(cql_text)
    translator = CQLToSQLTranslator(connection=con, library_loader=lambda *a: None)
    translator.translate_library(library)
    return translator.translate_library_to_population_sql(
        library=library, output_columns=columns
    )


def _expression_sql(cql_text: str, name: str) -> str:
    from fhir4ds.cql import translate_cql

    return translate_cql(cql_text)[name].to_sql()


def _load(con, patient_id: str, ids: tuple[str, ...]) -> None:
    con.execute(
        "CREATE OR REPLACE TABLE resources (id VARCHAR, resourceType VARCHAR, "
        "resource JSON, patient_ref VARCHAR)"
    )
    rows = [(_patient(patient_id), patient_id)] + [
        (_request(request_id, patient_id), patient_id) for request_id in ids
    ]
    con.executemany(
        "INSERT INTO resources VALUES (?,?,?::JSON,?)",
        [
            [r["id"], r["resourceType"], json.dumps(r), patient_ref]
            for r, patient_ref in rows
        ],
    )


def _as_list(value) -> list[str]:
    """Population SQL transports a list define as one list per patient."""
    if isinstance(value, list):
        return [str(v) for v in value]
    text = str(value)
    try:
        decoded = json.loads(text)
    except ValueError:
        decoded = None
    if isinstance(decoded, list):
        return [str(v) for v in decoded]
    inner = text.strip()[1:-1] if text.strip().startswith("[") else text
    return [part.strip() for part in inner.split(",") if part.strip()]


@contextmanager
def _python_supplements():
    from fhir4ds.cql.duckdb.extension import _register_python_supplements

    con = duckdb.connect()
    _register_python_supplements(con, cpp_loaded=False, include_fhirpath=True)
    try:
        yield con
    finally:
        con.close()


def _engines():
    """Python-supplement and no-Python engines (both must give one answer)."""
    return ((_python_supplements(), "python"), (no_python_connection(), "no_python"))


def test_sort_by_over_a_retrieve_breaks_ties_by_resource_id():
    sql = _expression_sql(_CQL, "Meds")
    order_by = sql[sql.index("ORDER BY") :].rstrip(")")
    assert order_by.endswith(_TIE_BREAK), order_by
    # The authored-date sort key stays FIRST: ties are broken after it, not instead of it.
    assert order_by.startswith("ORDER BY fhirpath_text(M.resource, 'authoredOn') ASC NULLS LAST"), order_by


def test_sort_by_over_a_resource_define_gets_the_same_tie_break():
    sql = _expression_sql(_CQL_VIA_DEFINE, "Meds")
    assert sql.startswith('(SELECT * FROM "All" AS M ORDER BY '), sql
    assert sql[sql.index("ORDER BY") :].rstrip(")").endswith(_TIE_BREAK), sql


def test_distinct_and_literal_list_sources_get_no_tie_break():
    distinct_sql = _expression_sql(_CQL_DISTINCT, "Statuses")
    assert distinct_sql.startswith("(SELECT DISTINCT"), distinct_sql
    assert "json_extract_string" not in distinct_sql, distinct_sql

    list_sql = _expression_sql(_CQL_LIST_SOURCE, "Sorted")
    assert list_sql == "list_sort([3, 1, 2], 'ASC', 'NULLS LAST')", list_sql


@pytest.mark.parametrize("insertion_order", [_SAME_DAY_IDS, tuple(reversed(_SAME_DAY_IDS))])
def test_tied_rows_come_out_in_id_order_whatever_the_source_order(insertion_order):
    """Three same-day requests, inserted in either order: one answer on both engines.

    ``First``/``Last`` read the sorted list, so they expose its order. Before
    the fix the tie order was the engine's: the sort key is equal for all three
    rows, so ``First`` returned whichever row the engine produced first.
    """
    columns = {"FirstId": "FirstId", "LastId": "LastId"}
    for context_manager, engine in _engines():
        with context_manager as con:
            _load(con, "p1", insertion_order)
            cur = con.execute(_translate(_CQL, con, columns))
            row = cur.fetchone()
            assert row is not None, engine
            result = dict(zip([d[0] for d in cur.description], row, strict=True))
            # The population surface transports these defines as one-item lists.
            assert _as_list(result["FirstId"]) == ["m-a"], (engine, insertion_order, result)
            assert _as_list(result["LastId"]) == ["m-c"], (engine, insertion_order, result)
