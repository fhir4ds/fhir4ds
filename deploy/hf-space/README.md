---
title: bulk-publish-demo-server
emoji: 🗓️
colorFrom: blue
colorTo: indigo
sdk: docker
app_port: 7860
pinned: false
---

# fhir4ds bulk-publish demo server

A private Docker Space serving the fhir4ds FHIR R4 / SQL-on-FHIR surface and
publishing every write to the private dataset
[`fhir4ds/bulk-publish-demo-data`](https://huggingface.co/datasets/fhir4ds/bulk-publish-demo-data).

| Surface | Path |
| --- | --- |
| Health / CapabilityStatement | `/health`, `/metadata` |
| SQL-on-FHIR `$sqlquery-run` | `/Library/{id}/$sqlquery-run`, `/Library/$sqlquery-run` |
| ViewDefinition `$run` | `/ViewDefinition/{id}/$run` |
| FHIR writes | `POST /{type}`, `PUT`, `DELETE`, `GET`, `_history`, `POST /Bundle` |
| Publish | flush every 30 s / 50 rows; `POST /admin/flush`; `GET /$bulk-publish` |

## What is seeded

* **Resources** — the SMART Scheduling Links `$bulk-publish` example set
  (`data/smart/`): Location, Device, Schedule, PractitionerRole and ~11.5k Slot
  resources, loaded at boot via `--resources` (skip-if-present).
* **Definitions** — the IG example Libraries and their ViewDefinitions
  (`data/seed/`), POSTed after health only when absent.

## Durability model

Writes land in the in-memory versioned log and are flushed to the dataset as
append-only parquet parts. On restart the server **rehydrates** from the
dataset: rows return with their original `_seq` (versionIds match the
published parts), tombstones included, and served definitions return to the
registry. `meta/state.json` in the dataset keeps `_seq` monotonic across
restarts even without persistent storage.

Secrets: `HF_TOKEN` (write access to `fhir4ds/bulk-publish-demo-data`) is
configured as a Space secret, never baked into the image.

## Deploy

From the repository root (see `deploy/hf-space/`):

```bash
# 1. Build the wheel with the bundled C++ extensions
cp fhir4ds/fhirpath/duckdb/extensions/fhirpath.duckdb_extension /tmp/ext/...
DUCKDB_FHIRPATH_EXT=... DUCKDB_CQL_EXT=... hatch build -t wheel

# 2. Stage payload + wheel OUTSIDE the repo (the local .gitignore that keeps
#    the wheel out of git also makes `hf upload` skip it — and a .gitignore
#    pushed to the Space would ignore it REMOTELY too; never upload that file)
mkdir -p /tmp/space-upload && cp -r deploy/hf-space/. /tmp/space-upload/
rm -f /tmp/space-upload/.gitignore
cp dist/fhir4ds_v2-*.whl /tmp/space-upload/

# 3. Upload
hf upload fhir4ds/bulk-publish-demo-server /tmp/space-upload . --repo-type space
```

Single writer by design: do not run two instances against the same dataset.
