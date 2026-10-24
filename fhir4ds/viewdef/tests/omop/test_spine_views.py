"""OMOP S2: the spine event VDs (person, visit_occurrence,
condition_occurrence, procedure_occurrence).

Joins the element-per-resource ConceptMap rows (S1 canonical join-target
form) with vocabulary-discriminated ON pairs (code + system). Pins the
coding-precedence rule (Muse R2), date/datetime duals, source-value
verbatim preservation, type-concept defaults, and cross-vocabulary decoy
rejection.
"""

import json
from pathlib import Path

import pytest

import fhir4ds
from fhir4ds.viewdef.parser import parse_view_definition
from fhir4ds.viewdef.generator import SQLGenerator

OMOP_DIR = Path(__file__).parents[2] / "resources" / "omop"

SCT = "http://snomed.info/sct"
ACTCODE = "http://terminology.hl7.org/CodeSystem/v3-ActCode"
CONDCAT = "http://terminology.hl7.org/CodeSystem/condition-category"
GENDER = "http://hl7.org/fhir/administrative-gender"


def _cm(cid, source, code, target):
    return {
        "resourceType": "ConceptMap", "id": cid, "status": "active",
        "group": [{"source": source, "element": [
            {"code": code, "target": [{"code": target, "equivalence": "equivalent"}]}]}],
    }


@pytest.fixture()
def conn():
    con = fhir4ds.create_connection()
    con.execute("CREATE OR REPLACE TABLE __vd_src (resource JSON)")
    return con


def _run(con, view_name):
    vd = parse_view_definition(json.loads((OMOP_DIR / f"{view_name}.json").read_text()))
    sql = SQLGenerator(source_table="__vd_src").generate(vd)
    return con.execute(sql).fetchall()


class TestPerson:
    def test_full_row(self, conn):
        for r in [
            {"resourceType": "Patient", "id": "p1", "gender": "male", "birthDate": "1974-12-25"},
            _cm("m1", GENDER, "male", "8507"),
        ]:
            conn.execute("INSERT INTO __vd_src VALUES (?)", [json.dumps(r)])
        rows = _run(conn, "person-view")
        assert rows == [("p1", "8507", "1974", "12", "25", "1974-12-25", "p1", "male")]

    def test_unmapped_gender_null_concept(self, conn):
        conn.execute("INSERT INTO __vd_src VALUES (?)", [json.dumps(
            {"resourceType": "Patient", "id": "p2", "gender": "female", "birthDate": "1985-05-06"})])
        rows = _run(conn, "person-view")
        assert rows[0][1] is None  # LEFT JOIN miss -> NULL (runner coalesces to 0)


class TestVisitOccurrence:
    def test_inpatient_class_maps(self, conn):
        for r in [
            {"resourceType": "Encounter", "id": "e1", "status": "finished",
             "class": {"system": ACTCODE, "code": "IMP"},
             "subject": {"reference": "Patient/p1"},
             "period": {"start": "2024-03-01T10:00:00Z", "end": "2024-03-05"}},
            _cm("m2", ACTCODE, "IMP", "9201"),
        ]:
            conn.execute("INSERT INTO __vd_src VALUES (?)", [json.dumps(r)])
        rows = _run(conn, "visit-occurrence-view")
        assert rows == [("e1", "p1", "9201", "2024-03-01", "2024-03-01T10:00:00Z",
                         "2024-03-05", "2024-03-05", "32810", "IMP")]

    def test_same_code_other_vocabulary_rejected(self, conn):
        for r in [
            {"resourceType": "Encounter", "id": "e1", "status": "finished",
             "class": {"system": ACTCODE, "code": "IMP"},
             "subject": {"reference": "Patient/p1"},
             "period": {"start": "2024-03-01", "end": "2024-03-01"}},
            _cm("decoy", "http://example.org/other", "IMP", "999"),
        ]:
            conn.execute("INSERT INTO __vd_src VALUES (?)", [json.dumps(r)])
        rows = _run(conn, "visit-occurrence-view")
        assert rows[0][2] is None  # decoy must not match


class TestConditionOccurrence:
    def test_coding_precedence_snomed_over_icd10(self, conn):
        for r in [
            {"resourceType": "Condition", "id": "c1",
             "code": {"coding": [
                 {"system": "http://example.org/local", "code": "L9"},
                 {"system": "http://hl7.org/fhir/sid/icd-10-cm", "code": "I10"},
                 {"system": SCT, "code": "38341003"}]},
             "subject": {"reference": "Patient/p1"},
             "encounter": {"reference": "Encounter/e1"},
             "onsetDateTime": "2024-02-10T08:30:00Z",
             "category": [{"coding": [{"system": CONDCAT, "code": "encounter-diagnosis"}]}]},
            _cm("m4", SCT, "38341003", "313217"),
            _cm("m3", CONDCAT, "encounter-diagnosis", "43542353"),
            _cm("decoy", "http://example.org/other", "38341003", "999"),
        ]:
            conn.execute("INSERT INTO __vd_src VALUES (?)", [json.dumps(r)])
        rows = _run(conn, "condition-occurrence-view")
        assert rows == [("c1", "p1", "313217", "2024-02-10", "2024-02-10T08:30:00Z",
                         None, None, "43542353", None, "38341003", "e1")]

    def test_icd10_fallback_when_no_snomed(self, conn):
        for r in [
            {"resourceType": "Condition", "id": "c2",
             "code": {"coding": [{"system": "http://hl7.org/fhir/sid/icd-10-cm", "code": "I10"}]},
             "subject": {"reference": "Patient/p1"}, "onsetDateTime": "2024-01-01"},
            _cm("m", "http://hl7.org/fhir/sid/icd-10-cm", "I10", "31991"),
        ]:
            conn.execute("INSERT INTO __vd_src VALUES (?)", [json.dumps(r)])
        rows = _run(conn, "condition-occurrence-view")
        assert rows[0][2] == "31991" and rows[0][9] == "I10"

    def test_local_code_unmapped_keeps_source(self, conn):
        conn.execute("INSERT INTO __vd_src VALUES (?)", [json.dumps(
            {"resourceType": "Condition", "id": "c3",
             "code": {"coding": [{"system": "http://example.org/local", "code": "L9"}]},
             "subject": {"reference": "Patient/p1"}, "onsetDateTime": "2024-01-01"})])
        rows = _run(conn, "condition-occurrence-view")
        assert rows[0][2] is None and rows[0][9] == "L9"


class TestProcedureOccurrence:
    def test_full_row_and_defaults(self, conn):
        for r in [
            {"resourceType": "Procedure", "id": "pr1", "status": "completed",
             "code": {"coding": [{"system": SCT, "code": "76601001"}]},
             "subject": {"reference": "Patient/p1"}, "encounter": {"reference": "Encounter/e1"},
             "performedDateTime": "2024-03-02T14:00:00Z"},
            _cm("m5", SCT, "76601001", "4325083"),
        ]:
            conn.execute("INSERT INTO __vd_src VALUES (?)", [json.dumps(r)])
        rows = _run(conn, "procedure-occurrence-view")
        assert rows == [("pr1", "p1", "4325083", "2024-03-02", "2024-03-02T14:00:00Z",
                         "32810", 1, "76601001", "e1")]


class TestSpineGrain:
    def test_one_row_per_resource(self, conn):
        for i in range(3):
            conn.execute(
                "INSERT INTO __vd_src VALUES (?)",
                [json.dumps({"resourceType": "Condition", "id": f"c{i}",
                             "code": {"coding": [{"system": SCT, "code": "X"}]},
                             "subject": {"reference": "Patient/p1"},
                             "onsetDateTime": "2024-01-01"})],
            )
        rows = _run(conn, "condition-occurrence-view")
        assert len(rows) == 3
