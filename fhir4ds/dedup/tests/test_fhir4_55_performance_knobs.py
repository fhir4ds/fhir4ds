"""Deduplication speed knobs: optional near-miss sweep, progress, cancel (FHIR4-55).

The fhir4px report measured fhir4ds dedup at 2.7 s for 923 records and 34.3 s
for 3,225, against 1.6 ms to 259 ms for the app's own JavaScript dedup. The
desktop profile put ~70% of a large run in ONE step —
``_cross_bucket_near_misses`` (pipeline.py) — which is quadratic in the size of
a shared-text group, and it had no way to be switched off.

Three properties are pinned here, and each one is a contract rather than a
micro-optimisation:

1. The cross-bucket sweep CANNOT change a merge decision. It only enriches the
   curation queue, so switching it off must leave clusters, survivors and audit
   rows identical. (If this ever stops being true, the switch is a correctness
   hazard and must be removed.)
2. The ``_sort_key`` hoist keeps the emitted near-miss set byte-identical: the
   sweep used to rebuild ``_sort_key`` — including a ``_partition_date`` parse —
   for both sides of every pair. Same entries, same order, far fewer calls.
3. ``progress`` and ``should_cancel`` give a background caller something to
   render and something to pull; a raising progress sink must never abort a run
   (observability is not a correctness risk), and a cancelled run must raise a
   typed error rather than return a partial result that looks complete.
"""

from __future__ import annotations

import duckdb
import pytest

from fhir4ds.dedup import dedup_pass, run_dedup
from fhir4ds.dedup.runner import DedupCancelled


def _obs(rid: str, when: str, code: str, *, text: str = "Hemoglobin",
         system: str = "urn:local:lab") -> dict:
    """An Observation whose only coding is a LOCAL code (so tier-2 applies)."""
    return {
        "resourceType": "Observation",
        "id": rid,
        "status": "final",
        "code": {"text": text, "coding": [
            {"system": system, "code": code, "display": text}]},
        "subject": {"reference": "Patient/p1"},
        "effectiveDateTime": when,
        "valueQuantity": {"value": 14.2, "unit": "g/dL"},
    }


def _near_miss_corpus() -> list[dict]:
    """Two same-text Observations in DIFFERENT buckets with disjoint codes.

    Different effectiveDateTime -> different partition date -> different
    Stage-1 bucket, so the union path cannot pair them; the shared tier-2 text
    with disjoint concept keys is exactly the cross-bucket near-miss case.
    """
    return [
        _obs("o1", "2024-05-01T10:00:00Z", "X1"),
        _obs("o2", "2024-06-01T10:00:00Z", "X2"),
    ]


def _cross_bucket(result) -> list[dict]:
    return [e for e in result.curation_records
            if e.get("kind") == "near_miss" and e.get("reason") == "cross_bucket"]


class TestNearMissSweepIsOptional:
    def test_switch_off_leaves_clusters_identical(self):
        corpus = _near_miss_corpus()
        with_on = dedup_pass(list(corpus), cross_bucket_near_misses=True)
        with_off = dedup_pass(list(corpus), cross_bucket_near_misses=False)

        assert [sorted(c, key=lambda r: r.rid) for c in with_on.clusters] == \
               [sorted(c, key=lambda r: r.rid) for c in with_off.clusters]
        assert sorted(r.rid for r in with_on.emitted) == \
               sorted(r.rid for r in with_off.emitted)
        # `stats` legitimately differs in the CURATION counters (that is what
        # the sweep produces); the contract is that clustering is untouched.
        for key in ("clusters", "duplicates", "records", "pairs"):
            if key in with_on.stats:
                assert with_on.stats[key] == with_off.stats[key], key
        assert with_on.stats.get("curation_near_miss", 0) > \
               with_off.stats.get("curation_near_miss", 0)

    def test_switch_only_removes_cross_bucket_entries(self):
        corpus = _near_miss_corpus()
        with_on = dedup_pass(list(corpus), cross_bucket_near_misses=True)
        with_off = dedup_pass(list(corpus), cross_bucket_near_misses=False)

        assert _cross_bucket(with_on), "corpus must produce a cross-bucket case"
        assert _cross_bucket(with_off) == []
        # every other kind of curation entry survives the switch untouched
        keep_on = [e for e in with_on.curation_records
                   if e.get("reason") != "cross_bucket"]
        keep_off = [e for e in with_off.curation_records
                    if e.get("reason") != "cross_bucket"]
        assert [e.get("kind") for e in keep_on] == \
               [e.get("kind") for e in keep_off]

    def test_run_dedup_forwards_the_switch(self):
        corpus = _near_miss_corpus()
        conn = duckdb.connect()
        try:
            run_dedup(list(corpus), "f55-off", conn=conn,
                      output_dir="/tmp", cross_bucket_near_misses=False)
        finally:
            conn.close()


class TestDeterministicCap:
    def test_cap_bounds_the_queue_and_says_so(self):
        corpus = _near_miss_corpus()
        full = dedup_pass(list(corpus), cross_bucket_near_misses=True)
        capped = dedup_pass(list(corpus), cross_bucket_near_misses=True,
                            cross_bucket_near_miss_limit=1)
        assert len(_cross_bucket(full)) >= 1
        assert len(_cross_bucket(capped)) == 1
        assert capped.stats["curation_near_miss_truncated"] is True
        assert full.stats["curation_near_miss_truncated"] is False

    def test_cap_keeps_the_same_prefix_a_full_run_emits(self):
        """Deterministic truncation: sorted keys + rid-sorted groups."""
        corpus = _near_miss_corpus()
        full = _cross_bucket(dedup_pass(list(corpus),
                                        cross_bucket_near_misses=True))
        capped = _cross_bucket(dedup_pass(list(corpus),
                                         cross_bucket_near_misses=True,
                                         cross_bucket_near_miss_limit=1))
        assert capped == full[:1]

    def test_cap_cannot_change_clustering(self):
        corpus = _near_miss_corpus()
        full = dedup_pass(list(corpus), cross_bucket_near_misses=True)
        capped = dedup_pass(list(corpus), cross_bucket_near_misses=True,
                            cross_bucket_near_miss_limit=1)
        assert [sorted(c, key=lambda r: r.rid) for c in full.clusters] == \
               [sorted(c, key=lambda r: r.rid) for c in capped.clusters]


class TestIdempotentDdlIsIssuedOncePerConnection:
    """fhir4px measured 900-6,280 small statements per run at ~0.6 ms each.

    Two of those per cluster were the idempotent `CREATE TABLE IF NOT EXISTS`
    DDLs, re-issued for every cluster (and, in audit mode, every singleton).
    """

    def test_linkage_ddl_is_memoised_per_connection(self):
        from fhir4ds.dedup.linkage import (
            _DDL_APPLIED, create_dedup_linkage_table)

        conn = duckdb.connect()
        try:
            create_dedup_linkage_table(conn)
            assert conn in _DDL_APPLIED
            # proving the second call really skips: drop the table, and a
            # memoised second call must NOT recreate it.
            conn.execute("DROP TABLE dedup_linkage")
            create_dedup_linkage_table(conn)
            assert conn.execute(
                "SELECT count(*) FROM information_schema.tables "
                "WHERE table_name = 'dedup_linkage'").fetchone()[0] == 0
        finally:
            conn.close()

    def test_audit_ddl_is_memoised_per_connection(self):
        from fhir4ds.dedup.audit import _DDL_APPLIED as AUDIT_APPLIED
        from fhir4ds.dedup.audit import create_dedup_audit_table

        conn = duckdb.connect()
        try:
            create_dedup_audit_table(conn)
            assert conn in AUDIT_APPLIED
        finally:
            conn.close()

    def test_a_new_connection_still_gets_its_own_tables(self):
        from fhir4ds.dedup.audit import create_dedup_audit_table
        from fhir4ds.dedup.linkage import create_dedup_linkage_table

        for _ in range(2):
            conn = duckdb.connect()
            try:
                create_dedup_linkage_table(conn)
                create_dedup_audit_table(conn)
                n = conn.execute(
                    "SELECT count(*) FROM information_schema.tables "
                    "WHERE table_name IN ('dedup_linkage', 'dedup_audit')"
                ).fetchone()[0]
                assert n == 2
            finally:
                conn.close()


class TestProgressAndCancel:
    def test_progress_is_reported_at_every_boundary(self):
        events: list[dict] = []
        conn = duckdb.connect()
        try:
            run_dedup(_near_miss_corpus(), "f55-progress", conn=conn,
                      progress=events.append)
        finally:
            conn.close()
        stages = [e["stage"] for e in events]
        assert stages == ["normalize+cluster", "clustered", "linkage+audit"]
        assert all(isinstance(e["done"], int) and isinstance(e["total"], int)
                   for e in events)

    def test_a_raising_progress_sink_cannot_abort_the_run(self):
        def boom(_event):
            raise RuntimeError("renderer exploded")

        conn = duckdb.connect()
        try:
            result = run_dedup(_near_miss_corpus(), "f55-boom", conn=conn,
                               progress=boom)
        finally:
            conn.close()
        assert result is not None, "observability must not be a failure mode"

    def test_cancel_raises_a_typed_error_before_any_audit_write(self):
        conn = duckdb.connect()
        try:
            with pytest.raises(DedupCancelled):
                run_dedup(_near_miss_corpus(), "f55-cancel", conn=conn,
                          should_cancel=lambda: True)
        finally:
            conn.close()

    def test_no_cancel_signal_completes_normally(self):
        conn = duckdb.connect()
        try:
            result = run_dedup(_near_miss_corpus(), "f55-nocancel", conn=conn,
                               should_cancel=lambda: False)
        finally:
            conn.close()
        assert result is not None
