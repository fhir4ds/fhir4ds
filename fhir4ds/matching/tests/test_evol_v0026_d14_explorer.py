"""D14 EXPLORER (v0.0.26) — adversarial fuzz regressions.

QA-D14E-001: EMBED/fuzzy evidence values containing the evidence-format
separators (``|`` / ``~``) — reachable only through the public
``match_fields`` field-map surface, since ``norm_text`` strips both
characters for every extractor-produced value — broke
``linkage._canonical_evidence`` two ways:

* query-side ``|`` (``'john~jo|hn|band=...'``): ``value.partition('|')``
  split the NAME pair, then ``name_part.split('~', 1)`` unpacked a
  1-element list -> raw ``ValueError: not enough values to unpack`` from
  the public match path (extractor-bypass field map);
* candidate-side ``|``: the stray name token migrated into the
  annotation zone of the CANONICAL evidence stored in the Linkage
  artifact (silently corrupted, parse-ambiguous bytes).
"""
from __future__ import annotations

import duckdb
import pytest

from fhir4ds.matching import corpus as m_corpus
from fhir4ds.matching import engine as m_engine
from fhir4ds.matching import linkage as m_linkage
from fhir4ds.matching import store as m_store
from fhir4ds.matching.rules import BAND_U_VALUES, EMBED, EXACT, MatchRule


PIPE_RULE = MatchRule(
    rule_id="X1",
    fields=(("first", EMBED), ("last", EXACT), ("dob", EXACT), ("street_line", EXACT)),
    p_collision=1e-13,
    p_collision_fuzzy=1e-11,
    p_fuzzy_fields=frozenset(),
    band_u_values=BAND_U_VALUES,
)


def _pipe_conn(indexed_first: str) -> duckdb.DuckDBPyConnection:
    conn = duckdb.connect()
    m_store.create_matching_tables(conn)
    m_linkage.create_linkage_tables(conn)
    conn.execute(
        "INSERT INTO field_values VALUES "
        f"('c1', 'first', '{indexed_first}', 'Patient'), "
        "('c1', 'last', 'ng', 'Patient'), "
        "('c1', 'dob', '1990-01-01', 'Patient'), "
        "('c1', 'street_line', '1 main st', 'Patient')"
    )
    return conn


BASE_FIELDS = {"last": ["ng"], "dob": ["1990-01-01"], "street_line": ["1 main st"]}


class TestCanonicalEvidenceSeparatorRobustnessD14Explorer:
    """QA-D14E-001 — ``|``/``~`` inside evidence values must not crash or
    corrupt the canonical Linkage evidence."""

    def test_query_side_pipe_does_not_crash_canonicalization(self) -> None:
        # Pre-fix: ValueError("not enough values to unpack (expected 2, got 1)")
        canon = m_linkage._canonical_evidence(
            {"first": "jo|hn~john|band=tight|model=name-embed-v1@860f1f59"}
        )
        assert "jo|hn" in canon["first"]
        assert canon["first"].endswith("|band=tight|model=name-embed-v1@860f1f59")

    def test_candidate_side_pipe_keeps_name_pair_intact(self) -> None:
        # Pre-fix: 'john~jo|hn|band=...' -> 'jo~john|hn|band=...' (the 'hn'
        # token migrated into the annotation zone).
        canon = m_linkage._canonical_evidence(
            {"first": "john~jo|hn|band=tight|model=name-embed-v1@860f1f59"}
        )
        name_part = canon["first"].split("|band=")[0]
        assert sorted(name_part.split("~", 1)) == sorted(["john", "jo|hn"])

    def test_canonicalization_is_direction_independent_with_pipes(self) -> None:
        a = m_linkage._canonical_evidence(
            {"first": "jo|hn~john|band=tight|model=m"}
        )["first"]
        b = m_linkage._canonical_evidence(
            {"first": "john~jo|hn|band=tight|model=m"}
        )["first"]
        assert a == b

    def test_canonicalization_direction_independent_double_separator(self) -> None:
        # A value containing BOTH separators makes the '~' split point
        # ambiguous; the canonical form must still not depend on which
        # side was the query.
        a = m_linkage._canonical_evidence({"first": "jo~|hn~john|band=tight"})["first"]
        b = m_linkage._canonical_evidence({"first": "john~jo~|hn|band=tight"})["first"]
        assert a == b

    def test_normal_evidence_bytes_unchanged(self) -> None:
        # Control: separator-free values canonicalize exactly as before
        # (golden/ONC byte-stability).
        assert m_linkage._canonical_evidence(
            {"first": "rick~nick|band=mid|model=m"}
        ) == {"first": "nick~rick|band=mid|model=m"}
        assert m_linkage._canonical_evidence({"dob": "1990-01-01"}) == {
            "dob": "1990-01-01"
        }

    def test_end_to_end_match_fields_pipe_query_no_raw_crash(self) -> None:
        conn = _pipe_conn("john")
        res = m_engine.match_fields(
            conn, {"first": ["jo|hn"], **BASE_FIELDS}, rules=[PIPE_RULE]
        )
        if res.outcome == "match":
            action = m_corpus.upsert_linkage(conn, res, "q1", "c1")
            assert action["action"] in ("created", "noop")

    def test_end_to_end_match_fields_pipe_candidate_no_corrupted_evidence(
        self,
    ) -> None:
        conn = _pipe_conn("jo|hn")
        res = m_engine.match_fields(
            conn, {"first": ["john"], **BASE_FIELDS}, rules=[PIPE_RULE]
        )
        if res.outcome == "match":
            m_corpus.upsert_linkage(conn, res, "q1", "c1")
            (resource,) = conn.execute(
                "SELECT resource FROM linkage WHERE linkage_id LIKE '%q1%'"
            ).fetchone() or (None,)
            if resource is not None:
                import json

                ev = json.loads(resource)["extension"][0]["extension"]
                first = next(
                    e["valueString"]
                    for e in next(x for x in ev if x["url"] == "evidence")["extension"]
                    if e["url"] == "first"
                )
                name_part = first.split("|band=")[0]
                assert sorted(name_part.split("~", 1)) == sorted(["john", "jo|hn"])


if __name__ == "__main__":  # pragma: no cover
    pytest.main([__file__, "-v"])
