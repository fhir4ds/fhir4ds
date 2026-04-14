"""
Unit tests for FHIRPath hasValue() and getValue() Functions.

Tests the value functions including:
- hasValue() - returns true if collection has a single non-null value
- getValue() - returns the value if hasValue() is true, else empty

These functions work with FHIR primitive types that can have extensions.
"""

from __future__ import annotations

import pytest

from ...import evaluate


class TestHasValue:
    """Tests for the hasValue() function."""

    def test_empty_collection_returns_false(self) -> None:
        """{}.hasValue() -> false - testing with missing field (empty result)"""
        # Note: At root level, the context is the resource itself (a dict),
        # not an empty collection. Testing with missing field instead.
        result = evaluate({}, "nonexistent.hasValue()")
        assert result == [False]

    def test_collection_with_single_value_returns_true(self) -> None:
        """[5].hasValue() -> true"""
        result = evaluate({"value": 5}, "value.hasValue()")
        assert result == [True]

    def test_collection_with_single_string_returns_true(self) -> None:
        """['test'].hasValue() -> true"""
        result = evaluate({"name": "test"}, "name.hasValue()")
        assert result == [True]

    def test_multi_item_collection_returns_false(self) -> None:
        """[1, 2].hasValue() -> false (more than one item)"""
        result = evaluate({"items": [1, 2]}, "items.hasValue()")
        assert result == [False]

    def test_null_value_returns_false(self) -> None:
        """null value returns false"""
        result = evaluate({"value": None}, "value.hasValue()")
        assert result == [False]

    def test_boolean_true_has_value(self) -> None:
        """true.hasValue() -> true"""
        result = evaluate({"active": True}, "active.hasValue()")
        assert result == [True]

    def test_boolean_false_has_value(self) -> None:
        """false.hasValue() -> true (false is still a value)"""
        result = evaluate({"active": False}, "active.hasValue()")
        assert result == [True]

    def test_empty_string_has_value(self) -> None:
        """''.hasValue() -> true (empty string is still a value)"""
        result = evaluate({"name": ""}, "name.hasValue()")
        assert result == [True]

    def test_integer_zero_has_value(self) -> None:
        """0.hasValue() -> true (zero is still a value)"""
        result = evaluate({"count": 0}, "count.hasValue()")
        assert result == [True]

    def test_chaining_has_value(self) -> None:
        """Test chaining with where()"""
        result = evaluate(
            {"items": [{"val": 1}, {"val": 2}]},
            "items.where(val = 1).val.hasValue()"
        )
        assert result == [True]


class TestGetValue:
    """Tests for the getValue() function."""

    def test_empty_collection_returns_empty(self) -> None:
        """{}.getValue() -> {} - testing with missing field (empty result)"""
        # Note: At root level, the context is the resource itself (a dict),
        # not an empty collection. Testing with missing field instead.
        result = evaluate({}, "nonexistent.getValue()")
        assert result == []

    def test_single_value_returns_value(self) -> None:
        """[5].getValue() -> 5"""
        result = evaluate({"value": 5}, "value.getValue()")
        assert result == [5]

    def test_single_string_returns_value(self) -> None:
        """['test'].getValue() -> 'test'"""
        result = evaluate({"name": "test"}, "name.getValue()")
        assert result == ["test"]

    def test_multi_item_collection_returns_empty(self) -> None:
        """[1, 2].getValue() -> {} (more than one item)"""
        result = evaluate({"items": [1, 2]}, "items.getValue()")
        assert result == []

    def test_null_value_returns_empty(self) -> None:
        """null.getValue() -> {}"""
        result = evaluate({"value": None}, "value.getValue()")
        assert result == []

    def test_boolean_true_get_value(self) -> None:
        """true.getValue() -> true"""
        result = evaluate({"active": True}, "active.getValue()")
        assert result == [True]

    def test_boolean_false_get_value(self) -> None:
        """false.getValue() -> false"""
        result = evaluate({"active": False}, "active.getValue()")
        assert result == [False]

    def test_integer_zero_get_value(self) -> None:
        """0.getValue() -> 0"""
        result = evaluate({"count": 0}, "count.getValue()")
        assert result == [0]

    def test_empty_string_get_value(self) -> None:
        """''.getValue() -> ''"""
        result = evaluate({"name": ""}, "name.getValue()")
        assert result == [""]

    def test_chaining_get_value(self) -> None:
        """Test chaining with where()"""
        result = evaluate(
            {"items": [{"val": 42}]},
            "items.where(val = 42).val.getValue()"
        )
        assert result == [42]


class TestHasValueGetValueRelationship:
    """Tests verifying the relationship between hasValue() and getValue()."""

    def test_has_value_true_means_get_value_returns_value(self) -> None:
        """If hasValue() is true, getValue() returns a value."""
        data = {"value": "test"}
        has_val = evaluate(data, "value.hasValue()")
        get_val = evaluate(data, "value.getValue()")
        assert has_val == [True]
        assert get_val == ["test"]

    def test_has_value_false_means_get_value_empty(self) -> None:
        """If hasValue() is false, getValue() returns empty."""
        # Empty collection from missing field
        has_val = evaluate({}, "nonexistent.hasValue()")
        get_val = evaluate({}, "nonexistent.getValue()")
        assert has_val == [False]
        assert get_val == []

    def test_null_value_both_consistent(self) -> None:
        """null value: hasValue() -> false, getValue() -> {}"""
        data = {"value": None}
        has_val = evaluate(data, "value.hasValue()")
        get_val = evaluate(data, "value.getValue()")
        assert has_val == [False]
        assert get_val == []

    def test_conditional_get_value(self) -> None:
        """Test using hasValue() in conditional with iif()"""
        result = evaluate(
            {"value": 10},
            "iif(value.hasValue(), value.getValue(), 0)"
        )
        assert result == [10]

    def test_conditional_get_value_with_null(self) -> None:
        """Test using hasValue() with null value"""
        result = evaluate(
            {"value": None},
            "iif(value.hasValue(), value.getValue(), 'default')"
        )
        assert result == ["default"]


class TestEdgeCases:
    """Tests for edge cases and special scenarios."""

    def test_nested_object_has_value(self) -> None:
        """Test hasValue() on nested object field."""
        data = {"person": {"name": "John"}}
        result = evaluate(data, "person.name.hasValue()")
        assert result == [True]

    def test_nested_object_get_value(self) -> None:
        """Test getValue() on nested object field."""
        data = {"person": {"name": "John"}}
        result = evaluate(data, "person.name.getValue()")
        assert result == ["John"]

    def test_missing_field_has_value(self) -> None:
        """Test hasValue() on missing field returns false."""
        result = evaluate({}, "missingField.hasValue()")
        assert result == [False]

    def test_missing_field_get_value(self) -> None:
        """Test getValue() on missing field returns empty."""
        result = evaluate({}, "missingField.getValue()")
        assert result == []

    def test_float_value(self) -> None:
        """Test with float value (converted to Decimal by FHIRPath)."""
        from decimal import Decimal
        data = {"value": 3.14}
        assert evaluate(data, "value.hasValue()") == [True]
        result = evaluate(data, "value.getValue()")
        # Float values are converted to Decimal in FHIRPath
        assert result == [Decimal('3.14')]

    def test_negative_value(self) -> None:
        """Test with negative value."""
        data = {"value": -42}
        assert evaluate(data, "value.hasValue()") == [True]
        assert evaluate(data, "value.getValue()") == [-42]
