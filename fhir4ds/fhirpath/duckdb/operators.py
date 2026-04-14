"""
FHIRPath Operators

Implements boolean, comparison, and collection operators as defined in the FHIRPath specification.

Boolean operators:
- and, or, xor, implies, not
- Handle empty collection semantics: `{} AND true` -> `{}`

Comparison operators:
- =, !=, <, >, <=, >=
- ~ (equivalent), !~ (not equivalent)

Collection operators:
- | (union)
- in (membership)
- contains (contains element)

Reference: https://hl7.org/fhirpath/#operators
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Optional, Union

from .collection import FHIRPathCollection, EMPTY, EmptyCollectionSentinel, wrap_as_collection

if TYPE_CHECKING:
    pass


# =============================================================================
# Boolean Operators
# =============================================================================

def boolean_and(
    left: FHIRPathCollection,
    right: FHIRPathCollection,
) -> FHIRPathCollection:
    """
    FHIRPath AND operator with empty collection semantics.

    Truth table:
    - true AND true = true
    - true AND false = false
    - false AND true = false
    - false AND false = false
    - true AND {} = {}
    - {} AND true = {}
    - false AND {} = false
    - {} AND false = false
    - {} AND {} = {}

    Args:
        left: Left operand collection.
        right: Right operand collection.

    Returns:
        Collection containing boolean result, or empty if propagating.
    """
    # Get values
    left_val = _get_boolean_value(left)
    right_val = _get_boolean_value(right)

    # Handle empty collection propagation
    if left_val is None and right_val is None:
        return FHIRPathCollection([])
    if left_val is None:
        # left is empty
        if right_val is False:
            return FHIRPathCollection([False])
        return FHIRPathCollection([])
    if right_val is None:
        # right is empty
        if left_val is False:
            return FHIRPathCollection([False])
        return FHIRPathCollection([])

    # Both have values
    return FHIRPathCollection([left_val and right_val])


def boolean_or(
    left: FHIRPathCollection,
    right: FHIRPathCollection,
) -> FHIRPathCollection:
    """
    FHIRPath OR operator with empty collection semantics.

    Truth table:
    - true OR true = true
    - true OR false = true
    - false OR true = true
    - false OR false = false
    - true OR {} = true
    - {} OR true = true
    - false OR {} = {}
    - {} OR false = {}
    - {} OR {} = {}

    Args:
        left: Left operand collection.
        right: Right operand collection.

    Returns:
        Collection containing boolean result, or empty if propagating.
    """
    # Get values
    left_val = _get_boolean_value(left)
    right_val = _get_boolean_value(right)

    # Handle empty collection propagation
    if left_val is None and right_val is None:
        return FHIRPathCollection([])
    if left_val is None:
        # left is empty
        if right_val is True:
            return FHIRPathCollection([True])
        return FHIRPathCollection([])
    if right_val is None:
        # right is empty
        if left_val is True:
            return FHIRPathCollection([True])
        return FHIRPathCollection([])

    # Both have values
    return FHIRPathCollection([left_val or right_val])


def boolean_xor(
    left: FHIRPathCollection,
    right: FHIRPathCollection,
) -> FHIRPathCollection:
    """
    FHIRPath XOR operator with empty collection semantics.

    Truth table:
    - true XOR true = false
    - true XOR false = true
    - false XOR true = true
    - false XOR false = false
    - If either is empty, result is empty

    Args:
        left: Left operand collection.
        right: Right operand collection.

    Returns:
        Collection containing boolean result, or empty if propagating.
    """
    left_val = _get_boolean_value(left)
    right_val = _get_boolean_value(right)

    # XOR requires both operands to be non-empty
    if left_val is None or right_val is None:
        return FHIRPathCollection([])

    return FHIRPathCollection([left_val != right_val])


def boolean_implies(
    left: FHIRPathCollection,
    right: FHIRPathCollection,
) -> FHIRPathCollection:
    """
    FHIRPath IMPLIES operator with empty collection semantics.

    Truth table (a implies b means !a OR b):
    - true implies true = true
    - true implies false = false
    - false implies true = true
    - false implies false = true
    - true implies {} = {}
    - {} implies true = true
    - false implies {} = true
    - {} implies false = {}
    - {} implies {} = {}

    Args:
        left: Left operand collection (antecedent).
        right: Right operand collection (consequent).

    Returns:
        Collection containing boolean result, or empty if propagating.
    """
    left_val = _get_boolean_value(left)
    right_val = _get_boolean_value(right)

    # Handle empty collection propagation
    if left_val is None and right_val is None:
        return FHIRPathCollection([])
    if left_val is None:
        # left is empty
        if right_val is False:
            return FHIRPathCollection([])
        return FHIRPathCollection([True])
    if right_val is None:
        # right is empty
        if left_val is False:
            return FHIRPathCollection([True])
        return FHIRPathCollection([])

    # Both have values: a implies b = !a OR b
    return FHIRPathCollection([not left_val or right_val])


def boolean_not(collection: FHIRPathCollection) -> FHIRPathCollection:
    """
    FHIRPath NOT operator.

    Returns the logical negation of the input.
    Empty collection returns empty.

    Args:
        collection: Input collection.

    Returns:
        Collection containing negated boolean, or empty if input is empty.
    """
    val = _get_boolean_value(collection)
    if val is None:
        return FHIRPathCollection([])
    return FHIRPathCollection([not val])


def _get_boolean_value(collection: FHIRPathCollection) -> Optional[bool]:
    """
    Extract boolean value from collection.

    Args:
        collection: Input collection.

    Returns:
        Boolean value, or None if empty or not a boolean singleton.
    """
    if collection.is_empty:
        return None
    if not collection.is_singleton:
        # Multi-element collections are not valid for boolean operations
        return None

    val = collection.singleton_value
    if isinstance(val, bool):
        return val
    if isinstance(val, str):
        if val.lower() == "true":
            return True
        if val.lower() == "false":
            return False
    # Non-boolean value
    return None


# =============================================================================
# Comparison Operators
# =============================================================================

def equals(
    left: FHIRPathCollection,
    right: FHIRPathCollection,
) -> FHIRPathCollection:
    """
    FHIRPath equality operator (=).

    For collections, equality means:
    - Both empty: true
    - One empty, one not: false
    - Same size and all elements equal: true
    - Otherwise: false

    Args:
        left: Left operand collection.
        right: Right operand collection.

    Returns:
        Collection containing boolean result.
    """
    # Per FHIRPath spec §6.5: if either operand is empty, result is empty
    if left.is_empty or right.is_empty:
        return FHIRPathCollection([])

    # Both singletons - compare values
    if left.is_singleton and right.is_singleton:
        return FHIRPathCollection([left.singleton_value == right.singleton_value])

    # Compare as collections
    if len(left) != len(right):
        return FHIRPathCollection([False])

    return FHIRPathCollection([left.values == right.values])


def not_equals(
    left: FHIRPathCollection,
    right: FHIRPathCollection,
) -> FHIRPathCollection:
    """
    FHIRPath inequality operator (!=).

    Args:
        left: Left operand collection.
        right: Right operand collection.

    Returns:
        Collection containing boolean result.
    """
    eq_result = equals(left, right)
    if eq_result.is_empty:
        return FHIRPathCollection([])

    return FHIRPathCollection([not eq_result.singleton_value])


def less_than(
    left: FHIRPathCollection,
    right: FHIRPathCollection,
) -> FHIRPathCollection:
    """
    FHIRPath less-than operator (<).

    Only valid for singletons of comparable types.

    Args:
        left: Left operand collection.
        right: Right operand collection.

    Returns:
        Collection containing boolean result, or empty if invalid.
    """
    if left.is_empty or right.is_empty:
        return FHIRPathCollection([])

    if not left.is_singleton or not right.is_singleton:
        return FHIRPathCollection([])

    left_val = left.singleton_value
    right_val = right.singleton_value

    try:
        return FHIRPathCollection([left_val < right_val])
    except TypeError:
        return FHIRPathCollection([])


def greater_than(
    left: FHIRPathCollection,
    right: FHIRPathCollection,
) -> FHIRPathCollection:
    """
    FHIRPath greater-than operator (>).

    Args:
        left: Left operand collection.
        right: Right operand collection.

    Returns:
        Collection containing boolean result, or empty if invalid.
    """
    if left.is_empty or right.is_empty:
        return FHIRPathCollection([])

    if not left.is_singleton or not right.is_singleton:
        return FHIRPathCollection([])

    left_val = left.singleton_value
    right_val = right.singleton_value

    try:
        return FHIRPathCollection([left_val > right_val])
    except TypeError:
        return FHIRPathCollection([])


def less_or_equal(
    left: FHIRPathCollection,
    right: FHIRPathCollection,
) -> FHIRPathCollection:
    """
    FHIRPath less-or-equal operator (<=).

    Args:
        left: Left operand collection.
        right: Right operand collection.

    Returns:
        Collection containing boolean result, or empty if invalid.
    """
    if left.is_empty or right.is_empty:
        return FHIRPathCollection([])

    if not left.is_singleton or not right.is_singleton:
        return FHIRPathCollection([])

    left_val = left.singleton_value
    right_val = right.singleton_value

    try:
        return FHIRPathCollection([left_val <= right_val])
    except TypeError:
        return FHIRPathCollection([])


def greater_or_equal(
    left: FHIRPathCollection,
    right: FHIRPathCollection,
) -> FHIRPathCollection:
    """
    FHIRPath greater-or-equal operator (>=).

    Args:
        left: Left operand collection.
        right: Right operand collection.

    Returns:
        Collection containing boolean result, or empty if invalid.
    """
    if left.is_empty or right.is_empty:
        return FHIRPathCollection([])

    if not left.is_singleton or not right.is_singleton:
        return FHIRPathCollection([])

    left_val = left.singleton_value
    right_val = right.singleton_value

    try:
        return FHIRPathCollection([left_val >= right_val])
    except TypeError:
        return FHIRPathCollection([])


def equivalent(
    left: FHIRPathCollection,
    right: FHIRPathCollection,
) -> FHIRPathCollection:
    """
    FHIRPath equivalence operator (~).

    Equivalence is similar to equality but:
    - Empty collections are equivalent to empty
    - String comparison is case-insensitive for some types
    - Focus on semantic equivalence

    Args:
        left: Left operand collection.
        right: Right operand collection.

    Returns:
        Collection containing boolean result.
    """
    # Both empty are equivalent
    if left.is_empty and right.is_empty:
        return FHIRPathCollection([True])

    # One empty, one not - not equivalent
    if left.is_empty or right.is_empty:
        return FHIRPathCollection([False])

    # Both singletons
    if left.is_singleton and right.is_singleton:
        return FHIRPathCollection([
            _values_equivalent(left.singleton_value, right.singleton_value)
        ])

    # Compare as collections
    if len(left) != len(right):
        return FHIRPathCollection([False])

    for l_val, r_val in zip(left.values, right.values):
        if not _values_equivalent(l_val, r_val):
            return FHIRPathCollection([False])

    return FHIRPathCollection([True])


def not_equivalent(
    left: FHIRPathCollection,
    right: FHIRPathCollection,
) -> FHIRPathCollection:
    """
    FHIRPath not-equivalent operator (!~).

    Args:
        left: Left operand collection.
        right: Right operand collection.

    Returns:
        Collection containing boolean result.
    """
    eq_result = equivalent(left, right)
    if eq_result.is_empty:
        return FHIRPathCollection([])

    return FHIRPathCollection([not eq_result.singleton_value])


def _values_equivalent(left: Any, right: Any) -> bool:
    """
    Check if two values are semantically equivalent.

    Args:
        left: Left value.
        right: Right value.

    Returns:
        True if values are equivalent.
    """
    if type(left) != type(right):
        # Different types - try string comparison for some cases
        if isinstance(left, str) and isinstance(right, str):
            return left.lower() == right.lower()
        return False

    if isinstance(left, str):
        # Case-insensitive string comparison
        return left.lower() == right.lower()

    if isinstance(left, float):
        # Handle floating point comparison
        return abs(left - right) < 1e-10

    if isinstance(left, dict):
        # Compare dicts
        if set(left.keys()) != set(right.keys()):
            return False
        return all(_values_equivalent(left[k], right.get(k)) for k in left)

    if isinstance(left, list):
        if len(left) != len(right):
            return False
        return all(_values_equivalent(l, r) for l, r in zip(left, right))

    return left == right


# =============================================================================
# Collection Operators
# =============================================================================

def union(
    left: FHIRPathCollection,
    right: FHIRPathCollection,
) -> FHIRPathCollection:
    """
    FHIRPath union operator (|).

    Combines two collections, removing duplicates.

    Args:
        left: Left operand collection.
        right: Right operand collection.

    Returns:
        Collection containing union of elements.
    """
    return left.union(right)


def membership(
    element: FHIRPathCollection,
    collection: FHIRPathCollection,
) -> FHIRPathCollection:
    """
    FHIRPath membership operator (in).

    Tests if element is in collection.

    Args:
        element: Element to search for (singleton).
        collection: Collection to search in.

    Returns:
        Collection containing boolean result.
    """
    if element.is_empty:
        return FHIRPathCollection([])

    if not element.is_singleton:
        return FHIRPathCollection([])

    target = element.singleton_value

    # Check if target is in collection
    for item in collection.values:
        if _values_equal(item, target):
            return FHIRPathCollection([True])

    return FHIRPathCollection([False])


def contains(
    collection: FHIRPathCollection,
    element: FHIRPathCollection,
) -> FHIRPathCollection:
    """
    FHIRPath contains operator.

    Tests if collection contains the element.
    This is the reverse of 'in'.

    Args:
        collection: Collection to search in.
        element: Element to search for (singleton).

    Returns:
        Collection containing boolean result.
    """
    return membership(element, collection)


def _values_equal(left: Any, right: Any) -> bool:
    """
    Check if two values are equal for membership purposes.

    Args:
        left: Left value.
        right: Right value.

    Returns:
        True if values are equal.
    """
    if type(left) != type(right):
        return False

    if isinstance(left, dict):
        if set(left.keys()) != set(right.keys()):
            return False
        return all(_values_equal(left[k], right.get(k)) for k in left)

    if isinstance(left, list):
        if len(left) != len(right):
            return False
        return all(_values_equal(l, r) for l, r in zip(left, right))

    return left == right


# =============================================================================
# Operator Registry
# =============================================================================

BOOLEAN_OPERATORS = {
    "and": boolean_and,
    "or": boolean_or,
    "xor": boolean_xor,
    "implies": boolean_implies,
    "not": boolean_not,
}

COMPARISON_OPERATORS = {
    "=": equals,
    "!=": not_equals,
    "<": less_than,
    ">": greater_than,
    "<=": less_or_equal,
    ">=": greater_or_equal,
    "~": equivalent,
    "!~": not_equivalent,
}

COLLECTION_OPERATORS = {
    "|": union,
    "in": membership,
    "contains": contains,
}

ALL_OPERATORS = {
    **BOOLEAN_OPERATORS,
    **COMPARISON_OPERATORS,
    **COLLECTION_OPERATORS,
}
