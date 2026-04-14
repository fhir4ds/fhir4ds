"""
Unit tests for related context retrieves.

Tests parsing and translation of related context retrieve expressions
using the navigation (->) syntax.
"""

import pytest

from ....parser.ast_nodes import (
    Identifier,
    Literal,
    Property,
    Retrieve,
)
from ....translator import CQLTranslator


class TestRelatedContextRetrieveParsing:
    """Tests for related context retrieve parsing."""

    @pytest.fixture
    def translator(self) -> CQLTranslator:
        """Create a translator instance for testing."""
        return CQLTranslator()

    def test_retrieve_with_navigation_path(self, translator: CQLTranslator):
        """Test parsing retrieve with navigation path."""
        expr = Retrieve(
            type="Condition",
            terminology=None,
            terminology_property=None,
            navigation_path="subject",
        )
        result = translator.translate_expression(expr)
        assert "Condition" in result

    def test_retrieve_without_navigation(self, translator: CQLTranslator):
        """Test regular retrieve without navigation."""
        expr = Retrieve(
            type="Patient",
            terminology=None,
            terminology_property=None,
            navigation_path=None,
        )
        result = translator.translate_expression(expr)
        assert "Patient" in result

    def test_encounter_service_provider(self, translator: CQLTranslator):
        """Test: [Encounter -> serviceProvider]."""
        expr = Retrieve(
            type="Encounter",
            terminology=None,
            terminology_property=None,
            navigation_path="serviceProvider",
        )
        result = translator.translate_expression(expr)
        assert "Encounter" in result

    def test_observation_encounter(self, translator: CQLTranslator):
        """Test: [Observation -> encounter]."""
        expr = Retrieve(
            type="Observation",
            terminology=None,
            terminology_property=None,
            navigation_path="encounter",
        )
        result = translator.translate_expression(expr)
        assert "Observation" in result

    def test_condition_subject(self, translator: CQLTranslator):
        """Test: [Condition -> subject]."""
        expr = Retrieve(
            type="Condition",
            terminology=None,
            terminology_property=None,
            navigation_path="subject",
        )
        result = translator.translate_expression(expr)
        assert "Condition" in result

    def test_diagnostic_report_subject(self, translator: CQLTranslator):
        """Test: [DiagnosticReport -> subject]."""
        expr = Retrieve(
            type="DiagnosticReport",
            terminology=None,
            terminology_property=None,
            navigation_path="subject",
        )
        result = translator.translate_expression(expr)
        assert "DiagnosticReport" in result

    def test_procedure_subject(self, translator: CQLTranslator):
        """Test: [Procedure -> subject]."""
        expr = Retrieve(
            type="Procedure",
            terminology=None,
            terminology_property=None,
            navigation_path="subject",
        )
        result = translator.translate_expression(expr)
        assert "Procedure" in result

    def test_medication_request_subject(self, translator: CQLTranslator):
        """Test: [MedicationRequest -> subject]."""
        expr = Retrieve(
            type="MedicationRequest",
            terminology=None,
            terminology_property=None,
            navigation_path="subject",
        )
        result = translator.translate_expression(expr)
        assert "MedicationRequest" in result


class TestRetrieveWithTerminology:
    """Tests for retrieve with terminology filtering."""

    @pytest.fixture
    def translator(self) -> CQLTranslator:
        """Create a translator instance for testing."""
        return CQLTranslator()

    def test_retrieve_with_code_filter(self, translator: CQLTranslator):
        """Test retrieve with code terminology filter."""
        expr = Retrieve(
            type="Condition",
            terminology=Literal(value="http://snomed.info/sct|73211009"),
            terminology_property="code",
            navigation_path=None,
        )
        result = translator.translate_expression(expr)
        assert "Condition" in result

    def test_retrieve_with_identifier_filter(self, translator: CQLTranslator):
        """Test retrieve with identifier terminology filter."""
        expr = Retrieve(
            type="Observation",
            terminology=Identifier(name="LabCodes"),
            terminology_property="code",
            navigation_path=None,
        )
        result = translator.translate_expression(expr)
        assert "Observation" in result

    def test_retrieve_with_value_set_reference(self, translator: CQLTranslator):
        """Test retrieve with value set reference."""
        expr = Retrieve(
            type="Condition",
            terminology=Identifier(name="DiabetesCodes"),
            terminology_property="code",
            navigation_path=None,
        )
        result = translator.translate_expression(expr)
        assert "Condition" in result


class TestRetrieveNavigationProperties:
    """Tests for various navigation properties."""

    @pytest.fixture
    def translator(self) -> CQLTranslator:
        """Create a translator instance for testing."""
        return CQLTranslator()

    def test_navigation_to_organization(self, translator: CQLTranslator):
        """Test navigation to Organization via serviceProvider."""
        expr = Retrieve(
            type="Encounter",
            terminology=None,
            terminology_property=None,
            navigation_path="serviceProvider",
        )
        result = translator.translate_expression(expr)
        assert "Encounter" in result

    def test_navigation_to_patient(self, translator: CQLTranslator):
        """Test navigation to Patient via subject."""
        expr = Retrieve(
            type="Condition",
            terminology=None,
            terminology_property=None,
            navigation_path="subject",
        )
        result = translator.translate_expression(expr)
        assert "Condition" in result

    def test_navigation_to_encounter(self, translator: CQLTranslator):
        """Test navigation to Encounter via encounter."""
        expr = Retrieve(
            type="Observation",
            terminology=None,
            terminology_property=None,
            navigation_path="encounter",
        )
        result = translator.translate_expression(expr)
        assert "Observation" in result

    def test_navigation_to_device(self, translator: CQLTranslator):
        """Test navigation to Device via device."""
        expr = Retrieve(
            type="Observation",
            terminology=None,
            terminology_property=None,
            navigation_path="device",
        )
        result = translator.translate_expression(expr)
        assert "Observation" in result

    def test_navigation_to_location(self, translator: CQLTranslator):
        """Test navigation to Location via location."""
        expr = Retrieve(
            type="Encounter",
            terminology=None,
            terminology_property=None,
            navigation_path="location",
        )
        result = translator.translate_expression(expr)
        assert "Encounter" in result


class TestRetrieveWithCombinedFilters:
    """Tests for retrieve with combined navigation and terminology."""

    @pytest.fixture
    def translator(self) -> CQLTranslator:
        """Create a translator instance for testing."""
        return CQLTranslator()

    def test_navigation_with_code_filter(self, translator: CQLTranslator):
        """Test navigation with code filter combined."""
        # Navigation with terminology - both specified
        expr = Retrieve(
            type="Condition",
            terminology=Literal(value="diabetes-code"),
            terminology_property="code",
            navigation_path="subject",
        )
        result = translator.translate_expression(expr)
        assert "Condition" in result

    def test_navigation_with_value_set(self, translator: CQLTranslator):
        """Test navigation with value set combined."""
        expr = Retrieve(
            type="Observation",
            terminology=Identifier(name="VitalSignCodes"),
            terminology_property="code",
            navigation_path="encounter",
        )
        result = translator.translate_expression(expr)
        assert "Observation" in result


class TestRetrieveEdgeCases:
    """Tests for edge cases in retrieve expressions."""

    @pytest.fixture
    def translator(self) -> CQLTranslator:
        """Create a translator instance for testing."""
        return CQLTranslator()

    def test_retrieve_resource_type_only(self, translator: CQLTranslator):
        """Test retrieve with just resource type."""
        expr = Retrieve(
            type="Patient",
            terminology=None,
            terminology_property=None,
            navigation_path=None,
        )
        result = translator.translate_expression(expr)
        assert "Patient" in result

    def test_retrieve_all_resources(self, translator: CQLTranslator):
        """Test retrieve for all resources of a type."""
        expr = Retrieve(
            type="Observation",
            terminology=None,
            terminology_property=None,
            navigation_path=None,
        )
        result = translator.translate_expression(expr)
        assert "Observation" in result

    def test_retrieve_with_multiple_word_type(self, translator: CQLTranslator):
        """Test retrieve with multi-word resource type."""
        expr = Retrieve(
            type="DiagnosticReport",
            terminology=None,
            terminology_property=None,
            navigation_path=None,
        )
        result = translator.translate_expression(expr)
        assert "DiagnosticReport" in result

    def test_retrieve_medication_request(self, translator: CQLTranslator):
        """Test retrieve for MedicationRequest."""
        expr = Retrieve(
            type="MedicationRequest",
            terminology=None,
            terminology_property=None,
            navigation_path="subject",
        )
        result = translator.translate_expression(expr)
        assert "MedicationRequest" in result

    def test_retrieve_immunization(self, translator: CQLTranslator):
        """Test retrieve for Immunization."""
        expr = Retrieve(
            type="Immunization",
            terminology=None,
            terminology_property=None,
            navigation_path="patient",
        )
        result = translator.translate_expression(expr)
        assert "Immunization" in result

    def test_retrieve_allergy_intolerance(self, translator: CQLTranslator):
        """Test retrieve for AllergyIntolerance."""
        expr = Retrieve(
            type="AllergyIntolerance",
            terminology=None,
            terminology_property=None,
            navigation_path="patient",
        )
        result = translator.translate_expression(expr)
        assert "AllergyIntolerance" in result


class TestRetrieveTerminologyProperty:
    """Tests for terminology property specification."""

    @pytest.fixture
    def translator(self) -> CQLTranslator:
        """Create a translator instance for testing."""
        return CQLTranslator()

    def test_code_property(self, translator: CQLTranslator):
        """Test retrieve with 'code' terminology property."""
        expr = Retrieve(
            type="Condition",
            terminology=Literal(value="flu"),
            terminology_property="code",
            navigation_path=None,
        )
        result = translator.translate_expression(expr)
        assert "Condition" in result

    def test_value_property(self, translator: CQLTranslator):
        """Test retrieve with 'value' terminology property."""
        expr = Retrieve(
            type="Observation",
            terminology=Literal(value="positive"),
            terminology_property="value",
            navigation_path=None,
        )
        result = translator.translate_expression(expr)
        assert "Observation" in result

    def test_category_property(self, translator: CQLTranslator):
        """Test retrieve with 'category' terminology property."""
        expr = Retrieve(
            type="Observation",
            terminology=Literal(value="vital-signs"),
            terminology_property="category",
            navigation_path=None,
        )
        result = translator.translate_expression(expr)
        assert "Observation" in result


class TestProfileRetrieve:
    """Tests for profile-based retrieve (placeholder tests)."""

    @pytest.fixture
    def translator(self) -> CQLTranslator:
        """Create a translator instance for testing."""
        return CQLTranslator()

    def test_profile_retrieve_basic(self, translator: CQLTranslator):
        """Test basic profile-based retrieve."""
        # Profile filtering would be handled via terminology in current implementation
        expr = Retrieve(
            type="Patient",
            terminology=None,
            terminology_property=None,
            navigation_path=None,
        )
        result = translator.translate_expression(expr)
        assert "Patient" in result

    def test_profile_with_url(self, translator: CQLTranslator):
        """Test profile retrieve with URL."""
        # Profile URL would be in terminology in current implementation
        expr = Retrieve(
            type="Observation",
            terminology=Literal(value="http://hl7.org/fhir/StructureDefinition/bodyheight"),
            terminology_property="code",
            navigation_path=None,
        )
        result = translator.translate_expression(expr)
        assert "Observation" in result

    def test_profile_laboratory_observations(self, translator: CQLTranslator):
        """Test profile for laboratory observations."""
        expr = Retrieve(
            type="Observation",
            terminology=Literal(value="http://hl7.org/fhir/StructureDefinition/observation-lab"),
            terminology_property="category",
            navigation_path=None,
        )
        result = translator.translate_expression(expr)
        assert "Observation" in result

    def test_profile_vital_signs(self, translator: CQLTranslator):
        """Test profile for vital signs."""
        expr = Retrieve(
            type="Observation",
            terminology=Literal(value="http://hl7.org/fhir/StructureDefinition/vitalsigns"),
            terminology_property="category",
            navigation_path=None,
        )
        result = translator.translate_expression(expr)
        assert "Observation" in result
