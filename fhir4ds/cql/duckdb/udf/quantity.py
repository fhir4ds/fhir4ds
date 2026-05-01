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


def _parse_quantity(value: str | None) -> dict | None:
    """Parse FHIR Quantity JSON to dict."""
    if not value:
        return None
    try:
        data = orjson.loads(value)
        if not isinstance(data, dict):
            _logger.warning("_parse_quantity expected object, got %s", type(data).__name__)
            return None
        code = data.get("code") or data.get("unit")
        result = {
            "value": data.get("value"),
            "code": code,
            "system": data.get("system", "http://unitsofmeasure.org"),
        }
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
    if not q_dict or q_dict.get("value") is None or not q_dict.get("code"):
        return None

    ureg = _get_ureg()
    if ureg is None:
        return None

    try:
        ucum_code = q_dict["code"]
        value = float(q_dict["value"])
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
    return orjson.dumps(q).decode("utf-8")


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


def quantityCompare(q1_json: str | None, q2_json: str | None, op: str) -> bool | None:
    """Compare two quantities with unit-aware comparison.

    Supports operators: >, <, >=, <=, ==, !=

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
        # Convert q2 to q1's units and add
        pint_q2_converted = pint_q2.to(pint_q1.units)
        result = pint_q1 + pint_q2_converted
        return _format_quantity(result)
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
        return _format_quantity(result)
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

    CQL Spec §16.8: Negation.
    """
    q_dict = _parse_quantity(q_json)
    if not q_dict:
        return None
    pint_q = _quantity_to_pint(q_dict)
    if pint_q is None:
        return None
    try:
        result = -pint_q
        return _format_quantity(result)
    except Exception as e:
        _logger.warning("UDF quantityNegate failed: %s", e)
        return None


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
        quotient = pint_q1 / pint_q2
        trunc_q = math.trunc(quotient.magnitude)
        pint_q2_converted = pint_q2.to(pint_q1.units)
        result = pint_q1 - pint_q2_converted * trunc_q
        return _format_quantity(result)
    except Exception as e:
        _logger.warning("UDF quantityModulo failed: %s", e)
        return None


def toQuantity(s: str | None) -> str | None:
    """CQL §22.31: ToQuantity — parse string like ``5.5 'cm'`` to Quantity JSON."""
    if s is None:
        return None
    import re
    # Match: number optionally followed by unit in single quotes
    m = re.match(r"^\s*(-?[\d.]+)\s*'([^']+)'\s*$", s)
    if not m:
        # Try plain number without unit
        m = re.match(r"^\s*(-?[\d.]+)\s*$", s)
        if m:
            return orjson.dumps({"value": float(m.group(1)), "unit": "1", "code": "1",
                                 "system": "http://unitsofmeasure.org"}).decode("utf-8")
        return None
    value = float(m.group(1))
    unit = m.group(2)
    return orjson.dumps({"value": value, "unit": unit, "code": unit,
                         "system": "http://unitsofmeasure.org"}).decode("utf-8")


def toConcept(code_json: str | None) -> str | None:
    """CQL §22.30: ToConcept — wrap a Code in a Concept."""
    if code_json is None:
        return None
    try:
        code = orjson.loads(code_json)
        concept = {"codes": [code] if isinstance(code, dict) else code}
        return orjson.dumps(concept).decode("utf-8")
    except Exception as e:
        _logger.debug("Unexpected error in UDF toConcept: %s", e)
        return None
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
    con.create_function("ToQuantity", toQuantity, null_handling="special")
    con.create_function("ToConcept", toConcept, null_handling="special")


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
]
