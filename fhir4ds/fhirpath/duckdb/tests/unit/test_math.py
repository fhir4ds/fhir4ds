"""
Unit tests for FHIRPath Math & Aggregate Functions

Tests the math functions module following FHIRPath semantics:
- Empty collection propagation
- Type coercion (Integer/Decimal)
- Division by zero handling
- Edge cases (infinity, NaN, negative roots)
"""

import math
import pytest

from ...functions.math import (
    # Arithmetic operators
    add,
    subtract,
    multiply,
    divide,
    div,
    mod,
    # Unary operators
    negate,
    positive,
    # Aggregate functions
    sum_fn,
    min_fn,
    max_fn,
    avg,
    # Math functions
    abs_fn,
    ceiling,
    floor,
    round_fn,
    sqrt,
    power,
    log,
    exp,
    ln,
    trunc,
    # Class and registries
    MathFunctions,
    MATH_FUNCTIONS,
    MATH_OPERATORS,
)


# ==============================================================================
# Arithmetic Operators Tests
# ==============================================================================


class TestAddition:
    """Tests for FHIRPath addition operator."""

    def test_integer_addition(self):
        """Integer + Integer -> Integer"""
        assert add(1, 2) == [3]
        assert add(0, 0) == [0]
        assert add(-5, 10) == [5]
        assert add(100, -50) == [50]

    def test_decimal_addition(self):
        """Decimal + Decimal -> Decimal"""
        assert add(1.5, 2.5) == [4.0]
        assert add(0.1, 0.2) == pytest.approx([0.3], rel=1e-9)
        assert add(-1.5, 2.5) == [1.0]

    def test_mixed_addition(self):
        """Integer + Decimal -> Decimal"""
        assert add(1, 2.5) == [3.5]
        assert add(2.5, 1) == [3.5]

    def test_empty_collection_propagation(self):
        """{} + x -> {}, x + {} -> {}"""
        assert add([], 1) == []
        assert add(1, []) == []
        assert add(None, 1) == []
        assert add(1, None) == []
        assert add([], []) == []

    def test_non_numeric_returns_empty(self):
        """Non-numeric operands return empty"""
        assert add("1", 2) == []
        assert add(1, "2") == []
        assert add(True, 1) == []  # Booleans not numeric in FHIRPath


class TestSubtraction:
    """Tests for FHIRPath subtraction operator."""

    def test_integer_subtraction(self):
        """Integer - Integer -> Integer"""
        assert subtract(5, 3) == [2]
        assert subtract(0, 5) == [-5]
        assert subtract(-5, -10) == [5]

    def test_decimal_subtraction(self):
        """Decimal - Decimal -> Decimal"""
        assert subtract(5.5, 2.5) == [3.0]
        assert subtract(1.0, 0.9) == pytest.approx([0.1], rel=1e-9)

    def test_empty_collection_propagation(self):
        """{} - x -> {}, x - {} -> {}"""
        assert subtract([], 1) == []
        assert subtract(1, []) == []


class TestMultiplication:
    """Tests for FHIRPath multiplication operator."""

    def test_integer_multiplication(self):
        """Integer * Integer -> Integer"""
        assert multiply(3, 4) == [12]
        assert multiply(-2, 5) == [-10]
        assert multiply(0, 100) == [0]

    def test_decimal_multiplication(self):
        """Decimal * any -> Decimal"""
        assert multiply(2.5, 2) == [5.0]
        assert multiply(2, 2.5) == [5.0]
        assert multiply(1.5, 1.5) == [2.25]

    def test_empty_collection_propagation(self):
        """{} * x -> {}, x * {} -> {}"""
        assert multiply([], 1) == []
        assert multiply(1, []) == []


class TestDivision:
    """Tests for FHIRPath division operator."""

    def test_division_returns_decimal(self):
        """Division always returns Decimal"""
        assert divide(10, 4) == [2.5]
        assert divide(10, 2) == [5.0]  # Even exact division returns float
        assert divide(7, 3) == pytest.approx([2.3333333333333335], rel=1e-9)

    def test_division_by_zero(self):
        """Division by zero returns empty collection"""
        assert divide(10, 0) == []
        assert divide(0, 0) == []
        assert divide(-10, 0) == []

    def test_negative_division(self):
        """Negative division works correctly"""
        assert divide(-10, 2) == [-5.0]
        assert divide(10, -2) == [-5.0]
        assert divide(-10, -2) == [5.0]

    def test_empty_collection_propagation(self):
        """{} / x -> {}, x / {} -> {}"""
        assert divide([], 1) == []
        assert divide(1, []) == []


class TestIntegerDivision:
    """Tests for FHIRPath integer division (div) operator."""

    def test_integer_division(self):
        """div truncates toward zero"""
        assert div(10, 3) == [3]
        assert div(10, 4) == [2]
        assert div(9, 3) == [3]

    def test_negative_division(self):
        """Negative div truncates toward zero"""
        assert div(-10, 3) == [-3]  # Not -4 (trunc toward zero)
        assert div(10, -3) == [-3]
        assert div(-10, -3) == [3]

    def test_division_by_zero(self):
        """div by zero returns empty collection"""
        assert div(10, 0) == []
        assert div(0, 0) == []

    def test_decimal_inputs(self):
        """div works with decimal inputs"""
        assert div(10.5, 3) == [3]
        assert div(10, 3.5) == [2]

    def test_empty_collection_propagation(self):
        """{} div x -> {}, x div {} -> {}"""
        assert div([], 1) == []
        assert div(1, []) == []


class TestModulo:
    """Tests for FHIRPath modulo (mod) operator."""

    def test_modulo(self):
        """mod returns remainder"""
        assert mod(10, 3) == [1]
        assert mod(10, 4) == [2]
        assert mod(9, 3) == [0]

    def test_negative_modulo(self):
        """Negative mod uses truncation semantics"""
        result = mod(-10, 3)
        assert len(result) == 1
        # fmod gives -1.0 for -10 % 3 (trunc toward zero)
        assert result[0] == pytest.approx(-1.0, rel=1e-9)

    def test_modulo_by_zero(self):
        """mod by zero returns empty collection"""
        assert mod(10, 0) == []

    def test_empty_collection_propagation(self):
        """{} mod x -> {}, x mod {} -> {}"""
        assert mod([], 1) == []
        assert mod(1, []) == []


# ==============================================================================
# Unary Operators Tests
# ==============================================================================


class TestNegate:
    """Tests for FHIRPath unary negation operator."""

    def test_negate_integer(self):
        """Negate integer"""
        assert negate(5) == [-5]
        assert negate(-5) == [5]
        assert negate(0) == [0]

    def test_negate_decimal(self):
        """Negate decimal"""
        assert negate(3.14) == [-3.14]
        assert negate(-2.5) == [2.5]

    def test_negate_empty(self):
        """Negate empty collection"""
        assert negate([]) == []
        assert negate(None) == []


class TestPositive:
    """Tests for FHIRPath unary positive operator."""

    def test_positive_integer(self):
        """Positive of integer"""
        assert positive(5) == [5]
        assert positive(-5) == [-5]

    def test_positive_empty(self):
        """Positive of empty collection"""
        assert positive([]) == []
        assert positive(None) == []


# ==============================================================================
# Aggregate Functions Tests
# ==============================================================================


class TestSum:
    """Tests for FHIRPath sum() function."""

    def test_sum_integers(self):
        """Sum of integers returns integer"""
        assert sum_fn([1, 2, 3]) == [6]
        assert sum_fn([10, -5, 3]) == [8]

    def test_sum_decimals(self):
        """Sum with decimals returns decimal"""
        assert sum_fn([1.5, 2.5]) == [4.0]
        assert sum_fn([1, 2.5, 3]) == [6.5]

    def test_sum_empty(self):
        """Sum of empty collection returns empty"""
        assert sum_fn([]) == []

    def test_sum_single_value(self):
        """Sum of single value"""
        assert sum_fn([5]) == [5]
        assert sum_fn([5.5]) == [5.5]

    def test_sum_non_numeric_filtered(self):
        """Non-numeric values are filtered"""
        assert sum_fn([1, "2", 3]) == [4]
        assert sum_fn([1, None, 3]) == [4]
        assert sum_fn(["a", "b"]) == []


class TestMin:
    """Tests for FHIRPath min() function."""

    def test_min_numbers(self):
        """Min of numbers"""
        assert min_fn([3, 1, 2]) == [1]
        assert min_fn([-5, 0, 5]) == [-5]

    def test_min_strings(self):
        """Min of strings"""
        assert min_fn(['c', 'a', 'b']) == ['a']

    def test_min_empty(self):
        """Min of empty collection returns empty"""
        assert min_fn([]) == []

    def test_min_single(self):
        """Min of single value"""
        assert min_fn([5]) == [5]


class TestMax:
    """Tests for FHIRPath max() function."""

    def test_max_numbers(self):
        """Max of numbers"""
        assert max_fn([3, 1, 2]) == [3]
        assert max_fn([-5, 0, 5]) == [5]

    def test_max_strings(self):
        """Max of strings"""
        assert max_fn(['c', 'a', 'b']) == ['c']

    def test_max_empty(self):
        """Max of empty collection returns empty"""
        assert max_fn([]) == []

    def test_max_single(self):
        """Max of single value"""
        assert max_fn([5]) == [5]


class TestAvg:
    """Tests for FHIRPath avg() function."""

    def test_avg_integers(self):
        """Avg always returns decimal"""
        assert avg([1, 2, 3]) == [2.0]
        assert avg([10, 20]) == [15.0]

    def test_avg_decimals(self):
        """Avg of decimals"""
        assert avg([1.5, 2.5]) == [2.0]
        assert avg([1.0, 2.0, 3.0]) == [2.0]

    def test_avg_empty(self):
        """Avg of empty collection returns empty"""
        assert avg([]) == []

    def test_avg_single(self):
        """Avg of single value"""
        assert avg([5]) == [5.0]
        assert avg([5.5]) == [5.5]

    def test_avg_non_numeric_filtered(self):
        """Non-numeric values are filtered"""
        assert avg([1, "2", 3]) == [2.0]


# ==============================================================================
# Math Functions Tests
# ==============================================================================


class TestAbs:
    """Tests for FHIRPath abs() function."""

    def test_abs_integer(self):
        """Abs of integer returns integer"""
        assert abs_fn(-5) == [5]
        assert abs_fn(5) == [5]
        assert abs_fn(0) == [0]

    def test_abs_decimal(self):
        """Abs of decimal returns decimal"""
        assert abs_fn(-3.14) == [3.14]
        assert abs_fn(3.14) == [3.14]

    def test_abs_empty(self):
        """Abs of empty returns empty"""
        assert abs_fn([]) == []


class TestCeiling:
    """Tests for FHIRPath ceiling() function."""

    def test_ceiling_positive(self):
        """Ceiling of positive numbers"""
        assert ceiling(3.2) == [4]
        assert ceiling(3.0) == [3]
        assert ceiling(3.9) == [4]

    def test_ceiling_negative(self):
        """Ceiling of negative numbers"""
        assert ceiling(-3.2) == [-3]  # -3 > -3.2
        assert ceiling(-3.9) == [-3]

    def test_ceiling_empty(self):
        """Ceiling of empty returns empty"""
        assert ceiling([]) == []


class TestFloor:
    """Tests for FHIRPath floor() function."""

    def test_floor_positive(self):
        """Floor of positive numbers"""
        assert floor(3.7) == [3]
        assert floor(3.0) == [3]
        assert floor(3.2) == [3]

    def test_floor_negative(self):
        """Floor of negative numbers"""
        assert floor(-3.2) == [-4]  # -4 < -3.2
        assert floor(-3.7) == [-4]

    def test_floor_empty(self):
        """Floor of empty returns empty"""
        assert floor([]) == []


class TestRound:
    """Tests for FHIRPath round() function."""

    def test_round_default_precision(self):
        """Round with default precision (0)"""
        assert round_fn(3.4) == [3]
        assert round_fn(3.5) == [4]  # Python round() rounds to even
        assert round_fn(3.6) == [4]
        assert round_fn(-3.5) == [-4]

    def test_round_with_precision(self):
        """Round with specified precision"""
        assert round_fn(3.456, 2) == [3.46]
        assert round_fn(3.456, 1) == [3.5]
        assert round_fn(3.456, 0) == [3]

    def test_round_empty(self):
        """Round of empty returns empty"""
        assert round_fn([]) == []

    def test_round_negative_precision(self):
        """Round with negative precision"""
        # Python round(123, -1) = 120
        result = round_fn(123, -1)
        assert len(result) == 1
        assert result[0] == 120


class TestSqrt:
    """Tests for FHIRPath sqrt() function."""

    def test_sqrt_perfect_square(self):
        """Sqrt of perfect square"""
        assert sqrt(16) == [4.0]
        assert sqrt(25) == [5.0]
        assert sqrt(0) == [0.0]

    def test_sqrt_irrational(self):
        """Sqrt of irrational result"""
        result = sqrt(2)
        assert len(result) == 1
        assert result[0] == pytest.approx(1.4142135623730951, rel=1e-9)

    def test_sqrt_negative_returns_empty(self):
        """Sqrt of negative returns empty (no imaginary numbers)"""
        assert sqrt(-1) == []
        assert sqrt(-4) == []

    def test_sqrt_empty(self):
        """Sqrt of empty returns empty"""
        assert sqrt([]) == []


class TestPower:
    """Tests for FHIRPath power() function."""

    def test_power_integer_exponent(self):
        """Power with integer exponent"""
        assert power(2, 3) == [8]
        assert power(5, 0) == [1]
        assert power(2, 1) == [2]

    def test_power_decimal_exponent(self):
        """Power with decimal exponent"""
        assert power(4, 0.5) == [2.0]
        assert power(9, 0.5) == [3.0]

    def test_power_negative_base_integer_exp(self):
        """Negative base with integer exponent"""
        assert power(-2, 3) == [-8]
        assert power(-2, 2) == [4]

    def test_power_negative_base_noninteger_exp(self):
        """Negative base with non-integer exponent returns empty"""
        assert power(-2, 0.5) == []  # sqrt(-2)
        assert power(-4, 0.5) == []

    def test_power_empty_propagation(self):
        """Power with empty operand returns empty"""
        assert power([], 2) == []
        assert power(2, []) == []

    def test_power_overflow(self):
        """Power overflow returns empty"""
        result = power(10, 1000)  # Very large number
        # May return empty due to overflow
        # Or may return inf which we handle
        if result:
            assert math.isinf(result[0]) or result == []


class TestLog:
    """Tests for FHIRPath log() function."""

    def test_log_base_10(self):
        """Log base 10"""
        assert log(100, 10) == [2.0]
        result = log(1000, 10)
        assert len(result) == 1
        assert result[0] == pytest.approx(3.0, rel=1e-9)
        assert log(10, 10) == [1.0]

    def test_log_base_2(self):
        """Log base 2"""
        assert log(8, 2) == [3.0]
        assert log(16, 2) == [4.0]

    def test_log_natural(self):
        """Log with no base (natural log)"""
        assert log(math.e) == [1.0]
        assert log(1) == [0.0]

    def test_log_non_positive_returns_empty(self):
        """Log of non-positive returns empty"""
        assert log(0) == []
        assert log(-1) == []

    def test_log_invalid_base(self):
        """Log with invalid base returns empty"""
        assert log(10, 0) == []
        assert log(10, 1) == []
        assert log(10, -2) == []

    def test_log_empty(self):
        """Log of empty returns empty"""
        assert log([]) == []


class TestExp:
    """Tests for FHIRPath exp() function."""

    def test_exp_zero(self):
        """exp(0) = 1"""
        assert exp(0) == [1.0]

    def test_exp_one(self):
        """exp(1) = e"""
        result = exp(1)
        assert len(result) == 1
        assert result[0] == pytest.approx(math.e, rel=1e-9)

    def test_exp_negative(self):
        """exp(-1) = 1/e"""
        result = exp(-1)
        assert len(result) == 1
        assert result[0] == pytest.approx(1 / math.e, rel=1e-9)

    def test_exp_empty(self):
        """exp of empty returns empty"""
        assert exp([]) == []

    def test_exp_large_value(self):
        """exp with very large input returns empty (overflow)"""
        result = exp(1000)
        # Should return empty due to overflow
        assert result == []


class TestLn:
    """Tests for FHIRPath ln() function."""

    def test_ln_e(self):
        """ln(e) = 1"""
        assert ln(math.e) == [1.0]

    def test_ln_one(self):
        """ln(1) = 0"""
        assert ln(1) == [0.0]

    def test_ln_non_positive_returns_empty(self):
        """ln of non-positive returns empty"""
        assert ln(0) == []
        assert ln(-1) == []

    def test_ln_empty(self):
        """ln of empty returns empty"""
        assert ln([]) == []


class TestTrunc:
    """Tests for FHIRPath trunc() function."""

    def test_trunc_positive(self):
        """Trunc of positive numbers"""
        assert trunc(3.7) == [3]
        assert trunc(3.2) == [3]
        assert trunc(3.0) == [3]

    def test_trunc_negative(self):
        """Trunc of negative numbers (toward zero)"""
        assert trunc(-3.7) == [-3]
        assert trunc(-3.2) == [-3]
        assert trunc(-3.0) == [-3]

    def test_trunc_empty(self):
        """Trunc of empty returns empty"""
        assert trunc([]) == []


# ==============================================================================
# MathFunctions Class Tests
# ==============================================================================


class TestMathFunctionsClass:
    """Tests for MathFunctions container class."""

    def test_class_has_all_methods(self):
        """MathFunctions class has all expected methods"""
        assert hasattr(MathFunctions, 'add')
        assert hasattr(MathFunctions, 'subtract')
        assert hasattr(MathFunctions, 'multiply')
        assert hasattr(MathFunctions, 'divide')
        assert hasattr(MathFunctions, 'div')
        assert hasattr(MathFunctions, 'mod')
        assert hasattr(MathFunctions, 'negate')
        assert hasattr(MathFunctions, 'positive')
        assert hasattr(MathFunctions, 'sum')
        assert hasattr(MathFunctions, 'min')
        assert hasattr(MathFunctions, 'max')
        assert hasattr(MathFunctions, 'avg')
        assert hasattr(MathFunctions, 'abs')
        assert hasattr(MathFunctions, 'ceiling')
        assert hasattr(MathFunctions, 'floor')
        assert hasattr(MathFunctions, 'round')
        assert hasattr(MathFunctions, 'sqrt')
        assert hasattr(MathFunctions, 'power')
        assert hasattr(MathFunctions, 'log')
        assert hasattr(MathFunctions, 'exp')
        assert hasattr(MathFunctions, 'ln')
        assert hasattr(MathFunctions, 'trunc')

    def test_class_methods_work(self):
        """MathFunctions class methods work correctly"""
        assert MathFunctions.add(1, 2) == [3]
        assert MathFunctions.subtract(5, 3) == [2]
        assert MathFunctions.sum([1, 2, 3]) == [6]
        assert MathFunctions.abs(-5) == [5]


# ==============================================================================
# Registry Tests
# ==============================================================================


class TestRegistries:
    """Tests for function and operator registries."""

    def test_math_functions_registry(self):
        """MATH_FUNCTIONS contains all expected functions"""
        expected_functions = [
            'sum', 'min', 'max', 'avg',
            'abs', 'ceiling', 'floor', 'round',
            'sqrt', 'power', 'log', 'exp', 'ln', 'trunc',
        ]
        for func_name in expected_functions:
            assert func_name in MATH_FUNCTIONS
            assert callable(MATH_FUNCTIONS[func_name])

    def test_math_operators_registry(self):
        """MATH_OPERATORS contains all expected operators"""
        expected_operators = ['+', '-', '*', '/', 'div', 'mod']
        for op in expected_operators:
            assert op in MATH_OPERATORS
            assert callable(MATH_OPERATORS[op])

    def test_registry_functions_work(self):
        """Functions from registry work correctly"""
        assert MATH_FUNCTIONS['sum']([1, 2, 3]) == [6]
        assert MATH_FUNCTIONS['abs'](-5) == [5]
        assert MATH_OPERATORS['+'](1, 2) == [3]
        assert MATH_OPERATORS['*'](3, 4) == [12]


# ==============================================================================
# Edge Cases and FHIRPath Semantics Tests
# ==============================================================================


class TestFHIRPathSemantics:
    """Tests for specific FHIRPath semantic behaviors."""

    def test_empty_propagation_chain(self):
        """Empty collection propagates through operations"""
        assert add(add([], 1), 2) == []
        assert multiply(subtract(5, []), 2) == []

    def test_integer_preservation(self):
        """Integer type is preserved when appropriate"""
        # Integer + Integer -> Integer
        result = add(1, 2)
        assert result == [3]
        assert isinstance(result[0], int)

        # Integer * Integer -> Integer
        result = multiply(3, 4)
        assert result == [12]
        assert isinstance(result[0], int)

    def test_decimal_promotion(self):
        """Decimal promotes result type"""
        # Integer + Decimal -> Decimal
        result = add(1, 2.5)
        assert result == [3.5]
        assert isinstance(result[0], float)

    def test_division_always_decimal(self):
        """Division always returns Decimal"""
        result = divide(10, 2)
        assert result == [5.0]
        assert isinstance(result[0], float)

    def test_boolean_not_numeric(self):
        """Booleans are not treated as numeric in FHIRPath"""
        assert add(True, False) == []
        assert add(True, 1) == []
        assert sum_fn([True, False, True]) == []
