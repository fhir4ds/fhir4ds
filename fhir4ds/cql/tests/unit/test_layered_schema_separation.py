"""
Tests for the Layered Schema Separation architecture.

Verifies that:
- FHIRSchemaRegistry loads configs from versioned ModelConfig paths
- ProfileRegistry loads extension_paths from versioned US Core dir
- translator.py threads all five context fields correctly
- column_generation functions work without module-level globals
- cte_builder fails fast when context.fhir_schema is missing
"""

import pytest

from ...translator.context import SQLTranslationContext
from ...translator.column_generation import (
    build_column_definitions,
    is_choice_type_column,
    property_to_column_name,
)
from ...translator.cte_builder import build_retrieve_cte
from ...translator.fhir_schema import FHIRSchemaRegistry
from ...translator.model_config import DEFAULT_MODEL_CONFIG, ModelConfig
from ...translator.profile_registry import ProfileRegistry
from ...translator.translator import CQLToSQLTranslator


class TestFHIRSchemaRegistryVersionedLoading:
    """Tests that FHIRSchemaRegistry loads configs from versioned path."""

    def test_column_mappings_loaded_from_versioned_dir(self, tmp_path):
        """column_mappings property reads from fhir_r4_dir, not legacy path."""
        schema_dir = tmp_path / "schema" / "fhir-r4-4.0.1"
        schema_dir.mkdir(parents=True)
        (schema_dir / "column_mappings.json").write_text(
            '{"Observation.status": "status"}'
        )
        (schema_dir / "choice_type_prefixes.json").write_text(
            '{"prefixes": ["value"]}'
        )
        (schema_dir / "fhir_type_mappings.json").write_text('{"type_mappings": {}}')
        cfg = ModelConfig(schema_root=tmp_path / "schema")
        reg = FHIRSchemaRegistry(model_config=cfg)
        assert reg.column_mappings == {"Observation.status": "status"}

    def test_choice_type_prefixes_loaded_from_versioned_dir(self, tmp_path):
        """choice_type_prefixes property reads from fhir_r4_dir."""
        schema_dir = tmp_path / "schema" / "fhir-r4-4.0.1"
        schema_dir.mkdir(parents=True)
        (schema_dir / "choice_type_prefixes.json").write_text(
            '{"prefixes": ["myprefix"]}'
        )
        (schema_dir / "column_mappings.json").write_text("{}")
        (schema_dir / "fhir_type_mappings.json").write_text('{"type_mappings": {}}')
        cfg = ModelConfig(schema_root=tmp_path / "schema")
        reg = FHIRSchemaRegistry(model_config=cfg)
        assert "myprefix" in reg.choice_type_prefixes

    def test_type_mappings_instance_level_not_module_level(self):
        """get_udf_for_element uses instance _type_to_udf, not module global."""
        reg = FHIRSchemaRegistry(model_config=DEFAULT_MODEL_CONFIG)
        reg.load_default_resources()
        result = reg.get_udf_for_element("Observation", "effectiveDateTime")
        assert result in ("fhirpath_date", "fhirpath_text")

    def test_fallback_to_legacy_when_versioned_missing(self, tmp_path):
        """Registry falls back gracefully when versioned dir doesn't exist."""
        cfg = ModelConfig(schema_root=tmp_path / "nonexistent")
        import warnings

        with warnings.catch_warnings(record=True):
            reg = FHIRSchemaRegistry(model_config=cfg)
        mappings = reg.column_mappings
        assert isinstance(mappings, dict)


class TestProfileRegistryVersionedLoading:
    """Tests that ProfileRegistry loads extension_paths from versioned US Core dir."""

    def test_extension_paths_loaded_from_versioned_dir(self, tmp_path):
        """extension_paths property reads from us_core_dir."""
        us_core_dir = tmp_path / "schema" / "us-core-3.1.1"
        us_core_dir.mkdir(parents=True)
        (us_core_dir / "extension_paths.json").write_text(
            '{"Patient": {"race": "http://example.org/race"}}'
        )
        qicore_dir = tmp_path / "schema" / "qicore-4.1.1"
        qicore_dir.mkdir(parents=True)
        (qicore_dir / "qicore-profiles.json").write_text(
            '{"generic_profiles": {}, "named_profiles": {}, '
            '"url_to_type": {}, "profiles_requiring_suffix": {}}'
        )
        cfg = ModelConfig(schema_root=tmp_path / "schema")
        registry = ProfileRegistry.from_model_config(cfg)
        assert "Patient" in registry.extension_paths

    def test_component_profile_keywords_from_qicore_json(self):
        """component_profile_keywords extracted from loaded qicore-profiles.json."""
        registry = ProfileRegistry.from_model_config(DEFAULT_MODEL_CONFIG)
        keywords = registry.component_profile_keywords
        assert isinstance(keywords, list)


class TestContextThreading:
    """Tests that translator.py correctly populates all context fields."""

    def test_context_has_all_versioned_fields(self):
        """After translator init, context has all five fields populated."""
        translator = CQLToSQLTranslator()
        ctx = translator.context
        assert ctx.fhir_schema is not None
        assert ctx.profile_registry is not None
        assert ctx.column_mappings is not None
        assert ctx.choice_type_prefixes is not None
        assert ctx.extension_paths is not None

    def test_context_column_mappings_matches_registry(self):
        """context.column_mappings is the same object as fhir_schema.column_mappings."""
        translator = CQLToSQLTranslator()
        ctx = translator.context
        assert ctx.column_mappings is ctx.fhir_schema.column_mappings

    def test_no_module_level_fallback_in_expressions(self):
        """ExpressionTranslator does not use _EXTENSION_PATHS fallback."""
        from ...translator import expressions as expr_module

        assert not hasattr(expr_module, "_EXTENSION_PATHS"), (
            "_EXTENSION_PATHS module-level global must be removed"
        )


class TestColumnGenerationWithoutGlobals:
    """Tests that column_generation functions work without module-level globals."""

    def test_build_column_definitions_requires_fhir_schema(self):
        """build_column_definitions raises ValueError when fhir_schema is None."""
        with pytest.raises((ValueError, TypeError)):
            build_column_definitions("Observation", {"status"}, fhir_schema=None)

    def test_property_to_column_name_uses_provided_mappings(self):
        """property_to_column_name uses explicit column_mappings when provided."""
        custom = {"Observation.status": "my_status_col"}
        result = property_to_column_name(
            "Observation.status", column_mappings=custom
        )
        assert result == "my_status_col"

    def test_is_choice_type_column_uses_provided_prefixes(self):
        """is_choice_type_column uses explicit prefixes when provided."""
        assert is_choice_type_column("custom_value", choice_type_prefixes={"custom"})
        assert not is_choice_type_column("status", choice_type_prefixes={"custom"})


class TestCTEBuilderFailsFast:
    """cte_builder raises RuntimeError when context.fhir_schema is None."""

    def test_build_retrieve_cte_raises_without_schema(self):
        """build_retrieve_cte raises RuntimeError (not creates fallback registry)."""
        ctx = SQLTranslationContext(resource_type="Observation")
        ctx.fhir_schema = None
        with pytest.raises(RuntimeError, match="fhir_schema is required"):
            build_retrieve_cte(
                resource_type="Observation",
                valueset=None,
                properties=set(),
                context=ctx,
            )
