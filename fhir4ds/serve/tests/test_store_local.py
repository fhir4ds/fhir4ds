"""``LocalDirStore``: append → commit → read back, and the persisted sequence.

These are the sequencing tests the phase-3 brief asks for first: ``_seq`` must
be monotonic across commits *and across process restarts*, and a part must
never be rewritten.
"""

from __future__ import annotations

import json

import duckdb

from fhir4ds.serve.store import STATE_PATH, LocalDirStore


def row(resource_id: str, seq: int, *, deleted: bool = False) -> dict:
    return {
        "id": resource_id,
        "resourceType": "Observation",
        "resource": json.dumps({"resourceType": "Observation", "id": resource_id}),
        "patient_ref": "p1",
        "_seq": seq,
        "_deleted": deleted,
        "_ingested_at": "2026-10-31T00:00:00Z",
    }


def read_parts(root) -> list[dict]:
    query = f"SELECT id, _seq, _deleted FROM read_parquet('{root}/resources/**/*.parquet') ORDER BY _seq"
    return duckdb.connect().execute(query).fetchall()


def test_append_commit_and_read_back(tmp_path):
    store = LocalDirStore(tmp_path)
    store.append([row("o1", 1), row("o2", 2)])

    revision = store.commit()

    assert revision and len(revision) == 12
    assert store.revision() == revision
    assert store.current_seq() == 2
    assert read_parts(tmp_path) == [("o1", 1, False), ("o2", 2, False)]

    state = json.loads((tmp_path / STATE_PATH).read_text())
    assert state == {"seq": 2, "revision": revision}


def test_parts_are_append_only(tmp_path):
    store = LocalDirStore(tmp_path)
    store.append([row("o1", 1)])
    store.commit()
    first = sorted((tmp_path / "resources").rglob("*.parquet"))
    assert len(first) == 1

    store.append([row("o1", 2)])
    store.commit()
    parts = sorted((tmp_path / "resources").rglob("*.parquet"))

    assert len(parts) == 2, "a new version must be a new part, never a rewrite"
    assert parts[0] == first[0]
    assert read_parts(tmp_path) == [("o1", 1, False), ("o1", 2, False)]


def test_sequence_survives_a_restart(tmp_path):
    store = LocalDirStore(tmp_path)
    store.append([row("o1", 1), row("o1", 2)])
    store.commit()

    restarted = LocalDirStore(tmp_path)
    assert restarted.current_seq() == 2
    assert restarted.revision() == store.revision()

    restarted.append([row("o1", 3)])
    restarted.commit()
    assert restarted.current_seq() == 3
    assert [entry[1] for entry in read_parts(tmp_path)] == [1, 2, 3]


def test_a_crashed_buffer_leaves_a_gap_and_never_reuses_a_value(tmp_path):
    """Rows buffered but never committed must not hand their seq to a new row."""
    store = LocalDirStore(tmp_path)
    store.append([row("o1", 7)])  # buffered, then "crash" (no commit)

    fresh = LocalDirStore(tmp_path)
    # The uncommitted seq is gone: the writer continues from the persisted state.
    assert fresh.current_seq() == 0

    fresh.append([row("o2", 8)])
    fresh.commit()
    assert fresh.current_seq() == 8
    assert [entry[1] for entry in read_parts(tmp_path)] == [8]


def test_commit_without_rows_keeps_the_state(tmp_path):
    store = LocalDirStore(tmp_path)
    store.append([row("o1", 5)])
    store.commit()

    revision = store.commit()
    assert store.current_seq() == 5
    assert store.revision() == revision
    assert read_parts(tmp_path) == [("o1", 5, False)]


def test_staged_files_are_tracked_as_dirty(tmp_path):
    store = LocalDirStore(tmp_path)
    store.stage_file("$bulk-publish", '{"resourceType": "Parameters"}')
    store.stage_file("README.md", "# dataset")

    assert store.dirty_paths() == {"$bulk-publish", "README.md"}
    assert (tmp_path / "$bulk-publish").read_text() == '{"resourceType": "Parameters"}'

    store.clear_dirty()
    assert store.dirty_paths() == set()


def test_append_requires_a_writer_assigned_seq(tmp_path):
    store = LocalDirStore(tmp_path)
    try:
        store.append([{"id": "o1", "resourceType": "Observation"}])
    except ValueError as exc:
        assert "_seq" in str(exc)
    else:  # pragma: no cover - the assertion above is the test
        raise AssertionError("append must reject rows without _seq")
