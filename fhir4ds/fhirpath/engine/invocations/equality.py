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

    # Calendar duration keywords and definite UCUM duration units above seconds
    # are explicitly unequal for equality (=), not incomparable/empty.
    if isinstance(a, nodes.FP_Quantity) and isinstance(b, nodes.FP_Quantity):
        _ucum_duration = {"'a'", "'mo'", "'wk'", "'d'", "'h'", "'min'", "a", "mo", "wk", "d", "h", "min"}
        _cal_duration = {
            "year", "years", "month", "months", "week", "weeks", "day", "days",
            "hour", "hours", "minute", "minutes",
        }
        if (a.unit in _ucum_duration and b.unit in _cal_duration) or \
           (a.unit in _cal_duration and b.unit in _ucum_duration):
            if not ctx.get("strict_mode"):
                return False
            _ucum_ym = {"'a'", "'mo'", "a", "mo"}
            _cal_ym = {"year", "years", "month", "months"}
            if (a.unit in _ucum_ym and b.unit in _cal_ym) or \
               (a.unit in _cal_ym and b.unit in _ucum_ym):
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

    return a == b


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
    return " ".join(s.lower().split())


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


def equivalence(ctx, x, y):
    if util.is_empty(x) and util.is_empty(y):
        return True

    if util.is_empty(x) or util.is_empty(y):
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
        return datetime_equality(ctx, x, y)

    if isinstance(a, str) and isinstance(b, str):
        return normalize_string(a) == normalize_string(b)

    if isinstance(a, Decimal) or isinstance(b, Decimal):
        return is_equivalent(a, b)

    x_val = util.parse_value(x[0])
    y_val = util.parse_value(y[0])

    if isinstance(x_val, nodes.FP_Quantity) and isinstance(y_val, nodes.FP_Quantity):
        if x_val.unit == y_val.unit:
            return x_val.deep_equal(y_val)

        l_base = _quantity_base(x_val)
        r_base = _quantity_base(y_val)
        if l_base is None or r_base is None:
            return x_val.deep_equal(y_val)
        l_value, l_unit = l_base
        r_value, r_unit = r_base
        if l_unit != r_unit:
            return False
        return is_equivalent(l_value, r_value)

    if isinstance(a, (abc.Mapping, list)) and isinstance(b, (abc.Mapping, list)):

        def deep_equal(a, b):
            a_quantity = util.parse_value(a)
            b_quantity = util.parse_value(b)
            if isinstance(a_quantity, nodes.FP_Quantity) and isinstance(b_quantity, nodes.FP_Quantity):
                return equivalence(ctx, [a_quantity], [b_quantity]) is True

            if isinstance(a, abc.Mapping) and isinstance(b, abc.Mapping):
                if a.keys() != b.keys():
                    return False
                return all(deep_equal(a[key], b[key]) for key in a)
            elif isinstance(a, list) and isinstance(b, list):
                if len(a) != len(b):
                    return False
                matched = [False] * len(b)
                for left in a:
                    found = False
                    for idx, right in enumerate(b):
                        if matched[idx]:
                            continue
                        if deep_equal(left, right):
                            matched[idx] = True
                            found = True
                            break
                    if not found:
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
    if len(unit) >= 2 and unit[0] == "'" and unit[-1] == "'":
        unit = unit[1:-1]

    table = {
        "ug": ("g", Decimal("0.000001")),
        "mg": ("g", Decimal("0.001")),
        "g": ("g", Decimal("1")),
        "kg": ("g", Decimal("1000")),
        "mm": ("m", Decimal("0.001")),
        "cm": ("m", Decimal("0.01")),
        "m": ("m", Decimal("1")),
        "km": ("m", Decimal("1000")),
        "ms": ("s", Decimal("0.001")),
        "s": ("s", Decimal("1")),
        "min": ("s", Decimal("60")),
        "h": ("s", Decimal("3600")),
        "d": ("s", Decimal("86400")),
        "wk": ("s", Decimal("604800")),
        "1": ("1", Decimal("1")),
        "%": ("1", Decimal("0.01")),
    }
    converted = table.get(unit)
    if not converted:
        return None
    base_unit, factor = converted
    return Decimal(str(q.value)) * factor, base_unit


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
    return util.arraify(equivalence_result, instead_none=False)


def unequival(ctx, a, b):
    equivalence_result = equivalence(ctx, a, b)
    unequivalence_result = None if equivalence_result is None else not equivalence_result
    return util.arraify(unequivalence_result, instead_none=True)


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
