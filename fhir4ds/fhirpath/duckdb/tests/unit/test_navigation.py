"""
Unit tests for FHIRPath navigation.

Tests basic path navigation functionality including:
- Simple path access
- Nested path navigation
- Array traversal
- Empty collection handling
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ...evaluator import FHIRPathEvaluator
from ...collection import FHIRPathCollection, wrap_as_collection


# Load test fixtures
FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"


@pytest.fixture
def patient_resource() -> dict:
    """Load the sample Patient resource."""
    with open(FIXTURES_DIR / "patient.json") as f:
        return json.load(f)


@pytest.fixture
def observation_resource() -> dict:
    """Load the sample Observation resource."""
    with open(FIXTURES_DIR / "observation.json") as f:
        return json.load(f)


@pytest.fixture
def evaluator() -> FHIRPathEvaluator:
    """Create a FHIRPath evaluator."""
    return FHIRPathEvaluator()


class TestSimpleNavigation:
    """Tests for simple path navigation."""

    def test_access_id(self, evaluator: FHIRPathEvaluator, patient_resource: dict) -> None:
        """Test accessing the id field."""
        result = evaluator.evaluate_expression(patient_resource, "id")
        assert result == ["example-patient-1"]

    def test_access_resource_type(self, evaluator: FHIRPathEvaluator, patient_resource: dict) -> None:
        """Test accessing resourceType."""
        result = evaluator.evaluate_expression(patient_resource, "resourceType")
        assert result == ["Patient"]

    def test_access_gender(self, evaluator: FHIRPathEvaluator, patient_resource: dict) -> None:
        """Test accessing gender field."""
        result = evaluator.evaluate_expression(patient_resource, "gender")
        assert result == ["male"]

    def test_access_birth_date(self, evaluator: FHIRPathEvaluator, patient_resource: dict) -> None:
        """Test accessing birthDate."""
        result = evaluator.evaluate_expression(patient_resource, "birthDate")
        assert result == ["1985-06-15"]

    def test_access_boolean(self, evaluator: FHIRPathEvaluator, patient_resource: dict) -> None:
        """Test accessing boolean field."""
        result = evaluator.evaluate_expression(patient_resource, "active")
        assert result == [True]

    def test_access_integer(self, evaluator: FHIRPathEvaluator, patient_resource: dict) -> None:
        """Test accessing integer field."""
        result = evaluator.evaluate_expression(patient_resource, "multipleBirthInteger")
        assert result == [1]

    def test_access_missing_field(self, evaluator: FHIRPathEvaluator, patient_resource: dict) -> None:
        """Test accessing a non-existent field returns empty collection."""
        result = evaluator.evaluate_expression(patient_resource, "nonExistentField")
        assert result == []


class TestNestedNavigation:
    """Tests for nested path navigation."""

    def test_access_nested_field(self, evaluator: FHIRPathEvaluator, patient_resource: dict) -> None:
        """Test accessing a nested field."""
        result = evaluator.evaluate_expression(patient_resource, "meta.versionId")
        assert result == ["1"]

    def test_access_deeply_nested(self, evaluator: FHIRPathEvaluator, observation_resource: dict) -> None:
        """Test accessing deeply nested fields."""
        result = evaluator.evaluate_expression(observation_resource, "subject.reference")
        assert result == ["Patient/example-patient-1"]

    def test_access_nested_in_array(self, evaluator: FHIRPathEvaluator, patient_resource: dict) -> None:
        """Test accessing fields within array elements."""
        result = evaluator.evaluate_expression(patient_resource, "name.given")
        # Should flatten across all name elements
        assert "John" in result
        assert "Adam" in result

    def test_access_nested_coding(self, evaluator: FHIRPathEvaluator, patient_resource: dict) -> None:
        """Test accessing coding within identifier."""
        result = evaluator.evaluate_expression(patient_resource, "identifier.type.coding.code")
        assert "MR" in result


class TestArrayTraversal:
    """Tests for array traversal."""

    def test_access_array(self, evaluator: FHIRPathEvaluator, patient_resource: dict) -> None:
        """Test accessing an array field."""
        result = evaluator.evaluate_expression(patient_resource, "name")
        assert len(result) == 2  # Two name elements

    def test_access_array_element_field(self, evaluator: FHIRPathEvaluator, patient_resource: dict) -> None:
        """Test accessing a field from array elements."""
        result = evaluator.evaluate_expression(patient_resource, "name.family")
        assert "Smith" in result

    def test_telecom_systems(self, evaluator: FHIRPathEvaluator, patient_resource: dict) -> None:
        """Test getting all telecom systems."""
        result = evaluator.evaluate_expression(patient_resource, "telecom.system")
        assert "phone" in result
        assert "email" in result

    def test_address_lines(self, evaluator: FHIRPathEvaluator, patient_resource: dict) -> None:
        """Test accessing nested array (line within address)."""
        result = evaluator.evaluate_expression(patient_resource, "address.line")
        assert "123 Main Street" in result
        assert "Apt 4B" in result


class TestResourceTypePrefix:
    """Tests for resource type prefix handling."""

    def test_with_resource_type_prefix(self, evaluator: FHIRPathEvaluator, patient_resource: dict) -> None:
        """Test path with resource type prefix."""
        result = evaluator.evaluate_expression(patient_resource, "Patient.id")
        assert result == ["example-patient-1"]

    def test_with_nested_resource_type_prefix(self, evaluator: FHIRPathEvaluator, patient_resource: dict) -> None:
        """Test nested path with resource type prefix."""
        result = evaluator.evaluate_expression(patient_resource, "Patient.name.given")
        assert "John" in result


class TestCollectionSemantics:
    """Tests for FHIRPath collection semantics."""

    def test_empty_collection(self, evaluator: FHIRPathEvaluator) -> None:
        """Test empty resource returns empty collection."""
        result = evaluator.evaluate_expression({}, "id")
        assert result == []

    def test_single_element_as_list(self, evaluator: FHIRPathEvaluator, patient_resource: dict) -> None:
        """Test that single elements are returned as single-item lists."""
        result = evaluator.evaluate_expression(patient_resource, "gender")
        assert result == ["male"]
        assert len(result) == 1


class TestFHIRPathCollection:
    """Tests for the FHIRPathCollection class."""

    def test_empty_collection(self) -> None:
        """Test creating empty collection."""
        col = FHIRPathCollection([])
        assert col.is_empty
        assert len(col) == 0

    def test_singleton_collection(self) -> None:
        """Test singleton collection."""
        col = FHIRPathCollection(["single"])
        assert col.is_singleton
        assert col.singleton_value == "single"

    def test_multi_element_collection(self) -> None:
        """Test multi-element collection."""
        col = FHIRPathCollection([1, 2, 3])
        assert not col.is_empty
        assert not col.is_singleton
        assert len(col) == 3

    def test_collection_iteration(self) -> None:
        """Test iterating over collection."""
        col = FHIRPathCollection([1, 2, 3])
        items = list(col)
        assert items == [1, 2, 3]

    def test_collection_first_last(self) -> None:
        """Test first() and last() methods."""
        col = FHIRPathCollection([1, 2, 3])
        assert col.first() == 1
        assert col.last() == 3

    def test_collection_where(self) -> None:
        """Test filtering with where()."""
        col = FHIRPathCollection([1, 2, 3, 4, 5])
        filtered = col.where(lambda x: x > 2)
        assert filtered.to_list() == [3, 4, 5]

    def test_collection_map(self) -> None:
        """Test mapping with select()."""
        col = FHIRPathCollection([1, 2, 3])
        mapped = col.select(lambda x: x * 2)
        assert mapped.to_list() == [2, 4, 6]

    def test_wrap_as_collection(self) -> None:
        """Test wrap_as_collection helper."""
        # Single value
        col1 = wrap_as_collection("single")
        assert col1.is_singleton
        assert col1.singleton_value == "single"

        # List value
        col2 = wrap_as_collection([1, 2, 3])
        assert len(col2) == 3

        # None value
        col3 = wrap_as_collection(None)
        assert col3.is_empty

        # Existing collection
        original = FHIRPathCollection([1, 2])
        col4 = wrap_as_collection(original)
        assert col4.to_list() == [1, 2]
