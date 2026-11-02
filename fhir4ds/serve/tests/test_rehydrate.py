"""Boot-time rehydration: a restarted server recovers from its publish dataset.

The publish dataset is the durable copy (rows as parquet parts, served
definitions as JSON). These tests simulate a process restart by wiping the
in-memory log and registry while keeping ``--publish-dir``, then asserting the
fresh app serves exactly what the dataset holds: rows with their original
``_seq`` (``meta.versionId`` matches the published parts), tombstones, and the
registry definitions — and that ``--resources`` preloading does not fight the
restored state.
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from fhir4ds.serve.app import create_app
from fhir4ds.serve.config import ServeConfig
from fhir4ds.serve.store import REGISTRY_TABLE
from fhir4ds.serve.versioning import BASE_TABLE

SLOT = {
    "resourceType": "Slot",
    "id": "slot-1",
    "status": "free",
    "start": "2027-01-04T14:00:00.000Z",
    "end": "2027-01-04T15:00:00.000Z",
    "schedule": {"reference": "Schedule/10"},
}

VIEW = {
    "resourceType": "ViewDefinition",
    "id": "slots-view",
    "name": "slots_view",
    "resource": "Slot",
    "select": [
        {"column": [{"name": "id", "path": "id"}, {"name": "status", "path": "status"}]}
    ],
}


@pytest.fixture()
def connection():
    """A private DuckDB connection: these tests manage their own log state."""
    from fhir4ds.connection import create_connection

    con = create_connection(":memory:")
    yield con
    con.close()


def boot(connection, publish_dir) -> TestClient:
    """Create an app against this connection and the (surviving) publish dir."""
    app = create_app(
        ServeConfig(publish_dir=str(publish_dir), flush_autostart=False),
        connection=connection,
    )
    return TestClient(app)


def restart(connection, publish_dir) -> TestClient:
    """Simulate a process restart: wipe in-memory state, boot again."""
    connection.execute(f"DELETE FROM {BASE_TABLE}")
    connection.execute(f"DELETE FROM {REGISTRY_TABLE}")
    return boot(connection, publish_dir)


def log_row_count(connection) -> int:
    return connection.execute(f"SELECT count(*) FROM {BASE_TABLE}").fetchone()[0]


def test_restart_restores_rows_definitions_and_sequence(connection, tmp_path):
    first = boot(connection, tmp_path)
    created = first.post("/Slot", json=SLOT)
    assert created.status_code == 201, created.text
    assert created.json()["meta"]["versionId"] == "1"
    assert first.post("/ViewDefinition", json=VIEW).status_code in (200, 201)
    assert first.post("/admin/flush").status_code == 200

    second = restart(connection, tmp_path)

    # The posted Slot is served again with its ORIGINAL version id.
    read = second.get("/Slot/slot-1")
    assert read.status_code == 200, read.text
    assert read.json()["meta"]["versionId"] == "1"

    # The definition registry was rehydrated from viewdefinitions/*.json.
    served = second.get("/ViewDefinition/slots-view")
    assert served.status_code == 200, served.text

    # The sequence continues past the restored maximum.
    nxt = second.post("/Slot", json={**SLOT, "id": "slot-2"})
    assert nxt.status_code == 201, nxt.text
    assert nxt.json()["meta"]["versionId"] == "2"


def test_tombstones_are_restored(connection, tmp_path):
    first = boot(connection, tmp_path)
    assert first.post("/Slot", json=SLOT).status_code == 201
    assert first.delete("/Slot/slot-1").status_code == 204
    assert first.post("/admin/flush").status_code == 200

    second = restart(connection, tmp_path)

    # Deleted stays deleted: 410 Gone (known id, tombstoned), not a resurrection.
    assert second.get("/Slot/slot-1").status_code == 410
    history = second.get("/Slot/slot-1/_history")
    assert history.status_code == 200, history.text
    entries = history.json()["entry"]
    assert len(entries) == 2, "both the create and the tombstone must come back"

    # The writer continues after the tombstone's seq, never reusing it.
    fresh = second.post("/Slot", json={**SLOT, "id": "slot-9"})
    assert fresh.status_code == 201, fresh.text
    assert fresh.json()["meta"]["versionId"] == "3"


def test_double_boot_is_idempotent(connection, tmp_path):
    first = boot(connection, tmp_path)
    assert first.post("/Slot", json=SLOT).status_code == 201
    assert first.post("/admin/flush").status_code == 200

    second = restart(connection, tmp_path)
    assert second.get("/Slot/slot-1").status_code == 200
    rows_after_first_restore = log_row_count(connection)

    third = restart(connection, tmp_path)
    assert third.get("/Slot/slot-1").status_code == 200
    assert log_row_count(connection) == rows_after_first_restore, (
        "a second boot must not duplicate restored versions"
    )


def test_seed_preload_skips_restored_resources(connection, tmp_path):
    from fhir4ds.cli.serve import load_resources

    first = boot(connection, tmp_path)
    assert first.post("/Slot", json=SLOT).status_code == 201
    assert first.post("/admin/flush").status_code == 200

    second = restart(connection, tmp_path)

    seed_dir = tmp_path / "seed"
    seed_dir.mkdir()
    (seed_dir / "slot-1.ndjson").write_text(json.dumps(SLOT) + "\n", encoding="utf-8")
    extra = {**SLOT, "id": "slot-extra"}
    (seed_dir / "slot-extra.ndjson").write_text(json.dumps(extra) + "\n", encoding="utf-8")

    context = second.app.state.serve
    imported = load_resources(context, seed_dir)

    assert imported == 1, "the restored slot-1 must be skipped, only slot-extra imported"
    assert second.get("/Slot/slot-extra").status_code == 200
    restored = second.get("/Slot/slot-1")
    assert restored.json()["meta"]["versionId"] == "1", (
        "the dataset version must win over the seed copy"
    )


def test_seed_preload_publishes_to_dataset(connection, tmp_path):
    """A preload is a write: it must reach the dataset, not only the local log.

    The durability claim is exactly this: a fresh boot WITHOUT re-running
    ``--resources`` still serves the preloaded resource, because rehydration
    restores it from the published part.
    """
    from fhir4ds.cli.serve import load_resources

    first = boot(connection, tmp_path)
    seed_dir = tmp_path / "seed"
    seed_dir.mkdir()
    (seed_dir / "slot-seed.ndjson").write_text(json.dumps(SLOT) + "\n", encoding="utf-8")
    assert load_resources(first.app.state.serve, seed_dir) == 1
    # load_resources publishes synchronously: nothing stays buffered.
    assert first.app.state.serve.flusher.pending() == 0
    assert first.post("/admin/flush").status_code == 200

    # Fresh boot, NO --resources: the dataset alone must carry the resource.
    second = restart(connection, tmp_path)
    read = second.get("/Slot/slot-1")
    assert read.status_code == 200, read.text
    assert read.json()["meta"]["versionId"] == "1"
