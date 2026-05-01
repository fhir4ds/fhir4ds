---
id: relational
title: Relational Databases
sidebar_label: Relational (Postgres/MySQL)
---

# Relational Databases

The `PostgresSource` allows you to evaluate clinical logic against FHIR data stored in traditional relational databases. 

## Supported Databases

*   PostgreSQL
*   MySQL
*   SQLite

## Usage

You must define a mapping between your database table columns and the standard FHIR4DS columns.

```python
from fhir4ds.sources import PostgresSource, PostgresTableMapping

# Define which columns in your 'raw_fhir' table match the engine's requirements
mapping = PostgresTableMapping(
    table_name="raw_fhir",
    id_col="logical_id",
    type_col="resource_type",
    resource_col="json_blob",
    patient_col="subject_id"
)

source = PostgresSource(
    connection_string="postgresql://user:pass@localhost:5432/db",
    mapping=mapping
)

fhir4ds.attach(con, source)
```

## How it Works

When you attach a relational source, DuckDB uses its **Database Scanners** (e.g., the `postgres` extension) to pull data from the remote database on-demand. 

This is much faster than traditional ETL because only the specific resources required for your CQL or FHIRPath query are fetched from the remote database.
