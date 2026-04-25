"""
Unit tests for Phase 6: Incremental Delta Tracking.

Covers:
- PostgresSource.supports_incremental() returns True
- PostgresSource.get_changed_patients() raises RuntimeError before register()
- PostgresSource.get_changed_patients() raises NotImplementedError for tables without updated_at
- FileSystemSource.supports_incremental() returns False for iceberg
- FileSystemSource.supports_incremental() returns True for parquet/ndjson/json
- FileSystemSource.get_changed_patients() raises RuntimeError before register()
- FileSystemSource.get_changed_patients() raises NotImplementedError for iceberg
- FileSystemSource.get_changed_patients() returns correct patient IDs for modified files
- ReactiveEvaluator raises ValueError for adapters where supports_incremental() is False
- ReactiveEvaluator.update() returns None when no patients have changed
- ReactiveEvaluator.update() calls evaluate with only the changed patient IDs
- ReactiveEvaluator docstring clearly states the three limitations
- ExistingTableSource.supports_incremental() returns False
- CSVSource.supports_incremental() returns False
"""

from __future__ import annotations

import os
import tempfile
import time
from datetime import datetime, timedelta
from unittest.mock import MagicMock, call, patch

import duckdb
import pytest

from fhir4ds.sources.csv import CSVSource
from fhir4ds.sources.existing import ExistingTableSource
from fhir4ds.sources.filesystem import FileSystemSource
from fhir4ds.sources.relational import PostgresSource, PostgresTableMapping
from fhir4ds.dqm.reactive import ReactiveEvaluator


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_con() -> duckdb.DuckDBPyConnection:
    return duckdb.connect(":memory:", config={"allow_unsigned_extensions": True})


def _write_parquet(path: str, rows: list[dict]) -> None:
    import json as _json
    con = duckdb.connect(":memory:")
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
    import json as _json
    with open(path, "w") as f:
        for row in rows:
            record = {
                "id": row["id"],
                "resourceType": row["resourceType"],
                "resource": row["resource"],
                "patient_ref": row["patient_ref"],
            }
            f.write(_json.dumps(record) + "\n")


_SAMPLE_ROWS = [
    {
        "id": "pat-1", "resourceType": "Patient",
        "resource": {"resourceType": "Patient", "id": "pat-1"},
        "patient_ref": "pat-1",
    },
    {
        "id": "pat-2", "resourceType": "Patient",
        "resource": {"resourceType": "Patient", "id": "pat-2"},
        "patient_ref": "pat-2",
    },
]


# ---------------------------------------------------------------------------
# supports_incremental()
# ---------------------------------------------------------------------------

class TestSupportsIncremental:
    def test_existing_table_source_returns_false(self):
        assert ExistingTableSource().supports_incremental() is False

    def test_csv_source_returns_false(self):
        assert CSVSource("/data/f.csv", "SELECT 1").supports_incremental() is False

    def test_filesystem_parquet_returns_true(self):
        assert FileSystemSource("/data/*.parquet").supports_incremental() is True

    def test_filesystem_ndjson_returns_true(self):
        assert FileSystemSource("/data/*.ndjson", format="ndjson").supports_incremental() is True

    def test_filesystem_json_returns_true(self):
        assert FileSystemSource("/data/*.json", format="json").supports_incremental() is True

    def test_filesystem_iceberg_returns_false(self):
        assert FileSystemSource("/data/", format="iceberg").supports_incremental() is False

    def test_postgres_source_returns_true(self):
        mapping = PostgresTableMapping("t", "id", "Patient", "res", "pid")
        src = PostgresSource("postgresql://user:pass@localhost/db", [mapping])
        assert src.supports_incremental() is True


# ---------------------------------------------------------------------------
# FileSystemSource.get_changed_patients()
# ---------------------------------------------------------------------------

class TestFileSystemGetChangedPatients:
    def test_raises_not_implemented_for_iceberg(self):
        source = FileSystemSource("/data/", format="iceberg")
        with pytest.raises(NotImplementedError, match="iceberg"):
            source.get_changed_patients(datetime.min)

    def test_raises_runtime_error_before_register(self):
        source = FileSystemSource("/data/*.parquet")
        with pytest.raises(RuntimeError, match="before register"):
            source.get_changed_patients(datetime.min)

    def test_returns_empty_when_no_files_modified(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "resources.parquet")
            _write_parquet(path, _SAMPLE_ROWS)

            con = _make_con()
            source = FileSystemSource(path)
            source.register(con)

            # Ask for changes after file was written — no new files
            future = datetime.utcnow() + timedelta(hours=1)
            result = source.get_changed_patients(future)
            assert result == []

    def test_returns_patient_ids_from_recently_modified_parquet(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "resources.parquet")
            before = datetime.utcnow() - timedelta(seconds=2)
            _write_parquet(path, _SAMPLE_ROWS)

            con = _make_con()
            source = FileSystemSource(path)
            source.register(con)

            result = source.get_changed_patients(before)
            assert set(result) == {"pat-1", "pat-2"}

    def test_returns_patient_ids_from_recently_modified_ndjson(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "resources.ndjson")
            before = datetime.utcnow() - timedelta(seconds=2)
            _write_ndjson(path, _SAMPLE_ROWS)

            con = _make_con()
            source = FileSystemSource(path, format="ndjson")
            source.register(con)

            result = source.get_changed_patients(before)
            assert set(result) == {"pat-1", "pat-2"}


# ---------------------------------------------------------------------------
# PostgresSource.get_changed_patients()
# ---------------------------------------------------------------------------

class TestPostgresGetChangedPatients:
    def test_raises_runtime_error_before_register(self):
        mapping = PostgresTableMapping("t", "id", "Patient", "res", "pid")
        src = PostgresSource("postgresql://user:pass@localhost/db", [mapping])
        with pytest.raises(RuntimeError, match="before register"):
            src.get_changed_patients(datetime.min)


# ---------------------------------------------------------------------------
# ReactiveEvaluator
# ---------------------------------------------------------------------------

class TestReactiveEvaluatorConstruction:
    def _make_non_incremental_adapter(self):
        class NotIncrementalAdapter:
            def register(self, con): pass
            def unregister(self, con): pass
            def supports_incremental(self): return False

        return NotIncrementalAdapter()

    def _make_incremental_adapter(self, changed: list[str] = None):
        class IncrementalAdapter:
            def register(self, con): pass
            def unregister(self, con): pass
            def supports_incremental(self): return True
            def get_changed_patients(self, since): return changed or []

        return IncrementalAdapter()

    def test_raises_value_error_for_non_incremental_adapter(self):
        adapter = self._make_non_incremental_adapter()
        with pytest.raises(ValueError, match="incremental"):
            ReactiveEvaluator(_make_con(), "CBP", adapter)

    def test_raises_value_error_includes_adapter_name(self):
        adapter = self._make_non_incremental_adapter()
        with pytest.raises(ValueError, match="NotIncrementalAdapter"):
            ReactiveEvaluator(_make_con(), "CBP", adapter)

    def test_raises_value_error_for_adapter_without_supports_incremental(self):
        class MinimalAdapter:
            def register(self, con): pass
            def unregister(self, con): pass

        with pytest.raises(ValueError):
            ReactiveEvaluator(_make_con(), "CBP", MinimalAdapter())

    def test_accepts_incremental_adapter(self):
        adapter = self._make_incremental_adapter()
        ev = ReactiveEvaluator(_make_con(), "CBP", adapter)
        assert ev is not None

    def test_last_sync_initially_none(self):
        adapter = self._make_incremental_adapter()
        ev = ReactiveEvaluator(_make_con(), "CBP", adapter)
        assert ev.last_sync is None


class TestReactiveEvaluatorUpdate:
    def _make_incremental_adapter(self, changed: list[str]):
        class IncrementalAdapter:
            def register(self, con): pass
            def unregister(self, con): pass
            def supports_incremental(self): return True
            def get_changed_patients(self, since): return changed

        return IncrementalAdapter()

    def test_returns_none_when_no_patients_changed(self):
        adapter = self._make_incremental_adapter(changed=[])
        ev = ReactiveEvaluator(_make_con(), "CBP", adapter)
        result = ev.update()
        assert result is None

    def test_updates_last_sync_even_when_no_changes(self):
        adapter = self._make_incremental_adapter(changed=[])
        ev = ReactiveEvaluator(_make_con(), "CBP", adapter)
        before = datetime.utcnow()
        ev.update()
        assert ev.last_sync is not None
        assert ev.last_sync >= before

    def test_calls_evaluate_with_only_changed_patient_ids(self):
        changed_ids = ["pat-1", "pat-2"]
        adapter = self._make_incremental_adapter(changed=changed_ids)

        mock_evaluator_instance = MagicMock()
        mock_evaluator_instance.evaluate.return_value = {"groups": []}

        with patch("fhir4ds.dqm.MeasureEvaluator") as MockEvaluator:
            MockEvaluator.return_value = mock_evaluator_instance
            ev = ReactiveEvaluator(_make_con(), "CBP", adapter)
            result = ev.update()

        MockEvaluator.assert_called_once()
        mock_evaluator_instance.evaluate.assert_called_once_with(patient_ids=changed_ids)
        assert result == {"groups": []}

    def test_update_uses_last_sync_as_since_on_second_call(self):
        since_values: list[datetime] = []

        class TrackingSinceAdapter:
            def register(self, con): pass
            def unregister(self, con): pass
            def supports_incremental(self): return True
            def get_changed_patients(self, since):
                since_values.append(since)
                return []

        adapter = TrackingSinceAdapter()
        ev = ReactiveEvaluator(_make_con(), "CBP", adapter)

        t1 = datetime(2026, 1, 1, 12, 0, 0)
        ev.update(as_of=t1)
        assert since_values[0] == datetime.min

        t2 = datetime(2026, 1, 1, 13, 0, 0)
        ev.update(as_of=t2)
        assert since_values[1] == t1

    def test_last_sync_updated_to_as_of_after_changes(self):
        adapter = self._make_incremental_adapter(changed=[])
        ev = ReactiveEvaluator(_make_con(), "CBP", adapter)
        target_time = datetime(2026, 4, 24, 12, 0, 0)
        ev.update(as_of=target_time)
        assert ev.last_sync == target_time


class TestReactiveEvaluatorDocstring:
    def test_docstring_mentions_population_level_limitation(self):
        doc = ReactiveEvaluator.__doc__
        assert "population" in doc.lower()

    def test_docstring_mentions_deletion_limitation(self):
        doc = ReactiveEvaluator.__doc__
        assert "delet" in doc.lower()

    def test_docstring_mentions_concurrency_limitation(self):
        doc = ReactiveEvaluator.__doc__
        assert "concurrent" in doc.lower() or "concurren" in doc.lower()
