"""Acceptance tests for the realism validation harness (AMUX-150 follow-on).

Written BEFORE the implementation (red-first doctrine). Group order:

1. corpus loader (NDJSON dir / bundles / MIMIC quirks)
2. corruption profiles (each documented transform)
3. injection determinism + gold-pair integrity
4. benchmark known-answer on the tiny fixture (P/R arithmetic, clean-dup
   floor, transliteration-gap pin) + byte-identical determinism
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from fhir4ds.realism.corpus import (
    bundle_entries,
    load_bundle_file,
    load_corpus,
    load_ndjson_dir,
)
from fhir4ds.realism.corrupt import (
    DEFAULT_PROFILE_WEIGHTS,
    PROFILES,
    TRANSLITERATION_GROUPS,
    CorruptionConfig,
    apply_profile,
    damerau_le1_typo,
    inject_duplicates,
)

FIXTURES = Path(__file__).resolve().parent / "fixtures"
TINY = FIXTURES / "tiny_corpus"


def tiny_patients() -> list[dict]:
    resources = load_corpus(TINY)
    return sorted(
        (r for r in resources if r["resourceType"] == "Patient"),
        key=lambda r: r["id"],
    )


def tiny_clinical() -> list[dict]:
    resources = load_corpus(TINY)
    return sorted(
        (r for r in resources if r["resourceType"] != "Patient"),
        key=lambda r: r["id"],
    )


# ---------------------------------------------------------------------------
# 1. corpus loader
# ---------------------------------------------------------------------------


class TestCorpusLoader:
    def test_ndjson_dir_mimic_layout(self):
        resources = load_corpus(TINY)
        types = {r["resourceType"] for r in resources}
        assert types == {"Patient", "Observation", "Condition", "Encounter"}
        assert len([r for r in resources if r["resourceType"] == "Patient"]) == 3

    def test_ndjson_dir_loader_sorted_deterministic(self):
        a = load_ndjson_dir(TINY)
        b = load_ndjson_dir(TINY)
        assert a == b
        ids = [r["id"] for r in a]
        assert ids == sorted(ids)

    def test_bundle_file(self):
        resources = load_bundle_file(FIXTURES / "tiny_bundle" / "bundle.json")
        assert {r["id"] for r in resources} == {"pat-delta", "obs-delta-1"}

    def test_bundle_dir(self):
        resources = load_corpus(FIXTURES / "tiny_bundle")
        assert {r["id"] for r in resources} == {"pat-delta", "obs-delta-1"}

    def test_load_corpus_dispatches_by_shape(self):
        assert {r["id"] for r in load_corpus(TINY / "Patient.ndjson")} == {
            "pat-alpha", "pat-bravo", "pat-charlie",
        }
        assert {r["id"] for r in load_corpus(
            FIXTURES / "tiny_bundle" / "bundle.json")} == {
            "pat-delta", "obs-delta-1",
        }

    def test_bundle_quirks_tolerated(self, tmp_path):
        # MIMIC demo quirks: entries without a resource, non-resource JSON
        # files in the directory, a searchset Bundle wrapping FHIR Bundle
        # entries, and blank NDJSON lines.
        bundle = {
            "resourceType": "Bundle",
            "type": "searchset",
            "entry": [
                {"fullUrl": "urn:uuid:x", "resource": {
                    "resourceType": "Patient", "id": "q1"}},
                {"request": {"method": "GET"}},  # no resource
                {"resource": {  # a contained Bundle entry
                    "resourceType": "Bundle", "id": "inner",
                    "entry": [{"resource": {
                        "resourceType": "Patient", "id": "q2"}}]}},
            ],
        }
        p = tmp_path / "Bundle_quirks.json"
        p.write_text(json.dumps(bundle))
        mixed = tmp_path / "Patient.ndjson"
        mixed.write_text(
            '{"resourceType":"Patient","id":"q3"}\n\n'
            '{"resourceType":"Patient","id":"q4"}\n')
        (tmp_path / "README.txt").write_text("not fhir")
        resources = load_corpus(tmp_path)
        assert {r["id"] for r in resources} == {"q1", "q2", "q3", "q4"}

    def test_bad_payload_rejected(self, tmp_path):
        (tmp_path / "junk.ndjson").write_text("not json at all\n")
        with pytest.raises(ValueError):
            load_corpus(tmp_path)

    def test_missing_path(self):
        with pytest.raises(FileNotFoundError):
            load_corpus(FIXTURES / "does-not-exist")

    def test_gzip_ndjson(self, tmp_path):
        import gzip
        src = (TINY / "Patient.ndjson").read_bytes()
        (tmp_path / "MimicPatient.ndjson.gz").write_bytes(
            gzip.compress(src))
        resources = load_corpus(tmp_path)
        assert {r["id"] for r in resources} == {
            "pat-alpha", "pat-bravo", "pat-charlie"}


# ---------------------------------------------------------------------------
# 2. corruption profiles
# ---------------------------------------------------------------------------


def base_patient() -> dict:
    return {
        "resourceType": "Patient",
        "id": "pat-x",
        "birthDate": "1980-04-12",
        "name": [{"use": "official", "family": "Alvarez",
                  "given": ["Robert"]}],
        "telecom": [{"system": "phone", "value": "555-301-4444"}],
        "address": [{"use": "home", "line": ["12 Elm Street"],
                     "city": "Springfield", "state": "IL",
                     "postalCode": "60601"}],
        "identifier": [{"type": {"coding": [{"code": "MR"}]},
                        "system": "urn:oid:1.2.3.4.5",
                        "value": "100234"}],
    }


class TestDamerauTypoHelper:
    def test_distance_one(self):
        for word in ("Robert", "Alvarez", "Mohammed"):
            out = damerau_le1_typo(word, seed=hash(word) % (2**31))
            assert out != word
            # DL distance 1: same multiset +- one op
            assert abs(len(out) - len(word)) <= 1
            shared = sum(
                1 for c in set(word) if c in set(out))
            assert shared >= min(len(set(word)), len(set(out))) - 1


class TestProfiles:
    def _apply(self, profile, patient, seed=7):
        import random
        rng = random.Random(seed)
        return apply_profile(profile, patient, rng)

    def test_name_typos(self):
        p = base_patient()
        assert self._apply("name_typos", p) is True
        given = p["name"][0]["given"][0]
        fam = p["name"][0]["family"]
        orig = ("Robert", "Alvarez")
        changed = given != orig[0] or fam != orig[1]
        assert changed

    def test_name_nicknames(self):
        p = base_patient()  # Robert -> Bob/Rob/...
        assert self._apply("name_nicknames", p) is True
        given = p["name"][0]["given"][0]
        from fhir4ds.matching.normalizers import nickname_set, norm_text
        eq = nickname_set(norm_text("robert"))
        assert norm_text(given) in eq
        assert norm_text(given) != "robert"

    def test_name_nicknames_inapplicable_on_unknown_name(self):
        p = base_patient()
        p["name"][0]["given"] = ["Xyzzyq"]  # not in the nickname table
        assert self._apply("name_nicknames", p) is False

    def test_name_transliteration(self):
        p = base_patient()
        p["name"][0]["given"] = ["Mohammed"]
        assert self._apply("name_transliteration", p) is True
        given = p["name"][0]["given"][0]
        group = next(g for g in TRANSLITERATION_GROUPS
                     if "mohammed" in g)
        assert given.lower() in group
        assert given != "Mohammed"

    def test_transliteration_table_is_symmetric_and_documented(self):
        flat = [n for g in TRANSLITERATION_GROUPS for n in g]
        assert len(flat) == len(set(flat))  # no overlaps
        # ComplyAdvantage-style examples must be present
        joined = " ".join(flat)
        for name in ("mohammed", "muhammad", "mohammad", "muhummad",
                     "stephen", "steven", "stephan",
                     "sofia", "sofiya", "sofia"):
            assert name in joined

    def test_dob_shift(self):
        p = base_patient()
        assert self._apply("dob_shift", p) is True
        assert p["birthDate"] != "1980-04-12"
        import datetime as dt
        a = dt.date.fromisoformat("1980-04-12")
        b = dt.date.fromisoformat(p["birthDate"])
        delta = abs((b - a).days)
        assert 0 < delta <= 31  # day-scale or single-month shift

    def test_address_move(self):
        p = base_patient()
        assert self._apply("address_move", p) is True
        addr = p["address"][0]
        orig_line, orig_zip = "12 Elm Street", "60601"
        assert addr["line"][0] != orig_line or addr["postalCode"] != orig_zip

    def test_phone_digit_flip(self):
        p = base_patient()
        assert self._apply("phone_digit_flip", p) is True
        new = p["telecom"][0]["value"]
        digits_old = "5553014444"
        digits_new = "".join(ch for ch in new if ch.isdigit())
        assert len(digits_old) == len(digits_new)
        diffs = sum(1 for a, b in zip(digits_old, digits_new) if a != b)
        assert diffs == 1

    def test_mrn_variant_keeps_digits(self):
        p = base_patient()
        assert self._apply("mrn_variant", p) is True
        val = p["identifier"][0]["value"]
        assert val != "100234"
        assert "".join(c for c in val if c.isdigit()) == "100234"

    def test_clean_copy_is_identity(self):
        p = base_patient()
        q = copy.deepcopy(p)
        assert self._apply("clean_copy", q) is True
        assert q == p

    def test_unknown_profile_rejected(self):
        import random
        with pytest.raises(ValueError):
            apply_profile("nope", base_patient(), random.Random(1))

    def test_profile_registry_matches_weights(self):
        assert set(PROFILES) - {"clean_copy"} == set(DEFAULT_PROFILE_WEIGHTS)


# ---------------------------------------------------------------------------
# 3. injection: determinism + gold integrity
# ---------------------------------------------------------------------------


class TestInjection:
    CFG = CorruptionConfig(
        seed=1234, num_patients=2, dups_per_patient=1,
        clean_duplicate_ratio=0.5,
    )

    def test_deterministic_same_seed(self):
        patients, clinical = tiny_patients(), tiny_clinical()
        r1 = inject_duplicates(patients, clinical, self.CFG)
        r2 = inject_duplicates(tiny_patients(), tiny_clinical(), self.CFG)
        assert r1.patients == r2.patients
        assert r1.clinical == r2.clinical
        assert r1.gold_pairs == r2.gold_pairs
        assert r1.seed == 1234

    def test_different_seed_different_output(self):
        patients, clinical = tiny_patients(), tiny_clinical()
        a = inject_duplicates(patients, clinical,
                              CorruptionConfig(seed=1, num_patients=2))
        b = inject_duplicates(patients, clinical,
                              CorruptionConfig(seed=2, num_patients=2))
        assert a != b

    def test_gold_pair_integrity(self):
        patients = tiny_patients()
        clinical = tiny_clinical()
        orig_patients = copy.deepcopy(patients)
        orig_clinical = copy.deepcopy(clinical)
        res = inject_duplicates(patients, clinical,
                                CorruptionConfig(seed=99, num_patients=2))
        # originals untouched
        assert patients == orig_patients
        assert clinical == orig_clinical
        # gold pairs reference real ids, dup ids new, profiles recorded
        assert len(res.gold_pairs) == 2
        known = {p["id"] for p in patients}
        by_id = {p["id"]: p for p in res.patients}
        for pair in res.gold_pairs:
            assert pair.original_id in known
            assert pair.dup_id not in known
            assert pair.dup_id in by_id
            assert pair.profiles_applied  # at least one profile
            assert all(p in PROFILES for p in pair.profiles_applied)
        # clinical duplicates carry the rewritten patient ref
        dup_ids = {p.dup_id for p in res.gold_pairs}
        dup_clinical = [c for c in res.clinical
                        if c["id"].endswith(tuple("-d%d" % i
                                                  for i in range(1, 4)))]
        assert dup_clinical, "expected injected clinical duplicates"
        for c in dup_clinical:
            ref = c.get("subject", {}).get("reference", "")
            pid = ref.split("/")[-1]
            assert pid in dup_ids | known

    def test_clean_duplicate_mode(self):
        patients, clinical = tiny_patients(), tiny_clinical()
        res = inject_duplicates(
            patients, clinical,
            CorruptionConfig(seed=5, num_patients=1,
                             clean_duplicate_ratio=1.0))
        pair = res.gold_pairs[0]
        assert pair.profiles_applied == ("clean_copy",)
        orig = {p["id"]: p for p in patients}[pair.original_id]
        dup = {p["id"]: p for p in res.patients}[pair.dup_id]
        dup_cmp = copy.deepcopy(dup)
        dup_cmp["id"] = orig["id"]
        assert dup_cmp == orig

    def test_multi_profile_stack(self):
        patients, clinical = tiny_patients(), tiny_clinical()
        res = inject_duplicates(
            patients, clinical,
            CorruptionConfig(seed=11, num_patients=3,
                             stack_probability=1.0))
        assert any(len(p.profiles_applied) >= 2 for p in res.gold_pairs)

    def test_num_patients_none_means_all(self):
        patients, clinical = tiny_patients(), tiny_clinical()
        res = inject_duplicates(patients, clinical,
                                CorruptionConfig(seed=3))
        assert len(res.gold_pairs) == len(patients)


class TestMimicPreprocessing:
    def _mimic_style_patient(self) -> dict:
        return {
            "resourceType": "Patient",
            "id": "mimic-1",
            "birthDate": "2083-04-10",
            "name": [{"use": "official", "family": "Patient_10007795"}],
            "identifier": [{"system":
                            "http://mimic.mit.edu/fhir/mimic/identifier/patient",
                            "value": "10007795"}],
        }

    def test_realisticize_names(self):
        import random
        from fhir4ds.realism.corrupt import realisticize_names
        real = base_patient()  # has real given+family
        synthetic = self._mimic_style_patient()
        out, replaced = realisticize_names(
            [real, synthetic], random.Random(4))
        assert replaced == ["mimic-1"]
        by_id = {p["id"]: p for p in out}
        # synthetic got a generated official name with given+family
        name = by_id["mimic-1"]["name"][0]
        assert name["given"] and name["family"]
        assert not name["family"].lower().startswith("patient_")
        # real patient untouched (same object)
        assert by_id["pat-x"] is real

    def test_rebase_future_birthdates(self):
        from fhir4ds.realism.corrupt import rebase_future_birthdates
        p = self._mimic_style_patient()
        out, shifted = rebase_future_birthdates([p, base_patient()])
        assert shifted == 1
        by_id = {q["id"]: q for q in out}
        assert by_id["mimic-1"]["birthDate"] == "1983-04-10"
        assert by_id["pat-x"]["birthDate"] == "1980-04-12"
        # original not mutated
        assert p["birthDate"] == "2083-04-10"

    def test_injection_with_mimic_preprocessing(self):
        patients = [self._mimic_style_patient()]
        res = inject_duplicates(
            patients, [],
            CorruptionConfig(seed=8, num_patients=1,
                             realistic_names=True,
                             rebase_future_birthdates=True,
                             clean_duplicate_ratio=1.0))
        assert res.names_replaced == ["mimic-1"]
        assert res.birthdates_rebased == 1
        pair = res.gold_pairs[0]
        orig = {p["id"]: p for p in res.patients}[pair.original_id]
        dup = {p["id"]: p for p in res.patients}[pair.dup_id]
        # clean copy AFTER preprocessing: identical names/dob, both past
        assert dup["name"] == orig["name"]
        assert dup["birthDate"] == orig["birthDate"] == "1983-04-10"


# ---------------------------------------------------------------------------
# 4. benchmark
# ---------------------------------------------------------------------------


class TestBenchmark:
    def test_tiny_known_answer(self, tmp_path):
        from fhir4ds.realism.benchmark import run_benchmark
        report = run_benchmark(
            TINY, output_dir=str(tmp_path / "out"),
            num_dup_patients=3, dups_per_patient=1,
            clean_duplicate_ratio=1.0, seed=42,
        )
        m = report["matching"]
        # exact duplicates: the engine must find every clean pair
        assert m["gold_pairs"] == 3
        assert m["true_positives"] == 3
        assert m["recall"] == 1.0
        assert m["precision"] == 1.0
        # per-profile recall: clean_copy found
        assert m["per_profile_recall"]["clean_copy"] == 1.0
        d = report["dedup"]
        assert d["clusters"] >= 0
        assert d["cross_patient_clusters"] == 0
        assert isinstance(d["curation_queue_by_kind"], dict)
        # determinism fields recorded
        assert report["seed"] == 42
        assert Path(report["report_path"]).exists()

    def test_transliteration_gap_pinned(self, tmp_path):
        from fhir4ds.realism.benchmark import run_benchmark
        # pat-bravo's given name is Mohammed: force the transliteration
        # profile so every dup pair is a transliteration variant.
        report = run_benchmark(
            TINY, output_dir=str(tmp_path / "out"),
            num_dup_patients=3, dups_per_patient=1, seed=77,
            profile_weights={"name_transliteration": 1.0},
        )
        m = report["matching"]
        gap = m["per_profile_recall"].get("name_transliteration")
        assert gap is not None
        # DOCUMENTED GAP: current rules have no transliteration table;
        # the engine is expected to miss these pairs. Pin < 1.0 so the
        # day transliteration support lands, this test forces a review.
        assert gap < 1.0, (
            "transliteration pairs are being matched — update the "
            "documented-gap pin in realism_harness_report.md")

    def test_byte_identical_reports(self, tmp_path):
        from fhir4ds.realism.benchmark import run_benchmark
        r1 = run_benchmark(TINY, output_dir=str(tmp_path / "a"), seed=9,
                           num_dup_patients=2)
        r2 = run_benchmark(TINY, output_dir=str(tmp_path / "b"), seed=9,
                           num_dup_patients=2)
        t1 = Path(r1["report_path"]).read_bytes()
        t2 = Path(r2["report_path"]).read_bytes()
        assert t1 == t2

    def test_pr_arithmetic(self, tmp_path):
        from fhir4ds.realism.benchmark import run_benchmark
        report = run_benchmark(TINY, output_dir=str(tmp_path / "o"),
                               seed=21, num_dup_patients=2)
        m = report["matching"]
        pred = m["predicted_pairs"]
        tp = m["true_positives"]
        assert tp <= m["gold_pairs"]
        assert tp <= pred
        if pred:
            assert abs(m["precision"] - tp / pred) < 1e-9
        assert abs(m["recall"] - tp / m["gold_pairs"]) < 1e-9

    def test_name_dob_only_gap_pinned(self, tmp_path):
        """KNOWN-ANSWER PIN (rule-table observation, not a harness bug):
        an EXACT duplicate of a patient carrying only first+last+DOB
        (no phone/email/street/identifier) is NOT matched — no Category-1
        rule covers name+DOB alone. This is exactly the class of fact
        the realism harness exists to surface; revisit this pin only
        when a name+DOB rule is deliberately added."""
        from fhir4ds.realism.corrupt import CorruptionConfig, inject_duplicates
        from fhir4ds.matching.store import create_matching_tables, index_patient
        from fhir4ds.matching.engine import match_patient
        import duckdb
        minimal = {
            "resourceType": "Patient", "id": "pat-min",
            "birthDate": "1990-02-02",
            "name": [{"use": "official", "family": "Nguyen",
                      "given": ["Bao"]}],
        }
        res = inject_duplicates([minimal], [],
                                CorruptionConfig(seed=1, num_patients=1,
                                                 clean_duplicate_ratio=1.0))
        conn = duckdb.connect()
        create_matching_tables(conn)
        for p in res.patients:
            index_patient(conn, p)
        result = match_patient(conn, res.patients[0],
                               exclude=frozenset({res.patients[0]["id"]}))
        assert result.outcome == "no_match"
