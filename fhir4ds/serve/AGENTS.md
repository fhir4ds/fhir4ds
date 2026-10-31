# Serve Layer Agent Notes (`fhir4ds/serve/`)

FHIR R4 HTTP surface that projects the engine as a FHIR API: the SQL-on-FHIR v2
operations `$sqlquery-run` and `$viewdefinition-run`/`$run`, the Library and
ViewDefinition registries that back them, a derived CapabilityStatement, and (as
of phase 2) the CQL `$cql` conformance facade plus the container image.

Design doc: `docs/design/serve-layer.md`. Container assets:
`deploy/docker/fhir4ds-serve/`.

## Structure

| Module | Responsibility |
| --- | --- |
| `app.py` | `create_app(ServeConfig, connection=...)` — builds the FastAPI app, one shared DuckDB connection + `threading.Lock`, error handlers, conditional `$cql` mount |
| `config.py` | `ServeConfig` (host/port/database/source_table/sources/max_rows/data_root/cql_facade/cql_max_request_bytes), `ServeContext` (runtime bundle incl. `loaded_sources`), `context_for(request)` |
| `routes/health.py` | `GET /health` |
| `routes/capability.py` | `GET /metadata` (serves the derived document) |
| `routes/library.py` | Library CRUD + `$sqlquery-run` at instance/type/system level |
| `routes/viewdefinition.py` | ViewDefinition CRUD + `$run` at instance/type level |
| `routes/cql.py` | `POST /fhir/$cql` — the facade mount, its raw-body middleware, and its capability declaration |
| `sources.py` | `source` resolution: configured names, data-root paths (loaded once), dataset URIs (400) |
| `metadata.py` | `RouteSpec`, `cap_interaction`, `cap_operation`, `build_capability_statement` |
| `parameters.py` | FHIR `Parameters` body parsing → typed bag; `ParameterSpec` declarations |
| `execution.py` | Operation pipeline: validate → negotiate format → cap `_limit` → run under lock → serialize |
| `formats.py` | `json`/`ndjson`/`csv`/`parquet`/`fhir` encoders, format negotiation, `value[x]` encoding |
| `store.py` | `ResourceStore` (DuckDB table `serve_resource_registry`), canonical resolution, dependency resolver |
| `resources.py` | CRUD helpers (body validation, `searchset` Bundle, `_count`/`_offset`) |
| `errors.py` | `ServeError`, `Issue`, `OperationOutcome` builders, `DiagnosticCode` → HTTP status |
| `__main__.py` | `python -m fhir4ds.serve` — the slim entry point (no pandas) |

Capabilities live in `fhir4ds/operations/capabilities/`
(`sqlquery.py`, `viewdefinition_run.py`, shared `tabular.py`); the CLI entry is
`fhir4ds/cli/serve.py` (`fhir4ds serve`).

## Rules

- **Adapter only.** No engine logic here: translation/execution belongs to
  `fhir4ds.sqlquery` / `fhir4ds.viewdef`. If a change is needed there, change it
  there (with its own tests) rather than working around it in a route.
- **Every handler is a plain `def`.** DuckDB is synchronous; `async def` would
  block the event loop. All connection work goes through
  `ServeContext.run_locked`, which holds the one connection lock for the whole
  call.
- **`ResourceStore` never takes the lock.** Callers hold it. The SQLQuery
  runner resolves dependencies *while* holding it, so an internal lock would
  deadlock (`threading.Lock` is not reentrant).
- **Parameters are bound, never interpolated.** Values reach DuckDB only through
  the runner's prepared statements. Table names from config are validated as
  identifiers (`require_identifier`); column identifiers are never built from
  request data.
- **Errors are `OperationOutcome`s.** Raise `ServeError` (or a capability
  envelope with diagnostics); never return a bare `{"detail": ...}`. Status
  comes from `errors.STATUS_BY_DIAGNOSTIC_CODE`, issue codes from
  `ISSUE_CODE_BY_DIAGNOSTIC_CODE`.
- **No message-string matching.** Failure classification branches on exception
  types; a resolver miss is detected by walking `__cause__` for `LookupError`.
- **`/metadata` stays derived.** Declare a route's FHIR role with
  `@cap_interaction` / `@cap_operation` (below the `@router.*` decorator — the
  attribute must exist on the function before FastAPI registers it). Never
  hand-write operations into the document.
- **One copy of the IG's type table.** `SQL_TO_FHIR_VALUE_TYPE`
  (`operations/capabilities/tabular.py`); `formats.py` reads
  `ResultColumn.fhir_type` instead of re-deriving it.
- **The `$cql` facade is used, never re-implemented.** `routes/cql.py` calls
  `fhir4ds.cql.fhir_server.handle_cql_operation` and serializes with that
  package's `dumps_fhir_json`. `fhir4ds/cql/fhir_server/**` must stay
  byte-identical: it is the surface `cqframework/cql-tests-runner` drives, and
  `tests/test_cql_facade.py` compares both servers' status **and** body for ten
  request shapes. Never "fix" a facade behavior from this side.
- **The `$cql` route declares no body parameter on purpose.** FastAPI parses
  `application/*+json` bodies itself (and answers malformed JSON in its own
  words), which breaks byte parity with `fhir4ds cql-server`. `RawBodyCapture`
  buffers the raw body for that one path into `scope["state"]` and the handler
  decodes it. Adding `body: dict = Body(...)` back would silently restore the
  divergence.
- **Anything that touches the connection happens under `ServeContext.lock`,
  including constructors.** `FHIRDataLoader.__init__` issues SQL (table +
  `resolve()` macro); building it outside the lock deadlocks concurrent
  path-source requests inside DuckDB. Found by
  `test_concurrent_path_source_requests_load_once` — keep that test.
- **`source` paths are confined to `--data-root`.** `sources.py` resolves and
  re-checks containment (`..` included) before touching the filesystem; a
  request may only name a path the deployment exposed. Dataset URIs (`hf://`)
  are a typed 400, not a crash and not a silent empty query.

## Known Fragile Areas

- **FastAPI/Starlette route enumeration.** Starlette ≥1.6 wraps included
  routers in `_IncludedRouter`, so `app.routes` is *not* flat; older versions
  are. `metadata.collect_route_specs` walks the tree and unwraps
  `original_router`, with `DECLARED_ROUTE_SPECS` as a fallback so `/metadata`
  can never silently empty out. Re-check this when bumping FastAPI: a version
  that changes the wrapper shape must not break discovery.
- **`$` in path segments.** `/Library/$sqlquery-run` and
  `/Library/{id}/$sqlquery-run` coexist because they differ in segment count.
  Do not add a `/{id}/...` route that could shadow a fixed `$` path.
- **Request bodies must stay tolerant.** FastAPI decodes
  `application/json`/`application/fhir+json` bodies to a dict but hands raw
  bytes for other content types, so handlers type the body as
  `Optional[Any] = Body(default=None)` and `parameters.decode_json_body`
  normalizes bytes | str | dict | None. Tightening that annotation to `dict`
  breaks curl-style clients.
- **URL router order matters for `{id}` vs `$op`.** Register fixed operation
  paths from the same router as their resource routes; FastAPI matches in
  registration order.
- **`ServeConfig.max_rows` capping is silent** (IG: returning fewer rows is not
  an error). Never turn a cap into a 4xx.
- **`_format=fhir` is a 422 minefield.** A column whose SQL type has no
  `value[x]` mapping must 422 *even when every value is NULL* (`to_parameters`
  checks columns first, not values), and duplicate column names 422 for
  parquet. Flat formats tolerate both.
- **`to_parquet` declares the schema from the cursor types**, not from the
  values: values are normalized (tz-aware datetimes → UTC, string fallback for
  exotic types). A new DuckDB scalar type will silently land in the string
  fallback — add it to `_arrow_type` if that matters.
- **Instance-level operations must reject the type-level parameters**
  (`queryReference`/`queryResource`, `viewReference`/`viewResource`) with 400;
  the path identifies the resource.
- **`resource` / `patient` / `group` / `_since` are declared
  `supported=False`.** They 400 with `not-supported` so clients are never left
  believing a filter was applied. Remove the flag only when the filter is
  implemented.
- **`source` only routes to configured tables** (`ServeConfig.sources`,
  `NAME=TABLE` on the CLI). A fixture SQLView that hardcodes `resources` will
  ignore it — documented, not a bug.
- **`getResourceKey()` columns must declare `type: "string"`.** Declaring `id`
  trips the viewdef runtime type guard (`type().name` for a computed string is
  `String`). The fixture views show the working form.
- **The `fhir4ds` console script cannot serve a `[serve]`-only install.**
  `fhir4ds/cli/main.py` imports every subcommand, and `dqm` needs pandas (the
  `[measures]` extra). The container therefore runs
  `python -m fhir4ds.serve` (`__main__.py`), which builds the same parser and
  calls the same `run()`. `tests/test_slim_entrypoint.py` pins that pandas is
  never imported by that path — do not "simplify" it back to the console script.
- **`RawBodyCapture` replays the body once, then answers `http.disconnect`** to
  anything that keeps reading. That matches Starlette's own buffering
  middleware contract; a hand-written loop that echoes `receive()` afterwards
  can hang on an exhausted stream.
- **uvicorn logs to stderr by default.** The image passes
  `--log-config /app/uvicorn-log.json` (uvicorn's default config with handlers
  pointed at `sys.stdout`) so `docker logs` shows a single unbuffered stream.
  Do not drop that flag while "simplifying" the CMD.
- **Path-source tables are cached per app, not per connection.**
  `ServeContext.loaded_sources` maps `serve_source_<digest>` → path; two apps
  over one connection each re-load once (the loader's delete-before-insert makes
  that idempotent). Do not move the cache to module scope: tests and the CLI
  rely on per-app isolation.

## NOT A BUG Registry

- **Dangling dependency is 404, not 422.** The store resolver raises
  `LookupError`; the capability maps that to `NOT_FOUND`. A dependency that
  exists but fails to materialize remains 422 `processing`.
- **`POST /Library` returns 201, not 200.** Create-or-replace upsert; the
  response body is the stored resource (with a generated `id` when omitted).
- **`GET /Library` totals are the whole collection, not the page**
  (`Bundle.total` = matched resources; `_count` limits `entry` only).
- **Empty ndjson is an empty body**, not `{}` or a newline. Empty `json` is
  `[]`; empty `fhir` is `{"resourceType": "Parameters"}`; empty `csv` is just
  the header row (when `header=true`).
- **`valueInteger64` is encoded as a JSON string**, per FHIR's `integer64`
  representation, even though the SQL column is a BIGINT.
- **`valueDecimal` from REAL/FLOAT/DOUBLE is a JSON number** — the IG itself
  warns that binary→decimal conversion may introduce representation artefacts.
- **`header` only affects `csv`.** Supplying it with another `_format` is
  accepted and ignored (IG: "Applies only when csv output is requested").
- **A duplicate recipient for an unknown `Accept`** (e.g. `application/xml`)
  falls back to the default ndjson rather than 406: the IG only says servers
  MAY honour `Accept`.
- **Serving a ViewDefinition whose `resourceType` is the canonical URL works**;
  the FHIR spelling `"ViewDefinition"` is normalized away only where the engine
  parses it, so `GET` still round-trips the resource verbatim.
- **The registry is not transactional with execution.** `CREATE OR REPLACE
  VIEW` materialization is idempotent, so re-running an operation is safe; a
  failed run may leave dependency views behind (the runner documents this).

## Validation

```bash
python3 -m pytest fhir4ds/serve/tests -q          # 166 tests, ~30s
python3 -m pytest fhir4ds/cql/tests/unit -q       # the facade's own suite, unchanged
python3 -m ruff check fhir4ds/serve fhir4ds/operations/capabilities/ fhir4ds/cli/
python3 fhir4ds/serve/tests/container_smoke.py    # docker build + run + 24 probes
```

The container smoke needs a Docker daemon and a few minutes; it is a script, not
a pytest module, so unit runs never depend on Docker.

`fhir4ds/operations/capabilities/measure.py` and `translate.py` carry
pre-existing Ruff findings unrelated to this package; scope lint checks to the
files you touch.
