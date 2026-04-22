"""
Vectorized CQL List Operation UDFs

Implements CQL list functions that require complex logic:
- SingletonFrom(list) - Return single element or NULL
- ElementAt(list, index) - Get element at 0-based index

Supports both scalar (row-by-row) and Arrow vectorized implementations.
"""

from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING, Any

import duckdb
import pyarrow as pa

if TYPE_CHECKING:
    import duckdb as duckdb_types

logger = logging.getLogger(__name__)

# Feature flag for rollback
_USE_ARROW = os.environ.get("CQL_USE_ARROW_UDFS", "1") == "1"


def _arrow_scalar_as_py(scalar: pa.Scalar) -> Any:
    """Convert an Arrow scalar to a Python value without batch materialization."""
    return scalar.as_py() if scalar.is_valid else None


# ========================================
# Scalar versions (fallback)
# ========================================

def singletonFrom_scalar(lst: list[Any] | None) -> Any:
    """
    CQL SingletonFrom(list) - scalar version.

    Returns the single element if list has exactly 1 element.
    Returns NULL if list is empty or NULL.
    Raises ValueError if list has >1 elements (CQL §20.30).
    """
    if lst is None:
        return None
    if len(lst) == 0:
        return None
    if len(lst) == 1:
        return lst[0]
    # >1 element: raise runtime error per CQL spec §20.30
    raise ValueError(
        f"SingletonFrom: Expected a list with at most one element, "
        f"but found a list with {len(lst)} elements."
    )


def elementAt_scalar(lst: list[Any] | None, index: int | None) -> Any:
    """
    CQL ElementAt(list, index) - scalar version.

    CQL uses 0-based indexing. DuckDB uses 1-based indexing internally.
    Returns NULL if list is NULL, empty, or index is out of bounds.
    """
    if lst is None or len(lst) == 0:
        return None
    if index is None:
        return None

    # Handle negative indices: -1 means last element, -2 second-to-last, etc.
    if index < 0:
        index = len(lst) + index
        if index < 0:
            return None

    # Check bounds (0-based)
    if index < 0 or index >= len(lst):
        return None

    return lst[index]


# ========================================
# Arrow vectorized versions
# ========================================

def singletonFrom_arrow(lists: pa.Array) -> pa.Array:
    """
    CQL SingletonFrom(list) - vectorized Arrow version.

    Returns the single element if list has exactly 1 element.
    Returns NULL if list is empty, NULL, or has >1 elements.
    """
    results = []

    for list_scalar in lists:
        lst = _arrow_scalar_as_py(list_scalar)
        if lst is None:
            results.append(None)
            continue
        if len(lst) == 0:
            results.append(None)
            continue
        if len(lst) == 1:
            results.append(lst[0])
            continue
        # >1 element: return NULL and log warning
        logger.warning(
            "SingletonFrom called on list with %d elements; returning NULL per CQL spec",
            len(lst)
        )
        results.append(None)

    # Infer the output type from the input list element type
    # For mixed types, use a generic type
    if len(results) == 0 or all(r is None for r in results):
        return pa.nulls(len(lists), type=pa.null())

    # Try to infer type from non-null values
    non_null_results = [r for r in results if r is not None]
    if non_null_results:
        sample = non_null_results[0]
        if isinstance(sample, bool):
            return pa.array(results, type=pa.bool_())
        elif isinstance(sample, str):
            return pa.array(results, type=pa.string())
        elif isinstance(sample, int):
            return pa.array(results, type=pa.int64())
        elif isinstance(sample, float):
            return pa.array(results, type=pa.float64())

    # Fallback to generic object type
    return pa.array(results)


def elementAt_arrow(lists: pa.Array, indices: pa.Array) -> pa.Array:
    """
    CQL ElementAt(list, index) - vectorized Arrow version.

    CQL uses 0-based indexing.
    Returns NULL if list is NULL, empty, or index is out of bounds.
    """
    results = []

    for list_scalar, index_scalar in zip(lists, indices):
        lst = _arrow_scalar_as_py(list_scalar)
        idx = _arrow_scalar_as_py(index_scalar)
        if lst is None or len(lst) == 0:
            results.append(None)
            continue
        if idx is None:
            results.append(None)
            continue

        # Handle negative indices: -1 means last element, -2 second-to-last, etc.
        if idx < 0:
            idx = len(lst) + idx
            if idx < 0:
                results.append(None)
                continue

        # Check bounds (0-based)
        if idx < 0 or idx >= len(lst):
            results.append(None)
            continue

        results.append(lst[idx])

    # Infer the output type from the input list element type
    if len(results) == 0 or all(r is None for r in results):
        return pa.nulls(len(lists), type=pa.null())

    # Try to infer type from non-null values
    non_null_results = [r for r in results if r is not None]
    if non_null_results:
        sample = non_null_results[0]
        if isinstance(sample, bool):
            return pa.array(results, type=pa.bool_())
        elif isinstance(sample, str):
            return pa.array(results, type=pa.string())
        elif isinstance(sample, int):
            return pa.array(results, type=pa.int64())
        elif isinstance(sample, float):
            return pa.array(results, type=pa.float64())

    # Fallback to generic object type
    return pa.array(results)


# ========================================
# Registration with feature flag
# ========================================

def registerListUdfs(con: "duckdb.DuckDBPyConnection") -> None:
    """Register list UDFs with Arrow or scalar based on feature flag."""
    # Use scalar versions only - Arrow requires explicit return types which
    # is difficult for polymorphic list element access (can return any type)
    # Use VARCHAR as return type for polymorphic functions
    # null_handling="special" needed because these functions return NULL for empty/multiple
    con.create_function(
        "SingletonFrom",
        singletonFrom_scalar,
        return_type="VARCHAR",
        null_handling="special"
    )
    con.create_function(
        "ElementAt",
        elementAt_scalar,
        return_type="VARCHAR",
        null_handling="special"
    )
    # jsonConcat for CQL union with JSON resources
    # Return type is VARCHAR[] (list of strings) to work with list_filter
    con.create_function(
        "jsonConcat",
        jsonConcat_scalar,
        return_type='VARCHAR[]',
        null_handling="special"
    )


def jsonConcat_scalar(left: Any, right: Any) -> list[Any]:
    """
    Concatenate two values into a list, handling JSON types.

    This is used for CQL union operator when dealing with FHIR JSON resources.
    - If both are lists, concatenate them
    - If one is a list and the other is a scalar, append the scalar
    - If both are scalars, create a 2-element list
    - NULL values are skipped
    """
    result = []

    # Handle left
    if left is not None:
        if isinstance(left, list):
            result.extend(left)
        else:
            result.append(left)

    # Handle right
    if right is not None:
        if isinstance(right, list):
            result.extend(right)
        else:
            result.append(right)

    return result


# Legacy aliases for backward compatibility
singletonFrom = singletonFrom_scalar
elementAt = elementAt_scalar
jsonConcat = jsonConcat_scalar


__all__ = [
    # Feature flag
    "_USE_ARROW",
    # Registration
    "registerListUdfs",
    # Scalar functions
    "singletonFrom_scalar",
    "elementAt_scalar",
    "jsonConcat_scalar",
    # Arrow functions
    "singletonFrom_arrow",
    "elementAt_arrow",
    # Legacy aliases
    "singletonFrom",
    "elementAt",
    "jsonConcat",
]
