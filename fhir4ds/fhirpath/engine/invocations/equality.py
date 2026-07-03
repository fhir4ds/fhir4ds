from collections import abc
from decimal import Decimal, ROUND_HALF_UP
import json
from ...engine import util as util
from ...engine import nodes as nodes
from ...engine.errors import FHIRPathError

"""
This file holds code to hande the FHIRPath Math functions.
"""
DATETIME_NODES_LIST = (nodes.FP_Date, nodes.FP_DateTime, nodes.FP_Time)

_CALENDAR_DURATION_UNITS = {
    "year", "years", "month", "months", "week", "weeks", "day", "days",
    "hour", "hours", "minute", "minutes", "second", "seconds",
    "millisecond", "milliseconds",
}
_UCUM_DURATION_UNITS = {"'a'", "'mo'", "'wk'", "'d'", "'h'", "'min'", "'s'", "'ms'", "a", "mo", "wk", "d", "h", "min", "s", "ms"}
_YEAR_MONTH_CALENDAR_UNITS = {"year", "years", "month", "months"}
_YEAR_MONTH_UCUM_UNITS = {"'a'", "'mo'", "a", "mo"}


def _is_numeric_value(value):
    return isinstance(value, (int, float, Decimal)) and not isinstance(value, bool)


def _numeric_to_unit_quantity(value):
    return nodes.FP_Quantity(Decimal(str(value)), "'1'")


def _coerce_numeric_quantity_pair(left, right):
    if isinstance(left, nodes.FP_Quantity) and _is_numeric_value(right):
        return left, _numeric_to_unit_quantity(right)
    if _is_numeric_value(left) and isinstance(right, nodes.FP_Quantity):
        return _numeric_to_unit_quantity(left), right
    return left, right


def _mixed_calendar_ucum_year_month(left_unit, right_unit):
    return (
        left_unit in _YEAR_MONTH_CALENDAR_UNITS and right_unit in _YEAR_MONTH_UCUM_UNITS
    ) or (
        left_unit in _YEAR_MONTH_UCUM_UNITS and right_unit in _YEAR_MONTH_CALENDAR_UNITS
    )


def equality(ctx, x, y):
    # FHIRPath §6.1.3: If either or both operands are empty, the result is empty (null propagation)
    if util.is_empty(x) or util.is_empty(y):
        return None

    if len(x) != len(y):
        return False

    if len(x) > 1:
        results = [equality(ctx, [left], [right]) for left, right in zip(x, y, strict=True)]
        if any(result is None for result in results):
            return None
        return all(results)

    if type(x[0]) in DATETIME_NODES_LIST or type(y[0]) in DATETIME_NODES_LIST:
        return datetime_equality(ctx, x, y)

    a = util.parse_value(x[0])
    b = util.parse_value(y[0])
    a, b = _coerce_numeric_quantity_pair(a, b)

    # §6.1: calendar years/months are not equal to definite UCUM years/months;
    # equality is indeterminate/empty. Other time-valued units are comparable.
    if isinstance(a, nodes.FP_Quantity) and isinstance(b, nodes.FP_Quantity):
        if _mixed_calendar_ucum_year_month(a.unit, b.unit):
            return None

    if (
        isinstance(a, nodes.FP_Quantity)
        and isinstance(b, nodes.FP_Quantity)
        and getattr(b, "unit", None) in nodes.FP_Quantity.mapUCUMCodeToTimeUnits.values()
    ):
        return a.deep_equal(b)

    if isinstance(a, nodes.FP_Quantity) and isinstance(b, nodes.FP_Quantity):
        if a.unit == b.unit:
            return a.value == b.value
        l_base = _quantity_base(a)
        r_base = _quantity_base(b)
        if l_base is None or r_base is None:
            return a == b
        l_value, l_unit = l_base
        r_value, r_unit = r_base
        if l_unit != r_unit:
            return None
        return l_value == r_value

    if isinstance(a, (abc.Mapping, list)) and isinstance(b, (abc.Mapping, list)):
        return _complex_equality(ctx, a, b)

    # FHIRPath §6.1.1: equality between incompatible types returns empty.
    # Only implicit conversions are allowed; Integer↔String is explicit.
    # Unwrap ResourceNode wrappers to get the actual data types.
    a_raw = util.get_data(a) if hasattr(a, 'data') else a
    b_raw = util.get_data(b) if hasattr(b, 'data') else b
    if isinstance(a_raw, (abc.Mapping, list)) and isinstance(b_raw, (abc.Mapping, list)):
        return _complex_equality(ctx, a_raw, b_raw)
    a_type = type(a_raw)
    b_type = type(b_raw)
    if a_type != b_type:
        # Allow numeric type mixing (int/float/Decimal)
        numeric = (int, float, Decimal)
        a_numeric = isinstance(a_raw, numeric) and not isinstance(a_raw, bool)
        b_numeric = isinstance(b_raw, numeric) and not isinstance(b_raw, bool)
        if not (a_numeric and b_numeric):
            return None  # incompatible types → empty

    # Compare the unwrapped values, not the original ResourceNode-wrapped
    # operands. ``util.get_data`` materializes raw JSON floats to ``Decimal``
    # so authored decimal digits survive; otherwise ResourceNode.__eq__ would
    # compare a binary float against a Decimal literal and silently return
    # False for §6.1.1-equal values such as ``probabilityDecimal = 123.45``.
    return a_raw == b_raw


def _complex_equality(ctx, a, b):
    a_quantity = util.parse_value(a)
    b_quantity = util.parse_value(b)
    if isinstance(a_quantity, nodes.FP_Quantity) and isinstance(b_quantity, nodes.FP_Quantity):
        return equality(ctx, [a_quantity], [b_quantity])

    if isinstance(a, abc.Mapping) and isinstance(b, abc.Mapping):
        if a.keys() != b.keys():
            return False
        for key in a:
            result = _complex_equality(ctx, a[key], b[key])
            if result is None:
                return None
            if result is False:
                return False
        return True

    if isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            return False
        for left, right in zip(a, b, strict=True):
            result = _complex_equality(ctx, left, right)
            if result is None:
                return None
            if result is False:
                return False
        return True

    if isinstance(a, (abc.Mapping, list)) or isinstance(b, (abc.Mapping, list)):
        return None

    return equality(ctx, [a], [b])


def normalize_string(s):
    return "".join(" " if ch.isspace() else ch.casefold() for ch in s)


def decimal_places(a):
    d = Decimal(str(a))
    match = f"{d:.{abs(d.as_tuple().exponent)}f}".rstrip("0").rstrip(".").split(".")
    return len(match[1]) if len(match) > 1 else 0


def round_to_decimal_places(a, n):
    rounding_format = Decimal("10") ** -n
    return Decimal(str(a)).quantize(rounding_format, rounding=ROUND_HALF_UP)


def is_equivalent(a, b):
    precision = min(decimal_places(a), decimal_places(b))
    if precision == 0:
        return round_to_decimal_places(a, 0) == round_to_decimal_places(b, 0)
    else:
        return round_to_decimal_places(a, precision) == round_to_decimal_places(b, precision)


def _quantity_equivalence_half_width(quantity, base_value):
    value = Decimal(str(quantity.value))
    if value == 0:
        scale = Decimal("1")
    else:
        scale = abs(Decimal(str(base_value)) / value)
    return Decimal("0.5") * (Decimal("10") ** -decimal_places(quantity.value)) * scale


def _quantities_equivalent(left, right):
    if left.unit == right.unit:
        return is_equivalent(left.value, right.value)

    l_base = _quantity_base(left)
    r_base = _quantity_base(right)
    if l_base is None or r_base is None:
        return None
    l_value, l_unit = l_base
    r_value, r_unit = r_base
    if l_unit != r_unit:
        return None

    tolerance = max(
        _quantity_equivalence_half_width(left, l_value),
        _quantity_equivalence_half_width(right, r_value),
    )
    return abs(l_value - r_value) < tolerance


def _is_implicitly_equivalent_pair(a, b):
    """Check whether two single-item values are implicitly convertible to
    the same type per FHIRPath §5.5 conversion table.

    Returns True if the types are the same OR if an implicit conversion
    exists between them. Returns False if only an Explicit conversion
    exists (e.g. Boolean<->Integer/Decimal/String, Decimal/Integer<->
    String), in which case §6.1.2 requires the result to be `false`
    (not auto-coerced).
    """
    # Unwrap ResourceNode to get the underlying data type.
    a_raw = util.get_data(a) if hasattr(a, 'data') else a
    b_raw = util.get_data(b) if hasattr(b, 'data') else b

    # Date/DateTime/Time: per §5.5 Date<->DateTime is Implicit; DateTime<->
    # Date is Explicit but Date->DateTime is Implicit. Treat the FP_TimeBase
    # family as compatible (the existing datetime_equality path handles
    # precision mismatch). Time is NOT compatible with Date/DateTime.
    a_is_temporal = isinstance(a_raw, DATETIME_NODES_LIST)
    b_is_temporal = isinstance(b_raw, DATETIME_NODES_LIST)
    if a_is_temporal or b_is_temporal:
        # Time vs Date/DateTime is not implicitly convertible (no
        # conversion path in §5.5 table between Time and Date/DateTime).
        a_is_time = isinstance(a_raw, nodes.FP_Time)
        b_is_time = isinstance(b_raw, nodes.FP_Time)
        if a_is_time != b_is_time:
            return False
        return True

    # FP_Quantity vs FP_Quantity or numeric vs FP_Quantity: Implicit.
    a_parsed = util.parse_value(a_raw)
    b_parsed = util.parse_value(b_raw)
    a_is_qty = isinstance(a_parsed, nodes.FP_Quantity)
    b_is_qty = isinstance(b_parsed, nodes.FP_Quantity)
    if a_is_qty or b_is_qty:
        # Numeric <-> Quantity is Implicit per §5.5; Quantity <->
        # Quantity is same-type. The downstream _quantities_equivalent
        # / _coerce_numeric_quantity_pair paths handle this.
        a_is_numeric = isinstance(a_raw, (int, float, Decimal)) and not isinstance(a_raw, bool)
        b_is_numeric = isinstance(b_raw, (int, float, Decimal)) and not isinstance(b_raw, bool)
        if a_is_qty and b_is_qty:
            return True
        if a_is_qty and b_is_numeric:
            return True
        if b_is_qty and a_is_numeric:
            return True
        # Quantity vs String/Boolean/Date/... not implicitly convertible.
        return False

    # Boolean: §5.5 says Boolean -> Integer/Decimal/String/Quantity are all
    # Explicit-only. Two Booleans are same-type. Boolean vs anything else
    # (without Quantity promotion above) returns False.
    a_is_bool = isinstance(a_raw, bool)
    b_is_bool = isinstance(b_raw, bool)
    if a_is_bool or b_is_bool:
        # Only same-type (bool==bool) is allowed.
        return a_is_bool and b_is_bool

    # Numeric (int/float/Decimal): Integer<->Decimal is Implicit.
    a_is_numeric = isinstance(a_raw, (int, float, Decimal))
    b_is_numeric = isinstance(b_raw, (int, float, Decimal))
    if a_is_numeric and b_is_numeric:
        return True

    # String: String<->Integer/Decimal/Boolean/Date/DateTime/Time are all
    # Explicit per §5.5 (String is Explicit in every From column). Only
    # String==String is implicitly equivalent.
    a_is_str = isinstance(a_raw, str)
    b_is_str = isinstance(b_raw, str)
    if a_is_str or b_is_str:
        return a_is_str and b_is_str

    # Mappings/lists: complex-type equivalence; defer to deep_equal.
    if isinstance(a_raw, (abc.Mapping, list)) or isinstance(b_raw, (abc.Mapping, list)):
        return isinstance(a_raw, (abc.Mapping, list)) and isinstance(b_raw, (abc.Mapping, list))

    # Fallback: same Python type allowed.
    return type(a_raw) == type(b_raw)


def equivalence(ctx, x, y):
    if util.is_empty(x) and util.is_empty(y):
        return True

    if util.is_empty(x) or util.is_empty(y):
        return False

    # FP-13 EXPLORER (2026-06-29): Per §6.1.2 "they must be of the same
    # type (or implicitly convertible to the same type)" combined with
    # the §5.5 conversion table. Boolean<->Integer/Decimal/String and
    # Decimal/Integer<->String are Explicit-only conversions; the
    # operands are NOT implicitly convertible, so the result is `false`
    # (not auto-coerced). Single-item check; multi-item delegates below
    # recurse through equivalence() which re-checks each pair.
    if len(x) == 1 and len(y) == 1:
        if not _is_implicitly_equivalent_pair(x[0], y[0]):
            return False

    if len(x) > 1 or len(y) > 1:
        def flatten_items(items):
            result = []
            for item in items:
                data = util.get_data(item)
                if isinstance(data, list):
                    result.extend(data)
                else:
                    result.append(item)
            return result

        x_flat = flatten_items(x)
        y_flat = flatten_items(y)

        if len(x_flat) != len(y_flat):
            return False

        matched = [False] * len(y_flat)
        for left in x_flat:
            found = False
            for idx, right in enumerate(y_flat):
                if matched[idx]:
                    continue
                if equivalence(ctx, [left], [right]) is True:
                    matched[idx] = True
                    found = True
                    break
            if not found:
                return False
        return True

    a = util.get_data(x[0])
    b = util.get_data(y[0])

    if type(a) in DATETIME_NODES_LIST or type(b) in DATETIME_NODES_LIST:
        result = datetime_equality(ctx, x, y)
        return False if result is None else result

    if isinstance(a, str) and isinstance(b, str):
        return normalize_string(a) == normalize_string(b)

    # FP-13 EXPLORER (2026-06-29): Per §5.5 Decimal/Integer<->Quantity is
    # Implicit; route Decimal-vs-Quantity pairs through the Quantity path
    # BEFORE the Decimal-only path below, which would crash on FP_Quantity
    # inputs to is_equivalent().
    x_val_early = util.parse_value(x[0])
    y_val_early = util.parse_value(y[0])
    if isinstance(x_val_early, nodes.FP_Quantity) or isinstance(y_val_early, nodes.FP_Quantity):
        x_val_early, y_val_early = _coerce_numeric_quantity_pair(x_val_early, y_val_early)
        if isinstance(x_val_early, nodes.FP_Quantity) and isinstance(y_val_early, nodes.FP_Quantity):
            return _quantities_equivalent(x_val_early, y_val_early)

    if isinstance(a, Decimal) or isinstance(b, Decimal):
        return is_equivalent(a, b)

    x_val = util.parse_value(x[0])
    y_val = util.parse_value(y[0])
    x_val, y_val = _coerce_numeric_quantity_pair(x_val, y_val)

    if isinstance(x_val, nodes.FP_Quantity) and isinstance(y_val, nodes.FP_Quantity):
        return _quantities_equivalent(x_val, y_val)

    if isinstance(a, (abc.Mapping, list)) and isinstance(b, (abc.Mapping, list)):

        def deep_equal(a, b):
            a_quantity = util.parse_value(a)
            b_quantity = util.parse_value(b)
            a_quantity, b_quantity = _coerce_numeric_quantity_pair(a_quantity, b_quantity)
            if isinstance(a_quantity, nodes.FP_Quantity) and isinstance(b_quantity, nodes.FP_Quantity):
                return _quantities_equivalent(a_quantity, b_quantity)

            if isinstance(a, abc.Mapping) and isinstance(b, abc.Mapping):
                if a.keys() != b.keys():
                    return False
                for key in a:
                    result = deep_equal(a[key], b[key])
                    if result is None:
                        return None
                    if result is False:
                        return False
                return True
            elif isinstance(a, list) and isinstance(b, list):
                if len(a) != len(b):
                    return False
                matched = [False] * len(b)
                saw_empty = False
                for left in a:
                    found = False
                    for idx, right in enumerate(b):
                        if matched[idx]:
                            continue
                        result = deep_equal(left, right)
                        if result is True:
                            matched[idx] = True
                            found = True
                            break
                        if result is None:
                            saw_empty = True
                    if not found:
                        if saw_empty:
                            return None
                        return False
                return True
            elif isinstance(a, str) and isinstance(b, str):
                return normalize_string(a) == normalize_string(b)
            elif (
                isinstance(a, (int, float, Decimal))
                and isinstance(b, (int, float, Decimal))
                and not isinstance(a, bool)
                and not isinstance(b, bool)
            ):
                return is_equivalent(a, b)
            else:
                return a == b

        return deep_equal(a, b)

    return x == y


def _quantity_base(q):
    unit = q.unit
    clean_unit = nodes.FP_Quantity._strip_unit_quotes(unit)
    if (
        unit not in nodes.FP_Quantity._ucum_base_conversion_factor
        and clean_unit not in nodes.FP_Quantity._ucum_base_conversion_factor
    ):
        return None
    converted = nodes.FP_Quantity.conv_unit_to_base(q.unit, q.value)
    return Decimal(str(converted.value)), converted.unit


def datetime_equality(ctx, x, y):
    datetime_x = x[0]
    datetime_y = y[0]
    if datetime_x is None or datetime_y is None:
        return None
    if type(datetime_x) not in DATETIME_NODES_LIST:
        v_x = util.get_data(datetime_x)
        if not isinstance(v_x, str):
            return None
        datetime_x = nodes.FP_TimeBase.get_match_data(v_x)
    if type(datetime_y) not in DATETIME_NODES_LIST:
        v_y = util.get_data(datetime_y)
        if not isinstance(v_y, str):
            return None
        datetime_y = nodes.FP_TimeBase.get_match_data(v_y)
    if datetime_x is None or datetime_y is None:
        return None
    return datetime_x.equals(datetime_y)


def equal(ctx, a, b):
    equality_result = equality(ctx, a, b)
    return util.arraify(equality_result)


def unequal(ctx, a, b):
    equality_result = equality(ctx, a, b)
    unequality_result = None if equality_result is None else not equality_result
    return util.arraify(unequality_result)


def equival(ctx, a, b):
    equivalence_result = equivalence(ctx, a, b)
    return util.arraify(equivalence_result)


def unequival(ctx, a, b):
    equivalence_result = equivalence(ctx, a, b)
    unequivalence_result = None if equivalence_result is None else not equivalence_result
    return util.arraify(unequivalence_result)


def check_length(value):
    if len(value) > 1:
        raise FHIRPathError(
            "Was expecting no more than one element but got "
            + json.dumps(value)
            + ". Singleton was expected"
        )


def remove_duplicate_extension(list):
    """
    This is a temporary solution for cases where the list contains 2 items with the same key,
    like birthDate and _birthDate. Needs to be fixed to a better solution.
    """
    if len(list) == 2 and isinstance(list[1], nodes.ResourceNode) and "extension" in list[1].data:
        return list[:1]
    return list


def _get_comparison_data(value):
    """Return comparison data while preserving typed FHIR XML primitive numerics."""
    if isinstance(value, nodes.ResourceNode):
        type_info = value.get_type_info()
        type_name = type_info.name if type_info else None
        if isinstance(value.data, str):
            if type_name in {"dateTime", "instant"}:
                parsed = nodes.FP_DateTime(value.data)
                if parsed is None and nodes.FP_Date(value.data):
                    parsed = nodes.FP_DateTime(value.data + "T")
                return parsed if parsed is not None else value.data
            if type_name == "date":
                parsed = nodes.FP_Date(value.data)
                return parsed if parsed is not None else value.data
            if type_name == "time":
                parsed = nodes.FP_Time(value.data)
                return parsed if parsed is not None else value.data
            if type_name in {"integer", "integer64", "unsignedInt", "positiveInt"}:
                try:
                    return int(value.data)
                except ValueError:
                    return value.data
            if type_name == "decimal":
                try:
                    return Decimal(value.data)
                except Exception:
                    return value.data
    return util.get_data(value)


def typecheck(a, b):
    """
    Checks that the types of a and b are suitable for comparison in an
    inequality expression.  It is assumed that a check has already been made
    that there is at least one value in a and b.

    Parameters:
    a (list) - the left side of the inequality expression (which should be an array of one value)
    b (list) -  the right side of the inequality expression (which should be an array of one value)

    returns the singleton values of the arrays a, and b.  If one was an FP_Type and the other was convertible, the coverted value will be retureed
    """
    rtn = None

    a = remove_duplicate_extension(a)
    b = remove_duplicate_extension(b)

    check_length(a)
    check_length(b)

    a = _get_comparison_data(a[0])
    b = _get_comparison_data(b[0])

    # Try to convert Quantity dicts to FP_Quantity
    a_parsed = util.parse_value(a)
    b_parsed = util.parse_value(b)
    if isinstance(a_parsed, nodes.FP_Quantity) or isinstance(b_parsed, nodes.FP_Quantity):
        a = a_parsed
        b = b_parsed

    lClass = a.__class__
    rClass = b.__class__

    areNumbers = util.is_number(a) and util.is_number(b)

    if lClass != rClass and not areNumbers:
        d = None

        # TODO refactor
        if lClass == str and (rClass == nodes.FP_DateTime or rClass == nodes.FP_Time or rClass == nodes.FP_Date):
            d = nodes.FP_Date(a) or nodes.FP_DateTime(a) or nodes.FP_Time(a)
            if d is not None:
                rtn = [d, b]
        elif rClass == str and (lClass == nodes.FP_DateTime or lClass == nodes.FP_Time or lClass == nodes.FP_Date):
            d = nodes.FP_Date(b) or nodes.FP_DateTime(b) or nodes.FP_Time(b)
            if d is not None:
                rtn = [a, d]
        # Allow Date vs DateTime comparison - they are both FP_TimeBase types
        # The comparison will return empty ({}) when types don't match at the compare() level
        elif isinstance(a, nodes.FP_TimeBase) and isinstance(b, nodes.FP_TimeBase):
            rtn = [a, b]

        if rtn is None:
            raise FHIRPathError(
                'Type of "'
                + str(a)
                + '" ('
                + lClass.__name__
                + ') did not match type of "'
                + str(b)
                + '" ('
                + rClass.__name__
                + "). InequalityExpression"
            )

    if rtn is not None:
        return rtn

    return [a, b]


def _is_time_domain_mismatch(a, b):
    return (
        isinstance(a, nodes.FP_TimeBase)
        and isinstance(b, nodes.FP_TimeBase)
        and isinstance(a, nodes.FP_Time) != isinstance(b, nodes.FP_Time)
    )


def _compare(ctx, a, b, fp_check, py_op):
    """Shared comparison logic for lt, gt, lte, gte."""
    if len(a) == 0 or len(b) == 0:
        return []
    if len(a) > 1 or len(b) > 1:
        raise FHIRPathError("Comparison operators require singleton operands")
    if a[0] is None or b[0] is None:
        return []

    vals = typecheck(a, b)
    a0 = vals[0]
    b0 = vals[1]

    if isinstance(a0, bool) and isinstance(b0, bool):
        raise FHIRPathError("Comparison operators are not defined for Boolean operands")

    # FHIRPath Section 6.2 defines ordering within Date, DateTime, or Time
    # domains. Time-only values are not implicitly convertible to calendar
    # Date/DateTime values.
    if _is_time_domain_mismatch(a0, b0):
        return None

    if isinstance(a0, nodes.FP_Type):
        try:
            cmp_result = a0.compare(b0)
            if cmp_result is None:
                return None
            return fp_check(cmp_result)
        except TypeError:
            return None

    return py_op(a0, b0)


def lt(ctx, a, b):
    return _compare(ctx, a, b, lambda c: c == -1, lambda x, y: x < y)


def gt(ctx, a, b):
    return _compare(ctx, a, b, lambda c: c == 1, lambda x, y: x > y)


def lte(ctx, a, b):
    return _compare(ctx, a, b, lambda c: c <= 0, lambda x, y: x <= y)


def gte(ctx, a, b):
    return _compare(ctx, a, b, lambda c: c >= 0, lambda x, y: x >= y)
