# serve layer — FHIR-native writes and the publish store (phase 3)

Status: phase 3, branch `feat/serve-layer`. Read/execute (phase 1), the container
and `$cql` (phase 2) are unchanged except where this document says so.

## Why

A read-only projection cannot answer "what did I POST?" A FHIR API needs
versions, history and conditional writes, and the demo needs a feed that keeps
working when the server does not. Phase 3 adds both halves: a versioned write
surface over DuckDB, and an append-only parquet dataset on the Hub
(`fhir4ds/bulk-publish-demo-data`) that is the durable copy.

## Storage model — one place, three consumers

```
resources_base     append-only: id, resourceType, resource, patient_ref,
                                _seq, _deleted, _ingested_at
resources (view)   row_number() OVER (PARTITION BY resourceType, id
                                      ORDER BY _seq DESC) = 1 AND NOT _deleted
```

`fhir4ds/serve/versioning.py` owns this and nothing else does. Reads
(`GET /{type}/{id}`), the SQL-on-FHIR path (`$sqlquery-run`, ViewDefinition
generation, the fhirpath UDFs) and writes all go through the `resources`
relation, so a write is visible to a query the moment it lands — while the row
is still pending publication. `_history` and vread read the base without the
dedupe.

A phase-1/2 plain `resources` **table** is migrated on first boot: its rows are
appended with fresh `_seq` values in `(resourceType, id)` order, the table is
dropped, and the view takes the name. That is why `--resources` imports and old
databases keep working.

## `_seq` — the version id

One monotonic integer owned by the writer, persisted in the dataset's
`meta/state.json` and committed with every flush. On boot the writer resumes at
`max(local log max(_seq), published seq)` — a fresh in-memory database against
an existing dataset continues from the dataset, and a surviving database
continues from its own rows. Values are never derived from timestamps and never
reused: a row buffered but never committed leaves a gap (tested).

`meta.versionId` is that number; the ETag is `W/"<seq>"` and `If-Match` accepts
`W/"<seq>"`, `"<seq>"` or `*`.

## Dataset layout (append-only)

```
README.md
$bulk-publish                                  aggregator manifest
publishers/<publisher>/$bulk-publish           per-publisher manifest
resources/dt=YYYY-MM-DD/part-<seq>.parquet     id, resourceType, resource,
                                               patient_ref, _seq, _deleted,
                                               _ingested_at
viewdefinitions/*.json   sqlqueries/*.json
meta/state.json                                {seq, revision}
```

Parts are written once, never rewritten. The store abstraction
(`PublishStore`, `LocalDirStore`, `HfDatasetStore`) lives in `store.py` /
`hf_store.py`; the tree mechanics (part naming, state, dirty tracking) are
shared in `TreeStore` so the local and Hub stores cannot drift.

## Write surface

| Method | Path | Semantics |
| --- | --- | --- |
| POST | `/{type}` | create; server assigns `id` when absent; `201` + `Location` + `ETag`; duplicate id → `400 duplicate` |
| PUT | `/{type}/{id}` | create-or-update; `201` create / `200` update; `If-Match` mismatch → `412` |
| DELETE | `/{type}/{id}` | tombstone; `204`; unknown or already-deleted → `404` |
| GET | `/{type}/{id}` | current version + `ETag`; tombstoned → `410`; unknown → `404` |
| GET | `/{type}/{id}/_history` | `Bundle(type=history)`, newest first |
| GET | `/{type}/{id}/_history/{vid}` | vread |
| POST | `/Bundle` | `transaction`/`batch`, entries in order, one flush |
| POST | `/admin/flush` | commit now → `{revision, committed, pending, last_error}` |
| GET | `/$bulk-publish` | the feed manifest |

Writes accept `application/fhir+json` or `application/json`; anything else is
`415`. Every error is an `OperationOutcome`.

Generic routes are registered **after** the phase-1/2 routers, so
`/Library/{id}`, `/ViewDefinition/{id}` and their operations keep winning.

A transaction is all-or-nothing: the entries run inside one DuckDB transaction,
a failing entry rolls everything back, and no publish rows reach the flush loop.
`batch` behaves the same way (partial batches are defensible in FHIR, but not
alongside a single flush boundary).

## Search and conditional writes

`search.py` is a deliberately small subset, and it is **strict**: `_id`,
`identifier` (`system|value`, `|value`, `value`), `_count`, `_offset`. Any other
parameter is a `400 not-supported` naming what is supported. Silently ignoring a
filter would answer a different question than the client asked — the one failure
mode a clinical API must not have. Adding a parameter means extending
`parse_search` **and** `condition_sql`, with tests.

`identifier` matches entries of the resource's `identifier` array via
`json_each` (repeated parameters are ANDed, per FHIR). On top of that matcher:

* **conditional create** — `POST /{type}` with `If-None-Exist: <filter>`:
  zero matches create (`201`), one returns the existing resource (`200`, no new
  version), many are `412`.
* **conditional update** — `PUT /{type}?<filter>`: zero matches create (`201`),
  one updates that id (`200`), many are `412`. A call with no filter at all is
  `400 required`.
* **`GET /{type}`** — `searchset` Bundle with `total` over all matches and a
  page of `_count` (default 100, capped by `ServeConfig.max_rows`).

Generic writes refuse the types the definition registry owns (`Library`,
`ViewDefinition`) with `400 not-supported`: they would bypass the registry's
canonical/`url` handling, so the registry routes stay the only way in.

## Commit discipline

Writes never wait for the Hub. The row lands in the log (reads see it) and its
publish row is buffered; a background thread flushes every `flush_interval_seconds`
(30 s) or as soon as `flush_batch_size` (50) rows wait, and `POST /admin/flush`
forces one synchronously. One `create_commit` per flush; a `409` parent conflict
re-reads the branch head and retries **once**; any remaining failure keeps the
buffer (rows keep their `_seq`) and records `last_error`, retried on the next
tick. `GET /health` reports `pending`, `last_commit`, `last_commit_at`,
`last_error` and keeps `status: "ok"` at the top level. Single writer only.

## Decisions taken (brief silent or self-contradictory)

1. **Write status codes are the FHIR ones** (`201`/`200`/`204`), not `202`
   `{accepted, pending}`. The brief's "COMMIT DISCIPLINE" section and its "FHIR
   SURFACE" table contradict each other; clients (`cqframework/cql-tests-runner`,
   generic FHIR clients) branch on 201/ETag, so the FHIR codes win and the
   buffer state is surfaced out of band: `X-Pending-Commits` on every write,
   `pending` in `/health`, `committed` from `/admin/flush`.
2. **Deleted reads are `410 Gone`** (not 404) — the tombstone is evidence the
   resource existed; documented here as the choice the brief left open.
3. **`$bulk-publish` output entries are parts, not resource types.**
   `output[].type` is `"resources"` and each `url` is one published parquet
   part. The layout is date-partitioned, so a per-FHIR-type URL would need a
   second duplicated copy of the data; the browser demo parses parts directly.
4. **Manifest URLs use `resolve/main/...`**, not a commit sha: the manifest is
   written by the same commit that writes the parts, so a sha-qualified URL
   would be self-referential. With `LocalDirStore` (no repository) the URLs are
   `file://` so a local run stays inspectable.
5. **`POST` with an existing id is a `400 duplicate`**, not an implicit update:
   silent upsert would hide a client that meant `PUT`.
6. **No cross-process locking**, by design and stated in the README: one writer,
   one DuckDB connection, one flush thread.
7. **Unknown search *filter* parameters are a 400**, not ignored. The FHIR
   spec lets a server ignore unknown parameters; doing so would return
   unfiltered data that looks filtered. The universal protocol parameter
   `_format` is the deliberate exception: it shapes the representation, not the
   result set (this surface speaks fhir+json regardless), and every generic
   client sends it — so it is accepted and ignored
   (`search.NON_FILTER_PARAMETERS`).
8. **`output[].type` stays `"resources"` (no per-type grouping).** Bulk Data uses
   per-type entries because each URL is a per-type NDJSON file. Here a URL is a
   date-partitioned parquet **part** that spans types, so a per-type entry would
   either name a URL that is not type-scoped or require a second, duplicated
   copy of the data. Consumers filter columnarly
   (`WHERE resourceType = 'Observation'`). Changing this means re-partitioning
   parts by type (`resources/type=<Type>/dt=…/part-<seq>.parquet`), which
   departs from the brief's fixed layout and re-publishes the dataset — offered,
   not taken.

## Review fixes (post-addendum self-review)

A self-review after the addendum found four real defects and three gaps; all
seven are fixed, each with a regression test that failed first:

1. **Bundle `entry.request.ifMatch` now takes the FHIR string form** and a
   non-string is a loud 400. It previously accepted only a list — the
   precondition inside transactions was silently ignored (the first version's
   own test had encoded the wrong shape).
2. **Conditional create/update decide and act in ONE locked section.** With
   `match_count` / `first_match` / the write in separate acquisitions, two
   concurrent identical conditional creates could both pass the "zero matches"
   check; the test now fires four and asserts exactly one resource.
3. **`DELETE` requires no Content-Type** — it carries no body; a plain
   `curl -X DELETE` was a 415.
4. **`_format` is accepted on search** (see decision 7).
5. **A flush that fails *after* the local commit is retried as an upload, never
   as a re-buffer.** Re-buffering committed rows would write them into a second
   part and double-publish them once new rows joined the buffer; the store
   contract gained `pending_files()` / `retry_publish()` for exactly this.
6. **Search pages carry `self`/`next`/`previous` links** (filters preserved,
   no link past the last page).
7. **The `$cql` body cap is enforced before buffering** — `Content-Length`
   when stated, the running total when chunked — so an oversized body can no
   longer be read fully into memory before rejection.

## Verification

```bash
pytest fhir4ds/serve/tests -q                                  # 209 passed, 1 skipped
FHIR4DS_HF_INTEGRATION=1 HF_TOKEN=... \
  pytest fhir4ds/serve/tests/test_store_hf.py -q               # live publish
```

The skipped test is the live publish, gated on both `FHIR4DS_HF_INTEGRATION=1`
and `HF_TOKEN`; everything else runs with no token at all.
