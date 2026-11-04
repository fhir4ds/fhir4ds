"""The operation ``source`` parameter: names, data-root paths, dataset URIs.

Phase 2 adds two shapes beyond configured table names: a path under the
mounted data root (loaded once, then reused) and dataset URIs such as
``hf://datasets/fhir4ds/bulk-publish-demo-data``, which must be answered with a
clear ``OperationOutcome`` rather than a crash — the dataset store itself
arrives in phase 3.
"""

from __future__ import annotations

import shutil
import threading

import pytest
from fastapi.testclient import TestClient

from fhir4ds.serve.app import create_app
from fhir4ds.serve.config import ServeConfig

from ._helpers import RESOURCE_BUNDLE, TEST_ADMIN_KEY, TEST_WRITE_KEY, keyed_client, parameters

VIEW_PATH = "/ViewDefinition/patient-view/$run"


@pytest.fixture()
def data_root(tmp_path):
    """A data root holding a copy of the synthetic Bundle."""
    root = tmp_path / "data"
    root.mkdir()
    shutil.copy(RESOURCE_BUNDLE, root / "bundle.json")
    return root


def _app(connection, **config_kwargs) -> TestClient:
    app = create_app(ServeConfig(
        admin_key=TEST_ADMIN_KEY,
        write_key=TEST_WRITE_KEY,
**config_kwargs), connection=connection)
    return keyed_client(app)


def _source(value: str) -> dict:
    return parameters({"name": "source", "valueString": value})


def test_configured_source_name_still_wins(connection, store):
    client = _app(connection, sources={"warehouse": "resources"})
    response = client.post(VIEW_PATH, json=_source("warehouse"))
    assert response.status_code == 200, response.text
    assert len(response.text.strip().splitlines()) == 3


def test_directory_source_is_loaded_and_reused(connection, store, data_root):
    client = _app(connection, data_root=str(data_root))

    first = client.post(VIEW_PATH, json=_source(str(data_root)))
    assert first.status_code == 200, first.text
    assert len(first.text.strip().splitlines()) == 3

    # Second call reuses the materialized table: same rows, no reload.
    second = client.post(VIEW_PATH, json=_source(str(data_root)))
    assert second.status_code == 200
    assert second.text == first.text

    tables = {
        row[0]
        for row in connection.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_name LIKE 'serve_source_%'"
        ).fetchall()
    }
    assert len(tables) == 1


def test_relative_path_resolves_under_the_root(connection, store, data_root):
    client = _app(connection, data_root=str(data_root))
    response = client.post(VIEW_PATH, json=_source("bundle.json"))
    assert response.status_code == 200, response.text
    assert len(response.text.strip().splitlines()) == 3


def test_path_outside_the_root_is_rejected(connection, store, data_root):
    client = _app(connection, data_root=str(data_root))
    response = client.post(VIEW_PATH, json=_source("/etc/passwd"))
    assert response.status_code == 400
    issue = response.json()["issue"][0]
    assert issue["code"] == "not-supported"
    assert issue["expression"] == ["source"]


def test_path_source_requires_a_data_root(connection, store, tmp_path):
    client = _app(connection)  # default: path sources disabled
    response = client.post(VIEW_PATH, json=_source(str(tmp_path)))
    assert response.status_code == 400
    issue = response.json()["issue"][0]
    assert issue["code"] == "not-supported"
    assert "--data-root" in issue["diagnostics"]


def test_missing_path_is_404(connection, store, data_root):
    client = _app(connection, data_root=str(data_root))
    response = client.post(VIEW_PATH, json=_source("nope"))
    assert response.status_code == 404
    assert response.json()["issue"][0]["code"] == "not-found"


def test_hf_dataset_uri_is_a_clear_operation_outcome(connection, store, data_root):
    client = _app(connection, data_root=str(data_root))
    response = client.post(VIEW_PATH, json=_source("hf://datasets/fhir4ds/bulk-publish-demo-data"))

    assert response.status_code == 400
    body = response.json()
    assert body["resourceType"] == "OperationOutcome"
    issue = body["issue"][0]
    assert issue["code"] == "not-supported"
    assert "phase 3" in issue["diagnostics"]

    # The server keeps serving afterwards.
    assert client.get("/health").status_code == 200
    assert client.post(VIEW_PATH, json=_source(str(data_root))).status_code == 200


@pytest.mark.parametrize("uri", ["s3://bucket/prefix", "gs://bucket/prefix"])
def test_other_dataset_schemes_are_rejected(connection, store, data_root, uri):
    client = _app(connection, data_root=str(data_root))
    response = client.post(VIEW_PATH, json=_source(uri))
    assert response.status_code == 400
    assert response.json()["issue"][0]["code"] == "not-supported"


def test_path_resolution_never_escapes_the_root(connection, store, data_root):
    """A ``..`` segment must not reach outside the configured root."""
    client = _app(connection, data_root=str(data_root))
    response = client.post(VIEW_PATH, json=_source("../../etc"))
    assert response.status_code == 400
    assert response.json()["issue"][0]["code"] == "not-supported"


def test_concurrent_path_source_requests_load_once(connection, store, data_root):
    """The load happens under the connection lock, once, even under races."""
    app = create_app(ServeConfig(
        admin_key=TEST_ADMIN_KEY,
        write_key=TEST_WRITE_KEY,
data_root=str(data_root)), connection=connection)
    results: list[int] = []

    def call() -> None:
        # A client per thread: httpx clients are not safe to share.
        results.append(keyed_client(app).post(VIEW_PATH, json=_source(str(data_root))).status_code)

    threads = [threading.Thread(target=call) for _ in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=120)

    assert results == [200, 200, 200, 200]
