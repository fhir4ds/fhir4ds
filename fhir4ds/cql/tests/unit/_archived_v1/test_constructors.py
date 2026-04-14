"""
Unit tests for constructor functions.

Tests parsing and translation of DateTime, Date, Time, and LastPositionOf
constructor functions.
"""

import pytest

from ....parser.ast_nodes import (
    FunctionRef,
    Identifier,
    Literal,
)
from ....translator import CQLTranslator


class TestDateTimeConstructor:
    """Tests for DateTime() constructor translation."""

    @pytest.fixture
    def translator(self) -> CQLTranslator:
        """Create a translator instance for testing."""
        return CQLTranslator()

    def test_datetime_basic(self, translator: CQLTranslator):
        """Test DateTime(2024, 1, 15)."""
        result = translator.translate_expression(
            FunctionRef(
                name="DateTime",
                arguments=[Literal(value=2024), Literal(value=1), Literal(value=15)],
            )
        )
        assert "@" in result
        assert "2024" in result

    def test_datetime_with_time(self, translator: CQLTranslator):
        """Test DateTime(2024, 1, 15, 10, 30, 45)."""
        result = translator.translate_expression(
            FunctionRef(
                name="DateTime",
                arguments=[
                    Literal(value=2024),
                    Literal(value=1),
                    Literal(value=15),
                    Literal(value=10),
                    Literal(value=30),
                    Literal(value=45),
                ],
            )
        )
        assert "@" in result
        assert "2024" in result
        assert "10" in result
        assert "30" in result
        assert "45" in result

    def test_datetime_with_expressions(self, translator: CQLTranslator):
        """Test DateTime with variable arguments."""
        result = translator.translate_expression(
            FunctionRef(
                name="DateTime",
                arguments=[
                    Identifier(name="year"),
                    Identifier(name="month"),
                    Identifier(name="day"),
                ],
            )
        )
        assert "@" in result
        assert "year" in result
        assert "month" in result
        assert "day" in result

    def test_datetime_with_hour_only(self, translator: CQLTranslator):
        """Test DateTime with date and hour only."""
        result = translator.translate_expression(
            FunctionRef(
                name="DateTime",
                arguments=[
                    Literal(value=2024),
                    Literal(value=6),
                    Literal(value=15),
                    Literal(value=14),
                ],
            )
        )
        assert "@" in result
        assert "2024" in result

    def test_datetime_with_hour_minute(self, translator: CQLTranslator):
        """Test DateTime with date, hour, and minute."""
        result = translator.translate_expression(
            FunctionRef(
                name="DateTime",
                arguments=[
                    Literal(value=2024),
                    Literal(value=6),
                    Literal(value=15),
                    Literal(value=14),
                    Literal(value=30),
                ],
            )
        )
        assert "@" in result
        assert "2024" in result

    def test_datetime_full_precision(self, translator: CQLTranslator):
        """Test DateTime with full precision including milliseconds."""
        result = translator.translate_expression(
            FunctionRef(
                name="DateTime",
                arguments=[
                    Literal(value=2024),
                    Literal(value=12),
                    Literal(value=25),
                    Literal(value=23),
                    Literal(value=59),
                    Literal(value=59),
                    Literal(value=999),
                ],
            )
        )
        assert "@" in result
        assert "2024" in result

    def test_datetime_case_insensitive(self, translator: CQLTranslator):
        """Test that DateTime is case-insensitive."""
        result = translator.translate_expression(
            FunctionRef(
                name="datetime",
                arguments=[Literal(value=2024), Literal(value=1), Literal(value=15)],
            )
        )
        assert "@" in result

    def test_datetime_with_identifier_year(self, translator: CQLTranslator):
        """Test DateTime with identifier for year."""
        result = translator.translate_expression(
            FunctionRef(
                name="DateTime",
                arguments=[
                    Identifier(name="birthYear"),
                    Literal(value=1),
                    Literal(value=1),
                ],
            )
        )
        assert "@" in result
        assert "birthYear" in result


class TestDateConstructor:
    """Tests for Date() constructor translation."""

    @pytest.fixture
    def translator(self) -> CQLTranslator:
        """Create a translator instance for testing."""
        return CQLTranslator()

    def test_date_basic(self, translator: CQLTranslator):
        """Test Date(2024, 1, 15)."""
        result = translator.translate_expression(
            FunctionRef(
                name="Date",
                arguments=[Literal(value=2024), Literal(value=1), Literal(value=15)],
            )
        )
        assert "@" in result
        assert "2024" in result

    def test_date_with_variables(self, translator: CQLTranslator):
        """Test Date(year, month, day)."""
        result = translator.translate_expression(
            FunctionRef(
                name="Date",
                arguments=[
                    Identifier(name="year"),
                    Identifier(name="month"),
                    Identifier(name="day"),
                ],
            )
        )
        assert "@" in result
        assert "year" in result

    def test_date_january_first(self, translator: CQLTranslator):
        """Test Date for January 1st."""
        result = translator.translate_expression(
            FunctionRef(
                name="Date",
                arguments=[Literal(value=2024), Literal(value=1), Literal(value=1)],
            )
        )
        assert "@" in result
        assert "2024" in result

    def test_date_december_thirty_first(self, translator: CQLTranslator):
        """Test Date for December 31st."""
        result = translator.translate_expression(
            FunctionRef(
                name="Date",
                arguments=[Literal(value=2024), Literal(value=12), Literal(value=31)],
            )
        )
        assert "@" in result
        assert "2024" in result

    def test_date_case_insensitive(self, translator: CQLTranslator):
        """Test that Date is case-insensitive."""
        result = translator.translate_expression(
            FunctionRef(
                name="date",
                arguments=[Literal(value=2024), Literal(value=1), Literal(value=15)],
            )
        )
        assert "@" in result

    def test_date_with_mixed_args(self, translator: CQLTranslator):
        """Test Date with mixed literal and identifier args."""
        result = translator.translate_expression(
            FunctionRef(
                name="Date",
                arguments=[Literal(value=2024), Identifier(name="month"), Literal(value=15)],
            )
        )
        assert "@" in result
        assert "month" in result


class TestTimeConstructor:
    """Tests for Time() constructor translation."""

    @pytest.fixture
    def translator(self) -> CQLTranslator:
        """Create a translator instance for testing."""
        return CQLTranslator()

    def test_time_basic(self, translator: CQLTranslator):
        """Test Time(14, 30, 0)."""
        result = translator.translate_expression(
            FunctionRef(
                name="Time",
                arguments=[Literal(value=14), Literal(value=30), Literal(value=0)],
            )
        )
        assert "@" in result or "T" in result

    def test_time_with_millisecond(self, translator: CQLTranslator):
        """Test Time(14, 30, 0, 500)."""
        result = translator.translate_expression(
            FunctionRef(
                name="Time",
                arguments=[Literal(value=14), Literal(value=30), Literal(value=0), Literal(value=500)],
            )
        )
        assert "500" in result

    def test_time_with_variables(self, translator: CQLTranslator):
        """Test Time with variable arguments."""
        result = translator.translate_expression(
            FunctionRef(
                name="Time",
                arguments=[
                    Identifier(name="hour"),
                    Identifier(name="minute"),
                    Identifier(name="second"),
                ],
            )
        )
        assert "@" in result or "T" in result

    def test_time_midnight(self, translator: CQLTranslator):
        """Test Time for midnight."""
        result = translator.translate_expression(
            FunctionRef(
                name="Time",
                arguments=[Literal(value=0), Literal(value=0), Literal(value=0)],
            )
        )
        assert "@" in result or "T" in result

    def test_time_noon(self, translator: CQLTranslator):
        """Test Time for noon."""
        result = translator.translate_expression(
            FunctionRef(
                name="Time",
                arguments=[Literal(value=12), Literal(value=0), Literal(value=0)],
            )
        )
        assert "@" in result or "T" in result

    def test_time_end_of_day(self, translator: CQLTranslator):
        """Test Time for end of day (23:59:59)."""
        result = translator.translate_expression(
            FunctionRef(
                name="Time",
                arguments=[Literal(value=23), Literal(value=59), Literal(value=59)],
            )
        )
        assert "@" in result or "T" in result

    def test_time_case_insensitive(self, translator: CQLTranslator):
        """Test that Time is case-insensitive."""
        result = translator.translate_expression(
            FunctionRef(
                name="time",
                arguments=[Literal(value=14), Literal(value=30), Literal(value=0)],
            )
        )
        assert "@" in result or "T" in result

    def test_time_with_identifier_hour(self, translator: CQLTranslator):
        """Test Time with identifier for hour."""
        result = translator.translate_expression(
            FunctionRef(
                name="Time",
                arguments=[Identifier(name="hour"), Literal(value=0), Literal(value=0)],
            )
        )
        assert "@" in result or "T" in result


class TestLastPositionOf:
    """Tests for LastPositionOf() function translation."""

    @pytest.fixture
    def translator(self) -> CQLTranslator:
        """Create a translator instance for testing."""
        return CQLTranslator()

    def test_last_position_of_basic(self, translator: CQLTranslator):
        """Test LastPositionOf('a', 'banana')."""
        result = translator.translate_expression(
            FunctionRef(
                name="LastPositionOf",
                arguments=[Literal(value="a"), Literal(value="banana")],
            )
        )
        assert "lastIndexOf" in result

    def test_last_position_of_translation(self, translator: CQLTranslator):
        """Test translation to lastIndexOf()."""
        result = translator.translate_expression(
            FunctionRef(
                name="LastPositionOf",
                arguments=[Literal(value="x"), Literal(value="text")],
            )
        )
        assert "lastIndexOf" in result

    def test_last_position_of_with_identifiers(self, translator: CQLTranslator):
        """Test LastPositionOf with identifier arguments."""
        result = translator.translate_expression(
            FunctionRef(
                name="LastPositionOf",
                arguments=[Identifier(name="pattern"), Identifier(name="source")],
            )
        )
        assert "lastIndexOf" in result
        assert "pattern" in result
        assert "source" in result

    def test_last_position_of_multichar_pattern(self, translator: CQLTranslator):
        """Test LastPositionOf with multi-character pattern."""
        result = translator.translate_expression(
            FunctionRef(
                name="LastPositionOf",
                arguments=[Literal(value="test"), Literal(value="this is a test string test")],
            )
        )
        assert "lastIndexOf" in result

    def test_last_position_of_not_found(self, translator: CQLTranslator):
        """Test LastPositionOf when pattern not found."""
        result = translator.translate_expression(
            FunctionRef(
                name="LastPositionOf",
                arguments=[Literal(value="z"), Literal(value="banana")],
            )
        )
        assert "lastIndexOf" in result

    def test_last_position_of_empty_pattern(self, translator: CQLTranslator):
        """Test LastPositionOf with empty pattern."""
        result = translator.translate_expression(
            FunctionRef(
                name="LastPositionOf",
                arguments=[Literal(value=""), Literal(value="test")],
            )
        )
        assert "lastIndexOf" in result

    def test_last_position_of_case_insensitive(self, translator: CQLTranslator):
        """Test that LastPositionOf is case-insensitive."""
        result = translator.translate_expression(
            FunctionRef(
                name="lastpositionof",
                arguments=[Literal(value="a"), Literal(value="banana")],
            )
        )
        assert "lastIndexOf" in result


class TestConstructorEdgeCases:
    """Tests for edge cases in constructor functions."""

    @pytest.fixture
    def translator(self) -> CQLTranslator:
        """Create a translator instance for testing."""
        return CQLTranslator()

    def test_datetime_minimum_args(self, translator: CQLTranslator):
        """Test DateTime with minimum arguments."""
        result = translator.translate_expression(
            FunctionRef(
                name="DateTime",
                arguments=[Literal(value=2024), Literal(value=1), Literal(value=1)],
            )
        )
        assert "@" in result

    def test_date_leap_year(self, translator: CQLTranslator):
        """Test Date for leap year date."""
        result = translator.translate_expression(
            FunctionRef(
                name="Date",
                arguments=[Literal(value=2024), Literal(value=2), Literal(value=29)],
            )
        )
        assert "@" in result
        assert "2024" in result

    def test_time_with_only_hour_minute(self, translator: CQLTranslator):
        """Test Time with only hour and minute (should still work)."""
        result = translator.translate_expression(
            FunctionRef(
                name="Time",
                arguments=[Literal(value=14), Literal(value=30), Literal(value=0)],
            )
        )
        assert "@" in result or "T" in result


class TestConstructorWithExpressions:
    """Tests for constructors with complex expressions."""

    @pytest.fixture
    def translator(self) -> CQLTranslator:
        """Create a translator instance for testing."""
        return CQLTranslator()

    def test_datetime_with_arithmetic_year(self, translator: CQLTranslator):
        """Test DateTime with arithmetic expression for year."""
        # Note: This would need proper AST for arithmetic, but we test the concept
        result = translator.translate_expression(
            FunctionRef(
                name="DateTime",
                arguments=[
                    Identifier(name="baseYear"),
                    Literal(value=1),
                    Literal(value=1),
                ],
            )
        )
        assert "@" in result
        assert "baseYear" in result

    def test_date_with_parameter_reference(self, translator: CQLTranslator):
        """Test Date with parameter reference."""
        result = translator.translate_expression(
            FunctionRef(
                name="Date",
                arguments=[
                    Identifier(name="MeasurementYear"),
                    Identifier(name="MeasurementMonth"),
                    Identifier(name="MeasurementDay"),
                ],
            )
        )
        assert "@" in result


class TestConstructorConsistency:
    """Tests for consistency across constructor functions."""

    @pytest.fixture
    def translator(self) -> CQLTranslator:
        """Create a translator instance for testing."""
        return CQLTranslator()

    def test_all_constructors_return_non_empty(self, translator: CQLTranslator):
        """Test that all constructors return non-empty strings."""
        datetime_result = translator.translate_expression(
            FunctionRef(
                name="DateTime",
                arguments=[Literal(value=2024), Literal(value=1), Literal(value=1)],
            )
        )
        date_result = translator.translate_expression(
            FunctionRef(
                name="Date",
                arguments=[Literal(value=2024), Literal(value=1), Literal(value=1)],
            )
        )
        time_result = translator.translate_expression(
            FunctionRef(
                name="Time",
                arguments=[Literal(value=12), Literal(value=0), Literal(value=0)],
            )
        )
        assert len(datetime_result) > 0
        assert len(date_result) > 0
        assert len(time_result) > 0

    def test_datetime_and_date_similar_format(self, translator: CQLTranslator):
        """Test that DateTime and Date produce similar date formats."""
        datetime_result = translator.translate_expression(
            FunctionRef(
                name="DateTime",
                arguments=[Literal(value=2024), Literal(value=6), Literal(value=15)],
            )
        )
        date_result = translator.translate_expression(
            FunctionRef(
                name="Date",
                arguments=[Literal(value=2024), Literal(value=6), Literal(value=15)],
            )
        )
        # Both should contain the date components
        assert "2024" in datetime_result
        assert "2024" in date_result


class TestAdditionalConstructorFunctions:
    """Tests for additional constructor-related functions."""

    @pytest.fixture
    def translator(self) -> CQLTranslator:
        """Create a translator instance for testing."""
        return CQLTranslator()

    def test_today_function(self, translator: CQLTranslator):
        """Test Today() function translation."""
        result = translator.translate_expression(
            FunctionRef(name="Today", arguments=[])
        )
        assert result == "today()"

    def test_now_function(self, translator: CQLTranslator):
        """Test Now() function translation."""
        result = translator.translate_expression(
            FunctionRef(name="Now", arguments=[])
        )
        assert result == "now()"

    def test_time_of_day_function(self, translator: CQLTranslator):
        """Test TimeOfDay() function translation."""
        result = translator.translate_expression(
            FunctionRef(name="TimeOfDay", arguments=[])
        )
        assert result == "timeOfDay()"
