"""Domain 4 SKEPTIC (v0.0.26 iteration 12) regression coverage.

QA-D4S-001 (LOUD BinderException, surface created by the QA-D3E-001
star-coercion guard in this same dev delta; silently wrong before the
delta): a count-over-union whose leaves are PLAIN retrieve-with-where
queries — the canonical eCQM ``Count(([A: "VS"] P where ... union
[B: "VS"] P where ...)) >= 2`` numerator shape — lowers each leaf to
``SELECT * FROM <retrieve CTE> AS P``. The retrieve CTE is not in
``definition_meta`` (it is a placeholder, not a define), so the
QA-D3E-001 star rewrite skipped it; the rows-to-list coercion then
no-oped on the star (never alias a star) and the whole union fell
through to the generic path, failing with
``Binder Error: Subquery returns 2 columns - expected 1``.

Fix: the leaf loop rewrites the star to the qualified ``resource``
column when the leaf's FROM is the retrieve itself (RetrievePlaceholder)
or the leaf's AST source is a Retrieve — retrieve CTEs always project
``(patient_id, resource)``.

Probe battery (attribution ordering, MP boundary threading, valueset
empty/unloaded distinction, multi-filter retrieves, with/such-that
correlation, parameter-override cache): all CLEAN — pinned by the
existing suites (``test_evaluator`` population-order tests, DQM gates).
"""

from __future__ import annotations

import duckdb

from fhir4ds.cql.loader.fhir_loader import FHIRDataLoader
from fhir4ds.cql.duckdb.extension import register
from fhir4ds.cql.parser import parse_cql
from fhir4ds.cql.translator.translator import CQLToSQLTranslator

_P1 = {"resourceType": "Patient", "id": "p1"}
_P2 = {"resourceType": "Patient", "id": "p2"}
_PROC_A = {
    "resourceType": "Procedure", "id": "pa", "status": "completed",
    "subject": {"reference": "Patient/p1"},
    "code": {"coding": [{"system": "http://snomed.info/sct", "code": "a"}]},
}
_PROC_B = {
    "resourceType": "Procedure", "id": "pb", "status": "completed",
    "subject": {"reference": "Patient/p1"},
    "code": {"coding": [{"system": "http://snomed.info/sct", "code": "b"}]},
}
_PROC_C = {  # not completed -> excluded by the where clause
    "resourceType": "Procedure", "id": "pc", "status": "preparation",
    "subject": {"reference": "Patient/p1"},
    "code": {"coding": [{"system": "http://snomed.info/sct", "code": "a"}]},
}
_OBS_P2 = {
    "resourceType": "Observation", "id": "o2", "status": "final",
    "subject": {"reference": "Patient/p2"},
    "code": {"coding": [{"system": "http://loinc.org", "code": "8867-4"}]},
}
_RESOURCES = [_P1, _P2, _PROC_A, _PROC_B, _PROC_C, _OBS_P2]

_CQL = """library D4SkepticCountUnion version '1.0.0'
using FHIR version '4.0.1'
context Patient
define ProcCount: Count(
  ([Procedure] P where P.status = 'completed')
  union
  ([Observation] O where O.status = 'final')
)
define TwoPlus: "ProcCount" >= 2
define SingleLeaf: Count([Procedure] P where P.status = 'completed')
"""

_SQL = CQLToSQLTranslator().translate_library_to_population_sql(
    parse_cql(_CQL),
    output_columns={
        "proc_count": "ProcCount",
        "two_plus": "TwoPlus",
        "single_leaf": "SingleLeaf",
    },
)


def _con_connections():
    native = duckdb.connect(config={"allow_unsigned_extensions": True})
    register(native)
    py = duckdb.connect()
    ver = duckdb.__version__
    duckdb.__version__ = "0.0.0-forced-python-fallback"
    register(py)
    duckdb.__version__ = ver
    for con in (native, py):
        FHIRDataLoader(con).load_resources(_RESOURCES)
    return native, py


def test_count_union_retrieve_leaves_execute_and_count_elements_d4_skeptic():
    """QA-D4S-001: retrieve-with-where union leaves must lower through the
    count-unnest machinery (per-patient element lists), not fail with a
    ``Subquery returns 2 columns`` binder error. p1 = procedures a+b
    (pc is filtered out) = 2; p2 = observation o2 = 1."""
    native, py = _con_connections()
    try:
        rn = native.execute(_SQL).fetchall()
        rp = py.execute(_SQL).fetchall()
    finally:
        native.close()
        py.close()
    by_patient = {row[0]: row for row in rn}
    assert sorted(by_patient) == ["p1", "p2"]
    assert by_patient["p1"][1] == 2, by_patient
    assert by_patient["p2"][1] == 1, by_patient
    assert by_patient["p1"][3] == 2, by_patient  # SingleLeaf: pa + pb
    assert by_patient["p2"][3] == 0, by_patient
    # dual-engine parity
    assert sorted(rn) == sorted(rp)


def test_count_union_retrieve_leaf_sql_aliases_resource_column_d4_skeptic():
    """The leaf projection must reference the retrieve's resource column —
    never a bare star over a retrieve CTE (QA-D3E-001 doctrine)."""
    assert "SELECT * AS __cql_list_value" not in _SQL
    assert "P.resource" in _SQL and "O.resource" in _SQL
