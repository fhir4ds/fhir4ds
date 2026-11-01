"""Shared helpers for the resource CRUD routes (Library, ViewDefinition).

This surface stores definitions, not patient data: ``POST`` upserts into the
registry and ``GET`` reads back. FHIR resources stay plain dicts — only the
fields the operations depend on are validated.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Any

from starlette.responses import Response

from .errors import bad_request, not_found, unprocessable
from .parameters import decode_json_body

FHIR_JSON = "application/fhir+json"


def parse_resource_body(body: Any, *, expected_type: str) -> dict:
    """Decode a request body into a resource dict of the expected type."""
    payload = decode_json_body(body, label="request body")
    if payload is None:
        raise bad_request(
            f"A {expected_type} resource body is required", code="structure"
        )
    if not isinstance(payload, dict):
        raise bad_request(
            f"Request body must be a {expected_type} resource; got "
            f"{type(payload).__name__}",
            code="structure",
        )
    resource_type = payload.get("resourceType")
    if resource_type != expected_type:
        raise bad_request(
            f"Request body must be a {expected_type} resource; got resourceType "
            f"{resource_type!r}",
            code="structure",
        )
    return payload


def resource_response(resource: dict, *, status_code: int = 200) -> Response:
    """Serialize a FHIR resource with the FHIR media type."""
    return Response(
        content=json.dumps(resource, ensure_ascii=False),
        media_type=FHIR_JSON,
        status_code=status_code,
    )


def require_resource(store: Any, resource_type: str, resource_id: str) -> dict:
    """Read a stored resource or raise the IG's 404 ``not-found``."""
    resource = store.get(resource_type, resource_id)
    if resource is None:
        raise not_found(f"{resource_type} with id {resource_id!r} not found")
    return resource


def resolve_reference(
    store: Any, reference: str, *, resource_type: str, parameter_name: str
) -> dict:
    """Resolve a ``queryReference``/``viewReference`` value to a stored resource."""
    resource = store.find_by_canonical(reference)
    if resource is None:
        raise not_found(
            f"{resource_type} {reference!r} not found", expression=[parameter_name]
        )
    if resource.get("resourceType") != resource_type:
        raise not_found(
            f"Reference {reference!r} resolves to a "
            f"{resource.get('resourceType')!r}, not a {resource_type}",
            expression=[parameter_name],
        )
    return resource


def searchset_bundle(
    resources: Sequence[dict], total: int, *, links: Sequence[dict] | None = None
) -> dict:
    """Build a ``searchset`` Bundle (``entry`` omitted when empty).

    ``links`` carries FHIR paging relations (``self`` / ``next`` / ``previous``)
    when the caller supplies them; the definition-registry search (phase 1)
    passes none and is unchanged.
    """
    bundle: dict = {
        "resourceType": "Bundle",
        "type": "searchset",
        "total": total,
    }
    if links:
        bundle["link"] = list(links)
    if resources:
        bundle["entry"] = [{"resource": resource} for resource in resources]
    return bundle


def paging_links(
    *, base_url: str, params: Any, page: Sequence[dict], total: int,
    count: int | None, offset: int,
) -> list[dict]:
    """``self``/``next``/``previous`` links for one search page.

    Filter parameters are carried through untouched; only ``_count`` and
    ``_offset`` are rewritten. ``next`` is omitted on the last page (and
    ``previous`` on the first).
    """
    from urllib.parse import urlencode

    default_count = 100
    size = count if count is not None else default_count
    filters = [
        (name, value)
        for name, value in (params.multi_items() if params else [])
        if name not in ("_count", "_offset")
    ]

    def url_for(page_offset: int) -> str:
        query = urlencode([*filters, ("_count", str(size)), ("_offset", str(page_offset))])
        return f"{base_url}?{query}"

    links = [{"relation": "self", "url": url_for(offset)}]
    if offset + len(page) < total and size > 0:
        links.append({"relation": "next", "url": url_for(offset + len(page))})
    if offset > 0:
        previous = max(0, offset - size)
        links.append({"relation": "previous", "url": url_for(previous)})
    return links


def search_controls(query_params: Any) -> tuple[int | None, int]:
    """Read ``_count``/``_offset`` from the query string.

    Read manually rather than through FastAPI's typed query parameters so a
    mistyped value yields a FHIR ``OperationOutcome`` instead of a bare 422.
    """
    count = _optional_integer(query_params, "_count")
    offset = _optional_integer(query_params, "_offset") or 0
    if offset < 0:
        raise bad_request("_offset must be >= 0", expression=["_offset"])
    return count, offset


def _optional_integer(query_params: Any, name: str) -> int | None:
    raw = query_params.get(name) if query_params is not None else None
    if raw is None or raw == "":
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        raise bad_request(
            f"{name} must be an integer; got {raw!r}", expression=[name]
        ) from None


__all__ = [
    "FHIR_JSON",
    "parse_resource_body",
    "resource_response",
    "require_resource",
    "resolve_reference",
    "searchset_bundle",
    "search_controls",
    "unprocessable",
]
