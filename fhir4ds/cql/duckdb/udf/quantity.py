"""
CQL Quantity Arithmetic UDFs

Implements CQL quantity operations with unit-aware calculations:
- parseQuantity(quantity_json) - Parse FHIR Quantity JSON
- quantityValue(quantity_json) - Extract numeric value
- quantityUnit(quantity_json) - Extract unit
- quantityCompare(q1, q2, op) - Unit-aware comparison
- quantityAdd(q1, q2) - Add two quantities with unit conversion
- quantitySubtract(q1, q2) - Subtract two quantities
- quantityConvert(q, target_unit) - Convert to different unit

Quantity format: JSON string {"value": 140, "code": "mm[Hg]", "system": "http://unitsofmeasure.org"}
"""

from __future__ import annotations

import ast as _ast
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import math
import re
import threading
from typing import TYPE_CHECKING

import orjson
from orjson import JSONDecodeError

try:
    from pint.errors import DimensionalityError, RedefinitionError, UndefinedUnitError
except ImportError:
    class DimensionalityError(Exception):
        """Fallback used when pint is unavailable at import time."""

    class RedefinitionError(Exception):
        """Fallback used when pint is unavailable at import time."""

    class UndefinedUnitError(Exception):
        """Fallback used when pint is unavailable at import time."""

if TYPE_CHECKING:
    import duckdb


import logging

_logger = logging.getLogger(__name__)
# Thread-safe singleton for UnitRegistry
_ureg_lock = threading.Lock()
_ureg = None

_CQL_DECIMAL_INTEGER_DIGITS = 30
_CQL_DECIMAL_SCALE = 8
_JSON_NUMBER_RE = r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?"
_JSON_VALUE_RE = re.compile(rf'"value"\s*:\s*({_JSON_NUMBER_RE})')

# Mapping from UCUM codes to Pint unit names
# UCUM uses special characters that aren't valid Python identifiers
UCUM_TO_PINT = {
    # Pressure - use abbreviations that pint supports
    "mm[Hg]": "mmHg",
    "cm[H2O]": "cmH2O",
    # Temperature
    "[degF]": "degF",
    "degF": "degF",
    "Cel": "degC",
    # Time - use standard pint abbreviations
    "a": "year",
    "mo": "month",
    "wk": "week",
    "d": "day",
    "h": "hour",
    "min": "minute",
    "s": "second",
    "ms": "millisecond",
    # Length
    "[in_i]": "inch",
    "in": "inch",
    "ft": "foot",
    "[ft_i]": "foot",
    "cm": "centimeter",
    "mm": "millimeter",
    "m": "meter",
    "km": "kilometer",
    # Mass
    "mg": "milligram",
    "g": "gram",
    "kg": "kilogram",
    "ug": "microgram",
    # Volume
    "mL": "milliliter",
    "L": "liter",
    "dL": "deciliter",
    # Concentration - compound units
    "mg/dL": "milligram / deciliter",
    "g/dL": "gram / deciliter",
    "mmol/L": "millimole / liter",
    "ug/mL": "microgram / milliliter",
    "g/cm3": "gram / centimeter ** 3",
    # Dimensionless
    "1": "dimensionless",
}

# Reverse mapping from Pint to UCUM
PINT_TO_UCUM = {
    "millimeter_of_mercury": "mm[Hg]",
    "mmHg": "mm[Hg]",
    "centimeter_of_water": "cm[H2O]",
    "cmH2O": "cm[H2O]",
    "degF": "[degF]",
    "degC": "Cel",
    "year": "a",
    "month": "mo",
    "week": "wk",
    "day": "d",
    "hour": "h",
    "minute": "min",
    "second": "s",
    "millisecond": "ms",
    "inch": "[in_i]",
    "foot": "[ft_i]",
    "millimeter": "mm",
    "centimeter": "cm",
    "meter": "m",
    "kilometer": "km",
    "milligram": "mg",
    "gram": "g",
    "kilogram": "kg",
    "microgram": "ug",
    "milliliter": "mL",
    "liter": "L",
    "deciliter": "dL",
    "dimensionless": "1",
}

_CQL_CALENDAR_DURATION_UNITS = {
    "year",
    "years",
    "month",
    "months",
    "week",
    "weeks",
    "day",
    "days",
    "hour",
    "hours",
    "minute",
    "minutes",
    "second",
    "seconds",
    "millisecond",
    "milliseconds",
}

_CQL_VARIABLE_CALENDAR_UNITS = {
    "year": Decimal("12"),
    "years": Decimal("12"),
    "month": Decimal("1"),
    "months": Decimal("1"),
}

_CQL_EQUIVALENT_DURATION_DAYS = {
    "year": Decimal("365"),
    "years": Decimal("365"),
    "a": Decimal("365"),
    "month": Decimal("30"),
    "months": Decimal("30"),
    "mo": Decimal("30"),
    "week": Decimal("7"),
    "weeks": Decimal("7"),
    "wk": Decimal("7"),
    "day": Decimal("1"),
    "days": Decimal("1"),
    "d": Decimal("1"),
    "hour": Decimal("1") / Decimal("24"),
    "hours": Decimal("1") / Decimal("24"),
    "h": Decimal("1") / Decimal("24"),
    "minute": Decimal("1") / Decimal("1440"),
    "minutes": Decimal("1") / Decimal("1440"),
    "min": Decimal("1") / Decimal("1440"),
    "second": Decimal("1") / Decimal("86400"),
    "seconds": Decimal("1") / Decimal("86400"),
    "s": Decimal("1") / Decimal("86400"),
    "millisecond": Decimal("1") / Decimal("86400000"),
    "milliseconds": Decimal("1") / Decimal("86400000"),
    "ms": Decimal("1") / Decimal("86400000"),
}

_CQL_DEFINITE_DURATION_DAYS = {
    key: value
    for key, value in _CQL_EQUIVALENT_DURATION_DAYS.items()
    if key not in {"year", "years", "a", "month", "months", "mo"}
}

_DURATION_NOT_APPLICABLE = object()

# Sentinel for "this is not a cross-unit offset-temperature comparison".
_OFFSET_NOT_APPLICABLE = object()

# UCUM and pint aliases that all refer to offset-temperature units. Used by
# `_compare_offset_temperature` to detect when explicit Cel<->[degF]
# conversion is required (pint refuses with "Ambiguous operation with
# offset unit"). Keys are canonical lowercased UCUM codes / aliases; the
# value is a canonical symbol used in the conversion table below.
_OFFSET_TEMPERATURE_ALIASES = {
    "cel": "Cel",
    "degc": "Cel",
    "degree_celsius": "Cel",
    "celsius": "Cel",
    "[degf]": "[degF]",
    "degf": "[degF]",
    "degree_fahrenheit": "[degF]",
    "fahrenheit": "[degF]",
    "k": "K",
    "kelvin": "K",
}


def _to_kelvin(value: float, unit: str) -> float | None:
    """Convert a temperature value in `unit` to Kelvin."""
    if unit == "Cel":
        return value + 273.15
    if unit == "[degF]":
        return (value - 32.0) * 5.0 / 9.0 + 273.15
    if unit == "K":
        return value
    return None


def _compare_offset_temperature(q1_dict: dict, q2_dict: dict, op: str):
    """Compare two quantities when at least one is an offset-temperature unit.

    Returns `_OFFSET_NOT_APPLICABLE` when neither operand is an offset-
    temperature unit (caller should fall through to the standard pint path),
    or when both operands are in the SAME unit (the standard path handles
    same-unit comparison correctly). Otherwise performs explicit conversion
    to Kelvin and compares magnitudes, returning True/False per `op`.

    Per CQL §Equal/§Equivalent (Quantity), comparison is performed after
    converting to a common unit. Pint refuses cross-unit offset-temperature
    conversion with "Ambiguous operation with offset unit"; the native C++
    quantity.cpp handles this internally, so the Python fallback must too
    or cross-unit temperature comparisons will silently return None.
    """
    code1 = (q1_dict.get("code") or "").strip()
    code2 = (q2_dict.get("code") or "").strip()
    if not code1 or not code2:
        return _OFFSET_NOT_APPLICABLE

    canon1 = _OFFSET_TEMPERATURE_ALIASES.get(code1.lower())
    canon2 = _OFFSET_TEMPERATURE_ALIASES.get(code2.lower())
    if canon1 is None and canon2 is None:
        return _OFFSET_NOT_APPLICABLE
    # Only handle offset-temperature; if only one operand is offset-temperature
    # and the other is not, units are genuinely incompatible -> return None
    # (do not raise; spec requires null for incompatible units).
    if canon1 is None or canon2 is None:
        return None
    # Same unit -> explicit comparison. Pint refuses even same-unit offset
    # comparison (`pint_q2.to(pint_q1.units)` raises "Ambiguous operation
    # with offset unit" for degC/degF), so we cannot fall through to the
    # standard pint path. Compare magnitudes directly.
    if canon1 == canon2:
        v1s = q1_dict.get("value")
        v2s = q2_dict.get("value")
        if v1s is None or v2s is None or isinstance(v1s, (str, bool)) or isinstance(v2s, (str, bool)):
            return None
        try:
            v1 = float(v1s)
            v2 = float(v2s)
        except (TypeError, ValueError):
            return None
    else:
        v1s = q1_dict.get("value")
        v2s = q2_dict.get("value")
        if v1s is None or v2s is None or isinstance(v1s, (str, bool)) or isinstance(v2s, (str, bool)):
            return None
        try:
            k1 = _to_kelvin(float(v1s), canon1)
            k2 = _to_kelvin(float(v2s), canon2)
        except (TypeError, ValueError):
            return None
        if k1 is None or k2 is None:
            return None
        v1 = k1
        v2 = k2

    if op == ">":
        return v1 > v2
    if op == "<":
        return v1 < v2
    if op == ">=":
        return v1 >= v2
    if op == "<=":
        return v1 <= v2
    if op == "==":
        return v1 == v2
    if op == "!=":
        return v1 != v2
    if op in ("~", "!~"):
        # Equivalence uses least-precision operand rounding. For temperatures
        # both operands are typically Decimal-scale; use a tight tolerance
        # consistent with the existing pint-based ~ path.
        tolerance = 1e-8
        if op == "~":
            return abs(v1 - v2) <= tolerance
        return abs(v1 - v2) > tolerance
    return None


def _get_ureg():
    """Lazy-load UnitRegistry (thread-safe singleton) with UCUM aliases."""
    global _ureg
    if _ureg is not None:
        return _ureg

    with _ureg_lock:
        if _ureg is not None:
            return _ureg

        try:
            from pint import UnitRegistry

            # Use default registry which has all standard units
            _ureg = UnitRegistry()

            # Add UCUM-specific aliases
            # Pressure units that pint doesn't have by default
            try:
                _ureg.define("mmHg = millimeter_Hg = 133.322 * pascal")
                _ureg.define("cmH2O = centimeter_H2O = 98.0665 * pascal")
            except RedefinitionError as e:
                _logger.warning("_get_ureg define unit failed: %s", e)  # Units may already exist

        except ImportError:
            _ureg = None

        return _ureg


def _require_ureg():
    """Return the unit registry or raise a clear error if pint is unavailable."""
    ureg = _get_ureg()
    if ureg is None:
        raise ImportError(
            "Quantity UDFs require 'pint' to be installed and importable. "
            "Reinstall duckdb-cql-py with its declared dependencies."
        )
    return ureg


def _ucum_to_pint_unit(ucum_code: str) -> str:
    """Convert UCUM code to Pint-compatible unit name."""
    # Check mapping first
    if ucum_code in UCUM_TO_PINT:
        return UCUM_TO_PINT[ucum_code]

    # Handle compound UCUM codes with / (e.g., "mg/dL" not in map)
    if "/" in ucum_code:
        parts = ucum_code.split("/", 1)
        return _ucum_to_pint_unit(parts[0]) + " / " + _ucum_to_pint_unit(parts[1])

    # Handle power notation like "cm2" → "centimeter ** 2"
    import re
    m = re.match(r'^([a-zA-Z\[\]]+)(\d+)$', ucum_code)
    if m:
        base = _ucum_to_pint_unit(m.group(1))
        return f"{base} ** {m.group(2)}"

    # Default: assume the code is already a valid Pint unit
    return ucum_code


def _pint_to_ucum_unit(pint_unit_str: str) -> str:
    """Convert Pint unit name back to UCUM code."""
    # Check reverse mapping
    if pint_unit_str in PINT_TO_UCUM:
        return PINT_TO_UCUM[pint_unit_str]

    # Handle compound units like "milligram / deciliter"
    if " / " in pint_unit_str:
        parts = pint_unit_str.split(" / ")
        converted_parts = [_pint_to_ucum_unit(p.strip()) for p in parts]
        return "/".join(converted_parts)

    # Handle power units like "centimeter ** 2" → "cm2"
    if " ** " in pint_unit_str:
        base, exp = pint_unit_str.split(" ** ", 1)
        base_ucum = _pint_to_ucum_unit(base.strip())
        return f"{base_ucum}{exp.strip()}"

    # Default: return as-is
    return pint_unit_str


def _is_valid_quantity_unit(unit: str | None) -> bool:
    if unit is None or unit == "1" or unit in _CQL_CALENDAR_DURATION_UNITS:
        return True
    ureg = _get_ureg()
    if ureg is None:
        return unit in UCUM_TO_PINT
    try:
        ureg(_ucum_to_pint_unit(unit))
        return True
    except (UndefinedUnitError, ValueError, TypeError, AssertionError):
        # pint's internal parser raises bare AssertionError on some malformed
        # unit strings (e.g. the single-codepoint degree-Celsius ``℃`` U+2103).
        # The CQL §ConvertsToQuantity / §ConvertsToRatio / §CanConvertQuantity
        # contracts require returning False for invalid units rather than
        # leaking the assertion through the public UDF surface.
        return False


def _decimal_quantity_value(q_dict: dict) -> Decimal | None:
    try:
        value = q_dict.get("value")
        if value is None:
            return None
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None


def _decimal_equivalence_precision(q_dict: dict) -> int:
    raw_precision = q_dict.get("_precision")
    if isinstance(raw_precision, int) and raw_precision >= 0:
        return raw_precision
    value = _decimal_quantity_value(q_dict)
    if value is None:
        return 0
    normalized = value.normalize()
    return max(0, -normalized.as_tuple().exponent)


def _round_decimal_for_equivalence(value: Decimal, precision: int) -> Decimal:
    quant = Decimal(1).scaleb(-precision)
    return value.quantize(quant, rounding=ROUND_HALF_UP)


def _apply_quantity_compare(
    left: Decimal,
    right: Decimal,
    op: str,
    left_precision: int | None = None,
    right_precision: int | None = None,
) -> bool | None:
    if op == "~":
        precision = min(left_precision or 0, right_precision or 0)
        return (
            _round_decimal_for_equivalence(left, precision)
            == _round_decimal_for_equivalence(right, precision)
        )
    if op == "!~":
        precision = min(left_precision or 0, right_precision or 0)
        return (
            _round_decimal_for_equivalence(left, precision)
            != _round_decimal_for_equivalence(right, precision)
        )
    if op == "==":
        return left == right
    if op == "!=":
        return left != right
    if op == ">":
        return left > right
    if op == "<":
        return left < right
    if op == ">=":
        return left >= right
    if op == "<=":
        return left <= right
    return None


def _compare_cql_duration_quantities(q1_dict: dict, q2_dict: dict, op: str):
    unit1 = (q1_dict.get("code") or q1_dict.get("unit") or "1")
    unit2 = (q2_dict.get("code") or q2_dict.get("unit") or "1")
    if unit1 not in _CQL_EQUIVALENT_DURATION_DAYS and unit2 not in _CQL_EQUIVALENT_DURATION_DAYS:
        return _DURATION_NOT_APPLICABLE
    if unit1 not in _CQL_EQUIVALENT_DURATION_DAYS or unit2 not in _CQL_EQUIVALENT_DURATION_DAYS:
        return None

    value1 = _decimal_quantity_value(q1_dict)
    value2 = _decimal_quantity_value(q2_dict)
    if value1 is None or value2 is None:
        return None
    precision1 = _decimal_equivalence_precision(q1_dict)
    precision2 = _decimal_equivalence_precision(q2_dict)

    if op in ("~", "!~"):
        left = value1 * _CQL_EQUIVALENT_DURATION_DAYS[unit1]
        right = value2 * _CQL_EQUIVALENT_DURATION_DAYS[unit2]
        return _apply_quantity_compare(left, right, op, precision1, precision2)

    if unit1 in _CQL_VARIABLE_CALENDAR_UNITS or unit2 in _CQL_VARIABLE_CALENDAR_UNITS:
        if unit1 in _CQL_VARIABLE_CALENDAR_UNITS and unit2 in _CQL_VARIABLE_CALENDAR_UNITS:
            left = value1 * _CQL_VARIABLE_CALENDAR_UNITS[unit1]
            right = value2 * _CQL_VARIABLE_CALENDAR_UNITS[unit2]
            return _apply_quantity_compare(left, right, op, precision1, precision2)
        return None

    left = value1 * _CQL_DEFINITE_DURATION_DAYS[unit1]
    right = value2 * _CQL_DEFINITE_DURATION_DAYS[unit2]
    return _apply_quantity_compare(left, right, op, precision1, precision2)


def _parse_quantity(value: str | None) -> dict | None:
    """Parse FHIR Quantity JSON to dict."""
    if not value:
        return None
    raw_precision = None
    try:
        match = _JSON_VALUE_RE.search(value)
        if match:
            raw_number = match.group(1)
            raw_precision = len(raw_number.split(".", 1)[1].split("e", 1)[0].split("E", 1)[0].rstrip("0")) if "." in raw_number else 0
    except (TypeError, AttributeError):
        raw_precision = None
    try:
        data = orjson.loads(value)
        if not isinstance(data, dict):
            _logger.warning("_parse_quantity expected object, got %s", type(data).__name__)
            return None
        raw_value = data.get("value")
        quantity_value = raw_value
        if raw_value is not None and (
            isinstance(raw_value, (bool, str))
            or not isinstance(raw_value, (int, float))
        ):
            quantity_value = None
        elif isinstance(quantity_value, int) and not isinstance(quantity_value, bool):
            # CQL §Types/Quantity: structured type Quantity { value Decimal,
            # unit String }. The serialized JSON must always present `value`
            # as Decimal/float, never as Integer. Without this normalization
            # the Python fallback diverges from the native C++ UDF for
            # integer-valued Quantity literals like `5 'mg'` or `1 year`
            # (Python emits `"value":5`, native emits `"value":5.0`).
            # bool is excluded because Python `True`/`False` are subclasses
            # of int; a Boolean `value` is invalid per spec.
            quantity_value = float(quantity_value)

        code = data.get("code") or data.get("unit") or "1"
        result = {
            "value": quantity_value,
            "code": code,
            "system": data.get("system", "http://unitsofmeasure.org"),
        }
        if raw_precision is not None:
            result["_precision"] = raw_precision
        # Preserve the unit field for FHIRPath .unit access
        unit = data.get("unit")
        if unit is not None:
            result["unit"] = unit
        return result
    except JSONDecodeError as e:
        _logger.warning("_parse_quantity failed: %s", e)
        return None


def _quantity_to_pint(q_dict: dict | None):
    """Convert quantity dict to pint Quantity."""
    value = q_dict.get("value") if q_dict else None
    if (
        not q_dict
        or value is None
        or isinstance(value, (bool, str))
        or not q_dict.get("code")
    ):
        return None

    ureg = _get_ureg()
    if ureg is None:
        return None

    try:
        ucum_code = q_dict["code"]
        value = float(value)
        pint_unit = _ucum_to_pint_unit(ucum_code)
        return value * ureg(pint_unit)
    except (TypeError, ValueError, UndefinedUnitError) as e:
        _logger.warning("_quantity_to_pint conversion failed: %s", e)
        return None


def _format_quantity(pint_q) -> str | None:
    """Format pint Quantity back to FHIR Quantity JSON."""
    if pint_q is None:
        return None

    try:
        # Get the magnitude and units
        value = float(pint_q.magnitude)
        unit_str = str(pint_q.units)
        code = _pint_to_ucum_unit(unit_str)

        result = {"value": value, "unit": code, "code": code, "system": "http://unitsofmeasure.org"}
        return orjson.dumps(result).decode("utf-8")
    except (TypeError, ValueError, AttributeError) as e:
        _logger.warning("_format_quantity failed: %s", e)
        return None


def _format_quantity_with_code(pint_q, code: str) -> str | None:
    """Format pint Quantity back to FHIR Quantity JSON, preserving the
    provided UCUM ``code`` string verbatim for both ``unit`` and ``code``
    fields.

    CQL Quantity arithmetic preserves the operand unit code as authored
    (CQL §09-b-cqlreference Sum/Subtract; LHS-preservation rule documented
    in ``fhir4ds/cql/AGENTS.md``). Routing the result back through
    :func:`_pint_to_ucum_unit` would normalize case (e.g. ``ml`` -> ``mL``)
    and lose the original authoring, diverging from the C++ extension which
    preserves the input code. Use this helper whenever the original operand
    code is known.
    """
    if pint_q is None:
        return None

    try:
        value = float(pint_q.magnitude)
        result = {
            "value": value,
            "unit": code,
            "code": code,
            "system": "http://unitsofmeasure.org",
        }
        return orjson.dumps(result).decode("utf-8")
    except (TypeError, ValueError, AttributeError) as e:
        _logger.warning("_format_quantity_with_code failed: %s", e)
        return None


def _most_granular_compatible_unit(code1: str, code2: str) -> str | None:
    """Return the smaller compatible UCUM unit for CQL Quantity addition."""
    if code1 == code2:
        return code1

    ureg = _get_ureg()
    if ureg is None:
        return None

    try:
        unit1 = _ucum_to_pint_unit(code1)
        unit2 = _ucum_to_pint_unit(code2)
        q1 = 1 * ureg(unit1)
        q2 = 1 * ureg(unit2)
        q2.to(q1.units)
        base1 = q1.to_base_units()
        base2 = q2.to_base_units()
        if str(base1.units) != str(base2.units):
            return None
        return code1 if abs(float(base1.magnitude)) <= abs(float(base2.magnitude)) else code2
    except (DimensionalityError, UndefinedUnitError, ValueError, AttributeError) as e:
        _logger.warning("_most_granular_compatible_unit failed: %s", e)
        return None


def _is_finite_decimal_value(value) -> bool:
    if isinstance(value, bool):
        return False
    try:
        decimal_value = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return False
    return decimal_value.is_finite()


def _representable_cql_decimal(value) -> Decimal | None:
    if isinstance(value, bool):
        return None
    try:
        decimal_value = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    if not decimal_value.is_finite():
        return None
    if decimal_value.as_tuple().exponent < -_CQL_DECIMAL_SCALE:
        return None
    if decimal_value.is_zero():
        return decimal_value
    integer_digits = decimal_value.copy_abs().adjusted() + 1
    if integer_digits > _CQL_DECIMAL_INTEGER_DIGITS:
        return None
    return decimal_value


def _raw_json_quantity_value_is_representable(value: str) -> bool:
    match = _JSON_VALUE_RE.search(value)
    return match is not None and _representable_cql_decimal(match.group(1)) is not None


def _decimal_json_number(value: Decimal) -> str:
    return format(value, "f")


def is_valid_quantity_object(value) -> bool:
    """Return true when a JSON object has the minimum CQL Quantity shape."""
    quantity_value = value.get("value") if isinstance(value, dict) else None
    if (
        not isinstance(value, dict)
        or quantity_value is None
        or isinstance(quantity_value, (bool, str))
        or _representable_cql_decimal(quantity_value) is None
    ):
        return False
    return _is_valid_quantity_unit(value.get("unit") or value.get("code") or "1")


def _format_cql_quantity(value, unit: str = "1") -> str | None:
    if (
        value is None
        or isinstance(value, bool)
        or not _is_valid_quantity_unit(unit)
    ):
        return None
    decimal_value = _representable_cql_decimal(value)
    if decimal_value is None:
        return None
    return (
        '{"value":'
        + _decimal_json_number(decimal_value)
        + ',"unit":'
        + orjson.dumps(unit).decode("utf-8")
        + ',"code":'
        + orjson.dumps(unit).decode("utf-8")
        + ',"system":"http://unitsofmeasure.org"}'
    )


def _quantity_from_ratio_json(value: str) -> str | None:
    if not _raw_json_quantity_value_is_representable(value):
        return None
    try:
        data = orjson.loads(value)
    except JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    numerator = data.get("numerator")
    denominator = data.get("denominator")
    if not is_valid_quantity_object(numerator) or not is_valid_quantity_object(denominator):
        return None
    return quantityDivide(orjson.dumps(numerator).decode("utf-8"), orjson.dumps(denominator).decode("utf-8"))


def _quantity_identity_from_json(value: str) -> str | None:
    """CQL 1.5 Appendix B §ToQuantity (Table 9-E): Quantity -> Quantity is the
    identity conversion; re-emit the canonical form after shape/unit validation."""
    try:
        data = orjson.loads(value)
    except JSONDecodeError:
        return None
    if not is_valid_quantity_object(data):
        return None
    return _format_cql_quantity(
        data["value"], data.get("unit") or data.get("code") or "1"
    )


# ========================================
# Core Functions
# ========================================


def parseQuantity(quantity_json: str | None) -> str | None:
    """Parse FHIR Quantity JSON and return as JSON string.

    Args:
        quantity_json: JSON string representing a FHIR Quantity

    Returns:
        JSON string with normalized quantity, or None if invalid
    """
    q = _parse_quantity(quantity_json)
    if q is None:
        return None
    public_q = {key: value for key, value in q.items() if key != "_precision"}
    return orjson.dumps(public_q).decode("utf-8")


def quantityValue(quantity_json: str | None) -> float | None:
    """Extract numeric value from a FHIR Quantity.

    Args:
        quantity_json: JSON string representing a FHIR Quantity

    Returns:
        The numeric value or None if invalid
    """
    q = _parse_quantity(quantity_json)
    if not q or q.get("value") is None:
        return None

    try:
        return float(q["value"])
    except (TypeError, ValueError):
        return None


def quantityUnit(quantity_json: str | None) -> str | None:
    """Extract unit from a FHIR Quantity.

    Args:
        quantity_json: JSON string representing a FHIR Quantity

    Returns:
        The unit code or None if invalid
    """
    q = _parse_quantity(quantity_json)
    if not q:
        return None
    return q.get("code")


# Canonical UCUM symbol set for structural same-code validity. Mirrors the
# native conversion-table keys in
# extensions/cql/src/include/shared/ucum_units.hpp (85 entries) plus 'l'
# (liter) and 'G' (gauss), which are valid UCUM symbols without a local
# conversion factor. Keep in lockstep with the C++ is_known_ucum_symbol().
_UCUM_VALIDITY_SYMBOLS = frozenset({
    "%", "[ft_i]", "[in_i]", "[lb_av]", "[oz_av]", "cm", "cm2", "d", "g", "h",
    "kg", "km", "m", "m2", "mg", "min", "mm", "ms", "s", "ug", "wk",
    "Cel", "K", "L", "Pa", "[degF]", "cmH2O", "cm[H2O]", "degF", "dL",
    "day", "days", "foot", "ft", "g/dL", "hour", "hours", "in", "inch",
    "kPa", "lb", "mL", "mg/dL", "millisecond", "milliseconds", "minute",
    "minutes", "mmHg", "mm[Hg]", "mmol/L", "mo", "month", "months", "oz",
    "second", "seconds", "uL", "ug/mL", "week", "weeks", "year", "years",
    "a", "'cm'", "'m'", "'mm'", "'km'", "'kg'", "'g'", "'[ft_i]'",
    "'[in_i]'", "'[lb_av]'", "'[oz_av]'", "/min", "l", "G",
})

# UCUM case-sensitive metric prefixes (single-char, plus two-char 'da').
_UCUM_METRIC_PREFIX_CHARS = frozenset("YZEPTGMkhdcunpfazy")


def _is_valid_ucum_atom(atom: str) -> bool:
    """Structural validity of a separator-free, annotation-free UCUM term.

    Mirrors the native is_valid_ucum_atom(): power-of-ten terms ('10*3',
    '10^-6'), known symbols, or a metric prefix applied to a known symbol
    ('Mg', 'ML', 'dag'). A bare prefix ('M') or unknown code ('xyz') is
    invalid.
    """
    if len(atom) > 3 and atom[:2] == "10" and atom[2] in "*^":
        digits = atom[3:]
        stripped = digits.lstrip("+-")
        if stripped and stripped.isdigit():
            return True
    if atom in _UCUM_VALIDITY_SYMBOLS:
        return True
    # Exponent-suffixed symbols ('m2', 'cm3'): a known symbol plus one
    # trailing exponent digit (1-9) is a valid UCUM atom.
    if len(atom) > 1 and atom[-1] in "123456789" and atom[:-1] in _UCUM_VALIDITY_SYMBOLS:
        return True
    if len(atom) > 2 and atom.startswith("da") and atom[2:] in _UCUM_VALIDITY_SYMBOLS:
        return True
    if (
        len(atom) > 1
        and atom[0] in _UCUM_METRIC_PREFIX_CHARS
        and atom[1:] in _UCUM_VALIDITY_SYMBOLS
    ):
        return True
    return False


def _same_code_unit_valid_for_compare(unit: str | None) -> bool:
    """Mirror of the native C++ ``same_code_unit_valid_for_compare`` guard.

    CQL 1.5 §Equal (Quantity): operating on quantities with invalid units
    yields null. Identical unit codes may compare by value only when the
    unit is valid — a known UCUM/calendar unit, a UCUM annotation
    ('{dose}', '[pH]'), an annotated known unit ('mm[Hg]' -> 'mm'), or a
    compound of valid components ('mg/m2'). Bare unknown codes ('xyz') are
    invalid. Keeps the Python fallback in lockstep with the native
    quantity_compare() same-code fast path.
    """
    if unit is None or unit == "1" or unit in _CQL_CALENDAR_DURATION_UNITS:
        return True
    core = ""
    i = 0
    while i < len(unit):
        c = unit[i]
        if c in "{[":
            closer = "}" if c == "{" else "]"
            close = unit.find(closer, i + 1)
            if close == -1:
                return False  # unterminated annotation
            i = close + 1
            continue
        core += c
        i += 1
    if not core:
        return True  # pure annotation ('{dose}', '[pH]')
    # Structural UCUM grammar, not pint: metric-prefixed symbols ('Mg',
    # 'ML') and power-of-ten terms ('10*3/uL') are valid UCUM that pint
    # cannot reliably judge, while invalid bare prefixes ('M') must not be
    # rescued by pint's case-insensitive parsing. Mirrors the native
    # same_code_unit_valid_for_compare() atom check.
    seps = "/."
    if not any(s in core for s in seps):
        return _is_valid_ucum_atom(core)
    component = ""
    for i, ch in enumerate(core):
        if ch in seps:
            if not component or not _same_code_unit_valid_for_compare(component):
                return False
            component = ""
        else:
            component += ch
    return bool(component) and _same_code_unit_valid_for_compare(component)


def quantityCompare(q1_json: str | None, q2_json: str | None, op: str) -> bool | None:
    """Compare two quantities with unit-aware comparison.

    Supports operators: >, <, >=, <=, ==, !=, ~, !~

    Args:
        q1_json: First quantity as JSON string
        q2_json: Second quantity as JSON string
        op: Comparison operator

    Returns:
        bool result, or None if units are incompatible
    """
    q1_dict = _parse_quantity(q1_json)
    q2_dict = _parse_quantity(q2_json)

    if not q1_dict or not q2_dict:
        return None

    duration_result = _compare_cql_duration_quantities(q1_dict, q2_dict, op)
    if duration_result is not _DURATION_NOT_APPLICABLE:
        return duration_result

    # CQL §Equal/§Equivalent (Quantity): comparison is performed after
    # converting to a common unit. Offset-temperature units (Cel/[degF])
    # require non-linear conversion (degF = degC * 9/5 + 32) which pint
    # refuses with "Ambiguous operation with offset unit". The native C++
    # quantity.cpp handles this internally; the Python fallback must do the
    # same so cross-unit temperature comparisons return correct True/False
    # instead of None.
    offset_result = _compare_offset_temperature(q1_dict, q2_dict, op)
    if offset_result is not _OFFSET_NOT_APPLICABLE:
        return offset_result

    # CQL 1.5 §Equal (Quantity): identical unit codes compare by value only
    # when the unit is valid; unknown UCUM codes ('xyz') yield null. This
    # mirrors the native quantity_compare() same-code fast path including
    # annotation ('{dose}') and compound ('mg/m2') units that pint cannot
    # resolve directly.
    code1 = q1_dict.get("code") or "1"
    code2 = q2_dict.get("code") or "1"
    if code1 == code2 and _same_code_unit_valid_for_compare(code1):
        v1 = float(q1_dict.get("value"))
        v2 = float(q2_dict.get("value"))
        if op == ">":
            return v1 > v2
        if op == "<":
            return v1 < v2
        if op == ">=":
            return v1 >= v2
        if op == "<=":
            return v1 <= v2
        if op == "==":
            return v1 == v2
        if op == "!=":
            return v1 != v2
        if op in ("~", "!~"):
            return _apply_quantity_compare(
                Decimal(str(v1)),
                Decimal(str(v2)),
                op,
                _decimal_equivalence_precision(q1_dict),
                _decimal_equivalence_precision(q2_dict),
            )
    elif code1 == code2:
        # Identical but INVALID unit codes must not be rescued by pint's
        # case-insensitive parsing (it accepts the bare prefix 'M'); the
        # native same-code path returns null here.
        return None

    pint_q1 = _quantity_to_pint(q1_dict)
    pint_q2 = _quantity_to_pint(q2_dict)

    if pint_q1 is None or pint_q2 is None:
        return None

    try:
        # Try to convert to same units for comparison
        pint_q2_converted = pint_q2.to(pint_q1.units)
    except (DimensionalityError, UndefinedUnitError, ValueError) as e:
        _logger.warning("UDF quantityCompare unit conversion failed: %s", e)
        return None

    v1 = pint_q1.magnitude
    v2 = pint_q2_converted.magnitude
    precision1 = _decimal_equivalence_precision(q1_dict)
    precision2 = _decimal_equivalence_precision(q2_dict)

    if op == ">":
        return v1 > v2
    elif op == "<":
        return v1 < v2
    elif op == ">=":
        return v1 >= v2
    elif op == "<=":
        return v1 <= v2
    elif op == "==":
        return v1 == v2
    elif op == "!=":
        return v1 != v2
    elif op == "~":
        return _apply_quantity_compare(Decimal(str(v1)), Decimal(str(v2)), op, precision1, precision2)
    elif op == "!~":
        return _apply_quantity_compare(Decimal(str(v1)), Decimal(str(v2)), op, precision1, precision2)
    else:
        return None


def quantityAdd(q1_json: str | None, q2_json: str | None) -> str | None:
    """Add two quantities with unit conversion.

    Args:
        q1_json: First quantity as JSON string
        q2_json: Second quantity as JSON string

    Returns:
        JSON string of resulting quantity, or None if incompatible units
    """
    q1_dict = _parse_quantity(q1_json)
    q2_dict = _parse_quantity(q2_json)

    if not q1_dict or not q2_dict:
        return None

    pint_q1 = _quantity_to_pint(q1_dict)
    pint_q2 = _quantity_to_pint(q2_dict)

    if pint_q1 is None or pint_q2 is None:
        return None

    try:
        code1 = q1_dict.get("code") or "1"
        code2 = q2_dict.get("code") or "1"
        result_code = _most_granular_compatible_unit(code1, code2)
        if result_code is None:
            return None
        result_unit = _ucum_to_pint_unit(result_code)
        result = pint_q1.to(result_unit) + pint_q2.to(result_unit)
        # Preserve the original result unit code (CQL §09-b Sum preserves
        # LHS or most-granular unit; pint round-trip would normalize case).
        return _format_quantity_with_code(result, result_code)
    except (DimensionalityError, UndefinedUnitError, ValueError) as e:
        _logger.warning("UDF quantityAdd failed: %s", e)
        return None


def quantitySubtract(q1_json: str | None, q2_json: str | None) -> str | None:
    """Subtract two quantities with unit conversion.

    Args:
        q1_json: First quantity as JSON string
        q2_json: Second quantity as JSON string

    Returns:
        JSON string of resulting quantity, or None if incompatible units
    """
    q1_dict = _parse_quantity(q1_json)
    q2_dict = _parse_quantity(q2_json)

    if not q1_dict or not q2_dict:
        return None

    pint_q1 = _quantity_to_pint(q1_dict)
    pint_q2 = _quantity_to_pint(q2_dict)

    if pint_q1 is None or pint_q2 is None:
        return None

    try:
        # Convert q2 to q1's units and subtract
        pint_q2_converted = pint_q2.to(pint_q1.units)
        result = pint_q1 - pint_q2_converted
        # Preserve the original LHS unit code (CQL §09-b Subtract preserves
        # LHS unit; pint round-trip would normalize case).
        lhs_code = q1_dict.get("code") or "1"
        return _format_quantity_with_code(result, lhs_code)
    except (DimensionalityError, UndefinedUnitError, ValueError) as e:
        _logger.warning("UDF quantitySubtract failed: %s", e)
        return None


def quantityConvert(q_json: str | None, target_unit: str) -> str | None:
    """Convert a quantity to a different unit.

    Args:
        q_json: Quantity as JSON string
        target_unit: Target unit code

    Returns:
        JSON string of converted quantity, or None if conversion not possible
    """
    q_dict = _parse_quantity(q_json)

    if not q_dict:
        return None

    pint_q = _quantity_to_pint(q_dict)

    if pint_q is None:
        return None

    ureg = _get_ureg()
    if ureg is None:
        return None

    try:
        target_pint_unit = _ucum_to_pint_unit(target_unit)
        result = pint_q.to(ureg(target_pint_unit))
        return _format_quantity(result)
    except (DimensionalityError, UndefinedUnitError, ValueError) as e:
        _logger.warning("UDF quantityConvert failed: %s", e)
        return None


def quantityNegate(q_json: str | None) -> str | None:
    """Negate a quantity (CQL unary minus on Quantity).

    CQL Spec §16.8: Negation. "When negating quantities, the unit is
    unchanged." Mirror the native C++ ``quantity_negate``: flip the value
    sign and re-serialize with the original unit preserved verbatim. Do
    NOT round-trip through pint — pint normalizes calendar-duration
    keywords ('day') to UCUM ('d'), which diverges from the native engine
    for temporals like `-(3 days)` (CQL-11 EXPLORER QA-003).
    """
    from decimal import Decimal, InvalidOperation

    if not q_json:
        return None
    match = _JSON_VALUE_RE.search(q_json)
    if not match:
        return None
    try:
        current = Decimal(match.group(1))
    except (InvalidOperation, TypeError):
        return None
    try:
        data = orjson.loads(q_json)
    except JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    unit = data.get("unit")
    code = data.get("code") or unit or "1"
    return (
        '{"value":'
        + str(float(-current))
        + ',"unit":'
        + orjson.dumps(unit if unit is not None else code).decode("utf-8")
        + ',"code":'
        + orjson.dumps(code).decode("utf-8")
        + ',"system":'
        + orjson.dumps(
            data.get("system", "http://unitsofmeasure.org")
        ).decode("utf-8")
        + "}"
    )


def quantityAbs(q_json: str | None) -> str | None:
    """Absolute value of a quantity (CQL Abs on Quantity).

    CQL Spec §16.1: Abs.
    """
    q_dict = _parse_quantity(q_json)
    if not q_dict:
        return None
    pint_q = _quantity_to_pint(q_dict)
    if pint_q is None:
        return None
    try:
        result = abs(pint_q)
        return _format_quantity(result)
    except Exception as e:
        _logger.warning("UDF quantityAbs failed: %s", e)
        return None


def quantityMultiply(q1_json: str | None, q2_json: str | None) -> str | None:
    """Multiply two quantities (CQL §16.7).

    Result unit is the product of units (e.g., cm * cm = cm^2).
    """
    q1_dict = _parse_quantity(q1_json)
    q2_dict = _parse_quantity(q2_json)
    if not q1_dict or not q2_dict:
        return None
    pint_q1 = _quantity_to_pint(q1_dict)
    pint_q2 = _quantity_to_pint(q2_dict)
    if pint_q1 is None or pint_q2 is None:
        return None
    try:
        result = pint_q1 * pint_q2
        return _format_quantity(result)
    except Exception as e:
        _logger.warning("UDF quantityMultiply failed: %s", e)
        return None


def quantityDivide(q1_json: str | None, q2_json: str | None) -> str | None:
    """Divide two quantities (CQL §16.4).

    Division by zero returns null per CQL spec.
    """
    q1_dict = _parse_quantity(q1_json)
    q2_dict = _parse_quantity(q2_json)
    if not q1_dict or not q2_dict:
        return None
    pint_q1 = _quantity_to_pint(q1_dict)
    pint_q2 = _quantity_to_pint(q2_dict)
    if pint_q1 is None or pint_q2 is None:
        return None
    try:
        if pint_q2.magnitude == 0:
            return None  # CQL §16.4: division by zero → null
        result = pint_q1 / pint_q2
        # CQL 1.5 §9.4 Divide: "For division operations involving quantities,
        # the resulting quantity will have the appropriate unit." Reference
        # engine (DivideEvaluator.kt) uses ucumService.divideBy, which applies
        # the unit conversion factor and cancels commensurable units, so
        # 1000 'mg' / 1 'g' is 1.0 '1' — not 1000 'mg/g'. pint only performs
        # that cancellation for equal-unit exponents, so reduce explicitly.
        # Incommensurable compound units (e.g. 'mg'/'mL') are unchanged.
        result = result.to_reduced_units()
        return _format_quantity(result)
    except Exception as e:
        _logger.warning("UDF quantityDivide failed: %s", e)
        return None


def quantityTruncatedDivide(q1_json: str | None, q2_json: str | None) -> str | None:
    """Truncated division of two quantities (CQL §16.13).

    Returns integer division result (truncated toward zero).
    When both operands have the same unit, result keeps that unit.
    Division by zero returns null per CQL spec.
    """
    q1_dict = _parse_quantity(q1_json)
    q2_dict = _parse_quantity(q2_json)
    if not q1_dict or not q2_dict:
        return None
    pint_q1 = _quantity_to_pint(q1_dict)
    pint_q2 = _quantity_to_pint(q2_dict)
    if pint_q1 is None or pint_q2 is None:
        return None
    try:
        if pint_q2.magnitude == 0:
            return None  # CQL §16.13: division by zero → null
        # Convert q2 to q1's units for same-dimension comparison
        pint_q2_converted = pint_q2.to(pint_q1.units)
        import math
        truncated_mag = float(math.trunc(pint_q1.magnitude / pint_q2_converted.magnitude))
        # Preserve the left operand's unit
        ureg = _get_ureg()
        truncated = truncated_mag * pint_q1.units
        return _format_quantity(truncated)
    except (DimensionalityError, Exception) as e:
        _logger.warning("UDF quantityTruncatedDivide failed: %s", e)
        return None


def quantityModulo(q1_json: str | None, q2_json: str | None) -> str | None:
    """Modulo of two quantities (CQL §16.6).

    x mod y = x - y * (x div y). Division by zero returns null.
    """
    q1_dict = _parse_quantity(q1_json)
    q2_dict = _parse_quantity(q2_json)
    if not q1_dict or not q2_dict:
        return None
    pint_q1 = _quantity_to_pint(q1_dict)
    pint_q2 = _quantity_to_pint(q2_dict)
    if pint_q1 is None or pint_q2 is None:
        return None
    try:
        if pint_q2.magnitude == 0:
            return None  # CQL §16.6: modulo by zero → null
        # CQL modulo: x - y * trunc(x/y)
        import math
        pint_q2_converted = pint_q2.to(pint_q1.units)
        if pint_q2_converted.magnitude == 0:
            return None
        trunc_q = math.trunc(pint_q1.magnitude / pint_q2_converted.magnitude)
        result = pint_q1 - pint_q2_converted * trunc_q
        return _format_quantity(result)
    except Exception as e:
        _logger.warning("UDF quantityModulo failed: %s", e)
        return None


def toQuantity(s) -> str | None:
    """CQL §22.31: ToQuantity — parse string like ``5.5 'cm'`` to Quantity JSON."""
    if s is None:
        return None
    if isinstance(s, bool):
        return None
    if isinstance(s, (int, float, Decimal)):
        return _format_cql_quantity(s)
    s = str(s)
    if s.strip().startswith("{"):
        # CQL 1.5 Appendix B §ToQuantity (Table 9-E): a Ratio input is
        # converted by dividing numerator by denominator; a Quantity input is
        # the identity conversion ("the quantity itself").
        ratio_result = _quantity_from_ratio_json(s)
        if ratio_result is not None:
            return ratio_result
        return _quantity_identity_from_json(s)
    import re
    # Match the CQL ToQuantity string grammar: (+|-)?#0(.0#)?('<unit>')?
    # CQL 1.5 Appendix B §ToQuantity: the unit designator is "a valid,
    # case-sensitive UCUM unit of measure or calendar duration keyword,
    # singular or plural. Spaces are allowed between the quantity value and
    # the unit designator." Table 9-G additionally requires ToString output
    # (`4 days`, i.e. a bare calendar keyword) to be round-trippable, so a
    # bare calendar duration keyword is a valid unit designator, while bare
    # UCUM units are not (they must appear as a quoted string literal).
    number = r"[+-]?\d+(?:\.\d+)?"
    m = re.match(rf"^({number})(?:\s*(?:'([^']+)'|(\S+)))?$", s)
    if not m:
        return None
    unit = m.group(2) or m.group(3) or "1"
    if m.group(3) is not None and unit not in _CQL_CALENDAR_DURATION_UNITS:
        return None
    return _format_cql_quantity(m.group(1), unit)


def toConcept(code_json: str | None) -> str | None:
    """CQL §22.30: ToConcept — wrap a Code in a Concept."""
    data = _load_clinical_json(code_json)
    if isinstance(data, dict):
        code = _normalize_code_object(data)
        if code is None:
            return None
        concept = {"codes": [code]}
        if code.get("display") is not None:
            concept["display"] = code["display"]
        return orjson.dumps(concept).decode("utf-8")
    if isinstance(data, list):
        normalized = []
        for item in data:
            if isinstance(item, str):
                item = _load_clinical_json(item)
            code = _normalize_code_object(item)
            if code is None:
                return None
            normalized.append(code)
        return orjson.dumps({"codes": normalized}).decode("utf-8")
    return None


def _load_clinical_json(value):
    if value is None:
        return None
    if isinstance(value, bytes):
        value = value.decode("utf-8")
    if isinstance(value, str):
        try:
            return orjson.loads(value)
        except JSONDecodeError:
            try:
                parsed = _ast.literal_eval(value)
            except (SyntaxError, ValueError):
                return None
            if isinstance(parsed, (dict, list)):
                return parsed
            return None
    return value


def _normalize_code_object(value) -> dict | None:
    """Return a CQL Code-shaped object, rejecting Quantity lookalikes."""
    data = _load_clinical_json(value)
    if not isinstance(data, dict):
        return None
    code = data.get("code")
    if code is None:
        return None
    if "value" in data:
        return None
    result = {"code": code}
    system = data.get("system", data.get("codesystem"))
    if system is not None:
        result["system"] = system
    version = data.get("version")
    if version is not None:
        result["version"] = version
    display = data.get("display")
    if display is not None:
        result["display"] = display
    return result


def toConceptFromList(codes: list[str] | None) -> str | None:
    """CQL convert List<Code> to Concept."""
    if codes is None:
        return None
    normalized = []
    for item in codes:
        code = _normalize_code_object(item)
        if code is None:
            return None
        normalized.append(code)
    return orjson.dumps({"codes": normalized}).decode("utf-8")


def conceptToListCode(concept_json: str | None) -> list[str] | None:
    """CQL convert Concept to List<Code>."""
    data = _load_clinical_json(concept_json)
    if not isinstance(data, dict):
        return None
    raw_codes = data.get("codes")
    if raw_codes is None:
        raw_codes = data.get("coding")
    if not isinstance(raw_codes, list):
        return None

    result = []
    for item in raw_codes:
        code = _normalize_code_object(item)
        if code is None:
            return None
        result.append(orjson.dumps(code).decode("utf-8"))
    return result
# ========================================
# Registration
# ========================================


def registerQuantityUdfs(con: "duckdb.DuckDBPyConnection") -> None:
    """Register all quantity UDFs."""
    _require_ureg()
    con.create_function("parseQuantity", parseQuantity, null_handling="special")
    con.create_function("parse_quantity", parseQuantity, null_handling="special")  # Alias with snake_case
    con.create_function("quantityValue", quantityValue, null_handling="special")
    con.create_function("quantity_value", quantityValue, null_handling="special")  # Alias with snake_case
    con.create_function("quantityUnit", quantityUnit, null_handling="special")
    con.create_function("quantity_unit", quantityUnit, null_handling="special")  # Alias with snake_case
    con.create_function("quantityCompare", quantityCompare, null_handling="special")
    con.create_function("quantity_compare", quantityCompare, null_handling="special")  # Alias with snake_case
    con.create_function("quantityAdd", quantityAdd, null_handling="special")
    con.create_function("quantity_add", quantityAdd, null_handling="special")  # Alias with snake_case
    con.create_function("quantitySubtract", quantitySubtract, null_handling="special")
    con.create_function("quantity_subtract", quantitySubtract, null_handling="special")  # Alias with snake_case
    con.create_function("quantityConvert", quantityConvert, null_handling="special")
    con.create_function("quantity_convert", quantityConvert, null_handling="special")  # Alias with snake_case
    con.create_function("quantityNegate", quantityNegate, null_handling="special")
    con.create_function("quantityAbs", quantityAbs, null_handling="special")
    con.create_function("quantityMultiply", quantityMultiply, null_handling="special")
    con.create_function("quantityDivide", quantityDivide, null_handling="special")
    con.create_function("quantityTruncatedDivide", quantityTruncatedDivide, null_handling="special")
    con.create_function("quantityModulo", quantityModulo, null_handling="special")
    con.create_function("ToQuantity", toQuantity, return_type="VARCHAR", null_handling="special")
    to_concept_exists = False
    try:
        to_concept_exists = con.execute(
            """
            SELECT 1
            FROM duckdb_functions()
            WHERE lower(function_name) = 'toconcept'
            LIMIT 1
            """
        ).fetchone() is not None
    except Exception:
        to_concept_exists = False
    if not to_concept_exists:
        con.create_function(
            "__fhir4ds_py_ToConcept",
            toConcept,
            parameters=["VARCHAR"],
            return_type="VARCHAR",
            null_handling="special",
        )
        con.execute(
            'CREATE OR REPLACE MACRO ToConcept(arg) AS "__fhir4ds_py_ToConcept"(CAST(arg AS VARCHAR))'
        )
    con.create_function(
        "ToConceptFromList",
        toConceptFromList,
        parameters=["VARCHAR[]"],
        return_type="VARCHAR",
        null_handling="special",
    )
    con.create_function(
        "ConceptToListCode",
        conceptToListCode,
        parameters=["VARCHAR"],
        return_type="VARCHAR[]",
        null_handling="special",
    )


__all__ = [
    "registerQuantityUdfs",
    "parseQuantity",
    "quantityValue",
    "quantityUnit",
    "quantityCompare",
    "quantityAdd",
    "quantitySubtract",
    "quantityConvert",
    "quantityNegate",
    "quantityAbs",
    "quantityMultiply",
    "quantityDivide",
    "quantityTruncatedDivide",
    "quantityModulo",
    "toConceptFromList",
    "conceptToListCode",
    "is_valid_quantity_object",
]
