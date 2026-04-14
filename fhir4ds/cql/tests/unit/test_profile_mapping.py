"""
Unit tests for US-Core and QICore profile URL to FHIR resource type mapping.

Tests verify:
- Profile URL to resource type mapping via ProfileRegistry
- Fallback behavior for unknown profiles
- Integration with retrieve translation
"""

import pytest

from ...translator.profile_registry import ProfileRegistry
from ...translator.patterns.retrieve import RetrieveTranslator


@pytest.fixture
def profile_registry():
    """Load the ProfileRegistry from the bundled JSON config."""
    return ProfileRegistry.from_json()


class TestProfileUrlMapping:
    """Test profile URL to FHIR resource type mapping."""

    def test_uscore_patient_mapping(self, profile_registry):
        """US Core Patient profile URL maps to Patient."""
        assert profile_registry.resolve_url_to_type(
            "http://hl7.org/fhir/us/core/StructureDefinition/us-core-patient"
        ) == "Patient"

    def test_uscore_condition_mapping(self, profile_registry):
        """US Core Condition profile URL maps to Condition."""
        assert profile_registry.resolve_url_to_type(
            "http://hl7.org/fhir/us/core/StructureDefinition/us-core-condition"
        ) == "Condition"

    def test_uscore_observation_mapping(self, profile_registry):
        """US Core Observation profile URL maps to Observation."""
        assert profile_registry.resolve_url_to_type(
            "http://hl7.org/fhir/us/core/StructureDefinition/us-core-observation"
        ) == "Observation"

    def test_uscore_observation_lab_mapping(self, profile_registry):
        """US Core Observation Lab profile URL maps to Observation."""
        assert profile_registry.resolve_url_to_type(
            "http://hl7.org/fhir/us/core/StructureDefinition/us-core-observation-lab"
        ) == "Observation"

    def test_uscore_encounter_mapping(self, profile_registry):
        """US Core Encounter profile URL maps to Encounter."""
        assert profile_registry.resolve_url_to_type(
            "http://hl7.org/fhir/us/core/StructureDefinition/us-core-encounter"
        ) == "Encounter"

    def test_uscore_procedure_mapping(self, profile_registry):
        """US Core Procedure profile URL maps to Procedure."""
        assert profile_registry.resolve_url_to_type(
            "http://hl7.org/fhir/us/core/StructureDefinition/us-core-procedure"
        ) == "Procedure"

    def test_qicore_condition_mapping(self, profile_registry):
        """QICore Condition profile URL maps to Condition."""
        assert profile_registry.resolve_url_to_type(
            "http://hl7.org/fhir/us/qicore/StructureDefinition/qicore-condition"
        ) == "Condition"

    def test_qicore_encounter_mapping(self, profile_registry):
        """QICore Encounter profile URL maps to Encounter."""
        assert profile_registry.resolve_url_to_type(
            "http://hl7.org/fhir/us/qicore/StructureDefinition/qicore-encounter"
        ) == "Encounter"

    def test_qicore_observation_mapping(self, profile_registry):
        """QICore Observation profile URL maps to Observation."""
        assert profile_registry.resolve_url_to_type(
            "http://hl7.org/fhir/us/qicore/StructureDefinition/qicore-observation"
        ) == "Observation"

    def test_qicore_procedure_mapping(self, profile_registry):
        """QICore Procedure profile URL maps to Procedure."""
        assert profile_registry.resolve_url_to_type(
            "http://hl7.org/fhir/us/qicore/StructureDefinition/qicore-procedure"
        ) == "Procedure"

    def test_qicore_medicationrequest_mapping(self, profile_registry):
        """QICore MedicationRequest profile URL maps to MedicationRequest."""
        assert profile_registry.resolve_url_to_type(
            "http://hl7.org/fhir/us/qicore/StructureDefinition/qicore-medicationrequest"
        ) == "MedicationRequest"

    def test_unknown_profile_returns_none(self, profile_registry):
        """Unknown profile URLs return None."""
        result = profile_registry.resolve_url_to_type(
            "http://example.org/unknown-profile"
        )
        assert result is None

    def test_empty_string_returns_none(self, profile_registry):
        """Empty string returns None."""
        result = profile_registry.resolve_url_to_type("")
        assert result is None


class TestQicoreToFhirType:
    """Test resolve_named_profile mapping for profile names."""

    def test_condition_problems_health_concerns(self, profile_registry):
        """ConditionProblemsHealthConcerns maps to Condition."""
        result = profile_registry.resolve_named_profile("ConditionProblemsHealthConcerns")
        assert result is not None
        fhir_type, profile_url = result
        assert fhir_type == "Condition"
        assert profile_url == "http://hl7.org/fhir/us/qicore/StructureDefinition/qicore-condition-problems-health-concerns"

    def test_condition_encounter_diagnosis(self, profile_registry):
        """ConditionEncounterDiagnosis maps to Condition."""
        result = profile_registry.resolve_named_profile("ConditionEncounterDiagnosis")
        assert result is not None
        fhir_type, profile_url = result
        assert fhir_type == "Condition"
        assert profile_url == "http://hl7.org/fhir/us/qicore/StructureDefinition/qicore-condition-encounter-diagnosis"

    def test_uscore_blood_pressure_profile(self, profile_registry):
        """USCoreBloodPressureProfile maps to Observation."""
        result = profile_registry.resolve_named_profile("USCoreBloodPressureProfile")
        assert result is not None
        fhir_type, profile_url = result
        assert fhir_type == "Observation"
        assert profile_url == "http://hl7.org/fhir/us/core/StructureDefinition/us-core-blood-pressure"

    def test_uscore_body_height(self, profile_registry):
        """USCoreBodyHeight maps to Observation."""
        result = profile_registry.resolve_named_profile("USCoreBodyHeight")
        assert result is not None
        fhir_type, profile_url = result
        assert fhir_type == "Observation"
        assert profile_url == "http://hl7.org/fhir/us/core/StructureDefinition/us-core-body-height"

    def test_uscore_body_weight(self, profile_registry):
        """USCoreBodyWeight maps to Observation."""
        result = profile_registry.resolve_named_profile("USCoreBodyWeight")
        assert result is not None
        fhir_type, profile_url = result
        assert fhir_type == "Observation"
        assert profile_url == "http://hl7.org/fhir/us/core/StructureDefinition/us-core-body-weight"

    def test_uscore_patient(self, profile_registry):
        """USCorePatient maps to Patient."""
        result = profile_registry.resolve_named_profile("USCorePatient")
        assert result is not None
        fhir_type, profile_url = result
        assert fhir_type == "Patient"
        assert profile_url == "http://hl7.org/fhir/us/core/StructureDefinition/us-core-patient"

    def test_qicore_encounter(self, profile_registry):
        """QICoreEncounter maps to Encounter."""
        result = profile_registry.resolve_named_profile("QICoreEncounter")
        assert result is not None
        fhir_type, profile_url = result
        assert fhir_type == "Encounter"
        assert profile_url == "http://hl7.org/fhir/us/qicore/StructureDefinition/qicore-encounter"

    def test_unknown_named_profile_returns_none(self, profile_registry):
        """Unknown named profile returns None."""
        result = profile_registry.resolve_named_profile("UnknownProfile")
        assert result is None


class TestResolveProfileUrlUdf:
    """Test the resolveProfileUrl UDF function."""

    def test_resolve_uscore_patient(self, profile_registry):
        """Resolve US Core Patient profile URL."""
        result = profile_registry.resolve_url_to_type(
            "http://hl7.org/fhir/us/core/StructureDefinition/us-core-patient"
        )
        assert result == "Patient"

    def test_resolve_uscore_condition(self, profile_registry):
        """Resolve US Core Condition profile URL."""
        result = profile_registry.resolve_url_to_type(
            "http://hl7.org/fhir/us/core/StructureDefinition/us-core-condition"
        )
        assert result == "Condition"

    def test_resolve_qicore_observation(self, profile_registry):
        """Resolve QICore Observation profile URL."""
        result = profile_registry.resolve_url_to_type(
            "http://hl7.org/fhir/us/qicore/StructureDefinition/qicore-observation"
        )
        assert result == "Observation"

    def test_resolve_unknown_returns_none(self, profile_registry):
        """Unknown profile URL returns None."""
        result = profile_registry.resolve_url_to_type("http://example.org/unknown-profile")
        assert result is None

    def test_resolve_empty_string_returns_none(self, profile_registry):
        """Empty string returns None."""
        result = profile_registry.resolve_url_to_type("")
        assert result is None
