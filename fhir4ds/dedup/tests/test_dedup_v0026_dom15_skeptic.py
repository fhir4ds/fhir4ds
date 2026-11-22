"""Domain 15 SKEPTIC regression tests (v0.0.26 evolution, iter 45).

Root-caused defects, red-first:

- QA-D15S-001 (HIGH): duplicate resource ids in one corpus fabricated
  clusters with no pair evidence (union-find keyed by rid collapses
  same-id records), made ``encounter_pass`` results depend on INPUT
  ORDER (features dict last-write-wins), and silently stripped a
  cluster's canonical edge evidence in the coded pipeline
  (``component_edges`` keyed by lead rid collides across buckets).
  Fix doctrine: ``(resourceType, id)`` is the corpus resource identity —
  a re-supplied id is the SAME resource; entry points collapse
  duplicates deterministically to the lexicographically smallest
  serialized form (MedicationIndex precedent), and component edges ride
  a list parallel to the groups.
- QA-D15S-002 (MEDIUM): a falsy ``membership`` master (``""`` /
  whitespace) co-grouped unrelated patients — a cross-patient merge
  path through the public API. Falsy masters now fall back to
  patient-identity grouping.

Pins (verified conformant, do not regress):

- ``code_fallback='off'`` keeps reference-resolved medication concepts
  OUT of merging (they are a hybrid tier, not canonical) while still
  counting them in stats.
"""

import copy
import json
import unittest

from fhir4ds.dedup.encounter import encounter_pass
from fhir4ds.dedup.pipeline import dedup_pass

_ACT = "http://terminology.hl7.org/CodeSystem/v3-ActCode"


def _enc(rid, start, end, klass="AMB", patient="p1"):
    return {"resourceType": "Encounter", "id": rid,
            "subject": {"reference": f"Patient/{patient}"},
            "class": {"system": _ACT, "code": klass},
            "period": {"start": start, "end": end}}


def _obs(rid, code, month):
    return {"resourceType": "Observation", "id": rid,
            "subject": {"reference": "Patient/p1"}, "status": "final",
            "code": {"coding": [{"system": "http://loinc.org", "code": code}]},
            "effectiveDateTime": f"2024-{month:02d}-01T00:00:00",
            "valueQuantity": {"value": 1, "code": "kg", "unit": "kg",
                              "system": "http://unitsofmeasure.org"}}


def _fingerprint(result) -> str:
    return json.dumps({
        "clusters": sorted(sorted(m.rid for m in c) for c in result.clusters),
        "emitted": sorted(m.rid for m in result.emitted),
        "stats": result.stats,
    }, sort_keys=True)


class TestDuplicateIdCollapse(unittest.TestCase):
    """QA-D15S-001 — duplicate ids: deterministic, no fabricated clusters."""

    def test_duplicate_encounter_ids_order_independent_and_not_fabricated(self):
        e_jan_emer = _enc("dup1", "2024-01-01T08:00:00",
                          "2024-01-01T09:00:00", klass="EMER")
        e_jun_amb = _enc("dup1", "2024-06-01T08:00:00",
                         "2024-06-01T09:00:00", klass="AMB")
        e3 = _enc("e3", "2024-01-01T08:05:00", "2024-01-01T08:59:00",
                  klass="EMER")
        fp_a = _fingerprint(encounter_pass(
            [copy.deepcopy(e_jan_emer), copy.deepcopy(e_jun_amb),
             copy.deepcopy(e3)]))
        fp_b = _fingerprint(encounter_pass(
            [copy.deepcopy(e_jun_amb), copy.deepcopy(e_jan_emer),
             copy.deepcopy(e3)]))
        self.assertEqual(fp_a, fp_b,
                         "same resource SET must yield identical results")
        result = encounter_pass([copy.deepcopy(e_jan_emer),
                                 copy.deepcopy(e_jun_amb),
                                 copy.deepcopy(e3)])
        # No cluster may contain two records with the same rid (a
        # fabricated merge of distinct resources sharing an id).
        for cluster in result.clusters:
            rids = [m.rid for m in cluster]
            self.assertEqual(len(rids), len(set(rids)),
                             f"fabricated cluster {rids}")
        # e3 must be judged on ITS period against the collapsed dup1, and
        # the duplicate resource must not vanish silently from stats.
        self.assertIn(result.stats.get("duplicate_id_resources", 0), (1,))

    def test_duplicate_coded_ids_keep_edge_evidence(self):
        corpus = [_obs("dupx", "1", 1), _obs("m1", "1", 1),
                  _obs("dupx", "2", 2), _obs("m2", "2", 2)]
        result = dedup_pass(copy.deepcopy(corpus), code_fallback="off")
        # (resourceType, id) is one resource identity: the two dupx
        # resources collapse to the smallest form (the January one), so
        # m2 becomes a singleton — no fabricated cross-bucket cluster,
        # and the real cluster keeps its canonical edge evidence.
        self.assertEqual(
            [[m.rid for m in c] for c in result.clusters], [["dupx", "m1"]])
        self.assertIn("m2", [r.rid for r in result.emitted])
        self.assertEqual(result.stats["duplicate_id_resources"], 1)
        for cluster, edges in zip(result.clusters, result.cluster_edges):
            ids = {m.rid for m in cluster}
            self.assertTrue(edges,
                            f"cluster {sorted(ids)} lost its edge evidence")
            for edge in edges:
                self.assertTrue(set(edge["edge"]) <= ids,
                                f"edge {edge['edge']} references non-members")

    def test_run_level_duplicate_ids_shuffle_invariant(self):
        from fhir4ds.dedup.runner import run_dedup
        import duckdb
        corpus = [
            _enc("dup1", "2024-01-01T08:00:00", "2024-01-01T09:00:00",
                 klass="EMER"),
            _enc("dup1", "2024-06-01T08:00:00", "2024-06-01T09:00:00"),
            _enc("e9", "2024-01-01T08:05:00", "2024-01-01T08:58:00",
                 klass="EMER"),
            _obs("ob1", "29463-7", 1), _obs("ob2", "29463-7", 1),
        ]

        def run(order):
            conn = duckdb.connect()
            try:
                out = run_dedup(copy.deepcopy(list(order)), "r")
                return json.dumps(
                    {"survivors": out.survivors,
                     "linkage": out.linkage_resources,
                     "stats": out.stats}, sort_keys=True)
            finally:
                conn.close()

        self.assertEqual(run(corpus), run(corpus[::-1]))


class TestMembershipSeam(unittest.TestCase):
    """QA-D15S-002 — falsy membership masters never group strangers."""

    def test_falsy_master_falls_back_to_patient_identity(self):
        a = _enc("x1", "2024-01-01T08:00:00", "2024-01-01T09:00:00",
                 patient="p2")
        b = _enc("x2", "2024-01-01T08:05:00", "2024-01-01T08:59:00",
                 patient="p3")
        for bad in ("", "   "):
            result = encounter_pass([copy.deepcopy(a), copy.deepcopy(b)],
                                    membership={"p2": bad, "p3": bad})
            self.assertFalse(
                any(len(c) == 2 for c in result.clusters),
                f"empty master {bad!r} merged unrelated patients")
        # a real master still groups (the feature this seam must keep).
        merged = encounter_pass([copy.deepcopy(a), copy.deepcopy(b)],
                                membership={"p2": "m1", "p3": "m1"})
        self.assertTrue(any(len(c) == 2 for c in merged.clusters))


class TestOffModeReferenceResolverPin(unittest.TestCase):
    """H6 pin — reference-resolved concepts are a HYBRID tier: 'off' mode
    (canonical-only) must not merge through them, while stats still
    count the resolutions."""

    def test_off_mode_does_not_merge_via_reference_resolution(self):
        med = {"resourceType": "Medication", "id": "med1",
               "code": {"coding": [{
                   "system": "http://www.nlm.nih.gov/research/umls/rxnorm",
                   "code": "104967"}]}}
        mr1 = {"resourceType": "MedicationRequest", "id": "mr1",
               "subject": {"reference": "Patient/p1"}, "status": "active",
               "intent": "order",
               "medicationReference": {"reference": "Medication/med1"},
               "authoredOn": "2024-01-01"}
        mr2 = dict(mr1, id="mr2")
        for mode, expect_merge in (("on", True), ("audit_only", False),
                                   ("off", False)):
            result = dedup_pass([copy.deepcopy(med), copy.deepcopy(mr1),
                                 copy.deepcopy(mr2)], code_fallback=mode)
            merged = any(len(c) == 2 for c in result.clusters)
            self.assertEqual(merged, expect_merge, msg=mode)
            self.assertEqual(result.stats["reference_resolved_records"], 2,
                             msg=mode)


if __name__ == "__main__":
    unittest.main()
