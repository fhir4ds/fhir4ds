"""Dependency-free HTTP adapter for the FHIR ``$cql`` facade."""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from .operations import handle_cql_operation
from .parameters import dumps_fhir_json, operation_outcome
from .types import CQLServerConfig, CQLErrorCategory


class CQLHTTPServer(ThreadingHTTPServer):
    """HTTP server carrying facade configuration."""

    config: CQLServerConfig


def create_http_server(config: CQLServerConfig | None = None) -> CQLHTTPServer:
    """Create a local HTTP server for runner ``$cql`` requests."""
    config = config or CQLServerConfig()

    class Handler(_CQLRequestHandler):
        pass

    server = CQLHTTPServer((config.host, config.port), Handler)
    server.config = config
    return server


def serve(config: CQLServerConfig | None = None) -> None:
    """Serve the facade until interrupted."""
    server = create_http_server(config)
    try:
        host, port = server.server_address[:2]
        print(f"FHIR4DS CQL server listening on http://{host}:{port}")  # noqa: T201
        server.serve_forever()
    finally:
        server.server_close()


class _CQLRequestHandler(BaseHTTPRequestHandler):
    server: CQLHTTPServer

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/health":
            self._write_json(200, {"status": "ok"})
            return
        if self.path == "/metadata":
            self._write_json(200, _metadata(self.server.config))
            return
        self._write_json(
            404,
            operation_outcome(
                message="Endpoint not found",
                category=CQLErrorCategory.INVALID_REQUEST,
            ),
        )

    def do_POST(self) -> None:  # noqa: N802
        if self.path not in self.server.config.cql_paths:
            self._write_json(
                404,
                operation_outcome(
                    message="Endpoint not found",
                    category=CQLErrorCategory.INVALID_REQUEST,
                ),
            )
            return
        try:
            size = int(self.headers.get("Content-Length", "0"))
            if size > self.server.config.max_request_bytes:
                self._write_json(
                    413,
                    operation_outcome(
                        message="Request body is too large",
                        category=CQLErrorCategory.INVALID_REQUEST,
                    ),
                )
                return
            raw = self.rfile.read(size)
            body = json.loads(raw.decode("utf-8")) if raw else None
        except (OSError, UnicodeDecodeError, ValueError):
            self._write_json(
                400,
                operation_outcome(
                    message="Request body must be valid JSON",
                    category=CQLErrorCategory.INVALID_REQUEST,
                ),
            )
            return
        status, response = handle_cql_operation(body, self.server.config)
        self._write_json(status, response)

    def log_message(self, format: str, *args: Any) -> None:
        if self.server.config.debug:
            super().log_message(format, *args)

    def _write_json(self, status: int, body: dict[str, Any]) -> None:
        data = dumps_fhir_json(body)
        self.send_response(status)
        self.send_header("Content-Type", "application/fhir+json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def _metadata(config: CQLServerConfig) -> dict[str, Any]:
    return {
        "resourceType": "CapabilityStatement",
        "status": "active",
        "kind": "instance",
        "software": {"name": "fhir4ds CQL facade"},
        "fhirVersion": "4.0.1",
        "rest": [
            {
                "mode": "server",
                "operation": [
                    {
                        "name": "cql",
                        "definition": "https://build.fhir.org/ig/HL7/cql-ig/en/OperationDefinition-cql-cql.html",
                    }
                ],
            }
        ],
        "implementation": {"url": f"http://{config.host}:{config.port}{config.base_path}"},
    }
