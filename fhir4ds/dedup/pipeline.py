"""AMUX-142 slice 2 — Stage-1 unified partitioning + Stage-2 temporal
clustering.

Pure, deterministic, in-memory pipeline over resource dicts:

- :class:`DedupRecord` — the normalized per-resource record assembled from
  the slice-1 normalizers (temporal signature, canonical code, value key,
  category, secondary timestamp).
- :func:`partition` — Stage 1: GROUP BY
  ``(patient_ref, resource_type, code_key, local_date, value_key)``;
  singleton groups emit directly, multi-groups escalate to Stage 2.
- :func:`escalate` — Stage 2: category-targeted temporal clustering
  (OTHER same-date merge + MONTH/YEAR subsumption; LAB/VITAL instant
  windows with single-linkage, exact effective==issued cross-field merge,
  and the 1:1 DATE_ONLY absorb guard).
- :func:`dedup_pass` — the full pipeline; no survivorship (slice 3), no
  Linkage (later slices).

Design grounding: FEATURE_TEMPORAL_DEDUP.md §2a/§2b/§2e, §3, §9.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
from zoneinfo import ZoneInfo

from .category import Category
from .codes import normalize_codes
from .temporal import (
    DEFAULT_TZ,
    NormalizedDate,
    Signature,
    _TEMPORAL_FIELDS,
    _classify_datetime,
    normalize_temporal,
    secondary_timestamp,
)
from .values import normalize_value

__all__ = [
    "DedupRecord",
    "DedupResult",
    "POC_TROPONIN",
    "VITAL_EXTENDED_WINDOW_LOINC",
    "dedup_pass",
    "escalate",
    "partition",
]


#: LOINC troponin mass-concentration codes (including point-of-care /
#: high-sensitivity) that tighten the LAB window from 30 to 5 minutes:
#: serial troponins minutes apart are usually repeats, not new draws.
#: 10839-9 Troponin I.cardiac [Mass/volume] in Serum or Plasma;
#: 89579-7   Troponin I.cardiac [...] by High sensitivity method;
#: 42637-9   Troponin I [Mass/volume] (vendor-named on the card);
#: 10501-5   Troponin T.ocardiac [Mass/volume] in Serum or Plasma;
#: 106733-9  Troponin I.cardiac [...] by Rapid immunoassay (POC);
#: 106906-1  Troponin I.cardiac [...] High sensitivity (Ser/Plas/Bld).
POC_TROPONIN: frozenset[str] = frozenset({
    "10839-9",
    "89579-7",
    "42637-9",
    "10501-5",
    "106733-9",
    "106906-1",
})

#: VITAL codes whose window extends from 5 to 30 minutes (height / weight /
#: BMI are routinely re-measured within one visit).
VITAL_EXTENDED_WINDOW_LOINC: frozenset[str] = frozenset({
    "8302-2",   # Body height
    "29463-7",  # Body weight
    "39156-5",  # Body mass index (BMI) [Ratio]
})

_LAB_WINDOW_MINUTES = 30
_LAB_TROPONIN_WINDOW_MINUTES = 5
_VITAL_WINDOW_MINUTES = 5
_VITAL_EXTENDED_WINDOW_MINUTES = 30

_LOINC = "http://loinc.org"

_DATETIME_SIGNATURES = (Signature.DT_NAIVE, Signature.DT_Z, Signature.DT_OFFSET)

# Patient-typed reference extraction: relative, absolute, and versioned
# spellings normalize to "Patient/<id>" (patient_ref doctrine — Patient-typed
# refs only; bare ids and non-Patient subjects do not attribute).
# ANCHORED (D15 SKEPTIC, v0.0.25): the Patient/<id> segment must be the FINAL
# path segment (after _history stripping) — an unanchored re.search attributed
# phantom patients from embedded/trailing path text such as
# ".../Patient/abc/other" or ".../List/Patient/abc-items" mid-path.
_PATIENT_REF_RE = re.compile(r"(?:^|/)Patient/([A-Za-z0-9\-.]{1,64})$")
_HISTORY_RE = re.compile(r"/_history/[A-Za-z0-9\-.]+$")


def _patient_ref(resource: dict) -> Optional[str]:
    """Extract the normalized Patient reference tail, if any.

    Checks ``subject`` then ``patient`` (the v1 resource scope carries one of
    the two). Only Patient-typed references attribute; a Group/Location/etc.
    reference yields None (never a phantom patient — loader doctrine).
    """
    for field_name in ("subject", "patient"):
        value = resource.get(field_name)
        if not isinstance(value, dict):
            continue
        reference = value.get("reference")
        if not isinstance(reference, str) or not reference:
            continue
        cleaned = _HISTORY_RE.sub("", reference)
        match = _PATIENT_REF_RE.search(cleaned)
        if match:
            return f"Patient/{match.group(1)}"
    return None


@dataclass(frozen=True)
class DedupRecord:
    """Normalized dedup record for one resource (immutable)."""

    resource: dict
    rid: str
    rtype: str
    patient_ref: Optional[str]
    nd: Optional[NormalizedDate]
    code_keys: frozenset[tuple[str, str]]
    value_key: str
    category: str
    secondary_ts: Optional[str]

    @classmethod
    def from_resource(cls, resource: dict) -> "DedupRecord":
        """Build a DedupRecord from a raw resource dict.

        Raises ValueError when the resource lacks a usable string ``id``
        (deterministic cluster keys require ids).
        """
        if not isinstance(resource, dict):
            raise ValueError("resource must be a dict")
        rid = resource.get("id")
        if not isinstance(rid, str) or not rid:
            raise ValueError("resource missing a usable string 'id'")
        rtype = resource.get("resourceType")
        if not isinstance(rtype, str) or not rtype:
            raise ValueError(f"resource {rid!r} missing resourceType")
        nd = normalize_temporal(resource)
        secondary = secondary_timestamp(resource)
        return cls(
            resource=resource,
            rid=rid,
            rtype=rtype,
            patient_ref=_patient_ref(resource),
            nd=nd,
            code_keys=normalize_codes(resource),
            value_key=normalize_value(resource),
            category=categorize_record(resource),
            secondary_ts=secondary.dt_utc if secondary is not None else None,
        )


def categorize_record(resource: dict) -> str:
    # Local import to avoid a circular module-level dependency at import time
    # (category.py is a leaf, but this keeps the pipeline module explicit).
    from .category import categorize

    return categorize(resource)


# ---------------------------------------------------------------------------
# Stage 1 — unified partitioning
# ---------------------------------------------------------------------------


def _partition_date(record: DedupRecord) -> str:
    """Date component of the Stage-1 key, precision-scoped.

    Day-precision-or-finer rows (DATE_ONLY, DT_*) key on their exact
    authored-local date. YEAR/MONTH rows key on the YEAR component: without
    this, an imprecise row could never share a partition with the cluster it
    must subsume into (a YEAR "2024" row and a MONTH "2024-06" row have
    different local_date strings), making the §2b subsumption rule
    unreachable. Year-bucketing only widens the candidate set — Stage 2
    re-filters with exact semantics.
    """
    nd = record.nd
    if nd is None:
        return ""
    if nd.signature in (Signature.YEAR, Signature.MONTH):
        return nd.local_date[:4]
    return nd.local_date


def _sort_key(record: DedupRecord) -> tuple:
    """Exact-equality partition axes (AMUX-142 addendum: code compatibility
    is NOT an exact axis — it is any-intersection inside the bucket).

    Axes: ``(patient_ref, resource_type, partition_date, value_key)``.
    """
    return (
        record.patient_ref or "",
        record.rtype,
        _partition_date(record),
        record.value_key,
    )


def _code_components(records: list[DedupRecord]) -> list[list[DedupRecord]]:
    """Union-find over code-set intersection (mirrors matching/corpus.py's
    deterministic components: sorted iteration, the smaller rid-root wins).

    Two records union when their canonical code SETS share at least one
    ``(system, code)`` pair — a LOINC-primary resource carrying a SNOMED
    translation unions with its SNOMED-primary duplicate. Empty code sets
    NEVER union (each such record is its own component).
    """
    parent: dict[str, str] = {r.rid: r.rid for r in records}

    def find(x: str) -> str:
        root = x
        while parent[root] != root:
            root = parent[root]
        while parent[x] != root:  # path compression
            parent[x], x = root, parent[x]
        return root

    ordered = sorted(records, key=lambda r: r.rid)
    for i, left in enumerate(ordered):
        if not left.code_keys:
            continue
        for right in ordered[i + 1:]:
            if not right.code_keys:
                continue
            if left.code_keys.isdisjoint(right.code_keys):
                continue
            rl, rr = find(left.rid), find(right.rid)
            if rl != rr:
                # Deterministic: the lexicographically smaller root wins.
                lo, hi = (rl, rr) if rl < rr else (rr, rl)
                parent[hi] = lo

    components: dict[str, list[DedupRecord]] = {}
    for record in ordered:
        components.setdefault(find(record.rid), []).append(record)
    return [components[root] for root in sorted(components)]


def partition(records: list[DedupRecord]) -> tuple[list[DedupRecord],
                                                   list[list[DedupRecord]]]:
    """Stage 1: partition records into duplicate-candidate groups.

    Exact axes: ``(patient_ref, resource_type, partition_date, value_key)``.
    WITHIN each bucket, records union when their canonical code sets
    intersect (any-intersection matching via deterministic union-find).
    Returns ``(singletons, multi_groups)``; groups sorted by key (then by
    first member rid inside a bucket's component list), members sorted by
    rid.
    """
    buckets: dict[tuple, list[DedupRecord]] = {}
    for record in records:
        buckets.setdefault(_sort_key(record), []).append(record)
    singletons: list[DedupRecord] = []
    multi_groups: list[list[DedupRecord]] = []
    for key in sorted(buckets):
        for component in _code_components(buckets[key]):
            members = sorted(component, key=lambda r: r.rid)
            if len(members) == 1:
                singletons.append(members[0])
            else:
                multi_groups.append(members)
    return singletons, multi_groups


# ---------------------------------------------------------------------------
# Stage 2 — targeted temporal escalation
# ---------------------------------------------------------------------------


def _instant(text: str) -> datetime:
    return datetime.fromisoformat(text.replace("Z", "+00:00"))


def _naive_authored_datetime(record: DedupRecord) -> Optional[datetime]:
    """Re-extract the authored naive datetime (primary field, start bound for
    periods). Returns None unless the authored value is a naive datetime."""
    for field_name, kind in _TEMPORAL_FIELDS.get(record.rtype, ()):
        value = record.resource.get(field_name)
        if value in (None, ""):
            continue
        if kind == "period":
            if not isinstance(value, dict):
                continue
            start = value.get("start")
            if not isinstance(start, str):
                continue
            classified = _classify_datetime(start)
            if classified and classified[0] == Signature.DT_NAIVE:
                return classified[1]
            continue
        classified = _classify_datetime(value) if isinstance(value, str) else None
        if classified and classified[0] == Signature.DT_NAIVE:
            return classified[1]
    return None


def _window_instant(record: DedupRecord, default_tz: str = DEFAULT_TZ
                    ) -> Optional[datetime]:
    """Comparable instant for Stage-2 windowing, or None.

    - DT_Z / DT_OFFSET: the authored instant (``dt_utc``, falling back to the
      period ``start_utc``, then the period ``end_utc`` — a mixed-precision
      Period whose start is date-only still windows on its timestamped END;
      before the v0.0.25 D15 fix such rows had NO comparable instant and
      silently dropped out of escalation).
    - DT_NAIVE: the authored wall clock interpreted in the configured default
      TZ (design §2a: the default TZ applies ONLY inside Stage-2 comparisons).
    - Date-level signatures: None (no time component to compare).
    """
    nd = record.nd
    if nd is None or nd.signature not in _DATETIME_SIGNATURES:
        return None
    if nd.signature in (Signature.DT_Z, Signature.DT_OFFSET):
        text = nd.dt_utc or nd.start_utc or nd.end_utc
        return _instant(text) if text else None
    naive = _naive_authored_datetime(record)
    if naive is None:
        return None
    return naive.replace(tzinfo=ZoneInfo(default_tz))


def _codes_in(group: list[DedupRecord], codes: frozenset[str]) -> bool:
    """True when ANY member's canonical code set carries one of the LOINC
    ``codes`` (window exceptions are any-member, per the addendum)."""
    for record in group:
        for system, code in record.code_keys:
            if system == _LOINC and code in codes:
                return True
    return False


def _sort_ts_records(records: list[DedupRecord], default_tz: str
                     ) -> list[tuple[datetime, DedupRecord]]:
    stamped = [(_window_instant(r, default_tz), r) for r in records]
    stamped = [(t, r) for t, r in stamped if t is not None]
    stamped.sort(key=lambda pair: (pair[0], pair[1].rid))
    return stamped


def _single_linkage(stamped: list[tuple[datetime, DedupRecord]],
                    window_minutes: int, default_tz: str
                    ) -> list[list[DedupRecord]]:
    """Greedy single-linkage over time-sorted rows: consecutive gaps within
    the window chain together (deterministic — input is pre-sorted)."""
    clusters: list[list[DedupRecord]] = []
    for instant, record in stamped:
        if clusters:
            # Chain against the last appended member (input is time-sorted).
            prev_instant = _window_instant(clusters[-1][-1], default_tz)
            if prev_instant is not None and \
                    (instant - prev_instant).total_seconds() <= \
                    window_minutes * 60:
                clusters[-1].append(record)
                continue
        clusters.append([record])
    return clusters


def _exact_cross_field_merge(
    clusters: list[list[DedupRecord]],
    row_cluster: dict[str, int],
) -> list[tuple[int, list[DedupRecord]]]:
    """Merge clusters when a row's ``secondary_ts`` (e.g. Observation.issued)
    equals ANOTHER row's authored effective instant (exact instant match).

    Deterministic union-find: rids processed in sorted order, the lower
    cluster index always wins. Returns ``(root, members)`` pairs, roots in
    ascending index order.
    """
    parent = list(range(len(clusters)))

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    authored: dict[str, str] = {}
    records_by_rid: dict[str, DedupRecord] = {}
    for index, cluster in enumerate(clusters):
        for record in cluster:
            records_by_rid[record.rid] = record
            if record.nd is not None and record.nd.dt_utc:
                authored[record.rid] = record.nd.dt_utc

    for rid in sorted(row_cluster):
        record = records_by_rid[rid]
        secondary = record.secondary_ts
        if not secondary:
            continue
        # "another's" authored instant — never self.
        partners = sorted(other for other, dt in authored.items()
                          if dt == secondary and other != rid)
        if not partners:
            continue
        own = find(row_cluster[rid])
        target = find(row_cluster[partners[0]])
        if own != target:
            lo, hi = min(own, target), max(own, target)
            parent[hi] = lo

    merged: dict[int, list[DedupRecord]] = {}
    for index, cluster in enumerate(clusters):
        merged.setdefault(find(index), []).extend(cluster)
    return sorted(merged.items())


def _escalate_temporal(group: list[DedupRecord], category: str,
                       default_tz: str) -> list[list[DedupRecord]]:
    """LAB/VITAL escalation: instant windows + exact cross-field + 1:1 guard."""
    if category == Category.LAB:
        if _codes_in(group, POC_TROPONIN):
            window = _LAB_TROPONIN_WINDOW_MINUTES
        else:
            window = _LAB_WINDOW_MINUTES
    else:  # VITAL
        if _codes_in(group, VITAL_EXTENDED_WINDOW_LOINC):
            window = _VITAL_EXTENDED_WINDOW_MINUTES
        else:
            window = _VITAL_WINDOW_MINUTES

    present = [r for r in group if r.nd is not None]
    ts_rows = [r for r in present
               if r.nd.signature in _DATETIME_SIGNATURES]

    stamped = _sort_ts_records(ts_rows, default_tz)
    clusters: list[list[DedupRecord]] = [list(c) for c in
                                         _single_linkage(stamped, window,
                                                         default_tz)]

    # Every remaining present row starts as its own singleton cluster so the
    # exact cross-field rule can pull any of them into a timestamped cluster.
    for record in sorted((r for r in present
                          if r.nd.signature not in _DATETIME_SIGNATURES),
                         key=lambda r: r.rid):
        clusters.append([record])

    row_cluster: dict[str, int] = {}
    for index, cluster in enumerate(clusters):
        for record in cluster:
            row_cluster[record.rid] = index

    clusters = _exact_cross_field_merge(clusters, row_cluster)

    # 1:1 absorb guard: DATE_ONLY rows join the unique timestamped cluster.
    def is_ts(cluster: list[DedupRecord]) -> bool:
        return any(r.nd is not None and r.nd.signature in _DATETIME_SIGNATURES
                   and _window_instant(r, default_tz) is not None
                   for r in cluster)

    ts_roots = [root for root, members in clusters if is_ts(members)]
    unique_ts_root = ts_roots[0] if len(ts_roots) == 1 else None
    result: list[list[DedupRecord]] = []
    for root, members in clusters:
        if root == unique_ts_root:
            continue  # emitted via the absorbed cluster below
        if unique_ts_root is not None and len(members) == 1 \
                and members[0].nd is not None \
                and members[0].nd.signature == Signature.DATE_ONLY:
            continue  # absorbed into the unique timestamped cluster below
        result.append(sorted(members, key=lambda r: r.rid))
    if unique_ts_root is not None:
        absorbed = sorted(
            [r for root, members in clusters for r in members
             if root == unique_ts_root
             or (len(members) == 1 and r.nd is not None
                 and r.nd.signature == Signature.DATE_ONLY)],
            key=lambda r: r.rid)
        result.append(absorbed)
    result.sort(key=lambda c: c[0].rid)
    return result


def _cluster_span(cluster: list[DedupRecord]) -> Optional[tuple[str, str]]:
    starts: list[str] = []
    ends: list[str] = []
    for record in cluster:
        nd = record.nd
        if nd is not None and nd.start_utc and nd.end_utc:
            starts.append(nd.start_utc)
            ends.append(nd.end_utc)
    if not starts:
        return None
    return min(starts), max(ends)


def _subsumes(cluster: list[DedupRecord], row: DedupRecord) -> bool:
    """True when the cluster's span CONTAINS the row's calendar span."""
    nd = row.nd
    if nd is None or not nd.start_utc or not nd.end_utc:
        return False
    span = _cluster_span(cluster)
    if span is not None:
        return span[0] <= nd.start_utc and nd.end_utc <= span[1]
    # Fallback: local prefix containment (cluster members are all at least
    # day-precision strings inside the row's MONTH/YEAR prefix).
    return all(member.nd is not None
               and member.nd.local_date.startswith(nd.local_date)
               for member in cluster)


def _escalate_other(group: list[DedupRecord]) -> list[list[DedupRecord]]:
    """OTHER escalation: same-local_date merge + MONTH/YEAR subsumption."""
    present = [r for r in group if r.nd is not None]
    imprecise = [r for r in present
                 if r.nd.signature in (Signature.YEAR, Signature.MONTH)]
    anchored = [r for r in present if r not in imprecise]

    # Same authored-local date (any signature) merges into ONE cluster.
    by_date: dict[str, list[DedupRecord]] = {}
    for record in anchored:
        by_date.setdefault(record.nd.local_date, []).append(record)
    clusters: list[list[DedupRecord]] = [
        sorted(members, key=lambda r: r.rid)
        for _, members in sorted(by_date.items())
    ]

    # MONTH/YEAR rows absorb into the first cluster whose span contains
    # their calendar span; otherwise they seed their own cluster. Sorted by
    # local_date so YEAR rows are processed before their MONTHs ("2024" <
    # "2024-03") and later MONTHs can absorb into an earlier YEAR cluster.
    for record in sorted(imprecise, key=lambda r: (r.nd.local_date, r.rid)):
        target = None
        for cluster in clusters:
            if _subsumes(cluster, record):
                target = cluster
                break
        if target is None:
            clusters.append([record])
        else:
            target.append(record)
            target.sort(key=lambda r: r.rid)
    clusters.sort(key=lambda c: (c[0].nd.local_date
                                 if c and c[0].nd is not None else "", c[0].rid))
    return clusters


def escalate(group: list[DedupRecord], *, default_tz: str = DEFAULT_TZ
             ) -> list[list[DedupRecord]]:
    """Stage 2: cluster one Stage-1 group; returns ALL clusters (including
    single-row clusters — callers route size-1 clusters back to emitted).

    Deterministic: inputs are sorted before every linkage/iteration; rows
    with ``nd is None`` never cluster.
    """
    if not group:
        return []
    singletons = [[r] for r in sorted(
        (r for r in group if r.nd is None), key=lambda r: r.rid)]
    present = [r for r in group if r.nd is not None]
    if not present:
        return singletons

    # A partition key guarantees patient/type/code/date/value equality, not
    # category: split by category (deterministic order) and escalate each.
    by_category: dict[str, list[DedupRecord]] = {}
    for record in present:
        by_category.setdefault(record.category, []).append(record)

    result: list[list[DedupRecord]] = list(singletons)
    for category in sorted(by_category):
        members = by_category[category]
        if category == Category.OTHER:
            result.extend(_escalate_other(members))
        else:  # LAB, VITAL
            result.extend(_escalate_temporal(members, category, default_tz))
    result.sort(key=lambda c: c[0].rid)
    return result


# ---------------------------------------------------------------------------
# Full pipeline
# ---------------------------------------------------------------------------


@dataclass
class DedupResult:
    """Outcome of one dedup pass (no survivorship yet — slice 3)."""

    emitted: list[DedupRecord] = field(default_factory=list)
    clusters: list[list[DedupRecord]] = field(default_factory=list)
    stats: dict = field(default_factory=dict)


def dedup_pass(resources: list[dict], *, default_tz: str = DEFAULT_TZ
               ) -> DedupResult:
    """Full pipeline: normalize → partition → escalate.

    ``emitted`` carries every record that is NOT part of a duplicate cluster
    (Stage-1 singletons plus rows that escalated but did not cluster).
    ``clusters`` carries duplicate groups (size >= 2, each sorted by rid,
    cluster list sorted by first member rid). ``stats`` carries counts.
    """
    records = [DedupRecord.from_resource(r) for r in resources]
    singletons, multi_groups = partition(records)
    emitted: list[DedupRecord] = list(
        sorted(singletons, key=lambda r: r.rid))
    clusters: list[list[DedupRecord]] = []
    for group in multi_groups:
        for cluster in escalate(group, default_tz=default_tz):
            if len(cluster) >= 2:
                clusters.append(sorted(cluster, key=lambda r: r.rid))
            else:
                emitted.append(cluster[0])
    emitted.sort(key=lambda r: r.rid)
    clusters.sort(key=lambda c: c[0].rid)
    duplicate_records = sum(len(c) for c in clusters)
    return DedupResult(
        emitted=emitted,
        clusters=clusters,
        stats={
            "input_resources": len(resources),
            "records": len(records),
            "stage1_singletons": len(singletons),
            "escalated_groups": len(multi_groups),
            "clusters": len(clusters),
            "duplicate_records": duplicate_records,
            "emitted": len(emitted),
        },
    )
