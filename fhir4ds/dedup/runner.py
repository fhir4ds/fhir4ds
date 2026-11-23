"""AMUX-142 slice 3 — the end-to-end temporal dedup run.

``run_dedup`` composes the slice-1/2 pipeline (normalize → partition →
escalate) with slice-3 survivorship, Linkage materialization, and audit:

    dedup_pass → per cluster: select_survivor → merge_resources
                            → upsert_dedup_linkage → record_dedup_audit

Source resources are NEVER mutated (design §2d); survivors are NEW
resources with deterministic ids, and every artifact is a pure function of
the resource SET — two runs over shuffled inputs produce byte-identical
survivor JSONs, Linkage rows, and audit contents.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import duckdb

from .audit import record_dedup_audit
from .linkage import infer_window_rule, upsert_dedup_linkage
from .pipeline import DEFAULT_TZ, DedupRecord, dedup_pass
from .survivorship import (
    merge_resources,
    select_survivor,
    survivor_dedup_id,
    survivor_ranking_key,
    survivor_rule_tuple,
)

__all__ = ["DedupRunResult", "run_dedup"]


@dataclass
class DedupRunResult:
    """Outcome of one full dedup run."""

    run_id: str
    survivors: list[dict] = field(default_factory=list)
    linkage_resources: list[dict] = field(default_factory=list)
    stats: dict = field(default_factory=dict)
    curation_queue_path: Optional[str] = None

    @property
    def dedup_ids(self) -> list[str]:
        return [s["id"] for s in self.survivors]


def _cluster_evidence(cluster: list[DedupRecord],
                      survivor: DedupRecord,
                      edges: Optional[list] = None) -> dict:
    evidence = {
        "members": [
            {
                "reference": f"{m.rtype}/{m.rid}",
                "signature": (m.nd.signature if m.nd is not None
                              else None),
                "rankingKey": list(survivor_ranking_key(m)),
            }
            for m in sorted(cluster, key=lambda m: m.rid)
        ],
        "survivor": f"{survivor.rtype}/{survivor.rid}",
    }
    if edges:
        evidence["codeEdges"] = edges
        non_canonical = [e for e in edges if e.get("tier") != "canonical"]
        if non_canonical:
            lead = non_canonical[0]
            evidence["codeProvenance"] = f"{lead['tier']}:{lead['subtype']}"
            hybrid_edges = [e for e in non_canonical
                            if e.get("tier") == "hybrid"]
            if hybrid_edges:
                evidence["conceptIndex"] = {
                    "version": hybrid_edges[0].get("index_version"),
                    "resolutions": [
                        {"edge": e["edge"],
                         "concept": e.get("resolved_concept"),
                         "score": e.get("score"),
                         "margin": e.get("margin"),
                         "resolved_by": e.get("resolved_by")}
                        for e in hybrid_edges],
                }
        else:
            evidence["codeProvenance"] = "canonical"
    return evidence


def run_dedup(
    resources: list[dict],
    run_id: str,
    *,
    conn: Optional[duckdb.DuckDBPyConnection] = None,
    include_singletons_in_audit: bool = False,
    default_tz: str = DEFAULT_TZ,
    code_fallback: str = "on",
    concept_index=None,
    medication_resolver=None,
    output_dir: Optional[str] = None,
    dedup_proposer=None,
) -> DedupRunResult:
    """Run the full temporal dedup pass over ``resources``.

    - ``run_id``: caller-supplied audit run identifier (no wall-clock).
    - ``conn``: optional DuckDB connection (tables ``dedup_linkage`` and
      ``dedup_audit`` are created idempotently); a fresh in-memory
      connection is used when omitted.
    - ``include_singletons_in_audit``: also write one audit row per
      non-duplicate record (rule ``SINGLETON``, ``dedup_id`` NULL).
    - ``code_fallback`` (AMUX-145): ``"on"`` (default) | ``"audit_only"``
      | ``"off"`` — see :func:`fhir4ds.dedup.dedup_pass`.
    - ``concept_index``: optional concept display index for the tier-2
      hybrid resolution (default: the versioned in-repo index).
    - ``medication_resolver`` (AMUX-150): optional bounded medication
      reference resolver; ``None`` lazily builds the same-corpus index.
    - ``output_dir``: when given, the deterministic tier-3 curation
      queue is written to ``<output_dir>/dedup_curation_queue.jsonl``.
    - ``dedup_proposer``: optional
      :class:`~fhir4ds.dedup.curation.DedupCodeProposer` (default-off);
      may only APPEND proposal entries to the queue — it can never
      affect merge decisions.

    Returns survivors (sorted by survivor id), Linkage resources (sorted
    by dedup id), and stats. Idempotent: re-running on the same corpus
    upserts identical rows (no-op).
    """
    if not isinstance(run_id, str) or not run_id:
        raise ValueError("run_id must be a non-empty string")
    own_connection = conn is None
    if own_connection:
        conn = duckdb.connect()
    else:
        from ._conn import require_open_connection

        require_open_connection(conn, "run dedup")

    result = dedup_pass(resources, default_tz=default_tz,
                        code_fallback=code_fallback,
                        concept_index=concept_index,
                        medication_resolver=medication_resolver)
    survivors: list[dict] = []
    linkage_resources: list[dict] = []
    try:
        for cluster, edges in zip(result.clusters, result.cluster_edges):
            survivor = select_survivor(cluster)
            merged = merge_resources(cluster, survivor)
            dedup_id = survivor_dedup_id(cluster)
            alternates = [m for m in cluster if m.rid != survivor.rid]
            rule = infer_window_rule(cluster)
            non_canonical = [e for e in edges if e.get("tier") != "canonical"]
            if non_canonical:
                lead = non_canonical[0]
                rule = (f"{rule}|{lead['tier'].upper()}:"
                        f"{lead['subtype']}")
            upsert = upsert_dedup_linkage(
                conn, survivor, alternates,
                category=survivor.category,
                window_rule=rule,
            )
            record_dedup_audit(
                conn,
                run_id,
                dedup_id,
                survivor.category,
                len(cluster),
                survivor.rid,
                rule,
                # L4 fix (v0.0.25 D15): the audit docstring (and slice-3
                # tests) define rule_json as the serialized SURVIVORSHIP
                # ranking tuple [signature, richness, rid] — timestamp-free
                # per the determinism doctrine. This was previously fed the
                # internal survivor_ranking_key, whose second element
                # embeds the authored timestamp; a doc/behavior mismatch.
                survivor_rule_tuple(survivor),
                _cluster_evidence(cluster, survivor, edges),
            )
            survivors.append(merged)
            linkage_resources.append(upsert["resource"])
        if include_singletons_in_audit:
            from .audit import record_dedup_audit as _record
            for record in result.emitted:
                _record(
                    conn,
                    run_id,
                    None,
                    record.category,
                    1,
                    record.rid,
                    "SINGLETON",
                    ["SINGLETON", None, record.rid],
                    {"members": [
                        {"reference": f"{record.rtype}/{record.rid}",
                         "signature": (record.nd.signature
                                       if record.nd is not None else None),
                         "rankingKey": None}],
                     "survivor": f"{record.rtype}/{record.rid}"},
                )
    finally:
        if own_connection:
            conn.close()

    queue_path = None
    if output_dir is not None:
        from .curation import CURATION_QUEUE_FILENAME, write_curation_queue
        entries = [dict(entry, run_id=run_id)
                   for entry in result.curation_records]
        if dedup_proposer is not None:
            proposals = list(dedup_proposer.propose(result.records))
            entries.extend(
                dict(proposal, kind="proposal",
                     proposer=f"{type(dedup_proposer).__name__}"
                              f"@{dedup_proposer.version}")
                for proposal in proposals)
        from pathlib import Path as _Path
        written = write_curation_queue(
            _Path(output_dir) / CURATION_QUEUE_FILENAME, entries)
        queue_path = str(written)

    survivors.sort(key=lambda s: s["id"])
    linkage_resources.sort(key=lambda r: r["id"])
    stats = dict(result.stats)
    stats.update({
        "run_id": run_id,
        "survivors": len(survivors),
        "linkage_resources": len(linkage_resources),
        "audit_rows": (len(result.clusters)
                       + (len(result.emitted)
                          if include_singletons_in_audit else 0)),
    })
    return DedupRunResult(run_id=run_id, survivors=survivors,
                          linkage_resources=linkage_resources, stats=stats,
                          curation_queue_path=queue_path)
