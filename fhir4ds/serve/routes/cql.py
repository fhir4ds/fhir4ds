"""The FHIR ``$cql`` conformance facade, mounted onto the serve app.

The facade implementation lives in :mod:`fhir4ds.cql.fhir_server` and is used
verbatim: ``handle_cql_operation`` owns request parsing, evaluation, and the
``Parameters`` / ``OperationOutcome`` bodies that ``cqframework/cql-tests-runner``
depends on. Nothing in that package is modified or re-implemented here. This
module adds exactly three things:

* an ASGI route (``POST /fhir/$cql``) that hands the decoded body to the same
  ``handle_cql_operation`` the stdlib facade uses, and serializes the response
  with the facade's own encoder so the two servers answer byte-identically;
* a tiny ASGI middleware that buffers that path's raw body. FastAPI parses
  ``application/json`` / ``application/*+json`` bodies before a handler runs and
  answers malformed JSON in its own words; the parity contract needs the
  facade's wording, so this route declares no body parameter and decodes the
  buffered bytes itself (the handler stays a plain ``def``);
* the matching CapabilityStatement declaration, applied by :func:`mount`, so
  ``/metadata`` advertises ``$cql`` exactly when the route exists.

Parity contract (pinned by ``tests/test_cql_facade.py``): for the same request
body, ``fhir4ds cql-server`` and ``fhir4ds serve`` return the same status code
and the same body.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from fastapi import APIRouter, FastAPI, Request
from starlette.responses import Response

from fhir4ds.cql.fhir_server.operations import handle_cql_operation
from fhir4ds.cql.fhir_server.parameters import dumps_fhir_json, operation_outcome
from fhir4ds.cql.fhir_server.types import CQLErrorCategory, CQLServerConfig

from ..config import ServeConfig, context_for
from ..metadata import cap_operation

logger = logging.getLogger(__name__)

#: Operation name advertised in the CapabilityStatement.
CQL_OPERATION = "cql"

#: Definition canonical the facade advertises.
#:
#: This mirrors the CapabilityStatement built by the stdlib facade
#: (``fhir4ds/cql/fhir_server/app.py::_metadata``). It is duplicated rather than
#: imported because importing a private helper out of a package this layer must
#: not modify is worse than one pinned string; the parity test compares both
#: servers' ``/metadata`` documents, so drift fails the suite.
CQL_OPERATION_DEFINITION = (
    "https://build.fhir.org/ig/HL7/cql-ig/en/OperationDefinition-cql-cql.html"
)

#: FHIR base path the facade answers on (``CQLServerConfig.base_path``).
CQL_BASE_PATH = "/fhir"

#: The one path this surface mounts (the facade itself also accepts ``/$cql``).
CQL_PATH = f"{CQL_BASE_PATH}/$cql"

#: Scope key carrying the buffered raw body (see :class:`RawBodyCapture`).
RAW_BODY_SCOPE_KEY = "fhir4ds.raw_body"

FHIR_JSON = "application/fhir+json"


def facade_config(config: ServeConfig) -> CQLServerConfig:
    """Map serve settings onto the facade's own configuration object."""
    return CQLServerConfig(
        host=config.host,
        port=config.port,
        base_path=CQL_BASE_PATH,
        max_request_bytes=config.cql_max_request_bytes,
    )


class RawBodyCapture:
    """Buffer the raw body of the ``$cql`` path into ``scope["state"]``.

    Only that path is buffered; every other request streams through untouched.
    The buffered bytes are replayed to the inner app so the rest of the stack
    sees a normal request.
    """

    def __init__(self, app: Any, *, path: str) -> None:
        self.app = app
        self.path = path

    async def __call__(self, scope: Any, receive: Any, send: Any) -> None:
        if (
            scope.get("type") != "http"
            or scope.get("path") != self.path
            or scope.get("method", "").upper() != "POST"
        ):
            await self.app(scope, receive, send)
            return

        body = bytearray()
        while True:
            message = await receive()
            if message.get("type") == "http.disconnect":
                return
            body.extend(message.get("body", b""))
            if not message.get("more_body", False):
                break

        scope.setdefault("state", {})[RAW_BODY_SCOPE_KEY] = bytes(body)

        replayed = False

        async def replay() -> Any:
            nonlocal replayed
            if not replayed:
                replayed = True
                return {"type": "http.request", "body": bytes(body), "more_body": False}
            return {"type": "http.disconnect"}

        await self.app(scope, replay, send)


def build_router(config: ServeConfig) -> APIRouter:
    """Build the router serving ``POST /fhir/$cql``."""
    router = APIRouter(tags=["cql"])
    settings = facade_config(config)

    @router.post(
        CQL_PATH,
        summary="Evaluate a CQL expression ($cql)",
        response_class=Response,
        openapi_extra={
            "requestBody": {
                "required": True,
                "content": {
                    "application/fhir+json": {
                        "schema": {"$ref": "#/components/schemas/Parameters"}
                    }
                },
                "description": (
                    "FHIR Parameters carrying one 'expression' valueString, "
                    "exactly as cqframework/cql-tests-runner sends it."
                ),
            }
        },
    )
    def cql_operation(request: Request) -> Response:
        """Evaluate one CQL expression exactly as the ``cql-server`` facade does."""
        raw = request.scope.get("state", {}).get(RAW_BODY_SCOPE_KEY, b"")
        if len(raw) > settings.max_request_bytes:
            return _outcome(413, "Request body is too large")

        try:
            document = _decode(raw)
        except ValueError:
            return _outcome(400, "Request body must be valid JSON")

        status, payload = handle_cql_operation(
            document, facade_config(context_for(request).config)
        )
        return Response(
            content=dumps_fhir_json(payload),
            status_code=status,
            media_type=FHIR_JSON,
        )

    return router


def mount(app: FastAPI, config: ServeConfig) -> bool:
    """Attach the ``$cql`` route, its body middleware, and its capability.

    Returns whether the facade was mounted, so callers can log the decision.
    """
    router = build_router(config)
    _declare_capability(router)
    app.add_middleware(RawBodyCapture, path=CQL_PATH)
    app.include_router(router)
    return True


def _declare_capability(router: APIRouter) -> None:
    """Declare the ``$cql`` system operation on the router's endpoints."""
    decorator = cap_operation(
        operation=CQL_OPERATION,
        definition=CQL_OPERATION_DEFINITION,
        scope="system",
        documentation=(
            "Evaluate a CQL expression and return the result as a FHIR "
            "Parameters resource (CQL test-runner facade)."
        ),
    )
    for route in router.routes:
        endpoint = getattr(route, "endpoint", None)
        if endpoint is not None:
            decorator(endpoint)


def _decode(body: bytes) -> Any:
    """Decode a request body the way the facade's stdlib adapter does.

    An empty body stays ``None`` (the facade reports the missing parameters);
    malformed JSON raises ``ValueError`` so the caller can answer with the
    facade's own wording.
    """
    if not body:
        return None
    return json.loads(body.decode("utf-8"))


def _outcome(status_code: int, message: str) -> Response:
    """Build an ``OperationOutcome`` response using the facade's own helpers."""
    payload = operation_outcome(
        message=message,
        category=CQLErrorCategory.INVALID_REQUEST,
    )
    return Response(
        content=dumps_fhir_json(payload),
        status_code=status_code,
        media_type=FHIR_JSON,
    )


__all__ = [
    "CQL_BASE_PATH",
    "CQL_OPERATION",
    "CQL_OPERATION_DEFINITION",
    "CQL_PATH",
    "RAW_BODY_SCOPE_KEY",
    "RawBodyCapture",
    "build_router",
    "facade_config",
    "mount",
]
