"""D6 HISTORIAN v0.0.26 — realism harness robustness (QA-D6H-001/002).

Red-first regressions, same tolerance doctrine as QA-D6S-001 (the
loader accepts structurally-valid-JSON / invalid-FHIR shapes with a
deterministic str()-coerced order; the downstream harness must not
crash on them with raw TypeError/KeyError):

* QA-D6H-001 — ``corrupt.inject_duplicates`` / ``realisticize_names``
  and ``benchmark._inject`` raised raw ``TypeError`` (mixed-type ids)
  or ``KeyError`` (missing id) on corpus shapes ``load_corpus``
  deliberately tolerates. Patients without a usable string id cannot
  participate in duplicate injection (dup ids, gold pairs and the
  matching index all key on the id) — they must pass through untouched
  instead of crashing; ordering keys are str()-coerced like
  ``corpus._sorted``.
* QA-D6H-002 — the strip-mode ``phase="all"`` single-process path of
  ``piqi_autocoding.run_benchmark`` dropped ``min_match_grade`` (the
  CLI ``--min-match-grade`` arm silently always ran 'certain'). The
  ``phase`` parameter itself was removed in FHIR4-25 (the benchmark is
  now a single-pass, in-process run); the propagation pin remains.
"""

from __future__ import annotations

import json
import unittest
import unittest.mock as mock
from pathlib import Path
from tempfile import TemporaryDirectory

from fhir4ds.realism.corrupt import (
    CorruptionConfig,
    inject_duplicates,
    realisticize_names,
)
from fhir4ds.realism.benchmark import run_benchmark as run_realism_benchmark


def _named_patient(pid: str) -> dict:
    return {"resourceType": "Patient", "id": pid, "gender": "male",
            "birthDate": "1950-06-15",
            "name": [{"use": "official", "family": "Smith",
                      "given": ["John"]}]}

class TestHarnessToleratesLoaderToleratedShapes(unittest.TestCase):
    """QA-D6H-001: no raw TypeError/KeyError from the corruption harness."""

    def test_inject_tolerates_non_string_id_patient(self):
        import random
        mixed = [_named_patient("m1"),
                 {"resourceType": "Patient", "id": 42,
                  "birthDate": "1950-01-01",
                  "name": [{"use": "official", "family": "Lee",
                            "given": ["Bob"]}]}]
        result = inject_duplicates(mixed, [],
                                   CorruptionConfig(seed=2,
                                                     num_patients=None))
        ids = [p.get("id") for p in result.patients]
        # both patients survive; the usable-id patient got its dup
        self.assertIn("m1", ids)
        self.assertIn(42, ids)
        self.assertEqual(
            sorted(g.original_id for g in result.gold_pairs), ["m1"])
        # the int-id patient passes through untouched (no dup emitted)
        int_id_patients = [p for p in result.patients
                           if p.get("id") == 42]
        self.assertEqual(len(int_id_patients), 1)

    def test_inject_tolerates_missing_id_patient(self):
        noid = [_named_patient("n1"),
                {"resourceType": "Patient",
                 "name": [{"family": "Lo", "given": ["Bo"]}]}]
        result = inject_duplicates(noid, [],
                                   CorruptionConfig(seed=2))
        self.assertEqual([g.original_id for g in result.gold_pairs],
                         ["n1"])
        # the id-less patient is still present in the output corpus
        self.assertEqual(len(result.patients), 3)

    def test_inject_tolerates_non_string_clinical_id(self):
        clinical = [{"resourceType": "Observation", "id": 7,
                     "subject": {"reference": "Patient/c1"},
                     "code": {"text": "bp"}}]
        result = inject_duplicates([_named_patient("c1")], clinical,
                                   CorruptionConfig(seed=3))
        dup_clinical = [r for r in result.clinical
                        if r.get("subject", {}).get("reference")
                        == "Patient/c1-d1"]
        self.assertEqual(len(dup_clinical), 1)

    def test_realisticize_tolerates_non_string_id(self):
        import random
        mixed = [{"resourceType": "Patient", "id": 9,
                  "birthDate": "1950-01-01",
                  "name": [{"family": "patient_9"}]}]
        out, replaced = realisticize_names(mixed, random.Random(1))
        self.assertEqual(len(out), 1)
        self.assertEqual(replaced, [])  # unusable id: skipped, not crashed

    def test_benchmark_tolerates_non_string_and_missing_ids(self):
        with TemporaryDirectory() as td:
            corp = Path(td) / "corpus"
            corp.mkdir()
            with (corp / "Patient.ndjson").open("w") as fh:
                fh.write(json.dumps(_named_patient("w1")) + "\n")
                fh.write(json.dumps({"resourceType": "Patient", "id": 7,
                                     "name": [{"family": "Lee",
                                               "given": ["Bob"]}]})
                         + "\n")
                fh.write(json.dumps({"resourceType": "Patient",
                                     "name": [{"family": "Lo"}]}) + "\n")
            report = run_realism_benchmark(corp, output_dir=td + "/out",
                                           seed=1, num_dup_patients=1)
        self.assertEqual(report["injection"]["gold_pairs"], 1)


class TestMinMatchGradePropagation(unittest.TestCase):
    """QA-D6H-002: the auto-coding leg passes the requested strictness arm."""

    def test_autocoding_leg_passes_min_match_grade(self):
        import fhir4ds.realism.piqi_autocoding as pa
        import fhir4ds.cql.terminology.in_process_adapter as ipa_mod

        def fake_run_autocoder(resources, endpoint,
                               min_match_grade="certain",
                               max_passes=3, search_mode="hybrid"):
            return {"cache_rows": 0, "engine_version": "stub",
                    "search_mode": search_mode,
                    "min_match_grade": min_match_grade,
                    "top_k": 3, "passes": []}

        with TemporaryDirectory() as td:
            corp = Path(td) / "corpus.ndjson"
            with corp.open("w") as fh:
                fh.write(json.dumps({
                    "resourceType": "Patient", "id": "p1",
                    "birthDate": "1980-01-01"}) + "\n")
                fh.write(json.dumps({
                    "resourceType": "Condition", "id": "c1",
                    "subject": {"reference": "Patient/p1"},
                    "code": {"coding": [
                        {"code": "195967001",
                         "system": "http://snomed.info/sct",
                         "display": "Asthma"}]}}) + "\n")
            with mock.patch.object(ipa_mod, "InProcessTerminologyEndpoint",
                                   object), \
                    mock.patch.object(pa, "run_autocoder",
                                      fake_run_autocoder):
                report = pa.run_benchmark(corp, td + "/out",
                                          num_patients=1,
                                          skip_autocoding=False,
                                          min_match_grade="probable")
        auto = report["autocoding"]
        self.assertEqual(auto["min_match_grade"], "probable")


if __name__ == "__main__":
    unittest.main()
