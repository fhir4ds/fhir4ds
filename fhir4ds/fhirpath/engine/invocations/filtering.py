from collections import abc
from decimal import Decimal
import numbers
from ...engine import util as util
from ...engine import nodes as nodes
from ...engine.errors import FHIRPathError

# Contains the FHIRPath Filtering and Projection functions.
# (Section 5.2 of the FHIRPath 1.0.0 specification).

"""
 Adds the filtering and projection functions to the given FHIRPath engine.
"""


def check_macro_expr(expr, x):
    result = expr(x)
    if len(result) > 0:
        return expr(x)[0]

    return False


def where_macro(ctx, data, expr):
    if not isinstance(data, list):
        return []

    result = []

    for i, x in enumerate(data):
        ctx["$index"] = i
        if check_macro_expr(expr, x):
            result.append(x)

    return util.flatten(result)


def select_macro(ctx, data, expr):
    if not isinstance(data, list):
        return []

    result = []

    for i, x in enumerate(data):
        ctx["$index"] = i
        result.append(expr(x))

    return util.flatten(result)


def repeat_macro(ctx, data, expr):
    if not isinstance(data, list):
        return []

    res = []
    items = data

    next = None
    lres = None

    uniq = set()

    while len(items) != 0:
        next = items[0]
        items = items[1:]
        lres = [l for l in expr(next) if l not in uniq]
        if len(lres) > 0:
            for l in lres:
                uniq.add(l)
            res = res + lres
            items = items + lres

    return res


# TODO: behavior on object?
def single_fn(ctx, x):
    if len(x) == 1:
        return x

    if len(x) == 0:
        return []

    # According to FHIRPath spec, single() should raise an error for multi-item collections
    raise FHIRPathError("Expected single item, but collection has " + str(len(x)) + " items")


def first_fn(ctx, x):
    if len(x) == 0:
        return []
    return x[0]


def last_fn(ctx, x):
    if len(x) == 0:
        return []
    return x[-1]


def tail_fn(ctx, x):
    if len(x) == 0:
        return []
    return x[1:]


def take_fn(ctx, x, n):
    n = int(n)
    if len(x) == 0 or n <= 0:
        return []
    return x[:n]


def skip_fn(ctx, x, n):
    n = int(n)
    if len(x) == 0 or n <= 0:
        return list(x)
    return x[n:]


def of_type_fn(ctx, coll, tp):
    # ofType() requires exact type match (no subtype matching)
    return [value for value in coll if nodes.TypeInfo.from_value(value).is_exact_type(tp)]


def extension(ctx, data, url=None):
    """
    Access extension values by URL.

    If url is provided, returns extension matching that URL.
    If no url, returns all extensions.

    Args:
        ctx: Evaluation context
        data: Collection of resources/elements
        url: Optional extension URL to filter by

    Returns:
        Collection of extension objects
    """
    res = []
    for d in data:
        element = util.get_data(d)

        # Check if this is a ResourceNode with _data (primitive extensions)
        if isinstance(d, nodes.ResourceNode) and d._data is not None:
            # Use the _data which contains extension info for primitives
            element = d._data

        if isinstance(element, abc.Mapping):
            exts_raw = element.get("extension", [])
            # Handle both single extension (dict) and multiple extensions (list)
            if isinstance(exts_raw, abc.Mapping):
                exts_raw = [exts_raw]

            if url is None:
                # Return all extensions
                for e in exts_raw:
                    if isinstance(e, abc.Mapping):
                        res.append(nodes.ResourceNode.create_node(e, "Extension"))
            else:
                # Filter by URL
                exts = [e for e in exts_raw if isinstance(e, abc.Mapping) and e.get("url") == url]
                if len(exts) > 0:
                    res.append(nodes.ResourceNode.create_node(exts[0], "Extension"))
    return res
