"""Regression tests for iteration 12 / Domain 4 (eCQM patterns) EXPLORER.

QA-019: `{ <query> }` list-selector used as a QUERY SOURCE (with alias)
produced a broken derived table (self-referential patient correlation,
unresolvable `_cql_list_source`). Iteration 12 fix: the coerced LIST
subquery is UNNESTed like an array source with the alias binding and a
projected patient_id.

Known remaining gaps (documented NOT A BUG / deferred, no real eCQM
usage): `({a}) union ({b})` braced-query unions, post-union aliases
with sort (`(... union ...) U return ... sort by`), braced alias
re-referenced inside braces, and the bare `({1,2,3}) Z return 1`
literal-source return-only form (pre-existing row-shape family,
CQL-05 QA-107).
"""

import json

import duckdb
import pytest

from fhir4ds.cql import FHIRDataLoader
from fhir4ds.cql.parser import parse_cql
from fhir4ds.cql.translator import CQLToSQLTranslator

LOINC = "http://loinc.org"

VALUESETS = [
    {"resourceType": "ValueSet", "id": "vs-hba1c", "url": "http://example.com/ValueSet/HbA1c",
     "expansion": {"contains": [{"system": LOINC, "code": "4548-4"}]}},
]

CQL_TEMPLATE = """library BracedSource
using FHIR version '4.0.1'
include FHIRHelpers version '4.0.1' called FHIRHelpers

valueset "HbA1c Labs": 'http://example.com/ValueSet/HbA1c'

context Patient

{body}
"""

COUNT_OVER_BRACED_SOURCE = '''define "X":
  Count(({ [Observation: "HbA1c Labs"] O where O.status = 'final' return O.id }) Z return Z)
'''

BRACED_SOURCE_WITH_FILTER = '''define "X":
  Count(({ [Observation: "HbA1c Labs"] O return O.status }) Z where Z = 'final')
'''



def _obs(oid, pid, status="final"):
    return {
        "resourceType": "Observation", "id": oid, "status": status,
        "subject": {"reference": f"Patient/{pid}"},
        "code": {"coding": [{"system": LOINC, "code": "4548-4"}]},
        "effectiveDateTime": "2024-06-15T09:00:00",
        "valueQuantity": {"value": 10.0, "unit": "g/dL", "system": "http://unitsofmeasure.org", "code": "g/dL"},
    }


@pytest.fixture(scope="module")
def conn():
    con = duckdb.connect(":memory:")
    from fhir4ds.fhirpath.duckdb import register_fhirpath
    register_fhirpath(con)
    from fhir4ds.cql.duckdb import register
    register(con, include_fhirpath=False)
    loader = FHIRDataLoader(con)
    loader.load_valuesets(VALUESETS)
    loader.load_resource({"resourceType": "Patient", "id": "p1", "gender": "female", "birthDate": "1980-01-01"})
    loader.load_resource({"resourceType": "Patient", "id": "p2", "gender": "female", "birthDate": "1980-01-01"})
    loader.load_resource(_obs("o1", "p1"))
    loader.load_resource(_obs("o2", "p1", status="preliminary"))
    loader.load_resource(_obs("o3", "p2"))
    yield con
    con.close()


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


class TestBracedQueryAsQuerySource:
    """QA-019: `({ <query> }) Alias <clauses>` executes and iterates elements."""

    def test_count_over_braced_source_return(self, conn):
        values = _values(conn, COUNT_OVER_BRACED_SOURCE)
        assert values["p1"]["X"] == 1   # only the 'final' observation passes the inner where
        assert values["p2"]["X"] == 1

    def test_braced_source_where_filter(self, conn):
        values = _values(conn, BRACED_SOURCE_WITH_FILTER)
        assert values["p1"]["X"] == 1   # only 'final' status passes the filter
        assert values["p2"]["X"] == 1
