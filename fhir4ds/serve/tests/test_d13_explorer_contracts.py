"""D13 EXPLORER (v0.0.26) — serve HTTP-surface adversarial contracts.

Red-first regressions for the two defects found by the EXPLORER fuzz battery
(``.temp/qa/d13_explorer_v0026/``):

* QA-D13E-001 — malformed bodies that fail body *reading* (invalid UTF-8,
  deep-nesting ``RecursionError``) were answered with FastAPI's bare
  ``{"detail": "There was an error parsing the body"}`` instead of a FHIR
  ``OperationOutcome``. Every error this surface emits is an OperationOutcome
  (``app.py`` contract); the missing piece was an ``HTTPException`` handler.
* QA-D13E-002 — the guard's streaming body cap SENT the 413 deny and then
  returned ``None`` from ``receive()``, so the downstream app kept running and
  emitted a SECOND response (double ``http.response.start``; the second body
  was itself a bare ``{"detail": ...}``). One request, exactly one response.
"""

from __future__ import annotations

import asyncio
import json

import pytest
from fastapi.testclient import TestClient

from fhir4ds.connection import create_connection
from fhir4ds.serve.app import create_app
from fhir4ds.serve.config import ServeConfig

from ._helpers import TEST_ADMIN_KEY, TEST_WRITE_KEY


def _client(**cfg) -> TestClient:
    connection = create_connection(":memory:")
    config = ServeConfig(
        admin_key=TEST_ADMIN_KEY,
        write_key=TEST_WRITE_KEY,
        writes_enabled=True,
        flush_autostart=False,
        **cfg,
    )
    app = create_app(config, connection=connection)
    client = TestClient(app)
    client._fhir4ds_connection = connection  # keep alive  # noqa: SLF001
    return client


HEADERS = {
    "X-Admin-Key": TEST_ADMIN_KEY,
    "X-Write-Key": TEST_WRITE_KEY,
    "Content-Type": "application/fhir+json",
}


class TestBodyReadErrorsAreOperationOutcomesD13Explorer:
    """QA-D13E-001: body-READ failures must be OperationOutcomes too."""

    @pytest.mark.parametrize("path", ["/Patient", "/Bundle"])
    @pytest.mark.parametrize(
        "label",
        ["invalid-utf8", "deep-nesting"],
    )
    def test_body_read_failure_is_an_outcome(self, path: str, label: str) -> None:
        client = _client()
        if label == "invalid-utf8":
            payload = b"\x00\xff\xfe garbage"
        else:
            payload = (
                b'{"resourceType":"Patient","x":' + b'{"a":' * 1500 + b"1" + b"}" * 1500 + b"}"
            )
        response = client.post(path, content=payload, headers=HEADERS)
        assert response.status_code == 400, response.text
        body = response.json()
        assert isinstance(body, dict), body
        assert body.get("resourceType") == "OperationOutcome", body
        assert "detail" not in body

    def test_registry_route_body_read_failure_is_an_outcome(self) -> None:
        client = _client()
        response = client.post(
            "/Library",
            content=b"\x00\xff\xfe",
            headers={k: v for k, v in HEADERS.items() if k != "X-Write-Key"},
        )
        assert response.status_code == 400, response.text
        assert response.json().get("resourceType") == "OperationOutcome", response.text


class TestCorruptStateSeqBootD13Explorer:
    """QA-D13E-003: a wrong-typed ``seq`` in meta/state.json must not kill boot.

    ``TreeStore.current_seq`` raised a raw ``ValueError`` from ``int("x")``,
    which escaped ``create_app`` entirely — one corrupt value in a small
    metadata file took the whole surface down (no degradation, no
    rehydration). The per-part corruption doctrine ("boot must not take the
    surface down") applies to the state file too: fall back to 0 with a
    warning; the QA-D13H-003 ``advance_to`` floor after rehydration keeps
    ``_seq`` collision-free even when the state file under-reports.
    """

    def _seed_dataset(self, tmp_path) -> str:
        import json as _json

        publish_dir = tmp_path / "pub"
        publish_dir.mkdir()
        connection = create_connection(":memory:")
        config = ServeConfig(
            admin_key=TEST_ADMIN_KEY,
            write_key=TEST_WRITE_KEY,
            writes_enabled=True,
            publish_dir=str(publish_dir),
            flush_autostart=False,
        )
        app = create_app(config, connection=connection)
        client = TestClient(app)
        headers = {
            "X-Admin-Key": TEST_ADMIN_KEY,
            "X-Write-Key": TEST_WRITE_KEY,
            "Content-Type": "application/fhir+json",
        }
        for i in range(3):
            response = client.post(
                "/Patient",
                content=json.dumps({"resourceType": "Patient", "id": f"s{i}"}),
                headers=headers,
            )
            assert response.status_code == 201, response.text
        assert client.post("/admin/flush", headers=headers).status_code == 200
        connection.close()
        (publish_dir / "meta" / "state.json").write_text(
            _json.dumps({"seq": "not-a-number", "revision": "r"})
        )
        return str(publish_dir)

    def test_boot_survives_corrupt_state_seq(self, tmp_path) -> None:
        publish_dir = self._seed_dataset(tmp_path)
        connection = create_connection(":memory:")
        try:
            config = ServeConfig(
                admin_key=TEST_ADMIN_KEY,
                write_key=TEST_WRITE_KEY,
                writes_enabled=True,
                publish_dir=publish_dir,
                flush_autostart=False,
            )
            app = create_app(config, connection=connection)  # must not raise
            client = TestClient(app)
            response = client.get("/Patient", params={"_count": 100})
            assert response.status_code == 200
            assert response.json()["total"] == 3  # parts rehydrated
        finally:
            connection.close()

    def test_write_after_corrupt_state_seq_is_unique(self, tmp_path) -> None:
        publish_dir = self._seed_dataset(tmp_path)
        connection = create_connection(":memory:")
        try:
            config = ServeConfig(
                admin_key=TEST_ADMIN_KEY,
                write_key=TEST_WRITE_KEY,
                writes_enabled=True,
                publish_dir=publish_dir,
                flush_autostart=False,
            )
            app = create_app(config, connection=connection)
            client = TestClient(app)
            headers = {
                "X-Admin-Key": TEST_ADMIN_KEY,
                "X-Write-Key": TEST_WRITE_KEY,
                "Content-Type": "application/fhir+json",
            }
            response = client.post(
                "/Patient",
                content=json.dumps({"resourceType": "Patient", "id": "new"}),
                headers=headers,
            )
            assert response.status_code == 201, response.text
            # the new version must not collide with any rehydrated _seq
            new_seq = int(response.headers["ETag"].strip('W/"'))
            history = client.get("/Patient/s0/_history").json()
            assert new_seq not in {
                int(e["response"]["etag"].strip('W/"')) for e in history["entry"]
            }
        finally:
            connection.close()

    def test_tree_store_current_seq_tolerates_bad_value(self, tmp_path) -> None:
        from fhir4ds.serve.store import TreeStore

        store = TreeStore(tmp_path / "tree")
        (tmp_path / "tree" / "meta").mkdir(parents=True, exist_ok=True)
        (tmp_path / "tree" / "meta" / "state.json").write_text(
            '{"seq": ["x"], "revision": 1}'
        )
        assert store.current_seq() == 0  # typed fallback, never a crash


class TestNonAsciiKeyHeaderD13Explorer:
    """QA-D13E-004: a non-ASCII key value must get the uniform 401.

    ``hmac.compare_digest`` on two *strings* raises
    ``TypeError: comparing strings with non-ASCII characters is not supported``.
    The guard decodes header bytes as latin-1, so any non-ASCII key header
    reached ``authenticate`` and crashed the request with an unhandled
    exception instead of the uniform 401. Compare as UTF-8 bytes.
    """

    def test_non_ascii_key_header_is_uniform_401(self) -> None:
        import asyncio

        client = _client()
        scope = {
            "type": "http",
            "http_version": "1.1",
            "method": "POST",
            "path": "/Patient",
            "raw_path": b"/Patient",
            "query_string": b"",
            "headers": [
                (b"content-type", b"application/fhir+json"),
                (b"x-write-key", "ключ-ключ-ключ".encode()),
            ],
            "client": ("127.0.0.1", 1),
            "scheme": "http",
            "server": ("t", 80),
            "root_path": "",
            "state": {},
        }
        body = json.dumps({"resourceType": "Patient", "id": "rawkey"}).encode()
        messages = [{"type": "http.request", "body": body, "more_body": False}]
        sent: list[dict] = []

        async def receive():
            return messages.pop(0) if messages else {"type": "http.disconnect"}

        async def send(message):
            sent.append(message)

        asyncio.run(client.app(scope, receive, send))
        starts = [m for m in sent if m["type"] == "http.response.start"]
        assert len(starts) == 1, starts
        assert starts[0]["status"] == 401, starts[0]

    def test_registry_authenticate_non_ascii_none(self) -> None:
        from fhir4ds.serve.auth import KeyRegistry

        registry = KeyRegistry(admin_key="a" * 24, write_key="b" * 24)
        assert registry.authenticate("ключ") is None  # no crash, no grant
    def test_absurd_expiry_rejected_typed(self) -> None:
        """QA-D13E-005: an unrepresentable expiry must be a typed 422.

        ``expires_in_days=1e12`` produced a deadline beyond ``datetime``'s
        range: the key was ADDED (200 path) and then every ``/admin/key``
        response crashed with ``OSError: [Errno 75]`` from
        ``write_key_info`` → persistent 500s on the key-management surface.
        """
        client = _client()
        response = client.post(
            "/admin/key",
            content=json.dumps(
                {"action": "add", "label": "far", "key": "k" * 20,
                 "expires_in_days": 1e12}
            ),
            headers={"X-Admin-Key": TEST_ADMIN_KEY,
                     "Content-Type": "application/fhir+json"},
        )
        assert response.status_code == 422, response.text
        assert response.json().get("resourceType") == "OperationOutcome", response.text
        # the surface stays healthy afterwards
        follow = client.post(
            "/admin/key",
            content=json.dumps({"action": "add", "label": "near", "key": "n" * 20,
                                "expires_in_days": 365}),
            headers={"X-Admin-Key": TEST_ADMIN_KEY,
                     "Content-Type": "application/fhir+json"},
        )
        assert follow.status_code == 200, follow.text

    def test_snapshot_with_unrepresentable_deadline_drops_key(self) -> None:
        """A tampered keys.json with an unrepresentable deadline adopts nothing."""
        from fhir4ds.serve.auth import KeyRegistry

        registry = KeyRegistry(admin_key="a" * 24, write_key="b" * 24)
        registry.adopt_write_keys(
            {"write_keys": {"tampered": "t" * 24},
             "expirations": {"tampered": 1e18}}
        )
        assert registry.authenticate("t" * 24) is None
        assert "tampered" not in registry.write_key_labels()


class TestStreamingCapSingleResponseD13Explorer:
    """QA-D13E-002: the streaming cap answers once, and only with the 413."""

    def _run(self, chunks: list[bytes], content_length: bytes | None) -> dict:
        connection = create_connection(":memory:")
        config = ServeConfig(
            admin_key=TEST_ADMIN_KEY,
            write_key=TEST_WRITE_KEY,
            writes_enabled=True,
            max_request_bytes=1000,
            flush_autostart=False,
        )
        app = create_app(config, connection=connection)
        headers = [
            (b"content-type", b"application/fhir+json"),
            (b"x-write-key", TEST_WRITE_KEY.encode()),
        ]
        if content_length is not None:
            headers.append((b"content-length", content_length))
        messages = [
            {"type": "http.request", "body": chunk, "more_body": i < len(chunks) - 1}
            for i, chunk in enumerate(chunks)
        ]

        async def receive():
            return messages.pop(0) if messages else {"type": "http.disconnect"}

        sent: list[dict] = []

        async def send(message):
            sent.append(message)

        scope = {
            "type": "http",
            "http_version": "1.1",
            "method": "POST",
            "path": "/Patient",
            "raw_path": b"/Patient",
            "query_string": b"",
            "headers": headers,
            "client": ("127.0.0.1", 1),
            "scheme": "http",
            "server": ("t", 80),
            "root_path": "",
            "state": {},
        }
        asyncio.run(app(scope, receive, send))
        connection.close()
        return {
            "starts": [m for m in sent if m["type"] == "http.response.start"],
            "bodies": [m for m in sent if m["type"] == "http.response.body"],
        }

    def test_chunked_over_cap_answers_exactly_one_413(self) -> None:
        result = self._run([b"x" * 600, b"x" * 600], content_length=None)
        assert len(result["starts"]) == 1, result["starts"]
        assert result["starts"][0]["status"] == 413
        body = b"".join(m.get("body", b"") for m in result["bodies"])
        assert json.loads(body)["resourceType"] == "OperationOutcome"

    def test_lying_content_length_answers_exactly_one_413(self) -> None:
        result = self._run([b"x" * 2000], content_length=b"10")
        assert len(result["starts"]) == 1, result["starts"]
        assert result["starts"][0]["status"] == 413

    def test_under_cap_body_passes_through(self) -> None:
        body = json.dumps({"resourceType": "Patient", "id": "raw-ok"}).encode()
        result = self._run([body[:40], body[40:]], content_length=None)
        assert len(result["starts"]) == 1
        assert result["starts"][0]["status"] == 201
