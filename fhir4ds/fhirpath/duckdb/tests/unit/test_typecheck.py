"""
Unit tests for FHIRPath type checking functions.

Tests the typecheck module including:
- is_type() function
- as_type() function
- type_fn() function
- get_fhir_type() helper
- resolve_polymorphic_field() helper
"""

import pytest
from typing import Any, Dict, List

from ...functions.typecheck import (
    is_type,
    as_type,
    type_fn,
    get_fhir_type,
    resolve_polymorphic_field,
    get_polymorphic_options,
)
from ...fhir_types_generated import (
    FHIR_TYPES,
    CHOICE_TYPES,
    TYPE_HIERARCHY,
    is_fhir_type,
    is_subclass_of,
    get_type_info,
    is_primitive,
    is_datatype,
    is_resource,
)


class TestFHIRTypesGenerated:
    """Tests for the generated FHIR types module."""

    def test_fhir_types_exists(self):
        """FHIR_TYPES dict should be populated."""
        assert FHIR_TYPES is not None
        assert len(FHIR_TYPES) > 0

    def test_primitive_types_exist(self):
        """Core primitive types should be present."""
        primitives = ["boolean", "integer", "decimal", "string", "date", "dateTime", "time"]
        for p in primitives:
            assert p in FHIR_TYPES, f"Primitive type {p} not found"
            assert FHIR_TYPES[p]["kind"] == "primitive"

    def test_datatypes_exist(self):
        """Core complex types should be present."""
        datatypes = ["Quantity", "Period", "Coding", "CodeableConcept", "Reference", "Identifier"]
        for d in datatypes:
            assert d in FHIR_TYPES, f"Datatype {d} not found"
            assert FHIR_TYPES[d]["kind"] == "datatype"

    def test_resources_exist(self):
        """Core resources should be present."""
        resources = ["Patient", "Observation", "Condition", "Encounter", "Practitioner"]
        for r in resources:
            assert r in FHIR_TYPES, f"Resource {r} not found"
            assert FHIR_TYPES[r]["kind"] == "resource"

    def test_choice_types_exist(self):
        """Choice type mappings should be present."""
        assert "Observation.value" in CHOICE_TYPES
        assert "valueQuantity" in CHOICE_TYPES["Observation.value"]
        assert "valueString" in CHOICE_TYPES["Observation.value"]

    def test_type_hierarchy_exists(self):
        """Type hierarchy should be populated."""
        assert TYPE_HIERARCHY is not None
        assert len(TYPE_HIERARCHY) > 0

    def test_is_fhir_type(self):
        """is_fhir_type helper should work correctly."""
        assert is_fhir_type("Patient") is True
        assert is_fhir_type("Quantity") is True
        assert is_fhir_type("string") is True
        assert is_fhir_type("NonExistentType") is False

    def test_is_subclass_of(self):
        """is_subclass_of should correctly check inheritance."""
        # Patient extends DomainResource
        assert is_subclass_of("Patient", "DomainResource") is True
        # DomainResource extends Resource
        assert is_subclass_of("DomainResource", "Resource") is True
        # Transitive: Patient is a Resource
        assert is_subclass_of("Patient", "Resource") is True
        # Age extends Quantity
        assert is_subclass_of("Age", "Quantity") is True
        # Not related
        assert is_subclass_of("Patient", "Observation") is False
        # Same type
        assert is_subclass_of("Patient", "Patient") is True

    def test_get_type_info(self):
        """get_type_info should return type metadata."""
        info = get_type_info("Quantity")
        assert info is not None
        assert info["kind"] == "datatype"
        assert "elements" in info
        assert "value" in info["elements"]

    def test_is_primitive(self):
        """is_primitive should correctly identify primitives."""
        assert is_primitive("string") is True
        assert is_primitive("integer") is True
        assert is_primitive("Quantity") is False
        assert is_primitive("Patient") is False

    def test_is_datatype(self):
        """is_datatype should correctly identify datatypes."""
        assert is_datatype("Quantity") is True
        assert is_datatype("Period") is True
        assert is_datatype("string") is False
        assert is_datatype("Patient") is False

    def test_is_resource(self):
        """is_resource should correctly identify resources."""
        assert is_resource("Patient") is True
        assert is_resource("Observation") is True
        assert is_resource("Quantity") is False
        assert is_resource("string") is False


class TestGetType:
    """Tests for get_fhir_type function."""

    def test_get_fhir_type_primitives(self):
        """Should correctly identify primitive types."""
        assert get_fhir_type(True) == "boolean"
        assert get_fhir_type(False) == "boolean"
        assert get_fhir_type(42) == "integer"
        assert get_fhir_type(3.14) == "decimal"
        assert get_fhir_type("hello") == "string"

    def test_get_fhir_type_quantity(self):
        """Should identify Quantity from structure."""
        value = {"value": 100, "unit": "mg"}
        assert get_fhir_type(value) == "Quantity"

    def test_get_fhir_type_period(self):
        """Should identify Period from structure."""
        value = {"start": "2020-01-01", "end": "2020-12-31"}
        assert get_fhir_type(value) == "Period"

    def test_get_fhir_type_coding(self):
        """Should identify Coding from structure."""
        value = {"system": "http://loinc.org", "code": "1234-5"}
        assert get_fhir_type(value) == "Coding"

    def test_get_fhir_type_codeable_concept(self):
        """Should identify CodeableConcept from structure."""
        value = {"coding": [{"system": "http://loinc.org", "code": "1234-5"}]}
        assert get_fhir_type(value) == "CodeableConcept"

    def test_get_fhir_type_reference(self):
        """Should identify Reference from structure."""
        value = {"reference": "Patient/123"}
        assert get_fhir_type(value) == "Reference"

    def test_get_fhir_type_identifier(self):
        """Should identify Identifier from structure."""
        value = {"system": "http://example.org", "value": "12345"}
        assert get_fhir_type(value) == "Identifier"

    def test_get_fhir_type_human_name(self):
        """Should identify HumanName from structure."""
        value = {"family": "Smith", "given": ["John"]}
        assert get_fhir_type(value) == "HumanName"

    def test_get_fhir_type_address(self):
        """Should identify Address from structure."""
        value = {"line": ["123 Main St"], "city": "Boston"}
        assert get_fhir_type(value) == "Address"

    def test_get_fhir_type_range(self):
        """Should identify Range from structure."""
        value = {"low": {"value": 10}, "high": {"value": 20}}
        assert get_fhir_type(value) == "Range"

    def test_get_fhir_type_ratio(self):
        """Should identify Ratio from structure."""
        value = {"numerator": {"value": 1}, "denominator": {"value": 2}}
        assert get_fhir_type(value) == "Ratio"

    def test_get_fhir_type_resource(self):
        """Should identify resource type from resourceType field."""
        value = {"resourceType": "Patient", "id": "123"}
        assert get_fhir_type(value) == "Patient"

        value = {"resourceType": "Observation", "id": "456"}
        assert get_fhir_type(value) == "Observation"

    def test_get_fhir_type_list(self):
        """Should identify lists as Collection."""
        assert get_fhir_type([1, 2, 3]) == "Collection"
        assert get_fhir_type([]) == "Collection"

    def test_get_fhir_type_none(self):
        """Should return None for None values."""
        assert get_fhir_type(None) is None


class TestPolymorphicFields:
    """Tests for polymorphic (choice type) field resolution."""

    def test_get_polymorphic_options_observation_value(self):
        """Should return all options for Observation.value."""
        options = get_polymorphic_options("Observation", "value")
        assert "valueQuantity" in options
        assert "valueString" in options
        assert "valueBoolean" in options
        assert "valueInteger" in options
        assert "valueCodeableConcept" in options

    def test_get_polymorphic_options_observation_effective(self):
        """Should return all options for Observation.effective."""
        options = get_polymorphic_options("Observation", "effective")
        assert "effectiveDateTime" in options
        assert "effectivePeriod" in options

    def test_get_polymorphic_options_patient_deceased(self):
        """Should return all options for Patient.deceased."""
        options = get_polymorphic_options("Patient", "deceased")
        assert "deceasedBoolean" in options
        assert "deceasedDateTime" in options

    def test_get_polymorphic_options_nonexistent(self):
        """Should return empty list for non-existent choice type."""
        options = get_polymorphic_options("Patient", "nonexistent")
        assert options == []

    def test_resolve_polymorphic_field_value_quantity(self):
        """Should resolve to valueQuantity when present."""
        resource = {
            "resourceType": "Observation",
            "valueQuantity": {"value": 100, "unit": "mg"}
        }
        result = resolve_polymorphic_field("Observation", "value", resource)
        assert result == "valueQuantity"

    def test_resolve_polymorphic_field_value_string(self):
        """Should resolve to valueString when present."""
        resource = {
            "resourceType": "Observation",
            "valueString": "Normal"
        }
        result = resolve_polymorphic_field("Observation", "value", resource)
        assert result == "valueString"

    def test_resolve_polymorphic_field_not_present(self):
        """Should return None when no choice type field is present."""
        resource = {
            "resourceType": "Observation",
            "status": "final"
        }
        result = resolve_polymorphic_field("Observation", "value", resource)
        assert result is None

    def test_resolve_polymorphic_field_none_value(self):
        """Should return None when choice field exists but is None."""
        resource = {
            "resourceType": "Observation",
            "valueQuantity": None
        }
        result = resolve_polymorphic_field("Observation", "value", resource)
        assert result is None


class TestIsType:
    """Tests for the is_type function."""

    @pytest.fixture
    def ctx(self):
        """Create a basic evaluation context."""
        return {"model": None}

    def test_is_type_integer(self, ctx):
        """Should return true for integer check on integer."""
        result = is_type(ctx, [42], "integer")
        assert result == [True]

    def test_is_type_string(self, ctx):
        """Should return true for string check on string."""
        result = is_type(ctx, ["hello"], "string")
        assert result == [True]

    def test_is_type_boolean(self, ctx):
        """Should return true for boolean check on boolean."""
        result = is_type(ctx, [True], "boolean")
        assert result == [True]

    def test_is_type_decimal(self, ctx):
        """Should return true for decimal check on float."""
        result = is_type(ctx, [3.14], "decimal")
        assert result == [True]

    def test_is_type_wrong_type(self, ctx):
        """Should return false for wrong type check."""
        result = is_type(ctx, [42], "string")
        assert result == [False]

    def test_is_type_empty_collection(self, ctx):
        """Should return empty list for empty input."""
        result = is_type(ctx, [], "integer")
        assert result == []

    def test_is_type_multiple_items_raises(self, ctx):
        """Should raise error for multiple items."""
        with pytest.raises(ValueError, match="singleton"):
            is_type(ctx, [1, 2, 3], "integer")

    def test_is_type_with_type_info_dict(self, ctx):
        """Should handle type info as dictionary."""
        result = is_type(ctx, [42], {"name": "integer"})
        assert result == [True]


class TestAsType:
    """Tests for the as_type function."""

    @pytest.fixture
    def ctx(self):
        """Create a basic evaluation context."""
        return {"model": None}

    def test_as_type_matching(self, ctx):
        """Should return original collection when type matches."""
        result = as_type(ctx, [42], "integer")
        assert result == [42]

    def test_as_type_not_matching(self, ctx):
        """Should return empty list when type doesn't match."""
        result = as_type(ctx, [42], "string")
        assert result == []

    def test_as_type_empty_collection(self, ctx):
        """Should return empty list for empty input."""
        result = as_type(ctx, [], "integer")
        assert result == []

    def test_as_type_multiple_items_raises(self, ctx):
        """Should raise error for multiple items."""
        with pytest.raises(ValueError, match="singleton"):
            as_type(ctx, [1, 2, 3], "integer")


class TestTypeFn:
    """Tests for the type_fn function."""

    @pytest.fixture
    def ctx(self):
        """Create a basic evaluation context."""
        return {"model": None}

    def test_type_fn_integer(self, ctx):
        """Should return type info for integer (System.Integer)."""
        result = type_fn(ctx, [42])
        assert len(result) == 1
        # System types are capitalized per FHIRPath spec
        assert result[0]["name"] == "Integer"
        assert result[0]["namespace"] == "System"

    def test_type_fn_string(self, ctx):
        """Should return type info for string (System.String)."""
        result = type_fn(ctx, ["hello"])
        assert len(result) == 1
        assert result[0]["name"] == "String"
        assert result[0]["namespace"] == "System"

    def test_type_fn_boolean(self, ctx):
        """Should return type info for boolean (System.Boolean)."""
        result = type_fn(ctx, [True])
        assert len(result) == 1
        assert result[0]["name"] == "Boolean"
        assert result[0]["namespace"] == "System"

    def test_type_fn_empty_collection(self, ctx):
        """Should return empty list for empty input."""
        result = type_fn(ctx, [])
        assert result == []

    def test_type_fn_multiple_items(self, ctx):
        """Should return type info for each item."""
        result = type_fn(ctx, [42, "hello", True])
        assert len(result) == 3
        assert result[0]["name"] == "Integer"
        assert result[1]["name"] == "String"
        assert result[2]["name"] == "Boolean"


class TestTypeInferenceEdgeCases:
    """Tests for edge cases in type inference."""

    def test_infer_empty_dict(self):
        """Should handle empty dictionary."""
        result = get_fhir_type({})
        # Empty dict doesn't match any specific type
        assert result == "object"

    def test_infer_list_with_different_types(self):
        """Should identify list as Collection regardless of content."""
        assert get_fhir_type([1, "two", True]) == "Collection"

    def test_infer_quantity_without_unit(self):
        """Should not identify as Quantity without both value and unit."""
        value = {"value": 100}
        # Only value, not Quantity
        assert get_fhir_type(value) != "Quantity"

    def test_infer_coding_minimal(self):
        """Should identify Coding with just system and code."""
        value = {"system": "http://example.org", "code": "test"}
        assert get_fhir_type(value) == "Coding"

    def test_infer_codeable_concept_with_text_only(self):
        """CodeableConcept needs coding to be identified."""
        value = {"text": "Some text"}
        # Without coding, not identified as CodeableConcept
        assert get_fhir_type(value) != "CodeableConcept"

    def test_infer_reference_with_display_only(self):
        """Reference needs 'reference' field to be identified."""
        value = {"display": "John Doe"}
        # Without reference, not identified as Reference
        assert get_fhir_type(value) != "Reference"
