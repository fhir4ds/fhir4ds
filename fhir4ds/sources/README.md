# fhir4ds Source Adapters — Zero-ETL Analytics

## Overview

`fhir4ds.sources` enables **Zero-ETL analytics** — evaluate CQL measures and
FHIRPath queries directly against your existing data infrastructure without
copying PHI into a local DuckDB file.

## Quick Start

### Parquet / Data Lake

```python
import fhir4ds
from fhir4ds.sources import FileSystemSource

con = fhir4ds.create_connection(
    source=FileSystemSource('/data/fhir/**/*.parquet')
)
# 'resources' view is mounted — run queries immediately
results = con.execute("SELECT id FROM resources WHERE resourceType = 'Patient'").fetchall()
```

### Cloud Storage (S3)

```python
from fhir4ds.sources import FileSystemSource, CloudCredentials

creds = CloudCredentials(
    provider="S3",
    access_key_id="AKIAIOSFODNN7EXAMPLE",
    secret_access_key="wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
    region="us-east-1",
)
source = FileSystemSource(
    "s3://my-bucket/fhir/**/*.parquet",
    credentials=creds,
    hive_partitioning=True,
)
con = fhir4ds.create_connection(source=source)
```

### NDJSON Files

```python
from fhir4ds.sources import FileSystemSource

source = FileSystemSource('/data/fhir/export/', format='ndjson')
fhir4ds.attach(con, source)
```

### Postgres (FHIR JSON in column)

```python
from fhir4ds.sources import PostgresSource, PostgresTableMapping

source = PostgresSource(
    connection_string='postgresql://user:pass@localhost/clinical',
    table_mappings=[
        PostgresTableMapping(
            table_name='fhir_patients',
            id_column='patient_id',
            resource_type='Patient',
            resource_column='fhir_json',
            patient_ref_column='patient_id',
        ),
        PostgresTableMapping(
            table_name='fhir_observations',
            id_column='obs_id',
            resource_type='Observation',
            resource_column='fhir_json',
            patient_ref_column='patient_id',
        ),
    ]
)
fhir4ds.attach(con, source)
```

### HAPI FHIR JPA Server on PostgreSQL

```python
from fhir4ds.sources import HapiPostgresSource

source = HapiPostgresSource(
    connection_string='postgresql://readonly:pass@hapi-db:5432/hapi'
)
fhir4ds.attach(con, source)
```

`HapiPostgresSource` reads current resources from HAPI's
`hfj_resource`/`hfj_res_ver` tables. V1 supports current resources with
`res_encoding = 'JSON'`: inline `res_text_vc` by default, and uncompressed
`res_text` large-object JSON when using the decoded view installed by
`fhir4ds dqm hapi install`. Compressed `JSONC` rows fail clearly by default.
The DQM materialization worker can temporarily scope the mounted source to the
claimed Patient IDs; with the decoded view, that scope is pushed to PostgreSQL
as a `patient_ref` predicate.

### Mongo-Backed FHIR Server

```python
from fhir4ds.sources import MongoFhirServerSchema, MongoFhirServerSource

source = MongoFhirServerSource(
    connection_string="mongodb://readonly:pass@mongo.example.org:27017",
    schema=MongoFhirServerSchema(
        database_name="fhir",
        resource_types=("Patient", "Observation", "Encounter"),
    ),
)
fhir4ds.attach(con, source)
```

`MongoFhirServerSource` reads current resources through DuckDB's community
`mongo` extension. The default layout targets Helix/icanbwell-style collections
such as `Patient_4_0_0`, and the schema can be configured for custom collection
names, shared collections, or wrapped FHIR resource documents.

For HAPI-like DQM materialization, generated `MeasureReport` storage, and
change-stream processing, use `fhir4ds dqm mongo ...`. Those features live in
the DQM materialization worker; the source adapter itself remains read-only. The
worker can also scope Mongo scans to the claimed Patient IDs for each queue
batch.

### CSV Files

```python
from fhir4ds.sources import CSVSource

source = CSVSource(
    path='/data/patients.csv',
    projection_sql='''
        SELECT
            patient_id AS id,
            'Patient'  AS resourceType,
            json_object(
                'resourceType', 'Patient',
                'id', patient_id,
                'birthDate', birth_date,
                'gender', gender
            ) AS resource,
            patient_id AS patient_ref
        FROM {source}
    '''
)
fhir4ds.attach(con, source)
```

### Existing FHIRDataLoader (API Uniformity)

```python
import fhir4ds
from fhir4ds.cql.loader import FHIRDataLoader
from fhir4ds.sources import ExistingTableSource

con = fhir4ds.create_connection()
loader = FHIRDataLoader(con)
loader.load_directory('/data/fhir/')

# Optionally wrap for schema validation
source = ExistingTableSource()
fhir4ds.attach(con, source)
```

## Detaching a Source

```python
fhir4ds.detach(con, source)
# 'resources' view is now gone; external connection released
```

## Schema Requirements

All source files/tables must expose (or be projected to) these columns:

| Column | Type | Description |
|--------|------|-------------|
| `id` | VARCHAR | FHIR resource ID |
| `resourceType` | VARCHAR | FHIR resource type |
| `resource` | JSON | Complete FHIR resource as JSON |
| `patient_ref` | VARCHAR | Patient ID |

Schema is validated at `attach()` / `register()` time — failures surface
immediately with a precise `SchemaValidationError` message.

## Incremental Delta Tracking (Phase 6)

For near-real-time measure re-evaluation, use `ReactiveEvaluator`:

```python
from fhir4ds.dqm.reactive import ReactiveEvaluator

evaluator = ReactiveEvaluator(con, measure_bundle='CBP', cql_library_path='/path/to/lib.cql', adapter=source)

# On each data sync:
delta = evaluator.update()
if delta:
    # merge delta into population report
    pass
```

**Limitations** (read before using):
1. Only correct for patient-level measures with no population-level dependencies
2. `PostgresSource` delta tracking cannot detect hard deletes unless tables use
   soft-delete patterns with an `updated_at` column
3. `FileSystemSource` uses file mtime — unreliable for patient-level precision
