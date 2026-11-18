"""AMUX-142 slice 3 tests — survivorship, merge, Linkage, audit, runner.

Ranking matrix, merged-resource shape, N-way Linkage + idempotent upsert +
delete-revert, audit rows, end-to-end run determinism (design doc §2d, §5).
"""

from __future__ import annotations

import json

import duckdb
import pytest

from fhir4ds.dedup import (
    DEDUP_EXTENSION_URL,
    DedupRecord,
    build_linkage_resource,
    dedup_pass,
    delete_linkage,
    infer_window_rule,
    load_dedup_audit,
    load_dedup_linkage_resources,
    merge_resources,
    run_dedup,
    select_survivor,
    survivor_dedup_id,
    survivor_ranking_key,
    upsert_dedup_linkage,
)
from fhir4ds.dedup.survivorship import _timestamp, survivor_rule_tuple

LOINC = "http://loinc.org"
SNOMED = "http://snomed.info/sct"


def obs(rid, effective=None, code="85352-4", value=120, unit="mm[Hg]",
        subject="Patient/p1", category=None, **extra):
    resource = {
        "resourceType": "Observation",
        "id": rid,
        "status": "final",
        "code": {"coding": [{"system": LOINC, "code": code}]},
        "subject": {"reference": subject},
        **extra,
    }
    if effective is not None:
        resource["effectiveDateTime"] = effective
    if value is not None:
        resource["valueQuantity"] = {"value": value, "code": unit,
                                     "unit": unit}
    if category is not None:
        resource["category"] = [
            {"coding": [{"system": "http://terminology.hl7.org/CodeSystem/"
                                   "observation-category", "code": category}]}
        ]
    return resource


def proc(rid, performed, code="70507-7", subject="Patient/p1", **extra):
    return {
        "resourceType": "Procedure",
        "id": rid,
        "status": "completed",
        "code": {"coding": [{"system": SNOMED, "code": code}]},
        "subject": {"reference": subject},
        "performedDateTime": performed,
        **extra,
    }


def records(*resources):
    return [DedupRecord.from_resource(r) for r in resources]


def sig_of(record):
    return record.nd.signature if record.nd is not None else None


# ===========================================================================
# select_survivor — the ranking total order
# ===========================================================================


class TestSurvivorRanking:
    def test_signature_beats_timestamp_richness_and_rid(self):
        # Precise-but-late, identifier-poor, lexicographically-larger rid
        # still wins over an earlier, richer DATE_ONLY member.
        precise = obs("zzz", effective="2024-03-05T22:00:00Z")
        date_only = obs("aaa", effective="2024-03-05", note=[{"text": "x"}],
                        performer=[{"display": "d"}])
        cluster = records(precise, date_only)
        assert select_survivor(cluster).rid == "zzz"

    def test_dt_z_beats_dt_naive(self):
        z = obs("b", effective="2024-03-05T12:00:00Z")
        naive = obs("a", effective="2024-03-05T08:00:00")  # earlier wall clock
        assert select_survivor(records(z, naive)).rid == "b"

    def test_dt_offset_beats_dt_naive(self):
        off = obs("b", effective="2024-03-05T12:00:00-06:00")
        naive = obs("a", effective="2024-03-05T01:00:00")
        assert select_survivor(records(off, naive)).rid == "b"

    def test_dt_z_and_dt_offset_share_the_top_tier(self):
        # Same tier -> earliest instant wins regardless of DT flavor.
        late_z = obs("a", effective="2024-03-05T20:00:00Z")
        early_offset = obs("b", effective="2024-03-05T12:00:00-08:00")
        # early_offset -> 20:00Z too; equal instants -> rid breaks the tie.
        assert select_survivor(records(late_z, early_offset)).rid == "a"
        earlier = obs("b", effective="2024-03-05T11:00:00-08:00")  # 19:00Z
        assert select_survivor(records(late_z, earlier)).rid == "b"

    def test_dt_naive_beats_date_only(self):
        naive = obs("b", effective="2024-03-05T00:00:00")
        date_only = obs("a", effective="2024-03-05")  # has a start_utc span
        assert select_survivor(records(naive, date_only)).rid == "b"

    def test_date_only_beats_month_beats_year(self):
        d = obs("c", effective="2024-03-05")
        m = obs("b", effective="2024-03")
        y = obs("a", effective="2024")
        cluster = records(d, m, y)
        assert select_survivor(cluster).rid == "c"

    def test_no_temporal_value_loses_to_any_signature(self):
        none = obs("a", note=[{"text": "rich"}])  # no effectiveDateTime
        year = obs("z", effective="2024")
        assert select_survivor(records(none, year)).rid == "z"

    def test_earliest_timestamp_wins_within_same_signature(self):
        early = obs("b", effective="2024-03-05T09:00:00Z")
        late = obs("a", effective="2024-03-05T10:00:00Z")
        assert select_survivor(records(early, late)).rid == "b"

    def test_none_timestamp_sorts_last(self):
        # Direct probe of the level-2 key shape: (ts is None, ts or "").
        stamped = records(obs("a", effective="2024-03-05T09:00:00Z"))[0]
        naive = records(obs("b", effective="2024-03-05T09:00:00"))[0]
        assert _timestamp(stamped) == "2024-03-05T09:00:00Z"
        assert _timestamp(naive) is None
        assert survivor_ranking_key(stamped)[1] == (False,
                                                    "2024-03-05T09:00:00Z")
        assert survivor_ranking_key(naive)[1] == (True, "")

    def test_richest_metadata_wins_when_signature_and_ts_tie(self):
        rich = obs("z", effective="2024-03-05T09:00:00Z",
                   performer=[{"display": "Dr"}],
                   referenceRange=[{"low": {"value": 1}}],
                   note=[{"text": "n"}],
                   bodySite={"coding": [{"code": "x"}]},
                   method={"coding": [{"code": "m"}]})
        poor = obs("a", effective="2024-03-05T09:00:00Z")
        assert select_survivor(records(rich, poor)).rid == "z"

    def test_explicit_empty_list_still_counts_as_present(self):
        # Richness counts authored presence: an explicitly empty note list
        # beats no note key at all.
        with_empty = obs("z", effective="2024-03-05T09:00:00Z", note=[])
        without = obs("a", effective="2024-03-05T09:00:00Z")
        assert select_survivor(records(with_empty, without)).rid == "z"

    def test_smallest_rid_is_the_final_tie_break(self):
        a = obs("bbb", effective="2024-03-05T09:00:00Z")
        b = obs("aaa", effective="2024-03-05T09:00:00Z")
        assert select_survivor(records(a, b)).rid == "aaa"

    def test_empty_cluster_rejected(self):
        with pytest.raises(ValueError):
            select_survivor([])

    def test_ranking_key_is_a_total_order(self):
        cluster = records(
            obs("r1", effective="2024-03-05T09:00:00Z"),
            obs("r2", effective="2024-03-05"),
            obs("r3", effective="2024-03-05T09:00:00Z", note=[]),
            obs("r4", effective="2024-03-05T08:00:00Z"),
            obs("r5"),
        )
        keys = [survivor_ranking_key(r) for r in cluster]
        assert len(set(keys)) == len(keys)          # total: no equal keys
        ordered = sorted(keys)                       # comparable end-to-end
        assert ordered[0] == survivor_ranking_key(
            next(r for r in cluster if r.rid == "r4"))  # earliest DT_Z
        assert ordered[-1][0] == 1                    # no-temporal ranks last
        assert select_survivor(cluster).rid == "r4"

    def test_survivor_rule_tuple_shape(self):
        survivor = records(obs("s", effective="2024-03-05T09:00:00Z",
                               note=[]))[0]
        assert survivor_rule_tuple(survivor) == ["DT_Z", 1, "s"]

    def test_survivor_rule_tuple_none_signature(self):
        survivor = records(obs("s"))[0]
        assert survivor_rule_tuple(survivor)[0] is None


# ===========================================================================
# survivor_dedup_id + merge_resources
# ===========================================================================


class TestMergeShape:
    def make_cluster(self):
        a = obs("obs-a", effective="2024-03-05T09:00:00Z",
                identifier=[{"system": "urn:a", "value": "1"},
                            {"system": "urn:dup", "value": "shared"}],
                meta={"source": "sys-b", "versionId": "3"},
                note=[{"text": "keep me"}])
        a["code"]["coding"].append({"system": SNOMED, "code": "s1"})
        b = obs("obs-b", effective="2024-03-05T09:30:00Z",
                identifier=[{"system": "urn:b", "value": "2"},
                            {"system": "urn:dup", "value": "shared"}],
                meta={"source": "sys-a"})
        b["code"]["coding"].append({"system": SNOMED, "code": "s2"})
        return records(a, b)

    def test_dedup_id_is_order_independent_and_hash_shaped(self):
        cluster = self.make_cluster()
        rids = sorted(r.rid for r in cluster)
        expected = "dedup-" + __import__("hashlib").sha256(
            ",".join(rids).encode()).hexdigest()[:16]
        assert survivor_dedup_id(cluster) == expected
        assert survivor_dedup_id(list(reversed(cluster))) == expected

    def test_merged_id_is_the_deterministic_hash(self):
        cluster = self.make_cluster()
        merged = merge_resources(cluster, select_survivor(cluster))
        assert merged["id"] == survivor_dedup_id(cluster)
        assert merged["id"].startswith("dedup-")
        assert len(merged["id"]) == len("dedup-") + 16

    def test_merged_starts_from_survivor_resource(self):
        cluster = self.make_cluster()
        survivor = select_survivor(cluster)
        merged = merge_resources(cluster, survivor)
        assert merged["resourceType"] == "Observation"
        assert merged["note"] == survivor.resource["note"]  # survivor's own
        assert merged["status"] == "final"

    def test_identifiers_union_dedup_survivor_first(self):
        cluster = self.make_cluster()
        merged = merge_resources(cluster, select_survivor(cluster))
        pairs = [(i["system"], i["value"]) for i in merged["identifier"]]
        assert pairs == [("urn:a", "1"), ("urn:dup", "shared"),
                         ("urn:b", "2")]
        assert len(pairs) == len(set(pairs))

    def test_identifiers_merged_when_only_alternates_have_them(self):
        a = obs("obs-a", effective="2024-03-05T09:00:00Z")
        b = obs("obs-b", effective="2024-03-05T09:30:00Z",
                identifier=[{"system": "urn:b", "value": "2"}])
        merged = merge_resources(records(a, b),
                                 select_survivor(records(a, b)))
        assert merged["identifier"] == [{"system": "urn:b", "value": "2"}]

    def test_meta_source_union_sorted_dedup(self):
        cluster = self.make_cluster()
        merged = merge_resources(cluster, select_survivor(cluster))
        assert merged["meta"]["source"] == ["sys-a", "sys-b"]
        assert merged["meta"]["versionId"] == "3"  # survivor's meta kept

    def test_meta_omitted_when_no_member_has_source(self):
        a = obs("obs-a", effective="2024-03-05T09:00:00Z")
        b = obs("obs-b", effective="2024-03-05T09:30:00Z")
        merged = merge_resources(records(a, b),
                                 select_survivor(records(a, b)))
        assert "meta" not in merged

    def test_codings_union_survivor_first_others_append(self):
        cluster = self.make_cluster()
        merged = merge_resources(cluster, select_survivor(cluster))
        codings = merged["code"]["coding"]
        assert [(c["system"], c["code"]) for c in codings] == [
            (LOINC, "85352-4"), (SNOMED, "s1"), (SNOMED, "s2")]

    def test_coding_dedup_by_system_and_code(self):
        a = obs("obs-a", effective="2024-03-05T09:00:00Z")
        a["code"]["coding"].append({"system": LOINC, "code": "85352-4",
                                    "display": "dup"})
        b = obs("obs-b", effective="2024-03-05T09:30:00Z")
        merged = merge_resources(records(a, b),
                                 select_survivor(records(a, b)))
        assert len(merged["code"]["coding"]) == 1

    def test_code_text_taken_from_first_author(self):
        # Survivor authors no text -> first authoring member's text is used;
        # when the survivor authors one, it wins.
        a = obs("obs-a", effective="2024-03-05T09:00:00Z")
        b = obs("obs-b", effective="2024-03-05T09:30:00Z")
        b["code"]["text"] = "later text"
        merged = merge_resources(records(a, b),
                                 select_survivor(records(a, b)))
        assert merged["code"]["text"] == "later text"
        a["code"]["text"] = "survivor text"
        merged = merge_resources(records(a, b),
                                 select_survivor(records(a, b)))
        assert merged["code"]["text"] == "survivor text"

    def test_category_union_dedup_by_coding_set(self):
        cat_sys = ("http://terminology.hl7.org/CodeSystem/"
                   "observation-category")
        a = obs("obs-a", effective="2024-03-05T09:00:00Z",
                category="laboratory")
        b = obs("obs-b", effective="2024-03-05T09:30:00Z",
                category="laboratory")
        b["category"].append(
            {"coding": [{"system": cat_sys, "code": "vital-signs"}]})
        merged = merge_resources(records(a, b),
                                 select_survivor(records(a, b)))
        codes = [c["coding"][0]["code"] for c in merged["category"]]
        assert codes == ["laboratory", "vital-signs"]

    def test_extension_fields(self):
        cluster = self.make_cluster()
        merged = merge_resources(cluster, select_survivor(cluster))
        ext = [e for e in merged["extension"]
               if e["url"] == DEDUP_EXTENSION_URL]
        assert len(ext) == 1
        fields = {e["url"]: e for e in ext[0]["extension"]}
        assert fields["dedupId"]["valueString"] == merged["id"]
        assert fields["sourceCount"]["valueInteger"] == 2
        refs = [e["valueString"] for e in
                fields["sourceReferences"]["extension"]]
        assert refs == ["Observation/obs-a", "Observation/obs-b"]
        assert fields["clusterCategory"]["valueString"] == "OTHER"
        rule = {e["url"]: e for e in fields["survivorRule"]["extension"]}
        assert rule["survivorRid"]["valueString"] == "obs-a"
        assert rule["signature"]["valueString"] == "DT_Z"
        assert rule["richness"]["valueInteger"] == 1

    def test_extension_carries_no_timestamps(self):
        cluster = self.make_cluster()
        merged = merge_resources(cluster, select_survivor(cluster))
        ext = json.dumps([e for e in merged["extension"]
                          if e.get("url") == DEDUP_EXTENSION_URL],
                         sort_keys=True).lower()
        assert "timestamp" not in ext
        assert "evaluatedat" not in ext
        assert "2024-03-05" not in ext  # no authored timestamps either

    def test_prior_dedup_extension_replaced_not_duplicated(self):
        a = obs("obs-a", effective="2024-03-05T09:00:00Z",
                extension=[{"url": DEDUP_EXTENSION_URL, "extension": []},
                           {"url": "http://example.org/other"}])
        b = obs("obs-b", effective="2024-03-05T09:30:00Z")
        merged = merge_resources(records(a, b),
                                 select_survivor(records(a, b)))
        dedup_exts = [e for e in merged["extension"]
                      if e.get("url") == DEDUP_EXTENSION_URL]
        assert len(dedup_exts) == 1
        assert merged["extension"][0]["url"] == "http://example.org/other"

    def test_non_survivor_field_values_not_merged_v1(self):
        # Documented v1 limitation: e.g. the alternate's note is dropped.
        a = obs("obs-a", effective="2024-03-05T09:00:00Z")
        b = obs("obs-b", effective="2024-03-05T09:30:00Z",
                note=[{"text": "alt note"}])
        merged = merge_resources(records(a, b),
                                 select_survivor(records(a, b)))
        assert "note" not in merged

    def test_merge_is_deterministic_under_shuffle(self):
        cluster = self.make_cluster()
        survivor = select_survivor(cluster)
        first = json.dumps(merge_resources(cluster, survivor), sort_keys=True)
        import random
        for seed in range(5):
            shuffled = list(cluster)
            random.Random(seed).shuffle(shuffled)
            again = json.dumps(merge_resources(shuffled, survivor),
                               sort_keys=True)
            assert again == first


# ===========================================================================
# Linkage writer
# ===========================================================================


class TestLinkage:
    def make_cluster(self):
        a = obs("obs-a", effective="2024-03-05T09:00:00Z")
        b = obs("obs-b", effective="2024-03-05T09:30:00Z")
        c = obs("obs-c", effective="2024-03-05T09:40:00Z")
        return records(a, b, c)

    def test_n_way_shape(self):
        cluster = self.make_cluster()
        survivor = select_survivor(cluster)
        alternates = [m for m in cluster if m.rid != survivor.rid]
        resource = build_linkage_resource(
            "dedup-x", survivor, alternates, "LAB", "LAB_30MIN")
        assert resource["resourceType"] == "Linkage"
        assert resource["active"] is True
        assert resource["item"][0] == {
            "type": "source",
            "resource": {"reference": "Observation/obs-a"}}
        alt_refs = [i["resource"]["reference"] for i in resource["item"][1:]]
        assert alt_refs == ["Observation/obs-b", "Observation/obs-c"]
        assert all(i["type"] == "alternate"
                   for i in resource["item"][1:])
        evidence = {e["url"]: e for e in resource["extension"][0]["extension"]}
        assert evidence["dedupId"]["valueString"] == "dedup-x"
        assert evidence["category"]["valueString"] == "LAB"
        assert evidence["memberCount"]["valueInteger"] == 3
        assert evidence["windowRule"]["valueString"] == "LAB_30MIN"

    def test_build_requires_alternates(self):
        cluster = self.make_cluster()
        survivor = select_survivor(cluster)
        with pytest.raises(ValueError):
            build_linkage_resource("d", survivor, [], "LAB", "LAB_30MIN")

    def test_upsert_creates_then_noops(self):
        conn = duckdb.connect()
        cluster = self.make_cluster()
        survivor = select_survivor(cluster)
        alternates = [m for m in cluster if m.rid != survivor.rid]
        first = upsert_dedup_linkage(conn, survivor, alternates)
        assert first["action"] == "created"
        assert first["dedup_id"] == survivor_dedup_id(cluster)
        second = upsert_dedup_linkage(conn, survivor, alternates)
        assert second["action"] == "noop"
        assert second["resource"] == first["resource"]
        assert len(load_dedup_linkage_resources(conn)) == 1

    def test_upsert_overwrites_on_corpus_drift(self):
        conn = duckdb.connect()
        cluster = self.make_cluster()
        survivor = select_survivor(cluster)
        alternates = [m for m in cluster if m.rid != survivor.rid]
        upsert_dedup_linkage(conn, survivor, alternates)
        # Corpus drift with the SAME membership (same dedup_id): obs-b's
        # timestamp moves earlier, so it becomes the survivor -> the stored
        # resource for the same key must be overwritten, not duplicated.
        drifted = records(
            obs("obs-a", effective="2024-03-05T09:00:00Z"),
            obs("obs-b", effective="2024-03-05T08:00:00Z"),
            obs("obs-c", effective="2024-03-05T09:40:00Z"))
        survivor2 = select_survivor(drifted)
        alternates2 = [m for m in drifted if m.rid != survivor2.rid]
        updated = upsert_dedup_linkage(conn, survivor2, alternates2)
        assert updated["action"] == "overwritten"
        assert updated["dedup_id"] == survivor_dedup_id(cluster)
        stored = load_dedup_linkage_resources(conn)
        assert len(stored) == 1
        assert stored[0]["item"][0]["resource"]["reference"] == \
            "Observation/obs-b"

    def test_upsert_order_independent(self):
        conn = duckdb.connect()
        cluster = self.make_cluster()
        survivor = select_survivor(cluster)
        alternates = [m for m in cluster if m.rid != survivor.rid]
        a = upsert_dedup_linkage(conn, survivor, alternates)
        conn2 = duckdb.connect()
        b = upsert_dedup_linkage(conn2, survivor, list(reversed(alternates)))
        assert a["resource"] == b["resource"]

    def test_delete_reverts(self):
        conn = duckdb.connect()
        cluster = self.make_cluster()
        survivor = select_survivor(cluster)
        dedup_id = upsert_dedup_linkage(
            conn, survivor,
            [m for m in cluster if m.rid != survivor.rid])["dedup_id"]
        assert delete_linkage(conn, dedup_id) == 1
        assert load_dedup_linkage_resources(conn) == []
        assert delete_linkage(conn, dedup_id) == 0

    def test_delete_all(self):
        conn = duckdb.connect()
        cluster = self.make_cluster()
        survivor = select_survivor(cluster)
        upsert_dedup_linkage(conn, survivor,
                             [m for m in cluster if m.rid != survivor.rid])
        assert delete_linkage(conn) == 1

    def test_window_rule_inference(self):
        lab = records(obs("a", effective="2024-03-05T09:00:00Z",
                          category="laboratory"),
                      obs("b", effective="2024-03-05T09:20:00Z",
                          category="laboratory"))
        assert infer_window_rule(lab) == "LAB_30MIN"
        trop = records(obs("a", effective="2024-03-05T09:00:00Z",
                           code="10839-9", category="laboratory"),
                       obs("b", effective="2024-03-05T09:04:00Z",
                           code="10839-9", category="laboratory"))
        assert infer_window_rule(trop) == "LAB_TROPONIN_5MIN"
        vital = records(obs("a", effective="2024-03-05T09:00:00Z",
                            code="8480-6"),
                        obs("b", effective="2024-03-05T09:03:00Z",
                            code="8480-6"))
        assert infer_window_rule(vital) == "VITAL_5MIN"
        height = records(obs("a", effective="2024-03-05T09:00:00Z",
                             code="8302-2"),
                         obs("b", effective="2024-03-05T09:20:00Z",
                             code="8302-2"))
        assert infer_window_rule(height) == "VITAL_EXTENDED_30MIN"
        subsumption = records(proc("a", performed="2024-06"),
                              proc("b", performed="2024-06-15"))
        assert infer_window_rule(subsumption) == "OTHER_SUBSUMPTION"
        same_date = records(proc("a", performed="2024-06-15"),
                            proc("b", performed="2024-06-15"))
        assert infer_window_rule(same_date) == "OTHER_SAME_DATE"


# ===========================================================================
# audit
# ===========================================================================


class TestAudit:
    def cluster(self):
        return records(obs("obs-a", effective="2024-03-05T09:00:00Z"),
                       obs("obs-b", effective="2024-03-05T09:30:00Z"))

    def test_one_row_per_cluster_decision(self):
        from fhir4ds.dedup import record_dedup_audit
        conn = duckdb.connect()
        cluster = self.cluster()
        survivor = select_survivor(cluster)
        record_dedup_audit(conn, "run-1", "dedup-x", "OTHER", 2,
                           survivor.rid, "OTHER_SAME_DATE",
                           survivor_rule_tuple(survivor),
                           {"members": [], "survivor": "Observation/obs-a"})
        rows = load_dedup_audit(conn, "run-1")
        assert len(rows) == 1
        row = rows[0]
        assert row["dedup_id"] == "dedup-x"
        assert row["category"] == "OTHER"
        assert row["member_count"] == 2
        assert row["survivor_rid"] == "obs-a"
        assert row["rule"] == "OTHER_SAME_DATE"
        assert row["rule_json"] == ["DT_Z", 0, "obs-a"]

    def test_run_id_scoping_and_validation(self):
        from fhir4ds.dedup import record_dedup_audit
        conn = duckdb.connect()
        record_dedup_audit(conn, "run-1", "dedup-x", "OTHER", 2, "s",
                           "OTHER_SAME_DATE", ["DT_Z", 0, "s"], {})
        record_dedup_audit(conn, "run-2", "dedup-x", "OTHER", 2, "s",
                           "OTHER_SAME_DATE", ["DT_Z", 0, "s"], {})
        assert len(load_dedup_audit(conn, "run-1")) == 1
        assert len(load_dedup_audit(conn, "run-2")) == 1
        with pytest.raises(ValueError):
            record_dedup_audit(conn, "", "d", "OTHER", 1, "s", "R", [], {})

    def test_no_wall_clock_in_audit_payload(self):
        conn = duckdb.connect()
        run_dedup([r.resource for r in self.cluster()], "run-audit",
                  conn=conn)
        payload = json.dumps(load_dedup_audit(conn, "run-audit"),
                             sort_keys=True).lower()
        assert "now" not in payload.replace("known", "")
        assert "utcnow" not in payload


# ===========================================================================
# run_dedup — end to end
# ===========================================================================


def mixed_corpus():
    # Duplicate Observation pair (LAB, same code/value/instant).
    lab_a = obs("lab-a", effective="2024-03-05T09:00:00Z",
                category="laboratory")
    lab_b = obs("lab-b", effective="2024-03-05T09:20:00Z",
                category="laboratory")
    # Duplicate Procedure pair: YEAR subsumes MONTH (slice-2 semantics —
    # day-precision rows bucket separately by design).
    proc_y = proc("proc-y", performed="2024")
    proc_m = proc("proc-m", performed="2024-06")
    # Unique rows.
    unique_obs = obs("uniq-1", effective="2024-03-06T09:00:00Z",
                     value=999)
    unique_proc = proc("uniq-2", performed="2024-07-01",
                       code="other-code")
    return [lab_a, lab_b, proc_y, proc_m, unique_obs, unique_proc]


class TestRunDedup:
    def test_mixed_corpus_counts(self):
        result = run_dedup(mixed_corpus(), "run-1")
        assert result.stats["input_resources"] == 6
        assert result.stats["clusters"] == 2
        assert result.stats["survivors"] == 2
        assert len(result.linkage_resources) == 2
        assert len(result.survivors) == 2
        assert result.stats["emitted"] == 2
        ids = sorted(result.dedup_ids)
        assert len(set(ids)) == 2

    def test_mixed_corpus_survivor_selection(self):
        result = run_dedup(mixed_corpus(), "run-1")
        assert len(result.survivors) == 2
        for s in result.survivors:
            ext = [e for e in s.get("extension", [])
                   if e.get("url") == DEDUP_EXTENSION_URL][0]
            fields = {e["url"]: e for e in ext["extension"]}
            rule = {e["url"]: e for e in
                    fields["survivorRule"]["extension"]}
            if s["resourceType"] == "Observation":
                # LAB pair: both DT_Z, lab-a is earliest -> survives.
                assert rule["survivorRid"]["valueString"] == "lab-a"
                assert rule["signature"]["valueString"] == "DT_Z"
            else:
                # Procedure: MONTH beats YEAR.
                assert rule["survivorRid"]["valueString"] == "proc-m"
                assert rule["signature"]["valueString"] == "MONTH"

    def test_mixed_corpus_linkage_window_rules(self):
        result = run_dedup(mixed_corpus(), "run-1")
        rules = {}
        for linkage in result.linkage_resources:
            evidence = {e["url"]: e for e in
                        linkage["extension"][0]["extension"]}
            rules[linkage["id"]] = evidence["windowRule"]["valueString"]
        assert sorted(rules.values()) == ["LAB_30MIN",
                                          "OTHER_SUBSUMPTION"]

    def test_audit_rows_default_skip_singletons(self):
        conn = duckdb.connect()
        run_dedup(mixed_corpus(), "run-1", conn=conn)
        rows = load_dedup_audit(conn, "run-1")
        assert len(rows) == 2
        assert all(r["dedup_id"] for r in rows)
        assert all(r["member_count"] == 2 for r in rows)

    def test_audit_rows_include_singletons_flag(self):
        conn = duckdb.connect()
        run_dedup(mixed_corpus(), "run-1", conn=conn,
                  include_singletons_in_audit=True)
        rows = load_dedup_audit(conn, "run-1")
        assert len(rows) == 4
        singletons = [r for r in rows if r["rule"] == "SINGLETON"]
        assert len(singletons) == 2
        assert all(r["dedup_id"] is None and r["member_count"] == 1
                   for r in singletons)

    def test_sources_never_mutated(self):
        corpus = mixed_corpus()
        import copy
        snapshots = [copy.deepcopy(r) for r in corpus]
        run_dedup(corpus, "run-1")
        assert corpus == snapshots

    def test_run_is_idempotent(self):
        conn = duckdb.connect()
        first = run_dedup(mixed_corpus(), "run-1", conn=conn)
        second = run_dedup(mixed_corpus(), "run-1", conn=conn)
        assert first.survivors == second.survivors
        assert first.linkage_resources == second.linkage_resources
        # Linkage upserts no-op; audit is append-only decision history.
        assert len(load_dedup_linkage_resources(conn)) == 2
        assert len(load_dedup_audit(conn, "run-1")) == 4

    def test_determinism_under_shuffle(self):
        import random
        baseline = None
        for seed in range(6):
            corpus = mixed_corpus()
            random.Random(seed).shuffle(corpus)
            result = run_dedup(corpus, "run-det")
            payload = {
                "survivors": json.dumps(result.survivors, sort_keys=True),
                "linkage": json.dumps(result.linkage_resources,
                                      sort_keys=True),
                "stats": json.dumps(result.stats, sort_keys=True),
            }
            if baseline is None:
                baseline = payload
            else:
                assert payload == baseline

    def test_revert_by_deleting_linkage(self):
        conn = duckdb.connect()
        result = run_dedup(mixed_corpus(), "run-1", conn=conn)
        for dedup_id in result.dedup_ids:
            delete_linkage(conn, dedup_id)
        assert load_dedup_linkage_resources(conn) == []
        # Sources were never touched: re-running rebuilds identical output.
        again = run_dedup(mixed_corpus(), "run-2", conn=conn)
        assert again.survivors == result.survivors
        assert again.linkage_resources == result.linkage_resources

    def test_run_id_validation(self):
        with pytest.raises(ValueError):
            run_dedup(mixed_corpus(), "")

    def test_empty_corpus(self):
        result = run_dedup([], "run-empty")
        assert result.survivors == []
        assert result.linkage_resources == []
        assert result.stats["clusters"] == 0

    def test_cross_unit_duplicate_pair_clusters(self):
        # Same instant, same code, mg vs g of the same mass: the UCUM
        # value-key canonicalization must collide (design §9 revision).
        corpus = [
            obs("mg-1", effective="2024-03-05T09:00:00Z",
                category="laboratory", value=5.0, unit="mg"),
            obs("g-1", effective="2024-03-05T09:00:00Z",
                category="laboratory", value=0.005, unit="g"),
        ]
        result = run_dedup(corpus, "run-cross-unit")
        assert result.stats["clusters"] == 1
        assert result.stats["survivors"] == 1
        # Equal ranking keys (same sig + ts + richness) -> smallest rid.
        ext = [e for e in result.survivors[0]["extension"]
               if e["url"] == DEDUP_EXTENSION_URL][0]
        fields = {e["url"]: e for e in ext["extension"]}
        rule = {e["url"]: e for e in fields["survivorRule"]["extension"]}
        assert rule["survivorRid"]["valueString"] == "g-1"


# ===========================================================================
# package surface
# ===========================================================================


def test_slice3_exports():
    import fhir4ds.dedup as pkg
    for name in ("select_survivor", "merge_resources", "run_dedup",
                 "upsert_dedup_linkage", "record_dedup_audit",
                 "delete_linkage", "DedupRunResult", "survivor_dedup_id"):
        assert hasattr(pkg, name), name


def test_dedup_pass_still_works_alongside():
    result = dedup_pass(mixed_corpus())
    assert result.stats["clusters"] == 2
