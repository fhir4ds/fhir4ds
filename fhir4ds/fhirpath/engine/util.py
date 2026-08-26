from decimal import Decimal, InvalidOperation
import json
import logging
from collections import OrderedDict
from functools import reduce
from ..engine.nodes import ResourceNode, FP_Quantity
from .errors import FHIRPathError

_logger = logging.getLogger(__name__)


class set_paths:
    def __init__(self, func, parsedPath, model=None, options=None):
        self.func = func
        self.parsedPath = parsedPath
        self.model = model
        self.options = options

    def __call__(self, resource, context=None):
        return self.func(
            resource, self.parsedPath, context or {}, self.model, self.options
        )


def get_data(value):
    if isinstance(value, ResourceNode):
        value = value.data

    if isinstance(value, float):
        return Decimal(str(value))
    return value


def parse_value(value):
    def parse_complex_value(v):
        num_value, unit = v.get("value"), v.get("code") or v.get("unit")
        if num_value is None or isinstance(num_value, bool) or not isinstance(unit, str) or not unit:
            return None
        try:
            num_value = Decimal(str(num_value))
        except (InvalidOperation, ValueError):
            return None
        if not num_value.is_finite():
            return None
        return FP_Quantity(num_value, f"'{unit}'")

    # Handle ResourceNode with type info
    # FP-12 SKEPTIC QA-001 (2026-08-17): parse_complex_value returns None for
    # "not a valid Quantity" (e.g. a unit-less {"value": 120} wrapper reached
    # through children()/descendants()). Returning that None directly made
    # equality() compare None == None -> True, so distinct unitless Quantity
    # objects collapsed as equal (breaking repeat(children()) == descendants()
    # and distinct/contains over such nodes). Fall through to the original
    # value so structural comparison proceeds instead.
    if getattr(value, "get_type_info", lambda: None)() and value.get_type_info().name == "Quantity":
        parsed = parse_complex_value(value.data)
        return parsed if parsed is not None else value

    # Handle plain dict that looks like a Quantity (has value and code/unit keys)
    # FP-12 SKEPTIC QA-001: same None fall-through as the typed-node branch —
    # an invalid Quantity-shaped dict must remain a dict for structural
    # comparison, not become None.
    if isinstance(value, dict) and "value" in value and ("code" in value or "unit" in value):
        parsed = parse_complex_value(value)
        return parsed if parsed is not None else value

    return value


def is_number(value):
    return isinstance(value, (int, Decimal, complex)) and not isinstance(value, bool)


def is_capitalized(x):
    return isinstance(x, str) and len(x) > 0 and x[0] == x[0].upper()


def is_empty(x):
    return isinstance(x, list) and len(x) == 0


def is_some(x):
    return x is not None and not is_empty(x)


def is_nullable(x):
    return x is None or is_empty(x)


def is_true(x, singleton_non_boolean=False):
    """
    Evaluate a value using FHIRPath singleton Boolean evaluation.

    - Empty collection {} -> false
    - Singleton true -> true
    - Singleton false -> false
    - Singleton non-boolean (string, number, etc.) -> semantic error unless
      non-strict callers explicitly request singleton Boolean truthiness
    - Multi-item collection -> semantic error (cannot convert to boolean)
    """
    if x is True:
        return True
    if x is False:
        return False
    if isinstance(x, list):
        if len(x) == 0:
            return False  # Empty collection is false
        if len(x) == 1:
            val = get_data(x[0])
            if val is True:
                return True
            if val is False:
                return False
            if singleton_non_boolean:
                return True
            raise FHIRPathError(f"Cannot convert {type(val).__name__} to boolean")
        # Multi-item collection: cannot convert to boolean
        raise FHIRPathError(f"Cannot convert a collection with multiple items to a boolean")
    if singleton_non_boolean:
        return True
    raise FHIRPathError(f"Cannot convert {type(x).__name__} to boolean")


def arraify(x, instead_none=None):
    if isinstance(x, list):
        return x
    if is_some(x):
        return [x]
    return [] if instead_none is None else [instead_none]


def flatten(x):
    def func(acc, x):
        if isinstance(x, list):
            acc = acc + x
        else:
            acc.append(x)

        return acc

    return reduce(func, x, [])


def uniq(arr):
    # Strong type fast implementation for unique values that preserves ordering
    ordered_dict = OrderedDict()
    for x in arr:
        try:
            key = json.dumps(x, sort_keys=True)
        except TypeError:
            key = str(x)
        ordered_dict[key] = x
    return list(ordered_dict.values())


def val_data_converted(val):
    if isinstance(val, ResourceNode):
        val = val.convert_data()

    return val


def process_user_invocation_table(table):
    return {
        name: {
            **entity,
            "fn": lambda ctx, inputs, *args, __fn__=entity["fn"]: __fn__(
                [get_data(i) for i in inputs], *args
            ),
        }
        for name, entity in table.items()
    }
