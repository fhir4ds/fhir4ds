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

from .evaluator import (
    FHIRPathEvaluator,
    _has_invalid_partial_datetime_time_literal,
    _has_invalid_timezone_literal,
    _has_invalid_week_date_literal,
    _has_out_of_range_integer_literal,
    _has_out_of_range_long_literal,
    _is_unary_minus_context,
    _strip_comments_for_precheck,
)
from .errors import FHIRPathError, FHIRPathSyntaxError

if TYPE_CHECKING:
    from collections.abc import Sequence

_logger = logging.getLogger(__name__)
_STRICT_MODE = os.environ.get("FHIRPATH_STRICT_MODE") == "1"

_VALID_BOOL_STRINGS = frozenset({"true", "false"})
_RECURSION_LIMIT_LOCK = threading.RLock()
_MALFORMED_LONG_SUFFIX_RE = re.compile(
    r"(?<![A-Za-z0-9_.])(?P<number>\d+(?:\.\d+)?)(?P<suffix>[A-Za-z_]\w*)"
)

# Cache compiled expressions for reuse
# This is shared across all UDF invocations
_EXPRESSION_CACHE_SIZE = 1024


def _is_row_resilient_invalid_literal(expression: object) -> bool:
    if not isinstance(expression, str):
        return False
    stripped = expression.strip()
    return (
        _has_invalid_partial_datetime_time_literal(stripped)
        or _has_invalid_week_date_literal(stripped)
        or _has_out_of_range_integer_literal(stripped)
        or _has_out_of_range_long_literal(stripped)
        or _has_malformed_long_literal_suffix(stripped)
    )


def _has_malformed_long_literal_suffix(expression: str) -> bool:
    text = _strip_comments_for_precheck(expression)
    text = re.sub(r"'(?:\\.|[^\\'])*'", "S", text)
    text = re.sub(r"`(?:\\.|[^\\`])*`", "I", text)
    text = re.sub(r"@[T0-9:.\-+Z]+", "D", text)
    for match in _MALFORMED_LONG_SUFFIX_RE.finditer(text):
        suffix = match.group("suffix")
        if not suffix or suffix[0] not in {"L", "l"}:
            continue
        if suffix == "L" and "." not in match.group("number"):
            continue
        return True
    return False


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


def _expression_max_nesting_depth(expression: str) -> int:
    """Return maximum FHIRPath expression syntactic nesting depth.

    Counts AST-node-introducing tokens (``(``, ``[``, ``|``, ``&``, ``.``,
    function-call commas) outside strings, delimited identifiers, and comments.
    Each AST node consumes ~5-10 Python stack frames during recursive
    ``do_eval`` evaluation, so this depth drives the Python recursion budget.

    Used by the row-resilient UDF wrapper to temporarily raise
    ``sys.recursionlimit`` for pathological-size expressions
    (e.g. ``(1 | 2 | ... | 500).aggregate(...)``) so they evaluate
    successfully instead of being silently swallowed as ``RecursionError``.
    Mirrors the resource-side ``_json_max_nesting_depth`` helper.

    See FP-19 EXPLORER QA-001 (2026-06-30): without this budget the
    Python fallback returns empty for 250+-element unions while native
    C++ handles 500+ correctly.
    """
    max_depth = 0
    depth = 0
    in_string = False
    in_delimited = False
    escaped = False
    i = 0
    n = len(expression)

    while i < n:
        ch = expression[i]

        if in_string or in_delimited:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif in_string and ch == "'":
                in_string = False
            elif in_delimited and ch == "`":
                in_delimited = False
            i += 1
            continue

        # Skip line comments
        if ch == "/" and i + 1 < n and expression[i + 1] == "/":
            i += 2
            while i < n and expression[i] not in "\r\n":
                i += 1
            continue
        # Skip block comments
        if ch == "/" and i + 1 < n and expression[i + 1] == "*":
            i += 2
            while i < n:
                if expression[i] == "*" and i + 1 < n and expression[i + 1] == "/":
                    i += 2
                    break
                i += 1
            continue

        if ch == "'":
            in_string = True
        elif ch == "`":
            in_delimited = True
        elif ch in "([":
            depth += 1
            if depth > max_depth:
                max_depth = depth
        elif ch in ")]":
            if depth > 0:
                depth -= 1
        elif ch in "|&,":  # binary operators and arg separators grow the AST spine
            depth += 1
            if depth > max_depth:
                max_depth = depth
        elif ch == ".":  # member/function invocation
            depth += 1
            if depth > max_depth:
                max_depth = depth
        i += 1

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
        # orjson's depth-limit wording differs across releases: <=3.11 says
        # "array and object recursion depth exceeded", 3.12+ says "depth
        # limit exceeded". Match both rather than pinning orjson.
        msg = str(exc).lower()
        if "recursion depth" not in msg and "depth limit" not in msg:
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


# C-stack-safe ceiling for raising the interpreter recursion limit in-place.
# On CPython <= 3.10 every Python-to-Python call consumes native stack, so a
# raised limit beyond roughly this ceiling lets deep recursive evaluation
# (e.g. the per-JSON-level ``visit`` recursion under fhirpath_repeat) smash
# the default 8 MB thread stack and SEGFAULT the host process before the
# Python-level limit fires (SOF-VD-07 SKEPTIC QA-001, 2026-08-23: crash at
# needed_limit ~57k / JSON depth ~14k). Budgets larger than this ceiling are
# executed on a dedicated thread whose stack is sized for the budget instead.
_INLINE_RECURSION_LIMIT_MAX = 20_000

# Native stack bytes to reserve per Python recursion frame (conservative).
_RECURSION_STACK_BYTES_PER_FRAME = 2048

_RECURSION_STACK_MIN = 1 << 20  # 1 MiB
_RECURSION_STACK_MAX = 1 << 29  # 512 MiB


def _run_with_recursion_budget(func, needed_limit: int, *args):
    """Run ``func()`` with the interpreter recursion limit raised to
    ``needed_limit`` without risking a native stack overflow.

    Small budgets raise the limit in-place. Large budgets run on a worker
    thread whose stack size is sized for the budget, because CPython <= 3.10
    consumes native stack for every Python frame and an in-place raise past
    ``_INLINE_RECURSION_LIMIT_MAX`` can overflow the default 8 MB stack.
    """
    current_limit = sys.getrecursionlimit()
    if needed_limit <= current_limit:
        return func(*args)

    if needed_limit <= _INLINE_RECURSION_LIMIT_MAX:
        try:
            with _RECURSION_LIMIT_LOCK:
                sys.setrecursionlimit(needed_limit)
                return func(*args)
        finally:
            with _RECURSION_LIMIT_LOCK:
                if sys.getrecursionlimit() != current_limit:
                    sys.setrecursionlimit(current_limit)

    # Large budget: provide real native stack instead of over-promising on
    # the current thread's 8 MB stack. If a worker stack cannot be configured
    # (platform restriction), degrade to the safe inline ceiling so the worst
    # outcome is a clean RecursionError, never a segfault.
    import threading

    stack_bytes = min(
        max(needed_limit * _RECURSION_STACK_BYTES_PER_FRAME, _RECURSION_STACK_MIN),
        _RECURSION_STACK_MAX,
    )
    worker_supported = True
    previous_stack_size = None
    try:
        previous_stack_size = threading.stack_size()
        threading.stack_size(stack_bytes)
    except (ValueError, RuntimeError, OverflowError):
        worker_supported = False

    if not worker_supported:
        try:
            with _RECURSION_LIMIT_LOCK:
                sys.setrecursionlimit(_INLINE_RECURSION_LIMIT_MAX)
                return func(*args)
        finally:
            with _RECURSION_LIMIT_LOCK:
                if sys.getrecursionlimit() != current_limit:
                    sys.setrecursionlimit(current_limit)

    outcome: dict = {}

    def _worker():
        try:
            with _RECURSION_LIMIT_LOCK:
                sys.setrecursionlimit(needed_limit)
            try:
                outcome["value"] = func(*args)
            finally:
                with _RECURSION_LIMIT_LOCK:
                    if sys.getrecursionlimit() != current_limit:
                        sys.setrecursionlimit(current_limit)
        except BaseException as exc:  # noqa: BLE001 - re-raised on caller
            outcome["error"] = exc

    thread = threading.Thread(
        target=_worker, name="fhirpath-recursion-budget", daemon=True
    )
    thread.start()
    thread.join()

    try:
        if previous_stack_size is not None:
            threading.stack_size(previous_stack_size)
    except (ValueError, RuntimeError, OverflowError):
        pass

    if "error" in outcome:
        raise outcome["error"]
    return outcome.get("value")


def _eval_with_recursion_budget(func, resource: object, expression: str) -> object:
    """Run ``func(resource)`` with a Python recursion budget sized for both
    the resource JSON nesting and the expression syntactic nesting.

    Each AST node in the recursive ``do_eval`` evaluator consumes ~5-10
    Python stack frames; without this budget, pathological expressions
    (250+-element unions / 250+-deep parens / 250+-deep function call
    chains) raise ``RecursionError`` which the UDF wrapper would silently
    swallow as empty. See FP-19 EXPLORER QA-001 (2026-06-30).
    """
    current_limit = sys.getrecursionlimit()
    json_depth = _json_max_nesting_depth(resource) if isinstance(resource, str) else 0
    expr_depth = _expression_max_nesting_depth(expression) if isinstance(expression, str) else 0
    # ~10 frames per AST node for the evaluator's recursive do_eval, plus
    # 4 frames per JSON nesting level for resource traversal, plus a
    # 1000-frame floor for ordinary Python machinery.
    needed_limit = max(
        current_limit,
        (expr_depth * 10) + (json_depth * 4) + 1000,
    )
    return _run_with_recursion_budget(func, needed_limit, resource)


def _json_default(obj: object) -> object:
    """JSON serialization fallback for types not natively supported."""
    from decimal import Decimal

    if isinstance(obj, Decimal):
        return float(obj)
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")


def _json_serialize(obj: object) -> str:
    """Serialize an object to a JSON string using orjson for performance.

    orjson enforces an internal nesting ceiling (~127 levels) and raises
    ``TypeError("Recursion limit reached")`` for deeper — but valid — JSON
    trees (e.g. chained Extensions). The native C++ evaluator serializes such
    results fine, so the Python fallback must not silently diverge to empty
    output. SOF-VD-11 EXPLORER QA-001 (2026-08-23): fall back to the
    iterative (explicit-stack) serializer for deeply nested structures.
    """
    try:
        return orjson.dumps(obj, default=_json_default).decode()
    except TypeError as exc:
        if "recursion limit" not in str(exc).lower():
            raise
        return _json_serialize_iterative(obj)


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

    # FP-18 SKEPTIC QA-005 (2026-08-18): `FP_TimeBase.plus` raises bare
    # ValueError for §6.7.1-invalid units (e.g. `@2012-01-01 + 25 hours`).
    # Convert to FHIRPathError so `fhirpath_is_valid` classifies it as an
    # accepted execution error (the native engine returns empty) instead
    # of leaking a raw ValueError.
    try:
        result = literal.plus(FP_Quantity(value, match.group("unit")))
    except ValueError as exc:
        raise FHIRPathError(str(exc)) from exc
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
    if _INVALID_TYPE_SPECIFIER_INVOCATION.search(_mask_string_literals(precheck_text)):
        raise FHIRPathSyntaxError(
            f"Invalid FHIRPath expression: rejected by pattern check: '{expression}'"
        )
    if _INVALID_DOLLAR_PATTERNS.search(_mask_string_literals(precheck_text)):
        raise FHIRPathSyntaxError(
            f"Invalid FHIRPath expression: rejected by pattern check: '{expression}'"
        )
    if _has_invalid_timezone_literal(stripped):
        raise FHIRPathSyntaxError(
            f"Invalid FHIRPath expression: invalid timezone placement in '{expression}'"
        )
    if _has_out_of_range_integer_literal(stripped):
        raise FHIRPathSyntaxError(
            f"Invalid FHIRPath expression: integer literal out of range in '{expression}'"
        )
    if _has_out_of_range_long_literal(stripped):
        raise FHIRPathSyntaxError(
            f"Invalid FHIRPath expression: long literal out of range in '{expression}'"
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
_KNOWN_FHIRPATH_FUNCTIONS = frozenset(
    {
        # Existence (§5.1)
        "empty",
        "exists",
        "all",
        "allTrue",
        "anyTrue",
        "allFalse",
        "anyFalse",
        "subsetOf",
        "supersetOf",
        "count",
        "distinct",
        "isDistinct",
        # Filtering and projection (§5.2)
        "where",
        "select",
        "repeat",
        "ofType",
        # Subsetting (§5.3)
        "single",
        "first",
        "last",
        "tail",
        "skip",
        "take",
        "intersect",
        "exclude",
        # Combining (§5.4)
        "union",
        "combine",
        # Conversion (§5.5)
        "iif",
        "toBoolean",
        "convertsToBoolean",
        "toInteger",
        "convertsToInteger",
        "toDate",
        "convertsToDate",
        "toDateTime",
        "convertsToDateTime",
        "toDecimal",
        "convertsToDecimal",
        "toString",
        "convertsToString",
        "toQuantity",
        "convertsToQuantity",
        "toTime",
        "convertsToTime",
        # String functions (§5.7)
        "indexOf",
        "substring",
        "startsWith",
        "endsWith",
        "contains",
        "upper",
        "lower",
        "replace",
        "matches",
        "replaceMatches",
        "length",
        "toChars",
        "trim",
        "split",
        "join",
        "encode",
        "decode",
        # Math (§5.8)
        "abs",
        "ceiling",
        "exp",
        "floor",
        "ln",
        "log",
        "power",
        "round",
        "sqrt",
        "truncate",
        # Tree navigation (§5.9)
        "children",
        "descendants",
        # Utility (§5.10)
        "trace",
        "now",
        "timeOfDay",
        "today",
        "defineVariable",
        # Types (§5.11/§6)
        "is",
        "as",
        "type",
        # Aggregate (§5.12)
        "aggregate",
        # STU/date-time helpers implemented by native/public surfaces
        "lowBoundary",
        "highBoundary",
        "precision",
        "yearOf",
        "monthOf",
        "dayOf",
        "hourOf",
        "minuteOf",
        "secondOf",
        "millisecondOf",
        "timezoneOffsetOf",
        "escape",
        "unescape",
        "matchesFull",
        "comparable",
        "coalesce",
        "repeatAll",
        "sort",
        # FHIR-specific
        "resolve",
        "extension",
        "hasValue",
        "getValue",
        "getResourceKey",
        "getReferenceKey",
        "memberOf",
        "htmlChecks",
        "htmlChecks2",
        "conformsTo",
        "elementDefinition",
        "slice",
        "checkModifiers",
        "hasTemplateIdOf",
        "create",
        "withExtension",
        "withProperty",
        "empty_collection",
        # Boolean
        "not",
    }
)

# Pattern to extract function names from FHIRPath expressions
_FHIRPATH_FUNC_RE = re.compile(r"\.?([a-zA-Z_]\w*)\s*\(")
_FHIRPATH_OPERATOR_KEYWORDS = frozenset(
    {"and", "or", "xor", "implies", "in", "contains", "is", "as"}
)
_FHIRPATH_STRING_SEARCH_ARITY = {
    "indexOf": (1, 1),
    "substring": (1, 2),
    "startsWith": (1, 1),
    "endsWith": (1, 1),
    "contains": (1, 1),
    "upper": (0, 0),
    "lower": (0, 0),
    "trim": (0, 0),
    "replace": (2, 2),
    "matches": (1, 2),
    "replaceMatches": (2, 3),
    "length": (0, 0),
    "toChars": (0, 0),
}
_FHIRPATH_STRING_ARG_TYPES = {
    "indexOf": ("String",),
    "substring": ("Integer", "Integer"),
    "startsWith": ("String",),
    "endsWith": ("String",),
    "contains": ("String",),
    "replace": ("String", "String"),
    "matches": ("String", "String"),
    "replaceMatches": ("String", "String", "String"),
}
_FHIRPATH_REGEX_ARG_INDEXES = {"matches": (0,), "replaceMatches": (0,)}
_FHIRPATH_REGEX_FLAG_ARG_INDEX = {"matches": 1, "replaceMatches": 2}
_FHIRPATH_MATH_ARITY = {
    "abs": (0, 0),
    "ceiling": (0, 0),
    "exp": (0, 0),
    "floor": (0, 0),
    "ln": (0, 0),
    "log": (1, 1),
    "power": (1, 1),
    "round": (0, 1),
    "sqrt": (0, 0),
    "truncate": (0, 0),
}
_FHIRPATH_MATH_ARG_TYPES = {
    "log": ("Number",),
    "power": ("Number",),
    "round": ("Integer",),
}


def _function_scan_text(expression: str) -> str:
    """Mask comments, strings, identifiers, and temporal literals before scanning calls."""
    text = _strip_comments_for_precheck(expression)
    text = re.sub(r"'(?:\\.|[^\\'])*'", "S", text)
    text = re.sub(r"`(?:\\.|[^\\`])*`", "I", text)
    text = re.sub(r"@[T0-9:.\-+Z]+", "D", text)
    return text


def _unknown_function_names(expression: str) -> list[str]:
    """Return lower-case-style unknown function calls in an expression."""
    unknown: list[str] = []
    scan_text = _function_scan_text(expression)
    for match in _FHIRPATH_FUNC_RE.finditer(scan_text):
        func_name = match.group(1)
        if func_name in _FHIRPATH_OPERATOR_KEYWORDS:
            prefix = scan_text[: match.start()].rstrip()
            if prefix and not prefix.endswith("."):
                continue
        if func_name not in _KNOWN_FHIRPATH_FUNCTIONS:
            # Skip common non-function patterns such as resource type names and
            # constructor-like clinical/FHIR type helpers.
            if func_name[0].isupper():
                continue
            unknown.append(func_name)
    return unknown


def _argument_count_at_call(scan_text: str, open_paren: int) -> int | None:
    args = _arguments_at_call(scan_text, open_paren)
    return None if args is None else len(args)


def _arguments_at_call(scan_text: str, open_paren: int) -> list[str] | None:
    depth = 0
    args: list[str] = []
    token_seen = False
    start = open_paren + 1
    i = open_paren + 1
    while i < len(scan_text):
        ch = scan_text[i]
        if ch == "(":
            depth += 1
            token_seen = True
        elif ch == ")":
            if depth == 0:
                if not token_seen and not args:
                    return []
                args.append(scan_text[start:i].strip())
                return args
            depth -= 1
        elif ch == "," and depth == 0:
            args.append(scan_text[start:i].strip())
            start = i + 1
            token_seen = False
        elif not ch.isspace():
            token_seen = True
        i += 1
    return None


def _has_invalid_string_search_arity(expression: str) -> bool:
    scan_text = _function_scan_text(expression)
    for match in _FHIRPATH_FUNC_RE.finditer(scan_text):
        func_name = match.group(1)
        if func_name not in _FHIRPATH_STRING_SEARCH_ARITY:
            continue
        is_method_call = match.group(0).startswith(".")
        if func_name in _FHIRPATH_OPERATOR_KEYWORDS and not is_method_call:
            prefix = scan_text[: match.start()].rstrip()
            if prefix and not prefix.endswith("."):
                continue
        arg_count = _argument_count_at_call(scan_text, match.end() - 1)
        if arg_count is None:
            return True
        min_args, max_args = _FHIRPATH_STRING_SEARCH_ARITY[func_name]
        if arg_count < min_args or arg_count > max_args:
            return True
    return False


def _has_invalid_math_arity(expression: str) -> bool:
    scan_text = _function_scan_text(expression)
    for match in _FHIRPATH_FUNC_RE.finditer(scan_text):
        func_name = match.group(1)
        if func_name not in _FHIRPATH_MATH_ARITY:
            continue
        arg_count = _argument_count_at_call(scan_text, match.end() - 1)
        if arg_count is None:
            return True
        min_args, max_args = _FHIRPATH_MATH_ARITY[func_name]
        if arg_count < min_args or arg_count > max_args:
            return True
    return False


_INTEGER_LITERAL_RE = re.compile(r"[+-]?[0-9]+")
_DECIMAL_LITERAL_RE = re.compile(r"[+-]?(?:[0-9]+\.[0-9]+|[0-9]+\.|[0-9]*\.[0-9]+)")


def _is_empty_collection_arg(arg: str) -> bool:
    return arg.strip() == "{}"


def _is_string_literal_arg(arg: str) -> bool:
    return arg.strip() == "S"


def _is_obvious_non_string_literal_arg(arg: str) -> bool:
    stripped = arg.strip()
    return (
        stripped in {"true", "false"}
        or _INTEGER_LITERAL_RE.fullmatch(stripped) is not None
        or _DECIMAL_LITERAL_RE.fullmatch(stripped) is not None
        or stripped == "D"
    )


def _is_obvious_non_integer_literal_arg(arg: str) -> bool:
    stripped = arg.strip()
    return (
        _is_string_literal_arg(stripped)
        or stripped in {"true", "false"}
        or _DECIMAL_LITERAL_RE.fullmatch(stripped) is not None
        or stripped == "D"
    )


def _is_obvious_literal_union_arg(arg: str) -> bool:
    compact = re.sub(r"\s+", "", arg.strip())
    return (
        re.fullmatch(r"\(?[SDtruefals0-9+.\-]+(?:\|[SDtruefals0-9+.\-]+)+\)?", compact) is not None
    )


def _function_scan_text_preserve_positions(expression: str) -> str:
    """Mask non-code spans while preserving indexes into the original string."""
    chars = list(expression)
    i = 0
    while i < len(chars):
        ch = chars[i]
        next_ch = chars[i + 1] if i + 1 < len(chars) else ""
        if ch == "/" and next_ch == "/":
            j = i
            while j < len(chars) and chars[j] not in "\r\n":
                chars[j] = " "
                j += 1
            i = j
            continue
        if ch == "/" and next_ch == "*":
            j = i
            while j < len(chars):
                end = chars[j] == "*" and j + 1 < len(chars) and chars[j + 1] == "/"
                chars[j] = " "
                if end:
                    chars[j + 1] = " "
                    j += 2
                    break
                j += 1
            i = j
            continue
        if ch in {"'", "`"}:
            quote = ch
            chars[i] = " "
            i += 1
            while i < len(chars):
                current = chars[i]
                chars[i] = " "
                if current == "\\" and i + 1 < len(chars):
                    chars[i + 1] = " "
                    i += 2
                    continue
                i += 1
                if current == quote:
                    break
            continue
        i += 1
    return "".join(chars)


def _split_call_args_original(expression: str, open_paren: int) -> list[str] | None:
    args: list[str] = []
    token_seen = False
    start = open_paren + 1
    depth_paren = 0
    depth_brace = 0
    depth_bracket = 0
    i = open_paren + 1
    while i < len(expression):
        ch = expression[i]
        if ch in {"'", "`"}:
            quote = ch
            token_seen = True
            i += 1
            while i < len(expression):
                current = expression[i]
                if current == "\\" and i + 1 < len(expression):
                    i += 2
                    continue
                i += 1
                if current == quote:
                    break
            continue
        if ch == "(":
            depth_paren += 1
            token_seen = True
        elif ch == ")":
            if depth_paren == 0 and depth_brace == 0 and depth_bracket == 0:
                if not token_seen and not args:
                    return []
                args.append(expression[start:i].strip())
                return args
            depth_paren -= 1
        elif ch == "{":
            depth_brace += 1
            token_seen = True
        elif ch == "}":
            depth_brace -= 1
        elif ch == "[":
            depth_bracket += 1
            token_seen = True
        elif ch == "]":
            depth_bracket -= 1
        elif ch == "," and depth_paren == 0 and depth_brace == 0 and depth_bracket == 0:
            args.append(expression[start:i].strip())
            start = i + 1
            token_seen = False
        elif not ch.isspace():
            token_seen = True
        i += 1
    return None


def _has_wrapping_parens(text: str) -> bool:
    if not (text.startswith("(") and text.endswith(")")):
        return False
    depth = 0
    i = 0
    while i < len(text):
        ch = text[i]
        if ch in {"'", "`"}:
            quote = ch
            i += 1
            while i < len(text):
                current = text[i]
                if current == "\\" and i + 1 < len(text):
                    i += 2
                    continue
                i += 1
                if current == quote:
                    break
            continue
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0 and i != len(text) - 1:
                return False
        i += 1
    return depth == 0


def _strip_wrapping_parens(text: str) -> str:
    stripped = text.strip()
    while _has_wrapping_parens(stripped):
        stripped = stripped[1:-1].strip()
    return stripped


def _split_top_level_union(text: str) -> list[str] | None:
    stripped = _strip_wrapping_parens(text)
    parts: list[str] = []
    start = 0
    depth_paren = 0
    depth_brace = 0
    depth_bracket = 0
    i = 0
    while i < len(stripped):
        ch = stripped[i]
        if ch in {"'", "`"}:
            quote = ch
            i += 1
            while i < len(stripped):
                current = stripped[i]
                if current == "\\" and i + 1 < len(stripped):
                    i += 2
                    continue
                i += 1
                if current == quote:
                    break
            continue
        if ch == "(":
            depth_paren += 1
        elif ch == ")":
            depth_paren -= 1
        elif ch == "{":
            depth_brace += 1
        elif ch == "}":
            depth_brace -= 1
        elif ch == "[":
            depth_bracket += 1
        elif ch == "]":
            depth_bracket -= 1
        elif ch == "|" and depth_paren == 0 and depth_brace == 0 and depth_bracket == 0:
            parts.append(stripped[start:i].strip())
            start = i + 1
        i += 1
    if not parts:
        return None
    parts.append(stripped[start:].strip())
    return parts


def _simple_literal_signature(text: str) -> tuple[str, object] | None:
    stripped = _strip_wrapping_parens(text)
    if stripped == "{}":
        return ("Empty", None)
    if re.fullmatch(r"'(?:\\.|[^\\'])*'", stripped):
        try:
            from ..engine.evaluators import _unescape_fhirpath_string

            return ("String", _unescape_fhirpath_string(stripped[1:-1]))
        except Exception:
            return ("String", stripped)
    if stripped in {"true", "false"}:
        return ("Boolean", stripped == "true")
    if _INTEGER_LITERAL_RE.fullmatch(stripped):
        return ("Integer", int(stripped))
    if _DECIMAL_LITERAL_RE.fullmatch(stripped):
        return ("Decimal", Decimal(stripped))
    if stripped.startswith("@"):
        return ("Temporal", stripped)
    return None


def _literal_union_seen_key(signature: tuple[str, object]) -> tuple[str, object]:
    if signature[0] in {"Integer", "Decimal"}:
        return ("Number", Decimal(signature[1]))
    return signature


def _literal_union_effective_items(arg: str) -> list[tuple[str, object]] | None:
    parts = _split_top_level_union(arg)
    if parts is None:
        return None
    effective: list[tuple[str, object]] = []
    seen: set[tuple[str, object]] = set()
    for part in parts:
        signature = _simple_literal_signature(part)
        if signature is None:
            return None
        if signature[0] == "Empty":
            continue
        seen_key = _literal_union_seen_key(signature)
        if seen_key not in seen:
            seen.add(seen_key)
            effective.append(signature)
    return effective


def _is_keyword_at(scan_text: str, index: int, keyword: str) -> bool:
    end = index + len(keyword)
    if scan_text[index:end] != keyword:
        return False
    previous = scan_text[index - 1] if index > 0 else ""
    following = scan_text[end] if end < len(scan_text) else ""
    return not (previous.isalnum() or previous == "_") and not (
        following.isalnum() or following == "_"
    )


def _split_top_level_keyword_segments(text: str, keywords: tuple[str, ...]) -> list[str] | None:
    scan_text = _function_scan_text_preserve_positions(text)
    sorted_keywords = sorted(keywords, key=len, reverse=True)
    parts: list[str] = []
    start = 0
    depth_paren = 0
    depth_brace = 0
    depth_bracket = 0
    i = 0
    while i < len(scan_text):
        ch = scan_text[i]
        if depth_paren == 0 and depth_brace == 0 and depth_bracket == 0:
            matched_keyword = None
            for keyword in sorted_keywords:
                if _is_keyword_at(scan_text, i, keyword):
                    matched_keyword = keyword
                    break
            if matched_keyword is not None:
                parts.append(text[start:i].strip())
                i += len(matched_keyword)
                start = i
                continue
        if ch == "(":
            depth_paren += 1
        elif ch == ")":
            depth_paren -= 1
        elif ch == "{":
            depth_brace += 1
        elif ch == "}":
            depth_brace -= 1
        elif ch == "[":
            depth_bracket += 1
        elif ch == "]":
            depth_bracket -= 1
        i += 1
    if not parts:
        return None
    parts.append(text[start:].strip())
    return parts


def _split_top_level_pipe_segments(text: str) -> list[str] | None:
    """Split an expression on top-level '|' union operators (§6.8 #07).

    Strings, backtick identifiers, and comments are masked via the
    position-preserving scan text; pipes nested inside (), {}, or [] are
    part of a parenthesized operand, not a top-level union boundary.
    Returns None when no top-level pipe exists.
    """
    scan_text = _function_scan_text_preserve_positions(text)
    parts: list[str] = []
    start = 0
    depth_paren = 0
    depth_brace = 0
    depth_bracket = 0
    i = 0
    while i < len(scan_text):
        ch = scan_text[i]
        if depth_paren == 0 and depth_brace == 0 and depth_bracket == 0 and ch == "|":
            parts.append(text[start:i].strip())
            start = i + 1
        elif ch == "(":
            depth_paren += 1
        elif ch == ")":
            depth_paren -= 1
        elif ch == "{":
            depth_brace += 1
        elif ch == "}":
            depth_brace -= 1
        elif ch == "[":
            depth_bracket += 1
        elif ch == "]":
            depth_bracket -= 1
        i += 1
    if not parts:
        return None
    parts.append(text[start:].strip())
    return parts


def _iter_top_level_membership_operators(text: str) -> list[tuple[str, int, int]]:
    scan_text = _function_scan_text_preserve_positions(text)
    operators: list[tuple[str, int, int]] = []
    depth_paren = 0
    depth_brace = 0
    depth_bracket = 0
    i = 0
    while i < len(scan_text):
        ch = scan_text[i]
        if depth_paren == 0 and depth_brace == 0 and depth_bracket == 0:
            matched_operator = False
            for operator in ("contains", "in"):
                if not _is_keyword_at(scan_text, i, operator):
                    continue
                previous_nonspace = text[:i].rstrip()[-1:] if text[:i].rstrip() else ""
                if previous_nonspace == ".":
                    continue
                operators.append((operator, i, i + len(operator)))
                i += len(operator)
                matched_operator = True
                break
            if matched_operator:
                continue
        if ch == "(":
            depth_paren += 1
        elif ch == ")":
            depth_paren -= 1
        elif ch == "{":
            depth_brace += 1
        elif ch == "}":
            depth_brace -= 1
        elif ch == "[":
            depth_bracket += 1
        elif ch == "]":
            depth_bracket -= 1
        i += 1
    return operators


def _literal_union_has_multiple_effective_items(arg: str) -> bool:
    effective = _literal_union_effective_items(arg)
    return effective is not None and len(effective) > 1


def _has_invalid_membership_literal_unions(expression: str) -> bool:
    stripped = _strip_wrapping_parens(expression.strip())
    if not stripped:
        return False

    logical_parts = _split_top_level_keyword_segments(stripped, ("implies", "and", "or", "xor"))
    if logical_parts is not None:
        return any(_has_invalid_membership_literal_unions(part) for part in logical_parts)

    for operator, start, end in _iter_top_level_membership_operators(stripped):
        left = stripped[:start].strip()
        right = stripped[end:].strip()
        if operator == "in" and _literal_union_has_multiple_effective_items(left):
            return True
        if operator == "contains" and _literal_union_has_multiple_effective_items(right):
            return True
        if _has_invalid_membership_literal_unions(left) or _has_invalid_membership_literal_unions(
            right
        ):
            return True

    return False


def _iter_top_level_math_operators(text: str) -> list[tuple[str, int, int]]:
    scan_text = _function_scan_text_preserve_positions(text)
    operators: list[tuple[str, int, int]] = []
    depth_paren = 0
    depth_brace = 0
    depth_bracket = 0
    i = 0
    while i < len(scan_text):
        ch = scan_text[i]
        if depth_paren == 0 and depth_brace == 0 and depth_bracket == 0:
            if ch in {"*", "/", "&"}:
                operators.append((ch, i, i + 1))
                i += 1
                continue
            if ch in {"+", "-"}:
                if not _is_unary_minus_context(scan_text, i):
                    operators.append((ch, i, i + 1))
                    i += 1
                    continue
            matched_keyword = False
            for operator in ("div", "mod"):
                if _is_keyword_at(scan_text, i, operator):
                    operators.append((operator, i, i + len(operator)))
                    i += len(operator)
                    matched_keyword = True
                    break
            if matched_keyword:
                continue
        if ch == "(":
            depth_paren += 1
        elif ch == ")":
            depth_paren -= 1
        elif ch == "{":
            depth_brace += 1
        elif ch == "}":
            depth_brace -= 1
        elif ch == "[":
            depth_bracket += 1
        elif ch == "]":
            depth_bracket -= 1
        i += 1
    return operators


def _has_invalid_math_literal_operands(expression: str) -> bool:
    stripped = _strip_wrapping_parens(expression.strip())
    if not stripped:
        return False

    logical_parts = _split_top_level_keyword_segments(stripped, ("implies", "and", "or", "xor"))
    if logical_parts is not None:
        return any(_has_invalid_math_literal_operands(part) for part in logical_parts)

    # FP-02 SKEPTIC QA-001 (2026-08-16): §6.8 precedence — arithmetic
    # operators (#04 `* / div mod`, #05 `+ - &`) bind TIGHTER than the '|'
    # union operator (#07), so `1 + 2 | 3` parses as `(1 + 2) | 3` and the
    # `+` operand is only the adjacent term. Analyze each top-level union
    # segment independently instead of attributing the whole textual side
    # of a math operator to it. Parenthesized unions like `(1 | 2) + 3`
    # contain no top-level pipe and are still flagged below.
    pipe_parts = _split_top_level_pipe_segments(stripped)
    if pipe_parts is not None:
        return any(_has_invalid_math_literal_operands(part) for part in pipe_parts)

    operators = _iter_top_level_math_operators(stripped)
    if not operators:
        return False
    for _operator, start, end in operators:
        left = stripped[:start].strip()
        right = stripped[end:].strip()
        if _literal_union_has_multiple_effective_items(left):
            return True
        if _literal_union_has_multiple_effective_items(right):
            return True
        if _has_invalid_math_literal_operands(left) or _has_invalid_math_literal_operands(right):
            return True
    return False


def _has_invalid_string_search_literal_unions(expression: str) -> bool:
    scan_text = _function_scan_text_preserve_positions(expression)
    for match in _FHIRPATH_FUNC_RE.finditer(scan_text):
        func_name = match.group(1)
        expected_types = _FHIRPATH_STRING_ARG_TYPES.get(func_name)
        if expected_types is None:
            continue
        is_method_call = match.group(0).startswith(".")
        if func_name in _FHIRPATH_OPERATOR_KEYWORDS and not is_method_call:
            prefix = scan_text[: match.start()].rstrip()
            if prefix and not prefix.endswith("."):
                continue
        args = _split_call_args_original(expression, match.end() - 1)
        if args is None:
            return True
        for index, expected_type in enumerate(expected_types):
            if index >= len(args):
                continue
            effective = _literal_union_effective_items(args[index])
            if effective is None:
                continue
            if len(effective) == 0:
                continue
            if len(effective) > 1 or effective[0][0] != expected_type:
                return True
    return False


def _has_invalid_math_literal_unions(expression: str) -> bool:
    scan_text = _function_scan_text_preserve_positions(expression)
    for match in _FHIRPATH_FUNC_RE.finditer(scan_text):
        func_name = match.group(1)
        expected_types = _FHIRPATH_MATH_ARG_TYPES.get(func_name)
        if expected_types is None:
            continue
        args = _split_call_args_original(expression, match.end() - 1)
        if args is None:
            return True
        for index, expected_type in enumerate(expected_types):
            if index >= len(args):
                continue
            effective = _literal_union_effective_items(args[index])
            if effective is None:
                signature = _simple_literal_signature(args[index])
                if signature is None:
                    continue
                effective = [] if signature[0] == "Empty" else [signature]
            if len(effective) == 0:
                continue
            if len(effective) > 1:
                return True
            actual_type = effective[0][0]
            if expected_type == "Number" and actual_type not in {"Integer", "Decimal"}:
                return True
            if expected_type == "Integer" and actual_type != "Integer":
                return True
            if func_name == "round" and expected_type == "Integer" and int(effective[0][1]) < 0:
                return True
    return False


def _has_invalid_string_search_literal_args(expression: str) -> bool:
    scan_text = _function_scan_text(expression)
    for match in _FHIRPATH_FUNC_RE.finditer(scan_text):
        func_name = match.group(1)
        expected_types = _FHIRPATH_STRING_ARG_TYPES.get(func_name)
        if expected_types is None:
            continue
        is_method_call = match.group(0).startswith(".")
        if func_name in _FHIRPATH_OPERATOR_KEYWORDS and not is_method_call:
            prefix = scan_text[: match.start()].rstrip()
            if prefix and not prefix.endswith("."):
                continue
        args = _arguments_at_call(scan_text, match.end() - 1)
        if args is None:
            return True
        for index, expected_type in enumerate(expected_types):
            if index >= len(args) or _is_empty_collection_arg(args[index]):
                continue
            if expected_type == "Integer" and _is_obvious_non_integer_literal_arg(args[index]):
                return True
            if expected_type == "String" and _is_obvious_non_string_literal_arg(args[index]):
                return True
    return False


def _has_invalid_math_literal_args(expression: str) -> bool:
    scan_text = _function_scan_text(expression)
    for match in _FHIRPATH_FUNC_RE.finditer(scan_text):
        func_name = match.group(1)
        expected_types = _FHIRPATH_MATH_ARG_TYPES.get(func_name)
        if expected_types is None:
            continue
        args = _arguments_at_call(scan_text, match.end() - 1)
        if args is None:
            return True
        for index, expected_type in enumerate(expected_types):
            if index >= len(args) or _is_empty_collection_arg(args[index]):
                continue
            if expected_type == "Integer" and _is_obvious_non_integer_literal_arg(args[index]):
                return True
            if expected_type == "Number":
                stripped_arg = args[index].strip()
                if (
                    _is_string_literal_arg(stripped_arg)
                    or stripped_arg in {"true", "false"}
                    or stripped_arg == "D"
                ):
                    return True
    return False


def _has_invalid_string_regex_literals(expression: str) -> bool:
    scan_text = _function_scan_text_preserve_positions(expression)
    for match in _FHIRPATH_FUNC_RE.finditer(scan_text):
        func_name = match.group(1)
        regex_indexes = _FHIRPATH_REGEX_ARG_INDEXES.get(func_name)
        if regex_indexes is None:
            continue
        args = _split_call_args_original(expression, match.end() - 1)
        if args is None:
            return True
        compile_flags = 0
        flags_index = _FHIRPATH_REGEX_FLAG_ARG_INDEX.get(func_name)
        if flags_index is not None and flags_index < len(args):
            flags_signature = _simple_literal_signature(args[flags_index])
            if flags_signature is None or flags_signature[0] != "String":
                continue
            try:
                from ..engine.invocations.strings import _regex_flags

                compile_flags = _regex_flags(str(flags_signature[1]))
            except FHIRPathError:
                return True
        for index in regex_indexes:
            if index >= len(args):
                continue
            signature = _simple_literal_signature(args[index])
            if signature is None or signature[0] != "String":
                continue
            try:
                from ..engine.invocations.strings import _compile_regex, _translate_named_groups

                # FP-10 HISTORIAN QA-001: (?<name>...) named groups are valid
                # §5.6.10 syntax; translate them for the Python re compile
                # check exactly as the engine does.
                _compile_regex(_translate_named_groups(str(signature[1])), compile_flags)
            except FHIRPathError:
                return True
    return False


def _warn_unknown_functions(expression: str) -> None:
    """Log warnings for unrecognized function names in a FHIRPath expression."""
    for func_name in _unknown_function_names(expression):
        _logger.warning(
            "FHIRPath expression contains unknown function '%s' — "
            "possible typo (will return empty/NULL): %s",
            func_name,
            expression,
        )


# Lazily cached choice type lookup table: base_name -> list of suffixed field names
_choice_type_lookup: dict[str, list[str]] | None = None
_choice_type_lock = __import__("threading").Lock()


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
                        # Only include ACTUAL choice types (multiple type
                        # options). Single-option entries are not value[x]
                        # choice fields: e.g. "Resource.contained":
                        # ["containedResource"] is the 0..* Resource backbone
                        # (R4), and "Observation.subject":
                        # ["subjectReference"] is a plain Reference field.
                        # Treating them as choice fields made the
                        # choice-assertion rescue hijack correct evaluator
                        # results for `contained is/as(T)` (FP-15 SKEPTIC
                        # QA-003, 2026-08-18). Mirrors the same rule in
                        # fhir_model.py::build_fhir_model.
                        if len(field_names) <= 1:
                            continue
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
    if match:
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

    trailing_match = re.fullmatch(
        r"\s*(?P<source>.+)\.ofType\(\s*(?P<type>`?[A-Za-z_]\w*`?(?:\.`?[A-Za-z_]\w*`?)*)\s*\)\s*",
        expression,
    )
    if not trailing_match:
        return []

    source_expression = trailing_match.group("source").strip()
    if not source_expression:
        return []

    # FHIRPath §5.2.4 parity: this trailing-regex branch is a rescue path for
    # choice-typed sources (e.g., `Observation.value`) where fhirpathpy missed
    # the ofType() resolution. It MUST NOT fire for plain primitive fields
    # like `Patient.id` (which is a non-choice field of FHIR type `id`), or
    # it will overwrite the engine's correct empty result with the raw value
    # — causing `id.ofType(string)` to wrongly return the value. Gate on the
    # source's last segment being a known choice-type base name.
    source_last_segment = source_expression.rsplit(".", 1)[-1]
    if source_last_segment not in _get_choice_type_lookup():
        return []

    try:
        type_text = trailing_match.group("type")
        if type_text.replace("`", "").startswith("System."):
            return []
        from ..engine import type_specifier
        from ..engine.invocations import filtering as filtering_invocations

        source_items = _evaluate_raw_items(resource_dict, source_expression)
        if not source_items:
            return []
        requested_type = type_specifier({}, [], {"text": type_text})
        return filtering_invocations.of_type_fn({}, source_items, requested_type)
    except (
        FHIRPathError,
        NotImplementedError,
        ValueError,
        TypeError,
        KeyError,
        AttributeError,
        IndexError,
    ):
        return []


_CHOICE_ASSERTION_METHOD_RE = re.compile(
    r"^\s*(?P<path>[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*)\."
    r"(?P<op>is|as)\(\s*(?P<type>`?[\w.]+`?)\s*\)\s*$",
    re.IGNORECASE,
)
_CHOICE_ASSERTION_INFIX_RE = re.compile(
    r"^\s*(?P<path>[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*)\s+" r"(?P<op>is|as)\s+(?P<type>`?[\w.]+`?)\s*$",
    re.IGNORECASE,
)
_TRAILING_CHOICE_ASSERTION_METHOD_RE = re.compile(
    r"^\s*(?P<source>.+)\.(?P<base>[A-Za-z_]\w*)\."
    r"(?P<op>is|as)\(\s*(?P<type>`?[\w.]+`?)\s*\)\s*$",
    re.IGNORECASE,
)
_TRAILING_CHOICE_ASSERTION_INFIX_RE = re.compile(
    r"^\s*(?P<source>.+)\.(?P<base>[A-Za-z_]\w*)\s+"
    r"(?P<op>is|as)\s+(?P<type>`?[\w.]+`?)\s*$",
    re.IGNORECASE,
)
_OFTYPE_TYPE_CHAIN_RE = re.compile(
    r"\.ofType\([^)]*\).*(?:\.(?:is|as)\(|\s+(?:is|as)\s+)",
    re.IGNORECASE,
)

_KNOWN_FUNCTION_NAMES = frozenset(
    {
        "abs",
        "aggregate",
        "all",
        "allFalse",
        "allTrue",
        "anyFalse",
        "anyTrue",
        "as",
        "ceiling",
        "checkModifiers",
        "children",
        "coalesce",
        "combine",
        "comparable",
        "conformsTo",
        "contains",
        "convertsToBoolean",
        "convertsToDate",
        "convertsToDateTime",
        "convertsToDecimal",
        "convertsToInteger",
        "convertsToQuantity",
        "convertsToString",
        "convertsToTime",
        "count",
        "dayOf",
        "decode",
        "defineVariable",
        "descendants",
        "distinct",
        "elementDefinition",
        "empty",
        "empty_collection",
        "encode",
        "endsWith",
        "escape",
        "exclude",
        "exists",
        "exp",
        "first",
        "floor",
        "getValue",
        "hasTemplateIdOf",
        "hasValue",
        "highBoundary",
        "hourOf",
        "htmlChecks",
        "htmlChecks2",
        "iif",
        "indexOf",
        "intersect",
        "is",
        "isDistinct",
        "join",
        "last",
        "length",
        "ln",
        "log",
        "lowBoundary",
        "lower",
        "matches",
        "matchesFull",
        "memberOf",
        "millisecondOf",
        "minuteOf",
        "monthOf",
        "not",
        "now",
        "ofType",
        "power",
        "precision",
        "repeat",
        "repeatAll",
        "replace",
        "replaceMatches",
        "resolve",
        "round",
        "secondOf",
        "select",
        "single",
        "skip",
        "sort",
        "split",
        "sqrt",
        "startsWith",
        "slice",
        "subsetOf",
        "substring",
        "supersetOf",
        "tail",
        "take",
        "timeOfDay",
        "timezoneOffsetOf",
        "toBoolean",
        "toChars",
        "toDate",
        "toDateTime",
        "toDecimal",
        "toInteger",
        "toQuantity",
        "toString",
        "toTime",
        "today",
        "trace",
        "trim",
        "truncate",
        "type",
        "unescape",
        "union",
        "upper",
        "where",
        "yearOf",
        "Address",
        "CodeableConcept",
        "Coding",
        "ContactPoint",
        "Extension",
        "HumanName",
        "Identifier",
        "Quantity",
        "create",
        "withExtension",
        "withProperty",
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


_CHOICE_SUFFIX_TO_FHIR_TYPE = {
    "Base64Binary": "base64Binary",
    "Boolean": "boolean",
    "Canonical": "canonical",
    "Code": "code",
    "Date": "date",
    "DateTime": "dateTime",
    "Decimal": "decimal",
    "Id": "id",
    "Instant": "instant",
    "Integer": "integer",
    "Integer64": "integer64",
    "Markdown": "markdown",
    "Oid": "oid",
    "PositiveInt": "positiveInt",
    "String": "string",
    "Time": "time",
    "UnsignedInt": "unsignedInt",
    "Uri": "uri",
    "Url": "url",
    "Uuid": "uuid",
    "Xhtml": "xhtml",
}


def _choice_suffix_to_fhir_type(suffix: str) -> str:
    return _CHOICE_SUFFIX_TO_FHIR_TYPE.get(suffix, suffix)


def _choice_field_is_type(base_name: str, field_name: str, requested_type: str) -> bool:
    requested_suffix = _choice_type_suffix(requested_type)
    if requested_suffix is None or not field_name.startswith(base_name):
        return False
    actual_suffix = field_name[len(base_name):]
    if not actual_suffix:
        return False
    if actual_suffix == requested_suffix:
        return True

    from ..engine.nodes import TypeInfo

    actual_fhir_type = _choice_suffix_to_fhir_type(actual_suffix)
    requested_fhir_type = _choice_suffix_to_fhir_type(requested_suffix)
    return TypeInfo.is_type(actual_fhir_type, requested_fhir_type)


def _resolve_choice_type_assertion(resource_dict: dict, expression: str) -> list | None:
    """Resolve simple choice-type ``is``/``as`` expressions missed by fallback evaluation."""
    match = _CHOICE_ASSERTION_METHOD_RE.fullmatch(
        expression
    ) or _CHOICE_ASSERTION_INFIX_RE.fullmatch(expression)
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
        if op == "is":
            return [False]
        # FP-15 HISTORIAN (2026-08-18) guard-on-empty: defer to the engine
        # instead of clobbering its result with [].
        return None
    target_field = f"{base_name}{suffix}"
    if target_field not in field_names:
        if op != "is":
            # FP-15 HISTORIAN (2026-08-18) guard-on-empty: the requested type
            # is not a declared choice arm; the engine's §6.3 subtype result
            # (e.g. valueUuid as FHIR.string via uuid <: uri <: string) wins.
            return None
        if op == "is":
            # §6.3.1: empty input collection must propagate as empty, not false.
            # When the resource has no populated choice-type field, the input
            # collection to `is` is empty -> result must be empty.
            # See FP-15 HISTORIAN iteration 1 (2026-06-29) QA-002.
            has_any_choice_value = any(
                resource_dict.get(field_name) is not None
                for field_name in field_names
            )
            if not has_any_choice_value:
                return []
            for field_name in field_names:
                if (
                    resource_dict.get(field_name) is not None
                    and _choice_field_is_type(base_name, field_name, match.group("type"))
                ):
                    return [True]
            return [False]
        return []

    if op == "is":
        # §6.3.1: empty input collection must propagate as empty, not false.
        # See FP-15 HISTORIAN iteration 1 (2026-06-29) QA-002.
        has_any_choice_value = any(
            resource_dict.get(field_name) is not None
            for field_name in field_names
        )
        if not has_any_choice_value:
            return []
        for field_name in field_names:
            if (
                resource_dict.get(field_name) is not None
                and _choice_field_is_type(base_name, field_name, match.group("type"))
            ):
                return [True]
        return [False]
    val = resource_dict.get(target_field)
    if val is None:
        # FP-15 HISTORIAN (2026-08-18) guard-on-empty: the target arm is not
        # populated; an empty [] here must not clobber a correct non-empty
        # engine subtype result for `as` (§6.3 "type or subclass").
        return None
    return [val]


def _resolve_trailing_choice_type_assertion(resource_dict: dict, expression: str) -> list | None:
    """Resolve choice ``is``/``as`` after an evaluated source expression.

    fhirpathpy can resolve ``entry.resource.ofType(Observation).value`` to the
    primitive value but loses the FHIR choice field name before ``is``/``as`` is
    applied. Re-evaluate the parent expression and apply singleton choice
    semantics only when exactly one concrete choice value is present.
    """
    match = _TRAILING_CHOICE_ASSERTION_METHOD_RE.fullmatch(
        expression
    ) or _TRAILING_CHOICE_ASSERTION_INFIX_RE.fullmatch(expression)
    if not match:
        return None

    base_name = match.group("base")
    field_names = _get_choice_type_lookup().get(base_name)
    if not field_names:
        return None

    suffix = _choice_type_suffix(match.group("type"))
    if suffix is None:
        target_field = None
    else:
        target_field = f"{base_name}{suffix}"
        if target_field not in field_names:
            target_field = None

    try:
        parents = _evaluate_raw_items(resource_dict, match.group("source").strip())
    except (
        FHIRPathError,
        NotImplementedError,
        ValueError,
        TypeError,
        KeyError,
        AttributeError,
        IndexError,
    ):
        return None

    concrete_values = []
    concrete_fields = []
    target_values = []
    for parent in parents:
        if not isinstance(parent, dict):
            continue
        for field_name in field_names:
            value = parent.get(field_name)
            if value is None:
                continue
            concrete_values.append(value)
            concrete_fields.append(field_name)
            if field_name == target_field:
                target_values.append(value)

    op = match.group("op").lower()
    if not concrete_values:
        # FP-15 EXPLORER iteration 1 (2026-06-29) QA-003 §6.3.1:
        # No choice-type field is populated on the parent. The trailing
        # `.value is X` (or similar) may be resolving to a NON-choice-type
        # field of the same name (e.g. `Identifier.value` is a plain
        # FHIR `string`, not an Observation-style `value[x]` choice).
        # Returning [False]/[] here would override the engine's correct
        # `is_fn` result. Defer to the engine by returning None.
        return None
    if len(concrete_values) > 1:
        return None

    if op == "is":
        return [_choice_field_is_type(base_name, concrete_fields[0], match.group("type"))]
    if target_values:
        return target_values[:1]
    # FP-15 HISTORIAN (2026-08-18) ARCH-001 guard-on-empty: an `as` that does
    # not match a concrete choice arm (or whose requested type is not a
    # declared arm) must DEFER to the engine instead of returning []. The
    # engine implements the §6.3 "type or subclass" rule (e.g.
    # `parameter[0].value as FHIR.string` on a valueUuid arm: uuid <: uri <:
    # string), and a [] here would clobber a correct non-empty engine result.
    return None


def _resolve_choice_type_assertion_any(resource_dict: dict, expression: str) -> list | None:
    result = _resolve_choice_type_assertion(resource_dict, expression)
    if result is not None:
        return result
    return _resolve_trailing_choice_type_assertion(resource_dict, expression)


def _resolve_core_type_chain(resource_dict: dict, expression: str) -> list | None:
    """Use the core evaluator for composed type chains the fallback wrapper loses."""
    if not _OFTYPE_TYPE_CHAIN_RE.search(expression):
        return None
    try:
        from .. import evaluate as core_evaluate

        result = core_evaluate(resource_dict, expression)
    except (
        FHIRPathError,
        NotImplementedError,
        ValueError,
        TypeError,
        KeyError,
        AttributeError,
        IndexError,
    ):
        return None
    return result if isinstance(result, list) else [result]


def _needs_type_chain_rescue(result: object) -> bool:
    return result is None or result == [] or result == [False]


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

            if _is_row_resilient_invalid_literal(expression):
                results.append([])
                continue

            # Get cached evaluator and evaluate. Both the ANTLR parser and
            # the recursive do_evaluator can hit Python's RecursionError on
            # pathological-size expressions. See FP-19 EXPLORER QA-001.
            def _compile_and_evaluate(_resource_dict, _expression=expression):
                evaluator = _get_compiled_evaluator(_expression)
                return evaluator.evaluate(_resource_dict)

            result = _eval_with_recursion_budget(
                _compile_and_evaluate,
                resource_dict,
                expression,
            )

            choice_assertion = _resolve_choice_type_assertion_any(resource_dict, expression)
            if choice_assertion is not None:
                result = choice_assertion
            if not result and isinstance(resource_dict, dict):
                result = _resolve_choice_type(resource_dict, expression)
            if not result and isinstance(resource_dict, dict):
                result = _resolve_choice_oftype(resource_dict, expression)
            if _needs_type_chain_rescue(result):
                core_result = _resolve_core_type_chain(resource_dict, expression)
                if core_result is not None:
                    result = core_result

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
                results.type,
                return_type,
                e,
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
                type(resource).__name__,
                expression,
            )
            return []

        temporal_result = _evaluate_literal_temporal_arithmetic(expression)
        if temporal_result is not None:
            return temporal_result
        if _is_row_resilient_invalid_literal(expression):
            return []

        # Get cached evaluator and evaluate. Both the ANTLR-generated parser
        # (parser.expression()) and the recursive do_evaluator can hit
        # Python's RecursionError on pathological-size expressions; the
        # _eval_with_recursion_budget wrapper temporarily raises the limit
        # based on the expression's syntactic depth. See FP-19 EXPLORER
        # QA-001 (2026-06-30).
        def _compile_and_evaluate(_resource_dict):
            evaluator = _get_compiled_evaluator(expression)
            return evaluator.evaluate(_resource_dict)

        result = _eval_with_recursion_budget(
            _compile_and_evaluate,
            resource_dict,
            expression,
        )

        choice_assertion = _resolve_choice_type_assertion_any(resource_dict, expression)
        if choice_assertion is not None:
            result = choice_assertion

        # Fallback: resolve choice type fields that fhirpathpy misses for primitives
        if not result and isinstance(resource_dict, dict):
            result = _resolve_choice_type(resource_dict, expression)
        if not result and isinstance(resource_dict, dict):
            result = _resolve_choice_oftype(resource_dict, expression)
        if _needs_type_chain_rescue(result):
            core_result = _resolve_core_type_chain(resource_dict, expression)
            if core_result is not None:
                result = core_result

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
                    # FP-11 EXPLORER (2026-06-29): For subnormal floats where
                    # `format(item, "f")` would produce a giant zero-padded
                    # expansion that doesn't match native C++ shortest-round-
                    # trip rendering, use `str(item)` which mirrors Python's
                    # David Gay shortest round-trip algorithm. For normal
                    # floats the existing `.17g` path is preserved.
                    if abs(item) < 1e-300 and item != 0.0:
                        return str(item)
                    text = format(item, ".17g")
                    if "." not in text and "e" not in text and "E" not in text:
                        text += ".0"
                    return text
                if isinstance(item, Decimal):
                    # FP-11 EXPLORER (2026-06-29): Subnormal values wrapped
                    # in Decimal by the upstream engine produce unwieldy
                    # 300+-character zero-padded strings via `format(d, "f")`.
                    # Match native C++ shortest-round-trip rendering for
                    # subnormal magnitudes by converting back through float
                    # and using `str(float)`.
                    if abs(item) < Decimal("1e-300") and item != 0:
                        return str(float(item))
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
            "fhirpath_scalar: invalid JSON resource for expression '%s'",
            expression,
        )
        if _STRICT_MODE:
            raise
        return []
    except FHIRPathSyntaxError as e:
        # Public DuckDB result-UDFs must be row-resilient for malformed
        # expressions (matching native C++ EvaluateFhirpath, which returns {}
        # when GetOrCompile(...) fails). The validity signal is
        # fhirpath_is_valid(); result UDFs return empty/NULL. Strict callers
        # can still opt in via FHIRPATH_STRICT_MODE=1.
        if _STRICT_MODE:
            raise
        _logger.warning(
            "FHIRPath scalar syntax error for '%s': %s — returning empty",
            expression,
            e,
        )
        return []
    except FHIRPathError:
        if _STRICT_MODE:
            raise
        _logger.warning("FHIRPath scalar evaluation error for '%s'", expression)
        return []
    except NotImplementedError:
        if _STRICT_MODE:
            raise
        return []
    except (ValueError, TypeError, KeyError, AttributeError, IndexError, OverflowError) as e:
        _logger.warning("FHIRPath scalar evaluation failed for '%s': %s", expression, e)
        if _STRICT_MODE:
            raise
        # Unexpected error - return empty collection
        return []


# FP-15 SKEPTIC QA-005 (2026-08-18): the N1 grammar defines the operand of
# infix `is`/`as` as a typeSpecifier (qualified identifier), NOT an
# expression. A function invocation chained directly onto the type specifier
# (`X is FHIR.Quantity.not()`) is therefore a SYNTAX error — the native
# parser rejects it; the lenient fallback grammar accepted it. Applied to
# string-masked text so literal parentheses in string literals cannot trip it.
_INVALID_TYPE_SPECIFIER_INVOCATION = re.compile(
    r"\b(?:is|as)\s+`?[A-Za-z_][\w.]*?`?\.[A-Za-z_]\w*\s*\("
)

_INVALID_EXPR_PATTERNS = re.compile(
    r"(?:"
    r"\.\s*$"  # trailing dot
    r"|\.\."  # double dot
    r"|\(\s*$"  # unclosed paren at end
    r"|^\s*[*\/|&]"  # leading binary operator
    r"|^\s*@\d{5}"  # Date year must be exactly four digits
    r"|^\s*@\d{4}-\d(?:\D|$)"  # Month must be two digits when separator is present
    r"|^\s*@\d{4}-\d{2}-\d(?:\D|$)"  # Day must be two digits when present
    r"|^\s*@T\d{2}:\d{2}\.\d"  # Fractional Time requires seconds component
    r"|^\s*\d+(?:\.\d+)?\s+(?!years?\b|months?\b|weeks?\b|days?\b|hours?\b|minutes?\b|seconds?\b|milliseconds?\b)[A-Za-z_]\w*\s*$"
    r"|^\s*\d+\.\d+\.\d+"  # Ambiguous numeric/member-access tokenization
    r")"
)

# Dollar-sign syntax checks must NOT run against string-literal contents:
# §5.6.10 replaceMatches substitutions legitimately contain $$, $N, and
# ${name} (FP-10 QA-005). Mask literals before applying these checks.
_INVALID_DOLLAR_PATTERNS = re.compile(
    r"(?:"
    r"\$\$"  # invalid $$ prefix
    r"|\$(?!this\b|total\b|index\b|that\b)[a-zA-Z]"  # $ not followed by valid env variable
    r")"
)


def _mask_string_literals(text: str) -> str:
    """Replace the contents of single-quoted string literals with spaces.

    Preserves literal boundaries and overall length so positional checks on
    the masked text stay aligned with the original expression.
    """
    out = list(text)
    in_string = False
    i = 0
    while i < len(text):
        ch = text[i]
        if in_string:
            if ch == "\\" and i + 1 < len(text):
                out[i] = " "
                out[i + 1] = " "
                i += 2
                continue
            if ch == "'":
                in_string = False
            else:
                out[i] = " "
            i += 1
            continue
        if ch == "'":
            in_string = True
        i += 1
    return "".join(out)


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
    if _INVALID_TYPE_SPECIFIER_INVOCATION.search(_mask_string_literals(precheck_text)):
        return False
    if _INVALID_DOLLAR_PATTERNS.search(_mask_string_literals(precheck_text)):
        return False
    if _has_invalid_timezone_literal(stripped):
        return False
    if _has_invalid_partial_datetime_time_literal(stripped):
        return False
    if _has_invalid_week_date_literal(stripped):
        return False
    if _has_out_of_range_integer_literal(stripped):
        return False
    if _has_out_of_range_long_literal(stripped):
        return False
    if not _has_balanced_delimiters(stripped):
        return False
    if _has_invalid_math_arity(stripped):
        return False
    if _has_invalid_math_literal_args(stripped):
        return False
    if _has_invalid_math_literal_unions(stripped):
        return False
    if _has_invalid_math_literal_operands(stripped):
        return False
    if _has_invalid_string_search_arity(stripped):
        return False
    if _has_invalid_string_search_literal_args(stripped):
        return False
    if _has_invalid_string_search_literal_unions(stripped):
        return False
    if _has_invalid_membership_literal_unions(stripped):
        return False
    if _has_invalid_string_regex_literals(stripped):
        return False
    if _unknown_function_names(stripped):
        return False
    try:
        if _evaluate_literal_temporal_arithmetic(expression) is not None:
            return True
        def _compile_and_evaluate(_resource_dict, _expression=expression):
            evaluator = _get_compiled_evaluator(_expression)
            return evaluator.evaluate(_resource_dict)
        _eval_with_recursion_budget(
            _compile_and_evaluate,
            {"resourceType": "Patient", "id": "_validation"},
            expression,
        )
        return True
    except FHIRPathError as exc:
        if _is_valid_empty_result_error(exc):
            return True
        if _is_undefined_environment_variable_error(exc):
            return True
        return False
    except NotImplementedError as exc:
        return _not_implemented_function_name(exc) in _KNOWN_FUNCTION_NAMES
    except ValueError as exc:
        # The Python fallback raises ValueError (not FHIRPathError) for
        # undefined environment variables. Per FHIRPath §9, syntactically-
        # valid env var forms (%name, %`name`, %'name') that reference an
        # undefined env var are runtime errors, not syntax errors. The
        # is_valid UDF validates expression syntax, not runtime
        # evaluability, so these expressions must still report as valid.
        if _is_undefined_environment_variable_error(exc):
            return True
        return False
    except Exception:
        # Catch all exceptions — a validation function must never throw
        return False


def _not_implemented_function_name(exc: NotImplementedError) -> str | None:
    message = str(exc)
    for prefix in ("Not implemented: ", "Not implemented "):
        if message.startswith(prefix):
            return message[len(prefix) :].strip()
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
    if message.startswith("Cannot [") and "fhir4ds.fhirpath.engine.nodes.FP_" not in message:
        return True
    if message.startswith("Expected number or quantity, got: "):
        return True
    # FP-02 SKEPTIC QA-002 (2026-08-16): unary +/- on a non-numeric literal is
    # an execution type error (§6.8 unary operators are valid syntax; §6.6
    # type errors signal at evaluation), the same class as binary
    # `'a' - 'b'` ("Cannot [...]"). Singleton violations ("can only be
    # applied to an individual number") stay invalid.
    if message.startswith("Unary - cannot be applied to non-numeric value"):
        return True
    if message.startswith("Unary + cannot be applied to non-numeric value"):
        return True
    # FP-02 EXPLORER QA-003 (2026-08-16): §6.2 defines ordering for strings,
    # integers, decimals, quantities, dates, datetimes and times — Boolean is
    # omitted, so boolean-vs-boolean ordering is the same execution type-error
    # class as mixed-type ordering (`1 > true`), which is accepted above via
    # the "Type of ... InequalityExpression" form. The special-cased message
    # must classify identically or `fhirpath_is_valid` disagrees with itself
    # across operand shapes.
    if message.startswith("Comparison operators are not defined for Boolean operands"):
        return True
    # FP-05 SKEPTIC QA-001 (2026-08-17): §5.3 subsetting argument type errors
    # (indexer `[i]`, skip(num), take(num) require Integer) are execution
    # type errors of the same class as `'a' - 'b'` — the expression grammar
    # is valid and the mismatch signals at evaluation. Singleton violations
    # ("Indexer requires a singleton integer index",
    # "Unexpected collection[...]; expected singleton of type Integer")
    # remain invalid.
    if message.startswith("Expected integer, got: "):
        return True
    # FP-18 SKEPTIC QA-005 (2026-08-18): §6.6.5/§6.6.6 div/mod accept
    # Integer and Decimal operands only; Quantity/Boolean operand
    # mismatches are execution type errors of the same class as
    # `'a' - 'b'` ("Cannot [..."). The native engine returns empty for
    # these shapes, so the expression stays valid.
    if message.startswith("Cannot ") and (" div " in message or " mod " in message):
        return True
    # FP-18 SKEPTIC QA-005 (2026-08-18): §6.7.1/§6.7.2 unit restrictions
    # (e.g. `@2012-01-01 + 25 hours`, `@T10:00:00 + 1 day`) signal at
    # evaluation; the native engine returns empty, so the expressions
    # remain valid.
    if message.startswith("For date arithmetic,"):
        return True
    if message.startswith("For time arithmetic,"):
        return True
    if message.startswith("For date/time arithmetic,"):
        return True
    if message.startswith("Indexer requires an integer index"):
        return True
    return False


def _is_undefined_environment_variable_error(exc: Exception) -> bool:
    """Return true for the spec-defined runtime error for undefined env vars.

    Per FHIRPath §9, accessing an undefined environment variable is a runtime
    semantic error (not a syntax error). The `is_valid` UDF validates
    expression syntax; syntactically-valid env var references
    (``%name``, ``%`name```, ``%'name'`` per §9 backward-compat note) that
    reference an env var not provided to the validation context must still
    report as valid. Both backends raise this error (the C++ side via
    ``FHIRPathSpecError("Undefined variable: ...")`` and the Python side via
    ``ValueError("Attempting to access an undefined environment variable: ...")``
    which is then wrapped by ``FHIRPathError("Evaluation error: ...")``).
    """
    message = str(exc)
    return (
        "Attempting to access an undefined environment variable" in message
        or message.startswith("Undefined variable:")
    )


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
        elif _is_row_resilient_invalid_literal(expression):
            return None
        else:
            def _compile_and_evaluate(_resource_dict, _expression=expression):
                evaluator = _get_compiled_evaluator(_expression)
                return evaluator.evaluate(_resource_dict)
            result = _eval_with_recursion_budget(
                _compile_and_evaluate,
                resource_dict,
                expression,
            )
            choice_assertion = _resolve_choice_type_assertion_any(resource_dict, expression)
            if choice_assertion is not None:
                result = choice_assertion
            if not result and isinstance(resource_dict, dict):
                result = _resolve_choice_type(resource_dict, expression)
            if not result and isinstance(resource_dict, dict):
                result = _resolve_choice_oftype(resource_dict, expression)
            if _needs_type_chain_rescue(result):
                core_result = _resolve_core_type_chain(resource_dict, expression)
                if core_result is not None:
                    result = core_result

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
    except FHIRPathSyntaxError as e:
        # Row-resilient: malformed expressions return NULL; fhirpath_is_valid is the signal.
        if _STRICT_MODE:
            raise
        _logger.warning(
            "FHIRPath boolean syntax error for '%s': %s — returning NULL",
            expression,
            e,
        )
        return None
    except (NotImplementedError, FHIRPathError):
        # Unimplemented functions return NULL in boolean context (used by ViewDef)
        return None
    except (ValueError, TypeError, KeyError, AttributeError, IndexError, OverflowError) as e:
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
                val,
                expression,
            )
            return None
        return low == "true"
    if isinstance(val, (int, float)):
        if val in (0, 1, 0.0, 1.0):
            return bool(val)
        _logger.warning(
            "Unexpected numeric boolean value %r for expression '%s'; returning NULL",
            val,
            expression,
        )
        return None
    _logger.warning(
        "Unexpected type %s for boolean expression '%s'; returning NULL",
        type(val).__name__,
        expression,
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
        elif _is_row_resilient_invalid_literal(expression):
            return None
        else:
            def _compile_and_evaluate(_resource_dict, _expression=expression):
                evaluator = _get_compiled_evaluator(_expression)
                return evaluator.evaluate(_resource_dict)
            result = _eval_with_recursion_budget(
                _compile_and_evaluate,
                resource_dict,
                expression,
            )

            choice_assertion = _resolve_choice_type_assertion_any(resource_dict, expression)
            if choice_assertion is not None:
                result = choice_assertion
            if not result and isinstance(resource_dict, dict):
                result = _resolve_choice_type(resource_dict, expression)
            if not result and isinstance(resource_dict, dict):
                result = _resolve_choice_oftype(resource_dict, expression)
            if _needs_type_chain_rescue(result):
                core_result = _resolve_core_type_chain(resource_dict, expression)
                if core_result is not None:
                    result = core_result
    except FHIRPathSyntaxError as e:
        # Row-resilient: malformed expressions return NULL; fhirpath_is_valid is the signal.
        if _STRICT_MODE:
            raise
        _logger.warning(
            "FHIRPath number syntax error for '%s': %s — returning NULL",
            expression,
            e,
        )
        return None
    except (NotImplementedError, FHIRPathError):
        return None
    except (orjson.JSONDecodeError, ValueError, TypeError, KeyError, AttributeError, IndexError, OverflowError):
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
        elif _is_row_resilient_invalid_literal(expression):
            return None
        else:
            def _compile_and_evaluate(_resource_dict, _expression=expression):
                evaluator = _get_compiled_evaluator(_expression)
                return evaluator.evaluate(_resource_dict)
            result = _eval_with_recursion_budget(
                _compile_and_evaluate,
                resource_dict,
                expression,
            )

            choice_assertion = _resolve_choice_type_assertion_any(resource_dict, expression)
            if choice_assertion is not None:
                result = choice_assertion
            if not result and isinstance(resource_dict, dict):
                result = _resolve_choice_type(resource_dict, expression)
            if not result and isinstance(resource_dict, dict):
                result = _resolve_choice_oftype(resource_dict, expression)
            if _needs_type_chain_rescue(result):
                core_result = _resolve_core_type_chain(resource_dict, expression)
                if core_result is not None:
                    result = core_result

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
                else:
                    # FP-01 SKEPTIC QA-007 (2026-08-16): Match the native
                    # precision-15 shortest-round-trip mask so quantity JSON
                    # values agree between the C++ extension and the Python
                    # fallback (e.g. `3.141592653589793236 'mg'` serializes
                    # as 3.14159265358979 in both paths).
                    value = float(format(value, ".15g"))
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
    except FHIRPathSyntaxError as e:
        # Row-resilient: malformed expressions return NULL; fhirpath_is_valid is the signal.
        if _STRICT_MODE:
            raise
        _logger.warning(
            "FHIRPath json syntax error for '%s': %s — returning NULL",
            expression,
            e,
        )
        return None
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
        result_items = _evaluate_raw_items(resource, expression)
    except FHIRPathSyntaxError as e:
        # Row-resilient: malformed expressions return NULL; fhirpath_is_valid is the signal.
        if _STRICT_MODE:
            raise
        _logger.warning(
            "FHIRPath timestamp syntax error for '%s': %s — returning NULL",
            expression,
            e,
        )
        return None
    except (
        NotImplementedError,
        FHIRPathError,
        orjson.JSONDecodeError,
        ValueError,
        TypeError,
        KeyError,
        AttributeError,
        IndexError,
        OverflowError,
    ):
        if _STRICT_MODE:
            raise
        return None

    if not result_items:
        return None

    from ..engine.nodes import FP_DateTime

    val = result_items[0]
    if isinstance(val, FP_DateTime):
        return str(val)
    if isinstance(val, str) and FP_DateTime(val) is not None:
        return val
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
        result_items = _evaluate_raw_items(resource, expression)
    except FHIRPathSyntaxError as e:
        # Row-resilient: malformed expressions return NULL; fhirpath_is_valid is the signal.
        if _STRICT_MODE:
            raise
        _logger.warning(
            "FHIRPath quantity syntax error for '%s': %s — returning NULL",
            expression,
            e,
        )
        return None
    except NotImplementedError:
        return None
    except (
        FHIRPathError,
        orjson.JSONDecodeError,
        ValueError,
        TypeError,
        KeyError,
        AttributeError,
        IndexError,
        OverflowError,
    ) as e:
        _logger.warning("FHIRPath quantity evaluation failed for '%s': %s", expression, e)
        if _STRICT_MODE:
            raise
        return None

    if not result_items:
        return None

    from ..engine.nodes import FP_Quantity

    val = result_items[0]
    if isinstance(val, FP_Quantity):
        return str(val)
    if isinstance(val, dict) and "value" in val and ("code" in val or "unit" in val):
        return _json_serialize(val)
    return None


def _evaluate_raw_items(resource: str | dict | None, expression: str | None) -> list[object]:
    """Evaluate FHIRPath without scalar stringification for typed wrappers."""
    if resource is None or expression is None:
        return []
    if isinstance(resource, str):
        resource_dict = _parse_json(resource)
    elif isinstance(resource, dict):
        resource_dict = resource
    else:
        return []

    temporal_result = _evaluate_literal_temporal_arithmetic(expression)
    if temporal_result is not None:
        result: object = temporal_result
    elif _is_row_resilient_invalid_literal(expression):
        return []
    else:
        def _compile_and_evaluate(_resource_dict, _expression=expression):
            evaluator = _get_compiled_evaluator(_expression)
            return evaluator.evaluate(_resource_dict)
        result = _eval_with_recursion_budget(
            _compile_and_evaluate,
            resource_dict,
            expression,
        )

        choice_assertion = _resolve_choice_type_assertion_any(resource_dict, expression)
        if choice_assertion is not None:
            result = choice_assertion
        if not result and isinstance(resource_dict, dict):
            result = _resolve_choice_type(resource_dict, expression)
        if not result and isinstance(resource_dict, dict):
            result = _resolve_choice_oftype(resource_dict, expression)
        if _needs_type_chain_rescue(result):
            core_result = _resolve_core_type_chain(resource_dict, expression)
            if core_result is not None:
                result = core_result

    if result is None:
        return []
    if isinstance(result, list):
        return result
    return [result]


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
    def _compile_and_evaluate(_resource_dict, _path=path):
        evaluator = _get_compiled_evaluator(_path)
        return evaluator.evaluate(_resource_dict)
    raw = _eval_with_recursion_budget(_compile_and_evaluate, current, path)
    return [item for item in raw if isinstance(item, dict)]


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
        return _run_with_recursion_budget(evaluate_repeat, needed_limit)
    except Exception:
        _logger.debug("fhirpath_repeat failed", exc_info=True)
        return []
