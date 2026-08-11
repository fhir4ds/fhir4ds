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

    # FHIRPath §5.5 conversion table: Integer/Decimal → Quantity (unit '1')
    # is implicit. When one operand is a Quantity and the other is a plain
    # numeric scalar, convert the scalar to a unit-'1' Quantity and dispatch
    # to the Quantity ± Quantity path so that mismatched UCUM dimensions
    # yield empty (per §6.6 "Implementations that do not support complete
    # UCUM functionality may return empty") rather than a hard type error.
    if isinstance(x, nodes.FP_Quantity) and util.is_number(y):
        y = nodes.FP_Quantity(nodes.FP_Quantity._normalize_quantity_value(y), "1")
    elif isinstance(y, nodes.FP_Quantity) and util.is_number(x):
        x = nodes.FP_Quantity(nodes.FP_Quantity._normalize_quantity_value(x), "1")

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
    # FP-18 HISTORIAN QA-002 (2026-06-30): Per §6.6, math operators require
    # operands to be Integer/Decimal/Quantity. Boolean is NOT implicitly
    # convertible to Integer/Decimal (§5.5 conversion table — Explicit only).
    # util.is_number correctly excludes bool; without this guard Python's
    # `isinstance(True, int) == True` would silently coerce `true * 2 = 2`.
    # The `plus`/`minus` paths already raise FHIRPathError via fallthrough;
    # `mul` was missing the same guard.
    if util.is_number(x) and util.is_number(y):
        return _numeric_arithmetic_result(x, y, x * y)
    if isinstance(x, nodes.FP_Quantity) or isinstance(y, nodes.FP_Quantity):
        return x * y
    raise FHIRPathError("Cannot " + str(x) + " * " + str(y))


def div(ctx, x, y):
    # FP-18 HISTORIAN QA-002 (2026-06-30): Same Boolean-coercion guard as
    # `mul`. Per §6.6 + §5.5, Boolean→Integer/Decimal is Explicit only.
    if not (util.is_number(x) and util.is_number(y)) and not (
        isinstance(x, nodes.FP_Quantity) or isinstance(y, nodes.FP_Quantity)
    ):
        raise FHIRPathError("Cannot " + str(x) + " / " + str(y))
    if y == 0:
        return []
    # FP-18 HISTORIAN QA-003 (2026-06-30): Per §6.6.2 "The result of a
    # division is always Decimal, even if the inputs are both Integer".
    # Decimal division may produce a whole-number Decimal like Decimal('3')
    # which serializes without a decimal point; force at least one decimal
    # place per §5.5.8 format (-)?#0.0#.
    result = x / y
    if isinstance(result, Decimal) and result == result.to_integral_value():
        return result.quantize(Decimal("0.1"))
    return result


def intdiv(ctx, x, y):
    # FP-18 HISTORIAN QA-002 (2026-06-30): Boolean-coercion guard.
    if not (util.is_number(x) and util.is_number(y)) and not (
        isinstance(x, nodes.FP_Quantity) or isinstance(y, nodes.FP_Quantity)
    ):
        raise FHIRPathError("Cannot " + str(x) + " div " + str(y))
    if y == 0:
        return []
    return int(x / y)


def mod(ctx, x, y):
    # FP-18 HISTORIAN QA-002 (2026-06-30): Boolean-coercion guard.
    if not (util.is_number(x) and util.is_number(y)) and not (
        isinstance(x, nodes.FP_Quantity) or isinstance(y, nodes.FP_Quantity)
    ):
        raise FHIRPathError("Cannot " + str(x) + " mod " + str(y))
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

    # FHIRPath §5.5 conversion table: Integer/Decimal → Quantity (unit '1')
    # is implicit. When one operand is a Quantity and the other is a plain
    # numeric scalar, convert the scalar to a unit-'1' Quantity and dispatch
    # to the Quantity ± Quantity path so that mismatched UCUM dimensions
    # yield empty (per §6.6 "Implementations that do not support complete
    # UCUM functionality may return empty") rather than a hard type error.
    if isinstance(x, nodes.FP_Quantity) and util.is_number(y):
        y = nodes.FP_Quantity(nodes.FP_Quantity._normalize_quantity_value(y), "1")
    elif isinstance(y, nodes.FP_Quantity) and util.is_number(x):
        x = nodes.FP_Quantity(nodes.FP_Quantity._normalize_quantity_value(x), "1")

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
    # FP-11 HISTORIAN (2026-06-28): Return raw float (consistent with
    # ln/log/sqrt siblings) so the result serializes via Python's
    # shortest-round-trip `str(float)` rendering, matching the native C++
    # `normalizeDecimalMathSourceText` precision-15 shortest-round-trip
    # source_text. Previously this returned `Decimal(format(result, ".17g"))`
    # which produced 17-sig-digit text and diverged from the §5.7.3 native
    # rendering on non-trivial results. The numerical value is unchanged;
    # only the toString shape is normalized across all four §5.7 Decimal-
    # returning math functions (exp/ln/log/sqrt).
    return result


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

    # FP-11 EXPLORER (2026-06-29): The previous implementation used
    # `degree = 10 ** Decimal(num2)` then `num * degree` and
    # `scaled.quantize(Decimal('1'), ...) / degree`. For large precision
    # values (e.g. 50, 100, INT_MAX), `10 ** Decimal(num2)` overflowed the
    # default Decimal context, raising InvalidOperation through DuckDB.
    # Per FHIRPath §5.7.8 round([precision]) accepts any non-negative
    # Integer precision. The text-based rounding below avoids the
    # intermediate Decimal power entirely and mirrors the native C++
    # `roundDecimalSourceText` algorithm:
    # 1. Decompose num into sign/int-part/frac-part digit strings.
    # 2. Keep the first `num2` fractional digits.
    # 3. If the next fractional digit is >= 5, ROUND_HALF_UP carry.
    # 4. Reassemble as Decimal text and quantize to exactly num2 fractional
    #    digits.
    # Cap the effective precision at len(frac_part) since padding beyond
    # that doesn't change the mathematical value (Decimal('1.5') and
    # Decimal('1.5000') are mathematically equal; their toString differs
    # but is preserved by Python's Decimal defaults for normal precision).
    # This avoids O(precision) memory blow-up for malicious INT_MAX
    # precision values while still producing the spec-correct rounded
    # result.
    sign_str, digits, exp = num.as_tuple()
    # Build a plain decimal digit string with explicit decimal point.
    # digits is a tuple of decimal digits; exp is the power of 10.
    digit_str = ''.join(str(d) for d in digits) if digits else '0'
    if exp >= 0:
        int_part = digit_str + ('0' * exp)
        frac_part = ''
    else:
        point_pos = len(digit_str) + exp
        if point_pos <= 0:
            int_part = '0'
            frac_part = ('0' * (-point_pos)) + digit_str
        else:
            int_part = digit_str[:point_pos]
            frac_part = digit_str[point_pos:]
    int_part = int_part.lstrip('0') or '0'

    # FP-11 EXPLORER (2026-06-29): Cap effective precision at the input's
    # actual fractional digit count when the requested precision exceeds
    # it. Padding beyond that doesn't change the mathematical value; only
    # the toString shape gains trailing zeros. Without this cap, malicious
    # INT_MAX precision values would materialize multi-gigabyte zero-
    # padded strings. The cap is bounded by len(frac_part) which is itself
    # bounded by the input's Decimal precision (typically 28 digits).
    effective_precision = num2 if num2 <= len(frac_part) else len(frac_part)

    # If the precision is at least the existing fractional digit count,
    # the number is already rounded. Construct the Decimal from the input
    # digits directly, stripping trailing zeros to match native
    # normalizeRoundedDecimalText per §5.5.8 (-)?#0.0# (trailing zeros
    # optional). Decimal('0.10').round(2) -> Decimal('0.1') to match
    # native '0.1'.
    if effective_precision >= len(frac_part):
        rounded_int = int_part
        rounded_frac = frac_part.rstrip('0')
        if not rounded_frac:
            rounded_frac = '0'
        negative = sign_str != 0
        is_zero = rounded_int == '0' and all(c == '0' for c in rounded_frac)
        sign_prefix = '-' if negative and not is_zero else ''
        result_text = sign_prefix + rounded_int + '.' + rounded_frac
        result = Decimal(result_text)
        if quantity is not None:
            return nodes.FP_Quantity(result, quantity.unit)
        return result

    # Truncate to effective_precision fractional digits, then ROUND_HALF_UP.
    kept_frac = frac_part[:effective_precision]
    next_digit = frac_part[effective_precision]
    combined = int_part + kept_frac
    if not combined:
        combined = '0'
    digit_list = list(combined)
    if next_digit >= '5':
        i = len(digit_list) - 1
        carry = True
        while i >= 0 and carry:
            if digit_list[i] == '9':
                digit_list[i] = '0'
                i -= 1
            else:
                digit_list[i] = chr(ord(digit_list[i]) + 1)
                carry = False
        if carry:
            digit_list.insert(0, '1')
    rounded_digits = ''.join(digit_list)
    # Split back into int/frac parts of correct length.
    int_len = len(int_part)
    if len(rounded_digits) > int_len + effective_precision:
        int_len = len(rounded_digits) - effective_precision
    rounded_int = rounded_digits[:int_len] or '0'
    rounded_frac = rounded_digits[int_len:]
    # Pad to effective_precision digits, then strip trailing zeros to match
    # native normalizeRoundedDecimalText per §5.5.8 (-)?#0.0# (trailing
    # zeros optional). If everything strips, use '0' to preserve a Decimal
    # fractional digit per spec.
    rounded_frac = rounded_frac + ('0' * (effective_precision - len(rounded_frac)))
    rounded_frac = rounded_frac.rstrip('0')
    if not rounded_frac:
        rounded_frac = '0'
    rounded_int = rounded_int.lstrip('0') or '0'
    negative = sign_str != 0
    is_zero = rounded_int == '0' and all(c == '0' for c in rounded_frac)
    result_text = ('-' if negative and not is_zero else '') + rounded_int + '.' + rounded_frac
    result = Decimal(result_text)
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
