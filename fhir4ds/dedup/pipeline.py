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

import json
import re
from dataclasses import dataclass, field, replace
from datetime import datetime
from typing import Optional
from zoneinfo import ZoneInfo

from .category import Category
from .codes import medication_code_keys, normalize_codes
from .lexical import raw_code_texts, tier2_provenance, tier2_text_set
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
    "CODE_FALLBACK_MODES",
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

#: Resource types whose medication[x] choice may be a medicationReference
#: resolved by the AMUX-150 bounded same-corpus resolver.
_MEDICATION_REFERENCE_TYPES = frozenset({
    "MedicationRequest", "MedicationDispense", "MedicationAdministration"})

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
    # AMUX-145 tier-2 fields (defaulted for direct-construction back-compat).
    # ``match_key`` is the SINGLE COALECED key (design redirect 2026-11-20):
    # ("code", system, code) elements from authored codings + confident
    # hybrid-index resolutions, plus ("text", normalized) elements ONLY
    # when the record did not confidently resolve (text tier is LAST —
    # resolved concepts outrank display equality). Attached in
    # :func:`dedup_pass` once the concept index is known.
    tier2_texts: frozenset[str] = frozenset()
    code_provenance: str = "none"
    resolved_concepts: dict = field(default_factory=dict)
    match_key: frozenset = frozenset()
    # AMUX-150 chunk A: code elements contributed by the bounded
    # same-corpus medication[x]-reference resolver. They live in
    # ``code_keys`` (they union like any coding) but are NOT authored
    # codings — pair-edge tier classification treats a shared
    # reference-resolved concept as ``hybrid:reference_resolved``.
    reference_resolved_keys: frozenset = frozenset()

    @property
    def concept_keys(self) -> frozenset[tuple[str, str]]:
        """Authored codings ∪ confidently resolved concepts."""
        return self.code_keys | frozenset(self.resolved_concepts)

    @classmethod
    def from_resource(cls, resource: dict, *,
                      code_resolver=None) -> "DedupRecord":
        """Build a DedupRecord from a raw resource dict.

        Raises ValueError when the resource lacks a usable string ``id``
        (deterministic cluster keys require ids).

        ``code_resolver`` (AMUX-150): optional bounded medication
        reference resolver (``.resolve(resource) -> Medication dict |
        None``); when given and the resource carries a
        ``medicationReference``, the resolved Medication's codings join
        ``code_keys`` with provenance ``reference_resolved``. Default
        ``None`` keeps direct construction working unchanged.
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
        code_keys = normalize_codes(resource)
        reference_resolved_keys: frozenset = frozenset()
        if code_resolver is not None and not code_keys \
                and rtype in _MEDICATION_REFERENCE_TYPES \
                and isinstance(resource.get("medicationReference"), dict):
            resolved = code_resolver.resolve(resource)
            resolved_keys = medication_code_keys(resolved) \
                if resolved is not None else frozenset()
            if resolved_keys:
                code_keys = resolved_keys
                reference_resolved_keys = resolved_keys
        provenance = tier2_provenance(resource, code_keys)
        if reference_resolved_keys:
            provenance = "reference_resolved"
        return cls(
            resource=resource,
            rid=rid,
            rtype=rtype,
            patient_ref=_patient_ref(resource),
            nd=nd,
            code_keys=code_keys,
            value_key=normalize_value(resource),
            category=categorize_record(resource),
            secondary_ts=secondary.dt_utc if secondary is not None else None,
            tier2_texts=tier2_text_set(resource),
            code_provenance=provenance,
            reference_resolved_keys=reference_resolved_keys,
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


#: AMUX-145 code-fallback cascade modes:
#: - ``on`` (default): the tier-2 coalesced match key (hybrid index
#:   resolution + text tier) is ACTIVE.
#: - ``audit_only``: tier-2 compatibility is computed for the curation
#:   queue but never unions.
#: - ``off``: canonical-only (pre-feature behavior).
CODE_FALLBACK_MODES = ("on", "audit_only", "off")


def _tier2_subtype(left: DedupRecord, right: DedupRecord) -> str:
    """Joel addendum (2026-11-20): ``hybrid`` when at least one side of
    the pair carried a usable coding (vocabulary disagreement — a
    terminology problem); ``text_only`` when neither side did (missing
    coded data — a source-data problem)."""
    return "hybrid" if (left.code_keys or right.code_keys) else "text_only"


def _pair_edge(left: DedupRecord, right: DedupRecord,
               shared: frozenset) -> Optional[dict]:
    """Build the union-edge record for a match-key intersection.

    Tier (design redirect 2026-11-20): ``canonical`` when any shared
    concept is an authored coding on BOTH sides; ``hybrid`` when a
    shared concept was introduced by index resolution on at least one
    side; ``text`` when only normalized-text tokens are shared.

    AMUX-150 §2.3: a shared concept introduced by the bounded
    medication-reference resolver on at least one side (and not authored
    on both) is ``hybrid`` with subtype ``reference_resolved`` — a
    data-completeness bridge, kept distinguishable from the vocabulary
    ``hybrid:text_only``/``hybrid:hybrid`` class.
    """
    concept_shared = sorted(
        (element for element in shared if element[0] == "code"),
        key=lambda element: (element[1], element[2]))
    text_shared = sorted(
        element for element in shared if element[0] == "text")
    edge = {"edge": sorted((left.rid, right.rid))}
    if concept_shared:
        for element in concept_shared:
            concept = (element[1], element[2])
            if concept in (left.code_keys - left.reference_resolved_keys) \
                    and concept in (right.code_keys
                                    - right.reference_resolved_keys):
                edge["tier"] = "canonical"
                return edge
        # Shared concept exists only via resolution on at least one side.
        # Reference-resolved first (AMUX-150), then concept-index.
        for element in concept_shared:
            concept = (element[1], element[2])
            resolvers = sorted(
                (record.rid for record in (left, right)
                 if concept in record.reference_resolved_keys))
            if resolvers:
                edge["tier"] = "hybrid"
                edge["subtype"] = "reference_resolved"
                edge["resolved_by"] = resolvers[0]
                edge["resolved_concept"] = list(concept)
                return edge
        edge["tier"] = "hybrid"
        edge["subtype"] = _tier2_subtype(left, right)
        for element in concept_shared:
            concept = (element[1], element[2])
            for record in sorted((left, right), key=lambda r: r.rid):
                meta = record.resolved_concepts.get(concept)
                if meta is not None:
                    edge["resolved_by"] = record.rid
                    edge["resolved_concept"] = list(concept)
                    edge["score"] = meta["score"]
                    edge["margin"] = meta["margin"]
                    edge["index_version"] = meta["index_version"]
                    break
            if "resolved_concept" in edge:
                break
        return edge
    if text_shared:
        from .lexical import normalize_lexical_text
        text_key = text_shared[0][1]
        edge["tier"] = "text"
        edge["subtype"] = _tier2_subtype(left, right)
        edge["text_key"] = text_key
        source_texts = {}
        for record in (left, right):
            source_texts[record.rid] = sorted(
                t for t in raw_code_texts(record.resource)
                if normalize_lexical_text(t) == text_key)
        edge["source_texts"] = source_texts
        return edge
    return None


def _code_components(records: list[DedupRecord], *,
                     tier2_union: bool = False,
                     tier2_compat: bool = False
                     ) -> tuple[list[list[DedupRecord]], list[dict],
                                list[dict]]:
    """Union-find over the COALESCED match key (design redirect
    2026-11-20), replacing the pre-redirect text-set any-intersection
    matcher.

    Two records union when their match-key sets share at least one
    element. Canonical intersections (an authored coding on both sides)
    always union — they never fall through to tier 2. Tier-2-only
    intersections (a resolved concept bridging vocabularies, or shared
    normalized text) union when ``tier2_union`` (mode ``on``); with
    ``tier2_compat`` only (``audit_only``) they are returned as
    suppressed candidates for the curation queue.

    Returns ``(components, edges, suppressed_pairs)``; deterministic
    (sorted rid order).
    """
    parent: dict[str, str] = {r.rid: r.rid for r in records}
    edges: list[dict] = []
    suppressed: list[dict] = []

    def find(x: str) -> str:
        root = x
        while parent[root] != root:
            root = parent[root]
        while parent[x] != root:  # path compression
            parent[x], x = root, parent[x]
        return root

    ordered = sorted(records, key=lambda r: r.rid)
    for i, left in enumerate(ordered):
        for right in ordered[i + 1:]:
            shared = left.match_key & right.match_key
            if not shared:
                continue
            edge = _pair_edge(left, right, shared)
            if edge is None:
                continue
            if edge["tier"] != "canonical" and not tier2_union:
                if tier2_compat:
                    suppressed.append(edge)
                continue
            rl, rr = find(left.rid), find(right.rid)
            if rl != rr:
                # Deterministic: the lexicographically smaller root wins.
                lo, hi = (rl, rr) if rl < rr else (rr, rl)
                parent[hi] = lo
                edges.append(edge)

    components: dict[str, list[DedupRecord]] = {}
    for record in ordered:
        components.setdefault(find(record.rid), []).append(record)
    return [components[root] for root in sorted(components)], edges, \
        suppressed


def _validate_code_fallback(code_fallback: str) -> str:
    if code_fallback not in CODE_FALLBACK_MODES:
        raise ValueError(
            f"code_fallback must be one of {CODE_FALLBACK_MODES}, "
            f"got {code_fallback!r}")
    return code_fallback


def partition(records: list[DedupRecord], *,
              code_fallback: str = "on"
              ) -> tuple[list[DedupRecord], list[list[DedupRecord]]]:
    """Stage 1: partition records into duplicate-candidate groups.

    Exact axes: ``(patient_ref, resource_type, partition_date, value_key)``.
    WITHIN each bucket, records union when their canonical code sets
    intersect (any-intersection matching via deterministic union-find);
    with ``code_fallback='on'`` (default), the tier-2 coalesced match
    key (hybrid index resolution + text tier) ALSO unions (AMUX-145).
    Returns ``(singletons, multi_groups)``; groups sorted by key (then by
    first member rid inside a bucket's component list), members sorted by
    rid.
    """
    singletons, multi_groups, _, _ = _partition_internal(
        records, code_fallback=code_fallback,
        attach_keys=True)
    return singletons, multi_groups


def _partition_internal(records: list[DedupRecord], *, code_fallback: str,
                        attach_keys: bool = False
                        ) -> tuple[list[DedupRecord],
                                   list[list[DedupRecord]],
                                   list[list[dict]],
                                   list[dict]]:
    """Partition + cascade bookkeeping.

    Returns ``(singletons, multi_groups, component_edges, suppressed)``:
    ``component_edges`` is a list PARALLEL to ``multi_groups`` — the
    union edges inside that group's component (tier ``canonical`` /
    ``hybrid`` / ``text``). Keying by the group's lead rid (the pre-fix
    shape) collides when two groups share a lead rid (duplicate ids in
    caller-built records), silently stripping the first group's edge
    evidence. ``suppressed`` carries tier-2-compatible same-bucket
    pairs that did NOT union (audit_only mode), annotated with their
    bucket key. ``attach_keys`` derives coalesced match keys for raw
    (never-attached) records — dedup_pass attaches earlier because it
    needs the records downstream.
    """
    mode = _validate_code_fallback(code_fallback)
    if attach_keys:
        # Lazy resolver: "off" mode never resolves, so it must not pay
        # the default-index build either (mirrors dedup_pass's contract).
        records = _attach_match_keys(records, _NULL_INDEX, mode)
    buckets: dict[tuple, list[DedupRecord]] = {}
    for record in records:
        buckets.setdefault(_sort_key(record), []).append(record)
    singletons: list[DedupRecord] = []
    multi_groups: list[list[DedupRecord]] = []
    component_edges: list[list[dict]] = []
    suppressed: list[dict] = []
    for key in sorted(buckets):
        components, edges, supp = _code_components(
            buckets[key],
            tier2_union=mode == "on",
            tier2_compat=mode in ("on", "audit_only"))
        for edge in supp:
            suppressed.append(dict(edge, bucket=list(key)))
        for component in components:
            members = sorted(component, key=lambda r: r.rid)
            if len(members) == 1:
                singletons.append(members[0])
                continue
            member_ids = {m.rid for m in members}
            multi_groups.append(members)
            component_edges.append(sorted(
                (e for e in edges
                 if e["edge"][0] in member_ids
                 and e["edge"][1] in member_ids),
                key=lambda e: (e["tier"], e["edge"])))
    return singletons, multi_groups, component_edges, suppressed


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
    """Outcome of one dedup pass (no survivorship yet — slice 3).

    AMUX-145 additions: ``cluster_edges`` (parallel to ``clusters``; the
    union edges inside each final cluster — tier ``canonical`` /
    ``hybrid`` / ``text``, hybrid edges carrying subtype + index version
    + score + margin), ``curation_records`` (deterministic tier-3 queue
    entries: ``unmatched`` + ``near_miss``), and ``records`` (the built
    DedupRecords, for proposer consumption).
    """

    emitted: list[DedupRecord] = field(default_factory=list)
    clusters: list[list[DedupRecord]] = field(default_factory=list)
    stats: dict = field(default_factory=dict)
    cluster_edges: list[list[dict]] = field(default_factory=list)
    curation_records: list[dict] = field(default_factory=list)
    records: list[DedupRecord] = field(default_factory=list)


def _codes_payload(record: DedupRecord) -> list[str]:
    return sorted(f"{system}|{code}" for system, code in record.code_keys)


def _records_by_rid_multimap(
        records: list[DedupRecord]) -> dict[str, list[DedupRecord]]:
    """rid -> records index, tolerant of cross-type id collisions.

    QA-D15H-001 (v0.0.26 D15 HISTORIAN): FHIR ids are unique per resource
    TYPE, so one corpus may legally carry an Observation and a Condition
    sharing an id. Near-miss edges are always same-type (built inside one
    Stage-1 bucket / text group, both of which key on rtype), so the
    lookup below resolves the pair by matching rtypes.
    """
    index: dict[str, list[DedupRecord]] = {}
    for record in records:
        index.setdefault(record.rid, []).append(record)
    return index


def _near_miss_pair(index: dict[str, list[DedupRecord]],
                    rid_a: str, rid_b: str) -> tuple[DedupRecord,
                                                     DedupRecord]:
    """Resolve the same-type record pair for a near-miss edge.

    Duplicate (rtype, id) identities were collapsed upstream, so at most
    one candidate per rid matches the peer's rtype — the resolution is
    unique for well-formed edges.
    """
    candidates_a = index[rid_a]
    candidates_b = index[rid_b]
    for left in candidates_a:
        for right in candidates_b:
            if left.rtype == right.rtype:
                return left, right
    raise KeyError(f"no same-type record pair for near-miss edge "
                   f"({rid_a}, {rid_b})")


def _near_miss_entry(records_by_rid: dict[str, list[DedupRecord]],
                     edge: dict, reason: str,
                     bucket: object) -> dict:
    left, right = _near_miss_pair(records_by_rid,
                                  edge["edge"][0], edge["edge"][1])
    entry = {
        "kind": "near_miss",
        "resource_type": left.rtype,
        "rids": [edge["edge"][0], edge["edge"][1]],
        "patient_ref": left.patient_ref,
        "bucket": bucket,
        "tier": edge.get("tier"),
        "shared_texts": [edge["text_key"]] if "text_key" in edge else [],
        "codes": {left.rid: _codes_payload(left),
                  right.rid: _codes_payload(right)},
        "reason": reason,
        "subtype": edge.get("subtype"),
    }
    if "resolved_concept" in edge:
        entry["shared_concept"] = edge["resolved_concept"]
    return entry


def _cross_bucket_near_misses(records: list[DedupRecord]) -> list[dict]:
    """Same-patient, same-type record pairs sharing a tier-2 text whose
    concept keys (authored codings + confident resolutions) are
    disjoint/empty but which landed in DIFFERENT Stage-1 buckets
    (corroboration failed on the date/value axis). These are exactly
    the pairs tier 2 might rescue with better data."""
    by_text: dict[tuple, list[DedupRecord]] = {}
    for record in records:
        if not record.tier2_texts:
            continue
        for text in record.tier2_texts:
            by_text.setdefault(
                (record.patient_ref or "", record.rtype, text),
                []).append(record)
    records_by_rid = _records_by_rid_multimap(records)
    seen: set[tuple[str, str]] = set()
    entries: list[dict] = []
    for key in sorted(by_text):
        group = sorted(by_text[key], key=lambda r: r.rid)
        if len(group) < 2:
            continue
        for i, left in enumerate(group):
            for right in group[i + 1:]:
                if _sort_key(left) == _sort_key(right):
                    continue  # same bucket — handled by the union path
                if left.concept_keys and right.concept_keys \
                        and not left.concept_keys.isdisjoint(
                            right.concept_keys):
                    continue  # concept-compatible — not a tier-2 case
                pair = (min(left.rid, right.rid), max(left.rid, right.rid))
                if pair in seen:
                    continue
                seen.add(pair)
                edge = {"edge": list(pair),
                        "tier": "text",
                        "subtype": _tier2_subtype(left, right),
                        "text_key": key[2]}
                entries.append(_near_miss_entry(
                    records_by_rid, edge, "cross_bucket", None))
    return entries


class _LazyDefaultIndex:
    """Resolves against the default concept index, building it on first
    use only (off mode never resolves, so it never pays the build)."""

    def __init__(self) -> None:
        self._index = None

    def resolve(self, text):
        if self._index is None:
            from .concept_index import default_concept_index
            self._index = default_concept_index()
        return self._index.resolve(text)


_NULL_INDEX = _LazyDefaultIndex()


def _collapse_duplicate_ids(resources: list[dict]) -> tuple[list[dict], int]:
    """Collapse resources sharing one ``(resourceType, id)`` identity.

    Doctrine (D15 SKEPTIC, v0.0.26; MedicationIndex precedent): an id
    is an identity only within a type+corpus — a re-supplied id is the
    SAME resource, and every downstream bookkeeping structure (union
    find, feature maps, edge evidence) keys on rid. Duplicate ids are
    collapsed deterministically to the lexicographically smallest
    ``json.dumps(sort_keys=True)`` form, so results depend on the
    resource SET, never on input order. Resources lacking a usable
    ``resourceType``/``id`` pass through untouched (``from_resource``
    raises on them with attribution, as before).

    Returns ``(collapsed_list, duplicate_count)``.
    """
    out: list[dict] = []
    seen: dict[tuple[str, str], dict] = {}
    pos: dict[tuple[str, str], int] = {}
    duplicates = 0
    for resource in resources:
        rtype = resource.get("resourceType") if isinstance(resource, dict) \
            else None
        rid = resource.get("id") if isinstance(resource, dict) else None
        if not (isinstance(rtype, str) and rtype
                and isinstance(rid, str) and rid):
            out.append(resource)
            continue
        key = (rtype, rid)
        existing = seen.get(key)
        if existing is None:
            seen[key] = resource
            pos[key] = len(out)
            out.append(resource)
            continue
        duplicates += 1
        if json.dumps(resource, sort_keys=True) < \
                json.dumps(existing, sort_keys=True):
            seen[key] = resource
            out[pos[key]] = resource
    return out, duplicates


def _attach_match_keys(records: list[DedupRecord], index,
                       mode: str) -> list[DedupRecord]:
    """Derive each record's COALESCED match key (design redirect
    2026-11-20): authored codings + confident hybrid-index resolutions,
    plus normalized-text tokens ONLY when the record resolved nothing
    confidently (text tier is LAST — resolved concepts outrank display
    equality). In ``off`` mode the key is the authored codings alone
    (canonical-only, pre-feature behavior)."""
    cache: dict[str, object] = {}

    def resolve(text: str):
        if text not in cache:
            cache[text] = index.resolve(text)
        return cache[text]

    out = []
    for record in records:
        resolved: dict[tuple[str, str], dict] = {}
        if mode != "off":
            for text in sorted(record.tier2_texts):
                hit = resolve(text)
                if hit is None:
                    continue
                meta = {"score": hit.score, "margin": hit.margin,
                        "index_version": hit.index_version,
                        "query": text}
                existing = resolved.get(hit.concept)
                if existing is None or (hit.score, text) < (
                        existing["score"], existing["query"]):
                    resolved[hit.concept] = meta
        key = {("code", system, code) for system, code in record.code_keys}
        key.update(("code", system, code)
                   for system, code in resolved)
        if mode != "off" and not resolved:
            key.update(("text", text) for text in record.tier2_texts)
        out.append(replace(
            record, resolved_concepts=resolved, match_key=frozenset(key)))
    return out


def dedup_pass(resources: list[dict], *, default_tz: str = DEFAULT_TZ,
               code_fallback: str = "on", concept_index=None,
               medication_resolver=None
               ) -> DedupResult:
    """Full pipeline: normalize → partition → escalate.

    ``emitted`` carries every record that is NOT part of a duplicate cluster
    (Stage-1 singletons plus rows that escalated but did not cluster).
    ``clusters`` carries duplicate groups (size >= 2, each sorted by rid,
    cluster list sorted by first member rid). ``stats`` carries counts.

    ``code_fallback`` (AMUX-145): ``"on"`` (default) activates the tier-2
    coalesced match key — hybrid concept-index resolution bridging
    vocabularies, then the conservative text tier; ``"audit_only"``
    computes tier-2 compatibility for the curation queue without
    merging; ``"off"`` restores canonical-only behavior.

    ``concept_index``: optional :class:`~fhir4ds.dedup.concept_index.
    ConceptIndex`; ``None`` uses the default versioned index built from
    the in-repo ValueSet display fixtures.

    ``medication_resolver`` (AMUX-150): optional bounded medication
    reference resolver (``.resolve(resource) -> Medication | None``);
    ``None`` (default) lazily builds the same-corpus
    :class:`~fhir4ds.dedup.medication.MedicationIndex` from
    ``resources`` on first use — a corpus without medication references
    never pays the build.
    """
    mode = _validate_code_fallback(code_fallback)
    stats_input_resources = len(resources)
    if medication_resolver is None:
        from .medication import LazyMedicationIndex
        medication_resolver = LazyMedicationIndex(resources)
    resources, duplicate_ids = _collapse_duplicate_ids(resources)
    records = [DedupRecord.from_resource(r,
                                         code_resolver=medication_resolver)
               for r in resources]
    # Off mode attaches canonical-only keys (the index is never consulted).
    records = _attach_match_keys(
        records,
        concept_index if concept_index is not None else _NULL_INDEX,
        mode)
    records_by_rid = _records_by_rid_multimap(records)
    singletons, multi_groups, component_edges, suppressed = \
        _partition_internal(records, code_fallback=mode)
    emitted: list[DedupRecord] = list(
        sorted(singletons, key=lambda r: r.rid))
    clusters: list[list[DedupRecord]] = []
    cluster_edges: list[list[dict]] = []
    near_misses: list[dict] = []
    for group, edges in zip(multi_groups, component_edges):
        tier2_edges = [e for e in edges if e["tier"] != "canonical"]
        escalated = escalate(group, default_tz=default_tz)
        cluster_of: dict[str, int] = {}
        for index, cluster in enumerate(escalated):
            for record in cluster:
                cluster_of[record.rid] = index
        for cluster in escalated:
            if len(cluster) >= 2:
                clusters.append(sorted(cluster, key=lambda r: r.rid))
                member_ids = {r.rid for r in cluster}
                cluster_edges.append(sorted(
                    (e for e in edges
                     if e["edge"][0] in member_ids
                     and e["edge"][1] in member_ids),
                    key=lambda e: (e["tier"], e["edge"])))
            else:
                emitted.append(cluster[0])
        if mode == "on":
            # Tier-2-compatible pairs the Stage-2 temporal rules split:
            # the corroboration tier did its job, time arbitrated no.
            for edge in tier2_edges:
                a, b = edge["edge"]
                if cluster_of.get(a) != cluster_of.get(b):
                    left, _right = _near_miss_pair(records_by_rid, a, b)
                    near_misses.append(_near_miss_entry(
                        records_by_rid, edge, "temporal_rejected",
                        list(_sort_key(left))))
    for edge in suppressed:
        near_misses.append(_near_miss_entry(
            records_by_rid, edge, "mode_suppressed", edge["bucket"]))
    if mode in ("on", "audit_only"):
        near_misses.extend(_cross_bucket_near_misses(records))

    # Tier-3 queue: unmatched = the never-canonical population (empty
    # canonical code key), regardless of tier-2 eligibility. A medication
    # record whose emptiness is caused by an unresolvable medication[x]
    # reference gets the DEDICATED kind (AMUX-150 §2.2) so the queue
    # distinguishes "missing coding" from "dangling reference".
    unmatched = []
    unresolved_refs = []
    for record in sorted((r for r in records if not r.code_keys),
                         key=lambda r: r.rid):
        reference_field = record.resource.get("medicationReference") \
            if record.rtype in _MEDICATION_REFERENCE_TYPES else None
        if isinstance(reference_field, dict):
            raw_ref = reference_field.get("reference")
            display = reference_field.get("display")
            unresolved_refs.append({
                "kind": "unresolved_medication_reference",
                "resource_type": record.rtype,
                "rid": record.rid,
                "patient_ref": record.patient_ref,
                "reference": raw_ref if isinstance(raw_ref, str)
                and raw_ref else None,
                **({"display": display}
                   if isinstance(display, str) and display else {}),
            })
            continue
        unmatched.append({
            "kind": "unmatched",
            "resource_type": record.rtype,
            "rid": record.rid,
            "patient_ref": record.patient_ref,
            "code_field": (record.resource.get(
                _code_field_name(record.rtype)) if _code_field_name(
                    record.rtype) else None),
            "tier2_texts": sorted(record.tier2_texts),
        })

    def queue_sort_key(entry: dict) -> tuple:
        lead = entry.get("rid") or sorted(entry["rids"])[0]
        return (entry["resource_type"], entry.get("patient_ref") or "",
                lead)

    curation_records = sorted(
        unmatched + unresolved_refs + near_misses,
        key=lambda e: (queue_sort_key(e), e["kind"]))

    emitted.sort(key=lambda r: r.rid)
    pairs = sorted(zip(clusters, cluster_edges),
                   key=lambda pair: pair[0][0].rid)
    clusters = [c for c, _ in pairs]
    cluster_edges = [e for _, e in pairs]
    duplicate_records = sum(len(c) for c in clusters)
    tier2_union_count = sum(
        1 for edges in component_edges for e in edges
        if e["tier"] != "canonical")
    return DedupResult(
        emitted=emitted,
        clusters=clusters,
        stats={
            "input_resources": stats_input_resources,
            "records": len(records),
            "duplicate_id_resources": duplicate_ids,
            "stage1_singletons": len(singletons),
            "escalated_groups": len(multi_groups),
            "clusters": len(clusters),
            "duplicate_records": duplicate_records,
            "emitted": len(emitted),
            "tier2_edges": sum(
                1 for edges in cluster_edges for e in edges
                if e["tier"] != "canonical"),
            "tier2_merges": tier2_union_count,
            "hybrid_resolutions": sum(
                len(r.resolved_concepts) for r in records),
            "curation_unmatched": len(unmatched),
            "curation_near_miss": len(near_misses),
            # AMUX-150 chunk A stats
            "reference_resolved_records": sum(
                1 for r in records if r.reference_resolved_keys),
            "unresolved_medication_references": len(unresolved_refs),
        },
        cluster_edges=cluster_edges,
        curation_records=curation_records,
        records=records,
    )


def _code_field_name(rtype: str) -> Optional[str]:
    from .codes import _CODE_FIELD_BY_TYPE
    return _CODE_FIELD_BY_TYPE.get(rtype)
