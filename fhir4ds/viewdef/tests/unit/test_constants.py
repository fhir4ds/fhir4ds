"""Unit tests for constant resolution.

Tests the resolution of constants defined in ViewDefinitions
into SQL values, including simple values, Codings, and
CodeableConcepts.
"""

import pytest

from ...types import Constant
from ...constants import (
    resolve_constant,
    resolve_constants_in_path,
    ConstantResolver,
)


class TestResolveConstant:
    """Tests for constant value resolution."""

    def test_resolve_string_constant(self):
        """Test resolving a string constant."""
        const = Constant(name="TestValue", value="test", value_type="string")
        result = resolve_constant(const)

        assert result == "'test'"

    def test_resolve_code_constant(self):
        """Test resolving a code constant."""
        const = Constant(name="StatusCode", value="active", value_type="code")
        result = resolve_constant(const)

        assert result == "'active'"

    def test_resolve_integer_constant(self):
        """Test resolving an integer constant."""
        const = Constant(name="MaxCount", value=10, value_type="integer")
        result = resolve_constant(const)

        assert result == "10"

    def test_resolve_decimal_constant(self):
        """Test resolving a decimal constant."""
        const = Constant(name="Ratio", value=3.14, value_type="decimal")
        result = resolve_constant(const)

        assert result == "3.14"

    def test_resolve_boolean_true_constant(self):
        """Test resolving a boolean true constant."""
        const = Constant(name="IsActive", value=True, value_type="boolean")
        result = resolve_constant(const)

        assert result == "true"

    def test_resolve_boolean_false_constant(self):
        """Test resolving a boolean false constant."""
        const = Constant(name="IsInactive", value=False, value_type="boolean")
        result = resolve_constant(const)

        assert result == "false"

    def test_resolve_null_constant(self):
        """Test resolving a null constant."""
        const = Constant(name="NullValue", value=None, value_type=None)
        result = resolve_constant(const)

        assert result == "null"


class TestResolveCodingConstant:
    """Tests for Coding constant resolution."""

    def test_resolve_simple_coding(self):
        """Test resolving a simple Coding constant."""
        coding = {
            "system": "http://hl7.org/fhir/gender-identity",
            "code": "female"
        }
        const = Constant(name="FemaleCoding", value=coding, value_type="Coding")
        result = resolve_constant(const)

        assert "Coding{" in result
        assert "system: 'http://hl7.org/fhir/gender-identity'" in result
        assert "code: 'female'" in result

    def test_resolve_coding_with_display(self):
        """Test resolving a Coding with display."""
        coding = {
            "system": "http://snomed.info/sct",
            "code": "73211009",
            "display": "Diabetes mellitus"
        }
        const = Constant(name="DiabetesCode", value=coding, value_type="Coding")
        result = resolve_constant(const)

        assert "Coding{" in result
        assert "display: 'Diabetes mellitus'" in result

    def test_resolve_coding_escapes_quotes(self):
        """Test that quotes in Coding values are escaped."""
        coding = {
            "system": "http://example.org",
            "code": "test's code"
        }
        const = Constant(name="EscapedCoding", value=coding, value_type="Coding")
        result = resolve_constant(const)

        # Single quotes should be doubled
        assert "test''s code" in result


class TestResolveCodeableConceptConstant:
    """Tests for CodeableConcept constant resolution."""

    def test_resolve_simple_codeable_concept(self):
        """Test resolving a simple CodeableConcept."""
        concept = {
            "coding": [
                {"system": "http://snomed.info/sct", "code": "73211009"}
            ]
        }
        const = Constant(name="DiabetesConcept", value=concept, value_type="CodeableConcept")
        result = resolve_constant(const)

        assert "CodeableConcept{" in result
        assert "coding: [" in result
        assert "Coding{" in result

    def test_resolve_codeable_concept_with_text(self):
        """Test resolving a CodeableConcept with text."""
        concept = {
            "coding": [
                {"system": "http://loinc.org", "code": "718-7"}
            ],
            "text": "Hemoglobin"
        }
        const = Constant(name="HemoglobinConcept", value=concept, value_type="CodeableConcept")
        result = resolve_constant(const)

        assert "text: 'Hemoglobin'" in result

    def test_resolve_codeable_concept_multiple_codings(self):
        """Test resolving a CodeableConcept with multiple codings."""
        concept = {
            "coding": [
                {"system": "http://snomed.info/sct", "code": "73211009"},
                {"system": "http://icd.codes", "code": "E11"}
            ]
        }
        const = Constant(name="MultiCodingConcept", value=concept, value_type="CodeableConcept")
        result = resolve_constant(const)

        assert result.count("Coding{") == 2


class TestResolveConstantsInPath:
    """Tests for resolving constants in FHIRPath expressions."""

    def test_resolve_single_constant(self):
        """Test resolving a single constant reference."""
        constants = {
            "Female": Constant(name="Female", value="female", value_type="code")
        }
        result = resolve_constants_in_path("gender = %Female", constants)

        assert result == "gender = 'female'"

    def test_resolve_multiple_constants(self):
        """Test resolving multiple constant references."""
        constants = {
            "Female": Constant(name="Female", value="female", value_type="code"),
            "Active": Constant(name="Active", value="active", value_type="code")
        }
        result = resolve_constants_in_path("gender = %Female and status = %Active", constants)

        assert result == "gender = 'female' and status = 'active'"

    def test_unknown_constant_left_as_is(self):
        """Test that unknown constant references are left unchanged."""
        constants = {}
        result = resolve_constants_in_path("value = %UnknownConstant", constants)

        assert result == "value = %UnknownConstant"

    def test_constant_in_function_call(self):
        """Test resolving constant in function call."""
        constants = {
            "HomeSystem": Constant(name="HomeSystem", value="http://home.org", value_type="string")
        }
        result = resolve_constants_in_path("telecom.where(system = %HomeSystem)", constants)

        assert "'http://home.org'" in result


class TestConstantResolver:
    """Tests for ConstantResolver class."""

    def test_initialization_empty(self):
        """Test initializing empty resolver."""
        resolver = ConstantResolver()

        assert len(resolver) == 0
        assert resolver.constants == {}

    def test_initialization_with_constants(self):
        """Test initializing resolver with constants."""
        constants = {
            "Test": Constant(name="Test", value="value", value_type="string")
        }
        resolver = ConstantResolver(constants)

        assert len(resolver) == 1
        assert "Test" in resolver

    def test_from_list_with_dict(self):
        """Test creating resolver from list of dicts."""
        constants_list = [
            {"name": "Female", "valueCode": "female"},
            {"name": "Male", "valueCode": "male"}
        ]
        resolver = ConstantResolver.from_list(constants_list)

        assert len(resolver) == 2
        assert "Female" in resolver
        assert "Male" in resolver

    def test_from_list_with_constant_objects(self):
        """Test creating resolver from list of Constant objects."""
        constants_list = [
            Constant(name="Active", value="active", value_type="code")
        ]
        resolver = ConstantResolver.from_list(constants_list)

        assert len(resolver) == 1
        assert resolver.has_constant("Active")

    def test_add_constant(self):
        """Test adding a constant."""
        resolver = ConstantResolver()
        const = Constant(name="New", value="value", value_type="string")

        resolver.add_constant(const)

        assert len(resolver) == 1
        assert resolver.get_constant("New") == const

    def test_add_from_dict(self):
        """Test adding a constant from dict."""
        resolver = ConstantResolver()

        resolver.add_from_dict({"name": "Test", "valueString": "test_value"})

        assert len(resolver) == 1
        assert resolver.has_constant("Test")

    def test_get_constant(self):
        """Test getting a constant by name."""
        const = Constant(name="Test", value="value", value_type="string")
        resolver = ConstantResolver({"Test": const})

        result = resolver.get_constant("Test")
        assert result == const

        result = resolver.get_constant("Nonexistent")
        assert result is None

    def test_resolve(self):
        """Test resolving a constant by name."""
        const = Constant(name="Test", value="test_value", value_type="string")
        resolver = ConstantResolver({"Test": const})

        result = resolver.resolve("Test")
        assert result == "'test_value'"

    def test_resolve_nonexistent_raises(self):
        """Test resolving nonexistent constant raises KeyError."""
        resolver = ConstantResolver()

        with pytest.raises(KeyError):
            resolver.resolve("Nonexistent")

    def test_resolve_in_path(self):
        """Test resolving constants in a path."""
        resolver = ConstantResolver.from_list([
            {"name": "Female", "valueCode": "female"}
        ])

        result = resolver.resolve_in_path("gender = %Female")
        assert result == "gender = 'female'"

    def test_has_constant(self):
        """Test checking if constant exists."""
        const = Constant(name="Test", value="value", value_type="string")
        resolver = ConstantResolver({"Test": const})

        assert resolver.has_constant("Test") is True
        assert resolver.has_constant("Nonexistent") is False

    def test_contains_operator(self):
        """Test 'in' operator."""
        const = Constant(name="Test", value="value", value_type="string")
        resolver = ConstantResolver({"Test": const})

        assert "Test" in resolver
        assert "Nonexistent" not in resolver

    def test_len(self):
        """Test len() returns count of constants."""
        resolver = ConstantResolver.from_list([
            {"name": "A", "valueCode": "a"},
            {"name": "B", "valueCode": "b"},
            {"name": "C", "valueCode": "c"}
        ])

        assert len(resolver) == 3

    def test_repr(self):
        """Test string representation."""
        resolver = ConstantResolver.from_list([
            {"name": "A", "valueCode": "a"}
        ])

        repr_str = repr(resolver)
        assert "ConstantResolver" in repr_str
        assert "1" in repr_str


class TestEdgeCases:
    """Tests for edge cases in constant resolution."""

    def test_empty_string_value(self):
        """Test resolving empty string."""
        const = Constant(name="Empty", value="", value_type="string")
        result = resolve_constant(const)

        assert result == "''"

    def test_value_with_special_sql_chars(self):
        """Test value with characters that need SQL escaping."""
        const = Constant(name="Special", value="it's a test", value_type="string")
        result = resolve_constant(const)

        # Single quote should be doubled
        assert "it''s a test" in result

    def test_zero_integer(self):
        """Test resolving zero."""
        const = Constant(name="Zero", value=0, value_type="integer")
        result = resolve_constant(const)

        assert result == "0"

    def test_negative_number(self):
        """Test resolving negative number."""
        const = Constant(name="Negative", value=-5.5, value_type="decimal")
        result = resolve_constant(const)

        assert result == "-5.5"

    def test_constant_name_with_underscore(self):
        """Test constant name with underscore."""
        constants = {
            "My_Constant": Constant(name="My_Constant", value="value", value_type="string")
        }
        result = resolve_constants_in_path("test = %My_Constant", constants)

        assert result == "test = 'value'"

    def test_constant_name_with_numbers(self):
        """Test constant name with numbers."""
        constants = {
            "Code1": Constant(name="Code1", value="value1", value_type="string")
        }
        result = resolve_constants_in_path("test = %Code1", constants)

        assert result == "test = 'value1'"
