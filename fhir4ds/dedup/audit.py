"""Temporal-dedup audit trail (AMUX-142 slice 3).

Mirrors :mod:`fhir4ds.matching.audit`'s doctrine: one row per DECISION,
no wall-clock timestamps anywhere — ordering comes from the caller-supplied
``run_id`` plus insertion sequence.

``dedup_audit`` carries one row per cluster survivorship decision
(``dedup_id``, category, member count, surviving rid, the serialized
ranking rule, and the full cluster evidence JSON). Singletons are NOT
clusters; the runner writes singleton rows only when the caller opts in
(``include_singletons_in_audit=True``) with ``dedup_id = NULL`` and
``rule = 'SINGLETON'``.
"""

from __future__ import annotations

import weakref

import json

import duckdb

__all__ = [
    "DEDUP_AUDIT_DDL",
    "create_dedup_audit_table",
    "record_dedup_audit",
    "load_dedup_audit",
]

DEDUP_AUDIT_DDL = """
CREATE TABLE IF NOT EXISTS dedup_audit (
    run_id VARCHAR NOT NULL,
    dedup_id VARCHAR,
    category VARCHAR NOT NULL,
    member_count INTEGER NOT NULL,
    survivor_rid VARCHAR NOT NULL,
    rule VARCHAR NOT NULL,
    rule_json JSON,
    cluster_evidence JSON
)
"""


# FHIR4-55: called once per CLUSTER (and once per singleton in audit mode), so
# the idempotent DDL was re-issued for every row written. Remember it per
# connection; see the same note in `linkage.create_dedup_linkage_table`.
_DDL_APPLIED: "weakref.WeakSet" = weakref.WeakSet()


def create_dedup_audit_table(conn: duckdb.DuckDBPyConnection) -> None:
    from ._conn import require_open_connection

    require_open_connection(conn, "create dedup audit table")
    if conn in _DDL_APPLIED:
        return
    conn.execute(DEDUP_AUDIT_DDL)
    _DDL_APPLIED.add(conn)


def record_dedup_audit(
    conn: duckdb.DuckDBPyConnection,
    run_id: str,
    dedup_id: str,
    category: str,
    member_count: int,
    survivor_rid: str,
    rule: str,
    rule_data: list,
    cluster_evidence: dict,
) -> None:
    """Write the audit row for one survivorship decision.

    ``rule_data`` is the serialized ranking tuple
    (:func:`survivorship.survivor_rule_tuple`); ``cluster_evidence`` is the
    per-member evidence (references + signatures + ranking keys).
    """
    params = audit_params(run_id, dedup_id, category, member_count,
                          survivor_rid, rule, rule_data, cluster_evidence)
    create_dedup_audit_table(conn)
    conn.execute(_AUDIT_INSERT, params)


#: One INSERT for every audit row; ``record_dedup_audit`` and
#: ``record_dedup_audit_many`` share it so the column order can never drift.
_AUDIT_INSERT = (
    "INSERT INTO dedup_audit (run_id, dedup_id, category, "
    "member_count, survivor_rid, rule, rule_json, cluster_evidence) "
    "VALUES (?, ?, ?, ?, ?, ?, ?, ?)"
)


def audit_params(run_id: str, dedup_id: Optional[str], category: str,
                 member_count: int, survivor_rid: str, rule: str,
                 rule_data: list, cluster_evidence: dict) -> list:
    """The bound-parameter list for one audit row (FHIR4-55).

    Split out so a caller that writes MANY rows can collect the parameters and
    issue one ``executemany`` instead of one round trip per cluster — fhir4px
    measured 900-6,280 small statements per run, and the audit INSERT was one
    of them.
    """
    if not isinstance(run_id, str) or not run_id:
        raise ValueError("run_id must be a non-empty string")
    return [
        run_id,
        dedup_id,
        category,
        member_count,
        survivor_rid,
        rule,
        json.dumps(rule_data, sort_keys=True),
        json.dumps(cluster_evidence, sort_keys=True),
    ]


def record_dedup_audit_many(conn: duckdb.DuckDBPyConnection,
                            rows: list[list]) -> None:
    """Write many audit rows in ONE statement (FHIR4-55).

    Order is irrelevant to the contract: ``load_dedup_audit`` orders by
    ``(dedup_id, survivor_rid)``, so the batch cannot change what a reader
    sees.
    """
    if not rows:
        return
    create_dedup_audit_table(conn)
    conn.executemany(_AUDIT_INSERT, rows)


def load_dedup_audit(conn: duckdb.DuckDBPyConnection,
                     run_id: str) -> list[dict]:
    """Audit rows for one run, ordered deterministically
    (dedup_id, survivor_rid).

    Returns ``[]`` when the run recorded no decisions — the tables are
    created lazily by the first write, so the loader ensures existence
    first (same create-first precedent as :func:`delete_linkage`)."""
    from ._conn import require_open_connection

    require_open_connection(conn, "load dedup audit")
    create_dedup_audit_table(conn)
    rows = conn.execute(
        "SELECT run_id, dedup_id, category, member_count, survivor_rid, "
        "rule, rule_json, cluster_evidence FROM dedup_audit "
        "WHERE run_id = ? ORDER BY dedup_id NULLS LAST, survivor_rid",
        [run_id],
    ).fetchall()
    return [
        {
            "run_id": r[0],
            "dedup_id": r[1],
            "category": r[2],
            "member_count": r[3],
            "survivor_rid": r[4],
            "rule": r[5],
            "rule_json": json.loads(r[6]) if r[6] else None,
            "cluster_evidence": json.loads(r[7]) if r[7] else None,
        }
        for r in rows
    ]
