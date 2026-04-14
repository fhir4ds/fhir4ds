"""
Tests for ModelConfig version configuration.
"""

import json
import pytest
from pathlib import Path

from ...translator.model_config import ModelConfig, DEFAULT_MODEL_CONFIG


class TestModelConfig:
    """Tests for ModelConfig dataclass."""

    def test_default_config_values(self):
        """Default ModelConfig should have production-target versions."""
        config = ModelConfig()
        assert config.fhir_r4_version == "4.0.1"
        assert config.us_core_version == "3.1.1"
        assert config.qicore_version == "4.1.1"

    def test_default_paths_exist(self):
        """Default ModelConfig should resolve to schema directories that exist."""
        config = ModelConfig()
        assert config.fhir_r4_dir.exists(), f"Missing: {config.fhir_r4_dir}"
        assert config.us_core_dir.exists(), f"Missing: {config.us_core_dir}"
        assert config.qicore_dir.exists(), f"Missing: {config.qicore_dir}"

    def test_validate_active(self):
        """Default config should validate without errors."""
        config = ModelConfig()
        errors = config.validate()
        assert errors == [], f"Unexpected errors: {errors}"

    def test_validate_not_implemented(self):
        """Future version config should report not-implemented errors."""
        config = ModelConfig(qicore_version="6.0.0", us_core_version="6.1.0")
        errors = config.validate()
        assert any("not yet implemented" in e for e in errors)

    def test_custom_schema_root(self, tmp_path):
        """ModelConfig should accept a custom schema_root."""
        config = ModelConfig(schema_root=tmp_path)
        assert tmp_path in config.fhir_r4_dir.parents or config.fhir_r4_dir.parent == tmp_path

    def test_validate_missing_dir(self, tmp_path):
        """Missing directories should produce validation errors."""
        config = ModelConfig(schema_root=tmp_path)
        errors = config.validate()
        assert len(errors) == 3  # All three layers missing

    def test_fhir_r4_dir_path(self):
        """fhir_r4_dir should include the version."""
        config = ModelConfig()
        assert "fhir-r4-4.0.1" in str(config.fhir_r4_dir)

    def test_us_core_dir_path(self):
        """us_core_dir should include the version."""
        config = ModelConfig()
        assert "us-core-3.1.1" in str(config.us_core_dir)

    def test_qicore_dir_path(self):
        """qicore_dir should include the version."""
        config = ModelConfig()
        assert "qicore-4.1.1" in str(config.qicore_dir)

    def test_default_singleton(self):
        """DEFAULT_MODEL_CONFIG should be a valid ModelConfig."""
        assert isinstance(DEFAULT_MODEL_CONFIG, ModelConfig)
        assert DEFAULT_MODEL_CONFIG.validate() == []


class TestMetadataFiles:
    """Tests that versioned metadata files exist and are valid."""

    def test_fhir_r4_metadata(self):
        config = ModelConfig()
        meta_path = config.fhir_r4_dir / "metadata.json"
        assert meta_path.exists()
        meta = json.loads(meta_path.read_text())
        assert meta["status"] == "active"
        assert meta["version"] == "4.0.1"

    def test_us_core_metadata(self):
        config = ModelConfig()
        meta_path = config.us_core_dir / "metadata.json"
        assert meta_path.exists()
        meta = json.loads(meta_path.read_text())
        assert meta["status"] == "active"
        assert meta["version"] == "3.1.1"

    def test_qicore_metadata(self):
        config = ModelConfig()
        meta_path = config.qicore_dir / "metadata.json"
        assert meta_path.exists()
        meta = json.loads(meta_path.read_text())
        assert meta["status"] == "active"
        assert meta["version"] == "4.1.1"

    def test_future_us_core_not_implemented(self):
        config = ModelConfig(us_core_version="6.1.0")
        meta_path = config.us_core_dir / "metadata.json"
        assert meta_path.exists()
        meta = json.loads(meta_path.read_text())
        assert meta["status"] == "not-implemented"

    def test_future_qicore_not_implemented(self):
        config = ModelConfig(qicore_version="6.0.0")
        meta_path = config.qicore_dir / "metadata.json"
        assert meta_path.exists()
        meta = json.loads(meta_path.read_text())
        assert meta["status"] == "not-implemented"
