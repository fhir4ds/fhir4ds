"""Regression tests for the CMS 2025 campaign review fixes
(muse-spark-1.3 independent review).

Covers the review's process HIGH finding: the Min/Max/Count-over-union
lowerings (commits b950370/4612f07/4ab7364) and the singular-query
typing change (6e1e951) landed with no committed tests — validation
rested entirely on the QI-Core conformance gate.

Pinned behaviors:

1. Min/Max over a union of two resource defines lowers to a correlated
   aggregate over the rows union (not LEAST of a 2-column union in
   column position) and executes with per-patient correlation.
2. Count over a union of retrieves counts the patient's rows (deduped
   union, non-null elements only).
3. Count over a union of QUERIES (with-clause + `return all X`) lowers
   through the per-leaf element-list machinery and executes.
4. The us-cql-ig singular-query rule does NOT fire for Any-typed
   (dynamic FHIR property) sources — their query returns stay List<>.
5. Min over a union of scalar value defines executes (value-column
   operands, not just resource columns).
"""

from __future__ import annotations

import duckdb

from ...parser import parse_cql
from ...translator import CQLToSQLTranslator
from fhir4ds.cql import FHIRDataLoader
from fhir4ds.cql.duckdb import register


_PAT = {"resourceType": "Patient", "id": "p1", "birthDate": "1990-01-01"}
_ENC = {
    "resourceType": "Encounter", "id": "e1", "status": "finished",
    "subject": {"reference": "Patient/p1"},
    "period": {"start": "2024-03-01T10:00:00", "end": "2024-03-02T10:00:00"},
}
_ENC2 = {
    "resourceType": "Encounter", "id": "e2", "status": "finished",
    "subject": {"reference": "Patient/p1"},
    "period": {"start": "2024-04-01T10:00:00", "end": "2024-04-02T10:00:00"},
}
_PROC = {
    "resourceType": "Procedure", "id": "pr1", "status": "completed",
    "subject": {"reference": "Patient/p1"},
    "performedPeriod": {"start": "2024-03-05T12:00:00", "end": "2024-03-05T13:00:00"},
}
_PROC2 = {
    "resourceType": "Procedure", "id": "pr2", "status": "completed",
    "subject": {"reference": "Patient/p1"},
    "performedPeriod": {"start": "2024-03-20T12:00:00", "end": "2024-03-20T13:00:00"},
}

_CQL_TEMPLATE = """
library T version '1'
using FHIR version '4.0.1'
context Patient

define "Encs":
  [Encounter] E where E.status = 'finished'
define "Procs":
  [Procedure] P where P.status = 'completed'

{extra}
"""


def _connect():
    con = duckdb.connect(config={"allow_unsigned_extensions": True})
    register(con)
    loader = FHIRDataLoader(con)
    for r in (_PAT, _ENC, _ENC2, _PROC, _PROC2):
        loader.load_resource(r)
    return con


def _run(cql_body: str, outputs):
    con = _connect()
    try:
        tr = CQLToSQLTranslator(connection=con)
        lib = parse_cql(cql_body)
        sql = tr.translate_library_to_population_sql(
            lib,
            output_columns={name: name for name in outputs},
            parameters={"Measurement Period": ("2024-01-01T00:00:00.000Z", "2024-12-31T23:59:59.999Z")},
        )
        rows = con.execute(sql).fetchall()
        return sql, rows
    finally:
        con.close()


def test_min_over_union_of_defines_executes():
    extra = """
define "Earliest":
  Min("Encs" union "Procs")
"""
    sql, rows = _run(_CQL_TEMPLATE.format(extra=extra), ["Earliest"])
    # Executes (no LEAST-of-union binder error) and produces a value per patient.
    assert rows and rows[0][0] == "p1"
    assert "MIN(" in sql.upper()
    assert "LEAST(((SELECT" not in sql


def test_max_over_union_of_defines_executes():
    extra = """
define "Latest":
  Max("Encs" union "Procs")
"""
    sql, rows = _run(_CQL_TEMPLATE.format(extra=extra), ["Latest"])
    assert rows and rows[0][0] == "p1"
    assert "MAX(" in sql.upper()


def test_count_over_union_of_retrieves_executes():
    extra = """
define "N":
  Count("Encs" union "Procs")
"""
    sql, rows = _run(_CQL_TEMPLATE.format(extra=extra), ["N"])
    assert rows and rows[0][0] == "p1"


def test_count_over_union_of_queries_executes():
    """CMS137 shape: union leaves are QUERIES (with-clause + return all X)."""
    extra = """
define "HasTwo":
  Count(("Encs" E with "Procs" P
      such that start of P.performed during Interval[start of E.period, end of E.period]
      return all E)
    union ("Procs" P2 return all P2)) > 0
"""
    sql, rows = _run(_CQL_TEMPLATE.format(extra=extra), ["HasTwo"])
    assert rows and rows[0][0] == "p1"


def test_min_over_union_of_scalar_value_defines_executes():
    """Scalar value defines (not resource rows) as union operands."""
    extra = """
define "D1":
  First("Encs" E sort by start of E.period return start of E.period)
define "D2":
  First("Procs" P sort by start of P.performed return start of P.performed)
define "EarliestDate":
  Min("D1" union "D2")
"""
    sql, rows = _run(_CQL_TEMPLATE.format(extra=extra), ["EarliestDate"])
    assert rows and rows[0][0] == "p1"


def test_singular_query_rule_not_applied_to_any_typed_source():
    """HIGH-3: a query over an Any-typed (dynamic FHIR property) source
    must stay List-typed — the singular rule only fires for KNOWN
    non-list sources."""
    extra = """
define "Names":
  (Patient.name N return N.given)
"""
    con = _connect()
    try:
        tr = CQLToSQLTranslator(connection=con)
        lib = parse_cql(_CQL_TEMPLATE.format(extra=extra))
        tr.translate_library(lib)
        from ...translator.context import DefinitionMeta
        meta = tr.context.definition_meta.get("Names")
        cql_type = str(getattr(meta, "cql_type", "") or "")
        # Any-typed sources keep the DYNAMIC classification ("Any" — the
        # pre-campaign conservative behavior) rather than being claimed as
        # a singular known type (String/Boolean/etc.), which would let
        # `and`/`or` consume the query as a scalar (review HIGH-3).
        assert cql_type in ("", "Any") or cql_type.startswith("List<"), (
            f"Any-typed source query must not be claimed as a singular "
            f"known type, got {cql_type!r}"
        )
    finally:
        con.close()


def test_singular_query_rule_applies_to_known_singular_source():
    """Positive control: Last(...) sources keep the singular rule."""
    extra = """
define "LastEnc":
  (Last("Encs" E sort by start of E.period) LE return start of LE.period)
"""
    con = _connect()
    try:
        tr = CQLToSQLTranslator(connection=con)
        lib = parse_cql(_CQL_TEMPLATE.format(extra=extra))
        tr.translate_library(lib)
        meta = tr.context.definition_meta.get("LastEnc")
        cql_type = str(getattr(meta, "cql_type", "") or "")
        assert not cql_type.startswith("List<"), (
            f"Known-singular source query should be singular, got {cql_type!r}"
        )
    finally:
        con.close()
