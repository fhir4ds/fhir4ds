"""The ``$bulk-publish`` manifest: a Bulk-Data-shaped feed served off the Hub.

The point of publishing to the dataset repo is that the demo can consume the
feed **without this server running**: the manifest is a file in the dataset, and
every ``output[].url`` is a public ``resolve`` URL that ``curl`` fetches with no
auth. ``GET /$bulk-publish`` serves the same document live.

Layout written by every flush (append-only for parts, rewritten for manifests):

    README.md
    $bulk-publish
    publishers/<publisher>/$bulk-publish
    resources/dt=YYYY-MM-DD/part-<seq>.parquet

Decisions recorded in ``docs/design/serve-writes.md``: parts are grouped by
ingestion date (the brief's layout), so an ``output`` entry is one published
**part** with ``type: "resources"`` rather than one per FHIR resource type —
grouping per type would require a second, duplicated copy of the data.
"""

from __future__ import annotations

import json
import time
from collections.abc import Iterable
from pathlib import Path
from typing import Any

#: Path of the aggregator manifest inside the dataset.
MANIFEST_PATH = "$bulk-publish"

#: Manifest path for one publisher.
PUBLISHER_MANIFEST_TEMPLATE = "publishers/{publisher}/$bulk-publish"

#: Resource type label used for a part-level output entry.
PART_OUTPUT_TYPE = "resources"

#: Default publisher identity.
DEFAULT_PUBLISHER = "fhir4ds-serve"

#: Dataset repository this surface publishes to (only this one).
DATASET_REPOSITORY = "fhir4ds/bulk-publish-demo"

README = """# fhir4ds bulk-publish demo

Synthetic FHIR resources published by `fhir4ds serve`. Every row is synthetic;
there is no patient data here.

* `resources/dt=YYYY-MM-DD/part-<seq>.parquet` — append-only parts. Columns:
  `id`, `resourceType`, `resource` (FHIR JSON as text), `patient_ref`, `_seq`
  (the writer's monotonic version id), `_deleted`, `_ingested_at`.
  A resource's current version is the highest `_seq` per
  (`resourceType`, `id`); a row with `_deleted = true` is a tombstone.
* `$bulk-publish` — aggregate manifest (Bulk Data shaped).
* `publishers/<publisher>/$bulk-publish` — the same feed for one publisher.
* `meta/state.json` — `{ "seq": <int>, "revision": "<sha>" }`.
* `viewdefinitions/*.json`, `sqlqueries/*.json` — the definitions the publisher
  served when the flush ran.

Query the whole dataset without this server:

```sql
SELECT * FROM read_parquet('hf://datasets/fhir4ds/bulk-publish-demo/resources/**/*.parquet');
```
"""


def utc_timestamp() -> str:
    """Current UTC time as a FHIR ``instant`` (second precision)."""
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def plan_part_path(seq: int, day: str | None = None) -> str:
    """Relative path of the part a commit of ``seq`` writes."""
    partition = day or time.strftime("%Y-%m-%d", time.gmtime())
    return f"resources/dt={partition}/part-{seq:08d}.parquet"


def collect_parts(root: Path) -> list[str]:
    """Every published part under ``root``, sorted (stable manifest order)."""
    resources = root / "resources"
    if not resources.exists():
        return []
    return sorted(
        str(path.relative_to(root)).replace("\\", "/")
        for path in resources.rglob("part-*.parquet")
    )


def resolve_url(repository: str | None, relative_path: str, root: Path | None = None) -> str:
    """Public URL for a dataset file.

    With a repository (the Hub-backed store) this is the standard
    ``/datasets/<repo>/resolve/main/<path>`` URL, which needs no auth for a
    public dataset. Without one (``LocalDirStore``) it is a ``file://`` URL, so
    a local run is still inspectable.
    """
    if repository:
        return f"https://huggingface.co/datasets/{repository}/resolve/main/{relative_path}"
    base = (root or Path(".")).resolve()
    return (base / relative_path).as_uri()


def build_manifest(
    *,
    repository: str | None,
    root: Path,
    request_url: str,
    parts: Iterable[str] | None = None,
    transaction_time: str | None = None,
) -> dict[str, Any]:
    """Bulk-Data-shaped manifest over ``parts`` (default: everything on disk)."""
    paths = list(parts if parts is not None else collect_parts(root))
    return {
        "transactionTime": transaction_time or utc_timestamp(),
        "request": {"method": "GET", "url": request_url},
        "output": [
            {"type": PART_OUTPUT_TYPE, "url": resolve_url(repository, path, root)}
            for path in paths
        ],
    }


def dataset_files(
    *,
    repository: str | None,
    root: Path,
    publisher: str,
    request_url: str,
    pending_part: str | None = None,
    definitions: dict[str, str] | None = None,
) -> dict[str, str]:
    """Files to stage for the next commit: manifests, README, definitions.

    ``pending_part`` is the part the very same commit is about to write, so the
    manifest can reference it without a second commit.
    """
    parts = collect_parts(root)
    if pending_part and pending_part not in parts:
        parts.append(pending_part)
    parts.sort()

    aggregate = build_manifest(
        repository=repository,
        root=root,
        request_url=request_url,
        parts=parts,
    )
    files = {
        MANIFEST_PATH: json.dumps(aggregate, ensure_ascii=False, indent=2) + "\n",
        PUBLISHER_MANIFEST_TEMPLATE.format(publisher=publisher): (
            json.dumps(aggregate, ensure_ascii=False, indent=2) + "\n"
        ),
        "README.md": README,
    }
    for relative_path, text in (definitions or {}).items():
        files[relative_path] = text
    return files


def definition_files(definitions: Iterable[dict]) -> dict[str, str]:
    """Serialize served Library/ViewDefinition resources for the dataset."""
    files: dict[str, str] = {}
    for definition in definitions:
        resource_type = definition.get("resourceType")
        resource_id = definition.get("id")
        if not resource_type or not resource_id:
            continue
        folder = "viewdefinitions" if resource_type == "ViewDefinition" else "sqlqueries"
        files[f"{folder}/{resource_id}.json"] = (
            json.dumps(definition, ensure_ascii=False, indent=2) + "\n"
        )
    return files


__all__ = [
    "DEFAULT_PUBLISHER",
    "DATASET_REPOSITORY",
    "MANIFEST_PATH",
    "PART_OUTPUT_TYPE",
    "README",
    "build_manifest",
    "collect_parts",
    "dataset_files",
    "definition_files",
    "plan_part_path",
    "resolve_url",
    "utc_timestamp",
]
