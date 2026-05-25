---
id: dqm-recipes
title: Source-to-DQM Production Recipes
sidebar_label: Production Recipes
---

# Source-to-DQM Production Recipes

These recipes show how to connect common FHIR data sources to Digital Quality
Measure evaluation. Each recipe starts from the same contract: by the time the
measure runs, DuckDB must expose a `resources` view with `id`, `resourceType`,
`resource`, and `patient_ref`.

Use the CLI batch runner when your data can be represented by the DQM config
source types. Use the Python API when you need a custom source adapter, an
already staged DuckDB table, or a database connection that should be managed by
application code.

## 1. Bulk FHIR Files to Batch DQM

Use this recipe for FHIR bulk export data in NDJSON, JSON, or Parquet. This is
the most common production path for scheduled measure runs.

### Directory Layout

```text
project/
  cql/
    CMS124FHIR.cql
    FHIRHelpers.cql
    QICoreCommon.cql
  measures/
    Measure-CMS124.json
  valuesets/
    valueset-1.json
    valueset-2.json
  data/
    Patient.ndjson
    Encounter.ndjson
    Observation.ndjson
  dqm-run.json
```

### Config

```json
{
  "measures": [
    {
      "id": "CMS124",
      "path": "./measures/Measure-CMS124.json",
      "cql": "./cql/CMS124FHIR.cql"
    }
  ],
  "libraries": {
    "paths": ["./cql"]
  },
  "source": {
    "type": "filesystem",
    "path": "./data/*.ndjson",
    "format": "ndjson"
  },
  "terminology": {
    "valuesets": ["./valuesets"]
  },
  "period": {
    "start": "2025-01-01",
    "end": "2025-12-31"
  },
  "audit": {
    "mode": "population",
    "narratives": false
  },
  "outputs": {
    "directory": "./out/dqm",
    "formats": ["json", "parquet"],
    "measure_reports": "both",
    "definitions": {
      "mode": "all",
      "formats": ["json"],
      "include_sde": false
    }
  }
}
```

### Run

```bash
fhir4ds dqm validate --config dqm-run.json
fhir4ds dqm inspect --config dqm-run.json
fhir4ds dqm run --config dqm-run.json
```

For Parquet, change only the source:

```json
{
  "source": {
    "type": "filesystem",
    "path": "./data/**/*.parquet",
    "format": "parquet",
    "hive_partitioning": true
  }
}
```

Use Parquet with Hive partitioning for larger repeated jobs. NDJSON is usually
best for raw bulk export ingestion and quick validation.

## 2. Cloud Data Lake to Batch DQM

The same `filesystem` source works for object storage paths supported by DuckDB.
Configure credentials in the environment or with DuckDB secrets before the run.

```json
{
  "source": {
    "type": "filesystem",
    "path": "s3://analytics-fhir/bulk-export/**/*.parquet",
    "format": "parquet",
    "hive_partitioning": true
  }
}
```

For cloud jobs, keep source paths, measure paths, library paths, valueset paths,
and output directories explicit in config. This makes `inspect` useful in CI and
scheduled runs.

## 3. Existing DuckDB Table to DQM

Use this recipe when another pipeline already staged FHIR resources in DuckDB.
Wrap the table with `ExistingTableSource`, then call `MeasureEvaluator`.

```python
import fhir4ds
from fhir4ds.dqm import AuditMode, MeasureEvaluator
from fhir4ds.sources import ExistingTableSource

con = fhir4ds.create_connection()

con.execute("""
    CREATE TABLE staged_resources AS
    SELECT
        id::VARCHAR AS id,
        resourceType::VARCHAR AS resourceType,
        resource::JSON AS resource,
        patient_ref::VARCHAR AS patient_ref
    FROM read_parquet('./warehouse/fhir_resources/*.parquet')
""")

fhir4ds.attach(con, ExistingTableSource("staged_resources"))

evaluator = MeasureEvaluator(con)
result = evaluator.evaluate(
    measure_bundle="./measures/Measure-CMS124.json",
    cql_library_path="./cql/CMS124FHIR.cql",
    include_paths=["./cql"],
    parameters={"Measurement Period": ("2025-01-01", "2025-12-31")},
    audit_mode=AuditMode.POPULATION,
    include_supporting_evidence=True,
)

report = evaluator.to_measure_report(
    result,
    period_start="2025-01-01",
    period_end="2025-12-31",
    report_type="summary",
)
```

This is the right pattern for notebooks, Airflow tasks, dbt-produced DuckDB
tables, and test fixtures where the staging SQL is already controlled by your
application.

## 4. PostgreSQL FHIR JSON to DQM

Use `PostgresSource` when FHIR resources already exist as JSON or JSONB columns
in PostgreSQL tables. The adapter does not construct FHIR from arbitrary
relational schemas; each mapped table must already contain complete FHIR JSON.

```python
import fhir4ds
from fhir4ds.dqm import AuditMode, MeasureEvaluator
from fhir4ds.sources import PostgresSource, PostgresTableMapping

source = PostgresSource(
    connection_string="postgresql://analytics_user@localhost:5432/clinical",
    table_mappings=[
        PostgresTableMapping(
            table_name="fhir_patients",
            id_column="patient_id",
            resource_type="Patient",
            resource_column="resource_json",
            patient_ref_column="patient_id",
        ),
        PostgresTableMapping(
            table_name="fhir_observations",
            id_column="observation_id",
            resource_type="Observation",
            resource_column="resource_json",
            patient_ref_column="patient_id",
        ),
        PostgresTableMapping(
            table_name="fhir_encounters",
            id_column="encounter_id",
            resource_type="Encounter",
            resource_column="resource_json",
            patient_ref_column="patient_id",
        ),
    ],
)

con = fhir4ds.create_connection()
fhir4ds.attach(con, source)

evaluator = MeasureEvaluator(con)
result = evaluator.evaluate(
    measure_bundle="./measures/Measure-CMS124.json",
    cql_library_path="./cql/CMS124FHIR.cql",
    include_paths=["./cql"],
    parameters={"Measurement Period": ("2025-01-01", "2025-12-31")},
    audit_mode=AuditMode.NONE,
)
```

For production, prefer read-only users, read replicas, or warehouse clones. Do
not hardcode passwords in source files; pass connection strings through your
runtime secret manager or environment.

## 5. CSV Export to DQM

Use `CSVSource` for mapped extracts, small pilots, and one-off workflows. It is
not a substitute for a full clinical data model; you must decide how each row
maps to valid FHIR JSON.

```python
import fhir4ds
from fhir4ds.dqm import AuditMode, MeasureEvaluator
from fhir4ds.sources import CSVSource

patients = CSVSource(
    path="./exports/patients.csv",
    projection_sql="""
        SELECT
            patient_id AS id,
            'Patient' AS resourceType,
            json_object(
                'resourceType', 'Patient',
                'id', patient_id,
                'birthDate', birth_date,
                'gender', gender
            ) AS resource,
            patient_id AS patient_ref
        FROM {source}
    """,
)

con = fhir4ds.create_connection()
fhir4ds.attach(con, patients)

evaluator = MeasureEvaluator(con)
result = evaluator.evaluate(
    measure_bundle="./measures/Measure-CMS124.json",
    cql_library_path="./cql/CMS124FHIR.cql",
    include_paths=["./cql"],
    parameters={"Measurement Period": ("2025-01-01", "2025-12-31")},
    audit_mode=AuditMode.POPULATION,
)
```

If a measure needs resources from multiple CSV files, create a staging table or
view that unions projections into the standard schema, then wrap it with
`ExistingTableSource`.

## 6. Operational Checklist

Before a production run:

1. Run `fhir4ds dqm validate --config <config>`.
2. Run `fhir4ds dqm inspect --config <config>` and confirm measures, CQL
   libraries, valuesets, source path, and outputs.
3. Use `audit.mode = "none"` for high-throughput scoring and summary reports.
4. Use `audit.mode = "population"` for routine review and individual
   MeasureReports.
5. Use `audit.mode = "full"` only for debugging expression-level behavior.
6. Write Parquet outputs for large downstream analytics jobs.
7. Write JSON outputs when downstream systems need FHIR `MeasureReport`
   resources or machine-readable definition values.

After the run, check root `run.json` first. It records per-measure status,
duration, output paths, and errors.
