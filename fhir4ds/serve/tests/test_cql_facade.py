"""The ``$cql`` facade mount: behaviour and parity with ``fhir4ds cql-server``.

The facade itself lives in ``fhir4ds/cql/fhir_server`` and must stay
byte-identical, so every assertion here is black-box: the same request body is
posted to the stdlib facade server (started on an ephemeral port) and to the
serve app, and the two answers are compared. That is the contract
``cqframework/cql-tests-runner`` depends on.
"""

from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request

import pytest
from fastapi.testclient import TestClient

from fhir4ds.cql.fhir_server import CQLServerConfig, create_http_server
from fhir4ds.serve.config import ServeConfig
from fhir4ds.serve.routes.cql import (
    CQL_OPERATION,
    CQL_OPERATION_DEFINITION,
    CQL_PATH,
    facade_config,
)


def cql_body(expression: str) -> dict:
    """A minimal ``$cql`` request: one ``expression`` valueString."""
    return {
        "resourceType": "Parameters",
        "parameter": [{"name": "expression", "valueString": expression}],
    }


@pytest.fixture(scope="module")
def facade_server():
    """The stdlib ``$cql`` facade on an ephemeral port, for parity comparisons."""
    config = CQLServerConfig(host="127.0.0.1", port=0)
    server = create_http_server(config)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address[:2]
    try:
        yield f"http://{host}:{port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def post_raw(url: str, raw: bytes | None) -> tuple[int, dict]:
    """POST a raw body and return ``(status, decoded JSON)``."""
    request = urllib.request.Request(
        url,
        data=raw if raw is not None else b"",
        headers={"Content-Type": "application/fhir+json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        return error.code, json.loads(error.read().decode("utf-8"))


def post_client(client: TestClient, raw: bytes | None) -> tuple[int, dict]:
    """POST the same raw body through the ASGI app."""
    response = client.post(
        CQL_PATH,
        content=raw if raw is not None else b"",
        headers={"Content-Type": "application/fhir+json"},
    )
    return response.status_code, response.json()


def get_json(url: str) -> dict:
    """GET a JSON document."""
    with urllib.request.urlopen(url, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


# -- behaviour --------------------------------------------------------------


def test_cql_mount_path_matches_the_facade_config():
    config = facade_config(ServeConfig())
    assert CQL_PATH in config.cql_paths
    assert CQL_PATH == "/fhir/$cql"


def test_cql_evaluates_an_expression(client):
    response = client.post(CQL_PATH, json=cql_body("1 + 1"))
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/fhir+json")
    document = response.json()
    assert document["resourceType"] == "Parameters"
    assert document["parameter"][0]["name"] == "return"
    assert document["parameter"][0]["valueInteger"] == 2


def test_cql_rejects_an_oversized_body(connection, store):
    """The facade's request cap applies on this surface too."""
    from fhir4ds.serve.app import create_app

    app = create_app(
        ServeConfig(cql_max_request_bytes=64), connection=connection
    )
    client = TestClient(app)
    response = client.post(CQL_PATH, json=cql_body("'" + "x" * 200 + "'"))
    assert response.status_code == 413
    assert response.json()["resourceType"] == "OperationOutcome"


# -- parity with the stdlib facade ------------------------------------------


PARITY_BODIES = {
    "integer expression": json.dumps(cql_body("1 + 1")),
    "string expression": json.dumps(cql_body("'hello'")),
    "boolean expression": json.dumps(cql_body("2 > 1")),
    "parse error": json.dumps(cql_body("1 +")),
    "missing expression": json.dumps({"resourceType": "Parameters", "parameter": []}),
    "two expressions": json.dumps(
        {
            "resourceType": "Parameters",
            "parameter": [
                {"name": "expression", "valueString": "1"},
                {"name": "expression", "valueString": "2"},
            ],
        }
    ),
    "unsupported top-level parameter": json.dumps(
        {
            "resourceType": "Parameters",
            "parameter": [
                {"name": "expression", "valueString": "1"},
                {"name": "library", "valueString": "Library/x"},
            ],
        }
    ),
    "malformed json": "this is not json",
    "json array body": "[1, 2, 3]",
    "empty body": "",
}


@pytest.mark.parametrize("name", sorted(PARITY_BODIES))
def test_cql_parity_with_stdlib_facade(name, client, facade_server):
    raw = PARITY_BODIES[name].encode("utf-8")

    facade_status, facade_body = post_raw(f"{facade_server}/fhir/$cql", raw)
    serve_status, serve_body = post_client(client, raw)

    assert serve_status == facade_status, f"{name}: status diverged"
    assert serve_body == facade_body, f"{name}: body diverged"


# -- capability statement ---------------------------------------------------


def _operations(document: dict) -> list[dict]:
    return document["rest"][0].get("operation", [])


def test_metadata_declares_the_cql_operation(client):
    document = client.get("/metadata").json()
    cql = [entry for entry in _operations(document) if entry["name"] == CQL_OPERATION]
    assert len(cql) == 1
    assert cql[0]["definition"] == CQL_OPERATION_DEFINITION


def test_cql_definition_matches_the_stdlib_facade_metadata(client, facade_server):
    """Both servers must advertise the same canonical for ``$cql``."""
    facade_document = get_json(f"{facade_server}/metadata")
    facade_cql = [
        entry for entry in _operations(facade_document) if entry["name"] == CQL_OPERATION
    ]
    serve_document = client.get("/metadata").json()
    serve_cql = [
        entry for entry in _operations(serve_document) if entry["name"] == CQL_OPERATION
    ]

    assert facade_cql and serve_cql
    assert serve_cql[0]["definition"] == facade_cql[0]["definition"]


def test_cql_is_not_advertised_when_the_facade_is_disabled(connection, store):
    from fhir4ds.serve.app import create_app

    app = create_app(ServeConfig(cql_facade=False), connection=connection)
    client = TestClient(app)

    names = {entry["name"] for entry in _operations(client.get("/metadata").json())}
    assert CQL_OPERATION not in names
    assert client.post(CQL_PATH, json=cql_body("1 + 1")).status_code == 404
