from collections import abc
from ...engine.invocations import misc
from ...engine.invocations import equality
from ...engine.invocations.misc import to_boolean
from ...engine import util as util
from ...engine import nodes as nodes
from ...engine.invocations import filtering as filtering
from ...engine.errors import FHIRPathError


"""
This file holds code to hande the FHIRPath Existence functions
(5.1 in the specification).
"""


def empty_fn(ctx, value):
    return util.is_empty(value)


def count_fn(ctx, value):
    if isinstance(value, list):
        return len(value)
    return 0


def not_fn(ctx, x):
    if len(x) == 0:
        return []

    if len(x) > 1:
        raise FHIRPathError("not() requires a singleton input, but got " + str(len(x)) + " items")

    data = util.get_data(x[0])
    data = misc.singleton(x, "Boolean")

    if isinstance(data, bool):
        return not data

    return []


def exists_macro(ctx, coll, expr=None):
    vec = coll
    if expr is not None:
        return exists_macro(ctx, filtering.where_macro(ctx, coll, expr))

    return not util.is_empty(vec)


def all_macro(ctx, colls, expr):
    missing = object()
    old_index = ctx.get("$index", missing)
    saved_vars = dict(ctx.get("vars", {}))
    old_chain = ctx.get("_chain_defined_vars", missing)

    try:
        for i, coll in enumerate(colls):
            ctx["$index"] = i
            ctx["vars"] = dict(saved_vars)
            if old_chain is not missing:
                ctx["_chain_defined_vars"] = set(old_chain)
            if not util.is_true(expr(coll)):
                return [False]
    finally:
        ctx["vars"] = saved_vars
        if old_chain is missing:
            ctx.pop("_chain_defined_vars", None)
        else:
            ctx["_chain_defined_vars"] = old_chain
        if old_index is missing:
            ctx.pop("$index", None)
        else:
            ctx["$index"] = old_index

    return [True]


def extract_boolean_value(data):
    value = util.get_data(data)
    if type(value) != bool:
        raise FHIRPathError("Found type '" + type(data).__name__ + "' but was expecting bool")
    return value


def all_true_fn(ctx, items):
    values = [extract_boolean_value(item) for item in items]
    return [all(values)]


def any_true_fn(ctx, items):
    values = [extract_boolean_value(item) for item in items]
    return [any(values)]


def all_false_fn(ctx, items):
    values = [extract_boolean_value(item) for item in items]
    return [all(not value for value in values)]


def any_false_fn(ctx, items):
    values = [extract_boolean_value(item) for item in items]
    return [any(not value for value in values)]


def _values_equal(ctx, left, right):
    return equality.equality(ctx, [left], [right]) is True


def subset_of(ctx, coll1, coll2):
    return all(any(_values_equal(ctx, item, other) for other in coll2) for item in coll1)


def subset_of_fn(ctx, coll1, coll2):
    return [subset_of(ctx, coll1, coll2)]


def superset_of_fn(ctx, coll1, coll2):
    return [subset_of(ctx, coll2, coll1)]


def distinct_fn(ctx, x):
    result = []
    for item in x:
        if not any(_values_equal(ctx, item, existing) for existing in result):
            result.append(item)
    return result


def isdistinct_fn(ctx, x):
    return [len(x) == len(distinct_fn(ctx, x))]


def has_value_fn(ctx, x):
    """
    Returns true if the input collection contains a single item and
    that item is not null (represented as [] in FHIRPath).

    For FHIR primitives with extensions but no value (e.g., from _given array
    where the corresponding given element is null), hasValue() should return
    false since there is no actual value, only an extension.
    """
    if len(x) != 1:
        return [False]

    # Get the data value, checking if it's a ResourceNode
    data = util.get_data(x[0])

    # Check if the value is null/empty
    if data is None:
        return [False]

    # For ResourceNode, check if the underlying data is valid
    if isinstance(x[0], nodes.ResourceNode):
        if x[0].data is None:
            return [False]

        # Handle FHIR primitives with extensions but no value
        # When a primitive has only an extension (no actual value), the data
        # is a dict with 'extension' key but no 'value' key
        if isinstance(x[0].data, abc.Mapping):
            # If it has extension but no value key, it's an extension-only primitive
            if 'extension' in x[0].data and 'value' not in x[0].data:
                return [False]

    return [True]


def get_value_fn(ctx, x):
    """
    Returns the value of the first item in the collection if it has a value.

    Per FHIRPath spec, getValue() returns:
    - The value of the first item if hasValue() is true
    - Empty collection {} if hasValue() is false

    This handles:
    - Primitive values directly
    - ResourceNode wrapping
    - FHIR extensions (_field)

    Args:
        ctx: Evaluation context
        x: Collection to get value from

    Returns:
        Collection containing the value, or empty if no value
    """
    # First check if there's a value using hasValue logic
    if len(x) != 1:
        return []

    first = x[0]
    if first is None:
        return []

    # Handle ResourceNode
    if isinstance(first, nodes.ResourceNode):
        if first.data is None:
            return []

        # Handle FHIR primitives with extensions but no value
        if isinstance(first.data, abc.Mapping):
            # If it has extension but no value key, it's an extension-only primitive
            if 'extension' in first.data and 'value' not in first.data:
                return []

        # Return the data value
        return [first.data]

    # Return the primitive value directly
    return [first]
