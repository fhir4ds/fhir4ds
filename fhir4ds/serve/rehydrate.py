"""Boot-time rehydration: fold a published dataset back into a fresh server.

The durable copy of everything this surface ever served is the publish dataset
(``resources/dt=.../part-*.parquet`` plus ``viewdefinitions/*.json`` and
``sqlqueries/*.json``). The read path, however, is the in-memory versioned log
(``resources_base``) — so a restarted process would serve an empty FHIR store
even though the dataset still holds every row.

This module closes that gap at boot: it reads the publish store's snapshot and

* restores log rows **with their original** ``_seq`` (so versionIds/ETags keep
  matching the published parts) and their ``_deleted`` tombstones (so delete
  history and ``_history`` stay correct);
* restores served definitions into the registry (dataset wins over baked seed
  — a definition edited at runtime has its newest copy in the dataset).

Restoration is idempotent: a version is identified by its ``_seq``, and rows
whose ``_seq`` is already in the log are skipped. It runs for both publish
backends — the local backend with a surviving ``--publish-dir`` gets the same
restart durability as the Hub-backed one.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from .store import SUPPORTED_RESOURCE_TYPES, ResourceStore
from .versioning import BASE_TABLE

logger = logging.getLogger(__name__)

#: Directories holding served definitions inside the dataset tree.
_DEFINITION_DIRECTORIES = ("viewdefinitions", "sqlqueries")

#: Glob for published resource parts, relative to the snapshot root.
_PART_GLOB = "part-*.parquet"


def rehydrate(
    connection: Any,
    publish_store: Any,
    registry_store: ResourceStore,
) -> tuple[int, int]:
    """Restore log rows and definitions from ``publish_store``'s snapshot.

    Returns ``(restored_rows, restored_definitions)``. Never raises for
    per-file problems (a corrupt part or definition is logged and skipped) —
    boot must not take the surface down — but a failure of the snapshot step
    itself (e.g. the dataset cannot be downloaded) propagates to the caller.
    """
    snapshot = Path(publish_store.snapshot())
    restored_rows = _restore_rows(connection, snapshot)
    restored_definitions = _restore_definitions(registry_store, snapshot)
    if restored_rows or restored_definitions:
        logger.info(
            "rehydrated from published dataset: %d row(s), %d definition(s)",
            restored_rows,
            restored_definitions,
        )
    return restored_rows, restored_definitions


def _restore_rows(connection: Any, snapshot: Path) -> int:
    """Insert every published version row whose ``_seq`` is not in the log.

    Original ``_seq``, ``_deleted`` and ``_ingested_at`` values are preserved,
    so a restored server reports the same versionIds the dataset carries and
    ``_history`` reproduces the published order.
    """
    resources_root = snapshot / "resources"
    if not resources_root.is_dir():
        return 0
    parts = sorted(str(path) for path in resources_root.rglob(_PART_GLOB))
    if not parts:
        return 0

    # Explicit file list (not a glob): auto Hive partitioning would inject a
    # phantom `dt` column the base table does not have.
    part_list = "[" + ", ".join(f"'{path.replace(chr(39), chr(39) * 2)}'" for path in parts) + "]"
    rows = connection.execute(
        f"""
        INSERT INTO {BASE_TABLE}
            (id, resourceType, resource, patient_ref, _seq, _deleted, _ingested_at)
        SELECT
            p.id,
            p.resourceType,
            CAST(p.resource AS JSON),
            p.patient_ref,
            p._seq,
            p._deleted,
            CAST(p._ingested_at AS TIMESTAMP)
        FROM read_parquet({part_list}) AS p
        WHERE NOT EXISTS (
            SELECT 1 FROM {BASE_TABLE} AS b WHERE b._seq = p._seq
        )
        RETURNING _seq
        """
    ).fetchall()
    return len(rows)


def _restore_definitions(registry_store: ResourceStore, snapshot: Path) -> int:
    """Load the dataset's definition files into the registry (create-or-replace).

    The dataset is the newer copy by construction — every flush stages the
    registry's current contents — so an upsert is the correct precedence: a
    definition edited at runtime is restored edited, not clobbered by whatever
    a baked seed would insert later (seed scripts skip resources already
    present).
    """
    from .errors import ServeError

    restored = 0
    for folder in _DEFINITION_DIRECTORIES:
        directory = snapshot / folder
        if not directory.is_dir():
            continue
        for path in sorted(directory.glob("*.json")):
            try:
                resource = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError) as exc:
                logger.warning("rehydrate: skipping unreadable definition %s: %s", path, exc)
                continue
            if not isinstance(resource, dict):
                logger.warning("rehydrate: skipping non-object definition %s", path)
                continue
            if resource.get("resourceType") not in SUPPORTED_RESOURCE_TYPES:
                logger.warning(
                    "rehydrate: skipping definition %s (unsupported resourceType %r)",
                    path,
                    resource.get("resourceType"),
                )
                continue
            try:
                registry_store.put(resource)
            except ServeError as exc:
                logger.warning("rehydrate: skipping invalid definition %s: %s", path, exc)
                continue
            restored += 1
    return restored


__all__ = ["rehydrate"]
