"""Tests for the PIQI auto-coding benchmark module.

The end-to-end legs (PIQI evaluation, medterm4ds augmentation) are
covered by the CLI run against a real corpus; these unit tests pin the
deterministic mechanics — patient slicing, text-only census, code
stripping, gold-accuracy scoring, and the stub-endpoint augmentation
path — without requiring medterm4ds or the MIMIC corpus.
"""

from __future__ import annotations

import unittest

from fhir4ds.realism.piqi_autocoding import (
    DEFAULT_STRIPPING,
    build_mimic_rubric,
    build_slice,
    census_text_only,
    gold_accuracy,
    recovery_table,
    run_autocoder,
    strip_codings,
    unmapped_classes,
)


def _condition(cid: str, pid: str, code: str, system: str,
               display: str) -> dict:
    return {"resourceType": "Condition", "id": cid,
            "subject": {"reference": f"Patient/{pid}"},
            "code": {"coding": [{"code": code, "system": system,
                                 "display": display}]}}


def _lab(oid: str, pid: str, code: str, display: str) -> dict:
    return {"resourceType": "Observation", "id": oid,
            "subject": {"reference": f"Patient/{pid}"},
            "status": "final",
            "category": [{"coding": [{"code": "laboratory"}]}],
            "code": {"coding": [{"code": code,
                                 "system": "http://loinc.org",
                                 "display": display}]}}


def _patient(pid: str) -> dict:
    return {"resourceType": "Patient", "id": pid, "gender": "female",
            "birthDate": "2083-04-10"}


class StubEndpoint:
    """TerminologyEndpoint stub: returns one fixed certain match."""

    def __init__(self, code: str = "91302008",
                 system: str = "http://snomed.info/sct",
                 display: str = "Sepsis"):
        self.code = code
        self.system = system
        self.display = display
        self.batch_calls = 0

    def search_text(self, text, category, mode="hybrid"):
        return [self._result()]

    def search_batch(self, pairs, mode="hybrid"):
        self.batch_calls += 1
        return [[self._result()] for _ in pairs]

    def _result(self):
        from fhir4ds.cql.terminology.types import SearchResult
        return SearchResult(system=self.system, code=self.code,
                            display=self.display, score=0.99,
                            match_grade="certain", search_mode=mode_name(),
                            index_version="stub-1")


def mode_name() -> str:
    return "hybrid"


class TestSliceAndCensus(unittest.TestCase):
    def test_build_slice_takes_first_n_patients_sorted(self):
        corpus = [_patient("p2"), _patient("p1"),
                  _condition("c1", "p1", "a", "s", "A"),
                  _condition("c2", "p2", "b", "s", "B"),
                  _condition("c3", "p9", "c", "s", "C")]
        sl = build_slice(corpus, 1)
        self.assertEqual({r["id"] for r in sl}, {"p1", "c1"})

    def test_build_slice_without_patients_raises(self):
        with self.assertRaises(ValueError):
            build_slice([_condition("c1", "p1", "a", "s", "A")], 2)

    def test_census_counts_text_only(self):
        coded = _condition("c1", "p1", "a", "s", "A")
        text_only = {"resourceType": "Condition", "id": "c2",
                     "code": {"text": "Sepsis"}}
        display_only = {"resourceType": "Condition", "id": "c3",
                        "code": {"coding": [{"display": "Sepsis"}]}}
        absent = {"resourceType": "Condition", "id": "c4"}
        census = census_text_only([coded, text_only, display_only, absent])
        self.assertEqual(census["per_type"]["Condition"],
                         {"coded": 1, "text_only": 2, "absent": 1})
        self.assertEqual(census["text_only_total"], 2)


class TestStripCodings(unittest.TestCase):
    def setUp(self):
        self.corpus = [
            _patient("p1"),
            _condition("c2", "p1", "x2", "s", "B2"),
            _condition("c1", "p1", "x1", "s", "B1"),
            _condition("c3", "p2", "x3", "s", "B3"),
            _lab("o1", "p1", "50885", "Bilirubin, Total"),
            # vital-signs category: never stripped under DEFAULT_STRIPPING
            {"resourceType": "Observation", "id": "v1",
             "subject": {"reference": "Patient/p1"},
             "category": [{"coding": [{"code": "vital-signs"}]}],
             "code": {"coding": [{"code": "8867-4",
                                  "system": "http://loinc.org",
                                  "display": "Heart rate"}]}},
        ]

    def test_strip_is_deterministic_and_preserves_text(self):
        stripped1, gold1 = strip_codings(self.corpus, DEFAULT_STRIPPING)
        stripped2, gold2 = strip_codings(self.corpus, DEFAULT_STRIPPING)
        self.assertEqual([g["id"] for g in gold1],
                         [g["id"] for g in gold2])
        # strip_codings works on whatever it is given (slice separately):
        # sorted (resourceType, id) order — Conditions c1..c3, then lab o1
        self.assertEqual([g["id"] for g in gold1],
                         ["c1", "c2", "c3", "o1"])
        clone = stripped1[0]
        self.assertEqual(clone["code"]["coding"], [])
        self.assertEqual(clone["code"]["text"], "B1")
        # originals untouched
        self.assertTrue(self.corpus[2]["code"]["coding"])
        # vitals untouched by stripping (control class)
        self.assertFalse(any(g["id"] == "v1" for g in gold1))

    def test_cap_applies_per_patient_in_id_order(self):
        spec = {"Condition": {"path": "code", "cap": 1}}
        _, gold = strip_codings(self.corpus, spec)
        # each patient keeps their FIRST condition in id order: p1→c1, p2→c3
        self.assertEqual([g["id"] for g in gold], ["c1", "c3"])

    def test_no_text_and_no_display_is_skipped(self):
        silent = {"resourceType": "Condition", "id": "c9",
                  "subject": {"reference": "Patient/p1"},
                  "code": {"coding": [{"code": "z", "system": "s"}]}}
        _, gold = strip_codings([silent], DEFAULT_STRIPPING)
        self.assertEqual(gold, [])

    def test_existing_text_is_kept_verbatim(self):
        with_text = {"resourceType": "Condition", "id": "c1",
                     "subject": {"reference": "Patient/p1"},
                     "code": {"text": "Custom text",
                              "coding": [{"code": "a", "system": "s",
                                          "display": "Display"}]}}
        stripped, gold = strip_codings([with_text], DEFAULT_STRIPPING)
        self.assertEqual(stripped[0]["code"]["text"], "Custom text")
        self.assertEqual(gold[0]["text"], "Custom text")


class TestGoldAccuracyAndRecovery(unittest.TestCase):
    def _run_stub(self, corpus):
        stripped, gold = strip_codings(corpus, DEFAULT_STRIPPING)
        run_autocoder(stripped, StubEndpoint())
        return gold_accuracy(gold, stripped)

    def test_exact_recovery_when_stub_returns_gold_code(self):
        corpus = [_patient("p1"),
                  _condition("c1", "p1", "91302008",
                             "http://snomed.info/sct", "Sepsis"),
                  _condition("c2", "p1", "other", "http://x", "Other")]
        acc = self._run_stub(corpus)
        self.assertEqual(acc["gold_resources"], 2)
        self.assertEqual(acc["autocoding_coverage"]["n"], 2)
        # match grades are nested inside the autocoding extension wrapper
        self.assertEqual(acc["match_grades_written"], {"certain": 2})
        # stub returns the SAME code for both: exact for c1, code-only 0
        self.assertEqual(acc["exact_recovery"]["n"], 1)
        self.assertEqual(acc["top1_exact_recovery"]["n"], 1)
        self.assertEqual(acc["code_only_recovery"]["n"], 0)
        self.assertEqual(acc["system_only_recovery"]["n"], 0)

    def test_zero_coverage_when_stub_returns_nothing(self):
        corpus = [_patient("p1"),
                  _condition("c1", "p1", "a", "s", "A")]

        class Empty(StubEndpoint):
            def search_batch(self, pairs, mode="hybrid"):
                return [[] for _ in pairs]

        stripped, gold = strip_codings(corpus, DEFAULT_STRIPPING)
        run_autocoder(stripped, Empty())
        acc = gold_accuracy(gold, stripped)
        self.assertEqual(acc["autocoding_coverage"]["n"], 0)
        self.assertEqual(acc["exact_recovery"]["n"], 0)

    def test_recovery_table_sums_recovered_and_new(self):
        before = {"failing_sam_counts": {"Concept_IsComplete": 10,
                                         "Attr_IsPopulated": 5}}
        after = {"failing_sam_counts": {"Concept_IsComplete": 3,
                                        "Attr_IsNumeric": 2}}
        rec = recovery_table(before, after)
        self.assertEqual(rec["total_fails_recovered"], 12)  # 7 + 5
        self.assertEqual(rec["total_new_failures"], 2)
        self.assertEqual(rec["per_sam"]["Concept_IsComplete"],
                         {"fail_before": 10, "fail_after": 3, "delta": -7})


class TestRubricAndUnmapped(unittest.TestCase):
    def test_mimic_rubric_builds_and_resolves_catalog(self):
        library, criteria = build_mimic_rubric()
        self.assertEqual(len(criteria), 15)
        self.assertTrue(library["url"].endswith("piqi-rubric-mimic-autocoding"))
        # every criterion resolved to a real SAM spec (build_rubric raises
        # KeyError on unknown ids, ValueError on class/entity mismatch)
        self.assertEqual({c["scoring_effect"] for c in criteria},
                         {"scoring", "informational"})

    def test_unmapped_classes_document_gaps(self):
        corpus = [_patient("p1"), _condition("c1", "p1", "a", "s", "A"),
                  {"resourceType": "Encounter", "id": "e1"},
                  {"resourceType": "Specimen", "id": "s1"}]
        out = unmapped_classes(corpus)
        self.assertIn("Patient", out["covered_types"])
        self.assertIn("Condition", out["covered_types"])
        self.assertEqual(out["unmapped"], {"Encounter": 1, "Specimen": 1})


if __name__ == "__main__":
    unittest.main()
