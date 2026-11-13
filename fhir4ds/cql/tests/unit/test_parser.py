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

    def test_ratio_literal_lowers_to_toratio(self):
        """Test quantity:quantity ratio literal parsing."""
        expr = parse_expression("1'cm':2.1'cm'")
        assert isinstance(expr, FunctionRef)
        assert expr.name == "ToRatio"
        assert len(expr.arguments) == 1
        assert isinstance(expr.arguments[0], Literal)
        assert expr.arguments[0].value == "1 'cm':2.1 'cm'"

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

    def test_valueset_definition_with_codesystems(self):
        """Test valueset definition with CQL 1.5 codesystems overrides."""
        library = parse_cql("""
            library Test
            codesystem "SNOMED-CT:2024": 'http://snomed.info/sct' version '2024'
            codesystem LOINC: 'http://loinc.org' version '2.74'
            valueset Diabetes: 'http://example.org/fhir/ValueSet/diabetes' version '2026'
              codesystems { "SNOMED-CT:2024", LOINC }
        """)
        assert len(library.valuesets) == 1
        assert library.valuesets[0].name == "Diabetes"
        assert library.valuesets[0].id == "http://example.org/fhir/ValueSet/diabetes"
        assert library.valuesets[0].version == "2026"
        assert library.valuesets[0].codesystems == ["SNOMED-CT:2024", "LOINC"]


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


class TestDqmContentCms2025Syntax:
    """Syntax forms required by the dqm-content-cms-2025 (US Core) suite:
    FHIRPath-style dot-where, convert-to-quoted-unit, bare boundary
    qualifiers, quoted model-qualified retrieves, and 'context' as a
    property name."""

    def _parse_expr(self, expr: str):
        src = "library T version '1'\nusing FHIR version '4.0.1'\ndefine F: " + expr
        return parse_cql(src)

    def test_dot_where_filters_source(self):
        from fhir4ds.cql.parser.ast_nodes import Query
        lib = self._parse_expr('Patient.identifier.where(type ~ "x").single().value')
        node = lib.statements[0].expression
        # .single()/property chain wraps the Query emitted by .where()
        while not isinstance(node, Query):
            node = getattr(node, "source", None) or getattr(node, "operand", None) \
                or getattr(node, "left", None)
            assert node is not None
        assert node.where is not None

    def test_convert_to_quoted_unit(self):
        from fhir4ds.cql.parser.ast_nodes import BinaryExpression, Literal
        lib = self._parse_expr("convert X.value to 'm2'")
        node = lib.statements[0].expression
        assert isinstance(node, BinaryExpression)
        assert node.operator == "convert"
        assert isinstance(node.right, Literal)
        assert node.right.value == "m2"

    def test_before_end_bare_qualifier(self):
        lib = self._parse_expr("A.onset before end B.period")
        node = lib.statements[0].expression
        assert getattr(node, "operator", None) == "before"
        from fhir4ds.cql.parser.ast_nodes import UnaryExpression
        assert isinstance(node.right, UnaryExpression)
        assert node.right.operator == "end of"

    def test_after_start_bare_qualifier_with_of(self):
        lib = self._parse_expr("A.onset after start of B.period")
        node = lib.statements[0].expression
        assert getattr(node, "operator", None) == "after"

    def test_quoted_model_qualified_retrieve_strips_namespace(self):
        from fhir4ds.cql.parser.ast_nodes import Retrieve
        lib = self._parse_expr('["USCore.BMIProfile"] BMI')
        node = lib.statements[0].expression
        assert isinstance(node.source if hasattr(node, "source") else node, (Query,)) or True
        # Walk to the Retrieve under any query wrapper
        stack = [lib.statements[0].expression]
        while stack:
            cur = stack.pop()
            if isinstance(cur, Retrieve):
                assert cur.type == "BMIProfile"
                return
            for child in (getattr(cur, "__dict__", {}) or {}).values():
                if isinstance(child, tuple):
                    stack.extend(child)
                elif hasattr(child, "__dict__"):
                    stack.append(child)
        raise AssertionError("no Retrieve found")

    def test_context_as_property_name(self):
        lib = self._parse_expr("R.context")
        node = lib.statements[0].expression
        assert getattr(node, "path", None) == "context"


class TestDifferenceBetweenTrailingIn:
    """CMS771: `difference in months between A and B in Interval[6, 12]` —
    the trailing `in Interval` applies to the whole difference expression
    (official CMS content semantics), not to operand B alone."""

    def _parse(self, text):
        from ...parser import parse_cql
        lib = parse_cql(
            "library T version '1'\nusing FHIR version '4.0.1'\n"
            "include FHIRHelpers version '4.0.1' called FHIRHelpers\n"
            "context Patient\n" + text
        )
        for stmt in lib.statements:
            if type(stmt).__name__ == "Definition" and stmt.name == "T":
                return stmt.expression
        raise AssertionError("define T not found")

    def test_difference_between_trailing_in_interval(self):
        e = self._parse(
            "define T:\n"
            "  difference in months between @2024-01-01 and @2024-06-01 in Interval[6, 12]"
        )
        from ...parser.ast_nodes import BinaryExpression, DifferenceBetween
        assert isinstance(e, BinaryExpression) and e.operator == "in", type(e)
        assert isinstance(e.left, DifferenceBetween)
        # The interval high operand must be the bare date, not `date in Interval`.
        assert str(e.left.operand_right).find("Interval") == -1

    def test_duration_between_trailing_in_interval(self):
        e = self._parse(
            "define T:\n"
            "  months between @2024-01-01 and @2024-06-01 in Interval[6, 12]"
        )
        from ...parser.ast_nodes import BinaryExpression, DurationBetween
        assert isinstance(e, BinaryExpression) and e.operator == "in", type(e)
        assert isinstance(e.left, DurationBetween)

    def test_difference_between_plain(self):
        e = self._parse(
            "define T:\n"
            "  difference in months between @2024-01-01 and @2024-06-01"
        )
        from ...parser.ast_nodes import DifferenceBetween
        assert isinstance(e, DifferenceBetween)


class TestExternalReviewB1ParserTokenDiscipline:
    """Regression coverage for the 2026-11-13 external parser review, batch B1
    (TRIAGE_cql_review_20261113.md): quoted-identifier attribution, silent
    token drops in speculative timing-phrase branches, and the let-clause
    trailing comma."""

    def test_quoted_flag_describes_the_consumed_token(self):
        # PAR-001: `quoted` was computed from peek() (pos+1), inverting it.
        ident = parse_expression('"My Quoted Def"')
        assert type(ident).__name__ == "Identifier"
        assert ident.name == "My Quoted Def" and ident.quoted is True

    def test_unquoted_identifier_followed_by_alias_is_not_quoted(self):
        ast = parse_expression('UnquotedSource "P"')
        src = ast.source.expression
        assert src.name == "UnquotedSource" and src.quoted is False
        assert ast.source.alias == "P"

    def test_stray_properly_is_not_silently_dropped(self):
        # PAR-003: `true properly` used to return Literal(True).
        with pytest.raises(ParseError):
            parse_expression("true properly")

    def test_bare_within_without_quantity_is_not_silently_dropped(self):
        # PAR-003: `true within 5` used to return Literal(True).
        with pytest.raises(ParseError):
            parse_expression("true within 5")

    def test_starts_within_interval_is_not_silently_dropped(self):
        # Grammar requires `within <quantity> <unit> of`; a bare
        # `starts within <expr>` must be a ParseError, not `starts <expr>`.
        with pytest.raises(ParseError):
            parse_expression("Interval[1, 5] starts within Interval[1, 5]")

    def test_valid_starts_within_quantity_of_still_parses(self):
        ast = parse_expression(
            "[Encounter] E where E.period starts within 3 days of @2024-01-01"
        )
        assert ast.where is not None

    def test_let_clause_trailing_comma_is_a_parse_error(self):
        # PAR-003 (let): the trailing comma used to be consumed and dropped.
        with pytest.raises(ParseError):
            parse_cql(
                "library T\nusing FHIR version '4.0.1'\ncontext Patient\n"
                "define \"D\": [Patient] P let x: 1, where P.active = true"
            )

    def test_let_clause_multi_binding_still_parses(self):
        ast = parse_cql(
            "library T\nusing FHIR version '4.0.1'\ncontext Patient\n"
            "define \"D\": [Patient] P let x: 1, y: 2 return x + y"
        )
        assert ast is not None

    def test_multi_word_keyword_spanning_newline_tracks_line(self):
        # PAR-002 (line tracking): the token AFTER `or more` spanning a
        # newline used to report the keyword's start line.
        from ...parser.lexer import Lexer
        tokens = Lexer("1 = 1 or\nmore garbage").tokenize()
        # `or\nmore` lexes as one OR_MORE token; the following token must be
        # on line 2.
        after = [t for t in tokens if t.type not in (TokenType.INTEGER,)]
        or_more = next(t for t in tokens if t.type == TokenType.OR_MORE)
        idx = tokens.index(or_more)
        assert tokens[idx + 1].line == 2


class TestExternalReviewB2DurationBetweenOperandTier:
    """Regression coverage for the 2026-11-13 external parser review, batch B2
    (TRIAGE_cql_review_20261113.md, PAR-004): durationBetweenExpression /
    differenceBetweenExpression operands are expressionTerm in the CQL 1.5
    grammar, so arithmetic (+ -) is absorbed but inequality/equality/
    membership/logical operators must bind OUTSIDE the duration-between.
    Also covers the `duration in <precision> between` keyword form, which
    previously misparsed as Bin('in', Identifier, DurationBetween)."""

    def _parse_expr(self, body: str):
        return parse_expression(body)

    def test_inequality_binds_outside_duration_between(self):
        e = self._parse_expr("years between @2024-01-01 and @2024-06-01 >= 5")
        from ...parser.ast_nodes import BinaryExpression, DurationBetween
        assert isinstance(e, BinaryExpression) and e.operator == ">=", type(e)
        assert isinstance(e.left, DurationBetween)

    def test_equality_binds_outside_duration_between(self):
        e = self._parse_expr("months between X and Y = 3")
        from ...parser.ast_nodes import BinaryExpression, DurationBetween
        assert isinstance(e, BinaryExpression) and e.operator == "="
        assert isinstance(e.left, DurationBetween)

    def test_logical_and_binds_outside_duration_between(self):
        e = self._parse_expr("years between A and B and flag")
        from ...parser.ast_nodes import BinaryExpression, DurationBetween
        assert isinstance(e, BinaryExpression) and e.operator == "and"
        assert isinstance(e.left, DurationBetween)

    def test_arithmetic_still_absorbed_into_operands(self):
        e = self._parse_expr("years between A + 1 day and B - 1 day")
        from ...parser.ast_nodes import BinaryExpression, DurationBetween
        assert isinstance(e, DurationBetween)
        assert isinstance(e.operand_left, BinaryExpression) and e.operand_left.operator == "+"
        assert isinstance(e.operand_right, BinaryExpression) and e.operand_right.operator == "-"

    def test_duration_in_precision_between_keyword_form(self):
        e = self._parse_expr("duration in years between @2024-01-01 and @2024-06-01")
        from ...parser.ast_nodes import BinaryExpression, DurationBetween
        assert isinstance(e, DurationBetween) and e.precision == "year", type(e)
        assert not isinstance(e, BinaryExpression)

    def test_duration_in_precision_between_inside_comparison(self):
        e = self._parse_expr("duration in days between A and B >= 3")
        from ...parser.ast_nodes import BinaryExpression, DurationBetween
        assert isinstance(e, BinaryExpression) and e.operator == ">="
        assert isinstance(e.left, DurationBetween) and e.left.precision == "day"

    def test_difference_between_operands_are_term_tier(self):
        e = self._parse_expr("difference in months between A and B in Interval[6, 12]")
        from ...parser.ast_nodes import BinaryExpression, DifferenceBetween, Interval as Iv
        assert isinstance(e, BinaryExpression) and e.operator == "in"
        assert isinstance(e.left, DifferenceBetween)
        assert isinstance(e.right, Iv)

    def test_unparenthesized_cast_operand_is_rejected_parentheses_work(self):
        # Strict grammar: typeExpression sits above expressionTerm, so an
        # unparenthesized `X as DateTime` operand is a ParseError; the
        # parenthesized form is the sanctioned spelling.
        with pytest.raises(ParseError):
            self._parse_expr("days between A as DateTime and B")
        e = self._parse_expr("days between (A as DateTime) and B")
        from ...parser.ast_nodes import DurationBetween
        assert isinstance(e, DurationBetween)


class TestExternalReviewB3LexerLiterals:
    """Regression coverage for the 2026-11-13 external parser review, batch B3
    (TRIAGE_cql_review_20261113.md): PAR-005 (ratio literal float repr) and
    PAR-009 (Time-literal token typing, month-precision calendar validation,
    greedy datetime lexing past a non-digit '.')."""

    def test_ratio_literal_preserves_authored_decimal_text(self):
        # PAR-005: `0.00001 'mg'` must NOT render as `1e-05 'mg'` in the
        # ToRatio argument (float repr corrupted small decimals).
        e = parse_expression("0.00001 'mg':1 'mg'")
        assert type(e).__name__ == "FunctionRef" and e.name == "ToRatio"
        assert e.arguments[0].value == "0.00001 'mg':1 'mg'"

    def test_ratio_literal_denominator_preserves_authored_decimal_text(self):
        e = parse_expression("1 'mg':0.00001 'mg'")
        assert e.arguments[0].value == "1 'mg':0.00001 'mg'"

    def test_ratio_literal_preserves_long_decimal_text(self):
        # Beyond float precision — authored text must survive verbatim.
        e = parse_expression("0.12345678901234567890 'g':1 'g'")
        assert e.arguments[0].value == "0.12345678901234567890 'g':1 'g'"

    def test_month_precision_literal_validates_month_range(self):
        # PAR-009: `@2024-13` used to lex successfully (the 3-component
        # calendar check never ran for the YYYY-MM shape).
        from ...parser.lexer import LexerError

        with pytest.raises(LexerError):
            parse_expression("@2024-13")
        with pytest.raises(LexerError):
            parse_expression("@2024-00")
        assert parse_expression("@2024-02") is not None

    def test_t_prefixed_literal_is_time_literal(self):
        # PAR-009: `@T...` is the grammar's TIME token, not DATETIME.
        from ...parser.ast_nodes import TimeLiteral

        e = parse_expression("@T12:30:00")
        assert isinstance(e, TimeLiteral) and e.value == "T12:30:00"

    def test_datetime_literal_postfix_invocation_not_swallowed(self):
        # PAR-009: greedy datetime lexing used to eat `.toString` into the
        # literal, making the whole expression an invalid-literal LexerError.
        e = parse_expression("@2024-01-15.toString()")
        assert type(e).__name__ == "MethodInvocation"
        e2 = parse_expression("@T14:30:22.5")
        assert e2.value == "T14:30:22.5"


class TestExternalReviewB4GrammarGaps:
    """Regression coverage for the 2026-11-13 external parser review, batch B4
    (TRIAGE_cql_review_20261113.md): PAR-007 (bare `flatten X` misparse,
    `1 foo` over-acceptance) and PAR-008 subset (typed list selector
    `List<T>{...}`, concept selector `Concept { Code ... }`)."""

    def test_bare_flatten_prefix_parses_as_function(self):
        # PAR-007: `flatten X` misparsed as Query(source=Identifier('flatten'),
        # alias=X). Grammar: `('distinct'|'flatten') expression`.
        e = parse_expression("flatten {1, 2}")
        assert type(e).__name__ == "FunctionRef" and e.name == "flatten"
        e2 = parse_expression("flatten X")
        assert type(e2).__name__ == "FunctionRef" and e2.name == "flatten"

    def test_bare_literal_alias_is_rejected(self):
        # PAR-007: `1 foo` is invalid grammar — querySource is a retrieve,
        # identifier, or parenthesized expression.
        from ...errors import ParseError

        for src in ["1 foo", "'x' bar", "true foo"]:
            with pytest.raises(ParseError):
                parse_expression(src)

    def test_parenthesized_literal_alias_still_accepted(self):
        # Grammar querySource admits '(' expression ')' — parens are valid.
        e = parse_expression("(1) X return X")
        assert type(e).__name__ == "Query"

    def test_typed_list_selector(self):
        # PAR-008: `List<Code>{ }` misparsed as chained </> comparisons.
        e = parse_expression("List<Code>{ }")
        from ...parser.ast_nodes import BinaryExpression, ListExpression, ListTypeSpecifier
        assert isinstance(e, BinaryExpression) and e.operator == "as"
        assert isinstance(e.left, ListExpression) and not e.left.elements
        assert isinstance(e.right, ListTypeSpecifier)

    def test_untyped_list_selector_and_typed_elements(self):
        assert type(parse_expression("List{1, 2}")).__name__ == "ListExpression"
        e = parse_expression("List<Integer>{1, 2, 3}")
        assert e.operator == "as" and len(e.left.elements) == 3

    def test_concept_selector_with_inline_codes(self):
        # PAR-008: `Concept { Code 'x' from "CS" }` was a ParseError.
        e = parse_expression('Concept { Code \'x\' from "CS" }')
        from ...parser.ast_nodes import InstanceExpression, ListExpression
        assert isinstance(e, InstanceExpression) and e.type == "Concept"
        assert e.elements[0].name == "codes"
        assert isinstance(e.elements[0].type, ListExpression)

    def test_concept_named_field_instance_still_supported(self):
        # The named-field form `Concept { codes: {...} }` predates the selector
        # and must keep its generic instance parse.
        e = parse_expression('Concept { codes: { Code \'x\' from "CS" } }')
        assert type(e).__name__ == "InstanceExpression" and e.type == "Concept"
        assert e.elements[0].name == "codes"

    def test_concept_selector_named_code_and_display_translate(self):
        # Review finding (B4): named-code members must emit quoted Identifiers
        # (the fold-resolvable shape), never bare str, and the grammar's
        # whole-selector display clause must parse. Verified end-to-end.
        cql = (
            "library L\n"
            'codesystem "CS": \'http://loinc.org\'\n'
            'code "N": \'x\' from "CS"\n'
            "context Unfiltered\n"
            'define C1: Concept { "N" }\n'
            'define C2: Concept { "N", Code \'y\' from "CS" } display \'Disp\'\n'
        )
        lib = parse_cql(cql)  # parse-only smoke
        assert len(lib.statements) >= 2

        from fhir4ds.cql import translate_cql

        res = translate_cql(cql)
        sql1 = res["C1"].to_sql() if hasattr(res["C1"], "to_sql") else str(res["C1"])
        assert '"code":"x"' in sql1 and '"system":"http://loinc.org"' in sql1
        sql2 = res["C2"].to_sql() if hasattr(res["C2"], "to_sql") else str(res["C2"])
        assert '"display":"Disp"' in sql2 and sql2.count('"code"') == 2


class TestExternalReviewB4bLibraryGrammar:
    """Regression coverage for the 2026-11-13 external parser review, batch
    B4 remainder (TRIAGE_cql_review_20261113.md, PAR-008): qualified library
    name, access modifiers on defines, and library-qualified Code selectors."""

    def test_qualified_library_name(self):
        lib = parse_cql("library a.b.C version '1.0.0'\ncontext Patient\ndefine X: 1")
        assert lib.identifier == "a.b.C"

    def test_access_modifiers_on_defines(self):
        for mod in ("private", "public"):
            lib = parse_cql(
                f"library L\ncontext Patient\ndefine {mod} X: 1"
            )
            d = [s for s in lib.statements if hasattr(s, "expression")][0]
            assert d.access_level == mod
            assert d.name == "X"

    def test_define_named_private_without_modifier(self):
        # `define "private": 1` — quoted name, not an access modifier. And an
        # unquoted `define private: 1` treats 'private' as the NAME (no
        # identifier follows it).
        lib = parse_cql('library L\ncontext Patient\ndefine "private": 1')
        d = [s for s in lib.statements if hasattr(s, "expression")][0]
        assert d.name == "private" and d.access_level is None
        lib2 = parse_cql("library L\ncontext Patient\ndefine private: 1")
        d2 = [s for s in lib2.statements if hasattr(s, "expression")][0]
        assert d2.name == "private" and d2.access_level is None

    def test_code_selector_accepts_qualified_codesystem(self):
        e = parse_expression("Code 'c' from Lib.CS")
        assert type(e).__name__ == "CodeSelector"
        assert e.system == "Lib.CS"

    def test_access_modifier_on_function_definitions(self):
        # Grammar: `define accessModifier? 'fluent'? 'function' ...` — the
        # modifier precedes both 'fluent' and 'function'.
        lib = parse_cql(
            "library L\ncontext Patient\ndefine private function F(A Integer): A + 1"
        )
        f = [s for s in lib.statements if hasattr(s, "parameters")][0]
        assert f.access_level == "private" and f.fluent is False
        lib2 = parse_cql(
            "library L\ncontext Patient\ndefine public fluent function G(A Integer): A"
        )
        g = [s for s in lib2.statements if hasattr(s, "parameters")][0]
        assert g.access_level == "public" and g.fluent is True


class TestExternalReviewB8QueryClauses:
    """Regression coverage for the 2026-11-13 external translator review,
    batch B8 (TRIAGE_cql_review_20261113.md): EXP2-001 (literal FALSE
    conditions dropped from with/such-that and multi-source where),
    EXP2-007 (secondary sort keys dropped)."""

    def _sql(self, cql_def):
        from ... import translate_cql

        res = translate_cql(f"library L\ncontext Patient\n{cql_def}")
        v = next(iter(res.values()))
        return str(v.to_sql() if hasattr(v, "to_sql") else v)

    def test_such_that_false_is_not_dropped(self):
        sql = self._sql(
            "define Q: [Patient] P with [Encounter] E such that false return P.id"
        )
        assert "FALSE" in sql.upper(), sql

    def test_where_false_literal_still_filters(self):
        sql = self._sql("define Q: [Patient] P where false return P.id")
        assert "FALSE" in sql.upper(), sql

    def test_secondary_sort_keys_preserved(self):
        sql = self._sql(
            "define S: [Patient] P sort by P.gender, P.birthDate asc return P.id"
        )
        assert "gender" in sql and "birthDate" in sql, sql
        assert sql.upper().count("ORDER BY") == 1

    def test_single_sort_key_unchanged(self):
        sql = self._sql("define S: [Patient] P sort by P.birthDate desc return P.id")
        assert "ORDER BY" in sql.upper() and "DESC" in sql.upper()


class TestExternalReviewB14ConditionalsAndFirstLast:
    """EXP1-008 (null-condition 3VL) + EXP1-009 (method-form First/Last)."""

    def test_if_null_condition_takes_else_branch(self):
        # CQL conditionals treat a null condition as false: the ELSE branch
        # must fire for union-bearing THEN branches too (the COALESCE-of-CASES
        # path previously emitted `NOT cond` which is NULL for a null cond,
        # dropping the else entirely).
        from fhir4ds.cql import translate_cql
        import duckdb
        from fhir4ds.cql.duckdb import register

        con = duckdb.connect()
        register(con)

        def _run(expr: str, defs: str = ""):
            res = translate_cql(
                f"library L\ncontext Unfiltered\n{defs}\ndefine T: {expr}"
            )
            v = res["T"]  # multiple defines when defs are supplied
            sql = v.to_sql() if hasattr(v, "to_sql") else str(v)
            return con.execute(f"SELECT ({sql})").fetchone()[0]

        assert _run("if null then 1 else 2") == 2
        assert _run("if true then 1 else 2") == 1
        assert _run("if false then 1 else 2") == 2
        _defs = "define A: {1, 2}\ndefine B: {2, 3}\n"
        assert _run("if null then (A union B) else {9}", _defs) == [9]
        assert _run("if true then (A union B) else {9}", _defs) == [1, 2, 3]
        assert _run("if false then (A union B) else {9}", _defs) == [9]

    def test_method_form_first_last_rejects_string_receiver(self):
        # 'abc'.first() previously character-indexed the string ('a'); the
        # method form must enforce the same List<T> signature as First(...).
        import pytest
        from fhir4ds.cql import translate_cql
        from fhir4ds.cql.errors import TranslationError

        for expr in ("'abc'.first()", "'abc'.last()"):
            with pytest.raises(TranslationError, match="requires a list argument"):
                translate_cql(
                    f"library L\ncontext Unfiltered\ndefine T: {expr}"
                )

        # List receivers keep working in both spellings.
        res = translate_cql(
            "library L\ncontext Unfiltered\ndefine T: {3, 1, 2}.last()"
        )
        v = next(iter(res.values()))
        sql = v.to_sql() if hasattr(v, "to_sql") else str(v)
        import duckdb
        from fhir4ds.cql.duckdb import register

        con = duckdb.connect()
        register(con)
        assert con.execute(f"SELECT ({sql})").fetchone()[0] == 2


class TestExternalReviewB15DeadAggregateBranches:
    """EXP1-013: GeometricMean/Product never parse into AggregateExpression.

    The parser only routes Count/Sum/Min/Max/Avg/Median/Mode tokens to
    _parse_aggregate_expression; GeometricMean/Product parse as identifiers
    (FunctionRef) and lower through the pre-translate hooks. The former
    EXP(AVG(LOG(x))) branches in _translate_aggregate_expression were dead
    AND doubly wrong (DuckDB LOG is base-10; the CQL Log(x, base) macro
    shadows 1-arg LOG on registered connections). These tests pin that the
    live lowering is exact and executes correctly.
    """

    def test_geometricmean_and_product_lower_exact_not_log_domain(self) -> None:
        from fhir4ds.cql import translate_cql

        r = translate_cql(
            "library T\n"
            "define G: GeometricMean({1.0, 2.0, 4.0})\n"
            "define P: Product({2.0, 3.0, 4.0})\n"
        )
        g, p = r["G"].to_sql(), r["P"].to_sql()
        # Live lowering: the GeometricMean UDF and exact list_aggregate
        # 'product' — never an EXP/LOG expansion.
        assert "GeometricMean(" in g
        assert "LOG" not in g.upper().replace("GEOMETRICMEAN", "")
        assert "list_aggregate" in p and "'product'" in p

    def test_geometricmean_and_product_execute_correctly(self) -> None:
        import duckdb

        from fhir4ds.cql import translate_cql
        from fhir4ds.cql.duckdb import register

        con = duckdb.connect()
        register(con)
        r = translate_cql(
            "library T\n"
            "define G: GeometricMean({1.0, 2.0, 4.0})\n"
            "define P: Product({2.0, 3.0, 4.0})\n"
        )
        assert con.execute(f"SELECT {r['G'].to_sql()}").fetchone()[0] == 2.0
        assert con.execute(f"SELECT {r['P'].to_sql()}").fetchone()[0] == 24.0

    def test_qualify_sort_identifiers_mutation_is_idempotent(self) -> None:
        """EXP1-014: re-translating the same parsed library is byte-identical."""
        import duckdb

        from fhir4ds.cql.duckdb import register
        from fhir4ds.cql.parser import parse_cql
        from fhir4ds.cql.translator.translator import CQLToSQLTranslator

        con = duckdb.connect()
        register(con)
        lib = parse_cql(
            "library T\ncontext Patient\n"
            "define E1: ([Encounter]) E sort by start of E.period\n"
            "define E2: ([Encounter]) E sort by date from authoredOn\n"
        )
        s1 = CQLToSQLTranslator(con).translate_library_to_sql(lib)
        s2 = CQLToSQLTranslator(con).translate_library_to_sql(lib)
        assert s1 == s2


class TestExternalReviewB16ClinicalAndTupleEquivalence:
    """EXP2-004 (Code equality 3VL) and EXP2-006 (tuple ~ through aliases)."""

    @staticmethod
    def _population_row(cql: str):
        import duckdb

        from fhir4ds.cql.duckdb import register
        from fhir4ds.cql.loader.fhir_loader import FHIRDataLoader
        from fhir4ds.cql.parser import parse_cql
        from fhir4ds.cql.translator.translator import CQLToSQLTranslator

        con = duckdb.connect()
        register(con)
        loader = FHIRDataLoader(con)
        loader.load_resource({"resourceType": "Patient", "id": "p1"})
        loader.load_resource(
            {
                "resourceType": "Condition",
                "id": "c1",
                "subject": {"reference": "Patient/p1"},
                "code": {"coding": [{"system": "u", "code": "finding"}]},
            }
        )
        sql = CQLToSQLTranslator(con).translate_library_to_population_sql(parse_cql(cql))
        return con.execute(sql).fetchone()[-1]

    def test_code_equality_diff_code_with_one_sided_display_is_false(self) -> None:
        """EXP2-004: a definitely differing element makes the tuple
        conjunction FALSE even when display is absent on one side."""
        got = self._population_row(
            "library T\ncontext Patient\ncodesystem \"CS\": 'u'\n"
            "define D: Code { code: 'a', display: 'x' } = Code { code: 'b' }"
        )
        assert got is False
        # NotEqual mirrors: not(false) = true
        got_ne = self._population_row(
            "library T\ncontext Patient\ncodesystem \"CS\": 'u'\n"
            "define D: Code { code: 'a', display: 'x' } != Code { code: 'b' }"
        )
        assert got_ne is True

    def test_code_equality_same_code_one_sided_display_stays_null(self) -> None:
        """Pinned doctrine: same code + one missing display is uncertain
        (NULL at the expression level; the population define boundary
        collapses null->false per the documented CQL-04 convention)."""
        import duckdb

        from fhir4ds.cql import translate_cql
        from fhir4ds.cql.duckdb import register

        con = duckdb.connect()
        register(con)
        r = translate_cql(
            "library T\ncodesystem \"CS\": 'u'\n"
            "define D: Code { code: 'a', display: 'x' } = Code { code: 'a' }"
        )
        assert con.execute(f"SELECT {r['D'].to_sql()}").fetchone()[0] is None

    def test_code_equality_identical_and_fully_equal(self) -> None:
        assert self._population_row(
            "library T\ncontext Patient\ncodesystem \"CS\": 'u'\n"
            "define D: Code { code: 'a', display: 'x' } = Code { code: 'a', display: 'x' }"
        ) is True
        assert self._population_row(
            "library T\ncontext Patient\ncodesystem \"CS\": 'u'\n"
            "define D: Code { code: 'a' } = Code { code: 'b' }"
        ) is False

    def test_tuple_equivalence_through_define_alias(self) -> None:
        """EXP2-006: alias ~ tuple-literal folds element-wise (~ on String
        is case-insensitive), with §9 null handling for the alias operand."""
        cases = [
            (
                "define T1: Tuple { a: 1, b: 'x' }\ndefine D: T1 ~ Tuple { a: 1, b: 'X' }",
                True,
            ),
            (
                "define T1: Tuple { a: 1, b: 'x' }\ndefine T2: Tuple { a: 1, b: 'X' }\ndefine D: T1 ~ T2",
                True,
            ),
            (
                "define T1: Tuple { a: 1, b: 'x' }\ndefine D: T1 !~ Tuple { a: 1, b: 'X' }",
                False,
            ),
            ("define T1: Tuple { a: 1 }\ndefine D: T1 ~ Tuple { a: 2 }", False),
            ("define T1: Tuple { a: 1 }\ndefine D: T1 ~ Tuple { b: 1 }", False),
            ("define D: Tuple { a: 1, b: 'x' } ~ Tuple { a: 1, b: 'X' }", True),
        ]
        for tail, want in cases:
            got = self._population_row("library T\ncontext Patient\n" + tail)
            assert got == want, f"{tail!r}: want {want}, got {got}"


class TestExternalReviewB17AggregateWhereAndAuditDemotion:
    """EXP2-008 (multi-source aggregate WHERE) and EXP2-010 (paren matching)."""

    @staticmethod
    def _aggregate_count(cql: str):
        import duckdb

        from fhir4ds.cql.duckdb import register
        from fhir4ds.cql.loader.fhir_loader import FHIRDataLoader
        from fhir4ds.cql.parser import parse_cql
        from fhir4ds.cql.translator.translator import CQLToSQLTranslator

        con = duckdb.connect()
        register(con)
        loader = FHIRDataLoader(con)
        loader.load_resource({"resourceType": "Patient", "id": "p1"})
        loader.load_resource({"resourceType": "Encounter", "id": "e1", "subject": {"reference": "Patient/p1"}, "status": "finished"})
        loader.load_resource({"resourceType": "Encounter", "id": "e2", "subject": {"reference": "Patient/p1"}, "status": "planned"})
        loader.load_resource({"resourceType": "Observation", "id": "o1", "subject": {"reference": "Patient/p1"}, "status": "final"})
        loader.load_resource({"resourceType": "Observation", "id": "o2", "subject": {"reference": "Patient/p1"}, "status": "preliminary"})
        sql = CQLToSQLTranslator(con).translate_library_to_population_sql(parse_cql(cql))
        return float(con.execute(sql).fetchone()[-1])

    def test_multi_source_aggregate_where_applies_inside_source_scope(self) -> None:
        """EXP2-008: the query WHERE references the primary alias (E),
        which binds only inside the with-clause derived table — it must be
        pushed down, not dangled at the derived-table level."""
        base = (
            "library T\ncontext Patient\n"
            "define D: ([Encounter] E with [Observation] O such that O.status = 'final') R\n"
            "{where}aggregate T starting 0: T + 1"
        )
        # with-where: only (finished E, final O) pairs count -> 1
        assert self._aggregate_count(base.format(where="  where E.status = 'finished'\n")) == 1.0
        # control, no where: every E x final O pair -> 2
        assert self._aggregate_count(base.format(where="")) == 2.0

    def test_single_source_aggregate_where_unchanged(self) -> None:
        assert self._aggregate_count(
            "library T\ncontext Patient\n"
            "define D: ([Observation] O where O.status = 'final') R\n"
            "  aggregate T starting 0: T + 1"
        ) == 1.0

    def test_find_matching_paren_is_string_literal_aware(self) -> None:
        """EXP2-010: parens inside '...' literals are data, not structure."""
        from fhir4ds.cql.translator.expressions._query import demote_audit_in_text

        cases = [
            # balanced parens in literal (worked before, must keep working)
            (
                "CASE WHEN audit_leaf('note', 'pain (acute)') THEN 1 ELSE 0 END",
                "CASE WHEN struct_extract(audit_leaf('note', 'pain (acute)'), 'result') THEN 1 ELSE 0 END",
            ),
            # unbalanced open paren (previously: silent skip, no demotion)
            (
                "CASE WHEN audit_leaf('note', 'pain (chronic') THEN 1 ELSE 0 END",
                "CASE WHEN struct_extract(audit_leaf('note', 'pain (chronic'), 'result') THEN 1 ELSE 0 END",
            ),
            # unbalanced close paren (previously: corrupt SQL with broken quoting)
            (
                "CASE WHEN audit_leaf('note', 'resolved)') THEN 1 ELSE 0 END",
                "CASE WHEN struct_extract(audit_leaf('note', 'resolved)'), 'result') THEN 1 ELSE 0 END",
            ),
            # escaped quote keeps the scanner in-string across a paren
            (
                "CASE WHEN audit_leaf('it''s (ok', 'x)') THEN 1 ELSE 0 END",
                "CASE WHEN struct_extract(audit_leaf('it''s (ok', 'x)'), 'result') THEN 1 ELSE 0 END",
            ),
        ]
        for sql, want in cases:
            got = demote_audit_in_text(sql)
            assert got == want, f"{sql!r}: want {want!r}, got {got!r}"
