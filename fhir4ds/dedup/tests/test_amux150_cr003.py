"""AMUX-150 code-review CR-003 — single-encounter semantics via
constrained edge admission in the Encounter clustering.

Joel decision (2026-11-20), option (a): the per-pair EMER hard-negative
veto (>= 2h disjoint, same class) must constrain the CLUSTER outcome,
not just the edge — before adding a merge edge, verify the resulting
cluster would contain no vetoed pair (vetoed pairs precomputed per
patient-group, deterministic tie-breaks). Refused edges are
audit-recorded with reason ``would_create_vetoed_pair`` and the vetoed
pair's rids.

Grounding: evolution_amux150.json CR-003, FDD §4.3.
"""

from __future__ import annotations

import json
from pathlib import Path

import duckdb

from fhir4ds.dedup.encounter import encounter_pass, run_encounter_dedup

_ACT = "http://terminology.hl7.org/CodeSystem/v3-ActCode"


def _enc(rid, *, start, end, patient="pat-1", klass="EMER",
         provider=None):
    resource = {
        "resourceType": "Encounter",
        "id": rid,
        "status": "finished",
        "class": {"system": _ACT, "code": klass},
        "subject": {"reference": f"Patient/{patient}"},
        "period": {"start": start, "end": end},
    }
    if provider:
        resource["serviceProvider"] = {
            "reference": f"Organization/{provider}"}
    return resource


def _transitive_chain():
    """A-B-C: A~B overlap-core, B~C overlap-core, A-C EMER disjoint >= 2h
    (vetoed). Union-find transitivity used to cluster all three."""
    return [
        _enc("enc-a", start="2026-01-01T10:00:00", end="2026-01-01T11:00:00"),
        _enc("enc-b", start="2026-01-01T10:00:00", end="2026-01-01T15:00:00"),
        _enc("enc-c", start="2026-01-01T14:00:00", end="2026-01-01T15:00:00"),
    ]


class TestConstrainedEdgeAdmission:
    def test_transitive_veto_yields_two_clusters(self):
        """CR-003 acceptance: the B-C edge (which would put the vetoed
        A-C pair into one cluster) is REFUSED -> {A,B} cluster + C
        singleton."""
        result = encounter_pass(_transitive_chain())
        cluster_ids = sorted(
            sorted(r.rid for r in cluster) for cluster in result.clusters)
        assert cluster_ids == [["enc-a", "enc-b"]]
        emitted_ids = sorted(r.rid for r in result.emitted)
        assert emitted_ids == ["enc-c"]
        assert result.stats["encounter_refused_edges"] == 1

    def test_refused_edge_audit_recorded(self):
        """The refusal carries reason would_create_vetoed_pair plus both
        the refused edge's rids and the vetoed pair's rids."""
        result = encounter_pass(_transitive_chain())
        refusals = [e for e in result.curation_records
                    if e.get("kind") == "encounter_edge_refused"]
        assert len(refusals) == 1
        refusal = refusals[0]
        assert refusal["reason"] == "would_create_vetoed_pair"
        assert refusal["rids"] == ["enc-b", "enc-c"]
        assert refusal["vetoed_pair"] == ["enc-a", "enc-c"]
        assert refusal["resource_type"] == "Encounter"
        # the merge-worthy score of the refused edge is preserved
        assert refusal["score"] >= 60

    def test_direct_veto_pair_still_never_merges(self):
        """Regression guard (chunk-C test 39 semantics): the vetoed A-C
        pair itself never produces an edge, cluster, or refusal record —
        only TRANSPARENT transitivity is new."""
        result = encounter_pass([
            _enc("enc-a", start="2026-01-01T10:00:00",
                 end="2026-01-01T11:00:00"),
            _enc("enc-c", start="2026-01-01T14:00:00",
                 end="2026-01-01T15:00:00"),
        ])
        assert result.clusters == []
        assert sorted(r.rid for r in result.emitted) == ["enc-a", "enc-c"]
        assert result.stats["encounter_refused_edges"] == 0
        assert not [e for e in result.curation_records
                    if e.get("kind") == "encounter_edge_refused"]

    def test_mutual_overlap_cluster_still_merges_three(self):
        """Over-enforcement guard: a legit 3-way mutually-containing
        cluster (each pair >= 80% containment, no veto anywhere) still
        collapses into ONE cluster of 3."""
        result = encounter_pass([
            _enc("enc-a", start="2026-01-01T10:00:00",
                 end="2026-01-01T15:00:00"),
            _enc("enc-b", start="2026-01-01T10:30:00",
                 end="2026-01-01T14:30:00"),
            _enc("enc-c", start="2026-01-01T11:00:00",
                 end="2026-01-01T13:00:00"),
        ])
        cluster_ids = sorted(
            sorted(r.rid for r in cluster) for cluster in result.clusters)
        assert cluster_ids == [["enc-a", "enc-b", "enc-c"]]
        assert result.stats["encounter_refused_edges"] == 0

    def test_determinism_shuffled_input(self):
        """Same resource SET -> identical clusters, refusals, and stats
        regardless of input order."""
        base = encounter_pass(_transitive_chain())
        shuffled = encounter_pass(list(reversed(_transitive_chain())))
        assert [sorted(r.rid for r in c) for c in base.clusters] == \
            [sorted(r.rid for r in c) for c in shuffled.clusters]
        assert sorted(r.rid for r in base.emitted) == \
            sorted(r.rid for r in shuffled.emitted)
        assert base.curation_records == shuffled.curation_records
        assert base.stats == shuffled.stats

    def test_run_encounter_dedup_surfaces_refusals(self):
        """End-to-end: the refusal lands in the curation queue JSONL and
        the cluster {A,B} flows through the unchanged back end."""
        conn = duckdb.connect()
        try:
            run = run_encounter_dedup(
                _transitive_chain(), "cr003-run", conn=conn,
                output_dir="/tmp/opencode/cr003-queue")
            # one survivor row: the merged {A,B} cluster (the refused
            # edge leaves C a singleton, which is not a survivor record)
            assert run.stats["survivors"] == 1
            assert run.stats["encounter_refused_edges"] == 1
            queue = Path(run.curation_queue_path).read_text()
            assert "would_create_vetoed_pair" in queue
            entries = [json.loads(line) for line in queue.splitlines()
                       if line.strip()]
            refusals = [e for e in entries
                        if e.get("kind") == "encounter_edge_refused"]
            assert len(refusals) == 1
            assert refusals[0]["vetoed_pair"] == ["enc-a", "enc-c"]
        finally:
            conn.close()
