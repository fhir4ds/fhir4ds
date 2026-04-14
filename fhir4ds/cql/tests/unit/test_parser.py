"""
Unit tests for CQL parser.

Comprehensive tests covering all CQL R1.5 parsing features.
"""

import pytest

from ...errors import ParseError
from ...parser.lexer import Lexer, TokenType
from ...parser.parser import CQLParser, parse_cql, parse_expression
from ...parser.ast_nodes import (
    BinaryExpression,
    CaseExpression,
    ConditionalExpression,
    DateTimeLiteral,
    Definition,
    ExistsExpression,
    FunctionDefinition,
    FunctionRef,
    Identifier,
    IncludeDefinition,
    IndexerExpression,
    InstanceExpression,
    Interval,
    Library,
    ListExpression,
    Literal,
    NamedTypeSpecifier,
    ParameterDefinition,
    Property,
    QualifiedIdentifier,
    Query,
    QuerySource,
    Retrieve,
    TupleExpression,
    UnaryExpression,
    UsingDefinition,
    ValueSetDefinition,
    CodeSystemDefinition,
    ContextDefinition,
)


class TestParserBasics:
    """Basic parser functionality tests."""

    def test_parser_instance(self):
        """Test creating Parser instance."""
        lexer = Lexer("library Test")
        tokens = lexer.tokenize()
        parser = CQLParser(tokens)
        assert parser.tokens == tokens
        assert parser.pos == 0

    def test_current_token(self):
        """Test getting current token."""
        lexer = Lexer("library Test")
        tokens = lexer.tokenize()
        parser = CQLParser(tokens)
        assert parser.current().type == TokenType.LIBRARY

    def test_peek_token(self):
        """Test peeking at next token."""
        lexer = Lexer("library Test")
        tokens = lexer.tokenize()
        parser = CQLParser(tokens)
        assert parser.peek().type == TokenType.IDENTIFIER


class TestLibraryDeclaration:
    """Tests for library declaration parsing."""

    def test_simple_library(self):
        """Test simple library declaration."""
        library = parse_cql("library MyLibrary")
        assert isinstance(library, Library)
        assert library.identifier == "MyLibrary"
        assert library.version is None

    def test_library_with_version(self):
        """Test library declaration with version."""
        library = parse_cql("library MyLibrary version '1.0.0'")
        assert library.identifier == "MyLibrary"
        assert library.version == "1.0.0"

    def test_library_with_quoted_identifier(self):
        """Test library with quoted identifier."""
        library = parse_cql('library "My-Library"')
        assert library.identifier == "My-Library"


class TestUsingDefinition:
    """Tests for using definition parsing."""

    def test_simple_using(self):
        """Test simple using declaration."""
        library = parse_cql("""
            library Test
            using FHIR
        """)
        assert len(library.using) == 1
        assert library.using[0].model == "FHIR"
        assert library.using[0].version is None

    def test_using_with_version(self):
        """Test using declaration with version."""
        library = parse_cql("""
            library Test
            using FHIR version '4.0.1'
        """)
        assert library.using[0].model == "FHIR"
        assert library.using[0].version == "4.0.1"


class TestIncludeDefinition:
    """Tests for include definition parsing."""

    def test_simple_include(self):
        """Test simple include declaration."""
        library = parse_cql("""
            library Test
            include FHIRHelpers
        """)
        assert len(library.includes) == 1
        assert library.includes[0].path == "FHIRHelpers"

    def test_include_with_version(self):
        """Test include declaration with version."""
        library = parse_cql("""
            library Test
            include FHIRHelpers version '4.0.1'
        """)
        assert library.includes[0].path == "FHIRHelpers"
        assert library.includes[0].version == "4.0.1"

    def test_include_with_alias(self):
        """Test include declaration with alias."""
        library = parse_cql("""
            library Test
            include FHIRHelpers called FH
        """)
        assert library.includes[0].path == "FHIRHelpers"
        assert library.includes[0].alias == "FH"


class TestParameterDefinition:
    """Tests for parameter definition parsing."""

    def test_simple_parameter(self):
        """Test simple parameter declaration."""
        library = parse_cql("""
            library Test
            parameter MeasurementPeriod
        """)
        assert len(library.parameters) == 1
        assert library.parameters[0].name == "MeasurementPeriod"

    def test_parameter_with_type(self):
        """Test parameter with type specifier."""
        library = parse_cql("""
            library Test
            parameter MaxAge Integer
        """)
        assert library.parameters[0].name == "MaxAge"
        assert library.parameters[0].type is not None

    def test_parameter_with_default(self):
        """Test parameter with default value."""
        library = parse_cql("""
            library Test
            parameter MaxAge Integer default 100
        """)
        assert library.parameters[0].name == "MaxAge"
        assert library.parameters[0].default is not None


class TestContextDefinition:
    """Tests for context definition parsing."""

    def test_patient_context(self):
        """Test Patient context."""
        library = parse_cql("""
            library Test
            context Patient
        """)
        assert library.context is not None
        assert library.context.name == "Patient"

    def test_population_context(self):
        """Test Population context."""
        library = parse_cql("""
            library Test
            context Population
        """)
        assert library.context.name == "Population"


class TestDefinition:
    """Tests for define statement parsing."""

    def test_simple_definition(self):
        """Test simple define statement."""
        library = parse_cql("""
            library Test
            define X: 42
        """)
        assert len(library.statements) == 1
        assert isinstance(library.statements[0], Definition)
        assert library.statements[0].name == "X"

    def test_definition_with_expression(self):
        """Test define with expression."""
        library = parse_cql("""
            library Test
            define Sum: 1 + 2
        """)
        statement = library.statements[0]
        assert statement.name == "Sum"
        assert isinstance(statement.expression, BinaryExpression)

    def test_definition_with_quoted_name(self):
        """Test define with quoted name."""
        library = parse_cql("""
            library Test
            define "In Demographic": true
        """)
        assert library.statements[0].name == "In Demographic"


class TestLiteralExpressions:
    """Tests for literal expression parsing."""

    def test_integer_literal(self):
        """Test integer literal."""
        expr = parse_expression("42")
        assert isinstance(expr, Literal)
        assert expr.value == 42
        assert expr.type == "Integer"

    def test_decimal_literal(self):
        """Test decimal literal."""
        expr = parse_expression("3.14")
        assert isinstance(expr, Literal)
        assert expr.value == 3.14
        assert expr.type == "Decimal"

    def test_string_literal(self):
        """Test string literal."""
        expr = parse_expression("'hello'")
        assert isinstance(expr, Literal)
        assert expr.value == "hello"
        assert expr.type == "String"

    def test_true_literal(self):
        """Test true literal."""
        expr = parse_expression("true")
        assert isinstance(expr, Literal)
        assert expr.value is True
        assert expr.type == "Boolean"

    def test_false_literal(self):
        """Test false literal."""
        expr = parse_expression("false")
        assert isinstance(expr, Literal)
        assert expr.value is False
        assert expr.type == "Boolean"

    def test_null_literal(self):
        """Test null literal."""
        expr = parse_expression("null")
        assert isinstance(expr, Literal)
        assert expr.value is None


class TestDateTimeLiterals:
    """Tests for date/time literal parsing."""

    def test_date_literal(self):
        """Test date literal."""
        expr = parse_expression("@2024-01-15")
        assert isinstance(expr, DateTimeLiteral)
        assert expr.value == "2024-01-15"

    def test_datetime_literal(self):
        """Test datetime literal."""
        expr = parse_expression("@2024-01-15T12:30:00")
        assert isinstance(expr, DateTimeLiteral)
        assert expr.value == "2024-01-15T12:30:00"


class TestIdentifierExpressions:
    """Tests for identifier expression parsing."""

    def test_simple_identifier(self):
        """Test simple identifier."""
        expr = parse_expression("Patient")
        assert isinstance(expr, Identifier)
        assert expr.name == "Patient"

    def test_qualified_identifier(self):
        """Test qualified identifier (parsed as property access)."""
        expr = parse_expression("FHIR.Patient")
        # In expression context, dotted identifiers are parsed as property access
        assert isinstance(expr, Property)
        assert expr.path == "Patient"
        assert isinstance(expr.source, Identifier)

    def test_quoted_identifier(self):
        """Test quoted identifier."""
        expr = parse_expression('"My-Identifier"')
        assert isinstance(expr, Identifier)
        assert expr.name == "My-Identifier"


class TestBinaryExpressions:
    """Tests for binary expression parsing."""

    def test_addition(self):
        """Test addition expression."""
        expr = parse_expression("1 + 2")
        assert isinstance(expr, BinaryExpression)
        assert expr.operator == "+"
        assert isinstance(expr.left, Literal)
        assert isinstance(expr.right, Literal)

    def test_subtraction(self):
        """Test subtraction expression."""
        expr = parse_expression("5 - 3")
        assert expr.operator == "-"

    def test_multiplication(self):
        """Test multiplication expression."""
        expr = parse_expression("4 * 2")
        assert expr.operator == "*"

    def test_division(self):
        """Test division expression."""
        expr = parse_expression("10 / 2")
        assert expr.operator == "/"

    def test_comparison_less_than(self):
        """Test less than comparison."""
        expr = parse_expression("x < 10")
        assert expr.operator == "<"

    def test_comparison_greater_than(self):
        """Test greater than comparison."""
        expr = parse_expression("x > 5")
        assert expr.operator == ">"

    def test_comparison_less_equal(self):
        """Test less than or equal comparison."""
        expr = parse_expression("x <= 10")
        assert expr.operator == "<="

    def test_comparison_greater_equal(self):
        """Test greater than or equal comparison."""
        expr = parse_expression("x >= 5")
        assert expr.operator == ">="

    def test_equality(self):
        """Test equality expression."""
        expr = parse_expression("x = 5")
        assert expr.operator == "="

    def test_inequality(self):
        """Test inequality expression."""
        expr = parse_expression("x != 5")
        assert expr.operator == "!="

    def test_logical_and(self):
        """Test logical AND expression."""
        expr = parse_expression("true and false")
        assert expr.operator == "and"

    def test_logical_or(self):
        """Test logical OR expression."""
        expr = parse_expression("true or false")
        assert expr.operator == "or"

    def test_precedence(self):
        """Test operator precedence."""
        expr = parse_expression("1 + 2 * 3")
        # Should be 1 + (2 * 3) due to precedence
        assert expr.operator == "+"
        assert expr.right.operator == "*"


class TestUnaryExpressions:
    """Tests for unary expression parsing."""

    def test_negation(self):
        """Test numeric negation."""
        expr = parse_expression("-5")
        assert isinstance(expr, UnaryExpression)
        assert expr.operator == "-"
        assert isinstance(expr.operand, Literal)

    def test_not(self):
        """Test logical NOT."""
        expr = parse_expression("not true")
        assert isinstance(expr, UnaryExpression)
        assert expr.operator == "not"


class TestPropertyAccess:
    """Tests for property access expression parsing."""

    def test_simple_property(self):
        """Test simple property access."""
        expr = parse_expression("Patient.name")
        assert isinstance(expr, Property)
        assert expr.path == "name"
        assert isinstance(expr.source, Identifier)

    def test_chained_property(self):
        """Test chained property access."""
        expr = parse_expression("Patient.address.city")
        assert isinstance(expr, Property)
        assert expr.path == "city"
        assert isinstance(expr.source, Property)


class TestFunctionCalls:
    """Tests for function call expression parsing."""

    def test_simple_function(self):
        """Test simple function call."""
        expr = parse_expression("Today()")
        assert isinstance(expr, FunctionRef)
        assert expr.name == "Today"
        assert len(expr.arguments) == 0

    def test_function_with_argument(self):
        """Test function with one argument."""
        expr = parse_expression("ToString(42)")
        assert isinstance(expr, FunctionRef)
        assert expr.name == "ToString"
        assert len(expr.arguments) == 1

    def test_function_with_multiple_arguments(self):
        """Test function with multiple arguments."""
        expr = parse_expression("Substring('hello', 1, 3)")
        assert isinstance(expr, FunctionRef)
        assert expr.name == "Substring"
        assert len(expr.arguments) == 3

    def test_qualified_function(self):
        """Test qualified function call.

        Note: With Phase 7 method invocation support, FHIRHelpers.ToQuantity(value)
        is now parsed as a MethodInvocation (source=FHIRHelpers, method=ToQuantity)
        rather than a FunctionRef. This is the correct CQL R1.5 behavior.
        """
        from ...parser.ast_nodes import MethodInvocation

        expr = parse_expression("FHIRHelpers.ToQuantity(value)")
        assert isinstance(expr, MethodInvocation)
        assert expr.method == "ToQuantity"
        assert isinstance(expr.source, Identifier)
        assert expr.source.name == "FHIRHelpers"
        assert len(expr.arguments) == 1


class TestIntervalExpressions:
    """Tests for interval expression parsing."""

    def test_closed_interval(self):
        """Test closed interval."""
        expr = parse_expression("Interval[1, 10]")
        assert isinstance(expr, Interval)
        assert expr.low_closed is True
        assert expr.high_closed is True

    def test_open_interval(self):
        """Test open interval with keyword."""
        expr = parse_expression("Interval[1, 10)")
        assert isinstance(expr, Interval)
        assert expr.low_closed is True
        assert expr.high_closed is False

    def test_interval_with_literals(self):
        """Test interval with literal bounds."""
        expr = parse_expression("Interval[@2024-01-01, @2024-12-31]")
        assert isinstance(expr, Interval)
        assert isinstance(expr.low, DateTimeLiteral)
        assert isinstance(expr.high, DateTimeLiteral)


class TestListExpressions:
    """Tests for list expression parsing."""

    def test_empty_list(self):
        """Test empty list."""
        expr = parse_expression("{}")
        assert isinstance(expr, ListExpression)
        assert len(expr.elements) == 0

    def test_simple_list(self):
        """Test simple list."""
        expr = parse_expression("{1, 2, 3}")
        assert isinstance(expr, ListExpression)
        assert len(expr.elements) == 3

    def test_mixed_list(self):
        """Test list with mixed types."""
        expr = parse_expression("{1, 'two', true}")
        assert isinstance(expr, ListExpression)
        assert len(expr.elements) == 3


class TestRetrieveExpressions:
    """Tests for retrieve expression parsing."""

    def test_simple_retrieve(self):
        """Test simple retrieve."""
        expr = parse_expression("[Patient]")
        assert isinstance(expr, Retrieve)
        assert expr.type == "Patient"
        assert expr.terminology is None

    def test_retrieve_with_terminology(self):
        """Test retrieve with terminology filter."""
        expr = parse_expression('[Condition: "Diabetes"]')
        assert isinstance(expr, Retrieve)
        assert expr.type == "Condition"
        assert expr.terminology is not None

    def test_retrieve_with_valueset(self):
        """Test retrieve with value set reference."""
        expr = parse_expression("[Observation: ObservationCodes]")
        assert isinstance(expr, Retrieve)
        assert expr.type == "Observation"


class TestConditionalExpressions:
    """Tests for conditional expression parsing."""

    def test_simple_conditional(self):
        """Test simple if-then-else."""
        expr = parse_expression("if true then 1 else 0")
        assert isinstance(expr, ConditionalExpression)
        assert isinstance(expr.condition, Literal)
        assert isinstance(expr.then_expr, Literal)
        assert isinstance(expr.else_expr, Literal)

    def test_conditional_with_comparison(self):
        """Test conditional with comparison."""
        expr = parse_expression("if x > 0 then 'positive' else 'non-positive'")
        assert isinstance(expr, ConditionalExpression)
        assert isinstance(expr.condition, BinaryExpression)


class TestCaseExpressions:
    """Tests for case expression parsing."""

    def test_simple_case(self):
        """Test simple case expression."""
        expr = parse_expression("""
            case
                when x < 0 then 'negative'
                when x > 0 then 'positive'
                else 'zero'
            end
        """)
        assert isinstance(expr, CaseExpression)
        assert len(expr.case_items) == 2
        assert expr.else_expr is not None


class TestParenthesizedExpressions:
    """Tests for parenthesized expression parsing."""

    def test_simple_parentheses(self):
        """Test simple parenthesized expression."""
        expr = parse_expression("(1 + 2)")
        assert isinstance(expr, BinaryExpression)

    def test_nested_parentheses(self):
        """Test nested parentheses."""
        expr = parse_expression("((1 + 2) * 3)")
        assert isinstance(expr, BinaryExpression)
        assert expr.operator == "*"

    def test_precedence_override(self):
        """Test parentheses overriding precedence."""
        expr = parse_expression("(1 + 2) * 3")
        assert expr.operator == "*"
        assert expr.left.operator == "+"


class TestIndexerExpressions:
    """Tests for indexer expression parsing."""

    def test_simple_indexer(self):
        """Test simple indexer."""
        expr = parse_expression("items[0]")
        assert isinstance(expr, IndexerExpression)
        assert isinstance(expr.source, Identifier)
        assert isinstance(expr.index, Literal)

    def test_property_indexer(self):
        """Test indexer on property."""
        expr = parse_expression("Patient.names[0]")
        assert isinstance(expr, IndexerExpression)
        assert isinstance(expr.source, Property)


class TestComplexExpressions:
    """Tests for complex expression parsing."""

    def test_combined_operators(self):
        """Test combined operators."""
        expr = parse_expression("a + b * c - d / e")
        assert isinstance(expr, BinaryExpression)

    def test_method_chain(self):
        """Test method chaining."""
        expr = parse_expression("Patient.name.given")
        assert isinstance(expr, Property)
        assert expr.path == "given"

    def test_function_in_expression(self):
        """Test function call in expression."""
        expr = parse_expression("AgeInYears() >= 18")
        assert isinstance(expr, BinaryExpression)
        assert isinstance(expr.left, FunctionRef)


class TestTerminologyDefinitions:
    """Tests for terminology definition parsing."""

    def test_codesystem_definition(self):
        """Test codesystem definition."""
        library = parse_cql("""
            library Test
            codesystem LOINC: 'http://loinc.org'
        """)
        assert len(library.codesystems) == 1
        assert library.codesystems[0].name == "LOINC"
        assert library.codesystems[0].id == "http://loinc.org"

    def test_valueset_definition(self):
        """Test valueset definition."""
        library = parse_cql("""
            library Test
            valueset "Diabetes Codes": 'http://example.org/ValueSet/diabetes'
        """)
        assert len(library.valuesets) == 1
        assert library.valuesets[0].name == "Diabetes Codes"


class TestFunctionDefinitions:
    """Tests for function definition parsing."""

    def test_simple_function_definition(self):
        """Test simple function definition."""
        library = parse_cql("""
            library Test
            define function Double(x Integer): x * 2
        """)
        assert len(library.statements) == 1
        func_def = library.statements[0]
        assert isinstance(func_def, FunctionDefinition)
        assert func_def.name == "Double"
        assert len(func_def.parameters) == 1

    def test_function_with_return_type(self):
        """Test function with explicit return type."""
        library = parse_cql("""
            library Test
            define function Add(a Integer, b Integer) returns Integer: a + b
        """)
        func_def = library.statements[0]
        assert isinstance(func_def, FunctionDefinition)
        assert func_def.name == "Add"


class TestErrorHandling:
    """Tests for parser error handling."""

    def test_unexpected_token(self):
        """Test unexpected token error."""
        with pytest.raises(ParseError):
            parse_cql("library Test invalid_keyword")

    def test_missing_colon(self):
        """Test missing colon error."""
        with pytest.raises(ParseError):
            parse_cql("library Test define X 42")

    def test_unexpected_eof(self):
        """Test unexpected EOF error."""
        with pytest.raises(ParseError):
            parse_expression("1 +")


class TestFullLibraryParsing:
    """Tests for parsing complete CQL libraries."""

    def test_fhir_quality_measure(self):
        """Test parsing a typical FHIR quality measure library."""
        cql = """
        library Example version '1.0.0'

        using FHIR version '4.0.1'

        include FHIRHelpers version '4.0.1' called FHIRHelpers

        codesystem LOINC: 'http://loinc.org'
        valueset "Office Visit": 'http://example.org/ValueSet/office-visit'

        parameter "Measurement Period" Interval<DateTime>

        context Patient

        define "In Demographic":
            Patient.age >= 18

        define "Office Visits":
            [Encounter: "Office Visit"] E
                where E.status = 'finished'

        define "Has Office Visit":
            exists "Office Visits"
        """
        library = parse_cql(cql)
        assert library.identifier == "Example"
        assert library.version == "1.0.0"
        assert len(library.using) == 1
        assert len(library.includes) == 1
        assert len(library.codesystems) == 1
        assert len(library.valuesets) == 1
        assert len(library.parameters) == 1
        assert library.context is not None
        assert len(library.statements) == 3
