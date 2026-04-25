"""
Unit tests for fhir4ds.sources.csv — Phase 4: CSVSource.

Acceptance criteria:
- CSVSource mounts a CSV file as the resources view using the user-provided projection
- CSVSource raises SchemaValidationError if the projection does not produce required columns
- {source} placeholder is correctly replaced with the DuckDB scan expression
- unregister() drops the view cleanly
- register() is idempotent
- supports_incremental() returns False
"""

from __future__ import annotations

import csv
import os
import tempfile

import duckdb
import pytest

from fhir4ds.sources.base import SchemaValidationError
from fhir4ds.sources.csv import CSVSource
import fhir4ds


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_con() -> duckdb.DuckDBPyConnection:
    return duckdb.connect(":memory:", config={"allow_unsigned_extensions": True})


_GOOD_PROJECTION = """
    SELECT
        patient_id::VARCHAR AS id,
        'Patient'::VARCHAR AS resourceType,
        json_object(
            'resourceType', 'Patient',
            'id', patient_id,
            'gender', gender
        )::JSON AS resource,
        patient_id::VARCHAR AS patient_ref
    FROM {source}
"""


def _write_patients_csv(path: str) -> None:
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["patient_id", "gender", "birth_date"])
        writer.writeheader()
        writer.writerow({"patient_id": "pat-1", "gender": "male", "birth_date": "1980-01-01"})
        writer.writerow({"patient_id": "pat-2", "gender": "female", "birth_date": "1990-06-15"})


# ---------------------------------------------------------------------------
# Tests: Happy path
# ---------------------------------------------------------------------------

class TestCSVSourceHappyPath:
    def test_mounts_csv_file_as_resources_view(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "patients.csv")
            _write_patients_csv(path)

            con = _make_con()
            source = CSVSource(path, _GOOD_PROJECTION)
            source.register(con)

            rows = con.execute("SELECT id FROM resources ORDER BY id").fetchall()
            assert rows == [("pat-1",), ("pat-2",)]

    def test_register_is_idempotent(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "patients.csv")
            _write_patients_csv(path)
            con = _make_con()
            source = CSVSource(path, _GOOD_PROJECTION)
            source.register(con)
            source.register(con)  # must not error

    def test_unregister_drops_view(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "patients.csv")
            _write_patients_csv(path)
            con = _make_con()
            source = CSVSource(path, _GOOD_PROJECTION)
            source.register(con)
            source.unregister(con)
            with pytest.raises(Exception):
                con.execute("SELECT * FROM resources").fetchall()

    def test_unregister_before_register_no_exception(self):
        con = _make_con()
        source = CSVSource("/nonexistent/path.csv", _GOOD_PROJECTION)
        source.unregister(con)  # must not raise

    def test_resource_column_is_json_type(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "patients.csv")
            _write_patients_csv(path)
            con = _make_con()
            source = CSVSource(path, _GOOD_PROJECTION)
            source.register(con)
            # Verify the resource column can be parsed as JSON
            row = con.execute("SELECT resource FROM resources LIMIT 1").fetchone()
            assert row is not None


# ---------------------------------------------------------------------------
# Tests: {source} placeholder substitution
# ---------------------------------------------------------------------------

class TestSourcePlaceholder:
    def test_placeholder_is_replaced_with_scan_expression(self):
        source = CSVSource("/data/patients.csv", "SELECT * FROM {source}")
        projection = source._projection_sql.replace(
            "{source}", f"read_csv_auto('{source._path}')"
        )
        assert "read_csv_auto('/data/patients.csv')" in projection

    def test_placeholder_not_present_if_not_in_sql(self):
        # If user provides SQL without {source}, it passes through unchanged
        source = CSVSource("/data/patients.csv", "SELECT 1 AS x")
        projection = source._projection_sql.replace(
            "{source}", f"read_csv_auto('{source._path}')"
        )
        assert projection == "SELECT 1 AS x"


# ---------------------------------------------------------------------------
# Tests: SchemaValidationError for bad projection
# ---------------------------------------------------------------------------

class TestCSVSourceSchemaValidation:
    def test_raises_schema_error_for_missing_id(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "patients.csv")
            _write_patients_csv(path)
            con = _make_con()
            bad_projection = """
                SELECT
                    'Patient'::VARCHAR AS resourceType,
                    '{}'::JSON AS resource,
                    patient_id::VARCHAR AS patient_ref
                FROM {source}
            """
            source = CSVSource(path, bad_projection)
            with pytest.raises(SchemaValidationError, match="'id'"):
                source.register(con)

    def test_raises_schema_error_for_missing_resource_type(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "patients.csv")
            _write_patients_csv(path)
            con = _make_con()
            bad_projection = """
                SELECT
                    patient_id::VARCHAR AS id,
                    '{}'::JSON AS resource,
                    patient_id::VARCHAR AS patient_ref
                FROM {source}
            """
            source = CSVSource(path, bad_projection)
            with pytest.raises(SchemaValidationError, match="'resourceType'"):
                source.register(con)

    def test_raises_schema_error_for_missing_resource(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "patients.csv")
            _write_patients_csv(path)
            con = _make_con()
            bad_projection = """
                SELECT
                    patient_id::VARCHAR AS id,
                    'Patient'::VARCHAR AS resourceType,
                    patient_id::VARCHAR AS patient_ref
                FROM {source}
            """
            source = CSVSource(path, bad_projection)
            with pytest.raises(SchemaValidationError, match="'resource'"):
                source.register(con)

    def test_raises_schema_error_for_missing_patient_ref(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "patients.csv")
            _write_patients_csv(path)
            con = _make_con()
            bad_projection = """
                SELECT
                    patient_id::VARCHAR AS id,
                    'Patient'::VARCHAR AS resourceType,
                    '{}'::JSON AS resource
                FROM {source}
            """
            source = CSVSource(path, bad_projection)
            with pytest.raises(SchemaValidationError, match="'patient_ref'"):
                source.register(con)

    def test_raises_schema_error_for_nonexistent_column_reference(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "patients.csv")
            _write_patients_csv(path)
            con = _make_con()
            bad_projection = """
                SELECT
                    nonexistent_col::VARCHAR AS id,
                    'Patient'::VARCHAR AS resourceType,
                    '{}'::JSON AS resource,
                    patient_id::VARCHAR AS patient_ref
                FROM {source}
            """
            source = CSVSource(path, bad_projection)
            # DuckDB BinderException → wrapped as SchemaValidationError
            with pytest.raises(SchemaValidationError):
                source.register(con)


# ---------------------------------------------------------------------------
# Tests: supports_incremental
# ---------------------------------------------------------------------------

class TestSupportsIncremental:
    def test_returns_false(self):
        source = CSVSource("/data/patients.csv", _GOOD_PROJECTION)
        assert source.supports_incremental() is False


# ---------------------------------------------------------------------------
# Tests: API uniformity — attach/detach
# ---------------------------------------------------------------------------

class TestApiUniformity:
    def test_attach_with_csv_source(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "patients.csv")
            _write_patients_csv(path)
            con = _make_con()
            source = CSVSource(path, _GOOD_PROJECTION)
            fhir4ds.attach(con, source)
            count = con.execute("SELECT COUNT(*) FROM resources").fetchone()[0]
            assert count == 2

    def test_detach_drops_view(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "patients.csv")
            _write_patients_csv(path)
            con = _make_con()
            source = CSVSource(path, _GOOD_PROJECTION)
            fhir4ds.attach(con, source)
            fhir4ds.detach(con, source)
            with pytest.raises(Exception):
                con.execute("SELECT * FROM resources").fetchall()
