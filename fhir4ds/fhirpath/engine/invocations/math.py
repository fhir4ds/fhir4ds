import math
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation, Overflow
from ...engine.invocations.equality import remove_duplicate_extension
from ...engine import util as util
from ...engine import nodes as nodes
from ...engine.errors import FHIRPathError

"""
Adds the math functions to the given FHIRPath engine.
"""


def is_empty(x):
    if util.is_number(x):
        return False
    return util.is_empty(x)


def ensure_number_singleton(x):
    data = util.get_data(x)
    if isinstance(data, float):
        data = Decimal(data)

    if not util.is_number(data):
        if not isinstance(data, list) or len(data) != 1:
            raise FHIRPathError("Expected list with number, but got " + str(data))

        value = util.get_data(data[0])

        if isinstance(value, float):
            value = Decimal(value)

        if not util.is_number(value):
            raise FHIRPathError("Expected number, but got " + str(x))

        return value
    return data


def ensure_integer_singleton(x):
    data = util.get_data(x)

    if not isinstance(data, int) or isinstance(data, bool):
        if not isinstance(data, list) or len(data) != 1:
            raise FHIRPathError("Expected list with integer, but got " + str(data))

        value = util.get_data(data[0])

        if not isinstance(value, int) or isinstance(value, bool):
            raise FHIRPathError("Expected integer, but got " + str(x))

        return value
    return data


def quantity_singleton(x):
    data = util.parse_value(util.val_data_converted(x))
    if isinstance(data, nodes.FP_Quantity):
        return data

    if not isinstance(data, list) or len(data) != 1:
        return None

    value = util.parse_value(util.val_data_converted(data[0]))
    if isinstance(value, nodes.FP_Quantity):
        return value
    return None


_FHIRPATH_INT32_MIN = -2147483648
_FHIRPATH_INT32_MAX = 2147483647


def _numeric_arithmetic_result(x, y, result):
    if (
        isinstance(x, int)
        and not isinstance(x, bool)
        and isinstance(y, int)
        and not isinstance(y, bool)
        and not (_FHIRPATH_INT32_MIN <= result <= _FHIRPATH_INT32_MAX)
    ):
        return Decimal(result)
    return result


def _quantity_add_or_sub(x, y, sign):
    if x.unit == y.unit:
        result = x.value + sign * y.value
        return nodes.FP_Quantity(nodes.FP_Quantity._normalize_quantity_value(result), x.unit)

    x_base = nodes.FP_Quantity.conv_unit_to_base(x.unit, x.value)
    y_base = nodes.FP_Quantity.conv_unit_to_base(y.unit, y.value)
    if x_base.unit != y_base.unit:
        return []

    result = x_base.value + sign * y_base.value
    return nodes.FP_Quantity(
        nodes.FP_Quantity._normalize_quantity_value(result),
        x_base.unit,
    )


def amp(ctx, x="", y=""):
    if isinstance(x, list) and len(x) > 1:
        raise FHIRPathError("Cannot concatenate a collection with more than one item")
    if isinstance(y, list) and len(y) > 1:
        raise FHIRPathError("Cannot concatenate a collection with more than one item")

    def _string_value(value):
        if isinstance(value, list):
            if not value:
                return ""
            value = value[0]
        value = util.get_data(value)
        if value is None:
            return ""
        if isinstance(value, bool):
            return "true" if value else "false"
        return str(value)

    return _string_value(x) + _string_value(y)


def minus(ctx, xs_, ys_):
    xs = remove_duplicate_extension(xs_)
    ys = remove_duplicate_extension(ys_)

    if len(xs) != 1 or len(ys) != 1:
        raise FHIRPathError("Cannot " + str(xs) + " - " + str(ys))

    x = util.get_data(util.val_data_converted(xs[0]))
    y = util.get_data(util.val_data_converted(ys[0]))

    if util.is_number(x) and util.is_number(y):
        return _numeric_arithmetic_result(x, y, x - y)

    if isinstance(x, nodes.FP_Quantity) and isinstance(y, nodes.FP_Quantity):
        return _quantity_add_or_sub(x, y, -1)

    if isinstance(x, nodes.FP_TimeBase) and isinstance(y, nodes.FP_Quantity):
        return x.plus(nodes.FP_Quantity(-y.value, y.unit))

    if isinstance(x, str) and isinstance(y, nodes.FP_Quantity):
        x_ = nodes.FP_TimeBase.get_match_data(x)
        if x_ is not None:
            return x_.plus(nodes.FP_Quantity(-y.value, y.unit))

    raise FHIRPathError("Cannot " + str(xs) + " - " + str(ys))


def mul(ctx, x, y):
    if util.is_number(x) and util.is_number(y):
        return _numeric_arithmetic_result(x, y, x * y)
    return x * y


def div(ctx, x, y):
    if y == 0:
        return []
    return x / y


def intdiv(ctx, x, y):
    if y == 0:
        return []
    return int(x / y)


def mod(ctx, x, y):
    if y == 0:
        return []

    # FHIRPath §6.6: mod uses truncated division.
    # Use Decimal arithmetic to avoid floating point precision issues.
    from decimal import Decimal, InvalidOperation
    try:
        dx = Decimal(str(x))
        dy = Decimal(str(y))
        # fmod semantics: x - int(x/y) * y  (truncated division)
        result = dx - int(dx / dy) * dy
        if isinstance(x, int) and isinstance(y, int):
            return int(result)
        return result
    except (InvalidOperation, ValueError):
        import math as _math
        result = _math.fmod(float(x), float(y))
        if isinstance(x, int) and isinstance(y, int):
            return int(result)
        return result


# HACK: for only polymorphic function
# Actually, "minus" is now also polymorphic
def plus(ctx, xs_, ys_):
    xs = remove_duplicate_extension(xs_)
    ys = remove_duplicate_extension(ys_)

    if len(xs) != 1 or len(ys) != 1:
        raise FHIRPathError("Cannot " + str(xs) + " + " + str(ys))

    x = util.get_data(util.val_data_converted(xs[0]))
    y = util.get_data(util.val_data_converted(ys[0]))

    """
    In the future, this and other functions might need to return ResourceNode
    to preserve the type information (integer vs decimal, and maybe decimal
    vs string if decimals are represented as strings), in order to support
    "as" and "is", but that support is deferred for now.
    """
    if isinstance(x, str) and isinstance(y, str):
        return x + y

    if util.is_number(x) and util.is_number(y):
        return _numeric_arithmetic_result(x, y, x + y)

    if isinstance(x, nodes.FP_Quantity) and isinstance(y, nodes.FP_Quantity):
        return _quantity_add_or_sub(x, y, 1)

    if isinstance(x, nodes.FP_TimeBase) and isinstance(y, nodes.FP_Quantity):
        return x.plus(y)

    if isinstance(x, str) and isinstance(y, nodes.FP_Quantity):
        x_ = nodes.FP_TimeBase.get_match_data(x)
        if x_ is not None:
            return x_.plus(y)

    raise FHIRPathError("Cannot " + str(xs) + " + " + str(ys))


def abs(ctx, x):
    if is_empty(x):
        return []

    quantity = quantity_singleton(x)
    if quantity is not None:
        return nodes.FP_Quantity(Decimal(quantity.value).copy_abs(), quantity.unit)

    num = ensure_number_singleton(x)
    result = Decimal(num).copy_abs()
    if isinstance(num, int):
        return int(result)
    return result


def ceiling(ctx, x):
    if is_empty(x):
        return []
    quantity = quantity_singleton(x)
    if quantity is not None:
        result = Decimal(quantity.value).to_integral_value(rounding="ROUND_CEILING")
        return nodes.FP_Quantity(result, quantity.unit)
    num = ensure_number_singleton(x)
    return int(Decimal(num).to_integral_value(rounding="ROUND_CEILING"))


def exp(ctx, x):
    if is_empty(x):
        return []
    num = ensure_number_singleton(x)
    try:
        result = math.exp(float(num))
    except (OverflowError, ValueError):
        return []
    if math.isinf(result) or math.isnan(result):
        return []
    return Decimal(format(result, ".17g"))


def floor(ctx, x):
    if is_empty(x):
        return []
    quantity = quantity_singleton(x)
    if quantity is not None:
        result = Decimal(quantity.value).to_integral_value(rounding="ROUND_FLOOR")
        return nodes.FP_Quantity(result, quantity.unit)
    num = ensure_number_singleton(x)
    return int(Decimal(num).to_integral_value(rounding="ROUND_FLOOR"))


def ln(ctx, x):
    """FHIRPath §5.7.2 — ln() returns empty for undefined inputs (<=0)."""
    if is_empty(x):
        return []

    num = ensure_number_singleton(x)
    if num <= 0:
        return []
    return math.log(float(num))


def log(ctx, x, base):
    """FHIRPath §5.7.2 — log() returns empty for undefined inputs."""
    if is_empty(x) or is_empty(base):
        return []

    num = Decimal(ensure_number_singleton(x))
    num2 = Decimal(ensure_number_singleton(base))

    if num <= 0 or num2 <= 0 or num2 == 1:
        return []

    return math.log(float(num)) / math.log(float(num2))


def power(ctx, x, degree):
    """FHIRPath §5.7.2 — power() returns empty for undefined results."""
    if is_empty(x) or is_empty(degree):
        return []

    base_raw = ensure_number_singleton(x)
    exponent_raw = ensure_number_singleton(degree)
    num = Decimal(base_raw)
    num2 = Decimal(exponent_raw)

    if num == 0 and num2 <= 0:
        return []
    if num < 0 and num2.to_integral_value(rounding="ROUND_FLOOR") != num2:
        return []

    if isinstance(base_raw, int) and isinstance(exponent_raw, int) and exponent_raw >= 0:
        return Decimal(pow(base_raw, exponent_raw))

    result = pow(num, num2)
    if isinstance(result, Decimal):
        text = format(result.normalize(), "f")
        if "." not in text:
            text += ".0"
        return Decimal(text)
    return result


def rround(ctx, x, acc=None):
    if is_empty(x):
        return []

    quantity = quantity_singleton(x)
    if quantity is not None:
        num = Decimal(quantity.value)
    else:
        num = Decimal(ensure_number_singleton(x))

    if acc is None:
        # FHIRPath §5.7.8 returns Decimal; omitted precision defaults to 0.
        result = num.quantize(Decimal('1'), rounding=ROUND_HALF_UP)
        if quantity is not None:
            return nodes.FP_Quantity(result, quantity.unit)
        return result

    if is_empty(acc):
        return []

    num2 = ensure_integer_singleton(acc)
    if num2 < 0:
        raise FHIRPathError("round() precision must be >= 0")

    degree = 10 ** Decimal(num2)

    # Use ROUND_HALF_UP for spec-compliant rounding
    scaled = num * degree
    result = Decimal(scaled.quantize(Decimal('1'), rounding=ROUND_HALF_UP)) / degree
    if quantity is not None:
        return nodes.FP_Quantity(result, quantity.unit)
    return result


def sqrt(ctx, x):
    if is_empty(x):
        return []

    num = ensure_number_singleton(x)
    if num < 0:
        return []

    return math.sqrt(float(num))


def truncate(ctx, x):
    if is_empty(x):
        return []
    quantity = quantity_singleton(x)
    if quantity is not None:
        result = Decimal(quantity.value).to_integral_value(rounding="ROUND_DOWN")
        return nodes.FP_Quantity(result, quantity.unit)
    num = ensure_number_singleton(x)
    return int(Decimal(num).to_integral_value(rounding="ROUND_DOWN"))
