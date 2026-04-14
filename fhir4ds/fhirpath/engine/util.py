from decimal import Decimal
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
        num_value, unit = v.get("value"), v.get("code")
        # Convert string values to Decimal for proper numeric comparison
        if isinstance(num_value, str):
            try:
                num_value = Decimal(num_value)
            except Exception as e:
                _logger.warning("Failed to convert Quantity string value '%s' to Decimal: %s", num_value, e)
                pass
        return FP_Quantity(num_value, f"'{unit}'") if num_value is not None and unit else None

    # Handle ResourceNode with type info
    if getattr(value, "get_type_info", lambda: None)() and value.get_type_info().name == "Quantity":
        return parse_complex_value(value.data)

    # Handle plain dict that looks like a Quantity (has value and code keys)
    if isinstance(value, dict) and "value" in value and "code" in value:
        return parse_complex_value(value)

    return value


def is_number(value):
    return isinstance(value, (int, Decimal, complex)) and not isinstance(value, bool)


def is_capitalized(x):
    return isinstance(x, str) and x[0] == x[0].upper()


def is_empty(x):
    return isinstance(x, list) and len(x) == 0


def is_some(x):
    return x is not None and not is_empty(x)


def is_nullable(x):
    return x is None or is_empty(x)


def is_true(x):
    """
    Check if a value represents boolean true in FHIRPath.

    For iif conditions:
    - Empty collection {} -> false
    - Singleton true -> true
    - Singleton false -> false
    - Singleton non-boolean (string, number, etc.) -> semantic error
    - Multi-item collection -> semantic error (cannot convert to boolean)
    """
    if x == True:
        return True
    if x == False:
        return False
    if isinstance(x, list):
        if len(x) == 0:
            return False  # Empty collection is false
        if len(x) == 1:
            val = x[0]
            if val == True:
                return True
            if val == False:
                return False
            # Singleton non-boolean: semantic error
            raise FHIRPathError(f"Cannot convert {type(val).__name__} to boolean")
        # Multi-item collection: cannot convert to boolean
        raise FHIRPathError(f"Cannot convert a collection with multiple items to a boolean")
    # Non-list, non-boolean value: semantic error
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
