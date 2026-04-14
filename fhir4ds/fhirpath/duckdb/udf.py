"""
Arrow UDF Implementation

Provides the vectorized FHIRPath UDF using PyArrow for efficient
batch processing of FHIR resources.
"""

from __future__ import annotations

import logging
import os
from functools import lru_cache

import orjson
from typing import TYPE_CHECKING

import pyarrow as pa
import pyarrow.compute as pc

from .evaluator import FHIRPathEvaluator
from .errors import FHIRPathError, FHIRPathSyntaxError

if TYPE_CHECKING:
    from collections.abc import Sequence

_logger = logging.getLogger(__name__)
_STRICT_MODE = os.environ.get("FHIRPATH_STRICT_MODE") == "1"

_VALID_BOOL_STRINGS = frozenset({"true", "false", "1", "0"})

# Cache compiled expressions for reuse
# This is shared across all UDF invocations
_EXPRESSION_CACHE_SIZE = 1024


def _parse_json(resource: str) -> dict:
    """Parse a JSON string. No caching — orjson is fast and caching returns
    mutable dicts that the evaluator may mutate, corrupting shared state."""
    return orjson.loads(resource)


def _json_default(obj: object) -> object:
    """JSON serialization fallback for types not natively supported."""
    from decimal import Decimal
    if isinstance(obj, Decimal):
        return float(obj)
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")


def _json_serialize(obj: object) -> str:
    """Serialize an object to a JSON string using orjson for performance."""
    return orjson.dumps(obj, default=_json_default).decode()


@lru_cache(maxsize=_EXPRESSION_CACHE_SIZE)
def _get_compiled_evaluator(expression: str) -> FHIRPathEvaluator:
    """
    Get a cached FHIRPathEvaluator with a compiled expression.

    Uses LRU cache to avoid re-parsing the same expressions repeatedly.

    Args:
        expression: A FHIRPath expression string.

    Returns:
        A FHIRPathEvaluator with the expression compiled.
    """
    evaluator = FHIRPathEvaluator()
    evaluator.compile(expression)
    return evaluator


# Lazily cached choice type lookup table: base_name -> list of suffixed field names
_choice_type_lookup: dict[str, list[str]] | None = None
_choice_type_lock = __import__('threading').Lock()


def _get_choice_type_lookup() -> dict[str, list[str]]:
    """Build a lookup from base property name to suffixed field names."""
    global _choice_type_lookup
    if _choice_type_lookup is None:
        with _choice_type_lock:
            if _choice_type_lookup is None:
                lookup = {}
                try:
                    from .fhir_types_generated import CHOICE_TYPES
                    for _path, field_names in CHOICE_TYPES.items():
                        # Extract base name (e.g., "Observation.value" -> "value")
                        base = _path.split(".")[-1] if "." in _path else _path
                        if base not in lookup:
                            lookup[base] = []
                        for fn in field_names:
                            if fn not in lookup[base]:
                                lookup[base].append(fn)
                except ImportError:
                    pass
                _choice_type_lookup = lookup
    return _choice_type_lookup


def _resolve_choice_type(resource_dict: dict, expression: str) -> list:
    """Resolve choice type fields that fhirpathpy misses for primitive types."""
    # Only handle simple single-segment property names
    if "." in expression or "(" in expression or "[" in expression:
        return []
    lookup = _get_choice_type_lookup()
    field_names = lookup.get(expression)
    if not field_names:
        return []
    for fn in field_names:
        val = resource_dict.get(fn)
        if val is not None:
            return [val]
    return []


def fhirpath_udf(
    resources: pa.Array,
    expressions: pa.Array,
) -> pa.Array:
    """
    Vectorized FHIRPath UDF for DuckDB.

    Evaluates FHIRPath expressions against FHIR resources in a vectorized
    manner using PyArrow for efficient batch processing.

    Args:
        resources: Arrow array of JSON strings representing FHIR resources.
        expressions: Arrow array of FHIRPath expression strings.

    Returns:
        Arrow array of lists containing the evaluation results.

    The function supports:
    - Vectorized processing of resources and expressions
    - Expression caching for repeated queries
    - Proper error handling and empty collection propagation
    - Null handling for invalid resources or expressions

    Example:
        >>> import pyarrow as pa
        >>> resources = pa.array(['{"id":"123"}', '{"id":"456"}'])
        >>> expressions = pa.array(['id', 'id'])
        >>> result = fhirpath_udf(resources, expressions)
        >>> print(result)
        [['123'], ['456']]
    """
    # Handle null inputs
    null_mask = pc.or_(
        pc.is_null(resources, nan_is_null=True),
        pc.is_null(expressions, nan_is_null=True),
    )

    # Convert to Python for processing
    # In a production implementation, we could optimize this further
    # by staying in Arrow as long as possible
    resources_py = resources.to_pylist()
    expressions_py = expressions.to_pylist()

    # Process each resource-expression pair
    results: list[list[object] | None] = []
    for i, (resource, expression) in enumerate(zip(resources_py, expressions_py)):
        # Check null mask
        if null_mask[i].as_py():
            results.append(None)
            continue

        try:
            # Parse JSON resource
            if isinstance(resource, str):
                resource_dict = _parse_json(resource)
            elif isinstance(resource, dict):
                resource_dict = resource
            else:
                results.append(None)
                continue

            # Get cached evaluator and evaluate
            evaluator = _get_compiled_evaluator(expression)
            result = evaluator.evaluate(resource_dict)

            # Convert result to list for Arrow
            if result is None:
                results.append([])
            elif isinstance(result, list):
                # Serialize complex objects to valid JSON strings
                serialized = []
                for item in result:
                    if isinstance(item, (dict, list)):
                        serialized.append(_json_serialize(item))
                    elif isinstance(item, str):
                        serialized.append(item)
                    else:
                        serialized.append(str(item))
                results.append(serialized)
            else:
                results.append([result])

        except orjson.JSONDecodeError:
            # Invalid JSON - return empty collection
            results.append([])
        except FHIRPathSyntaxError:
            # Invalid expression - return empty collection
            results.append([])
        except FHIRPathError:
            # Evaluation error - return empty collection (FHIRPath semantics)
            results.append([])
        except (ValueError, TypeError, KeyError, AttributeError, IndexError, NotImplementedError) as e:
            _logger.warning("FHIRPath evaluation failed for '%s': %s", expression, e)
            if _STRICT_MODE:
                raise
            # Unexpected error - return empty collection
            results.append([])

    # Convert results back to Arrow
    # Use list type with string elements (most common FHIRPath result)
    # In production, we'd use a more sophisticated type inference
    return pa.array(results, type=pa.list_(pa.string()))


def fhirpath_udf_typed(
    resources: pa.Array,
    expressions: pa.Array,
    return_type: pa.DataType = pa.list_(pa.string()),
) -> pa.Array:
    """
    Typed variant of the FHIRPath UDF.

    Allows specifying the return type for better type integration
    with DuckDB's type system.

    Args:
        resources: Arrow array of JSON strings representing FHIR resources.
        expressions: Arrow array of FHIRPath expression strings.
        return_type: The Arrow type to cast results to.

    Returns:
        Arrow array of the specified type containing evaluation results.
    """
    results = fhirpath_udf(resources, expressions)

    # Cast to requested type if different
    if results.type != return_type:
        try:
            results = results.cast(return_type)
        except (pa.ArrowInvalid, pa.ArrowNotImplementedError):
            # If cast fails, return original results
            pass

    return results


def clear_expression_cache() -> None:
    """
    Clear the compiled expression cache.

    Useful for testing or when memory needs to be reclaimed.
    """
    _get_compiled_evaluator.cache_clear()


def get_cache_info() -> tuple[int, int, int]:
    """
    Get expression cache statistics.

    Returns:
        Tuple of (hits, misses, maxsize) for the LRU cache.
    """
    info = _get_compiled_evaluator.cache_info()
    return (info.hits, info.misses, info.maxsize)


def fhirpath_scalar(resource: str | None, expression: str | None) -> list[object] | None:
    """
    Scalar FHIRPath UDF for DuckDB.

    Evaluates a FHIRPath expression against a single FHIR resource.
    This is the simpler scalar interface used by DuckDB's create_function.

    Args:
        resource: JSON string representing a FHIR resource, or None.
        expression: FHIRPath expression string, or None.

    Returns:
        List of matching values, or None if inputs are NULL.

    Example:
        >>> result = fhirpath_scalar('{"id":"123"}', 'id')
        >>> print(result)
        ['123']
    """
    # Handle null inputs
    if resource is None or expression is None:
        return None

    try:
        # Parse JSON resource
        if isinstance(resource, str):
            resource_dict = _parse_json(resource)
        elif isinstance(resource, dict):
            resource_dict = resource
        else:
            return []

        # Get cached evaluator and evaluate
        evaluator = _get_compiled_evaluator(expression)
        result = evaluator.evaluate(resource_dict)

        # Fallback: resolve choice type fields that fhirpathpy misses for primitives
        if not result and isinstance(resource_dict, dict):
            result = _resolve_choice_type(resource_dict, expression)

        # Convert result to list of strings for DuckDB
        if result is None:
            return []
        if isinstance(result, list):
            # Convert all items to strings for consistent return type
            def _to_str(item):
                if isinstance(item, str):
                    return item
                if isinstance(item, (dict, list)):
                    return _json_serialize(item)
                return str(item)
            return [_to_str(item) for item in result]
        if isinstance(result, (dict, list)):
            return [_json_serialize(result)]
        return [str(result)]

    except orjson.JSONDecodeError:
        # Invalid JSON - return empty collection
        return []
    except FHIRPathSyntaxError:
        # Invalid expression - return empty collection
        return []
    except FHIRPathError:
        # Evaluation error - return empty collection (FHIRPath semantics)
        return []
    except (ValueError, TypeError, KeyError, AttributeError, IndexError, NotImplementedError) as e:
        _logger.warning("FHIRPath scalar evaluation failed for '%s': %s", expression, e)
        if _STRICT_MODE:
            raise
        # Unexpected error - return empty collection
        return []


def fhirpath_is_valid_udf(expression: str | None) -> bool:
    """Check if a FHIRPath expression is valid."""
    if not expression or not isinstance(expression, str):
        return False
    try:
        _get_compiled_evaluator(expression)
        return True
    except (ValueError, TypeError, KeyError, AttributeError, NotImplementedError,
            FHIRPathSyntaxError, FHIRPathError):
        return False


def fhirpath_text_udf(resource: str | None, expression: str | None) -> str | None:
    """
    Convenience UDF that returns the first value as text.

    Args:
        resource: JSON string representing a FHIR resource, or None.
        expression: FHIRPath expression string, or None.

    Returns:
        First matching value as string, or None if empty/error.

    Example:
        >>> result = fhirpath_text_udf('{"id":"123"}', 'id')
        >>> print(result)
        '123'
    """
    result = fhirpath_scalar(resource, expression)
    if not result:
        return None
    val = result[0]
    if isinstance(val, (dict, list)):
        return _json_serialize(val)
    return str(val) if val is not None else None


def fhirpath_date_udf(resource: str | None, expression: str | None) -> str | None:
    """
    Convenience UDF that returns the first value as a date string.

    Args:
        resource: JSON string representing a FHIR resource, or None.
        expression: FHIRPath expression string, or None.

    Returns:
        First matching value as date string in YYYY-MM-DD format, or None if empty/error.

    Example:
        >>> result = fhirpath_date_udf('{"birthDate":"1970-01-01"}', 'birthDate')
        >>> print(result)
        '1970-01-01'
    """
    result = fhirpath_scalar(resource, expression)
    if not result:
        return None

    value = result[0]
    if isinstance(value, str):
        # Try to parse as a date
        try:
            # Handle FHIR date formats (YYYY, YYYY-MM, YYYY-MM-DD)
            if len(value) >= 10:
                # Full date
                return value[:10]
            elif len(value) == 7:
                # Month precision – day component invented as -01
                _logger.warning(
                    "Date '%s' has only month precision; padding to '%s-01'",
                    value, value,
                )
                return value + "-01"
            elif len(value) == 4:
                # Year precision – month and day invented as -01-01
                _logger.warning(
                    "Date '%s' has only year precision; padding to '%s-01-01'",
                    value, value,
                )
                return value + "-01-01"
            else:
                # Invalid format
                return None
        except (ValueError, IndexError):
            return None
    return None


def fhirpath_bool_udf(resource: str | None, expression: str | None) -> bool | None:
    """
    Convenience UDF that returns a boolean value.

    Args:
        resource: JSON string representing a FHIR resource, or None.
        expression: FHIRPath expression string, or None.

    Returns:
        Boolean value, or None if empty/error.

    Example:
        >>> result = fhirpath_bool_udf('{"active":true}', 'active')
        >>> print(result)
        True
    """
    result = fhirpath_scalar(resource, expression)
    if not result:
        return None
    val = result[0]
    if isinstance(val, bool):
        return val
    if isinstance(val, str):
        low = val.lower()
        if low not in _VALID_BOOL_STRINGS:
            _logger.warning(
                "Unexpected boolean string '%s' for expression '%s'; treating as False",
                val, expression,
            )
            return False
        return low in ("true", "1")
    if isinstance(val, (int, float)):
        if val in (0, 1, 0.0, 1.0):
            return bool(val)
        _logger.warning(
            "Unexpected numeric boolean value %r for expression '%s'; treating as bool",
            val, expression,
        )
        return bool(val)
    _logger.warning(
        "Unexpected type %s for boolean expression '%s'; treating as False",
        type(val).__name__, expression,
    )
    return False


def fhirpath_number_udf(resource: str | None, expression: str | None) -> float | None:
    """
    Convenience UDF that returns a numeric value as double.

    Args:
        resource: JSON string representing a FHIR resource, or None.
        expression: FHIRPath expression string, or None.

    Returns:
        Numeric value as float, or None if empty/error/non-numeric.

    Example:
        >>> result = fhirpath_number_udf('{"value":42}', 'value')
        >>> print(result)
        42.0
    """
    result = fhirpath_scalar(resource, expression)
    if not result:
        return None
    try:
        return float(result[0])
    except (ValueError, TypeError):
        return None


def fhirpath_json_udf(resource: str | None, expression: str | None) -> str | None:
    """
    Convenience UDF that returns the result as a JSON string.

    Args:
        resource: JSON string representing a FHIR resource, or None.
        expression: FHIRPath expression string, or None.

    Returns:
        JSON string representation of the result, or None if inputs are NULL.

    Example:
        >>> result = fhirpath_json_udf('{"name":["John","Jane"]}', 'name')
        >>> print(result)
        '["John", "Jane"]'
    """
    result = fhirpath_scalar(resource, expression)
    if result is None:
        return None
    return _json_serialize(result)


def fhirpath_timestamp_udf(resource: str | None, expression: str | None) -> str | None:
    """
    Extract a timestamp value from a FHIR resource using FHIRPath.

    Like fhirpath_date_udf but returns timestamp string for datetime fields.

    Args:
        resource: FHIR resource as JSON string
        expression: FHIRPath expression to evaluate

    Returns:
        Timestamp string (ISO 8601 format) or None
    """
    if resource is None or expression is None:
        return None
    try:
        result = fhirpath_scalar(resource, expression)
        if result:
            # Return first value as string
            val = result[0] if isinstance(result, list) else result
            return str(val) if val is not None else None
        return None
    except (ValueError, TypeError, KeyError, AttributeError, IndexError, NotImplementedError) as e:
        _logger.warning("FHIRPath timestamp evaluation failed for '%s': %s", expression, e)
        if _STRICT_MODE:
            raise
        return None


def fhirpath_quantity_udf(resource: str | None, expression: str | None) -> str | None:
    """
    Extract a quantity value from a FHIR resource using FHIRPath.

    Returns quantity as a string representation (e.g., "120 mmHg").

    Args:
        resource: FHIR resource as JSON string
        expression: FHIRPath expression to evaluate

    Returns:
        Quantity string or None
    """
    if resource is None or expression is None:
        return None
    try:
        result = fhirpath_scalar(resource, expression)
        if result:
            val = result[0] if isinstance(result, list) else result
            return str(val) if val is not None else None
        return None
    except (ValueError, TypeError, KeyError, AttributeError, IndexError, NotImplementedError) as e:
        _logger.warning("FHIRPath quantity evaluation failed for '%s': %s", expression, e)
        if _STRICT_MODE:
            raise
        return None
