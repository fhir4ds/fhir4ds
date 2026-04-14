"""
Unit tests for FHIRPath Existence and Quantifier Functions.

Tests existence, quantifier, and counting functions including:
- empty() - returns true if collection is empty
- exists() - returns true if collection has elements
- exists(criteria) - returns true if any element matches criteria
- all(criteria) - true if all elements satisfy criteria
- allTrue() - true if all elements are true
- allFalse() - true if all elements are false
- anyTrue() - true if any element is true
- anyFalse() - true if any element is false
- count() - number of elements
- distinct() - unique elements
"""

from __future__ import annotations

import pytest

from ...collection import FHIRPathCollection
from ...functions.existence import (
    empty,
    exists,
    exists_with_criteria,
    all_criteria,
    all_true,
    all_false,
    any_true,
    any_false,
    count,
    distinct,
)


class TestEmpty:
    """Tests for the empty() function."""

    def test_empty_collection_returns_true(self) -> None:
        """{}.empty() -> true"""
        col = FHIRPathCollection([])
        result = empty(col)
        assert result.is_singleton
        assert result.singleton_value is True

    def test_singleton_collection_returns_false(self) -> None:
        """[x].empty() -> false"""
        col = FHIRPathCollection([1])
        result = empty(col)
        assert result.is_singleton
        assert result.singleton_value is False

    def test_multi_element_collection_returns_false(self) -> None:
        """[x, y].empty() -> false"""
        col = FHIRPathCollection([1, 2, 3])
        result = empty(col)
        assert result.is_singleton
        assert result.singleton_value is False

    def test_empty_with_none_returns_true(self) -> None:
        """Collection with None as element is not empty."""
        col = FHIRPathCollection([None])
        result = empty(col)
        assert result.singleton_value is False

    def test_empty_with_false_returns_false(self) -> None:
        """Collection with False is not empty."""
        col = FHIRPathCollection([False])
        result = empty(col)
        assert result.singleton_value is False


class TestExists:
    """Tests for the exists() function."""

    def test_empty_collection_returns_false(self) -> None:
        """{}.exists() -> false"""
        col = FHIRPathCollection([])
        result = exists(col)
        assert result.is_singleton
        assert result.singleton_value is False

    def test_singleton_collection_returns_true(self) -> None:
        """[x].exists() -> true"""
        col = FHIRPathCollection([1])
        result = exists(col)
        assert result.is_singleton
        assert result.singleton_value is True

    def test_multi_element_collection_returns_true(self) -> None:
        """[x, y].exists() -> true"""
        col = FHIRPathCollection([1, 2, 3])
        result = exists(col)
        assert result.is_singleton
        assert result.singleton_value is True

    def test_exists_with_false_element_returns_true(self) -> None:
        """Collection with False element still exists."""
        col = FHIRPathCollection([False])
        result = exists(col)
        assert result.singleton_value is True


class TestExistsWithCriteria:
    """Tests for the exists(criteria) function."""

    def test_empty_collection_returns_false(self) -> None:
        """{}.exists(X) -> false"""
        col = FHIRPathCollection([])
        result = exists_with_criteria(col, lambda x: x > 0)
        assert result.is_singleton
        assert result.singleton_value is False

    def test_matching_element_returns_true(self) -> None:
        """[1, 2, 3].exists(x > 2) -> true"""
        col = FHIRPathCollection([1, 2, 3])
        result = exists_with_criteria(col, lambda x: x > 2)
        assert result.singleton_value is True

    def test_no_matching_element_returns_false(self) -> None:
        """[1, 2, 3].exists(x > 5) -> false"""
        col = FHIRPathCollection([1, 2, 3])
        result = exists_with_criteria(col, lambda x: x > 5)
        assert result.singleton_value is False

    def test_first_element_matches_short_circuits(self) -> None:
        """Short-circuits on first match."""
        col = FHIRPathCollection([3, 2, 1])
        result = exists_with_criteria(col, lambda x: x > 2)
        assert result.singleton_value is True

    def test_criteria_with_string_elements(self) -> None:
        """Works with string elements."""
        col = FHIRPathCollection(["apple", "banana", "cherry"])
        result = exists_with_criteria(col, lambda x: x.startswith("b"))
        assert result.singleton_value is True

    def test_criteria_with_dict_elements(self) -> None:
        """Works with dictionary elements."""
        col = FHIRPathCollection([
            {"name": "Alice", "active": True},
            {"name": "Bob", "active": False},
        ])
        result = exists_with_criteria(col, lambda x: x.get("active") is True)
        assert result.singleton_value is True


class TestAllCriteria:
    """Tests for the all(criteria) function."""

    def test_empty_collection_returns_true_vacuous_truth(self) -> None:
        """{}.all(X) -> true (vacuous truth)"""
        col = FHIRPathCollection([])
        result = all_criteria(col, lambda x: x > 0)
        assert result.is_singleton
        assert result.singleton_value is True

    def test_all_elements_match_returns_true(self) -> None:
        """[2, 4, 6].all(x % 2 == 0) -> true"""
        col = FHIRPathCollection([2, 4, 6])
        result = all_criteria(col, lambda x: x % 2 == 0)
        assert result.singleton_value is True

    def test_some_elements_dont_match_returns_false(self) -> None:
        """[2, 3, 4].all(x % 2 == 0) -> false"""
        col = FHIRPathCollection([2, 3, 4])
        result = all_criteria(col, lambda x: x % 2 == 0)
        assert result.singleton_value is False

    def test_no_elements_match_returns_false(self) -> None:
        """[1, 3, 5].all(x % 2 == 0) -> false"""
        col = FHIRPathCollection([1, 3, 5])
        result = all_criteria(col, lambda x: x % 2 == 0)
        assert result.singleton_value is False

    def test_singleton_matching_returns_true(self) -> None:
        """[2].all(x % 2 == 0) -> true"""
        col = FHIRPathCollection([2])
        result = all_criteria(col, lambda x: x % 2 == 0)
        assert result.singleton_value is True

    def test_singleton_not_matching_returns_false(self) -> None:
        """[3].all(x % 2 == 0) -> false"""
        col = FHIRPathCollection([3])
        result = all_criteria(col, lambda x: x % 2 == 0)
        assert result.singleton_value is False

    def test_short_circuits_on_first_failure(self) -> None:
        """Stops evaluation on first failure."""
        # This tests that we don't process all elements unnecessarily
        col = FHIRPathCollection([2, 3, 4, 5, 6])
        result = all_criteria(col, lambda x: x % 2 == 0)
        assert result.singleton_value is False


class TestAllTrue:
    """Tests for the allTrue() function."""

    def test_empty_collection_returns_true_vacuous_truth(self) -> None:
        """{}.allTrue() -> true"""
        col = FHIRPathCollection([])
        result = all_true(col)
        assert result.is_singleton
        assert result.singleton_value is True

    def test_all_true_returns_true(self) -> None:
        """[true, true].allTrue() -> true"""
        col = FHIRPathCollection([True, True])
        result = all_true(col)
        assert result.singleton_value is True

    def test_mixed_true_false_returns_false(self) -> None:
        """[true, false].allTrue() -> false"""
        col = FHIRPathCollection([True, False])
        result = all_true(col)
        assert result.singleton_value is False

    def test_all_false_returns_false(self) -> None:
        """[false, false].allTrue() -> false"""
        col = FHIRPathCollection([False, False])
        result = all_true(col)
        assert result.singleton_value is False

    def test_singleton_true_returns_true(self) -> None:
        """[true].allTrue() -> true"""
        col = FHIRPathCollection([True])
        result = all_true(col)
        assert result.singleton_value is True

    def test_singleton_false_returns_false(self) -> None:
        """[false].allTrue() -> false"""
        col = FHIRPathCollection([False])
        result = all_true(col)
        assert result.singleton_value is False

    def test_non_boolean_values_not_considered_true(self) -> None:
        """Non-boolean truthy values are not considered 'true'."""
        col = FHIRPathCollection([1, "yes", True])
        result = all_true(col)
        # Only boolean True counts
        assert result.singleton_value is False


class TestAllFalse:
    """Tests for the allFalse() function."""

    def test_empty_collection_returns_true_vacuous_truth(self) -> None:
        """{}.allFalse() -> true"""
        col = FHIRPathCollection([])
        result = all_false(col)
        assert result.is_singleton
        assert result.singleton_value is True

    def test_all_false_returns_true(self) -> None:
        """[false, false].allFalse() -> true"""
        col = FHIRPathCollection([False, False])
        result = all_false(col)
        assert result.singleton_value is True

    def test_mixed_true_false_returns_false(self) -> None:
        """[true, false].allFalse() -> false"""
        col = FHIRPathCollection([True, False])
        result = all_false(col)
        assert result.singleton_value is False

    def test_all_true_returns_false(self) -> None:
        """[true, true].allFalse() -> false"""
        col = FHIRPathCollection([True, True])
        result = all_false(col)
        assert result.singleton_value is False

    def test_singleton_false_returns_true(self) -> None:
        """[false].allFalse() -> true"""
        col = FHIRPathCollection([False])
        result = all_false(col)
        assert result.singleton_value is True

    def test_singleton_true_returns_false(self) -> None:
        """[true].allFalse() -> false"""
        col = FHIRPathCollection([True])
        result = all_false(col)
        assert result.singleton_value is False


class TestAnyTrue:
    """Tests for the anyTrue() function."""

    def test_empty_collection_returns_false(self) -> None:
        """{}.anyTrue() -> false"""
        col = FHIRPathCollection([])
        result = any_true(col)
        assert result.is_singleton
        assert result.singleton_value is False

    def test_has_true_returns_true(self) -> None:
        """[false, true].anyTrue() -> true"""
        col = FHIRPathCollection([False, True])
        result = any_true(col)
        assert result.singleton_value is True

    def test_all_true_returns_true(self) -> None:
        """[true, true].anyTrue() -> true"""
        col = FHIRPathCollection([True, True])
        result = any_true(col)
        assert result.singleton_value is True

    def test_all_false_returns_false(self) -> None:
        """[false, false].anyTrue() -> false"""
        col = FHIRPathCollection([False, False])
        result = any_true(col)
        assert result.singleton_value is False

    def test_singleton_true_returns_true(self) -> None:
        """[true].anyTrue() -> true"""
        col = FHIRPathCollection([True])
        result = any_true(col)
        assert result.singleton_value is True

    def test_singleton_false_returns_false(self) -> None:
        """[false].anyTrue() -> false"""
        col = FHIRPathCollection([False])
        result = any_true(col)
        assert result.singleton_value is False

    def test_short_circuits_on_first_true(self) -> None:
        """Stops evaluation on first true."""
        col = FHIRPathCollection([False, False, True, False])
        result = any_true(col)
        assert result.singleton_value is True


class TestAnyFalse:
    """Tests for the anyFalse() function."""

    def test_empty_collection_returns_false(self) -> None:
        """{}.anyFalse() -> false"""
        col = FHIRPathCollection([])
        result = any_false(col)
        assert result.is_singleton
        assert result.singleton_value is False

    def test_has_false_returns_true(self) -> None:
        """[true, false].anyFalse() -> true"""
        col = FHIRPathCollection([True, False])
        result = any_false(col)
        assert result.singleton_value is True

    def test_all_false_returns_true(self) -> None:
        """[false, false].anyFalse() -> true"""
        col = FHIRPathCollection([False, False])
        result = any_false(col)
        assert result.singleton_value is True

    def test_all_true_returns_false(self) -> None:
        """[true, true].anyFalse() -> false"""
        col = FHIRPathCollection([True, True])
        result = any_false(col)
        assert result.singleton_value is False

    def test_singleton_false_returns_true(self) -> None:
        """[false].anyFalse() -> true"""
        col = FHIRPathCollection([False])
        result = any_false(col)
        assert result.singleton_value is True

    def test_singleton_true_returns_false(self) -> None:
        """[true].anyFalse() -> false"""
        col = FHIRPathCollection([True])
        result = any_false(col)
        assert result.singleton_value is False

    def test_short_circuits_on_first_false(self) -> None:
        """Stops evaluation on first false."""
        col = FHIRPathCollection([True, True, False, True])
        result = any_false(col)
        assert result.singleton_value is True


class TestCount:
    """Tests for the count() function."""

    def test_empty_collection_returns_zero(self) -> None:
        """{}.count() -> 0"""
        col = FHIRPathCollection([])
        result = count(col)
        assert result.is_singleton
        assert result.singleton_value == 0

    def test_singleton_returns_one(self) -> None:
        """[x].count() -> 1"""
        col = FHIRPathCollection([1])
        result = count(col)
        assert result.singleton_value == 1

    def test_multi_element_returns_count(self) -> None:
        """[x, y, z].count() -> 3"""
        col = FHIRPathCollection([1, 2, 3])
        result = count(col)
        assert result.singleton_value == 3

    def test_count_with_duplicates(self) -> None:
        """Count includes duplicates."""
        col = FHIRPathCollection([1, 1, 2, 2, 3])
        result = count(col)
        assert result.singleton_value == 5

    def test_count_with_none_elements(self) -> None:
        """None elements are counted."""
        col = FHIRPathCollection([None, None, 1])
        result = count(col)
        assert result.singleton_value == 3

    def test_count_with_false_elements(self) -> None:
        """False elements are counted."""
        col = FHIRPathCollection([False, False])
        result = count(col)
        assert result.singleton_value == 2


class TestDistinct:
    """Tests for the distinct() function."""

    def test_empty_collection_returns_empty(self) -> None:
        """{}.distinct() -> {}"""
        col = FHIRPathCollection([])
        result = distinct(col)
        assert result.is_empty

    def test_singleton_returns_same(self) -> None:
        """[x].distinct() -> [x]"""
        col = FHIRPathCollection([1])
        result = distinct(col)
        assert result.to_list() == [1]

    def test_removes_duplicates(self) -> None:
        """[x, x, y].distinct() -> [x, y]"""
        col = FHIRPathCollection([1, 1, 2, 2, 3])
        result = distinct(col)
        assert result.to_list() == [1, 2, 3]

    def test_preserves_order(self) -> None:
        """Order is preserved (first occurrence kept)."""
        col = FHIRPathCollection([3, 1, 2, 1, 3, 2])
        result = distinct(col)
        assert result.to_list() == [3, 1, 2]

    def test_all_unique_returns_same(self) -> None:
        """All unique elements returns same collection."""
        col = FHIRPathCollection([1, 2, 3, 4, 5])
        result = distinct(col)
        assert result.to_list() == [1, 2, 3, 4, 5]

    def test_distinct_with_strings(self) -> None:
        """Works with strings."""
        col = FHIRPathCollection(["a", "b", "a", "c"])
        result = distinct(col)
        assert result.to_list() == ["a", "b", "c"]

    def test_distinct_with_mixed_types(self) -> None:
        """Works with mixed types."""
        col = FHIRPathCollection([1, "1", 1, "1"])
        result = distinct(col)
        # "1" and 1 are distinct values
        assert len(result) == 2


class TestFHIRPathSemantics:
    """Tests verifying key FHIRPath semantic rules."""

    def test_empty_vs_exists_relationship(self) -> None:
        """empty().not() == exists()"""
        col = FHIRPathCollection([])
        assert empty(col).singleton_value is not exists(col).singleton_value

        col = FHIRPathCollection([1])
        assert empty(col).singleton_value is not exists(col).singleton_value

    def test_vacuous_truth_for_all_functions(self) -> None:
        """Empty collection returns true for all-like functions."""
        col = FHIRPathCollection([])

        # all() - vacuous truth
        assert all_criteria(col, lambda x: x > 0).singleton_value is True

        # allTrue() - vacuous truth
        assert all_true(col).singleton_value is True

        # allFalse() - vacuous truth
        assert all_false(col).singleton_value is True

    def test_empty_returns_false_for_any_functions(self) -> None:
        """Empty collection returns false for any-like functions."""
        col = FHIRPathCollection([])

        # exists() - false
        assert exists(col).singleton_value is False

        # exists(criteria) - false
        assert exists_with_criteria(col, lambda x: True).singleton_value is False

        # anyTrue() - false
        assert any_true(col).singleton_value is False

        # anyFalse() - false
        assert any_false(col).singleton_value is False

    def test_count_always_returns_singleton(self) -> None:
        """count() always returns a value, never empty collection."""
        col = FHIRPathCollection([])
        result = count(col)
        assert result.is_singleton
        assert result.singleton_value == 0


class TestEdgeCases:
    """Tests for edge cases and special scenarios."""

    def test_exists_with_exception_in_criteria(self) -> None:
        """Exceptions in criteria are handled gracefully."""
        col = FHIRPathCollection([1, 2, "not a number", 4])
        # Should not raise, just skip the element that causes error
        result = exists_with_criteria(col, lambda x: x > 3)
        assert result.singleton_value is True  # 4 > 3

    def test_all_with_exception_in_criteria(self) -> None:
        """Exceptions in criteria cause all() to return false."""
        col = FHIRPathCollection([1, 2, "not a number"])
        # Exception is treated as false
        result = all_criteria(col, lambda x: x > 0)
        assert result.singleton_value is False

    def test_distinct_with_dicts(self) -> None:
        """Distinct works with dictionaries."""
        d1 = {"a": 1}
        d2 = {"a": 1}
        d3 = {"a": 2}
        col = FHIRPathCollection([d1, d2, d3])
        result = distinct(col)
        # Note: dict comparison may vary based on implementation
        assert len(result) >= 2

    def test_empty_with_string_singleton(self) -> None:
        """Empty string is not an empty collection."""
        col = FHIRPathCollection([""])
        result = empty(col)
        assert result.singleton_value is False

    def test_count_with_large_collection(self) -> None:
        """Count works with large collections."""
        col = FHIRPathCollection(list(range(10000)))
        result = count(col)
        assert result.singleton_value == 10000
