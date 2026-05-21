"""
Arrow UDF Implementation

Provides the vectorized FHIRPath UDF using PyArrow for efficient
batch processing of FHIR resources.
"""

from __future__ import annotations

import calendar
import json
import logging
import os
import re
import sys
import threading
from decimal import Decimal
from functools import lru_cache

import orjson
from typing import TYPE_CHECKING

import pyarrow as pa
import pyarrow.compute as pc

from .evaluator import FHIRPathEvaluator, _strip_comments_for_precheck
from .errors import FHIRPathError, FHIRPathSyntaxError

if TYPE_CHECKING:
    from collections.abc import Sequence

_logger = logging.getLogger(__name__)
_STRICT_MODE = os.environ.get("FHIRPATH_STRICT_MODE") == "1"

_VALID_BOOL_STRINGS = frozenset({"true", "false"})
_RECURSION_LIMIT_LOCK = threading.RLock()

# Cache compiled expressions for reuse
# This is shared across all UDF invocations
_EXPRESSION_CACHE_SIZE = 1024


def _json_max_nesting_depth(resource: str) -> int:
    """Return maximum JSON object/array nesting depth, ignoring quoted text."""
    max_depth = 0
    depth = 0
    in_string = False
    escaped = False

    for char in resource:
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue

        if char == '"':
            in_string = True
        elif char in "[{":
            depth += 1
            if depth > max_depth:
                max_depth = depth
        elif char in "]}":
            depth -= 1

    return max_depth


def _parse_json(resource: str) -> dict:
    """Parse a JSON string.

    No caching — parsing returns mutable dicts that the evaluator may mutate.
    ``orjson`` is the normal fast path, but it enforces a nesting ceiling below
    DuckDB/yyjson. Fall back to the standard parser with a temporary recursion
    budget for valid deeply nested resources.
    """
    try:
        return orjson.loads(resource)
    except orjson.JSONDecodeError as exc:
        if "recursion depth" not in str(exc):
            raise

        current_limit = sys.getrecursionlimit()
        needed_limit = max(current_limit, (_json_max_nesting_depth(resource) * 4) + 1000)
        try:
            if needed_limit > current_limit:
                sys.setrecursionlimit(needed_limit)
            return json.loads(resource)
        finally:
            if sys.getrecursionlimit() != current_limit:
                sys.setrecursionlimit(current_limit)


def _json_default(obj: object) -> object:
    """JSON serialization fallback for types not natively supported."""
    from decimal import Decimal
    if isinstance(obj, Decimal):
        return float(obj)
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")


def _json_serialize(obj: object) -> str:
    """Serialize an object to a JSON string using orjson for performance."""
    return orjson.dumps(obj, default=_json_default).decode()


def _json_scalar_serialize(obj: object) -> str:
    """Serialize a scalar JSON value with compact separators."""
    if obj is None:
        return "null"
    if obj is True:
        return "true"
    if obj is False:
        return "false"
    if isinstance(obj, Decimal):
        obj = float(obj)
    if isinstance(obj, (str, int, float)):
        return json.dumps(obj, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")


def _json_serialize_iterative(obj: object) -> str:
    """Serialize JSON-compatible objects without Python recursion.

    DuckDB fallback repeat traversal may need to return deeply nested child
    objects. Both ``orjson`` and ``json.dumps`` have recursion ceilings, so this
    compact serializer handles dict/list structure with an explicit stack.
    """
    chunks: list[str] = []
    stack: list[tuple[str, object]] = [("value", obj)]

    while stack:
        kind, value = stack.pop()
        if kind == "literal":
            chunks.append(value)  # type: ignore[arg-type]
            continue

        if isinstance(value, dict):
            chunks.append("{")
            items = list(value.items())
            stack.append(("literal", "}"))
            for index in range(len(items) - 1, -1, -1):
                key, item_value = items[index]
                if index < len(items) - 1:
                    stack.append(("literal", ","))
                stack.append(("value", item_value))
                stack.append(("literal", ":"))
                stack.append(("literal", _json_scalar_serialize(str(key))))
            continue

        if isinstance(value, (list, tuple)):
            chunks.append("[")
            stack.append(("literal", "]"))
            for index in range(len(value) - 1, -1, -1):
                if index < len(value) - 1:
                    stack.append(("literal", ","))
                stack.append(("value", value[index]))
            continue

        chunks.append(_json_scalar_serialize(value))

    return "".join(chunks)


_TEMPORAL_ARITH_RE = re.compile(
    r"^\s*@(?P<literal>(?:T\d{2}(?::\d{2})?(?::\d{2})?(?:\.\d+)?)|(?:\d{4}(?:-\d{2}(?:-\d{2})?)?(?:T(?:\d{2}(?::\d{2})?(?::\d{2})?(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})?)?)?))"
    r"\s*(?P<op>[+-])\s*"
    r"(?P<value>\d+(?:\.\d+)?)\s+"
    r"(?P<unit>years?|months?|weeks?|days?|hours?|minutes?|seconds?|milliseconds?)\s*$"
)


def _evaluate_literal_temporal_arithmetic(expression: str) -> list[str] | None:
    """Evaluate literal Date/DateTime/Time arithmetic that the Python parser rejects for '+'."""
    match = _TEMPORAL_ARITH_RE.match(expression)
    if not match:
        return None

    from ..engine.nodes import FP_Quantity, FP_TimeBase

    value = Decimal(match.group("value"))
    if match.group("op") == "-":
        value = -value

    literal = FP_TimeBase.get_match_data(match.group("literal"))
    if literal is None:
        return None

    result = literal.plus(FP_Quantity(value, match.group("unit")))
    return [str(result)]


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
    precheck_text = _strip_comments_for_precheck(stripped)
    if _INVALID_EXPR_PATTERNS.search(precheck_text):
        raise FHIRPathSyntaxError(
            f"Invalid FHIRPath expression: rejected by pattern check: '{expression}'"
        )
    # Reject unbalanced parentheses and brackets
    if not _has_balanced_delimiters(stripped):
        raise FHIRPathSyntaxError(
            f"Invalid FHIRPath expression: unbalanced delimiters in '{expression}'"
        )
    evaluator = FHIRPathEvaluator()
    evaluator.compile(expression)
    # QA-010: Warn on unknown function names to flag typos
    _warn_unknown_functions(stripped)
    return evaluator


# Known FHIRPath functions per FHIRPath §5 + FHIR extensions
_KNOWN_FHIRPATH_FUNCTIONS = frozenset({
    # Existence (§5.1)
    'empty', 'exists', 'all', 'allTrue', 'anyTrue', 'allFalse', 'anyFalse',
    'subsetOf', 'supersetOf', 'count', 'distinct', 'isDistinct',
    # Filtering and projection (§5.2)
    'where', 'select', 'repeat', 'ofType',
    # Subsetting (§5.3)
    'single', 'first', 'last', 'tail', 'skip', 'take', 'intersect', 'exclude',
    # Combining (§5.4)
    'union', 'combine',
    # Conversion (§5.5)
    'iif', 'toBoolean', 'convertsToBoolean', 'toInteger', 'convertsToInteger',
    'toDate', 'convertsToDate', 'toDateTime', 'convertsToDateTime',
    'toDecimal', 'convertsToDecimal', 'toString', 'convertsToString',
    'toQuantity', 'convertsToQuantity', 'toTime', 'convertsToTime',
    # String functions (§5.7)
    'indexOf', 'substring', 'startsWith', 'endsWith', 'contains', 'upper',
    'lower', 'replace', 'matches', 'replaceMatches', 'length', 'toChars',
    'trim', 'split', 'join', 'encode', 'decode',
    # Math (§5.8)
    'abs', 'ceiling', 'exp', 'floor', 'ln', 'log', 'power', 'round',
    'sqrt', 'truncate',
    # Tree navigation (§5.9)
    'children', 'descendants',
    # Utility (§5.10)
    'trace', 'now', 'timeOfDay', 'today', 'defineVariable',
    # Types (§5.11/§6)
    'is', 'as', 'type',
    # Aggregate (§5.12)
    'aggregate',
    # STU/date-time helpers implemented by native/public surfaces
    'lowBoundary', 'highBoundary', 'precision', 'yearOf', 'monthOf', 'dayOf',
    'hourOf', 'minuteOf', 'secondOf', 'millisecondOf', 'timezoneOffsetOf',
    'escape', 'unescape', 'matchesFull', 'comparable', 'coalesce',
    'repeatAll', 'sort',
    # FHIR-specific
    'resolve', 'extension', 'hasValue', 'getValue', 'getResourceKey',
    'getReferenceKey', 'memberOf',
    'htmlChecks', 'conformsTo', 'elementDefinition', 'slice', 'checkModifiers',
    # Boolean
    'not',
})

# Pattern to extract function names from FHIRPath expressions
_FHIRPATH_FUNC_RE = re.compile(r'\.?([a-zA-Z_]\w*)\s*\(')


def _warn_unknown_functions(expression: str) -> None:
    """Log warnings for unrecognized function names in a FHIRPath expression."""
    for match in _FHIRPATH_FUNC_RE.finditer(expression):
        func_name = match.group(1)
        if func_name not in _KNOWN_FHIRPATH_FUNCTIONS:
            # Skip common non-function patterns (resource types, string literals)
            if func_name[0].isupper():
                continue  # Resource type names like Patient, Observation
            _logger.warning(
                "FHIRPath expression contains unknown function '%s' — "
                "possible typo (will return empty/NULL): %s",
                func_name, expression,
            )


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


def _resolve_choice_oftype(resource_dict: dict, expression: str) -> list:
    """Resolve simple choice-type ofType() expressions missed by fhirpathpy."""
    match = re.fullmatch(r"\s*([A-Za-z_]\w*)\.ofType\(\s*([A-Za-z_]\w*)\s*\)\s*", expression)
    if not match:
        return []
    base_name, type_name = match.groups()
    field_names = _get_choice_type_lookup().get(base_name)
    if not field_names:
        return []
    target_field = f"{base_name}{type_name[0].upper()}{type_name[1:]}"
    if target_field not in field_names:
        return []
    val = resource_dict.get(target_field)
    if val is None:
        return []
    return [val]


_CHOICE_ASSERTION_METHOD_RE = re.compile(
    r"^\s*(?P<path>[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*)\."
    r"(?P<op>is|as)\(\s*(?P<type>`?[\w.]+`?)\s*\)\s*$",
    re.IGNORECASE,
)
_CHOICE_ASSERTION_INFIX_RE = re.compile(
    r"^\s*(?P<path>[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*)\s+"
    r"(?P<op>is|as)\s+(?P<type>`?[\w.]+`?)\s*$",
    re.IGNORECASE,
)

_KNOWN_FUNCTION_NAMES = frozenset(
    {
        "abs", "aggregate", "all", "allFalse", "allTrue", "anyFalse", "anyTrue", "as",
        "ceiling", "checkModifiers", "children", "coalesce", "combine", "comparable",
        "conformsTo", "contains", "convertsToBoolean", "convertsToDate", "convertsToDateTime",
        "convertsToDecimal", "convertsToInteger", "convertsToQuantity", "convertsToString",
        "convertsToTime", "count", "dayOf", "decode", "defineVariable", "descendants",
        "distinct", "elementDefinition", "empty", "empty_collection", "encode", "endsWith", "escape", "exclude",
        "exists", "exp", "first", "floor", "getValue", "hasTemplateIdOf", "hasValue",
        "highBoundary", "hourOf", "htmlChecks", "htmlChecks2", "iif", "indexOf", "intersect",
        "is", "isDistinct", "join", "last", "length", "ln", "log", "lowBoundary", "lower",
        "matches", "matchesFull", "memberOf", "millisecondOf", "minuteOf", "monthOf", "not", "now",
        "ofType", "power", "precision", "repeat", "repeatAll", "replace", "replaceMatches", "resolve",
        "round", "secondOf", "select", "single", "skip", "sort", "split", "sqrt", "startsWith",
        "slice", "subsetOf", "substring", "supersetOf", "tail", "take", "timeOfDay", "timezoneOffsetOf",
        "toBoolean", "toChars", "toDate", "toDateTime", "toDecimal", "toInteger", "toQuantity",
        "toString", "toTime", "today", "trace", "trim", "truncate", "type", "unescape", "union",
        "upper", "where", "yearOf",
        "Address", "CodeableConcept", "Coding", "ContactPoint", "Extension", "HumanName",
        "Identifier", "Quantity", "create", "withExtension", "withProperty",
    }
)


def _choice_type_suffix(type_name: str) -> str | None:
    parts = type_name.strip().strip("`").split(".")
    if len(parts) > 1 and parts[-2].lower() == "system":
        return None
    bare = parts[-1]
    return {
        "base64binary": "Base64Binary",
        "boolean": "Boolean",
        "canonical": "Canonical",
        "code": "Code",
        "codeableconcept": "CodeableConcept",
        "coding": "Coding",
        "date": "Date",
        "datetime": "DateTime",
        "decimal": "Decimal",
        "id": "Id",
        "instant": "Instant",
        "integer": "Integer",
        "integer64": "Integer64",
        "markdown": "Markdown",
        "oid": "Oid",
        "positiveint": "PositiveInt",
        "quantity": "Quantity",
        "string": "String",
        "time": "Time",
        "unsignedint": "UnsignedInt",
        "uri": "Uri",
        "url": "Url",
        "uuid": "Uuid",
    }.get(bare.lower(), bare[:1].upper() + bare[1:])


def _resolve_choice_type_assertion(resource_dict: dict, expression: str) -> list | None:
    """Resolve simple choice-type ``is``/``as`` expressions missed by fallback evaluation."""
    match = _CHOICE_ASSERTION_METHOD_RE.fullmatch(expression) or _CHOICE_ASSERTION_INFIX_RE.fullmatch(expression)
    if not match:
        return None

    path = match.group("path")
    op = match.group("op").lower()
    parts = path.split(".")
    if len(parts) > 2:
        return None
    if len(parts) == 2 and parts[0] != resource_dict.get("resourceType"):
        return None
    base_name = parts[-1]

    field_names = _get_choice_type_lookup().get(base_name)
    if not field_names:
        return None

    suffix = _choice_type_suffix(match.group("type"))
    if suffix is None:
        return [False] if op == "is" else []
    target_field = f"{base_name}{suffix}"
    if target_field not in field_names:
        return [False] if op == "is" else []

    val = resource_dict.get(target_field)
    if op == "is":
        return [val is not None]
    if val is None:
        return []
    return [val]


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

            choice_assertion = _resolve_choice_type_assertion(resource_dict, expression)
            if choice_assertion is not None:
                result = choice_assertion
            if not result and isinstance(resource_dict, dict):
                result = _resolve_choice_type(resource_dict, expression)
            if not result and isinstance(resource_dict, dict):
                result = _resolve_choice_oftype(resource_dict, expression)

            # Convert result to list for Arrow
            if result is None:
                results.append([])
            elif isinstance(result, list):
                # Serialize complex objects to valid JSON strings
                serialized = []
                for item in result:
                    if item is None:
                        serialized.append("")
                    elif isinstance(item, (dict, list)):
                        serialized.append(_json_serialize(item))
                    elif isinstance(item, bool):
                        serialized.append("true" if item else "false")
                    elif isinstance(item, Decimal):
                        text = format(item, "f")
                        if "." not in text:
                            text += ".0"
                        serialized.append(text)
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
            if _STRICT_MODE:
                raise
            results.append([])
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
        except (pa.ArrowInvalid, pa.ArrowNotImplementedError) as e:
            _logger.warning(
                "Arrow type cast from %s to %s failed: %s. "
                "Returning results with original type.",
                results.type, return_type, e,
            )

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
            _logger.warning(
                "fhirpath_scalar: unexpected resource type %s for expression '%s' — returning empty",
                type(resource).__name__, expression,
            )
            return []

        temporal_result = _evaluate_literal_temporal_arithmetic(expression)
        if temporal_result is not None:
            return temporal_result

        # Get cached evaluator and evaluate
        evaluator = _get_compiled_evaluator(expression)
        result = evaluator.evaluate(resource_dict)

        choice_assertion = _resolve_choice_type_assertion(resource_dict, expression)
        if choice_assertion is not None:
            result = choice_assertion

        # Fallback: resolve choice type fields that fhirpathpy misses for primitives
        if not result and isinstance(resource_dict, dict):
            result = _resolve_choice_type(resource_dict, expression)
        if not result and isinstance(resource_dict, dict):
            result = _resolve_choice_oftype(resource_dict, expression)

        # Convert result to list of strings for DuckDB
        if result is None:
            return []
        if isinstance(result, list):
            # Convert all items to strings for consistent return type
            def _to_str(item):
                if item is None:
                    return ""
                if isinstance(item, bool):
                    return "true" if item else "false"
                if isinstance(item, float):
                    text = format(item, ".17g")
                    if "." not in text and "e" not in text and "E" not in text:
                        text += ".0"
                    return text
                if isinstance(item, Decimal):
                    text = format(item, "f")
                    if "." not in text:
                        text += ".0"
                    return text
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
        _logger.warning(
            "fhirpath_scalar: invalid JSON resource for expression '%s'", expression,
        )
        if _STRICT_MODE:
            raise
        return []
    except FHIRPathSyntaxError:
        # Syntax errors are never valid "no data" — always propagate.
        raise
    except FHIRPathError:
        if _STRICT_MODE:
            raise
        _logger.warning("FHIRPath scalar evaluation error for '%s'", expression)
        return []
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
    r'|^\s*@\d{5}'      # Date year must be exactly four digits
    r'|^\s*@\d{4}-\d(?:\D|$)'  # Month must be two digits when separator is present
    r'|^\s*@\d{4}-\d{2}-\d(?:\D|$)'  # Day must be two digits when present
    r'|^\s*@T\d{2}:\d{2}\.\d'  # Fractional Time requires seconds component
    r'|^\s*\d+(?:\.\d+)?\s+(?!years?\b|months?\b|weeks?\b|days?\b|hours?\b|minutes?\b|seconds?\b|milliseconds?\b)[A-Za-z_]\w*\s*$'
    r'|^\s*\d+\.\d+\.\d+'  # Ambiguous numeric/member-access tokenization
    r'|\$\$'            # invalid $$ prefix
    r'|\$(?!this\b|total\b|index\b|that\b)[a-zA-Z]'  # $ not followed by valid env variable
    r')'
)


def _has_balanced_delimiters(expression: str) -> bool:
    depth_paren = 0
    depth_bracket = 0
    i = 0
    in_string = False
    in_delimited_identifier = False

    while i < len(expression):
        ch = expression[i]

        if in_string or in_delimited_identifier:
            if ch == "\\" and i + 1 < len(expression):
                i += 2
                continue
            if in_string and ch == "'":
                in_string = False
            elif in_delimited_identifier and ch == "`":
                in_delimited_identifier = False
            i += 1
            continue

        if ch == "'":
            in_string = True
            i += 1
            continue
        if ch == "`":
            in_delimited_identifier = True
            i += 1
            continue
        if ch == "/" and i + 1 < len(expression) and expression[i + 1] == "/":
            i += 2
            while i < len(expression) and expression[i] not in "\r\n":
                i += 1
            continue
        if ch == "/" and i + 1 < len(expression) and expression[i + 1] == "*":
            i += 2
            while i < len(expression):
                if expression[i] == "*" and i + 1 < len(expression) and expression[i + 1] == "/":
                    i += 2
                    break
                i += 1
            continue
        if ch == "(":
            depth_paren += 1
        elif ch == ")":
            depth_paren -= 1
        elif ch == "[":
            depth_bracket += 1
        elif ch == "]":
            depth_bracket -= 1
        if depth_paren < 0 or depth_bracket < 0:
            return False
        i += 1

    return depth_paren == 0 and depth_bracket == 0


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
    precheck_text = _strip_comments_for_precheck(stripped)
    if _INVALID_EXPR_PATTERNS.search(precheck_text):
        return False
    if not _has_balanced_delimiters(stripped):
        return False
    try:
        if _evaluate_literal_temporal_arithmetic(expression) is not None:
            return True
        evaluator = _get_compiled_evaluator(expression)
        evaluator.evaluate({"resourceType": "Patient", "id": "_validation"})
        return True
    except FHIRPathError as exc:
        if _is_valid_empty_result_error(exc):
            return True
        return False
    except NotImplementedError as exc:
        return _not_implemented_function_name(exc) in _KNOWN_FUNCTION_NAMES
    except Exception:
        # Catch all exceptions — a validation function must never throw
        return False


def _not_implemented_function_name(exc: NotImplementedError) -> str | None:
    message = str(exc)
    for prefix in ("Not implemented: ", "Not implemented "):
        if message.startswith(prefix):
            return message[len(prefix):].strip()
    return None


def _is_valid_empty_result_error(exc: FHIRPathError) -> bool:
    """Return true for spec-valid expressions that evaluate to empty on data.

    `fhirpath_is_valid` is an expression validity helper, not a result
    non-emptiness helper. The Python fallback validates by running a compiled
    expression against a minimal Patient resource, so runtime empty-result
    errors from incompatible comparison/arithmetic operands must not be
    conflated with syntax errors, bad type specifiers, wrong arity, or
    singleton violations.
    """
    message = str(exc)
    if message.startswith("Type of ") and "InequalityExpression" in message:
        return True
    if (
        message.startswith("Cannot [")
        and "fhir4ds.fhirpath.engine.nodes.FP_" not in message
    ):
        return True
    if message.startswith("Expected number or quantity, got: "):
        return True
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
    except (NotImplementedError, FHIRPathSyntaxError, FHIRPathError) as e:
        _logger.warning("fhirpath_text evaluation error for expression %r: %s", expression, e)
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
        return _normalize_fhir_date_string(value)
    return None


def _normalize_fhir_date_string(value: str) -> str | None:
    """Return a valid FHIR date component, preserving precision."""
    if "T" in value:
        date_part, _, _time_part = value.partition("T")
        # A DateTime can be exposed as a date only when a full date exists.
        if len(date_part) != 10:
            return None
    else:
        date_part = value

    parts = date_part.split("-")
    if len(parts) not in (1, 2, 3):
        return None
    if len(parts[0]) != 4 or not parts[0].isdigit():
        return None

    if len(parts) == 1:
        return date_part

    if len(parts[1]) != 2 or not parts[1].isdigit():
        return None
    month = int(parts[1])
    if month < 1 or month > 12:
        return None

    if len(parts) == 2:
        return date_part

    if len(parts[2]) != 2 or not parts[2].isdigit():
        return None
    day = int(parts[2])
    max_day = calendar.monthrange(int(parts[0]), month)[1]
    if day < 1 or day > max_day:
        return None
    return date_part


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
    if resource is None or expression is None:
        return None

    try:
        if isinstance(resource, str):
            resource_dict = _parse_json(resource)
        elif isinstance(resource, dict):
            resource_dict = resource
        else:
            return None

        temporal_result = _evaluate_literal_temporal_arithmetic(expression)
        if temporal_result is not None:
            result = temporal_result
        else:
            evaluator = _get_compiled_evaluator(expression)
            result = evaluator.evaluate(resource_dict)
            choice_assertion = _resolve_choice_type_assertion(resource_dict, expression)
            if choice_assertion is not None:
                result = choice_assertion
            if not result and isinstance(resource_dict, dict):
                result = _resolve_choice_type(resource_dict, expression)
            if not result and isinstance(resource_dict, dict):
                result = _resolve_choice_oftype(resource_dict, expression)

        if isinstance(result, list):
            result_items = result
        elif result is None:
            result_items = []
        else:
            result_items = [result]
    except orjson.JSONDecodeError:
        if _STRICT_MODE:
            raise
        return None
    except FHIRPathSyntaxError:
        raise
    except (NotImplementedError, FHIRPathError):
        # Unimplemented functions return NULL in boolean context (used by ViewDef)
        return None
    except (ValueError, TypeError, KeyError, AttributeError, IndexError) as e:
        _logger.warning("FHIRPath boolean evaluation failed for '%s': %s", expression, e)
        if _STRICT_MODE:
            raise
        return None

    if not result_items:
        return None
    val = result_items[0]
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
        return low == "true"
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
    if resource is None or expression is None:
        return None

    try:
        if isinstance(resource, str):
            resource_dict = _parse_json(resource)
        elif isinstance(resource, dict):
            resource_dict = resource
        else:
            return None

        temporal_result = _evaluate_literal_temporal_arithmetic(expression)
        if temporal_result is not None:
            result = temporal_result
        else:
            evaluator = _get_compiled_evaluator(expression)
            result = evaluator.evaluate(resource_dict)

            choice_assertion = _resolve_choice_type_assertion(resource_dict, expression)
            if choice_assertion is not None:
                result = choice_assertion
            if not result and isinstance(resource_dict, dict):
                result = _resolve_choice_type(resource_dict, expression)
            if not result and isinstance(resource_dict, dict):
                result = _resolve_choice_oftype(resource_dict, expression)
    except FHIRPathSyntaxError:
        raise
    except (NotImplementedError, FHIRPathError):
        return None
    except (orjson.JSONDecodeError, ValueError, TypeError, KeyError, AttributeError, IndexError):
        if _STRICT_MODE:
            raise
        return None
    if not result:
        return None
    if isinstance(result, list) and len(result) != 1:
        return None
    value = result[0] if isinstance(result, list) else result
    from ..engine.nodes import FP_Quantity
    if isinstance(value, FP_Quantity):
        return float(value.value)
    if isinstance(value, bool) or not isinstance(value, (int, float, Decimal)):
        return None
    try:
        return float(value)
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

        temporal_result = _evaluate_literal_temporal_arithmetic(expression)
        if temporal_result is not None:
            result = temporal_result
        else:
            evaluator = _get_compiled_evaluator(expression)
            result = evaluator.evaluate(resource_dict)

            choice_assertion = _resolve_choice_type_assertion(resource_dict, expression)
            if choice_assertion is not None:
                result = choice_assertion
            if not result and isinstance(resource_dict, dict):
                result = _resolve_choice_type(resource_dict, expression)
            if not result and isinstance(resource_dict, dict):
                result = _resolve_choice_oftype(resource_dict, expression)

        if result is None or (isinstance(result, list) and len(result) == 0):
            return None

        # Preserve native types for proper JSON serialization.
        # FHIRPath nodes need special handling; primitives pass through.
        def _to_native(item):
            from ..engine.nodes import FP_TimeBase, FP_Quantity
            if item is None:
                return None
            if isinstance(item, bool):
                return item
            if isinstance(item, (int, float)):
                return item
            if isinstance(item, Decimal):
                return item
            if isinstance(item, FP_Quantity):
                value = float(item.value)
                if value.is_integer():
                    value = int(value)
                unit = str(item.unit)
                if len(unit) >= 2 and unit[0] == "'" and unit[-1] == "'":
                    unit = unit[1:-1]
                return {"value": value, "unit": unit}
            if isinstance(item, FP_TimeBase):
                return str(item)
            if isinstance(item, (dict, list)):
                return item
            return str(item)

        if isinstance(result, list):
            native = [_to_native(item) for item in result]
        else:
            native = [_to_native(result)]

        def _json_item(item):
            if isinstance(item, bool):
                return "true" if item else "false"
            if isinstance(item, int):
                return str(item)
            if isinstance(item, float):
                text = format(item, ".17g")
                if "." not in text and "e" not in text and "E" not in text:
                    text += ".0"
                return text
            if isinstance(item, Decimal):
                text = format(item, "f")
                if "." not in text:
                    text += ".0"
                return text
            return _json_serialize(item)

        return "[" + ",".join(_json_item(item) for item in native) + "]"
    except FHIRPathSyntaxError:
        raise
    except FHIRPathError:
        if _STRICT_MODE:
            raise
        return None
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

def _repeat_json_serialize(obj: object) -> str:
    """Serialize repeated nodes, falling back for deeply nested structures."""
    try:
        return _json_serialize(obj)
    except (TypeError, RecursionError):
        return _json_serialize_iterative(obj)


def _evaluate_repeat_expression(current: dict, path: str) -> list[dict]:
    evaluator = _get_compiled_evaluator(path)
    return [item for item in evaluator.evaluate(current) if isinstance(item, dict)]


def _repeat_traverse(root: dict, paths: list[str]) -> list[str]:
    """Depth-first repeat traversal using FHIRPath expressions.

    SQL-on-FHIR ``repeat`` applies each FHIRPath expression at the current
    node, recurses into each result, and unions results across paths/levels.
    JSON input is finite, so traversal needs a visited set for duplicate path
    hits rather than an arbitrary depth cap. The traversal uses explicit frames
    so a valid deeply nested JSON tree does not trip Python's recursion limit.
    """
    results: list[str] = []
    seen: set[str] = set()
    stack: list[dict[str, object]] = [
        {"current": root, "path_index": 0, "children": None, "child_index": 0}
    ]

    while stack:
        frame = stack[-1]
        path_index = frame["path_index"]
        if not isinstance(path_index, int):
            raise TypeError("repeat traversal frame path_index must be an integer")

        if frame["children"] is None:
            if path_index >= len(paths):
                stack.pop()
                continue
            try:
                frame["children"] = _evaluate_repeat_expression(
                    frame["current"],  # type: ignore[arg-type]
                    paths[path_index],
                )
            except Exception:
                _logger.debug(
                    "fhirpath_repeat path failed: %s",
                    paths[path_index],
                    exc_info=True,
                )
                frame["path_index"] = path_index + 1
                frame["children"] = None
                frame["child_index"] = 0
                continue
            frame["child_index"] = 0

        children = frame["children"]
        child_index = frame["child_index"]
        if not isinstance(children, list) or not isinstance(child_index, int):
            raise TypeError("repeat traversal frame is malformed")

        if child_index >= len(children):
            frame["path_index"] = path_index + 1
            frame["children"] = None
            frame["child_index"] = 0
            continue

        child = children[child_index]
        frame["child_index"] = child_index + 1
        child_json = _repeat_json_serialize(child)
        if child_json in seen:
            continue
        seen.add(child_json)
        results.append(child_json)
        stack.append({"current": child, "path_index": 0, "children": None, "child_index": 0})

    return results


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

    def evaluate_repeat() -> list:
        obj = _parse_json(resource)
        paths = orjson.loads(paths_json)
        if (
            not isinstance(paths, list)
            or not paths
            or any(not isinstance(path, str) or not path for path in paths)
        ):
            return []
        return _repeat_traverse(obj, paths)

    needed_limit = (_json_max_nesting_depth(resource) * 4) + 1000
    try:
        with _RECURSION_LIMIT_LOCK:
            current_limit = sys.getrecursionlimit()
            try:
                if needed_limit > current_limit:
                    sys.setrecursionlimit(needed_limit)
                return evaluate_repeat()
            finally:
                if sys.getrecursionlimit() != current_limit:
                    sys.setrecursionlimit(current_limit)
    except Exception:
        _logger.debug("fhirpath_repeat failed", exc_info=True)
        return []
