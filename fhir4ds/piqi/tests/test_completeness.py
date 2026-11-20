"""PIQI completeness campaign acceptance tests (2026-11-20).

Authored BEFORE implementation per the red/green doctrine; the RED run
is archived at
``fhir4ds-private/docs/prompts/.ai_loop/piqi_completeness_redgreen.md``.

Batches (PIQI_COMPLETENESS_MATRIX.md §"Recommended implementation batch
order", Joel-approved non-controversial subset):

1. Binding widening + pure-logic SAMs (Concept_Has* to every coded
   attribute; numeric/timestamp/valid-date widening; temporal
   future/past SAMs; ObservationValue_IsQualitative/MatchesType;
   Class_HasDuplicates to remaining classes).
2. Rubric metadata fidelity (RG v1.2 fields, name overrides,
   informational weight-0 enforcement, automatic sequence).
3. Code-system registry [HB p.15] + Concept_HasRecognizedCodeSystem.
4. Parameterized SAM execution (Attr_MatchesRegex / Attr_InList /
   ObservationValueType_InList).
5. Terminology SAMs against the TerminologyEndpoint PROTOCOL (stub
   endpoint in tests; optional live integration behind an env var).
"""

from __future__ import annotations

import json
import typing as _t

import pytest

from . import fixtures as fx
from fhir4ds.piqi import (
    build_rubric,
    evaluate_rubric,
    get_sam,
    run_sam,
)


def _results(rows: _t.List[dict]) -> dict:
    return {r["element_id"]: r["result"] for r in rows}


def _catalog_mnemonics() -> set:
    from fhir4ds.piqi.authoring import build_sam_catalog

    return {s.mnemonic for s in build_sam_catalog()}


# ===========================================================================
# Batch 1 — binding widening + pure-logic SAMs
# ===========================================================================
def test_b1_concept_has_parts_bound_to_every_coded_attribute():
    """Concept_HasCode/HasCodeSystem/HasDisplay run on every class's
    primary concept, not just LabResult.test / VitalSign.vitalSign
    (closes the concept-coverage asymmetry, matrix §2)."""
    import copy

    device = copy.deepcopy(fx.DEVICE_IG_P17)
    device["patient"] = {"reference": "Patient/pat-1"}
    con = fx.make_connection([
        fx.PATIENT_IG_P11, fx.ALLERGY_IG_P9, fx.CONDITION_IG_P10,
        fx.HEALTH_ASSESSMENT_IG_P13, fx.IMMUNIZATION_IG_P14,
        fx.MEDICATION_IG_P18, fx.PROCEDURE_IG_P19, device,
        fx.BP_OBS_IG_P20, fx.GLUCOSE_OBS_IG_P15,
    ])
    for iid in (
        "piqi-sam-allergy-substance-hascode",
        "piqi-sam-allergy-substance-hascodesystem",
        "piqi-sam-allergy-substance-hasdisplay",
        "piqi-sam-condition-condition-hascode",
        "piqi-sam-healthassessment-assessment-hascodesystem",
        "piqi-sam-immunization-immunization-hasdisplay",
        "piqi-sam-medication-medication-hascode",
        "piqi-sam-procedure-procedure-hascodesystem",
        "piqi-sam-medicaldevice-devicetype-hasdisplay",
        "piqi-sam-demographics-birthsex-hascode",
        "piqi-sam-demographics-race-hascodesystem",
        "piqi-sam-demographics-ethnicity-hasdisplay",
    ):
        rows = run_sam(con, iid)
        assert rows, iid
        assert all(r["result"] == "pass" for r in rows), (iid, rows)
    # BOTH guide fixtures carry TEXT-ONLY interpretations [IG p.15/p.20]
    # — Concept_HasCodeSystem legitimately FAILS on them (that is the
    # asymmetry the widening exposes).
    assert _results(run_sam(
        con, "piqi-sam-vitalsign-interpretation-hascodesystem"))["vs-bp-1"] == "fail"
    # the guide's own glucose fixture carries a TEXT-ONLY interpretation
    # [IG p.15] — Concept_HasCode legitimately FAILS on it (that is the
    # asymmetry the widening exposes); a coded interpretation passes.
    rows = run_sam(con, "piqi-sam-labresult-interpretation-hascode")
    assert _results(rows)["lab-1"] == "fail"
    coded = fx.lab_obs("lab-i", "x", extra={"interpretation": [{
        "text": "H", "coding": [{"code": "H", "display": "High",
                                 "system": "http://hl7.org/fhir/v2/0078"}]}]})
    con2 = fx.make_connection([fx.PATIENT_IG_P11, coded])
    rows = run_sam(con2, "piqi-sam-labresult-interpretation-hascode")
    assert _results(rows)["lab-i"] == "pass"


def test_b1_concept_hascodesystem_fails_on_empty_system():
    con = fx.make_connection([
        fx.PATIENT_IG_P11,
        fx.lab_obs("lab-nosys", "x", code={"text": "T", "coding": [
            {"code": "742-7", "display": "d", "system": ""}]}),
    ])
    rows = run_sam(con, "piqi-sam-labresult-test-hascodesystem")
    assert _results(rows)["lab-nosys"] == "fail"


def test_b1_numeric_sams_widened():
    """Attr_IsNumeric family runs on VitalSign/HealthAssessment
    resultValue and Medication.doseAmount. A BP panel's text form
    ('130/80') is honestly NOT a scalar number (its numbers live in
    the _number/_number2 columns) — documented semantics."""
    import copy

    con = fx.make_connection([
        fx.PATIENT_IG_P11, fx.BP_OBS_IG_P20,
        fx.HEALTH_ASSESSMENT_IG_P13, fx.MEDICATION_IG_P18,
    ])
    rows = run_sam(con, "piqi-sam-vitalsign-resultvalue-isnumeric")
    assert _results(rows)["vs-bp-1"] == "fail"  # '130/80' BP panel text
    rows = run_sam(con, "piqi-sam-healthassessment-resultvalue-isnumeric")
    assert _results(rows)["ha-1"] == "fail"  # text value, not numeric
    import copy

    med = copy.deepcopy(fx.MEDICATION_IG_P18)
    med["dosageInstruction"][0]["doseAndRate"] = [{
        "doseQuantity": {"value": 1.5, "unit": "tabs"}}]
    con3 = fx.make_connection([fx.PATIENT_IG_P11, med])
    rows = run_sam(con3, "piqi-sam-medication-doseamount-isnumeric")
    assert rows and rows[0]["result"] == "pass"
    # a scalar (component-less) vital IS numeric
    scalar = fx.vital_obs("vs-scalar", 72.0, 0.0)
    del scalar["component"]
    scalar["valueQuantity"] = {"value": 72, "unit": "bpm"}
    con2 = fx.make_connection([fx.PATIENT_IG_P11, scalar])
    assert _results(run_sam(
        con2, "piqi-sam-vitalsign-resultvalue-isnumeric"))["vs-scalar"] == "pass"


def test_b1_timestamp_sams_widened():
    import copy

    ha_ts = copy.deepcopy(fx.HEALTH_ASSESSMENT_IG_P13)
    ha_ts["effectiveDateTime"] = "2024-11-14T10:30:00-07:00"
    con = fx.make_connection([
        fx.PATIENT_IG_P11, fx.BP_OBS_IG_P20, ha_ts,
    ])
    assert _results(run_sam(con, "piqi-sam-vitalsign-performeddatetime-istimestamp"))["vs-bp-1"] == "pass"
    assert _results(run_sam(con, "piqi-sam-healthassessment-performeddatetime-istimestamp"))["ha-1"] == "pass"
    # date-only performedDatetime FAILS IsTimestamp (AMUX-152 #25 doctrine)
    con2 = fx.make_connection([fx.PATIENT_IG_P11,
                               fx.HEALTH_ASSESSMENT_IG_P13])
    assert _results(run_sam(
        con2, "piqi-sam-healthassessment-performeddatetime-istimestamp"))["ha-1"] == "fail"


def test_b1_isvaliddate_widened():
    import copy

    device = copy.deepcopy(fx.DEVICE_IG_P17)
    device["patient"] = {"reference": "Patient/pat-1"}
    device["extension"] = device.get("extension", []) + [{
        "url": fx.PIQI_EXT + "implantationDate", "valueString": "2020-07-10"}]
    con = fx.make_connection([
        fx.PATIENT_IG_P11, fx.CONDITION_IG_P10, fx.ALLERGY_IG_P9,
        fx.IMMUNIZATION_IG_P14, device,
    ])
    for iid in ("piqi-sam-condition-onsetdate-isvaliddate",
                "piqi-sam-condition-resolutiondate-isvaliddate",
                "piqi-sam-allergy-effectivedate-isvaliddate",
                "piqi-sam-immunization-administrationdate-isvaliddate",
                "piqi-sam-immunization-expirationdate-isvaliddate",
                "piqi-sam-medicaldevice-implantationdate-isvaliddate"):
        rows = run_sam(con, iid)
        # absent/empty date ⇒ prerequisite unpopulated ⇒ row absence is OK
        assert all(r["result"] == "pass" for r in rows), iid

    bad = dict(fx.CONDITION_IG_P10)
    bad["id"] = "cond-bad"
    bad["onsetDateTime"] = "2020-02-30"
    con2 = fx.make_connection([fx.PATIENT_IG_P11, bad])
    assert _results(run_sam(con2, "piqi-sam-condition-onsetdate-isvaliddate"))["cond-bad"] == "fail"


def test_b1_future_and_past_date_sams():
    """[SG pp.13-14] Attr_IsFutureDate / Attr_IsPastDate, pure logic."""
    past = fx.patient_with_birthdate("1966-05-18")
    future = fx.patient_with_birthdate("2099-05-18")
    future["id"] = "pat-future"
    con = fx.make_connection([past, future])
    res = _results(run_sam(con, "piqi-sam-demographics-birthdate-ispastdate"))
    assert res["pat-1"] == "pass"
    assert res["pat-future"] == "fail"
    # malformed dates fail (not crash)
    bad = fx.patient_with_birthdate("not-a-date")
    bad["id"] = "pat-bad2"
    con2 = fx.make_connection([bad])
    assert _results(run_sam(con2, "piqi-sam-demographics-birthdate-ispastdate"))["pat-bad2"] == "fail"


def test_b1_observationvalue_isqualitative():
    """[SG p.21] qualitative = value types CE, CWE, CD, ST."""
    con = fx.make_connection([
        fx.PATIENT_IG_P11,
        fx.HEALTH_ASSESSMENT_IG_P13,      # CE-coded value
        fx.GLUCOSE_OBS_IG_P15,            # NM (quantity)
    ])
    res = _results(run_sam(con, "piqi-sam-healthassessment-resultvalue-isqualitative"))
    assert res["ha-1"] == "pass"
    res = _results(run_sam(con, "piqi-sam-labresult-resultvalue-isqualitative"))
    assert res["lab-1"] == "fail"


def test_b1_observationvalue_matchestype():
    """[SG p.21] value shape consistent with declared type."""
    con = fx.make_connection([
        fx.PATIENT_IG_P11, fx.GLUCOSE_OBS_IG_P15,
        # type says ST (string) but value parses numeric — guide examples
        # treat NM/ST consistency; a string-typed value passes here
        fx.lab_obs("lab-txt", "abc"),
    ])
    res = _results(run_sam(con, "piqi-sam-labresult-resultvalue-matchestype"))
    assert res["lab-1"] == "pass"       # NM with numeric text
    assert res["lab-txt"] == "pass"     # ST with text


def test_b1_class_hasduplicates_remaining_classes():
    dup = dict(fx.CONDITION_IG_P10)
    dup["id"] = "cond-dup-a"
    dup2 = dict(fx.CONDITION_IG_P10)
    dup2["id"] = "cond-dup-b"
    con = fx.make_connection([fx.PATIENT_IG_P11, dup, dup2])
    rows = run_sam(con, "piqi-sam-condition-hasduplicates")
    assert rows[0]["result"] == "pass"
    assert "cond-dup-a" in rows[0]["detail"]
    # catalog carries instances for every non-Demographics class
    ids = {s.instance_id for s in __import__(
        "fhir4ds.piqi.authoring", fromlist=["build_sam_catalog"]).build_sam_catalog()}
    for dc in ("allergy", "condition", "healthassessment", "immunization",
               "medication", "procedure", "medicaldevice"):
        assert any(i.startswith(f"{dc}-") and i.endswith("hasduplicates")
                   for i in ids), dc


def test_b1_has_type_ghost_not_implemented():
    """ObservationValue_HasType is a guide ghost (SG references, never
    defines) — a Joel decision; it must NOT appear in the catalog."""
    assert "ObservationValue_HasType" not in _catalog_mnemonics()


# ===========================================================================
# Batch 2 — rubric metadata fidelity (RG v1.2)
# ===========================================================================
def test_b2_informational_weight_zero_enforced():
    """[RG p.6] informational criteria have weight 0 (ValueError otherwise)."""
    with pytest.raises(ValueError, match="weight"):
        build_rubric("badw", "x", [{
            "sequence": 1, "data_class": "Demographics", "entity": "birthDate",
            "sam": "piqi-sam-demographics-birthdate-isvaliddate",
            "scoring_effect": "informational", "weight": 5, "criticality": False,
        }])
    # informational weight defaults to 0 when omitted
    lib, meta = build_rubric("okw", "x", [{
        "sequence": 1, "data_class": "Demographics", "entity": "birthDate",
        "sam": "piqi-sam-demographics-birthdate-isvaliddate",
        "scoring_effect": "informational", "criticality": False,
    }])
    assert meta[0]["weight"] == 0


def test_b2_informational_criticality_enforced():
    with pytest.raises(ValueError, match="criticality"):
        build_rubric("badc", "x", [{
            "sequence": 1, "data_class": "Demographics", "entity": "birthDate",
            "sam": "piqi-sam-demographics-birthdate-isvaliddate",
            "scoring_effect": "informational", "criticality": True,
        }])


def test_b2_scoring_weight_defaults_to_one():
    lib, meta = build_rubric("defw", "x", [{
        "sequence": 1, "data_class": "Demographics", "entity": "birthDate",
        "sam": "piqi-sam-demographics-birthdate-isvaliddate",
        "scoring_effect": "scoring", "criticality": False,
    }])
    assert meta[0]["weight"] == 1


def test_b2_name_overrides_reach_the_detail():
    """[RG p.5] success/failure name overrides replace the SAM-authored
    detail strings in the rubric SQL."""
    rubric = build_rubric("ovr", "override probe", [{
        "sequence": 1, "data_class": "Demographics", "entity": "birthDate",
        "sam": "piqi-sam-demographics-birthdate-isvaliddate",
        "scoring_effect": "scoring", "weight": 1, "criticality": False,
        "success_name_override": "birthdate OK per site rule",
        "failure_name_override": "birthdate BAD per site rule",
    }])
    con = fx.make_connection([fx.patient_with_birthdate("1966-13-45")])
    sc = evaluate_rubric(con, rubric, verbose=True)
    assert sc.issues[0].detail == "birthdate BAD per site rule"
    con2 = fx.make_connection([fx.patient_with_birthdate("1966-05-18")])
    from fhir4ds.piqi import piqi_resolver
    from fhir4ds.sqlquery import SQLQueryRunner
    lib = rubric[0] if isinstance(rubric, tuple) else rubric
    rows = SQLQueryRunner(con2, piqi_resolver()).execute(lib, {"patient_id": None})
    cols = ("patient_id", "element_id", "sequence", "data_class", "entity",
            "attributed_mnemonic", "scoring_effect", "weight", "criticality",
            "result", "detail")
    det = [dict(zip(cols, r))["detail"] for r in rows]
    assert det == ["birthdate OK per site rule"]


def test_b2_rubric_metadata_fields():
    """[RG pp.4-5] version/authority/model/source/dates/mnemonic."""
    rubric = build_rubric(
        "meta", "metadata probe",
        [{
            "sequence": 1, "data_class": "Demographics", "entity": "birthDate",
            "sam": "piqi-sam-demographics-birthdate-isvaliddate",
            "scoring_effect": "scoring", "weight": 1, "criticality": False,
        }],
        mnemonic="SiteBirthdateCheck", version="1.2.0",
        authority="PIQI Alliance sample adaptation",
        model={"versionMnemonic": "PCDM", "mnemonic": "v1.1",
               "version": "1.1", "extensionMnemonic": ""},
        source={"organizationUid": "urn:uuid:1111-2222",
                "organizationName": "Example Org"},
        creation_datetime="2026-11-20T09:00:00Z",
        modified_datetime="2026-11-20T09:30:00Z",
    )
    lib = rubric[0] if isinstance(rubric, tuple) else rubric
    assert lib["version"] == "1.2.0"
    m = lib["piqiRubric"]
    assert m["mnemonic"] == "SiteBirthdateCheck"
    assert m["name"] == "meta"
    assert m["description"] == "metadata probe"
    assert m["version"] == "1.2.0"
    assert m["authority"] == "PIQI Alliance sample adaptation"
    assert m["model"]["mnemonic"] == "v1.1"
    assert m["source"]["organizationName"] == "Example Org"
    assert m["creationDateTime"] == "2026-11-20T09:00:00Z"
    assert m["modifiedDateTime"] == "2026-11-20T09:30:00Z"


def test_b2_automatic_sequence_assignment():
    """[RG p.5] sequence 'assigned automatically based on the data class
    and entity' — criteria may omit sequence entirely."""
    lib, meta = build_rubric("autoseq", "auto sequence probe", [
        {"data_class": "LabResult", "entity": "test",
         "sam": "piqi-sam-labresult-test-iscomplete",
         "scoring_effect": "scoring", "weight": 1, "criticality": False},
        {"data_class": "Demographics", "entity": "birthDate",
         "sam": "piqi-sam-demographics-birthdate-isvaliddate",
         "scoring_effect": "scoring", "weight": 1, "criticality": False},
        {"data_class": "Demographics", "entity": "race",
         "sam": "piqi-sam-demographics-race-iscomplete",
         "scoring_effect": "scoring", "weight": 1, "criticality": False},
    ])
    seqs = [c["sequence"] for c in meta]
    assert seqs == [1, 2, 3]
    # ordering: Demographics before LabResult; birthDate before race
    assert [c["entity"] for c in meta] == ["birthDate", "race", "test"]
    # partial sequences still rejected
    with pytest.raises(ValueError, match="sequence"):
        build_rubric("mixseq", "x", [
            {"sequence": 1, "data_class": "Demographics", "entity": "birthDate",
             "sam": "piqi-sam-demographics-birthdate-isvaliddate",
             "scoring_effect": "scoring", "weight": 1, "criticality": False},
            {"data_class": "Demographics", "entity": "race",
             "sam": "piqi-sam-demographics-race-iscomplete",
             "scoring_effect": "scoring", "weight": 1, "criticality": False},
        ])


# ===========================================================================
# Batch 3 — code-system registry + Concept_HasRecognizedCodeSystem
# ===========================================================================
def test_b3_registry_structure_and_lookup():
    """[HB p.15] codeSystems JSON: mnemonic/name/identifier/aliases/
    terminologyServerStatus, built on the FHIR4-24 standard registry."""
    from fhir4ds.piqi import codesystems as cs

    entries = cs.code_system_registry()
    by_mnem = {e["mnemonic"]: e for e in entries}
    loinc = by_mnem["LOINC"]
    assert loinc["identifier"] == "http://loinc.org"
    assert "LNC" in loinc["aliases"]
    assert "http://loinc.org" in loinc["aliases"]
    assert loinc["terminologyServerStatus"] == "active"
    assert by_mnem["SNOMEDCT"]["identifier"] == "http://snomed.info/sct"
    # [HB p.15] ICD9CM carries deprecated status
    assert by_mnem["ICD9CM"]["terminologyServerStatus"] == "deprecated"
    # lookup resolves identifier, alias, OID spellings
    assert cs.resolve_code_system("LOINC") is loinc
    assert cs.resolve_code_system("http://loinc.org") is loinc
    assert cs.resolve_code_system("urn:oid:2.16.840.1.113883.6.1") is loinc
    assert cs.resolve_code_system("bogus-system") is None
    assert cs.is_recognized_code_system("SNOMEDCT")
    assert not cs.is_recognized_code_system("LCL")


def test_b3_registry_resource_packaged():
    from fhir4ds.piqi.authoring import generate_all

    text = generate_all()["codesystems.json"]
    data = json.loads(text)
    assert {"codeSystems": data["codeSystems"]}
    assert any(e["mnemonic"] == "LOINC" for e in data["codeSystems"])


def test_b3_concept_has_recognized_codesystem():
    """[SG p.18] recognized across registry identifier/alias/OID forms."""
    # CONDITION fixture uses the alias spelling "SNOMEDCT"
    con = fx.make_connection([fx.PATIENT_IG_P11, fx.CONDITION_IG_P10])
    rows = run_sam(con, "piqi-sam-condition-condition-hasrecognizedcodesystem")
    assert _results(rows)["cond-1"] == "pass"
    # unrecognized local system fails
    con2 = fx.make_connection([fx.PATIENT_IG_P11, fx.ALLERGY_IG_P9,
                               fx.MONOCYTES_OBS_SG_P16])
    # allergy substance uses alias "RXNORM" — recognized
    assert _results(run_sam(
        con2, "piqi-sam-allergy-substance-hasrecognizedcodesystem"))["all-1"] == "pass"
    # lab test carries LCL + LOINC + empty — LOINC arm recognizes it
    assert _results(run_sam(
        con2, "piqi-sam-labresult-test-hasrecognizedcodesystem"))["lab-mono"] == "pass"
    # a coding whose ONLY system is unrecognized fails
    con3 = fx.make_connection([
        fx.PATIENT_IG_P11,
        fx.lab_obs("lab-lcl", "x", code={"text": "T", "coding": [
            {"code": "X1", "display": "d", "system": "LCL"}]}),
    ])
    assert _results(run_sam(
        con3, "piqi-sam-labresult-test-hasrecognizedcodesystem"))["lab-lcl"] == "fail"


def test_b3_recognized_system_bound_across_classes():
    con = fx.make_connection([
        fx.PATIENT_IG_P11, fx.PROCEDURE_IG_P19, fx.MEDICATION_IG_P18,
        fx.HEALTH_ASSESSMENT_IG_P13,
    ])
    for iid in ("piqi-sam-procedure-procedure-hasrecognizedcodesystem",
                "piqi-sam-medication-medication-hasrecognizedcodesystem",
                "piqi-sam-healthassessment-assessment-hasrecognizedcodesystem"):
        rows = run_sam(con, iid)
        assert all(r["result"] == "pass" for r in rows), iid


# ===========================================================================
# Batch 4 — parameterized SAM execution
# ===========================================================================
def test_b4_matches_regex_parameterized_sam():
    """Attr_MatchesRegex as a public, parameter-taking authored SAM."""
    from fhir4ds.piqi import build_parameterized_sam, run_parameterized_sam

    sam = build_parameterized_sam(
        "Attr_MatchesRegex", "LabResult", "test", column="test_text")
    con = fx.make_connection([fx.PATIENT_IG_P11,
                              fx.lab_obs("lab-g", "x", code={"text": "Glucose, Serum",
                                        "coding": [{"code": "2345-7", "system": fx.LOINC}]}),
                              fx.lab_obs("lab-o", "x", code={"text": "Other",
                                        "coding": [{"code": "0000-0", "system": fx.LOINC}]})])
    rows = run_parameterized_sam(
        con, sam, {"pattern": "^Glucose"}, patient_id=None)
    res = _results(rows)
    assert res["lab-g"] == "pass"
    assert res["lab-o"] == "fail"
    # injection payload in the parameter is a bound VALUE, never SQL text
    rows2 = run_parameterized_sam(
        con, sam, {"pattern": "' OR 1=1 --"}, patient_id=None)
    assert all(r["result"] == "fail" for r in rows2)


def test_b4_in_list_parameterized_sam():
    from fhir4ds.piqi import build_parameterized_sam, run_parameterized_sam

    sam = build_parameterized_sam(
        "Attr_InList", "LabResult", "resultStatus", column="resultStatus_text")
    con = fx.make_connection([fx.PATIENT_IG_P11, fx.GLUCOSE_OBS_IG_P15])
    rows = run_parameterized_sam(con, sam, {"values": "F,P"}, patient_id=None)
    assert _results(rows)["lab-1"] == "pass"
    rows = run_parameterized_sam(con, sam, {"values": "P"}, patient_id=None)
    assert _results(rows)["lab-1"] == "fail"


def test_b4_observationvaluetype_inlist_parameterized():
    from fhir4ds.piqi import build_parameterized_sam, run_parameterized_sam

    sam = build_parameterized_sam(
        "ObservationValueType_InList", "LabResult", "resultValue")
    con = fx.make_connection([fx.PATIENT_IG_P11, fx.GLUCOSE_OBS_IG_P15])
    rows = run_parameterized_sam(con, sam, {"valueTypes": "NM,ST"}, patient_id=None)
    assert _results(rows)["lab-1"] == "pass"
    rows = run_parameterized_sam(con, sam, {"valueTypes": "CE"}, patient_id=None)
    assert _results(rows)["lab-1"] == "fail"


def test_b4_parameterized_sam_declares_parameters():
    from fhir4ds.piqi import build_parameterized_sam

    sam = build_parameterized_sam(
        "Attr_MatchesRegex", "LabResult", "test", column="test_text")
    params = {p["name"] for p in sam["parameter"]}
    assert "pattern" in params
    # parameterized SAMs are NOT packaged (dependency views cannot bind
    # parameters — SOF-SQ-03 doctrine)
    from fhir4ds.piqi.authoring import generate_all
    assert not any("matchesregex" in k for k in generate_all())


# ===========================================================================
# Batch 5 — terminology SAMs (endpoint PROTOCOL; stub in tests)
# ===========================================================================
class _StubEndpoint:
    """Deterministic TerminologyEndpoint test double (protocol-shaped)."""

    def __init__(self):
        self.expand_calls: list[str] = []

    def expand(self, valueset_url: str):
        self.expand_calls.append(valueset_url)
        if "vitals" in valueset_url:
            return [
                _CodeRef("http://loinc.org", "8867-4", "Heart rate"),
                _CodeRef("http://loinc.org", "8480-5", "Systolic BP"),
            ]
        if valueset_url.startswith("http://loinc.org?fhir_vs"):
            return [_CodeRef("http://loinc.org", "2345-7", "Glucose Ser/Plas"),
                    _CodeRef("http://loinc.org", "742-7", "Monocytes")]
        return []

    def expand_intensional(self, value_set):
        return []

    def search_text(self, query, category, *, mode="hybrid"):
        return []

    def search_batch(self, queries, *, mode="hybrid"):
        return [[] for _ in queries]


class _CodeRef:
    def __init__(self, system, code, display=None):
        self.system = system
        self.code = code
        self.display = display


def test_b5_valid_member_via_endpoint_valueset():
    from fhir4ds.piqi import run_terminology_sam

    stub = _StubEndpoint()
    con = fx.make_connection([fx.PATIENT_IG_P11, fx.MONOCYTES_OBS_SG_P16])
    rows = run_terminology_sam(
        con, "Concept_IsValidMember", data_class="LabResult", entity="test",
        valueset="http://example.org/ValueSet/vitals", endpoint=stub)
    # 742-7 is NOT in the vitals expansion — membership fails (honest
    # verdict, still endpoint-assessed)
    assert _results(rows)["lab-mono"] == "fail"
    assert rows[0]["provenance"]["source"] == "terminology_endpoint"
    # the fhir_vs code-system arm DOES contain 742-7 — membership passes
    rows = run_terminology_sam(
        con, "Concept_IsValidMember", data_class="LabResult", entity="test",
        valueset="http://loinc.org?fhir_vs", endpoint=stub)
    assert _results(rows)["lab-mono"] == "pass"


def test_b5_valid_member_no_endpoint_could_not_assess():
    from fhir4ds.piqi import run_terminology_sam

    con = fx.make_connection([fx.PATIENT_IG_P11, fx.MONOCYTES_OBS_SG_P16])
    rows = run_terminology_sam(
        con, "Concept_IsValidMember", data_class="LabResult", entity="test",
        valueset="http://example.org/ValueSet/vitals")
    assert rows
    assert all(r["result"] == "could not assess" for r in rows)


def test_b5_valid_member_via_local_valueset_cache():
    """Local ValueSet cache membership when the VS is loaded in the
    connection (valueset_codes table)."""
    from fhir4ds.piqi import run_terminology_sam

    con = fx.make_connection([fx.PATIENT_IG_P11, fx.MONOCYTES_OBS_SG_P16])
    con.execute(
        "CREATE TABLE valueset_codes (url VARCHAR, system VARCHAR, "
        "code VARCHAR, display VARCHAR)")
    con.execute(
        "INSERT INTO valueset_codes VALUES "
        "('http://example.org/ValueSet/vitals', 'http://loinc.org', "
        "'742-7', 'Monocytes')")
    rows = run_terminology_sam(
        con, "Concept_IsValidMember", data_class="LabResult", entity="test",
        valueset="http://example.org/ValueSet/vitals")
    assert rows[0]["provenance"]["source"] == "local_valueset_cache"
    assert _results(rows)["lab-mono"] == "pass"


def test_b5_is_consistent_local_cache_display():
    from fhir4ds.piqi import run_terminology_sam

    con = fx.make_connection([fx.PATIENT_IG_P11, fx.MONOCYTES_OBS_SG_P16])
    con.execute(
        "CREATE TABLE valueset_codes (url VARCHAR, system VARCHAR, "
        "code VARCHAR, display VARCHAR)")
    # display matches the fixture's LOINC coding display
    con.execute(
        "INSERT INTO valueset_codes VALUES "
        "('http://example.org/ValueSet/vs', 'http://loinc.org', '742-7', "
        "'MONOCYTES:NCNC:PT:BLD:QN:AUTOMATED COUNT')")
    rows = run_terminology_sam(
        con, "Concept_IsConsistent", data_class="LabResult", entity="test",
        valueset="http://example.org/ValueSet/vs")
    assert _results(rows)["lab-mono"] == "pass"
    # divergent display fails
    con.execute("UPDATE valueset_codes SET display = 'Something Else'")
    rows = run_terminology_sam(
        con, "Concept_IsConsistent", data_class="LabResult", entity="test",
        valueset="http://example.org/ValueSet/vs")
    assert _results(rows)["lab-mono"] == "fail"


def test_b5_is_active_is_protocol_gap():
    """Concept_IsActive needs a code-lookup op the TerminologyEndpoint
    protocol does not define — could-not-assess + documented decision."""
    from fhir4ds.piqi import run_terminology_sam

    con = fx.make_connection([fx.PATIENT_IG_P11, fx.MONOCYTES_OBS_SG_P16])
    rows = run_terminology_sam(
        con, "Concept_IsActive", data_class="LabResult", entity="test",
        endpoint=_StubEndpoint())
    assert all(r["result"] == "could not assess" for r in rows)


def test_b5_live_endpoint_integration_optional():
    """OPTIONAL live-path integration — skipped unless the sidecar env
    var is set (never required in the test suite)."""
    import os

    endpoint_url = os.getenv("FHIR4DS_PIQI_TEST_TERMINOLOGY_URL")
    if not endpoint_url:
        pytest.skip("FHIR4DS_PIQI_TEST_TERMINOLOGY_URL not set")
    from fhir4ds.cql.terminology.http_adapter import HTTPTerminologyEndpoint

    con = fx.make_connection([fx.PATIENT_IG_P11, fx.MONOCYTES_OBS_SG_P16])
    rows = run_terminology_sam(
        con, "Concept_IsValidMember", data_class="LabResult", entity="test",
        valueset="http://loinc.org?fhir_vs",
        endpoint=HTTPTerminologyEndpoint(endpoint_url))
    assert rows
    assert rows[0]["provenance"]["source"] == "terminology_endpoint"


# ===========================================================================
# Cross-cutting: packaged resources + determinism
# ===========================================================================
def test_packaged_resources_consistent():
    """Regenerated packaged resources == generate_all() output."""
    from fhir4ds.piqi.authoring import generate_all
    from pathlib import Path

    res_dir = Path(__file__).parent.parent / "resources"
    for rel, text in generate_all().items():
        assert (res_dir / rel).read_text(encoding="utf-8") == text, rel


def test_shuffle_invariance_of_generated_catalog():
    """generate_all() is deterministic across calls (authoring order is
    fully driven by the catalog, never by set iteration)."""
    from fhir4ds.piqi.authoring import generate_all

    assert generate_all() == generate_all()
