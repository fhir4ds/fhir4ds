# fhir4ds-serve container

One image, two FHIR surfaces on port 7860:

| Surface | Path |
| --- | --- |
| SQL-on-FHIR v2 `$sqlquery-run` | `/Library/{id}/$sqlquery-run`, `/Library/$sqlquery-run`, `/$sqlquery-run` |
| SQL-on-FHIR v2 ViewDefinition `$run` | `/ViewDefinition/{id}/$run`, `/ViewDefinition/$run` |
| CQL conformance facade (`cqframework/cql-tests-runner`) | `/fhir/$cql` |
| Registries | `/Library`, `/ViewDefinition`, `/metadata`, `/health`, `/docs`, `/openapi.json` |
| FHIR writes (phase 3) | `POST /{type}`, `PUT /{type}/{id}`, `DELETE /{type}/{id}`, `GET /{type}/{id}`, `_history`, `POST /Bundle` |
| Publication | `POST /admin/flush`, `GET /$bulk-publish` |

## Build

The build context is the **repository root** (the image installs the package
from source; `fhir4ds/` carries the bundled DuckDB extensions):

```bash
docker build -f deploy/docker/fhir4ds-serve/Dockerfile -t fhir4ds-serve:phase2 .
```

`.dockerignore` (repo root) keeps the context small — `tests/` and `.git` are
never sent.

## Run

Data is a **mount**, never baked in. The container reads it from `/data`
(non-root user, read-only mount is fine):

```bash
docker run --rm -p 7860:7860 \
  -v "$PWD/fhir4ds/serve/tests/fixtures/resources":/data:ro \
  fhir4ds-serve:phase2 \
  python -m fhir4ds.serve --host 0.0.0.0 --port 7860 --data-root /data --resources /data
```

* `--resources /data` loads the mounted FHIR files into the `resources` table
  before serving.
* `--data-root /data` lets an operation's `source` parameter name a path under
  `/data` (`source=/data/bundle.json`). Without it, path sources are refused
  with a 400 — the root is the only part of the filesystem a request may name.
* `source=hf://datasets/fhir4ds/bulk-publish-demo` is answered with a 400
  `OperationOutcome` in this phase: the Hugging Face dataset store arrives in
  phase 3 and that dataset holds no data before then.

Compose (same thing, `FHIR4DS_DATA` defaults to `./data`):

```bash
HF_TOKEN=... docker compose -f deploy/docker/fhir4ds-serve/compose.yml up --build
```

## Writes and publication

The container is a FHIR **writer**: resources are versioned locally and
published as an append-only parquet dataset.

```bash
docker run --rm -p 7860:7860 \
  -v "$PWD/fhir4ds-publish":/publish \
  -e HF_TOKEN="$HF_TOKEN" \
  fhir4ds-serve:phase2 \
  python -m fhir4ds.serve --host 0.0.0.0 --port 7860 --data-root /data \
    --publish-dir /publish --publish-backend hf \
    --publish-repository fhir4ds/bulk-publish-demo
```

* **Single writer only.** One container, one DuckDB connection, one flush
  thread. Do not scale this image horizontally: two writers would fight over
  `_seq` and the dataset. (No cross-process lock exists by design.)
* Writes return the FHIR status (`201`/`200`/`204`) with an `ETag`; the number of
  rows still awaiting a commit rides `X-Pending-Commits`.
* Flushes happen every 30 s or every 50 rows; `POST /admin/flush` forces one.
  `GET /health` reports `pending`, `last_commit`, `last_commit_at`,
  `last_error` next to `status`.
* `--publish-dir` must be a **volume** if you want versions to survive a
  restart: the DuckDB database is in-memory, and `meta/state.json` in that
  directory is what keeps `_seq` monotonic across restarts.
* With `--publish-backend local` (the default) nothing leaves the machine; the
  `$bulk-publish` manifest then carries `file://` URLs.

## Secrets

**No secrets are in the image.** `HF_TOKEN` is read from the environment at run
time:

```bash
docker run --rm -e HF_TOKEN="$HF_TOKEN" ... fhir4ds-serve:phase2
```

It is never an `ARG`, never an `ENV`, and never copied into a layer. Verify:

```bash
docker history --no-trunc fhir4ds-serve:phase2 | grep -i token    # no output
```

Phase 2 makes no Hugging Face calls, so the token is simply unused today; the
contract exists so phase 3 can consume it without changing how the image is
built.

### Why `python -m fhir4ds.serve` and not `fhir4ds serve`

The installed `fhir4ds` console script imports every subcommand at startup,
including `dqm`, which needs pandas (the `[measures]` extra). This image installs
only `[serve]`, so the console script exits with `ModuleNotFoundError: pandas`.
`python -m fhir4ds.serve` runs the identical `serve` command without that import.
A full install (`pip install "fhir4ds-v2[serve,measures]"`) can still use
`fhir4ds serve`.

## Health and shutdown

* `HEALTHCHECK` polls `http://127.0.0.1:7860/health` every 30 s.
* `CMD` is exec-form, so `docker stop` delivers SIGTERM straight to uvicorn,
  which shuts down cleanly.
* Logs go to stdout unbuffered (`PYTHONUNBUFFERED=1`) — `docker logs -f` is live.

## Smoke test

`fhir4ds/serve/tests/container_smoke.py` builds (or reuses) the image, runs it
against the fixture data, exercises every surface, checks the SIGTERM exit, and
asserts the image history carries no token:

```bash
python3 fhir4ds/serve/tests/container_smoke.py            # build + run + probe
python3 fhir4ds/serve/tests/container_smoke.py --no-build # reuse the image
```
