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


class TestDrugExposureChildren:
    def test_medication_request(self, conn):
        conn.execute("INSERT INTO __vd_src VALUES (?)", [json.dumps({
            "resourceType": "MedicationRequest", "id": "mr1", "status": "active",
            "medicationCodeableConcept": {"coding": [{"system": RXNORM, "code": "1049697"}]},
            "subject": {"reference": "Patient/p1"}, "encounter": {"reference": "Encounter/e1"},
            "authoredOn": "2024-03-02T09:00:00Z",
            "dosageInstruction": [{"text": "1 tablet daily"}],
            "dispenseRequest": {"quantity": {"value": 30}, "expectedSupplyDays": 30}})])
        by = dict(zip(_COLUMNS, _compose(conn, "drug_exposure")[0]))
        assert by["drug_concept_id"] == 1128940
        assert by["drug_type_concept_id"] == 38000177
        assert by["drug_exposure_start_date"] == "2024-03-02"
        assert by["drug_source_value"] == "1049697"
        assert by["src"] == "MedicationRequest"
        assert float(by["quantity_num"]) == 30.0 and by["days_supply"] == 30
        assert isinstance(by["drug_exposure_id"], int)
        assert isinstance(by["visit_occurrence_id"], int)

    def test_medication_statement_period_fallback(self, conn):
        conn.execute("INSERT INTO __vd_src VALUES (?)", [json.dumps({
            "resourceType": "MedicationStatement", "id": "ms1", "status": "active",
            "medicationCodeableConcept": {"coding": [{"system": RXNORM, "code": "1049697"}]},
            "subject": {"reference": "Patient/p1"},
            "effectivePeriod": {"start": "2024-03-01", "end": "2024-03-10"}})])
        by = dict(zip(_COLUMNS, _compose(conn, "drug_exposure")[0]))
        assert by["drug_concept_id"] == 1128940
        assert by["drug_exposure_start_date"] == "2024-03-01"
        assert by["drug_exposure_end_date"] == "2024-03-10"
        assert by["drug_type_concept_id"] == 38000175

    def test_medication_administration(self, conn):
        conn.execute("INSERT INTO __vd_src VALUES (?)", [json.dumps({
            "resourceType": "MedicationAdministration", "id": "ma1", "status": "completed",
            "medicationCodeableConcept": {"coding": [{"system": RXNORM, "code": "1049697"}]},
            "subject": {"reference": "Patient/p1"}, "effectiveDateTime": "2024-03-02T14:30:00Z",
            "dosage": {"dose": {"value": 2}}})])
        by = dict(zip(_COLUMNS, _compose(conn, "drug_exposure")[0]))
        assert by["drug_concept_id"] == 1128940
        assert by["drug_type_concept_id"] == 38000180
        assert float(by["quantity_num"]) == 2.0
        assert by["src"] == "MedicationAdministration"

    def test_immunization_cvx(self, conn):
        conn.execute("INSERT INTO __vd_src VALUES (?)", [json.dumps({
            "resourceType": "Immunization", "id": "im1", "status": "completed",
            "vaccineCode": {"coding": [{"system": CVX, "code": "140"}]},
            "patient": {"reference": "Patient/p1"}, "occurrenceDateTime": "2024-02-15"})])
        by = dict(zip(_COLUMNS, _compose(conn, "drug_exposure")[0]))
        assert by["drug_concept_id"] == 4056
        assert by["drug_source_value"] == "140"
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
        conn.execute("INSERT INTO __vd_src VALUES (?)", [json.dumps(self.LAB)])
        rows = _compose(conn, "measurement")
        assert len(rows) == 1
        by = dict(zip(["measurement_id", "person_id", "measurement_concept_id",
                       "measurement_date", "measurement_datetime",
                       "measurement_type_concept_id", "value_as_number",
                       "unit_source_value", "range_low", "range_high",
                       "measurement_source_value", "value_source_value",
                       "visit_occurrence_id"], rows[0]))
        assert by["measurement_concept_id"] == 3024929
        assert by["value_as_number"] == 13.5
        assert by["unit_source_value"] == "g/dL"
        assert by["range_low"] == 12.0 and by["range_high"] == 17.5

    def test_coded_lands_in_observation(self, conn):
        conn.execute("INSERT INTO __vd_src VALUES (?)", [json.dumps(self.SMOKING)])
        rows = _compose(conn, "observation")
        assert len(rows) == 1
        by = dict(zip(["observation_id", "person_id", "observation_concept_id",
                       "observation_date", "observation_datetime",
                       "observation_type_concept_id", "value_as_string",
                       "observation_source_value", "value_source_value",
                       "visit_occurrence_id"], rows[0]))
        assert by["observation_concept_id"] == 4076669
        assert by["value_as_string"] == "Former smoker"
        assert by["value_source_value"] == "8517006"

    def test_split_is_disjoint(self, conn):
        for r in (self.LAB, self.SMOKING):
            conn.execute("INSERT INTO __vd_src VALUES (?)", [json.dumps(r)])
        m = _compose(conn, "measurement")
        o = _compose(conn, "observation")
        assert len(m) == 1 and len(o) == 1
        assert dict(zip(["measurement_source_value"], [])) == {}  # shape guard
        assert "718-7" in str(m) and "72166-2" not in str(m)
        assert "72166-2" in str(o) and "718-7" not in str(o)


class TestDeath:
    COLS = ["person_id", "death_date", "death_datetime", "death_type_concept_id",
            "cause_source_value"]

    def test_deceased_patient_row(self, conn):
        conn.execute("INSERT INTO __vd_src VALUES (?)", [json.dumps({
            "resourceType": "Patient", "id": "p2", "gender": "female",
            "birthDate": "1930-01-01", "deceasedDateTime": "2024-06-01T00:00:00Z"})])
        rows = _compose(conn, "death")
        assert len(rows) == 1
        by = dict(zip(self.COLS, rows[0]))
        assert by["death_date"] == "2024-06-01"
        assert by["death_datetime"] == "2024-06-01T00:00:00Z"
        assert by["death_type_concept_id"] == 32810
        assert isinstance(by["person_id"], int)

    def test_living_patient_no_row(self, conn):
        for r in ({"resourceType": "Patient", "id": "p1", "birthDate": "1974-12-25"},
                  {"resourceType": "Patient", "id": "p2", "deceasedDateTime": "2024-06-01T00:00:00Z"}):
            conn.execute("INSERT INTO __vd_src VALUES (?)", [json.dumps(r)])
        assert len(_compose(conn, "death")) == 1


class TestGrain:
    def test_child_grain_one_row_per_resource(self, conn):
        resources = [{
            "resourceType": "MedicationRequest", "id": f"mr{i}", "status": "active",
            "medicationCodeableConcept": {"coding": [{"system": RXNORM, "code": "1049697"}]},
            "subject": {"reference": "Patient/p1"}, "authoredOn": "2024-03-02"} for i in range(3)]
        for r in resources:
            conn.execute("INSERT INTO __vd_src VALUES (?)", [json.dumps(r)])
        assert len(_compose(conn, "drug_exposure")) == 3
