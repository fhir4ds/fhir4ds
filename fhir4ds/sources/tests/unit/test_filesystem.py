"""
Unit tests for fhir4ds.sources.filesystem — Phase 2: FileSystemSource.

Acceptance criteria:
- FileSystemSource mounts a local Parquet directory as the resources view
- FileSystemSource mounts a local NDJSON file as the resources view
- FileSystemSource raises ValueError for unsupported format
- FileSystemSource raises SchemaValidationError if Parquet files are missing required columns
- FileSystemSource emits UserWarning when a cloud URI is used without credentials
- FileSystemSource with CloudCredentials configures a DuckDB secret before creating the view
- hive_partitioning=True passes the option through to read_parquet
- unregister() drops the view cleanly
- register() is idempotent — calling twice does not error
"""

from __future__ import annotations

import json
import os
import tempfile
import warnings

import duckdb
import pytest

from fhir4ds.sources.base import SchemaValidationError
from fhir4ds.sources.filesystem import CloudCredentials, FileSystemSource


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_con() -> duckdb.DuckDBPyConnection:
    return duckdb.connect(":memory:", config={"allow_unsigned_extensions": True})


def _write_parquet(path: str, rows: list[dict]) -> None:
    """Write a list of row dicts to a Parquet file using DuckDB."""
    con = duckdb.connect(":memory:")
    import json as _json
    values = ", ".join(
        f"('{r['id']}', '{r['resourceType']}', '{_json.dumps(r['resource'])}'::JSON, '{r['patient_ref']}')"
        for r in rows
    )
    con.execute(f"""
        COPY (
            SELECT * FROM (VALUES {values}) t(id, resourceType, resource, patient_ref)
        ) TO '{path}' (FORMAT PARQUET)
    """)


def _write_ndjson(path: str, rows: list[dict]) -> None:
    """Write a list of row dicts to an NDJSON file.

    The ``resource`` field is written as a nested JSON object so that
    DuckDB's ``read_json_auto`` reads it as a STRUCT, which can then be
    cast to JSON in the view.
    """
    with open(path, "w") as f:
        for row in rows:
            record = {
                "id": row["id"],
                "resourceType": row["resourceType"],
                "resource": row["resource"],   # nested object → DuckDB STRUCT → castable to JSON
                "patient_ref": row["patient_ref"],
            }
            f.write(json.dumps(record) + "\n")


_SAMPLE_ROWS = [
    {
        "id": "pat-1",
        "resourceType": "Patient",
        "resource": {"resourceType": "Patient", "id": "pat-1"},
        "patient_ref": "pat-1",
    },
    {
        "id": "obs-1",
        "resourceType": "Observation",
        "resource": {"resourceType": "Observation", "id": "obs-1"},
        "patient_ref": "pat-1",
    },
]


# ---------------------------------------------------------------------------
# Tests: ValueError for unsupported format
# ---------------------------------------------------------------------------

class TestUnsupportedFormat:
    def test_raises_value_error(self):
        with pytest.raises(ValueError, match="Unsupported format"):
            FileSystemSource("/data/fhir/", format="csv")

    def test_error_message_lists_supported_formats(self):
        with pytest.raises(ValueError, match="parquet"):
            FileSystemSource("/data/fhir/", format="avro")


# ---------------------------------------------------------------------------
# Tests: Parquet source
# ---------------------------------------------------------------------------

class TestParquetSource:
    def test_mounts_local_parquet_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "resources.parquet")
            _write_parquet(path, _SAMPLE_ROWS)

            con = _make_con()
            source = FileSystemSource(path)
            source.register(con)

            rows = con.execute("SELECT id FROM resources ORDER BY id").fetchall()
            assert ("obs-1",) in rows
            assert ("pat-1",) in rows

    def test_raises_schema_error_for_missing_column(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "bad.parquet")
            # Write Parquet with missing patient_ref column
            inner_con = duckdb.connect(":memory:")
            inner_con.execute(f"""
                COPY (SELECT 'p1'::VARCHAR AS id, 'Patient'::VARCHAR AS resourceType,
                             '{{}}'::JSON AS resource)
                TO '{path}' (FORMAT PARQUET)
            """)
            con = _make_con()
            source = FileSystemSource(path)
            # DuckDB raises BinderException when column is missing; we wrap as SchemaValidationError
            with pytest.raises(SchemaValidationError):
                source.register(con)

    def test_hive_partitioning_option_in_scan_expression(self):
        source = FileSystemSource("/data/fhir/**/*.parquet", hive_partitioning=True)
        expr = source._build_scan_expression()
        assert "hive_partitioning=true" in expr

    def test_no_hive_partitioning_by_default(self):
        source = FileSystemSource("/data/fhir/**/*.parquet")
        expr = source._build_scan_expression()
        assert "hive_partitioning" not in expr

    def test_register_is_idempotent(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "resources.parquet")
            _write_parquet(path, _SAMPLE_ROWS)
            con = _make_con()
            source = FileSystemSource(path)
            source.register(con)
            source.register(con)  # must not error

    def test_unregister_drops_view(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "resources.parquet")
            _write_parquet(path, _SAMPLE_ROWS)
            con = _make_con()
            source = FileSystemSource(path)
            source.register(con)
            source.unregister(con)
            with pytest.raises(Exception):
                con.execute("SELECT * FROM resources").fetchall()

    def test_unregister_before_register_no_exception(self):
        con = _make_con()
        source = FileSystemSource("/nonexistent/path.parquet")
        source.unregister(con)  # must not raise


# ---------------------------------------------------------------------------
# Tests: NDJSON source
# ---------------------------------------------------------------------------

class TestNDJSONSource:
    def test_mounts_local_ndjson_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "resources.ndjson")
            _write_ndjson(path, _SAMPLE_ROWS)

            con = _make_con()
            source = FileSystemSource(path, format="ndjson")
            source.register(con)

            rows = con.execute("SELECT id FROM resources ORDER BY id").fetchall()
            assert ("obs-1",) in rows
            assert ("pat-1",) in rows

    def test_json_format_uses_read_json_auto(self):
        source = FileSystemSource("/data/fhir.json", format="json")
        expr = source._build_scan_expression()
        assert "read_json_auto" in expr

    def test_ndjson_format_uses_read_json_auto(self):
        source = FileSystemSource("/data/fhir.ndjson", format="ndjson")
        expr = source._build_scan_expression()
        assert "read_json_auto" in expr


# ---------------------------------------------------------------------------
# Tests: Iceberg source
# ---------------------------------------------------------------------------

class TestIcebergSource:
    def test_iceberg_format_uses_iceberg_scan(self):
        source = FileSystemSource("/data/fhir/", format="iceberg")
        expr = source._build_scan_expression()
        assert "iceberg_scan" in expr

    def test_supports_incremental_returns_false_for_iceberg(self):
        source = FileSystemSource("/data/fhir/", format="iceberg")
        assert source.supports_incremental() is False


# ---------------------------------------------------------------------------
# Tests: Cloud URI warning
# ---------------------------------------------------------------------------

class TestCloudWarning:
    @pytest.mark.parametrize("prefix", ["s3://", "az://", "abfs://", "gs://", "gcs://"])
    def test_warns_when_cloud_uri_without_credentials(self, prefix):
        source = FileSystemSource(f"{prefix}my-bucket/fhir/**/*.parquet")
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            source._warn_if_cloud_without_credentials()
        assert len(caught) == 1
        assert issubclass(caught[0].category, UserWarning)
        assert "cloud URI" in str(caught[0].message)

    def test_no_warning_for_local_path(self):
        source = FileSystemSource("/data/fhir/**/*.parquet")
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            source._warn_if_cloud_without_credentials()
        assert len(caught) == 0

    def test_no_warning_when_credentials_provided(self):
        creds = CloudCredentials("S3", access_key_id="x", secret_access_key="y")
        source = FileSystemSource("s3://bucket/fhir/*.parquet", credentials=creds)
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            source._warn_if_cloud_without_credentials()
        assert len(caught) == 0


# ---------------------------------------------------------------------------
# Tests: CloudCredentials
# ---------------------------------------------------------------------------

class TestCloudCredentials:
    def test_default_secret_name(self):
        creds = CloudCredentials("S3", access_key_id="k", secret_access_key="s")
        assert creds.secret_name == "fhir4ds_s3_secret"

    def test_custom_secret_name(self):
        creds = CloudCredentials("S3", secret_name="my_s3_secret", access_key_id="k")
        assert creds.secret_name == "my_s3_secret"

    def test_provider_is_uppercased(self):
        creds = CloudCredentials("gcs", service_account_json="{}")
        assert creds.provider == "GCS"

    def test_configure_generates_create_secret_sql(self, monkeypatch):
        executed = []

        class FakeCon:
            def execute(self, sql):
                executed.append(sql)

        creds = CloudCredentials("S3", access_key_id="AKID", secret_access_key="SAK")
        creds.configure(FakeCon())
        assert len(executed) == 1
        sql = executed[0]
        assert "CREATE OR REPLACE SECRET" in sql
        assert "TYPE S3" in sql
        assert "access_key_id" in sql
        assert "secret_access_key" in sql


# ---------------------------------------------------------------------------
# Tests: supports_incremental
# ---------------------------------------------------------------------------

class TestSupportsIncremental:
    def test_parquet_is_incremental(self):
        assert FileSystemSource("/data/*.parquet", format="parquet").supports_incremental()

    def test_ndjson_is_incremental(self):
        assert FileSystemSource("/data/*.ndjson", format="ndjson").supports_incremental()

    def test_json_is_incremental(self):
        assert FileSystemSource("/data/*.json", format="json").supports_incremental()

    def test_iceberg_is_not_incremental(self):
        assert not FileSystemSource("/data/", format="iceberg").supports_incremental()
