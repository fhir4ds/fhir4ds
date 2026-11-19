"""PIQI acceptance tests — FDD §5 (FEATURE_PIQI_FRAMEWORK.md).

Authored BEFORE implementation per Joel's before/after doctrine: the
RED run is archived at
``fhir4ds-private/docs/prompts/.ai_loop/piqi_acceptance_red.txt`` and the
identical suite's GREEN run at ``piqi_acceptance_green.txt``.

Fixture citations inline ([HB]/[IG]/[SG]/[RG] page numbers).
"""

from __future__ import annotations

import hashlib
import json
import typing as _t

import pytest

from . import fixtures as fx
from fhir4ds.piqi import (
    PIQIIssue,
    PIQIScorecard,
    build_rubric,
    evaluate_rubric,
    get_sam,
    run_sam,
)
from fhir4ds.piqi.taxonomy import PIQIDimension, dimension_for_sam, resolve_dimension


def _results(rows: _t.List[dict]) -> dict:
    """Map element_id -> result for SAM rows."""
    return {r["element_id"]: r["result"] for r in rows}


# ===========================================================================
# A. Data-model layer (guides' example payloads → PIQI views)
# ===========================================================================
def test_a01_glucose_labresult_view_row():
    """[IG pp.15-16] glucose lab result → piqi_labresult row shape."""
    from fhir4ds.piqi import load_piqi_views

    con = fx.make_connection([fx.PATIENT_IG_P11, fx.GLUCOSE_OBS_IG_P15])
    load_piqi_views(con)
    rows = con.execute('SELECT * FROM piqi."piqi_labresult"').fetchall()
    assert len(rows) == 1
    cols = [d[0] for d in con.execute(
        'DESCRIBE SELECT * FROM piqi."piqi_labresult"').fetchall()]
    row = dict(zip(cols, rows[0]))
    assert row["patient_id"] == "pat-1"
    assert row["element_id"] == "lab-1"
    assert row["test_text"] == "Glucose, Serum"
    assert any('"2345-7"' in c for c in row["test_codings"])
    assert float(row["resultValue_number"]) == 126.0
    assert float(row["referenceRange_low_value"]) == 70.0
    assert float(row["referenceRange_high_value"]) == 100.0
    assert row["resultStatus_text"] == "F"  # HL7 v2 F = final
    assert row["resultUnit_text"] == "mg/dL"
    assert row["interpretation_text"] == "H"
    assert row["specimenType_text"] == "blood"


def test_a02_demographics_view_row():
    """[IG pp.11-12] demographics fixture → all 9 PIQI attributes."""
    from fhir4ds.piqi import load_piqi_views

    con = fx.make_connection([fx.PATIENT_IG_P11])
    load_piqi_views(con)
    cols = [d[0] for d in con.execute(
        'DESCRIBE SELECT * FROM piqi."piqi_demographics"').fetchall()]
    rows = con.execute('SELECT * FROM piqi."piqi_demographics"').fetchall()
    assert len(rows) == 1
    row = dict(zip(cols, rows[0]))
    assert row["birthDate"] == "1966-05-18"
    assert row["deathDate"] in ("", None)  # guide's empty deathDate
    assert row["birthSex_text"] == "M"
    assert row["deceased_text"] == "N"
    assert row["ethnicity_text"] == "U"
    assert row["genderIdentity_text"] == "male gender"
    assert row["primaryLanguage_text"] == "English"
    assert row["maritalStatus_text"] == "M"
    assert row["race_text"] == "Other Race"
    assert any('"2131-1"' in c for c in row["race_codings"])


def test_a03_monocytes_multicoding_concept():
    """[SG p.16] MONOCYTES 3-coding fixture materializes all codings."""
    from fhir4ds.piqi import load_piqi_views

    con = fx.make_connection([fx.PATIENT_IG_P11, fx.MONOCYTES_OBS_SG_P16])
    load_piqi_views(con)
    cols = [d[0] for d in con.execute(
        'DESCRIBE SELECT * FROM piqi."piqi_labresult"').fetchall()]
    rows = con.execute('SELECT * FROM piqi."piqi_labresult"').fetchall()
    row = dict(zip(cols, rows[0]))
    assert row["test_text"].strip().startswith("MONOCYTES")
    assert len(row["test_codings"]) == 3
    assert any('"742-7"' in c for c in row["test_codings"])
    # third coding carries the guide's EMPTY system
    assert any(json.loads(c).get("system", "") == "" for c in row["test_codings"])


def test_a04_bp_vitalsign_number_pair():
    """[IG p.20] BP 130/80 → resultValue number/number2 pair."""
    from fhir4ds.piqi import load_piqi_views

    con = fx.make_connection([fx.PATIENT_IG_P11, fx.BP_OBS_IG_P20])
    load_piqi_views(con)
    cols = [d[0] for d in con.execute(
        'DESCRIBE SELECT * FROM piqi."piqi_vital_sign"').fetchall()]
    rows = con.execute('SELECT * FROM piqi."piqi_vital_sign"').fetchall()
    assert len(rows) == 1
    row = dict(zip(cols, rows[0]))
    assert float(row["resultValue_number"]) == 130.0
    assert float(row["resultValue_number2"]) == 80.0
    assert row["vitalSign_text"] == "Blood Pressure"


def test_a05_other_data_class_row_shapes():
    """[IG pp.9,10,13,14,17,18,19] one row-shape test per remaining class."""
    from fhir4ds.piqi import load_piqi_views

    con = fx.make_connection([
        fx.PATIENT_IG_P11, fx.ALLERGY_IG_P9, fx.CONDITION_IG_P10,
        fx.HEALTH_ASSESSMENT_IG_P13, fx.IMMUNIZATION_IG_P14,
        fx.MEDICATION_IG_P18, fx.PROCEDURE_IG_P19, fx.DEVICE_IG_P17,
    ])
    load_piqi_views(con)

    def one_row(view):
        cols = [d[0] for d in con.execute(
            f'DESCRIBE SELECT * FROM piqi."{view}"').fetchall()]
        rows = con.execute(f'SELECT * FROM piqi."{view}"').fetchall()
        assert len(rows) == 1, (view, rows)
        return dict(zip(cols, rows[0]))

    a = one_row("piqi_allergy")
    assert a["substance_text"] == "cephalexin"
    assert a["severity_text"] == "Severe"
    assert a["effectiveDate"] == "2024-11-14"

    c = one_row("piqi_condition")
    assert c["condition_text"] == "Type 2 diabetes mellitus"
    assert c["conditionStatus_text"] == "confirmed"
    assert c["onsetDate"] == "2020-11-14"
    assert c["resolutionDate"] in ("", None)

    h = one_row("piqi_health_assessment")
    assert h["assessment_text"] == "TOBACCO SMOKING STATUS"
    assert h["resultValue_text"] == "Current Heavy tobacco smoker"

    i = one_row("piqi_immunization")
    assert i["immunization_text"] == "Influenza, seasonal, injectable"
    assert i["administrationDate"] == "2024-06-01"
    assert i["expirationDate"] == "2025-05-18"
    assert i["reaction_text"] == "Wheal"

    m = one_row("piqi_medication_request")
    assert m["medication_text"] == "ibuprofen 600 MG Oral Tablet"
    assert m["doseRoute_text"] == "Oral"
    assert m["instructions"] == "take 1 tablet QID PRN"
    assert m["fillStatus_text"] == "completed"

    p = one_row("piqi_procedure")
    assert p["procedure_text"] == "Other excision of appendix NOS"
    assert p["procedureDateTime"] == "2020-11-14"
    assert p["procedureReason_text"] == "Acute appendicitis"

    d = one_row("piqi_medical_device")
    assert d["deviceType_text"] == "Glucose Monitor"
    assert d["deviceID_text"] == "04719871820322"
    assert d["deviceStatus_text"] == "active"


# ===========================================================================
# B. SAM layer (pass/fail semantics from the guide tables)
# ===========================================================================
def test_b06_attr_ispopulated_semantics():
    """[SG p.11] populated → pass; empty/absent → fail; complex → text."""
    con = fx.make_connection([
        fx.PATIENT_IG_P11,
        fx.GLUCOSE_OBS_IG_P15,                                  # populated
        fx.lab_obs("lab-empty", {"value": {"value": None}} if False else {"value": None}),  # absent value
        fx.lab_obs("lab-blank", ""),                            # empty string value
    ])
    rows = run_sam(con, "piqi-sam-labresult-resultvalue-ispopulated")
    res = _results(rows)
    assert res["lab-1"] == "pass"
    assert res["lab-empty"] == "fail"
    assert res["lab-blank"] == "fail"
    det = {r["element_id"]: r["detail"] for r in rows}
    assert "resultValue" in det["lab-blank"]


def test_b07_concept_best_case_aggregates():
    """[SG p.16] on the 3-coding fixture all four aggregate SAMs pass."""
    con = fx.make_connection([fx.PATIENT_IG_P11, fx.MONOCYTES_OBS_SG_P16])
    for name, mnemonic in [
        ("piqi-sam-labresult-test-hascode", "Concept_HasCode"),
        ("piqi-sam-labresult-test-hascodesystem", "Concept_HasCodeSystem"),
        ("piqi-sam-labresult-test-hasdisplay", "Concept_HasDisplay"),
        ("piqi-sam-labresult-test-iscomplete", "Concept_IsComplete"),
    ]:
        rows = run_sam(con, name)
        assert len(rows) == 1, (name, rows)
        assert rows[0]["sam_mnemonic"] == mnemonic
        assert rows[0]["result"] == "pass", (name, rows[0])


def test_b08_concept_iscomplete_fails_without_complete_coding():
    """[SG p.16] Is Complete fails when no single coding has all 3 parts."""
    con = fx.make_connection([
        fx.PATIENT_IG_P11,
        # each coding is missing exactly one part
        fx.lab_obs("lab-inc", "x", code={"text": "Incomplete Concept", "coding": [
            {"code": "c1", "display": "has both", "system": ""},
            {"code": "", "display": "d2", "system": "S"},
            {"code": "c3", "display": "", "system": "S"},
        ]}),
    ])
    rows = run_sam(con, "piqi-sam-labresult-test-iscomplete")
    assert _results(rows)["lab-inc"] == "fail"


def test_b09_prerequisite_attribution():
    """[HB p.21] unpopulated test ⇒ IsComplete emits NO rows; the
    IsPopulated FAIL carries Availability.Unpopulated."""
    con = fx.make_connection([
        fx.PATIENT_IG_P11,
        fx.lab_obs("lab-nocode", "x", code={"text": "", "coding": []}),
    ])
    iso = run_sam(con, "piqi-sam-labresult-test-iscomplete")
    assert iso == []  # row absence = could-not-assess
    pop = run_sam(con, "piqi-sam-labresult-test-ispopulated")
    assert _results(pop)["lab-nocode"] == "fail"
    assert pop[0]["sam_mnemonic"] == "Attr_IsPopulated"
    dim = dimension_for_sam("Attr_IsPopulated")
    assert dim is PIQIDimension.AV_UNPOP
    assert dim.category == "Availability"
    assert dim.name == "Unpopulated"


def test_b10_attr_isvaliddate():
    """[SG p.9] valid/invalid dates over Demographics.birthDate."""
    bad = fx.patient_with_birthdate("1966-13-45")
    bad["id"] = "pat-bad"
    con = fx.make_connection([fx.patient_with_birthdate("1966-05-18"), bad])
    rows = run_sam(con, "piqi-sam-demographics-birthdate-isvaliddate")
    res = _results(rows)
    assert res["pat-1"] == "pass"
    assert res["pat-bad"] == "fail"


def test_b11_numeric_sam_truth_table():
    """[SG pp.11-12] IsNumeric/IsInteger/IsDecimal/IsPositiveNumber."""
    con = fx.make_connection([
        fx.PATIENT_IG_P11,
        fx.lab_obs("n-int", "126"),
        fx.lab_obs("n-dec", "12.5"),
        fx.lab_obs("n-neg", "-3"),
        fx.lab_obs("n-txt", "abc"),
        fx.lab_obs("n-blank", ""),
    ])

    def res(name):
        return _results(run_sam(con, name))

    assert res("piqi-sam-labresult-resultvalue-isnumeric") == {
        "n-int": "pass", "n-dec": "pass", "n-neg": "pass", "n-txt": "fail"}
    assert res("piqi-sam-labresult-resultvalue-isinteger") == {
        "n-int": "pass", "n-dec": "fail", "n-neg": "pass", "n-txt": "fail"}
    assert res("piqi-sam-labresult-resultvalue-isdecimal") == {
        "n-int": "fail", "n-dec": "pass", "n-neg": "fail", "n-txt": "fail"}
    assert res("piqi-sam-labresult-resultvalue-ispositivenumber") == {
        "n-int": "pass", "n-dec": "pass", "n-neg": "fail", "n-txt": "fail"}


def test_b12_rangevalue_complete_and_valid():
    """[SG p.22] 14-88 passes; inverted fails; missing high incomplete."""
    con = fx.make_connection([
        fx.PATIENT_IG_P11,
        fx.lab_obs("r-ok", "x",
                   reference_range={"text": "14-88", "low": {"value": 14},
                                    "high": {"value": 88}}),
        fx.lab_obs("r-inv", "x",
                   reference_range={"text": "100-70", "low": {"value": 100},
                                    "high": {"value": 70}}),
        fx.lab_obs("r-miss", "x",
                   reference_range={"text": "14-", "low": {"value": 14}}),
    ])
    assert _results(run_sam(con, "piqi-sam-labresult-referencerange-rangeiscomplete")) == {
        "r-ok": "pass", "r-inv": "pass", "r-miss": "fail"}
    # IsValid has IsComplete as prerequisite ⇒ r-miss row absent
    assert _results(run_sam(con, "piqi-sam-labresult-referencerange-rangeisvalid")) == {
        "r-ok": "pass", "r-inv": "fail"}


def test_b13_class_hasduplicates():
    """[SG p.25] duplicate (test, performedDateTime) lab elements."""
    dup = fx.lab_obs("dup-a", "x", code={"text": "Glucose, Serum",
                                         "coding": [{"code": "2345-7", "system": fx.LOINC}]})
    dup2 = fx.lab_obs("dup-b", "x", code={"text": "Glucose, Serum",
                                          "coding": [{"code": "2345-7", "system": fx.LOINC}]})
    con = fx.make_connection([fx.PATIENT_IG_P11, dup, dup2])
    rows = run_sam(con, "piqi-sam-labresult-hasduplicates")
    assert len(rows) == 1
    # guide aliases: Success = "Has duplicates"
    assert rows[0]["result"] == "pass"
    assert rows[0]["sam_mnemonic"] == "Class_HasDuplicates"
    assert "dup-a" in rows[0]["detail"] and "dup-b" in rows[0]["detail"]

    con2 = fx.make_connection([fx.PATIENT_IG_P11, dup,
                               fx.lab_obs("other", "x")])
    rows2 = run_sam(con2, "piqi-sam-labresult-hasduplicates")
    assert rows2[0]["result"] == "fail"


def test_b14_could_not_assess_is_row_absence():
    """[SG p.5] "could not assess" is represented by row absence only."""
    con = fx.make_connection([
        fx.PATIENT_IG_P11,
        fx.lab_obs("lab-nocode2", "x", code={"text": "", "coding": []}),
    ])
    rows = run_sam(con, "piqi-sam-labresult-test-iscomplete")
    assert rows == []
    # result domain is pass/fail only — never a third value
    for r in run_sam(con, "piqi-sam-labresult-test-ispopulated"):
        assert r["result"] in ("pass", "fail")


# ===========================================================================
# C. Rubric + scorecard layer (the guide's own arithmetic)
# ===========================================================================
def test_c15_sample_rubric_reproduced():
    """[RG p.7] sample rubric on the [IG p.11] fixture: 1/1, index 100."""
    con = fx.make_connection([fx.PATIENT_IG_P11])
    sc = evaluate_rubric(con, "sample", message_id="msg-1",
                         data_provider_id="prov-1", data_source_id="src-1")
    assert isinstance(sc, PIQIScorecard)
    assert sc.message_id == "msg-1"
    assert sc.data_provider_id == "prov-1"
    assert sc.data_source_id == "src-1"
    assert sc.potential_item_score == 1
    assert sc.total_item_score == 1
    assert sc.piqi_index == 100.0
    assert sc.critical_failure_count == 0
    assert sc.data_class_frequency == {"Demographics": 1}
    # criterion 2 is informational — weighted score not used (weights 1/0)
    assert sc.potential_weighted_item_score is None
    assert sc.total_weighted_item_score is None
    assert sc.piqi_weighted_index is None


def test_c16_sample_rubric_invalid_birthdate():
    """[RG p.7] on mutated fixture (birthDate '1966-13-45'): 0/1, index 0."""
    con = fx.make_connection([fx.patient_with_birthdate("1966-13-45")])
    sc = evaluate_rubric(con, "sample", message_id="m", verbose=True)
    assert sc.potential_item_score == 1
    assert sc.total_item_score == 0
    assert sc.piqi_index == 0.0
    assert len(sc.issues) == 1
    issue = sc.issues[0]
    assert isinstance(issue, PIQIIssue)
    assert issue.data_class == "Demographics"
    assert issue.entity == "birthDate"
    assert issue.sam_mnemonic == "Attr_IsValidDate"
    assert issue.dimension is PIQIDimension.AC_FMT  # Accuracy.InvalidFormat


def test_c17_conditional_sam_skip_arithmetic():
    """[HB p.23] empty genderIdentity ⇒ criterion 2 contributes neither
    numerator nor denominator (informational statistics only)."""
    con = fx.make_connection([fx.patient_with_empty_gender_identity()])
    sc = evaluate_rubric(con, "sample")
    assert sc.potential_item_score == 1  # unchanged
    assert sc.total_item_score == 1
    assert sc.piqi_index == 100.0
    # the informational item itself still FAILS (statistics present)
    pop = run_sam(con, "piqi-sam-demographics-genderidentity-ispopulated")
    assert _results(pop)["pat-1"] == "fail"


def test_c18_prerequisite_failure_arithmetic():
    """[HB p.23] prereq fail ⇒ denominator +1, numerator +0, attributed to
    the PREREQUISITE's dimension (distinct from conditional skip)."""
    # single-criterion rubric: Attr_IsValidDate(birthDate), no conditional
    rubric = build_rubric("prereq_arithmetic", "prereq arithmetic probe", [{
        "sequence": 1, "data_class": "Demographics", "entity": "birthDate",
        "sam": "piqi-sam-demographics-birthdate-isvaliddate",
        "scoring_effect": "scoring", "weight": 1, "criticality": False,
    }])
    p = fx.patient_with_birthdate("")  # unpopulated birthDate
    con = fx.make_connection([p])
    sc = evaluate_rubric(con, rubric, verbose=True)
    assert sc.potential_item_score == 1
    assert sc.total_item_score == 0
    assert sc.piqi_index == 0.0
    assert len(sc.issues) == 1
    # failure is attributed to the PREREQUISITE SAM + its dimension
    assert sc.issues[0].sam_mnemonic == "Attr_IsPopulated"
    assert sc.issues[0].dimension is PIQIDimension.AV_UNPOP


def test_c19_weighted_scoring_diverges():
    """[HB p.23] weights 1 and 3 ⇒ PIQI Index and Weighted Index diverge."""
    rubric = build_rubric("weighted", "weighted probe", [
        {"sequence": 1, "data_class": "Demographics", "entity": "birthDate",
         "sam": "piqi-sam-demographics-birthdate-isvaliddate",
         "scoring_effect": "scoring", "weight": 1, "criticality": False},
        {"sequence": 2, "data_class": "Demographics", "entity": "deathDate",
         "sam": "piqi-sam-demographics-deathdate-isvaliddate",
         "scoring_effect": "scoring", "weight": 3, "criticality": False},
    ])
    # birthDate valid; deathDate populated-but-invalid ("not-a-date")
    p = fx.patient_with_birthdate("1966-05-18")
    for e in p["extension"]:
        if e["url"] == fx.PIQI_EXT + "deathDate":
            e["valueString"] = "not-a-date"
    con = fx.make_connection([p])
    sc = evaluate_rubric(con, rubric)
    assert sc.potential_item_score == 2
    assert sc.total_item_score == 1
    assert sc.piqi_index == 50.0
    assert sc.potential_weighted_item_score == 4
    assert sc.total_weighted_item_score == 1
    assert sc.piqi_weighted_index == 25.0


def test_c20_critical_failure_count():
    """[HB p.23] critical criterion failing ⇒ count 1, index unaffected."""
    rubric = build_rubric("critical", "criticality probe", [
        {"sequence": 1, "data_class": "Demographics", "entity": "birthDate",
         "sam": "piqi-sam-demographics-birthdate-isvaliddate",
         "scoring_effect": "scoring", "weight": 1, "criticality": True},
    ])
    con = fx.make_connection([fx.patient_with_birthdate("1966-13-45")])
    sc = evaluate_rubric(con, rubric)
    assert sc.potential_item_score == 1
    assert sc.total_item_score == 0
    assert sc.piqi_index == 0.0
    assert sc.critical_failure_count == 1

    ok = evaluate_rubric(
        fx.make_connection([fx.patient_with_birthdate("1966-05-18")]), rubric)
    assert ok.critical_failure_count == 0
    assert ok.piqi_index == 100.0


def test_c21_scorecard_field_contract():
    """[HB p.24] every scorecard field present and named per the guide."""
    con = fx.make_connection([fx.PATIENT_IG_P11, fx.GLUCOSE_OBS_IG_P15])
    sc = evaluate_rubric(con, "sample", message_id="m1", data_provider_id="dp1",
                         data_source_id="ds1", verbose=True)
    d = sc.to_dict()
    for key in ("MessageID", "DataProviderID", "DataSourceID",
                "PotentialItemScore", "TotalItemScore", "PIQIIndex",
                "CriticalFailureCount", "DataClassFrequency"):
        assert key in d, key
    assert d["MessageID"] == "m1"
    assert d["PotentialItemScore"] == 1
    assert d["TotalItemScore"] == 1
    assert d["PIQIIndex"] == 100.0
    assert d["CriticalFailureCount"] == 0
    # Data Class Frequency counts only rubric-referenced classes
    # (glucose Observation present but LabResult not referenced by rubric)
    assert d["DataClassFrequency"] == {"Demographics": 1}


def test_c22_dimension_rollup():
    """Failures across Availability + Accuracy roll up per category/dimension."""
    rubric = build_rubric("rollup", "dimension rollup probe", [
        {"sequence": 1, "data_class": "Demographics", "entity": "birthDate",
         "sam": "piqi-sam-demographics-birthdate-isvaliddate",
         "scoring_effect": "scoring", "weight": 1, "criticality": False},
        {"sequence": 2, "data_class": "Demographics", "entity": "deathDate",
         "sam": "piqi-sam-demographics-deathdate-isvaliddate",
         "scoring_effect": "scoring", "weight": 1, "criticality": False},
        {"sequence": 3, "data_class": "LabResult", "entity": "resultValue",
         "sam": "piqi-sam-labresult-resultvalue-ispopulated",
         "scoring_effect": "scoring", "weight": 1, "criticality": False},
        {"sequence": 4, "data_class": "LabResult", "entity": "test",
         "sam": "piqi-sam-labresult-test-iscomplete",
         "scoring_effect": "scoring", "weight": 1, "criticality": False},
    ])
    p = fx.patient_with_birthdate("1966-13-45")  # Accuracy.InvalidFormat fail
    for e in p["extension"]:
        if e["url"] == fx.PIQI_EXT + "deathDate":
            e["valueString"] = "not-a-date"
    labs = [
        fx.lab_obs("lab-v", "x"),                                     # healthy
        fx.lab_obs("lab-nov", {"value": None}),                       # resultValue unpopulated
        # test text populated but no complete coding → IsComplete's OWN fail
        fx.lab_obs("lab-inc", "x", code={"text": "Incomplete Concept", "coding": [
            {"code": "c1", "system": ""}]}),
    ]
    con = fx.make_connection([p] + labs)
    sc = evaluate_rubric(con, rubric, verbose=True)
    roll = sc.dimension_rollup
    assert roll["Accuracy"]["InvalidFormat"] == 2     # birthDate + deathDate
    assert roll["Availability"]["Unpopulated"] == 1   # resultValue
    assert roll["Availability"]["Incomplete"] == 1    # Concept_IsComplete own fail
    # items: 2 demographics + 3 resultValue rows + 3 test rows
    assert sc.potential_item_score == 8
    assert sc.total_item_score == 4


# ===========================================================================
# D. Cross-cutting
# ===========================================================================
def test_d23_determinism_hash():
    """Two consecutive evaluate_rubric runs → identical rows + JSON hash."""
    con = fx.make_connection([fx.PATIENT_IG_P11, fx.GLUCOSE_OBS_IG_P15,
                              fx.MONOCYTES_OBS_SG_P16])
    from fhir4ds.piqi import piqi_resolver
    from fhir4ds.sqlquery import SQLQueryRunner

    runner1 = SQLQueryRunner(con, piqi_resolver())
    rows1 = runner1.execute(_rubric_dict("sample"), {"patient_id": None})
    rows2 = SQLQueryRunner(con, piqi_resolver()).execute(
        _rubric_dict("sample"), {"patient_id": None})
    assert rows1 == rows2

    sc1 = evaluate_rubric(con, "sample", message_id="m", verbose=True)
    sc2 = evaluate_rubric(con, "sample", message_id="m", verbose=True)
    h1 = hashlib.sha256(json.dumps(sc1.to_dict(), sort_keys=False,
                                   default=str).encode()).hexdigest()
    h2 = hashlib.sha256(json.dumps(sc2.to_dict(), sort_keys=False,
                                   default=str).encode()).hexdigest()
    assert h1 == h2


def _rubric_dict(name):
    from fhir4ds.piqi import get_rubric

    return get_rubric(name)


def test_d24_dual_engine_parity():
    """LabResult VD + slice SAMs identical on native and forced fallback."""
    resources = [fx.PATIENT_IG_P11, fx.GLUCOSE_OBS_IG_P15,
                 fx.MONOCYTES_OBS_SG_P16]
    native = fx.make_connection(resources)
    fallback = fx.make_connection(resources, force_python_fallback=True)
    from fhir4ds.piqi import load_piqi_views

    for con in (native, fallback):
        load_piqi_views(con)
    q = 'SELECT * FROM piqi."piqi_labresult" ORDER BY element_id'
    a = native.execute(q).fetchall()
    b = fallback.execute(q).fetchall()
    assert a == b
    for name in ("piqi-sam-labresult-resultvalue-ispopulated",
                 "piqi-sam-labresult-test-iscomplete"):
        ra = [tuple(r.values()) for r in run_sam(native, name)]
        rb = [tuple(r.values()) for r in run_sam(fallback, name)]
        assert ra == rb, name


def test_d25_patient_id_injection_is_bound():
    """Injection payload in patient_id returns no rows, never interpolates."""
    con = fx.make_connection([fx.PATIENT_IG_P11, fx.GLUCOSE_OBS_IG_P15])
    payload = "' OR 1=1 --"
    rows = run_sam(con, "piqi-sam-labresult-resultvalue-ispopulated",
                   patient_id=payload)
    assert rows == []
    sc = evaluate_rubric(con, "sample", patient_id=payload)
    assert sc.potential_item_score == 0
    # and the same query path with the REAL id does return rows
    rows2 = run_sam(con, "piqi-sam-labresult-resultvalue-ispopulated",
                    patient_id="pat-1")
    assert len(rows2) == 1


def test_d26_taxonomy_alias_table():
    """Every guide dimension spelling maps to exactly one canonical code."""
    # canonical mnemonics [HB pp.17-19]
    canonical = {
        "Availability.Missing": "AV-MISS",
        "Availability.Unpopulated": "AV-UNPOP",
        "Availability.Incomplete": "AV-INCOMP",
        "Availability.Duplication": "AV-DUP",
        "Accuracy.InvalidFormat": "AC-FMT",
        "Accuracy.InvalidValue": "AC-VAL",
        "Accuracy.InvalidGrouping": "AC-GRP",
        "Conformity.InvalidMember": "CF-INVM",
        "Conformity.Incompatible": "CF-INCMPT",
        "Conformity.Obsolete": "CF-OBS",
        "Plausibility.TemporallyImplausible": "PL-TMP",
        "Plausibility.ClinicallyImplausible": "PL-CLI",
        "Plausibility.SituationallyImplausible": "PL-SIT",
    }
    for mnemonic, code in canonical.items():
        assert resolve_dimension(mnemonic).code == code
    # the guides' own inconsistent spellings [SG pp.11,16-19]
    aliases = {
        "Availablity.Populated": PIQIDimension.AV_UNPOP,   # [SG p.11] typo
        "Availability.Populated": PIQIDimension.AV_UNPOP,
        "Availability.IsPopulated": PIQIDimension.AV_UNPOP,  # [SG p.17]
        "Availability.Complete": PIQIDimension.AV_INCOMP,    # [SG p.18]
        "Availability.IsComplete": PIQIDimension.AV_INCOMP,  # [SG p.22]
        "Conformance.Invalid": PIQIDimension.CF_INVM,        # [SG p.18]
        "Conformance.Incompatible": PIQIDimension.CF_INCMPT,
        "Conformance.Obsolete": PIQIDimension.CF_OBS,
        "Conformity.Invalid": PIQIDimension.CF_INVM,
        "Accuracy.ValidValue": PIQIDimension.AC_VAL,         # [SG pp.11-14]
        "Accuracy.ValidFormat": PIQIDimension.AC_FMT,
        "Plausibility.Clinical": PIQIDimension.PL_CLI,       # [SG p.9]
        "Plausibility.Temporally": PIQIDimension.PL_TMP,
        "Availability.Duplication": PIQIDimension.AV_DUP,
    }
    for spelling, expected in aliases.items():
        got = resolve_dimension(spelling)
        assert got is expected, (spelling, got)
    # every SAM mnemonic in the catalog classifies through taxonomy.py alone
    for mnem in ("Attr_IsPopulated", "Attr_IsValidDate", "Attr_IsNumeric",
                 "Concept_HasCode", "Concept_IsComplete", "RangeValue_IsValid",
                 "Element_IsClean", "Class_HasDuplicates",
                 "LabResult_UnitIsPlausible"):
        dim = dimension_for_sam(mnem)
        assert isinstance(dim, PIQIDimension)
    with pytest.raises(ValueError):
        resolve_dimension("Bogus.Dimension")
