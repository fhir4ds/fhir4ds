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
from decimal import Decimal, InvalidOperation as DecimalInvalidOperation
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Sequence

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
        - Decimal -> truncated (toward zero)
        - String -> parsed if valid integer representation
        - Boolean -> 1 or 0
        - Other types -> empty
    """
    if value is None:
        return None

    if isinstance(value, bool):
        return 1 if value else 0

    if isinstance(value, int):
        return value

    if isinstance(value, float):
        # Check for special values
        if value != value or value == float('inf') or value == float('-inf'):
            return None
        # Truncate toward zero
        return int(value)

    if isinstance(value, Decimal):
        try:
            return int(value)
        except (ValueError, OverflowError):
            return None

    if isinstance(value, str):
        value = value.strip()
        if not value:
            return None

        # Try parsing as integer
        try:
            # Handle decimal string by truncating
            if '.' in value:
                return int(float(value))
            return int(value)
        except ValueError:
            return None

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
        return Decimal('1') if value else Decimal('0')

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
        value = value.strip()
        if not value:
            return None

        try:
            return Decimal(value)
        except DecimalInvalidOperation:
            return None

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
        value = value.strip()
        if not value:
            return None

        # Try ISO format first
        try:
            # Handle datetime strings - extract date part
            if 'T' in value:
                iso_value = value.split('T')[0]
            else:
                iso_value = value

            # Handle partial dates (e.g., "2024-01")
            parts = iso_value.split('-')
            if len(parts) >= 3:
                return date(int(parts[0]), int(parts[1]), int(parts[2]))
            elif len(parts) == 2:
                # Partial date - return None per FHIRPath spec
                return None
            elif len(parts) == 1 and len(parts[0]) == 4:
                # Year only - return None per FHIRPath spec
                return None
        except (ValueError, IndexError):
            pass

        # Try explicit formats
        for pattern, fmt in DATE_PATTERNS:
            if pattern.match(value):
                try:
                    return datetime.strptime(value, fmt).date()
                except ValueError:
                    continue

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
        value = value.strip()
        if not value:
            return None

        # Try ISO format first
        try:
            # Handle datetime strings - extract time part
            if 'T' in value:
                time_part = value.split('T')[1]
            else:
                time_part = value

            # Remove timezone for parsing
            # Handle +HH:MM or -HH:MM or Z suffix
            time_part = re.sub(r'[+-]\d{2}:\d{2}$', '', time_part)
            time_part = time_part.replace('Z', '')

            # Parse time
            return time.fromisoformat(time_part)
        except (ValueError, IndexError):
            pass

        # Try explicit formats
        for pattern, fmt in TIME_PATTERNS:
            if pattern.match(value):
                if fmt:
                    try:
                        return datetime.strptime(value, fmt).time()
                    except ValueError:
                        continue

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
        - Integer/Decimal -> true if non-zero
        - String -> "true"/"false" (case-insensitive) or conversion to number then check
        - Other types -> empty
    """
    if value is None:
        return None

    if isinstance(value, bool):
        return value

    if isinstance(value, (int, float, Decimal)):
        return bool(value)

    if isinstance(value, str):
        value_lower = value.strip().lower()
        if not value_lower:
            return None

        # Check for explicit true/false
        if value_lower == 'true':
            return True
        if value_lower == 'false':
            return False

        # Check for 1/0
        if value_lower == '1':
            return True
        if value_lower == '0':
            return False

        # Try converting to number first
        try:
            num = Decimal(value_lower)
            return bool(num)
        except DecimalInvalidOperation:
            pass

        # Check for yes/no (common extension)
        if value_lower == 'yes':
            return True
        if value_lower == 'no':
            return False

        return None

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
        # Already a Quantity-like structure
        if 'value' in value:
            result = {
                'value': value.get('value'),
                'unit': value.get('unit') or value.get('code', ''),
            }
            # Add optional fields
            if 'system' in value:
                result['system'] = value['system']
            if 'code' in value:
                result['code'] = value['code']
            if 'comparator' in value:
                result['comparator'] = value['comparator']

            # TODO: Implement unit conversion when unit parameter is provided
            if unit:
                # For now, just return the quantity as-is
                # Unit conversion would require UCUM library
                pass

            return result
        return None

    if isinstance(value, bool):
        return {
            'value': 1 if value else 0,
            'unit': unit or '',
        }

    if isinstance(value, (int, float, Decimal)):
        # Handle special float values
        if isinstance(value, float):
            if value != value or value == float('inf') or value == float('-inf'):
                return None

        return {
            'value': float(value) if isinstance(value, float) else int(value) if isinstance(value, int) else float(value),
            'unit': unit or '',
        }

    if isinstance(value, str):
        value = value.strip()
        if not value:
            return None

        # Try parsing as "value 'unit'" format
        # Pattern: number followed by optional unit in quotes or just unit
        match = re.match(
            r'^([+-]?\d+(?:\.\d+)?)\s*(?:\'([^\']+)\'|"([^"]+)"|(\S+))?$',
            value
        )
        if match:
            num_str = match.group(1)
            unit_str = match.group(2) or match.group(3) or match.group(4) or ''

            try:
                num_value = float(num_str)
                return {
                    'value': num_value,
                    'unit': unit or unit_str,
                }
            except ValueError:
                pass

        # Try parsing as just a number
        try:
            num_value = float(value)
            return {
                'value': num_value,
                'unit': unit or '',
            }
        except ValueError:
            pass

        return None

    return None
