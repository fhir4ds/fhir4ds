"""
FHIRPath Type System & Conversion Functions

Implements FHIRPath type operators and conversion functions as defined in:
https://hl7.org/fhirpath/#types-and-reflection

Type Operators:
- is Type: Type checking (e.g., value is Quantity)
- as Type: Type casting (e.g., value as Quantity)

Type Functions:
- ofType(type): Filter collection by type
- type(): Get FHIRPath type name

Conversion Functions:
- toString(): Convert to string
- toInteger(): Convert to integer
- toDecimal(): Convert to decimal
- toDateTime(): Convert to datetime
- toDate(): Convert to date
- toTime(): Convert to time
- toBoolean(): Convert to boolean
- toQuantity(unit?): Convert to quantity
"""

from __future__ import annotations

import re
from datetime import date, datetime, time
from decimal import Decimal
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Sequence

from ...engine import nodes
from ..types import FHIRPathType, infer_fhirpath_type


# FHIRPath type name mappings
TYPE_NAME_MAP = {
    FHIRPathType.BOOLEAN: "boolean",
    FHIRPathType.INTEGER: "integer",
    FHIRPathType.DECIMAL: "decimal",
    FHIRPathType.STRING: "string",
    FHIRPathType.DATE: "date",
    FHIRPathType.DATETIME: "dateTime",
    FHIRPathType.TIME: "time",
    FHIRPathType.QUANTITY: "Quantity",
    FHIRPathType.CODING: "Coding",
    FHIRPathType.CODEABLE_CONCEPT: "CodeableConcept",
    FHIRPathType.RESOURCE: "Resource",
    FHIRPathType.COLLECTION: "Collection",
    FHIRPathType.ANY: "any",
}

# Reverse mapping for type name resolution
NAME_TO_TYPE_MAP = {v.lower(): k for k, v in TYPE_NAME_MAP.items()}

# Additional type aliases
TYPE_ALIASES = {
    "int": FHIRPathType.INTEGER,
    "num": FHIRPathType.DECIMAL,
    "str": FHIRPathType.STRING,
    "bool": FHIRPathType.BOOLEAN,
    "datetime": FHIRPathType.DATETIME,
    "qty": FHIRPathType.QUANTITY,
}

# Date/time format patterns for parsing
DATE_PATTERNS = [
    (re.compile(r'^\d{4}-\d{2}-\d{2}$'), '%Y-%m-%d'),
    (re.compile(r'^\d{4}-\d{2}$'), '%Y-%m'),  # Partial date
    (re.compile(r'^\d{4}$'), '%Y'),  # Year only
]

DATETIME_PATTERNS = [
    (re.compile(r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:\d{2})?$'), None),  # ISO format
    (re.compile(r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}$'), '%Y-%m-%dT%H:%M:%S'),
    (re.compile(r'^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$'), '%Y-%m-%d %H:%M:%S'),
]

TIME_PATTERNS = [
    (re.compile(r'^\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:\d{2})?$'), None),  # ISO format
    (re.compile(r'^\d{2}:\d{2}:\d{2}$'), '%H:%M:%S'),
    (re.compile(r'^\d{2}:\d{2}$'), '%H:%M'),
]

DECIMAL_PATTERN = re.compile(r'^[+-]?\d+(\.\d+)?$')
DATE_STRING_PATTERN = re.compile(r'^\d{4}-\d{2}-\d{2}$')
DATETIME_STRING_PATTERN = re.compile(
    r'^\d{4}-\d{2}-\d{2}T\d{2}(:\d{2})?(:\d{2}(\.\d+)?)?(Z|[+-]\d{2}:\d{2})?$'
)
TIME_STRING_PATTERN = re.compile(r'^\d{2}:\d{2}(:\d{2}(\.\d+)?)?$')
QUANTITY_STRING_PATTERN = re.compile(r"^([+-]?\d+(\.\d+)?)\s*(('[^']+')|([a-zA-Z]+))?$")


def resolve_type_name(type_name: str) -> FHIRPathType | None:
    """
    Resolve a type name string to a FHIRPathType.

    Args:
        type_name: The type name (e.g., "Quantity", "integer", "String").

    Returns:
        The corresponding FHIRPathType, or None if not recognized.
    """
    # Check direct mapping (case-insensitive)
    normalized = type_name.lower().strip()
    if normalized in NAME_TO_TYPE_MAP:
        return NAME_TO_TYPE_MAP[normalized]

    # Check aliases
    if normalized in TYPE_ALIASES:
        return TYPE_ALIASES[normalized]

    return None


def get_type_name(value: Any) -> str:
    """
    Get the FHIRPath type name for a value.

    Args:
        value: Any Python value.

    Returns:
        The FHIRPath type name string.
    """
    fhir_type = infer_fhirpath_type(value)
    return TYPE_NAME_MAP.get(fhir_type, "any")


def is_type(value: Any, type_name: str) -> bool:
    """
    Check if a value is of a specific FHIRPath type (is operator).

    Implements the FHIRPath 'is' operator which returns true if the input
    is of the specified type.

    Args:
        value: The value to check.
        type_name: The type name to check against.

    Returns:
        True if value is of the specified type, False otherwise.

    FHIRPath Semantics:
        - Empty collection -> false
        - Type matching is by FHIRPath type system, not Python types
        - Type names are case-insensitive
    """
    if value is None:
        return False

    # Resolve the target type
    target_type = resolve_type_name(type_name)
    if target_type is None:
        return False

    # Get the actual type of the value
    actual_type = infer_fhirpath_type(value)

    # Check for type match
    if actual_type == target_type:
        return True

    # Special case: ANY matches everything
    if target_type == FHIRPathType.ANY:
        return True

    # Special case: integer is compatible with decimal
    if actual_type == FHIRPathType.INTEGER and target_type == FHIRPathType.DECIMAL:
        return True

    # Check for Quantity type (dict with value and unit)
    if target_type == FHIRPathType.QUANTITY:
        if isinstance(value, dict):
            return 'value' in value and ('unit' in value or 'system' in value)
        return False

    # Check for Coding type
    if target_type == FHIRPathType.CODING:
        if isinstance(value, dict):
            return 'system' in value or 'code' in value
        return False

    # Check for CodeableConcept type
    if target_type == FHIRPathType.CODEABLE_CONCEPT:
        if isinstance(value, dict):
            return 'coding' in value or 'text' in value
        return False

    return False


def as_type(value: Any, type_name: str) -> Any:
    """
    Cast a value to a specific FHIRPath type (as operator).

    Implements the FHIRPath 'as' operator which returns the value if it
    is of the specified type, or empty ({}) if not.

    Args:
        value: The value to cast.
        type_name: The type name to cast to.

    Returns:
        The value if it matches the type, or None (empty) if not.

    FHIRPath Semantics:
        - Empty collection -> empty
        - Type mismatch -> empty ({})
        - Type names are case-insensitive
    """
    if value is None:
        return None

    if is_type(value, type_name):
        return value

    return None


def of_type(collection: list[Any], type_name: str) -> list[Any]:
    """
    Filter a collection to only include items of a specific type.

    Implements the FHIRPath ofType() function which returns only the
    items in the collection that are of the specified type.

    Args:
        collection: A list of values.
        type_name: The type name to filter by.

    Returns:
        A list containing only items of the specified type.

    FHIRPath Semantics:
        - Empty collection -> empty
        - Each item is checked individually
    """
    if not collection:
        return []

    return [item for item in collection if is_type(item, type_name)]


def type_of(value: Any) -> str | None:
    """
    Get the FHIRPath type name of a value.

    Implements the FHIRPath type() function which returns the type name
    of the input.

    Args:
        value: The value to get the type of.

    Returns:
        The FHIRPath type name, or None for empty collection.

    FHIRPath Semantics:
        - Empty collection -> empty
        - Singleton -> type name
        - Collection with multiple items -> error (should not happen at item level)
    """
    if value is None:
        return None

    return get_type_name(value)


def to_string(value: Any) -> str | None:
    """
    Convert a value to string.

    Implements the FHIRPath toString() function.

    Args:
        value: The value to convert.

    Returns:
        The string representation, or None if conversion fails.

    FHIRPath Semantics:
        - Empty collection -> empty
        - String -> unchanged
        - Boolean -> "true" or "false"
        - Integer/Decimal -> string representation
        - Date/DateTime/Time -> ISO format string
        - Other -> JSON representation
    """
    if value is None:
        return None

    if isinstance(value, bool):
        return "true" if value else "false"

    if isinstance(value, (int, float, Decimal)):
        # Handle special float values
        if isinstance(value, float):
            if value != value:  # NaN
                return None
            if value == float('inf'):
                return None
            if value == float('-inf'):
                return None
        return str(value)

    if isinstance(value, str):
        return value

    if isinstance(value, date):
        return value.isoformat()

    if isinstance(value, datetime):
        return value.isoformat()

    if isinstance(value, time):
        return value.isoformat()

    if isinstance(value, dict):
        # For Quantity, use special format
        if 'value' in value and ('unit' in value or 'code' in value):
            v = value.get('value')
            u = value.get('unit') or value.get('code', '')
            return f"{v} '{u}'"
        # For other dicts, return JSON
        import json
        try:
            return json.dumps(value)
        except (TypeError, ValueError):
            return str(value)

    if isinstance(value, list):
        import json
        try:
            return json.dumps(value)
        except (TypeError, ValueError):
            return str(value)

    return str(value)


def to_integer(value: Any) -> int | None:
    """
    Convert a value to integer.

    Implements the FHIRPath toInteger() function.

    Args:
        value: The value to convert.

    Returns:
        The integer value, or None if conversion fails.

    FHIRPath Semantics:
        - Empty collection -> empty
        - Integer -> unchanged
        - String -> parsed if valid integer representation
        - Boolean -> 1 or 0
        - Other types -> empty
    """
    if value is None:
        return None

    if isinstance(value, bool):
        return 1 if value else 0

    if isinstance(value, int):
        return value if -2147483648 <= value <= 2147483647 else None

    if isinstance(value, str):
        if not value:
            return None

        if re.fullmatch(r"[+-]?\d+", value) is None:
            return None
        int_value = int(value)
        return int_value if -2147483648 <= int_value <= 2147483647 else None

    return None


def to_decimal(value: Any) -> Decimal | None:
    """
    Convert a value to decimal.

    Implements the FHIRPath toDecimal() function.

    Args:
        value: The value to convert.

    Returns:
        The decimal value, or None if conversion fails.

    FHIRPath Semantics:
        - Empty collection -> empty
        - Integer/Decimal -> unchanged
        - String -> parsed if valid decimal representation
        - Boolean -> 1.0 or 0.0
        - Other types -> empty
    """
    if value is None:
        return None

    if isinstance(value, bool):
        return Decimal('1.0') if value else Decimal('0.0')

    if isinstance(value, int):
        return Decimal(value)

    if isinstance(value, float):
        # Check for special values
        if value != value or value == float('inf') or value == float('-inf'):
            return None
        return Decimal(str(value))

    if isinstance(value, Decimal):
        return value

    if isinstance(value, str):
        if DECIMAL_PATTERN.fullmatch(value) is None:
            return None
        return Decimal(value)

    return None


def to_date_time(value: Any) -> datetime | None:
    """
    Convert a value to datetime.

    Implements the FHIRPath toDateTime() function.

    Args:
        value: The value to convert.

    Returns:
        The datetime value, or None if conversion fails.

    FHIRPath Semantics:
        - Empty collection -> empty
        - DateTime -> unchanged
        - Date -> datetime at start of day
        - String -> parsed if valid datetime representation
        - Other types -> empty
    """
    if value is None:
        return None

    if isinstance(value, datetime):
        return value

    if isinstance(value, date):
        return datetime.combine(value, time(0, 0, 0))

    if isinstance(value, str):
        value = value.strip()
        if not value:
            return None

        # Try ISO format first (Python 3.7+)
        try:
            # Handle various ISO formats
            # Replace Z with +00:00 for fromisoformat compatibility
            iso_value = value.replace('Z', '+00:00')
            return datetime.fromisoformat(iso_value)
        except ValueError:
            pass

        # Try explicit formats
        for pattern, fmt in DATETIME_PATTERNS:
            if pattern.match(value):
                if fmt:
                    try:
                        return datetime.strptime(value, fmt)
                    except ValueError:
                        continue

        # Try date + time formats
        for _, date_fmt in DATE_PATTERNS:
            try:
                parsed_date = datetime.strptime(value, date_fmt)
                return datetime.combine(parsed_date.date(), time(0, 0, 0))
            except ValueError:
                continue

        return None

    return None


def to_date(value: Any) -> date | None:
    """
    Convert a value to date.

    Implements the FHIRPath toDate() function.

    Args:
        value: The value to convert.

    Returns:
        The date value, or None if conversion fails.

    FHIRPath Semantics:
        - Empty collection -> empty
        - Date -> unchanged
        - DateTime -> date portion only
        - String -> parsed if valid date representation
        - Other types -> empty
    """
    if value is None:
        return None

    if isinstance(value, date):
        if isinstance(value, datetime):
            return value.date()
        return value

    if isinstance(value, str):
        if not value or value != value.strip():
            return None

        if DATE_STRING_PATTERN.fullmatch(value):
            try:
                return datetime.strptime(value, "%Y-%m-%d").date()
            except ValueError:
                return None

        if DATETIME_STRING_PATTERN.fullmatch(value):
            date_time_value = nodes.FP_DateTime(value)
            if date_time_value:
                return datetime.strptime(str(date_time_value)[:10], "%Y-%m-%d").date()
            return None

        return None

    return None


def to_time(value: Any) -> time | None:
    """
    Convert a value to time.

    Implements the FHIRPath toTime() function.

    Args:
        value: The value to convert.

    Returns:
        The time value, or None if conversion fails.

    FHIRPath Semantics:
        - Empty collection -> empty
        - Time -> unchanged
        - DateTime -> time portion only
        - String -> parsed if valid time representation
        - Other types -> empty
    """
    if value is None:
        return None

    if isinstance(value, time):
        return value

    if isinstance(value, datetime):
        return value.time()

    if isinstance(value, str):
        if not value or value != value.strip():
            return None

        if 'T' in value:
            if not DATETIME_STRING_PATTERN.fullmatch(value):
                return None
            time_part = value.split('T', 1)[1]
        else:
            time_part = value

        if time_part.endswith('Z') or re.search(r'[+-]\d{2}:\d{2}$', time_part):
            return None

        if not TIME_STRING_PATTERN.fullmatch(time_part):
            return None

        try:
            return time.fromisoformat(time_part)
        except ValueError:
            return None

        return None

    return None


def to_boolean(value: Any) -> bool | None:
    """
    Convert a value to boolean.

    Implements the FHIRPath toBoolean() function.

    Args:
        value: The value to convert.

    Returns:
        The boolean value, or None if conversion fails.

    FHIRPath Semantics:
        - Empty collection -> empty
        - Boolean -> unchanged
        - Integer/Decimal -> true for 1/1.0, false for 0/0.0
        - String -> one of the specification-defined boolean representations
        - Other types -> empty
    """
    if value is None:
        return None

    if isinstance(value, bool):
        return value

    if isinstance(value, (int, float, Decimal)):
        if value == 1 or value == Decimal("1") or value == 1.0:
            return True
        if value == 0 or value == Decimal("0") or value == 0.0:
            return False
        return None

    if isinstance(value, str):
        value_lower = value.lower()
        if not value_lower:
            return None

        if value_lower in {"true", "t", "yes", "y", "1", "1.0"}:
            return True
        if value_lower in {"false", "f", "no", "n", "0", "0.0"}:
            return False

        return None

    return None


def _core_quantity_unit(unit: str | None) -> str:
    if not unit:
        return "'1'"
    if unit.startswith("'") and unit.endswith("'"):
        return unit
    if nodes.FP_Quantity.timeUnitsToUCUM.get(unit):
        return unit
    return f"'{unit}'"


def _quantity_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    return value


def _quantity_dict(quantity: nodes.FP_Quantity, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    result: dict[str, Any] = {
        "value": _quantity_value(quantity.value),
        "unit": quantity.unit.strip("'"),
    }
    if extra:
        result.update(extra)
    return result


def _convert_quantity(quantity: nodes.FP_Quantity, unit: str | None) -> nodes.FP_Quantity | None:
    if not unit:
        return quantity
    target_unit = _core_quantity_unit(unit)
    if quantity.unit == target_unit:
        return quantity
    # FP-08 HISTORIAN QA-002 (2026-08-17): direct helpers follow the same
    # §5.5.7 conversion-factor table as the core engine (1 year = 365
    # days, 1 month = 30 days) — route duration pairs through the
    # toQuantity-only spec table before the metric/mass group tables.
    converted = nodes.FP_Quantity.conv_duration_to_spec(quantity.unit, quantity.value, target_unit)
    if converted is None:
        converted = nodes.FP_Quantity.conv_unit_to(quantity.unit, quantity.value, target_unit)
    return converted


def _quantity_from_string(value: str) -> nodes.FP_Quantity | None:
    match = QUANTITY_STRING_PATTERN.fullmatch(value)
    if not match:
        return None

    num_value = Decimal(match.group(1))
    quoted_unit = match.group(4)
    time_unit = match.group(5)

    if quoted_unit:
        return nodes.FP_Quantity(num_value, quoted_unit)
    if not time_unit:
        return nodes.FP_Quantity(num_value, "'1'")
    if nodes.FP_Quantity.timeUnitsToUCUM.get(time_unit) and len(time_unit) > 2:
        return nodes.FP_Quantity(num_value, time_unit)
    if nodes.FP_Quantity.timeUnitsToUCUM.get(time_unit.lower()) and len(time_unit) > 2:
        return nodes.FP_Quantity(num_value, time_unit.lower())
    if time_unit.lower() not in {u.strip("'") for u in nodes.FP_Quantity.mapUCUMCodeToTimeUnits} and not (
        nodes.FP_Quantity.timeUnitsToUCUM.get(time_unit)
        or nodes.FP_Quantity.timeUnitsToUCUM.get(time_unit.lower())
    ):
        return nodes.FP_Quantity(num_value, f"'{time_unit}'")
    return None


def to_quantity(value: Any, unit: str | None = None) -> dict | None:
    """
    Convert a value to Quantity.

    Implements the FHIRPath toQuantity() function.

    Args:
        value: The value to convert.
        unit: Optional target unit for conversion.

    Returns:
        A Quantity dict with 'value' and 'unit' keys, or None if conversion fails.

    FHIRPath Semantics:
        - Empty collection -> empty
        - Quantity -> converted to target unit if specified
        - Integer/Decimal -> Quantity with value and no unit
        - String -> parsed if valid quantity representation ("value 'unit'")
        - Other types -> empty

    Note: Unit conversion requires a UCUM implementation. This implementation
    provides basic parsing but does not perform unit conversions.
    """
    if value is None:
        return None

    if isinstance(value, dict):
        if 'value' in value:
            quantity = nodes.FP_Quantity(value.get('value'), _core_quantity_unit(value.get('unit') or value.get('code')))
            converted = _convert_quantity(quantity, unit)
            if not converted:
                return None
            extra = None
            if not unit:
                extra = {
                    key: value[key]
                    for key in ("system", "code", "comparator")
                    if key in value
                }
            return _quantity_dict(converted, extra)
        return None

    if isinstance(value, bool):
        quantity = nodes.FP_Quantity(1 if value else 0, "'1'")
        converted = _convert_quantity(quantity, unit)
        return _quantity_dict(converted) if converted else None

    if isinstance(value, (int, float, Decimal)):
        # Handle special float values
        if isinstance(value, float):
            if value != value or value == float('inf') or value == float('-inf'):
                return None

        quantity = nodes.FP_Quantity(value, "'1'")
        converted = _convert_quantity(quantity, unit)
        return _quantity_dict(converted) if converted else None

    if isinstance(value, str):
        if not value or value != value.strip():
            return None

        quantity = _quantity_from_string(value)
        if not quantity:
            return None
        converted = _convert_quantity(quantity, unit)
        return _quantity_dict(converted) if converted else None

    return None
