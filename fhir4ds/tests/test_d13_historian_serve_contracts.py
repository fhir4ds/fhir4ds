"""D13 HISTORIAN serve contracts (v0.0.26, iteration 40).

Red-first regression coverage for the four durability/surface defects found
by the section-by-section walkthrough:

* QA-D13H-001 — search on an unknown resource type returned an empty
  searchset (200) instead of 404; the write path already enforces the closed
  FHIR type set (``_require_type``), the read path did not.
* QA-D13H-002 — a flush failure after ``store.append`` but before commit
  re-buffered rows that were still in the store's own buffer, so the retry
  published every row twice (duplicate ``_seq`` in the dataset parts).
* QA-D13H-003 — the writer's sequence floor was computed BEFORE
  rehydration, so a boot after a mid-flush crash (published part ahead of
  ``meta/state.json``) reissued a colliding ``_seq``; the next boot's
  ``NOT EXISTS`` rehydration dedup then silently DROPPED the new write.
* QA-D13H-004 — a dataset recreated under a live Hub-backed publisher left
  the store serving a stale local cache; the parent-conflict retry now
  re-syncs the tree from the remote head (pruning files the recreation
  removed) while preserving dirty, not-yet-uploaded files.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from fastapi.testclient import TestClient

from fhir4ds.connection import create_connection
from fhir4ds.serve.app import create_app
from fhir4ds.serve.config import ServeConfig
from fhir4ds.serve.store import LocalDirStore

ADMIN = "test-admin-key-0123456789"
WRITE = "test-write-key-0123456789"
HEADERS = {"X-Admin-Key": ADMIN, "X-Write-Key": WRITE}
PATIENT = {"resourceType": "Patient"}


def _boot(tmp_path, store_factory=None, connection=None, publish_dir=None):
    connection = connection or create_connection(":memory:")
    publish_dir = publish_dir or Path(tempfile.mkdtemp(prefix="d13h-"))

    if store_factory is None:
        store = LocalDirStore(publish_dir)

        def store_factory():
            return store
    class _Cfg(ServeConfig):
        def publish_store(self):  # noqa: D102
            return store_factory()

    app = create_app(
        _Cfg(admin_key=ADMIN, write_key=WRITE,
             publish_dir=str(publish_dir), flush_autostart=False),
        connection=connection,
    )
    return TestClient(app), publish_dir


def _dataset_seqs(publish_dir: Path) -> list[int]:
    import duckdb

    seqs: list[int] = []
    for part in sorted(Path(publish_dir).rglob("part-*.parquet")):
        seqs.extend(r[0] for r in duckdb.sql(
            f"SELECT _seq FROM read_parquet('{part}')").fetchall())
    return sorted(seqs)


# -- QA-D13H-001: unknown resource type on the search path -------------------


def test_search_unknown_resource_type_is_404_not_empty_searchset(tmp_path):
    """`GET /NotAType` must not answer an empty searchset (silent no-data)."""
    client, _ = _boot(tmp_path)
    response = client.get("/NotAType")
    assert response.status_code == 404
    outcome = response.json()
    assert outcome["resourceType"] == "OperationOutcome"
    assert "NotAType" in outcome["issue"][0]["diagnostics"]
    # lexically-valid names only; malformed names keep the 400 shape check
    assert client.get("/patient").status_code == 400
    # known types still search fine
    assert client.get("/Patient").status_code == 200


# -- QA-D13H-002: transient flush failure must not double-publish ------------


class _CommitFailsOnceStore(LocalDirStore):
    """commit() raises BEFORE writing anything (pre-commit failure)."""

    fail_next = 0

    def commit(self):
        if self.fail_next > 0:
            self.fail_next -= 1
            raise OSError("simulated pre-commit failure")
        return super().commit()


def test_transient_flush_failure_does_not_double_publish(tmp_path):
    store = _CommitFailsOnceStore(Path(tempfile.mkdtemp(prefix="d13h-")))
    client, _ = _boot(tmp_path, store_factory=lambda: store)
    for _ in range(3):
        assert client.post("/Patient", json=PATIENT, headers=HEADERS).status_code == 201

    store.fail_next = 1
    first = client.post("/admin/flush", headers=HEADERS).json()
    assert first["committed"] == 0 and first["pending"] == 3

    second = client.post("/admin/flush", headers=HEADERS).json()
    assert second["committed"] == 3

    seqs = _dataset_seqs(store.root)
    assert seqs == [1, 2, 3], f"duplicate _seq published: {seqs}"


# -- QA-D13H-003: mid-flush crash must not reissue sequence numbers ----------


def test_mid_flush_crash_boot_does_not_collide_seq_or_lose_writes(tmp_path):
    """Part written, state.json stale -> boot -> new write must take _seq 3.

    Pre-fix: the writer floor came from state.json (0), so the new write
    took _seq 1 — colliding with the restored row — and the NEXT boot's
    rehydration dedup silently dropped it.
    """
    client, publish_dir = _boot(tmp_path)
    connection = client.app.state.serve.connection
    for i in range(2):
        client.post("/Patient", json={**PATIENT, "id": f"crash-{i}"}, headers=HEADERS)

    # Simulate the crash: the part reached the dataset, state.json did not.
    store = client.app.state.serve.flusher._store
    rows = [
        {"id": r[0], "resourceType": r[1], "resource": r[2], "patient_ref": r[3],
         "_seq": r[4], "_deleted": r[5]}
        for r in connection.execute(
            "SELECT id, resourceType, resource, patient_ref, _seq, _deleted "
            "FROM resources_base ORDER BY _seq").fetchall()
    ]
    for row in rows:
        row["resource"] = (
            row["resource"] if isinstance(row["resource"], str)
            else json.dumps(row["resource"])
        )
    store._write_part(rows, max(int(r["_seq"]) for r in rows))
    assert not (Path(store.root) / "meta" / "state.json").exists()

    # Reboot on the same dataset: the restored rows set the writer floor.
    reboot, _ = _boot(tmp_path, publish_dir=publish_dir)
    assert reboot.get("/Patient").json()["total"] == 2
    created = reboot.post("/Patient", json={**PATIENT, "id": "post-crash"},
                          headers=HEADERS)
    assert created.status_code == 201
    assert created.json()["meta"]["versionId"] == "3"

    # And the new write survives the NEXT boot (no dedup data loss).
    reboot.post("/admin/flush", headers=HEADERS)
    reboot2, _ = _boot(tmp_path, publish_dir=publish_dir)
    assert reboot2.get("/Patient/post-crash").status_code == 200
    assert reboot2.get("/Patient").json()["total"] == 3


# -- QA-D13H-004: dataset recreation under a live Hub-backed publisher -------


def test_recreated_dataset_resyncs_local_cache_on_conflict(monkeypatch, tmp_path):
    """After remote recreation, the conflict retry re-syncs the local tree."""
    import sys
    import types

    remote_files = {"meta/state.json": json.dumps({"seq": 0, "revision": "f"}).encode()}
    state = {"head": "fresh-head"}

    class _Resp:
        status_code = 409

    class ParentConflict(Exception):
        def __init__(self):
            super().__init__("parent_commit mismatch")
            self.response = _Resp()

    def snapshot_download(*, repo_id, repo_type, revision, local_dir, token=None):
        # Hub local_dir semantics: files removed from the repo are pruned.
        local = Path(local_dir)
        for path in local.rglob("*"):
            if path.is_file() and str(path.relative_to(local)) not in remote_files:
                path.unlink()
        for rel, data in remote_files.items():
            target = local / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)

    class HfApi:
        def __init__(self, token=None):
            pass

        def repo_info(self, repo_id, repo_type, revision):
            return types.SimpleNamespace(sha=state["head"])

    def create_commit(repo_id, operations, commit_message, repo_type, token=None,
                      revision=None, parent_commit=None):
        if parent_commit is not None and parent_commit != state["head"]:
            raise ParentConflict()
        for op in operations:
            remote_files[op.path_in_repo] = Path(op.path_or_fileobj).read_bytes()
        state["head"] = f"c{len(remote_files)}"
        return types.SimpleNamespace(oid=state["head"])

    module = types.ModuleType("huggingface_hub")
    module.snapshot_download = snapshot_download
    module.HfApi = HfApi
    module.create_commit = create_commit

    class _Op:
        def __init__(self, path_in_repo, path_or_fileobj):
            self.path_in_repo = path_in_repo
            self.path_or_fileobj = path_or_fileobj

    module.CommitOperationAdd = _Op
    monkeypatch.setitem(sys.modules, "huggingface_hub", module)

    from fhir4ds.serve.hf_store import HfDatasetStore

    cache = Path(tempfile.mkdtemp(prefix="d13h-hf-"))
    store = HfDatasetStore("owner/data", cache)
    store.append([{"id": "a", "resourceType": "Patient",
                   "resource": '{"resourceType":"Patient","id":"a"}', "_seq": 1}])
    store.commit()
    assert "resources/dt=" not in "".join(remote_files) or any(
        p.startswith("resources/") for p in remote_files)

    # Remote recreation: every published file gone, new head.
    remote_files.clear()
    remote_files["meta/state.json"] = json.dumps(
        {"seq": 0, "revision": "fresh"}).encode()
    state["head"] = "fresh-head"

    store.append([{"id": "b", "resourceType": "Patient",
                   "resource": '{"resourceType":"Patient","id":"b"}', "_seq": 2}])
    store.commit()  # parent conflict -> retry re-syncs -> commits on fresh head

    local_parts = sorted(str(p.relative_to(cache)) for p in cache.rglob("part-*.parquet"))
    remote_parts = sorted(p for p in remote_files if p.startswith("resources/"))
    assert local_parts == remote_parts, (
        f"stale local parts survived recreation: local={local_parts} "
        f"remote={remote_parts}"
    )
    # and the pending row reached the recreated remote
    assert any('"id":"b"' in remote_files[p].decode("utf-8", "replace")
               for p in remote_parts)
