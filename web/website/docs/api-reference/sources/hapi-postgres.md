---
title: HapiPostgresSource
sidebar_label: HapiPostgresSource
---

# HapiPostgresSource

`fhir4ds.sources.HapiPostgresSource` mounts a HAPI FHIR JPA Server PostgreSQL
database as the standard FHIR4DS `resources` view.

```python
HapiPostgresSource(
    connection_string: str,
    *,
    schema: HapiPostgresSchema | None = None,
    attachment_name: str = "fhir4ds_hapi_pg",
    fail_on_unsupported_storage: bool = True,
    patient_reference_paths: tuple[str, ...] = (
        "$.subject.reference",
        "$.patient.reference",
        "$.beneficiary.reference",
    ),
)
```

## HapiPostgresSchema

```python
HapiPostgresSchema(
    schema: str = "public",
    resource_table: str = "hfj_resource",
    version_table: str = "hfj_res_ver",
    resource_pk_column: str = "res_id",
    version_resource_fk_column: str = "res_id",
    resource_type_column: str = "res_type",
    fhir_id_column: str = "fhir_id",
    current_version_column: str = "res_ver",
    version_number_column: str = "res_ver",
    updated_at_column: str = "res_updated",
    deleted_at_column: str = "res_deleted_at",
    encoding_column: str = "res_encoding",
    text_vc_column: str = "res_text_vc",
    text_lob_column: str = "res_text",
    decoded_view: str | None = None,
)
```

## Methods

### `register(con)`

Installs and loads DuckDB's `postgres` extension, attaches the HAPI PostgreSQL
database read-only, checks for unsupported current resource storage, and creates
the `resources` view.

V1 supports only current resources where:

```sql
hfj_resource.res_deleted_at IS NULL
hfj_res_ver.res_encoding = 'JSON'
hfj_res_ver.res_text_vc IS NOT NULL
```

When `decoded_view` is set, the adapter reads that installed PostgreSQL view
instead of joining the HAPI tables directly. The default materialization install
creates `fhir4ds_hapi_current_resources`, which exposes inline JSON and
uncompressed JSON stored in HAPI's `res_text` large-object column. `JSONC`
storage is still treated as unsupported.

### `unregister(con)`

Drops the `resources` view and detaches the PostgreSQL attachment.

### `supports_incremental()`

Returns `True`.

### `get_changed_patients(since)`

Returns raw Patient IDs for decodable current resources updated after `since`.
Deletes and compressed historical bodies are outside the v1 delta scope.

## Example

```python
import duckdb
from fhir4ds.sources import HapiPostgresSource

con = duckdb.connect(":memory:")
source = HapiPostgresSource("postgresql://hapi:hapi@localhost:15432/hapi")
source.register(con)

print(con.execute("""
    SELECT id, resourceType, patient_ref
    FROM resources
    LIMIT 10
""").fetchall())
```
