"""
Unit tests for FHIRPath Filter, Subsetting, and Operator Functions.

Tests cover:
- Filter functions: where, select, repeat
- Subsetting functions: first, last, tail, take, skip, ofType
- Boolean operators: and, or, xor, implies, not
- Comparison operators: =, !=, <, >, <=, >=, ~, !~
- Collection operators: | (union), in, contains
"""

from __future__ import annotations

import pytest

from ...collection import FHIRPathCollection, EMPTY, wrap_as_collection
from ...functions.filter import (
    where,
    select,
    repeat,
    first,
    last,
    tail,
    take,
    skip,
    of_type,
    infer_fhir_type,
)
from ...operators import (
    # Boolean operators
    boolean_and,
    boolean_or,
    boolean_xor,
    boolean_implies,
    boolean_not,
    # Comparison operators
    equals,
    not_equals,
    less_than,
    greater_than,
    less_or_equal,
    greater_or_equal,
    equivalent,
    not_equivalent,
    # Collection operators
    union,
    membership,
    contains,
)


# =============================================================================
# Filter Function Tests
# =============================================================================

class TestWhere:
    """Tests for the where() filter function."""

    def test_where_with_predicate(self) -> None:
        """Test filtering with a callable predicate."""
        col = FHIRPathCollection([1, 2, 3, 4, 5])
        result = where(col, lambda x: x > 2)
        assert result.to_list() == [3, 4, 5]

    def test_where_empty_collection(self) -> None:
        """Test that empty collection returns EMPTY."""
        col = FHIRPathCollection([])
        result = where(col, lambda x: x > 0)
        assert result == EMPTY

    def test_where_no_matches(self) -> None:
        """Test filtering where no elements match."""
        col = FHIRPathCollection([1, 2, 3])
        result = where(col, lambda x: x > 10)
        assert result.to_list() == []

    def test_where_all_match(self) -> None:
        """Test filtering where all elements match."""
        col = FHIRPathCollection([2, 4, 6, 8])
        result = where(col, lambda x: x % 2 == 0)
        assert result.to_list() == [2, 4, 6, 8]

    def test_where_with_dicts(self) -> None:
        """Test filtering dictionaries."""
        col = FHIRPathCollection([
            {"name": "John", "active": True},
            {"name": "Jane", "active": False},
            {"name": "Bob", "active": True},
        ])
        result = where(col, lambda x: x.get("active", False))
        assert len(result) == 2
        assert result.values[0]["name"] == "John"
        assert result.values[1]["name"] == "Bob"


class TestSelect:
    """Tests for the select() projection function."""

    def test_select_with_function(self) -> None:
        """Test projecting with a callable."""
        col = FHIRPathCollection([1, 2, 3])
        result = select(col, lambda x: x * 2)
        assert result.to_list() == [2, 4, 6]

    def test_select_empty_collection(self) -> None:
        """Test that empty collection returns EMPTY."""
        col = FHIRPathCollection([])
        result = select(col, lambda x: x * 2)
        assert result == EMPTY

    def test_select_flattens_lists(self) -> None:
        """Test that select flattens nested lists."""
        col = FHIRPathCollection([1, 2])
        result = select(col, lambda x: [x, x * 10])
        assert result.to_list() == [1, 10, 2, 20]

    def test_select_excludes_none(self) -> None:
        """Test that None results are excluded."""
        col = FHIRPathCollection([1, 2, 3])
        result = select(col, lambda x: x if x > 1 else None)
        assert result.to_list() == [2, 3]

    def test_select_with_dicts(self) -> None:
        """Test projecting dictionary fields."""
        col = FHIRPathCollection([
            {"name": "John", "age": 30},
            {"name": "Jane", "age": 25},
        ])
        result = select(col, lambda x: x.get("name"))
        assert result.to_list() == ["John", "Jane"]


class TestRepeat:
    """Tests for the repeat() iteration function."""

    def test_repeat_simple(self) -> None:
        """Test simple repeat iteration."""
        col = FHIRPathCollection([1])
        # Returns None for non-dicts, so should just return [1]
        result = repeat(col, lambda x: x + 1 if isinstance(x, int) and x < 3 else None)
        assert result.to_list() == [1, 2, 3]

    def test_repeat_empty_collection(self) -> None:
        """Test that empty collection returns EMPTY."""
        col = FHIRPathCollection([])
        result = repeat(col, lambda x: x)
        assert result == EMPTY

    def test_repeat_stops_when_no_new_results(self) -> None:
        """Test that repeat stops when no new results are found."""
        col = FHIRPathCollection([1])
        result = repeat(col, lambda x: x)  # Same value, no new results
        assert result.to_list() == [1]


# =============================================================================
# Subsetting Function Tests
# =============================================================================

class TestFirst:
    """Tests for the first() function."""

    def test_first_of_collection(self) -> None:
        """Test getting first element."""
        col = FHIRPathCollection([1, 2, 3])
        assert first(col) == 1

    def test_first_of_empty(self) -> None:
        """Test first of empty collection returns None."""
        col = FHIRPathCollection([])
        assert first(col) is None

    def test_first_of_singleton(self) -> None:
        """Test first of singleton returns the value."""
        col = FHIRPathCollection(["only"])
        assert first(col) == "only"


class TestLast:
    """Tests for the last() function."""

    def test_last_of_collection(self) -> None:
        """Test getting last element."""
        col = FHIRPathCollection([1, 2, 3])
        assert last(col) == 3

    def test_last_of_empty(self) -> None:
        """Test last of empty collection returns None."""
        col = FHIRPathCollection([])
        assert last(col) is None

    def test_last_of_singleton(self) -> None:
        """Test last of singleton returns the value."""
        col = FHIRPathCollection(["only"])
        assert last(col) == "only"


class TestTail:
    """Tests for the tail() function."""

    def test_tail_default_n(self) -> None:
        """Test tail with default n=1."""
        col = FHIRPathCollection([1, 2, 3, 4])
        result = tail(col)
        assert result.to_list() == [2, 3, 4]

    def test_tail_with_n(self) -> None:
        """Test tail with custom n."""
        col = FHIRPathCollection([1, 2, 3, 4, 5])
        result = tail(col, 2)
        assert result.to_list() == [3, 4, 5]

    def test_tail_empty(self) -> None:
        """Test tail of empty collection."""
        col = FHIRPathCollection([])
        result = tail(col, 1)
        assert result.to_list() == []

    def test_tail_n_greater_than_size(self) -> None:
        """Test tail when n >= collection size."""
        col = FHIRPathCollection([1, 2])
        result = tail(col, 5)
        assert result.to_list() == []


class TestTake:
    """Tests for the take() function."""

    def test_take_fewer_than_size(self) -> None:
        """Test taking fewer elements than collection size."""
        col = FHIRPathCollection([1, 2, 3, 4, 5])
        result = take(col, 3)
        assert result.to_list() == [1, 2, 3]

    def test_take_more_than_size(self) -> None:
        """Test taking more elements than collection size."""
        col = FHIRPathCollection([1, 2])
        result = take(col, 5)
        assert result.to_list() == [1, 2]

    def test_take_zero(self) -> None:
        """Test taking zero elements."""
        col = FHIRPathCollection([1, 2, 3])
        result = take(col, 0)
        assert result.to_list() == []

    def test_take_empty(self) -> None:
        """Test take of empty collection."""
        col = FHIRPathCollection([])
        result = take(col, 3)
        assert result.to_list() == []


class TestSkip:
    """Tests for the skip() function."""

    def test_skip_fewer_than_size(self) -> None:
        """Test skipping fewer elements than collection size."""
        col = FHIRPathCollection([1, 2, 3, 4, 5])
        result = skip(col, 2)
        assert result.to_list() == [3, 4, 5]

    def test_skip_more_than_size(self) -> None:
        """Test skipping more elements than collection size."""
        col = FHIRPathCollection([1, 2])
        result = skip(col, 5)
        assert result.to_list() == []

    def test_skip_zero(self) -> None:
        """Test skipping zero elements."""
        col = FHIRPathCollection([1, 2, 3])
        result = skip(col, 0)
        assert result.to_list() == [1, 2, 3]

    def test_skip_empty(self) -> None:
        """Test skip of empty collection."""
        col = FHIRPathCollection([])
        result = skip(col, 2)
        assert result.to_list() == []


class TestOfType:
    """Tests for the ofType() function."""

    def test_of_type_integer(self) -> None:
        """Test filtering integers."""
        col = FHIRPathCollection([1, "a", 2, "b", 3])
        result = of_type(col, "integer")
        assert result.to_list() == [1, 2, 3]

    def test_of_type_string(self) -> None:
        """Test filtering strings."""
        col = FHIRPathCollection([1, "a", 2, "b", 3])
        result = of_type(col, "string")
        assert result.to_list() == ["a", "b"]

    def test_of_type_boolean(self) -> None:
        """Test filtering booleans (not confused with int)."""
        col = FHIRPathCollection([True, 1, False, 0, 2])
        result = of_type(col, "boolean")
        assert result.to_list() == [True, False]

    def test_of_type_empty(self) -> None:
        """Test ofType on empty collection."""
        col = FHIRPathCollection([])
        result = of_type(col, "integer")
        assert result.to_list() == []

    def test_of_type_resource(self) -> None:
        """Test filtering resources (dicts)."""
        col = FHIRPathCollection([
            {"resourceType": "Patient", "id": "1"},
            "not a resource",
            {"resourceType": "Observation", "id": "2"},
        ])
        result = of_type(col, "Resource")
        assert len(result) == 2

    def test_of_type_unknown(self) -> None:
        """Test filtering by unknown type returns empty."""
        col = FHIRPathCollection([1, 2, 3])
        result = of_type(col, "UnknownType")
        assert result.to_list() == []


class TestInferFHIRType:
    """Tests for the infer_fhir_type() function."""

    def test_infer_integer(self) -> None:
        """Test inferring integer type."""
        assert infer_fhir_type(42) == "integer"

    def test_infer_boolean(self) -> None:
        """Test inferring boolean type."""
        assert infer_fhir_type(True) == "boolean"
        assert infer_fhir_type(False) == "boolean"

    def test_infer_string(self) -> None:
        """Test inferring string type."""
        assert infer_fhir_type("hello") == "string"

    def test_infer_decimal(self) -> None:
        """Test inferring decimal type."""
        assert infer_fhir_type(3.14) == "decimal"

    def test_infer_resource(self) -> None:
        """Test inferring resource type."""
        assert infer_fhir_type({"resourceType": "Patient"}) == "Patient"


# =============================================================================
# Boolean Operator Tests
# =============================================================================

class TestBooleanAnd:
    """Tests for the AND operator."""

    def test_and_true_true(self) -> None:
        """Test true AND true = true."""
        left = FHIRPathCollection([True])
        right = FHIRPathCollection([True])
        result = boolean_and(left, right)
        assert result.to_list() == [True]

    def test_and_true_false(self) -> None:
        """Test true AND false = false."""
        left = FHIRPathCollection([True])
        right = FHIRPathCollection([False])
        result = boolean_and(left, right)
        assert result.to_list() == [False]

    def test_and_false_true(self) -> None:
        """Test false AND true = false."""
        left = FHIRPathCollection([False])
        right = FHIRPathCollection([True])
        result = boolean_and(left, right)
        assert result.to_list() == [False]

    def test_and_false_false(self) -> None:
        """Test false AND false = false."""
        left = FHIRPathCollection([False])
        right = FHIRPathCollection([False])
        result = boolean_and(left, right)
        assert result.to_list() == [False]

    def test_and_empty_true(self) -> None:
        """Test {} AND true = {}."""
        left = FHIRPathCollection([])
        right = FHIRPathCollection([True])
        result = boolean_and(left, right)
        assert result.is_empty

    def test_and_true_empty(self) -> None:
        """Test true AND {} = {}."""
        left = FHIRPathCollection([True])
        right = FHIRPathCollection([])
        result = boolean_and(left, right)
        assert result.is_empty

    def test_and_false_empty(self) -> None:
        """Test false AND {} = false (short-circuit)."""
        left = FHIRPathCollection([False])
        right = FHIRPathCollection([])
        result = boolean_and(left, right)
        assert result.to_list() == [False]

    def test_and_empty_false(self) -> None:
        """Test {} AND false = false (short-circuit)."""
        left = FHIRPathCollection([])
        right = FHIRPathCollection([False])
        result = boolean_and(left, right)
        assert result.to_list() == [False]

    def test_and_empty_empty(self) -> None:
        """Test {} AND {} = {}."""
        left = FHIRPathCollection([])
        right = FHIRPathCollection([])
        result = boolean_and(left, right)
        assert result.is_empty


class TestBooleanOr:
    """Tests for the OR operator."""

    def test_or_true_false(self) -> None:
        """Test true OR false = true."""
        left = FHIRPathCollection([True])
        right = FHIRPathCollection([False])
        result = boolean_or(left, right)
        assert result.to_list() == [True]

    def test_or_false_true(self) -> None:
        """Test false OR true = true."""
        left = FHIRPathCollection([False])
        right = FHIRPathCollection([True])
        result = boolean_or(left, right)
        assert result.to_list() == [True]

    def test_or_false_false(self) -> None:
        """Test false OR false = false."""
        left = FHIRPathCollection([False])
        right = FHIRPathCollection([False])
        result = boolean_or(left, right)
        assert result.to_list() == [False]

    def test_or_true_empty(self) -> None:
        """Test true OR {} = true (short-circuit)."""
        left = FHIRPathCollection([True])
        right = FHIRPathCollection([])
        result = boolean_or(left, right)
        assert result.to_list() == [True]

    def test_or_empty_true(self) -> None:
        """Test {} OR true = true (short-circuit)."""
        left = FHIRPathCollection([])
        right = FHIRPathCollection([True])
        result = boolean_or(left, right)
        assert result.to_list() == [True]

    def test_or_false_empty(self) -> None:
        """Test false OR {} = {}."""
        left = FHIRPathCollection([False])
        right = FHIRPathCollection([])
        result = boolean_or(left, right)
        assert result.is_empty


class TestBooleanXor:
    """Tests for the XOR operator."""

    def test_xor_true_false(self) -> None:
        """Test true XOR false = true."""
        left = FHIRPathCollection([True])
        right = FHIRPathCollection([False])
        result = boolean_xor(left, right)
        assert result.to_list() == [True]

    def test_xor_false_true(self) -> None:
        """Test false XOR true = true."""
        left = FHIRPathCollection([False])
        right = FHIRPathCollection([True])
        result = boolean_xor(left, right)
        assert result.to_list() == [True]

    def test_xor_true_true(self) -> None:
        """Test true XOR true = false."""
        left = FHIRPathCollection([True])
        right = FHIRPathCollection([True])
        result = boolean_xor(left, right)
        assert result.to_list() == [False]

    def test_xor_false_false(self) -> None:
        """Test false XOR false = false."""
        left = FHIRPathCollection([False])
        right = FHIRPathCollection([False])
        result = boolean_xor(left, right)
        assert result.to_list() == [False]

    def test_xor_empty_operand(self) -> None:
        """Test XOR with empty operand returns empty."""
        left = FHIRPathCollection([])
        right = FHIRPathCollection([True])
        result = boolean_xor(left, right)
        assert result.is_empty


class TestBooleanImplies:
    """Tests for the IMPLIES operator."""

    def test_implies_true_true(self) -> None:
        """Test true implies true = true."""
        left = FHIRPathCollection([True])
        right = FHIRPathCollection([True])
        result = boolean_implies(left, right)
        assert result.to_list() == [True]

    def test_implies_true_false(self) -> None:
        """Test true implies false = false."""
        left = FHIRPathCollection([True])
        right = FHIRPathCollection([False])
        result = boolean_implies(left, right)
        assert result.to_list() == [False]

    def test_implies_false_true(self) -> None:
        """Test false implies true = true."""
        left = FHIRPathCollection([False])
        right = FHIRPathCollection([True])
        result = boolean_implies(left, right)
        assert result.to_list() == [True]

    def test_implies_false_false(self) -> None:
        """Test false implies false = true."""
        left = FHIRPathCollection([False])
        right = FHIRPathCollection([False])
        result = boolean_implies(left, right)
        assert result.to_list() == [True]

    def test_implies_empty_true(self) -> None:
        """Test {} implies true = true."""
        left = FHIRPathCollection([])
        right = FHIRPathCollection([True])
        result = boolean_implies(left, right)
        assert result.to_list() == [True]

    def test_implies_false_empty(self) -> None:
        """Test false implies {} = true."""
        left = FHIRPathCollection([False])
        right = FHIRPathCollection([])
        result = boolean_implies(left, right)
        assert result.to_list() == [True]


class TestBooleanNot:
    """Tests for the NOT operator."""

    def test_not_true(self) -> None:
        """Test not true = false."""
        col = FHIRPathCollection([True])
        result = boolean_not(col)
        assert result.to_list() == [False]

    def test_not_false(self) -> None:
        """Test not false = true."""
        col = FHIRPathCollection([False])
        result = boolean_not(col)
        assert result.to_list() == [True]

    def test_not_empty(self) -> None:
        """Test not {} = {}."""
        col = FHIRPathCollection([])
        result = boolean_not(col)
        assert result.is_empty


# =============================================================================
# Comparison Operator Tests
# =============================================================================

class TestEquals:
    """Tests for the equality operator."""

    def test_equals_same_values(self) -> None:
        """Test equality of same values."""
        left = FHIRPathCollection([5])
        right = FHIRPathCollection([5])
        result = equals(left, right)
        assert result.to_list() == [True]

    def test_equals_different_values(self) -> None:
        """Test equality of different values."""
        left = FHIRPathCollection([5])
        right = FHIRPathCollection([3])
        result = equals(left, right)
        assert result.to_list() == [False]

    def test_equals_both_empty(self) -> None:
        """Test equality of two empty collections = empty (per FHIRPath spec §6.5)."""
        left = FHIRPathCollection([])
        right = FHIRPathCollection([])
        result = equals(left, right)
        assert result.to_list() == []

    def test_equals_one_empty(self) -> None:
        """Test equality with one empty collection = empty (per FHIRPath spec §6.5)."""
        left = FHIRPathCollection([1])
        right = FHIRPathCollection([])
        result = equals(left, right)
        assert result.to_list() == []

    def test_equals_strings(self) -> None:
        """Test string equality."""
        left = FHIRPathCollection(["hello"])
        right = FHIRPathCollection(["hello"])
        result = equals(left, right)
        assert result.to_list() == [True]


class TestNotEquals:
    """Tests for the inequality operator."""

    def test_not_equals_same_values(self) -> None:
        """Test inequality of same values."""
        left = FHIRPathCollection([5])
        right = FHIRPathCollection([5])
        result = not_equals(left, right)
        assert result.to_list() == [False]

    def test_not_equals_different_values(self) -> None:
        """Test inequality of different values."""
        left = FHIRPathCollection([5])
        right = FHIRPathCollection([3])
        result = not_equals(left, right)
        assert result.to_list() == [True]


class TestComparison:
    """Tests for comparison operators (<, >, <=, >=)."""

    def test_less_than_true(self) -> None:
        """Test 3 < 5 = true."""
        left = FHIRPathCollection([3])
        right = FHIRPathCollection([5])
        result = less_than(left, right)
        assert result.to_list() == [True]

    def test_less_than_false(self) -> None:
        """Test 5 < 3 = false."""
        left = FHIRPathCollection([5])
        right = FHIRPathCollection([3])
        result = less_than(left, right)
        assert result.to_list() == [False]

    def test_greater_than_true(self) -> None:
        """Test 5 > 3 = true."""
        left = FHIRPathCollection([5])
        right = FHIRPathCollection([3])
        result = greater_than(left, right)
        assert result.to_list() == [True]

    def test_less_or_equal_true(self) -> None:
        """Test 3 <= 3 = true."""
        left = FHIRPathCollection([3])
        right = FHIRPathCollection([3])
        result = less_or_equal(left, right)
        assert result.to_list() == [True]

    def test_greater_or_equal_true(self) -> None:
        """Test 5 >= 5 = true."""
        left = FHIRPathCollection([5])
        right = FHIRPathCollection([5])
        result = greater_or_equal(left, right)
        assert result.to_list() == [True]

    def test_comparison_with_empty(self) -> None:
        """Test comparison with empty collection returns empty."""
        left = FHIRPathCollection([])
        right = FHIRPathCollection([5])
        result = less_than(left, right)
        assert result.is_empty


class TestEquivalent:
    """Tests for the equivalence operator (~)."""

    def test_equivalent_same_values(self) -> None:
        """Test equivalence of same values."""
        left = FHIRPathCollection([5])
        right = FHIRPathCollection([5])
        result = equivalent(left, right)
        assert result.to_list() == [True]

    def test_equivalent_both_empty(self) -> None:
        """Test equivalence of two empty collections = true."""
        left = FHIRPathCollection([])
        right = FHIRPathCollection([])
        result = equivalent(left, right)
        assert result.to_list() == [True]

    def test_equivalent_strings_case_insensitive(self) -> None:
        """Test string equivalence is case-insensitive."""
        left = FHIRPathCollection(["Hello"])
        right = FHIRPathCollection(["HELLO"])
        result = equivalent(left, right)
        assert result.to_list() == [True]


# =============================================================================
# Collection Operator Tests
# =============================================================================

class TestUnion:
    """Tests for the union operator (|)."""

    def test_union_disjoint(self) -> None:
        """Test union of disjoint collections."""
        left = FHIRPathCollection([1, 2])
        right = FHIRPathCollection([3, 4])
        result = union(left, right)
        assert set(result.to_list()) == {1, 2, 3, 4}

    def test_union_with_overlap(self) -> None:
        """Test union removes duplicates."""
        left = FHIRPathCollection([1, 2, 3])
        right = FHIRPathCollection([2, 3, 4])
        result = union(left, right)
        assert set(result.to_list()) == {1, 2, 3, 4}

    def test_union_with_empty(self) -> None:
        """Test union with empty collection."""
        left = FHIRPathCollection([1, 2])
        right = FHIRPathCollection([])
        result = union(left, right)
        assert result.to_list() == [1, 2]


class TestMembership:
    """Tests for the membership operator (in)."""

    def test_in_found(self) -> None:
        """Test element in collection = true."""
        element = FHIRPathCollection([3])
        collection = FHIRPathCollection([1, 2, 3, 4, 5])
        result = membership(element, collection)
        assert result.to_list() == [True]

    def test_in_not_found(self) -> None:
        """Test element not in collection = false."""
        element = FHIRPathCollection([6])
        collection = FHIRPathCollection([1, 2, 3, 4, 5])
        result = membership(element, collection)
        assert result.to_list() == [False]

    def test_in_empty_collection(self) -> None:
        """Test element in empty collection = false."""
        element = FHIRPathCollection([1])
        collection = FHIRPathCollection([])
        result = membership(element, collection)
        assert result.to_list() == [False]

    def test_in_empty_element(self) -> None:
        """Test empty element in collection = empty."""
        element = FHIRPathCollection([])
        collection = FHIRPathCollection([1, 2, 3])
        result = membership(element, collection)
        assert result.is_empty


class TestContains:
    """Tests for the contains operator."""

    def test_contains_found(self) -> None:
        """Test collection contains element = true."""
        collection = FHIRPathCollection([1, 2, 3, 4, 5])
        element = FHIRPathCollection([3])
        result = contains(collection, element)
        assert result.to_list() == [True]

    def test_contains_not_found(self) -> None:
        """Test collection does not contain element = false."""
        collection = FHIRPathCollection([1, 2, 3, 4, 5])
        element = FHIRPathCollection([6])
        result = contains(collection, element)
        assert result.to_list() == [False]

    def test_contains_string(self) -> None:
        """Test contains with strings."""
        collection = FHIRPathCollection(["apple", "banana", "cherry"])
        element = FHIRPathCollection(["banana"])
        result = contains(collection, element)
        assert result.to_list() == [True]


# =============================================================================
# Integration Tests
# =============================================================================

class TestFilterIntegration:
    """Integration tests combining filter functions and operators."""

    def test_where_with_comparison(self) -> None:
        """Test where() with comparison operators."""
        col = FHIRPathCollection([1, 2, 3, 4, 5, 6])
        # Filter for values > 3
        result = where(col, lambda x: greater_than(FHIRPathCollection([x]), FHIRPathCollection([3])).singleton_value)
        assert result.to_list() == [4, 5, 6]

    def test_chained_filter_operations(self) -> None:
        """Test chaining filter operations."""
        col = FHIRPathCollection([1, 2, 3, 4, 5, 6, 7, 8, 9, 10])
        # Get even numbers > 4
        filtered = where(col, lambda x: x > 4 and x % 2 == 0)
        # Take first 2
        result = take(filtered, 2)
        assert result.to_list() == [6, 8]

    def test_select_and_first(self) -> None:
        """Test select followed by first."""
        col = FHIRPathCollection([
            {"name": "John", "score": 85},
            {"name": "Jane", "score": 92},
            {"name": "Bob", "score": 78},
        ])
        # Get all scores, take the first
        scores = select(col, lambda x: x.get("score"))
        result = first(scores)
        assert result == 85

    def test_union_and_contains(self) -> None:
        """Test union followed by contains."""
        left = FHIRPathCollection([1, 2, 3])
        right = FHIRPathCollection([3, 4, 5])
        combined = union(left, right)
        # Check if 3 is in the union
        result = contains(combined, FHIRPathCollection([3]))
        assert result.to_list() == [True]
