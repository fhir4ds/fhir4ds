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


@pytest.mark.parametrize("register_first", [True, False])
def test_resolve_macro_survives_cql_macro_registration(register_first):
    """resolve() must keep working when CQL macros are registered.

    The CQL ``Trim(s)`` macro shadows DuckDB's 2-arg builtin ``trim(x, chars)``
    for every connection that registers CQL macros, so the resolve() macro
    body must not use ``TRIM(BOTH '"' FROM ...)`` (regression: resolve()
    was broken at bind time in the standard register()+FHIRDataLoader flow,
    both load orders, since 2026-05). Also pins versioned-ref stripping in
    BOTH macro definitions (loader's and macros/clinical.py's).
    """
    from fhir4ds.cql.duckdb import register as register_cql

    con = duckdb.connect(":memory:")
    if register_first:
        register_cql(con)
        loader = FHIRDataLoader(con)
        loader.load_resource({"resourceType": "Patient", "id": "p1"})
    else:
        loader = FHIRDataLoader(con)
        loader.load_resource({"resourceType": "Patient", "id": "p1"})
        register_cql(con)

    for ref, expected in [
        ("Patient/p1", "p1"),
        ('"Patient/p1"', "p1"),
        (json.dumps({"reference": "Patient/p1"}), "p1"),
        ("Patient/p1/_history/9", "p1"),
        ("https://example.org/fhir/Patient/p1", "p1"),
        ("Patient/missing", None),
        (None, None),
    ]:
        result = con.execute(
            "SELECT json_extract_string(resolve(?::VARCHAR), '$.id')",
            [ref],
        ).fetchone()
        assert result == (expected,), f"resolve({ref!r}) -> {result!r}, expected {expected!r}"
    con.close()


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
    """An expansion is authoritative: compose is NOT re-read on top of it.

    FHIR R4 ValueSet.expansion is the membership a terminology server computed
    from the definition (filters, exclude rules, activity status). Reading
    compose.include alongside it re-adds codes the expansion deliberately
    omitted, so the expansion branch wins outright.
    """
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

    assert count == 1
    assert loader.count_valueset_codes("http://example.org/ValueSet/Raw") == 1
    assert loader.con.execute(
        "SELECT system, code FROM valueset_codes"
    ).fetchall() == [("http://snomed.info/sct", "67890")]


def test_load_valuesets_null_expansion_compose_treated_as_absent(loader):
    """FHIR JSON null members are absent (0.0.13 QA-002): a null expansion
    must not crash extraction and must not mask compose codes."""
    null_expansion = {
        "resourceType": "ValueSet",
        "url": "http://example.org/ValueSet/NullExpansion",
        "expansion": None,
        "compose": {
            "include": [
                {"system": "http://loinc.org", "concept": [{"code": "la"}]}
            ]
        },
    }
    null_compose = {
        "resourceType": "ValueSet",
        "url": "http://example.org/ValueSet/NullCompose",
        "compose": None,
        "expansion": {"contains": [{"system": "http://snomed.info/sct", "code": "ec"}]},
    }

    assert loader.load_valuesets([null_expansion]) == 1
    assert loader.count_valueset_codes("http://example.org/ValueSet/NullExpansion") == 1
    assert loader.load_valuesets([null_compose]) == 1
    assert loader.count_valueset_codes("http://example.org/ValueSet/NullCompose") == 1


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


def test_load_from_url_wraps_malformed_json(loader, monkeypatch):
    """Malformed server payloads raise a wrapped ValueError with url context
    (0.0.13 QA-004), not a raw json.JSONDecodeError."""
    import urllib.request

    class MockResponse:
        def read(self):
            return b'{"resourceType": "Patient", '
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass

    monkeypatch.setattr(urllib.request, "urlopen", lambda *args, **kwargs: MockResponse())

    with pytest.raises(ValueError, match=r"Malformed JSON from http://example.org/fhir"):
        loader.load_from_url("http://example.org/fhir")


def test_load_from_url_tolerates_utf8_bom(loader, monkeypatch):
    """A UTF-8 BOM in the server payload is tolerated (0.0.13 QA-004)."""
    import urllib.request

    patient = {"resourceType": "Patient", "id": "bom-p1"}
    bom_bytes = b"\xef\xbb\xbf" + json.dumps(patient).encode("utf-8")

    class MockResponse:
        def read(self):
            return bom_bytes
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass

    monkeypatch.setattr(urllib.request, "urlopen", lambda *args, **kwargs: MockResponse())

    assert loader.load_from_url("http://example.org/fhir/Patient/bom-p1") == 1
    assert loader.count("Patient") == 1


def test_serialize_rejects_non_json_native_values(loader):
    """Non-JSON-native values (datetime etc.) raise a wrapped ValueError on
    every entry point (0.0.13 QA-003), mirroring the bundle/ndjson contract."""
    import datetime

    resource = {
        "resourceType": "Observation",
        "id": "o-dt",
        "effectiveDateTime": datetime.datetime(2020, 1, 1),
    }
    message = r"cannot be represented as standard JSON.*datetime"

    with pytest.raises(ValueError, match=message):
        loader.load_resource(resource)
    with pytest.raises(ValueError, match=message):
        loader.load_resources([resource])


def test_rejects_duplicate_json_members(loader, tmp_path):
    """FHIR json.html: property names SHALL be unique (0.0.13 QA-007) —
    strict decode boundaries reject duplicates with location attribution
    instead of silently keeping the last member."""
    dup_ndjson = tmp_path / "dup.ndjson"
    dup_ndjson.write_text(
        '{"resourceType": "Patient", "id": "a", "id": "b"}\n'
    )
    with pytest.raises(ValueError, match=r"line 1.*Duplicate JSON member 'id'"):
        loader.load_ndjson(dup_ndjson)

    dup_json = tmp_path / "dup.json"
    dup_json.write_text('{"resourceType": "Patient", "id": "a", "id": "b"}')
    with pytest.raises(ValueError, match=r"Invalid FHIR JSON in .*dup\.json.*Duplicate JSON member 'id'"):
        loader.load_file(dup_json)


def test_ndjson_non_strict_skips_duplicate_member_lines(loader, tmp_path, caplog):
    dup_ndjson = tmp_path / "dup.ndjson"
    dup_ndjson.write_text(
        '{"resourceType": "Patient", "id": "ok"}\n'
        '{"resourceType": "Patient", "id": "a", "id": "b"}\n'
    )
    count = loader.load_ndjson(dup_ndjson, strict=False)
    assert count == 1
    assert loader.count("Patient") == 1


def test_ndjson_deep_nesting_raises_wrapped_valueerror(loader, tmp_path):
    """Parse-side deep nesting raises a wrapped ValueError with line
    attribution (0.0.13 QA-011), not a raw RecursionError."""
    deep = tmp_path / "deep.ndjson"
    deep.write_text('{"resourceType": "Patient", "id": "d1", "x": '
                    + "[" * 20000 + "]" * 20000 + "}\n")
    with pytest.raises(ValueError, match=r"line 1.*nesting is too deep to parse"):
        loader.load_ndjson(deep)


def test_load_valuesets_object_missing_codes_is_typed_error(loader):
    """Duck-typed .url-without-.codes raises a typed, indexed TypeError
    (0.0.13 QA-012), not a raw AttributeError."""
    class Partial:
        url = "http://example.org/VS"
    with pytest.raises(TypeError, match=r"valuesets\[0\].*\.codes"):
        loader.load_valuesets([Partial()])


def test_ndjson_rejects_lone_surrogates(loader, tmp_path):
    """Unpaired surrogates are rejected at the validation boundary with line
    attribution (0.0.13 QA-013); non-strict mode skips the bad line; real
    surrogate pairs (emoji) load fine."""
    bad = tmp_path / "surrogate.ndjson"
    bad.write_text(
        '{"resourceType": "Patient", "id": "ok1"}\n'
        '{"resourceType": "Patient", "id": "bad1", "name": "x\\ud800y"}\n'
    )
    with pytest.raises(ValueError, match=r"line 2.*unpaired Unicode surrogates"):
        loader.load_ndjson(bad)

    loader.clear()
    count = loader.load_ndjson(bad, strict=False)
    assert count == 1
    assert loader.count("Patient") == 1

    emoji = tmp_path / "emoji.ndjson"
    emoji.write_text(
        '{"resourceType": "Patient", "id": "e1", "name": "😀"}\n', encoding="utf-8"
    )
    assert loader.load_ndjson(emoji) == 1
    stored = loader.con.execute(
        "SELECT json_extract_string(resource, '$.name') FROM resources "
        "WHERE id = 'e1'").fetchone()[0]
    assert stored == "😀"


def test_load_from_url_rejects_duplicate_members(loader, monkeypatch):
    import urllib.request

    class MockResponse:
        def read(self):
            return b'{"resourceType": "Patient", "id": "a", "id": "b"}'
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass

    monkeypatch.setattr(urllib.request, "urlopen", lambda *args, **kwargs: MockResponse())

    with pytest.raises(ValueError, match=r"Invalid FHIR JSON from http://.*Duplicate JSON member 'id'"):
        loader.load_from_url("http://example.org/fhir/Patient")


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


def test_loader_constructor_on_closed_connection_is_wrapped():
    """FHIRDataLoader(closed_con) fails with the actionable wrap (0.0.13
    QA-015), mirroring load_resource's closed-connection guard."""
    import duckdb as _duckdb

    con = _duckdb.connect(":memory:")
    con.close()
    with pytest.raises(_duckdb.ConnectionException, match="Cannot create FHIRDataLoader.*closed"):
        FHIRDataLoader(con)


class TestValueSetExtractionPerFhirR4:
    """Iteration 5 / Domain 6 HISTORIAN — FHIR R4 ValueSet membership semantics.

    `_extract_codes_from_valueset_resource` and the dependency resolver's
    `_index_valueset` previously duplicated this logic and both skipped
    `expansion.contains.contains` recursion, ignored `compose.exclude`, and
    re-read `compose` on top of a present `expansion`.
    """

    def test_hierarchical_expansion_is_flattened(self):
        """expansion.contains.contains (0..*) descendants are members."""
        from ...valueset_codes import extract_codes_from_valueset_resource

        codes = extract_codes_from_valueset_resource({
            "resourceType": "ValueSet",
            "url": "http://ex.org/VS/hier",
            "expansion": {"contains": [
                {"system": "sct", "code": "73211009", "contains": [
                    {"system": "sct", "code": "44054006", "contains": [
                        {"system": "sct", "code": "deep"},
                    ]},
                    {"system": "sct", "code": "46635009"},
                ]},
            ]},
        })
        assert [c["code"] for c in codes] == [
            "73211009", "44054006", "deep", "46635009"
        ]

    def test_blank_code_grouping_node_is_not_a_member(self):
        """expansion.contains.code is 0..1 — blank means "not selectable"."""
        from ...valueset_codes import extract_codes_from_valueset_resource

        codes = extract_codes_from_valueset_resource({
            "resourceType": "ValueSet",
            "url": "http://ex.org/VS/grouped",
            "expansion": {"contains": [
                {"display": "Grouping header", "contains": [
                    {"system": "sct", "code": "real-code"},
                ]},
            ]},
        })
        assert codes == [{"system": "sct", "code": "real-code", "display": None}]

    def test_expansion_authoritative_over_compose(self):
        from ...valueset_codes import extract_codes_from_valueset_resource

        codes = extract_codes_from_valueset_resource({
            "resourceType": "ValueSet",
            "expansion": {"contains": [{"system": "loinc", "code": "1111-1"}]},
            "compose": {"include": [
                {"system": "loinc", "concept": [{"code": "1111-1"}, {"code": "9999-9"}]}
            ]},
        })
        assert [c["code"] for c in codes] == ["1111-1"]

    def test_compose_exclude_concept_list_removes_codes(self):
        from ...valueset_codes import extract_codes_from_valueset_resource

        codes = extract_codes_from_valueset_resource({
            "resourceType": "ValueSet",
            "compose": {
                "include": [{"system": "sct", "concept": [
                    {"code": "A"}, {"code": "B"}, {"code": "C"}]}],
                "exclude": [{"system": "sct", "concept": [{"code": "B"}]}],
            },
        })
        assert [c["code"] for c in codes] == ["A", "C"]

    def test_compose_exclude_whole_system(self):
        from ...valueset_codes import extract_codes_from_valueset_resource

        codes = extract_codes_from_valueset_resource({
            "resourceType": "ValueSet",
            "compose": {
                "include": [
                    {"system": "sct", "concept": [{"code": "A"}]},
                    {"system": "loinc", "concept": [{"code": "1111-1"}]},
                ],
                "exclude": [{"system": "sct"}],
            },
        })
        assert codes == [{"system": "loinc", "code": "1111-1", "display": None}]

    def test_compose_exclude_enumerable_eq_filter(self):
        """VSAC emits `property=concept, op='=', value=<code>` to exclude a code."""
        from ...valueset_codes import extract_codes_from_valueset_resource

        codes = extract_codes_from_valueset_resource({
            "resourceType": "ValueSet",
            "compose": {
                "include": [{"system": "sopt", "concept": [
                    {"code": "1002-5"}, {"code": "111"}, {"code": "2106-3"}]}],
                "exclude": [{"system": "sopt", "filter": [
                    {"property": "concept", "op": "=", "value": "111"}]}],
            },
        })
        assert [c["code"] for c in codes] == ["1002-5", "2106-3"]

    def test_unenumerable_exclude_fails_loud(self):
        """A descendant-of exclude cannot be enumerated; never over-report."""
        from ...valueset_codes import (
            ValueSetExpansionError,
            extract_codes_from_valueset_resource,
        )

        with pytest.raises(ValueSetExpansionError, match="cannot be enumerated"):
            extract_codes_from_valueset_resource({
                "resourceType": "ValueSet",
                "compose": {
                    "include": [{"system": "sct", "concept": [{"code": "A"}]}],
                    "exclude": [{"system": "sct", "filter": [
                        {"property": "concept", "op": "is-a", "value": "root"}]}],
                },
            })

    def test_nested_valueset_exclude_fails_loud(self):
        from ...valueset_codes import (
            ValueSetExpansionError,
            extract_codes_from_valueset_resource,
        )

        with pytest.raises(ValueSetExpansionError, match="nested value sets"):
            extract_codes_from_valueset_resource({
                "resourceType": "ValueSet",
                "compose": {
                    "include": [{"system": "sct", "concept": [{"code": "A"}]}],
                    "exclude": [{"valueSet": ["http://ex.org/VS/other"]}],
                },
            })

    def test_expansion_duplicates_collapse(self):
        """A code reachable through two parents is one member."""
        from ...valueset_codes import extract_codes_from_valueset_resource

        codes = extract_codes_from_valueset_resource({
            "resourceType": "ValueSet",
            "expansion": {"contains": [
                {"system": "sct", "code": "shared"},
                {"system": "sct", "code": "other", "contains": [
                    {"system": "sct", "code": "shared"}]},
            ]},
        })
        assert [c["code"] for c in codes] == ["shared", "other"]

    def test_loader_loads_hierarchical_expansion(self, loader):
        count = loader.load_valuesets([{
            "resourceType": "ValueSet",
            "url": "http://ex.org/VS/hier",
            "expansion": {"contains": [
                {"system": "sct", "code": "parent", "contains": [
                    {"system": "sct", "code": "child"},
                ]},
            ]},
        }])
        assert count == 2
        assert loader.count_valueset_codes("http://ex.org/VS/hier") == 2


class TestValueSetExcludeMootWhenIncludeIsIntensional:
    """A system-only include yields no enumerable codes, so unenumerable
    excludes have nothing to remove and must not hard-fail.

    VSAC emits exactly this shape (e.g. the SOPT race value set:
    `include: [{system}]` with `op: 'descendent-of'` excludes). Raising here
    would fail every measure that loads such a ValueSet, while the honest
    signal is the existing zero-code warning.
    """

    def test_system_only_include_with_filter_excludes_returns_empty(self):
        from ...valueset_codes import extract_codes_from_valueset_resource

        codes = extract_codes_from_valueset_resource({
            "resourceType": "ValueSet",
            "compose": {
                "include": [{"system": "https://nahdo.org/sopt"}],
                "exclude": [
                    {"system": "https://nahdo.org/sopt", "filter": [
                        {"property": "concept", "op": "=", "value": "111"}]},
                    {"system": "https://nahdo.org/sopt", "filter": [
                        {"property": "concept", "op": "descendent-of", "value": "321"}]},
                ],
            },
        })
        assert codes == []

    def test_enumerable_exclude_still_applies_when_codes_present(self):
        from ...valueset_codes import extract_codes_from_valueset_resource

        codes = extract_codes_from_valueset_resource({
            "resourceType": "ValueSet",
            "compose": {
                "include": [{"system": "s", "concept": [
                    {"code": "111"}, {"code": "1002-5"}]}],
                "exclude": [{"system": "s", "filter": [
                    {"property": "concept", "op": "=", "value": "111"}]}],
            },
        })
        assert [c["code"] for c in codes] == ["1002-5"]


class TestValuesetMembershipSeesLaterLoads:
    """Iteration 6 / Domain 6 EXPLORER.

    `createValuesetMembershipUdf` used to SNAPSHOT the codes cache at factory
    time, but the UDF is registered exactly once per connection and
    `load_valuesets` updates the cache dict in place afterwards. Every ValueSet
    loaded after the first `load_valuesets` call was therefore invisible to the
    Python-fallback membership check: `in_valueset` answered SQL NULL (unknown)
    where the native C++ cache — repopulated from the table on every load —
    answered true. Silent under-membership in exactly the engine mode used by
    the browser/WASM build and any unsigned dev connection.
    """

    def test_second_load_valuesets_call_is_visible_to_membership(self, duckdb_con):
        from ...duckdb.udf.valueset import createValuesetMembershipUdf

        cache: dict = {}
        udf = createValuesetMembershipUdf(cache)
        loader = FHIRDataLoader(duckdb_con)
        loader._valueset_udf_cache = cache  # same object the closure reads

        loader.load_valuesets([{
            "resourceType": "ValueSet", "url": "http://ex.org/VS/first",
            "compose": {"include": [{"system": "s", "concept": [{"code": "c1"}]}]},
        }])
        assert udf('{"coding":[{"system":"s","code":"c1"}]}', "coding",
                   "http://ex.org/VS/first") is True

        loader.load_valuesets([{
            "resourceType": "ValueSet", "url": "http://ex.org/VS/second",
            "compose": {"include": [{"system": "s", "concept": [{"code": "c2"}]}]},
        }])
        # The pre-existing UDF object (registered once) must see the new set.
        assert udf('{"coding":[{"system":"s","code":"c2"}]}', "coding",
                   "http://ex.org/VS/second") is True
        # ... and must keep seeing the first one.
        assert udf('{"coding":[{"system":"s","code":"c1"}]}', "coding",
                   "http://ex.org/VS/first") is True
        # A genuinely absent code is False, not NULL.
        assert udf('{"coding":[{"system":"s","code":"zz"}]}', "coding",
                   "http://ex.org/VS/second") is False

    def test_bare_string_cache_shape_still_supported(self):
        """Documented alternate cache shape: bare codes become ("", code)."""
        from ...duckdb.udf.valueset import createValuesetMembershipUdf

        udf = createValuesetMembershipUdf({"http://ex.org/VS/bare": {"1002-5"}})
        assert udf('{"coding":[{"system":"","code":"1002-5"}]}', "coding",
                   "http://ex.org/VS/bare") is True

    def test_cache_growing_after_factory_call_is_seen(self):
        """A caller that keeps its own dict (documented UDF usage) stays live."""
        from ...duckdb.udf.valueset import createValuesetMembershipUdf

        cache = {"http://ex.org/VS/a": {("s", "ca")}}
        udf = createValuesetMembershipUdf(cache)
        assert udf('{"coding":[{"system":"s","code":"cb"}]}', "coding",
                   "http://ex.org/VS/b") is None  # unknown set -> NULL
        cache["http://ex.org/VS/b"] = {("s", "cb")}
        assert udf('{"coding":[{"system":"s","code":"cb"}]}', "coding",
                   "http://ex.org/VS/b") is True


class TestValuesetNonStringDisplayTyped:
    """Iteration 6 / Domain 6 EXPLORER — INV-8 at the load_valuesets boundary.

    A JSON-number `display` (invalid FHIR: display is `string 0..1`) used to
    escape the public loader API as `pyarrow.lib.ArrowTypeError` from the bulk
    insert path. Sibling member fields (`system`, `code`) already raise a typed
    ValueError with index attribution; display now does the same.
    """

    def test_non_string_display_raises_typed_value_error(self, loader):
        with pytest.raises(ValueError, match=r"codes\[0\]\.display must be a string"):
            loader.load_valuesets([{
                "resourceType": "ValueSet", "url": "http://ex.org/VS/x",
                "expansion": {"contains": [
                    {"system": "s", "code": "a", "display": 42}]},
            }])

    def test_no_rows_committed_on_failure(self, loader):
        with pytest.raises(ValueError):
            loader.load_valuesets([{
                "resourceType": "ValueSet", "url": "http://ex.org/VS/x",
                "expansion": {"contains": [
                    {"system": "s", "code": "ok"},
                    {"system": "s", "code": "bad", "display": 42}]},
            }])
        assert loader.count_valueset_codes() == 0


def test_membership_sees_in_place_set_growth():
    """Iteration 6 / Domain 6 EXPLORER — memo invalidation on in-place growth.

    The per-URL normalization memo keys on (set identity, size). The loader
    replaces sets on refresh; a caller that grows one in place changes only the
    size, which must still invalidate the memo.
    """
    from ...duckdb.udf.valueset import createValuesetMembershipUdf

    entries: set = {("s", "ca")}
    cache = {"http://ex.org/VS/a": entries}
    udf = createValuesetMembershipUdf(cache)
    assert udf('{"coding":[{"system":"s","code":"cb"}]}', "coding",
               "http://ex.org/VS/a") is False
    entries.add(("s", "cb"))          # same set object, new content
    assert udf('{"coding":[{"system":"s","code":"cb"}]}', "coding",
               "http://ex.org/VS/a") is True


class TestScopedValuesetCacheRefresh:
    """Iteration 7 / Domain 7 SKEPTIC — incremental loading must not be O(table).

    `_refresh_in_valueset_udf` used to re-read the ENTIRE valueset_codes table
    and rebuild the whole cache on every `load_valuesets` call: measured 207 ms
    per call against a 200k-row table versus 5.7 ms scoped, so loading a corpus
    one ValueSet at a time paid O(rows in table) per call (O(N^2) in aggregate).
    The refresh is now scoped to the URLs just written.
    """

    def test_scoped_refresh_preserves_unrelated_cache_entries(self, loader):
        # A sentinel entry that exists ONLY in the cache proves the refresh did
        # not clear-and-rebuild from the table.
        loader._valueset_udf_cache["http://ex.org/VS/sentinel"] = {("s", "keep")}
        loader.load_valuesets([{
            "resourceType": "ValueSet", "url": "http://ex.org/VS/new",
            "compose": {"include": [{"system": "s", "concept": [{"code": "n1"}]}]},
        }])
        assert loader._valueset_udf_cache["http://ex.org/VS/sentinel"] == {("s", "keep")}
        assert ("s", "n1") in loader._valueset_udf_cache["http://ex.org/VS/new"]

    def test_scoped_refresh_replaces_only_the_written_url(self, loader):
        loader.load_valuesets([{
            "resourceType": "ValueSet", "url": "http://ex.org/VS/a",
            "compose": {"include": [{"system": "s", "concept": [{"code": "a1"}]}]},
        }])
        # Poison the cache entry for the URL we are about to rewrite: a scoped
        # refresh must re-read it from the table, not trust the cache.
        loader._valueset_udf_cache["http://ex.org/VS/a"] = {("s", "stale")}
        loader.load_valuesets([{
            "resourceType": "ValueSet", "url": "http://ex.org/VS/a",
            "compose": {"include": [{"system": "s", "concept": [{"code": "a2"}]}]},
        }])
        assert loader._valueset_udf_cache["http://ex.org/VS/a"] == {("s", "a1"), ("s", "a2")}

    def test_clear_valuesets_still_does_a_full_reset(self, loader):
        loader._valueset_udf_cache["http://ex.org/VS/sentinel"] = {("s", "keep")}
        loader.load_valuesets([{
            "resourceType": "ValueSet", "url": "http://ex.org/VS/a",
            "compose": {"include": [{"system": "s", "concept": [{"code": "a1"}]}]},
        }])
        loader.clear_valuesets()
        assert loader._valueset_udf_cache == {}

    def test_native_cache_capability_is_probed_not_guessed(self, loader):
        # Plain (non-native) connection: no cpp cache API, so the loader must
        # fall back to the Python path without raising or logging a warning.
        assert loader._cpp_valueset_cache_available() is False
        loader.load_valuesets([{
            "resourceType": "ValueSet", "url": "http://ex.org/VS/a",
            "compose": {"include": [{"system": "s", "concept": [{"code": "a1"}]}]},
        }])
        # Second call reuses the memoized probe (no repeated duckdb_functions()).
        assert loader._cpp_valueset_cache_available() is False


def test_scoped_refresh_chunks_large_url_batches(loader):
    """Iteration 7 / Domain 7 SKEPTIC — >1 chunk of URLs in a single call.

    The scoped refresh builds parameterized IN-lists of at most
    _VALUESET_REFRESH_CHUNK URLs; a single bulk load carrying more URLs than
    that must still cache every one of them.
    """
    from ...loader.fhir_loader import _VALUESET_REFRESH_CHUNK

    n = _VALUESET_REFRESH_CHUNK + 37
    loader.load_valuesets([
        {"resourceType": "ValueSet", "url": f"http://ex.org/VS/bulk{i}",
         "compose": {"include": [{"system": "s", "concept": [{"code": f"c{i}"}]}]}}
        for i in range(n)
    ])
    missing = [i for i in range(n)
               if ("s", f"c{i}") not in loader._valueset_udf_cache.get(
                   f"http://ex.org/VS/bulk{i}", set())]
    assert missing == []
    assert loader.count_valueset_codes() == n


class TestValuesetExtractionErrorsAreAttributed:
    """Iteration 10 / Domain 8 SKEPTIC — INV-8 attribution on the new boundaries.

    `load_valuesets` validates everything else with `valuesets[i] ...` messages,
    but the shared extractor's errors propagated raw: with a corpus of hundreds
    of ValueSets the caller could not tell which one was broken.
    """

    def test_unenumerable_exclude_names_index_and_url(self, loader):
        from ...valueset_codes import ValueSetExpansionError

        bad = {"resourceType": "ValueSet", "url": "http://ex.org/VS/bad",
               "compose": {"include": [{"system": "s", "concept": [{"code": "a"}]}],
                           "exclude": [{"system": "s", "filter": [
                               {"property": "concept", "op": "is-a", "value": "x"}]}]}}
        with pytest.raises(ValueSetExpansionError) as exc:
            loader.load_valuesets([
                {"resourceType": "ValueSet", "url": "http://ex.org/VS/ok",
                 "compose": {"include": [{"system": "s", "concept": [{"code": "ok"}]}]}},
                bad,
            ])
        msg = str(exc.value)
        assert "valuesets[1]" in msg
        assert "http://ex.org/VS/bad" in msg
        assert loader.count_valueset_codes() == 0

    def test_malformed_container_names_index_and_url(self, loader):
        with pytest.raises(TypeError) as exc:
            loader.load_valuesets([
                {"resourceType": "ValueSet", "url": "http://ex.org/VS/broken",
                 "expansion": {"contains": "nope"}},
            ])
        msg = str(exc.value)
        assert "valuesets[0]" in msg and "http://ex.org/VS/broken" in msg
        assert loader.count_valueset_codes() == 0


class TestClosedConnectionMessageIsNamespacedEverywhere:
    """Iteration 11 / Domain 8 HISTORIAN — INV-8 symmetry.

    Only `__init__` and `load_resource` used to say "Cannot <op>: DuckDB
    connection is closed". The rest leaked the raw engine text
    ("Connection Error: Connection already closed!"), which names no FHIR4DS
    operation and is indistinguishable across a pipeline of calls. Every
    connection-touching public method now carries the namespaced message via
    `_translate_closed_connection` (a message translation, not an extra query,
    and idempotent so a wrapped inner error is not re-wrapped).
    """

    def _closed(self):
        import fhir4ds as _fhir4ds

        con = duckdb.connect(":memory:")
        _fhir4ds.register(con)
        loader = FHIRDataLoader(con)
        con.close()
        return loader

    def test_every_public_method_names_the_operation(self, tmp_path):
        loader = self._closed()
        nd = tmp_path / "x.ndjson"
        nd.write_text('{"resourceType":"Patient","id":"p1"}\n')
        f = tmp_path / "x.json"
        f.write_text('{"resourceType":"Patient","id":"p1"}')
        calls = {
            "load_resource": lambda: loader.load_resource({"resourceType": "Patient", "id": "p2"}),
            "load_resources": lambda: loader.load_resources([{"resourceType": "Patient", "id": "p2"}]),
            # One entry: an EMPTY bundle is a legitimate no-op that never
            # touches the connection (pinned by TestLoadBundleEmptyIsNoOp).
            "load_bundle": lambda: loader.load_bundle({
                "resourceType": "Bundle", "type": "collection",
                "entry": [{"resource": {"resourceType": "Patient", "id": "p2"}}],
            }),
            "load_file": lambda: loader.load_file(f),
            "load_ndjson": lambda: loader.load_ndjson(nd),
            "load_directory": lambda: loader.load_directory(tmp_path),
            "load_valuesets": lambda: loader.load_valuesets(
                [{"resourceType": "ValueSet", "url": "u", "compose": {"include": []}}]),
            "count": lambda: loader.count(),
            "clear": lambda: loader.clear(),
            "count_valueset_codes": lambda: loader.count_valueset_codes(),
            "clear_valuesets": lambda: loader.clear_valuesets(),
            "valueset_table_exists": lambda: loader.valueset_table_exists(),
        }
        for name, call in calls.items():
            with pytest.raises(duckdb.ConnectionException) as exc:
                call()
            msg = str(exc.value)
            assert msg.startswith("Cannot "), f"{name}: {msg!r}"
            assert "DuckDB connection is closed" in msg, f"{name}: {msg!r}"


def test_load_bundle_empty_is_a_noop_even_on_a_closed_connection():
    """Domain 8 pin (iteration 11): an entry-less Bundle writes nothing, so it
    must not fail — nor silently claim work it did not do. Returns 0."""
    import fhir4ds as _fhir4ds

    con = duckdb.connect(":memory:")
    _fhir4ds.register(con)
    loader = FHIRDataLoader(con)
    con.close()
    assert loader.load_bundle({"resourceType": "Bundle", "type": "collection"}) == 0
