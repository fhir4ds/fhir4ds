"""Seed the demo ViewDefinition and Library registries over the HTTP API.

Runs once at container start, after /health answers. **Skip-if-present**: boot
already rehydrated the registry from the dataset's ``viewdefinitions/`` and
``sqlqueries/`` files — the dataset is the newer copy (dataset wins), so this
script only POSTs definitions the rehydrated registry does not already hold.
On first boot (empty dataset) that is all of them.

Failures are reported and swallowed — the server itself is the Space's main
process and must stay up even if seeding cannot reach it.
"""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

SEED_DIR = Path(__file__).resolve().parent / "data" / "seed"
RESOURCE_TYPE_ORDER = ("ViewDefinition", "Library")


def request(base_url: str, path: str, payload: dict | None = None) -> tuple[int, str]:
    """GET (payload None) or POST one registry resource; return (status, note)."""
    body = json.dumps(payload).encode("utf-8") if payload is not None else None
    headers = {"Content-Type": "application/fhir+json"} if body else {}
    req = urllib.request.Request(base_url + path, data=body, headers=headers,
                                 method="POST" if body else "GET")
    try:
        with urllib.request.urlopen(req, timeout=60) as response:
            return response.status, ""
    except urllib.error.HTTPError as exc:
        detail = exc.read()[:200].decode("utf-8", "replace")
        return exc.code, detail
    except Exception as exc:  # noqa: BLE001 - reported, not raised
        return 0, str(exc)


def main(argv: list[str]) -> int:
    base_url = (argv[1] if len(argv) > 1 else "http://127.0.0.1:7860").rstrip("/")
    if not SEED_DIR.is_dir():
        print(f"seed: {SEED_DIR} not found; nothing to seed")
        return 0

    payloads = []
    for path in sorted(SEED_DIR.glob("*.json")):
        try:
            payloads.append(json.loads(path.read_text(encoding="utf-8")))
        except json.JSONDecodeError as exc:
            print(f"seed: skipping {path.name}: {exc}")

    # Registries first, then the Libraries that reference them by canonical.
    payloads.sort(key=lambda r: RESOURCE_TYPE_ORDER.index(r["resourceType"])
                  if r.get("resourceType") in RESOURCE_TYPE_ORDER else 99)

    failures = 0
    for resource in payloads:
        resource_type = resource.get("resourceType", "")
        resource_id = resource.get("id", "?")
        if resource_type not in RESOURCE_TYPE_ORDER:
            print(f"seed: skip {resource_id} (unsupported resourceType)")
            continue

        # Skip-if-present: the rehydrated registry (dataset copy) wins.
        status, note = request(base_url, f"/{resource_type}/{resource_id}")
        if status == 200:
            print(f"seed: keep {resource_type}/{resource_id} (restored from dataset)")
            continue
        if status != 404:
            print(f"seed: {resource_type}/{resource_id} check failed ({status} {note})")
            failures += 1
            continue

        status, note = request(base_url, f"/{resource_type}", resource)
        if status in (200, 201):
            print(f"seed: {status} {resource_type}/{resource_id}")
        else:
            print(f"seed: {status} {resource_type}/{resource_id} {note}")
            failures += 1

    print(f"seed: {len(payloads) - failures}/{len(payloads)} registered")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
