"""
fhir4ds.sources
===============
Zero-ETL source adapters for fhir4ds.

Each adapter registers an external data source as a DuckDB ``resources``
view that conforms to the fhir4ds schema contract, enabling CQL measures,
FHIRPath queries, and ViewDefinitions to run directly against external data
without copying it into a local DuckDB file.

Adapters
--------
- :class:`ExistingTableSource` — wraps an already-loaded DuckDB table/view
- :class:`FileSystemSource` — Parquet, NDJSON, Iceberg (local or cloud)
- :class:`PostgresSource` — FHIR JSON stored in Postgres columns
- :class:`CSVSource` — flat CSV files with a user-defined SQL projection

Usage::

    import fhir4ds
    from fhir4ds.sources import FileSystemSource

    con = fhir4ds.create_connection(
        source=FileSystemSource('/data/fhir/**/*.parquet')
    )
    # 'resources' view is already mounted — run measures immediately

Cloud storage::

    from fhir4ds.sources import FileSystemSource, CloudCredentials

    creds = CloudCredentials("S3", access_key_id="...", secret_access_key="...")
    source = FileSystemSource("s3://bucket/fhir/**/*.parquet", credentials=creds)
    fhir4ds.attach(con, source)
"""

from fhir4ds.sources.base import SchemaValidationError, SourceAdapter
from fhir4ds.sources.csv import CSVSource
from fhir4ds.sources.existing import ExistingTableSource
from fhir4ds.sources.filesystem import CloudCredentials, FileSystemSource
from fhir4ds.sources.relational import PostgresSource, PostgresTableMapping

__all__ = [
    "SourceAdapter",
    "SchemaValidationError",
    "FileSystemSource",
    "CloudCredentials",
    "PostgresSource",
    "PostgresTableMapping",
    "ExistingTableSource",
    "CSVSource",
]
