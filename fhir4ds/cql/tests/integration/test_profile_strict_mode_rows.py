"""STRICT PROFILE MODE — end-to-end row behaviour (not just SQL text).

The mode's contract is what rows come back, so these tests load real resources
into a ``resources`` table and execute the generated population SQL both ways:

* STRICT (default): a profile-qualified retrieve returns only resources whose
  ``meta.profile`` declares that canonical. A resource with no ``meta.profile``
  is invisible to it (LIST membership over a missing array is NULL, and a NULL
  WHERE drops the row).
* NON-STRICT: the same retrieve matches the base resource type.

The regression that motivated the knob: US Quality Core declares paired
Condition profiles distinguished ONLY by ``meta.profile`` /
``Condition.category`` (``condition-encounter-diagnosis`` vs
``condition-problems-health-concerns``). Without the membership test a
``[ConditionProblemsHealthConcerns: …]`` retrieve silently picks up encounter
diagnoses — in the CMS 2025 suite that flipped 6 measures (CMS22, CMS72, CMS108,
CMS138, CMS155, CMS832) toward false-positive Denominator Exclusions.
"""

from __future__ import annotations

import json

import pytest

from fhir4ds import create_connection
from ...parser import parse_cql
from ...translator import CQLToSQLTranslator

USQC = "http://fhir.org/guides/astp/us-quality-core/StructureDefinition"

CQL = f"""
library Test version '1.0'

using USQualityCore version '0.1.0-cibuild'
using FHIR version '4.0.1'

context Patient

define "Any Problem Concern":
    exists([USQualityCore.ConditionProblemsHealthConcerns])
"""

PATIENT = {
    "resourceType": "Patient",
    "id": "p1",
    "meta": {"profile": [f"{USQC}/us-quality-core-patient"]},
}

ENCOUNTER_DIAGNOSIS = {
    "resourceType": "Condition",
    "id": "c-enc",
    "meta": {"profile": [f"{USQC}/us-quality-core-condition-encounter-diagnosis"]},
    "category": [
        {
            "coding": [
                {
                    "system": "http://terminology.hl7.org/CodeSystem/condition-category",
                    "code": "encounter-diagnosis",
                }
            ]
        }
    ],
    "code": {
        "coding": [
            {"system": "http://snomed.info/sct", "code": "10725009", "display": "Benign hypertension"}
        ]
    },
    "subject": {"reference": "Patient/p1"},
}

PROBLEM_CONCERN = {
    "resourceType": "Condition",
    "id": "c-prob",
    "meta": {
        "profile": [f"{USQC}/us-quality-core-condition-problems-health-concerns"]
    },
    "category": [
        {
            "coding": [
                {
                    "system": "http://terminology.hl7.org/CodeSystem/condition-category",
                    "code": "problem-list-item",
                }
            ]
        }
    ],
    "code": {
        "coding": [
            {"system": "http://snomed.info/sct", "code": "38341003", "display": "Hypertension"}
        ]
    },
    "subject": {"reference": "Patient/p1"},
}

NO_PROFILE_CONDITION = {
    "resourceType": "Condition",
    "id": "c-bare",
    "code": {
        "coding": [
            {"system": "http://snomed.info/sct", "code": "38341003", "display": "Hypertension"}
        ]
    },
    "subject": {"reference": "Patient/p1"},
}


def _connection(resources):
    conn = create_connection()
    conn.execute(
        "CREATE TABLE resources (id VARCHAR, resourceType VARCHAR, "
        "resource JSON, patient_ref VARCHAR)"
    )
    for res in resources:
        conn.execute(
            "INSERT INTO resources VALUES (?, ?, ?, ?)",
            [res.get("id"), res["resourceType"], json.dumps(res), "p1"],
        )
    return conn


def _evaluate(resources, strict_profiles):
    conn = _connection(resources)
    translator = CQLToSQLTranslator(
        connection=conn, strict_profiles=strict_profiles
    )
    sql = translator.translate_library_to_population_sql(parse_cql(CQL))
    row = conn.execute(sql).fetchone()
    conn.close()
    return row


def _flag(rows):
    """Normalise the population row ``(patient_id, value)`` to a bool."""
    assert rows is not None and len(rows) >= 2, f"unexpected row shape: {rows!r}"
    return bool(rows[-1])


class TestStrictProfileModeRows:
    def test_encounter_diagnosis_is_not_a_problem_concern_in_strict_mode(self):
        """PAIRED-PROFILE REGRESSION: an encounter diagnosis must not satisfy a
        ProblemsHealthConcerns retrieve. This is the CMS22/CMS72 false
        Denominator Exclusion class."""
        assert _flag(_evaluate([PATIENT, ENCOUNTER_DIAGNOSIS], True)) is False

    def test_encounter_diagnosis_matches_in_non_strict_mode(self):
        """Turning strict mode off restores base-type matching (the documented
        trade-off), which is why the default stays ON."""
        assert _flag(_evaluate([PATIENT, ENCOUNTER_DIAGNOSIS], False)) is True

    def test_declared_problem_concern_matches_in_both_modes(self):
        for strict in (True, False):
            assert _flag(_evaluate([PATIENT, PROBLEM_CONCERN], strict)) is True, (
                f"a correctly-profiled resource must match with strict_profiles={strict}"
            )

    def test_resource_without_meta_profile_is_invisible_in_strict_mode(self):
        """The 'my data has no meta.profile' case the knob exists for."""
        assert _flag(_evaluate([PATIENT, NO_PROFILE_CONDITION], True)) is False

    def test_resource_without_meta_profile_is_visible_in_non_strict_mode(self):
        assert _flag(_evaluate([PATIENT, NO_PROFILE_CONDITION], False)) is True

    def test_mixed_payload_keeps_only_the_declared_profile_in_strict_mode(self):
        """Both conditions present: strict mode sees exactly one member."""
        resources = [PATIENT, ENCOUNTER_DIAGNOSIS, PROBLEM_CONCERN, NO_PROFILE_CONDITION]
        assert _flag(_evaluate(resources, True)) is True


class TestNegationProfileExclusionUnaffected:
    """A not-done profile must never surface as positive evidence, in either mode."""

    CQL_MED = """
    library TestMed version '1.0'

    using USQualityCore version '0.1.0-cibuild'
    using FHIR version '4.0.1'

    context Patient

    define "Any Order":
        exists([USQualityCore.MedicationRequest])
    """

    PATIENT = PATIENT

    ORDER = {
        "resourceType": "MedicationRequest",
        "id": "m1",
        "meta": {"profile": [f"{USQC}/us-quality-core-medicationrequest"]},
        "status": "active",
        "intent": "order",
        "medicationCodeableConcept": {
            "coding": [{"system": "http://www.nlm.nih.gov/research/umls/rxnorm", "code": "1234"}]
        },
        "subject": {"reference": "Patient/p1"},
    }

    NOT_DONE = {
        "resourceType": "MedicationRequest",
        "id": "m-notdone",
        "meta": {"profile": [f"{USQC}/us-quality-core-medicationnotrequested"]},
        "status": "active",
        "intent": "order",
        "doNotPerform": True,
        "medicationCodeableConcept": {
            "coding": [{"system": "http://www.nlm.nih.gov/research/umls/rxnorm", "code": "1234"}]
        },
        "subject": {"reference": "Patient/p1"},
    }

    def _run(self, resources, strict_profiles):
        conn = _connection(resources)
        translator = CQLToSQLTranslator(connection=conn, strict_profiles=strict_profiles)
        sql = translator.translate_library_to_population_sql(parse_cql(self.CQL_MED))
        row = conn.execute(sql).fetchone()
        conn.close()
        return _flag(row)

    def test_not_done_only_payload_never_counts_as_positive(self):
        for strict in (True, False):
            assert self._run([self.PATIENT, self.NOT_DONE], strict) is False, (
                f"a not-done resource must not be positive with strict_profiles={strict}"
            )

    def test_real_order_counts_when_mixed_with_not_done(self):
        for strict in (True, False):
            assert self._run([self.PATIENT, self.ORDER, self.NOT_DONE], strict) is True
