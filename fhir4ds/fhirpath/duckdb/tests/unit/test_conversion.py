"""
Unit tests for FHIRPath Type System & Conversion Functions.

Tests the conversion functions as defined in:
https://hl7.org/fhirpath/#types-and-reflection

Tests cover:
- Type operators (is, as)
- ofType function
- type function
- Conversion functions (toString, toInteger, toDecimal, toDateTime, toDate, toTime, toBoolean, toQuantity)
"""

from __future__ import annotations

from datetime import date, datetime, time
from decimal import Decimal

import pytest

from ...functions.conversion import (
    is_type,
    as_type,
    of_type,
    type_of,
    to_string,
    to_integer,
    to_decimal,
    to_date_time,
    to_date,
    to_time,
    to_boolean,
    to_quantity,
    resolve_type_name,
    get_type_name,
)


class TestResolveTypeName:
    """Tests for type name resolution."""

    def test_resolve_standard_types(self) -> None:
        """Test resolving standard FHIRPath type names."""
        assert resolve_type_name("integer") is not None
        assert resolve_type_name("INTEGER") is not None
        assert resolve_type_name("Integer") is not None
        assert resolve_type_name("decimal") is not None
        assert resolve_type_name("string") is not None
        assert resolve_type_name("boolean") is not None
        assert resolve_type_name("date") is not None
        assert resolve_type_name("dateTime") is not None
        assert resolve_type_name("time") is not None
        assert resolve_type_name("Quantity") is not None

    def test_resolve_type_aliases(self) -> None:
        """Test resolving type aliases."""
        assert resolve_type_name("int") is not None
        assert resolve_type_name("str") is not None
        assert resolve_type_name("bool") is not None
        assert resolve_type_name("num") is not None

    def test_resolve_invalid_type(self) -> None:
        """Test resolving invalid type name returns None."""
        assert resolve_type_name("InvalidType") is None
        assert resolve_type_name("") is None
        assert resolve_type_name("  ") is None


class TestGetTypeName:
    """Tests for getting type names from values."""

    def test_get_type_name_integer(self) -> None:
        """Test type name for integer."""
        assert get_type_name(42) == "integer"
        assert get_type_name(0) == "integer"
        assert get_type_name(-10) == "integer"

    def test_get_type_name_decimal(self) -> None:
        """Test type name for decimal."""
        assert get_type_name(3.14) == "decimal"
        assert get_type_name(0.0) == "decimal"
        assert get_type_name(Decimal("1.5")) == "decimal"

    def test_get_type_name_string(self) -> None:
        """Test type name for string."""
        assert get_type_name("hello") == "string"
        assert get_type_name("") == "string"

    def test_get_type_name_boolean(self) -> None:
        """Test type name for boolean."""
        assert get_type_name(True) == "boolean"
        assert get_type_name(False) == "boolean"

    def test_get_type_name_date(self) -> None:
        """Test type name for date."""
        assert get_type_name(date(2024, 1, 15)) == "date"

    def test_get_type_name_datetime(self) -> None:
        """Test type name for datetime."""
        assert get_type_name(datetime(2024, 1, 15, 10, 30, 0)) == "dateTime"

    def test_get_type_name_time(self) -> None:
        """Test type name for time."""
        assert get_type_name(time(10, 30, 0)) == "time"


class TestIsOperator:
    """Tests for the FHIRPath 'is' type operator."""

    def test_is_integer(self) -> None:
        """Test 'is integer' check."""
        assert is_type(42, "integer") is True
        assert is_type(0, "integer") is True
        assert is_type(-10, "integer") is True
        assert is_type(3.14, "integer") is False
        assert is_type("42", "integer") is False
        assert is_type(True, "integer") is False

    def test_is_decimal(self) -> None:
        """Test 'is decimal' check."""
        assert is_type(3.14, "decimal") is True
        assert is_type(0.0, "decimal") is True
        assert is_type(Decimal("1.5"), "decimal") is True
        # Integer is compatible with decimal per FHIRPath spec
        assert is_type(42, "decimal") is True

    def test_is_string(self) -> None:
        """Test 'is string' check."""
        assert is_type("hello", "string") is True
        assert is_type("", "string") is True
        assert is_type(42, "string") is False
        assert is_type(True, "string") is False

    def test_is_boolean(self) -> None:
        """Test 'is boolean' check."""
        assert is_type(True, "boolean") is True
        assert is_type(False, "boolean") is True
        assert is_type(1, "boolean") is False
        assert is_type("true", "boolean") is False

    def test_is_date(self) -> None:
        """Test 'is date' check."""
        assert is_type(date(2024, 1, 15), "date") is True
        assert is_type(datetime(2024, 1, 15, 10, 30), "date") is False
        assert is_type("2024-01-15", "date") is False

    def test_is_datetime(self) -> None:
        """Test 'is dateTime' check."""
        assert is_type(datetime(2024, 1, 15, 10, 30), "dateTime") is True
        assert is_type(date(2024, 1, 15), "dateTime") is False

    def test_is_time(self) -> None:
        """Test 'is time' check."""
        assert is_type(time(10, 30, 0), "time") is True
        assert is_type("10:30:00", "time") is False

    def test_is_quantity(self) -> None:
        """Test 'is Quantity' check."""
        quantity = {"value": 100, "unit": "mg"}
        assert is_type(quantity, "Quantity") is True

        quantity_with_system = {"value": 100, "unit": "mg", "system": "http://unitsofmeasure.org"}
        assert is_type(quantity_with_system, "Quantity") is True

        # Missing required fields
        assert is_type({"value": 100}, "Quantity") is False
        assert is_type({"unit": "mg"}, "Quantity") is False
        assert is_type(100, "Quantity") is False

    def test_is_coding(self) -> None:
        """Test 'is Coding' check."""
        coding = {"system": "http://loinc.org", "code": "123-4", "display": "Test"}
        assert is_type(coding, "Coding") is True

        coding_minimal = {"code": "123-4"}
        assert is_type(coding_minimal, "Coding") is True

        assert is_type({}, "Coding") is False
        assert is_type("code", "Coding") is False

    def test_is_codeable_concept(self) -> None:
        """Test 'is CodeableConcept' check."""
        cc = {"coding": [{"system": "http://loinc.org", "code": "123-4"}], "text": "Test"}
        assert is_type(cc, "CodeableConcept") is True

        cc_minimal = {"text": "Test"}
        assert is_type(cc_minimal, "CodeableConcept") is True

        assert is_type({}, "CodeableConcept") is False

    def test_is_empty(self) -> None:
        """Test 'is' with empty collection (None)."""
        assert is_type(None, "integer") is False
        assert is_type(None, "string") is False

    def test_is_case_insensitive(self) -> None:
        """Test that type names are case-insensitive."""
        assert is_type(42, "INTEGER") is True
        assert is_type(42, "Integer") is True
        assert is_type(42, "integer") is True
        assert is_type("hello", "STRING") is True
        assert is_type(True, "BOOLEAN") is True


class TestAsOperator:
    """Tests for the FHIRPath 'as' type operator."""

    def test_as_integer(self) -> None:
        """Test 'as integer' cast."""
        assert as_type(42, "integer") == 42
        assert as_type(-10, "integer") == -10
        assert as_type(3.14, "integer") is None  # Type mismatch
        assert as_type("42", "integer") is None  # Type mismatch

    def test_as_string(self) -> None:
        """Test 'as string' cast."""
        assert as_type("hello", "string") == "hello"
        assert as_type("", "string") == ""
        assert as_type(42, "string") is None  # Type mismatch

    def test_as_boolean(self) -> None:
        """Test 'as boolean' cast."""
        assert as_type(True, "boolean") is True
        assert as_type(False, "boolean") is False
        assert as_type(1, "boolean") is None  # Type mismatch

    def test_as_quantity(self) -> None:
        """Test 'as Quantity' cast."""
        quantity = {"value": 100, "unit": "mg"}
        assert as_type(quantity, "Quantity") == quantity
        assert as_type(100, "Quantity") is None

    def test_as_empty(self) -> None:
        """Test 'as' with empty collection."""
        assert as_type(None, "integer") is None
        assert as_type(None, "string") is None


class TestOfType:
    """Tests for the ofType() function."""

    def test_of_type_integer(self) -> None:
        """Test filtering by integer type."""
        collection = [1, 2, "three", 4, "five", 6]
        result = of_type(collection, "integer")
        assert result == [1, 2, 4, 6]

    def test_of_type_string(self) -> None:
        """Test filtering by string type."""
        collection = [1, "two", 3, "four", "five"]
        result = of_type(collection, "string")
        assert result == ["two", "four", "five"]

    def test_of_type_boolean(self) -> None:
        """Test filtering by boolean type."""
        collection = [True, 1, False, "true", True]
        result = of_type(collection, "boolean")
        assert result == [True, False, True]

    def test_of_type_decimal_includes_integer(self) -> None:
        """Test filtering by decimal includes integers (compatible types)."""
        collection = [1, 2.5, 3, 4.75]
        result = of_type(collection, "decimal")
        assert 2.5 in result
        assert 4.75 in result
        # Integers are compatible with decimal
        assert 1 in result
        assert 3 in result

    def test_of_type_quantity(self) -> None:
        """Test filtering by Quantity type."""
        collection = [
            {"value": 100, "unit": "mg"},
            42,
            {"value": 50, "unit": "ml"},
            "string",
        ]
        result = of_type(collection, "Quantity")
        assert len(result) == 2
        assert {"value": 100, "unit": "mg"} in result
        assert {"value": 50, "unit": "ml"} in result

    def test_of_type_empty(self) -> None:
        """Test ofType on empty collection."""
        assert of_type([], "integer") == []

    def test_of_type_no_matches(self) -> None:
        """Test ofType when no items match."""
        collection = [1, 2, 3]
        result = of_type(collection, "string")
        assert result == []


class TestTypeFunction:
    """Tests for the type() function."""

    def test_type_of_integer(self) -> None:
        """Test type of integer."""
        assert type_of(42) == "integer"

    def test_type_of_decimal(self) -> None:
        """Test type of decimal."""
        assert type_of(3.14) == "decimal"

    def test_type_of_string(self) -> None:
        """Test type of string."""
        assert type_of("hello") == "string"

    def test_type_of_boolean(self) -> None:
        """Test type of boolean."""
        assert type_of(True) == "boolean"
        assert type_of(False) == "boolean"

    def test_type_of_date(self) -> None:
        """Test type of date."""
        assert type_of(date(2024, 1, 15)) == "date"

    def test_type_of_datetime(self) -> None:
        """Test type of datetime."""
        assert type_of(datetime(2024, 1, 15, 10, 30)) == "dateTime"

    def test_type_of_time(self) -> None:
        """Test type of time."""
        assert type_of(time(10, 30, 0)) == "time"

    def test_type_of_empty(self) -> None:
        """Test type of empty (None)."""
        assert type_of(None) is None


class TestToString:
    """Tests for the toString() function."""

    def test_to_string_from_string(self) -> None:
        """Test toString from string."""
        assert to_string("hello") == "hello"
        assert to_string("") == ""

    def test_to_string_from_integer(self) -> None:
        """Test toString from integer."""
        assert to_string(42) == "42"
        assert to_string(0) == "0"
        assert to_string(-10) == "-10"

    def test_to_string_from_decimal(self) -> None:
        """Test toString from decimal."""
        assert to_string(3.14) == "3.14"
        assert to_string(Decimal("1.5")) == "1.5"

    def test_to_string_from_boolean(self) -> None:
        """Test toString from boolean."""
        assert to_string(True) == "true"
        assert to_string(False) == "false"

    def test_to_string_from_date(self) -> None:
        """Test toString from date."""
        assert to_string(date(2024, 1, 15)) == "2024-01-15"

    def test_to_string_from_datetime(self) -> None:
        """Test toString from datetime."""
        result = to_string(datetime(2024, 1, 15, 10, 30, 0))
        assert result == "2024-01-15T10:30:00"

    def test_to_string_from_time(self) -> None:
        """Test toString from time."""
        result = to_string(time(10, 30, 45))
        assert result == "10:30:45"

    def test_to_string_from_quantity(self) -> None:
        """Test toString from Quantity."""
        quantity = {"value": 100, "unit": "mg"}
        assert to_string(quantity) == "100 'mg'"

    def test_to_string_from_dict(self) -> None:
        """Test toString from dictionary."""
        d = {"key": "value"}
        assert to_string(d) == '{"key": "value"}'

    def test_to_string_from_list(self) -> None:
        """Test toString from list."""
        lst = [1, 2, 3]
        assert to_string(lst) == "[1, 2, 3]"

    def test_to_string_from_none(self) -> None:
        """Test toString from None."""
        assert to_string(None) is None

    def test_to_string_special_floats(self) -> None:
        """Test toString with special float values."""
        assert to_string(float("nan")) is None
        assert to_string(float("inf")) is None
        assert to_string(float("-inf")) is None


class TestToInteger:
    """Tests for the toInteger() function."""

    def test_to_integer_from_integer(self) -> None:
        """Test toInteger from integer."""
        assert to_integer(42) == 42
        assert to_integer(0) == 0
        assert to_integer(-10) == -10

    def test_to_integer_from_decimal(self) -> None:
        """Test toInteger from decimal (truncates toward zero)."""
        assert to_integer(3.14) == 3
        assert to_integer(3.99) == 3
        assert to_integer(-3.99) == -3

    def test_to_integer_from_string(self) -> None:
        """Test toInteger from string."""
        assert to_integer("42") == 42
        assert to_integer("-10") == -10
        assert to_integer("3.14") == 3  # Truncates
        assert to_integer("  42  ") == 42  # Trims whitespace

    def test_to_integer_from_boolean(self) -> None:
        """Test toInteger from boolean."""
        assert to_integer(True) == 1
        assert to_integer(False) == 0

    def test_to_integer_from_invalid_string(self) -> None:
        """Test toInteger from invalid string."""
        assert to_integer("hello") is None
        assert to_integer("") is None
        assert to_integer("  ") is None

    def test_to_integer_from_none(self) -> None:
        """Test toInteger from None."""
        assert to_integer(None) is None

    def test_to_integer_from_other_types(self) -> None:
        """Test toInteger from other types."""
        assert to_integer(date(2024, 1, 15)) is None
        assert to_integer([1, 2, 3]) is None


class TestToDecimal:
    """Tests for the toDecimal() function."""

    def test_to_decimal_from_integer(self) -> None:
        """Test toDecimal from integer."""
        assert to_decimal(42) == Decimal("42")
        assert to_decimal(0) == Decimal("0")

    def test_to_decimal_from_decimal(self) -> None:
        """Test toDecimal from decimal."""
        assert to_decimal(3.14) == Decimal(str(3.14))
        assert to_decimal(Decimal("1.5")) == Decimal("1.5")

    def test_to_decimal_from_string(self) -> None:
        """Test toDecimal from string."""
        assert to_decimal("3.14") == Decimal("3.14")
        assert to_decimal("-10.5") == Decimal("-10.5")
        assert to_decimal("  42.0  ") == Decimal("42.0")

    def test_to_decimal_from_boolean(self) -> None:
        """Test toDecimal from boolean."""
        assert to_decimal(True) == Decimal("1")
        assert to_decimal(False) == Decimal("0")

    def test_to_decimal_from_invalid_string(self) -> None:
        """Test toDecimal from invalid string."""
        assert to_decimal("hello") is None
        assert to_decimal("") is None
        assert to_decimal("  ") is None

    def test_to_decimal_from_none(self) -> None:
        """Test toDecimal from None."""
        assert to_decimal(None) is None


class TestToDateTime:
    """Tests for the toDateTime() function."""

    def test_to_datetime_from_datetime(self) -> None:
        """Test toDateTime from datetime."""
        dt = datetime(2024, 1, 15, 10, 30, 0)
        assert to_date_time(dt) == dt

    def test_to_datetime_from_date(self) -> None:
        """Test toDateTime from date (returns datetime at start of day)."""
        d = date(2024, 1, 15)
        result = to_date_time(d)
        assert result == datetime(2024, 1, 15, 0, 0, 0)

    def test_to_datetime_from_string_iso(self) -> None:
        """Test toDateTime from ISO format string."""
        result = to_date_time("2024-01-15T10:30:00")
        assert result == datetime(2024, 1, 15, 10, 30, 0)

    def test_to_datetime_from_string_with_timezone(self) -> None:
        """Test toDateTime from string with timezone."""
        result = to_date_time("2024-01-15T10:30:00Z")
        assert result is not None
        assert result.year == 2024
        assert result.month == 1
        assert result.day == 15

    def test_to_datetime_from_string_space_separated(self) -> None:
        """Test toDateTime from space-separated format."""
        result = to_date_time("2024-01-15 10:30:00")
        assert result == datetime(2024, 1, 15, 10, 30, 0)

    def test_to_datetime_from_invalid_string(self) -> None:
        """Test toDateTime from invalid string."""
        assert to_date_time("hello") is None
        assert to_date_time("") is None
        assert to_date_time("not-a-date") is None

    def test_to_datetime_from_none(self) -> None:
        """Test toDateTime from None."""
        assert to_date_time(None) is None

    def test_to_datetime_from_other_types(self) -> None:
        """Test toDateTime from other types."""
        assert to_date_time(42) is None
        assert to_date_time(True) is None


class TestToDate:
    """Tests for the toDate() function."""

    def test_to_date_from_date(self) -> None:
        """Test toDate from date."""
        d = date(2024, 1, 15)
        assert to_date(d) == d

    def test_to_date_from_datetime(self) -> None:
        """Test toDate from datetime (extracts date part)."""
        dt = datetime(2024, 1, 15, 10, 30, 0)
        assert to_date(dt) == date(2024, 1, 15)

    def test_to_date_from_string_iso(self) -> None:
        """Test toDate from ISO format string."""
        assert to_date("2024-01-15") == date(2024, 1, 15)

    def test_to_date_from_string_datetime(self) -> None:
        """Test toDate from datetime string (extracts date part)."""
        result = to_date("2024-01-15T10:30:00")
        assert result == date(2024, 1, 15)

    def test_to_date_from_partial_string(self) -> None:
        """Test toDate from partial date strings."""
        # Partial dates should return None per FHIRPath spec
        assert to_date("2024-01") is None
        assert to_date("2024") is None

    def test_to_date_from_invalid_string(self) -> None:
        """Test toDate from invalid string."""
        assert to_date("hello") is None
        assert to_date("") is None
        assert to_date("not-a-date") is None

    def test_to_date_from_none(self) -> None:
        """Test toDate from None."""
        assert to_date(None) is None


class TestToTime:
    """Tests for the toTime() function."""

    def test_to_time_from_time(self) -> None:
        """Test toTime from time."""
        t = time(10, 30, 45)
        assert to_time(t) == t

    def test_to_time_from_datetime(self) -> None:
        """Test toTime from datetime (extracts time part)."""
        dt = datetime(2024, 1, 15, 10, 30, 45)
        assert to_time(dt) == time(10, 30, 45)

    def test_to_time_from_string_iso(self) -> None:
        """Test toTime from ISO format string."""
        result = to_time("10:30:45")
        assert result == time(10, 30, 45)

    def test_to_time_from_string_with_timezone(self) -> None:
        """Test toTime from string with timezone."""
        result = to_time("10:30:45Z")
        assert result == time(10, 30, 45)

    def test_to_time_from_string_datetime(self) -> None:
        """Test toTime from datetime string (extracts time part)."""
        result = to_time("2024-01-15T10:30:45")
        assert result == time(10, 30, 45)

    def test_to_time_from_partial_string(self) -> None:
        """Test toTime from partial time string."""
        result = to_time("10:30")
        assert result == time(10, 30, 0)

    def test_to_time_from_invalid_string(self) -> None:
        """Test toTime from invalid string."""
        assert to_time("hello") is None
        assert to_time("") is None

    def test_to_time_from_none(self) -> None:
        """Test toTime from None."""
        assert to_time(None) is None


class TestToBoolean:
    """Tests for the toBoolean() function."""

    def test_to_boolean_from_boolean(self) -> None:
        """Test toBoolean from boolean."""
        assert to_boolean(True) is True
        assert to_boolean(False) is False

    def test_to_boolean_from_integer(self) -> None:
        """Test toBoolean from integer."""
        assert to_boolean(1) is True
        assert to_boolean(0) is False
        assert to_boolean(42) is True
        assert to_boolean(-1) is True

    def test_to_boolean_from_decimal(self) -> None:
        """Test toBoolean from decimal."""
        assert to_boolean(1.0) is True
        assert to_boolean(0.0) is False
        assert to_boolean(3.14) is True

    def test_to_boolean_from_string_true(self) -> None:
        """Test toBoolean from string 'true'."""
        assert to_boolean("true") is True
        assert to_boolean("TRUE") is True
        assert to_boolean("True") is True
        assert to_boolean("  true  ") is True

    def test_to_boolean_from_string_false(self) -> None:
        """Test toBoolean from string 'false'."""
        assert to_boolean("false") is False
        assert to_boolean("FALSE") is False
        assert to_boolean("False") is False

    def test_to_boolean_from_string_numbers(self) -> None:
        """Test toBoolean from string numbers."""
        assert to_boolean("1") is True
        assert to_boolean("0") is False
        assert to_boolean("2.5") is True

    def test_to_boolean_from_string_yes_no(self) -> None:
        """Test toBoolean from string yes/no."""
        assert to_boolean("yes") is True
        assert to_boolean("no") is False
        assert to_boolean("YES") is True
        assert to_boolean("NO") is False

    def test_to_boolean_from_invalid_string(self) -> None:
        """Test toBoolean from invalid string."""
        assert to_boolean("hello") is None
        assert to_boolean("") is None
        assert to_boolean("  ") is None

    def test_to_boolean_from_none(self) -> None:
        """Test toBoolean from None."""
        assert to_boolean(None) is None


class TestToQuantity:
    """Tests for the toQuantity() function."""

    def test_to_quantity_from_quantity(self) -> None:
        """Test toQuantity from Quantity."""
        quantity = {"value": 100, "unit": "mg"}
        result = to_quantity(quantity)
        assert result == {"value": 100, "unit": "mg"}

    def test_to_quantity_from_quantity_with_code(self) -> None:
        """Test toQuantity from Quantity with code instead of unit."""
        quantity = {"value": 100, "code": "mg"}
        result = to_quantity(quantity)
        assert result["value"] == 100
        assert result["unit"] == "mg"

    def test_to_quantity_from_integer(self) -> None:
        """Test toQuantity from integer."""
        result = to_quantity(100)
        assert result == {"value": 100, "unit": ""}

    def test_to_quantity_from_decimal(self) -> None:
        """Test toQuantity from decimal."""
        result = to_quantity(3.14)
        assert result == {"value": 3.14, "unit": ""}

    def test_to_quantity_from_string_with_unit(self) -> None:
        """Test toQuantity from string with unit."""
        result = to_quantity("100 'mg'")
        assert result == {"value": 100.0, "unit": "mg"}

        result = to_quantity('50 "ml"')
        assert result == {"value": 50.0, "unit": "ml"}

    def test_to_quantity_from_string_without_unit(self) -> None:
        """Test toQuantity from string without unit."""
        result = to_quantity("100")
        assert result == {"value": 100.0, "unit": ""}

    def test_to_quantity_from_string_with_bare_unit(self) -> None:
        """Test toQuantity from string with bare unit (no quotes)."""
        result = to_quantity("100 mg")
        assert result == {"value": 100.0, "unit": "mg"}

    def test_to_quantity_from_boolean(self) -> None:
        """Test toQuantity from boolean."""
        assert to_quantity(True) == {"value": 1, "unit": ""}
        assert to_quantity(False) == {"value": 0, "unit": ""}

    def test_to_quantity_with_target_unit(self) -> None:
        """Test toQuantity with target unit parameter."""
        result = to_quantity(100, "kg")
        assert result == {"value": 100, "unit": "kg"}

    def test_to_quantity_from_invalid_string(self) -> None:
        """Test toQuantity from invalid string."""
        assert to_quantity("hello") is None
        assert to_quantity("") is None

    def test_to_quantity_from_none(self) -> None:
        """Test toQuantity from None."""
        assert to_quantity(None) is None

    def test_to_quantity_from_other_types(self) -> None:
        """Test toQuantity from other types."""
        assert to_quantity(date(2024, 1, 15)) is None

    def test_to_quantity_preserves_optional_fields(self) -> None:
        """Test toQuantity preserves optional Quantity fields."""
        quantity = {
            "value": 100,
            "unit": "mg",
            "system": "http://unitsofmeasure.org",
            "code": "mg",
            "comparator": ">",
        }
        result = to_quantity(quantity)
        assert result["system"] == "http://unitsofmeasure.org"
        assert result["code"] == "mg"
        assert result["comparator"] == ">"
