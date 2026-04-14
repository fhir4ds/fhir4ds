"""
Unit tests for CQL translator.

Tests the translation of CQL AST to FHIRPath expressions.
"""

import pytest

from ....parser.ast_nodes import (
    BinaryExpression,
    CaseExpression,
    CaseItem,
    ConditionalExpression,
    ContextDefinition,
    DateTimeLiteral,
    Definition,
    FunctionRef,
    Identifier,
    Interval,
    Library,
    ListExpression,
    Literal,
    ParameterDefinition,
    Property,
    QualifiedIdentifier,
    Query,
    QuerySource,
    Retrieve,
    TimeLiteral,
    UnaryExpression,
    ValueSetDefinition,
    WhereClause,
)
from ....translator import CQLTranslator, TranslationContext, TranslationResult


class TestTranslatorBasics:
    """Tests for basic translator functionality."""

    def test_translator_initialization(self):
        """Test that translator initializes correctly."""
        translator = CQLTranslator()
        assert translator is not None
        assert translator.context is not None
        assert translator.context.current_context == "Unfiltered"

    def test_translation_context_defaults(self):
        """Test that translation context has correct defaults."""
        ctx = TranslationContext()
        assert ctx.current_context == "Unfiltered"
        assert ctx.definitions == {}
        assert ctx.parameters == {}
        assert ctx.aliases == []


class TestLiteralTranslation:
    """Tests for literal translation."""

    def test_integer_literal(self):
        """Test integer literal translation."""
        translator = CQLTranslator()
        result = translator.translate_expression(Literal(value=42))
        assert result == "42"

    def test_float_literal(self):
        """Test float literal translation."""
        translator = CQLTranslator()
        result = translator.translate_expression(Literal(value=3.14))
        assert result == "3.14"

    def test_string_literal(self):
        """Test string literal translation."""
        translator = CQLTranslator()
        result = translator.translate_expression(Literal(value="hello"))
        assert result == "'hello'"

    def test_string_literal_with_quotes(self):
        """Test string literal with embedded quotes."""
        translator = CQLTranslator()
        result = translator.translate_expression(Literal(value="it's a test"))
        assert result == "'it\\'s a test'"

    def test_boolean_true_literal(self):
        """Test boolean true literal translation."""
        translator = CQLTranslator()
        result = translator.translate_expression(Literal(value=True))
        assert result == "true"

    def test_boolean_false_literal(self):
        """Test boolean false literal translation."""
        translator = CQLTranslator()
        result = translator.translate_expression(Literal(value=False))
        assert result == "false"

    def test_null_literal(self):
        """Test null literal translation."""
        translator = CQLTranslator()
        result = translator.translate_expression(Literal(value=None))
        assert result == "null"


class TestDateTimeTranslation:
    """Tests for date/time literal translation."""

    def test_date_literal(self):
        """Test date literal translation."""
        translator = CQLTranslator()
        result = translator.translate_expression(DateTimeLiteral(value="2024-01-15"))
        assert result == "@2024-01-15"

    def test_datetime_literal(self):
        """Test datetime literal translation."""
        translator = CQLTranslator()
        result = translator.translate_expression(
            DateTimeLiteral(value="2024-01-15T12:30:00")
        )
        assert result == "@2024-01-15T12:30:00"

    def test_time_literal(self):
        """Test time literal translation."""
        translator = CQLTranslator()
        result = translator.translate_expression(TimeLiteral(value="T12:30:00"))
        assert result == "@T12:30:00"

    def test_time_literal_without_prefix(self):
        """Test time literal without T prefix gets it added."""
        translator = CQLTranslator()
        result = translator.translate_expression(TimeLiteral(value="12:30:00"))
        assert result == "@T12:30:00"


class TestIdentifierTranslation:
    """Tests for identifier translation."""

    def test_simple_identifier(self):
        """Test simple identifier translation."""
        translator = CQLTranslator()
        result = translator.translate_expression(Identifier(name="SomeVar"))
        assert result == "SomeVar"

    def test_patient_identifier(self):
        """Test Patient identifier translates to retrieve marker."""
        translator = CQLTranslator()
        result = translator.translate_expression(Identifier(name="Patient"))
        assert result == "__retrieve__:Patient"

    def test_parameter_reference(self):
        """Test parameter reference translation."""
        translator = CQLTranslator()
        translator.context.parameters["MeasurementPeriod"] = ParameterDefinition(
            name="MeasurementPeriod"
        )
        result = translator.translate_expression(Identifier(name="MeasurementPeriod"))
        assert result == "%MeasurementPeriod"

    def test_qualified_identifier(self):
        """Test qualified identifier translation."""
        translator = CQLTranslator()
        result = translator.translate_expression(
            QualifiedIdentifier(parts=["FHIRHelpers", "ToDateTime"])
        )
        assert result == "FHIRHelpers.ToDateTime"


class TestPropertyTranslation:
    """Tests for property access translation."""

    def test_simple_property(self):
        """Test simple property access."""
        translator = CQLTranslator()
        result = translator.translate_expression(Property(source=None, path="name"))
        assert result == "name"

    def test_property_with_source(self):
        """Test property access with source expression."""
        translator = CQLTranslator()
        result = translator.translate_expression(
            Property(source=Identifier(name="Patient"), path="birthDate")
        )
        assert result == "__retrieve__:Patient.birthDate"

    def test_nested_property(self):
        """Test nested property access."""
        translator = CQLTranslator()
        result = translator.translate_expression(
            Property(
                source=Property(source=Identifier(name="Patient"), path="name"),
                path="given",
            )
        )
        assert result == "__retrieve__:Patient.name.given"


class TestIntervalTranslation:
    """Tests for interval translation."""

    def test_closed_interval(self):
        """Test closed interval translation."""
        translator = CQLTranslator()
        result = translator.translate_expression(
            Interval(
                low=Literal(value=1),
                high=Literal(value=10),
                low_closed=True,
                high_closed=True,
            )
        )
        assert result == "Interval[1, 10]"

    def test_open_interval(self):
        """Test open interval translation."""
        translator = CQLTranslator()
        result = translator.translate_expression(
            Interval(
                low=Literal(value=1),
                high=Literal(value=10),
                low_closed=False,
                high_closed=False,
            )
        )
        assert result == "Interval(1, 10)"

    def test_half_open_interval(self):
        """Test half-open interval translation."""
        translator = CQLTranslator()
        result = translator.translate_expression(
            Interval(
                low=Literal(value=1),
                high=Literal(value=10),
                low_closed=True,
                high_closed=False,
            )
        )
        assert result == "Interval[1, 10)"

    def test_date_interval(self):
        """Test date interval translation."""
        translator = CQLTranslator()
        result = translator.translate_expression(
            Interval(
                low=DateTimeLiteral(value="2024-01-01"),
                high=DateTimeLiteral(value="2024-12-31"),
                low_closed=True,
                high_closed=True,
            )
        )
        assert result == "Interval[@2024-01-01, @2024-12-31]"


class TestListTranslation:
    """Tests for list translation."""

    def test_empty_list(self):
        """Test empty list translation."""
        translator = CQLTranslator()
        result = translator.translate_expression(ListExpression(elements=[]))
        assert result == "{  }"

    def test_simple_list(self):
        """Test simple list translation."""
        translator = CQLTranslator()
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

    def test_string_list(self):
        """Test string list translation."""
        translator = CQLTranslator()
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


class TestBinaryOperators:
    """Tests for binary operator translation."""

    def test_addition(self):
        """Test addition operator."""
        translator = CQLTranslator()
        result = translator.translate_expression(
            BinaryExpression(
                operator="+",
                left=Literal(value=1),
                right=Literal(value=2),
            )
        )
        assert result == "(1 + 2)"

    def test_subtraction(self):
        """Test subtraction operator."""
        translator = CQLTranslator()
        result = translator.translate_expression(
            BinaryExpression(
                operator="-",
                left=Literal(value=5),
                right=Literal(value=3),
            )
        )
        assert result == "(5 - 3)"

    def test_multiplication(self):
        """Test multiplication operator."""
        translator = CQLTranslator()
        result = translator.translate_expression(
            BinaryExpression(
                operator="*",
                left=Literal(value=4),
                right=Literal(value=2),
            )
        )
        assert result == "(4 * 2)"

    def test_division(self):
        """Test division operator."""
        translator = CQLTranslator()
        result = translator.translate_expression(
            BinaryExpression(
                operator="/",
                left=Literal(value=10),
                right=Literal(value=2),
            )
        )
        assert result == "(10 / 2)"

    def test_equality(self):
        """Test equality operator."""
        translator = CQLTranslator()
        result = translator.translate_expression(
            BinaryExpression(
                operator="=",
                left=Identifier(name="x"),
                right=Literal(value=5),
            )
        )
        assert result == "(x = 5)"

    def test_not_equal(self):
        """Test not equal operator."""
        translator = CQLTranslator()
        result = translator.translate_expression(
            BinaryExpression(
                operator="!=",
                left=Identifier(name="x"),
                right=Literal(value=5),
            )
        )
        assert result == "(x != 5)"

    def test_less_than(self):
        """Test less than operator."""
        translator = CQLTranslator()
        result = translator.translate_expression(
            BinaryExpression(
                operator="<",
                left=Identifier(name="age"),
                right=Literal(value=18),
            )
        )
        assert result == "(age < 18)"

    def test_greater_than_or_equal(self):
        """Test greater than or equal operator."""
        translator = CQLTranslator()
        result = translator.translate_expression(
            BinaryExpression(
                operator=">=",
                left=Identifier(name="age"),
                right=Literal(value=18),
            )
        )
        assert result == "(age >= 18)"

    def test_and_operator(self):
        """Test logical AND operator."""
        translator = CQLTranslator()
        result = translator.translate_expression(
            BinaryExpression(
                operator="and",
                left=Literal(value=True),
                right=Literal(value=False),
            )
        )
        assert result == "(true and false)"

    def test_or_operator(self):
        """Test logical OR operator."""
        translator = CQLTranslator()
        result = translator.translate_expression(
            BinaryExpression(
                operator="or",
                left=Literal(value=True),
                right=Literal(value=False),
            )
        )
        assert result == "(true or false)"

    def test_power_operator(self):
        """Test power/exponentiation operator."""
        translator = CQLTranslator()
        result = translator.translate_expression(
            BinaryExpression(
                operator="^",
                left=Literal(value=2),
                right=Literal(value=3),
            )
        )
        assert result == "2.power(3)"


class TestUnaryOperators:
    """Tests for unary operator translation."""

    def test_negation(self):
        """Test numeric negation."""
        translator = CQLTranslator()
        result = translator.translate_expression(
            UnaryExpression(operator="-", operand=Literal(value=5))
        )
        assert result == "(-5)"

    def test_not_operator(self):
        """Test logical NOT operator."""
        translator = CQLTranslator()
        result = translator.translate_expression(
            UnaryExpression(operator="not", operand=Literal(value=True))
        )
        assert result == "(true).not()"


class TestConditionalTranslation:
    """Tests for conditional expression translation."""

    def test_if_then_else(self):
        """Test if-then-else translation."""
        translator = CQLTranslator()
        result = translator.translate_expression(
            ConditionalExpression(
                condition=BinaryExpression(
                    operator=">",
                    left=Identifier(name="x"),
                    right=Literal(value=0),
                ),
                then_expr=Literal(value="positive"),
                else_expr=Literal(value="non-positive"),
            )
        )
        assert "iif(" in result
        assert "positive" in result
        assert "non-positive" in result


class TestCaseExpression:
    """Tests for case expression translation."""

    def test_searched_case(self):
        """Test searched case expression translation."""
        translator = CQLTranslator()
        result = translator.translate_expression(
            CaseExpression(
                case_items=[
                    CaseItem(
                        when=BinaryExpression(
                            operator="<",
                            left=Identifier(name="x"),
                            right=Literal(value=0),
                        ),
                        then=Literal(value="negative"),
                    ),
                    CaseItem(
                        when=BinaryExpression(
                            operator=">",
                            left=Identifier(name="x"),
                            right=Literal(value=0),
                        ),
                        then=Literal(value="positive"),
                    ),
                ],
                else_expr=Literal(value="zero"),
            )
        )
        assert "iif(" in result
        assert "negative" in result
        assert "positive" in result
        assert "zero" in result


class TestFunctionTranslation:
    """Tests for function translation."""

    def test_simple_function(self):
        """Test simple function call."""
        translator = CQLTranslator()
        result = translator.translate_expression(
            FunctionRef(name="Today", arguments=[])
        )
        assert result == "today()"

    def test_function_with_args(self):
        """Test function with arguments."""
        translator = CQLTranslator()
        result = translator.translate_expression(
            FunctionRef(
                name="ToString",
                arguments=[Literal(value=123)],
            )
        )
        assert result == "123.toString()"

    def test_age_in_years(self):
        """Test AgeInYears function translation."""
        translator = CQLTranslator()
        result = translator.translate_expression(
            FunctionRef(name="AgeInYears", arguments=[])
        )
        assert result == "ageInYears($this)"

    def test_exists_function(self):
        """Test exists function translation."""
        translator = CQLTranslator()
        result = translator.translate_expression(
            FunctionRef(
                name="exists",
                arguments=[Identifier(name="conditions")],
            )
        )
        assert result == "conditions.exists()"


class TestQueryTranslation:
    """Tests for query translation."""

    def test_simple_retrieve(self):
        """Test simple retrieve translation."""
        translator = CQLTranslator()
        result = translator.translate_expression(Retrieve(type="Patient"))
        assert result == "__retrieve__:Patient"

    def test_retrieve_with_terminology(self):
        """Test retrieve with terminology."""
        translator = CQLTranslator()
        translator.context.valuesets["Diabetes"] = "http://example.org/ValueSet/diabetes"
        result = translator.translate_expression(
            Retrieve(
                type="Condition",
                terminology=Identifier(name="Diabetes"),
            )
        )
        assert result == "__retrieve__:Condition:http://example.org/ValueSet/diabetes"

    def test_simple_query_with_where(self):
        """Test simple query with where clause."""
        translator = CQLTranslator()
        result = translator.translate_expression(
            Query(
                source=QuerySource(
                    alias="P",
                    expression=Retrieve(type="Patient"),
                ),
                where=WhereClause(
                    expression=BinaryExpression(
                        operator="=",
                        left=Property(source=Identifier(name="P"), path="active"),
                        right=Literal(value=True),
                    )
                ),
            )
        )
        assert "__retrieve__:Patient" in result
        assert ".where(" in result
        assert "active = true" in result


class TestLibraryTranslation:
    """Tests for full library translation."""

    def test_simple_library(self):
        """Test translating a simple library."""
        translator = CQLTranslator()
        library = Library(
            identifier="TestLibrary",
            version="1.0.0",
            context=ContextDefinition(name="Patient"),
            statements=[
                Definition(
                    name="IsActive",
                    expression=BinaryExpression(
                        operator="=",
                        left=Property(source=None, path="active"),
                        right=Literal(value=True),
                    ),
                ),
            ],
        )
        results = translator.translate_library(library)
        assert "IsActive" in results
        assert "active = true" in results["IsActive"].fhirpath

    def test_library_with_valuesets(self):
        """Test library with value set definitions."""
        translator = CQLTranslator()
        library = Library(
            identifier="TestLibrary",
            valuesets=[
                ValueSetDefinition(
                    name="Diabetes",
                    id="http://example.org/ValueSet/diabetes",
                )
            ],
            statements=[
                Definition(
                    name="HasDiabetes",
                    expression=Retrieve(
                        type="Condition",
                        terminology=Identifier(name="Diabetes"),
                    ),
                ),
            ],
        )
        results = translator.translate_library(library)
        assert "HasDiabetes" in results
        assert "http://example.org/ValueSet/diabetes" in results["HasDiabetes"].fhirpath


class TestTranslationContext:
    """Tests for translation context management."""

    def test_with_alias(self):
        """Test creating context with additional alias."""
        ctx = TranslationContext(current_context="Patient", aliases=["P"])
        new_ctx = ctx.with_alias("C")
        assert "P" in new_ctx.aliases
        assert "C" in new_ctx.aliases
        assert "P" in ctx.aliases  # Original unchanged
        assert "C" not in ctx.aliases

    def test_resolve_valueset(self):
        """Test value set resolution."""
        ctx = TranslationContext(
            valuesets={"Diabetes": "http://example.org/ValueSet/diabetes"}
        )
        result = ctx.resolve_valueset("Diabetes")
        assert result == "http://example.org/ValueSet/diabetes"

        result = ctx.resolve_valueset("NonExistent")
        assert result is None


class TestTranslationResult:
    """Tests for translation result."""

    def test_basic_result(self):
        """Test basic translation result."""
        result = TranslationResult(fhirpath="active = true")
        assert result.fhirpath == "active = true"
        assert result.sql is None
        assert result.context == "Unfiltered"
        assert result.dependencies == []

    def test_result_with_all_fields(self):
        """Test translation result with all fields."""
        result = TranslationResult(
            fhirpath="active = true",
            sql="SELECT * FROM Patient WHERE active = true",
            context="Patient",
            dependencies=["BaseDefinition"],
        )
        assert result.fhirpath == "active = true"
        assert result.sql == "SELECT * FROM Patient WHERE active = true"
        assert result.context == "Patient"
        assert "BaseDefinition" in result.dependencies
