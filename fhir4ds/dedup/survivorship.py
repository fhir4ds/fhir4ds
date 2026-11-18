"""AMUX-142 slice 3 — survivorship ranking + merged survivor resources.

Design grounding: FEATURE_TEMPORAL_DEDUP.md §2d / §9 Q1 (survivor = a
materialized NEW merged resource; sources untouched; revert = delete the
Linkage + survivor).

Survivorship ranking (§2d) is a TOTAL ORDER over the members of a cluster:

1. **Highest date_format_signature** — DT_Z / DT_OFFSET (rank 4) >
   DT_NAIVE (3) > DATE_ONLY (2) > MONTH (1) > YEAR (0); no temporal value
   ranks -1 (always loses to any dated member).
2. **Earliest timestamp** — ``dt_utc`` falling back to ``start_utc``;
   ``None`` sorts LAST (a member without a comparable instant can never win
   this level, only lose it).
3. **Richest clinical metadata** — deterministic count of present keys
   among :data:`RICHNESS_KEYS`; more present keys wins.
4. **Lexicographically smallest rid** — the final total tie-break.

Levels are compared in that fixed order, so a higher-signature member
ALWAYS beats an earlier-timestamp member, and so on down. The ranking key
is exposed as :func:`survivor_ranking_key` (a plain tuple, minimized).

Merge semantics (v1): start from the survivor's resource; merge
identifiers, ``meta.source`` and codings on code-bearing elements from ALL
members; attach the dedup extension. Non-survivor field values beyond
identifiers / meta.source / codings are NOT merged in v1 (documented
limitation — element-level survivorship arrives with a later slice).
"""

from __future__ import annotations

import copy
import hashlib
import json
from typing import Any, Optional

from .pipeline import DedupRecord
from .temporal import Signature

__all__ = [
    "DEDUP_EXTENSION_URL",
    "RICHNESS_KEYS",
    "SURVIVOR_SIGNATURE_RANK",
    "survivor_ranking_key",
    "survivor_rule_tuple",
    "select_survivor",
    "survivor_dedup_id",
    "merge_resources",
]

#: fhir4ds temporal-dedup extension URL carried by survivors and Linkage.
DEDUP_EXTENSION_URL = "http://fhir4ds.com/fhir/StructureDefinition/dedup"

#: Clinical-metadata richness keys (design §2d "richest metadata"):
#: deterministic count of PRESENT keys (key exists, value is not None;
#: an explicitly empty list still counts as authored presence).
RICHNESS_KEYS: tuple[str, ...] = (
    "encounter",
    "performer",
    "referenceRange",
    "note",
    "dataAbsentReason",
    "bodySite",
    "method",
)

#: Signature tier for ranking level 1. DT_Z and DT_OFFSET share the top
#: tier (both fully determine an instant); the timestamp level breaks ties
#: between them. ``nd is None`` (no temporal value) ranks below YEAR.
SURVIVOR_SIGNATURE_RANK: dict[Optional[str], int] = {
    Signature.YEAR: 0,
    Signature.MONTH: 1,
    Signature.DATE_ONLY: 2,
    Signature.DT_NAIVE: 3,
    Signature.DT_Z: 4,
    Signature.DT_OFFSET: 4,
    None: -1,
}


def _signature_rank(record: DedupRecord) -> int:
    signature = record.nd.signature if record.nd is not None else None
    return SURVIVOR_SIGNATURE_RANK.get(signature, -1)


def _timestamp(record: DedupRecord) -> Optional[str]:
    """Comparable instant text (``dt_utc`` then ``start_utc``), or None."""
    nd = record.nd
    if nd is None:
        return None
    return nd.dt_utc or nd.start_utc


def _richness(record: DedupRecord) -> int:
    resource = record.resource
    return sum(
        1 for key in RICHNESS_KEYS
        if key in resource and resource[key] is not None
    )


def survivor_ranking_key(record: DedupRecord) -> tuple:
    """The total-order ranking key (MINIMIZED to select the survivor).

    Shape: ``(-signature_rank, (ts is None, ts or ""), -richness, rid)``.
    """
    ts = _timestamp(record)
    return (
        -_signature_rank(record),
        (ts is None, ts or ""),
        -_richness(record),
        record.rid,
    )


def survivor_rule_tuple(survivor: DedupRecord) -> list:
    """JSON-serializable rendering of the ranking tuple for evidence.

    ``[signature, richness, rid]`` — the surviving member's ranking levels
    EXCEPT the timestamp component: the extension carries NO timestamps
    (determinism doctrine, per the slice contract), and the signature tier
    plus the surviving rid pin the decision deterministically.
    """
    signature = survivor.nd.signature if survivor.nd is not None else None
    return [signature, _richness(survivor), survivor.rid]


def select_survivor(cluster: list[DedupRecord]) -> DedupRecord:
    """Select the survivor of one duplicate cluster (total order above)."""
    if not cluster:
        raise ValueError("cluster must be non-empty")
    return min(cluster, key=survivor_ranking_key)


def survivor_dedup_id(cluster: list[DedupRecord]) -> str:
    """Deterministic survivor id: ``dedup-<sha256(sorted rids)[:16]>``.

    Pure function of the SORTED member ids — ingest order and cluster
    discovery order never affect it (design §5.2).
    """
    rids = sorted(r.rid for r in cluster)
    digest = hashlib.sha256(",".join(rids).encode("utf-8")).hexdigest()
    return f"dedup-{digest[:16]}"


# ---------------------------------------------------------------------------
# Merge
# ---------------------------------------------------------------------------


def _coding_key(coding: Any) -> tuple[str, str]:
    if isinstance(coding, dict):
        return (str(coding.get("system") or ""),
                str(coding.get("code") or ""))
    return ("", json.dumps(coding, sort_keys=True, default=str))


def _merge_identifier_list(resources_in_order: list[dict]) -> Optional[list]:
    """Union of identifier entries, dedup by (system, value), first wins."""
    seen: set[tuple[str, str]] = set()
    merged: list = []
    for resource in resources_in_order:
        identifiers = resource.get("identifier")
        if not isinstance(identifiers, list):
            continue
        for identifier in identifiers:
            if not isinstance(identifier, dict):
                continue
            key = (str(identifier.get("system") or ""),
                   str(identifier.get("value") or ""))
            if key in seen:
                continue
            seen.add(key)
            merged.append(copy.deepcopy(identifier))
    return merged or None


def _merge_meta_source(resources_in_order: list[dict]) -> Optional[list[str]]:
    """Union of meta.source values across members, deduped and SORTED.

    FHIR's meta.source is 0..1 string per resource; the merged survivor
    carries the SORTED LIST of all sources' values (fhir4ds convention —
    the dedup extension also carries structured evidence). ``None`` when no
    member authors a meta.source.
    """
    values: list[str] = []
    for resource in resources_in_order:
        meta = resource.get("meta")
        if not isinstance(meta, dict):
            continue
        source = meta.get("source")
        if isinstance(source, str) and source:
            values.append(source)
        elif isinstance(source, list):
            values.extend(s for s in source if isinstance(s, str) and s)
    if not values:
        return None
    return sorted(set(values))


def _merge_code_concept(concepts_in_order: list[Any]) -> Optional[dict]:
    """Merge CodeableConcept values: union codings (dedup by system+code),
    first-authored order preserved (survivor's codings first); text from
    the first concept that authors one."""
    codings: list[Any] = []
    seen: set[tuple[str, str]] = set()
    text: Optional[str] = None
    base: Optional[dict] = None
    for concept in concepts_in_order:
        if not isinstance(concept, dict):
            continue
        if base is None:
            base = copy.deepcopy(concept)
        if text is None and isinstance(concept.get("text"), str):
            text = concept["text"]
        for coding in concept.get("coding") or []:
            if not isinstance(coding, dict):
                continue
            key = _coding_key(coding)
            if key in seen:
                continue
            seen.add(key)
            codings.append(copy.deepcopy(coding))
    if base is None:
        return None
    merged = copy.deepcopy(base)
    if codings:
        merged["coding"] = codings
    if text is not None:
        merged["text"] = text
    return merged


def _concept_set_key(concept: Any) -> str:
    """Stable identity for a CodeableConcept list entry (category union)."""
    if not isinstance(concept, dict):
        return json.dumps(concept, sort_keys=True, default=str)
    codings = concept.get("coding")
    if isinstance(codings, list) and codings:
        pairs = sorted(_coding_key(c) for c in codings
                       if isinstance(c, dict))
        return json.dumps(pairs)
    return json.dumps(concept, sort_keys=True, default=str)


def _merge_category_list(resources_in_order: list[dict]) -> Optional[list]:
    """Union of Observation.category entries by canonical coding set,
    first-authored order preserved."""
    merged: list[Any] = []
    seen: set[str] = set()
    for resource in resources_in_order:
        categories = resource.get("category")
        if not isinstance(categories, list):
            continue
        for category in categories:
            key = _concept_set_key(category)
            if key in seen:
                continue
            seen.add(key)
            merged.append(copy.deepcopy(category))
    return merged or None


def merge_resources(cluster: list[DedupRecord],
                    survivor: DedupRecord) -> dict:
    """Build the merged survivor resource for one cluster.

    - starts from a deep copy of the survivor's resource;
    - ``id`` = :func:`survivor_dedup_id` (deterministic hash);
    - identifiers: union over ALL members, dedup by (system, value),
      survivor's first (then remaining members in sorted-rid order);
    - ``meta.source``: sorted deduped list of every member's value;
    - codings on code-bearing elements (``code`` concept union,
      ``category`` entry union) preserve first-authored order;
    - appends the dedup extension (:data:`DEDUP_EXTENSION_URL`) carrying
      dedupId / sourceCount / sourceReferences / survivorRule /
      clusterCategory — NO timestamps (determinism doctrine).

    v1 limitation: non-survivor field values beyond identifiers /
    meta.source / codings are NOT merged.
    """
    if not cluster:
        raise ValueError("cluster must be non-empty")
    members = sorted(cluster, key=lambda r: (r.rid != survivor.rid, r.rid))
    resources_in_order = [m.resource for m in members]

    merged = copy.deepcopy(survivor.resource)
    merged["id"] = survivor_dedup_id(cluster)

    identifiers = _merge_identifier_list(resources_in_order)
    if identifiers is not None:
        merged["identifier"] = identifiers
    else:
        merged.pop("identifier", None)

    sources = _merge_meta_source(resources_in_order)
    survivor_meta = survivor.resource.get("meta")
    if isinstance(survivor_meta, dict):
        meta = copy.deepcopy(survivor_meta)
    else:
        meta = {}
    if sources is not None:
        meta["source"] = sources
    else:
        meta.pop("source", None)
    if meta:
        merged["meta"] = meta
    else:
        merged.pop("meta", None)

    code_concept = _merge_code_concept(
        [r.get("code") for r in resources_in_order])
    if code_concept is not None:
        merged["code"] = code_concept

    categories = _merge_category_list(resources_in_order)
    if categories is not None:
        merged["category"] = categories

    dedup_id = merged["id"]
    source_references = [f"{m.rtype}/{m.rid}" for m in
                         sorted(cluster, key=lambda m: m.rid)]
    extension_entry = {
        "url": DEDUP_EXTENSION_URL,
        "extension": [
            {"url": "dedupId", "valueString": dedup_id},
            {"url": "sourceCount",
             "valueInteger": len(source_references)},
            {"url": "sourceReferences", "extension": [
                {"url": "sourceReference", "valueString": ref}
                for ref in source_references
            ]},
            {"url": "survivorRule", "extension": [
                {"url": "signature", "valueString":
                 survivor_rule_tuple(survivor)[0] or "none"},
                {"url": "richness",
                 "valueInteger": survivor_rule_tuple(survivor)[1]},
                {"url": "survivorRid", "valueString": survivor.rid},
            ]},
            {"url": "clusterCategory", "valueString": survivor.category},
        ],
    }
    # Replace any prior dedup extension, preserve other extensions in order.
    existing = merged.get("extension")
    kept = ([copy.deepcopy(e) for e in existing
             if isinstance(e, dict) and e.get("url") != DEDUP_EXTENSION_URL]
            if isinstance(existing, list) else [])
    merged["extension"] = kept + [extension_entry]
    return merged
