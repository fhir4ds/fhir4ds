from decimal import Decimal, ROUND_HALF_UP
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


def amp(ctx, x="", y=""):
    if isinstance(x, list) and not x:
        x = ""
    if isinstance(y, list) and not y:
        y = ""
    return x + y


def minus(ctx, xs_, ys_):
    xs = remove_duplicate_extension(xs_)
    ys = remove_duplicate_extension(ys_)

    if len(xs) != 1 or len(ys) != 1:
        raise FHIRPathError("Cannot " + str(xs) + " - " + str(ys))

    x = util.get_data(util.val_data_converted(xs[0]))
    y = util.get_data(util.val_data_converted(ys[0]))

    if util.is_number(x) and util.is_number(y):
        return x - y

    if isinstance(x, nodes.FP_Quantity) and isinstance(y, nodes.FP_Quantity):
        if x.unit == y.unit:
            return nodes.FP_Quantity(x.value - y.value, x.unit)
        converted = nodes.FP_Quantity.conv_unit_to(y.unit, y.value, x.unit)
        if converted is not None:
            return nodes.FP_Quantity(x.value - converted.value, x.unit)
        return []

    if isinstance(x, nodes.FP_TimeBase) and isinstance(y, nodes.FP_Quantity):
        return x.plus(nodes.FP_Quantity(-y.value, y.unit))

    if isinstance(x, str) and isinstance(y, nodes.FP_Quantity):
        x_ = nodes.FP_TimeBase.get_match_data(x)
        if x_ is not None:
            return x_.plus(nodes.FP_Quantity(-y.value, y.unit))

    raise FHIRPathError("Cannot " + str(xs) + " - " + str(ys))


def mul(ctx, x, y):
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
        return x + y

    if isinstance(x, nodes.FP_Quantity) and isinstance(y, nodes.FP_Quantity):
        if x.unit == y.unit:
            return nodes.FP_Quantity(x.value + y.value, x.unit)
        converted = nodes.FP_Quantity.conv_unit_to(y.unit, y.value, x.unit)
        if converted is not None:
            return nodes.FP_Quantity(x.value + converted.value, x.unit)
        return []

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

    # Check if it's a Quantity
    from ...engine.nodes import FP_Quantity
    data = util.get_data(x[0]) if isinstance(x, list) and len(x) > 0 else x
    if isinstance(data, FP_Quantity):
        return FP_Quantity(Decimal(data.value).copy_abs(), data.unit)

    num = ensure_number_singleton(x)
    result = Decimal(num).copy_abs()
    if isinstance(num, int):
        return int(result)
    return result


def ceiling(ctx, x):
    if is_empty(x):
        return []
    num = ensure_number_singleton(x)
    return Decimal(num).to_integral_value(rounding="ROUND_CEILING")


def exp(ctx, x):
    if is_empty(x):
        return []
    num = ensure_number_singleton(x)
    return Decimal(num).exp()


def floor(ctx, x):
    if is_empty(x):
        return []
    num = ensure_number_singleton(x)
    return Decimal(num).to_integral_value(rounding="ROUND_FLOOR")


def ln(ctx, x):
    """FHIRPath §5.7.2 — ln() returns empty for undefined inputs (<=0)."""
    if is_empty(x):
        return []

    num = ensure_number_singleton(x)
    if num <= 0:
        return []
    return Decimal(num).ln()


def log(ctx, x, base):
    """FHIRPath §5.7.2 — log() returns empty for undefined inputs."""
    if is_empty(x) or is_empty(base):
        return []

    num = Decimal(ensure_number_singleton(x))
    num2 = Decimal(ensure_number_singleton(base))

    if num <= 0 or num2 <= 0 or num2 == 1:
        return []

    return (num.ln() / num2.ln()).quantize(Decimal("1.000000000000000"))


def power(ctx, x, degree):
    """FHIRPath §5.7.2 — power() returns empty for undefined results."""
    if is_empty(x) or is_empty(degree):
        return []

    num = Decimal(ensure_number_singleton(x))
    num2 = Decimal(ensure_number_singleton(degree))

    if num == 0 and num2 <= 0:
        return []
    if num < 0 and num2.to_integral_value(rounding="ROUND_FLOOR") != num2:
        return []

    return pow(num, num2)


def rround(ctx, x, acc=None):
    if is_empty(x):
        return []

    num = Decimal(ensure_number_singleton(x))
    if acc is None or is_empty(acc):
        # FHIRPath §5.5: ties round towards positive infinity (ROUND_HALF_UP)
        return int(num.quantize(Decimal('1'), rounding=ROUND_HALF_UP))

    num2 = ensure_number_singleton(acc)
    degree = 10 ** Decimal(num2)

    # Use ROUND_HALF_UP for spec-compliant rounding
    scaled = num * degree
    return Decimal(scaled.quantize(Decimal('1'), rounding=ROUND_HALF_UP)) / degree


def sqrt(ctx, x):
    if is_empty(x):
        return []

    num = ensure_number_singleton(x)
    if num < 0:
        return []

    return Decimal(num).sqrt()


def truncate(ctx, x):
    if is_empty(x):
        return []
    num = ensure_number_singleton(x)
    return Decimal(num).to_integral_value(rounding="ROUND_DOWN")
