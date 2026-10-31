# serve layer — FHIR R4 HTTP surface for SQL-on-FHIR

Status: Phase 1 complete (`feat/serve-layer`). Read/execute only — no writes
beyond the definition registry, no Hugging Face or network calls.

## Why this layer exists

The engine already knows how to translate and run SQL-on-FHIR v2 artifacts
(`fhir4ds/sqlquery/`, `fhir4ds/viewdef/`) and how to execute CQL measures.
What it did not have was a standards-shaped way to *reach* them: no HTTP
surface, no FHIR `Parameters` in/out, no format negotiation, no discovery
document.

`fhir4ds/serve/` is that adapter. It owns routing, FHIR request/response
shapes, and format negotiation; it owns **no** engine logic. Every translation
and execution decision stays in the engine modules it calls.

## Surface inventory

| Method | Path | Level | Returns |
| --- | --- | --- | --- |
| GET | `/health` | service | `{"status": "ok"}` |
| GET | `/metadata` | service | CapabilityStatement (fhirVersion 4.0.1) |
| POST | `/Library` | resource | 201 + stored Library |
| GET | `/Library` | resource | `searchset` Bundle |
| GET | `/Library/{id}` | resource | Library, or 404 |
| POST | `/Library/{id}/$sqlquery-run` | instance | ndjson by default |
| POST | `/Library/$sqlquery-run` | type | needs `queryReference` \| `queryResource` |
| POST | `/$sqlquery-run` | system | needs `queryReference` \| `queryResource` |
| POST | `/ViewDefinition` | resource | 201 + stored ViewDefinition |
| GET | `/ViewDefinition` | resource | `searchset` Bundle |
| GET | `/ViewDefinition/{id}` | resource | ViewDefinition, or 404 |
| POST | `/ViewDefinition/{id}/$run` | instance | ndjson by default |
| POST | `/ViewDefinition/$run` | type | needs `viewReference` \| `viewResource` |
| GET | `/openapi.json`, `/docs` | service | FastAPI/OpenAPI |

`fhir4ds serve --port 8766 [--resources PATH]` starts it; the `[serve]` extra
supplies FastAPI + uvicorn.

## Capability mapping

Each route is a thin adapter over one operations-layer capability:

| Route | Capability | Engine seam |
| --- | --- | --- |
| `$sqlquery-run` (all levels) | `fhir4ds.operations.capabilities.sqlquery.sqlquery_run` | `fhir4ds.sqlquery.runner.SQLQueryRunner` |
| `$run` (both levels) | `fhir4ds.operations.capabilities.viewdefinition_run.viewdefinition_run` | `fhir4ds.viewdef.SQLGenerator` |
| `POST`/`GET` resource routes | — | `fhir4ds.serve.store.ResourceStore` (DuckDB table) |

Capabilities return `TabularResult` — an operations-layer envelope
(`schema: 1`, `ok`, `diagnostics`) extended with typed `columns` (name, physical
SQL type, FHIR `value[x]`) and `rows`. Diagnostics are the contract: the HTTP
layer maps `DiagnosticCode` → status, so no status logic leaks into the engine
and no engine exception is matched by message text.

`SQL_TO_FHIR_VALUE_TYPE` in `fhir4ds/operations/capabilities/tabular.py` is the
single copy of the IG's ISO/IEC 9075 → `value[x]` table; the `_format=fhir`
encoder reads `ResultColumn.fhir_type` from it rather than re-deriving a type.

## Encoding

* **Request**: a FHIR `Parameters` resource (`application/fhir+json`, or raw
  JSON of any content type). Unknown names, known-but-unsupported names,
  wrong `value[x]` types, duplicate names and missing conditionally-required
  parameters are all 400 (`OperationOutcome`).
* **Response**: `_format` ∈ `json | ndjson | csv | parquet | fhir`, default
  **ndjson**. `_format` beats `Accept`; `Accept` is honoured only when
  `_format` is absent. Flat formats return a Binary body with the matching
  content type; `fhir` returns a `Parameters` resource with one `row` parameter
  per result row and one `part` per column, SQL NULL omitting the part
  (zero rows → `Parameters` with no `parameter` element).
* **Errors**: always `OperationOutcome` — 400 bad request, 404 missing
  Library/ViewDefinition/dependency, 422 execution failure or unmapped column
  type under `_format=fhir`.

## Decisions taken

1. **Sync handlers + one connection under a `threading.Lock`.** DuckDB is
   synchronous; an `async def` handler would block the event loop. One shared
   connection, one lock, held for a whole request (the SQLQuery runner creates
   views on that connection, so a narrower lock would be wrong).
2. **FHIR resources are plain dicts.** No pydantic FHIR models. Only the fields
   the operations depend on (`resourceType`, `id`, `parameter[].name/type`,
   `relatedArtifact`) are validated.
3. **The registry lives in DuckDB** (`serve_resource_registry`), not in a
   Python dict: dependency resolution must see the same snapshot as execution,
   and it gives canonical lookups for free.
4. **`/metadata` is derived from the route table.** Route handlers declare
   their FHIR role with `@cap_interaction` / `@cap_operation`; the document is
   built by walking the router tree. Adding an undeclared route does not
   advertise it, and declaring one cannot be forgotten — the same decorator is
   what makes the route meaningful. (Starlette ≥1.6 keeps included routers
   behind `_IncludedRouter`, so the walk unwraps both shapes and falls back to
   an ordered declaration registry.)
5. **`_limit` is applied post-evaluation**, after the SQL ran, and capped by
   `ServeConfig.max_rows`. Capping is silent — fewer rows, still 200 — per the
   IG's Row Limit section.
6. **`source` routing** maps a named source to a physical DuckDB table
   (`ServeConfig.sources`); an unknown name is 400 `not-supported`. There is no
   external data-source plugin in phase 1.
7. **IG parameters this phase does not implement** (`patient`, `group`,
   `resource`, `_since` on `$run`) are declared `supported=False` so the server
   answers 400 `not-supported` instead of silently ignoring them — the IG's own
   guidance.
8. **A dangling `relatedArtifact` is 404, not 422.** The store's resolver raises
   `LookupError`; the capability maps that (walking `__cause__`, never
   message-matching) to `NOT_FOUND`. A dependency that exists but cannot
   materialize stays 422.
9. **ViewDefinition `resourceType` normalization.** The IG publishes instances
   with `"resourceType": "ViewDefinition"`, while the engine's `resourceType`
   field means the logical model's canonical URL. The serve layer drops the
   FHIR spelling at the parse boundary (`normalize_view_definition`) and keeps
   the resource verbatim for `GET` round-trips.
10. **`library`/`type`/`instance` parameter rules follow the IG exactly**:
    `queryReference`/`queryResource` are required-and-exclusive at system/type
    level, forbidden at instance level (and the same for `viewReference`/
    `viewResource`).

## Engine notes discovered in this phase

* **LibraryTypesCodes spelling.** The IG's own example Libraries declare
  `type.coding.system = "https://sql-on-fhir.org/ig/CodeSystem/LibraryTypesCodes"`,
  which the engine's canonical set rejected, so the spec's published examples
  could not be executed at all. Fixed by adding the two `sql-on-fhir.org/ig`
  spellings to `LIBRARY_TYPES_CODESYSTEM_CANONICALS`
  (`fhir4ds/sqlquery/types.py`). This is the only engine file touched, and it is
  a data-only change to an accepted-canonical set.
* **Temporal ViewDefinition columns are VARCHAR.** The generator's scalar casts
  cover integer/decimal only (`_TYPE_CAST`), and the official spec tests pin
  date/dateTime as strings. A SQLQuery that compares such a column against a
  `date`-typed parameter therefore fails to bind (VARCHAR vs DATE). The IG's
  `SqlOnFhirExample` does exactly that, so its `blood_pressure_view` dependency
  is committed as a **SQLView** Library that casts to DATE — which also means
  the fixtures exercise both dependency kinds (ViewDefinition and SQLView).
* `getResourceKey()` columns must be declared `type: "string"`; declaring `id`
  trips the generator's runtime type guard (`type().name` for a computed string
  is `String`).

## Not in scope (phase 1)

Bulk export (`$viewdefinition-export`, `$sqlquery-export`), asynchronous
operations, `patient`/`group`/`_since`/`resource` filtering, write operations on
patient data, authentication, and multi-tenant isolation. `ARCHITECTURE` note:
the lock serializes requests, which is correct for a single-node DuckDB service
and deliberately not a concurrency story.
