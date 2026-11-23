"""AMUX-152 batch 5 — PIQI hardening (#18, #23-partial, #24, #25, #26).

Authored RED before the fixes per Joel's before/after doctrine.
"""

from __future__ import annotations

import base64
import copy

import pytest

from . import fixtures as fx
from fhir4ds.piqi import build_rubric, evaluate_rubric, run_sam


def _results(rows):
    return {r["element_id"]: r["result"] for r in rows}


def _clean_lab(obs_id: str, unit: str, codings: list[dict],
               *, value=4.2, effective="2020-07-10T10:30:00-07:00") -> dict:
    """A lab element that passes Element_IsClean (UnitIsPlausible's prereq):
    populated test text + a complete coding + value + timestamp."""
    return fx.lab_obs(
        obs_id, {"value": value, "unit": unit},
        code={"text": "Some Test", "coding": codings}, effective=effective)


# ===========================================================================
# #18 — LabResult_UnitIsPlausible: 742-7 typo + multi-coding arm logic
# ===========================================================================
class TestAmux152Batch5UnitPlausible:
    def test_wrong_unit_742_7_fails_amux152_18(self):
        """LOINC 742-7 (monocytes) with a glucose unit must FAIL — the old
        exclusion arm typo'd '742-2', letting 742-7 pass with any unit."""
        obs = _clean_lab("mono-wrong", "mg/dL", [
            {"code": "742-7", "system": fx.LOINC, "display": "MONOCYTES"}])
        con = fx.make_connection([fx.PATIENT_IG_P11, obs])
        assert _results(run_sam(con, "piqi-sam-labresult-unitplausible")) == {
            "mono-wrong": "fail"}

    def test_correct_unit_742_7_passes_amux152_18(self):
        obs = _clean_lab("mono-ok", "10*3/uL", [
            {"code": "742-7", "system": fx.LOINC, "display": "MONOCYTES"}])
        con = fx.make_connection([fx.PATIENT_IG_P11, obs])
        assert _results(run_sam(con, "piqi-sam-labresult-unitplausible")) == {
            "mono-ok": "pass"}

    def test_multicoding_requires_coded_arm_plausibility_amux152_18(self):
        """A multi-coding concept carrying a LOCAL code alongside a
        governed code (2345-7) must be judged by the CODED arm's unit —
        not pass merely because a non-governed coding exists."""
        obs = _clean_lab("multi-wrong", "10*3/uL", [
            {"code": "MONO100", "system": "LCL", "display": "MONOS"},
            {"code": "2345-7", "system": fx.LOINC,
             "display": "Glucose Ser/Plas MCnc Pt Qn"},
        ])
        con = fx.make_connection([fx.PATIENT_IG_P11, obs])
        assert _results(run_sam(con, "piqi-sam-labresult-unitplausible")) == {
            "multi-wrong": "fail"}

    def test_correct_unit_2345_7_passes_amux152_18(self):
        obs = _clean_lab("gluc-ok", "mg/dL", [
            {"code": "2345-7", "system": fx.LOINC,
             "display": "Glucose Ser/Plas MCnc Pt Qn"}])
        con = fx.make_connection([fx.PATIENT_IG_P11, obs])
        assert _results(run_sam(con, "piqi-sam-labresult-unitplausible")) == {
            "gluc-ok": "pass"}

    def test_packaged_monocytes_fixture_still_passes_amux152_18(self):
        """The [SG p.16] three-coding MONOCYTES fixture (local + LOINC +
        empty-system) keeps passing with its authored 10*3/uL unit."""
        con = fx.make_connection([fx.PATIENT_IG_P11,
                                  fx.MONOCYTES_OBS_SG_P16])
        assert _results(run_sam(con, "piqi-sam-labresult-unitplausible")) == {
            "lab-mono": "pass"}


# ===========================================================================
# #25 — typed public validation, Attr_IsTimestamp, Class_HasDuplicates
# ===========================================================================
class TestAmux152Batch5RubricValidation:
    _CRITERION = {
        "sequence": 1, "data_class": "Demographics", "entity": "birthDate",
        "sam": "demographics-birthdate-isvaliddate",
        "scoring_effect": "scoring", "weight": 1, "criticality": False,
    }

    def test_empty_criteria_rejected_amux152_25(self):
        with pytest.raises(ValueError, match="at least one criterion"):
            build_rubric("empty", "empty probe", [])

    def test_mismatched_data_class_is_valueerror_amux152_25(self):
        """Public-input validation must be typed ValueError (assert
        disappears under ``python -O``)."""
        with pytest.raises(ValueError, match="data_class"):
            build_rubric("bad", "bad probe", [
                {**self._CRITERION, "data_class": "LabResult"}])

    def test_mismatched_entity_is_valueerror_amux152_25(self):
        with pytest.raises(ValueError, match="entity"):
            build_rubric("bad", "bad probe", [
                {**self._CRITERION, "entity": "deathDate"}])

    def test_mismatched_condition_data_class_is_valueerror_amux152_25(self):
        with pytest.raises(ValueError, match="condition_sam"):
            build_rubric("bad", "bad probe", [
                {**self._CRITERION,
                 "condition_sam": "labresult-test-ispopulated"}])


class TestAmux152Batch5IsTimestamp:
    """[SG p.14] 'a timestamp including a date and time' — date-only
    values must FAIL Attr_IsTimestamp (they are Attr_IsValidDate's domain)."""

    def test_date_only_fails_amux152_25(self):
        obs = fx.lab_obs("lab-dateonly", "x", effective="2020-07-10")
        con = fx.make_connection([fx.PATIENT_IG_P11, obs])
        assert _results(run_sam(
            con, "piqi-sam-labresult-performeddatetime-istimestamp")) == {
            "lab-dateonly": "fail"}

    def test_full_timestamp_passes_amux152_25(self):
        obs = fx.lab_obs("lab-full", "x")
        con = fx.make_connection([fx.PATIENT_IG_P11, obs])
        assert _results(run_sam(
            con, "piqi-sam-labresult-performeddatetime-istimestamp")) == {
            "lab-full": "pass"}


class TestAmux152Batch5HasDuplicatesNullKeys:
    def test_null_keys_are_not_duplicates_amux152_25(self):
        """Two elements whose identity attributes are NULL must NOT be
        counted as duplicates (house 3VL doctrine: NULL keys are unknown
        identity, not equal identity) — and the class row must still be
        emitted (one row per patient, deterministic)."""
        null_key = {"coding": [{"code": "0000-0", "system": fx.LOINC,
                                "display": "Some Test"}]}  # no text -> NULL
        a = fx.lab_obs("nl-a", "x", code=null_key)
        b = fx.lab_obs("nl-b", "x", code=null_key)
        con = fx.make_connection([fx.PATIENT_IG_P11, a, b])
        rows = run_sam(con, "piqi-sam-labresult-hasduplicates")
        assert len(rows) == 1
        assert rows[0]["patient_id"] == "pat-1"
        assert rows[0]["element_id"] is None  # class-level SAM
        assert rows[0]["result"] == "fail"    # NULL keys: not duplicates

    def test_real_duplicates_still_detected_amux152_25(self):
        dup = fx.lab_obs("dup-a", "x", code={"text": "Glucose, Serum",
                                             "coding": [
                                                 {"code": "2345-7",
                                                  "system": fx.LOINC}]})
        dup2 = fx.lab_obs("dup-b", "x", code={"text": "Glucose, Serum",
                                              "coding": [
                                                  {"code": "2345-7",
                                                   "system": fx.LOINC}]})
        con = fx.make_connection([fx.PATIENT_IG_P11, dup, dup2])
        rows = run_sam(con, "piqi-sam-labresult-hasduplicates")
        assert rows[0]["result"] == "pass"
        assert "dup-a" in rows[0]["detail"] and "dup-b" in rows[0]["detail"]


# ===========================================================================
# #24 — source_table parameter + typed piqiCriteria access
# ===========================================================================
class TestAmux152Batch5SourceTable:
    def test_run_sam_and_evaluate_rubric_accept_source_table_amux152_24(self):
        """run_sam / evaluate_rubric / data-class frequency must read from
        a caller-named physical table, not a hardcoded 'resources'."""
        con = fx.make_connection([fx.PATIENT_IG_P11])
        con.execute("CREATE OR REPLACE TABLE alt_src AS SELECT * FROM resources")
        con.execute("DROP TABLE resources")
        rows = run_sam(con, "piqi-sam-labresult-resultvalue-ispopulated",
                       source_table="alt_src")
        assert rows == []  # no lab elements in the alt table; query RAN
        lib, meta = build_rubric("alt", "alt probe", [{
            "sequence": 1, "data_class": "Demographics", "entity": "birthDate",
            "sam": "demographics-birthdate-isvaliddate",
            "scoring_effect": "scoring", "weight": 1, "criticality": False,
        }])
        sc = evaluate_rubric(con, (lib, meta), source_table="alt_src")
        assert sc.data_class_frequency == {"Demographics": 1}

    def test_fhir_pure_rubric_without_criteria_metadata_errors_amux152_24(self):
        """A FHIR-pure rubric Library (no piqiCriteria metadata) raises a
        typed ValueError instead of a KeyError/invalid SQL."""
        lib, _ = build_rubric("pure", "pure probe", [{
            "sequence": 1, "data_class": "Demographics", "entity": "birthDate",
            "sam": "demographics-birthdate-isvaliddate",
            "scoring_effect": "scoring", "weight": 1, "criticality": False,
        }])
        pure = {k: v for k, v in lib.items() if k != "piqiCriteria"}
        con = fx.make_connection([fx.PATIENT_IG_P11])
        with pytest.raises(ValueError, match="piqiCriteria"):
            evaluate_rubric(con, pure)


# ===========================================================================
# #23-partial — runtime DATA_CLASS_TO_VIEW import comes from registry
# ===========================================================================
def test_runtime_data_class_map_imported_from_registry_amux152_23():
    """scorecard (runtime) must not import authoring-time tables; the
    mapping is re-exported by registry, which is the runtime surface."""
    import inspect
    from fhir4ds.piqi import scorecard
    src = inspect.getsource(scorecard)
    assert "from .authoring import" not in src
    from fhir4ds.piqi.registry import DATA_CLASS_TO_VIEW  # noqa: F401
