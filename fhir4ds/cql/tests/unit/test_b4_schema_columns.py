"""
Unit tests for Task B4: Schema-driven property validation.

Tests that FHIRSchemaRegistry.is_valid_precomputed_column() correctly validates
column names against FHIR StructureDefinitions, replacing hardcoded dicts.
"""

import pytest

from ...translator.fhir_schema import FHIRSchemaRegistry


@pytest.fixture
def fhir_registry():
    """Create and load the FHIR schema registry."""
    registry = FHIRSchemaRegistry()
    registry.load_default_resources()
    return registry


class TestResourceTypeValidColumns:
    """Task B4: Schema-driven property validation."""

    def test_observation_status_is_valid(self, fhir_registry):
        """Observation.status should be valid."""
        assert fhir_registry.is_valid_precomputed_column("Observation", "status")

    def test_observation_effective_date_is_valid(self, fhir_registry):
        """Observation.effective_date should be valid (maps to effective[x])."""
        assert fhir_registry.is_valid_precomputed_column("Observation", "effective_date")

    def test_observation_invalid_column(self, fhir_registry):
        """Invalid column name should return False."""
        assert not fhir_registry.is_valid_precomputed_column("Observation", "nonexistent_col")

    def test_condition_verification_status(self, fhir_registry):
        """Condition.verificationStatus should be valid."""
        assert fhir_registry.is_valid_precomputed_column("Condition", "verification_status")

    def test_condition_onset_date(self, fhir_registry):
        """Condition.onset_date should be valid (maps to onset[x])."""
        assert fhir_registry.is_valid_precomputed_column("Condition", "onset_date")

    def test_encounter_class_code(self, fhir_registry):
        """Encounter.class should be valid."""
        assert fhir_registry.is_valid_precomputed_column("Encounter", "class_code")

    def test_encounter_status(self, fhir_registry):
        """Encounter.status should be valid."""
        assert fhir_registry.is_valid_precomputed_column("Encounter", "status")

    def test_patient_birth_date(self, fhir_registry):
        """Patient.birthDate should be valid."""
        assert fhir_registry.is_valid_precomputed_column("Patient", "birth_date")

    def test_patient_gender(self, fhir_registry):
        """Patient.gender should be valid."""
        assert fhir_registry.is_valid_precomputed_column("Patient", "gender")

    def test_procedure_performed_date(self, fhir_registry):
        """Procedure.performed_date should be valid (maps to performed[x])."""
        assert fhir_registry.is_valid_precomputed_column("Procedure", "performed_date")

    def test_medication_request_authored_on(self, fhir_registry):
        """MedicationRequest.authoredOn should be valid."""
        assert fhir_registry.is_valid_precomputed_column("MedicationRequest", "authored_on")

    def test_unknown_resource_returns_false(self, fhir_registry):
        """Unknown resource type should return False."""
        assert not fhir_registry.is_valid_precomputed_column("FakeResource", "status")

    def test_invalid_column_for_valid_resource(self, fhir_registry):
        """Valid resource but invalid column should return False."""
        assert not fhir_registry.is_valid_precomputed_column("Observation", "fake_column")

    def test_code_column(self, fhir_registry):
        """Code column should be valid for many resources."""
        assert fhir_registry.is_valid_precomputed_column("Condition", "code")
        assert fhir_registry.is_valid_precomputed_column("Observation", "code")
        assert fhir_registry.is_valid_precomputed_column("Procedure", "code")

    def test_value_quantity_for_observation(self, fhir_registry):
        """Observation.value_quantity should be valid."""
        assert fhir_registry.is_valid_precomputed_column("Observation", "value_quantity")


class TestSchemaVsHardcodedParity:
    """Verify schema-driven approach matches hardcoded dict coverage."""

    def test_all_dict_resource_types_loaded(self, fhir_registry):
        """All resource types from RESOURCE_TYPE_VALID_COLUMNS should be loadable."""
        dict_resource_types = [
            "Condition", "Observation", "Encounter", "Procedure",
            "MedicationRequest", "MedicationAdministration", "Coverage",
            "Patient", "ServiceRequest", "DiagnosticReport",
            "Immunization", "AllergyIntolerance", "DeviceRequest",
            "CommunicationRequest",
        ]
        for resource_type in dict_resource_types:
            fhir_registry.load_resource(resource_type)
            # Should not raise - resource should be loadable

    def test_condition_columns_match(self, fhir_registry):
        """Condition columns should match hardcoded dict (minus invalid 'status')."""
        # Note: Condition doesn't have a 'status' element in FHIR - only clinicalStatus
        # and verificationStatus. The hardcoded dict incorrectly includes 'status'.
        condition_columns = {
            "onset_date", "abatement_date", "abatement_end_date", "recorded_date",
            "verification_status", "clinical_status", "code",
        }
        for col in condition_columns:
            assert fhir_registry.is_valid_precomputed_column("Condition", col), \
                f"Column {col} should be valid for Condition"

    def test_observation_columns_match(self, fhir_registry):
        """Observation columns should match hardcoded dict."""
        observation_columns = {
            "effective_date", "status", "value_quantity", "code", "issued",
        }
        for col in observation_columns:
            assert fhir_registry.is_valid_precomputed_column("Observation", col), \
                f"Column {col} should be valid for Observation"
