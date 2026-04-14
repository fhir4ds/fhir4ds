"""Tests for ProfileRegistry."""

import pytest
from ...translator.profile_registry import ProfileRegistry, get_default_profile_registry


class TestProfileRegistryFromJson:
    """Test loading ProfileRegistry from JSON config."""

    def test_loads_default_config(self):
        registry = get_default_profile_registry()
        assert registry is not None

    def test_generic_profile_url(self):
        registry = get_default_profile_registry()
        assert registry.get_generic_profile_url("Condition") == \
            "http://hl7.org/fhir/us/qicore/StructureDefinition/qicore-condition"

    def test_generic_profile_url_unknown(self):
        registry = get_default_profile_registry()
        assert registry.get_generic_profile_url("FakeResource") is None

    def test_resolve_named_profile(self):
        registry = get_default_profile_registry()
        result = registry.resolve_named_profile("ConditionProblemsHealthConcerns")
        assert result == (
            "Condition",
            "http://hl7.org/fhir/us/qicore/StructureDefinition/qicore-condition-problems-health-concerns",
        )

    def test_resolve_named_profile_bp(self):
        registry = get_default_profile_registry()
        result = registry.resolve_named_profile("USCoreBloodPressureProfile")
        assert result == (
            "Observation",
            "http://hl7.org/fhir/us/core/StructureDefinition/us-core-blood-pressure",
        )

    def test_resolve_named_profile_unknown(self):
        registry = get_default_profile_registry()
        assert registry.resolve_named_profile("UnknownProfile") is None

    def test_resolve_url_to_type(self):
        registry = get_default_profile_registry()
        assert registry.resolve_url_to_type(
            "http://hl7.org/fhir/us/core/StructureDefinition/us-core-patient"
        ) == "Patient"

    def test_resolve_url_to_type_unknown(self):
        registry = get_default_profile_registry()
        assert registry.resolve_url_to_type("http://example.com/unknown") is None

    def test_get_suffix_bp(self):
        registry = get_default_profile_registry()
        assert registry.get_suffix(
            "http://hl7.org/fhir/us/core/StructureDefinition/us-core-blood-pressure"
        ) == "us-core-blood-pressure"

    def test_get_suffix_no_suffix(self):
        registry = get_default_profile_registry()
        assert registry.get_suffix(
            "http://hl7.org/fhir/us/qicore/StructureDefinition/qicore-condition"
        ) is None


class TestProfileRegistryCompatibility:
    """Test backward-compatible property accessors.

    Note: The old hardcoded dicts (QICORE_PROFILE_PATTERNS, QICORE_TO_FHIR_TYPE,
    USCORE_PROFILE_TO_FHIR_TYPE, PROFILES_REQUIRING_SUFFIX) have been removed.
    These tests verify the ProfileRegistry provides equivalent functionality.
    """

    def test_generic_profiles_available(self):
        """Verify generic profile URLs are available for common resource types."""
        registry = get_default_profile_registry()
        # Check that common resource types have generic profiles
        for resource_type in ["Condition", "Observation", "Encounter", "Patient", "Procedure"]:
            url = registry.get_generic_profile_url(resource_type)
            assert url is not None, f"Missing generic profile for {resource_type}"
            assert "qicore" in url.lower() or "us/core" in url.lower(), \
                f"Unexpected URL format for {resource_type}: {url}"

    def test_named_profiles_available(self):
        """Verify named profiles resolve correctly."""
        registry = get_default_profile_registry()
        # Test some known named profiles
        known_profiles = [
            ("ConditionProblemsHealthConcerns", "Condition"),
            ("USCoreBloodPressureProfile", "Observation"),
            ("USCorePatient", "Patient"),
        ]
        for name, expected_type in known_profiles:
            result = registry.resolve_named_profile(name)
            assert result is not None, f"Missing named profile: {name}"
            assert result[0] == expected_type, f"Type mismatch for {name}: {result[0]}"

    def test_url_to_type_resolution(self):
        """Verify URL to type resolution works for common profiles."""
        registry = get_default_profile_registry()
        # Test some known URLs
        known_urls = [
            ("http://hl7.org/fhir/us/core/StructureDefinition/us-core-patient", "Patient"),
            ("http://hl7.org/fhir/us/core/StructureDefinition/us-core-condition", "Condition"),
            ("http://hl7.org/fhir/us/qicore/StructureDefinition/qicore-observation", "Observation"),
        ]
        for url, expected_type in known_urls:
            result = registry.resolve_url_to_type(url)
            assert result == expected_type, f"URL resolution failed for {url}: {result}"

    def test_suffix_profiles_available(self):
        """Verify suffix profiles are configured correctly."""
        registry = get_default_profile_registry()
        # Check blood pressure profile has a suffix
        bp_suffix = registry.get_suffix(
            "http://hl7.org/fhir/us/core/StructureDefinition/us-core-blood-pressure"
        )
        assert bp_suffix is not None, "Missing suffix for blood pressure profile"
        assert "bp" in bp_suffix.lower() or "blood" in bp_suffix.lower(), \
            f"Unexpected suffix format: {bp_suffix}"
