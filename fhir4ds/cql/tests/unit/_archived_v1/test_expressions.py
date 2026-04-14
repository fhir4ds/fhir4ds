"""
Unit tests for expression translation.

Tests the translation of CQL expressions to FHIRPath, including:
- Literal expressions (null, boolean, string, integer, decimal, special values)
- DateTime and Time literals
- Identifier references (simple, parameter, let, definition)
- Property access (simple and nested)
- Intervals (closed, open, half-open)
- Lists (empty, simple, mixed types)
- Tuples (empty, simple)
- Quantities (simple and time-based)
"""

import json

import pytest

from ....parser.ast_nodes import (
    DateTimeLiteral,
    Definition,
    Identifier,
    InstanceExpression,
    Interval,
    Library,
    ListExpression,
    Literal,
    ParameterDefinition,
    Property,
    Quantity,
    QualifiedIdentifier,
    TimeLiteral,
    TupleElement,
    TupleExpression,
)
from ....translator import CQLTranslator


class TestLiteralExpressions:
    """Tests for literal expression translation."""

    @pytest.fixture
    def translator(self) -> CQLTranslator:
        """Create a translator instance for testing."""
        return CQLTranslator()

    # === Null Literal ===
    def test_null_literal(self, translator: CQLTranslator):
        """Test null literal translation."""
        result = translator.translate_expression(Literal(value=None))
        assert result == "null"

    # === Boolean Literals ===
    def test_boolean_true(self, translator: CQLTranslator):
        """Test boolean true literal translation."""
        result = translator.translate_expression(Literal(value=True))
        assert result == "true"

    def test_boolean_false(self, translator: CQLTranslator):
        """Test boolean false literal translation."""
        result = translator.translate_expression(Literal(value=False))
        assert result == "false"

    # === String Literals ===
    def test_string_simple(self, translator: CQLTranslator):
        """Test simple string literal translation."""
        result = translator.translate_expression(Literal(value="hello"))
        assert result == "'hello'"

    def test_string_with_single_quote(self, translator: CQLTranslator):
        """Test string with embedded single quote is escaped."""
        result = translator.translate_expression(Literal(value="it's a test"))
        assert result == "'it\\'s a test'"

    def test_string_with_backslash(self, translator: CQLTranslator):
        """Test string with backslash is escaped."""
        result = translator.translate_expression(Literal(value="path\\to\\file"))
        assert result == "'path\\\\to\\\\file'"

    def test_string_with_both_quotes_and_backslash(self, translator: CQLTranslator):
        """Test string with both quotes and backslash."""
        result = translator.translate_expression(Literal(value="it's\\nice"))
        assert result == "'it\\'s\\\\nice'"

    def test_string_empty(self, translator: CQLTranslator):
        """Test empty string literal."""
        result = translator.translate_expression(Literal(value=""))
        assert result == "''"

    # === Integer Literals ===
    def test_integer_positive(self, translator: CQLTranslator):
        """Test positive integer literal."""
        result = translator.translate_expression(Literal(value=42))
        assert result == "42"

    def test_integer_zero(self, translator: CQLTranslator):
        """Test zero integer literal."""
        result = translator.translate_expression(Literal(value=0))
        assert result == "0"

    def test_integer_large(self, translator: CQLTranslator):
        """Test large integer literal."""
        result = translator.translate_expression(Literal(value=9999999999))
        assert result == "9999999999"

    # === Decimal/Float Literals ===
    def test_decimal_simple(self, translator: CQLTranslator):
        """Test simple decimal literal."""
        result = translator.translate_expression(Literal(value=3.14))
        assert result == "3.14"

    def test_decimal_small(self, translator: CQLTranslator):
        """Test small decimal literal."""
        result = translator.translate_expression(Literal(value=0.001))
        assert result == "0.001"

    def test_float_infinity(self, translator: CQLTranslator):
        """Test positive infinity is represented as division."""
        result = translator.translate_expression(Literal(value=float("inf")))
        assert result == "1.0 / 0.0"

    def test_float_negative_infinity(self, translator: CQLTranslator):
        """Test negative infinity is represented as division."""
        result = translator.translate_expression(Literal(value=float("-inf")))
        assert result == "-1.0 / 0.0"

    def test_float_nan(self, translator: CQLTranslator):
        """Test NaN is represented as 0/0 division."""
        result = translator.translate_expression(Literal(value=float("nan")))
        assert result == "0.0 / 0.0"


class TestDateTimeLiterals:
    """Tests for DateTime literal translation."""

    @pytest.fixture
    def translator(self) -> CQLTranslator:
        """Create a translator instance for testing."""
        return CQLTranslator()

    def test_date_only(self, translator: CQLTranslator):
        """Test date-only literal."""
        result = translator.translate_expression(DateTimeLiteral(value="2024-01-15"))
        assert result == "@2024-01-15"

    def test_datetime_no_timezone(self, translator: CQLTranslator):
        """Test datetime without timezone."""
        result = translator.translate_expression(
            DateTimeLiteral(value="2024-01-15T12:30:00")
        )
        assert result == "@2024-01-15T12:30:00"

    def test_datetime_with_z_timezone(self, translator: CQLTranslator):
        """Test datetime with Z timezone."""
        result = translator.translate_expression(
            DateTimeLiteral(value="2024-01-15T12:30:00Z")
        )
        assert result == "@2024-01-15T12:30:00Z"

    def test_datetime_with_offset_timezone(self, translator: CQLTranslator):
        """Test datetime with offset timezone."""
        result = translator.translate_expression(
            DateTimeLiteral(value="2024-01-15T12:30:00+05:00")
        )
        assert result == "@2024-01-15T12:30:00+05:00"

    def test_datetime_with_milliseconds(self, translator: CQLTranslator):
        """Test datetime with milliseconds."""
        result = translator.translate_expression(
            DateTimeLiteral(value="2024-01-15T12:30:00.500")
        )
        assert result == "@2024-01-15T12:30:00.500"


class TestTimeLiterals:
    """Tests for Time literal translation."""

    @pytest.fixture
    def translator(self) -> CQLTranslator:
        """Create a translator instance for testing."""
        return CQLTranslator()

    def test_time_with_t_prefix(self, translator: CQLTranslator):
        """Test time literal with T prefix."""
        result = translator.translate_expression(TimeLiteral(value="T12:30:00"))
        assert result == "@T12:30:00"

    def test_time_without_t_prefix(self, translator: CQLTranslator):
        """Test time literal without T prefix gets it added."""
        result = translator.translate_expression(TimeLiteral(value="12:30:00"))
        assert result == "@T12:30:00"

    def test_time_with_milliseconds(self, translator: CQLTranslator):
        """Test time with milliseconds."""
        result = translator.translate_expression(TimeLiteral(value="T12:30:00.500"))
        assert result == "@T12:30:00.500"

    def test_time_hour_only(self, translator: CQLTranslator):
        """Test time with hour only."""
        result = translator.translate_expression(TimeLiteral(value="T14"))
        assert result == "@T14"


class TestIdentifierExpressions:
    """Tests for identifier translation."""

    @pytest.fixture
    def translator(self) -> CQLTranslator:
        """Create a translator instance for testing."""
        return CQLTranslator()

    def test_simple_identifier(self, translator: CQLTranslator):
        """Test simple identifier reference."""
        result = translator.translate_expression(Identifier(name="SomeVar"))
        assert result == "SomeVar"

    def test_patient_identifier(self, translator: CQLTranslator):
        """Test Patient identifier translates to retrieve marker."""
        result = translator.translate_expression(Identifier(name="Patient"))
        assert result == "__retrieve__:Patient"

    def test_parameter_reference(self, translator: CQLTranslator):
        """Test parameter reference uses % prefix."""
        translator.context.parameters["MeasurementPeriod"] = ParameterDefinition(
            name="MeasurementPeriod"
        )
        result = translator.translate_expression(Identifier(name="MeasurementPeriod"))
        assert result == "%MeasurementPeriod"

    def test_definition_reference(self, translator: CQLTranslator):
        """Test definition reference uses % prefix."""
        from ....translator import TranslationResult

        translator.context.definitions["IsActive"] = TranslationResult(
            fhirpath="active = true"
        )
        result = translator.translate_expression(Identifier(name="IsActive"))
        assert result == "%IsActive"

    def test_let_variable_reference(self, translator: CQLTranslator):
        """Test let variable reference returns stored expression."""
        translator.context.let_variables["age"] = "AgeInYears()"
        result = translator.translate_expression(Identifier(name="age"))
        assert result == "AgeInYears()"

    def test_alias_reference(self, translator: CQLTranslator):
        """Test alias reference uses % prefix."""
        translator.context.aliases = ["P", "C"]
        result = translator.translate_expression(Identifier(name="P"))
        assert result == "%P"

    def test_qualified_identifier(self, translator: CQLTranslator):
        """Test qualified identifier with dot notation."""
        result = translator.translate_expression(
            QualifiedIdentifier(parts=["FHIRHelpers", "ToDateTime"])
        )
        assert result == "FHIRHelpers.ToDateTime"

    def test_qualified_identifier_three_parts(self, translator: CQLTranslator):
        """Test qualified identifier with three parts."""
        result = translator.translate_expression(
            QualifiedIdentifier(parts=["FHIR", "Patient", "name"])
        )
        assert result == "FHIR.Patient.name"


class TestPropertyAccess:
    """Tests for property access translation."""

    @pytest.fixture
    def translator(self) -> CQLTranslator:
        """Create a translator instance for testing."""
        return CQLTranslator()

    def test_simple_property_implicit_source(self, translator: CQLTranslator):
        """Test simple property with implicit source."""
        result = translator.translate_expression(Property(source=None, path="name"))
        assert result == "name"

    def test_property_with_source(self, translator: CQLTranslator):
        """Test property access with explicit source."""
        result = translator.translate_expression(
            Property(source=Identifier(name="Patient"), path="birthDate")
        )
        assert result == "__retrieve__:Patient.birthDate"

    def test_nested_property(self, translator: CQLTranslator):
        """Test nested property access."""
        result = translator.translate_expression(
            Property(
                source=Property(source=Identifier(name="Patient"), path="name"),
                path="given",
            )
        )
        assert result == "__retrieve__:Patient.name.given"

    def test_deeply_nested_property(self, translator: CQLTranslator):
        """Test deeply nested property access."""
        result = translator.translate_expression(
            Property(
                source=Property(
                    source=Property(source=Identifier(name="Observation"), path="value"),
                    path="quantity",
                ),
                path="value",
            )
        )
        # Observation is not a special identifier (Patient is), so it remains as-is
        assert result == "Observation.value.quantity.value"


class TestIntervalExpressions:
    """Tests for interval expression translation."""

    @pytest.fixture
    def translator(self) -> CQLTranslator:
        """Create a translator instance for testing."""
        return CQLTranslator()

    def test_closed_interval(self, translator: CQLTranslator):
        """Test closed interval [1, 10]."""
        result = translator.translate_expression(
            Interval(
                low=Literal(value=1),
                high=Literal(value=10),
                low_closed=True,
                high_closed=True,
            )
        )
        assert result == "Interval[1, 10]"

    def test_open_interval(self, translator: CQLTranslator):
        """Test open interval (1, 10)."""
        result = translator.translate_expression(
            Interval(
                low=Literal(value=1),
                high=Literal(value=10),
                low_closed=False,
                high_closed=False,
            )
        )
        assert result == "Interval(1, 10)"

    def test_half_open_left_closed(self, translator: CQLTranslator):
        """Test half-open interval [1, 10)."""
        result = translator.translate_expression(
            Interval(
                low=Literal(value=1),
                high=Literal(value=10),
                low_closed=True,
                high_closed=False,
            )
        )
        assert result == "Interval[1, 10)"

    def test_half_open_right_closed(self, translator: CQLTranslator):
        """Test half-open interval (1, 10]."""
        result = translator.translate_expression(
            Interval(
                low=Literal(value=1),
                high=Literal(value=10),
                low_closed=False,
                high_closed=True,
            )
        )
        assert result == "Interval(1, 10]"

    def test_date_interval(self, translator: CQLTranslator):
        """Test date interval."""
        result = translator.translate_expression(
            Interval(
                low=DateTimeLiteral(value="2024-01-01"),
                high=DateTimeLiteral(value="2024-12-31"),
                low_closed=True,
                high_closed=True,
            )
        )
        assert result == "Interval[@2024-01-01, @2024-12-31]"

    def test_interval_null_low(self, translator: CQLTranslator):
        """Test interval with null low bound."""
        result = translator.translate_expression(
            Interval(
                low=None,
                high=Literal(value=10),
                low_closed=True,
                high_closed=True,
            )
        )
        assert result == "Interval[null, 10]"

    def test_interval_null_high(self, translator: CQLTranslator):
        """Test interval with null high bound."""
        result = translator.translate_expression(
            Interval(
                low=Literal(value=1),
                high=None,
                low_closed=True,
                high_closed=True,
            )
        )
        assert result == "Interval[1, null]"


class TestListExpressions:
    """Tests for list expression translation."""

    @pytest.fixture
    def translator(self) -> CQLTranslator:
        """Create a translator instance for testing."""
        return CQLTranslator()

    def test_empty_list(self, translator: CQLTranslator):
        """Test empty list."""
        result = translator.translate_expression(ListExpression(elements=[]))
        assert result == "{  }"

    def test_single_element_list(self, translator: CQLTranslator):
        """Test single element list."""
        result = translator.translate_expression(
            ListExpression(elements=[Literal(value=42)])
        )
        assert result == "{ 42 }"

    def test_integer_list(self, translator: CQLTranslator):
        """Test list of integers."""
        result = translator.translate_expression(
            ListExpression(
                elements=[
                    Literal(value=1),
                    Literal(value=2),
                    Literal(value=3),
                ]
            )
        )
        assert result == "{ 1, 2, 3 }"

    def test_string_list(self, translator: CQLTranslator):
        """Test list of strings."""
        result = translator.translate_expression(
            ListExpression(
                elements=[
                    Literal(value="a"),
                    Literal(value="b"),
                    Literal(value="c"),
                ]
            )
        )
        assert result == "{ 'a', 'b', 'c' }"

    def test_boolean_list(self, translator: CQLTranslator):
        """Test list of booleans."""
        result = translator.translate_expression(
            ListExpression(
                elements=[
                    Literal(value=True),
                    Literal(value=False),
                    Literal(value=True),
                ]
            )
        )
        assert result == "{ true, false, true }"

    def test_mixed_type_list(self, translator: CQLTranslator):
        """Test list with mixed types."""
        result = translator.translate_expression(
            ListExpression(
                elements=[
                    Literal(value=1),
                    Literal(value="two"),
                    Literal(value=True),
                    Literal(value=None),
                ]
            )
        )
        assert result == "{ 1, 'two', true, null }"

    def test_nested_list(self, translator: CQLTranslator):
        """Test nested list."""
        result = translator.translate_expression(
            ListExpression(
                elements=[
                    ListExpression(elements=[Literal(value=1), Literal(value=2)]),
                    ListExpression(elements=[Literal(value=3), Literal(value=4)]),
                ]
            )
        )
        assert result == "{ { 1, 2 }, { 3, 4 } }"


class TestTupleExpressions:
    """Tests for tuple expression translation."""

    @pytest.fixture
    def translator(self) -> CQLTranslator:
        """Create a translator instance for testing."""
        return CQLTranslator()

    def test_empty_tuple(self, translator: CQLTranslator):
        """Test empty tuple."""
        result = translator.translate_expression(TupleExpression(elements=[]))
        assert result == "{  }"

    def test_simple_tuple(self, translator: CQLTranslator):
        """Test simple tuple with name and age."""
        result = translator.translate_expression(
            TupleExpression(
                elements=[
                    TupleElement(name="name", type=Literal(value="John")),
                    TupleElement(name="age", type=Literal(value=30)),
                ]
            )
        )
        assert result == "{ name: 'John', age: 30 }"

    def test_tuple_with_boolean(self, translator: CQLTranslator):
        """Test tuple with boolean value."""
        result = translator.translate_expression(
            TupleExpression(
                elements=[
                    TupleElement(name="active", type=Literal(value=True)),
                ]
            )
        )
        assert result == "{ active: true }"

    def test_tuple_with_null(self, translator: CQLTranslator):
        """Test tuple with null value."""
        result = translator.translate_expression(
            TupleExpression(
                elements=[
                    TupleElement(name="optional", type=Literal(value=None)),
                ]
            )
        )
        assert result == "{ optional: null }"

    def test_tuple_with_datetime(self, translator: CQLTranslator):
        """Test tuple with datetime value."""
        result = translator.translate_expression(
            TupleExpression(
                elements=[
                    TupleElement(name="birthDate", type=DateTimeLiteral(value="1990-05-15")),
                ]
            )
        )
        assert result == "{ birthDate: @1990-05-15 }"

    def test_nested_tuple(self, translator: CQLTranslator):
        """Test nested tuple structure."""
        result = translator.translate_expression(
            TupleExpression(
                elements=[
                    TupleElement(
                        name="person",
                        type=TupleExpression(
                            elements=[
                                TupleElement(name="first", type=Literal(value="Jane")),
                                TupleElement(name="last", type=Literal(value="Doe")),
                            ]
                        ),
                    ),
                ]
            )
        )
        assert result == "{ person: { first: 'Jane', last: 'Doe' } }"


class TestQuantityExpressions:
    """Tests for quantity expression translation."""

    @pytest.fixture
    def translator(self) -> CQLTranslator:
        """Create a translator instance for testing."""
        return CQLTranslator()

    def test_simple_quantity_mg(self, translator: CQLTranslator):
        """Test simple quantity with 'mg' unit."""
        result = translator.translate_expression(Quantity(value=5, unit="mg"))
        # Quantity is translated to a JSON structure for UDF parsing
        parsed = json.loads(result)
        assert parsed["value"] == 5.0
        assert parsed["code"] == "mg"
        assert parsed["system"] == "http://unitsofmeasure.org"

    def test_quantity_decimal_value(self, translator: CQLTranslator):
        """Test quantity with decimal value."""
        result = translator.translate_expression(Quantity(value=2.5, unit="mL"))
        parsed = json.loads(result)
        assert parsed["value"] == 2.5
        assert parsed["code"] == "mL"

    def test_time_quantity_days(self, translator: CQLTranslator):
        """Test time quantity in days."""
        result = translator.translate_expression(Quantity(value=10, unit="days"))
        parsed = json.loads(result)
        assert parsed["value"] == 10.0
        assert parsed["code"] == "days"

    def test_time_quantity_years(self, translator: CQLTranslator):
        """Test time quantity in years."""
        result = translator.translate_expression(Quantity(value=5, unit="years"))
        parsed = json.loads(result)
        assert parsed["value"] == 5.0
        assert parsed["code"] == "years"

    def test_time_quantity_hours(self, translator: CQLTranslator):
        """Test time quantity in hours."""
        result = translator.translate_expression(Quantity(value=24, unit="hours"))
        parsed = json.loads(result)
        assert parsed["value"] == 24.0
        assert parsed["code"] == "hours"

    def test_quantity_ucum_unit(self, translator: CQLTranslator):
        """Test quantity with UCUM unit syntax."""
        result = translator.translate_expression(Quantity(value=100, unit="kg/m2"))
        parsed = json.loads(result)
        assert parsed["value"] == 100.0
        assert parsed["code"] == "kg/m2"


class TestInstanceExpressions:
    """Tests for instance expression translation."""

    @pytest.fixture
    def translator(self) -> CQLTranslator:
        """Create a translator instance for testing."""
        return CQLTranslator()

    def test_interval_instance(self, translator: CQLTranslator):
        """Test Interval instance expression."""
        result = translator.translate_expression(
            InstanceExpression(
                type="Interval",
                elements=[
                    TupleElement(name="low", type=Literal(value=1)),
                    TupleElement(name="high", type=Literal(value=10)),
                    TupleElement(name="lowClosed", type=Literal(value=True)),
                    TupleElement(name="highClosed", type=Literal(value=True)),
                ],
            )
        )
        assert result == "Interval[1, 10]"

    def test_interval_instance_open(self, translator: CQLTranslator):
        """Test open Interval instance expression."""
        result = translator.translate_expression(
            InstanceExpression(
                type="Interval",
                elements=[
                    TupleElement(name="low", type=Literal(value=1)),
                    TupleElement(name="high", type=Literal(value=10)),
                    TupleElement(name="lowClosed", type=Literal(value=False)),
                    TupleElement(name="highClosed", type=Literal(value=False)),
                ],
            )
        )
        assert result == "Interval(1, 10)"

    def test_generic_instance(self, translator: CQLTranslator):
        """Test generic instance expression creates object."""
        result = translator.translate_expression(
            InstanceExpression(
                type="CustomType",
                elements=[
                    TupleElement(name="field1", type=Literal(value="value1")),
                    TupleElement(name="field2", type=Literal(value=42)),
                ],
            )
        )
        # Generic instances create object representations
        assert "field1" in result
        assert "field2" in result


class TestLibraryIntegration:
    """Tests for full library translation with expressions."""

    @pytest.fixture
    def translator(self) -> CQLTranslator:
        """Create a translator instance for testing."""
        return CQLTranslator()

    def test_library_with_literal_definition(self, translator: CQLTranslator):
        """Test library with a literal definition."""
        library = Library(
            identifier="TestLibrary",
            statements=[
                Definition(name="MyNull", expression=Literal(value=None)),
                Definition(name="MyTrue", expression=Literal(value=True)),
                Definition(name="MyInt", expression=Literal(value=42)),
                Definition(name="MyString", expression=Literal(value="hello")),
            ],
        )
        results = translator.translate_library(library)
        assert results["MyNull"].fhirpath == "null"
        assert results["MyTrue"].fhirpath == "true"
        assert results["MyInt"].fhirpath == "42"
        assert results["MyString"].fhirpath == "'hello'"

    def test_library_with_interval_definition(self, translator: CQLTranslator):
        """Test library with interval definition."""
        library = Library(
            identifier="TestLibrary",
            statements=[
                Definition(
                    name="ValidRange",
                    expression=Interval(
                        low=Literal(value=0),
                        high=Literal(value=100),
                        low_closed=True,
                        high_closed=True,
                    ),
                ),
            ],
        )
        results = translator.translate_library(library)
        assert results["ValidRange"].fhirpath == "Interval[0, 100]"

    def test_library_with_list_definition(self, translator: CQLTranslator):
        """Test library with list definition."""
        library = Library(
            identifier="TestLibrary",
            statements=[
                Definition(
                    name="ValidCodes",
                    expression=ListExpression(
                        elements=[
                            Literal(value="A"),
                            Literal(value="B"),
                            Literal(value="C"),
                        ]
                    ),
                ),
            ],
        )
        results = translator.translate_library(library)
        assert results["ValidCodes"].fhirpath == "{ 'A', 'B', 'C' }"

    def test_library_with_tuple_definition(self, translator: CQLTranslator):
        """Test library with tuple definition."""
        library = Library(
            identifier="TestLibrary",
            statements=[
                Definition(
                    name="PatientInfo",
                    expression=TupleExpression(
                        elements=[
                            TupleElement(name="name", type=Literal(value="Test")),
                            TupleElement(name="count", type=Literal(value=10)),
                        ]
                    ),
                ),
            ],
        )
        results = translator.translate_library(library)
        assert results["PatientInfo"].fhirpath == "{ name: 'Test', count: 10 }"

    def test_library_with_quantity_definition(self, translator: CQLTranslator):
        """Test library with quantity definition."""
        library = Library(
            identifier="TestLibrary",
            statements=[
                Definition(name="Dosage", expression=Quantity(value=500, unit="mg")),
            ],
        )
        results = translator.translate_library(library)
        # Quantity is JSON
        parsed = json.loads(results["Dosage"].fhirpath)
        assert parsed["value"] == 500.0
        assert parsed["code"] == "mg"
