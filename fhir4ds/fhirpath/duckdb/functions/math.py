"""
FHIRPath Math & Aggregate Functions

Implements FHIRPath mathematical operations and aggregate functions
following the FHIRPath specification.

Key FHIRPath semantics:
- Math on empty collection returns empty collection
- `1 + {}` -> `{}`
- Handle infinity and NaN appropriately
- Type coercion between Integer and Decimal
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, Any, Union

if TYPE_CHECKING:
    from collections.abc import Sequence

# Type aliases for numeric values
Numeric = Union[int, float]


# ==============================================================================
# Empty Collection Handling
# ==============================================================================


def _is_empty(value: Any) -> bool:
    """Check if a value represents an empty FHIRPath collection."""
    if value is None:
        return True
    if isinstance(value, list):
        return len(value) == 0
    if hasattr(value, 'is_empty'):
        return value.is_empty
    return False


def _to_numeric(value: Any) -> Numeric | None:
    """
    Convert a value to numeric type for FHIRPath math operations.

    FHIRPath uses Integer (int) and Decimal (float) types.
    Strings and other types are not coerced to numbers.

    Args:
        value: Any value to convert.

    Returns:
        int, float, or None if conversion not possible.
    """
    if value is None:
        return None
    if isinstance(value, bool):
        # Booleans are not numeric in FHIRPath
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return value
    return None


def _wrap_result(value: Any) -> list[Any]:
    """Wrap a result value in a list (FHIRPath collection)."""
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


# ==============================================================================
# Arithmetic Operators
# ==============================================================================


def add(left: Any, right: Any) -> list[Any]:
    """
    FHIRPath addition operator (+).

    Adds two numeric values following FHIRPath semantics:
    - Empty collection propagates: {} + x -> {}, x + {} -> {}
    - Integer + Integer -> Integer
    - Decimal + any -> Decimal

    Args:
        left: Left operand (numeric or empty).
        right: Right operand (numeric or empty).

    Returns:
        List containing the sum, or empty list if either operand is empty.

    Example:
        >>> add(1, 2)
        [3]
        >>> add(1.5, 2)
        [3.5]
        >>> add(1, [])
        []
    """
    if _is_empty(left) or _is_empty(right):
        return []

    left_num = _to_numeric(left)
    right_num = _to_numeric(right)

    if left_num is None or right_num is None:
        return []

    result = left_num + right_num

    # Preserve integer type if both operands are integers
    if isinstance(left_num, int) and isinstance(right_num, int):
        return [int(result)]

    return [result]


def subtract(left: Any, right: Any) -> list[Any]:
    """
    FHIRPath subtraction operator (-).

    Subtracts two numeric values following FHIRPath semantics:
    - Empty collection propagates: {} - x -> {}, x - {} -> {}
    - Integer - Integer -> Integer
    - Decimal - any -> Decimal

    Args:
        left: Left operand (numeric or empty).
        right: Right operand (numeric or empty).

    Returns:
        List containing the difference, or empty list if either operand is empty.

    Example:
        >>> subtract(5, 3)
        [2]
        >>> subtract(1.5, 0.5)
        [1.0]
    """
    if _is_empty(left) or _is_empty(right):
        return []

    left_num = _to_numeric(left)
    right_num = _to_numeric(right)

    if left_num is None or right_num is None:
        return []

    result = left_num - right_num

    # Preserve integer type if both operands are integers
    if isinstance(left_num, int) and isinstance(right_num, int):
        return [int(result)]

    return [result]


def multiply(left: Any, right: Any) -> list[Any]:
    """
    FHIRPath multiplication operator (*).

    Multiplies two numeric values following FHIRPath semantics:
    - Empty collection propagates
    - Integer * Integer -> Integer
    - Decimal * any -> Decimal

    Args:
        left: Left operand (numeric or empty).
        right: Right operand (numeric or empty).

    Returns:
        List containing the product, or empty list if either operand is empty.

    Example:
        >>> multiply(3, 4)
        [12]
        >>> multiply(2.5, 2)
        [5.0]
    """
    if _is_empty(left) or _is_empty(right):
        return []

    left_num = _to_numeric(left)
    right_num = _to_numeric(right)

    if left_num is None or right_num is None:
        return []

    result = left_num * right_num

    # Preserve integer type if both operands are integers
    if isinstance(left_num, int) and isinstance(right_num, int):
        return [int(result)]

    return [result]


def divide(left: Any, right: Any) -> list[Any]:
    """
    FHIRPath division operator (/).

    Divides two numeric values following FHIRPath semantics:
    - Empty collection propagates
    - Division always returns Decimal (float)
    - Division by zero returns empty collection (polymorphic behavior)

    Args:
        left: Left operand (numeric or empty).
        right: Right operand (numeric or empty).

    Returns:
        List containing the quotient as float, or empty list.

    Example:
        >>> divide(10, 4)
        [2.5]
        >>> divide(10, 0)
        []
    """
    if _is_empty(left) or _is_empty(right):
        return []

    left_num = _to_numeric(left)
    right_num = _to_numeric(right)

    if left_num is None or right_num is None:
        return []

    # Division by zero returns empty in FHIRPath
    if right_num == 0:
        return []

    # Division always returns Decimal in FHIRPath
    return [float(left_num) / float(right_num)]


def div(left: Any, right: Any) -> list[Any]:
    """
    FHIRPath integer division operator (div).

    Performs integer division (truncates toward zero):
    - Empty collection propagates
    - Division by zero returns empty collection

    Args:
        left: Left operand (numeric or empty).
        right: Right operand (numeric or empty).

    Returns:
        List containing the integer quotient, or empty list.

    Example:
        >>> div(10, 3)
        [3]
        >>> div(-10, 3)
        [-3]
        >>> div(10, 0)
        []
    """
    if _is_empty(left) or _is_empty(right):
        return []

    left_num = _to_numeric(left)
    right_num = _to_numeric(right)

    if left_num is None or right_num is None:
        return []

    # Division by zero returns empty in FHIRPath
    if right_num == 0:
        return []

    # Integer division truncates toward zero
    # Python's // truncates toward negative infinity, so use int(a/b) for trunc toward zero
    result = int(float(left_num) / float(right_num))
    return [result]


def mod(left: Any, right: Any) -> list[Any]:
    """
    FHIRPath modulo operator (mod).

    Returns the remainder of integer division:
    - Empty collection propagates
    - Division by zero returns empty collection
    - Result has same sign as dividend (truncation semantics)

    Args:
        left: Left operand (numeric or empty).
        right: Right operand (numeric or empty).

    Returns:
        List containing the remainder, or empty list.

    Example:
        >>> mod(10, 3)
        [1]
        >>> mod(-10, 3)
        [-1]
        >>> mod(10, 0)
        []
    """
    if _is_empty(left) or _is_empty(right):
        return []

    left_num = _to_numeric(left)
    right_num = _to_numeric(right)

    if left_num is None or right_num is None:
        return []

    # Division by zero returns empty in FHIRPath
    if right_num == 0:
        return []

    # Python's % follows truncation toward negative infinity,
    # but FHIRPath div truncates toward zero, so we need to adjust
    # Actually, FHIRPath uses trunc(dividend / divisor) semantics
    result = math.fmod(float(left_num), float(right_num))
    return [result]


# ==============================================================================
# Unary Operators
# ==============================================================================


def negate(value: Any) -> list[Any]:
    """
    FHIRPath unary negation operator (-).

    Negates a numeric value:
    - Empty collection returns empty

    Args:
        value: Numeric value or empty.

    Returns:
        List containing the negated value, or empty list.

    Example:
        >>> negate(5)
        [-5]
        >>> negate(-3.5)
        [3.5]
        >>> negate([])
        []
    """
    if _is_empty(value):
        return []

    num = _to_numeric(value)
    if num is None:
        return []

    return [-num]


def positive(value: Any) -> list[Any]:
    """
    FHIRPath unary positive operator (+).

    Returns the numeric value unchanged:
    - Empty collection returns empty

    Args:
        value: Numeric value or empty.

    Returns:
        List containing the value, or empty list.

    Example:
        >>> positive(5)
        [5]
        >>> positive(-3.5)
        [-3.5]
        >>> positive([])
        []
    """
    if _is_empty(value):
        return []

    num = _to_numeric(value)
    if num is None:
        return []

    return [num]


# ==============================================================================
# Aggregate Functions
# ==============================================================================


def sum_fn(collection: Any) -> list[Any]:
    """
    FHIRPath sum() function.

    Returns the sum of all numeric values in the collection:
    - Empty collection returns empty
    - Sum of Integers -> Integer
    - Sum with any Decimal -> Decimal

    Args:
        collection: A collection of numeric values.

    Returns:
        List containing the sum, or empty list.

    Example:
        >>> sum_fn([1, 2, 3])
        [6]
        >>> sum_fn([1.5, 2.5])
        [4.0]
        >>> sum_fn([])
        []
    """
    if _is_empty(collection):
        return []

    # Handle list/collection
    items = collection if isinstance(collection, list) else [collection]

    # Filter to numeric values only
    numeric_values = []
    has_decimal = False

    for item in items:
        num = _to_numeric(item)
        if num is not None:
            numeric_values.append(num)
            if isinstance(num, float):
                has_decimal = True

    if not numeric_values:
        return []

    result = sum(numeric_values)

    # Preserve integer if all values are integers
    if not has_decimal:
        result = int(result)

    return [result]


def min_fn(collection: Any) -> list[Any]:
    """
    FHIRPath min() function.

    Returns the minimum value in the collection:
    - Empty collection returns empty
    - Works with numbers, strings, dates, times

    Args:
        collection: A collection of comparable values.

    Returns:
        List containing the minimum value, or empty list.

    Example:
        >>> min_fn([3, 1, 2])
        [1]
        >>> min_fn(['c', 'a', 'b'])
        ['a']
        >>> min_fn([])
        []
    """
    if _is_empty(collection):
        return []

    items = collection if isinstance(collection, list) else [collection]

    if not items:
        return []

    # Filter out None values
    valid_items = [item for item in items if item is not None]

    if not valid_items:
        return []

    try:
        return [min(valid_items)]
    except TypeError:
        # Items are not comparable
        return []


def max_fn(collection: Any) -> list[Any]:
    """
    FHIRPath max() function.

    Returns the maximum value in the collection:
    - Empty collection returns empty
    - Works with numbers, strings, dates, times

    Args:
        collection: A collection of comparable values.

    Returns:
        List containing the maximum value, or empty list.

    Example:
        >>> max_fn([3, 1, 2])
        [3]
        >>> max_fn(['c', 'a', 'b'])
        ['c']
        >>> max_fn([])
        []
    """
    if _is_empty(collection):
        return []

    items = collection if isinstance(collection, list) else [collection]

    if not items:
        return []

    # Filter out None values
    valid_items = [item for item in items if item is not None]

    if not valid_items:
        return []

    try:
        return [max(valid_items)]
    except TypeError:
        # Items are not comparable
        return []


def avg(collection: Any) -> list[Any]:
    """
    FHIRPath avg() function.

    Returns the average of all numeric values in the collection:
    - Empty collection returns empty
    - Always returns Decimal (float)

    Args:
        collection: A collection of numeric values.

    Returns:
        List containing the average as float, or empty list.

    Example:
        >>> avg([1, 2, 3])
        [2.0]
        >>> avg([1.5, 2.5])
        [2.0]
        >>> avg([])
        []
    """
    if _is_empty(collection):
        return []

    items = collection if isinstance(collection, list) else [collection]

    # Filter to numeric values only
    numeric_values = []
    for item in items:
        num = _to_numeric(item)
        if num is not None:
            numeric_values.append(num)

    if not numeric_values:
        return []

    result = sum(numeric_values) / len(numeric_values)
    return [float(result)]


# ==============================================================================
# Math Functions
# ==============================================================================


def abs_fn(value: Any) -> list[Any]:
    """
    FHIRPath abs() function.

    Returns the absolute value:
    - Empty collection returns empty
    - Integer input -> Integer output
    - Decimal input -> Decimal output

    Args:
        value: Numeric value or empty.

    Returns:
        List containing the absolute value, or empty list.

    Example:
        >>> abs_fn(-5)
        [5]
        >>> abs_fn(-3.14)
        [3.14]
        >>> abs_fn([])
        []
    """
    if _is_empty(value):
        return []

    num = _to_numeric(value)
    if num is None:
        return []

    result = abs(num)

    # Preserve integer type
    if isinstance(num, int):
        return [int(result)]

    return [result]


def ceiling(value: Any) -> list[Any]:
    """
    FHIRPath ceiling() function.

    Returns the smallest integer greater than or equal to the value:
    - Empty collection returns empty
    - Always returns Integer

    Args:
        value: Numeric value or empty.

    Returns:
        List containing the ceiling integer, or empty list.

    Example:
        >>> ceiling(3.2)
        [4]
        >>> ceiling(-3.2)
        [-3]
        >>> ceiling(5)
        [5]
    """
    if _is_empty(value):
        return []

    num = _to_numeric(value)
    if num is None:
        return []

    return [math.ceil(num)]


def floor(value: Any) -> list[Any]:
    """
    FHIRPath floor() function.

    Returns the largest integer less than or equal to the value:
    - Empty collection returns empty
    - Always returns Integer

    Args:
        value: Numeric value or empty.

    Returns:
        List containing the floor integer, or empty list.

    Example:
        >>> floor(3.7)
        [3]
        >>> floor(-3.7)
        [-4]
        >>> floor(5)
        [5]
    """
    if _is_empty(value):
        return []

    num = _to_numeric(value)
    if num is None:
        return []

    return [math.floor(num)]


def round_fn(value: Any, precision: Any = None) -> list[Any]:
    """
    FHIRPath round() function.

    Rounds to the specified precision:
    - Empty collection returns empty
    - Default precision is 0 (round to integer)
    - Returns Decimal if precision > 0, Integer if precision = 0

    Args:
        value: Numeric value or empty.
        precision: Number of decimal places (default 0).

    Returns:
        List containing the rounded value, or empty list.

    Example:
        >>> round_fn(3.456, 2)
        [3.46]
        >>> round_fn(3.5)
        [4]
        >>> round_fn(3.4)
        [3]
    """
    if _is_empty(value):
        return []

    num = _to_numeric(value)
    if num is None:
        return []

    # Default precision is 0
    prec = 0
    if precision is not None:
        prec_num = _to_numeric(precision)
        if prec_num is None:
            return []
        prec = int(prec_num)

    result = round(num, prec)

    # If precision is 0, return integer
    if prec == 0:
        return [int(result)]

    return [result]


def sqrt(value: Any) -> list[Any]:
    """
    FHIRPath sqrt() function.

    Returns the square root:
    - Empty collection returns empty
    - Negative values return empty (no imaginary numbers in FHIRPath)
    - Always returns Decimal

    Args:
        value: Numeric value or empty.

    Returns:
        List containing the square root, or empty list.

    Example:
        >>> sqrt(16)
        [4.0]
        >>> sqrt(2)
        [1.4142135623730951]
        >>> sqrt(-1)
        []
    """
    if _is_empty(value):
        return []

    num = _to_numeric(value)
    if num is None:
        return []

    # Negative values return empty
    if num < 0:
        return []

    return [math.sqrt(num)]


def power(value: Any, exponent: Any) -> list[Any]:
    """
    FHIRPath power() function.

    Raises a value to the specified power:
    - Empty collection propagates
    - Returns empty for negative base with non-integer exponent
    - Integer ^ Integer -> Integer (if result is exact)
    - Otherwise Decimal

    Args:
        value: Base value or empty.
        exponent: Exponent value or empty.

    Returns:
        List containing the result, or empty list.

    Example:
        >>> power(2, 3)
        [8]
        >>> power(4, 0.5)
        [2.0]
        >>> power(-2, 3)
        [-8]
        >>> power(-2, 0.5)
        []
    """
    if _is_empty(value) or _is_empty(exponent):
        return []

    base_num = _to_numeric(value)
    exp_num = _to_numeric(exponent)

    if base_num is None or exp_num is None:
        return []

    # Negative base with non-integer exponent returns empty
    if base_num < 0 and not isinstance(exp_num, int) and not exp_num.is_integer():
        return []

    try:
        result = math.pow(base_num, exp_num)

        # Check for overflow
        if math.isinf(result):
            return []

        # Return integer if both inputs are integers and result is exact
        if isinstance(base_num, int) and isinstance(exp_num, int) and exp_num >= 0:
            return [int(result)]

        return [result]
    except (ValueError, OverflowError):
        return []


def log(value: Any, base: Any = None) -> list[Any]:
    """
    FHIRPath log() function.

    Returns the logarithm with specified base:
    - Empty collection propagates
    - Default base is e (natural log) - same as ln()
    - Non-positive values return empty
    - Base <= 0 or base == 1 returns empty

    Args:
        value: Numeric value or empty.
        base: Logarithm base (default is e).

    Returns:
        List containing the logarithm, or empty list.

    Example:
        >>> log(100, 10)
        [2.0]
        >>> log(math.e)
        [1.0]
        >>> log(0)
        []
    """
    if _is_empty(value):
        return []

    num = _to_numeric(value)
    if num is None:
        return []

    # Non-positive values return empty
    if num <= 0:
        return []

    if base is None:
        # Default to natural log
        return [math.log(num)]

    base_num = _to_numeric(base)
    if base_num is None:
        return []

    # Invalid base
    if base_num <= 0 or base_num == 1:
        return []

    return [math.log(num, base_num)]


def exp(value: Any) -> list[Any]:
    """
    FHIRPath exp() function.

    Returns e raised to the power of the value:
    - Empty collection returns empty
    - Returns Decimal
    - Handles overflow (returns empty for very large inputs)

    Args:
        value: Numeric value or empty.

    Returns:
        List containing e^value, or empty list.

    Example:
        >>> exp(1)
        [2.718281828459045]
        >>> exp(0)
        [1.0]
    """
    if _is_empty(value):
        return []

    num = _to_numeric(value)
    if num is None:
        return []

    try:
        result = math.exp(num)

        # Handle overflow
        if math.isinf(result):
            return []

        return [result]
    except OverflowError:
        return []


def ln(value: Any) -> list[Any]:
    """
    FHIRPath ln() function.

    Returns the natural logarithm:
    - Empty collection returns empty
    - Non-positive values return empty
    - Returns Decimal

    Args:
        value: Numeric value or empty.

    Returns:
        List containing the natural log, or empty list.

    Example:
        >>> ln(math.e)
        [1.0]
        >>> ln(1)
        [0.0]
        >>> ln(0)
        []
    """
    if _is_empty(value):
        return []

    num = _to_numeric(value)
    if num is None:
        return []

    # Non-positive values return empty
    if num <= 0:
        return []

    return [math.log(num)]


def trunc(value: Any) -> list[Any]:
    """
    FHIRPath trunc() function.

    Returns the integer part of the value (truncates toward zero):
    - Empty collection returns empty
    - Always returns Integer

    Args:
        value: Numeric value or empty.

    Returns:
        List containing the truncated integer, or empty list.

    Example:
        >>> trunc(3.7)
        [3]
        >>> trunc(-3.7)
        [-3]
        >>> trunc(5)
        [5]
    """
    if _is_empty(value):
        return []

    num = _to_numeric(value)
    if num is None:
        return []

    # math.trunc truncates toward zero
    return [math.trunc(num)]


# ==============================================================================
# Math Functions Class
# ==============================================================================


class MathFunctions:
    """
    Container class for FHIRPath math functions.

    Provides all math functions as methods for use in expression evaluation.
    """

    # Arithmetic operators
    add = staticmethod(add)
    subtract = staticmethod(subtract)
    multiply = staticmethod(multiply)
    divide = staticmethod(divide)
    div = staticmethod(div)
    mod = staticmethod(mod)

    # Unary operators
    negate = staticmethod(negate)
    positive = staticmethod(positive)

    # Aggregate functions
    sum = staticmethod(sum_fn)
    min = staticmethod(min_fn)
    max = staticmethod(max_fn)
    avg = staticmethod(avg)

    # Math functions
    abs = staticmethod(abs_fn)
    ceiling = staticmethod(ceiling)
    floor = staticmethod(floor)
    round = staticmethod(round_fn)
    sqrt = staticmethod(sqrt)
    power = staticmethod(power)
    log = staticmethod(log)
    exp = staticmethod(exp)
    ln = staticmethod(ln)
    trunc = staticmethod(trunc)


# ==============================================================================
# Function Registry for Evaluator Integration
# ==============================================================================

MATH_FUNCTIONS: dict[str, callable] = {
    # Aggregate functions
    'sum': sum_fn,
    'min': min_fn,
    'max': max_fn,
    'avg': avg,
    # Math functions
    'abs': abs_fn,
    'ceiling': ceiling,
    'floor': floor,
    'round': round_fn,
    'sqrt': sqrt,
    'power': power,
    'log': log,
    'exp': exp,
    'ln': ln,
    'trunc': trunc,
}

MATH_OPERATORS: dict[str, callable] = {
    '+': add,
    '-': subtract,
    '*': multiply,
    '/': divide,
    'div': div,
    'mod': mod,
}
