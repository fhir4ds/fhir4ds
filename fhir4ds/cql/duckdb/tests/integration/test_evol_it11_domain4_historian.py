"""Regression tests for iteration 11 / Domain 4 (eCQM patterns) HISTORIAN.

QA-018: chained `with` clauses where a later `such that` references an
EARLIER with alias (CMS71-style multi-with eCQM queries) raised
BinderException "Referenced table E1 not found" — each with-clause's
alias registration was popped before later clauses translated, and the
later EXISTS could not bind the earlier alias in any scope.
"""

import duckdb
import pytest

from fhir4ds.cql import FHIRDataLoader
from fhir4ds.cql.parser import parse_cql
from fhir4ds.cql.translator import CQLToSQLTranslator

LOINC = "http://loinc.org"
SNOMED = "http://snomed.info/sct"

VALUESETS = [
    {"resourceType": "ValueSet", "id": "vs-enc", "url": "http://example.com/ValueSet/Encounter",
     "expansion": {"contains": [{"system": SNOMED, "code": "308335008"}]}},
    {"resourceType": "ValueSet", "id": "vs-hba1c", "url": "http://example.com/ValueSet/HbA1c",
     "expansion": {"contains": [{"system": LOINC, "code": "4548-4"}]}},
    {"resourceType": "ValueSet", "id": "vs-vs", "url": "http://example.com/ValueSet/VitalSigns",
     "expansion": {"contains": [{"system": LOINC, "code": "8867-4"}]}},
]

CQL_TEMPLATE = """library ChainedWith
using FHIR version '4.0.1'
include FHIRHelpers version '4.0.1' called FHIRHelpers

valueset "Office Visits": 'http://example.com/ValueSet/Encounter'
valueset "HbA1c Labs": 'http://example.com/ValueSet/HbA1c'
valueset "Vital Signs": 'http://example.com/ValueSet/VitalSigns'

parameter "Measurement Period" Interval<DateTime> default Interval[@2024-01-01T00:00:00, @2024-12-31T23:59:59.999]

context Patient

define "Qualifying Encounters":
  [Encounter: "Office Visits"] E
    where E.status = 'finished' and E.period during "Measurement Period"

{body}
"""

CHAINED_WITH_BODY = '''define "X":
  exists ({
    [Observation: "HbA1c Labs"] O
      with [Encounter: "Office Visits"] E1
        such that O.effective during E1.period
      with [Observation: "Vital Signs"] V
        such that V.status = 'final' and V.effective during E1.period
    where O.status = 'final'
  })
'''

SINGLE_WITH_BODY = '''define "X":
  exists ({
    [Observation: "HbA1c Labs"] O
      with "Qualifying Encounters" E
        such that O.effective during E.period
    where O.status = 'final'
  })
'''

THREE_WITH_BODY = '''define "X":
  exists ({
    [Observation: "HbA1c Labs"] O
      with [Encounter: "Office Visits"] E1
        such that O.effective during E1.period
      with [Observation: "Vital Signs"] V
        such that V.effective during E1.period
      with [Encounter: "Office Visits"] E2
        such that start of V.effective during day of E2.period
    where O.status = 'final'
  })
'''


def _enc(eid, pid, start, end):
    return {
        "resourceType": "Encounter", "id": eid, "status": "finished",
        "subject": {"reference": f"Patient/{pid}"},
        "type": [{"coding": [{"system": SNOMED, "code": "308335008"}]}],
        "period": {"start": start, "end": end},
    }


def _obs(oid, pid, code, eff, status="final"):
    return {
        "resourceType": "Observation", "id": oid, "status": status,
        "subject": {"reference": f"Patient/{pid}"},
        "code": {"coding": [{"system": LOINC, "code": code}]},
        "effectiveDateTime": eff,
        "valueQuantity": {"value": 10.0, "unit": "g/dL", "system": "http://unitsofmeasure.org", "code": "g/dL"},
    }


def _conn():
    con = duckdb.connect(":memory:")
    from fhir4ds.fhirpath.duckdb import register_fhirpath
    register_fhirpath(con)
    from fhir4ds.cql.duckdb import register
    register(con, include_fhirpath=False)
    loader = FHIRDataLoader(con)
    loader.load_valuesets(VALUESETS)
    loader.load_resource({"resourceType": "Patient", "id": "p1", "gender": "female", "birthDate": "1980-01-01"})
    loader.load_resource({"resourceType": "Patient", "id": "p2", "gender": "female", "birthDate": "1980-01-01"})
    # p1: encounter + HbA1c + vital sign inside encounter window
    loader.load_resource(_enc("e1", "p1", "2024-06-15T08:00:00", "2024-06-16T09:00:00"))
    loader.load_resource(_obs("o1", "p1", "4548-4", "2024-06-15T08:30:00"))
    loader.load_resource(_obs("v1", "p1", "8867-4", "2024-06-15T08:45:00"))
    # p2: encounter + HbA1c but NO vital sign
    loader.load_resource(_enc("e2", "p2", "2024-06-15T08:00:00", "2024-06-16T09:00:00"))
    loader.load_resource(_obs("o2", "p2", "4548-4", "2024-06-15T08:30:00"))
    return con


def _values(con, body):
    cql = CQL_TEMPLATE.format(body=body)
    lib = parse_cql(cql)
    translator = CQLToSQLTranslator(lib)
    from pathlib import Path
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


class TestChainedWithClauses:
    """QA-018: later such_that referencing earlier with alias."""

    def test_chained_with_references_first_alias(self, conn):
        values = _values(conn, CHAINED_WITH_BODY)
        assert values["p1"]["X"] is True   # vital sign inside encounter window
        assert values["p2"]["X"] is False  # no vital sign

    def test_single_with_still_works(self, conn):
        values = _values(conn, SINGLE_WITH_BODY)
        assert values["p1"]["X"] is True
        assert values["p2"]["X"] is True

    def test_three_with_chain(self, conn):
        values = _values(conn, THREE_WITH_BODY)
        assert values["p1"]["X"] is True
        assert values["p2"]["X"] is False

    def test_sql_shape_nested_exists(self, conn):
        """Clause 2's EXISTS must be nested inside clause 1's EXISTS (the
        earlier alias is bound by clause 1's FROM)."""
        cql = CQL_TEMPLATE.format(body=CHAINED_WITH_BODY)
        lib = parse_cql(cql)
        translator = CQLToSQLTranslator(lib)
        from pathlib import Path
        bundled = Path(__file__).resolve().parents[4] / "cql" / "resources" / "cql"

        def loader(name):
            p = bundled / f"{name}.cql"
            return parse_cql(p.read_text()) if p.exists() else None

        translator.set_library_loader(loader)
        sql = translator.translate_library_to_population_sql(lib)
        i = sql.find('"X" AS (')
        seg = sql[i:i + 4000]
        e1_pos = seg.find("FROM \"Encounter: Office Visits\" AS E1")
        v_pos = seg.find("FROM \"Observation: Vital Signs\" AS V")
        assert e1_pos != -1 and v_pos != -1
        # V's EXISTS is nested inside E1's EXISTS: V appears after E1's FROM
        assert v_pos > e1_pos
        # and the correlation links V to E1
        assert "V.patient_id = E1.patient_id" in seg
