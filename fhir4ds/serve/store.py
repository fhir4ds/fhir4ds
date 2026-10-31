"""Resource registry for the serve surface (Library and ViewDefinition).

The registry is a DuckDB table on the same connection the operations run
against, so a stored ``Library`` and the ``ViewDefinition`` tables it
references live in one consistent snapshot. It holds *definitions* only —
this surface never stores patient data of its own.

Two lookup keys matter:

* ``resourceType`` + ``id`` — the FHIR read path (``GET /Library/{id}``);
* ``url`` (+ optional ``version``) — canonical resolution for a SQLQuery's
  ``relatedArtifact.resource`` entries (SQL-on-FHIR v2 Analytics Layer).

A resolver miss raises :class:`ResourceNotFound` (a ``LookupError``), which is
how the capability layer distinguishes "dependency does not exist" (404) from
"dependency failed to materialize" (422).

Concurrency: the store never takes the connection lock itself. Callers hold
``ServeContext.lock`` for the whole request; the SQLQuery runner resolves
dependencies while already holding it, so an internal lock would deadlock.
"""

from __future__ import annotations

import json
import re
import uuid
from collections.abc import Callable
from typing import Any
from urllib.parse import urlsplit

from fhir4ds.operations.capabilities.viewdefinition_run import normalize_view_definition

from .errors import bad_request

#: FHIR ``id`` lexical space (Id: ``[A-Za-z0-9\\-\\.]{1,64}``).
ID_PATTERN = re.compile(r"^[A-Za-z0-9\-.]{1,64}$")

#: Table holding served definitions.
REGISTRY_TABLE = "serve_resource_registry"

#: Resource types this surface stores and serves.
SUPPORTED_RESOURCE_TYPES: tuple[str, ...] = ("Library", "ViewDefinition")


class ResourceNotFound(LookupError):
    """A canonical / reference could not be resolved to a stored definition."""


class ResourceStore:
    """Registry of served Library and ViewDefinition resources.

    All methods require the caller to hold the shared connection lock (see the
    module docstring).
    """

    def __init__(self, connection: Any) -> None:
        self._connection = connection

    # -- schema ----------------------------------------------------------

    def ensure_schema(self) -> None:
        """Create the registry table when absent (idempotent)."""
        self._connection.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {REGISTRY_TABLE} (
                resource_type VARCHAR NOT NULL,
                id VARCHAR NOT NULL,
                url VARCHAR,
                version VARCHAR,
                body VARCHAR NOT NULL,
                PRIMARY KEY (resource_type, id)
            )
            """
        )

    # -- writes ----------------------------------------------------------

    def put(self, resource: Any) -> dict:
        """Store (create or replace) a Library or ViewDefinition.

        Returns the stored resource, with a generated ``id`` when the caller
        omitted one.
        """
        if not isinstance(resource, dict):
            raise bad_request("Resource body must be a JSON object", code="structure")
        resource_type = resource.get("resourceType")
        if resource_type not in SUPPORTED_RESOURCE_TYPES:
            raise bad_request(
                f"Unsupported resourceType {resource_type!r}; this server stores "
                f"{' and '.join(SUPPORTED_RESOURCE_TYPES)}",
                code="not-supported",
            )
        resource_id = resource.get("id")
        if resource_id is None:
            resource = dict(resource)
            resource_id = uuid.uuid4().hex
            resource["id"] = resource_id
        if not isinstance(resource_id, str) or not ID_PATTERN.match(resource_id):
            raise bad_request(
                f"Resource id {resource_id!r} is not a valid FHIR id "
                f"([A-Za-z0-9-.]{{1,64}})",
                expression=["id"],
                code="value",
            )
        url = resource.get("url")
        if url is not None and not isinstance(url, str):
            raise bad_request("Resource url must be a string", expression=["url"], code="value")
        version = resource.get("version")
        if version is not None and not isinstance(version, str):
            raise bad_request(
                "Resource version must be a string", expression=["version"], code="value"
            )

        self._connection.execute(
            f"INSERT OR REPLACE INTO {REGISTRY_TABLE} "
            f"(resource_type, id, url, version, body) VALUES (?, ?, ?, ?, ?)",
            [resource_type, resource_id, url, version, json.dumps(resource)],
        )
        return resource

    # -- reads -----------------------------------------------------------

    def get(self, resource_type: str, resource_id: str) -> dict | None:
        """Read one stored resource, or ``None`` when absent."""
        row = self._connection.execute(
            f"SELECT body FROM {REGISTRY_TABLE} WHERE resource_type = ? AND id = ?",
            [resource_type, resource_id],
        ).fetchone()
        return json.loads(row[0]) if row else None

    def search(
        self,
        resource_type: str,
        *,
        count: int | None = None,
        offset: int = 0,
    ) -> list[dict]:
        """List stored resources of one type in a deterministic order."""
        sql = f"SELECT body FROM {REGISTRY_TABLE} WHERE resource_type = ? ORDER BY id"
        parameters: list[Any] = [resource_type]
        if count is not None:
            sql += " LIMIT ?"
            parameters.append(max(0, count))
        if offset:
            sql += " OFFSET ?"
            parameters.append(max(0, offset))
        rows = self._connection.execute(sql, parameters).fetchall()
        return [json.loads(row[0]) for row in rows]

    def count(self, resource_type: str) -> int:
        row = self._connection.execute(
            f"SELECT count(*) FROM {REGISTRY_TABLE} WHERE resource_type = ?",
            [resource_type],
        ).fetchone()
        return int(row[0]) if row else 0

    def search_page(
        self,
        resource_type: str,
        *,
        count: int | None = None,
        offset: int = 0,
    ) -> tuple[list[dict], int]:
        """Return ``(page, total)`` in one lock-held call."""
        return (
            self.search(resource_type, count=count, offset=offset),
            self.count(resource_type),
        )

    # -- canonical resolution -------------------------------------------

    def find_by_canonical(self, canonical: str) -> dict | None:
        """Resolve a canonical URL, ``ResourceType/id``, or bare id.

        Supports the three reference forms the IG recommends for
        ``viewReference``: a relative URL (``ViewDefinition/123``), a
        versioned canonical (``http://host/ViewDefinition/123|1.0.0``), and an
        absolute URL.
        """
        if not isinstance(canonical, str) or not canonical.strip():
            return None
        reference = canonical.strip()
        url_part, _, version_part = reference.partition("|")

        stored = self._find_by_url(url_part, version_part or None)
        if stored is not None:
            return stored

        resource_type, resource_id = split_reference(url_part)
        if resource_type is not None and resource_id is not None:
            return self.get(resource_type, resource_id)

        # Bare id: try both served types (ViewDefinition first — the more
        # common dependency in a SQLQuery's relatedArtifact).
        for candidate in reversed(SUPPORTED_RESOURCE_TYPES):
            if ID_PATTERN.match(url_part):
                found = self.get(candidate, url_part)
                if found is not None:
                    return found
        return None

    def _find_by_url(self, url: str, version: str | None) -> dict | None:
        if version is None:
            row = self._connection.execute(
                f"SELECT body FROM {REGISTRY_TABLE} WHERE url = ? ORDER BY version DESC",
                [url],
            ).fetchone()
        else:
            row = self._connection.execute(
                f"SELECT body FROM {REGISTRY_TABLE} WHERE url = ? AND version = ?",
                [url, version],
            ).fetchone()
        return json.loads(row[0]) if row else None

    # -- dependency resolver --------------------------------------------

    def resolve_dependency(self, canonical: str) -> dict:
        """Resolver for ``fhir4ds.sqlquery`` ``relatedArtifact`` entries.

        Returns the stored resource in the shape the engine parses: a served
        ViewDefinition carries the FHIR ``resourceType`` spelling
        (``"ViewDefinition"``), while the engine's ``resourceType`` field means
        the logical model's canonical URL, so the spelling is dropped here.
        ``get``/``search`` keep the resource verbatim for round-trip reads.
        """
        stored = self.find_by_canonical(canonical)
        if stored is None:
            raise ResourceNotFound(
                f"No Library or ViewDefinition is stored for reference {canonical!r}"
            )
        return normalize_view_definition(stored)

    def resolver(self) -> Callable[[str], dict]:
        """Return a ``DependencyResolver`` bound to this store."""
        return self.resolve_dependency


def split_reference(reference: str) -> tuple[str | None, str | None]:
    """Split ``[base/]ResourceType/id`` into its type and id components.

    Handles relative references, absolute URLs, and the versioned
    ``.../ResourceType/id`` prefix of a ``url|version`` canonical.
    """
    path = urlsplit(reference).path if "://" in reference else reference
    segments = [segment for segment in path.split("/") if segment]
    for index in range(len(segments) - 1, -1, -1):
        if segments[index] in SUPPORTED_RESOURCE_TYPES:
            return segments[index], segments[index + 1] if index + 1 < len(segments) else None
    return None, None


__all__ = [
    "ResourceStore",
    "ResourceNotFound",
    "split_reference",
    "REGISTRY_TABLE",
    "SUPPORTED_RESOURCE_TYPES",
    "ID_PATTERN",
]
