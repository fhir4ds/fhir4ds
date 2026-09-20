"""Regression tests for iteration 10 / Domain 4 (eCQM patterns) SKEPTIC.

QA-017: `{ <query> }` list-selector (CQL 1.5 listSelector grammar
`'{' (query | expression)? '}'`) crashed or mis-evaluated in every
consumer position (exists / Count / First / Last / singleton from /
distinct / flatten / indexer / Sum) because the query element was
wrapped in SQLArray as `[(SELECT * FROM ...)]`.

Fix: single-Query list selectors lower to the rows-to-list coercion
(`SELECT COALESCE(list(<value col>), []) ...`) with patient correlation
and resource-valued star-shape projection; `exists ({ query })` unwraps
to the plain query EXISTS form.
"""

import json
from pathlib import Path

import duckdb
import pytest

from fhir4ds.cql import FHIRDataLoader
from fhir4ds.cql.parser import parse_cql
from fhir4ds.cql.translator import CQLToSQLTranslator

SNOMED = "http://snomed.info/sct"
VS_URL = "http://example.com/ValueSet/ESRD"

VS_ESRD = {
    "resourceType": "ValueSet",
    "id": "vs-esrd",
    "url": VS_URL,
    "expansion": {"contains": [{"system": SNOMED, "code": "46177005"}]},
}

CONDITIONS = [
    {
        "resourceType": "Condition",
        "id": "c1",
        "subject": {"reference": "Patient/p1"},
        "code": {"coding": [{"system": SNOMED, "code": "46177005"}]},
        "clinicalStatus": {"coding": [{"system": "http://terminology.hl7.org/CodeSystem/condition-clinical", "code": "active"}]},
    },
    {
        "resourceType": "Condition",
        "id": "c2",
        "subject": {"reference": "Patient/p1"},
        "code": {"coding": [{"system": SNOMED, "code": "46177005"}]},
        "clinicalStatus": {"coding": [{"system": "http://terminology.hl7.org/CodeSystem/condition-clinical", "code": "inactive"}]},
    },
    {
        "resourceType": "Condition",
        "id": "c3",
        "subject": {"reference": "Patient/p2"},
        "code": {"coding": [{"system": SNOMED, "code": "46177005"}]},
        "clinicalStatus": {"coding": [{"system": "http://terminology.hl7.org/CodeSystem/condition-clinical", "code": "active"}]},
    },
]

PATIENTS = [
    {"resourceType": "Patient", "id": "p1", "gender": "female", "birthDate": "1980-06-15"},
    {"resourceType": "Patient", "id": "p2", "gender": "female", "birthDate": "1980-06-15"},
]

CQL_LIB_HEADER = """library TestBracedQuery
using FHIR version '4.0.1'
valueset "ESRD": 'http://example.com/ValueSet/ESRD'
context Patient
"""


def _make_conn():
    con = duckdb.connect(":memory:")
    from fhir4ds.fhirpath.duckdb import register_fhirpath
    register_fhirpath(con)
    from fhir4ds.cql.duckdb import register
    register(con, include_fhirpath=False)
    loader = FHIRDataLoader(con)
    loader.load_valuesets([VS_ESRD])
    for p in PATIENTS:
        loader.load_resource(p)
    for c in CONDITIONS:
        loader.load_resource(c)
    return con


def _translate(cql_text: str) -> str:
    lib = parse_cql(cql_text)
    translator = CQLToSQLTranslator(lib)
    bundled = Path(__file__).resolve().parents[4] / "cql" / "resources" / "cql"

    def loader(name):
        p = bundled / f"{name}.cql"
        return parse_cql(p.read_text()) if p.exists() else None

    translator.set_library_loader(loader)
    return translator.translate_library_to_population_sql(lib)


def _define_values(con, cql_text: str) -> dict:
    sql = _translate(cql_text)
    cur = con.execute(sql)
    cols = [d[0] for d in cur.description]
    out = {}
    for row in cur.fetchall():
        out[row[0]] = dict(zip(cols, row))
    return out


@pytest.fixture(scope="module")
def conn():
    con = _make_conn()
    yield con
    con.close()


class TestBracedQueryListSelector:
    """QA-017: `{ <query> }` list selector executes in every consumer."""

    def test_exists_over_braced_where_query(self, conn):
        values = _define_values(
            conn,
            CQL_LIB_HEADER
            + 'define "X": exists ({ [Condition: "ESRD"] C where C.clinicalStatus.coding.code contains \'active\' })\n',
        )
        assert values["p1"]["X"] is True
        assert values["p2"]["X"] is True

    def test_exists_over_braced_return_query(self, conn):
        values = _define_values(
            conn,
            CQL_LIB_HEADER
            + 'define "X": exists ({ [Condition: "ESRD"] C return C.id })\n',
        )
        assert values["p1"]["X"] is True
        assert values["p2"]["X"] is True

    def test_count_over_braced_query(self, conn):
        values = _define_values(
            conn,
            CQL_LIB_HEADER
            + 'define "X": Count({ [Condition: "ESRD"] C where C.clinicalStatus.coding.code contains \'active\' })\n',
        )
        assert values["p1"]["X"] == 1
        assert values["p2"]["X"] == 1

    def test_count_over_braced_return_query(self, conn):
        values = _define_values(
            conn,
            CQL_LIB_HEADER + 'define "X": Count({ [Condition: "ESRD"] C return C.id })\n',
        )
        assert values["p1"]["X"] == 2
        assert values["p2"]["X"] == 1

    def test_first_last_over_braced_return_query(self, conn):
        values = _define_values(
            conn,
            CQL_LIB_HEADER
            + 'define "F": First({ [Condition: "ESRD"] C return C.id })\n'
            + 'define "L": Last({ [Condition: "ESRD"] C return C.id })\n'
            + 'define "Only": First({ [Condition: "ESRD"] C where C.id = \'c3\' return C.id })\n',
        )
        # p1 has {c1, c2}; p2 has {c3}. Unordered retrieves make which of
        # c1/c2 comes first unspecified, so only assert membership/set facts.
        assert values["p1"]["F"] in {"c1", "c2"}
        assert values["p1"]["L"] in {"c1", "c2"}
        assert values["p1"]["Only"] is None
        assert values["p2"]["F"] == "c3"
        assert values["p2"]["L"] == "c3"

    def test_singleton_from_braced_query(self, conn):
        values = _define_values(
            conn,
            CQL_LIB_HEADER
            + 'define "X": singleton from ({ [Condition: "ESRD"] C where C.id = \'c3\' return C.id })\n',
        )
        assert values["p1"]["X"] is None
        assert values["p2"]["X"] == "c3"

    def test_singleton_from_multi_element_braced_raises(self, conn):
        sql = _translate(
            CQL_LIB_HEADER
            + 'define "X": singleton from ({ [Condition: "ESRD"] C return C.id })\n'
        )
        with pytest.raises(Exception, match="SingletonFrom"):
            conn.execute(sql).fetchall()

    def test_distinct_over_braced_query(self, conn):
        values = _define_values(
            conn,
            CQL_LIB_HEADER
            + 'define "X": distinct ({ [Condition: "ESRD"] C return C.clinicalStatus.coding.code })\n',
        )
        p1 = json.loads(values["p1"]["X"]) if isinstance(values["p1"]["X"], str) else values["p1"]["X"]
        assert sorted(p1) == ["active", "inactive"]

    def test_flatten_over_braced_query(self, conn):
        values = _define_values(
            conn,
            CQL_LIB_HEADER
            + 'define "X": flatten ({ { [Condition: "ESRD"] C return C.id } })\n',
        )
        p1 = json.loads(values["p1"]["X"]) if isinstance(values["p1"]["X"], str) else values["p1"]["X"]
        assert sorted(p1) == ["c1", "c2"]

    def test_indexer_over_braced_query(self, conn):
        values = _define_values(
            conn,
            CQL_LIB_HEADER
            + 'define "X": ({ [Condition: "ESRD"] C return C.id })[0]\n',
        )
        assert values["p1"]["X"] in {"c1", "c2"}
        assert values["p2"]["X"] == "c3"

    def test_sum_over_braced_query(self, conn):
        values = _define_values(
            conn,
            CQL_LIB_HEADER
            + 'define "X": Sum({ [Condition: "ESRD"] C return 1 })\n',
        )
        assert values["p1"]["X"] is not None
        assert float(values["p1"]["X"]) == 2.0
        assert float(values["p2"]["X"]) == 1.0

    def test_patient_isolation_braced_query(self, conn):
        """The braced-query LIST must not leak rows across patients."""
        values = _define_values(
            conn,
            CQL_LIB_HEADER + 'define "X": Count({ [Condition: "ESRD"] C return C.id })\n',
        )
        assert values["p1"]["X"] == 2
        assert values["p2"]["X"] == 1


class TestBracedWhereFormValueColumn:
    """Where-only braced queries must project the resource (elements are
    CQL resources), matching the unbraced query-define path."""

    def test_first_over_braced_where_is_resource_json(self, conn):
        values = _define_values(
            conn,
            CQL_LIB_HEADER
            + 'define "X": First({ [Condition: "ESRD"] C where C.clinicalStatus.coding.code contains \'active\' })\n',
        )
        v = values["p2"]["X"]
        assert isinstance(v, str)
        resource = json.loads(v)
        assert resource["resourceType"] == "Condition"
        assert resource["id"] == "c3"
