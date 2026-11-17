"""ONC labeled-pair loader tests (AMUX-134 prep — SKIP until the data is fetched).

Run ``python3 -m fhir4ds.matching.scripts.fetch_onc_test_data`` once to
populate ``fhir4ds/matching/tests/fixtures/onc/``; these tests then exercise
``load_onc_pairs`` end-to-end (shape validation + engine smoke over a small
slice). No gate is asserted yet — that is the next session's work.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from fhir4ds.matching import create_matching_tables, index_patient, match_patient
from fhir4ds.matching.scripts.fetch_onc_test_data import (
    DEFAULT_ARTIFACT,
    ONC_FIXTURE_DIR,
    load_onc_pairs,
)

_ONC_PATH = ONC_FIXTURE_DIR / DEFAULT_ARTIFACT

# Environment-availability skip (missing fetched fixture), per the test-skip
# policy: fixture data that is deliberately not committed.
pytestmark = pytest.mark.skipif(
    not _ONC_PATH.exists(),
    reason=f"ONC fixture not fetched — run "
    f"`python3 -m fhir4ds.matching.scripts.fetch_onc_test_data` to populate "
    f"{_ONC_PATH}",
)


def test_loader_end_to_end_when_fetched():
    import duckdb

    pairs = load_onc_pairs(_ONC_PATH)
    assert pairs, "fetched file must contain at least one pair"
    # shape contract from the upstream JSONL schema
    assert all(isinstance(p.expected_match, bool) for p in pairs)
    assert all(p.source.get("resourceType") == "Patient" for p in pairs)
    assert all(p.target.get("resourceType") == "Patient" for p in pairs)
    assert all(p.case_id for p in pairs)
    assert any(p.expected_match for p in pairs)
    assert any(not p.expected_match for p in pairs)
    # rationale taxonomy is populated upstream (fuzzy_variant/, near_miss/, ...)
    assert any(p.rationale for p in pairs)

    # engine smoke: a small deterministic slice runs both directions through
    # the real engine without crashing and yields decidable outcomes
    conn = duckdb.connect()
    create_matching_tables(conn)
    sample = pairs[:50]
    indexed_ids = set()
    for pair in sample:
        for resource in (pair.source, pair.target):
            if resource["id"] not in indexed_ids:
                index_patient(conn, resource)
                indexed_ids.add(resource["id"])
    outcomes = set()
    for pair in sample:
        for query, other in ((pair.source, pair.target), (pair.target, pair.source)):
            result = match_patient(conn, query, exclude=frozenset({other["id"]}))
            outcomes.add(result.outcome)
            assert result.outcome in {"match", "no_match", "ambiguous"}
    # the slice must actually exercise at least one linking decision
    assert "match" in outcomes or "ambiguous" in outcomes


def test_loader_rejects_malformed_file(tmp_path: Path):
    bad = tmp_path / "bad.jsonl"
    bad.write_text('{"case_id": "x", "source": {"resourceType": "Encounter"}, "target": {}, "expected_match": true}\n', encoding="utf-8")
    with pytest.raises(ValueError):
        load_onc_pairs(bad)

    empty = tmp_path / "empty.jsonl"
    empty.write_text("", encoding="utf-8")
    with pytest.raises(ValueError):
        load_onc_pairs(empty)
