import json
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

    # FP-02 HISTORIAN QA-002 (2026-08-16): N1 §6.6.3 — "When the units of
    # quantity arguments are different, the quantity values must be
    # converted to the most granular unit, then simple addition on the
    # values can be performed" (`3 'm' + 3 'cm' // 303 'cm'`, `3 'cm' +
    # 3 'm' // 303 'cm'`). The operand whose unit has the smaller base
    # factor is the more granular one; ties prefer the operand already in
    # canonical (base) form so `1 'm2/m' + 1 'm'` still renders as 'm'.
    x_factor = nodes.FP_Quantity.conv_unit_to_base(x.unit, 1).value
    y_factor = nodes.FP_Quantity.conv_unit_to_base(y.unit, 1).value
    x_canonical = (
        nodes.FP_Quantity._strip_unit_quotes(x.unit)
        == nodes.FP_Quantity._strip_unit_quotes(x_base.unit)
    )
    y_canonical = (
        nodes.FP_Quantity._strip_unit_quotes(y.unit)
        == nodes.FP_Quantity._strip_unit_quotes(y_base.unit)
    )
    # NOTE: this module defines the FHIRPath `abs` function, so compute
    # magnitudes without shadowed builtins.
    def _magnitude(factor):
        return factor if factor >= 0 else -factor

    use_y = _magnitude(y_factor) < _magnitude(x_factor) or (
        _magnitude(y_factor) == _magnitude(x_factor) and y_canonical and not x_canonical
    )

    total_base = x_base.value + sign * y_base.value
    if use_y:
        result = total_base / y_factor
        return nodes.FP_Quantity(
            nodes.FP_Quantity._normalize_quantity_value(result), y.unit
        )
    result = total_base / x_factor
    return nodes.FP_Quantity(
        nodes.FP_Quantity._normalize_quantity_value(result), x.unit
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
        # FP-18 EXPLORER QA-002 (2026-08-18): §6.6.7 — implicit string
        # conversion of complex JSON values must use compact JSON
        # serialization (native C++ serializes via yyjson), never the Python
        # dict/list repr, which leaks single quotes and spaces.
        if isinstance(value, (dict, list)):
            return json.dumps(value, separators=(",", ":"), ensure_ascii=False)
        return str(value)

    return _string_value(x) + _string_value(y)



def _temporal_plus(x, q):
    # FP-18 SKEPTIC QA-005 (2026-08-18): §6.7.1 — an invalid time-valued
    # unit must "signal an error to the calling environment". The strict
    # core error contract is FHIRPathError; nodes.FP_TimeBase.plus raises
    # bare ValueError for invalid units (e.g. `@2012-01-01 + 25 hours`,
    # `@T10:00:00 + 1 day`). Translate at the operator boundary.
    try:
        return x.plus(q)
    except ValueError as exc:
        raise FHIRPathError(str(exc)) from exc


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
        y = nodes.FP_Quantity(nodes.FP_Quantity._normalize_quantity_value(y), "'1'")
    elif isinstance(y, nodes.FP_Quantity) and util.is_number(x):
        x = nodes.FP_Quantity(nodes.FP_Quantity._normalize_quantity_value(x), "'1'")

    if isinstance(x, nodes.FP_Quantity) and isinstance(y, nodes.FP_Quantity):
        return _quantity_add_or_sub(x, y, -1)

    if isinstance(x, nodes.FP_TimeBase) and isinstance(y, nodes.FP_Quantity):
        return _temporal_plus(x, nodes.FP_Quantity(-y.value, y.unit))

    if isinstance(x, str) and isinstance(y, nodes.FP_Quantity):
        x_ = nodes.FP_TimeBase.get_match_data(x)
        if x_ is not None:
            return _temporal_plus(x_, nodes.FP_Quantity(-y.value, y.unit))

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
    # FP-01 EXPLORER QA-002 (2026-08-16): Per §6.6.2 "The result of a
    # division is always Decimal, even if the inputs are both Integer".
    # Python's int/int truediv yields a binary64 float, which leaked the
    # double rendering into FHIRPath Decimal semantics: `1 / 3` displayed
    # '0.3333333333333333' while `1 / 3 = 0.3333333333333333` evaluated
    # FALSE (float-vs-Decimal comparison is exact). Convert Integer
    # operands to Decimal before dividing so the result is always a
    # Decimal at the default 28-significant-digit context (matching the
    # native C++ decimal-text division).
    if isinstance(x, int) and not isinstance(x, bool):
        x = Decimal(x)
    if isinstance(y, int) and not isinstance(y, bool):
        y = Decimal(y)
    # FP-18 HISTORIAN QA-003 (2026-06-30): Decimal division may produce a
    # whole-number Decimal like Decimal('3') which serializes without a
    # decimal point; force at least one decimal place per §5.5.8 format
    # (-)?#0.0#.
    result = x / y
    if isinstance(result, Decimal) and result == result.to_integral_value():
        try:
            return result.quantize(Decimal("0.1"))
        except InvalidOperation:
            # FP-01 EXPLORER QA-002 follow-up (2026-08-16): quotients at the
            # 28-digit context limit (e.g. `9999999999999999999999999999.99999999 / 1`
            # rounds to 1.000000000000000000000000000E+28) cannot quantize to
            # one decimal place without exceeding context precision; the
            # previous unguarded call crashed the whole DuckDB UDF with
            # InvalidOperation. Keep the unquantized Decimal — renderers
            # still append ".0" for integral text.
            return result
    return result


def _truncated_divmod_int(x, y):
    # FP-18 SKEPTIC QA-002 (2026-08-18): §6.6.5/§6.6.6 require EXACT
    # truncated division. int(x / y) routes through binary64 and silently
    # rounds 64-bit operands (9223372036854775807 div 1 -> ...808).
    # Python's // floors, so adjust toward zero explicitly.
    q = x // y
    if q < 0 and q * y != x:
        q += 1
    return q, x - q * y


def intdiv(ctx, x, y):
    # FP-18 HISTORIAN QA-002 (2026-06-30): Boolean-coercion guard.
    if not (util.is_number(x) and util.is_number(y)) and not (
        isinstance(x, nodes.FP_Quantity) or isinstance(y, nodes.FP_Quantity)
    ):
        raise FHIRPathError("Cannot " + str(x) + " div " + str(y))
    # FP-18 SKEPTIC QA-005 (2026-08-18): §6.6.5 div supports Integer and
    # Decimal only; a Quantity operand must signal an execution error, not
    # crash with a raw TypeError from int()/float() coercion.
    if isinstance(x, nodes.FP_Quantity) or isinstance(y, nodes.FP_Quantity):
        raise FHIRPathError("Cannot " + str(x) + " div " + str(y))
    if y == 0:
        return []
    if isinstance(x, int) and isinstance(y, int):
        # Exact int path (Long-sized operands included). int64 div
        # overflow (LLONG_MIN div -1) mirrors the native engine and the
        # §6.6.5 divide-by-zero convention: empty.
        if x == -(2**63) and y == -1:
            return []
        return _truncated_divmod_int(x, y)[0]
    # Decimal operands: exact truncated division at decimal context.
    from decimal import Decimal

    dx = x if isinstance(x, Decimal) else Decimal(x)
    dy = y if isinstance(y, Decimal) else Decimal(y)
    # Decimal // is exact truncated division (toward zero), §6.6.5.
    return int(dx // dy)


def mod(ctx, x, y):
    # FP-18 HISTORIAN QA-002 (2026-06-30): Boolean-coercion guard.
    if not (util.is_number(x) and util.is_number(y)) and not (
        isinstance(x, nodes.FP_Quantity) or isinstance(y, nodes.FP_Quantity)
    ):
        raise FHIRPathError("Cannot " + str(x) + " mod " + str(y))
    # FP-18 SKEPTIC QA-005 (2026-08-18): §6.6.6 mod supports Integer and
    # Decimal only; Quantity operands must raise FHIRPathError.
    if isinstance(x, nodes.FP_Quantity) or isinstance(y, nodes.FP_Quantity):
        raise FHIRPathError("Cannot " + str(x) + " mod " + str(y))
    if y == 0:
        return []

    # FHIRPath §6.6: mod uses truncated division.
    if isinstance(x, int) and isinstance(y, int):
        # FP-18 SKEPTIC QA-002 (2026-08-18): exact int path; float fmod
        # loses precision for 64-bit operands.
        return _truncated_divmod_int(x, y)[1]
    # Decimal arithmetic to avoid floating point precision issues.
    from decimal import Decimal, InvalidOperation
    try:
        dx = Decimal(str(x))
        dy = Decimal(str(y))
        # fmod semantics: x - trunc(x/y) * y (truncated division).
        # Decimal // is exact truncated division, §6.6.6 — avoid
        # int(dx / dy) whose 28-digit context can round the quotient.
        result = dx - (dx // dy) * dy
        return result
    except (InvalidOperation, ValueError):
        import math as _math
        result = _math.fmod(float(x), float(y))
        if isinstance(x, int) and isinstance(y, int):
            return int(result)
        return result
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
        y = nodes.FP_Quantity(nodes.FP_Quantity._normalize_quantity_value(y), "'1'")
    elif isinstance(y, nodes.FP_Quantity) and util.is_number(x):
        x = nodes.FP_Quantity(nodes.FP_Quantity._normalize_quantity_value(x), "'1'")

    if isinstance(x, nodes.FP_Quantity) and isinstance(y, nodes.FP_Quantity):
        return _quantity_add_or_sub(x, y, 1)

    if isinstance(x, nodes.FP_TimeBase) and isinstance(y, nodes.FP_Quantity):
        return _temporal_plus(x, y)

    if isinstance(x, str) and isinstance(y, nodes.FP_Quantity):
        x_ = nodes.FP_TimeBase.get_match_data(x)
        if x_ is not None:
            return _temporal_plus(x_, y)

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

    # FP-11 SKEPTIC QA-001 (2026-08-17): §5.7 power — Integer base with
    # Integer exponent yields an Integer result. A negative Integer exponent
    # cannot be represented as an Integer, so the result is empty (STU3
    # functions.json states this explicitly). Results beyond the 64-bit
    # Integer range degrade to the exact Decimal-shaped value (engine
    # doctrine shared with the native evaluator).
    result = None
    if isinstance(base_raw, int) and isinstance(exponent_raw, int):
        if exponent_raw < 0:
            return []
        result_int = base_raw ** exponent_raw
        if -(2 ** 63) <= result_int < 2 ** 63:
            return result_int
        # Beyond 64-bit Integer range: preserve the full exact Decimal-
        # shaped digits (FP-11 EXPLORER 2026-06-29 doctrine, e.g.
        # (2).power(1024)); do NOT normalize under the 28-digit context.
        return Decimal(result_int)
    elif num2 != num2.to_integral_value():
        # FP-11 SKEPTIC QA-004 (2026-08-17): Non-integral exponents are
        # transcendental; compute via binary64 so the result renders with
        # the shortest-round-trip float text on both engines (matching the
        # native std::pow path and the sqrt()/ln()/exp() siblings; per
        # §5.7 sqrt() is "equivalent to raising a number to the power of
        # 0.5").
        try:
            result = math.pow(float(num), float(num2))
        except (OverflowError, ValueError):
            return []
        if math.isinf(result) or math.isnan(result):
            return []
        return result
    else:
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
        # FP-11 SKEPTIC QA-003 (2026-08-17): a tie-free negative operand in
        # (-0.5, 0] quantizes to Decimal('-0'), which serialized as '-0.0'
        # and diverged from the native evaluator's '0.0'. Normalize negative
        # zero to positive zero (Decimal('-0') == 0 is True).
        if result == 0:
            result = result.copy_abs()
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
