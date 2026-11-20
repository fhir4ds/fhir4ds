"""AMUX-152 batch 4 — PIQI security + correctness (#17, #19, #20, #21, #22).

Authored RED before the fixes per Joel's before/after doctrine.
"""

from __future__ import annotations

import base64
import json

import pytest

from . import fixtures as fx
from fhir4ds.piqi import build_rubric, evaluate_rubric, get_sam, run_sam
from fhir4ds.piqi.taxonomy import PIQIDimension


def _results(rows):
    return {r["element_id"]: r["result"] for r in rows}


def _vital(obs_id: str, *, value=None, component=None) -> dict:
    obs = {
        "resourceType": "Observation",
        "id": obs_id,
        "status": "final",
        "category": [{"coding": [{"system": fx.OBS_CATEGORY_SYSTEM,
                                  "code": "vital-signs"}]}],
        "code": {"text": "Some Vital", "coding": [{"code": "0000-0",
                                                    "system": fx.LOINC}]},
        "subject": {"reference": "Patient/pat-1"},
        "effectiveDateTime": "2020-07-10T10:30:00-07:00",
    }
    if value is not None:
        obs["valueQuantity"] = value
    if component is not None:
        obs["component"] = component
    return obs


# ===========================================================================
# #17 — SQL injection in the public build_rubric surface
# ===========================================================================
class TestAmux152Batch4Injection:
    _CRITERION = {
        "sequence": 1, "data_class": "Demographics", "entity": "birthDate",
        "sam": "demographics-birthdate-isvaliddate",
        "scoring_effect": "scoring", "weight": 1, "criticality": False,
    }

    def test_scoring_effect_injection_rejected_amux152_17(self):
        """The triage PoC class: attacker-controlled scoring_effect must
        never reach the generated SQL — allowlist + typed ValueError."""
        for payload in [
            # closes the string and rewrites the projection
            "scoring', 999 AS weight, TRUE AS criticality, 'pass' AS result,"
            " 'pwned' AS detail FROM resources --",
            "scoring' UNION SELECT 'pwned' --",
            "informational' ; DROP VIEW x; --",
            "SCORING",      # not in the authored vocabulary
            "",             # empty is outside the allowlist
        ]:
            with pytest.raises(ValueError, match="scoring_effect"):
                build_rubric("inject", "injection probe", [
                    {**self._CRITERION, "scoring_effect": payload}])

    def test_sequence_injection_rejected_amux152_17(self):
        """sequence must be int-coerced — a SQL fragment in the sequence
        slot (it reaches ``{seq} AS sequence`` and the dependency labels)
        raises a typed ValueError."""
        for payload in [
            "1 AS sequence, (SELECT count(*) FROM resources) AS extra --",
            "1; DROP VIEW x",
            "1.5",
        ]:
            with pytest.raises(ValueError, match="sequence"):
                build_rubric("inject", "injection probe", [
                    {**self._CRITERION, "sequence": payload}])

    def test_weight_injection_rejected_amux152_17(self):
        for payload in ["1 OR 1=1", "1; DROP VIEW x", "abc"]:
            with pytest.raises(ValueError, match="weight"):
                build_rubric("inject", "injection probe", [
                    {**self._CRITERION, "weight": payload}])

    def test_valid_criteria_still_build_amux152_17(self):
        lib, meta = build_rubric("ok", "ok probe", [dict(self._CRITERION)])
        assert meta[0]["scoring_effect"] == "scoring"
        body = base64.b64decode(lib["content"][0]["data"]).decode()
        assert "999" not in body

    def test_authored_strings_are_quoted_literals_amux152_17_review(self):
        """Batch-4 review: EVERY string interpolated into the rubric SQL
        (data_class, entity, attributed mnemonics) is emitted as a quoted
        SQL literal — defense in depth beyond the scoring_effect
        allowlist, so no interpolation site is a future injection seam."""
        lib, _ = build_rubric("quote", "quote probe", [dict(self._CRITERION)])
        body = base64.b64decode(lib["content"][0]["data"]).decode()
        assert "'Demographics' AS data_class" in body
        assert "'birthDate' AS entity" in body
        assert "'Attr_IsValidDate' END AS attributed_mnemonic" in body \
            or "'Attr_IsValidDate' AS attributed_mnemonic" in body


# ===========================================================================
# #21 — duplicate sequence values
# ===========================================================================
class TestAmux152Batch4DuplicateSequence:
    def test_duplicate_sequences_rejected_amux152_21(self):
        with pytest.raises(ValueError, match="[Dd]uplicate.*sequence"):
            build_rubric("dup", "duplicate probe", [
                {"sequence": 1, "data_class": "Demographics",
                 "entity": "birthDate",
                 "sam": "demographics-birthdate-isvaliddate",
                 "scoring_effect": "scoring", "weight": 1,
                 "criticality": False},
                {"sequence": 1, "data_class": "Demographics",
                 "entity": "deathDate",
                 "sam": "demographics-deathdate-isvaliddate",
                 "scoring_effect": "scoring", "weight": 1,
                 "criticality": False},
            ])


# ===========================================================================
# #22 — run_sam accepts custom SAM Library dicts
# ===========================================================================
class TestAmux152Batch4CustomSamDict:
    def test_run_sam_materializes_user_dict_amux152_22(self):
        """A custom SAM Library dict (non-packaged url) must materialize
        through a dict-identity/url resolver fallback; packaged canonical
        dependencies (the data-class view) still resolve normally."""
        sam = get_sam("labresult-resultvalue-ispopulated")
        custom_body = (
            "SELECT v.patient_id AS patient_id, v.element_id AS element_id,\n"
            "  'LabResult' AS data_class, 'resultValue' AS entity, "
            "'CustomSAM' AS sam_mnemonic,\n"
            "  CASE WHEN COALESCE(TRIM(CAST(v.resultValue_text AS VARCHAR)), "
            "'') <> '' THEN 'pass' ELSE 'fail' END AS result,\n"
            "  'custom sam body ran' AS detail\n"
            "FROM \"view_piqi_labresult\" v\n"
            "ORDER BY v.patient_id, v.element_id"
        )
        custom = dict(sam)
        custom["url"] = "https://example.org/sam/custom-ispopulated"
        custom["id"] = "custom-ispopulated"
        custom["content"] = [{
            "contentType": "application/sql;dialect=duckdb",
            "data": base64.b64encode(custom_body.encode()).decode(),
        }]
        con = fx.make_connection([fx.PATIENT_IG_P11, fx.GLUCOSE_OBS_IG_P15])
        rows = run_sam(con, custom)
        assert len(rows) == 1
        assert rows[0]["sam_mnemonic"] == "CustomSAM"
        assert rows[0]["result"] == "pass"
        assert rows[0]["detail"] == "custom sam body ran"
        # packaged behavior unchanged
        packed = run_sam(con, "piqi-sam-labresult-resultvalue-ispopulated")
        assert packed[0]["sam_mnemonic"] == "Attr_IsPopulated"

    def test_custom_dict_cannot_shadow_packaged_canonical_amux152_22(self):
        """Batch-4 review: a custom dict whose url CLAIMS a packaged
        canonical is rejected loudly — it must never silently replace the
        packaged SAM's body for its own or any dependency resolution."""
        sam = get_sam("labresult-resultvalue-ispopulated")
        con = fx.make_connection([fx.PATIENT_IG_P11])
        with pytest.raises(ValueError, match="packaged canonical"):
            run_sam(con, dict(sam))  # same url as the packaged SAM


# ===========================================================================
# #19 — piqi_vital_sign resultValue_text
# ===========================================================================
class TestAmux152Batch4VitalSignText:
    def _row(self, con, obs_id):
        cols = [d[0] for d in con.execute(
            'DESCRIBE SELECT * FROM piqi."piqi_vital_sign"').fetchall()]
        rows = con.execute(
            f'SELECT * FROM piqi."piqi_vital_sign" WHERE element_id = '
            f"'{obs_id}'").fetchall()
        assert len(rows) == 1
        return dict(zip(cols, rows[0]))

    def test_valuequantity_vital_keeps_value_and_unit_amux152_19(self):
        """A non-BP vital (scalar valueQuantity) must keep its value (and
        unit) — the systolic/diastolic projection must not erase it."""
        from fhir4ds.piqi import load_piqi_views

        weight = _vital("vs-wt", value={"value": 80, "unit": "kg"})
        con = fx.make_connection([fx.PATIENT_IG_P11, weight])
        load_piqi_views(con)
        row = self._row(con, "vs-wt")
        assert row["resultValue_text"] == "80"
        assert float(row["resultValue_number"]) == 80.0
        assert row["resultUnit_text"] == "kg"
        assert _results(run_sam(
            con, "piqi-sam-vitalsign-resultvalue-ispopulated"))["vs-wt"] == "pass"

    def test_empty_vital_fails_ispopulated_amux152_19(self):
        """A vital with NO value at all must render '' so Attr_IsPopulated
        FAILS — the FHIRPath ``&`` empty-as-'' behavior must not turn the
        BP separator alone ('/') into populated content."""
        from fhir4ds.piqi import load_piqi_views

        empty = _vital("vs-empty")
        partial_bp = _vital("vs-sys-only", component=[
            {"code": {"coding": [{"code": "8480-5", "system": fx.LOINC}]},
             "valueQuantity": {"value": 120, "unit": "mmHg"}},
        ])
        con = fx.make_connection([fx.PATIENT_IG_P11, empty, partial_bp])
        load_piqi_views(con)
        assert self._row(con, "vs-empty")["resultValue_text"] in ("", None)
        assert self._row(con, "vs-sys-only")["resultValue_text"] in ("", None)
        res = _results(run_sam(con, "piqi-sam-vitalsign-resultvalue-ispopulated"))
        assert res["vs-empty"] == "fail"
        assert res["vs-sys-only"] == "fail"

    def test_bp_panel_pair_unchanged_amux152_19(self):
        from fhir4ds.piqi import load_piqi_views

        con = fx.make_connection([fx.PATIENT_IG_P11, fx.BP_OBS_IG_P20])
        load_piqi_views(con)
        row = self._row(con, "vs-bp-1")
        assert row["resultValue_text"] == "130/80"
        assert float(row["resultValue_number"]) == 130.0
        assert float(row["resultValue_number2"]) == 80.0
        assert row["resultUnit_text"] == "mmHg"


# ===========================================================================
# #20 — multi-hop prerequisite chains
# ===========================================================================
class TestAmux152Batch4TwoHopPrereq:
    """[HB p.21] 'Prerequisites can stack' + [HB p.23] prereq failure ⇒
    denominator+1 / numerator+0 attributed to the PREREQUISITE's
    dimension — at ANY depth of the chain, not only depth 1."""

    def _rubric(self):
        # chain: referenceRange IsPopulated -> RangeValue_IsComplete ->
        # RangeValue_IsValid (a real 2-hop packaged chain)
        return build_rubric("twohop", "two-hop probe", [{
            "sequence": 1, "data_class": "LabResult",
            "entity": "referenceRange",
            "sam": "labresult-referencerange-rangeisvalid",
            "scoring_effect": "scoring", "weight": 1, "criticality": False,
        }])

    def test_root_prereq_failure_surfaces_as_fail_amux152_20(self):
        """referenceRange unpopulated (ROOT prereq fails): the item must
        still count (potential 1) and FAIL attributed to
        Attr_IsPopulated / Availability.Unpopulated — the inner-join
        chain must not drop the element as could-not-assess."""
        # populated value + NO referenceRange at all → root ispopulated fails
        con = fx.make_connection([
            fx.PATIENT_IG_P11, fx.lab_obs("lab-norr", "x")])
        sc = evaluate_rubric(con, self._rubric(), verbose=True)
        assert sc.potential_item_score == 1, "2-hop root failure dropped"
        assert sc.total_item_score == 0
        assert sc.piqi_index == 0.0
        assert len(sc.issues) == 1
        assert sc.issues[0].sam_mnemonic == "Attr_IsPopulated"
        assert sc.issues[0].dimension is PIQIDimension.AV_UNPOP

    def test_mid_chain_failure_attributed_to_direct_prereq_amux152_20(self):
        """IsPopulated passes, RangeIsComplete fails (missing high) → the
        item FAILS attributed to RangeValue_IsComplete."""
        con = fx.make_connection([
            fx.PATIENT_IG_P11,
            fx.lab_obs("lab-inc", "x",
                       reference_range={"text": "14-", "low": {"value": 14}}),
        ])
        sc = evaluate_rubric(con, self._rubric(), verbose=True)
        assert sc.potential_item_score == 1
        assert sc.total_item_score == 0
        assert sc.issues[0].sam_mnemonic == "RangeValue_IsComplete"

    def test_full_chain_pass_and_own_fail_amux152_20(self):
        con_ok = fx.make_connection([
            fx.PATIENT_IG_P11,
            fx.lab_obs("lab-ok", "x", reference_range={
                "text": "70-100", "low": {"value": 70}, "high": {"value": 100}}),
        ])
        sc = evaluate_rubric(con_ok, self._rubric())
        assert sc.potential_item_score == 1
        assert sc.total_item_score == 1
        assert sc.piqi_index == 100.0

        con_inv = fx.make_connection([
            fx.PATIENT_IG_P11,
            fx.lab_obs("lab-inv", "x", reference_range={
                "text": "100-70", "low": {"value": 100}, "high": {"value": 70}}),
        ])
        sc2 = evaluate_rubric(con_inv, self._rubric(), verbose=True)
        assert sc2.potential_item_score == 1
        assert sc2.total_item_score == 0
        # all prereqs passed → attributed to the ASSIGNED SAM itself
        assert sc2.issues[0].sam_mnemonic == "RangeValue_IsValid"


# ===========================================================================
# Packaged-resource consistency (regeneration guard)
# ===========================================================================
def test_packaged_resources_match_authoring_amux152():
    """The committed resources must be exactly what ``python3 -m
    fhir4ds.piqi.authoring`` emits — guards the #19 regeneration."""
    from fhir4ds.piqi.authoring import generate_all
    from pathlib import Path

    res_dir = Path(__file__).parent.parent / "resources"
    generated = generate_all()
    for rel, text in sorted(generated.items()):
        committed = (res_dir / rel).read_text(encoding="utf-8")
        assert committed == text, f"{rel} is stale — regenerate resources"
    # and no extra committed files beyond the generated set
    committed_files = {
        str(p.relative_to(res_dir)) for sub in ("views", "sams", "rubrics")
        for p in (res_dir / sub).glob("*.json")}
    # codesystems.json [HB p.15] is generated at the resources root
    committed_files.add("codesystems.json")
    assert committed_files == set(generated), (
        sorted(committed_files ^ set(generated)))
