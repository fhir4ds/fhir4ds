"""
Unit tests for Task B5: Schema-driven property → column/UDF mapping.

Tests that FHIRSchemaRegistry.get_udf_for_element() and get_sql_type_for_element()
correctly map FHIR element types to DuckDB UDF functions and SQL types.
"""

import pytest

from ...translator.fhir_schema import FHIRSchemaRegistry


@pytest.fixture
def fhir_registry():
    """Create and load the FHIR schema registry."""
    from ...translator.model_config import DEFAULT_MODEL_CONFIG
    registry = FHIRSchemaRegistry(model_config=DEFAULT_MODEL_CONFIG)
    registry.load_default_resources()
    return registry


@pytest.fixture
def type_to_udf(fhir_registry):
    """Instance-level type→UDF mapping from the registry."""
    return fhir_registry._type_to_udf


@pytest.fixture
def type_to_sql(fhir_registry):
    """Instance-level type→SQL mapping from the registry."""
    return fhir_registry._type_to_sql


class TestSchemaAwarePropertyMapping:
    """Task B5: Schema-driven property → column/UDF mapping."""

    def test_infer_udf_observation_status(self, fhir_registry):
        """Observation.status is type 'code' → fhirpath_text."""
        udf = fhir_registry.get_udf_for_element("Observation", "status")
        assert udf == "fhirpath_text"

    def test_infer_udf_observation_effective(self, fhir_registry):
        """Observation.effectiveDateTime is type 'dateTime' → fhirpath_text (dateTime includes time component)."""
        udf = fhir_registry.get_udf_for_element("Observation", "effectiveDateTime")
        assert udf == "fhirpath_text"

    def test_infer_udf_patient_active(self, fhir_registry):
        """Patient.active is type 'boolean' → fhirpath_bool."""
        udf = fhir_registry.get_udf_for_element("Patient", "active")
        assert udf == "fhirpath_bool"

    def test_infer_udf_unknown_element(self, fhir_registry):
        """Unknown element should default to fhirpath_text."""
        udf = fhir_registry.get_udf_for_element("Observation", "nonexistent")
        assert udf == "fhirpath_text"  # safe default

    def test_infer_udf_unknown_resource(self, fhir_registry):
        """Unknown resource type should default to fhirpath_text."""
        udf = fhir_registry.get_udf_for_element("FakeResource", "status")
        assert udf == "fhirpath_text"

    def test_sql_type_date(self, fhir_registry):
        """Condition.recordedDate (dateTime type) maps to VARCHAR (includes time)."""
        sql_type = fhir_registry.get_sql_type_for_element("Condition", "recordedDate")
        assert sql_type == "VARCHAR"

    def test_sql_type_code(self, fhir_registry):
        """Observation.status should be VARCHAR."""
        sql_type = fhir_registry.get_sql_type_for_element("Observation", "status")
        assert sql_type == "VARCHAR"

    def test_sql_type_boolean(self, fhir_registry):
        """Patient.active should be BOOLEAN."""
        sql_type = fhir_registry.get_sql_type_for_element("Patient", "active")
        assert sql_type == "BOOLEAN"

    def test_sql_type_unknown_element(self, fhir_registry):
        """Unknown element should default to VARCHAR."""
        sql_type = fhir_registry.get_sql_type_for_element("Observation", "nonexistent")
        assert sql_type == "VARCHAR"


class TestFhirTypeToUdfMapping:
    """Test the instance-level type→UDF mapping."""

    def test_datetime_maps_to_date(self, type_to_udf):
        """dateTime type maps to fhirpath_text (dateTime includes time component)."""
        assert type_to_udf["dateTime"] == "fhirpath_text"

    def test_date_maps_to_date(self, type_to_udf):
        """date type should map to fhirpath_date."""
        assert type_to_udf["date"] == "fhirpath_date"

    def test_period_maps_to_date(self, type_to_udf):
        """Period type should map to fhirpath_date."""
        assert type_to_udf["Period"] == "fhirpath_date"

    def test_boolean_maps_to_bool(self, type_to_udf):
        """boolean type should map to fhirpath_bool."""
        assert type_to_udf["boolean"] == "fhirpath_bool"

    def test_code_maps_to_text(self, type_to_udf):
        """code type should map to fhirpath_text."""
        assert type_to_udf["code"] == "fhirpath_text"

    def test_string_maps_to_text(self, type_to_udf):
        """string type should map to fhirpath_text."""
        assert type_to_udf["string"] == "fhirpath_text"

    def test_quantity_maps_to_number(self, type_to_udf):
        """Quantity type should map to fhirpath_number."""
        assert type_to_udf["Quantity"] == "fhirpath_number"

    def test_integer_maps_to_number(self, type_to_udf):
        """integer type should map to fhirpath_number."""
        assert type_to_udf["integer"] == "fhirpath_number"


class TestFhirTypeToSqlMapping:
    """Test the instance-level type→SQL mapping."""

    def test_datetime_maps_to_date(self, type_to_sql):
        """dateTime type maps to VARCHAR (includes time component)."""
        assert type_to_sql["dateTime"] == "VARCHAR"

    def test_boolean_maps_to_boolean(self, type_to_sql):
        """boolean type should map to BOOLEAN."""
        assert type_to_sql["boolean"] == "BOOLEAN"

    def test_code_maps_to_varchar(self, type_to_sql):
        """code type should map to VARCHAR."""
        assert type_to_sql["code"] == "VARCHAR"

    def test_integer_maps_to_integer(self, type_to_sql):
        """integer type should map to INTEGER."""
        assert type_to_sql["integer"] == "INTEGER"

    def test_decimal_maps_to_double(self, type_to_sql):
        """decimal type should map to DOUBLE."""
        assert type_to_sql["decimal"] == "DOUBLE"
