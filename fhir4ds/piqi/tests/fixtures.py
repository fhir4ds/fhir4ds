"""Guide-verbatim PIQI fixtures, wrapped as the equivalent FHIR resources.

Per FEATURE_PIQI_FRAMEWORK.md §8 Q2 (approved default): PIQI is
message-in-flight [HB p.7]; our stack assesses the *equivalent FHIR
payload*. Fixtures below are the guides' own worked examples, adapted
only by mapping PIQI attributes onto FHIR elements/extensions:

* Demographics concept attributes are carried as Patient extensions
  ``https://fhir4ds.org/piqi/StructureDefinition/<attributeName>`` with
  ``valueCodeableConcept`` (text + codings verbatim from [IG p.11]);
  ``deathDate`` is carried as an extension ``valueString`` so the
  guide's *empty string* survives (FHIR has no empty-primitive form).
* LabResult / VitalSign / HealthAssessment are Observations
  distinguished by ``category`` (laboratory / vital-signs /
  social-history); performedDateTime keeps the guide's instant
  (e.g. ``202007101030-0700`` → ``2020-07-10T10:30:00-07:00``).

Citations: [IG pp.9-20] (class examples), [SG p.16] (MONOCYTES
three-coding concept), [SG p.22] (range 14-88).
"""

from __future__ import annotations

import copy
import json
import typing as _t

PIQI_EXT = "https://fhir4ds.org/piqi/StructureDefinition/"
OBS_CATEGORY_SYSTEM = "http://terminology.hl7.org/CodeSystem/observation-category"
LOINC = "http://loinc.org"


def _cc(text: str, *codings: _t.Dict[str, str]) -> _t.Dict[str, _t.Any]:
    coding_list = [dict(c) for c in codings]
    return {"text": text, "coding": coding_list}


def _ext(name: str, value_key: str, value) -> _t.Dict[str, _t.Any]:
    return {"url": PIQI_EXT + name, value_key: value}


# ---------------------------------------------------------------------------
# [IG pp.11-12] Demographics example
# ---------------------------------------------------------------------------
PATIENT_IG_P11: _t.Dict[str, _t.Any] = {
    "resourceType": "Patient",
    "id": "pat-1",
    "gender": "male",
    "birthDate": "1966-05-18",
    "extension": [
        _ext("birthSex", "valueCodeableConcept",
             _cc("M", {"code": "M", "display": "Male", "system": "HL7-001"})),
        _ext("deathDate", "valueString", ""),
        _ext("deceased", "valueCodeableConcept",
             _cc("N", {"code": "N", "display": "No", "system": "HL7-0136"})),
        _ext("ethnicity", "valueCodeableConcept",
             _cc("U", {"code": "U", "display": "Unknown", "system": "HL7-0189"})),
        _ext("genderIdentity", "valueCodeableConcept",
             _cc("male gender", {"code": "446151000124109",
                                  "display": "Identifies as male gender",
                                  "system": "2.16.840.1.114222.4.11.8062"})),
        _ext("primaryLanguage", "valueCodeableConcept",
             _cc("English", {"code": "eng", "display": "English",
                             "system": "ISO 639-2"})),
        _ext("maritalStatus", "valueCodeableConcept",
             _cc("M", {"code": "M", "display": "Married", "system": "HL7-0002"})),
        _ext("race", "valueCodeableConcept",
             _cc("Other Race", {"code": "2131-1", "display": "Other Race",
                                "system": "http://hl7.org/fhir/ValueSet/v2-0005"})),
    ],
}


def patient_with_birthdate(value: str) -> _t.Dict[str, _t.Any]:
    p = copy.deepcopy(PATIENT_IG_P11)
    p["birthDate"] = value
    return p


def patient_with_empty_gender_identity() -> _t.Dict[str, _t.Any]:
    p = copy.deepcopy(PATIENT_IG_P11)
    for e in p["extension"]:
        if e["url"] == PIQI_EXT + "genderIdentity":
            e["valueCodeableConcept"] = {"text": "", "coding": []}
    return p


# ---------------------------------------------------------------------------
# [IG pp.15-16] Lab Result example (glucose)
# ---------------------------------------------------------------------------
GLUCOSE_OBS_IG_P15: _t.Dict[str, _t.Any] = {
    "resourceType": "Observation",
    "id": "lab-1",
    "status": "final",
    "category": [{"coding": [{"system": OBS_CATEGORY_SYSTEM, "code": "laboratory"}]}],
    "code": _cc("Glucose, Serum",
                {"code": "2345-7", "display": "Glucose Ser/Plas MCnc Pt Qn",
                 "system": LOINC}),
    "subject": {"reference": "Patient/pat-1"},
    "effectiveDateTime": "2020-07-10T10:30:00-07:00",
    "valueQuantity": {"value": 126, "unit": "mg/dL"},
    "interpretation": [{"text": "H"}],
    "referenceRange": [{"text": "70-100", "low": {"value": 70},
                        "high": {"value": 100}}],
    "specimen": {"reference": "Specimen/spec-1", "display": "blood"},
}

# [SG p.16] MONOCYTES three-coding test concept (LCL local + LOINC + empty system)
MONOCYTES_CODINGS = [
    {"code": "MONO100", "display": "MONOS", "system": "LCL"},
    {"code": "742-7", "display": "MONOCYTES:NCNC:PT:BLD:QN:AUTOMATED COUNT",
     "system": "LOINC"},
    {"code": "123456789", "display": "MONOCYTES, Serum", "system": ""},
]

MONOCYTES_OBS_SG_P16: _t.Dict[str, _t.Any] = {
    "resourceType": "Observation",
    "id": "lab-mono",
    "status": "final",
    "category": [{"coding": [{"system": OBS_CATEGORY_SYSTEM, "code": "laboratory"}]}],
    "code": {"text": "MONOCYTES, Serum", "coding": copy.deepcopy(MONOCYTES_CODINGS)},
    "subject": {"reference": "Patient/pat-1"},
    "effectiveDateTime": "2020-07-10T10:30:00-07:00",
    "valueQuantity": {"value": 4.2, "unit": "10*3/uL"},
}


def lab_obs(obs_id: str, value, *, code=None, effective="2020-07-10T10:30:00-07:00",
            reference_range=None, extra: _t.Dict | None = None) -> _t.Dict[str, _t.Any]:
    """Build a laboratory Observation with the given raw value.

    ``value`` may be a string (valueString) or a dict (valueQuantity).
    """
    obs: _t.Dict[str, _t.Any] = {
        "resourceType": "Observation",
        "id": obs_id,
        "status": "final",
        "category": [{"coding": [{"system": OBS_CATEGORY_SYSTEM,
                                  "code": "laboratory"}]}],
        "code": code if code is not None else _cc("Some Test",
                                                  {"code": "0000-0", "system": LOINC,
                                                   "display": "Some Test"}),
        "subject": {"reference": "Patient/pat-1"},
        "effectiveDateTime": effective,
    }
    if isinstance(value, dict):
        obs["valueQuantity"] = value
    else:
        obs["valueString"] = value
    if reference_range is not None:
        obs["referenceRange"] = [reference_range]
    if extra:
        obs.update(extra)
    return obs


# ---------------------------------------------------------------------------
# [IG p.20] Vital Sign example (BP 130/80)
# ---------------------------------------------------------------------------
BP_OBS_IG_P20: _t.Dict[str, _t.Any] = {
    "resourceType": "Observation",
    "id": "vs-bp-1",
    "status": "final",
    "category": [{"coding": [{"system": OBS_CATEGORY_SYSTEM, "code": "vital-signs"}]}],
    "code": _cc("Blood Pressure",
                {"code": "55284-4",
                 "display": "Blood pressure systolic & diastolic Arterial system - Pt -",
                 "system": LOINC}),
    "subject": {"reference": "Patient/pat-1"},
    "effectiveDateTime": "2020-07-10T10:30:00-07:00",
    "component": [
        {"code": {"coding": [{"code": "8480-5", "system": LOINC,
                              "display": "Systolic blood pressure"}]},
         "valueQuantity": {"value": 130, "unit": "mmHg"}},
        {"code": {"coding": [{"code": "8462-4", "system": LOINC,
                              "display": "Diastolic blood pressure"}]},
         "valueQuantity": {"value": 80, "unit": "mmHg"}},
    ],
    "interpretation": [{"text": "N"}],
}


def vital_obs(obs_id: str, systolic: float, diastolic: float, *,
              code_text="Blood Pressure", reference_range=None) -> _t.Dict[str, _t.Any]:
    obs: _t.Dict[str, _t.Any] = {
        "resourceType": "Observation",
        "id": obs_id,
        "status": "final",
        "category": [{"coding": [{"system": OBS_CATEGORY_SYSTEM,
                                  "code": "vital-signs"}]}],
        "code": _cc(code_text, {"code": "55284-4", "system": LOINC}),
        "subject": {"reference": "Patient/pat-1"},
        "effectiveDateTime": "2020-07-10T10:30:00-07:00",
        "component": [
            {"code": {"coding": [{"code": "8480-5", "system": LOINC}]},
             "valueQuantity": {"value": systolic, "unit": "mmHg"}},
            {"code": {"coding": [{"code": "8462-4", "system": LOINC}]},
             "valueQuantity": {"value": diastolic, "unit": "mmHg"}},
        ],
    }
    if reference_range is not None:
        obs["referenceRange"] = [reference_range]
    return obs


# ---------------------------------------------------------------------------
# [IG pp.9,10,13,14,17,18,19] remaining data-class examples
# ---------------------------------------------------------------------------
ALLERGY_IG_P9: _t.Dict[str, _t.Any] = {
    "resourceType": "AllergyIntolerance",
    "id": "all-1",
    "patient": {"reference": "Patient/pat-1"},
    "code": _cc("cephalexin", {"code": "2231", "display": "cephalexin",
                               "system": "RXNORM"}),
    "category": ["medication"],
    "criticality": "high",
    "onsetDateTime": "2024-11-14",
    "reaction": [{"manifestation": _cc(
        "Anaphylaxis", {"code": "39579001", "display": "Anaphylaxis",
                        "system": "http://snomed.info/sct"})}],
    # PIQI severity concept ("Severe", HL7-0128 SV) — carried verbatim
    "extension": [_ext("severity", "valueCodeableConcept",
                       _cc("Severe", {"code": "SV", "display": "Severe",
                                      "system": "HL7-0128"}))],
}

CONDITION_IG_P10: _t.Dict[str, _t.Any] = {
    "resourceType": "Condition",
    "id": "cond-1",
    "subject": {"reference": "Patient/pat-1"},
    "code": _cc("Type 2 diabetes mellitus",
                {"code": "44054006", "display": "Type 2 diabetes mellitus",
                 "system": "SNOMEDCT"}),
    "clinicalStatus": _cc("confirmed", {"code": "confirmed",
                                        "system": "http://hl7.org/fhir/resource-status"}),
    "category": [{"coding": [{"code": "problem-list-item"}]}],
    "onsetDateTime": "2020-11-14",
}

HEALTH_ASSESSMENT_IG_P13: _t.Dict[str, _t.Any] = {
    "resourceType": "Observation",
    "id": "ha-1",
    "status": "final",
    "category": [{"coding": [{"system": OBS_CATEGORY_SYSTEM,
                              "code": "social-history"}]}],
    "code": _cc("TOBACCO SMOKING STATUS",
                {"code": "72166-2", "display": "TOBACCO SMOKING STATUS",
                 "system": "LOINC"}),
    "subject": {"reference": "Patient/pat-1"},
    "effectiveDateTime": "2024-11-14",
    "valueCodeableConcept": _cc(
        "Current Heavy tobacco smoker",
        {"code": "428071000124103", "display": "Current Heavy tobacco smoker",
         "system": "SCT"}),
}

IMMUNIZATION_IG_P14: _t.Dict[str, _t.Any] = {
    "resourceType": "Immunization",
    "id": "imm-1",
    "status": "completed",
    "patient": {"reference": "Patient/pat-1"},
    "vaccineCode": _cc("Influenza, seasonal, injectable",
                       {"code": "141", "display": "Influenza, seasonal, injectable",
                        "system": "2.16.840.1.113883.12.292"}),
    "occurrenceDateTime": "2024-06-01",
    "expirationDate": "2025-05-18",
    "reaction": [{"detail": {"reference": "Observation/rx",
                             "display": "Wheal"}}],
}

MEDICATION_IG_P18: _t.Dict[str, _t.Any] = {
    "resourceType": "MedicationRequest",
    "id": "med-1",
    "status": "completed",
    "intent": "order",
    "subject": {"reference": "Patient/pat-1"},
    "medicationCodeableConcept": _cc(
        "ibuprofen 600 MG Oral Tablet",
        {"code": "197806", "display": "ibuprofen 600 MG Oral Tablet",
         "system": "RXNORM"}),
    "authoredOn": "2020-07-10T10:30:00-07:00",
    "dosageInstruction": [{"text": "take 1 tablet QID PRN",
                           "route": _cc("Oral", {"code": "C38288",
                                                 "display": "Oral Route of Administration",
                                                 "system": "2.16.840.1.113883.3.26.1.1"})}],
    "dispenseRequest": {"quantity": {"value": 1, "unit": "tabs"}},
}

PROCEDURE_IG_P19: _t.Dict[str, _t.Any] = {
    "resourceType": "Procedure",
    "id": "proc-1",
    "status": "completed",
    "subject": {"reference": "Patient/pat-1"},
    "code": _cc("Other excision of appendix NOS",
                {"code": "265390009", "display": "Other excision of appendix NOS",
                 "system": "SNOMEDCT"}),
    "performedDateTime": "2020-11-14",
    "reasonCode": [_cc("Acute appendicitis",
                       {"code": "85189001", "display": "Acute appendicitis",
                        "system": "SNOMEDCT"})],
}

DEVICE_IG_P17: _t.Dict[str, _t.Any] = {
    "resourceType": "Device",
    "id": "dev-1",
    "status": "active",
    "manufacturer": "NuvoMed",
    "deviceName": [{"name": "NuvoMed Wireless Glucose Monitor",
                    "type": "model-name"}],
    "type": _cc("Glucose Monitor",
                {"code": "528401", "display": "Glucose Monitor",
                 "system": "http://hl7.org/fhir/ValueSet/device-type"}),
    "udiCarrier": [{"deviceIdentifier": "04719871820322"}],
    "manufactureDate": "2020-07-10",
}


# ---------------------------------------------------------------------------
# connection helper
# ---------------------------------------------------------------------------
def make_connection(resources, con=None, *, force_python_fallback: bool = False):
    """Create a DuckDB connection with fhirpath UDFs and a resources table."""
    import duckdb

    orig_version = duckdb.__version__
    if force_python_fallback:
        duckdb.__version__ = "0.0.0-forced-python-fallback"
    try:
        if con is None:
            con = duckdb.connect(config={"allow_unsigned_extensions": True})
        from fhir4ds.fhirpath.duckdb import register_fhirpath

        registered = register_fhirpath(con)
    finally:
        # restore the module attribute so later connects in the same
        # pytest session are not silently forced onto the fallback path
        duckdb.__version__ = orig_version
    if force_python_fallback:
        assert registered is False, "expected Python fallback registration"
    else:
        assert registered is True, "native FHIRPath extension did not load"
    con.execute("CREATE OR REPLACE TABLE resources (resource JSON)")
    for r in resources:
        con.execute("INSERT INTO resources VALUES (?)", [json.dumps(r)])
    return con
