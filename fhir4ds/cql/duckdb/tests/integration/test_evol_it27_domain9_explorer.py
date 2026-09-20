"""Regression tests for iteration 27 / Domain 9 EXPLORER (QA-021).

audit_mode='full' measures using `Count(<rows-define alias>) >= N`
(e.g. DenomExcl: Count("Encs") >= 5 — a real eCQM pattern) raised
"More than one row returned by a subquery": (1) the evidence-JOIN fan
out was only aggregated for bare SQLAuditStruct expressions —
comparison-wrapped audit expressions (COALESCE(__pre ...)) fell
through; (2) the synthesized audit-target twin subquery returned one
row per matching resource.
"""

import json
from pathlib import Path

import duckdb
import pytest

from fhir4ds.cql import FHIRDataLoader
from fhir4ds.cql.parser import parse_cql
from fhir4ds.cql.translator import CQLToSQLTranslator

SNOMED = "http://snomed.info/sct"
VALUESETS = [
    {"resourceType": "ValueSet", "id": "vs-enc", "url": "http://example.com/VS/Enc",
     "expansion": {"contains": [{"system": SNOMED, "code": "308335008"}]}}
]

CQL = """library X
using FHIR version '4.0.1'
include FHIRHelpers version '4.0.1' called FHIRHelpers
valueset "Enc": 'http://example.com/VS/Enc'
context Patient
define "Encs": [Encounter: "Enc"] E where E.status = 'finished'
define "Many": Count("Encs") >= 2
"""


def _conn():
    con = duckdb.connect(":memory:")
    from fhir4ds.fhirpath.duckdb import register_fhirpath
    register_fhirpath(con)
    from fhir4ds.cql.duckdb import register
    register(con, include_fhirpath=False)
    loader = FHIRDataLoader(con)
    loader.load_valuesets(VALUESETS)
    loader.load_resource({"resourceType": "Patient", "id": "x1"})
    loader.load_resource({"resourceType": "Patient", "id": "x2"})
    for eid in ("e1", "e2"):
        loader.load_resource({
            "resourceType": "Encounter", "id": eid, "status": "finished",
            "subject": {"reference": "Patient/x1"},
            "type": [{"coding": [{"system": SNOMED, "code": "308335008"}]}],
            "period": {"start": "2024-06-15T08:00:00", "end": "2024-06-15T09:00:00"}})
    loader.load_resource({
        "resourceType": "Encounter", "id": "e3", "status": "finished",
        "subject": {"reference": "Patient/x2"},
        "type": [{"coding": [{"system": SNOMED, "code": "308335008"}]}],
        "period": {"start": "2024-06-15T08:00:00", "end": "2024-06-15T09:00:00"}})
    return con


def _values(con, audit_mode):
    lib = parse_cql(CQL)
    translator = CQLToSQLTranslator(lib, audit_mode=audit_mode)
    bundled = Path(__file__).resolve().parents[4] / "cql" / "resources" / "cql"

    def loader(name):
        p = bundled / f"{name}.cql"
        return parse_cql(p.read_text()) if p.exists() else None

    translator.set_library_loader(loader)
    sql = translator.translate_library_to_population_sql(lib)
    cur = con.execute(sql)
    cols = [d[0] for d in cur.description]
    out = {}
    for row in cur.fetchall():
        out[row[0]] = dict(zip(cols, row))
    return out


@pytest.fixture(scope="module")
def conn():
    con = _conn()
    yield con
    con.close()


class TestAuditCountComparison:
    """QA-021: Count(alias) >= N under audit_mode='full'."""

    def test_audit_full_count_comparison_executes(self, conn):
        values = _values(conn, True)
        many_x1 = values["x1"]["Many"]
        many_x2 = values["x2"]["Many"]
        if isinstance(many_x1, dict):
            assert many_x1.get("result") is True   # x1 has 2 encounters
            assert many_x2.get("result") is False  # x2 has 1
        else:
            assert bool(many_x1) is True
            assert bool(many_x2) is False

    def test_audit_evidence_names_all_winners(self, conn):
        values = _values(conn, True)
        many = values["x1"]["Many"]
        evidence = many.get("evidence", []) if isinstance(many, dict) else []
        targets = {e.get("target", "") for e in evidence}
        joined = ",".join(sorted(targets))
        assert "Encounter/e1" in joined and "Encounter/e2" in joined

    def test_noaudit_unchanged(self, conn):
        values = _values(conn, False)
        assert bool(values["x1"]["Many"]) is True
        assert bool(values["x2"]["Many"]) is False
