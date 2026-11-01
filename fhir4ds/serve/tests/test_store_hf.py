"""The Hub-backed store: conflict retry (no token) and the live publish (token).

The retry tests replace ``huggingface_hub`` with a stub, so they run everywhere
and pin the semantics that matter: a ``409`` parent conflict re-reads the branch
head and retries **once**, on top of the new head, and a second conflict is
surfaced instead of looping.

The live test publishes to ``fhir4ds/bulk-publish-demo`` only and is skipped
unless both conditions hold::

    FHIR4DS_HF_INTEGRATION=1 HF_TOKEN=... pytest fhir4ds/serve/tests/test_store_hf.py -q

Its data is synthetic (no patient identifiers, invented FHIR ids).
"""

from __future__ import annotations

import json
import os
import sys
import types
import urllib.request
import uuid

import pytest

REPO = "fhir4ds/bulk-publish-demo"
FHIR_JSON = {"Content-Type": "application/fhir+json"}


# -- conflict retry, with a stubbed hub --------------------------------------


class _Conflict(Exception):
    """A parent-commit rejection: the branch head moved."""

    response = types.SimpleNamespace(status_code=409)


def _row(seq: int) -> dict:
    return {
        "id": f"o{seq}",
        "resourceType": "Observation",
        "resource": json.dumps({"resourceType": "Observation", "id": f"o{seq}"}),
        "patient_ref": "p1",
        "_seq": seq,
        "_deleted": False,
        "_ingested_at": "2026-10-31T00:00:00Z",
    }


def _stub_hub(monkeypatch, *, conflicts: int, heads: list[str]) -> list[dict]:
    """Install a fake ``huggingface_hub`` module; record every commit attempt."""
    calls: list[dict] = []
    head = {"value": heads[0]}

    def create_commit(*args, **kwargs):
        calls.append(kwargs)
        if len(calls) <= conflicts:
            head["value"] = heads[min(len(calls), len(heads) - 1)]
            raise _Conflict("409 conflict: the branch head moved")
        return types.SimpleNamespace(oid="sha-final")

    def repo_info(*args, **kwargs):
        return types.SimpleNamespace(sha=head["value"])

    module = types.SimpleNamespace(
        snapshot_download=lambda **kwargs: kwargs.get("local_dir"),
        create_commit=create_commit,
        CommitOperationAdd=lambda path_in_repo, path_or_fileobj: types.SimpleNamespace(
            path_in_repo=path_in_repo, path_or_fileobj=path_or_fileobj
        ),
        HfApi=lambda token=None: types.SimpleNamespace(repo_info=repo_info),
    )
    monkeypatch.setitem(sys.modules, "huggingface_hub", module)
    return calls


@pytest.fixture()
def store(tmp_path, monkeypatch):
    from fhir4ds.serve.hf_store import HfDatasetStore

    instance = HfDatasetStore(REPO, tmp_path / "cache", max_retries=1)
    monkeypatch.setattr(instance, "_downloaded", True)
    monkeypatch.setattr(instance, "_revision", "sha-head-1")
    return instance


def test_commit_retries_once_on_parent_conflict(store, monkeypatch):
    calls = _stub_hub(monkeypatch, conflicts=1, heads=["sha-head-1", "sha-head-2"])

    store.append([_row(1)])
    store.commit()

    assert len(calls) == 2, "a parent conflict must be retried exactly once"
    assert calls[0]["parent_commit"] == "sha-head-1"
    assert calls[1]["parent_commit"] == "sha-head-2", "the retry rebases on the new head"
    assert store.revision() == "sha-final"


def test_repeated_conflict_is_surfaced(store, monkeypatch):
    calls = _stub_hub(monkeypatch, conflicts=5, heads=["h1", "h2", "h3", "h4", "h5", "h6"])

    store.append([_row(1)])
    with pytest.raises(_Conflict):
        store.commit()

    assert len(calls) == 2, "max_retries=1 means one retry, not a loop"


def test_rows_keep_their_seq_across_a_conflict(store, monkeypatch):
    _stub_hub(monkeypatch, conflicts=1, heads=["h1", "h2"])

    store.append([_row(7), _row(8)])
    store.commit()

    state = json.loads((store.root / "meta" / "state.json").read_text())
    assert state["seq"] == 8


# -- the live publish (token-gated) ------------------------------------------


def _observation(index: int, run_id: str) -> dict:
    return {
        "resourceType": "Observation",
        "id": f"syn-{run_id}-{index}",
        "status": "final",
        "code": {"coding": [{"system": "http://loinc.org", "code": "8867-4"}]},
        "subject": {"reference": f"Patient/synthetic-{run_id}"},
        "valueQuantity": {"value": 60 + index, "unit": "beats/min"},
    }


def _hf_connection():
    """A DuckDB connection able to read ``hf://`` datasets."""
    import duckdb

    con = duckdb.connect()
    for statement in ("INSTALL hf;", "LOAD hf;", "INSTALL httpfs;", "LOAD httpfs;"):
        try:
            con.execute(statement)
        except Exception:  # noqa: BLE001 - extension availability is environmental
            continue
    return con


@pytest.mark.skipif(
    os.environ.get("FHIR4DS_HF_INTEGRATION") != "1",
    reason="set FHIR4DS_HF_INTEGRATION=1 (and HF_TOKEN) to publish to the Hub",
)
def test_publish_100_observations_then_reput_one(tmp_path):
    pytest.importorskip("huggingface_hub")
    if not os.environ.get("HF_TOKEN"):
        pytest.skip("HF_TOKEN is required to publish")

    from fastapi.testclient import TestClient

    from fhir4ds.serve.app import create_app
    from fhir4ds.serve.config import ServeConfig

    run_id = uuid.uuid4().hex[:8]
    app = create_app(
        ServeConfig(
            publish_dir=str(tmp_path / "cache"),
            publish_backend="hf",
            publish_repository=REPO,
            publisher="fhir4ds-serve",
            flush_autostart=False,
        )
    )
    client = TestClient(app)

    for index in range(100):
        response = client.post(
            "/Observation", json=_observation(index, run_id), headers=FHIR_JSON
        )
        assert response.status_code == 201, response.text

    flush = client.post("/admin/flush")
    assert flush.status_code == 200, flush.text
    assert flush.json()["committed"] == 100

    con = _hf_connection()
    try:
        pattern = f"hf://datasets/{REPO}/resources/**/*.parquet"
        published = con.execute(
            f"SELECT count(*) FROM read_parquet('{pattern}') WHERE id LIKE 'syn-{run_id}-%'"
        ).fetchone()[0]
        assert published == 100

        latest = con.execute(
            f"""
            SELECT count(*) FROM (
                SELECT id, _deleted,
                       row_number() OVER (PARTITION BY resourceType, id ORDER BY _seq DESC) AS rn
                FROM read_parquet('{pattern}')
                WHERE id LIKE 'syn-{run_id}-%'
            )
            WHERE rn = 1 AND NOT _deleted
            """
        ).fetchone()[0]
        assert latest == 100

        # Re-PUT one id: a new version, still one latest row, two versions total.
        amended = _observation(0, run_id)
        amended["status"] = "amended"
        again = client.put(f"/Observation/syn-{run_id}-0", json=amended, headers=FHIR_JSON)
        assert again.status_code == 200, again.text
        assert client.post("/admin/flush").json()["committed"] == 1

        rows = con.execute(
            f"SELECT count(*) FROM read_parquet('{pattern}') WHERE id = 'syn-{run_id}-0'"
        ).fetchone()[0]
        assert rows == 2, "_history for that id is 2 versions"

        latest_for_id = con.execute(
            f"""
            SELECT count(*) FROM read_parquet('{pattern}')
            WHERE id = 'syn-{run_id}-0'
              AND _seq = (SELECT max(_seq) FROM read_parquet('{pattern}')
                          WHERE id = 'syn-{run_id}-0')
            """
        ).fetchone()[0]
        assert latest_for_id == 1
    finally:
        con.close()

    # The manifest is public: no auth, plain fetch.
    manifest_url = f"https://huggingface.co/datasets/{REPO}/resolve/main/$bulk-publish"
    with urllib.request.urlopen(manifest_url, timeout=60) as response:
        manifest = json.loads(response.read().decode("utf-8"))
    assert manifest["request"]["method"] == "GET"
    assert any("resources/" in entry["url"] for entry in manifest["output"])

    live = client.get("/$bulk-publish").json()
    assert live["output"] and all(
        entry["url"].startswith(f"https://huggingface.co/datasets/{REPO}/resolve/main/")
        for entry in live["output"]
    )
