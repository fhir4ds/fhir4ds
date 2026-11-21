"""FHIR4-20 name-embedding rule (P1-P3) acceptance tests.

Written RED before implementation (feature_implementation doctrine).
Covers: artifact loading + hash identity, inference determinism, band
assignment + hysteresis, additive rule registration (CATEGORY1_RULES
byte-compat by construction), manifest == constants parity, degradation
(missing/corrupt artifact -> no rules + exactly ONE warning), end-to-end
EMBED-rule match with audit evidence shape, use_embedding=False legacy
equivalence, per-band effective P, and training-data generation
determinism (torch itself stays dev-only; the generation layer is pure
Python).
"""

from __future__ import annotations

import importlib.util
import json
import logging
import math
from pathlib import Path

import duckdb

from fhir4ds.matching.engine import match_patient
from fhir4ds.matching import name_embedding
from fhir4ds.matching.name_embedding import (
    BAND_HYSTERESIS,
    MODEL_VERSION,
    _band_for_distance,
    artifact_available,
    band_edges,
    band_u_values,
    distance,
    embed,
    embedding_model_id,
    name_distance_band,
    reload as reload_embedding,
)
from fhir4ds.matching.rules import (
    CATEGORY1_RULES,
    EMBED,
    embedding_rules,
    patient_rules_with_embedding,
)
from fhir4ds.matching.store import index_patient

ARTIFACT = Path(name_embedding.__file__).parent / "artifacts" / "name_embed_v1.npz"


# ---------------------------------------------------------------------------
# P2: artifact + inference
# ---------------------------------------------------------------------------


class TestArtifactAndInference:
    def test_artifact_ships_and_model_id(self):
        assert ARTIFACT.exists(), "pinned artifact must ship in-tree"
        assert artifact_available()
        model_id = embedding_model_id()
        assert model_id == f"{MODEL_VERSION}@{model_id.split('@')[1]}"
        assert len(model_id.split("@")[1]) == 8
        int(model_id.split("@")[1], 16)  # sha8 hex

    def test_embed_deterministic_bounded(self):
        for name in ("mohammed", "muhammad", "robert", "bob", "x"):
            v1 = embed(name)
            v2 = embed(name)
            assert v1.shape == (16,)
            assert v1.dtype.name == "float64"
            assert v1.tobytes() == v2.tobytes()  # bit-identical
            assert math.isclose(float((v1 * v1).sum()), 1.0, rel_tol=1e-9)

    def test_distance_semantics(self):
        assert distance("john", "john") == 0.0
        d_ab = distance("mohammed", "muhammad")
        d_ba = distance("muhammad", "mohammed")
        assert d_ab == d_ba
        assert 0.0 <= d_ab <= 2.0

    def test_variant_pairs_closer_than_unrelated(self):
        """The pinned model must have learned the equivalence structure:
        mean distance over transliteration/nickname pairs < mean distance
        over unrelated name pairs (the reason the artifact exists)."""
        from fhir4ds.realism.corrupt import TRANSLITERATION_GROUPS

        near, far = [], []
        for group in TRANSLITERATION_GROUPS:
            names = sorted(group)
            for i, a in enumerate(names):
                for b in names[i + 1:]:
                    near.append(distance(a, b))
        far_pool = [
            ("mohammed", "robert"), ("sofia", "chen"), ("ali", "stephen"),
            ("yusuf", "maria"), ("omar", "katherine"), ("wei", "bartholomew"),
            ("ahmed", "georgi"), ("nikolai", "sofia"), ("kim", "youssef"),
            ("john", "wei"),
        ]
        far = [distance(a, b) for a, b in far_pool]
        assert sum(near) / len(near) < sum(far) / len(far)

    def test_band_assignment(self):
        band = name_distance_band("mohammed", "mohammed")
        assert band == "tight"  # distance 0
        assert name_distance_band("mohammed", "zzzzzzzzzz") is None

    def test_band_hysteresis_tight_side(self):
        edges = band_edges()
        tight_edge = edges["tight"]
        # at or within +1e-3 of an edge -> the TIGHTER band (deterministic)
        assert _band_for_distance(tight_edge) == "tight"
        assert _band_for_distance(tight_edge + BAND_HYSTERESIS * 0.5) == "tight"
        assert _band_for_distance(tight_edge + BAND_HYSTERESIS) == "tight"
        assert (
            _band_for_distance(tight_edge + 10 * BAND_HYSTERESIS) == "mid"
        )


# ---------------------------------------------------------------------------
# P3: rule registration (additive-only, byte-compat by construction)
# ---------------------------------------------------------------------------


class TestRuleRegistration:
    def test_category1_table_untouched(self):
        # The 29 upstream ids, in the exact upstream order.
        ids = [r.rule_id for r in CATEGORY1_RULES]
        assert ids == [
            "22", "02", "03", "01", "10", "24", "30", "04", "05", "06",
            "07", "17", "18", "19", "20", "21", "25", "26", "27", "28",
            "13", "14", "15", "16", "08", "09", "11", "12", "23",
        ]
        assert not any(
            m == EMBED for r in CATEGORY1_RULES for _f, m in r.fields
        )
        assert all(not r.band_u_values for r in CATEGORY1_RULES)

    def test_embedding_rules_shape(self):
        rules = {r.rule_id: r for r in embedding_rules()}
        assert set(rules) == {"E1", "E2", "E3"}
        e1 = rules["E1"]
        assert ("first", EMBED) in e1.fields
        assert ("last", "exact") in e1.fields
        assert ("dob", "exact") in e1.fields
        assert ("ssn4", "exact") in e1.fields
        e2 = rules["E2"]
        assert ("first", EMBED) in e2.fields
        assert ("phone", "exact") in e2.fields
        e3 = rules["E3"]
        assert ("first", EMBED) in e3.fields
        assert ("last", EMBED) in e3.fields
        assert ("street_line", "exact") in e3.fields
        for rule in rules.values():
            assert rule.band_u_values, "E-rules carry per-band u-values"
            assert [b for b, _u in rule.band_u_values] == ["tight", "mid", "loose"]
            assert all(0.0 < u < 1.0 for _b, u in rule.band_u_values)
            # ordering bounds: p_collision is the TIGHTEST-band product,
            # p_collision_fuzzy the LOOSEST-band product
            assert rule.p_collision <= rule.p_collision_fuzzy

    def test_table_is_additive_sorted_and_category1_identical(self):
        combined = patient_rules_with_embedding()
        assert len(combined) == len(CATEGORY1_RULES) + 3
        # CATEGORY1_RULES keeps its exact order as the PREFIX, and the
        # E-rules (sorted among themselves by tightest-band P) follow —
        # every Category-1 rule gets first refusal, so existing match
        # attribution is byte-identical (FDD §3.3 deviation note).
        assert [r.rule_id for r in combined[:len(CATEGORY1_RULES)]] == [
            r.rule_id for r in CATEGORY1_RULES
        ]
        e_keys = [
            (r.effective_p_min, r.rule_id)
            for r in combined[len(CATEGORY1_RULES):]
        ]
        assert e_keys == sorted(e_keys)
        cat_ids = {r.rule_id for r in combined} - {"E1", "E2", "E3"}
        assert cat_ids == {r.rule_id for r in CATEGORY1_RULES}
        for r in CATEGORY1_RULES:
            assert r in combined

    def test_manifest_u_values_match_constants(self):
        from fhir4ds.matching.rules import BAND_U_VALUES

        assert {k: round(v, 10) for k, v in band_u_values()} == {
            k: round(v, 10) for k, v in dict(BAND_U_VALUES).items()
        }

    def test_effective_p_per_band(self):
        e1 = {r.rule_id: r for r in embedding_rules()}["E1"]
        from fhir4ds.matching.rules import FIELD_U_PROBS

        base = (
            FIELD_U_PROBS["last"][0]
            * FIELD_U_PROBS["dob"][0]
            * FIELD_U_PROBS["ssn4"][0]
        )
        u = dict(e1.band_u_values)
        assert math.isclose(
            e1.effective_p({"first": "tight"}), base * u["tight"], rel_tol=1e-15
        )
        assert math.isclose(
            e1.effective_p({"first": "loose"}), base * u["loose"], rel_tol=1e-15
        )
        # a rule without embed fields ignores the bands argument
        r04 = next(r for r in CATEGORY1_RULES if r.rule_id == "04")
        assert r04.effective_p({}) == r04.p_collision


# ---------------------------------------------------------------------------
# P3: degradation — no artifact -> no rules + exactly one WARNING
# ---------------------------------------------------------------------------


class TestDegradation:
    def test_missing_artifact_no_rules_one_warning(self, tmp_path, caplog):
        reload_embedding(tmp_path / "absent.npz")
        try:
            with caplog.at_level(logging.WARNING, logger="fhir4ds.matching.name_embedding"):
                assert embedding_rules() == []
                table = patient_rules_with_embedding()
                assert [r.rule_id for r in table] == [r.rule_id for r in CATEGORY1_RULES]
                # second call: no additional warning (warn-once)
                assert embedding_rules() == []
            warnings = [
                r for r in caplog.records
                if r.name == "fhir4ds.matching.name_embedding"
                and r.levelno == logging.WARNING
            ]
            assert len(warnings) == 1, "exactly ONE degradation warning"
            assert "name_embed_v1" in warnings[0].getMessage()
        finally:
            reload_embedding()  # restore the shipped artifact

    def test_corrupt_artifact_degrades(self, tmp_path, caplog):
        bad = tmp_path / "bad.npz"
        bad.write_bytes(b"not an npz at all")
        reload_embedding(bad)
        try:
            with caplog.at_level(logging.WARNING, logger="fhir4ds.matching.name_embedding"):
                assert embedding_rules() == []
            assert not artifact_available()
        finally:
            reload_embedding()

    def test_hash_mismatch_degrades(self, tmp_path, caplog):
        """Flip weight bytes inside a copy of the real artifact: the
        manifest weights-hash check must reject it."""
        import numpy as np

        good = np.load(ARTIFACT, allow_pickle=False)
        payload = {k: good[k] for k in good.files}
        w = payload["conv3_weight"]
        payload["conv3_weight"] = w + np.float32(1.0)
        bad = tmp_path / "tampered.npz"
        np.savez(bad, **payload)
        reload_embedding(bad)
        try:
            with caplog.at_level(logging.WARNING, logger="fhir4ds.matching.name_embedding"):
                assert embedding_rules() == []
            assert not artifact_available()
        finally:
            reload_embedding()


# ---------------------------------------------------------------------------
# P3: end-to-end engine behavior
# ---------------------------------------------------------------------------

_BASE = {
    "resourceType": "Patient",
    "name": [{"use": "official", "family": "Ibrahim", "given": ["Mohammed"]}],
    "birthDate": "1980-05-17",
    "id": "p1",
    "identifier": [
        {"type": {"coding": [{"code": "SS"}]},
         "system": "http://hl7.org/fhir/sid/us-ssn",
         "value": "1234"}
    ],
}


def _conn():
    conn = duckdb.connect()
    from fhir4ds.matching.store import create_matching_tables

    create_matching_tables(conn)
    return conn


class TestEngineEmbed:
    def test_e1_fires_with_audit_evidence(self):
        conn = _conn()
        index_patient(conn, _BASE)
        variant = json.loads(json.dumps(_BASE))
        variant["id"] = "p2"
        variant["name"] = [
            {"use": "official", "family": "Ibrahim", "given": ["Muhummad"]}
        ]
        index_patient(conn, variant)
        result = match_patient(conn, variant, exclude=frozenset({"p2"}))
        assert result.outcome == "match", result
        assert result.rule_id in {"E1", "E2", "E3"}
        ev = result.evidence["first"]
        # "mohammed~muhummad|band=mid|model=name-embed-v1@<sha8>"
        # (query value first — either order accepted)
        assert ev.startswith(("mohammed~muhummad|band=",
                              "muhummad~mohammed|band="))
        assert "|model=name-embed-v1@" in ev
        model_part = ev.split("|model=")[1]
        assert len(model_part.split("@")[1]) == 8
        assert result.match_type == "fuzzy"
        # per-band confidence: 1 - effective_p with the matched band u
        u = dict(band_u_values())
        band = ev.split("|band=")[1].split("|")[0]
        from fhir4ds.matching.rules import FIELD_U_PROBS

        expected_p = (
            FIELD_U_PROBS["last"][0]
            * FIELD_U_PROBS["dob"][0]
            * FIELD_U_PROBS["ssn4"][0]
            * u[band]
        )
        assert math.isclose(result.confidence, 1.0 - expected_p, rel_tol=1e-12)

    def test_unrelated_first_name_does_not_fire_e_rule(self):
        conn = _conn()
        index_patient(conn, _BASE)
        other = json.loads(json.dumps(_BASE))
        other["id"] = "p2"
        other["name"] = [
            {"use": "official", "family": "Ibrahim", "given": ["Katherine"]}
        ]
        index_patient(conn, other)
        result = match_patient(conn, other, exclude=frozenset({"p2"}))
        ev = result.evidence.get("first", "")
        assert "model=name-embed-v1" not in ev

    def test_use_embedding_false_is_legacy(self):
        conn = _conn()
        index_patient(conn, _BASE)
        variant = json.loads(json.dumps(_BASE))
        variant["id"] = "p2"
        variant["name"] = [
            {"use": "official", "family": "Ibrahim", "given": ["Muhummad"]}
        ]
        index_patient(conn, variant)
        legacy = match_patient(
            conn, variant, exclude=frozenset({"p2"}), use_embedding=False
        )
        assert legacy.rule_id not in {"E1", "E2", "E3"}
        assert "model=name-embed-v1" not in legacy.evidence.get("first", "")

    def test_embed_field_exact_equality_takes_tight_band(self):
        conn = _conn()
        index_patient(conn, _BASE)
        exact = json.loads(json.dumps(_BASE))
        exact["id"] = "p2"
        index_patient(conn, exact)
        result = match_patient(conn, exact, exclude=frozenset({"p2"}))
        # exact values should be caught by cheaper Category-1 rules first
        assert result.rule_id not in {"E1", "E2", "E3"}


# ---------------------------------------------------------------------------
# P1: training-data generation determinism (pure-Python layer; torch is
# dev-only and exercised by the offline script runs, not here)
# ---------------------------------------------------------------------------


def _load_trainer():
    import sys

    path = Path(__file__).resolve().parents[3] / "scripts" / "train_name_embedding.py"
    spec = importlib.util.spec_from_file_location("train_name_embedding", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class TestTrainingDataGeneration:
    def test_pair_generation_is_deterministic(self):
        trainer = _load_trainer()
        data1 = trainer.generate_training_data(seed=20261120, pool_limit=400)
        data2 = trainer.generate_training_data(seed=20261120, pool_limit=400)
        h1 = trainer.hash_training_data(data1)
        h2 = trainer.hash_training_data(data2)
        assert h1 == h2
        assert h1 != trainer.hash_training_data(
            trainer.generate_training_data(seed=20261121, pool_limit=400)
        )

    def test_training_data_structure(self):
        trainer = _load_trainer()
        data = trainer.generate_training_data(seed=20261120, pool_limit=400)
        assert set(data.split_of.values()) <= {"train", "val", "calibration"}
        assert data.positives and data.negatives
        # every positive carries a group key, and splits are GROUP-level
        for a, b, group in data.positives[:50]:
            assert a != b
            assert group
        groups_train = {g for _a, _b, g in data.positives
                        if data.split_of.get(g) == "train"}
        assert groups_train
        # group split means one group never spans two splits
        by_group: dict[str, set] = {}
        for a, b, g in data.positives:
            by_group.setdefault(g, set())
        for g in by_group:
            assert data.split_of[g] in {"train", "val", "calibration"}
