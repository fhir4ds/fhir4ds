"""
Unit tests for function translation.

Tests the translation of CQL function calls to FHIRPath equivalents.
"""

import pytest

from ....parser.ast_nodes import (
    FunctionRef,
    Identifier,
    Literal,
)
from ....translator import CQLTranslator


class TestStringFunctions:
    """Tests for string function translation."""

    @pytest.fixture
    def translator(self) -> CQLTranslator:
        """Create a translator instance for testing."""
        return CQLTranslator()

    # Length()
    def test_length_with_string_arg(self, translator: CQLTranslator):
        """Test Length() function with string argument."""
        result = translator.translate_expression(
            FunctionRef(name="Length", arguments=[Literal(value="hello")])
        )
        assert result == "'hello'.length()"

    def test_length_with_identifier(self, translator: CQLTranslator):
        """Test Length() function with identifier."""
        result = translator.translate_expression(
            FunctionRef(name="Length", arguments=[Identifier(name="myString")])
        )
        assert result == "myString.length()"

    # Upper() / Lower()
    def test_upper(self, translator: CQLTranslator):
        """Test Upper() function translation."""
        result = translator.translate_expression(
            FunctionRef(name="Upper", arguments=[Literal(value="hello")])
        )
        assert result == "'hello'.upper()"

    def test_lower(self, translator: CQLTranslator):
        """Test Lower() function translation."""
        result = translator.translate_expression(
            FunctionRef(name="Lower", arguments=[Literal(value="HELLO")])
        )
        assert result == "'HELLO'.lower()"

    # Substring()
    def test_substring_single_arg(self, translator: CQLTranslator):
        """Test Substring() with start index only."""
        result = translator.translate_expression(
            FunctionRef(
                name="Substring",
                arguments=[Literal(value="hello"), Literal(value=1)],
            )
        )
        assert result == "'hello'.substring(1)"

    def test_substring_two_args(self, translator: CQLTranslator):
        """Test Substring() with start index and length."""
        result = translator.translate_expression(
            FunctionRef(
                name="Substring",
                arguments=[Literal(value="hello"), Literal(value=1), Literal(value=3)],
            )
        )
        assert result == "'hello'.substring(1, 3)"

    # IndexOf()
    def test_index_of(self, translator: CQLTranslator):
        """Test IndexOf() function translation."""
        result = translator.translate_expression(
            FunctionRef(
                name="IndexOf",
                arguments=[Literal(value="hello world"), Literal(value="world")],
            )
        )
        assert result == "'hello world'.indexOf('world')"

    # StartsWith() / EndsWith()
    def test_starts_with(self, translator: CQLTranslator):
        """Test StartsWith() function translation."""
        result = translator.translate_expression(
            FunctionRef(
                name="StartsWith",
                arguments=[Literal(value="hello world"), Literal(value="hello")],
            )
        )
        assert result == "'hello world'.startsWith('hello')"

    def test_ends_with(self, translator: CQLTranslator):
        """Test EndsWith() function translation."""
        result = translator.translate_expression(
            FunctionRef(
                name="EndsWith",
                arguments=[Literal(value="hello world"), Literal(value="world")],
            )
        )
        assert result == "'hello world'.endsWith('world')"

    # Contains()
    def test_contains(self, translator: CQLTranslator):
        """Test Contains() function translation."""
        result = translator.translate_expression(
            FunctionRef(
                name="Contains",
                arguments=[Literal(value="hello world"), Literal(value="llo")],
            )
        )
        assert result == "'hello world'.contains('llo')"

    # Matches()
    def test_matches(self, translator: CQLTranslator):
        """Test Matches() function translation."""
        result = translator.translate_expression(
            FunctionRef(
                name="Matches",
                arguments=[Literal(value="test123"), Literal(value="[0-9]+")],
            )
        )
        assert result == "'test123'.matches('[0-9]+')"

    # Replace()
    def test_replace(self, translator: CQLTranslator):
        """Test Replace() function translation."""
        result = translator.translate_expression(
            FunctionRef(
                name="replace",
                arguments=[Literal(value="hello"), Literal(value="l"), Literal(value="x")],
            )
        )
        assert result == "'hello'.replace('l', 'x')"

    # Split()
    def test_split(self, translator: CQLTranslator):
        """Test Split() function translation."""
        result = translator.translate_expression(
            FunctionRef(
                name="Split",
                arguments=[Literal(value="a,b,c"), Literal(value=",")],
            )
        )
        assert result == "'a,b,c'.split(',')"

    # Join()
    def test_join(self, translator: CQLTranslator):
        """Test Join() function translation."""
        result = translator.translate_expression(
            FunctionRef(
                name="Join",
                arguments=[Identifier(name="myList"), Literal(value=",")],
            )
        )
        assert result == "myList.join(',')"


class TestMathFunctions:
    """Tests for math function translation."""

    @pytest.fixture
    def translator(self) -> CQLTranslator:
        """Create a translator instance for testing."""
        return CQLTranslator()

    # Abs()
    def test_abs(self, translator: CQLTranslator):
        """Test Abs() function translation."""
        result = translator.translate_expression(
            FunctionRef(name="Abs", arguments=[Literal(value=-5)])
        )
        assert result == "-5.abs()"

    # Round()
    def test_round_no_precision(self, translator: CQLTranslator):
        """Test Round() without precision."""
        result = translator.translate_expression(
            FunctionRef(name="Round", arguments=[Literal(value=3.14159)])
        )
        assert result == "3.14159.round()"

    def test_round_with_precision(self, translator: CQLTranslator):
        """Test Round() with precision."""
        result = translator.translate_expression(
            FunctionRef(
                name="Round",
                arguments=[Literal(value=3.14159), Literal(value=2)],
            )
        )
        assert result == "3.14159.round(2)"

    # Floor()
    def test_floor(self, translator: CQLTranslator):
        """Test Floor() function translation."""
        result = translator.translate_expression(
            FunctionRef(name="Floor", arguments=[Literal(value=3.7)])
        )
        assert result == "3.7.floor()"

    # Ceiling()
    def test_ceiling(self, translator: CQLTranslator):
        """Test Ceiling() function translation."""
        result = translator.translate_expression(
            FunctionRef(name="Ceiling", arguments=[Literal(value=3.2)])
        )
        assert result == "3.2.ceiling()"

    # Sqrt()
    def test_sqrt(self, translator: CQLTranslator):
        """Test Sqrt() function translation."""
        result = translator.translate_expression(
            FunctionRef(name="Sqrt", arguments=[Literal(value=16)])
        )
        assert result == "16.sqrt()"

    # Exp()
    def test_exp(self, translator: CQLTranslator):
        """Test Exp() function translation."""
        result = translator.translate_expression(
            FunctionRef(name="Exp", arguments=[Literal(value=2)])
        )
        assert result == "2.exp()"

    # Ln()
    def test_ln(self, translator: CQLTranslator):
        """Test Ln() function translation."""
        result = translator.translate_expression(
            FunctionRef(name="Ln", arguments=[Literal(value=10)])
        )
        assert result == "10.ln()"

    # Log()
    def test_log(self, translator: CQLTranslator):
        """Test Log() function translation."""
        result = translator.translate_expression(
            FunctionRef(
                name="Log",
                arguments=[Literal(value=100), Literal(value=10)],
            )
        )
        assert result == "100.log(10)"

    # Power()
    def test_power(self, translator: CQLTranslator):
        """Test Power() function translation."""
        result = translator.translate_expression(
            FunctionRef(
                name="Power",
                arguments=[Literal(value=2), Literal(value=3)],
            )
        )
        assert result == "2.power(3)"

    # Truncate()
    def test_truncate(self, translator: CQLTranslator):
        """Test Truncate() function translation."""
        result = translator.translate_expression(
            FunctionRef(name="Truncate", arguments=[Literal(value=3.7)])
        )
        assert result == "3.7.truncate()"


class TestDateTimeFunctions:
    """Tests for date/time function translation."""

    @pytest.fixture
    def translator(self) -> CQLTranslator:
        """Create a translator instance for testing."""
        return CQLTranslator()

    # Today()
    def test_today(self, translator: CQLTranslator):
        """Test Today() function translation."""
        result = translator.translate_expression(
            FunctionRef(name="Today", arguments=[])
        )
        assert result == "today()"

    # Now()
    def test_now(self, translator: CQLTranslator):
        """Test Now() function translation."""
        result = translator.translate_expression(
            FunctionRef(name="Now", arguments=[])
        )
        assert result == "now()"

    # TimeOfDay()
    def test_time_of_day(self, translator: CQLTranslator):
        """Test TimeOfDay() function translation."""
        result = translator.translate_expression(
            FunctionRef(name="TimeOfDay", arguments=[])
        )
        assert result == "timeOfDay()"


class TestTypeConversionFunctions:
    """Tests for type conversion function translation."""

    @pytest.fixture
    def translator(self) -> CQLTranslator:
        """Create a translator instance for testing."""
        return CQLTranslator()

    # ToString()
    def test_to_string(self, translator: CQLTranslator):
        """Test ToString() function translation."""
        result = translator.translate_expression(
            FunctionRef(name="ToString", arguments=[Literal(value=123)])
        )
        assert result == "123.toString()"

    # ToBoolean()
    def test_to_boolean(self, translator: CQLTranslator):
        """Test ToBoolean() function translation."""
        result = translator.translate_expression(
            FunctionRef(name="ToBoolean", arguments=[Literal(value="true")])
        )
        assert result == "'true'.toBoolean()"

    # ToInteger()
    def test_to_integer(self, translator: CQLTranslator):
        """Test ToInteger() function translation."""
        result = translator.translate_expression(
            FunctionRef(name="ToInteger", arguments=[Literal(value="42")])
        )
        assert result == "'42'.toInteger()"

    # ToDecimal()
    def test_to_decimal(self, translator: CQLTranslator):
        """Test ToDecimal() function translation."""
        result = translator.translate_expression(
            FunctionRef(name="ToDecimal", arguments=[Literal(value="3.14")])
        )
        assert result == "'3.14'.toDecimal()"

    # ToDateTime()
    def test_to_datetime(self, translator: CQLTranslator):
        """Test ToDateTime() function translation."""
        result = translator.translate_expression(
            FunctionRef(name="ToDateTime", arguments=[Literal(value="2024-01-15")])
        )
        assert result == "'2024-01-15'.toDateTime()"

    # ToDate()
    def test_to_date(self, translator: CQLTranslator):
        """Test ToDate() function translation."""
        result = translator.translate_expression(
            FunctionRef(name="ToDate", arguments=[Literal(value="2024-01-15T12:00:00")])
        )
        assert result == "'2024-01-15T12:00:00'.toDate()"

    # ToTime()
    def test_to_time(self, translator: CQLTranslator):
        """Test ToTime() function translation."""
        result = translator.translate_expression(
            FunctionRef(name="ToTime", arguments=[Literal(value="T12:30:00")])
        )
        assert result == "'T12:30:00'.toTime()"

    # ToQuantity()
    def test_to_quantity(self, translator: CQLTranslator):
        """Test ToQuantity() function translation."""
        result = translator.translate_expression(
            FunctionRef(name="ToQuantity", arguments=[Literal(value="5 mg")])
        )
        assert result == "'5 mg'.toQuantity()"

    # ToConcept()
    def test_to_concept(self, translator: CQLTranslator):
        """Test ToConcept() function translation."""
        result = translator.translate_expression(
            FunctionRef(name="ToConcept", arguments=[Identifier(name="myCode")])
        )
        assert result == "myCode.toConcept()"


class TestAggregateFunctions:
    """Tests for aggregate function translation."""

    @pytest.fixture
    def translator(self) -> CQLTranslator:
        """Create a translator instance for testing."""
        return CQLTranslator()

    # Count
    def test_count(self, translator: CQLTranslator):
        """Test Count() function translation."""
        result = translator.translate_expression(
            FunctionRef(name="Count", arguments=[Identifier(name="items")])
        )
        assert result == "items.count()"

    # Sum
    def test_sum(self, translator: CQLTranslator):
        """Test Sum() function translation."""
        result = translator.translate_expression(
            FunctionRef(name="Sum", arguments=[Identifier(name="values")])
        )
        assert result == "values.sum()"

    # Min
    def test_min(self, translator: CQLTranslator):
        """Test Min() function translation."""
        result = translator.translate_expression(
            FunctionRef(name="Min", arguments=[Identifier(name="values")])
        )
        assert result == "values.min()"

    # Max
    def test_max(self, translator: CQLTranslator):
        """Test Max() function translation."""
        result = translator.translate_expression(
            FunctionRef(name="Max", arguments=[Identifier(name="values")])
        )
        assert result == "values.max()"

    # Avg
    def test_avg(self, translator: CQLTranslator):
        """Test Avg() function translation."""
        result = translator.translate_expression(
            FunctionRef(name="Avg", arguments=[Identifier(name="values")])
        )
        assert result == "values.avg()"

    # AllTrue()
    def test_all_true(self, translator: CQLTranslator):
        """Test AllTrue() function translation."""
        result = translator.translate_expression(
            FunctionRef(name="AllTrue", arguments=[Identifier(name="flags")])
        )
        assert result == "flags.allTrue()"

    # AnyTrue()
    def test_any_true(self, translator: CQLTranslator):
        """Test AnyTrue() function translation."""
        result = translator.translate_expression(
            FunctionRef(name="AnyTrue", arguments=[Identifier(name="flags")])
        )
        assert result == "flags.anyTrue()"

    # AllFalse()
    def test_all_false(self, translator: CQLTranslator):
        """Test AllFalse() function translation."""
        result = translator.translate_expression(
            FunctionRef(name="AllFalse", arguments=[Identifier(name="flags")])
        )
        assert result == "flags.allFalse()"

    # AnyFalse()
    def test_any_false(self, translator: CQLTranslator):
        """Test AnyFalse() function translation."""
        result = translator.translate_expression(
            FunctionRef(name="AnyFalse", arguments=[Identifier(name="flags")])
        )
        assert result == "flags.anyFalse()"


class TestExistenceFunctions:
    """Tests for existence function translation."""

    @pytest.fixture
    def translator(self) -> CQLTranslator:
        """Create a translator instance for testing."""
        return CQLTranslator()

    # exists
    def test_exists(self, translator: CQLTranslator):
        """Test exists() function translation."""
        result = translator.translate_expression(
            FunctionRef(name="exists", arguments=[Identifier(name="items")])
        )
        assert result == "items.exists()"

    # empty
    def test_empty(self, translator: CQLTranslator):
        """Test empty() function translation."""
        result = translator.translate_expression(
            FunctionRef(name="empty", arguments=[Identifier(name="items")])
        )
        assert result == "items.empty()"

    # HasValue()
    def test_has_value(self, translator: CQLTranslator):
        """Test HasValue() function translation."""
        result = translator.translate_expression(
            FunctionRef(name="HasValue", arguments=[Identifier(name="field")])
        )
        assert result == "field.hasValue()"


class TestNavigationFunctions:
    """Tests for navigation/collection function translation."""

    @pytest.fixture
    def translator(self) -> CQLTranslator:
        """Create a translator instance for testing."""
        return CQLTranslator()

    # first()
    def test_first(self, translator: CQLTranslator):
        """Test first() function translation."""
        result = translator.translate_expression(
            FunctionRef(name="first", arguments=[Identifier(name="items")])
        )
        assert result == "items.first()"

    # last()
    def test_last(self, translator: CQLTranslator):
        """Test last() function translation."""
        result = translator.translate_expression(
            FunctionRef(name="last", arguments=[Identifier(name="items")])
        )
        assert result == "items.last()"

    # skip()
    def test_skip(self, translator: CQLTranslator):
        """Test skip() function translation."""
        result = translator.translate_expression(
            FunctionRef(name="skip", arguments=[Identifier(name="items"), Literal(value=5)])
        )
        assert result == "items.skip(5)"

    # take()
    def test_take(self, translator: CQLTranslator):
        """Test take() function translation."""
        result = translator.translate_expression(
            FunctionRef(name="take", arguments=[Identifier(name="items"), Literal(value=3)])
        )
        assert result == "items.take(3)"

    # single()
    def test_single(self, translator: CQLTranslator):
        """Test single() function translation."""
        result = translator.translate_expression(
            FunctionRef(name="single", arguments=[Identifier(name="items")])
        )
        assert result == "items.single()"

    # distinct()
    def test_distinct(self, translator: CQLTranslator):
        """Test distinct() function translation."""
        result = translator.translate_expression(
            FunctionRef(name="distinct", arguments=[Identifier(name="items")])
        )
        assert result == "items.distinct()"

    # tail()
    def test_tail(self, translator: CQLTranslator):
        """Test tail() function translation."""
        result = translator.translate_expression(
            FunctionRef(name="tail", arguments=[Identifier(name="items")])
        )
        assert result == "items.tail()"


class TestFilteringFunctions:
    """Tests for filtering function translation."""

    @pytest.fixture
    def translator(self) -> CQLTranslator:
        """Create a translator instance for testing."""
        return CQLTranslator()

    # where()
    def test_where(self, translator: CQLTranslator):
        """Test where() function translation."""
        result = translator.translate_expression(
            FunctionRef(name="where", arguments=[Identifier(name="items")])
        )
        assert result == "items.where()"

    # select()
    def test_select(self, translator: CQLTranslator):
        """Test select() function translation."""
        result = translator.translate_expression(
            FunctionRef(name="select", arguments=[Identifier(name="items")])
        )
        assert result == "items.select()"


class TestCombiningFunctions:
    """Tests for combining function translation."""

    @pytest.fixture
    def translator(self) -> CQLTranslator:
        """Create a translator instance for testing."""
        return CQLTranslator()

    # union
    def test_union(self, translator: CQLTranslator):
        """Test union() function translation."""
        result = translator.translate_expression(
            FunctionRef(name="union", arguments=[Identifier(name="a"), Identifier(name="b")])
        )
        assert result == "a.union(b)"

    # intersect
    def test_intersect(self, translator: CQLTranslator):
        """Test intersect() function translation."""
        result = translator.translate_expression(
            FunctionRef(name="intersect", arguments=[Identifier(name="a"), Identifier(name="b")])
        )
        assert result == "a.intersect(b)"

    # exclude
    def test_exclude(self, translator: CQLTranslator):
        """Test exclude() function translation."""
        result = translator.translate_expression(
            FunctionRef(name="exclude", arguments=[Identifier(name="a"), Identifier(name="b")])
        )
        assert result == "a.exclude(b)"


class TestAgeFunctions:
    """Tests for age-related function translation."""

    @pytest.fixture
    def translator(self) -> CQLTranslator:
        """Create a translator instance for testing."""
        return CQLTranslator()

    def test_age_in_years(self, translator: CQLTranslator):
        """Test AgeInYears() function translation."""
        result = translator.translate_expression(
            FunctionRef(name="AgeInYears", arguments=[])
        )
        assert result == "ageInYears($this)"

    def test_age_in_months(self, translator: CQLTranslator):
        """Test AgeInMonths() function translation."""
        result = translator.translate_expression(
            FunctionRef(name="AgeInMonths", arguments=[])
        )
        assert result == "ageInMonths($this)"

    def test_age_in_days(self, translator: CQLTranslator):
        """Test AgeInDays() function translation."""
        result = translator.translate_expression(
            FunctionRef(name="AgeInDays", arguments=[])
        )
        assert result == "ageInDays($this)"

    def test_age_in_hours(self, translator: CQLTranslator):
        """Test AgeInHours() function translation."""
        result = translator.translate_expression(
            FunctionRef(name="AgeInHours", arguments=[])
        )
        assert result == "ageInHours($this)"

    def test_age_in_minutes(self, translator: CQLTranslator):
        """Test AgeInMinutes() function translation."""
        result = translator.translate_expression(
            FunctionRef(name="AgeInMinutes", arguments=[])
        )
        assert result == "ageInMinutes($this)"

    def test_age_in_seconds(self, translator: CQLTranslator):
        """Test AgeInSeconds() function translation."""
        result = translator.translate_expression(
            FunctionRef(name="AgeInSeconds", arguments=[])
        )
        assert result == "ageInSeconds($this)"

    def test_age_in_years_at(self, translator: CQLTranslator):
        """Test AgeInYearsAt() function translation."""
        result = translator.translate_expression(
            FunctionRef(name="AgeInYearsAt", arguments=[Identifier(name="asOf")])
        )
        assert result == "ageInYearsAt($this, asOf)"

    def test_age_in_months_at(self, translator: CQLTranslator):
        """Test AgeInMonthsAt() function translation."""
        result = translator.translate_expression(
            FunctionRef(name="AgeInMonthsAt", arguments=[Identifier(name="asOf")])
        )
        assert result == "ageInMonthsAt($this, asOf)"

    def test_age_in_days_at(self, translator: CQLTranslator):
        """Test AgeInDaysAt() function translation."""
        result = translator.translate_expression(
            FunctionRef(name="AgeInDaysAt", arguments=[Identifier(name="asOf")])
        )
        assert result == "ageInDaysAt($this, asOf)"


class TestIntervalFunctions:
    """Tests for interval-related function translation."""

    @pytest.fixture
    def translator(self) -> CQLTranslator:
        """Create a translator instance for testing."""
        return CQLTranslator()

    def test_start(self, translator: CQLTranslator):
        """Test Start() function translation."""
        result = translator.translate_expression(
            FunctionRef(name="Start", arguments=[Identifier(name="myInterval")])
        )
        assert result == "myInterval.start()"

    def test_end(self, translator: CQLTranslator):
        """Test End() function translation."""
        result = translator.translate_expression(
            FunctionRef(name="End", arguments=[Identifier(name="myInterval")])
        )
        assert result == "myInterval.end()"

    def test_size(self, translator: CQLTranslator):
        """Test Size() function translation."""
        result = translator.translate_expression(
            FunctionRef(name="Size", arguments=[Identifier(name="myInterval")])
        )
        assert result == "myInterval.size()"


class TestMiscellaneousFunctions:
    """Tests for miscellaneous function translation."""

    @pytest.fixture
    def translator(self) -> CQLTranslator:
        """Create a translator instance for testing."""
        return CQLTranslator()

    def test_children(self, translator: CQLTranslator):
        """Test children() function translation."""
        result = translator.translate_expression(
            FunctionRef(name="children", arguments=[Identifier(name="resource")])
        )
        assert result == "resource.children()"

    def test_descendants(self, translator: CQLTranslator):
        """Test descendants() function translation."""
        result = translator.translate_expression(
            FunctionRef(name="descendants", arguments=[Identifier(name="resource")])
        )
        assert result == "resource.descendants()"

    def test_expand(self, translator: CQLTranslator):
        """Test Expand() function translation."""
        result = translator.translate_expression(
            FunctionRef(name="Expand", arguments=[Identifier(name="valueset")])
        )
        assert result == "valueset.expand()"

    def test_combine(self, translator: CQLTranslator):
        """Test Combine() function translation."""
        result = translator.translate_expression(
            FunctionRef(
                name="Combine",
                arguments=[Identifier(name="list1"), Identifier(name="list2")],
            )
        )
        assert result == "list1.combine(list2)"


class TestCaseInsensitiveFunctions:
    """Tests for case-insensitive function name handling."""

    @pytest.fixture
    def translator(self) -> CQLTranslator:
        """Create a translator instance for testing."""
        return CQLTranslator()

    def test_uppercase_function_name(self, translator: CQLTranslator):
        """Test that uppercase function names work."""
        result = translator.translate_expression(
            FunctionRef(name="TODAY", arguments=[])
        )
        assert result == "today()"

    def test_lowercase_function_name(self, translator: CQLTranslator):
        """Test that lowercase function names work."""
        result = translator.translate_expression(
            FunctionRef(name="today", arguments=[])
        )
        assert result == "today()"

    def test_mixed_case_function_name(self, translator: CQLTranslator):
        """Test that mixed case function names work."""
        result = translator.translate_expression(
            FunctionRef(name="ToDay", arguments=[])
        )
        assert result == "today()"


class TestUnknownFunctions:
    """Tests for unknown/unmapped function handling."""

    @pytest.fixture
    def translator(self) -> CQLTranslator:
        """Create a translator instance for testing."""
        return CQLTranslator()

    def test_unknown_function_passes_through(self, translator: CQLTranslator):
        """Test that unknown functions pass through as-is."""
        result = translator.translate_expression(
            FunctionRef(name="CustomFunction", arguments=[Literal(value=1), Literal(value=2)])
        )
        assert result == "CustomFunction(1, 2)"

    def test_unknown_function_no_args(self, translator: CQLTranslator):
        """Test unknown function with no arguments."""
        result = translator.translate_expression(
            FunctionRef(name="MyCustomFunc", arguments=[])
        )
        assert result == "MyCustomFunc()"
