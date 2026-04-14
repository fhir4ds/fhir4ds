"""
FHIRPath Existence and Quantifier Functions

Implements existence, quantifier, and counting functions as defined in the FHIRPath specification.

Existence functions:
- empty(): Returns true if the collection is empty
- exists(): Returns true if the collection has any elements
- exists(criteria): Returns true if any element matches criteria

Quantifier functions:
- all(criteria): Returns true if all elements satisfy criteria
- allTrue(): Returns true if all elements are true
- allFalse(): Returns true if all elements are false
- anyTrue(): Returns true if any element is true
- anyFalse(): Returns true if any element is false

Counting functions:
- count(): Returns the number of elements
- distinct(): Returns unique elements

Key FHIRPath semantics:
- {}.empty() -> true
- {}.exists() -> false
- {}.count() -> 0
- all() on empty collection returns true (vacuous truth)

Reference: https://hl7.org/fhirpath/#existence
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Callable

from ..collection import FHIRPathCollection, EMPTY, EmptyCollectionSentinel

if TYPE_CHECKING:
    pass

_logger = logging.getLogger(__name__)


# =============================================================================
# Existence Functions
# =============================================================================


def empty(collection: FHIRPathCollection) -> FHIRPathCollection:
    """
    Returns true if the input collection is empty.

    FHIRPath: empty() : boolean

    FHIRPath semantics:
    - {}.empty() -> true
    - [x].empty() -> false
    - [x, y].empty() -> false

    Args:
        collection: The input collection.

    Returns:
        Collection containing true if empty, false otherwise.

    Example:
        >>> empty(FHIRPathCollection([]))
        FHIRPathCollection([True])
        >>> empty(FHIRPathCollection([1]))
        FHIRPathCollection([False])
    """
    return FHIRPathCollection([collection.is_empty])


def exists(collection: FHIRPathCollection) -> FHIRPathCollection:
    """
    Returns true if the collection has any elements.

    FHIRPath: exists() : boolean

    FHIRPath semantics:
    - {}.exists() -> false
    - [x].exists() -> true
    - [x, y].exists() -> true

    Note: This is equivalent to empty().not() but more intuitive.

    Args:
        collection: The input collection.

    Returns:
        Collection containing true if non-empty, false otherwise.

    Example:
        >>> exists(FHIRPathCollection([]))
        FHIRPathCollection([False])
        >>> exists(FHIRPathCollection([1]))
        FHIRPathCollection([True])
    """
    return FHIRPathCollection([not collection.is_empty])


def exists_with_criteria(
    collection: FHIRPathCollection,
    criteria: Callable[[Any], bool] | str,
    evaluator: Callable[[str, Any], Any] | None = None,
) -> FHIRPathCollection:
    """
    Returns true if any element in the collection matches the criteria.

    FHIRPath: exists(criteria : expression) : boolean

    FHIRPath semantics:
    - {}.exists(X) -> false
    - [a, b, c].exists(X) -> true if any of a, b, c matches
    - Short-circuits on first match

    Args:
        collection: The input collection.
        criteria: Either a callable predicate or a FHIRPath expression string.
        evaluator: Optional evaluator function for expression strings.

    Returns:
        Collection containing true if any element matches, false otherwise.

    Example:
        >>> exists_with_criteria(FHIRPathCollection([1, 2, 3]), lambda x: x > 2)
        FHIRPathCollection([True])
        >>> exists_with_criteria(FHIRPathCollection([1, 2, 3]), lambda x: x > 5)
        FHIRPathCollection([False])
    """
    if collection.is_empty:
        return FHIRPathCollection([False])

    if callable(criteria):
        # Use predicate directly - short-circuit on first match
        for item in collection.values:
            try:
                if criteria(item):
                    return FHIRPathCollection([True])
            except (ValueError, TypeError, KeyError, AttributeError) as e:
                _logger.warning("exists() criteria evaluation failed for item: %s", e)
                # Error in evaluation - skip this item
                continue
        return FHIRPathCollection([False])

    elif evaluator is not None and isinstance(criteria, str):
        # Evaluate expression against each element
        for item in collection.values:
            try:
                eval_result = evaluator(criteria, item)
                if _is_truthy(eval_result):
                    return FHIRPathCollection([True])
            except (ValueError, TypeError, KeyError, AttributeError) as e:
                _logger.warning("exists() expression evaluation failed for '%s': %s", criteria, e)
                # Error in evaluation - skip this item
                continue
        return FHIRPathCollection([False])

    else:
        raise ValueError("criteria must be callable or evaluator must be provided for string criteria")


# =============================================================================
# Quantifier Functions
# =============================================================================


def all_criteria(
    collection: FHIRPathCollection,
    criteria: Callable[[Any], bool] | str,
    evaluator: Callable[[str, Any], Any] | None = None,
) -> FHIRPathCollection:
    """
    Returns true if all elements in the collection satisfy the criteria.

    FHIRPath: all(criteria : expression) : boolean

    FHIRPath semantics:
    - {}.all(X) -> true (vacuous truth)
    - [a].all(X) -> true if a satisfies X
    - [a, b, c].all(X) -> true if all satisfy X
    - Short-circuits on first failure

    Note: Empty collection returns true (vacuous truth).

    Args:
        collection: The input collection.
        criteria: Either a callable predicate or a FHIRPath expression string.
        evaluator: Optional evaluator function for expression strings.

    Returns:
        Collection containing true if all elements satisfy criteria.

    Example:
        >>> all_criteria(FHIRPathCollection([2, 4, 6]), lambda x: x % 2 == 0)
        FHIRPathCollection([True])
        >>> all_criteria(FHIRPathCollection([2, 3, 4]), lambda x: x % 2 == 0)
        FHIRPathCollection([False])
        >>> all_criteria(FHIRPathCollection([]), lambda x: x > 0)
        FHIRPathCollection([True])
    """
    # Vacuous truth: empty collection returns true
    if collection.is_empty:
        return FHIRPathCollection([True])

    if callable(criteria):
        # Use predicate directly
        for item in collection.values:
            try:
                if not criteria(item):
                    return FHIRPathCollection([False])
            except (ValueError, TypeError, KeyError, AttributeError) as e:
                _logger.warning("all() criteria evaluation failed for item: %s", e)
                # Error in evaluation - treat as false
                return FHIRPathCollection([False])
        return FHIRPathCollection([True])

    elif evaluator is not None and isinstance(criteria, str):
        # Evaluate expression against each element
        for item in collection.values:
            try:
                eval_result = evaluator(criteria, item)
                if not _is_truthy(eval_result):
                    return FHIRPathCollection([False])
            except (ValueError, TypeError, KeyError, AttributeError) as e:
                _logger.warning("all() expression evaluation failed for '%s': %s", criteria, e)
                # Error in evaluation - treat as false
                return FHIRPathCollection([False])
        return FHIRPathCollection([True])

    else:
        raise ValueError("criteria must be callable or evaluator must be provided for string criteria")


def all_true(collection: FHIRPathCollection) -> FHIRPathCollection:
    """
    Returns true if all elements in the collection are true.

    FHIRPath: allTrue() : boolean

    FHIRPath semantics:
    - {}.allTrue() -> true (vacuous truth)
    - [true].allTrue() -> true
    - [true, false].allTrue() -> false
    - [true, true].allTrue() -> true
    - Non-boolean values are evaluated for truthiness

    Args:
        collection: The input collection.

    Returns:
        Collection containing true if all elements are true.

    Example:
        >>> all_true(FHIRPathCollection([True, True]))
        FHIRPathCollection([True])
        >>> all_true(FHIRPathCollection([True, False]))
        FHIRPathCollection([False])
        >>> all_true(FHIRPathCollection([]))
        FHIRPathCollection([True])
    """
    # Vacuous truth: empty collection returns true
    if collection.is_empty:
        return FHIRPathCollection([True])

    for item in collection.values:
        # Check truthiness, but be explicit about boolean comparison
        if not _is_boolean_true(item):
            return FHIRPathCollection([False])

    return FHIRPathCollection([True])


def all_false(collection: FHIRPathCollection) -> FHIRPathCollection:
    """
    Returns true if all elements in the collection are false.

    FHIRPath: allFalse() : boolean

    FHIRPath semantics:
    - {}.allFalse() -> true (vacuous truth)
    - [false].allFalse() -> true
    - [true, false].allFalse() -> false
    - [false, false].allFalse() -> true
    - Non-boolean values are evaluated for truthiness

    Args:
        collection: The input collection.

    Returns:
        Collection containing true if all elements are false.

    Example:
        >>> all_false(FHIRPathCollection([False, False]))
        FHIRPathCollection([True])
        >>> all_false(FHIRPathCollection([True, False]))
        FHIRPathCollection([False])
        >>> all_false(FHIRPathCollection([]))
        FHIRPathCollection([True])
    """
    # Vacuous truth: empty collection returns true
    if collection.is_empty:
        return FHIRPathCollection([True])

    for item in collection.values:
        if not _is_boolean_false(item):
            return FHIRPathCollection([False])

    return FHIRPathCollection([True])


def any_true(collection: FHIRPathCollection) -> FHIRPathCollection:
    """
    Returns true if any element in the collection is true.

    FHIRPath: anyTrue() : boolean

    FHIRPath semantics:
    - {}.anyTrue() -> false
    - [true].anyTrue() -> true
    - [true, false].anyTrue() -> true
    - [false, false].anyTrue() -> false
    - Short-circuits on first true
    - Non-boolean values are evaluated for truthiness

    Args:
        collection: The input collection.

    Returns:
        Collection containing true if any element is true.

    Example:
        >>> any_true(FHIRPathCollection([False, True]))
        FHIRPathCollection([True])
        >>> any_true(FHIRPathCollection([False, False]))
        FHIRPathCollection([False])
        >>> any_true(FHIRPathCollection([]))
        FHIRPathCollection([False])
    """
    # Empty collection returns false
    if collection.is_empty:
        return FHIRPathCollection([False])

    for item in collection.values:
        if _is_boolean_true(item):
            return FHIRPathCollection([True])

    return FHIRPathCollection([False])


def any_false(collection: FHIRPathCollection) -> FHIRPathCollection:
    """
    Returns true if any element in the collection is false.

    FHIRPath: anyFalse() : boolean

    FHIRPath semantics:
    - {}.anyFalse() -> false
    - [false].anyFalse() -> true
    - [true, false].anyFalse() -> true
    - [true, true].anyFalse() -> false
    - Short-circuits on first false
    - Non-boolean values are evaluated for truthiness

    Args:
        collection: The input collection.

    Returns:
        Collection containing true if any element is false.

    Example:
        >>> any_false(FHIRPathCollection([True, False]))
        FHIRPathCollection([True])
        >>> any_false(FHIRPathCollection([True, True]))
        FHIRPathCollection([False])
        >>> any_false(FHIRPathCollection([]))
        FHIRPathCollection([False])
    """
    # Empty collection returns false
    if collection.is_empty:
        return FHIRPathCollection([False])

    for item in collection.values:
        if _is_boolean_false(item):
            return FHIRPathCollection([True])

    return FHIRPathCollection([False])


# =============================================================================
# Counting Functions
# =============================================================================


def count(collection: FHIRPathCollection) -> FHIRPathCollection:
    """
    Returns the number of elements in the collection.

    FHIRPath: count() : integer

    FHIRPath semantics:
    - {}.count() -> 0
    - [x].count() -> 1
    - [x, y, z].count() -> 3

    Note: Unlike empty() and exists(), count() always returns a value
    (never an empty collection).

    Args:
        collection: The input collection.

    Returns:
        Collection containing the count of elements.

    Example:
        >>> count(FHIRPathCollection([]))
        FHIRPathCollection([0])
        >>> count(FHIRPathCollection([1, 2, 3]))
        FHIRPathCollection([3])
    """
    return FHIRPathCollection([len(collection)])


def distinct(collection: FHIRPathCollection) -> FHIRPathCollection:
    """
    Returns a collection containing only unique elements.

    FHIRPath: distinct() : collection

    FHIRPath semantics:
    - {}.distinct() -> {}
    - [x].distinct() -> [x]
    - [x, x, y].distinct() -> [x, y]
    - Uniqueness is based on equality comparison
    - Order is preserved (first occurrence kept)

    Note: This delegates to the collection's distinct() method.

    Args:
        collection: The input collection.

    Returns:
        Collection with duplicates removed.

    Example:
        >>> distinct(FHIRPathCollection([1, 2, 1, 3, 2]))
        FHIRPathCollection([1, 2, 3])
        >>> distinct(FHIRPathCollection([]))
        FHIRPathCollection([])
    """
    return collection.distinct()


# =============================================================================
# Helper Functions
# =============================================================================


def _is_truthy(value: Any) -> bool:
    """
    Check if a value is truthy in FHIRPath semantics.

    FHIRPath considers a value truthy if:
    - It's a boolean true
    - It's a non-empty collection containing true
    - It's a non-empty collection (for non-boolean values)

    Args:
        value: Any value to check.

    Returns:
        True if the value is considered truthy.
    """
    if value is None:
        return False

    if isinstance(value, bool):
        return value

    if isinstance(value, FHIRPathCollection):
        if value.is_empty:
            return False
        if value.is_singleton:
            return _is_truthy(value.singleton_value)
        # Non-empty collection is truthy
        return True

    if isinstance(value, list):
        if not value:
            return False
        if len(value) == 1:
            return _is_truthy(value[0])
        return True

    if isinstance(value, EmptyCollectionSentinel):
        return False

    # For other values, use Python truthiness
    return bool(value)


def _is_boolean_true(value: Any) -> bool:
    """
    Check if a value is specifically boolean true.

    FHIRPath allTrue/anyTrue expect actual boolean true values,
    not just truthy values.

    Args:
        value: Any value to check.

    Returns:
        True only if value is boolean True.
    """
    if isinstance(value, bool):
        return value is True
    # Non-boolean values are not considered "true" for allTrue/anyTrue
    return False


def _is_boolean_false(value: Any) -> bool:
    """
    Check if a value is specifically boolean false.

    FHIRPath allFalse/anyFalse expect actual boolean false values,
    not just falsy values.

    Args:
        value: Any value to check.

    Returns:
        True only if value is boolean False.
    """
    if isinstance(value, bool):
        return value is False
    # Non-boolean values are not considered "false" for allFalse/anyFalse
    # They are "other" - neither true nor false
    return False


# =============================================================================
# Function Registry for Evaluator Integration
# =============================================================================

EXISTENCE_FUNCTIONS = {
    # No-argument existence functions
    "empty": empty,
    "exists": exists,
    "count": count,
    "distinct": distinct,

    # Boolean quantifier functions
    "allTrue": all_true,
    "allFalse": all_false,
    "anyTrue": any_true,
    "anyFalse": any_false,

    # Criteria-based functions (require expression evaluator)
    # These are registered differently as they need expression handling
}
