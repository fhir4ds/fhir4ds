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


@pytest.mark.parametrize(
    "reference",
    [
        "Patient/p1",
        "p1",
        "http://example.org/fhir/Patient/p1",
        {"reference": "Patient/p1"},
        {"reference": "http://example.org/fhir/Patient/p1"},
    ],
)
def test_resolve_macro_accepts_common_reference_forms(loader, duckdb_con, reference):
    """CQL resolve() should accept HEDIS reference id/url forms."""
    loader.load_resource({"resourceType": "Patient", "id": "p1", "gender": "female"})

    ref_value = json.dumps(reference) if isinstance(reference, dict) else reference

    result = duckdb_con.execute(
        "SELECT json_extract_string(resolve(?), '$.id')",
        [ref_value],
    ).fetchone()

    assert result == ("p1",)


def test_load_resource_rejects_non_standard_json_numbers(loader):
    with pytest.raises(ValueError, match="standard JSON"):
        loader.load_resource({"resourceType": "Patient", "id": "nan", "value": float("nan")})

    with pytest.raises(ValueError, match="standard JSON"):
        loader.load_resource({"resourceType": "Patient", "id": "inf", "value": float("inf")})


@pytest.mark.parametrize(
    "resource_type",
    ["Pаtient", "Patient'; DROP TABLE resources; --", "patient", ""],
)
def test_load_resource_rejects_invalid_resource_type(loader, resource_type):
    with pytest.raises(ValueError, match="resourceType"):
        loader.load_resource({"resourceType": resource_type, "id": "p1"})


@pytest.mark.parametrize("resource_id", [" ", "bad/id", "x" * 65])
def test_load_resource_rejects_invalid_fhir_id(loader, resource_id):
    with pytest.raises(ValueError, match="FHIR id pattern"):
        loader.load_resource({"resourceType": "Patient", "id": resource_id})


def test_load_resources_rejects_none(loader):
    with pytest.raises(TypeError, match="Expected list"):
        loader.load_resources(None)


def test_load_resources_rejects_non_list(loader):
    with pytest.raises(TypeError, match="Expected list"):
        loader.load_resources("not resources")


def test_load_resources_validates_before_insert(loader):
    with pytest.raises(ValueError, match="standard JSON"):
        loader.load_resources([
            {"resourceType": "Patient", "id": "p1"},
            {"resourceType": "Patient", "id": "bad", "value": float("nan")},
        ])
    assert loader.count() == 0


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
        "type": "collection",
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


def test_load_bundle_rejects_malformed_entries(loader):
    with pytest.raises(TypeError, match=r"Bundle\.entry must be a list"):
        loader.load_bundle({"resourceType": "Bundle", "type": "collection", "entry": {"resource": {}}})

    with pytest.raises(TypeError, match=r"Bundle\.entry\[0\] must be an object"):
        loader.load_bundle({"resourceType": "Bundle", "type": "collection", "entry": ["not an entry"]})

    with pytest.raises(TypeError, match=r"Bundle\.entry\[0\]\.resource must be an object"):
        loader.load_bundle({"resourceType": "Bundle", "type": "collection", "entry": [{"resource": "not a resource"}]})


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


def test_load_ndjson_strict_validation_error_is_all_or_nothing(loader, tmp_path):
    """Strict NDJSON loading should not leave partial rows after validation errors."""
    ndjson_file = tmp_path / "bad-valid-json.ndjson"
    ndjson_file.write_text(
        '{"resourceType": "Patient", "id": "p1"}\n'
        '{"id": "missing-resource-type"}\n'
        '{"resourceType": "Patient", "id": "p2"}\n'
    )

    with pytest.raises(ValueError, match="resourceType"):
        loader.load_ndjson(ndjson_file)

    assert loader.count() == 0


def test_load_ndjson_non_strict_skips_invalid_resource_records(loader, tmp_path):
    """Non-strict NDJSON loading skips valid JSON records that are not FHIR resources."""
    ndjson_file = tmp_path / "mixed.ndjson"
    ndjson_file.write_text(
        '{"resourceType": "Patient", "id": "p1"}\n'
        '{"id": "missing-resource-type"}\n'
        '{"resourceType": "Patient", "id": "p2"}\n'
    )

    count = loader.load_ndjson(ndjson_file, strict=False)

    assert count == 2
    assert loader.count("Patient") == 2


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
        "type": "collection",
        "entry": [
            {"resource": {"resourceType": "Patient", "id": "p1"}},
            {"resource": {"resourceType": "Patient", "id": "p2"}}
        ]
    }))

    count = loader.load_file(bundle_file)
    assert count == 2
    assert loader.count("Patient") == 2


@pytest.mark.parametrize(
    ("payload", "type_name"),
    [
        ([], "list"),
        ("not an object", "str"),
        (None, "NoneType"),
    ],
)
def test_load_file_rejects_non_object_json(loader, tmp_path, payload, type_name):
    """Valid JSON that is not a FHIR object should raise an actionable error."""
    resource_file = tmp_path / "not-object.json"
    resource_file.write_text(json.dumps(payload))

    with pytest.raises(TypeError, match=rf"object resource or Bundle.*{type_name}"):
        loader.load_file(resource_file)


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


def test_load_directory_skips_non_object_json(loader, tmp_path):
    """Directory loading should skip non-FHIR JSON shapes without crashing."""
    (tmp_path / "patient.json").write_text(json.dumps({
        "resourceType": "Patient", "id": "p1"
    }))
    (tmp_path / "array.json").write_text(json.dumps([]))

    assert loader.load_directory(tmp_path) == 1
    assert loader.count("Patient") == 1


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


def test_load_valuesets_from_raw_fhir_valueset(loader):
    valuesets = [
        {
            "resourceType": "ValueSet",
            "url": "http://example.org/ValueSet/Raw",
            "compose": {
                "include": [
                    {
                        "system": "http://loinc.org",
                        "concept": [
                            {"code": "1234-5", "display": "Compose Code"},
                        ],
                    }
                ]
            },
            "expansion": {
                "contains": [
                    {
                        "system": "http://snomed.info/sct",
                        "code": "67890",
                        "display": "Expansion Code",
                    }
                ]
            },
        }
    ]

    count = loader.load_valuesets(valuesets)

    assert count == 2
    assert loader.count_valueset_codes("http://example.org/ValueSet/Raw") == 2


def test_load_valuesets_rejects_invalid_inputs(loader):
    with pytest.raises(TypeError, match="valuesets must be a list"):
        loader.load_valuesets(None)

    with pytest.raises(TypeError, match="valuesets must be a list"):
        loader.load_valuesets("not a valueset")

    with pytest.raises(ValueError, match="non-empty string 'url'"):
        loader.load_valuesets([{"not": "a valueset"}])

    with pytest.raises(ValueError, match="'system' and 'code'"):
        loader.load_valuesets([{"url": "http://example.org/vs", "codes": [{"code": "x"}]}])


def test_empty_valueset_helpers_do_not_require_table(loader):
    assert loader.count_valueset_codes() == 0
    loader.clear_valuesets()
    assert loader.count_valueset_codes() == 0


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


def test_custom_resource_table_name_sql_keyword_is_quoted(duckdb_con):
    """SQL keyword table names should work through the loader API."""
    loader = FHIRDataLoader(duckdb_con, table_name="select")
    loader.load_resource({"resourceType": "Patient", "id": "p1", "gender": "female"})

    assert loader.count("Patient") == 1
    assert duckdb_con.execute('SELECT COUNT(*) FROM "select"').fetchone() == (1,)

    resolved = duckdb_con.execute(
        "SELECT json_extract_string(resolve(?), '$.id')",
        ["Patient/p1"],
    ).fetchone()
    assert resolved == ("p1",)

    loader.clear()
    assert loader.count() == 0


def test_custom_valueset_table_name_sql_keyword_is_quoted(duckdb_con):
    """ValueSet code table names use identifier quoting consistently."""
    loader = FHIRDataLoader(duckdb_con)
    valuesets = [
        ResolvedValueSet(
            url="http://example.org/ValueSet/Keyword",
            source_path=Path("."),
            codes=[{"system": "http://loinc.org", "code": "1234-5", "display": "A"}],
        )
    ]

    assert loader.load_valuesets(valuesets, table_name="where") == 1
    assert loader.count_valueset_codes(table_name="where") == 1
    assert (
        loader.count_valueset_codes(
            "http://example.org/ValueSet/Keyword",
            table_name="where",
        )
        == 1
    )
    assert duckdb_con.execute('SELECT COUNT(*) FROM "where"').fetchone() == (1,)

    loader.clear_valuesets(table_name="where")
    assert loader.count_valueset_codes(table_name="where") == 0


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
        "type": "searchset",
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


def test_load_from_url_rejects_file_scheme(loader):
    with pytest.raises(ValueError, match="Only 'http' and 'https'"):
        loader.load_from_url("file:///tmp/patient.json")


def test_load_from_url_rejects_non_http_scheme(loader):
    with pytest.raises(ValueError, match="Unsupported URL scheme"):
        loader.load_from_url("ftp://example.org/patient.json")


def test_load_from_url_rejects_non_object_json(loader, monkeypatch):
    import urllib.request

    class MockResponse:
        def read(self):
            return json.dumps([]).encode()
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass

    monkeypatch.setattr(urllib.request, "urlopen", lambda *args, **kwargs: MockResponse())

    with pytest.raises(TypeError, match="object resource or Bundle.*list"):
        loader.load_from_url("http://example.org/fhir")


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


# --- 0.0.12 evolution campaign, Domain 6 SKEPTIC fixes (QA-001..QA-005) ---

def test_patient_ref_group_subject_not_attributed(loader, duckdb_con):
    """QA-001: non-Patient subject references must not create phantom patients."""
    loader.load_resource({
        "resourceType": "Condition", "id": "c1",
        "subject": {"reference": "Group/g7"}, "code": {"text": "dx"},
    })
    got = duckdb_con.execute(
        "SELECT patient_ref FROM resources WHERE id = 'c1'"
    ).fetchone()[0]
    assert got is None


def test_patient_ref_patient_typed_subject(loader, duckdb_con):
    loader.load_resource({
        "resourceType": "Observation", "id": "o1",
        "subject": {"reference": "Patient/123"},
    })
    got = duckdb_con.execute(
        "SELECT patient_ref FROM resources WHERE id = 'o1'"
    ).fetchone()[0]
    assert got == "123"


def test_patient_ref_absolute_and_versioned(loader, duckdb_con):
    loader.load_resource({
        "resourceType": "Condition", "id": "c2",
        "subject": {"reference": "https://example.org/fhir/Patient/abc"},
    })
    loader.load_resource({
        "resourceType": "Condition", "id": "c3",
        "subject": {"reference": "Patient/p9/_history/4"},
    })
    rows = dict(duckdb_con.execute(
        "SELECT id, patient_ref FROM resources WHERE id IN ('c2', 'c3')"
    ).fetchall())
    assert rows == {"c2": "abc", "c3": "p9"}


def test_patient_ref_bare_id_not_attributed(loader, duckdb_con):
    """Bare ids are not valid FHIR R4 references and carry no target type."""
    loader.load_resource({
        "resourceType": "Condition", "id": "c4",
        "subject": {"reference": "bare-id"},
    })
    got = duckdb_con.execute(
        "SELECT patient_ref FROM resources WHERE id = 'c4'"
    ).fetchone()[0]
    assert got is None


def test_patient_ref_list_valued_reference(loader, duckdb_con):
    """QA-004: Appointment-style 0..* patient references use the first Patient entry."""
    loader.load_resource({
        "resourceType": "Appointment", "id": "a1", "status": "booked",
        "patient": [
            {"reference": "Group/g1"},
            {"reference": "Patient/p11"},
            {"reference": "Patient/p12"},
        ],
    })
    got = duckdb_con.execute(
        "SELECT patient_ref FROM resources WHERE id = 'a1'"
    ).fetchone()[0]
    assert got == "p11"


def test_patient_ref_urn_uuid_bundle_local(loader, duckdb_con):
    loader.load_resource({
        "resourceType": "Condition", "id": "c5",
        "subject": {"reference": "urn:uuid:7f9c4d2a"},
    })
    got = duckdb_con.execute(
        "SELECT patient_ref FROM resources WHERE id = 'c5'"
    ).fetchone()[0]
    assert got == "7f9c4d2a"


def test_resolve_macro_versioned_reference(loader, duckdb_con):
    """QA-002: version-specific references resolve to the current resource."""
    loader.load_resource({"resourceType": "Patient", "id": "p20"})
    got = duckdb_con.execute(
        "SELECT json_extract_string(resolve('Patient/p20/_history/9'), '$.id')"
    ).fetchone()[0]
    assert got == "p20"


def test_resolve_macro_regression_forms(loader, duckdb_con):
    loader.load_resources([
        {"resourceType": "Patient", "id": "p30"},
        {"resourceType": "Observation", "id": "ob30",
         "subject": {"reference": "Patient/p30"}},
    ])
    assert duckdb_con.execute(
        "SELECT json_extract_string(resolve('Patient/p30'), '$.id')"
    ).fetchone()[0] == "p30"
    assert duckdb_con.execute(
        "SELECT json_extract_string(resolve('https://s/fhir/Patient/p30'), '$.id')"
    ).fetchone()[0] == "p30"
    assert duckdb_con.execute(
        "SELECT json_extract_string("
        "resolve(json('{\"reference\": \"Patient/p30\"}')), '$.id')"
    ).fetchone()[0] == "p30"
    assert duckdb_con.execute(
        "SELECT json_extract_string(resolve('urn:uuid:p30'), '$.id')"
    ).fetchone()[0] == "p30"
    assert duckdb_con.execute("SELECT resolve('Patient/missing')").fetchone()[0] is None


def test_load_ndjson_bom_tolerated(loader, duckdb_con, tmp_path):
    """QA-003: UTF-8 BOM on the first line must not reject the file."""
    p = tmp_path / "bom.ndjson"
    p.write_text('{"resourceType": "Patient", "id": "b1"}\n', encoding="utf-8-sig")
    assert loader.load_ndjson(p) == 1
    assert loader.count() == 1


def test_load_file_bom_tolerated(loader, duckdb_con, tmp_path):
    p = tmp_path / "bom.json"
    p.write_text('{"resourceType": "Patient", "id": "b2"}', encoding="utf-8-sig")
    assert loader.load_file(p) == 1
    assert loader.count() == 1


def test_load_bundle_rejects_empty_resource_with_index(loader):
    """QA-005: entry.resource == {} is invalid FHIR, not a silent skip."""
    with pytest.raises(ValueError, match=r"Bundle.entry\[0\]\.resource is empty"):
        loader.load_bundle({
            "resourceType": "Bundle", "type": "collection",
            "entry": [{"resource": {}}],
        })


def test_load_bundle_invalid_entry_attribution(loader):
    with pytest.raises(ValueError, match=r"Bundle.entry\[1\].*resourceType"):
        loader.load_bundle({
            "resourceType": "Bundle", "type": "collection",
            "entry": [
                {"resource": {"resourceType": "Patient", "id": "ok1"}},
                {"resource": {"id": "no-type"}},
            ],
        })


# --- 0.0.12 evolution campaign, Domain 6 EXPLORER fixes (QA-009..QA-012) ---

def test_load_directory_case_variant_extensions(loader, tmp_path):
    """QA-009: .JSON/.NdJsOn files must load on case-insensitive trees."""
    (tmp_path / "UPPER.JSON").write_text('{"resourceType": "Patient", "id": "u1"}')
    (tmp_path / "mixed.NdJsOn").write_text('{"resourceType": "Patient", "id": "m1"}\n')
    assert loader.load_directory(tmp_path) == 2
    assert loader.count() == 2


def test_load_directory_skips_unreadable_file(loader, duckdb_con, tmp_path):
    """QA-010: an unreadable file must not abort the whole directory load."""
    (tmp_path / "ok.json").write_text('{"resourceType": "Patient", "id": "ok1"}')
    bad = tmp_path / "bad.json"
    bad.write_text('{"resourceType": "Patient", "id": "never"}')
    bad.chmod(0o000)
    try:
        loaded = loader.load_directory(tmp_path)
    finally:
        bad.chmod(0o644)
    assert loaded == 1
    assert loader.count() == 1


def test_serialize_deep_nesting_raises_value_error(loader):
    """QA-011: pathological nesting surfaces as ValueError, not RecursionError."""
    obj = {"resourceType": "Patient", "id": "d1"}
    node = obj
    for _ in range(5000):
        node["contained"] = [{"resourceType": "Basic"}]
        node = node["contained"][0]
    with pytest.raises(ValueError, match="nesting"):
        loader.load_resource(obj)


def test_serialize_circular_reference_message(loader):
    """QA-012: circular-reference errors name the actual cause."""
    a = {"resourceType": "Patient", "id": "circ"}
    a["self"] = a
    with pytest.raises(ValueError, match="circular"):
        loader.load_resource(a)


# --- 0.0.12 evolution campaign, Domain 7 SKEPTIC fix (QA-013) ---

def test_load_resources_bulk_path_and_fallback(loader, duckdb_con, monkeypatch):
    """QA-013: Arrow bulk insert used when available; executemany fallback intact."""
    batch = [{"resourceType": "Patient", "id": f"p{i}"} for i in range(500)]
    assert loader.load_resources(batch) == 500
    assert loader.count() == 500
    # reload same identities: dedup DELETE + bulk insert, no row growth
    batch2 = [{"resourceType": "Patient", "id": f"p{i}", "active": True} for i in range(500)]
    assert loader.load_resources(batch2) == 500
    assert loader.count() == 500
    assert duckdb_con.execute(
        "SELECT COUNT(*) FROM resources WHERE json_extract_string(resource,'$.active') = 'true'"
    ).fetchone()[0] == 500
    # fallback: block pyarrow import inside the loader module path
    import builtins
    real_import = builtins.__import__
    def no_pa(name, *a, **k):
        if name == "pyarrow":
            raise ImportError("blocked")
        return real_import(name, *a, **k)
    monkeypatch.setattr(builtins, "__import__", no_pa)
    batch3 = [{"resourceType": "Observation", "id": f"o{i}",
               "subject": {"reference": "Patient/p0"}} for i in range(50)]
    assert loader.load_resources(batch3) == 50
    assert loader.count("Observation") == 50


def test_load_resources_mixed_null_ids_bulk(loader, duckdb_con):
    """Bulk path must handle NULL ids and NULL patient_refs (Arrow typed columns)."""
    batch = [
        {"resourceType": "Patient"},
        {"resourceType": "Patient", "id": "x1"},
        {"resourceType": "Observation", "subject": {"reference": "Patient/x1"}},
    ]
    assert loader.load_resources(batch) == 3
    rows = duckdb_con.execute(
        "SELECT id, patient_ref FROM resources ORDER BY resourceType, id NULLS FIRST"
    ).fetchall()
    assert rows == [(None, "x1"), (None, None), ("x1", "x1")]
