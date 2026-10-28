"""FHIR reference forms must normalize to one OMOP person id.

Every event view derives ``person_id`` (and the encounter ids) from
``<resource>.reference``. FHIR allows references as ``Patient/{id}``,
absolute URLs ending in ``/Patient/{id}``, and — inside a transaction
bundle, which is exactly what Synthea's NDJSON export preserves —
``urn:uuid:{id}``. Splitting on ``/`` alone leaves the ``urn:uuid:``
prefix on the id, so the parent row's ``id`` and every child's
``person_id`` disagree: the foreign key dangles silently (the key
projection hashes whatever string it is given).

The shipped 25-patient cohort uses ``urn:uuid:`` references exclusively,
so this is the form the demo actually exercises.
"""

import json
from pathlib import Path

import pytest

import fhir4ds
from fhir4ds.viewdef.omop_runner import create_omop_views

OMOP_DIR = Path(__file__).parents[2] / "resources" / "omop"
RXNORM = "http://www.nlm.nih.gov/research/umls/rxnorm"


def _resource(**fields):
    return json.dumps(fields)


@pytest.fixture(scope="module")
def con():
    con = fhir4ds.create_connection()
    con.execute("CREATE TABLE resources (resource JSON)")
    rows = [
        _resource(
            resourceType="Patient",
            id="pat-urn",
            gender="male",
            birthDate="1980-01-01",
        ),
        _resource(
            resourceType="Patient",
            id="pat-rel",
            gender="female",
            birthDate="1990-02-02",
        ),
        _resource(
            resourceType="Encounter",
            id="enc-urn",
            status="finished",
            **{"class": {"system": "http://terminology.hl7.org/CodeSystem/v3-ActCode", "code": "AMB"}},
            subject={"reference": "urn:uuid:pat-urn"},
            period={"start": "2020-01-01", "end": "2020-01-02"},
        ),
        # urn:uuid reference (Synthea / bundle-local)
        _resource(
            resourceType="MedicationRequest",
            id="med-urn",
            status="active",
            subject={"reference": "urn:uuid:pat-urn"},
            encounter={"reference": "urn:uuid:enc-urn"},
            medicationCodeableConcept={"coding": [{"system": RXNORM, "code": "106892"}]},
            authoredOn="2020-01-01",
        ),
        # relative reference
        _resource(
            resourceType="MedicationRequest",
            id="med-rel",
            status="active",
            subject={"reference": "Patient/pat-rel"},
            encounter={"reference": "Encounter/enc-urn"},
            medicationCodeableConcept={"coding": [{"system": RXNORM, "code": "106892"}]},
            authoredOn="2020-01-03",
        ),
        # absolute URL reference
        _resource(
            resourceType="MedicationRequest",
            id="med-abs",
            status="active",
            subject={"reference": "https://example.org/fhir/Patient/pat-urn"},
            encounter={"reference": "https://example.org/fhir/Encounter/enc-urn"},
            medicationCodeableConcept={"coding": [{"system": RXNORM, "code": "106892"}]},
            authoredOn="2020-01-05",
        ),
    ]
    for row in rows:
        con.execute("INSERT INTO resources VALUES (?)", [row])
    create_omop_views(con, source_table="resources")
    return con


def test_no_urn_prefix_leaks_into_event_ids(con):
    for column, table in [
        ("person_id", "drug_exposure"),
        ("visit_occurrence_id", "drug_exposure"),
        ("person_id", "visit_occurrence"),
    ]:
        leaked = con.execute(
            f"SELECT count(*) FROM omop.{table} WHERE CAST({column} AS VARCHAR) LIKE 'urn:uuid:%'"
        ).fetchone()[0]
        assert leaked == 0, f"{table}.{column} kept the urn:uuid: prefix"


def test_all_reference_forms_land_on_the_parent_row(con):
    # Three prescriptions: urn, relative, absolute. Two belong to pat-urn,
    # one to pat-rel, and each must join its person row exactly once.
    by_patient = dict(
        con.execute(
            """
            SELECT p.person_source_value, count(*)
            FROM omop.drug_exposure d
            JOIN omop.person p ON p.person_id = d.person_id
            GROUP BY 1 ORDER BY 1
            """
        ).fetchall()
    )
    assert by_patient == {"pat-rel": 1, "pat-urn": 2}, by_patient


def test_no_orphaned_events(con):
    for table in ["drug_exposure", "visit_occurrence"]:
        orphans = con.execute(
            f"""
            SELECT count(*) FROM omop.{table} t
            LEFT JOIN omop.person p ON p.person_id = t.person_id
            WHERE p.person_id IS NULL
            """
        ).fetchone()[0]
        assert orphans == 0, f"{orphans} orphaned rows in {table}"


def test_visit_occurrence_ids_normalize_too(con):
    # Encounter ids resolve from the same reference forms (urn + relative +
    # absolute); all three prescriptions point at enc-urn.
    assert con.execute(
        """
        SELECT count(*) FROM omop.drug_exposure d
        JOIN omop.visit_occurrence v ON v.visit_occurrence_id = d.visit_occurrence_id
        """
    ).fetchone()[0] == 3
