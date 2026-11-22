"""AMUX-150 chunk C — the temporal dedup strategy: Encounter.

Encounters have no code worth keying and no identity fields; their
duplicate signal is TEMPORAL: same patient (hard anchor), overlapping
periods, corroborating context. This front-end generates candidate pairs
(anchor grouping + interval bucketing) and makes additive-corroboration
decisions; the DECISION → union-find → survivorship → N-way dedup
Linkage → audit path is the shipped ``fhir4ds.dedup`` machinery,
unchanged (FDD §4).

Scoring (FDD §4.3, additive corroboration — each field's contribution is
the log of its inverse collision rate within one patient's encounter set):

===========================  =======  ==============================
signal                       points   requires
===========================  =======  ==============================
period overlap >= 80%          60     the temporal core
period overlap 1-80%           30     partial overlap is WEAK
adjacency (gap <= 15 min,      20     ED-to-admit handoffs
  same local day)
class.coding identical         10
>= 1 shared participant        10     practitioner ref tail id
serviceProvider identical      10
>= 1 shared location           10     Encounter.location tail id
serviceType identical           5
reasonCode any-intersection     5
===========================  =======  ==============================

**Merge**: score >= 60 AND temporal core present (overlap >= 80% or
adjacency). **Hard negative**: identical class=EMER encounters with
disjoint periods >= 2h apart never merge regardless of score. **CR-003
(Joel decision 2026-11-20, option a)**: the veto also constrains the
CLUSTER — before a merge edge is admitted, the resulting cluster must
contain no vetoed pair (vetoes precomputed per patient-group; edges
admitted in sorted-pair order, deterministic). Refused edges are
recorded with reason ``would_create_vetoed_pair`` plus the refused and
vetoed rids (curation queue kind ``encounter_edge_refused`` + the
``encounter_refused_edges`` stat). **Queue**:
score >= 30 with >= 2 corroborators (or >= 60 without a core) →
near-miss curation entry (``kind: "encounter_near_miss"``).

Encounters with NO usable period are singletons (queue ``unmatched``);
cross-patient encounters NEVER merge (the master-patient anchor groups
BEFORE any pairing); a Group-subject encounter (no patient reference)
is a singleton.

Determinism: no wall-clock anywhere; pairs iterate in sorted order; the
same resource SET yields identical clusters, Linkage, audit, and queue.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional
from zoneinfo import ZoneInfo

import duckdb

from .audit import record_dedup_audit
from .linkage import upsert_dedup_linkage
from .pipeline import DEFAULT_TZ, DedupRecord, DedupResult, _patient_ref
from .survivorship import (
    merge_resources,
    select_survivor,
    survivor_dedup_id,
    survivor_rule_tuple,
)
from .temporal import (
    NormalizedDate,
    Signature,
    _classify_datetime,
    _format_instant,
    overlap_fraction,
    period_overlap,
)

__all__ = [
    "EncounterFeatures",
    "encounter_pass",
    "run_encounter_dedup",
    "ENCOUNTER_MERGE_THRESHOLD",
]

#: Merge decision constants (FDD §4.3; Joel-approved defaults).
ENCOUNTER_MERGE_THRESHOLD = 60
_CONTAINMENT_FRACTION = 0.80
_ADJACENCY_MAX_GAP = "15m"
_HARD_NEGATIVE_MIN_GAP = "2h"

_ACT_SYSTEM = "http://terminology.hl7.org/CodeSystem/v3-ActCode"
_EMERGENCY_CLASS = "EMER"

_REF_TAIL_RE = re.compile(r"(?:^|/)([A-Za-z0-9\-.]{1,64})$")
_HISTORY_RE = re.compile(r"/_history/[A-Za-z0-9\-.]+$")


def _ref_tail(reference) -> Optional[str]:
    """Tail id of a FHIR reference string (``Practitioner/dr1`` ->
    ``dr1``), ``_history``-stripped."""
    if not isinstance(reference, str) or not reference:
        return None
    cleaned = _HISTORY_RE.sub("", reference)
    match = _REF_TAIL_RE.search(cleaned)
    return match.group(1) if match else None


def _coding_codes(concept) -> frozenset[tuple[str, str]]:
    """Codes of a CodeableConcept OR a bare Coding (``Encounter.class``
    is a Coding in FHIR R4)."""
    if not isinstance(concept, dict):
        return frozenset()
    codings = concept.get("coding")
    if codings is None and "code" in concept:
        codings = [concept]
    codes: set[tuple[str, str]] = set()
    for coding in codings or []:
        if not isinstance(coding, dict):
            continue
        system = coding.get("system")
        code = coding.get("code")
        if isinstance(system, str) and isinstance(code, str) and code:
            codes.add((system, code))
    return frozenset(codes)


@dataclass(frozen=True)
class EncounterFeatures:
    """Corroboration surface of one Encounter resource."""

    rid: str
    klass: frozenset[tuple[str, str]]
    participants: frozenset[str]
    provider: Optional[str]
    locations: frozenset[str]
    service_type: frozenset[tuple[str, str]]
    reason_codes: frozenset[tuple[str, str]]

    @property
    def is_emergency(self) -> bool:
        return (_ACT_SYSTEM, _EMERGENCY_CLASS) in self.klass

    @classmethod
    def from_resource(cls, resource: dict) -> "EncounterFeatures":
        participants: set[str] = set()
        for entry in resource.get("participant") or []:
            if not isinstance(entry, dict):
                continue
            individual = entry.get("individual")
            if isinstance(individual, dict):
                tail = _ref_tail(individual.get("reference"))
                if tail:
                    participants.add(tail)
        provider = None
        provider_ref = resource.get("serviceProvider")
        if isinstance(provider_ref, dict):
            provider = _ref_tail(provider_ref.get("reference"))
        locations: set[str] = set()
        for entry in resource.get("location") or []:
            if not isinstance(entry, dict):
                continue
            location_ref = entry.get("location")
            if isinstance(location_ref, dict):
                tail = _ref_tail(location_ref.get("reference"))
                if tail:
                    locations.add(tail)
        return cls(
            rid=resource.get("id") or "",
            klass=_coding_codes(resource.get("class")),
            participants=frozenset(participants),
            provider=provider,
            locations=frozenset(locations),
            service_type=_coding_codes(resource.get("serviceType")),
            reason_codes=frozenset(
                code for reason in resource.get("reasonCode") or []
                for code in _coding_codes(reason)),
        )


def _encounter_nd(resource: dict,
                  default_tz: str = DEFAULT_TZ) -> Optional[NormalizedDate]:
    """NormalizedDate for an Encounter period, with UTC bounds derived
    for naive/date-level bounds (default-TZ interpretation — Stage-2
    doctrine) so :func:`period_overlap` always sees comparable instants.

    None when the resource carries no usable period.
    """
    period = resource.get("period")
    if not isinstance(period, dict):
        return None
    tz = ZoneInfo(default_tz)
    start = _classify_datetime(period.get("start")) \
        if isinstance(period.get("start"), str) else None
    end = _classify_datetime(period.get("end")) \
        if isinstance(period.get("end"), str) else None
    if start is None and end is None:
        return None

    def bound_utc(bound) -> Optional[str]:
        if bound is None:
            return None
        signature, dt, _ = bound
        if signature in (Signature.DT_Z, Signature.DT_OFFSET):
            return _format_instant(dt)
        if signature == Signature.DT_NAIVE:
            return _format_instant(dt.replace(tzinfo=tz))
        # DATE_ONLY bound: local midnight (end extends to next midnight).
        day = dt.date()
        midnight = datetime(day.year, day.month, day.day, tzinfo=tz, fold=0)
        return _format_instant(midnight)

    def end_bound_utc(bound) -> Optional[str]:
        if bound is None:
            return None
        signature, dt, _ = bound
        if signature == Signature.DATE_ONLY:
            day = dt.date() + timedelta(days=1)
            return _format_instant(
                datetime(day.year, day.month, day.day, tzinfo=tz, fold=0))
        return bound_utc(bound)

    start_utc = bound_utc(start)
    end_utc = end_bound_utc(end)
    if start is not None and end is not None:
        signatures = {start[0], end[0]}
    else:
        signatures = {(start or end)[0]}
    if signatures & {Signature.DT_Z, Signature.DT_OFFSET}:
        signature = Signature.DT_Z
    elif Signature.DT_NAIVE in signatures:
        signature = Signature.DT_NAIVE
    else:
        signature = Signature.DATE_ONLY
    local_date = (start or end)[2][:10]
    return NormalizedDate(signature=signature, local_date=local_date,
                          dt_utc=None, start_utc=start_utc, end_utc=end_utc)


def _encounter_record(resource: dict,
                      default_tz: str = DEFAULT_TZ) -> DedupRecord:
    """Build the DedupRecord for one Encounter (category OTHER, no code
    keys, constant value key; the period carries in ``nd``; the raw
    resource carries the corroboration surface for survivorship)."""
    return DedupRecord(
        resource=resource,
        rid=resource["id"],
        rtype="Encounter",
        patient_ref=_patient_ref(resource),
        nd=_encounter_nd(resource, default_tz),
        code_keys=frozenset(),
        value_key="n/a",
        category="OTHER",
        secondary_ts=None,
    )


def _score_pair(a_nd, b_nd, a: EncounterFeatures, b: EncounterFeatures,
                default_tz: str) -> Optional[dict]:
    """Score one candidate pair; None when not even a candidate
    (periods neither overlap nor are same-day adjacent within 15 min)."""
    relationship = period_overlap(a_nd, b_nd)
    if relationship == "unknown":
        # Unknown periods never union; corroboration weight 0.
        return None
    # Hard negative FIRST (FDD §4.3): identical class=EMER encounters
    # disjoint >= 2h apart never merge regardless of score. This check
    # runs BEFORE the adjacency candidate gate — a disjoint pair is only
    # scored as a candidate when gap <= 15 min, so evaluating the veto
    # after the gate could never fire (it would be dead logic).
    hard_negative = (relationship == "disjoint"
                     and a.is_emergency and b.is_emergency
                     and period_overlap(a_nd, b_nd,
                                        max_gap=_HARD_NEGATIVE_MIN_GAP)
                     == "disjoint")
    if hard_negative:
        return {
            "score": 0,
            "signals": {},
            "core": False,
            "corroborators": 0,
            "hard_negative": True,
            "relationship": relationship,
            "overlap_fraction": 0.0,
        }
    if relationship == "disjoint":
        # Candidate only when same-day adjacent (ED-to-admit handoffs).
        if period_overlap(a_nd, b_nd, max_gap=_ADJACENCY_MAX_GAP) \
                != "adjacent" or not _same_day(a_nd, b_nd):
            return None
        relationship = "adjacent"
    signals: dict[str, int] = {}
    core = False
    if relationship == "overlap":
        fraction = overlap_fraction(a_nd, b_nd) or 0.0
        if fraction >= _CONTAINMENT_FRACTION:
            signals["overlap_containment"] = 60
            core = True
        elif fraction > 0:
            signals["overlap_partial"] = 30
    else:  # adjacency
        signals["adjacency"] = 20
        core = True
    if a.klass and a.klass == b.klass:
        signals["class"] = 10
    if a.participants & b.participants:
        signals["participant"] = 10
    if a.provider is not None and a.provider == b.provider:
        signals["serviceProvider"] = 10
    if a.locations & b.locations:
        signals["location"] = 10
    if a.service_type and a.service_type == b.service_type:
        signals["serviceType"] = 5
    if a.reason_codes & b.reason_codes:
        signals["reasonCode"] = 5
    corroborators = sum(1 for name in signals
                        if name not in ("overlap_containment",
                                        "overlap_partial", "adjacency"))
    score = sum(signals.values())
    return {
        "score": score,
        "signals": signals,
        "core": core,
        "corroborators": corroborators,
        "hard_negative": False,
        "relationship": relationship,
        "overlap_fraction": (overlap_fraction(a_nd, b_nd)
                             if relationship == "overlap" else 0.0),
    }


def _same_day(a_nd, b_nd) -> bool:
    """Same authored-local calendar day (adjacency is a same-day signal:
    ED-to-admit handoffs)."""
    return a_nd is not None and b_nd is not None \
        and a_nd.local_date == b_nd.local_date


def encounter_pass(resources: list[dict], *,
                   default_tz: str = DEFAULT_TZ,
                   membership: Optional[dict[str, str]] = None
                   ) -> DedupResult:
    """The temporal strategy pass over Encounter resources.

    ``membership``: member patient id -> master individual id (e.g.
    ``patient_membership``); ``None`` treats every patient reference as
    its own group (identity). Grouping happens BEFORE any pairing, so
    cross-patient encounters can never merge.

    CR-003: within a group, merge edges are admitted under the veto
    constraint — an edge whose admission would place a vetoed (EMER
    hard-negative) pair inside one cluster is refused and audit-recorded
    (``encounter_edge_refused`` curation entry with reason
    ``would_create_vetoed_pair``).
    """
    features: dict[str, EncounterFeatures] = {}
    records: list[DedupRecord] = []
    # QA-D15S-001 (v0.0.26 D15 SKEPTIC): an Encounter id is the corpus
    # identity — duplicate ids are the SAME resource re-supplied. Collapse
    # deterministically to the smallest serialized form BEFORE any pairing:
    # the feature map, union-find, and component bookkeeping all key on
    # rid, so uncollapsed duplicates fabricated clusters (no pair
    # evidence) and made results depend on input order.
    encounters_by_id: dict[str, dict] = {}
    for resource in resources:
        if not isinstance(resource, dict) \
                or resource.get("resourceType") != "Encounter":
            continue
        rid = resource.get("id")
        if not isinstance(rid, str) or not rid:
            continue
        existing = encounters_by_id.get(rid)
        if existing is None or json.dumps(resource, sort_keys=True) < \
                json.dumps(existing, sort_keys=True):
            encounters_by_id[rid] = resource
    duplicate_ids = len(resources) - len(encounters_by_id) - sum(
        1 for r in resources
        if not (isinstance(r, dict)
                and r.get("resourceType") == "Encounter"
                and isinstance(r.get("id"), str) and r.get("id")))
    for rid in sorted(encounters_by_id):
        resource = encounters_by_id[rid]
        records.append(_encounter_record(resource, default_tz))
        features[rid] = EncounterFeatures.from_resource(resource)

    membership = membership or {}

    def group_key(record: DedupRecord) -> Optional[str]:
        if record.patient_ref is None:
            return None
        member = record.patient_ref[len("Patient/"):]
        individual = membership.get(member)
        # QA-D15S-002 (v0.0.26 D15 SKEPTIC): a falsy/blank master must
        # NEVER co-group unrelated patients (the documented "cross-
        # patient encounters never merge" invariant); fall back to
        # patient-identity grouping.
        if isinstance(individual, str) and individual.strip():
            return f"ind:{individual}"
        return f"pat:{record.patient_ref}"

    groups: dict[str, list[DedupRecord]] = {}
    ungrouped: list[DedupRecord] = []
    for record in sorted(records, key=lambda r: r.rid):
        key = group_key(record)
        if key is None:
            ungrouped.append(record)
        else:
            groups.setdefault(key, []).append(record)

    emitted: list[DedupRecord] = list(ungrouped)
    clusters: list[list[DedupRecord]] = []
    cluster_edges: list[list[dict]] = []
    curation: list[dict] = []

    # No usable period -> singleton (emitted via the group/ungrouped paths)
    # + unmatched queue entry.
    for record in sorted(records, key=lambda r: r.rid):
        if record.nd is None:
            curation.append({
                "kind": "unmatched",
                "resource_type": "Encounter",
                "rid": record.rid,
                "patient_ref": record.patient_ref,
                "reason": "no_usable_period",
            })

    merge_edges: list[dict] = []
    refused_edges: list[dict] = []
    for key in sorted(groups):
        members = groups[key]
        parent: dict[str, str] = {r.rid: r.rid for r in members}

        def find(x: str) -> str:
            root = x
            while parent[root] != root:
                root = parent[root]
            while parent[x] != root:
                parent[x], x = root, parent[x]
            return root

        # CR-003: precompute the per-pair scores AND the vetoed pairs
        # (EMER hard negatives) for this patient-group BEFORE any edge is
        # admitted, so cluster admission can be constrained: a merge edge
        # is refused when the resulting cluster would contain a vetoed
        # pair (union-find transitivity must not defeat the veto).
        # Pairs iterate in sorted order — deterministic admission order.
        scored_pairs: dict[tuple[str, str], dict] = {}
        vetoed_pairs: list[tuple[str, str]] = []
        for i, left in enumerate(members):
            for right in members[i + 1:]:
                if left.nd is None or right.nd is None:
                    continue
                scored = _score_pair(
                    left.nd, right.nd, features[left.rid],
                    features[right.rid], default_tz)
                if scored is None:
                    continue
                pair = (min(left.rid, right.rid), max(left.rid, right.rid))
                scored_pairs[pair] = scored
                if scored["hard_negative"]:
                    vetoed_pairs.append(pair)

        group_edges: list[dict] = []
        for (left_rid, right_rid) in sorted(scored_pairs):
            scored = scored_pairs[(left_rid, right_rid)]
            left = next(r for r in members if r.rid == left_rid)
            right = next(r for r in members if r.rid == right_rid)
            edge = {"edge": [left_rid, right_rid],
                    "patient_group": key, **scored}
            merges = (scored["score"] >= ENCOUNTER_MERGE_THRESHOLD
                      and scored["core"]
                      and not scored["hard_negative"])
            near_miss = (not merges and not scored["hard_negative"]
                         and scored["score"] >= 30
                         and (scored["corroborators"] >= 2
                              or scored["score"]
                              >= ENCOUNTER_MERGE_THRESHOLD))
            if merges:
                rl, rr = find(left_rid), find(right_rid)
                if rl == rr:
                    # Redundant edge inside an admitted cluster — safe.
                    group_edges.append(edge)
                    merge_edges.append(edge)
                    continue
                # Constrained admission (CR-003): refuse the edge when the
                # union would place any vetoed pair inside one cluster.
                conflict = None
                for veto in sorted(vetoed_pairs):
                    vl, vr = find(veto[0]), find(veto[1])
                    if (vl, vr) in ((rl, rr), (rr, rl)):
                        conflict = veto
                        break
                if conflict is not None:
                    refused = {
                        "kind": "encounter_edge_refused",
                        "resource_type": "Encounter",
                        "rids": [left_rid, right_rid],
                        "patient_group": key,
                        "reason": "would_create_vetoed_pair",
                        "vetoed_pair": [conflict[0], conflict[1]],
                        "score": scored["score"],
                        "signals": scored["signals"],
                        "corroborators": scored["corroborators"],
                    }
                    refused_edges.append(refused)
                    curation.append(refused)
                    continue
                group_edges.append(edge)
                merge_edges.append(edge)
                lo, hi = (rl, rr) if rl < rr else (rr, rl)
                parent[hi] = lo
            elif near_miss:
                curation.append({
                    "kind": "encounter_near_miss",
                    "resource_type": "Encounter",
                    "rids": edge["edge"],
                    "patient_ref": left.patient_ref,
                    "score": scored["score"],
                    "signals": scored["signals"],
                    "corroborators": scored["corroborators"],
                })
        components: dict[str, list[DedupRecord]] = {}
        for record in members:
            components.setdefault(find(record.rid), []).append(record)
        member_ids_by_root = {root: {r.rid for r in comps}
                              for root, comps in components.items()}
        for root in sorted(components):
            component = sorted(components[root], key=lambda r: r.rid)
            if len(component) >= 2:
                ids = member_ids_by_root[root]
                clusters.append(component)
                cluster_edges.append(sorted(
                    (e for e in group_edges
                     if e["edge"][0] in ids and e["edge"][1] in ids),
                    key=lambda e: e["edge"]))
            else:
                emitted.append(component[0])

    emitted.sort(key=lambda r: r.rid)
    pairs = sorted(zip(clusters, cluster_edges),
                   key=lambda pair: pair[0][0].rid)
    clusters = [c for c, _ in pairs]
    cluster_edges = [e for _, e in pairs]
    curation.sort(key=lambda e: (e.get("rid") or sorted(e["rids"])[0],
                                 e["kind"]))
    return DedupResult(
        emitted=emitted,
        clusters=clusters,
        stats={
            "input_resources": len(resources),
            "records": len(records),
            "duplicate_id_resources": duplicate_ids,
            "stage1_singletons": len(emitted),
            "escalated_groups": len(groups),
            "clusters": len(clusters),
            "duplicate_records": sum(len(c) for c in clusters),
            "emitted": len(emitted),
            "encounter_patient_groups": len(groups),
            "encounter_near_miss": sum(
                1 for e in curation if e["kind"] == "encounter_near_miss"),
            "encounter_refused_edges": len(refused_edges),
        },
        cluster_edges=cluster_edges,
        curation_records=curation,
        records=records,
    )


@dataclass
class EncounterRunResult:
    """Outcome of one encounter dedup run (mirrors DedupRunResult)."""

    run_id: str
    survivors: list[dict] = field(default_factory=list)
    linkage_resources: list[dict] = field(default_factory=list)
    stats: dict = field(default_factory=dict)
    curation_queue_path: Optional[str] = None

    @property
    def dedup_ids(self) -> list[str]:
        return [s["id"] for s in self.survivors]


def _encounter_evidence(cluster: list[DedupRecord],
                        survivor: DedupRecord,
                        edges: list[dict]) -> dict:
    lead = max(edges, key=lambda e: e["score"]) if edges else None
    evidence = {
        "members": [
            {"reference": f"Encounter/{m.rid}",
             "signature": (m.nd.signature if m.nd is not None else None),
             "rankingKey": None}
            for m in sorted(cluster, key=lambda m: m.rid)
        ],
        "survivor": f"Encounter/{survivor.rid}",
    }
    if lead is not None:
        evidence["encounterScore"] = {
            "score": lead["score"],
            "signals": lead["signals"],
            "corroborators": lead["corroborators"],
            "overlapFraction": lead["overlap_fraction"],
            "relationship": lead["relationship"],
        }
    return evidence


def run_encounter_dedup(
    resources: list[dict],
    run_id: str,
    *,
    conn: Optional[duckdb.DuckDBPyConnection] = None,
    include_singletons_in_audit: bool = False,
    default_tz: str = DEFAULT_TZ,
    membership: Optional[dict[str, str]] = None,
    output_dir: Optional[str] = None,
) -> EncounterRunResult:
    """Run the temporal (Encounter) dedup strategy end to end.

    Clusters flow through the UNCHANGED back end — ``select_survivor`` /
    ``merge_resources`` / ``upsert_dedup_linkage`` /
    ``record_dedup_audit`` — with ``window_rule = "encounter:overlap"``
    (``|CORROB:<n>`` when the cluster's best edge carries corroborators).
    """
    if not isinstance(run_id, str) or not run_id:
        raise ValueError("run_id must be a non-empty string")
    own_connection = conn is None
    if own_connection:
        conn = duckdb.connect()
    else:
        from ._conn import require_open_connection

        require_open_connection(conn, "run encounter dedup")

    result = encounter_pass(resources, default_tz=default_tz,
                            membership=membership)
    survivors: list[dict] = []
    linkage_resources: list[dict] = []
    try:
        for cluster, edges in zip(result.clusters, result.cluster_edges):
            survivor = select_survivor(cluster)
            merged = merge_resources(cluster, survivor)
            alternates = [m for m in cluster if m.rid != survivor.rid]
            rule = "encounter:overlap"
            if edges:
                best = max(edges, key=lambda e: e["score"])
                if best["corroborators"] > 0:
                    rule += f"|CORROB:{best['corroborators']}"
            upsert = upsert_dedup_linkage(
                conn, survivor, alternates,
                category=survivor.category,
                window_rule=rule,
            )
            record_dedup_audit(
                conn,
                run_id,
                survivor_dedup_id(cluster),
                survivor.category,
                len(cluster),
                survivor.rid,
                rule,
                survivor_rule_tuple(survivor),
                _encounter_evidence(cluster, survivor, edges),
            )
            survivors.append(merged)
            linkage_resources.append(upsert["resource"])
    finally:
        if own_connection:
            conn.close()

    queue_path = None
    if output_dir is not None:
        from .curation import CURATION_QUEUE_FILENAME, write_curation_queue
        from pathlib import Path as _Path
        written = write_curation_queue(
            _Path(output_dir) / CURATION_QUEUE_FILENAME,
            [dict(entry, run_id=run_id) for entry in result.curation_records])
        queue_path = str(written)

    survivors.sort(key=lambda s: s["id"])
    linkage_resources.sort(key=lambda r: r["id"])
    stats = dict(result.stats)
    stats.update({
        "run_id": run_id,
        "survivors": len(survivors),
        "linkage_resources": len(linkage_resources),
        "audit_rows": len(result.clusters),
    })
    return EncounterRunResult(run_id=run_id, survivors=survivors,
                              linkage_resources=linkage_resources,
                              stats=stats, curation_queue_path=queue_path)
