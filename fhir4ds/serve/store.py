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
import time
import uuid
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any, Protocol
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


# -- publish stores (phase 3) ----------------------------------------------
#
# The dataset is an append-only tree:
#
#     README.md
#     $bulk-publish                     aggregator manifest
#     publishers/<publisher>/$bulk-publish
#     resources/dt=YYYY-MM-DD/part-<seq>.parquet
#     viewdefinitions/*.json
#     sqlqueries/*.json
#     meta/state.json                   {"seq": <int>, "revision": "<sha>"}
#
# `_seq` is the writer's single monotonic integer: assigned before the row is
# buffered, persisted in meta/state.json with every commit, and never reused
# (a crashed buffer leaves a gap, which is correct). A part file is written
# once and never rewritten — that is what makes the history durable and the
# parquet dataset append-only.

#: Directory holding the append-only resource parts.
RESOURCE_PARTITIONS = "resources"

#: Writer state: the monotonic sequence and the last committed revision.
STATE_PATH = "meta/state.json"

#: Column order of a resource part (fixed so every part reads alike).
PART_COLUMNS: tuple[str, ...] = (
    "id",
    "resourceType",
    "resource",
    "patient_ref",
    "_seq",
    "_deleted",
    "_ingested_at",
)


class PublishStore(Protocol):
    """Append-only dataset store the flush loop publishes through.

    ``snapshot`` returns a local directory holding the current tree; ``append``
    buffers rows; ``commit`` publishes them and returns the new revision;
    ``revision`` reports the last committed revision.

    Two extensions beyond the four core methods: ``current_seq`` (the persisted
    monotonic counter, needed before the first flush) and ``stage_file`` (write
    a generated file such as a manifest into the next commit).
    """

    def snapshot(self) -> Path:
        """Local directory holding the dataset tree."""

    def append(self, rows: Sequence[Mapping[str, Any]]) -> None:
        """Buffer rows for the next commit."""

    def commit(self) -> str:
        """Publish buffered rows; return the new revision."""

    def revision(self) -> str:
        """Last committed revision (empty when nothing has been committed)."""

    def current_seq(self) -> int:
        """The persisted monotonic sequence."""

    def stage_file(self, relative_path: str, text: str) -> None:
        """Write a generated file into the next commit."""


class TreeStore:
    """A dataset tree on local disk.

    ``LocalDirStore`` uses it directly; ``HfDatasetStore`` subclasses it and
    uploads the changed paths on commit. Keeping the tree mechanics here means
    the two stores cannot drift on layout, part naming or state handling.
    """

    def __init__(self, root: Path | str) -> None:
        self._root = Path(root)
        self._root.mkdir(parents=True, exist_ok=True)
        self._buffer: list[dict[str, Any]] = []
        self._dirty: set[str] = set()

    # -- protocol --------------------------------------------------------

    def snapshot(self) -> Path:
        return self._root

    def append(self, rows: Sequence[Mapping[str, Any]]) -> None:
        for row in rows:
            if "_seq" not in row:
                raise ValueError("publish rows require a writer-assigned _seq")
            self._buffer.append(dict(row))

    def commit(self) -> str:
        buffered = list(self._buffer)
        seq = max((int(row["_seq"]) for row in buffered), default=self.current_seq())
        if buffered:
            self._write_part(buffered, seq)
        revision = self._digest(seq, buffered)
        self._write_text(
            STATE_PATH, json.dumps({"seq": seq, "revision": revision}, separators=(",", ":"))
        )
        self._buffer.clear()
        return revision

    def revision(self) -> str:
        return str(self._read_state().get("revision", ""))

    def current_seq(self) -> int:
        return int(self._read_state().get("seq", 0))

    def stage_file(self, relative_path: str, text: str) -> None:
        self._write_text(relative_path, text)

    # -- for subclasses --------------------------------------------------

    @property
    def root(self) -> Path:
        return self._root

    def dirty_paths(self) -> set[str]:
        """Relative paths written since the last ``clear_dirty``."""
        return set(self._dirty)

    def clear_dirty(self) -> None:
        self._dirty.clear()

    def pending_rows(self) -> int:
        return len(self._buffer)

    # -- internals -------------------------------------------------------

    def _write_part(self, rows: Sequence[Mapping[str, Any]], seq: int) -> str:
        import pyarrow as pa
        import pyarrow.parquet as pq

        day = time.strftime("%Y-%m-%d", time.gmtime())
        relative = f"{RESOURCE_PARTITIONS}/dt={day}/part-{seq:08d}.parquet"
        target = self._root / relative
        target.parent.mkdir(parents=True, exist_ok=True)

        columns: dict[str, list[Any]] = {name: [] for name in PART_COLUMNS}
        for row in sorted(rows, key=lambda item: int(item["_seq"])):
            resource = row.get("resource")
            columns["id"].append(row.get("id"))
            columns["resourceType"].append(row.get("resourceType"))
            columns["resource"].append(
                resource if isinstance(resource, str) else json.dumps(resource, separators=(",", ":"))
            )
            columns["patient_ref"].append(row.get("patient_ref"))
            columns["_seq"].append(int(row["_seq"]))
            columns["_deleted"].append(bool(row.get("_deleted", False)))
            columns["_ingested_at"].append(row.get("_ingested_at") or utc_timestamp())

        table = pa.table(columns)
        pq.write_table(table, target)
        self._dirty.add(relative)
        return relative

    def _write_text(self, relative_path: str, text: str) -> None:
        target = self._root / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
        self._dirty.add(relative_path)

    def _read_state(self) -> dict[str, Any]:
        state_file = self._root / STATE_PATH
        if not state_file.exists():
            return {}
        try:
            payload = json.loads(state_file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        return payload if isinstance(payload, dict) else {}

    def _digest(self, seq: int, rows: Sequence[Mapping[str, Any]]) -> str:
        import hashlib

        material = {
            "seq": seq,
            "rows": sorted(
                (str(row.get("resourceType")), str(row.get("id")), int(row["_seq"]))
                for row in rows
            ),
        }
        return hashlib.sha256(json.dumps(material, sort_keys=True).encode("utf-8")).hexdigest()[:12]


class LocalDirStore(TreeStore):
    """A dataset tree in a local directory — the no-token store.

    Every unit test and CI run uses this; it has the same layout and state
    semantics as the Hub-backed store, minus the upload.
    """


def utc_timestamp() -> str:
    """Current UTC time as a FHIR ``instant`` (second precision)."""
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


__all__ = [
    "ResourceStore",
    "ResourceNotFound",
    "split_reference",
    "REGISTRY_TABLE",
    "SUPPORTED_RESOURCE_TYPES",
    "ID_PATTERN",
    "PublishStore",
    "LocalDirStore",
    "TreeStore",
    "RESOURCE_PARTITIONS",
    "STATE_PATH",
]
