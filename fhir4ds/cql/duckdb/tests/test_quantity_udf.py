"""
Unit tests for CQL Quantity Arithmetic UDFs.

Tests for quantity operations:
- parseQuantity, quantityValue, quantityUnit
- quantityCompare (same units, different units, incompatible units)
- quantityAdd, quantitySubtract
- quantityConvert
"""

import json

import pytest
import duckdb

from ..udf.quantity import (
    parseQuantity,
    quantityValue,
    quantityUnit,
    quantityCompare,
    quantityAdd,
    quantitySubtract,
    quantityConvert,
    registerQuantityUdfs,
)


# ========================================
# Fixtures
# ========================================


@pytest.fixture
def bp_systolic():
    """Blood pressure systolic measurement: 140 mmHg."""
    return '{"value": 140, "code": "mm[Hg]", "system": "http://unitsofmeasure.org"}'


@pytest.fixture
def bp_diastolic():
    """Blood pressure diastolic measurement: 120 mmHg."""
    return '{"value": 120, "code": "mm[Hg]", "system": "http://unitsofmeasure.org"}'


@pytest.fixture
def weight_grams():
    """Weight in grams: 1 g."""
    return '{"value": 1, "code": "g"}'


@pytest.fixture
def weight_mg():
    """Weight in milligrams: 500 mg."""
    return '{"value": 500, "code": "mg"}'


# ========================================
# parseQuantity tests
# ========================================


def test_parse_quantity_valid(bp_systolic):
    """Test parsing valid quantity JSON."""
    result = parseQuantity(bp_systolic)
    assert result is not None
    parsed = json.loads(result)
    assert parsed["value"] == 140
    assert parsed["code"] == "mm[Hg]"


def test_parse_quantity_null():
    """Test parsing null input."""
    assert parseQuantity(None) is None


def test_parse_quantity_empty():
    """Test parsing empty string."""
    assert parseQuantity("") is None


def test_parse_quantity_invalid_json():
    """Test parsing invalid JSON."""
    assert parseQuantity("not json") is None


def test_parse_quantity_missing_value():
    """Test parsing quantity with missing value."""
    q = '{"code": "mg"}'
    result = parseQuantity(q)
    assert result is not None
    parsed = json.loads(result)
    assert parsed["value"] is None


# ========================================
# quantityValue tests
# ========================================


def test_quantity_value_valid(bp_systolic):
    """Test extracting value from valid quantity."""
    result = quantityValue(bp_systolic)
    assert result == 140.0


def test_quantity_value_null():
    """Test extracting value from null."""
    assert quantityValue(None) is None


def test_quantity_value_empty():
    """Test extracting value from empty string."""
    assert quantityValue("") is None


def test_quantity_value_missing():
    """Test extracting value when missing."""
    q = '{"code": "mg"}'
    assert quantityValue(q) is None


# ========================================
# quantityUnit tests
# ========================================


def test_quantity_unit_valid(bp_systolic):
    """Test extracting unit from valid quantity."""
    result = quantityUnit(bp_systolic)
    assert result == "mm[Hg]"


def test_quantity_unit_null():
    """Test extracting unit from null."""
    assert quantityUnit(None) is None


def test_quantity_unit_empty():
    """Test extracting unit from empty string."""
    assert quantityUnit("") is None


def test_quantity_unit_uses_unit_field():
    """Test that 'unit' field is used if 'code' is missing."""
    q = '{"value": 100, "unit": "kg"}'
    result = quantityUnit(q)
    assert result == "kg"


# ========================================
# quantityCompare tests - Same Units
# ========================================


def test_quantity_compare_same_units_greater(bp_systolic, bp_diastolic):
    """Test comparison with same units - greater than."""
    result = quantityCompare(bp_systolic, bp_diastolic, ">")
    assert result is True


def test_quantity_compare_same_units_less(bp_systolic, bp_diastolic):
    """Test comparison with same units - less than."""
    result = quantityCompare(bp_diastolic, bp_systolic, "<")
    assert result is True


def test_quantity_compare_same_units_greater_equal():
    """Test comparison with same units - greater or equal."""
    q1 = '{"value": 140, "code": "mm[Hg]"}'
    q2 = '{"value": 140, "code": "mm[Hg]"}'
    result = quantityCompare(q1, q2, ">=")
    assert result is True


def test_quantity_compare_same_units_less_equal():
    """Test comparison with same units - less or equal."""
    q1 = '{"value": 140, "code": "mm[Hg]"}'
    q2 = '{"value": 140, "code": "mm[Hg]"}'
    result = quantityCompare(q1, q2, "<=")
    assert result is True


def test_quantity_compare_same_units_equal():
    """Test comparison with same units - equal."""
    q1 = '{"value": 140, "code": "mm[Hg]"}'
    q2 = '{"value": 140, "code": "mm[Hg]"}'
    result = quantityCompare(q1, q2, "==")
    assert result is True


def test_quantity_compare_same_units_not_equal(bp_systolic, bp_diastolic):
    """Test comparison with same units - not equal."""
    result = quantityCompare(bp_systolic, bp_diastolic, "!=")
    assert result is True


# ========================================
# quantityCompare tests - Different Units
# ========================================


def test_quantity_compare_different_units_greater(weight_grams, weight_mg):
    """Test comparison with different but compatible units - greater than."""
    # 1g = 1000mg > 500mg
    result = quantityCompare(weight_grams, weight_mg, ">")
    assert result is True


def test_quantity_compare_different_units_less(weight_grams, weight_mg):
    """Test comparison with different but compatible units - less than."""
    # 500mg < 1g (1000mg)
    result = quantityCompare(weight_mg, weight_grams, "<")
    assert result is True


def test_quantity_compare_different_units_equal():
    """Test comparison with different but compatible units - equal."""
    # 1g = 1000mg
    q1 = '{"value": 1, "code": "g"}'
    q2 = '{"value": 1000, "code": "mg"}'
    result = quantityCompare(q1, q2, "==")
    assert result is True


# ========================================
# quantityCompare tests - Incompatible Units
# ========================================


def test_quantity_compare_incompatible_units():
    """Test comparison with incompatible units returns NULL."""
    # mg/dL and mm[Hg] are incompatible
    q1 = '{"value": 100, "code": "mg/dL"}'
    q2 = '{"value": 120, "code": "mm[Hg]"}'
    result = quantityCompare(q1, q2, ">")
    assert result is None


def test_quantity_compare_incompatible_units_mass_volume():
    """Test comparison mass vs volume returns NULL."""
    q1 = '{"value": 100, "code": "kg"}'
    q2 = '{"value": 100, "code": "L"}'
    result = quantityCompare(q1, q2, ">")
    assert result is None


# ========================================
# quantityAdd tests
# ========================================


def test_quantity_add_same_units():
    """Test addition with same units."""
    q1 = '{"value": 5, "code": "mg"}'
    q2 = '{"value": 3, "code": "mg"}'
    result = quantityAdd(q1, q2)
    assert result is not None
    parsed = json.loads(result)
    assert parsed["value"] == 8.0
    assert parsed["code"] == "mg"


def test_quantity_add_different_units():
    """Test addition with different but compatible units."""
    q1 = '{"value": 1, "code": "g"}'  # 1000 mg
    q2 = '{"value": 500, "code": "mg"}'  # 500 mg
    result = quantityAdd(q1, q2)
    assert result is not None
    parsed = json.loads(result)
    # Result should be 1500 mg (in grams since q1 is in g)
    assert parsed["value"] == 1.5  # 1g + 0.5g = 1.5g
    assert parsed["code"] == "g"


def test_quantity_add_incompatible_units():
    """Test addition with incompatible units returns NULL."""
    q1 = '{"value": 100, "code": "kg"}'
    q2 = '{"value": 50, "code": "mm[Hg]"}'
    result = quantityAdd(q1, q2)
    assert result is None


def test_quantity_add_null_first():
    """Test addition with null first operand."""
    q2 = '{"value": 5, "code": "mg"}'
    result = quantityAdd(None, q2)
    assert result is None


def test_quantity_add_null_second():
    """Test addition with null second operand."""
    q1 = '{"value": 5, "code": "mg"}'
    result = quantityAdd(q1, None)
    assert result is None


# ========================================
# quantitySubtract tests
# ========================================


def test_quantity_subtract_same_units():
    """Test subtraction with same units."""
    q1 = '{"value": 10, "code": "mg"}'
    q2 = '{"value": 3, "code": "mg"}'
    result = quantitySubtract(q1, q2)
    assert result is not None
    parsed = json.loads(result)
    assert parsed["value"] == 7.0
    assert parsed["code"] == "mg"


def test_quantity_subtract_different_units():
    """Test subtraction with different but compatible units."""
    q1 = '{"value": 2, "code": "g"}'  # 2000 mg
    q2 = '{"value": 500, "code": "mg"}'  # 500 mg
    result = quantitySubtract(q1, q2)
    assert result is not None
    parsed = json.loads(result)
    # Result should be 1.5 g
    assert parsed["value"] == 1.5
    assert parsed["code"] == "g"


def test_quantity_subtract_incompatible_units():
    """Test subtraction with incompatible units returns NULL."""
    q1 = '{"value": 100, "code": "kg"}'
    q2 = '{"value": 50, "code": "mm[Hg]"}'
    result = quantitySubtract(q1, q2)
    assert result is None


def test_quantity_subtract_null():
    """Test subtraction with null operand."""
    q1 = '{"value": 10, "code": "mg"}'
    result = quantitySubtract(q1, None)
    assert result is None


# ========================================
# quantityConvert tests
# ========================================


def test_quantity_convert_grams_to_mg():
    """Test converting grams to milligrams."""
    q = '{"value": 1, "code": "g"}'
    result = quantityConvert(q, "mg")
    assert result is not None
    parsed = json.loads(result)
    assert parsed["value"] == 1000.0
    assert parsed["code"] == "mg"


def test_quantity_convert_mg_to_grams():
    """Test converting milligrams to grams."""
    q = '{"value": 500, "code": "mg"}'
    result = quantityConvert(q, "g")
    assert result is not None
    parsed = json.loads(result)
    assert parsed["value"] == 0.5
    assert parsed["code"] == "g"


def test_quantity_convert_same_unit():
    """Test converting to same unit."""
    q = '{"value": 100, "code": "mg"}'
    result = quantityConvert(q, "mg")
    assert result is not None
    parsed = json.loads(result)
    assert parsed["value"] == 100.0


def test_quantity_convert_incompatible():
    """Test converting between incompatible units returns NULL."""
    q = '{"value": 100, "code": "kg"}'
    result = quantityConvert(q, "mm[Hg]")
    assert result is None


def test_quantity_convert_null():
    """Test converting null quantity."""
    result = quantityConvert(None, "mg")
    assert result is None


# ========================================
# DuckDB Registration tests
# ========================================


def test_registration():
    """Test that UDFs can be registered with DuckDB."""
    import duckdb

    con = duckdb.connect()
    registerQuantityUdfs(con)

    q1 = '{"value": 140, "code": "mm[Hg]"}'
    q2 = '{"value": 120, "code": "mm[Hg]"}'

    # Test quantityValue
    result = con.execute("SELECT quantityValue(?)", [q1]).fetchone()
    assert result[0] == 140.0

    # Test quantityUnit
    result = con.execute("SELECT quantityUnit(?)", [q1]).fetchone()
    assert result[0] == "mm[Hg]"

    # Test quantityCompare
    result = con.execute("SELECT quantityCompare(?, ?, '>')", [q1, q2]).fetchone()
    assert result[0] is True

    con.close()


def test_registration_all_functions():
    """Test that all quantity functions are properly registered."""
    import duckdb

    con = duckdb.connect()
    registerQuantityUdfs(con)

    q1 = '{"value": 5, "code": "mg"}'
    q2 = '{"value": 3, "code": "mg"}'

    functions = [
        ("parseQuantity", [q1]),
        ("quantityValue", [q1]),
        ("quantityUnit", [q1]),
        ("quantityCompare", [q1, q2, ">"]),
        ("quantityAdd", [q1, q2]),
        ("quantitySubtract", [q1, q2]),
        ("quantityConvert", [q1, "g"]),
    ]

    for func_name, params in functions:
        result = con.execute(
            f"SELECT {func_name}({', '.join(['?'] * len(params))})", params
        ).fetchone()
        # Should not raise an error
        assert result is not None

    con.close()


def test_registration_fails_fast_without_pint(monkeypatch):
    """Quantity UDF registration should fail clearly if pint is unavailable."""
    con = duckdb.connect()
    monkeypatch.setattr("fhir4ds.cql.duckdb.udf.quantity._get_ureg", lambda: None)

    with pytest.raises(ImportError, match="pint"):
        registerQuantityUdfs(con)

    con.close()


# ========================================
# Edge case tests
# ========================================


def test_quantity_with_unit_field():
    """Test quantity using 'unit' instead of 'code'."""
    q = '{"value": 100, "unit": "kg"}'
    assert quantityValue(q) == 100.0
    assert quantityUnit(q) == "kg"


def test_quantity_negative_value():
    """Test quantity with negative value."""
    q = '{"value": -10, "code": "mg"}'
    assert quantityValue(q) == -10.0


def test_quantity_float_value():
    """Test quantity with float value."""
    q = '{"value": 3.14159, "code": "mg"}'
    result = quantityValue(q)
    assert abs(result - 3.14159) < 0.0001


def test_quantity_compare_null_operand():
    """Test comparison with null operand."""
    q = '{"value": 100, "code": "mg"}'
    assert quantityCompare(q, None, ">") is None
    assert quantityCompare(None, q, ">") is None


def test_quantity_compare_invalid_operator():
    """Test comparison with invalid operator."""
    q1 = '{"value": 100, "code": "mg"}'
    q2 = '{"value": 50, "code": "mg"}'
    assert quantityCompare(q1, q2, "invalid") is None
