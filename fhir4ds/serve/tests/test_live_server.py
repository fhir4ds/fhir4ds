"""Real-socket smoke test: the factory app served by uvicorn.

The TestClient exercises the ASGI app in-process; this test proves the same app
works behind a real HTTP server on a real socket (the ``fhir4ds serve`` path).
"""

from __future__ import annotations

import json
import socket
import threading
import time

import pytest

pytest.importorskip("uvicorn")
httpx = pytest.importorskip("httpx")

from ._helpers import SQLONFHIR_PARAMETERS, parameter_body, parameters  # noqa: E402


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def test_live_server_end_to_end(connection, store, tmp_path):
    import uvicorn

    from fhir4ds.serve.app import create_app

    from ._helpers import serve_config

    app = create_app(serve_config(tmp_path), connection=connection)
    port = _free_port()
    server = uvicorn.Server(
        uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    try:
        deadline = time.monotonic() + 30
        while not server.started:
            if not thread.is_alive():
                pytest.fail("uvicorn exited before it started serving")
            if time.monotonic() > deadline:
                pytest.fail("uvicorn did not start within 30s")
            time.sleep(0.05)

        with httpx.Client(base_url=f"http://127.0.0.1:{port}", timeout=60) as client:
            health = client.get("/health")
            assert health.status_code == 200
            assert health.json()["status"] == "ok"

            metadata = client.get("/metadata")
            assert metadata.status_code == 200
            document = metadata.json()
            assert document["fhirVersion"] == "4.0.1"
            advertised = {
                entry["type"]: {op["name"] for op in entry["operation"]}
                for entry in document["rest"][0]["resource"]
            }
            assert advertised == {
                "Library": {"sqlquery-run"},
                "ViewDefinition": {"run"},
            }

            run = client.post(
                "/Library/SqlOnFhirExample/$sqlquery-run",
                json=parameter_body(dict(SQLONFHIR_PARAMETERS)),
            )
            assert run.status_code == 200
            assert run.headers["content-type"].startswith("application/x-ndjson")
            rows = [json.loads(line) for line in run.text.strip().splitlines()]
            assert len(rows) == 2

            bad = client.post("/Library/SqlOnFhirExample/$sqlquery-run", json=parameters())
            assert bad.status_code == 400
            assert bad.json()["resourceType"] == "OperationOutcome"
    finally:
        server.should_exit = True
        thread.join(timeout=20)
