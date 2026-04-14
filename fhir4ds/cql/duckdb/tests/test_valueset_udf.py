"""
Unit tests for CQL Valueset UDFs.

Tests for code extraction functions:
- extractCodes
- extractFirstCode
- extractFirstCodeSystem
- extractFirstCodeValue
- resolveProfileUrl
"""

import json

import duckdb
import pytest

from ..udf.valueset import (
    extractCodes,
    extractFirstCode,
    extractFirstCodeSystem,
    extractFirstCodeValue,
    registerValuesetUdfs,
    resolveProfileUrl,
)


@pytest.fixture
def resource_with_codeable_concept():
    """A resource with CodeableConcept at code path."""
    return json.dumps({
        "resourceType": "Observation",
        "code": {
            "coding": [
                {"system": "http://loinc.org", "code": "8480-6", "display": "Systolic blood pressure"},
                {"system": "http://loinc.org", "code": "8462-4", "display": "Diastolic blood pressure"}
            ],
            "text": "Blood pressure"
        }
    })


@pytest.fixture
def resource_with_direct_coding():
    """A resource with direct Coding at code path."""
    return json.dumps({
        "resourceType": "Observation",
        "code": {
            "system": "http://loinc.org",
            "code": "8480-6",
            "display": "Systolic blood pressure"
        }
    })


@pytest.fixture
def resource_with_coding_array():
    """A resource with coding array at code path."""
    return json.dumps({
        "resourceType": "Observation",
        "code": [
            {
                "coding": [
                    {"system": "http://loinc.org", "code": "8480-6"}
                ]
            }
        ]
    })


@pytest.fixture
def resource_nested_path():
    """A resource with nested code path."""
    return json.dumps({
        "resourceType": "Observation",
        "valueCodeableConcept": {
            "coding": [
                {"system": "http://snomed.info/sct", "code": "123456789"}
            ]
        }
    })


@pytest.fixture
def resource_no_code():
    """A resource without code."""
    return json.dumps({
        "resourceType": "Patient",
        "name": [{"family": "Doe"}]
    })


@pytest.fixture
def resource_empty_coding():
    """A resource with empty coding array."""
    return json.dumps({
        "resourceType": "Observation",
        "code": {
            "coding": []
        }
    })


# ========================================
# extractCodes tests
# ========================================

class TestExtractCodes:
    """Tests for extractCodes function."""

    def test_codeable_concept(self, resource_with_codeable_concept):
        """Test extracting codes from CodeableConcept."""
        result = extractCodes(resource_with_codeable_concept, "code")
        assert len(result) == 2
        assert result[0] == ("http://loinc.org", "8480-6")
        assert result[1] == ("http://loinc.org", "8462-4")

    def test_direct_coding(self, resource_with_direct_coding):
        """Test extracting code from direct Coding."""
        result = extractCodes(resource_with_direct_coding, "code")
        assert len(result) == 1
        assert result[0] == ("http://loinc.org", "8480-6")

    def test_nested_path(self, resource_nested_path):
        """Test extracting codes with nested path."""
        result = extractCodes(resource_nested_path, "valueCodeableConcept")
        assert len(result) == 1
        assert result[0] == ("http://snomed.info/sct", "123456789")

    def test_no_code(self, resource_no_code):
        """Test extracting from resource without code."""
        result = extractCodes(resource_no_code, "code")
        assert result == []

    def test_empty_coding(self, resource_empty_coding):
        """Test extracting from empty coding array."""
        result = extractCodes(resource_empty_coding, "code")
        assert result == []

    def test_null_resource(self):
        """Test with null resource."""
        result = extractCodes(None, "code")
        assert result == []

    def test_null_path(self, resource_with_codeable_concept):
        """Test with null path."""
        result = extractCodes(resource_with_codeable_concept, None)
        assert result == []

    def test_empty_path(self, resource_with_codeable_concept):
        """Test with empty path."""
        result = extractCodes(resource_with_codeable_concept, "")
        assert result == []

    def test_invalid_json(self):
        """Test with invalid JSON."""
        result = extractCodes("not json", "code")
        assert result == []

    def test_missing_system(self):
        """Test coding without system."""
        resource = json.dumps({
            "code": {
                "coding": [
                    {"code": "8480-6"}  # Missing system
                ]
            }
        })
        result = extractCodes(resource, "code")
        assert len(result) == 1
        assert result[0] == ("", "8480-6")

    def test_missing_code(self):
        """Test coding without code."""
        resource = json.dumps({
            "code": {
                "coding": [
                    {"system": "http://loinc.org"}  # Missing code
                ]
            }
        })
        result = extractCodes(resource, "code")
        assert result == []  # Empty code is not included

    def test_deep_nested_path(self):
        """Test with deeply nested path."""
        resource = json.dumps({
            "component": {
                "item": {
                    "code": {
                        "coding": [
                            {"system": "http://loinc.org", "code": "test-code"}
                        ]
                    }
                }
            }
        })
        result = extractCodes(resource, "component.item.code")
        assert len(result) == 1
        assert result[0] == ("http://loinc.org", "test-code")


# ========================================
# extractFirstCode tests
# ========================================

class TestExtractFirstCode:
    """Tests for extractFirstCode function."""

    def test_codeable_concept(self, resource_with_codeable_concept):
        """Test extracting first code from CodeableConcept."""
        result = extractFirstCode(resource_with_codeable_concept, "code")
        assert result is not None
        parsed = json.loads(result)
        assert parsed["system"] == "http://loinc.org"
        assert parsed["code"] == "8480-6"

    def test_direct_coding(self, resource_with_direct_coding):
        """Test extracting first code from direct Coding."""
        result = extractFirstCode(resource_with_direct_coding, "code")
        assert result is not None
        parsed = json.loads(result)
        assert parsed["system"] == "http://loinc.org"
        assert parsed["code"] == "8480-6"

    def test_no_code(self, resource_no_code):
        """Test extracting from resource without code."""
        result = extractFirstCode(resource_no_code, "code")
        assert result is None

    def test_null_resource(self):
        """Test with null resource."""
        result = extractFirstCode(None, "code")
        assert result is None


# ========================================
# extractFirstCodeSystem tests
# ========================================

class TestExtractFirstCodeSystem:
    """Tests for extractFirstCodeSystem function."""

    def test_codeable_concept(self, resource_with_codeable_concept):
        """Test extracting system from CodeableConcept."""
        result = extractFirstCodeSystem(resource_with_codeable_concept, "code")
        assert result == "http://loinc.org"

    def test_no_code(self, resource_no_code):
        """Test extracting from resource without code."""
        result = extractFirstCodeSystem(resource_no_code, "code")
        assert result is None

    def test_null_resource(self):
        """Test with null resource."""
        result = extractFirstCodeSystem(None, "code")
        assert result is None

    def test_missing_system(self):
        """Test coding without system."""
        resource = json.dumps({
            "code": {
                "coding": [
                    {"code": "8480-6"}  # Missing system
                ]
            }
        })
        result = extractFirstCodeSystem(resource, "code")
        assert result is None  # Empty string becomes None


# ========================================
# extractFirstCodeValue tests
# ========================================

class TestExtractFirstCodeValue:
    """Tests for extractFirstCodeValue function."""

    def test_codeable_concept(self, resource_with_codeable_concept):
        """Test extracting code value from CodeableConcept."""
        result = extractFirstCodeValue(resource_with_codeable_concept, "code")
        assert result == "8480-6"

    def test_no_code(self, resource_no_code):
        """Test extracting from resource without code."""
        result = extractFirstCodeValue(resource_no_code, "code")
        assert result is None

    def test_null_resource(self):
        """Test with null resource."""
        result = extractFirstCodeValue(None, "code")
        assert result is None


# ========================================
# resolveProfileUrl tests
# ========================================

class TestResolveProfileUrl:
    """Tests for resolving StructureDefinition URLs to base resource types."""

    @pytest.mark.parametrize(
        ("profile_url", "expected"),
        [
            (
                "http://hl7.org/fhir/us/core/StructureDefinition/us-core-patient",
                "Patient",
            ),
            (
                "http://hl7.org/fhir/us/qicore/StructureDefinition/qicore-medicationrequest",
                "MedicationRequest",
            ),
            (
                "http://hl7.org/fhir/us/core/StructureDefinition/us-core-blood-pressure",
                "Observation",
            ),
            (
                "http://hl7.org/fhir/us/core/StructureDefinition/us-core-laboratory-result-observation",
                "Observation",
            ),
            (
                "http://hl7.org/fhir/us/qicore/StructureDefinition/qicore-servicenotrequested",
                "ServiceRequest",
            ),
            (
                "http://hl7.org/fhir/us/qicore/StructureDefinition/qicore-medicationnotrequested|4.1.1",
                "MedicationRequest",
            ),
            (
                "http://hl7.org/fhir/StructureDefinition/Observation",
                "Observation",
            ),
        ],
    )
    def test_profile_url_resolution(self, profile_url, expected):
        """Profile URLs should resolve without profile-specific hardcoded maps."""
        assert resolveProfileUrl(profile_url) == expected

    def test_unknown_profile_returns_none(self):
        """Unknown StructureDefinition URLs should not guess a resource type."""
        assert resolveProfileUrl("http://example.org/StructureDefinition/unknown-profile") is None

    def test_empty_profile_returns_none(self):
        """Empty or null profile URLs should return None."""
        assert resolveProfileUrl("") is None
        assert resolveProfileUrl(None) is None


# ========================================
# DuckDB Registration tests
# ========================================

class TestDuckDBRegistration:
    """Tests for DuckDB UDF registration.

    NOTE: extractCodes returns List[Tuple[str, str]] which DuckDB
    cannot infer automatically. Registration requires explicit return type.
    These tests register the scalar functions individually with explicit types.
    """

    def test_registration_scalar_functions(self):
        """Test that scalar UDFs can be registered with DuckDB."""
        con = duckdb.connect()

        # Register scalar functions with explicit return types
        con.create_function(
            "extractFirstCode",
            extractFirstCode,
            return_type="VARCHAR"
        )
        con.create_function(
            "extractFirstCodeSystem",
            extractFirstCodeSystem,
            return_type="VARCHAR"
        )
        con.create_function(
            "extractFirstCodeValue",
            extractFirstCodeValue,
            return_type="VARCHAR"
        )
        con.create_function(
            "resolveProfileUrl",
            resolveProfileUrl,
            return_type="VARCHAR"
        )

        resource = json.dumps({
            "code": {
                "coding": [
                    {"system": "http://loinc.org", "code": "8480-6"}
                ]
            }
        })

        # Test extractFirstCode (returns string)
        result = con.execute(
            "SELECT extractFirstCode(?, 'code')", [resource]
        ).fetchone()
        assert result[0] is not None

        # Test extractFirstCodeSystem (returns string)
        result = con.execute(
            "SELECT extractFirstCodeSystem(?, 'code')", [resource]
        ).fetchone()
        assert result[0] == "http://loinc.org"

        # Test extractFirstCodeValue (returns string)
        result = con.execute(
            "SELECT extractFirstCodeValue(?, 'code')", [resource]
        ).fetchone()
        assert result[0] == "8480-6"

        result = con.execute(
            "SELECT resolveProfileUrl(?)",
            ["http://hl7.org/fhir/us/qicore/StructureDefinition/qicore-medicationrequest"],
        ).fetchone()
        assert result[0] == "MedicationRequest"

        con.close()

    def test_registration_null_handling(self):
        """Test null handling through DuckDB for scalar functions."""
        con = duckdb.connect()

        # Register scalar functions with explicit return types
        con.create_function(
            "extractFirstCode",
            extractFirstCode,
            return_type="VARCHAR"
        )
        con.create_function(
            "extractFirstCodeSystem",
            extractFirstCodeSystem,
            return_type="VARCHAR"
        )
        con.create_function(
            "extractFirstCodeValue",
            extractFirstCodeValue,
            return_type="VARCHAR"
        )
        con.create_function(
            "resolveProfileUrl",
            resolveProfileUrl,
            return_type="VARCHAR"
        )

        result = con.execute("SELECT extractFirstCode(NULL, 'code')").fetchone()
        assert result[0] is None

        result = con.execute("SELECT extractFirstCodeSystem(NULL, 'code')").fetchone()
        assert result[0] is None

        result = con.execute("SELECT extractFirstCodeValue(NULL, 'code')").fetchone()
        assert result[0] is None

        result = con.execute("SELECT resolveProfileUrl(NULL)").fetchone()
        assert result[0] is None

        con.close()

    def test_all_scalar_functions_work(self):
        """Test that all scalar valueset functions work correctly."""
        con = duckdb.connect()

        # Register scalar functions with explicit return types
        con.create_function(
            "extractFirstCode",
            extractFirstCode,
            return_type="VARCHAR"
        )
        con.create_function(
            "extractFirstCodeSystem",
            extractFirstCodeSystem,
            return_type="VARCHAR"
        )
        con.create_function(
            "extractFirstCodeValue",
            extractFirstCodeValue,
            return_type="VARCHAR"
        )
        con.create_function(
            "resolveProfileUrl",
            resolveProfileUrl,
            return_type="VARCHAR"
        )

        resource = json.dumps({
            "code": {
                "coding": [
                    {"system": "http://loinc.org", "code": "8480-6"}
                ]
            }
        })

        functions = [
            ("extractFirstCode", [resource, "code"]),
            ("extractFirstCodeSystem", [resource, "code"]),
            ("extractFirstCodeValue", [resource, "code"]),
            (
                "resolveProfileUrl",
                ["http://hl7.org/fhir/us/core/StructureDefinition/us-core-blood-pressure"],
            ),
        ]

        for func_name, params in functions:
            result = con.execute(
                f"SELECT {func_name}({', '.join(['?'] * len(params))})", params
            ).fetchone()
            # Should not raise an error
            assert result is not None

        con.close()


# ========================================
# Edge case tests
# ========================================

class TestEdgeCases:
    """Tests for edge cases."""

    def test_empty_resource(self):
        """Test with empty resource object."""
        result = extractCodes("{}", "code")
        assert result == []

    def test_path_not_found(self):
        """Test with path that doesn't exist."""
        resource = json.dumps({"resourceType": "Patient"})
        result = extractCodes(resource, "nonexistent.path")
        assert result == []

    def test_coding_array_with_multiple_items(self):
        """Test coding array with multiple items."""
        resource = json.dumps({
            "code": {
                "coding": [
                    {"system": "http://loinc.org", "code": "code1"},
                    {"system": "http://snomed.info/sct", "code": "code2"},
                    {"system": "http://hl7.org", "code": "code3"}
                ]
            }
        })
        result = extractCodes(resource, "code")
        assert len(result) == 3
        assert result[0][1] == "code1"
        assert result[1][1] == "code2"
        assert result[2][1] == "code3"

    def test_code_with_special_characters(self):
        """Test code with special characters."""
        resource = json.dumps({
            "code": {
                "coding": [
                    {"system": "http://example.org", "code": "code-with-special_chars.123"}
                ]
            }
        })
        result = extractCodes(resource, "code")
        assert result[0][1] == "code-with-special_chars.123"

    def test_unicode_in_display(self):
        """Test with unicode characters (should not affect code extraction)."""
        resource = json.dumps({
            "code": {
                "coding": [
                    {"system": "http://example.org", "code": "test", "display": "Test \u00e9\u00e8\u00ea"}
                ]
            }
        })
        result = extractCodes(resource, "code")
        assert len(result) == 1
        assert result[0][1] == "test"

    def test_first_code_returns_correct_json_format(self):
        """Test that first code returns properly formatted JSON."""
        resource = json.dumps({
            "code": {
                "coding": [
                    {"system": "http://loinc.org", "code": "8480-6"}
                ]
            }
        })
        result = extractFirstCode(resource, "code")
        # Verify it's valid JSON with expected structure
        parsed = json.loads(result)
        assert "system" in parsed
        assert "code" in parsed
        assert len(parsed) == 2  # Only system and code, no other fields
