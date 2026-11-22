"""Corpus pass + individual membership (AMUX-134 slice 4).

Stage 1 of the design doc §3 linkage graph: after every patient is
indexed, ``match_corpus`` evaluates each patient against the whole corpus
(self excluded) in sorted-id order, records one audit row set per
decision, and upserts Linkage resources for approved matches. Match
pairs are collected as canonical sorted pairs and deduplicated, so a
pair A~B discovered from either direction lands on exactly one Linkage
row (the slice-3 upsert key makes the second write a no-op).

``build_membership`` then computes connected components over the linkage
pairs (union-find, edges iterated in sorted linkage-key order) and writes
``patient_membership(member_patient_id, individual_id)`` with the
lexicographically smallest member id as the component's individual id.
Patients not in any linkage get identity rows so downstream joins are
uniform. ``veto_pairs`` excludes operator-supplied edges from the union
(hard-contradiction split path — v1 surfaces contradictions via
``find_contradictions`` but never auto-splits).

Determinism doctrine: no wall-clock timestamps, sorted iteration
everywhere; the same patient SET yields byte-identical membership rows
regardless of insertion order.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Iterable, Optional

import duckdb

from .audit import record_match_audit
from .fuzzy import dob_fuzzy_matches
from .linkage import create_linkage_tables, upsert_linkage
from .rules import CATEGORY1_RULES
from .store import create_matching_tables
from ._conn import require_open_connection

__all__ = [
    "MEMBERSHIP_DDL",
    "CorpusReport",
    "match_corpus",
    "build_membership",
    "individual_context_patients",
    "find_contradictions",
    "individual_patients_view",
]

MEMBERSHIP_DDL = """
CREATE TABLE IF NOT EXISTS patient_membership (
    member_patient_id VARCHAR PRIMARY KEY,
    individual_id VARCHAR NOT NULL
)
"""

_INDIVIDUAL_PATIENTS_VIEW_DDL = """
CREATE OR REPLACE VIEW _individual_patients AS
SELECT individual_id AS patient_id
FROM patient_membership
GROUP BY individual_id
"""

_INDIVIDUAL_RESOURCE_MAP_VIEW_DDL = """
CREATE OR REPLACE VIEW _individual_resource_map AS
SELECT member_patient_id, individual_id FROM patient_membership
"""


@dataclass
class CorpusReport:
    patients_evaluated: int = 0
    match_outcomes: int = 0
    ambiguous_outcomes: int = 0
    no_match_outcomes: int = 0
    unique_pairs: int = 0
    links_created: int = 0

    @property
    def counts(self) -> dict[str, int]:
        return asdict(self)


# ---------------------------------------------------------------------------
# Corpus matching pass
# ---------------------------------------------------------------------------


def _indexed_patient_ids(conn: duckdb.DuckDBPyConnection,
                         entity_type: str = "Patient") -> list[str]:
    rows = conn.execute(
        "SELECT DISTINCT patient_id FROM field_values WHERE entity_type = ? "
        "ORDER BY patient_id",
        [entity_type],
    ).fetchall()
    return [r[0] for r in rows]


def _indexed_fields(
    conn: duckdb.DuckDBPyConnection, patient_id: str,
    entity_type: str = "Patient",
) -> dict[str, list[str]]:
    rows = conn.execute(
        "SELECT field_name, value FROM field_values "
        "WHERE entity_type = ? AND patient_id = ? "
        "ORDER BY field_name, value",
        [entity_type, patient_id],
    ).fetchall()
    fields: dict[str, list[str]] = {}
    for field_name, value in rows:
        fields.setdefault(field_name, []).append(value)
    return fields


def match_corpus(
    conn: duckdb.DuckDBPyConnection, run_id: str, *,
    rules: list = CATEGORY1_RULES,
    entity_type: str = "Patient",
) -> CorpusReport:
    """Evaluate every indexed entity against the full corpus (self excluded).

    Entities are visited in sorted-id order; each decision is audited under
    ``run_id`` and every ``match`` outcome upserts one Linkage per matched
    pair. Because the engine sees the complete corpus on every pass, the
    decision set depends only on the entity SET (determinism doctrine,
    design doc §4) — re-running over an unchanged corpus audits again but
    creates no new Linkage rows.

    AMUX-150: ``rules`` + ``entity_type`` parameterize the pass (defaults
    reproduce Patient corpus matching byte-for-byte).
    """
    from .engine import match_fields
    from .rules import MatchRule  # noqa: F401  (type documentation)

    if not isinstance(run_id, str) or not run_id:
        raise ValueError("run_id must be a non-empty string")
    create_matching_tables(conn)
    create_linkage_tables(conn)
    report = CorpusReport()
    pairs: set[tuple[str, str]] = set()
    for patient_id in _indexed_patient_ids(conn, entity_type):
        fields = _indexed_fields(conn, patient_id, entity_type)
        result = match_fields(conn, fields,
                              exclude=frozenset({patient_id}),
                              rules=rules, entity_type=entity_type)
        record_match_audit(conn, run_id, patient_id, result)
        report.patients_evaluated += 1
        if result.outcome == "match":
            report.match_outcomes += 1
        elif result.outcome == "ambiguous":
            report.ambiguous_outcomes += 1
        else:
            report.no_match_outcomes += 1
        if result.outcome != "match":
            continue
        for candidate_id in result.matched_ids:
            pair = tuple(sorted((patient_id, candidate_id)))
            pairs.add(pair)
            outcome = upsert_linkage(conn, result, patient_id, candidate_id,
                                     entity_type=entity_type)
            if outcome["action"] == "created":
                report.links_created += 1
    report.unique_pairs = len(pairs)
    return report


# ---------------------------------------------------------------------------
# Connected components / membership
# ---------------------------------------------------------------------------


def _normalize_member_ref(ref: str) -> str:
    return ref[len("Patient/") :] if ref.startswith("Patient/") else ref


def _linkage_edges(
    conn: duckdb.DuckDBPyConnection
) -> list[tuple[str, str]]:
    """Sorted (a, b) member-id edges from the linkage table."""
    rows = conn.execute("SELECT linkage_id FROM linkage ORDER BY linkage_id").fetchall()
    edges = []
    for (linkage_id,) in rows:
        left, right = linkage_id.split("|", 1)
        edges.append(
            tuple(sorted((_normalize_member_ref(left), _normalize_member_ref(right))))
        )
    return edges


def _veto_set(
    veto_pairs: Iterable[Iterable[str]],
) -> frozenset[tuple[str, str]]:
    vetoes = set()
    for pair in veto_pairs:
        a, b = tuple(pair)
        vetoes.add(tuple(sorted((_normalize_member_ref(str(a)), _normalize_member_ref(str(b))))))
    return frozenset(vetoes)


def _components(
    members: list[str], edges: list[tuple[str, str]], vetoes: frozenset[tuple[str, str]]
) -> dict[str, str]:
    """Union-find over the (non-vetoed) edges; member -> component id.

    The component id is the lexicographically smallest member id
    (deterministic tie-break, design doc §5).
    """
    parent: dict[str, str] = {m: m for m in members}

    def find(x: str) -> str:
        root = x
        while parent[root] != root:
            root = parent[root]
        while parent[x] != root:  # path compression
            parent[x], x = root, parent[x]
        return root

    for a, b in edges:
        if a not in parent or b not in parent:
            continue  # edge references an unindexed patient
        if (a, b) in vetoes:
            continue
        ra, rb = find(a), find(b)
        if ra != rb:
            # Union by smaller id so the root IS the component label.
            if ra < rb:
                parent[rb] = ra
            else:
                parent[ra] = rb
    return {m: find(m) for m in members}


def build_membership(
    conn: duckdb.DuckDBPyConnection,
    veto_pairs: Iterable[Iterable[str]] = (),
) -> int:
    """(Re)build ``patient_membership`` from the current linkage pairs.

    Every indexed patient gets exactly one row; unlinked patients get
    identity rows. ``veto_pairs`` names linkage edges (patient ids or
    ``Patient/<id>`` refs) to EXCLUDE from the union-find — the operator
    path for hard-contradiction splits. Returns the component count.
    """
    create_matching_tables(conn)
    create_linkage_tables(conn)
    members = _indexed_patient_ids(conn)
    edges = _linkage_edges(conn)
    roots = _components(members, edges, _veto_set(veto_pairs))
    conn.execute(MEMBERSHIP_DDL)
    conn.execute("DELETE FROM patient_membership")
    rows = [(m, roots[m]) for m in members]  # members sorted -> deterministic order
    if rows:
        conn.executemany("INSERT INTO patient_membership VALUES (?, ?)", rows)
    return len(set(roots.values()))


def individual_context_patients(
    conn: duckdb.DuckDBPyConnection,
) -> list[tuple[str, int]]:
    """``[(individual_id, member_count)]`` sorted by individual_id.

    Requires ``build_membership`` to have run (the membership table must
    exist and be populated).
    """
    require_open_connection(conn, "list individual context patients")
    rows = conn.execute(
        "SELECT individual_id, COUNT(*) AS member_count FROM patient_membership "
        "GROUP BY individual_id ORDER BY individual_id"
    ).fetchall()
    return [(r[0], int(r[1])) for r in rows]


# ---------------------------------------------------------------------------
# Stage 2 (consistency): hard-contradiction surfacing — v1 NEVER auto-splits
# ---------------------------------------------------------------------------


def _component_field_sets(
    conn: duckdb.DuckDBPyConnection, component_members: list[str]
) -> dict[str, dict[str, set[str]]]:
    sets: dict[str, dict[str, set[str]]] = {m: {} for m in component_members}
    member_in = ", ".join("?" for _ in component_members)
    rows = conn.execute(
        f"SELECT patient_id, field_name, value FROM field_values "
        f"WHERE field_name IN ('ssn4', 'dob', 'suffix') AND patient_id IN ({member_in}) "
        f"ORDER BY patient_id, field_name, value",
        component_members,
    ).fetchall()
    for patient_id, field_name, value in rows:
        sets[patient_id].setdefault(field_name, set()).add(value)
    return sets


def _pair_contradictions(
    a: str, b: str, a_sets: dict[str, set[str]], b_sets: dict[str, set[str]]
) -> list[dict]:
    """Hard contradictions between two members (design doc §3 stage 2)."""
    found: list[dict] = []
    for field_name, kind in (
        ("ssn4", "disjoint_values"),
        ("suffix", "disjoint_values"),
    ):
        a_values, b_values = a_sets.get(field_name), b_sets.get(field_name)
        if a_values and b_values and a_values.isdisjoint(b_values):
            found.append(
                {
                    "field": field_name,
                    "kind": kind,
                    "members": [a, b],
                    "values": {a: sorted(a_values), b: sorted(b_values)},
                }
            )
    a_dobs, b_dobs = a_sets.get("dob"), b_sets.get("dob")
    if a_dobs and b_dobs:
        if not any(
            dob_fuzzy_matches(x, y) for x in a_dobs for y in b_dobs
        ):
            found.append(
                {
                    "field": "dob",
                    "kind": "no_cross_pair_equal_or_within_1_day",
                    "members": [a, b],
                    "values": {a: sorted(a_dobs), b: sorted(b_dobs)},
                }
            )
    return found


def find_contradictions(
    conn: duckdb.DuckDBPyConnection,
    veto_pairs: Iterable[Iterable[str]] = (),
) -> list[dict]:
    """Hard-contradiction evidence per multi-member component.

    Checks only the three HARD contradiction classes (design doc §3):
    disjoint non-null SSN-last-4 sets, DOB sets with NO cross pair equal
    or within +/-1 day, and disjoint non-empty suffix sets. Soft signals
    (e.g. disjoint addresses) are deliberately NOT surfaced here.

    v1 is conservative: contradictions are RETURNED for operator review —
    no component is split automatically. The operator path is
    ``build_membership(conn, veto_pairs=[...])`` with the offending pairs.
    """
    create_matching_tables(conn)
    create_linkage_tables(conn)
    members = _indexed_patient_ids(conn)
    edges = _linkage_edges(conn)
    roots = _components(members, edges, _veto_set(veto_pairs))
    by_root: dict[str, list[str]] = {}
    for m in members:
        by_root.setdefault(roots[m], []).append(m)

    results: list[dict] = []
    for root in sorted(by_root):
        component = by_root[root]
        if len(component) < 2:
            continue
        field_sets = _component_field_sets(conn, component)
        contradictions: list[dict] = []
        for i in range(len(component)):
            for j in range(i + 1, len(component)):
                a, b = component[i], component[j]
                contradictions.extend(
                    _pair_contradictions(a, b, field_sets[a], field_sets[b])
                )
        if contradictions:
            results.append(
                {
                    "individual_id": root,
                    "members": component,
                    "contradictions": contradictions,
                }
            )
    return results


# ---------------------------------------------------------------------------
# §5 substrate: individual-context views (CQL translator swap is a LATER slice)
# ---------------------------------------------------------------------------


def individual_patients_view(conn: duckdb.DuckDBPyConnection) -> None:
    """Create the individual-context views over ``patient_membership``.

    - ``_individual_patients`` — one row per individual (``individual_id
      AS patient_id``): the §5 ``_patients`` substrate.
    - ``_individual_resource_map`` — member -> individual for retrieve
      correlation.

    The CQL ``_patients`` swap itself is a later gated slice; this only
    provides the SQL substrate.
    """
    require_open_connection(conn, "create individual patients view")
    conn.execute(MEMBERSHIP_DDL)
    conn.execute(_INDIVIDUAL_PATIENTS_VIEW_DDL)
    conn.execute(_INDIVIDUAL_RESOURCE_MAP_VIEW_DDL)
