"""Regression tests for iteration 25 / Domain 9 SKEPTIC.

QA-020: audit-mode `contains` over dynamic multi-valued FHIR properties
emitted `list_contains(VARCHAR, ...)` binder errors. The audit fast
path in `_list_contains_call` skipped the CQL-18 fhirpath_text ->
full-list promotion.
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
    {"resourceType": "ValueSet", "id": "vs", "url": "http://example.com/VS",
     "expansion": {"contains": [{"system": SNOMED, "code": "x"}]}}
]

CQL = """library A
using FHIR version '4.0.1'
valueset "VS": 'http://example.com/VS'
context Patient
define "E": exists ({ [Condition: "VS"] C where C.clinicalStatus.coding.code contains 'active' })
"""


def _conn():
    con = duckdb.connect(":memory:")
    from fhir4ds.fhirpath.duckdb import register_fhirpath
    register_fhirpath(con)
    from fhir4ds.cql.duckdb import register
    register(con, include_fhirpath=False)
    loader = FHIRDataLoader(con)
    loader.load_valuesets(VALUESETS)
    loader.load_resource({"resourceType": "Patient", "id": "p1"})
    loader.load_resource({"resourceType": "Condition", "id": "c1",
                          "subject": {"reference": "Patient/p1"},
                          "code": {"coding": [{"system": SNOMED, "code": "x"}]},
                          "clinicalStatus": {"coding": [{"code": "active"}]}})
    return con


def _translate(audit_mode: str) -> str:
    lib = parse_cql(CQL)
    translator = CQLToSQLTranslator(lib, audit_mode=(audit_mode == "full"))
    bundled = Path(__file__).resolve().parents[4] / "cql" / "resources" / "cql"

    def loader(name):
        p = bundled / f"{name}.cql"
        return parse_cql(p.read_text()) if p.exists() else None

    translator.set_library_loader(loader)
    return translator.translate_library_to_population_sql(lib)


@pytest.fixture(scope="module")
def conn():
    con = _conn()
    yield con
    con.close()


class TestAuditContainsPromotion:
    def test_audit_mode_contains_executes(self, conn):
        sql = _translate("full")
        cur = conn.execute(sql)
        cols = [d[0] for d in cur.description]
        row = cur.fetchone()
        values = dict(zip(cols, row))
        e = values.get("E")
        # E is True (active condition exists); audit cell may be dict or bool
        if isinstance(e, dict):
            assert e.get("result") is True
        else:
            assert bool(e) is True

    def test_noaudit_mode_still_works(self, conn):
        sql = _translate("none")
        row = conn.execute(sql).fetchone()
        values = dict(zip([d[0] for d in conn.execute(sql).description], row))
        e = values.get("E")
        if isinstance(e, dict):
            assert e.get("result") is True
        else:
            assert bool(e) is True

    def test_audit_sql_uses_list_form(self):
        sql = _translate("full")
        assert "list_contains(from_json(fhirpath(" in sql.replace(" ", " ").replace(
            "list_contains( from_json( fhirpath(", "list_contains(from_json(fhirpath("
        ) or "list_contains(from_json(fhirpath(" in sql
        assert "list_contains(fhirpath_text(" not in sql
