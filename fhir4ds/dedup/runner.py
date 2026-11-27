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

import json

import duckdb

from .audit import audit_params, record_dedup_audit_many
from .linkage import (
    build_linkage_row,
    infer_window_rule,
    prefetch_linkage,
    write_linkage_many,
)
from .pipeline import DEFAULT_TZ, DedupRecord, dedup_pass
from .survivorship import (
    merge_resources,
    select_survivor,
    survivor_dedup_id,
    survivor_ranking_key,
    survivor_rule_tuple,
)

__all__ = ["DedupCancelled", "DedupRunResult", "run_dedup"]


class DedupCancelled(RuntimeError):
    """A deduplication run stopped because ``should_cancel()`` returned True.

    FHIR4-55: a caller that runs dedup in the background (the browser app runs
    it behind a request) needs to be able to stop it. Raising a TYPED error —
    rather than returning a partial result — keeps a cancelled run from ever
    being mistaken for a complete one: the audit rows written so far stay, and
    nothing after the cancellation point is written.
    """


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
    cross_bucket_near_misses: bool = True,
    cross_bucket_near_miss_limit: Optional[int] = None,
    progress=None,
    should_cancel=None,
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
    - ``cross_bucket_near_misses`` (FHIR4-55): the cross-bucket sweep is the
      quadratic stage and feeds ONLY the curation queue (it cannot change a
      merge decision). ``False`` skips it; clusters and survivors are
      identical either way.
    - ``cross_bucket_near_miss_limit`` (FHIR4-55): cap the sweep's OUTPUT.
      A shared-text group produces one curation entry per PAIR (400 records in
      one group -> ~78k entries), so both time and queue size are quadratic.
      The cap is deterministic: iteration is over sorted keys and rid-sorted
      groups, so a truncated run emits the same PREFIX a full run would, and
      ``stats["curation_near_miss_truncated"]`` says it was cut.
    - ``progress`` (FHIR4-55): optional ``callable(dict)`` invoked at each
      stage boundary with ``{"stage": str, "done": int, "total": int}``, so
      a background caller can render a bar. Never raises into the pipeline.
    - ``should_cancel`` (FHIR4-55): optional ``callable() -> bool`` polled at
      the same boundaries; when it returns True the run stops and raises
      :class:`DedupCancelled` (a ``RuntimeError``) BEFORE writing further
      audit rows, so a cancelled run never looks like a complete one.

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

    def _report(stage: str, done: int, total: int) -> None:
        if progress is not None:
            try:
                progress({"stage": stage, "done": done, "total": total})
            except Exception:  # noqa: BLE001 - a progress sink must not
                # abort a deduplication run; that would make observability a
                # correctness risk.
                pass
        if should_cancel is not None and should_cancel():
            raise DedupCancelled(
                f"deduplication cancelled during {stage!r} "
                f"({done}/{total}) — no further audit rows were written")

    _report("normalize+cluster", 0, len(resources))
    result = dedup_pass(resources, default_tz=default_tz,
                        code_fallback=code_fallback,
                        concept_index=concept_index,
                        medication_resolver=medication_resolver,
                        cross_bucket_near_misses=cross_bucket_near_misses,
                        cross_bucket_near_miss_limit=(
                            cross_bucket_near_miss_limit))
    _report("clustered", len(result.clusters), len(result.clusters))
    survivors: list[dict] = []
    linkage_resources: list[dict] = []
    # FHIR4-55: this loop used to issue ~4 small statements PER CLUSTER (DDL,
    # SELECT-exists, INSERT, audit INSERT). fhir4px measured 900-6,280 such
    # statements per run at ~0.6 ms each. Everything below is now derived
    # first and written in two batched statements; the per-cluster decisions
    # (created / noop / overwritten) and their ORDER are unchanged.
    plans: list[tuple] = []
    for cluster, edges in zip(result.clusters, result.cluster_edges):
        survivor = select_survivor(cluster)
        alternates = [m for m in cluster if m.rid != survivor.rid]
        rule = infer_window_rule(cluster)
        non_canonical = [e for e in edges if e.get("tier") != "canonical"]
        if non_canonical:
            lead = non_canonical[0]
            rule = (f"{rule}|{lead['tier'].upper()}:"
                    f"{lead['subtype']}")
        resource, params = build_linkage_row(
            survivor, alternates, category=survivor.category,
            window_rule=rule)
        plans.append((cluster, edges, survivor,
                      merge_resources(cluster, survivor), resource, params,
                      rule))
    existing = prefetch_linkage(conn, [plan[5][0] for plan in plans])
    audit_rows: list[list] = []
    try:
        writes: list[list] = []
        for cluster, edges, survivor, merged, resource, params, rule in plans:
            prior = existing.get(params[0])
            if prior is None:
                writes.append(params)          # created
            elif json.loads(prior) != resource:
                writes.append(params)          # overwritten (corpus drift)
            # identical stored resource -> noop: no write, same as before
            audit_rows.append(audit_params(
                run_id,
                params[0],
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
            ))
            survivors.append(merged)
            linkage_resources.append(resource)
        write_linkage_many(conn, writes)
        if include_singletons_in_audit:
            for record in result.emitted:
                audit_rows.append(audit_params(
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
                ))
        record_dedup_audit_many(conn, audit_rows)
    finally:
        if own_connection:
            conn.close()

    _report("linkage+audit", len(survivors), len(survivors))
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
