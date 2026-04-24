"""
Arrow UDF Implementation

Provides the vectorized FHIRPath UDF using PyArrow for efficient
batch processing of FHIR resources.
"""

from __future__ import annotations

import logging
import os
import re
from decimal import Decimal
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
    Rejects known-invalid patterns before attempting parse.

    Args:
        expression: A FHIRPath expression string.

    Returns:
        A FHIRPathEvaluator with the expression compiled.

    Raises:
        FHIRPathSyntaxError: If the expression matches a known-invalid pattern.
    """
    stripped = expression.strip()
    if _INVALID_EXPR_PATTERNS.search(stripped):
        raise FHIRPathSyntaxError(
            f"Invalid FHIRPath expression: rejected by pattern check: '{expression}'"
        )
    # Reject unbalanced parentheses and brackets
    depth_paren = 0
    depth_bracket = 0
    for ch in stripped:
        if ch == '(':
            depth_paren += 1
        elif ch == ')':
            depth_paren -= 1
        elif ch == '[':
            depth_bracket += 1
        elif ch == ']':
            depth_bracket -= 1
        if depth_paren < 0 or depth_bracket < 0:
            raise FHIRPathSyntaxError(
                f"Invalid FHIRPath expression: unbalanced delimiters in '{expression}'"
            )
    if depth_paren != 0 or depth_bracket != 0:
        raise FHIRPathSyntaxError(
            f"Invalid FHIRPath expression: unbalanced delimiters in '{expression}'"
        )
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

    Error handling policy:
    - FHIRPathSyntaxError, FHIRPathError, NotImplementedError: always propagate
      (expression-level errors that apply to all rows).
    - orjson.JSONDecodeError: return [] for the row (data-dependent; one bad
      resource must not abort the entire batch). In STRICT_MODE, propagate.
    - ValueError/TypeError/KeyError/AttributeError/IndexError: return [] for
      the row (data-dependent evaluation failures). In STRICT_MODE, propagate.

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
                    elif isinstance(item, bool):
                        serialized.append("true" if item else "false")
                    elif isinstance(item, str):
                        serialized.append(item)
                    else:
                        serialized.append(str(item))
                results.append(serialized)
            else:
                results.append([result])

        except orjson.JSONDecodeError:
            # Invalid JSON — data-dependent error. In batch queries, one bad
            # resource should not abort the entire query.
            if _STRICT_MODE:
                raise
            results.append([])
        except FHIRPathSyntaxError:
            # Syntax errors are never valid "no data" — always propagate.
            # The expression is constant across all rows, so the error
            # represents a user mistake, not a data-dependent condition.
            raise
        except FHIRPathError:
            # FHIRPathError represents spec-mandated evaluation errors (e.g., single()
            # on multi-element collections). These must always propagate per spec.
            raise
        except NotImplementedError:
            raise
        except (ValueError, TypeError, KeyError, AttributeError, IndexError) as e:
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
                if isinstance(item, bool):
                    return "true" if item else "false"
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
        # Invalid JSON — data-dependent error. In scalar context, return empty.
        if _STRICT_MODE:
            raise
        return []
    except FHIRPathSyntaxError:
        # Syntax errors are never valid "no data" — always propagate.
        raise
    except FHIRPathError:
        # FHIRPathError represents spec-mandated evaluation errors (e.g., single()
        # on multi-element collections). These must always propagate per spec.
        raise
    except NotImplementedError:
        # Unimplemented functions should be visible to users
        raise
    except (ValueError, TypeError, KeyError, AttributeError, IndexError) as e:
        _logger.warning("FHIRPath scalar evaluation failed for '%s': %s", expression, e)
        if _STRICT_MODE:
            raise
        # Unexpected error - return empty collection
        return []



_INVALID_EXPR_PATTERNS = re.compile(
    r'(?:'
    r'\.\s*$'           # trailing dot
    r'|\.\.'            # double dot
    r'|\(\s*$'          # unclosed paren at end
    r'|^\s*[+*/|&]'    # leading operator
    r'|\$\$'            # invalid $$ prefix
    r'|\$(?!this\b|total\b|index\b|that\b)[a-zA-Z]'  # $ not followed by valid env variable
    r')'
)


def fhirpath_is_valid_udf(expression: str | None) -> bool:
    """Check if a FHIRPath expression is syntactically valid.

    Validates by compiling AND evaluating against a minimal resource,
    plus rejects common malformed patterns the parser may accept.
    """
    if not expression or not isinstance(expression, str):
        return False
    stripped = expression.strip()
    if not stripped:
        return False
    # Reject common invalid patterns that fhirpathpy may accept
    if _INVALID_EXPR_PATTERNS.search(stripped):
        return False
    # Check for unbalanced parentheses
    depth = 0
    for ch in stripped:
        if ch == '(':
            depth += 1
        elif ch == ')':
            depth -= 1
        if depth < 0:
            return False
    if depth != 0:
        return False
    try:
        evaluator = _get_compiled_evaluator(expression)
        evaluator.evaluate({"resourceType": "Patient", "id": "_validation"})
        return True
    except Exception:
        # Catch all exceptions — a validation function must never throw
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
    try:
        result = fhirpath_scalar(resource, expression)
    except (NotImplementedError, FHIRPathSyntaxError, FHIRPathError):
        return None
    if not result:
        return None
    val = result[0]
    if isinstance(val, (dict, list)):
        return _json_serialize(val)
    if isinstance(val, bool):
        return "true" if val else "false"
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
    try:
        result = fhirpath_scalar(resource, expression)
    except NotImplementedError:
        return None
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
    try:
        result = fhirpath_scalar(resource, expression)
    except NotImplementedError:
        # Unimplemented functions return NULL in boolean context (used by ViewDef)
        return None
    if not result:
        return None
    val = result[0]
    if isinstance(val, bool):
        return val
    if isinstance(val, str):
        low = val.lower()
        if low not in _VALID_BOOL_STRINGS:
            _logger.warning(
                "Unexpected boolean string '%s' for expression '%s'; returning NULL",
                val, expression,
            )
            return None
        return low in ("true", "1")
    if isinstance(val, (int, float)):
        if val in (0, 1, 0.0, 1.0):
            return bool(val)
        _logger.warning(
            "Unexpected numeric boolean value %r for expression '%s'; returning NULL",
            val, expression,
        )
        return None
    _logger.warning(
        "Unexpected type %s for boolean expression '%s'; returning NULL",
        type(val).__name__, expression,
    )
    return None


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
    try:
        result = fhirpath_scalar(resource, expression)
    except NotImplementedError:
        return None
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
    if resource is None or expression is None:
        return None
    try:
        if isinstance(resource, str):
            resource_dict = _parse_json(resource)
        elif isinstance(resource, dict):
            resource_dict = resource
        else:
            return None

        evaluator = _get_compiled_evaluator(expression)
        result = evaluator.evaluate(resource_dict)

        if not result and isinstance(resource_dict, dict):
            result = _resolve_choice_type(resource_dict, expression)

        if result is None or (isinstance(result, list) and len(result) == 0):
            return None

        # Preserve native types for proper JSON serialization.
        # FHIRPath nodes need special handling; primitives pass through.
        def _to_native(item):
            from ..engine.nodes import FP_TimeBase, FP_Quantity
            if isinstance(item, bool):
                return item
            if isinstance(item, (int, float)):
                return item
            if isinstance(item, Decimal):
                # Preserve precision: use float only if lossless
                f = float(item)
                if Decimal(str(f)) == item:
                    return f
                # Precision loss — still use float (orjson can't serialize Decimal)
                # but this is acceptable for JSON which is float64 natively
                return f
            if isinstance(item, FP_Quantity):
                return {"value": float(item.value), "unit": str(item.unit)}
            if isinstance(item, FP_TimeBase):
                return str(item)
            if isinstance(item, (dict, list)):
                return item
            return str(item)

        if isinstance(result, list):
            native = [_to_native(item) for item in result]
        else:
            native = [_to_native(result)]
        return _json_serialize(native)
    except (FHIRPathSyntaxError, FHIRPathError):
        raise
    except NotImplementedError:
        return None
    except Exception:
        if _STRICT_MODE:
            raise
        return None


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
    except NotImplementedError:
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
    except NotImplementedError:
        return None
    except (ValueError, TypeError, KeyError, AttributeError, IndexError) as e:
        _logger.warning("FHIRPath quantity evaluation failed for '%s': %s", expression, e)
        if _STRICT_MODE:
            raise
        return None


# ---------------------------------------------------------------------------
# fhirpath_repeat: recursive traversal for SQL-on-FHIR v2 ``repeat``
# ---------------------------------------------------------------------------

def _navigate_simple_path(obj: dict, path: str) -> list:
    """Navigate a dotted property path in a JSON object.

    For ``repeat``, paths are simple dotted property names (e.g. ``item``
    or ``answer.item``), not full FHIRPath expressions.

    Returns a list of dict children found at the end of the path.
    """
    parts = path.split(".")
    candidates = [obj]
    for part in parts:
        next_candidates: list = []
        for c in candidates:
            if isinstance(c, dict) and part in c:
                val = c[part]
                if isinstance(val, list):
                    next_candidates.extend(val)
                else:
                    next_candidates.append(val)
        candidates = next_candidates
    # Only return dict-typed children (JSON objects)
    return [c for c in candidates if isinstance(c, dict)]


def _repeat_dfs(current: dict, paths: list, results: list, max_depth: int = 200, depth: int = 0) -> None:
    """Depth-first recursive traversal collecting all repeat path results.

    Per SQL-on-FHIR v2 §Select.repeat, the repeat directive recursively
    applies each path expression and collects all matching elements in
    document order (depth-first).
    """
    if depth >= max_depth:
        return
    for path in paths:
        children = _navigate_simple_path(current, path)
        for child in children:
            results.append(orjson.dumps(child).decode())
            _repeat_dfs(child, paths, results, max_depth, depth + 1)


def fhirpath_repeat_udf(resource: str, paths_json: str) -> list:
    """Recursively apply FHIRPath paths and return flattened array of JSON elements.

    Implements the SQL-on-FHIR v2 ``repeat`` directive. Given a FHIR resource
    and a JSON array of simple dotted paths, performs a depth-first traversal
    collecting all matching elements at every nesting level.

    Args:
        resource: JSON string of the FHIR resource.
        paths_json: JSON array of path strings, e.g. ``'["item","answer.item"]'``.

    Returns:
        List of JSON strings, one per collected element.
    """
    if resource is None or paths_json is None:
        return []
    try:
        obj = orjson.loads(resource)
        paths = orjson.loads(paths_json)
        if not isinstance(paths, list) or not paths:
            return []
        results: list = []
        _repeat_dfs(obj, paths, results)
        return results
    except Exception:
        _logger.debug("fhirpath_repeat failed", exc_info=True)
        return []
