"""FHIR R4 Linkage writer for temporal-dedup clusters (AMUX-142 slice 3).

Mirrors :mod:`fhir4ds.matching.linkage`'s writer pattern (canonical
storage key, deterministic ``sort_keys`` JSON, idempotent upsert with
noop / overwritten / created semantics) — MIRRORED rather than imported
because the matching writer is pairwise (``Patient/<a>|Patient/<b>` keyed,
``MatchResult``-typed) and cannot express an N-way resource cluster;
modifying ``fhir4ds/matching`` is out of scope for AMUX-142. Divergences
from the matching writer, all structural consequences of N-way clusters:

- storage key is the deterministic ``dedup_id`` (sha256 of sorted member
  rids — :func:`survivorship.survivor_dedup_id`), not a pair key;
- ``item[0]`` = survivor (``type: source``); ``item[1..n]`` = every OTHER
  member as ``type: alternate`` (the survivor links the sources to
  itself; linking a resource to itself as its own alternate would be
  redundant);
- extension URL is the temporal-dedup URL with cluster evidence
  (dedupId / category / memberCount / windowRule).

Determinism doctrine: no wall-clock timestamps anywhere in the resource.
Deleting a cluster's row (:func:`delete_linkage`) fully reverts the merge
decision (survivor resources live with the caller — sources are never
touched).
"""

from __future__ import annotations

import json
from typing import Any, Optional

import duckdb

from .pipeline import (
    POC_TROPONIN,
    VITAL_EXTENDED_WINDOW_LOINC,
    DedupRecord,
)
from .survivorship import survivor_dedup_id

__all__ = [
    "TEMPORAL_DEDUP_EXTENSION_URL",
    "DEDUP_LINKAGE_DDL",
    "build_linkage_resource",
    "infer_window_rule",
    "create_dedup_linkage_table",
    "upsert_dedup_linkage",
    "delete_linkage",
    "load_dedup_linkage_resources",
]

#: Extension URL carried by dedup Linkage resources (design §1.4). The
#: survivor resource itself carries the sibling ``.../dedup`` URL
#: (:data:`survivorship.DEDUP_EXTENSION_URL`).
TEMPORAL_DEDUP_EXTENSION_URL = (
    "http://fhir4ds.com/fhir/StructureDefinition/temporal-dedup"
)

DEDUP_LINKAGE_DDL = """
CREATE TABLE IF NOT EXISTS dedup_linkage (
    dedup_id VARCHAR PRIMARY KEY,
    resource JSON,
    category VARCHAR,
    member_count INTEGER
)
"""

_LOINC = "http://loinc.org"


def infer_window_rule(cluster: list[DedupRecord]) -> str:
    """Deterministic label for the Stage-2 rule that plausibly fired.

    Coarse by design (slice 2 does not record per-cluster rule identity):
    imprecise-signature spread in an OTHER cluster implies the §2b
    subsumption rule; LAB/VITAL clusters refine by the vendored window
    exception code sets (any-member, matching the escalation semantics).
    """
    category = cluster[0].category if cluster else "OTHER"
    signatures = {r.nd.signature if r.nd is not None else None
                  for r in cluster}
    if category == "OTHER":
        if signatures & {"YEAR", "MONTH"} and len(signatures) > 1:
            return "OTHER_SUBSUMPTION"
        return "OTHER_SAME_DATE"
    if category == "LAB":
        for record in cluster:
            for system, code in record.code_keys:
                if system == _LOINC and code in POC_TROPONIN:
                    return "LAB_TROPONIN_5MIN"
        return "LAB_30MIN"
    # VITAL
    for record in cluster:
        for system, code in record.code_keys:
            if system == _LOINC and code in VITAL_EXTENDED_WINDOW_LOINC:
                return "VITAL_EXTENDED_30MIN"
    return "VITAL_5MIN"


def build_linkage_resource(
    dedup_id: str,
    survivor: DedupRecord,
    alternates: list[DedupRecord],
    category: str,
    window_rule: str,
) -> dict[str, Any]:
    """Build the deterministic N-way Linkage resource for one cluster."""
    if not alternates:
        raise ValueError("a dedup Linkage requires at least one alternate")
    items = [{"type": "source",
              "resource": {"reference": f"{survivor.rtype}/{survivor.rid}"}}]
    for member in sorted(alternates, key=lambda m: m.rid):
        items.append({"type": "alternate",
                      "resource": {"reference":
                                   f"{member.rtype}/{member.rid}"}})
    return {
        "resourceType": "Linkage",
        "id": dedup_id,
        "active": True,
        "item": items,
        "extension": [
            {
                "url": TEMPORAL_DEDUP_EXTENSION_URL,
                "extension": [
                    {"url": "dedupId", "valueString": dedup_id},
                    {"url": "category", "valueString": category},
                    {"url": "memberCount",
                     "valueInteger": 1 + len(alternates)},
                    {"url": "windowRule", "valueString": window_rule},
                ],
            }
        ],
    }


def create_dedup_linkage_table(conn: duckdb.DuckDBPyConnection) -> None:
    conn.execute(DEDUP_LINKAGE_DDL)


def upsert_dedup_linkage(
    conn: duckdb.DuckDBPyConnection,
    survivor: DedupRecord,
    alternates: list[DedupRecord],
    *,
    category: Optional[str] = None,
    window_rule: Optional[str] = None,
) -> dict[str, Any]:
    """Insert or update the Linkage row for one cluster.

    Returns ``{"action": "created" | "noop" | "overwritten", "dedup_id":
    ..., "resource": ...}`` — same contract as the matching writer: an
    identical stored resource is a no-op; any change (corpus drift) is an
    overwrite, keeping decision history in the audit table.
    """
    create_dedup_linkage_table(conn)
    dedup_id = survivor_dedup_id([survivor] + list(alternates))
    category = category or survivor.category
    window_rule = window_rule or infer_window_rule([survivor] +
                                                   list(alternates))
    resource = build_linkage_resource(dedup_id, survivor,
                                      sorted(alternates, key=lambda m: m.rid),
                                      category, window_rule)
    existing = conn.execute(
        "SELECT resource FROM dedup_linkage WHERE dedup_id = ?", [dedup_id]
    ).fetchone()
    if existing is not None:
        if json.loads(existing[0]) == resource:
            return {"action": "noop", "dedup_id": dedup_id,
                    "resource": resource}
        action = "overwritten"
    else:
        action = "created"
    conn.execute(
        "INSERT OR REPLACE INTO dedup_linkage VALUES (?, ?, ?, ?)",
        [dedup_id, json.dumps(resource, sort_keys=True), category,
         1 + len(alternates)],
    )
    return {"action": action, "dedup_id": dedup_id, "resource": resource}


def delete_linkage(conn: duckdb.DuckDBPyConnection,
                   dedup_id: Optional[str] = None) -> int:
    """Delete one Linkage row (or ALL rows when ``dedup_id`` is None).

    Revert semantics (design §2d): deleting the cluster's Linkage fully
    reverts the merge decision — source resources were never touched.
    Returns rows deleted.
    """
    create_dedup_linkage_table(conn)
    if dedup_id is None:
        count = conn.execute(
            "SELECT count(*) FROM dedup_linkage").fetchone()[0]
        conn.execute("DELETE FROM dedup_linkage")
        return int(count)
    row = conn.execute(
        "SELECT count(*) FROM dedup_linkage WHERE dedup_id = ?",
        [dedup_id]).fetchone()[0]
    conn.execute("DELETE FROM dedup_linkage WHERE dedup_id = ?", [dedup_id])
    return int(row)


def load_dedup_linkage_resources(
    conn: duckdb.DuckDBPyConnection,
) -> list[dict[str, Any]]:
    """All stored dedup Linkage resources, ordered by dedup_id."""
    rows = conn.execute(
        "SELECT resource FROM dedup_linkage ORDER BY dedup_id"
    ).fetchall()
    return [json.loads(r[0]) for r in rows]
