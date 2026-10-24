"""OMOP S3: unions + split (drug_exposure children, device_exposure,
measurement/observation value-type split, death).

The per-table child VDs feeding the S4 composite union runner. Pins the
value-type split rule (their OmopObservation.java:1380-1440 Quantity-rule
adopted), per-branch drug type concepts (prescription-written 38000177 /
dispensed 38000175 / administered 38000180), RxNorm/CVX concept
resolution, Period fallbacks, death extraction, and per-branch grain.
"""

import json
from pathlib import Path

import pytest

import fhir4ds
from fhir4ds.viewdef.parser import parse_view_definition
from fhir4ds.viewdef.generator import SQLGenerator

OMOP_DIR = Path(__file__).parents[2] / "resources" / "omop"

RXNORM = "http://www.nlm.nih.gov/research/umls/rxnorm"
CVX = "http://hl7.org/fhir/sid/cvx"
LOINC = "http://loinc.org"
SCT = "http://snomed.info/sct"


def _stage_maps(con, mappings):
    """Stage ONE monolithic ConceptMap + materialize the flattened view."""
    groups = {}
    for source, code, target in mappings:
        groups.setdefault(source, []).append(
            {"code": code, "target": [{"code": target, "equivalence": "equivalent"}]})
    cm = {"resourceType": "ConceptMap", "id": "test-maps", "status": "active",
          "group": [{"source": s, "element": els} for s, els in groups.items()]}
    con.execute("INSERT INTO __vd_src VALUES (?)", [json.dumps(cm)])
    from fhir4ds.viewdef.omop_runner import OMOP_DIR
    vd = parse_view_definition(json.loads((OMOP_DIR / "conceptmap-view.json").read_text()))
    sql = SQLGenerator(source_table="__vd_src").generate(vd)
    con.execute("CREATE SCHEMA IF NOT EXISTS omop")
    con.execute(f'CREATE OR REPLACE VIEW omop."omop_conceptmap" AS\n{sql}')


_COLUMNS = [
    "drug_exposure_id", "person_id", "drug_concept_id",
    "drug_exposure_start_date", "drug_exposure_start_datetime",
    "drug_exposure_end_date", "drug_exposure_end_datetime",
    "drug_type_concept_id", "sig", "quantity_num", "days_supply",
    "drug_source_value", "visit_occurrence_id", "src",
]

MAPS = [
    (RXNORM, "1049697", "1128940"),
    (CVX, "140", "4056"),
    (LOINC, "718-7", "3024929"),
    (LOINC, "72166-2", "4076669"),
]


@pytest.fixture()
def conn():
    con = fhir4ds.create_connection()
    con.execute("CREATE OR REPLACE TABLE __vd_src (resource JSON)")
    _stage_maps(con, MAPS)
    return con


def _run(con, view_name, resources):
    extra_maps = []
    for r in resources:
        if isinstance(r, tuple):
            extra_maps.append(r)
        else:
            con.execute("INSERT INTO __vd_src VALUES (?)", [json.dumps(r)])
    if extra_maps:
        _stage_maps(con, extra_maps)
    vd = parse_view_definition(json.loads((OMOP_DIR / f"{view_name}.json").read_text()))
    sql = SQLGenerator(source_table="__vd_src").generate(vd)
    return con.execute(sql).fetchall()


class TestDrugExposureChildren:
    def test_medication_request(self, conn):
        rows = _run(conn, "drug-exposure-medication-request-view", [{
            "resourceType": "MedicationRequest", "id": "mr1", "status": "active",
            "medicationCodeableConcept": {"coding": [{"system": RXNORM, "code": "1049697"}]},
            "subject": {"reference": "Patient/p1"}, "encounter": {"reference": "Encounter/e1"},
            "authoredOn": "2024-03-02T09:00:00Z",
            "dosageInstruction": [{"text": "1 tablet daily"}],
            "dispenseRequest": {"quantity": {"value": 30}, "expectedSupplyDays": 30}}])
        assert rows == [("mr1", "p1", "1128940", "2024-03-02", "2024-03-02T09:00:00Z",
                         "2024-03-02", "2024-03-02T09:00:00Z", "38000177",
                         "1 tablet daily", 30.0, 30, "1049697", "e1", "MedicationRequest")]

    def test_medication_statement_period_fallback(self, conn):
        rows = _run(conn, "drug-exposure-medication-statement-view", [{
            "resourceType": "MedicationStatement", "id": "ms1", "status": "active",
            "medicationCodeableConcept": {"coding": [{"system": RXNORM, "code": "1049697"}]},
            "subject": {"reference": "Patient/p1"},
            "effectivePeriod": {"start": "2024-03-01", "end": "2024-03-10"}}])
        r = rows[0]
        assert r[2] == "1128940" and r[3] == "2024-03-01" and r[5] == "2024-03-10" and r[7] == "38000175"

    def test_medication_administration(self, conn):
        rows = _run(conn, "drug-exposure-medication-administration-view", [{
            "resourceType": "MedicationAdministration", "id": "ma1", "status": "completed",
            "medicationCodeableConcept": {"coding": [{"system": RXNORM, "code": "1049697"}]},
            "subject": {"reference": "Patient/p1"}, "effectiveDateTime": "2024-03-02T14:30:00Z",
            "dosage": {"dose": {"value": 2}}}])
        by = dict(zip(_COLUMNS, rows[0]))
        assert by["drug_concept_id"] == "1128940" and by["drug_type_concept_id"] == "38000180"
        assert by["quantity_num"] == 2.0 and by["src"] == "MedicationAdministration"

    def test_immunization_cvx(self, conn):
        rows = _run(conn, "drug-exposure-immunization-view", [{
            "resourceType": "Immunization", "id": "im1", "status": "completed",
            "vaccineCode": {"coding": [{"system": CVX, "code": "140"}]},
            "patient": {"reference": "Patient/p1"}, "occurrenceDateTime": "2024-02-15"}])
        by = dict(zip(_COLUMNS, rows[0]))
        assert by["drug_concept_id"] == "4056" and by["drug_source_value"] == "140"
        assert by["src"] == "Immunization"


class TestMeasurementObservationSplit:
    LAB = {"resourceType": "Observation", "id": "o-lab", "status": "final",
           "code": {"coding": [{"system": LOINC, "code": "718-7"}]},
           "subject": {"reference": "Patient/p1"}, "effectiveDateTime": "2024-03-01T08:00:00Z",
           "valueQuantity": {"value": 13.5, "unit": "g/dL"},
           "referenceRange": [{"low": {"value": 12.0}, "high": {"value": 17.5}}]}
    SMOKING = {"resourceType": "Observation", "id": "o-smoke", "status": "final",
               "code": {"coding": [{"system": LOINC, "code": "72166-2"}]},
               "subject": {"reference": "Patient/p1"}, "effectiveDateTime": "2024-03-01T09:00:00Z",
               "valueCodeableConcept": {"coding": [{"system": SCT, "code": "8517006", "display": "Former smoker"}]}}

    def test_quantity_lands_in_measurement(self, conn):
        rows = _run(conn, "measurement-view", [self.LAB])
        assert len(rows) == 1
        r = rows[0]
        assert r[2] == "3024929" and r[6] == 13.5 and r[7] == "g/dL"
        assert r[8] == 12.0 and r[9] == 17.5

    def test_coded_lands_in_observation(self, conn):
        rows = _run(conn, "observation-view", [self.SMOKING])
        assert len(rows) == 1
        r = rows[0]
        assert r[2] == "4076669" and r[6] == "Former smoker" and r[8] == "8517006"

    def test_split_is_disjoint(self, conn):
        m = _run(conn, "measurement-view", [self.LAB, self.SMOKING])
        # fresh conn for the second view (same staging table would double-insert)
        con2 = fhir4ds.create_connection()
        con2.execute("CREATE OR REPLACE TABLE __vd_src (resource JSON)")
        _stage_maps(con2, MAPS)
        o = _run(con2, "observation-view", [self.LAB, self.SMOKING])
        assert sorted(x[0] for x in m) == ["o-lab"]
        assert sorted(x[0] for x in o) == ["o-smoke"]


class TestDeath:
    def test_deceased_patient_row(self, conn):
        rows = _run(conn, "death-view", [{
            "resourceType": "Patient", "id": "p2", "gender": "female",
            "birthDate": "1930-01-01", "deceasedDateTime": "2024-06-01T00:00:00Z"}])
        assert rows == [("p2", "2024-06-01", "2024-06-01T00:00:00Z", "32810", "2024-06-01T00:00:00Z")]

    def test_living_patient_no_row(self, conn):
        _run(conn, "death-view", [{
            "resourceType": "Patient", "id": "p1", "birthDate": "1974-12-25"}])
        con2 = fhir4ds.create_connection()
        con2.execute("CREATE OR REPLACE TABLE __vd_src (resource JSON)")
        vd = parse_view_definition(json.loads((OMOP_DIR / "death-view.json").read_text()))
        sql = SQLGenerator(source_table="__vd_src").generate(vd)
        # fresh staging with BOTH patients: only the deceased one yields a row
        for r in ({"resourceType": "Patient", "id": "p1", "birthDate": "1974-12-25"},
                  {"resourceType": "Patient", "id": "p2", "deceasedDateTime": "2024-06-01T00:00:00Z"}):
            con2.execute("INSERT INTO __vd_src VALUES (?)", [json.dumps(r)])
        names = [row[0] for row in con2.execute(sql).fetchall()]
        assert "p1" not in names and "p2" in names


class TestGrain:
    def test_child_grain_one_row_per_resource(self, conn):
        resources = [{
            "resourceType": "MedicationRequest", "id": f"mr{i}", "status": "active",
            "medicationCodeableConcept": {"coding": [{"system": RXNORM, "code": "1049697"}]},
            "subject": {"reference": "Patient/p1"}, "authoredOn": "2024-03-02"} for i in range(3)]
        rows = _run(conn, "drug-exposure-medication-request-view", resources)
        assert len(rows) == 3
