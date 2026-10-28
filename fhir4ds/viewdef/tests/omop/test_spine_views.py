"""OMOP S2 (rev 2): the spine event VDs join the flattened conceptmap VIEW.

Vocabulary-discriminated ON pairs: (best-coding <-> cm.concept_code) AND
(derived source URI <-> cm.source_system). Coding precedence (Muse R2),
date/datetime duals, source-value preservation, decoy rejection.
"""

import json
from pathlib import Path

import pytest

import fhir4ds
from fhir4ds.viewdef.parser import parse_view_definition
from fhir4ds.viewdef.generator import SQLGenerator
from fhir4ds.viewdef.omop_runner import OMOP_DIR
from fhir4ds.viewdef.tests.omop.test_conceptmap import _run as _run_cm  # noqa: F401 (reuse)

SCT = "http://snomed.info/sct"
ACTCODE = "http://terminology.hl7.org/CodeSystem/v3-ActCode"
CONDCAT = "http://terminology.hl7.org/CodeSystem/condition-category"
GENDER = "http://hl7.org/fhir/administrative-gender"
ICD10CM = "http://hl7.org/fhir/sid/icd-10-cm"


def _stage_maps(con, mappings):
    groups = {}
    for source, code, target in mappings:
        groups.setdefault(source, []).append(
            {"code": code, "target": [{"code": target, "equivalence": "equivalent"}]})
    cm = {"resourceType": "ConceptMap", "id": "test-maps", "status": "active",
          "group": [{"source": s, "element": els} for s, els in groups.items()]}
    con.execute("INSERT INTO __vd_src VALUES (?)", [json.dumps(cm)])
    vd = parse_view_definition(json.loads((OMOP_DIR / "conceptmap-view.json").read_text()))
    sql = SQLGenerator(source_table="__vd_src").generate(vd)
    con.execute("CREATE SCHEMA IF NOT EXISTS omop")
    con.execute(f'CREATE OR REPLACE VIEW omop."omop_conceptmap" AS\n{sql}')


def _run(con, view_name):
    vd = parse_view_definition(json.loads((OMOP_DIR / f"{view_name}.json").read_text()))
    sql = SQLGenerator(source_table="__vd_src").generate(vd)
    return con.execute(sql).fetchall()


# ---------------------------------------------------------------------------
# Composition helpers: the reshape views only carry source columns now; the
# joins, concept ids and integer keys live in the table's SQLQuery.
# ---------------------------------------------------------------------------
def _library_sql(table):
    import base64
    path = OMOP_DIR / "sqlqueries" / f"{table.replace('_', '-')}-omop.json"
    lib = json.loads(path.read_text())
    return base64.b64decode(lib["content"][0]["data"]).decode()


def _source_view(con, stem, target):
    vd = parse_view_definition(json.loads((OMOP_DIR / f"{stem}.json").read_text()))
    sql = SQLGenerator(source_table="__vd_src").generate(vd)
    con.execute("CREATE SCHEMA IF NOT EXISTS omop")
    con.execute(f'CREATE OR REPLACE VIEW omop."{target}" AS\n{sql}')


DRUG_ARMS = (
    "medication_request", "medication_statement", "medication_administration",
    "medication_dispense", "immunization",
)


def _compose(con, table):
    """Run the table's SQLQuery over its materialized reshape view(s)."""
    if table == "drug_exposure":
        for arm in DRUG_ARMS:
            _source_view(con, f"drug-exposure-{arm.replace('_', '-')}-source-view",
                         f"drug_exposure__{arm}")
    else:
        _source_view(con, f"{table.replace('_', '-')}-source-view", f"{table}_source")
    return con.execute(_library_sql(table)).fetchall()


@pytest.fixture()
def conn():
    con = fhir4ds.create_connection()
    con.execute("CREATE OR REPLACE TABLE __vd_src (resource JSON)")
    return con


class TestPerson:
    def test_reshape_keeps_source_columns(self, conn):
        # The person view is the raw reshape: no join, no concept id. The
        # SQLQuery (sqlqueries/person-omop.json) joins and keys.
        conn.execute("INSERT INTO __vd_src VALUES (?)", [json.dumps(
            {"resourceType": "Patient", "id": "p1", "gender": "male", "birthDate": "1974-12-25"})])
        rows = _run(conn, "person-source-view")
        # No person_id: the integer key belongs to the SQLQuery, and the
        # source id is the only identity the reshape needs to carry.
        assert rows == [("p1", "1974", "12", "25", "1974-12-25", "male")]


class TestVisitOccurrence:
    COLS = ["visit_occurrence_id", "person_id", "visit_concept_id",
            "visit_start_date", "visit_start_datetime", "visit_end_date",
            "visit_end_datetime", "visit_type_concept_id", "visit_source_value"]

    def test_inpatient_class_maps(self, conn):
        conn.execute("INSERT INTO __vd_src VALUES (?)", [json.dumps(
            {"resourceType": "Encounter", "id": "e1", "status": "finished",
             "class": {"system": ACTCODE, "code": "IMP"},
             "subject": {"reference": "Patient/p1"},
             "period": {"start": "2024-03-01T10:00:00Z", "end": "2024-03-05"}})])
        _stage_maps(conn, [(ACTCODE, "IMP", "9201")])
        by = dict(zip(self.COLS, _compose(conn, "visit_occurrence")[0]))
        assert by["visit_concept_id"] == 9201
        assert by["visit_start_date"] == "2024-03-01"
        assert by["visit_start_datetime"] == "2024-03-01T10:00:00Z"
        assert by["visit_type_concept_id"] == 32810
        assert by["visit_source_value"] == "IMP"
        assert isinstance(by["visit_occurrence_id"], int)
        assert isinstance(by["person_id"], int)

    def test_same_code_other_vocabulary_rejected(self, conn):
        conn.execute("INSERT INTO __vd_src VALUES (?)", [json.dumps(
            {"resourceType": "Encounter", "id": "e1", "status": "finished",
             "class": {"system": ACTCODE, "code": "IMP"},
             "subject": {"reference": "Patient/p1"},
             "period": {"start": "2024-03-01", "end": "2024-03-01"}})])
        _stage_maps(conn, [("http://example.org/other", "IMP", "999")])
        by = dict(zip(self.COLS, _compose(conn, "visit_occurrence")[0]))
        # Right code, wrong vocabulary: OMOP "no matching concept".
        assert by["visit_concept_id"] == 0


class TestConditionOccurrence:
    COLS = ["condition_occurrence_id", "person_id", "condition_concept_id",
            "condition_start_date", "condition_start_datetime",
            "condition_end_date", "condition_end_datetime",
            "condition_type_concept_id", "condition_status_concept_id",
            "condition_source_value", "visit_occurrence_id"]
    COND = {"resourceType": "Condition", "id": "c1",
            "code": {"coding": [
                {"system": "http://example.org/local", "code": "L9"},
                {"system": ICD10CM, "code": "I10"},
                {"system": SCT, "code": "38341003"}]},
            "subject": {"reference": "Patient/p1"},
            "encounter": {"reference": "Encounter/e1"},
            "onsetDateTime": "2024-02-10T08:30:00Z",
            "category": [{"coding": [{"system": CONDCAT, "code": "encounter-diagnosis"}]}]}

    def test_coding_precedence_snomed_over_icd10(self, conn):
        conn.execute("INSERT INTO __vd_src VALUES (?)", [json.dumps(self.COND)])
        _stage_maps(conn, [
            (SCT, "38341003", "313217"),
            (CONDCAT, "encounter-diagnosis", "43542353"),
            ("http://example.org/other", "38341003", "999"),  # decoy
        ])
        by = dict(zip(self.COLS, _compose(conn, "condition_occurrence")[0]))
        assert by["condition_concept_id"] == 313217
        assert by["condition_type_concept_id"] == 43542353
        assert by["condition_source_value"] == "38341003"
        assert by["condition_start_datetime"] == "2024-02-10T08:30:00Z"

    def test_icd10_fallback_when_no_snomed(self, conn):
        cond = {**self.COND, "id": "c2",
                "code": {"coding": [{"system": ICD10CM, "code": "I10"}]}}
        cond.pop("category")
        conn.execute("INSERT INTO __vd_src VALUES (?)", [json.dumps(cond)])
        _stage_maps(conn, [(ICD10CM, "I10", "31991")])
        by = dict(zip(self.COLS, _compose(conn, "condition_occurrence")[0]))
        assert by["condition_concept_id"] == 31991
        assert by["condition_source_value"] == "I10"

    def test_local_code_unmapped_keeps_source(self, conn):
        cond = {**self.COND, "id": "c3",
                "code": {"coding": [{"system": "http://example.org/local", "code": "L9"}]}}
        cond.pop("category")
        conn.execute("INSERT INTO __vd_src VALUES (?)", [json.dumps(cond)])
        _stage_maps(conn, [(SCT, "38341003", "313217")])
        by = dict(zip(self.COLS, _compose(conn, "condition_occurrence")[0]))
        assert by["condition_concept_id"] == 0
        assert by["condition_source_value"] == "L9"


class TestProcedureOccurrence:
    COLS = ["procedure_occurrence_id", "person_id", "procedure_concept_id",
            "procedure_date", "procedure_datetime", "procedure_type_concept_id",
            "quantity", "procedure_source_value", "visit_occurrence_id"]

    def test_full_row_and_defaults(self, conn):
        conn.execute("INSERT INTO __vd_src VALUES (?)", [json.dumps(
            {"resourceType": "Procedure", "id": "pr1", "status": "completed",
             "code": {"coding": [{"system": SCT, "code": "76601001"}]},
             "subject": {"reference": "Patient/p1"}, "encounter": {"reference": "Encounter/e1"},
             "performedDateTime": "2024-03-02T14:00:00Z"})])
        _stage_maps(conn, [(SCT, "76601001", "4325083")])
        by = dict(zip(self.COLS, _compose(conn, "procedure_occurrence")[0]))
        assert by["procedure_concept_id"] == 4325083
        assert by["procedure_type_concept_id"] == 32810
        assert by["procedure_date"] == "2024-03-02"
        assert by["quantity"] == 1
        assert by["procedure_source_value"] == "76601001"
