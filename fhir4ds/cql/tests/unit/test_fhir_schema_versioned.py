"""
Tests for versioned FHIRSchemaRegistry.
"""

import pytest

from ...translator.model_config import ModelConfig
from ...translator.fhir_schema import FHIRSchemaRegistry


class TestFHIRSchemaRegistryVersioned:
    """Tests for FHIRSchemaRegistry with ModelConfig."""

    def test_loads_from_versioned_directory(self):
        """Registry should load resources from versioned schema directory."""
        config = ModelConfig()
        registry = FHIRSchemaRegistry(model_config=config)
        registry.load_resource("Observation")
        assert "Observation" in registry.resources

    def test_loads_without_model_config(self):
        """Registry should still work without ModelConfig (legacy path)."""
        registry = FHIRSchemaRegistry()
        registry.load_resource("Observation")
        assert "Observation" in registry.resources

    def test_load_default_resources_versioned(self):
        """load_default_resources should work with versioned config."""
        config = ModelConfig()
        registry = FHIRSchemaRegistry(model_config=config)
        registry.load_default_resources()
        assert len(registry.resources) > 0

    def test_choice_types_from_versioned(self):
        """Versioned StructureDefinitions should report choice types."""
        config = ModelConfig()
        registry = FHIRSchemaRegistry(model_config=config)
        registry.load_resource("Condition")
        types = registry.get_choice_types("Condition", "onset")
        assert "dateTime" in types

    def test_patient_loaded_versioned(self):
        """Patient resource should load from versioned directory."""
        config = ModelConfig()
        registry = FHIRSchemaRegistry(model_config=config)
        registry.load_resource("Patient")
        assert "Patient" in registry.resources
