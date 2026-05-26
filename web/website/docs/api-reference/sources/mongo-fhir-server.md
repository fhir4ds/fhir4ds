---
id: mongo-fhir-server
title: MongoFhirServerSource
sidebar_label: MongoFhirServerSource
---

# MongoFhirServerSource

`fhir4ds.sources.MongoFhirServerSource` mounts current FHIR resources from a
Mongo-backed FHIR server as the standard FHIR4DS `resources` view.

It uses DuckDB's community `mongo` extension and `mongo_scan`; it does not use a
Python MongoDB client.

## Class Signature

```python
MongoFhirServerSource(
    connection_string: str,
    *,
    schema: MongoFhirServerSchema | None = None,
    attachment_name: str = "fhir4ds_mongo",
    install_extension: bool = True,
)
```

| Parameter | Type | Description |
|-----------|------|-------------|
| `connection_string` | `str` | MongoDB URI passed to DuckDB `mongo_scan`. |
| `schema` | `MongoFhirServerSchema \| None` | Mongo collection and resource layout configuration. Defaults to Helix/icanbwell per-resource collections. |
| `attachment_name` | `str` | DuckDB attachment name used only for best-effort collection discovery. |
| `install_extension` | `bool` | If `True`, runs `INSTALL mongo FROM community` before `LOAD mongo`. |

## MongoFhirServerSchema

```python
MongoFhirServerSchema(
    database_name: str = "fhir",
    base_version: str = "4_0_0",
    collection_strategy: Literal["per_resource", "explicit", "shared"] = "per_resource",
    resource_types: tuple[str, ...] | list[str] | None = None,
    collections: tuple[MongoResourceCollection, ...] | list[MongoResourceCollection] | None = None,
    collection_mappings: Mapping[str, str] | None = None,
    shared_collection: str | None = None,
    shared_resource_path: str = "$",
    shared_id_path: str = "$.id",
    shared_resource_type_path: str = "$.resourceType",
    shared_current_filter: Mapping[str, Any] | None = None,
    shared_deleted_filter: Mapping[str, Any] | None = None,
    sample_size: int | None = -1,
    include_hidden: bool = False,
    hidden_tag_system: str = "https://fhir.icanbwell.com/4_0_0/CodeSystem/server-behavior",
    hidden_tag_code: str = "hidden",
    patient_reference_paths: tuple[str, ...] | list[str] = (
        "$.subject.reference",
        "$.patient.reference",
        "$.beneficiary.reference",
    ),
    scrub_private_fields: tuple[str, ...] | list[str] = (
        "_id",
        "_uuid",
        "_sourceId",
        "_sourceAssigningAuthority",
    ),
)
```

| Parameter | Description |
|-----------|-------------|
| `database_name` | Mongo database name. |
| `base_version` | Suffix used by `per_resource` collection names, such as `4_0_0`. |
| `collection_strategy` | Collection layout strategy. |
| `resource_types` | Resource types to mount. Required for `per_resource` and `shared`; optional filter for `explicit` mappings. |
| `collections` | Full explicit `MongoResourceCollection` entries. |
| `collection_mappings` | Shorthand mapping from resource type to collection name for root-document layouts. |
| `shared_collection` | Collection name used by `shared` strategy. |
| `shared_resource_path` | JSON path to the FHIR resource in shared-collection rows. |
| `shared_id_path` | JSON path to the FHIR resource id in shared-collection rows. |
| `shared_resource_type_path` | JSON path to the FHIR resource type in shared-collection rows. |
| `shared_current_filter` | Inclusion Mongo filter applied to every shared-collection resource type. |
| `shared_deleted_filter` | Delete marker filter wrapped in `$nor`. |
| `sample_size` | DuckDB `mongo_scan` sample size. Use `-1` for full inference, or `None` to omit the option. |
| `include_hidden` | If `False`, exclude resources with the configured hidden tag. |
| `patient_reference_paths` | JSON paths checked for patient references inside the FHIR resource JSON. |
| `scrub_private_fields` | Root fields removed from emitted `resource` JSON with `json_merge_patch`. |

## MongoResourceCollection

```python
MongoResourceCollection(
    resource_type: str,
    collection_name: str,
    resource_path: str = "$",
    id_path: str = "$.id",
    resource_type_path: str = "$.resourceType",
    current_filter: Mapping[str, Any] | None = None,
    deleted_filter: Mapping[str, Any] | None = None,
)
```

Use this class for custom collection names, wrapped FHIR resources, tenant
filters, or non-standard delete markers.

## Methods

### `register(con)`

Loads DuckDB's `mongo` extension, creates `resources`, and calls
`validate_schema()`.

Raises `SchemaValidationError` if the extension cannot load, Mongo cannot be
scanned, or the resulting view does not expose the required schema.

### `unregister(con)`

Drops the `resources` view and detaches the best-effort discovery attachment if
one was created.

### `supports_incremental()`

Returns `False`.

## Example

```python
import fhir4ds
from fhir4ds.sources import MongoFhirServerSchema, MongoFhirServerSource

source = MongoFhirServerSource(
    "mongodb://readonly:secret@mongo.example.org:27017",
    schema=MongoFhirServerSchema(
        database_name="fhir",
        resource_types=("Patient", "Observation"),
        include_hidden=False,
    ),
)

con = fhir4ds.create_connection(source=source)
rows = con.execute("""
    SELECT id, resourceType, patient_ref
    FROM resources
    ORDER BY resourceType, id
""").fetchall()
```

## Security Notes

Mongo URIs, database names, collection names, JSON paths, and filter documents
are quoted as SQL string literals before being passed to DuckDB. Error messages
redact credentials and sensitive URI query parameters.

## DQM Materialization

`MongoFhirServerSource` remains read-only. HAPI-like queues, change streams,
result storage, and generated `MeasureReport` publishing live in
`fhir4ds.dqm.mongo_materialization` and the `fhir4ds dqm mongo ...` CLI.

Install the optional dependency set before using that worker:

```bash
python3 -m pip install "fhir4ds-v2[mongo]"
```

Mongo change streams require a replica set or sharded cluster. They are the
Mongo-native analogue to HAPI PostgreSQL triggers plus `LISTEN/NOTIFY`.
The materialization worker enables patient-scoped source reads by default via
`worker.source_patient_pushdown: true`.
