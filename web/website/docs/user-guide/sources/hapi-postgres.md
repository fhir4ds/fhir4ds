---
title: Connecting to HAPI FHIR PostgreSQL
sidebar_label: HAPI PostgreSQL
---

# Connecting to HAPI FHIR PostgreSQL

`HapiPostgresSource` lets FHIR4DS query a HAPI FHIR JPA Server PostgreSQL
backend in place through DuckDB's PostgreSQL extension.

This adapter is read-only. It creates the standard `resources` view from HAPI's
current-resource tables without copying FHIR data into DuckDB.

## Supported v1 Scope

Version 1 supports:

- Current, non-deleted HAPI resources.
- PostgreSQL-backed HAPI JPA Server.
- Inline JSON resource bodies in `hfj_res_ver.res_text_vc`.
- `res_encoding = 'JSON'`.

Version 1 deliberately rejects compressed/LOB resource storage such as `JSONC`
by default. This prevents partial analysis where compressed resources are
silently omitted.

## Example

```python
import duckdb
import fhir4ds
from fhir4ds.sources import HapiPostgresSource

con = duckdb.connect(":memory:")

source = HapiPostgresSource(
    "postgresql://hapi:hapi@localhost:15432/hapi"
)

fhir4ds.attach(con, source)

rows = con.execute("""
    SELECT id, resourceType, patient_ref
    FROM resources
    WHERE resourceType = 'Patient'
""").fetchall()
```

## HAPI Schema Defaults

The default schema mapping targets the current HAPI 8.8 PostgreSQL layout:

| Purpose | Default |
|---------|---------|
| Resource table | `public.hfj_resource` |
| Version table | `public.hfj_res_ver` |
| Resource primary key | `hfj_resource.res_id` |
| Version resource FK | `hfj_res_ver.res_id` |
| Current version join | `hfj_resource.res_ver = hfj_res_ver.res_ver` |
| FHIR resource ID | `hfj_resource.fhir_id` |
| Resource type | `hfj_resource.res_type` |
| Updated timestamp | `hfj_resource.res_updated` |
| Deleted timestamp | `hfj_resource.res_deleted_at` |
| Resource JSON text | `hfj_res_ver.res_text_vc` |
| Resource encoding | `hfj_res_ver.res_encoding` |

Override these defaults with `HapiPostgresSchema` for older HAPI versions or
custom table names:

```python
from fhir4ds.sources import HapiPostgresSchema, HapiPostgresSource

schema = HapiPostgresSchema(
    resource_pk_column="pid",
    version_resource_fk_column="res_id",
)

source = HapiPostgresSource(
    "postgresql://readonly:secret@hapi-db.example.org:5432/hapi",
    schema=schema,
)
```

## Patient Attribution

The adapter maps `patient_ref` as a raw Patient ID:

- `Patient` resources use their own `fhir_id`.
- Other resources check common FHIR reference paths:
  - `subject.reference`
  - `patient.reference`
  - `beneficiary.reference`

Only local references of the form `Patient/<id>` are converted to raw IDs. Add
paths with `patient_reference_paths` if your target resources use different
patient-bearing fields.

## Local Docker Stack

Use the disposable compose stack for development:

```bash
cd docker/hapi-postgres
docker compose up -d
```

It exposes:

- HAPI FHIR at `http://localhost:18080/fhir`
- PostgreSQL at `postgresql://hapi:hapi@localhost:15432/hapi`

## Operational Notes

Use a read replica or a read-only database user for production analytics. Large
CQL or DQM queries can scan many resources and should not compete with a busy
transactional HAPI server.

`HapiPostgresSource.supports_incremental()` supports insert/update delta checks
against current inline JSON resources. Deletes and compressed historical bodies
are outside the v1 incremental scope.

For event-driven DQM materialization with PostgreSQL triggers and
`LISTEN/NOTIFY`, see
[HAPI DQM Materialization](/docs/user-guide/quality/hapi-materialization).
