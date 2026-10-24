"""OMOP S4: composite runner + demo bundle (design §4/§5/§6).

Pins the composed omop.* schema: union counts, the 63-bit integer-key
projection (stable, referentially consistent hashes), concept-0
defaults, column sets, and the demo bundle's expected-row fixture
(fresh-evidence).
"""

import json
from pathlib import Path

import pytest

import fhir4ds
from fhir4ds.viewdef.omop_runner import create_omop_views

OMOP_DIR = Path(__file__).parents[2] / "resources" / "omop"


@pytest.fixture(scope="module")
def con():
    con = fhir4ds.create_connection()
    con.execute("CREATE TABLE resources (resource JSON)")
    for line in (OMOP_DIR / "demo" / "resources.ndjson").read_text().splitlines():
        if line.strip():
            con.execute("INSERT INTO resources VALUES (?)", [line.strip()])
    create_omop_views(con, source_table="resources")
    return con


def test_expected_row_counts(con):
    expected = json.loads((OMOP_DIR / "demo" / "expected-rows.json").read_text())
    for table, spec in expected.items():
        n = con.execute(f"SELECT count(*) FROM omop.{table}").fetchone()[0]
        assert n == spec["row_count"], f"omop.{table}: {n} != {spec['row_count']}"


def test_expected_column_sets(con):
    expected = json.loads((OMOP_DIR / "demo" / "expected-rows.json").read_text())
    for table, spec in expected.items():
        cols = [d[0] for d in con.execute(f"SELECT * FROM omop.{table} LIMIT 0").description]
        assert cols == spec["columns"], f"omop.{table} columns drifted"


def test_integer_keys_stable_and_referential(con):
    # person key identical across every event table
    rows = con.execute("""
        SELECT DISTINCT p.person_id FROM omop.person p
        JOIN omop.visit_occurrence v ON v.person_id = p.person_id
        JOIN omop.condition_occurrence c ON c.person_id = p.person_id
        JOIN omop.drug_exposure d ON d.person_id = p.person_id
        WHERE p.person_source_value = 'pat-001'
    """).fetchall()
    assert len(rows) == 1
    # positive 63-bit range
    assert 0 < rows[0][0] < 2**63
    # deterministic across recompute
    again = con.execute("""
        SELECT DISTINCT hash('pat-001') & 9223372036854775807
    """).fetchone()[0]
    assert again == rows[0][0]


def test_concept_defaults_and_spot_values(con):
    expected = json.loads((OMOP_DIR / "demo" / "expected-rows.json").read_text())
    spot = expected["person"]["spot"]["person_source_value->gender_concept_id"]
    got = [list(r) for r in con.execute(
        "SELECT person_source_value, gender_concept_id FROM omop.person ORDER BY person_source_value").fetchall()]
    assert got == spot  # pat-001->8507, pat-002->8532
    cspot = expected["condition_occurrence"]["spot"]["condition_source_value->condition_concept_id"]
    cgot = [list(r) for r in con.execute(
        "SELECT condition_source_value, condition_concept_id FROM omop.condition_occurrence").fetchall()]
    assert cgot == cspot  # SNOMED preferred: 38341003 -> 313217
    dspot = expected["drug_exposure"]["spot"]["src->drug_concept_id"]
    dgot = [list(r) for r in con.execute(
        "SELECT src, drug_concept_id FROM omop.drug_exposure ORDER BY src").fetchall()]
    assert dgot == dspot  # MedicationRequest->1128940, Immunization->4056
    assert con.execute(
        "SELECT value_as_number, measurement_concept_id FROM omop.measurement").fetchone() == (13.5, 3024929)
    assert con.execute(
        "SELECT value_as_string, observation_concept_id FROM omop.observation").fetchone() == ("Former smoker", 4076669)


def test_concept_columns_are_integer_typed(con):
    t = con.execute("SELECT typeof(person_id), typeof(gender_concept_id) FROM omop.person LIMIT 1").fetchone()
    assert t == ("BIGINT", "BIGINT")


def test_union_is_sum_of_children(con):
    # drug_exposure = sum of the four child views' rows
    n_union = con.execute("SELECT count(*) FROM omop.drug_exposure").fetchone()[0]
    n_children = sum(
        con.execute(f"SELECT count(*) FROM omop.drug_exposure__{suffix}").fetchone()[0]
        for suffix in ("medication_request", "medication_statement",
                       "medication_administration", "immunization")
    )
    assert n_union == n_children == 2
