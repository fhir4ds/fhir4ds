"""
Unit tests for CQL lexer.

Comprehensive tests covering all CQL R1.5 lexical features.
"""

import pytest

from ...errors import LexerError
from ...parser.lexer import Lexer, Token, TokenType, tokenize_cql


class TestLexerBasics:
    """Basic lexer functionality tests."""

    def test_empty_input(self):
        """Test tokenizing empty input."""
        tokens = tokenize_cql("")
        assert len(tokens) == 1
        assert tokens[0].type == TokenType.EOF

    def test_whitespace_only(self):
        """Test tokenizing whitespace-only input."""
        tokens = tokenize_cql("   \t\n\r   ")
        assert len(tokens) == 1
        assert tokens[0].type == TokenType.EOF

    def test_single_identifier(self):
        """Test tokenizing a single identifier."""
        tokens = tokenize_cql("myIdentifier")
        assert len(tokens) == 2
        assert tokens[0].type == TokenType.IDENTIFIER
        assert tokens[0].value == "myIdentifier"

    def test_token_positions(self):
        """Test that token positions are tracked correctly."""
        tokens = tokenize_cql("abc def")
        assert tokens[0].line == 1
        assert tokens[0].column == 1
        assert tokens[1].line == 1
        assert tokens[1].column == 5


class TestLibraryDeclaration:
    """Tests for library declaration tokenization."""

    def test_simple_library(self):
        """Test simple library declaration."""
        tokens = tokenize_cql("library MyLibrary")
        assert len(tokens) >= 3
        assert tokens[0].type == TokenType.LIBRARY
        assert tokens[1].type == TokenType.IDENTIFIER
        assert tokens[1].value == "MyLibrary"

    def test_library_with_version(self):
        """Test library declaration with version."""
        tokens = tokenize_cql("library MyLibrary version '1.0.0'")
        types = [t.type for t in tokens]
        assert TokenType.LIBRARY in types
        assert TokenType.VERSION in types
        assert TokenType.STRING in types

    def test_using_declaration(self):
        """Test using declaration."""
        tokens = tokenize_cql("using FHIR version '4.0.1'")
        types = [t.type for t in tokens]
        assert TokenType.USING in types

    def test_include_declaration(self):
        """Test include declaration."""
        tokens = tokenize_cql("include Common called Common")
        types = [t.type for t in tokens]
        assert TokenType.INCLUDE in types
        assert TokenType.CALLED in types


class TestDateAndTimeLiterals:
    """Tests for date/time literal tokenization."""

    def test_date_literal(self):
        """Test date literal with @ prefix."""
        tokens = tokenize_cql("@2024-01-15")
        assert len(tokens) == 2
        assert tokens[0].type == TokenType.DATE
        assert tokens[0].value == "2024-01-15"

    def test_datetime_literal(self):
        """Test datetime literal with time component."""
        tokens = tokenize_cql("@2024-01-15T12:30:00")
        assert len(tokens) == 2
        assert tokens[0].type == TokenType.DATETIME
        assert tokens[0].value == "2024-01-15T12:30:00"

    def test_datetime_with_milliseconds(self):
        """Test datetime literal with milliseconds."""
        tokens = tokenize_cql("@2024-01-15T12:30:00.123")
        assert tokens[0].type == TokenType.DATETIME
        assert tokens[0].value == "2024-01-15T12:30:00.123"

    def test_datetime_with_timezone_z(self):
        """Test datetime literal with Z timezone."""
        tokens = tokenize_cql("@2024-01-15T12:30:00Z")
        assert tokens[0].type == TokenType.DATETIME
        assert tokens[0].value == "2024-01-15T12:30:00Z"

    def test_datetime_with_timezone_offset(self):
        """Test datetime literal with timezone offset."""
        tokens = tokenize_cql("@2024-01-15T12:30:00+05:00")
        assert tokens[0].type == TokenType.DATETIME
        assert tokens[0].value == "2024-01-15T12:30:00+05:00"


class TestStringLiterals:
    """Tests for string literal tokenization."""

    def test_simple_string(self):
        """Test simple string literal."""
        tokens = tokenize_cql("'hello world'")
        assert len(tokens) == 2
        assert tokens[0].type == TokenType.STRING
        assert tokens[0].value == "hello world"

    def test_empty_string(self):
        """Test empty string literal."""
        tokens = tokenize_cql("''")
        assert len(tokens) == 2
        assert tokens[0].type == TokenType.STRING
        assert tokens[0].value == ""

    def test_escaped_single_quote(self):
        """Test escaped single quote ('')."""
        tokens = tokenize_cql("'it''s a test'")
        assert tokens[0].type == TokenType.STRING
        assert tokens[0].value == "it's a test"

    def test_escape_sequences(self):
        """Test backslash escape sequences."""
        tokens = tokenize_cql("'line1\\nline2'")
        assert tokens[0].type == TokenType.STRING
        assert tokens[0].value == "line1\nline2"

    def test_escape_tab(self):
        """Test tab escape sequence."""
        tokens = tokenize_cql("'col1\\tcol2'")
        assert tokens[0].type == TokenType.STRING
        assert tokens[0].value == "col1\tcol2"

    def test_escape_backslash(self):
        """Test escaped backslash."""
        tokens = tokenize_cql("'path\\\\to\\\\file'")
        assert tokens[0].type == TokenType.STRING
        assert tokens[0].value == "path\\to\\file"

    def test_unicode_escape(self):
        """Test unicode escape sequence."""
        tokens = tokenize_cql("'\\u0041'")
        assert tokens[0].type == TokenType.STRING
        assert tokens[0].value == "A"

    def test_unterminated_string_error(self):
        """Test error for unterminated string."""
        with pytest.raises(LexerError):
            tokenize_cql("'unterminated")


class TestQuotedIdentifiers:
    """Tests for quoted identifier tokenization."""

    def test_simple_quoted_identifier(self):
        """Test simple quoted identifier."""
        tokens = tokenize_cql('"my-identifier"')
        assert len(tokens) == 2
        assert tokens[0].type == TokenType.QUOTED_IDENTIFIER
        assert tokens[0].value == "my-identifier"

    def test_quoted_identifier_with_spaces(self):
        """Test quoted identifier with spaces."""
        tokens = tokenize_cql('"my identifier"')
        assert tokens[0].type == TokenType.QUOTED_IDENTIFIER
        assert tokens[0].value == "my identifier"

    def test_unterminated_quoted_identifier_error(self):
        """Test error for unterminated quoted identifier."""
        with pytest.raises(LexerError):
            tokenize_cql('"unterminated')


class TestNumbers:
    """Tests for number tokenization."""

    def test_integer(self):
        """Test integer literal."""
        tokens = tokenize_cql("42")
        assert len(tokens) == 2
        assert tokens[0].type == TokenType.INTEGER
        assert tokens[0].value == "42"

    def test_zero(self):
        """Test zero literal."""
        tokens = tokenize_cql("0")
        assert tokens[0].type == TokenType.INTEGER
        assert tokens[0].value == "0"

    def test_large_integer(self):
        """Test large integer literal."""
        tokens = tokenize_cql("1234567890")
        assert tokens[0].type == TokenType.INTEGER
        assert tokens[0].value == "1234567890"

    def test_decimal(self):
        """Test decimal literal."""
        tokens = tokenize_cql("3.14")
        assert len(tokens) == 2
        assert tokens[0].type == TokenType.DECIMAL
        assert tokens[0].value == "3.14"

    def test_decimal_with_leading_zero(self):
        """Test decimal with leading zero."""
        tokens = tokenize_cql("0.5")
        assert tokens[0].type == TokenType.DECIMAL
        assert tokens[0].value == "0.5"

    def test_number_followed_by_dot(self):
        """Test number followed by method call (dot not part of number)."""
        tokens = tokenize_cql("42.value")
        types = [t.type for t in tokens]
        assert TokenType.INTEGER in types
        assert TokenType.DOT in types
        assert TokenType.IDENTIFIER in types


class TestKeywords:
    """Tests for keyword tokenization."""

    def test_define_keyword(self):
        """Test define keyword."""
        tokens = tokenize_cql("define")
        assert tokens[0].type == TokenType.DEFINE

    def test_context_keyword(self):
        """Test context keyword."""
        tokens = tokenize_cql("context")
        assert tokens[0].type == TokenType.CONTEXT

    def test_parameter_keyword(self):
        """Test parameter keyword."""
        tokens = tokenize_cql("parameter")
        assert tokens[0].type == TokenType.PARAMETER

    def test_true_keyword(self):
        """Test true keyword."""
        tokens = tokenize_cql("true")
        assert tokens[0].type == TokenType.TRUE

    def test_false_keyword(self):
        """Test false keyword."""
        tokens = tokenize_cql("false")
        assert tokens[0].type == TokenType.FALSE

    def test_null_keyword(self):
        """Test null keyword."""
        tokens = tokenize_cql("null")
        assert tokens[0].type == TokenType.NULL

    def test_case_insensitive_keywords(self):
        """Test that keywords are case-insensitive."""
        tokens_lower = tokenize_cql("define")
        tokens_upper = tokenize_cql("DEFINE")
        tokens_mixed = tokenize_cql("DeFiNe")

        assert tokens_lower[0].type == TokenType.DEFINE
        assert tokens_upper[0].type == TokenType.DEFINE
        assert tokens_mixed[0].type == TokenType.DEFINE


class TestTypeKeywords:
    """Tests for type keyword tokenization."""

    def test_boolean_type(self):
        """Test Boolean type keyword."""
        tokens = tokenize_cql("Boolean")
        assert tokens[0].type == TokenType.BOOLEAN

    def test_integer_type(self):
        """Test Integer type keyword."""
        tokens = tokenize_cql("Integer")
        assert tokens[0].type == TokenType.INTEGER_TYPE

    def test_decimal_type(self):
        """Test Decimal type keyword."""
        tokens = tokenize_cql("Decimal")
        assert tokens[0].type == TokenType.DECIMAL_TYPE

    def test_string_type(self):
        """Test String type keyword."""
        tokens = tokenize_cql("String")
        assert tokens[0].type == TokenType.STRING_TYPE

    def test_date_type(self):
        """Test Date type keyword."""
        tokens = tokenize_cql("Date")
        assert tokens[0].type == TokenType.DATE_TYPE

    def test_datetime_type(self):
        """Test DateTime type keyword."""
        tokens = tokenize_cql("DateTime")
        assert tokens[0].type == TokenType.DATETIME_TYPE

    def test_interval_type(self):
        """Test Interval type keyword."""
        tokens = tokenize_cql("Interval")
        assert tokens[0].type == TokenType.INTERVAL

    def test_list_type(self):
        """Test List type keyword."""
        tokens = tokenize_cql("List")
        assert tokens[0].type == TokenType.LIST_TYPE


class TestQueryKeywords:
    """Tests for query keyword tokenization."""

    def test_from_keyword(self):
        """Test from keyword."""
        tokens = tokenize_cql("from")
        assert tokens[0].type == TokenType.FROM

    def test_where_keyword(self):
        """Test where keyword."""
        tokens = tokenize_cql("where")
        assert tokens[0].type == TokenType.WHERE

    def test_return_keyword(self):
        """Test return keyword."""
        tokens = tokenize_cql("return")
        assert tokens[0].type == TokenType.RETURN

    def test_sort_keyword(self):
        """Test sort keyword."""
        tokens = tokenize_cql("sort")
        assert tokens[0].type == TokenType.SORT

    def test_asc_keyword(self):
        """Test asc keyword."""
        tokens = tokenize_cql("asc")
        assert tokens[0].type == TokenType.ASC

    def test_desc_keyword(self):
        """Test desc keyword."""
        tokens = tokenize_cql("desc")
        assert tokens[0].type == TokenType.DESC


class TestTemporalKeywords:
    """Tests for temporal keyword tokenization."""

    def test_after_keyword(self):
        """Test after keyword."""
        tokens = tokenize_cql("after")
        assert tokens[0].type == TokenType.AFTER

    def test_before_keyword(self):
        """Test before keyword."""
        tokens = tokenize_cql("before")
        assert tokens[0].type == TokenType.BEFORE

    def test_during_keyword(self):
        """Test during keyword."""
        tokens = tokenize_cql("during")
        assert tokens[0].type == TokenType.DURING

    def test_includes_keyword(self):
        """Test includes keyword."""
        tokens = tokenize_cql("includes")
        assert tokens[0].type == TokenType.INCLUDES

    def test_overlaps_keyword(self):
        """Test overlaps keyword."""
        tokens = tokenize_cql("overlaps")
        assert tokens[0].type == TokenType.OVERLAPS

    def test_meets_keyword(self):
        """Test meets keyword."""
        tokens = tokenize_cql("meets")
        assert tokens[0].type == TokenType.MEETS


class TestMultiWordKeywords:
    """Tests for multi-word keyword tokenization."""

    def test_meets_before(self):
        """Test 'meets before' multi-word keyword."""
        tokens = tokenize_cql("meets before")
        assert len(tokens) == 2
        assert tokens[0].type == TokenType.MEETS_BEFORE
        assert tokens[0].value == "meets before"

    def test_meets_after(self):
        """Test 'meets after' multi-word keyword."""
        tokens = tokenize_cql("meets after")
        assert tokens[0].type == TokenType.MEETS_AFTER

    def test_overlaps_before(self):
        """Test 'overlaps before' multi-word keyword."""
        tokens = tokenize_cql("overlaps before")
        assert tokens[0].type == TokenType.OVERLAPS_BEFORE

    def test_overlaps_after(self):
        """Test 'overlaps after' multi-word keyword."""
        tokens = tokenize_cql("overlaps after")
        assert tokens[0].type == TokenType.OVERLAPS_AFTER

    def test_on_or_before(self):
        """Test 'on or before' multi-word keyword."""
        tokens = tokenize_cql("on or before")
        assert tokens[0].type == TokenType.ON_OR_BEFORE

    def test_on_or_after(self):
        """Test 'on or after' multi-word keyword."""
        tokens = tokenize_cql("on or after")
        assert tokens[0].type == TokenType.ON_OR_AFTER

    def test_is_null(self):
        """Test 'is null' multi-word keyword."""
        tokens = tokenize_cql("is null")
        assert tokens[0].type == TokenType.IS_NULL

    def test_is_not_null(self):
        """Test 'is not null' multi-word keyword."""
        tokens = tokenize_cql("is not null")
        assert tokens[0].type == TokenType.IS_NOT_NULL

    def test_is_true(self):
        """Test 'is true' multi-word keyword."""
        tokens = tokenize_cql("is true")
        assert tokens[0].type == TokenType.IS_TRUE

    def test_is_false(self):
        """Test 'is false' multi-word keyword."""
        tokens = tokenize_cql("is false")
        assert tokens[0].type == TokenType.IS_FALSE

    def test_open_closed_interval(self):
        """Test 'open closed' multi-word keyword."""
        tokens = tokenize_cql("open closed")
        assert tokens[0].type == TokenType.OPEN_CLOSED

    def test_closed_open_interval(self):
        """Test 'closed open' multi-word keyword."""
        tokens = tokenize_cql("closed open")
        assert tokens[0].type == TokenType.CLOSED_OPEN


class TestTemporalUnits:
    """Tests for temporal unit keyword tokenization."""

    def test_year_units(self):
        """Test year/years keywords."""
        tokens = tokenize_cql("year years")
        assert tokens[0].type == TokenType.YEAR
        assert tokens[1].type == TokenType.YEARS

    def test_month_units(self):
        """Test month/months keywords."""
        tokens = tokenize_cql("month months")
        assert tokens[0].type == TokenType.MONTH
        assert tokens[1].type == TokenType.MONTHS

    def test_day_units(self):
        """Test day/days keywords."""
        tokens = tokenize_cql("day days")
        assert tokens[0].type == TokenType.DAY
        assert tokens[1].type == TokenType.DAYS

    def test_hour_units(self):
        """Test hour/hours keywords."""
        tokens = tokenize_cql("hour hours")
        assert tokens[0].type == TokenType.HOUR
        assert tokens[1].type == TokenType.HOURS

    def test_minute_units(self):
        """Test minute/minutes keywords."""
        tokens = tokenize_cql("minute minutes")
        assert tokens[0].type == TokenType.MINUTE
        assert tokens[1].type == TokenType.MINUTES

    def test_second_units(self):
        """Test second/seconds keywords."""
        tokens = tokenize_cql("second seconds")
        assert tokens[0].type == TokenType.SECOND
        assert tokens[1].type == TokenType.SECONDS


class TestOperators:
    """Tests for operator tokenization."""

    def test_equals(self):
        """Test equals operator."""
        tokens = tokenize_cql("=")
        assert tokens[0].type == TokenType.EQUALS

    def test_not_equals_bang(self):
        """Test not equals operator (!=)."""
        tokens = tokenize_cql("!=")
        assert tokens[0].type == TokenType.NOT_EQUALS

    def test_not_equals_angle(self):
        """Test not equals operator (<>)."""
        tokens = tokenize_cql("<>")
        assert tokens[0].type == TokenType.NOT_EQUALS

    def test_less_than(self):
        """Test less than operator."""
        tokens = tokenize_cql("<")
        assert tokens[0].type == TokenType.LESS_THAN

    def test_greater_than(self):
        """Test greater than operator."""
        tokens = tokenize_cql(">")
        assert tokens[0].type == TokenType.GREATER_THAN

    def test_less_equal(self):
        """Test less than or equal operator."""
        tokens = tokenize_cql("<=")
        assert tokens[0].type == TokenType.LESS_EQUAL

    def test_greater_equal(self):
        """Test greater than or equal operator."""
        tokens = tokenize_cql(">=")
        assert tokens[0].type == TokenType.GREATER_EQUAL

    def test_equivalent(self):
        """Test equivalence operator (~)."""
        tokens = tokenize_cql("~")
        assert tokens[0].type == TokenType.TILDE

    def test_not_equivalent(self):
        """Test not equivalent operator (!~)."""
        tokens = tokenize_cql("!~")
        assert tokens[0].type == TokenType.NOT_EQUIVALENT


class TestArithmeticOperators:
    """Tests for arithmetic operator tokenization."""

    def test_plus(self):
        """Test plus operator."""
        tokens = tokenize_cql("+")
        assert tokens[0].type == TokenType.PLUS

    def test_minus(self):
        """Test minus operator."""
        tokens = tokenize_cql("-")
        assert tokens[0].type == TokenType.MINUS

    def test_multiply(self):
        """Test multiply operator."""
        tokens = tokenize_cql("*")
        assert tokens[0].type == TokenType.MULTIPLY

    def test_divide(self):
        """Test divide operator."""
        tokens = tokenize_cql("/")
        assert tokens[0].type == TokenType.DIVIDE

    def test_arrow(self):
        """Test arrow operator (->)."""
        tokens = tokenize_cql("->")
        assert tokens[0].type == TokenType.ARROW

    def test_div_keyword(self):
        """Test div keyword."""
        tokens = tokenize_cql("div")
        assert tokens[0].type == TokenType.DIV

    def test_mod_keyword(self):
        """Test mod keyword."""
        tokens = tokenize_cql("mod")
        assert tokens[0].type == TokenType.MOD


class TestLogicalOperators:
    """Tests for logical operator tokenization."""

    def test_and_keyword(self):
        """Test and keyword."""
        tokens = tokenize_cql("and")
        assert tokens[0].type == TokenType.AND

    def test_or_keyword(self):
        """Test or keyword."""
        tokens = tokenize_cql("or")
        assert tokens[0].type == TokenType.OR

    def test_not_keyword(self):
        """Test not keyword."""
        tokens = tokenize_cql("not")
        assert tokens[0].type == TokenType.NOT

    def test_xor_keyword(self):
        """Test xor keyword."""
        tokens = tokenize_cql("xor")
        assert tokens[0].type == TokenType.XOR

    def test_implies_keyword(self):
        """Test implies keyword."""
        tokens = tokenize_cql("implies")
        assert tokens[0].type == TokenType.IMPLIES


class TestDelimiters:
    """Tests for delimiter tokenization."""

    def test_parentheses(self):
        """Test parentheses."""
        tokens = tokenize_cql("()")
        assert tokens[0].type == TokenType.LPAREN
        assert tokens[1].type == TokenType.RPAREN

    def test_brackets(self):
        """Test brackets."""
        tokens = tokenize_cql("[]")
        assert tokens[0].type == TokenType.LBRACKET
        assert tokens[1].type == TokenType.RBRACKET

    def test_braces(self):
        """Test braces."""
        tokens = tokenize_cql("{}")
        assert tokens[0].type == TokenType.LBRACE
        assert tokens[1].type == TokenType.RBRACE

    def test_comma(self):
        """Test comma."""
        tokens = tokenize_cql(",")
        assert tokens[0].type == TokenType.COMMA

    def test_dot(self):
        """Test dot."""
        tokens = tokenize_cql(".")
        assert tokens[0].type == TokenType.DOT

    def test_colon(self):
        """Test colon."""
        tokens = tokenize_cql(":")
        assert tokens[0].type == TokenType.COLON

    def test_semicolon(self):
        """Test semicolon."""
        tokens = tokenize_cql(";")
        assert tokens[0].type == TokenType.SEMICOLON

    def test_pipe(self):
        """Test pipe."""
        tokens = tokenize_cql("|")
        assert tokens[0].type == TokenType.PIPE

    def test_caret(self):
        """Test caret."""
        tokens = tokenize_cql("^")
        assert tokens[0].type == TokenType.CARET


class TestComments:
    """Tests for comment tokenization."""

    def test_line_comment(self):
        """Test single-line comment."""
        tokens = tokenize_cql("// this is a comment")
        assert len(tokens) == 2  # comment + EOF
        assert tokens[0].type == TokenType.LINE_COMMENT
        assert tokens[0].value == " this is a comment"

    def test_line_comment_at_end(self):
        """Test single-line comment at end of line."""
        tokens = tokenize_cql("x // comment")
        assert tokens[0].type == TokenType.IDENTIFIER
        assert tokens[1].type == TokenType.LINE_COMMENT

    def test_block_comment(self):
        """Test block comment."""
        tokens = tokenize_cql("/* this is a block comment */")
        assert len(tokens) == 2
        assert tokens[0].type == TokenType.BLOCK_COMMENT
        assert tokens[0].value == " this is a block comment "

    def test_multiline_block_comment(self):
        """Test multi-line block comment."""
        tokens = tokenize_cql("/* line1\nline2 */")
        assert tokens[0].type == TokenType.BLOCK_COMMENT
        assert "line1" in tokens[0].value
        assert "line2" in tokens[0].value

    def test_unterminated_block_comment_error(self):
        """Test error for unterminated block comment."""
        with pytest.raises(LexerError):
            tokenize_cql("/* unterminated")


class TestIntervalSyntax:
    """Tests for interval syntax tokenization."""

    def test_interval_literal(self):
        """Test interval literal."""
        tokens = tokenize_cql("Interval[1, 10]")
        types = [t.type for t in tokens]
        assert TokenType.INTERVAL in types
        assert TokenType.LBRACKET in types
        assert TokenType.INTEGER in types
        assert TokenType.COMMA in types
        assert TokenType.RBRACKET in types

    def test_open_interval(self):
        """Test open interval syntax."""
        tokens = tokenize_cql("open")
        assert tokens[0].type == TokenType.OPEN

    def test_closed_interval(self):
        """Test closed interval syntax."""
        tokens = tokenize_cql("closed")
        assert tokens[0].type == TokenType.CLOSED


class TestFunctionKeywords:
    """Tests for function keyword tokenization."""

    def test_aggregate_functions(self):
        """Test aggregate function keywords."""
        tokens = tokenize_cql("Count Sum Min Max Avg")
        types = [t.type for t in tokens]
        assert TokenType.COUNT in types
        assert TokenType.SUM in types
        assert TokenType.MIN in types
        assert TokenType.MAX in types
        assert TokenType.AVG in types

    def test_string_functions(self):
        """Test string function keywords."""
        tokens = tokenize_cql("Length Upper Lower Concatenate")
        types = [t.type for t in tokens]
        assert TokenType.LENGTH in types
        assert TokenType.UPPER in types
        assert TokenType.LOWER in types
        assert TokenType.CONCATENATE in types

    def test_conversion_functions(self):
        """Test type conversion function keywords."""
        tokens = tokenize_cql("ToBoolean ToInteger ToDecimal ToString")
        types = [t.type for t in tokens]
        assert TokenType.TO_BOOLEAN in types
        assert TokenType.TO_INTEGER in types
        assert TokenType.TO_DECIMAL in types
        assert TokenType.TO_STRING in types

    def test_conditional_functions(self):
        """Test conditional function keywords."""
        tokens = tokenize_cql("Coalesce If Case When Then Else End")
        types = [t.type for t in tokens]
        assert TokenType.COALESCE in types
        assert TokenType.IFF in types
        assert TokenType.CASE in types
        assert TokenType.WHEN in types
        assert TokenType.THEN in types
        assert TokenType.ELSE in types
        assert TokenType.END in types


class TestComplexExpressions:
    """Tests for complex CQL expressions."""

    def test_simple_query(self):
        """Test simple query expression."""
        cql = "from [Observation] O where O.status = 'final' return O"
        tokens = tokenize_cql(cql)
        types = [t.type for t in tokens]
        assert TokenType.FROM in types
        assert TokenType.LBRACKET in types
        assert TokenType.WHERE in types
        assert TokenType.EQUALS in types
        assert TokenType.STRING in types
        assert TokenType.RETURN in types

    def test_define_expression(self):
        """Test define expression."""
        cql = "define InDemographic: Patient.age >= 18"
        tokens = tokenize_cql(cql)
        types = [t.type for t in tokens]
        assert TokenType.DEFINE in types
        assert TokenType.IDENTIFIER in types
        assert TokenType.COLON in types
        assert TokenType.GREATER_EQUAL in types
        assert TokenType.INTEGER in types

    def test_interval_comparison(self):
        """Test interval comparison expression."""
        cql = "Interval[@2024-01-01, @2024-12-31]"
        tokens = tokenize_cql(cql)
        types = [t.type for t in tokens]
        assert TokenType.INTERVAL in types
        assert TokenType.LBRACKET in types
        assert TokenType.DATE in types
        assert TokenType.COMMA in types
        assert TokenType.RBRACKET in types

    def test_temporal_comparison(self):
        """Test temporal comparison expression."""
        cql = "Observation.effective during MeasurementPeriod"
        tokens = tokenize_cql(cql)
        types = [t.type for t in tokens]
        assert TokenType.DURING in types
        assert TokenType.IDENTIFIER in types

    def test_conditional_expression(self):
        """Test conditional expression."""
        cql = "if X > 0 then 1 else 0"
        tokens = tokenize_cql(cql)
        types = [t.type for t in tokens]
        assert TokenType.IFF in types
        assert TokenType.GREATER_THAN in types
        assert TokenType.THEN in types
        assert TokenType.ELSE in types


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    def test_unexpected_character(self):
        """Test error for unexpected character."""
        with pytest.raises(LexerError):
            tokenize_cql("\x00invalid")

    def test_consecutive_operators(self):
        """Test consecutive operators."""
        tokens = tokenize_cql("+-*/")
        assert tokens[0].type == TokenType.PLUS
        assert tokens[1].type == TokenType.MINUS
        assert tokens[2].type == TokenType.MULTIPLY
        assert tokens[3].type == TokenType.DIVIDE

    def test_identifier_with_underscore(self):
        """Test identifier with underscore."""
        tokens = tokenize_cql("my_identifier")
        assert tokens[0].type == TokenType.IDENTIFIER
        assert tokens[0].value == "my_identifier"

    def test_identifier_with_numbers(self):
        """Test identifier with numbers."""
        tokens = tokenize_cql("var123")
        assert tokens[0].type == TokenType.IDENTIFIER
        assert tokens[0].value == "var123"

    def test_multiline_input(self):
        """Test multiline input."""
        cql = """library Test
        define X: 1
        define Y: 2"""
        tokens = tokenize_cql(cql)
        types = [t.type for t in tokens]
        assert TokenType.LIBRARY in types
        assert types.count(TokenType.DEFINE) == 2

    def test_newline_tracking(self):
        """Test that newlines are tracked for line numbers."""
        tokens = tokenize_cql("line1\nline2")
        assert tokens[0].line == 1
        assert tokens[1].line == 2


class TestLexerClass:
    """Tests for Lexer class directly."""

    def test_lexer_instance(self):
        """Test creating Lexer instance."""
        lexer = Lexer("test")
        assert lexer.source == "test"
        assert lexer.pos == 0
        assert lexer.line == 1
        assert lexer.column == 1

    def test_tokenize_method(self):
        """Test tokenize method."""
        lexer = Lexer("define X: 1")
        tokens = lexer.tokenize()
        assert len(tokens) > 0
        assert tokens[-1].type == TokenType.EOF
