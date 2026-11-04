"""ASGI guard: request-size cap and API-key tier enforcement.

One pure-ASGI middleware wraps the app so both checks run before routing:

* **Body cap** — requests whose ``Content-Length`` exceeds the configured
  maximum (or whose streaming body exceeds it despite the header) receive a
  ``413`` FHIR ``OperationOutcome``.
* **Auth tiers** — see :mod:`fhir4ds.serve.auth`. Open by default for reads
  and stored-definition operations; write tier for FHIR writes and
  ``/admin/flush``; admin tier for definition management, key management,
  inline-resource operations and the ``$cql`` facade. Fail-closed: when a
  tier has no key configured, its routes answer ``401`` for everyone.

Tier rules live here, expressed as (method, path-pattern) predicates, because
they must hold no matter which router handles the path.
"""

from __future__ import annotations

import json
from typing import Any

from .auth import ROLE_ADMIN, ROLE_WRITE

FHIR_JSON = "application/fhir+json"

#: Substrings identifying admin-tier paths (checked with `in` on the path).
_ADMIN_PATH_MARKERS = (
    "/admin/key",
    "/fhir/$cql",
    "/ViewDefinition/$run",  # type-level: accepts inline viewResource
    "/Library/$sqlquery-run",  # type-level: accepts inline queryResource
)

_WRITE_METHODS = ("POST", "PUT", "DELETE")

#: Paths that are writes-in-disguise but POST-only operation routes.
_OPEN_POST_SUFFIXES = ("/$run", "/$sqlquery-run")


def _outcome(status: int, code: str, message: str) -> bytes:
    body = {
        "resourceType": "OperationOutcome",
        "issue": [{"severity": "error", "code": code, "diagnostics": message}],
    }
    return json.dumps(body).encode("utf-8")


def required_role(method: str, path: str) -> str | None:
    """The tier a request needs, or ``None`` when it is open.

    Rules, in order:

    1. Definition management (``POST``/``PUT``/``DELETE`` on ``/Library`` or
       ``/ViewDefinition`` collection endpoints) — admin.
    2. Admin-marked paths (key management, ``$cql``, inline-resource
       operations) — admin, whatever the method.
    3. ``GET``/``HEAD`` — open (admin paths already matched above).
    4. Mutation methods — write tier, except the stored-definition operation
       suffixes on instance paths, which are open.
    """
    parts = [segment for segment in path.split("/") if segment]
    resource_type = parts[0] if parts else ""
    is_definition_endpoint = resource_type in ("Library", "ViewDefinition")

    if is_definition_endpoint and method in _WRITE_METHODS:
        # Type-level operation POSTs (inline resources) are admin via rule 2;
        # instance-level ``$run``/``$sqlquery-run`` are open via rule 4.
        if not any(path.endswith(suffix) for suffix in _OPEN_POST_SUFFIXES):
            return ROLE_ADMIN

    if any(marker in path for marker in _ADMIN_PATH_MARKERS) or path == "/$sqlquery-run":
        return ROLE_ADMIN

    if method in ("GET", "HEAD", "OPTIONS"):
        return None

    if method in _WRITE_METHODS:
        if any(path.endswith(suffix) for suffix in _OPEN_POST_SUFFIXES):
            return None
        return ROLE_WRITE

    return None


class GuardMiddleware:
    """Wrap an ASGI app with the body cap and tier enforcement."""

    def __init__(self, app: Any, *, registry: Any, max_request_bytes: int) -> None:
        self.app = app
        self._registry = registry
        self._max_bytes = int(max_request_bytes)

    async def __call__(self, scope: Any, receive: Any, send: Any) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        method = scope.get("method", "GET")

        # Body cap: refuse oversized requests before reading them.
        for name, value in scope.get("headers", []):
            if name == b"content-length":
                try:
                    if int(value) > self._max_bytes:
                        return await self._deny(
                            send, 413, "too-costly", "request body exceeds the server limit"
                        )
                except ValueError:
                    return await self._deny(
                        send, 400, "structure", "invalid Content-Length header"
                    )
                break

        role = required_role(method, path)
        if role is not None:
            candidates = []
            for name, value in scope.get("headers", []):
                if name in (b"x-admin-key", b"x-write-key", b"authorization"):
                    candidates.append(value.decode("latin-1"))
            granted = None
            for candidate in candidates:
                outcome = self._registry.authenticate(_key_from_header(candidate))
                if outcome == ROLE_ADMIN:
                    granted = ROLE_ADMIN
                    break
                if outcome == ROLE_WRITE:
                    granted = ROLE_WRITE
            if granted != ROLE_ADMIN and granted != role:
                # Uniform 401: never reveal whether a key is valid-but-wrong-tier.
                return await self._deny(
                    send, 401, "login", "this operation requires an authorized key"
                )

        # Streaming cap: bodies without (or lying about) Content-Length.
        received: list[bytes] = []
        total = 0

        async def capped_receive() -> dict[str, Any]:
            nonlocal total
            message = await receive()
            if message["type"] == "http.request":
                total += len(message.get("body", b""))
                if total > self._max_bytes:
                    return await self._deny(
                        send, 413, "too-costly", "request body exceeds the server limit"
                    )
                received.append(message)
            return message

        # The streaming cap always applies: a lying Content-Length header
        # (claiming less than the body actually sent) must not bypass it.
        # Well-behaved requests pass through capped_receive untouched — it
        # forwards every message verbatim while under the cap.
        await self.app(scope, capped_receive, send)

    @staticmethod
    async def _deny(send: Any, status: int, code: str, message: str) -> None:
        body = _outcome(status, code, message)
        await send(
            {
                "type": "http.response.start",
                "status": status,
                "headers": [
                    (b"content-type", FHIR_JSON.encode("ascii")),
                    (b"content-length", str(len(body)).encode("ascii")),
                ],
            }
        )
        await send({"type": "http.response.body", "body": body})


def _key_from_header(header: str | None) -> str | None:
    """Accept a raw key or a Bearer token in the key headers."""
    if not header:
        return None
    if header.startswith("Bearer "):
        return header[len("Bearer "):]
    return header


__all__ = ["GuardMiddleware", "required_role"]
