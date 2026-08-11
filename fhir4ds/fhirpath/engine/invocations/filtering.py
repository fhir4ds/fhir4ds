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
    return util.is_true(result)


def where_macro(ctx, data, expr):
    if not isinstance(data, list):
        return []

    result = []
    missing = object()
    old_index = ctx.get("$index", missing)
    saved_vars = dict(ctx.get("vars", {}))
    old_chain = ctx.get("_chain_defined_vars", missing)

    try:
        for i, x in enumerate(data):
            ctx["$index"] = i
            ctx["vars"] = dict(saved_vars)
            if old_chain is not missing:
                ctx["_chain_defined_vars"] = set(old_chain)
            if check_macro_expr(expr, x):
                result.append(x)
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

    return util.flatten(result)


def select_macro(ctx, data, expr):
    if not isinstance(data, list):
        return []

    result = []
    missing = object()
    old_index = ctx.get("$index", missing)
    saved_vars = dict(ctx.get("vars", {}))
    old_chain = ctx.get("_chain_defined_vars", missing)

    try:
        for i, x in enumerate(data):
            ctx["$index"] = i
            ctx["vars"] = dict(saved_vars)
            if old_chain is not missing:
                ctx["_chain_defined_vars"] = set(old_chain)
            result.append(expr(x))
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

    return util.flatten(result)


def repeat_macro(ctx, data, expr):
    if not isinstance(data, list):
        return []

    res = []
    items = data

    next = None
    lres = None

    missing = object()
    old_index = ctx.get("$index", missing)
    saved_vars = dict(ctx.get("vars", {}))
    old_chain = ctx.get("_chain_defined_vars", missing)

    try:
        while len(items) != 0:
            next = items[0]
            items = items[1:]
            ctx["vars"] = dict(saved_vars)
            if old_chain is not missing:
                ctx["_chain_defined_vars"] = set(old_chain)
            lres = []
            for l in expr(next):
                if not _contains_equal(ctx, res, l) and not _contains_equal(ctx, lres, l):
                    lres.append(l)
            if len(lres) > 0:
                res = res + lres
                items = items + lres
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

    return res


def _contains_equal(ctx, items, candidate):
    # FHIRPath repeat() de-duplicates using the same semantic equality as `=`.
    from . import equality as equality_invocations

    for item in items:
        if equality_invocations.equality(ctx, [item], [candidate]) is True:
            return True
    return False


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
    if util.is_empty(n):
        return []
    n = int(n)
    if len(x) == 0 or n <= 0:
        return []
    return x[:n]


def skip_fn(ctx, x, n):
    if util.is_empty(n):
        return []
    n = int(n)
    if len(x) == 0 or n <= 0:
        return list(x)
    return x[n:]


def of_type_fn(ctx, coll, tp):
    from .types import _is_any_type, _matches_unqualified_choice_primitive

    result = []
    for value in coll:
        if _is_any_type(tp) or _matches_unqualified_choice_primitive(value, tp):
            result.append(value)
            continue
        value_type = nodes.TypeInfo.from_value(value)
        if value_type.is_exact_type(tp):
            result.append(value)
            continue
        # FHIRPath §5.2.4 parity: when the value is a raw Python primitive
        # (not a ResourceNode) and the requested type is a FHIR primitive
        # (qualified or unqualified), normalize the comparison via the
        # System↔FHIR primitive map. Without this, qualified specifiers
        # like `FHIR.decimal` fail to match raw float values that
        # `TypeInfo.from_value` types as `System.Decimal`. The R4 baseline
        # has no such test today but the native C++ path matches, so this
        # keeps the fallback in lockstep.
        if not isinstance(value, nodes.ResourceNode) and tp.namespace in (
            nodes.TypeInfo.FHIR,
            None,
        ):
            tp_lower = tp.name
            if tp_lower and tp_lower[0].islower():
                # Map FHIR primitive name to its System equivalent and back.
                system_name = nodes.TypeInfo.FHIR_TO_SYSTEM_TYPE.get(tp_lower)
                if system_name:
                    system_tp = nodes.TypeInfo(
                        name=system_name, namespace=nodes.TypeInfo.System
                    )
                    if value_type.is_exact_type(system_tp):
                        result.append(value)
                        continue
        # FHIRPath ofType() includes subclasses, but official R4 tests keep
        # primitive FHIR types such as code distinct from string here.
        if (
            value_type.namespace == nodes.TypeInfo.FHIR
            and tp.namespace in (nodes.TypeInfo.FHIR, None)
            and value_type.name
            and tp.name
            and value_type.name[0].isupper()
            and tp.name[0].isupper()
            and value_type.is_(tp)
        ):
            result.append(value)
    return result


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
