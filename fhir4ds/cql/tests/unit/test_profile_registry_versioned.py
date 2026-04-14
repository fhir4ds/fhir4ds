"""
Tests for versioned ProfileRegistry.
"""

import pytest

from ...translator.model_config import ModelConfig
from ...translator.profile_registry import ProfileRegistry


class TestProfileRegistryVersioned:
    """Tests for ProfileRegistry with ModelConfig."""

    def test_loads_from_versioned_qicore_dir(self):
        """ProfileRegistry should load from versioned QI Core directory."""
        config = ModelConfig()
        registry = ProfileRegistry.from_model_config(config)
        assert registry is not None

    def test_resolve_blood_pressure_profile(self):
        """Should resolve US Core patient profile to a type."""
        config = ModelConfig()
        registry = ProfileRegistry.from_model_config(config)
        base_type = registry.resolve_url_to_type(
            "http://hl7.org/fhir/us/core/StructureDefinition/us-core-observation"
        )
        assert base_type == "Observation"

    def test_generic_profile_url(self):
        """Should resolve generic QICore profile URL for Condition."""
        config = ModelConfig()
        registry = ProfileRegistry.from_model_config(config)
        url = registry.get_generic_profile_url("Condition")
        assert url is not None

    def test_from_model_config_fallback(self, tmp_path):
        """Should fall back to legacy path when versioned dir doesn't exist."""
        config = ModelConfig(schema_root=tmp_path)
        # Should still work because it falls back to the legacy _DEFAULT_CONFIG
        registry = ProfileRegistry.from_model_config(config)
        assert registry is not None

    def test_qicore_profiles_json_in_versioned_dir(self):
        """qicore-profiles.json should exist in qicore-4.1.1 directory."""
        config = ModelConfig()
        path = config.qicore_dir / "qicore-profiles.json"
        assert path.exists()
