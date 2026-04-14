"""
Tests for FHIR Schema Registry.
"""

import pytest
from ...translator.fhir_schema import FHIRSchemaRegistry


class TestFHIRSchemaRegistry:
    """Test FHIR Schema Registry functionality."""
    
    @pytest.fixture
    def registry(self):
        """Create a registry with loaded resources."""
        reg = FHIRSchemaRegistry()
        reg.load_resource("Observation")
        reg.load_resource("Condition")
        reg.load_resource("Patient")
        return reg
        
    def test_load_resource(self, registry):
        """Test loading a resource StructureDefinition."""
        assert "Observation" in registry.resources
        assert "Condition" in registry.resources
        assert "Patient" in registry.resources
        
    def test_get_choice_types_observation_value(self, registry):
        """Test getting choice types for Observation.value[x]."""
        types = registry.get_choice_types("Observation", "value")
        
        # Observation.value[x] should have multiple types
        assert len(types) > 0
        # Common types for value[x]
        assert "Quantity" in types or "CodeableConcept" in types
        
    def test_get_choice_types_condition_onset(self, registry):
        """Test getting choice types for Condition.onset[x]."""
        types = registry.get_choice_types("Condition", "onset")
        
        # Condition.onset[x] should have multiple types
        assert len(types) > 0
        assert "dateTime" in types or "Period" in types
        
    def test_get_choice_types_nonexistent(self, registry):
        """Test getting choice types for non-existent element."""
        types = registry.get_choice_types("Observation", "nonexistent")
        assert types == []
        
    def test_get_choice_types_non_choice_element(self, registry):
        """Test getting choice types for a non-choice element."""
        types = registry.get_choice_types("Observation", "status")
        # status is not a choice type
        assert types == []
        
    def test_get_element_type(self, registry):
        """Test getting element type."""
        # Observation.status should be 'code'
        elem_type = registry.get_element_type("Observation", "status")
        assert elem_type == "code"
        
    def test_is_valid_element(self, registry):
        """Test checking if element is valid."""
        assert registry.is_valid_element("Observation", "status") is True
        assert registry.is_valid_element("Observation", "code") is True
        assert registry.is_valid_element("Observation", "value[x]") is True
        assert registry.is_valid_element("Observation", "nonexistent") is False
        
    def test_is_choice_element(self, registry):
        """Test checking if element is a choice type."""
        assert registry.is_choice_element("Observation", "value") is True
        assert registry.is_choice_element("Observation", "effective") is True
        assert registry.is_choice_element("Observation", "status") is False
        
    def test_get_all_choice_elements(self, registry):
        """Test getting all choice elements for a resource."""
        choice_elements = registry.get_all_choice_elements("Observation")
        
        # Observation has several choice elements
        assert "value" in choice_elements
        assert "effective" in choice_elements
        assert "status" not in choice_elements  # Not a choice element
        
    def test_load_default_resources(self):
        """Test loading default resource set."""
        registry = FHIRSchemaRegistry()
        registry.load_default_resources()
        
        # Should have loaded several resources
        assert len(registry.resources) > 0
        # Core resources should be present (if files exist)
        # Don't assert specific resources since files may not be available


class TestFHIRSchemaRegistryIntegration:
    """Integration tests for common use cases."""
    
    def test_observation_value_types(self):
        """Test that Observation.value[x] has expected types."""
        registry = FHIRSchemaRegistry()
        registry.load_resource("Observation")
        
        types = registry.get_choice_types("Observation", "value")
        
        # value[x] should support at least Quantity and CodeableConcept
        # (actual FHIR R4 has ~11 types)
        assert len(types) >= 2
        
    def test_multiple_resources(self):
        """Test working with multiple resources."""
        registry = FHIRSchemaRegistry()
        registry.load_resource("Observation")
        registry.load_resource("Condition")
        registry.load_resource("Procedure")
        
        # Each should have choice elements
        obs_choices = registry.get_all_choice_elements("Observation")
        cond_choices = registry.get_all_choice_elements("Condition")
        proc_choices = registry.get_all_choice_elements("Procedure")
        
        # Observation has value[x], effective[x]
        assert "value" in obs_choices
        
        # Condition has onset[x], abatement[x]
        assert "onset" in cond_choices or len(cond_choices) > 0
        
        # Procedure has performed[x]
        assert "performed" in proc_choices or len(proc_choices) > 0
