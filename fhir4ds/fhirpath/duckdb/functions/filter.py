"""
FHIRPath Filter and Subsetting Functions

Implements filtering and subsetting operations as defined in the FHIRPath specification.

Filter functions:
- where(criteria): Filter collection by criteria expression
- select(projection): Project each element through an expression
- repeat(expression): Iterate expression until no new results

Subsetting functions:
- first(): Get first element (or empty if collection is empty)
- last(): Get last element (or empty if collection is empty)
- tail(n): Get all elements except first n
- take(n): Get first n elements
- skip(n): Skip first n elements
- ofType(type): Filter by FHIR type

Reference: https://hl7.org/fhirpath/#filtering-and-projection
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Callable

from ..collection import FHIRPathCollection, EMPTY, EmptyCollectionSentinel
from ..errors import FHIRPathError

if TYPE_CHECKING:
    pass

_logger = logging.getLogger(__name__)


# FHIR type name to Python type mapping
FHIR_TYPE_MAP: dict[str, type] = {
    "boolean": bool,
    "integer": int,
    "decimal": float,
    "string": str,
    "date": str,
    "dateTime": str,
    "time": str,
    "Quantity": dict,
    "Coding": dict,
    "CodeableConcept": dict,
    "Resource": dict,
}

# Reverse mapping for type inference
PYTHON_TO_FHIR_TYPE: dict[type, str] = {
    bool: "boolean",
    int: "integer",
    float: "decimal",
    str: "string",
    dict: "Resource",
    list: "Collection",
}


def where(
    collection: FHIRPathCollection,
    criteria: Callable[[Any], bool] | str,
    evaluator: Callable[[str, Any], Any] | None = None,
) -> FHIRPathCollection | EmptyCollectionSentinel:
    """
    Filter a collection by a criteria expression.

    FHIRPath semantics:
    - Empty collection returns empty: {}.where(X) -> {}
    - Each element is evaluated against the criteria
    - Elements where criteria is true are retained

    Args:
        collection: The collection to filter.
        criteria: Either a callable predicate or a FHIRPath expression string.
        evaluator: Optional evaluator function for expression strings.

    Returns:
        Filtered collection or EMPTY if input is empty.

    Example:
        >>> col = FHIRPathCollection([1, 2, 3, 4, 5])
        >>> where(col, lambda x: x > 2)
        FHIRPathCollection([3, 4, 5])
    """
    if collection.is_empty:
        return EMPTY

    if callable(criteria):
        results = []
        for item in collection.values:
            if _criteria_result_is_true(criteria(item)):
                results.append(item)
        return FHIRPathCollection(results)
    elif evaluator is not None and isinstance(criteria, str):
        # Evaluate expression against each element
        results = []
        for item in collection.values:
            try:
                eval_result = evaluator(criteria, item)
                if _criteria_result_is_true(eval_result):
                    results.append(item)
            except (ValueError, TypeError, KeyError, AttributeError) as e:
                raise FHIRPathError(f"where() expression evaluation failed for '{criteria}': {e}") from e
        return FHIRPathCollection(results)
    else:
        raise ValueError("criteria must be callable or evaluator must be provided for string criteria")


def _criteria_result_is_true(result: Any) -> bool:
    """Return whether a where() criterion is the singleton Boolean true."""
    if result is None or isinstance(result, EmptyCollectionSentinel):
        return False
    if isinstance(result, FHIRPathCollection):
        if result.is_empty:
            return False
        values = result.values
    elif isinstance(result, list):
        values = result
    else:
        values = [result]

    if len(values) == 0:
        return False
    if len(values) != 1 or not isinstance(values[0], bool):
        raise FHIRPathError("where() criteria must evaluate to a singleton Boolean")
    return values[0]


def select(
    collection: FHIRPathCollection,
    projection: Callable[[Any], Any] | str,
    evaluator: Callable[[str, Any], Any] | None = None,
) -> FHIRPathCollection | EmptyCollectionSentinel:
    """
    Project each element through an expression.

    FHIRPath semantics:
    - Empty collection returns empty: {}.select(X) -> {}
    - Each element is projected, results are flattened
    - Empty results are excluded

    Args:
        collection: The collection to project.
        projection: Either a callable or a FHIRPath expression string.
        evaluator: Optional evaluator function for expression strings.

    Returns:
        Projected collection or EMPTY if input is empty.

    Example:
        >>> col = FHIRPathCollection([1, 2, 3])
        >>> select(col, lambda x: x * 2)
        FHIRPathCollection([2, 4, 6])
    """
    if collection.is_empty:
        return EMPTY

    results = []

    if callable(projection):
        for item in collection.values:
            result = projection(item)
            _flatten_result(results, result)
    elif evaluator is not None and isinstance(projection, str):
        for item in collection.values:
            try:
                result = evaluator(projection, item)
                _flatten_result(results, result)
            except (ValueError, TypeError, KeyError, AttributeError) as e:
                raise FHIRPathError(f"select() projection evaluation failed for '{projection}': {e}") from e
    else:
        raise ValueError("projection must be callable or evaluator must be provided for string projection")

    return FHIRPathCollection(results)


def _flatten_result(results: list, result: Any) -> None:
    """Helper to flatten results into a list, handling FHIRPath collections."""
    if result is None:
        return
    if isinstance(result, FHIRPathCollection):
        if not result.is_empty:
            results.extend(result.values)
    elif isinstance(result, list):
        for item in result:
            if item is not None:
                results.append(item)
    elif isinstance(result, EmptyCollectionSentinel):
        pass  # Skip empty
    else:
        results.append(result)


def repeat(
    collection: FHIRPathCollection,
    expression: Callable[[Any], Any] | str,
    evaluator: Callable[[str, Any], Any] | None = None,
    max_iterations: int = 1000,
) -> FHIRPathCollection | EmptyCollectionSentinel:
    """
    Iterate an expression until no new results are found.

    FHIRPath semantics:
    - Empty collection returns empty: {}.repeat(X) -> {}
    - Expression is applied to each element
    - New projection results are added to the working collection
    - Process repeats until no new results
    - Final result includes discovered projection results, not the input seeds

    Args:
        collection: The starting collection.
        expression: Either a callable or a FHIRPath expression string.
        evaluator: Optional evaluator function for expression strings.
        max_iterations: Safety limit to prevent infinite loops.

    Returns:
        Collection of discovered projection results or EMPTY if input is empty.

    Example:
        >>> # Get all descendant nodes
        >>> col = FHIRPathCollection([{"a": {"b": 1}}])
        >>> repeat(col, lambda x: x.values() if isinstance(x, dict) else None)
        FHIRPathCollection([{"b": 1}, 1])
    """
    if collection.is_empty:
        return EMPTY

    all_results: list[Any] = []
    current_items = list(collection.values)

    iteration = 0
    while current_items:
        if iteration >= max_iterations:
            raise FHIRPathError("repeat() maximum iteration limit exceeded")
        iteration += 1
        new_items = []

        for item in current_items:
            try:
                if callable(expression):
                    result = expression(item)
                elif evaluator is not None and isinstance(expression, str):
                    result = evaluator(expression, item)
                else:
                    raise ValueError("expression must be callable or evaluator must be provided")

                # Process result
                if isinstance(result, FHIRPathCollection):
                    result_items = result.values
                elif isinstance(result, list):
                    result_items = result
                elif isinstance(result, EmptyCollectionSentinel):
                    result_items = []
                elif result is not None:
                    result_items = [result]
                else:
                    result_items = []

                for new_item in result_items:
                    if not _contains_equal(all_results, new_item) and not _contains_equal(new_items, new_item):
                        all_results.append(new_item)
                        new_items.append(new_item)

            except (ValueError, TypeError, KeyError, AttributeError) as e:
                raise FHIRPathError(f"repeat() expression evaluation failed: {e}") from e

        current_items = new_items

    return FHIRPathCollection(all_results)


def _contains_equal(items: list[Any], candidate: Any) -> bool:
    """Check membership using FHIRPath `=` semantics."""
    from ...engine.invocations import equality as equality_invocations

    for item in items:
        if equality_invocations.equality({}, [item], [candidate]) is True:
            return True
    return False


def first(collection: FHIRPathCollection) -> Any:
    """
    Get the first element of a collection.

    FHIRPath semantics:
    - Returns the single first element if collection is non-empty
    - Returns empty collection {} if input is empty

    Note: In FHIRPath, first() returns a singleton value, not a collection.
    This function returns the value directly or None for empty.

    Args:
        collection: The collection.

    Returns:
        First element or None if empty.

    Example:
        >>> first(FHIRPathCollection([1, 2, 3]))
        1
        >>> first(FHIRPathCollection([]))
        None
    """
    return collection.first()


def last(collection: FHIRPathCollection) -> Any:
    """
    Get the last element of a collection.

    FHIRPath semantics:
    - Returns the single last element if collection is non-empty
    - Returns empty collection {} if input is empty

    Note: In FHIRPath, last() returns a singleton value, not a collection.
    This function returns the value directly or None for empty.

    Args:
        collection: The collection.

    Returns:
        Last element or None if empty.

    Example:
        >>> last(FHIRPathCollection([1, 2, 3]))
        3
        >>> last(FHIRPathCollection([]))
        None
    """
    return collection.last()


def tail(collection: FHIRPathCollection, n: int = 1) -> FHIRPathCollection:
    """
    Get all elements except the first n.

    FHIRPath semantics:
    - Empty collection returns empty: {}.tail(n) -> {}
    - If n >= collection size, returns empty collection
    - n defaults to 1 if not specified

    Note: In FHIRPath, tail() returns a collection.

    Args:
        collection: The collection.
        n: Number of elements to skip from the start.

    Returns:
        Collection without the first n elements.

    Example:
        >>> tail(FHIRPathCollection([1, 2, 3, 4]), 2)
        FHIRPathCollection([3, 4])
        >>> tail(FHIRPathCollection([1, 2]), 1)
        FHIRPathCollection([2])
    """
    if collection.is_empty:
        return FHIRPathCollection([])

    if n <= 0:
        return FHIRPathCollection(collection.values[:])

    return FHIRPathCollection(collection.values[n:])


def take(collection: FHIRPathCollection, n: int) -> FHIRPathCollection:
    """
    Get the first n elements.

    FHIRPath semantics:
    - Empty collection returns empty: {}.take(n) -> {}
    - If n > collection size, returns all elements
    - If n <= 0, returns empty collection

    Args:
        collection: The collection.
        n: Number of elements to take.

    Returns:
        Collection with at most n elements.

    Example:
        >>> take(FHIRPathCollection([1, 2, 3, 4]), 2)
        FHIRPathCollection([1, 2])
        >>> take(FHIRPathCollection([1, 2]), 5)
        FHIRPathCollection([1, 2])
    """
    if collection.is_empty:
        return FHIRPathCollection([])

    if n <= 0:
        return FHIRPathCollection([])

    return FHIRPathCollection(collection.values[:n])


def skip(collection: FHIRPathCollection, n: int) -> FHIRPathCollection:
    """
    Skip the first n elements.

    FHIRPath semantics:
    - Empty collection returns empty: {}.skip(n) -> {}
    - If n >= collection size, returns empty collection
    - If n <= 0, returns all elements

    Args:
        collection: The collection.
        n: Number of elements to skip.

    Returns:
        Collection without the first n elements.

    Example:
        >>> skip(FHIRPathCollection([1, 2, 3, 4]), 2)
        FHIRPathCollection([3, 4])
        >>> skip(FHIRPathCollection([1, 2]), 5)
        FHIRPathCollection([])
    """
    if collection.is_empty:
        return FHIRPathCollection([])

    if n <= 0:
        return FHIRPathCollection(collection.values[:])

    return FHIRPathCollection(collection.values[n:])


def of_type(collection: FHIRPathCollection, type_name: str) -> FHIRPathCollection:
    """
    Filter collection by FHIR type.

    FHIRPath semantics:
    - Empty collection returns empty: {}.ofType(T) -> {}
    - Filters to only elements of the specified type
    - Type names are case-sensitive

    Supported types:
    - Primitive: boolean, integer, decimal, string, date, dateTime, time
    - Complex: Quantity, Coding, CodeableConcept, Resource

    Args:
        collection: The collection to filter.
        type_name: FHIR type name (e.g., 'string', 'integer', 'Resource').

    Returns:
        Collection containing only elements of the specified type.

    Example:
        >>> of_type(FHIRPathCollection([1, 'a', 2, 'b']), 'integer')
        FHIRPathCollection([1, 2])
        >>> of_type(FHIRPathCollection([{'a': 1}, 'str']), 'Resource')
        FHIRPathCollection([{'a': 1}])
    """
    if collection.is_empty:
        return FHIRPathCollection([])

    expected_type = FHIR_TYPE_MAP.get(type_name)

    results = []

    for item in collection.values:
        if isinstance(item, dict) and "resourceType" in item:
            if _is_fhir_subtype(item["resourceType"], type_name):
                results.append(item)
        elif expected_type is dict:
            if isinstance(item, dict):
                if _is_fhir_complex_type(item, type_name):
                    results.append(item)
        elif expected_type is not None and isinstance(item, expected_type):
            # Handle bool/int overlap (bool is subclass of int)
            if expected_type is int and isinstance(item, bool):
                continue
            if expected_type is float and isinstance(item, bool):
                continue
            results.append(item)

    return FHIRPathCollection(results)


def _is_fhir_subtype(actual_type: str, requested_type: str) -> bool:
    if actual_type == requested_type:
        return True
    try:
        from ..fhir_model import get_fhir_model

        type2parent = get_fhir_model().get("type2Parent", {})
    except Exception:
        type2parent = {}

    parent = type2parent.get(actual_type)
    while parent:
        if parent == requested_type:
            return True
        parent = type2parent.get(parent)
    return False


def _is_fhir_complex_type(item: dict, type_name: str) -> bool:
    """Check if a dict represents a specific FHIR complex type."""
    # FHIR complex types have specific structures
    type_signatures = {
        "Quantity": ["value", "unit", "system", "code"],
        "Coding": ["system", "code", "display"],
        "CodeableConcept": ["coding", "text"],
    }

    if type_name not in type_signatures:
        return False

    # Check if item has characteristic fields for this type
    signature = type_signatures[type_name]
    return any(field in item for field in signature)


def infer_fhir_type(value: Any) -> str | None:
    """
    Infer the FHIR type name from a Python value.

    Args:
        value: A Python value.

    Returns:
        FHIR type name or None if cannot determine.

    Example:
        >>> infer_fhir_type(42)
        'integer'
        >>> infer_fhir_type(True)
        'boolean'
        >>> infer_fhir_type({'resourceType': 'Patient'})
        'Patient'
    """
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "decimal"
    if isinstance(value, str):
        # Could be date, dateTime, time, or string
        # For simplicity, return string
        return "string"
    if isinstance(value, dict):
        # Check for resourceType
        if "resourceType" in value:
            return value["resourceType"]
        # Check for known complex types
        if _is_fhir_complex_type(value, "Quantity"):
            return "Quantity"
        if _is_fhir_complex_type(value, "Coding"):
            return "Coding"
        if _is_fhir_complex_type(value, "CodeableConcept"):
            return "CodeableConcept"
        return "Resource"
    return None
