"""
Unit tests for CQL Ratio UDFs.

Tests for ratio operations:
- ratioNumeratorValue, ratioDenominatorValue
- ratioValue
- ratioNumeratorUnit, ratioDenominatorUnit
"""

import pytest
import duckdb

from ..udf.ratio import (
    ratioNumeratorValue,
    ratioDenominatorValue,
    ratioValue,
    ratioNumeratorUnit,
    ratioDenominatorUnit,
    registerRatioUdfs,
)


@pytest.fixture
def simple_ratio():
    """A simple ratio 5mg/1mL."""
    return '{"numerator": {"value": 5, "unit": "mg"}, "denominator": {"value": 1, "unit": "mL"}}'


@pytest.fixture
def ratio_with_code():
    """A ratio using code instead of unit."""
    return '{"numerator": {"value": 10, "code": "mg"}, "denominator": {"value": 2, "code": "mL"}}'


@pytest.fixture
def ratio_zero_denominator():
    """A ratio with zero denominator."""
    return '{"numerator": {"value": 5, "unit": "mg"}, "denominator": {"value": 0, "unit": "mL"}}'


@pytest.fixture
def ratio_missing_values():
    """A ratio with missing values."""
    return '{"numerator": {"unit": "mg"}, "denominator": {"unit": "mL"}}'


@pytest.fixture
def ratio_missing_denominator():
    """A ratio with missing denominator."""
    return '{"numerator": {"value": 5, "unit": "mg"}}'


# ========================================
# ratioNumeratorValue tests
# ========================================

def test_numerator_value_valid(simple_ratio):
    """Test getting numerator value from valid ratio."""
    result = ratioNumeratorValue(simple_ratio)
    assert result == 5


def test_numerator_value_null():
    """Test numerator value with null input."""
    assert ratioNumeratorValue(None) is None


def test_numerator_value_empty_string():
    """Test numerator value with empty string."""
    assert ratioNumeratorValue("") is None


def test_numerator_value_invalid_json():
    """Test numerator value with invalid JSON."""
    assert ratioNumeratorValue("not json") is None


def test_numerator_value_missing(simple_ratio):
    """Test numerator value when missing."""
    result = ratioNumeratorValue(ratio_missing_values)
    assert result is None


# ========================================
# ratioDenominatorValue tests
# ========================================

def test_denominator_value_valid(simple_ratio):
    """Test getting denominator value from valid ratio."""
    result = ratioDenominatorValue(simple_ratio)
    assert result == 1


def test_denominator_value_null():
    """Test denominator value with null input."""
    assert ratioDenominatorValue(None) is None


def test_denominator_value_missing():
    """Test denominator value when missing."""
    result = ratioDenominatorValue(ratio_missing_values)
    assert result is None


def test_denominator_value_missing_denominator():
    """Test denominator value when denominator is missing."""
    result = ratioDenominatorValue(ratio_missing_denominator)
    assert result is None


# ========================================
# ratioValue tests
# ========================================

def test_ratio_value_valid(simple_ratio):
    """Test calculating ratio value."""
    result = ratioValue(simple_ratio)
    assert result == 5.0


def test_ratio_value_fraction():
    """Test calculating ratio value with fraction."""
    ratio = '{"numerator": {"value": 10, "unit": "mg"}, "denominator": {"value": 4, "unit": "mL"}}'
    result = ratioValue(ratio)
    assert result == 2.5


def test_ratio_value_zero_numerator():
    """Test ratio value with zero numerator."""
    ratio = '{"numerator": {"value": 0, "unit": "mg"}, "denominator": {"value": 5, "unit": "mL"}}'
    result = ratioValue(ratio)
    assert result == 0.0


def test_ratio_value_zero_denominator(ratio_zero_denominator):
    """Test ratio value with zero denominator."""
    result = ratioValue(ratio_zero_denominator)
    assert result is None


def test_ratio_value_null():
    """Test ratio value with null input."""
    assert ratioValue(None) is None


def test_ratio_value_missing_numerator():
    """Test ratio value with missing numerator value."""
    ratio = '{"numerator": {"unit": "mg"}, "denominator": {"value": 5, "unit": "mL"}}'
    result = ratioValue(ratio)
    assert result is None


def test_ratio_value_missing_denominator():
    """Test ratio value with missing denominator value."""
    ratio = '{"numerator": {"value": 5, "unit": "mg"}, "denominator": {"unit": "mL"}}'
    result = ratioValue(ratio)
    assert result is None


# ========================================
# ratioNumeratorUnit tests
# ========================================

def test_numerator_unit_valid(simple_ratio):
    """Test getting numerator unit from valid ratio."""
    result = ratioNumeratorUnit(simple_ratio)
    assert result == "mg"


def test_numerator_unit_from_code(ratio_with_code):
    """Test getting numerator unit from code field."""
    result = ratioNumeratorUnit(ratio_with_code)
    assert result == "mg"


def test_numerator_unit_null():
    """Test numerator unit with null input."""
    assert ratioNumeratorUnit(None) is None


def test_numerator_unit_missing():
    """Test numerator unit when missing."""
    ratio = '{"numerator": {"value": 5}, "denominator": {"value": 1}}'
    result = ratioNumeratorUnit(ratio)
    assert result is None


# ========================================
# ratioDenominatorUnit tests
# ========================================

def test_denominator_unit_valid(simple_ratio):
    """Test getting denominator unit from valid ratio."""
    result = ratioDenominatorUnit(simple_ratio)
    assert result == "mL"


def test_denominator_unit_from_code(ratio_with_code):
    """Test getting denominator unit from code field."""
    result = ratioDenominatorUnit(ratio_with_code)
    assert result == "mL"


def test_denominator_unit_null():
    """Test denominator unit with null input."""
    assert ratioDenominatorUnit(None) is None


def test_denominator_unit_missing():
    """Test denominator unit when missing."""
    ratio = '{"numerator": {"value": 5}, "denominator": {"value": 1}}'
    result = ratioDenominatorUnit(ratio)
    assert result is None


# ========================================
# DuckDB Registration tests
# ========================================

def test_registration():
    """Test that UDFs can be registered with DuckDB."""
    con = duckdb.connect()
    registerRatioUdfs(con)

    ratio = '{"numerator": {"value": 5, "unit": "mg"}, "denominator": {"value": 1, "unit": "mL"}}'

    # Test numerator value
    result = con.execute("SELECT ratioNumeratorValue(?)", [ratio]).fetchone()
    assert result[0] == 5

    # Test denominator value
    result = con.execute("SELECT ratioDenominatorValue(?)", [ratio]).fetchone()
    assert result[0] == 1

    # Test ratio value
    result = con.execute("SELECT ratioValue(?)", [ratio]).fetchone()
    assert result[0] == 5.0

    con.close()


def test_registration_null_handling():
    """Test null handling through DuckDB."""
    con = duckdb.connect()
    registerRatioUdfs(con)

    result = con.execute("SELECT ratioNumeratorValue(NULL)").fetchone()
    assert result[0] is None

    result = con.execute("SELECT ratioValue(NULL)").fetchone()
    assert result[0] is None

    con.close()


def test_registration_all_functions():
    """Test that all ratio functions are properly registered."""
    con = duckdb.connect()
    registerRatioUdfs(con)

    ratio = '{"numerator": {"value": 10, "unit": "mg"}, "denominator": {"value": 2, "unit": "mL"}}'

    functions = [
        ("ratioNumeratorValue", [ratio], 10),
        ("ratioDenominatorValue", [ratio], 2),
        ("ratioValue", [ratio], 5.0),
        ("ratioNumeratorUnit", [ratio], "mg"),
        ("ratioDenominatorUnit", [ratio], "mL"),
    ]

    for func_name, params, expected in functions:
        result = con.execute(f"SELECT {func_name}({', '.join(['?'] * len(params))})", params).fetchone()
        assert result[0] == expected, f"{func_name} returned {result[0]}, expected {expected}"

    con.close()


# ========================================
# Edge case tests
# ========================================

def test_ratio_float_values():
    """Test ratio with float values."""
    ratio = '{"numerator": {"value": 7.5, "unit": "mg"}, "denominator": {"value": 2.5, "unit": "mL"}}'
    assert ratioNumeratorValue(ratio) == 7.5
    assert ratioDenominatorValue(ratio) == 2.5
    assert ratioValue(ratio) == 3.0


def test_ratio_negative_values():
    """Test ratio with negative values."""
    ratio = '{"numerator": {"value": -10, "unit": "mg"}, "denominator": {"value": 2, "unit": "mL"}}'
    assert ratioNumeratorValue(ratio) == -10
    assert ratioValue(ratio) == -5.0


def test_ratio_large_values():
    """Test ratio with large values."""
    ratio = '{"numerator": {"value": 1000000, "unit": "mg"}, "denominator": {"value": 1000, "unit": "mL"}}'
    assert ratioValue(ratio) == 1000.0


def test_ratio_empty_numerator():
    """Test ratio with empty numerator object."""
    ratio = '{"numerator": {}, "denominator": {"value": 1, "unit": "mL"}}'
    assert ratioNumeratorValue(ratio) is None
    assert ratioValue(ratio) is None


def test_ratio_empty_denominator():
    """Test ratio with empty denominator object."""
    ratio = '{"numerator": {"value": 5, "unit": "mg"}, "denominator": {}}'
    assert ratioDenominatorValue(ratio) is None
    assert ratioValue(ratio) is None


def test_ratio_prefers_unit_over_code():
    """Test that unit is preferred over code when both present."""
    ratio = '{"numerator": {"value": 5, "unit": "mg", "code": "should_be_ignored"}, "denominator": {"value": 1, "unit": "mL", "code": "ignored"}}'
    assert ratioNumeratorUnit(ratio) == "mg"
    assert ratioDenominatorUnit(ratio) == "mL"
