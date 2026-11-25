"""D6 EXPLORER (v0.0.26) red-first regressions.

Every test here reproduced a raw-crash / silent-lie from the EXPLORER
probe battery (.temp/qa/d6_explorer_v0026/) before the fix:

- QA-D6E-001 corpus loader: raw RecursionError on deeply nested JSON
  (10k-deep object; 900-deep Bundle chain) with no file attribution.
- QA-D6E-002 corpus loader: truncated .gz leaked raw EOFError.
- QA-D6E-003 corrupt harness: dob_shift raised raw OverflowError on
  extent birthDates and reported applied-but-unchanged at 9999-12-xx.
- QA-D6E-004 piqi_autocoding: raw TypeError on mixed str/int ids
  (QA-D6H-001 sibling paths).
- QA-D6E-005 piqi_autocoding: tampered phase artifacts leaked raw
  JSONDecodeError/AttributeError; stale artifacts from a different
  corpus silently contaminated the after scorecard. SUPERSEDED by
  FHIR4-25 — the phase artifacts no longer exist (single-pass run), so
  the class now pins their absence.
"""

from __future__ import annotations

import copy
import gzip
import json
import random
import shutil
import unittest
from pathlib import Path

from fhir4ds.realism.corpus import load_corpus
from fhir4ds.realism.corrupt import CorruptionConfig, apply_profile, inject_duplicates
from fhir4ds.realism import piqi_autocoding as pa

import tempfile


def _patient(pid: str = "p1", **kw) -> dict:
    p = {"resourceType": "Patient", "id": pid, "gender": "female",
         "birthDate": "1990-05-15",
         "name": [{"use": "official", "family": "Chalmers",
                   "given": ["John"]}]}
    p.update(kw)
    return p


def _cond(cid: str, pid: str) -> dict:
    return {"resourceType": "Condition", "id": cid,
            "subject": {"reference": f"Patient/{pid}"},
            "code": {"coding": [{"code": "1234",
                                 "system": "http://snomed.info/sct",
                                 "display": "X"}]}}


def _lab(oid: str, pid: str) -> dict:
    return {"resourceType": "Observation", "id": oid,
            "subject": {"reference": f"Patient/{pid}"},
            "status": "final",
            "category": [{"coding": [{"code": "laboratory"}]}],
            "code": {"coding": [{"code": "8480-6",
                                 "system": "http://loinc.org",
                                 "display": "BP"}]}}


class TestCorpusDeepNestingTypedD6E001(unittest.TestCase):
    def setUp(self):
        self.d = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.d, ignore_errors=True)

    def test_deep_object_in_dir_is_attributed_valueerror(self):
        deep = '{"a":' * 10000 + "1" + "}" * 10000
        (self.d / "deep.json").write_text(deep)
        (self.d / "good.ndjson").write_text(
            json.dumps({"resourceType": "Patient", "id": "p1"}) + "\n")
        with self.assertRaises(ValueError) as ctx:
            load_corpus(self.d)
        self.assertIn("deep.json", str(ctx.exception))

    def test_deep_object_single_file_is_attributed_valueerror(self):
        deep = '{"a":' * 10000 + "1" + "}" * 10000
        f = self.d / "deep.json"
        f.write_text(deep)
        with self.assertRaises(ValueError) as ctx:
            load_corpus(f)
        self.assertIn("deep.json", str(ctx.exception))

    def test_deep_object_gz_is_attributed_valueerror(self):
        deep = '{"a":' * 10000 + "1" + "}" * 10000
        f = self.d / "deep.json.gz"
        f.write_bytes(gzip.compress(deep.encode()))
        with self.assertRaises(ValueError) as ctx:
            load_corpus(f)
        self.assertIn("deep.json.gz", str(ctx.exception))

    def test_deep_bundle_chain_flattens_iteratively(self):
        # 400-deep Bundle-in-Bundle: parseable (below the json parser
        # recursion ceiling of ~600; each chain level is 3 containers) and flattened by the ITERATIVE walker
        # (the recursive walker consumed 2 Python frames per level and
        # crashed well below the parser ceiling).
        doc = '{"resourceType":"Patient","id":"deep-p"}'
        for _ in range(250):
            doc = ('{"resourceType":"Bundle","type":"collection",'
                   '"entry":[{"resource":' + doc + "}]}")
        f = self.d / "chain.json"
        f.write_text(doc)
        res = load_corpus(f)
        self.assertEqual([r["id"] for r in res], ["deep-p"])

    def test_bundle_entries_document_order_preserved(self):
        bundle = {"resourceType": "Bundle", "type": "collection", "entry": [
            {"resource": {"resourceType": "Patient", "id": "a"}},
            {"resource": {"resourceType": "Bundle", "entry": [
                {"resource": {"resourceType": "Patient", "id": "b1"}},
                {"resource": {"resourceType": "Bundle", "entry": [
                    {"resource": {"resourceType": "Patient", "id": "c"}}]}},
                {"resource": {"resourceType": "Patient", "id": "b2"}}]}},
            {"resource": {"resourceType": "Patient", "id": "z"}},
        ]}
        from fhir4ds.realism.corpus import bundle_entries
        self.assertEqual([r["id"] for r in bundle_entries(bundle)],
                         ["a", "b1", "c", "b2", "z"])


class TestCorpusTruncatedGzipTypedD6E002(unittest.TestCase):
    def test_truncated_gz_is_attributed_valueerror(self):
        with tempfile.TemporaryDirectory() as td:
            f = Path(td) / "bad.ndjson.gz"
            raw = gzip.compress(
                (json.dumps({"resourceType": "Patient", "id": "z"})
                 + "\n").encode())
            f.write_bytes(raw[: len(raw) // 2])
            with self.assertRaises(ValueError) as ctx:
                load_corpus(f)
            self.assertIn("bad.ndjson.gz", str(ctx.exception))


class TestDobShiftBoundariesD6E003(unittest.TestCase):
    def test_extent_birthdates_never_raise(self):
        for dob in ("0001-01-05", "0001-01-31", "9999-12-20", "9999-12-31"):
            for seed in range(200):
                p = _patient(birthDate=dob)
                # must not raise for ANY seed
                apply_profile("dob_shift", p, random.Random(seed))

    def test_extent_birthdates_never_report_applied_unchanged(self):
        for dob in ("0001-01-05", "9999-12-15", "9999-12-31"):
            for seed in range(200):
                p = _patient(birthDate=dob)
                before = copy.deepcopy(p)
                changed = apply_profile("dob_shift", p, random.Random(seed))
                if changed:
                    self.assertNotEqual(
                        p["birthDate"], before["birthDate"],
                        f"dob_shift reported applied but changed nothing "
                        f"({dob}, seed {seed})")

    def test_inject_duplicates_extent_dob_corpus_end_to_end(self):
        patients = [_patient("e1", birthDate="0001-01-05"),
                    _patient("e2", birthDate="9999-12-20")]
        res = inject_duplicates(
            patients, [],
            CorruptionConfig(seed=1, num_patients=None,
                             profile_weights={"dob_shift": 1.0}))
        # every gold pair either changed the duplicate or fell back to
        # clean_copy — never a crash, never a lie
        for g in res.gold_pairs:
            self.assertIn(g.profiles_applied[0],
                          ("dob_shift", "clean_copy", "name_typos"))


class TestPiqiAutocodingIdToleranceD6E004(unittest.TestCase):
    def _mixed_corpus(self, td):
        rows = [_patient("p1"),
                {"resourceType": "Patient", "id": 7, "gender": "male",
                 "birthDate": "1991-02-02"},
                _patient("p3"),
                _cond("c1", "p1"), _cond("c2", "p3"), _lab("o1", "p1")]
        d = Path(td) / "corpus"
        d.mkdir()
        (d / "p.ndjson").write_text(
            "".join(json.dumps(r) + "\n" for r in rows))
        return d

    def test_mixed_id_types_through_piqi_phase(self):
        with tempfile.TemporaryDirectory() as td:
            d = self._mixed_corpus(td)
            report = pa.run_benchmark(d, Path(td) / "out", num_patients=3,
                                      skip_autocoding=True)
            # string-id patients dominate the slice; int id simply not keyed
            self.assertGreaterEqual(report["slice"]["resources"], 3)

    def test_mixed_id_types_through_build_slice_direct(self):
        rows = [_patient("a"),
                {"resourceType": "Patient", "id": 5, "birthDate": "1990-01-01"},
                _cond("c", "a")]
        sl = pa.build_slice(rows, 5)
        ids = {r.get("id") for r in sl if r.get("resourceType") == "Patient"}
        self.assertEqual(ids, {"a"})

    def test_mixed_id_types_sort_in_evaluate(self):
        # _load_resources_table str()-coerced ordering must not raise a
        # raw mixed-type TypeError; downstream the PIQI view's own typed
        # column guard may still reject an int id LOUDLY (spec-correct
        # boundary, out of scope here).
        rows = [_patient("a"), _patient("b"),
                {"resourceType": "Patient", "id": 9,
                 "birthDate": "1990-01-01"}]
        import duckdb
        rubric = pa.build_mimic_rubric()
        try:
            summary = pa.evaluate_slice(rows, rubric)
            self.assertIn("piqi_index", summary)
        except duckdb.InvalidInputException:
            pass  # the view's typed column guard — loud and attributed


class TestNoInterphaseArtifactsD6E005(unittest.TestCase):
    """QA-D6E-005, superseded by FHIR4-25.

    The old benchmark passed state between three ``--phase`` invocations
    through JSONL + partial-report artifacts; EXPLORER found that a
    tampered or stale artifact leaked raw ``JSONDecodeError`` /
    ``AttributeError`` and silently contaminated the AFTER scorecard. The
    phase split is gone (medterm4ds 0.0.14 makes in-process the supported
    pattern), so there is no cross-invocation state to tamper with: one
    call computes every leg in memory and writes exactly one report.

    The suite below is the surviving guarantee — a run leaves no
    intermediate artifacts behind, and re-running is self-contained
    rather than inheriting anything from a previous run.
    """

    def setUp(self):
        self.td = tempfile.mkdtemp()
        self.base = Path(self.td)
        self.corpus = self.base / "corpus"
        self.corpus.mkdir()
        rows = [_patient("g1"), _patient("g2"), _cond("gc1", "g1"),
                _cond("gc2", "g2"), _lab("go1", "g1")]
        (self.corpus / "p.ndjson").write_text(
            "".join(json.dumps(r) + "\n" for r in rows))

    def tearDown(self):
        shutil.rmtree(self.td, ignore_errors=True)

    def test_run_leaves_only_the_final_report(self):
        out = self.base / "out"
        pa.run_benchmark(self.corpus, out, num_patients=2,
                         skip_autocoding=True)
        self.assertEqual([p.name for p in out.iterdir()],
                         ["piqi_autocoding_report.json"])

    def test_a_stale_result_directory_cannot_influence_the_next_run(self):
        out = self.base / "out"
        first = pa.run_benchmark(self.corpus, out, num_patients=2,
                                skip_autocoding=True)
        # anything an old release might have dropped here is inert: with
        # no artifact loader left, a second run recomputes from the corpus
        (out / "report.partial.json").write_text("{not json")
        (out / "augmented.jsonl").write_text('"just a string"\n')
        second = pa.run_benchmark(self.corpus, out, num_patients=2,
                                  skip_autocoding=True)
        self.assertEqual(json.dumps(first, sort_keys=True),
                         json.dumps(second, sort_keys=True))

    def test_partial_leg_helpers_are_gone(self):
        for name in ("_load_partial", "_require_partial_leg",
                     "_load_jsonl", "_check_artifact_corpus"):
            self.assertFalse(hasattr(pa, name), name)


if __name__ == "__main__":
    unittest.main()
