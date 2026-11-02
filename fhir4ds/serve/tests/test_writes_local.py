"""The write surface end to end: versions, history, If-Match, bundles, flush.

Runs against a fresh in-memory DuckDB and a ``LocalDirStore``, so it needs no
token and no Hub. The Hub-backed path is exercised separately in
``test_store_hf.py`` (skipped unless ``FHIR4DS_HF_INTEGRATION=1``).
"""

from __future__ import annotations

import json
import pathlib
import urllib.parse
import urllib.request

import duckdb
import pytest
from fastapi.testclient import TestClient

from fhir4ds.serve.app import create_app
from fhir4ds.serve.config import ServeConfig

FHIR_JSON = {"Content-Type": "application/fhir+json"}


@pytest.fixture()
def publish_dir(tmp_path):
    return tmp_path / "publish"


@pytest.fixture()
def app_connection():
    con = duckdb.connect()
    try:
        yield con
    finally:
        con.close()


@pytest.fixture()
def client(publish_dir, app_connection):
    app = create_app(
        ServeConfig(publish_dir=str(publish_dir), flush_autostart=False),
        connection=app_connection,
    )
    return TestClient(app)


def patient(resource_id: str | None = None, family: str = "Smith") -> dict:
    resource = {"resourceType": "Patient", "name": [{"family": family}]}
    if resource_id:
        resource["id"] = resource_id
    return resource


def latest_count(connection, resource_type: str = "Patient") -> int:
    row = connection.execute(
        "SELECT count(*) FROM resources WHERE resourceType = ?", [resource_type]
    ).fetchone()
    return int(row[0])


# -- create / read -----------------------------------------------------------


def test_post_assigns_id_version_and_location(client):
    response = client.post("/Patient", json=patient(), headers=FHIR_JSON)

    assert response.status_code == 201
    assert response.headers["etag"] == 'W/"1"'
    body = response.json()
    assert body["id"]
    assert response.headers["location"] == f"Patient/{body['id']}"
    assert body["meta"]["versionId"] == "1"


def test_post_keeps_a_supplied_id(client):
    response = client.post("/Patient", json=patient("p1"), headers=FHIR_JSON)
    assert response.status_code == 201
    assert response.json()["id"] == "p1"


def test_post_duplicate_id_is_rejected(client):
    client.post("/Patient", json=patient("p1"), headers=FHIR_JSON)
    response = client.post("/Patient", json=patient("p1"), headers=FHIR_JSON)

    assert response.status_code == 400
    assert response.json()["issue"][0]["code"] == "duplicate"


def test_get_returns_version_and_etag(client):
    client.post("/Patient", json=patient("p1"), headers=FHIR_JSON)

    response = client.get("/Patient/p1")

    assert response.status_code == 200
    assert response.headers["etag"] == 'W/"1"'
    assert response.json()["meta"]["versionId"] == "1"


def test_get_unknown_resource_is_404(client):
    response = client.get("/Patient/absent")
    assert response.status_code == 404
    assert response.json()["resourceType"] == "OperationOutcome"


# -- updates and history -----------------------------------------------------


def test_put_bumps_the_version(client, app_connection):
    client.post("/Patient", json=patient("p1"), headers=FHIR_JSON)

    response = client.put("/Patient/p1", json=patient("p1", family="Jones"), headers=FHIR_JSON)

    assert response.status_code == 200
    assert response.headers["etag"] == 'W/"2"'
    assert response.json()["meta"]["versionId"] == "2"

    # latest-wins keeps exactly one row
    assert latest_count(app_connection) == 1
    assert client.get("/Patient/p1").json()["name"][0]["family"] == "Jones"


def test_history_returns_every_version_newest_first(client):
    client.post("/Patient", json=patient("p1"), headers=FHIR_JSON)
    client.put("/Patient/p1", json=patient("p1", family="Jones"), headers=FHIR_JSON)

    response = client.get("/Patient/p1/_history")

    assert response.status_code == 200
    bundle = response.json()
    assert bundle["type"] == "history"
    assert [entry["resource"]["meta"]["versionId"] for entry in bundle["entry"]] == ["2", "1"]
    assert bundle["entry"][1]["resource"]["name"][0]["family"] == "Smith"


def test_vread_returns_one_version(client):
    client.post("/Patient", json=patient("p1"), headers=FHIR_JSON)
    client.put("/Patient/p1", json=patient("p1", family="Jones"), headers=FHIR_JSON)

    assert client.get("/Patient/p1/_history/1").json()["name"][0]["family"] == "Smith"
    assert client.get("/Patient/p1/_history/2").json()["name"][0]["family"] == "Jones"
    assert client.get("/Patient/p1/_history/9").status_code == 404


def test_put_of_an_unknown_id_creates_it(client):
    response = client.put("/Patient/new", json=patient("new"), headers=FHIR_JSON)
    assert response.status_code == 201
    assert response.headers["etag"] == 'W/"1"'


# -- If-Match ----------------------------------------------------------------


def test_if_match_mismatch_is_412(client):
    client.post("/Patient", json=patient("p1"), headers=FHIR_JSON)
    client.put("/Patient/p1", json=patient("p1", family="Jones"), headers=FHIR_JSON)

    response = client.put(
        "/Patient/p1",
        json=patient("p1", family="Stale"),
        headers={**FHIR_JSON, "If-Match": 'W/"1"'},
    )

    assert response.status_code == 412
    assert response.json()["issue"][0]["code"] == "conflict"
    # nothing was written
    assert client.get("/Patient/p1").json()["name"][0]["family"] == "Jones"
    assert len(client.get("/Patient/p1/_history").json()["entry"]) == 2


def test_if_match_current_version_is_accepted(client):
    client.post("/Patient", json=patient("p1"), headers=FHIR_JSON)
    client.put("/Patient/p1", json=patient("p1", family="Jones"), headers=FHIR_JSON)

    response = client.put(
        "/Patient/p1",
        json=patient("p1", family="Jones2"),
        headers={**FHIR_JSON, "If-Match": 'W/"2"'},
    )

    assert response.status_code == 200
    assert response.headers["etag"] == 'W/"3"'


def test_if_match_wildcard_matches_anything_existing(client):
    client.post("/Patient", json=patient("p1"), headers=FHIR_JSON)
    response = client.put(
        "/Patient/p1", json=patient("p1", family="J"), headers={**FHIR_JSON, "If-Match": "*"}
    )
    assert response.status_code == 200


# -- delete / tombstone ------------------------------------------------------


def test_delete_tombstones_and_hides_from_reads(client, app_connection):
    client.post("/Patient", json=patient("p1"), headers=FHIR_JSON)

    response = client.delete("/Patient/p1", headers=FHIR_JSON)

    assert response.status_code == 204
    assert latest_count(app_connection) == 0
    assert client.get("/Patient/p1").status_code == 410

    history = client.get("/Patient/p1/_history").json()
    assert len(history["entry"]) == 2
    assert history["entry"][0]["response"]["status"] == "204 No Content"


def test_delete_unknown_is_404(client):
    assert client.delete("/Patient/absent", headers=FHIR_JSON).status_code == 404


def test_deleted_resource_can_be_recreated(client):
    client.post("/Patient", json=patient("p1"), headers=FHIR_JSON)
    client.delete("/Patient/p1", headers=FHIR_JSON)

    response = client.put("/Patient/p1", json=patient("p1", family="Again"), headers=FHIR_JSON)

    assert response.status_code == 201
    assert client.get("/Patient/p1").json()["name"][0]["family"] == "Again"
    assert len(client.get("/Patient/p1/_history").json()["entry"]) == 3


# -- content type ------------------------------------------------------------


def test_writes_reject_non_json_content_types(client):
    response = client.post(
        "/Patient", content=b"<Patient/>", headers={"Content-Type": "application/xml"}
    )
    assert response.status_code == 415
    assert response.json()["resourceType"] == "OperationOutcome"


def test_body_resource_type_must_match_the_path(client):
    response = client.post(
        "/Patient",
        json={"resourceType": "Observation", "status": "final"},
        headers=FHIR_JSON,
    )
    assert response.status_code == 400


# -- bundles -----------------------------------------------------------------


def transaction(entries: list[dict]) -> dict:
    return {"resourceType": "Bundle", "type": "transaction", "entry": entries}


def post_entry(resource_id: str) -> dict:
    return {"request": {"method": "POST", "url": "Patient"}, "resource": patient(resource_id)}


def test_transaction_applies_three_entries_in_one_revision(client, app_connection, publish_dir):
    response = client.post(
        "/Bundle",
        json=transaction([post_entry("p1"), post_entry("p2"), post_entry("p3")]),
        headers=FHIR_JSON,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["type"] == "transaction-response"
    assert [entry["response"]["status"] for entry in body["entry"]] == ["201 Created"] * 3
    assert latest_count(app_connection) == 3

    flush = client.post("/admin/flush").json()
    assert flush["committed"] == 3

    parts = sorted((publish_dir / "resources").rglob("*.parquet"))
    assert len(parts) == 1, "one flush is one part (one revision)"
    rows = duckdb.connect().execute(
        f"SELECT count(*), max(_seq) FROM read_parquet('{parts[0]}')"
    ).fetchone()
    assert rows == (3, 3)


def test_failed_transaction_entry_aborts_everything(client, app_connection):
    client.post("/Patient", json=patient("p1"), headers=FHIR_JSON)
    client.put("/Patient/p1", json=patient("p1", family="Jones"), headers=FHIR_JSON)

    response = client.post(
        "/Bundle",
        json=transaction(
            [
                post_entry("p2"),
                {
                    "request": {"method": "PUT", "url": "Patient/p1", "ifMatch": 'W/"1"'},
                    "resource": patient("p1", family="Stale"),
                },
            ]
        ),
        headers=FHIR_JSON,
    )

    assert response.status_code == 412
    assert latest_count(app_connection) == 1, "the aborted entry rolled the bundle back"
    assert client.get("/Patient/p2").status_code == 404
    assert client.get("/health").json()["pending"] == 2  # only the two pre-bundle writes


def test_batch_bundle_is_applied(client):
    response = client.post(
        "/Bundle",
        json={
            "resourceType": "Bundle",
            "type": "batch",
            "entry": [post_entry("p1")],
        },
        headers=FHIR_JSON,
    )
    assert response.status_code == 200
    assert response.json()["type"] == "batch-response"


def test_bundle_if_match_string_form_is_enforced(client, app_connection):
    """Regression (review finding 1): FHIR sends ``ifMatch`` as a STRING.

    A stale string ETag inside a transaction must be a 412 that rolls the whole
    bundle back — not a silently-ignored precondition.
    """
    client.post("/Patient", json=patient("p1"), headers=FHIR_JSON)
    client.put("/Patient/p1", json=patient("p1", family="Jones"), headers=FHIR_JSON)

    response = client.post(
        "/Bundle",
        json=transaction(
            [
                post_entry("p2"),
                {
                    "request": {"method": "PUT", "url": "Patient/p1", "ifMatch": 'W/"1"'},
                    "resource": patient("p1", family="Stale"),
                },
            ]
        ),
        headers=FHIR_JSON,
    )

    assert response.status_code == 412
    assert latest_count(app_connection) == 1
    assert client.get("/Patient/p2").status_code == 404
    assert client.get("/Patient/p1").json()["name"][0]["family"] == "Jones"


def test_bundle_if_match_current_string_is_accepted(client):
    client.post("/Patient", json=patient("p1"), headers=FHIR_JSON)
    response = client.post(
        "/Bundle",
        json=transaction(
            [
                {
                    "request": {"method": "PUT", "url": "Patient/p1", "ifMatch": 'W/"1"'},
                    "resource": patient("p1", family="Jones"),
                }
            ]
        ),
        headers=FHIR_JSON,
    )
    assert response.status_code == 200
    assert response.json()["entry"][0]["response"]["etag"] == 'W/"2"'


def test_bundle_if_match_must_be_a_string(client):
    """A non-string ifMatch is rejected loudly, never silently dropped."""
    client.post("/Patient", json=patient("p1"), headers=FHIR_JSON)
    response = client.post(
        "/Bundle",
        json=transaction(
            [
                {
                    "request": {"method": "PUT", "url": "Patient/p1", "ifMatch": ['W/"1"']},
                    "resource": patient("p1", family="Jones"),
                }
            ]
        ),
        headers=FHIR_JSON,
    )
    assert response.status_code == 400
    assert client.get("/Patient/p1").json()["name"][0]["family"] == "Smith"


def test_delete_needs_no_content_type(client, app_connection):
    """Regression (review finding 3): DELETE carries no body; a plain
    ``curl -X DELETE`` must not be a 415."""
    client.post("/Patient", json=patient("p1"), headers=FHIR_JSON)
    response = client.delete("/Patient/p1")
    assert response.status_code == 204
    assert latest_count(app_connection) == 0


def test_bundle_rejects_unknown_types(client):
    response = client.post(
        "/Bundle",
        json={"resourceType": "Bundle", "type": "document", "entry": []},
        headers=FHIR_JSON,
    )
    assert response.status_code == 400


# -- publication -------------------------------------------------------------


def test_health_reports_publication_state(client):
    client.post("/Patient", json=patient("p1"), headers=FHIR_JSON)

    health = client.get("/health").json()
    assert health["status"] == "ok"
    assert health["pending"] == 1
    assert health["last_commit"] is None
    assert health["last_error"] is None


def test_admin_flush_commits_the_buffer(client, publish_dir):
    client.post("/Patient", json=patient("p1"), headers=FHIR_JSON)
    client.post("/Observation", json={"resourceType": "Observation", "status": "final"}, headers=FHIR_JSON)

    flush = client.post("/admin/flush").json()

    assert flush["committed"] == 2
    assert flush["pending"] == 0
    assert flush["revision"]

    state = json.loads((publish_dir / "meta" / "state.json").read_text())
    assert state["seq"] == 2
    assert state["revision"] == flush["revision"]

    health = client.get("/health").json()
    assert health["last_commit"] == flush["revision"]
    assert health["last_commit_at"]
    assert health["pending"] == 0


def test_versions_survive_a_restart(publish_dir, app_connection):
    first = TestClient(
        create_app(
            ServeConfig(publish_dir=str(publish_dir), flush_autostart=False),
            connection=app_connection,
        )
    )
    first.post("/Patient", json=patient("p1"), headers=FHIR_JSON)
    first.post("/admin/flush")

    # A new process: fresh in-memory database, same dataset directory. Boot-time
    # rehydration restores p1 (original _seq 1) from the published part before
    # the surface serves, so the id exists: read it back and UPDATE it — a
    # duplicate create would be a phantom rewrite of published history.
    second_connection = duckdb.connect()
    try:
        second = TestClient(
            create_app(
                ServeConfig(publish_dir=str(publish_dir), flush_autostart=False),
                connection=second_connection,
            )
        )
        restored = second.get("/Patient/p1")
        assert restored.status_code == 200, restored.text
        assert restored.headers["etag"] == 'W/"1"'
        response = second.put(
            "/Patient/p1", json=patient("p1", family="Next"), headers=FHIR_JSON
        )
        assert response.status_code == 200
        assert response.headers["etag"] == 'W/"2"'
    finally:
        second_connection.close()


def test_upload_failure_does_not_double_publish(tmp_path):
    """Review fix 5: rows committed locally but not uploaded are retried as an
    upload — never re-buffered into a second part."""
    import duckdb as _duckdb

    from fhir4ds.serve.flusher import FlushManager
    from fhir4ds.serve.store import LocalDirStore

    root = tmp_path / "dataset"

    class FlakyStore(LocalDirStore):
        """Local tree commits fine; the 'upload' fails on demand.

        Mirrors HfDatasetStore's seam exactly: ``commit`` writes the local tree
        and then publishes, so raising AFTER ``super().commit()`` is the shape
        of a Hub outage mid-flush.
        """

        def __init__(self, root_dir):
            super().__init__(root_dir)
            self.fail_upload = False

        def commit(self):
            revision = super().commit()
            if self.fail_upload:
                raise RuntimeError("hub down")
            return revision

        def pending_files(self):
            return len(self.dirty_paths())

        def retry_publish(self):
            if self.fail_upload:
                raise RuntimeError("hub down")
            return super().retry_publish()

    store = FlakyStore(root)
    manager = FlushManager(store, autostart=False)

    def row(seq):
        return {
            "id": f"o{seq}", "resourceType": "Observation",
            "resource": json.dumps({"resourceType": "Observation", "id": f"o{seq}"}),
            "patient_ref": "p1", "_seq": seq, "_deleted": False,
            "_ingested_at": "2026-11-01T00:00:00Z",
        }

    # First flush: local commit succeeds, upload fails.
    store.fail_upload = True
    manager.enqueue([row(1), row(2)])
    result = manager.flush()
    assert result.committed == 0
    assert manager.last_error and "hub down" in manager.last_error
    assert manager.pending() == 0, "committed rows are NOT re-buffered"
    assert store.current_seq() == 2, "the local tree already holds them"

    # New rows join; the next flush writes them and retries the upload.
    store.fail_upload = False
    manager.enqueue([row(3)])
    result = manager.flush()
    assert result.committed == 1

    parts = sorted((root / "resources").rglob("*.parquet"))
    dataset = _duckdb.connect().execute(
        f"SELECT count(*), count(DISTINCT _seq) FROM read_parquet('{root}/resources/**/*.parquet')"
    ).fetchone()
    assert dataset == (3, 3), f"no duplicated _seq across parts; got {dataset}"
    assert len(parts) == 2
    assert manager.last_error is None


def test_bulk_publish_manifest_lists_the_published_part(client, publish_dir):
    client.post("/Patient", json=patient("p1"), headers=FHIR_JSON)
    client.post("/admin/flush")

    manifest = client.get("/$bulk-publish").json()

    assert manifest["request"]["method"] == "GET"
    assert manifest["output"], "a flushed part must be advertised"
    url = manifest["output"][0]["url"]
    assert url.startswith("file://")
    # ``as_uri`` percent-encodes the partition (``dt=...`` -> ``dt%3D...``).
    path = pathlib.Path(urllib.request.url2pathname(urllib.parse.urlparse(url).path))
    assert path.exists()
    assert path.is_relative_to(publish_dir)

    # The manifest is also a file in the dataset, so it works with the server down.
    assert (publish_dir / "$bulk-publish").exists()
    assert (publish_dir / "publishers" / "fhir4ds-serve" / "$bulk-publish").exists()
    assert (publish_dir / "README.md").exists()


def test_dataset_carries_served_definitions(client, publish_dir, connection, store):
    """Definitions the server serves are published alongside the data."""
    installed = TestClient(
        create_app(
            ServeConfig(publish_dir=str(publish_dir), flush_autostart=False),
            connection=connection,
        )
    )
    installed.post("/Patient", json=patient("p1"), headers=FHIR_JSON)
    installed.post("/admin/flush")

    files = sorted(path.name for path in (publish_dir / "viewdefinitions").glob("*.json"))
    assert "patient-view.json" in files
    queries = sorted(path.name for path in (publish_dir / "sqlqueries").glob("*.json"))
    assert "SqlOnFhirExample.json" in queries
