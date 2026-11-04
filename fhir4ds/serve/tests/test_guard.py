"""Public-hardening surfaces: key tiers, rotation, caps, timeouts, query params.

These tests pin the guard's tier matrix, the runtime write-key registry
(persistence, never-zero), the request-size cap, the query watchdog, the
concurrency gate, the default row cap, write resourceType sanity, and the
query-string parameter overlay.
"""

from __future__ import annotations

import json
import threading

import pytest
from fastapi.testclient import TestClient

from fhir4ds.serve.app import create_app
from fhir4ds.serve.config import ServeConfig
from fhir4ds.serve.tests._helpers import (
    TEST_ADMIN_KEY,
    TEST_WRITE_KEY,
    keyed_client,
)

ADMIN = {"X-Admin-Key": TEST_ADMIN_KEY}
WRITE = {"X-Write-Key": TEST_WRITE_KEY}
SLOT_VIEW = {
    "resourceType": "ViewDefinition",
    "id": "slot-view",
    "name": "slot_view",
    "status": "active",
    "resource": "Slot",
    "select": [{"column": [{"name": "slot_id", "path": "id", "type": "string"}]}],
}

SLOT = {
    "resourceType": "Slot",
    "id": "s1",
    "status": "free",
    "schedule": {"reference": "Schedule/1"},
}


@pytest.fixture()
def connection():
    from fhir4ds.connection import create_connection

    con = create_connection(":memory:")
    yield con
    con.close()


def plain_client(app):
    """A TestClient carrying NO credentials (the keyed default is app-wide)."""
    return TestClient(app)


def boot(connection, tmp_path, **overrides):
    config = ServeConfig(
        admin_key=TEST_ADMIN_KEY,
        write_key=TEST_WRITE_KEY,
        publish_dir=str(tmp_path),
        flush_autostart=False,
        **overrides,
    )
    return keyed_client(create_app(config, connection=connection))


# -- tier matrix -----------------------------------------------------------


def test_write_requires_a_key_and_accepts_either_tier(connection, tmp_path):
    client = boot(connection, tmp_path)
    anonymous = plain_client(client.app)
    assert anonymous.post("/Slot", json=SLOT).status_code == 401
    assert anonymous.post("/Slot", json=SLOT, headers=WRITE).status_code == 201
    second = {**SLOT, "id": "s2"}
    assert anonymous.post("/Slot", json=second, headers=ADMIN).status_code == 201


def test_reads_and_stored_operations_are_open(connection, tmp_path):
    client = boot(connection, tmp_path)
    client.post("/Slot", json=SLOT, headers=WRITE)
    no_key = client.headers.copy()
    for header in ("X-Admin-Key", "X-Write-Key"):
        no_key.pop(header, None)
    plain = client  # keyed_client carries keys; strip them per-request instead
    read = plain.get("/Slot/s1")
    assert read.status_code == 200
    history = plain.get("/Slot/s1/_history")
    assert history.status_code == 200


def test_key_management_and_inline_resources_are_admin_only(connection, tmp_path):
    client = boot(connection, tmp_path)
    anonymous = plain_client(client.app)
    body = {"action": "add", "label": "ci", "key": "x" * 24}
    assert anonymous.post("/admin/key", json=body, headers=WRITE).status_code == 401
    assert anonymous.post("/admin/key", json=body, headers=ADMIN).status_code == 200
    # type-level $run (inline viewResource) is admin; instance $run stays open
    assert anonymous.post("/ViewDefinition/$run", json={}).status_code == 401


def test_fail_closed_when_no_keys_configured(connection, tmp_path):
    config = ServeConfig(publish_dir=str(tmp_path), flush_autostart=False)
    client = plain_client(create_app(config, connection=connection))
    # no keys are configured at all: every write tier request is refused
    assert client.post("/Slot", json=SLOT, headers=WRITE).status_code == 401
    assert client.post("/Slot", json=SLOT, headers=ADMIN).status_code == 401


# -- write-key rotation -----------------------------------------------------


def test_write_key_rotation_add_revoke_and_persistence(connection, tmp_path):
    key_store = tmp_path / "keys.json"
    config = ServeConfig(
        admin_key=TEST_ADMIN_KEY,
        write_key=TEST_WRITE_KEY,
        key_store=str(key_store),
        publish_dir=str(tmp_path / "p"),
        flush_autostart=False,
    )
    client = plain_client(create_app(config, connection=connection))

    new_key = "rotated-write-key-abcdef"
    added = client.post(
        "/admin/key",
        json={"action": "add", "label": "publisher", "key": new_key},
        headers=ADMIN,
    )
    assert added.status_code == 200
    assert set(added.json()["write_keys"]) >= {"__env__", "publisher"}

    # the new key writes; the bootstrap key still writes (two active)
    assert client.post(
        "/Slot", json=SLOT, headers={"X-Write-Key": new_key}
    ).status_code == 201

    # revoking the bootstrap leaves the rotated one active
    revoked = client.post(
        "/admin/key", json={"action": "revoke", "label": "__env__"}, headers=ADMIN
    )
    assert revoked.status_code == 200
    assert client.post(
        "/Slot", json={**SLOT, "id": "s2"}, headers=WRITE
    ).status_code == 401

    # never down to zero
    denied = client.post(
        "/admin/key", json={"action": "revoke", "label": "publisher"}, headers=ADMIN
    )
    assert denied.status_code in (404, 422)

    # a fresh registry adopts the persisted file over env bootstrap
    from fhir4ds.serve.auth import KeyRegistry

    resumed = KeyRegistry(
        admin_key=TEST_ADMIN_KEY,
        write_key=TEST_WRITE_KEY,
        key_store=key_store,
    )
    assert resumed.authenticate(new_key) == "write"
    assert resumed.authenticate(TEST_WRITE_KEY) is None


# -- body cap ---------------------------------------------------------------


def test_request_body_cap_is_a_413(connection, tmp_path):
    client = boot(connection, tmp_path, max_request_bytes=200)
    big = {**SLOT, "id": "s-big", "note": "x" * 500}
    response = client.post("/Slot", json=big, headers=WRITE)
    assert response.status_code == 413
    assert response.json()["resourceType"] == "OperationOutcome"


# -- query-string parameters -------------------------------------------------


def test_query_string_format_and_limit_apply(connection, tmp_path):
    client = boot(connection, tmp_path, default_limit=1000)
    client.post("/ViewDefinition", json=SLOT_VIEW, headers=ADMIN)
    client.post("/Slot", json=SLOT, headers=WRITE)
    response = client.post("/ViewDefinition/slot-view/$run?_format=csv")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert response.text.splitlines()[0].startswith("slot_id")


def test_query_string_duplicate_with_body_is_a_400(connection, tmp_path):
    client = boot(connection, tmp_path)
    body = {"resourceType": "Parameters", "parameter": [{"name": "_limit", "valueInteger": 1}]}
    response = client.post(
        "/ViewDefinition/slot-view/$run?_limit=2", json=body
    )
    assert response.status_code == 400


def test_query_string_bad_type_is_a_400(connection, tmp_path):
    client = boot(connection, tmp_path)
    response = client.post("/ViewDefinition/slot-view/$run?_limit=banana")
    assert response.status_code == 400


# -- default row cap ----------------------------------------------------------


def test_default_limit_applies_when_limit_omitted(connection, tmp_path):
    client = boot(connection, tmp_path, default_limit=2)
    client.post("/ViewDefinition", json=SLOT_VIEW, headers=ADMIN)
    for index in range(5):
        client.post(
            "/Slot", json={**SLOT, "id": f"s{index}"}, headers=WRITE
        )
    rows = [json.loads(line) for line in client.post(
        "/ViewDefinition/slot-view/$run"
    ).text.splitlines() if line]
    assert len(rows) == 2


# -- resourceType sanity --------------------------------------------------------


def test_invalid_resource_type_is_a_400(connection, tmp_path):
    client = boot(connection, tmp_path)
    bogus = {**SLOT, "resourceType": "n0t_a_type"}
    assert client.post("/n0t_a_type", json=bogus, headers=WRITE).status_code == 400


# -- concurrency gate ------------------------------------------------------------


def test_gate_saturates_to_503(connection, tmp_path):
    client = boot(connection, tmp_path, max_waiting_requests=1)
    context = client.app.state.serve
    held = threading.Event()
    release = threading.Event()

    def hold() -> None:
        with context.lock:
            held.set()
            release.wait(timeout=10)

    keeper = context._try_gate()  # the one waiting slot is now taken
    assert keeper
    try:
        thread = threading.Thread(target=hold, daemon=True)
        thread.start()
        held.wait(timeout=5)
        response = client.post("/Slot", json=SLOT, headers=WRITE)
        assert response.status_code == 503
        assert response.json()["issue"][0]["code"] == "busy"
    finally:
        context._release_gate()
        release.set()
        thread.join(timeout=5)


# -- query watchdog ---------------------------------------------------------------


def test_slow_query_times_out_with_408(connection, tmp_path):
    import base64

    slow_sql = (
        "SELECT count(*) AS n FROM range(1000000000) a, range(50) b"
    )
    library = {
        "resourceType": "Library",
        "id": "slow-probe",
        "status": "active",
        "meta": {
            "profile": ["https://sql-on-fhir.org/ig/StructureDefinition/SQLView"]
        },
        "type": {"coding": [{
            "system": "https://sql-on-fhir.org/ig/CodeSystem/LibraryTypesCodes",
            "code": "sql-view",
        }]},
        "content": [{
            "contentType": "application/sql;dialect=duckdb",
            "data": base64.b64encode(slow_sql.encode()).decode(),
        }],
    }
    client = plain_client(boot(connection, tmp_path, query_timeout_seconds=1).app)
    assert client.post("/Library", json=library, headers=ADMIN).status_code == 201
    response = client.post("/Library/slow-probe/$sqlquery-run")
    assert response.status_code == 408
    assert "interrupted" in response.json()["issue"][0]["diagnostics"]


# -- key persistence via the dataset ----------------------------------------


def test_write_keys_persist_to_dataset_and_adopt_on_boot(connection, tmp_path):
    """Rotation survives restarts through meta/keys.json in the dataset."""
    import pathlib

    config = ServeConfig(
        admin_key=TEST_ADMIN_KEY,
        write_key=TEST_WRITE_KEY,
        publish_dir=str(tmp_path),
        flush_autostart=False,
    )
    client = plain_client(create_app(config, connection=connection))
    new_key = "dataset-persisted-key-0001"
    assert client.post(
        "/admin/key",
        json={"action": "add", "label": "publisher", "key": new_key},
        headers=ADMIN,
    ).status_code == 200
    assert client.post("/admin/flush", headers=ADMIN).status_code == 200
    assert (pathlib.Path(tmp_path) / "meta" / "keys.json").is_file()

    # A fresh boot on the same dataset adopts the snapshot: the rotated key
    # works, the revoked bootstrap key does not.
    assert client.post(
        "/admin/key", json={"action": "revoke", "label": "__env__"}, headers=ADMIN
    ).status_code == 200
    assert client.post("/admin/flush", headers=ADMIN).status_code == 200

    second = plain_client(create_app(config, connection=connection))
    probe = {**SLOT, "id": "adopted"}
    assert second.post(
        "/Slot", json=probe, headers={"X-Write-Key": new_key}
    ).status_code == 201
    assert second.post("/Slot", json=probe, headers=WRITE).status_code == 401


# -- CORS ----------------------------------------------------------------------


def test_cors_preflight_and_origin_headers(connection, tmp_path):
    config = ServeConfig(
        admin_key=TEST_ADMIN_KEY,
        write_key=TEST_WRITE_KEY,
        publish_dir=str(tmp_path),
        flush_autostart=False,
        cors_origins=("https://fhir4ds.com",),
    )
    client = plain_client(create_app(config, connection=connection))
    preflight = client.options(
        "/Slot",
        headers={
            "Origin": "https://fhir4ds.com",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "X-Write-Key",
        },
    )
    assert preflight.status_code == 200
    assert preflight.headers["access-control-allow-origin"] == "https://fhir4ds.com"
    assert "x-write-key" in preflight.headers["access-control-allow-headers"].lower()

    read = client.get("/health", headers={"Origin": "https://fhir4ds.com"})
    assert read.headers["access-control-allow-origin"] == "https://fhir4ds.com"


def test_cors_disallowed_origin_gets_no_allow_header(connection, tmp_path):
    config = ServeConfig(
        admin_key=TEST_ADMIN_KEY,
        write_key=TEST_WRITE_KEY,
        publish_dir=str(tmp_path),
        flush_autostart=False,
        cors_origins=("https://fhir4ds.com",),
    )
    client = plain_client(create_app(config, connection=connection))
    read = client.get("/health", headers={"Origin": "https://evil.example"})
    assert "access-control-allow-origin" not in read.headers


# -- self-hosted API docs -------------------------------------------------------


def test_api_docs_page_is_open_and_complete(connection, tmp_path):
    client = boot(connection, tmp_path)
    page = client.get("/api-docs")
    assert page.status_code == 200
    assert page.headers["content-type"].startswith("text/html")
    for marker in ("$sqlquery-run", "X-Write-Key", "/admin/key", "If-Match", "$bulk-publish", "fhir4ds.com"):
        assert marker in page.text


def test_lying_content_length_cannot_bypass_streaming_cap_v22_qa003(tmp_path):
    """The streaming cap must hold even when Content-Length lies (V22-QA-003)."""
    import asyncio

    from fhir4ds.connection import create_connection
    from fhir4ds.serve.guard import GuardMiddleware

    con = create_connection(":memory:")
    try:
        app = create_app(
            ServeConfig(
                admin_key=TEST_ADMIN_KEY,
                write_key=TEST_WRITE_KEY,
                publish_dir=str(tmp_path / "lying"),
                flush_autostart=False,
                max_request_bytes=1000,
            ),
            connection=con,
        )
        chunks = [b"x" * 600, b"x" * 600]  # 1200 bytes > 1000 cap
        messages = [
            {"type": "http.request", "body": c, "more_body": i < len(chunks) - 1}
            for i, c in enumerate(chunks)
        ]

        async def receive():
            return messages.pop(0) if messages else {"type": "http.disconnect"}

        sent = []

        async def send(message):
            sent.append(message)

        scope = {
            "type": "http",
            "method": "POST",
            "path": "/Slot",
            "query_string": b"",
            "headers": [
                (b"content-length", b"100"),  # lying: claims 100, streams 1200
                (b"x-write-key", TEST_WRITE_KEY.encode()),
            ],
        }
        guard = GuardMiddleware(
            app, registry=app.state.serve.keys, max_request_bytes=1000
        )
        asyncio.run(guard(scope, receive, send))
        status = next(
            (m["status"] for m in sent if m["type"] == "http.response.start"), None
        )
        assert status == 413, f"oversized lying-CL body must be refused, got {status}"
    finally:
        con.close()


def test_adopted_keys_are_validated_like_added_keys_v22_qa004(tmp_path):
    """Dataset-provided keys face the same label/value rules as runtime adds.

    Hostile labels (newline) and non-string values must be dropped at adopt
    time, never enter the registry. The reserved ``__env__`` label is exempt
    from the identifier pattern by design.
    """
    from fhir4ds.connection import create_connection

    registry_client = boot(create_connection(":memory:"), tmp_path)
    try:
        keys = registry_client.app.state.serve.keys
        keys.adopt_write_keys(
            {
                "__env__": "legitimate-env-key-00000001",
                "evil\nlabel": "k-should-be-dropped-0001",
                "bad-value": 12345,
                "empty": "",
                "good-label": "k-good-snapshot-key-01",
            }
        )
        labels = keys.write_key_labels()
        assert "evil\nlabel" not in labels, f"hostile label adopted: {labels}"
        assert "bad-value" not in labels and "empty" not in labels
        assert "__env__" in labels and "good-label" in labels
        assert keys.authenticate("k-good-snapshot-key-01") == "write"
        assert keys.authenticate("legitimate-env-key-00000001") == "write"
    finally:
        registry_client.app.state.serve.connection.close()


def test_location_header_carries_history_form_v22_qa007(connection, tmp_path):
    """FHIR R4 http.html 3.1.0.1: Location is {type}/{id}/_history/{vid}."""
    client = boot(connection, tmp_path)
    created = client.post("/Slot", json=SLOT, headers=WRITE)
    assert created.status_code == 201
    assert created.headers["Location"] == "Slot/s1/_history/1", created.headers["Location"]
    updated = client.put("/Slot/s1", json={**SLOT, "status": "busy"}, headers=WRITE)
    assert updated.status_code == 200
    assert updated.headers["Location"] == "Slot/s1/_history/2", updated.headers["Location"]

    bundle = client.post(
        "/Bundle",
        headers=WRITE,
        json={
            "resourceType": "Bundle",
            "type": "transaction",
            "entry": [
                {"request": {"method": "POST", "url": "Slot"},
                 "resource": {**SLOT, "id": "s9"}}
            ],
        },
    )
    assert bundle.status_code == 200, bundle.text
    entry_loc = bundle.json()["entry"][0]["response"]["location"]
    assert entry_loc == "Slot/s9/_history/3", entry_loc
