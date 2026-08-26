import logging
import re
from calendar import monthrange
from decimal import Decimal

from ...engine import util as util
from ...engine import nodes as nodes
from ...engine.errors import FHIRPathError

_logger = logging.getLogger(__name__)

# This file holds code to hande the FHIRPath Existence functions (5.1 in the
# specification).

# FP-06 HISTORIAN (2026-08-17): use \Z (absolute end-of-string), not `$` —
# Python re `$` also matches before a single trailing newline, so '1\n'
# passed the grammar and converted to 1 while the native evaluator (and the
# exact (\+|-)?\d+ grammar of FHIRPath §5.5.3) reject it.
intRegex = re.compile(r"^[+-]?[0-9]+\Z")
# FP-06 HISTORIAN (2026-08-17): \Z end-anchor for the same reason as intRegex
# above — `$` matches before a single trailing newline, so '1\n'.toDecimal()
# converted in the fallback while the native evaluator rejects it.
numRegex = re.compile(r"^[+-]?[0-9]+(\.[0-9]+)?\Z")
# FP-07 SKEPTIC (2026-08-17): \Z end-anchor for the same reason as
# intRegex/numRegex above — `$` matches before a single trailing newline,
# so '5L\n' passed this regex and Decimal('5L') raised ConversionSyntax
# (unhandled UDF crash) while the native evaluator correctly returns empty
# via isFHIRPathLongDecimalString.
longDecimalStringRegex = re.compile(r"^[+-]?[0-9]+L\Z")


def _read_digits(value, pos, min_len, max_len):
    end = pos
    while end < len(value) and end - pos < max_len and value[end].isdigit():
        end += 1
    if end - pos < min_len:
        return None, pos
    return int(value[pos:end]), end


def _read_am_pm(value, pos):
    for token, is_pm in (("AM", False), ("PM", True), ("A", False), ("P", True)):
        if value[pos:pos + len(token)].upper() == token:
            return is_pm, pos + len(token)
    return None, pos


def _read_tz(value, pos):
    if pos >= len(value):
        return None, pos
    if value[pos] == "Z":
        return "Z", pos + 1
    if value[pos] not in "+-":
        return None, pos
    sign = value[pos]
    pos += 1
    hour, pos = _read_digits(value, pos, 2, 2)
    if hour is None:
        return None, pos
    if pos < len(value) and value[pos] == ":":
        pos += 1
    minute, pos = _read_digits(value, pos, 2, 2)
    if minute is None or hour > 14 or minute > 59 or (hour == 14 and minute != 0):
        return None, pos
    return f"{sign}{hour:02d}:{minute:02d}", pos


def _parse_temporal_with_format(value, fmt, want_datetime):
    if not isinstance(value, str) or not isinstance(fmt, str) or fmt == "":
        return None

    fields = {
        "year": None,
        "month": None,
        "day": None,
        "hour": None,
        "hour12": None,
        "minute": None,
        "second": None,
        "fraction": None,
        "tz": "",
        "ampm": None,
    }
    pos = 0
    fpos = 0

    while fpos < len(fmt):
        if fmt.startswith("yyyy", fpos):
            fields["year"], pos = _read_digits(value, pos, 4, 4)
            if fields["year"] is None:
                return None
            fpos += 4
        elif fmt.startswith("yy", fpos):
            yy, pos = _read_digits(value, pos, 2, 2)
            if yy is None:
                return None
            fields["year"] = 2000 + yy if yy <= 49 else 1900 + yy
            fpos += 2
        elif fmt.startswith("MM", fpos):
            fields["month"], pos = _read_digits(value, pos, 2, 2)
            if fields["month"] is None:
                return None
            fpos += 2
        elif fmt[fpos] == "M":
            fields["month"], pos = _read_digits(value, pos, 1, 2)
            if fields["month"] is None:
                return None
            fpos += 1
        elif fmt.startswith("dd", fpos):
            fields["day"], pos = _read_digits(value, pos, 2, 2)
            if fields["day"] is None:
                return None
            fpos += 2
        elif fmt[fpos] == "d":
            fields["day"], pos = _read_digits(value, pos, 1, 2)
            if fields["day"] is None:
                return None
            fpos += 1
        elif fmt.startswith("HH", fpos):
            fields["hour"], pos = _read_digits(value, pos, 2, 2)
            if fields["hour"] is None:
                return None
            fpos += 2
        elif fmt[fpos] == "H":
            fields["hour"], pos = _read_digits(value, pos, 1, 2)
            if fields["hour"] is None:
                return None
            fpos += 1
        elif fmt.startswith("hh", fpos):
            fields["hour12"], pos = _read_digits(value, pos, 2, 2)
            if fields["hour12"] is None:
                return None
            fpos += 2
        elif fmt[fpos] == "h":
            fields["hour12"], pos = _read_digits(value, pos, 1, 2)
            if fields["hour12"] is None:
                return None
            fpos += 1
        elif fmt.startswith("mm", fpos):
            fields["minute"], pos = _read_digits(value, pos, 2, 2)
            if fields["minute"] is None:
                return None
            fpos += 2
        elif fmt[fpos] == "m":
            fields["minute"], pos = _read_digits(value, pos, 1, 2)
            if fields["minute"] is None:
                return None
            fpos += 1
        elif fmt.startswith("ss", fpos):
            fields["second"], pos = _read_digits(value, pos, 2, 2)
            if fields["second"] is None:
                return None
            fpos += 2
        elif fmt[fpos] == "s":
            fields["second"], pos = _read_digits(value, pos, 1, 2)
            if fields["second"] is None:
                return None
            fpos += 1
        elif fmt[fpos] == "S":
            start = fpos
            while fpos < len(fmt) and fmt[fpos] == "S":
                fpos += 1
            width = fpos - start
            frac = value[pos:pos + width]
            if len(frac) != width or not frac.isdigit():
                return None
            fields["fraction"] = frac
            pos += width
        elif fmt[fpos] == "a":
            fields["ampm"], pos = _read_am_pm(value, pos)
            if fields["ampm"] is None:
                return None
            fpos += 1
        elif fmt[fpos] == "Z":
            fields["tz"], pos = _read_tz(value, pos)
            if fields["tz"] is None:
                return None
            fpos += 1
        elif fmt[fpos] in "yMdHhmsaSz":
            return None
        else:
            if pos >= len(value) or value[pos] != fmt[fpos]:
                return None
            pos += 1
            fpos += 1

    if pos != len(value) or fields["year"] is None:
        return None

    year = fields["year"]
    month = fields["month"]
    day = fields["day"]
    if not 1 <= year <= 9999:
        return None
    if month is not None and not 1 <= month <= 12:
        return None
    if day is not None:
        if month is None or not 1 <= day <= monthrange(year, month)[1]:
            return None

    date_part = f"{year:04d}"
    if month is not None:
        date_part += f"-{month:02d}"
    if day is not None:
        date_part += f"-{day:02d}"

    has_time = (
        fields["hour"] is not None
        or fields["hour12"] is not None
        or fields["minute"] is not None
        or fields["second"] is not None
        or fields["fraction"] is not None
        or bool(fields["tz"])
    )
    if not want_datetime and not has_time:
        return nodes.FP_Date(date_part) and date_part
    if not want_datetime:
        if month is None or day is None:
            return None

        hour = fields["hour"]
        if fields["hour12"] is not None:
            if fields["ampm"] is None or not 1 <= fields["hour12"] <= 12:
                return None
            hour = fields["hour12"] % 12 + (12 if fields["ampm"] else 0)
        if hour is None or not 0 <= hour <= 23:
            return None
        if fields["minute"] is not None and not 0 <= fields["minute"] <= 59:
            return None
        if fields["second"] is not None:
            if fields["minute"] is None or not 0 <= fields["second"] <= 59:
                return None
        if fields["fraction"] is not None and fields["second"] is None:
            return None
        return nodes.FP_Date(date_part) and date_part

    if not has_time:
        return nodes.FP_DateTime(date_part + "T") and date_part + "T"
    if month is None or day is None:
        return None

    hour = fields["hour"]
    if fields["hour12"] is not None:
        if fields["ampm"] is None or not 1 <= fields["hour12"] <= 12:
            return None
        hour = fields["hour12"] % 12 + (12 if fields["ampm"] else 0)
    if hour is None or not 0 <= hour <= 23:
        return None
    text = f"{date_part}T{hour:02d}"
    if fields["minute"] is not None:
        if not 0 <= fields["minute"] <= 59:
            return None
        text += f":{fields['minute']:02d}"
    if fields["second"] is not None:
        if fields["minute"] is None or not 0 <= fields["second"] <= 59:
            return None
        text += f":{fields['second']:02d}"
    if fields["fraction"] is not None:
        if fields["second"] is None:
            return None
        text += f".{fields['fraction']}"
    if fields["tz"]:
        text += fields["tz"]
    return nodes.FP_DateTime(text) and text


def iif_macro(ctx, data, cond, ok, fail=None):
    # iif can only be called on an empty or singleton collection
    if len(data) > 1:
        raise FHIRPathError("iif() can only be called on an empty or singleton collection")

    # FP-06 HISTORIAN (2026-08-17): mirror native fn_iif scope semantics —
    # variables defined in an iif branch do not escape it, and each branch
    # is evaluated with a cleared chain scope and restored vars/chain.
    # FP-06 EXPLORER (2026-08-17): native fn_iif evaluates the criterion in
    # the expression's main scope (defined_variables_ restored only for the
    # branch snapshots), so variables defined in the iif CRITERION persist
    # for the remainder of the whole expression — matching the §5.2.9
    # defineVariable contract ("available for the remainder of the
    # expression"). Verified natively for true, false, and empty criteria.
    # Branch-defined variables remain scoped to their branch.
    missing = object()
    old_chain = ctx.get("_chain_defined_vars", missing)

    def _eval_branch(branch):
        branch_base_vars = dict(ctx.get("vars", {}))
        try:
            if old_chain is not missing:
                ctx["_chain_defined_vars"] = set()
            return branch(data)
        finally:
            ctx["vars"] = branch_base_vars
            if old_chain is missing:
                ctx.pop("_chain_defined_vars", None)
            else:
                ctx["_chain_defined_vars"] = old_chain

    taken = util.is_true(cond(data), singleton_non_boolean=not ctx.get("strict_mode"))

    if taken:
        return _eval_branch(ok)
    elif fail:
        return _eval_branch(fail)
    else:
        return []


def trace_fn(ctx, x, label="", projection=None):
    trace_value = x
    if projection is not None:
        missing = object()
        old_index = ctx.get("$index", missing)
        saved_vars = dict(ctx.get("vars", {}))
        old_chain = ctx.get("_chain_defined_vars", missing)
        projected = []
        try:
            for i, item in enumerate(x):
                ctx["$index"] = i
                ctx["vars"] = dict(saved_vars)
                if old_chain is not missing:
                    ctx["_chain_defined_vars"] = set(old_chain)
                projected.append(projection(item))
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
        trace_value = util.flatten(projected)

    # Check if a custom trace callback is provided in the context
    if "traceFn" in ctx and callable(ctx["traceFn"]):
        ctx["traceFn"](label, trace_value)
    else:
        # Extract underlying FHIR data from ResourceNode wrappers
        display = [util.get_data(item) for item in trace_value] if isinstance(trace_value, list) else trace_value
        print("TRACE:[" + label + "]", str(display))
    return x


_SYSTEM_VARIABLES = frozenset({
    "context",
    "resource",
    "rootResource",
    "ucum",
    "sct",
    "loinc",
    "vs-administrative-gender",
    "ext-patient-birthTime",
})


def define_variable(ctx, coll, name, value_expr=None):
    """Define a transient environment variable for the current invocation chain."""
    if not isinstance(name, str):
        raise FHIRPathError("defineVariable() variable name must be a string")

    if name in _SYSTEM_VARIABLES:
        raise FHIRPathError(f"Cannot overwrite system variable %{name}")

    chain_vars = ctx.setdefault("_chain_defined_vars", set())
    if name in chain_vars:
        raise FHIRPathError(f"Variable %{name} is already defined in this scope")
    chain_vars.add(name)

    value = coll
    if value_expr is not None:
        saved_vars = dict(ctx.get("vars", {}))
        saved_chain = set(chain_vars)
        ctx["_chain_defined_vars"] = set()
        try:
            value = value_expr(coll)
        finally:
            ctx["vars"] = saved_vars
            ctx["_chain_defined_vars"] = saved_chain

    ctx["vars"][name] = value
    return coll


def to_integer(ctx, coll):
    if len(coll) > 1:
        raise FHIRPathError("toInteger() requires a single item input collection")
    if len(coll) == 0:
        return []

    value = util.get_data(coll[0])

    if value is False:
        return 0

    if value is True:
        return 1

    if isinstance(value, int) and not isinstance(value, bool):
        # FHIRPath Integer is 32-bit signed
        if -2147483648 <= value <= 2147483647:
            return value
        return []

    if isinstance(value, str):
        if re.match(intRegex, value) is not None:
            int_val = int(value)
            if -2147483648 <= int_val <= 2147483647:
                return int_val

    return []


# FP-08 EXPLORER (2026-06-28): use explicit ASCII `[0-9]` rather than `\d`
# because Python's `re` module treats `\d` as Unicode-aware (matching
# full-width U+FF10-U+FF19, Arabic-Indic U+0660-U+0669, Devanagari
# U+0966-U+096F, etc.), while the FHIRPath ANTLR grammar DIGIT fragment is
# the ASCII-only `[0-9]`. Native C++ `fn_toQuantity` uses
# `std::isdigit((unsigned char)...)` (ASCII-only) and rejects these inputs,
# producing a silent native↔fallback asymmetry. Same Python-re-Unicode
# trap as FP-07 EXPLORER (numRegex/intRegex/longDecimalStringRegex) — the
# `quantity_regex` was the explicitly-noted out-of-scope sibling that
# §5.5.7 now owns.
quantity_regex = re.compile(r"^((\+|-)?[0-9]+(\.[0-9]+)?)\s*(('[^']+')|([a-zA-Z]+))?$")
quantity_regex_map = {"value": 1, "unit": 5, "time": 6}


def to_quantity(ctx, coll, to_unit=None):
    result = None

    if to_unit == []:
        return []

    # Surround UCUM unit code in the to_unit parameter with single quotes
    if to_unit and not nodes.FP_Quantity.timeUnitsToUCUM.get(to_unit):
        to_unit = f"'{to_unit}'"

    if len(coll) > 1:
        raise FHIRPathError("Could not convert to quantity: input collection contains multiple items")
    elif len(coll) == 1:
        v = util.parse_value(util.val_data_converted(coll[0]))
        quantity_regex_res = None

        if isinstance(v, bool):
            result = nodes.FP_Quantity(1 if v else 0, "'1'")
        elif isinstance(v, (int, float, Decimal)):
            result = nodes.FP_Quantity(v, "'1'")
        elif isinstance(v, nodes.FP_Quantity):
            result = v
        elif isinstance(v, str):
            quantity_regex_res = quantity_regex.match(v)
            if quantity_regex_res:
                value = quantity_regex_res.group(quantity_regex_map["value"])
                unit = quantity_regex_res.group(quantity_regex_map["unit"])
                time = quantity_regex_res.group(quantity_regex_map["time"])

                if not time:
                    result = nodes.FP_Quantity(Decimal(value), unit or "'1'")
                elif nodes.FP_Quantity.timeUnitsToUCUM.get(time) and len(time) > 2:
                    result = nodes.FP_Quantity(Decimal(value), time)
                # FP-08 EXPLORER (2026-06-28): the prior
                # `elif nodes.FP_Quantity.timeUnitsToUCUM.get(time.lower())`
                # branch was removed because FHIRPath is case-sensitive (§8.7)
                # and §8.5 defines calendar duration keywords as lowercase
                # only (`year`/`years`/`month`/`months`/...). Uppercase or
                # mixed-case variants like `'1 YEAR'`, `'1 Year'`,
                # `'1 YEARS'`, `'1 DAYS'` must be rejected to match native
                # C++ `isBareDurationKeyword` (evaluator.cpp:1869-1875) which
                # already does case-sensitive lookup.
                # FHIRPath §5.5.7: the `time` regex group `[a-zA-Z]+` is for
                # calendar duration keywords only (per spec examples
                # `'4 days'`, `'10 \\'mg[Hg]\\''`). Bare UCUM codes must be
                # single-quoted via the `unit` group. Any unmatched alpha
                # sequence (e.g. '0xFF', '4 abc') must be rejected to match
                # native C++ behavior.

        if result and to_unit and result.unit != to_unit:
            # FP-08 SKEPTIC QA-001 (2026-08-17): §5.5.7 toQuantity() uses
            # its own canonical conversion-factor table (1 year = 12 months
            # or 365 days, 1 month = 30 days); route duration pairs through
            # it first so calendar-keyword cross conversions succeed, then
            # fall back to the equality-oriented group tables for metric /
            # mass / reduced-UCUM units.
            converted = nodes.FP_Quantity.conv_duration_to_spec(result.unit, result.value, to_unit)
            if converted is None:
                converted = nodes.FP_Quantity.conv_unit_to(result.unit, result.value, to_unit)
            if not converted:
                _logger.debug(
                    "Unit conversion from %s to %s failed — returning empty",
                    result.unit, to_unit,
                )
            # FP-08 HISTORIAN QA-001 (2026-08-17): conv_duration_to_spec()
            # and conv_unit_to() render exact terminating quotients without
            # Decimal scale artifacts (native parity); non-terminating
            # quotients keep their 28-significant-digit rounding verbatim.
            result = converted

    return result if result else []


def to_decimal(ctx, coll):
    if len(coll) > 1:
        raise FHIRPathError("toDecimal() requires a single item input collection")
    if len(coll) == 0:
        return []

    value = util.get_data(coll[0])

    if value is False:
        return Decimal("0.0")

    if value is True:
        return Decimal("1.0")

    if util.is_number(value):
        if isinstance(value, int) and not isinstance(value, bool):
            return Decimal(value)
        return Decimal(value)

    if isinstance(value, str):
        if re.match(numRegex, value) is not None:
            return Decimal(value)
        if re.match(longDecimalStringRegex, value) is not None:
            return Decimal(value[:-1])

    return []


def to_string(ctx, coll):
    if len(coll) > 1:
        raise FHIRPathError("toString() requires a single item input collection")
    if len(coll) == 0:
        return []

    value = util.parse_value(util.val_data_converted(coll[0]))
    if isinstance(value, float):
        value = Decimal(str(value))

    # A null item (e.g. a JSON-null child preserved by children()) has no
    # String representation (§5.5.2): empty, never the Python None repr.
    if value is None:
        return []

    if isinstance(value, (dict, list)):
        return []

    # Handle boolean values - FHIRPath uses lowercase 'true'/'false'
    if isinstance(value, bool):
        return 'true' if value else 'false'
    if isinstance(value, Decimal):
        text = format(value, "f")
        if "." not in text:
            text += ".0"
        return text

    return str(value)


# Defines a function on engine called to+timeType (e.g., toDateTime, etc.).
# @param timeType The string name of a class for a time type (e.g. "FP_DateTime").


def to_date_time(ctx, coll, fmt=None):
    ln = len(coll)
    rtn = []
    if ln > 1:
        raise FHIRPathError("to_date_time called for a collection of length " + str(ln))
    if fmt == []:
        return []

    if ln == 1:
        value = util.get_data(coll[0])

        if isinstance(value, nodes.FP_DateTime):
            rtn.append(value)
        elif isinstance(value, nodes.FP_Date):
            dateTimeObject = nodes.FP_DateTime(str(value) + 'T')
            if dateTimeObject:
                rtn.append(dateTimeObject)
        elif isinstance(value, str) and fmt is not None:
            dateTimeObject = _parse_temporal_with_format(value, fmt, want_datetime=True)
            if dateTimeObject:
                rtn.append(nodes.FP_DateTime(dateTimeObject))
        # First try FP_DateTime directly
        elif (dateTimeObject := nodes.FP_DateTime(value)):
            rtn.append(dateTimeObject)
        else:
            # If that fails, try FP_Date for date-only strings (e.g., "2015", "2015-02")
            # and convert them to FP_DateTime by appending 'T'
            dateObject = nodes.FP_Date(value)
            if dateObject:
                # Convert FP_Date string to FP_DateTime format by appending 'T'
                dateTimeObject = nodes.FP_DateTime(value + 'T')
                if dateTimeObject:
                    rtn.append(dateTimeObject)


    return util.get_data(rtn[0]) if rtn else []


def to_time(ctx, coll):
    ln = len(coll)
    rtn = []
    if ln > 1:
        raise FHIRPathError("to_time called for a collection of length " + str(ln))

    if ln == 1:
        value = util.get_data(coll[0])

        # FHIRPath §5.5.9 toTime(): "If the input collection contains a single
        # item, this function will return a single time if: the item is a Time
        # [or] the item is a String and is convertible to a Time." An FP_Time
        # input must passthrough unchanged; only String inputs go through the
        # FP_Time(string) constructor.
        if isinstance(value, nodes.FP_Time):
            rtn.append(value)
        else:
            timeObject = nodes.FP_Time(value)

            if timeObject:
                rtn.append(timeObject)

    return util.get_data(rtn[0]) if rtn else []


def to_date(ctx, coll, fmt=None):
    ln = len(coll)
    rtn = []

    if ln > 1:
        raise FHIRPathError("to_date called for a collection of length " + str(ln))
    if fmt == []:
        return []

    if ln == 1:
        value = util.get_data(coll[0])

        if isinstance(value, nodes.FP_Date):
            rtn.append(value)
        elif isinstance(value, nodes.FP_DateTime):
            date_str = str(value)
            tpos = date_str.find("T")
            if tpos != -1:
                date_str = date_str[:tpos]
            dateObject = nodes.FP_Date(date_str)
            if dateObject:
                rtn.append(dateObject)
        elif isinstance(value, str) and fmt is not None:
            dateObject = _parse_temporal_with_format(value, fmt, want_datetime=False)
            if dateObject:
                rtn.append(nodes.FP_Date(dateObject))
        # Try FP_Date first for date-only strings (e.g., "2015", "2015-02", "2015-02-04")
        elif (dateObject := nodes.FP_Date(value)):
            rtn.append(dateObject)
        else:
            dateTimeObject = nodes.FP_DateTime(value)
            if dateTimeObject:
                date_str = str(dateTimeObject)
                tpos = date_str.find("T")
                if tpos != -1:
                    date_str = date_str[:tpos]
                dateObject = nodes.FP_Date(date_str)
                if dateObject:
                    rtn.append(dateObject)

    return util.get_data(rtn[0]) if rtn else []


def create_converts_to_fn(to_function, _type):
    """Create a convertsToX function.

    Supports both invocation forms:
      - 'value'.convertsToX()  — 0-param form (parentData is the input)
      - convertsToX(value)     — 1-param form (first param is the input)
    """
    if isinstance(_type, str):
        def in_function(ctx, coll, *args):
            if args:
                # 1-param form: treat args[0] as the input collection
                coll = util.arraify(args[0])
            if len(coll) > 1:
                raise FHIRPathError("Conversion function requires a single item input collection")
            if len(coll) == 0:
                return []
            return type(to_function(ctx, coll)).__name__ == _type
        return in_function

    def in_function(ctx, coll, *args):
        if args:
            coll = util.arraify(args[0])
        if len(coll) > 1:
            raise FHIRPathError("Conversion function requires a single item input collection")
        if len(coll) == 0:
            return []
        return isinstance(to_function(ctx, coll), _type)

    return in_function


def converts_to_date(ctx, coll, fmt=None):
    if len(coll) > 1:
        raise FHIRPathError("convertsToDate() requires a single item input collection")
    if len(coll) == 0:
        return []
    if fmt == []:
        return []
    return isinstance(to_date(ctx, coll, fmt), nodes.FP_Date)


def converts_to_date_time(ctx, coll, fmt=None):
    if len(coll) > 1:
        raise FHIRPathError("convertsToDateTime() requires a single item input collection")
    if len(coll) == 0:
        return []
    if fmt == []:
        return []
    return isinstance(to_date_time(ctx, coll, fmt), nodes.FP_DateTime)


def converts_to_quantity(ctx, coll, to_unit=None):
    if len(coll) > 1:
        raise FHIRPathError("convertsToQuantity() requires a single item input collection")
    if len(coll) == 0:
        return []
    if to_unit == []:
        return []
    return isinstance(to_quantity(ctx, coll, to_unit), nodes.FP_Quantity)


def to_boolean(ctx, coll):
    true_strings = ['true', 't', 'yes', 'y', '1', '1.0']
    false_strings = ['false', 'f', 'no', 'n', '0', '0.0']

    if len(coll) > 1:
        raise FHIRPathError("toBoolean() requires a single item input collection")
    if len(coll) == 0:
        return []

    val = util.get_data(coll[0])
    var_type = type(val).__name__

    if var_type == "bool":
        return val
    elif var_type == "int" or var_type == "float" or var_type == "Decimal":
        if val == 1 or val == Decimal('1') or val == 1.0:
            return True
        elif val == 0 or val == Decimal('0') or val == 0.0:
            return False
    elif var_type == "str":
        lower_case_var = val.lower()
        if lower_case_var in true_strings:
            return True
        if lower_case_var in false_strings:
            return False

    return []


def boolean_singleton(coll):
    d = util.get_data(coll[0])
    if isinstance(d, bool):
        return d
    elif len(coll) == 1:
        return True

def string_singleton(coll):
    d = util.get_data(coll[0])
    if isinstance(d, str):
        return d

singleton_eval_by_type = {
    "Boolean": boolean_singleton,
    "String": string_singleton,
}

def singleton(coll, type):
    if len(coll) > 1:
        raise FHIRPathError("Unexpected collection {coll}; expected singleton of type {type}".format(coll=coll, type=type))
    elif len(coll) == 0:
        return []
    to_singleton = singleton_eval_by_type[type]
    if to_singleton:
        val = to_singleton(coll)
        if (val is not None):
            return val
        raise FHIRPathError("Expected {type}, but got: {coll}".format(type=type.lower(), coll=coll))
    raise FHIRPathError("Not supported type {}".format(type))


def _normalize_profile_url(url: str) -> str:
    """Strip version suffix from profile URL for comparison."""
    # Remove |version suffix if present (e.g., "...Patient|4.0.1" -> "...Patient")
    return url.split("|")[0].rstrip("/")


def conforms_to(ctx, coll, structure_definition_url):
    """
    Returns true if the input collection contains a single item that
    conforms to the given structure definition URL.

    This is a basic implementation that checks if the resource's resourceType
    matches the expected type from the URL using exact URL comparison
    (after stripping any version suffix).

    For example:
    - conformsTo('http://hl7.org/fhir/StructureDefinition/Patient') -> true for Patient resources
    - conformsTo('http://hl7.org/fhir/StructureDefinition/Person') -> false for Patient resources
    - conformsTo('http://trash') -> execution error (invalid URL)
    """
    if len(coll) != 1:
        return []

    item = coll[0]
    data = util.get_data(item)

    # Check if this is a FHIR resource
    if not isinstance(data, dict) or 'resourceType' not in data:
        return [False]

    resource_type = data['resourceType']

    # Check if URL is a valid FHIR StructureDefinition URL
    if not structure_definition_url:
        raise FHIRPathError("conformsTo requires a valid StructureDefinition URL")

    # For invalid/non-FHIR URLs, raise an error per FHIRPath spec
    if not structure_definition_url.startswith('http://hl7.org/fhir') and \
       not structure_definition_url.startswith('https://hl7.org/fhir'):
        raise FHIRPathError(f"Unable to resolve structure definition: {structure_definition_url}")

    # Normalize URL by stripping version suffix
    normalized = _normalize_profile_url(structure_definition_url)

    # Exact match against the canonical StructureDefinition URL for this resource type
    expected = f"http://hl7.org/fhir/StructureDefinition/{resource_type}"
    if normalized == expected:
        return [True]

    # Handle FHIR core types that are base types
    # Per FHIR R4: Bundle, Binary, Parameters extend Resource directly.
    # All other resources extend DomainResource which extends Resource.
    _RESOURCE_ONLY_TYPES = frozenset({'Bundle', 'Binary', 'Parameters'})

    expected_type = normalized.split('/')[-1]

    if resource_type in _RESOURCE_ONLY_TYPES:
        ancestors = ['Resource']
    else:
        ancestors = ['DomainResource', 'Resource']

    if expected_type in ancestors:
        return [True]

    return [False]
