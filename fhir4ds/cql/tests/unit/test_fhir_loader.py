"""Unit tests for FHIRDataLoader."""

import pytest
import json
from pathlib import Path
import duckdb

from ...loader import FHIRDataLoader
from ...dependency.types import ResolvedValueSet


@pytest.fixture
def duckdb_con():
    """Create an in-memory DuckDB connection."""
    con = duckdb.connect(":memory:")
    yield con
    con.close()


@pytest.fixture
def loader(duckdb_con):
    """Create a FHIRDataLoader instance."""
    return FHIRDataLoader(duckdb_con)


def test_load_single_resource(loader):
    """Test loading a single FHIR resource."""
    patient = {"resourceType": "Patient", "id": "p1", "name": [{"family": "Test"}]}
    loader.load_resource(patient)

    assert loader.count() == 1
    assert loader.count("Patient") == 1


def test_load_multiple_resources(loader):
    """Test loading multiple resources."""
    patient = {"resourceType": "Patient", "id": "p1"}
    observation = {"resourceType": "Observation", "id": "o1"}
    condition = {"resourceType": "Condition", "id": "c1"}

    loader.load_resource(patient)
    loader.load_resource(observation)
    loader.load_resource(condition)

    assert loader.count() == 3
    assert loader.count("Patient") == 1
    assert loader.count("Observation") == 1
    assert loader.count("Condition") == 1


def test_load_bundle(loader):
    """Test loading resources from a FHIR Bundle."""
    bundle = {
        "resourceType": "Bundle",
        "type": "collection",
        "entry": [
            {"resource": {"resourceType": "Patient", "id": "p1"}},
            {"resource": {"resourceType": "Observation", "id": "o1"}},
            {"resource": {"resourceType": "Condition", "id": "c1"}}
        ]
    }

    count = loader.load_bundle(bundle)
    assert count == 3
    assert loader.count() == 3
    assert loader.count("Patient") == 1


def test_load_bundle_with_nested_resources(loader):
    """Test loading bundle with nested contained resources."""
    bundle = {
        "resourceType": "Bundle",
        "entry": [
            {
                "resource": {
                    "resourceType": "Patient",
                    "id": "p1",
                    "contained": [
                        {"resourceType": "Organization", "id": "org1"}
                    ]
                }
            }
        ]
    }

    count = loader.load_bundle(bundle)
    # Only top-level resources are loaded (Patient)
    assert count == 1
    assert loader.count("Patient") == 1


def test_load_bundle_invalid(loader):
    """Test that loading non-bundle raises error."""
    not_a_bundle = {"resourceType": "Patient", "id": "p1"}

    with pytest.raises(ValueError, match="Expected a FHIR Bundle"):
        loader.load_bundle(not_a_bundle)


def test_load_ndjson(loader, tmp_path):
    """Test loading from NDJSON file."""
    ndjson_file = tmp_path / "test.ndjson"
    ndjson_file.write_text(
        '{"resourceType": "Patient", "id": "p1"}\n'
        '{"resourceType": "Patient", "id": "p2"}\n'
        '{"resourceType": "Observation", "id": "o1"}\n'
    )

    count = loader.load_ndjson(ndjson_file)
    assert count == 3
    assert loader.count("Patient") == 2
    assert loader.count("Observation") == 1


def test_load_ndjson_with_empty_lines(loader, tmp_path):
    """Test loading NDJSON with empty lines."""
    ndjson_file = tmp_path / "test.ndjson"
    ndjson_file.write_text(
        '{"resourceType": "Patient", "id": "p1"}\n'
        '\n'
        '{"resourceType": "Patient", "id": "p2"}\n'
        '   \n'
    )

    count = loader.load_ndjson(ndjson_file)
    assert count == 2


def test_load_file_single_resource(loader, tmp_path):
    """Test loading a single resource JSON file."""
    resource_file = tmp_path / "patient.json"
    resource_file.write_text(json.dumps({
        "resourceType": "Patient",
        "id": "p1",
        "name": [{"family": "Test"}]
    }))

    count = loader.load_file(resource_file)
    assert count == 1
    assert loader.count("Patient") == 1


def test_load_file_bundle(loader, tmp_path):
    """Test loading a Bundle JSON file."""
    bundle_file = tmp_path / "bundle.json"
    bundle_file.write_text(json.dumps({
        "resourceType": "Bundle",
        "entry": [
            {"resource": {"resourceType": "Patient", "id": "p1"}},
            {"resource": {"resourceType": "Patient", "id": "p2"}}
        ]
    }))

    count = loader.load_file(bundle_file)
    assert count == 2
    assert loader.count("Patient") == 2


def test_load_directory(loader, tmp_path):
    """Test loading all files from a directory."""
    # Create multiple files
    (tmp_path / "patient1.json").write_text(json.dumps({
        "resourceType": "Patient", "id": "p1"
    }))
    (tmp_path / "patient2.json").write_text(json.dumps({
        "resourceType": "Patient", "id": "p2"
    }))

    # Create NDJSON file
    (tmp_path / "observations.ndjson").write_text(
        '{"resourceType": "Observation", "id": "o1"}\n'
        '{"resourceType": "Observation", "id": "o2"}\n'
    )

    count = loader.load_directory(tmp_path)
    assert count == 4
    assert loader.count("Patient") == 2
    assert loader.count("Observation") == 2


def test_load_directory_recursive(loader, tmp_path):
    """Test recursive directory loading."""
    subdir = tmp_path / "subdir"
    subdir.mkdir()

    (tmp_path / "root.json").write_text(json.dumps({
        "resourceType": "Patient", "id": "p1"
    }))
    (subdir / "nested.json").write_text(json.dumps({
        "resourceType": "Patient", "id": "p2"
    }))

    # Recursive (default)
    count = loader.load_directory(tmp_path, recursive=True)
    assert count == 2

    # Clear and test non-recursive
    loader.clear()
    count = loader.load_directory(tmp_path, recursive=False)
    assert count == 1


def test_load_valuesets(loader):
    """Test loading valueset codes into database."""
    valuesets = [
        ResolvedValueSet(
            url="http://example.org/ValueSet/Test",
            source_path=Path("."),
            codes=[
                {"system": "http://loinc.org", "code": "12345", "display": "Test Code"},
                {"system": "http://loinc.org", "code": "67890", "display": "Another Code"}
            ]
        )
    ]

    count = loader.load_valuesets(valuesets)
    assert count == 2
    assert loader.count_valueset_codes("http://example.org/ValueSet/Test") == 2


def test_load_valuesets_multiple(loader):
    """Test loading multiple valuesets."""
    valuesets = [
        ResolvedValueSet(
            url="http://example.org/ValueSet/VS1",
            source_path=Path("."),
            codes=[
                {"system": "http://loinc.org", "code": "1", "display": "A"}
            ]
        ),
        ResolvedValueSet(
            url="http://example.org/ValueSet/VS2",
            source_path=Path("."),
            codes=[
                {"system": "http://loinc.org", "code": "2", "display": "B"},
                {"system": "http://loinc.org", "code": "3", "display": "C"}
            ]
        )
    ]

    count = loader.load_valuesets(valuesets)
    assert count == 3
    assert loader.count_valueset_codes("http://example.org/ValueSet/VS1") == 1
    assert loader.count_valueset_codes("http://example.org/ValueSet/VS2") == 2


def test_load_valuesets_from_dict(loader):
    """Test loading valuesets passed as dictionaries."""
    valuesets = [
        {
            "url": "http://example.org/ValueSet/Dict",
            "codes": [
                {"system": "http://snomed.info/sct", "code": "ABC", "display": "Dict Code"}
            ]
        }
    ]

    count = loader.load_valuesets(valuesets)
    assert count == 1
    assert loader.count_valueset_codes("http://example.org/ValueSet/Dict") == 1


def test_count_valueset_codes(loader):
    """Test counting valueset codes."""
    valuesets = [
        ResolvedValueSet(
            url="http://example.org/ValueSet/Test",
            source_path=Path("."),
            codes=[
                {"system": "http://loinc.org", "code": "1", "display": "A"},
                {"system": "http://loinc.org", "code": "2", "display": "B"}
            ]
        )
    ]

    loader.load_valuesets(valuesets)

    # Count specific valueset
    assert loader.count_valueset_codes("http://example.org/ValueSet/Test") == 2

    # Count all valueset codes
    assert loader.count_valueset_codes() == 2


def test_clear(loader):
    """Test clearing resources."""
    loader.load_resource({"resourceType": "Patient", "id": "p1"})
    loader.load_resource({"resourceType": "Observation", "id": "o1"})

    assert loader.count() == 2

    loader.clear()
    assert loader.count() == 0


def test_clear_valuesets(loader):
    """Test clearing valueset codes."""
    valuesets = [
        ResolvedValueSet(
            url="http://example.org/ValueSet/Test",
            source_path=Path("."),
            codes=[{"system": "s", "code": "c", "display": "d"}]
        )
    ]

    loader.load_valuesets(valuesets)
    assert loader.count_valueset_codes() == 1

    loader.clear_valuesets()
    assert loader.count_valueset_codes() == 0


def test_custom_table_name(duckdb_con):
    """Test using custom table name."""
    loader = FHIRDataLoader(duckdb_con, table_name="custom_resources")
    loader.load_resource({"resourceType": "Patient", "id": "p1"})

    # Verify data in custom table
    result = duckdb_con.execute("SELECT COUNT(*) FROM custom_resources").fetchone()
    assert result[0] == 1


def test_no_auto_create_table(duckdb_con):
    """Test that table is not created when create_table=False."""
    loader = FHIRDataLoader(duckdb_con, create_table=False)

    # Table should not exist
    result = duckdb_con.execute(
        "SELECT COUNT(*) FROM information_schema.tables WHERE table_name = 'resources'"
    ).fetchone()
    assert result[0] == 0


def test_load_from_url(loader, tmp_path, monkeypatch):
    """Test loading from URL (mocked)."""
    import urllib.request

    # Create a mock response
    bundle_data = {
        "resourceType": "Bundle",
        "entry": [
            {"resource": {"resourceType": "Patient", "id": "url-p1"}}
        ]
    }

    # Mock urlopen
    class MockResponse:
        def read(self):
            return json.dumps(bundle_data).encode()
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass

    def mock_urlopen(*args, **kwargs):
        return MockResponse()

    monkeypatch.setattr(urllib.request, "urlopen", mock_urlopen)

    count = loader.load_from_url("http://example.org/fhir/Patient")
    assert count == 1
    assert loader.count("Patient") == 1


def test_resource_json_stored_correctly(loader, duckdb_con):
    """Test that resource JSON is stored correctly."""
    patient = {
        "resourceType": "Patient",
        "id": "p1",
        "name": [{"family": "Test", "given": ["John"]}],
        "birthDate": "1990-01-01"
    }

    loader.load_resource(patient)

    # Verify stored JSON
    result = duckdb_con.execute(
        "SELECT id, resourceType, resource FROM resources WHERE id = 'p1'"
    ).fetchone()

    assert result[0] == "p1"
    assert result[1] == "Patient"

    stored_resource = json.loads(result[2])
    assert stored_resource["name"][0]["family"] == "Test"
    assert stored_resource["birthDate"] == "1990-01-01"


# ── CRITICAL-9 regression tests: duplicate resource deduplication ──


def test_duplicate_resource_same_type_deduplicated(loader, duckdb_con):
    """Loading the same (id, resourceType) twice keeps only the latest version.

    Regression test for CRITICAL-9: duplicate resource IDs must be
    deduplicated to prevent data integrity corruption in measure results.

    Per FHIR spec, each resource is uniquely identified by its
    resourceType and id within a server.
    """
    loader.load_resource({"resourceType": "Patient", "id": "dup1", "name": [{"family": "V1"}]})
    loader.load_resource({"resourceType": "Patient", "id": "dup1", "name": [{"family": "V2"}]})

    # Should be exactly 1 row
    count = duckdb_con.execute(
        "SELECT COUNT(*) FROM resources WHERE id = 'dup1' AND resourceType = 'Patient'"
    ).fetchone()[0]
    assert count == 1, f"Expected 1 row for (dup1, Patient), got {count}"

    # Latest version should be kept
    resource = duckdb_con.execute(
        "SELECT resource FROM resources WHERE id = 'dup1' AND resourceType = 'Patient'"
    ).fetchone()[0]
    data = json.loads(resource)
    assert data["name"][0]["family"] == "V2", "Latest version should overwrite previous"


def test_same_id_different_type_both_kept(loader, duckdb_con):
    """Same id with different resourceTypes should both be kept.

    FHIR identity is (resourceType, id), not just id alone.
    """
    loader.load_resource({"resourceType": "Patient", "id": "shared1"})
    loader.load_resource({"resourceType": "Observation", "id": "shared1"})

    total = duckdb_con.execute(
        "SELECT COUNT(*) FROM resources WHERE id = 'shared1'"
    ).fetchone()[0]
    assert total == 2, f"Expected 2 rows for different types with same id, got {total}"


def test_null_id_resources_not_deduplicated(loader, duckdb_con):
    """Resources without an id (e.g., contained) should not be deduplicated."""
    loader.load_resource({"resourceType": "Patient"})
    loader.load_resource({"resourceType": "Patient"})

    null_count = duckdb_con.execute(
        "SELECT COUNT(*) FROM resources WHERE id IS NULL"
    ).fetchone()[0]
    assert null_count >= 2, "Null-id resources should not be deduplicated"


def test_bundle_deduplication(loader, duckdb_con):
    """Bundles containing duplicate entries should deduplicate them."""
    bundle = {
        "resourceType": "Bundle",
        "type": "collection",
        "entry": [
            {"resource": {"resourceType": "Patient", "id": "bp1"}},
            {"resource": {"resourceType": "Patient", "id": "bp1"}},
            {"resource": {"resourceType": "Observation", "id": "bo1"}},
        ]
    }
    loader.load_bundle(bundle)

    assert loader.count("Patient") == 1
    assert loader.count("Observation") == 1


# ---------------------------------------------------------------------------
# QA-006: load_bundle(None) must raise TypeError, not AttributeError
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("bad_input", [None, 42, "not-a-dict", []])
def test_load_bundle_rejects_non_dict(loader, bad_input):
    """load_bundle must raise TypeError for non-dict inputs (QA-006)."""
    with pytest.raises(TypeError, match="Expected dict for bundle"):
        loader.load_bundle(bad_input)
