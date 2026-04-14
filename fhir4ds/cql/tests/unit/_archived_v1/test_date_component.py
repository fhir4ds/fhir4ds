"""
Unit tests for DateComponent translation.

Tests that CQL date component extraction (year from, month from, etc.)
translates correctly to FHIRPath dateComponent() calls.
"""

import pytest

from ....parser.ast_nodes import (
    DateComponent,
    DateTimeLiteral,
    Identifier,
    Literal,
    Property,
)
from ....translator import CQLTranslator


class TestDateComponentTranslation:
    """Tests for DateComponent expression translation."""

    def test_year_from_datetime_literal(self):
        """Test 'year from @2024-01-15' translation.

        CQL: year from @2024-01-15
        FHIRPath: dateComponent(@2024-01-15, 'year')
        """
        translator = CQLTranslator()

        expr = DateComponent(
            component="year",
            operand=DateTimeLiteral(value="2024-01-15"),
        )

        result = translator.translate_expression(expr)
        assert result == "dateComponent(@2024-01-15, 'year')"

    def test_month_from_datetime_literal(self):
        """Test 'month from @2024-06-15' translation.

        CQL: month from @2024-06-15
        FHIRPath: dateComponent(@2024-06-15, 'month')
        """
        translator = CQLTranslator()

        expr = DateComponent(
            component="month",
            operand=DateTimeLiteral(value="2024-06-15"),
        )

        result = translator.translate_expression(expr)
        assert result == "dateComponent(@2024-06-15, 'month')"

    def test_day_from_datetime_literal(self):
        """Test 'day from @2024-01-15' translation.

        CQL: day from @2024-01-15
        FHIRPath: dateComponent(@2024-01-15, 'day')
        """
        translator = CQLTranslator()

        expr = DateComponent(
            component="day",
            operand=DateTimeLiteral(value="2024-01-15"),
        )

        result = translator.translate_expression(expr)
        assert result == "dateComponent(@2024-01-15, 'day')"

    def test_hour_from_datetime(self):
        """Test 'hour from @2024-01-15T14:30:00' translation.

        CQL: hour from @2024-01-15T14:30:00
        FHIRPath: dateComponent(@2024-01-15T14:30:00, 'hour')
        """
        translator = CQLTranslator()

        expr = DateComponent(
            component="hour",
            operand=DateTimeLiteral(value="2024-01-15T14:30:00"),
        )

        result = translator.translate_expression(expr)
        assert result == "dateComponent(@2024-01-15T14:30:00, 'hour')"

    def test_minute_from_datetime(self):
        """Test 'minute from @2024-01-15T14:30:45' translation.

        CQL: minute from @2024-01-15T14:30:45
        FHIRPath: dateComponent(@2024-01-15T14:30:45, 'minute')
        """
        translator = CQLTranslator()

        expr = DateComponent(
            component="minute",
            operand=DateTimeLiteral(value="2024-01-15T14:30:45"),
        )

        result = translator.translate_expression(expr)
        assert result == "dateComponent(@2024-01-15T14:30:45, 'minute')"

    def test_second_from_datetime(self):
        """Test 'second from @2024-01-15T14:30:45' translation.

        CQL: second from @2024-01-15T14:30:45
        FHIRPath: dateComponent(@2024-01-15T14:30:45, 'second')
        """
        translator = CQLTranslator()

        expr = DateComponent(
            component="second",
            operand=DateTimeLiteral(value="2024-01-15T14:30:45"),
        )

        result = translator.translate_expression(expr)
        assert result == "dateComponent(@2024-01-15T14:30:45, 'second')"

    def test_year_from_property(self):
        """Test 'year from Patient.birthDate' translation.

        CQL: year from Patient.birthDate
        FHIRPath: dateComponent(__retrieve__:Patient.birthDate, 'year')

        Note: Patient is translated to __retrieve__:Patient as it's
        a context reference.
        """
        translator = CQLTranslator()

        expr = DateComponent(
            component="year",
            operand=Property(
                source=Identifier(name="Patient"),
                path="birthDate",
            ),
        )

        result = translator.translate_expression(expr)
        assert result == "dateComponent(__retrieve__:Patient.birthDate, 'year')"

    def test_month_from_identifier(self):
        """Test 'month from X' translation where X is an identifier.

        CQL: month from MeasurementPeriod
        FHIRPath: dateComponent(%MeasurementPeriod, 'month')
        """
        translator = CQLTranslator()

        expr = DateComponent(
            component="month",
            operand=Identifier(name="MeasurementPeriod"),
        )

        result = translator.translate_expression(expr)
        # Identifiers are translated with % prefix for definitions
        assert "dateComponent(" in result
        assert "'month'" in result
