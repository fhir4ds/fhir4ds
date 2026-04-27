"""
Tests for the column generation helpers and SQLRetrieveCTE precomputed columns.
"""

import pytest

from ...translator.column_generation import build_column_definitions
from ...translator.fhir_schema import FHIRSchemaRegistry
from ...translator.model_config import DEFAULT_MODEL_CONFIG
from ...translator.profile_registry import ProfileRegistry
from ...translator.types import SQLRetrieveCTE

BP_PROFILE_URL = "http://hl7.org/fhir/us/core/StructureDefinition/us-core-blood-pressure"


@pytest.fixture
def fhir_schema():
    """Create schema registry for tests."""
    schema = FHIRSchemaRegistry(model_config=DEFAULT_MODEL_CONFIG)
    schema.load_default_resources()
    return schema


@pytest.fixture
def profile_registry():
    """Create profile registry for tests."""
    return ProfileRegistry.from_model_config(DEFAULT_MODEL_CONFIG)


class TestColumnGeneration:
    """Validate schema-driven column metadata creation."""

    def test_choice_type_column_combines_paths(self, fhir_schema):
        """Choice type properties should produce a combined column definition."""
        column_defs = build_column_definitions(
            "Observation",
            {"effectiveDateTime", "effectivePeriod.start"},
            fhir_schema=fhir_schema,
        )

        assert "effective_date" in column_defs
        col_def = column_defs["effective_date"]
        assert col_def.fhirpath_function == "fhirpath_text"
        assert col_def.paths == ["effectiveDateTime", "effectivePeriod.start"]
        assert col_def.is_choice_type is True

    def test_component_where_columns_use_loinc(self, fhir_schema):
        """BP component.where() paths should resolve to systolic/diastolic column names."""
        systolic_path = "component.where(code.coding.exists(code = '8480-6')).valueQuantity.value"
        diastolic_path = "component.where(code.coding.exists(code = '8462-4')).valueQuantity.value"
        column_defs = build_column_definitions(
            "Observation", {systolic_path, diastolic_path},
            fhir_schema=fhir_schema,
        )

        assert "systolic_value" in column_defs
        assert "diastolic_value" in column_defs
        assert column_defs["systolic_value"].fhirpath_function == "fhirpath_number"
        assert column_defs["diastolic_value"].fhirpath_function == "fhirpath_number"


class TestSQLRetrieveCTE:
    """Tests for precomputed columns exposed by SQLRetrieveCTE."""

    def test_condition_cte_includes_standard_columns(self, fhir_schema):
        """Condition CTE should expose choice-type columns like onset_date and status."""
        cte = SQLRetrieveCTE.create_with_precomputed_columns(
            "Condition", fhir_schema=fhir_schema,
        )
        assert "onset_date" in cte.precomputed_columns
        assert "verification_status" in cte.precomputed_columns
        assert "COALESCE" in cte.to_sql()

    def test_bp_profile_includes_component_columns(self, fhir_schema, profile_registry):
        """Blood pressure profile CTE should include standard Observation columns.

        Component columns (systolic_value/diastolic_value) are demand-driven —
        they are generated only when CQL paths reference them, not eagerly.
        This test validates that the BP profile URL is accepted and standard
        columns are still present.
        """
        cte = SQLRetrieveCTE.create_with_precomputed_columns(
            "Observation",
            profile_url=BP_PROFILE_URL,
            fhir_schema=fhir_schema,
            profile_registry=profile_registry,
        )
        assert "effective_date" in cte.precomputed_columns
        assert "status" in cte.precomputed_columns
        # systolic/diastolic are demand-driven, not eagerly precomputed
        assert "systolic_value" not in cte.precomputed_columns
        assert "diastolic_value" not in cte.precomputed_columns

    def test_non_bp_profile_excludes_component_columns(self, fhir_schema):
        """Observation without BP profile should not expose systolic/diastolic."""
        cte = SQLRetrieveCTE.create_with_precomputed_columns(
            "Observation", fhir_schema=fhir_schema,
        )
        assert "systolic_value" not in cte.precomputed_columns
        assert "diastolic_value" not in cte.precomputed_columns

    def test_bp_profile_sql_includes_standard_observation_columns(self, fhir_schema, profile_registry):
        """BP profile CTE SQL should contain standard Observation column expressions."""
        cte = SQLRetrieveCTE.create_with_precomputed_columns(
            "Observation",
            profile_url=BP_PROFILE_URL,
            fhir_schema=fhir_schema,
            profile_registry=profile_registry,
        )
        sql = cte.to_sql()
        assert "fhirpath_text" in sql
        assert "effectiveDateTime" in sql or "effective_date" in sql
