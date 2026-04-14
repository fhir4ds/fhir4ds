"""
Tests for QI Core model properties and extension path loading.
"""

import json
import pytest
from pathlib import Path

from ...translator.model_config import ModelConfig
from ...translator.profile_registry import ProfileRegistry, get_default_profile_registry


class TestModelProperties:
    """Tests for QI Core model_properties.json."""

    def test_model_properties_file_exists(self):
        """model_properties.json should exist in qicore-4.1.1 directory."""
        config = ModelConfig()
        path = config.qicore_dir / "model_properties.json"
        assert path.exists()

    def test_patient_race_in_model_properties(self):
        """Patient.race should be defined in model properties."""
        config = ModelConfig()
        with open(config.qicore_dir / "model_properties.json") as f:
            props = json.load(f)
        assert "Patient" in props
        assert "race" in props["Patient"]
        assert "us-core-race" in props["Patient"]["race"]["extension_url"]

    def test_patient_sex_in_model_properties(self):
        """Patient.sex should be defined in model properties."""
        config = ModelConfig()
        with open(config.qicore_dir / "model_properties.json") as f:
            props = json.load(f)
        assert "sex" in props["Patient"]
        assert "us-core-sex" in props["Patient"]["sex"]["extension_url"]

    def test_patient_birthsex_in_4_1_1(self):
        """Patient.birthSex should be present in QI Core 4.1.1."""
        config = ModelConfig(qicore_version="4.1.1")
        with open(config.qicore_dir / "model_properties.json") as f:
            props = json.load(f)
        assert "birthSex" in props["Patient"]


class TestExtensionPaths:
    """Tests for versioned extension path loading via ProfileRegistry."""

    def test_load_extension_paths_default(self):
        """Default loading should return Patient extension paths."""
        registry = get_default_profile_registry()
        paths = registry.extension_paths
        assert "Patient" in paths

    def test_load_extension_paths_with_config(self):
        """Loading with ModelConfig should return versioned extension paths."""
        config = ModelConfig()
        registry = ProfileRegistry.from_model_config(config)
        paths = registry.extension_paths
        assert "Patient" in paths
        assert "sex" in paths["Patient"]
        assert "race" in paths["Patient"]
        assert "ethnicity" in paths["Patient"]

    def test_extension_paths_include_birthsex(self):
        """US Core 3.1.1 extension paths should include birthSex."""
        config = ModelConfig()
        registry = ProfileRegistry.from_model_config(config)
        paths = registry.extension_paths
        assert "birthSex" in paths["Patient"]

    def test_extension_paths_file_exists_in_versioned_dir(self):
        """extension_paths.json should exist in us-core-3.1.1 directory."""
        config = ModelConfig()
        path = config.us_core_dir / "extension_paths.json"
        assert path.exists()
