"""
This file holds code to handle the FHIRPath collection functions.
"""

import logging

from ...engine.nodes import FP_DateTime, FP_Time, FP_Date, ResourceNode
from ...engine.util import get_data
from ...engine.errors import FHIRPathError

_logger = logging.getLogger(__name__)


class DescendingSortMarker:
    """Wrapper to indicate descending sort order for non-numeric values."""
    def __init__(self, value):
        self.value = value

    def __repr__(self):
        return f"DescendingSortMarker({self.value!r})"


def sort_fn(ctx, coll, *exprs):
    """
    Sorts a collection of values.

    Supports sorting with optional expression parameters:
    - sort() - natural ordering
    - sort($this) - sort by the value itself (ascending)
    - sort(-$this) - sort by negation (descending)
    - sort(-family, -given.first()) - multiple sort criteria

    For numbers and strings, uses natural ordering.
    For dates/times, uses date/time comparison.

    Examples:
    - (3 | 1 | 2).sort() -> [1, 2, 3]
    - ('c' | 'b' | 'a').sort() -> ['a', 'b', 'c']
    """
    if not coll or len(coll) == 0:
        return []

    def get_sort_key(item):
        """Extract a comparable value from an item."""
        data = get_data(item)

        # Handle FP_DateTime and FP_Time by converting to comparable value
        if isinstance(data, (FP_DateTime, FP_Time)):
            return (0, data._getDateTimeInt() if data._getDateTimeInt() is not None else 0)
        # Handle ResourceNode by extracting data
        if isinstance(data, ResourceNode):
            data = data.data
        # Handle numbers and strings - they sort naturally
        return (1, data)

    def compare_values(a, b):
        """Compare two values, returning -1, 0, or 1."""
        data_a = get_data(a)
        data_b = get_data(b)

        # Handle ResourceNode
        if isinstance(data_a, ResourceNode):
            data_a = data_a.data
        if isinstance(data_b, ResourceNode):
            data_b = data_b.data

        # Handle FP_DateTime and FP_Time
        if isinstance(data_a, (FP_DateTime, FP_Time)) and isinstance(data_b, (FP_DateTime, FP_Time)):
            int_a = data_a._getDateTimeInt() if data_a._getDateTimeInt() is not None else 0
            int_b = data_b._getDateTimeInt() if data_b._getDateTimeInt() is not None else 0
            if int_a < int_b:
                return -1
            elif int_a > int_b:
                return 1
            return 0

        # Try direct comparison
        try:
            if data_a < data_b:
                return -1
            elif data_a > data_b:
                return 1
            return 0
        except TypeError:
            # If comparison fails, use string representation
            str_a = str(data_a)
            str_b = str(data_b)
            if str_a < str_b:
                return -1
            elif str_a > str_b:
                return 1
            return 0

    # If no expression parameters, do simple sort
    if not exprs or len(exprs) == 0:
        # Use a stable sort with custom comparison
        try:
            return sorted(coll, key=get_sort_key)
        except TypeError:
            # Fallback for uncomparable types - use string comparison
            return sorted(coll, key=lambda x: str(get_data(x)))

    # Sort with expression parameters
    # Each expression is a lambda that can be called with an item to get the sort key
    # A negative sign prefix (detected during parsing) indicates descending order

    def multi_sort_key(item):
        """Generate a sort key tuple for multiple criteria."""
        keys = []
        for expr in exprs:
            if callable(expr):
                # Evaluate the expression on the item
                result = expr(item)
                # Get the first value if it's a list
                if isinstance(result, list) and len(result) > 0:
                    result = result[0]
                elif isinstance(result, list):
                    result = None

                # Extract data from ResourceNode
                result = get_data(result)

                # For descending sort, we need to negate or reverse
                # The expression result should already be wrapped appropriately
                keys.append(result)
            else:
                keys.append(expr)
        return keys

    # For multiple sort criteria, we need to handle descending order
    # In FHIRPath, -$this means descending, which is handled by negating numbers
    # or by using a custom comparison

    # Create a list of (index, item) pairs to maintain stability
    indexed = list(enumerate(coll))

    def compare_with_expr(a_tuple, b_tuple):
        """Compare two items using expression criteria."""
        idx_a, a = a_tuple
        idx_b, b = b_tuple

        for expr in exprs:
            if not callable(expr):
                continue

            # Evaluate expressions
            val_a = expr(a)
            val_b = expr(b)

            # Check for DescendingSortMarker (for descending sort of non-numeric values)
            descending_a = isinstance(val_a, list) and len(val_a) > 0 and isinstance(val_a[0], DescendingSortMarker)
            descending_b = isinstance(val_b, list) and len(val_b) > 0 and isinstance(val_b[0], DescendingSortMarker)
            is_descending = descending_a or descending_b

            if descending_a:
                val_a = val_a[0].value
            if descending_b:
                val_b = val_b[0].value

            # Get first value if list
            if isinstance(val_a, list) and len(val_a) > 0:
                val_a = val_a[0]
            elif isinstance(val_a, list):
                val_a = None
            if isinstance(val_b, list) and len(val_b) > 0:
                val_b = val_b[0]
            elif isinstance(val_b, list):
                val_b = None

            # Extract data
            val_a = get_data(val_a)
            val_b = get_data(val_b)

            # Handle None values
            if val_a is None and val_b is None:
                continue
            if val_a is None:
                # In descending order, None sorts first; in ascending, None sorts last
                return 1 if not is_descending else -1
            if val_b is None:
                return -1 if not is_descending else 1

            # Compare
            try:
                if val_a < val_b:
                    cmp_result = -1
                elif val_a > val_b:
                    cmp_result = 1
                else:
                    cmp_result = 0
            except TypeError:
                # Fallback to string comparison
                str_a = str(val_a)
                str_b = str(val_b)
                if str_a < str_b:
                    cmp_result = -1
                elif str_a > str_b:
                    cmp_result = 1
                else:
                    cmp_result = 0

            if cmp_result != 0:
                # Reverse comparison for descending order
                return -cmp_result if is_descending else cmp_result

        # All criteria equal, maintain original order (stable sort)
        return idx_a - idx_b

    # Sort using the comparison function
    from functools import cmp_to_key
    sorted_indexed = sorted(indexed, key=cmp_to_key(compare_with_expr))

    return [item for idx, item in sorted_indexed]


def comparable(ctx, a, b):
    """
    Returns true if the values can be compared.

    Two values are comparable if:
    - Both are numbers (int, float, Decimal)
    - Both are strings
    - Both are boolean
    - Both are date/time types (FP_DateTime, FP_Time)
    - Both are Quantities with comparable units

    Examples:
    - 1.comparable(2) -> true
    - 1.comparable('a') -> false
    - @2014.comparable(@2015) -> true
    - 1 'cm'.comparable(1 '[in_i]') -> true (both are lengths)
    """
    if not a or len(a) == 0:
        return []
    if not b or len(b) == 0:
        return []

    val_a = a[0]
    val_b = b[0]

    # Get actual data from ResourceNode if needed
    from ...engine.util import get_data
    val_a = get_data(val_a)
    val_b = get_data(val_b)

    # Check if both are numbers
    def is_number(v):
        from decimal import Decimal
        return isinstance(v, (int, float, Decimal)) and not isinstance(v, bool)

    # Check if both are date/time types
    def is_datetime(v):
        return isinstance(v, (FP_DateTime, FP_Time, FP_Date))

    # Both numbers
    if is_number(val_a) and is_number(val_b):
        return [True]

    # Both strings
    if isinstance(val_a, str) and isinstance(val_b, str):
        return [True]

    # Both booleans
    if isinstance(val_a, bool) and isinstance(val_b, bool):
        return [True]

    # Both date/time types
    if is_datetime(val_a) and is_datetime(val_b):
        # Both must be the same type (both DateTime, both Time, or both Date)
        if type(val_a) == type(val_b):
            return [True]
        return [False]

    # Both FP_Quantity - check if units are comparable
    from ...engine.nodes import FP_Quantity
    if isinstance(val_a, FP_Quantity) and isinstance(val_b, FP_Quantity):
        # Quantities are comparable if they have the same unit dimension
        # For simplicity, we check if units can be converted between each other
        # UCUM units are comparable if they have the same base dimension
        try:
            # Try to compare by attempting unit conversion
            # If units share the same base, they are comparable
            unit_a = val_a.unit
            unit_b = val_b.unit

            # Simple check: if units are the same, they're comparable
            if unit_a == unit_b:
                return [True]

            # Check for common comparable unit patterns
            # Length units: m, cm, mm, [in_i], [ft_i], etc.
            # Time units: s, min, h, d, wk, mo, a
            # Mass units: g, kg, mg, [oz_av], [lb_av]

            length_units = {'m', 'cm', 'mm', 'km', '[in_i]', '[ft_i]', '[yd_i]', '[mi_i]'}
            time_units = {'s', 'min', 'h', 'd', 'wk', 'mo', 'a', 'ms'}
            mass_units = {'g', 'kg', 'mg', '[oz_av]', '[lb_av]'}

            def get_unit_category(unit):
                unit_base = unit.strip("'").split("'")[0] if "'" in unit else unit
                if unit_base in length_units:
                    return 'length'
                if unit_base in time_units:
                    return 'time'
                if unit_base in mass_units:
                    return 'mass'
                return None

            cat_a = get_unit_category(unit_a)
            cat_b = get_unit_category(unit_b)

            if cat_a and cat_b and cat_a == cat_b:
                return [True]

            return [False]
        except Exception as e:
            _logger.warning("Quantity comparability check failed for units '%s' and '%s': %s", val_a.unit, val_b.unit, e)
            return [False]

    return [False]


def contains_impl(ctx, a, b):
    # b is assumed to have one element and it tests whether b[0] is in a
    if len(b) == 0:
        return True

    for i in range(0, len(a)):
        if a[i] == b[0]:
            return True

    return False


def contains(ctx, a, b):
    if len(b) == 0:
        return []
    if len(a) == 0:
        return False
    if len(b) > 1:
        raise FHIRPathError("Expected singleton on right side of contains, got " + str(b))

    return contains_impl(ctx, a, b)


def inn(ctx, a, b):
    if len(a) == 0:
        return []
    if len(b) == 0:
        return False
    if len(a) > 1:
        raise FHIRPathError("Expected singleton on right side of in, got " + str(b))

    return contains_impl(ctx, b, a)
