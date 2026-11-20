"""Environment code-system aliases for the PIQI registry (alias-rerun, 2026-11-20).

The MIMIC-IV-FHIR demo wraps standard ICD vocabularies under local
CodeSystem URIs (``mimic-diagnosis-icd9/icd10``,
``mimic-procedure-icd9/icd10``). Without an alias layer the
``Concept_HasRecognizedCodeSystem`` SAM scores every mimic-wrapped ICD
condition as unrecognized (0% recognized in the 2026-11-20 no-strip run).

The alias table is **data**, not code behavior: it is environment
specific (a different EHR export gets a different table), it is
consulted only AFTER the standard registry spellings, and a
recognized-via-alias verdict is distinguishable from a standard one.
"""

from __future__ import annotations

import typing as _t

from . import fixtures as fx
from .test_completeness import _results
from fhir4ds.piqi import run_sam

MIMIC_CS = "http://mimic.mit.edu/fhir/mimic/CodeSystem/"


def test_icd10_pcs_is_standard_and_recognized():
    """ICD-10-PCS (procedure coding) must be in the STANDARD registry —
    the 2026-11-20 no-strip run found appended PCS codes unrecognized
    while ICD-10-CM was recognized, under-counting procedures."""
    from fhir4ds.cql.terminology.system_mappings import (
        is_standard_code_system,
    )
    from fhir4ds.piqi.codesystems import is_recognized_code_system

    assert is_standard_code_system("http://hl7.org/fhir/sid/icd-10-pcs")
    assert is_recognized_code_system("http://hl7.org/fhir/sid/icd-10-pcs")


def test_environment_alias_table_is_declarative_data():
    from fhir4ds.piqi.codesystems import ENVIRONMENT_ALIASES

    assert ENVIRONMENT_ALIASES == {
        MIMIC_CS + "mimic-diagnosis-icd9":
            "http://hl7.org/fhir/sid/icd-9-cm",
        MIMIC_CS + "mimic-diagnosis-icd10":
            "http://hl7.org/fhir/sid/icd-10-cm",
        MIMIC_CS + "mimic-procedure-icd9":
            "http://hl7.org/fhir/sid/icd-9-cm",
        MIMIC_CS + "mimic-procedure-icd10":
            "http://hl7.org/fhir/sid/icd-10-pcs",
        MIMIC_CS + "mimic-medication-ndc":
            "http://hl7.org/fhir/sid/ndc",
    }


def test_aliases_resolve_after_standard_and_carry_provenance():
    from fhir4ds.piqi import codesystems as cs

    for alias, canonical in cs.ENVIRONMENT_ALIASES.items():
        entry = cs.resolve_code_system(alias)
        assert entry is not None, alias
        assert entry["identifier"] == canonical
        # provenance: recognized-via-alias is distinguishable from a
        # standard spelling
        assert cs.environment_alias_target(alias) == canonical
        assert cs.is_recognized_code_system(alias)
    # standard spellings are NOT environment aliases
    assert cs.environment_alias_target("http://loinc.org") is None
    assert cs.environment_alias_target("http://snomed.info/sct") is None
    # an alias spelling that collides with a standard spelling would
    # resolve through the STANDARD entry (aliases are second)
    assert (cs.resolve_code_system("http://loinc.org")["identifier"]
            == "http://loinc.org")


def test_recognized_closure_includes_aliases_not_proprietary():
    """The author-time SQL closure must recognize the alias spellings,
    and must NOT recognize MIMIC's proprietary systems — those have no
    standard counterpart, which is the translation-required signal."""
    from fhir4ds.piqi.codesystems import (
        ENVIRONMENT_ALIASES,
        is_recognized_code_system,
        recognized_system_strings,
    )

    closure = set(recognized_system_strings())
    for alias in ENVIRONMENT_ALIASES:
        assert alias in closure
        assert alias.upper() in closure
    for proprietary in (
            MIMIC_CS + "mimic-medication-name",
            MIMIC_CS + "mimic-medication-formulary-drug-cd",
            MIMIC_CS + "mimic-medication-poe-iv",
            MIMIC_CS + "mimic-d-items",
            MIMIC_CS + "mimic-chartevents-d-items"):
        assert proprietary not in closure
        assert not is_recognized_code_system(proprietary)


def _mimic_condition() -> _t.Dict[str, _t.Any]:
    return {
        "resourceType": "Condition",
        "id": "cond-icd10",
        "subject": {"reference": "Patient/pat-1"},
        "code": {"text": "Sepsis", "coding": [{
            "code": "A41.9", "display": "Sepsis",
            "system": MIMIC_CS + "mimic-diagnosis-icd10"}]},
        "clinicalStatus": {"coding": [{"code": "confirmed"}]},
        "onsetDateTime": "2020-11-14",
    }


def _mimic_medication() -> _t.Dict[str, _t.Any]:
    return {
        "resourceType": "MedicationRequest",
        "id": "med-name",
        "status": "completed",
        "intent": "order",
        "subject": {"reference": "Patient/pat-1"},
        "medicationCodeableConcept": {"text": "Ondansetron", "coding": [{
            "code": "Ondansetron",
            "system": MIMIC_CS + "mimic-medication-name"}]},
        "authoredOn": "2020-07-10",
    }


def test_mimic_wrapped_icd_condition_passes_recognized_sam():
    """End-to-end: a mimic-wrapped ICD condition passes
    Concept_HasRecognizedCodeSystem through the PACKAGED SAM (the SQL
    closure is embedded at author time, so this fails until resources
    are regenerated with the alias layer)."""
    con = fx.make_connection([fx.PATIENT_IG_P11, _mimic_condition()])
    rows = run_sam(con, "piqi-sam-condition-condition-hasrecognizedcodesystem")
    assert _results(rows)["cond-icd10"] == "pass"


def test_mimic_wrapped_pcs_procedure_passes_recognized_sam():
    con = fx.make_connection([fx.PATIENT_IG_P11, {
        "resourceType": "Procedure",
        "id": "proc-pcs",
        "status": "completed",
        "subject": {"reference": "Patient/pat-1"},
        "code": {"text": "Abdominal ultrasound", "coding": [{
            "code": "88.79", "display": "Abdominal ultrasound",
            "system": MIMIC_CS + "mimic-procedure-icd10"}]},
        "performedDateTime": "2020-11-14",
    }])
    rows = run_sam(con, "piqi-sam-procedure-procedure-hasrecognizedcodesystem")
    assert _results(rows)["proc-pcs"] == "pass"


def test_proprietary_medication_system_still_fails_recognized_sam():
    """The translation-required tier stays visible: a name-code med
    system is NOT alias-recognizable and keeps failing the SAM."""
    con = fx.make_connection([fx.PATIENT_IG_P11, _mimic_medication()])
    rows = run_sam(con, "piqi-sam-medication-medication-hasrecognizedcodesystem")
    assert _results(rows)["med-name"] == "fail"
