"""Run-history tests (parity item 2)."""

from __future__ import annotations

from pathlib import Path

import pytest

from ..runlog import RunLogStore


@pytest.fixture()
def store(tmp_path: Path) -> RunLogStore:
    return RunLogStore(tmp_path)


def test_record_and_load_newest_first(store: RunLogStore, tmp_path: Path) -> None:
    for i in range(3):
        store.record(
            kind="measure",
            target=f"M{i}",
            status="pass",
            duration_ms=10 + i,
            row_count=i,
            summary={"initial-population": i},
            library_text=f"library L{i}",
            sql_text=f"SELECT {i}",
            datasets=["data/p.ndjson"],
            patient_count=2,
        )
    events = store.load()
    assert [e["target"] for e in events] == ["M2", "M1", "M0"]
    assert events[0]["kind"] == "measure"
    assert events[0]["status"] == "pass"
    assert events[0]["summary"] == {"initial-population": 2}
    assert events[0]["library_sha"].startswith("sha256:")
    assert events[0]["sql_sha"].startswith("sha256:")
    assert events[0]["datasets"] == ["data/p.ndjson"]
    assert events[0]["patient_count"] == 2
    # no SQL bodies in the log
    log_text = (tmp_path / ".runlog.jsonl").read_text()
    assert "SELECT" not in log_text


def test_load_filters_kind_and_limit(store: RunLogStore) -> None:
    store.record(kind="cell", target="A/x", status="pass", duration_ms=1, row_count=0)
    store.record(kind="measure", target="M", status="pass", duration_ms=1, row_count=0)
    store.record(kind="cell", target="A/y", status="error", duration_ms=1, row_count=0, error="boom")
    assert [e["target"] for e in store.load(kind="cell")] == ["A/y", "A/x"]
    assert len(store.load(limit=1)) == 1


def test_corrupt_tail_skipped(store: RunLogStore, tmp_path: Path) -> None:
    store.record(kind="cell", target="ok", status="pass", duration_ms=1, row_count=0)
    with (tmp_path / ".runlog.jsonl").open("a") as fh:
        fh.write('{"trunc')
    events = store.load()
    assert len(events) == 1 and events[0]["target"] == "ok"


def test_cap_prunes_oldest_third(store: RunLogStore) -> None:
    for i in range(600):
        store.record(kind="cell", target=f"T{i}", status="pass", duration_ms=1, row_count=0)
    events = store.load(limit=1000)
    assert len(events) <= 500
    # oldest third gone: T0..~T199 absent, newest present
    targets = {e["target"] for e in events}
    assert "T0" not in targets
    assert "T599" in targets


def test_clear(store: RunLogStore) -> None:
    store.record(kind="cell", target="x", status="pass", duration_ms=1, row_count=0)
    store.clear()
    assert store.load() == []
