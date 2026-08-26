"""
FHIRPath Tree Navigation and Utility Functions

Implements the direct-helper surface for FHIRPath §5.8 (Tree Navigation)
and §5.9 (Utility Functions):

- children(data): §5.8.1 — immediate child nodes, preserving null children
  and key order; primitives have no children.
- descendants(data): §5.8.2 — shorthand for repeat(children()), i.e. all
  recursive children, de-duplicated by FHIRPath `=` equality.
- trace(value, name, [projection]): §5.9.1 — log the (optionally projected)
  value and return the input unchanged.

The §5.9.2 current-time helpers now()/today()/timeOfDay() live in
``datetime.DateTimeFunctions``.

Reference: https://hl7.org/fhirpath/#tree-navigation
"""

from __future__ import annotations

import logging
from decimal import Decimal, InvalidOperation
from typing import Any, Callable, Mapping

from ..errors import FHIRPathError

_logger = logging.getLogger(__name__)

# Properties that are not child nodes (§5.8.1: children are the element
# properties of the node, not the resourceType discriminator).
_NON_CHILD_PROPS = frozenset({"resourceType"})


def children(data: Any) -> list[Any]:
    """
    Return the immediate child nodes of ``data`` (FHIRPath §5.8.1).

    - Objects yield their property values in key order; JSON null children
      are preserved (GLOBAL_RULES invariant).
    - Array-valued properties yield the array's items in array order.
    - ``resourceType`` and ``_``-prefixed primitive-extension properties are
      not children.
    - Primitives (strings, numbers, booleans, null) have no children.

    Args:
        data: A FHIR element (dict), list, or primitive value.

    Returns:
        The list of child values; empty for primitives and empty containers.

    Raises:
        FHIRPathError: If data is of an unsupported type.
    """
    if data is None or isinstance(data, (bool, int, float, Decimal, str)):
        return []
    if isinstance(data, list):
        # Engine semantics (invocations/navigation.children): a collection
        # input yields the children of EACH item, flattened.
        result: list[Any] = []
        for item in data:
            result.extend(children(item))
        return result
    if isinstance(data, Mapping):
        result: list[Any] = []
        for prop, value in data.items():
            if prop in _NON_CHILD_PROPS or prop.startswith("_"):
                continue
            if isinstance(value, list):
                result.extend(value)
            else:
                result.append(value)
        return result
    raise FHIRPathError(
        f"children() requires a FHIR element or collection, got {type(data).__name__}"
    )


def _equals(left: Any, right: Any) -> bool:
    """FHIRPath `=` deep equality for helper values (§6.1.1).

    Numbers compare numerically (1 = 1.0); dicts and lists compare
    structurally; Quantity-shaped dicts compare by value+unit.
    """
    if isinstance(left, Mapping) and isinstance(right, Mapping):
        # Quantity-shaped dicts use engine Quantity equality (unit-aware).
        from ...engine.nodes import FP_Quantity  # noqa: PLC0415

        lq, rq = _quantity_value(left), _quantity_value(right)
        if lq is not None and rq is not None:
            return FP_Quantity(lq[0], f"'{lq[1]}'") == FP_Quantity(rq[0], f"'{rq[1]}'")
        if set(left.keys()) != set(right.keys()):
            return False
        return all(_equals(left[k], right[k]) for k in left)
    if isinstance(left, list) and isinstance(right, list):
        return len(left) == len(right) and all(
            _equals(a, b) for a, b in zip(left, right, strict=True)
        )
    if _is_number(left) and _is_number(right):
        return Decimal(str(left)) == Decimal(str(right))
    if isinstance(left, str) and isinstance(right, str):
        return left == right
    return type(left) is type(right) and left == right


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float, Decimal)) and not isinstance(value, bool)


def _quantity_value(data: Mapping) -> tuple[Decimal, str] | None:
    value, unit = data.get("value"), data.get("code") or data.get("unit")
    if value is None or isinstance(value, bool) or not isinstance(unit, str) or not unit:
        return None
    try:
        num = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    return (num, unit) if num.is_finite() else None


def descendants(data: Any) -> list[Any]:
    """
    Return all recursive child nodes of ``data`` (FHIRPath §5.8.2).

    Equivalent to ``repeat(children())``: iteratively expands children and
    adds projection results while they are new according to FHIRPath `=`
    equality.

    Args:
        data: A FHIR element (dict), list, or primitive value.

    Returns:
        The de-duplicated list of descendant values.

    Raises:
        FHIRPathError: If data is of an unsupported type.
    """
    result: list[Any] = []
    queue: list[Any] = [data]
    while queue:
        item = queue.pop(0)
        for child in children(item):
            if not any(_equals(child, seen) for seen in result):
                result.append(child)
                queue.append(child)
    return result


def trace(
    value: Any,
    name: str,
    projection: Callable[[Any], Any] | None = None,
) -> Any:
    """
    Log ``value`` (or its projection) and return the input unchanged
    (FHIRPath §5.9.1).

    Args:
        value: The input collection or item.
        name: Required trace name (must be a non-empty string).
        projection: Optional callable applied to each item of a collection
            input; its result is logged instead of the input.

    Returns:
        The input value, unchanged.

    Raises:
        FHIRPathError: If name is not a non-empty string.
    """
    if not isinstance(name, str) or not name:
        raise FHIRPathError("trace() requires a non-empty string name argument")
    trace_value = value
    if projection is not None:
        if isinstance(value, list):
            trace_value = [projection(item) for item in value]
        else:
            trace_value = projection(value)
    _logger.info("TRACE:[%s] %s", name, trace_value)
    return value


# Registry for the tree-navigation helper family.
NAVIGATION_FUNCTIONS: dict[str, Callable[..., Any]] = {
    "children": children,
    "descendants": descendants,
    "trace": trace,
}
