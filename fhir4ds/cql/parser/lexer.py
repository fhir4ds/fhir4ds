"""
CQL tokenizer / lexer.

Converts CQL source text into tokens for the parser.
Based on CQL R1.5 specification (https://cql.hl7.org).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum, auto
from typing import TYPE_CHECKING

from ..errors import LexerError

if TYPE_CHECKING:
    pass


class TokenType(Enum):
    """Token types for CQL lexical analysis."""

    # Literals
    INTEGER = auto()
    LONG = auto()  # For long literals like 123456789L
    DECIMAL = auto()
    STRING = auto()
    # Date/Time literals with @ prefix
    DATE = auto()
    DATETIME = auto()
    TIME = auto()

    # Identifiers
    IDENTIFIER = auto()
    QUOTED_IDENTIFIER = auto()

    # Keywords - Definition Keywords
    LIBRARY = auto()
    USING = auto()
    INCLUDE = auto()
    DEFINE = auto()
    CONTEXT = auto()
    PARAMETER = auto()
    DEFAULT = auto()
    CODESYSTEM = auto()
    VALUESYSTEM = auto()
    CODE = auto()
    CONCEPT = auto()
    LET = auto()
    VERSION = auto()
    CALLED = auto()
    FUNCTION = auto()
    FLUENT = auto()
    DISPLAY = auto()

    # Keywords - Type Keywords
    BOOLEAN = auto()
    INTEGER_TYPE = auto()
    LONG_TYPE = auto()  # For type specifier 'Long'
    REAL = auto()
    DECIMAL_TYPE = auto()
    STRING_TYPE = auto()
    DATE_TYPE = auto()
    DATETIME_TYPE = auto()
    TIME_TYPE = auto()
    QUANTITY = auto()
    RATIO = auto()
    INTERVAL = auto()
    LIST_TYPE = auto()
    TUPLE = auto()
    CHOICE = auto()
    ANY = auto()
    CODE_TYPE = auto()
    CONCEPT_TYPE = auto()
    CODESYSTEM_TYPE = auto()
    VALUESET_TYPE = auto()

    # Keywords - Literal Keywords
    TRUE = auto()
    FALSE = auto()
    NULL = auto()

    # Keywords - Query Keywords
    FROM = auto()
    WHERE = auto()
    RETURN = auto()
    SORT = auto()
    ASC = auto()
    DESC = auto()
    WITH = auto()
    WITHOUT = auto()
    DISTINCT = auto()
    SKIP = auto()
    TAKE = auto()

    # Keywords - Temporal Keywords
    AFTER = auto()
    BEFORE = auto()
    DURING = auto()
    INCLUDES = auto()
    INCLUDED_IN = auto()
    OVERLAPS = auto()
    MEETS = auto()
    STARTS = auto()
    ENDS = auto()

    # Multi-word temporal keywords (stored as single token)
    MEETS_BEFORE = auto()
    MEETS_AFTER = auto()
    OVERLAPS_BEFORE = auto()
    OVERLAPS_AFTER = auto()
    ON_OR_BEFORE = auto()
    ON_OR_AFTER = auto()
    OR_LESS = auto()
    OR_MORE = auto()
    OR_BEFORE = auto()
    OR_AFTER = auto()

    # Keywords - Temporal Units
    YEAR = auto()
    MONTH = auto()
    WEEK = auto()
    DAY = auto()
    HOUR = auto()
    MINUTE = auto()
    SECOND = auto()
    MILLISECOND = auto()

    # Keywords - Plural Temporal Units
    YEARS = auto()
    MONTHS = auto()
    WEEKS = auto()
    DAYS = auto()
    HOURS = auto()
    MINUTES = auto()
    SECONDS = auto()
    MILLISECONDS = auto()

    # Keywords - Date/Time Parts
    DATE_FROM = auto()
    TIME_FROM = auto()
    TIMEZONE_FROM = auto()
    DATE_COMPONENT = auto()
    TIME_COMPONENT = auto()

    # Keywords - Interval Keywords
    CLOSED = auto()
    OPEN = auto()
    OPEN_CLOSED = auto()
    CLOSED_OPEN = auto()

    # Keywords - Interval Operators
    START = auto()  # start of
    END_OF = auto()  # end of (for intervals)
    POINT = auto()  # point from

    # Keywords - Logical Operators
    AND = auto()
    OR = auto()
    NOT = auto()
    XOR = auto()
    IMPLIES = auto()

    # Keywords - Comparison Keywords
    IS = auto()
    AS = auto()
    IN = auto()
    BETWEEN = auto()
    EXISTS = auto()

    # Keywords - Nullology
    IS_NULL = auto()
    IS_NOT_NULL = auto()
    IS_TRUE = auto()
    IS_FALSE = auto()

    # Keywords - Query Aggregate Clause
    AGGREGATE = auto()
    STARTING = auto()
    ALL = auto()

    # Keywords - Aggregate Functions
    COUNT = auto()
    SUM = auto()
    MIN = auto()
    MAX = auto()
    AVG = auto()
    MEDIAN = auto()
    MODE = auto()
    VARIANCE = auto()
    STDDEV = auto()
    ALL_TRUE = auto()
    ANY_TRUE = auto()

    # Keywords - String Functions
    LENGTH = auto()
    UPPER = auto()
    LOWER = auto()
    CONCATENATE = auto()
    COMBINE = auto()
    SPLIT = auto()
    POSITION_OF = auto()
    SUBSTRING = auto()
    STARTS_WITH = auto()
    ENDS_WITH = auto()
    MATCHES = auto()
    REPLACE_MATCHES = auto()
    REPLACE = auto()

    # Keywords - Other Functions
    COALESCE = auto()
    IFF = auto()
    IF_THEN_ELSE = auto()
    CASE = auto()
    WHEN = auto()
    THEN = auto()
    ELSE = auto()
    END = auto()
    TO_BOOLEAN = auto()
    TO_CONCEPT = auto()
    TO_DATE = auto()
    TO_DATETIME = auto()
    TO_DECIMAL = auto()
    TO_INTEGER = auto()
    TO_QUANTITY = auto()
    TO_STRING = auto()
    TO_TIME = auto()
    TO_CODE = auto()
    TO_CHARS = auto()
    FROM_CHARS = auto()
    CAST = auto()
    CONVERT = auto()
    TO = auto()  # for convert ... to
    FIRST = auto()
    LAST = auto()
    INDEXER = auto()
    FLATTEN = auto()
    DISTINCT_FN = auto()
    CURRENT = auto()
    CHILDREN = auto()
    DESCENDENTS = auto()
    ENCODE = auto()
    ESCAPE = auto()
    PREVIOUS = auto()
    PREDECESSOR = auto()
    SUCCESSOR = auto()
    SINGLE = auto()
    SINGLETON_FROM = auto()
    SELECT = auto()
    FOR = auto()
    OF = auto()
    REPEAT = auto()
    INTERSECT = auto()
    EXCEPT = auto()
    UNION = auto()
    CONTAINS = auto()
    PROPERLY = auto()
    PROPER_CONTAINS = auto()
    PROPER_IN = auto()
    PROPER_INCLUDES = auto()
    EXPAND = auto()
    PER = auto()  # for expand ... per ...
    ROUND = auto()
    ABS = auto()
    CEILING = auto()
    FLOOR = auto()
    LN = auto()
    LOG = auto()
    POWER = auto()
    TRUNCATE = auto()
    EXP = auto()
    SQRT = auto()
    DIV = auto()
    MOD = auto()
    REMAINDER = auto()
    WIDTH = auto()
    SIZE = auto()
    POINT_FROM = auto()
    LOWBOUNDARY = auto()
    HIGHBOUNDARY = auto()
    PRECISION = auto()
    MINIMUM = auto()
    MAXIMUM = auto()

    # Keywords - FHIR-specific
    PATIENT = auto()
    PRACTITIONER = auto()
    ORGANIZATION = auto()
    LOCATION = auto()
    RESOURCE = auto()
    BUNDLE = auto()

    # Comparison Operators
    EQUALS = auto()  # =
    NOT_EQUALS = auto()  # != or <>
    LESS_THAN = auto()  # <
    GREATER_THAN = auto()  # >
    LESS_EQUAL = auto()  # <=
    GREATER_EQUAL = auto()  # >=
    EQUIVALENT = auto()  # ~
    NOT_EQUIVALENT = auto()  # !~

    # Arithmetic Operators
    PLUS = auto()  # +
    MINUS = auto()  # -
    MULTIPLY = auto()  # *
    DIVIDE = auto()  # /
    INTEGER_DIVIDE = auto()  # div keyword
    MODULO = auto()  # mod keyword
    TRUNCATED_DIVIDE = auto()  # truncated divide (div for integers)

    # Other Operators
    ARROW = auto()  # ->
    PIPE = auto()  # |
    CARET = auto()  # ^
    TILDE = auto()  # ~ (equivalence)
    EXCLAMATION = auto()  # !

    # Delimiters
    LPAREN = auto()  # (
    RPAREN = auto()  # )
    LBRACKET = auto()  # [
    RBRACKET = auto()  # ]
    LBRACE = auto()  # {
    RBRACE = auto()  # }
    COMMA = auto()  # ,
    DOT = auto()  # .
    COLON = auto()  # :
    SEMICOLON = auto()  # ;
    HASH = auto()  # #
    AT = auto()  # @
    QUESTION = auto()  # ?
    DOLLAR = auto()  # $
    BACKTICK = auto()  # `
    LT = auto()  # < (for type parameters)
    GT = auto()  # > (for type parameters)

    # Query keywords
    BY = auto()
    SUCH = auto()
    THAT = auto()
    RETURNS = auto()

    # Special tokens
    EOF = auto()
    NEWLINE = auto()
    WHITESPACE = auto()
    COMMENT = auto()
    LINE_COMMENT = auto()
    BLOCK_COMMENT = auto()


@dataclass
class Token:
    """Represents a single token from CQL source."""

    type: TokenType
    value: str
    line: int
    column: int

    def __repr__(self) -> str:
        return f"Token({self.type.name}, {self.value!r}, line={self.line}, col={self.column})"


# Keyword to TokenType mapping (case-insensitive lookup)
KEYWORDS: dict[str, TokenType] = {
    # Definition Keywords
    "library": TokenType.LIBRARY,
    "using": TokenType.USING,
    "include": TokenType.INCLUDE,
    "define": TokenType.DEFINE,
    "context": TokenType.CONTEXT,
    "parameter": TokenType.PARAMETER,
    "default": TokenType.DEFAULT,
    "codesystem": TokenType.CODESYSTEM,
    "valueset": TokenType.VALUESYSTEM,
    "code": TokenType.CODE,
    "concept": TokenType.CONCEPT,
    "let": TokenType.LET,
    "version": TokenType.VERSION,
    "called": TokenType.CALLED,
    "function": TokenType.FUNCTION,
    "fluent": TokenType.FLUENT,
    "display": TokenType.DISPLAY,
    "by": TokenType.BY,
    "such": TokenType.SUCH,
    "that": TokenType.THAT,
    "returns": TokenType.RETURNS,
    # Type Keywords
    # Type Keywords - both PascalCase and lowercase supported
    "Boolean": TokenType.BOOLEAN,
    "boolean": TokenType.BOOLEAN,
    "Integer": TokenType.INTEGER_TYPE,
    "integer": TokenType.INTEGER_TYPE,
    "Long": TokenType.LONG_TYPE,
    "long": TokenType.LONG_TYPE,
    "Real": TokenType.REAL,
    "real": TokenType.REAL,
    "Decimal": TokenType.DECIMAL_TYPE,
    "decimal": TokenType.DECIMAL_TYPE,
    "String": TokenType.STRING_TYPE,
    "string": TokenType.STRING_TYPE,
    "Date": TokenType.DATE_TYPE,
    "DateTime": TokenType.DATETIME_TYPE,
    "datetime": TokenType.DATETIME_TYPE,
    "Time": TokenType.TIME_TYPE,
    "Quantity": TokenType.QUANTITY,
    "quantity": TokenType.QUANTITY,
    "Ratio": TokenType.RATIO,
    "ratio": TokenType.RATIO,
    "Interval": TokenType.INTERVAL,
    "interval": TokenType.INTERVAL,
    "List": TokenType.LIST_TYPE,
    "list": TokenType.LIST_TYPE,
    "Tuple": TokenType.TUPLE,
    "tuple": TokenType.TUPLE,
    "Choice": TokenType.CHOICE,
    "choice": TokenType.CHOICE,
    "Any": TokenType.ANY,
    "any": TokenType.ANY,
    "Code": TokenType.CODE_TYPE,
    "Concept": TokenType.CONCEPT_TYPE,
    "concept": TokenType.CONCEPT_TYPE,
    "CodeSystem": TokenType.CODESYSTEM_TYPE,
    "ValueSet": TokenType.VALUESET_TYPE,
    # Literal Keywords
    "true": TokenType.TRUE,
    "false": TokenType.FALSE,
    "null": TokenType.NULL,
    # Query Keywords
    "from": TokenType.FROM,
    "where": TokenType.WHERE,
    "return": TokenType.RETURN,
    "sort": TokenType.SORT,
    "asc": TokenType.ASC,
    "ascending": TokenType.ASC,
    "desc": TokenType.DESC,
    "descending": TokenType.DESC,
    "with": TokenType.WITH,
    "without": TokenType.WITHOUT,
    "distinct": TokenType.DISTINCT,
    "Skip": TokenType.SKIP,
    "skip": TokenType.SKIP,
    "Take": TokenType.TAKE,
    "take": TokenType.TAKE,
    # Temporal Keywords
    "after": TokenType.AFTER,
    "before": TokenType.BEFORE,
    "during": TokenType.DURING,
    "includes": TokenType.INCLUDES,
    "included": TokenType.INCLUDED_IN,
    "overlaps": TokenType.OVERLAPS,
    "meets": TokenType.MEETS,
    "starts": TokenType.STARTS,
    "ends": TokenType.ENDS,
    # Temporal Units (singular)
    "year": TokenType.YEAR,
    "month": TokenType.MONTH,
    "week": TokenType.WEEK,
    "day": TokenType.DAY,
    "hour": TokenType.HOUR,
    "minute": TokenType.MINUTE,
    "second": TokenType.SECOND,
    "millisecond": TokenType.MILLISECOND,
    # Temporal Units (plural)
    "years": TokenType.YEARS,
    "months": TokenType.MONTHS,
    "weeks": TokenType.WEEKS,
    "days": TokenType.DAYS,
    "hours": TokenType.HOURS,
    "minutes": TokenType.MINUTES,
    "seconds": TokenType.SECONDS,
    "milliseconds": TokenType.MILLISECONDS,
    # Interval Keywords
    "closed": TokenType.CLOSED,
    "open": TokenType.OPEN,
    # Interval Operators
    "start": TokenType.START,
    "end": TokenType.END,
    "point": TokenType.POINT,
    "contains": TokenType.CONTAINS,
    "properly": TokenType.PROPERLY,
    # Logical Operators
    "and": TokenType.AND,
    "or": TokenType.OR,
    "not": TokenType.NOT,
    "xor": TokenType.XOR,
    "implies": TokenType.IMPLIES,
    # Comparison Keywords
    "is": TokenType.IS,
    "as": TokenType.AS,
    "in": TokenType.IN,
    "between": TokenType.BETWEEN,
    "exists": TokenType.EXISTS,
    # Query Aggregate Clause
    "aggregate": TokenType.AGGREGATE,
    "starting": TokenType.STARTING,
    "all": TokenType.ALL,
    # Aggregate Functions
    "Count": TokenType.COUNT,
    "count": TokenType.COUNT,
    "Sum": TokenType.SUM,
    "sum": TokenType.SUM,
    "Min": TokenType.MIN,
    "min": TokenType.MIN,
    "Max": TokenType.MAX,
    "max": TokenType.MAX,
    "Avg": TokenType.AVG,
    "avg": TokenType.AVG,
    "Median": TokenType.MEDIAN,
    "median": TokenType.MEDIAN,
    "Mode": TokenType.MODE,
    "mode": TokenType.MODE,
    "Variance": TokenType.VARIANCE,
    "variance": TokenType.VARIANCE,
    "StdDev": TokenType.STDDEV,
    "stddev": TokenType.STDDEV,
    "AllTrue": TokenType.ALL_TRUE,
    "alltrue": TokenType.ALL_TRUE,
    "AnyTrue": TokenType.ANY_TRUE,
    "anytrue": TokenType.ANY_TRUE,
    # String Functions
    "Length": TokenType.LENGTH,
    "length": TokenType.LENGTH,
    "Upper": TokenType.UPPER,
    "upper": TokenType.UPPER,
    "Lower": TokenType.LOWER,
    "lower": TokenType.LOWER,
    "Concatenate": TokenType.CONCATENATE,
    "concatenate": TokenType.CONCATENATE,
    "Combine": TokenType.COMBINE,
    "combine": TokenType.COMBINE,
    "Split": TokenType.SPLIT,
    "split": TokenType.SPLIT,
    "PositionOf": TokenType.POSITION_OF,
    "positionof": TokenType.POSITION_OF,
    "Substring": TokenType.SUBSTRING,
    "substring": TokenType.SUBSTRING,
    "StartsWith": TokenType.STARTS_WITH,
    "startswith": TokenType.STARTS_WITH,
    "EndsWith": TokenType.ENDS_WITH,
    "endswith": TokenType.ENDS_WITH,
    "Matches": TokenType.MATCHES,
    "matches": TokenType.MATCHES,
    "ReplaceMatches": TokenType.REPLACE_MATCHES,
    "replacematches": TokenType.REPLACE_MATCHES,
    "Replace": TokenType.REPLACE,
    "replace": TokenType.REPLACE,
    # Other Functions
    "Coalesce": TokenType.COALESCE,
    "coalesce": TokenType.COALESCE,
    "If": TokenType.IFF,
    "if": TokenType.IFF,
    "Case": TokenType.CASE,
    "case": TokenType.CASE,
    "When": TokenType.WHEN,
    "when": TokenType.WHEN,
    "Then": TokenType.THEN,
    "then": TokenType.THEN,
    "Else": TokenType.ELSE,
    "else": TokenType.ELSE,
    "End": TokenType.END,
    "end": TokenType.END,
    "ToBoolean": TokenType.TO_BOOLEAN,
    "toboolean": TokenType.TO_BOOLEAN,
    "ToConcept": TokenType.TO_CONCEPT,
    "toconcept": TokenType.TO_CONCEPT,
    "ToDate": TokenType.TO_DATE,
    "todate": TokenType.TO_DATE,
    "ToDateTime": TokenType.TO_DATETIME,
    "todatetime": TokenType.TO_DATETIME,
    "ToDecimal": TokenType.TO_DECIMAL,
    "todecimal": TokenType.TO_DECIMAL,
    "ToInteger": TokenType.TO_INTEGER,
    "tointeger": TokenType.TO_INTEGER,
    "ToQuantity": TokenType.TO_QUANTITY,
    "toquantity": TokenType.TO_QUANTITY,
    "ToString": TokenType.TO_STRING,
    "tostring": TokenType.TO_STRING,
    "ToTime": TokenType.TO_TIME,
    "totime": TokenType.TO_TIME,
    "ToCode": TokenType.TO_CODE,
    "tocode": TokenType.TO_CODE,
    "ToChars": TokenType.TO_CHARS,
    "tochars": TokenType.TO_CHARS,
    "FromChars": TokenType.FROM_CHARS,
    "fromchars": TokenType.FROM_CHARS,
    "cast": TokenType.CAST,
    "convert": TokenType.CONVERT,
    "to": TokenType.TO,  # for convert ... to
    "First": TokenType.FIRST,
    "first": TokenType.FIRST,
    "Last": TokenType.LAST,
    "last": TokenType.LAST,
    "Indexer": TokenType.INDEXER,
    "indexer": TokenType.INDEXER,
    "Flatten": TokenType.FLATTEN,
    "flatten": TokenType.FLATTEN,
    "Distinct": TokenType.DISTINCT_FN,
    "distinct": TokenType.DISTINCT_FN,
    "Current": TokenType.CURRENT,
    "current": TokenType.CURRENT,
    "Children": TokenType.CHILDREN,
    "children": TokenType.CHILDREN,
    "Descendents": TokenType.DESCENDENTS,
    "descendents": TokenType.DESCENDENTS,
    "Encode": TokenType.ENCODE,
    "encode": TokenType.ENCODE,
    "Escape": TokenType.ESCAPE,
    "escape": TokenType.ESCAPE,
    "Previous": TokenType.PREVIOUS,
    "previous": TokenType.PREVIOUS,
    "Predecessor": TokenType.PREDECESSOR,
    "predecessor": TokenType.PREDECESSOR,
    "Successor": TokenType.SUCCESSOR,
    "successor": TokenType.SUCCESSOR,
    "Singleton": TokenType.SINGLE,
    "singleton": TokenType.SINGLE,
    "Select": TokenType.SELECT,
    "select": TokenType.SELECT,
    "For": TokenType.FOR,
    "for": TokenType.FOR,
    "Of": TokenType.OF,
    "of": TokenType.OF,
    "Repeat": TokenType.REPEAT,
    "repeat": TokenType.REPEAT,
    "Intersect": TokenType.INTERSECT,
    "intersect": TokenType.INTERSECT,
    "Except": TokenType.EXCEPT,
    "except": TokenType.EXCEPT,
    "Union": TokenType.UNION,
    "union": TokenType.UNION,
    "Contains": TokenType.CONTAINS,
    "contains": TokenType.CONTAINS,
    "Properly": TokenType.PROPERLY,
    "properly": TokenType.PROPERLY,
    "Expand": TokenType.EXPAND,
    "expand": TokenType.EXPAND,
    "per": TokenType.PER,
    "Round": TokenType.ROUND,
    "round": TokenType.ROUND,
    "Abs": TokenType.ABS,
    "abs": TokenType.ABS,
    "Ceiling": TokenType.CEILING,
    "ceiling": TokenType.CEILING,
    "Floor": TokenType.FLOOR,
    "floor": TokenType.FLOOR,
    "Ln": TokenType.LN,
    "ln": TokenType.LN,
    "Log": TokenType.LOG,
    "log": TokenType.LOG,
    "Power": TokenType.POWER,
    "power": TokenType.POWER,
    "Truncate": TokenType.TRUNCATE,
    "truncate": TokenType.TRUNCATE,
    "Exp": TokenType.EXP,
    "exp": TokenType.EXP,
    "Sqrt": TokenType.SQRT,
    "sqrt": TokenType.SQRT,
    "div": TokenType.DIV,
    "mod": TokenType.MOD,
    "Remainder": TokenType.REMAINDER,
    "remainder": TokenType.REMAINDER,
    "Width": TokenType.WIDTH,
    "width": TokenType.WIDTH,
    "Size": TokenType.SIZE,
    "size": TokenType.SIZE,
    "PointFrom": TokenType.POINT_FROM,
    "pointfrom": TokenType.POINT_FROM,
    "LowBoundary": TokenType.LOWBOUNDARY,
    "lowboundary": TokenType.LOWBOUNDARY,
    "HighBoundary": TokenType.HIGHBOUNDARY,
    "highboundary": TokenType.HIGHBOUNDARY,
    "Precision": TokenType.PRECISION,
    "precision": TokenType.PRECISION,
    "minimum": TokenType.MINIMUM,
    "maximum": TokenType.MAXIMUM,
    "Date": TokenType.DATE_TYPE,  # Date type
    "date": TokenType.DATE_FROM,  # date() function
    "Time": TokenType.TIME_TYPE,  # Time type
    "time": TokenType.TIME_FROM,  # time() function
    "timezone": TokenType.TIMEZONE_FROM,
    "timezoneoffset": TokenType.TIMEZONE_FROM,
    "DateComponent": TokenType.DATE_COMPONENT,
    "dateComponent": TokenType.DATE_COMPONENT,
    "datecomponent": TokenType.DATE_COMPONENT,
    "timeComponent": TokenType.TIME_COMPONENT,
    "timecomponent": TokenType.TIME_COMPONENT,
    # FHIR-specific
    "Patient": TokenType.PATIENT,
    "patient": TokenType.PATIENT,
    "Practitioner": TokenType.PRACTITIONER,
    "practitioner": TokenType.PRACTITIONER,
    "Organization": TokenType.ORGANIZATION,
    "organization": TokenType.ORGANIZATION,
    "Location": TokenType.LOCATION,
    "location": TokenType.LOCATION,
    "Resource": TokenType.RESOURCE,
    "resource": TokenType.RESOURCE,
    "Bundle": TokenType.BUNDLE,
    "bundle": TokenType.BUNDLE,
}

# Multi-word keywords that should be recognized as a single token
# Order matters: longer phrases first
MULTI_WORD_KEYWORDS: list[tuple[list[str], TokenType]] = [
    # Temporal multi-word operators
    (["meets", "before"], TokenType.MEETS_BEFORE),
    (["meets", "after"], TokenType.MEETS_AFTER),
    (["overlaps", "before"], TokenType.OVERLAPS_BEFORE),
    (["overlaps", "after"], TokenType.OVERLAPS_AFTER),
    (["on", "or", "before"], TokenType.ON_OR_BEFORE),
    (["on", "or", "after"], TokenType.ON_OR_AFTER),
    (["or", "less"], TokenType.OR_LESS),
    (["or", "more"], TokenType.OR_MORE),
    (["or", "before"], TokenType.OR_BEFORE),
    (["or", "after"], TokenType.OR_AFTER),
    # Interval types
    (["open", "closed"], TokenType.OPEN_CLOSED),
    (["closed", "open"], TokenType.CLOSED_OPEN),
    # Nullology
    (["is", "not", "null"], TokenType.IS_NOT_NULL),
    (["is", "null"], TokenType.IS_NULL),
    (["is", "true"], TokenType.IS_TRUE),
    (["is", "false"], TokenType.IS_FALSE),
    # List operators - properly variants (longer first)
    (["properly", "included", "in"], TokenType.PROPER_IN),
    (["properly", "includes"], TokenType.PROPER_INCLUDES),
    (["properly", "contains"], TokenType.PROPER_CONTAINS),
    # List operators - included in
    (["included", "in"], TokenType.INCLUDED_IN),
    # Singleton from operator
    (["singleton", "from"], TokenType.SINGLETON_FROM),
]


class Lexer:
    """
    CQL Lexer that converts source text into tokens.

    This lexer handles all CQL R1.5 features including:
    - Case-insensitive keywords
    - Quoted identifiers (double quotes)
    - String literals (single quotes)
    - Date/time literals (@ prefix)
    - Multi-character operators (!=, <>, <=, >=, !~, ->)
    - Single-line comments (//)
    - Block comments (/* */)
    - Multi-word keywords (meets before, overlaps after, etc.)
    """

    def __init__(self, source: str):
        """
        Initialize the lexer with CQL source code.

        Args:
            source: The CQL source code to tokenize
        """
        self.source = source
        self.pos = 0
        self.line = 1
        self.column = 1
        self.tokens: list[Token] = []

    def tokenize(self) -> list[Token]:
        """
        Tokenize the entire source and return the list of tokens.

        Returns:
            List of Token objects representing the tokenized source

        Raises:
            LexerError: If an invalid character or construct is encountered
        """
        while self.pos < len(self.source):
            self._skip_whitespace()
            if self.pos >= len(self.source):
                break

            char = self.source[self.pos]

            # Handle comments
            if char == "/" and self._peek() == "/":
                self._read_line_comment()
            elif char == "/" and self._peek() == "*":
                self._read_block_comment()
            # Handle date/time literals
            elif char == "@":
                self._read_datetime_literal()
            # Handle string literals
            elif char == "'":
                self._read_string()
            # Handle quoted identifiers
            elif char == '"':
                self._read_quoted_identifier()
            # Handle numbers
            elif char.isdigit():
                self._read_number()
            # Handle identifiers and keywords
            elif char.isalpha() or char == "_":
                self._read_identifier()
            # Handle operators and delimiters
            elif char == "-":
                if self._peek() == ">":
                    self._add_token(TokenType.ARROW, "->")
                    self._advance()
                    self._advance()
                else:
                    self._add_token(TokenType.MINUS, "-")
                    self._advance()
            elif char == "!":
                if self._peek() == "=":
                    self._add_token(TokenType.NOT_EQUALS, "!=")
                    self._advance()
                    self._advance()
                elif self._peek() == "~":
                    self._add_token(TokenType.NOT_EQUIVALENT, "!~")
                    self._advance()
                    self._advance()
                else:
                    self._add_token(TokenType.EXCLAMATION, "!")
                    self._advance()
            elif char == "<":
                if self._peek() == "=":
                    self._add_token(TokenType.LESS_EQUAL, "<=")
                    self._advance()
                    self._advance()
                elif self._peek() == ">":
                    self._add_token(TokenType.NOT_EQUALS, "<>")
                    self._advance()
                    self._advance()
                else:
                    self._add_token(TokenType.LESS_THAN, "<")
                    self._advance()
            elif char == ">":
                if self._peek() == "=":
                    self._add_token(TokenType.GREATER_EQUAL, ">=")
                    self._advance()
                    self._advance()
                else:
                    self._add_token(TokenType.GREATER_THAN, ">")
                    self._advance()
            elif char == "=":
                self._add_token(TokenType.EQUALS, "=")
                self._advance()
            elif char == "+":
                self._add_token(TokenType.PLUS, "+")
                self._advance()
            elif char == "*":
                self._add_token(TokenType.MULTIPLY, "*")
                self._advance()
            elif char == "/":
                self._add_token(TokenType.DIVIDE, "/")
                self._advance()
            elif char == "(":
                self._add_token(TokenType.LPAREN, "(")
                self._advance()
            elif char == ")":
                self._add_token(TokenType.RPAREN, ")")
                self._advance()
            elif char == "[":
                self._add_token(TokenType.LBRACKET, "[")
                self._advance()
            elif char == "]":
                self._add_token(TokenType.RBRACKET, "]")
                self._advance()
            elif char == "{":
                self._add_token(TokenType.LBRACE, "{")
                self._advance()
            elif char == "}":
                self._add_token(TokenType.RBRACE, "}")
                self._advance()
            elif char == ",":
                self._add_token(TokenType.COMMA, ",")
                self._advance()
            elif char == ".":
                self._add_token(TokenType.DOT, ".")
                self._advance()
            elif char == ":":
                self._add_token(TokenType.COLON, ":")
                self._advance()
            elif char == ";":
                self._add_token(TokenType.SEMICOLON, ";")
                self._advance()
            elif char == "#":
                self._add_token(TokenType.HASH, "#")
                self._advance()
            elif char == "@":
                # Already handled above for date/time, but if we get here
                # it's a standalone @ token
                self._add_token(TokenType.AT, "@")
                self._advance()
            elif char == "?":
                self._add_token(TokenType.QUESTION, "?")
                self._advance()
            elif char == "$":
                self._add_token(TokenType.DOLLAR, "$")
                self._advance()
            elif char == "`":
                self._add_token(TokenType.BACKTICK, "`")
                self._advance()
            elif char == "|":
                self._add_token(TokenType.PIPE, "|")
                self._advance()
            elif char == "^":
                self._add_token(TokenType.CARET, "^")
                self._advance()
            elif char == "~":
                self._add_token(TokenType.TILDE, "~")
                self._advance()
            elif char == "&":
                self._add_token(TokenType.CONCATENATE, "&")
                self._advance()
            else:
                raise LexerError(
                    f"Unexpected character: {char!r}",
                    position=(self.line, self.column),
                )

        self._add_token(TokenType.EOF, "")
        return self.tokens

    def _advance(self) -> str | None:
        """Advance position by one character and return it."""
        if self.pos >= len(self.source):
            return None
        char = self.source[self.pos]
        self.pos += 1
        if char == "\n":
            self.line += 1
            self.column = 1
        else:
            self.column += 1
        return char

    def _peek(self, offset: int = 1) -> str | None:
        """Look ahead without advancing position."""
        peek_pos = self.pos + offset
        if peek_pos >= len(self.source):
            return None
        return self.source[peek_pos]

    def _current(self) -> str | None:
        """Get current character without advancing."""
        if self.pos >= len(self.source):
            return None
        return self.source[self.pos]

    def _skip_whitespace(self) -> None:
        """Skip whitespace characters (but not newlines in significant positions)."""
        while self.pos < len(self.source):
            char = self.source[self.pos]
            if char in " \t\r":
                self._advance()
            elif char == "\n":
                # Skip newlines too for now
                self._advance()
            else:
                break

    def _add_token(self, token_type: TokenType, value: str) -> None:
        """Add a token to the token list."""
        # Adjust column to be 1-indexed and point to start of token
        col = self.column - len(value)
        if col < 1:
            col = 1
        self.tokens.append(Token(token_type, value, self.line, col))

    def _read_line_comment(self) -> None:
        """Read a single-line comment (// ...)."""
        start_line = self.line
        start_col = self.column
        value = ""

        # Skip the //
        self._advance()
        self._advance()

        while self.pos < len(self.source) and self.source[self.pos] != "\n":
            value += self.source[self.pos]
            self._advance()

        self.tokens.append(Token(TokenType.LINE_COMMENT, value, start_line, start_col))

    def _read_block_comment(self) -> None:
        """Read a block comment (/* ... */)."""
        start_line = self.line
        start_col = self.column
        value = ""

        # Skip the /*
        self._advance()
        self._advance()

        while self.pos < len(self.source):
            if self.source[self.pos] == "*" and self._peek() == "/":
                self._advance()  # Skip *
                self._advance()  # Skip /
                break
            value += self.source[self.pos]
            if self.source[self.pos] == "\n":
                self.line += 1
                self.column = 1
            self.pos += 1
            self.column += 1
        else:
            raise LexerError(
                "Unterminated block comment",
                position=(start_line, start_col),
            )

        self.tokens.append(Token(TokenType.BLOCK_COMMENT, value, start_line, start_col))

    def _read_string(self) -> None:
        """Read a single-quoted string literal."""
        start_line = self.line
        start_col = self.column
        value = ""

        # Skip opening quote
        self._advance()

        while self.pos < len(self.source):
            char = self.source[self.pos]
            if char == "'":
                # Check for escaped single quote ('')
                if self._peek() == "'":
                    value += "'"
                    self._advance()  # Skip first quote
                    self._advance()  # Skip second quote
                else:
                    self._advance()  # Skip closing quote
                    break
            elif char == "\\":
                # Handle escape sequences
                self._advance()
                next_char = self._current()
                if next_char is None:
                    raise LexerError(
                        "Unterminated string escape sequence",
                        position=(start_line, start_col),
                    )
                escape_chars = {
                    "n": "\n",
                    "t": "\t",
                    "r": "\r",
                    "\\": "\\",
                    "'": "'",
                    '"': '"',
                    "f": "\f",
                    "v": "\v",
                    "0": "\0",
                }
                if next_char in escape_chars:
                    value += escape_chars[next_char]
                elif next_char == "u":
                    # Unicode escape \uXXXX
                    self._advance()
                    hex_val = ""
                    for _ in range(4):
                        if self._current() is None:
                            raise LexerError(
                                "Unterminated unicode escape sequence",
                                position=(start_line, start_col),
                            )
                        hex_val += self._current()
                        self._advance()
                    try:
                        value += chr(int(hex_val, 16))
                    except ValueError:
                        raise LexerError(
                            f"Invalid unicode escape: \\u{hex_val}",
                            position=(start_line, start_col),
                        )
                    continue
                else:
                    value += "\\" + next_char
                self._advance()
            elif char == "\n":
                raise LexerError(
                    "Unterminated string literal",
                    position=(start_line, start_col),
                )
            else:
                value += char
                self._advance()
        else:
            # Reached EOF without finding closing quote
            raise LexerError(
                "Unterminated string literal",
                position=(start_line, start_col),
            )

        self.tokens.append(Token(TokenType.STRING, value, start_line, start_col))

    def _read_quoted_identifier(self) -> None:
        """Read a double-quoted identifier."""
        start_line = self.line
        start_col = self.column
        value = ""

        # Skip opening quote
        self._advance()

        while self.pos < len(self.source):
            char = self.source[self.pos]
            if char == '"':
                self._advance()  # Skip closing quote
                break
            value += char
            self._advance()
        else:
            raise LexerError(
                "Unterminated quoted identifier",
                position=(start_line, start_col),
            )

        self.tokens.append(Token(TokenType.QUOTED_IDENTIFIER, value, start_line, start_col))

    def _read_datetime_literal(self) -> None:
        """Read a date/time literal (@ prefix)."""
        start_line = self.line
        start_col = self.column
        value = ""

        # Skip the @
        self._advance()

        # Read the date/time pattern
        # Format: YYYY-MM-DD or YYYY-MM-DDThh:mm:ss or YYYY-MM-DDThh:mm:ss.fff+ZZ:ZZ
        date_pattern = (
            r"(\d{4}-\d{2}-\d{2})"  # Date
            r"(T\d{2}:\d{2}:\d{2})?"  # Optional time
            r"(\.\d+)?"  # Optional milliseconds
            r"(Z|[+-]\d{2}:\d{2})?"  # Optional timezone
        )

        # Collect characters that look like a date/time
        datetime_chars = ""
        while self.pos < len(self.source):
            char = self.source[self.pos]
            if char.isalnum() or char in "-T:.+Z":
                datetime_chars += char
                self._advance()
            else:
                break

        value = datetime_chars

        # Validate date/time components
        if value:
            self._validate_datetime_literal(value, start_line, start_col)

        # Determine if it's a date, datetime, or time
        if "T" in value:
            self.tokens.append(Token(TokenType.DATETIME, value, start_line, start_col))
        elif ":" in value:
            # Time only format @Thh:mm:ss
            self.tokens.append(Token(TokenType.TIME, value, start_line, start_col))
        else:
            self.tokens.append(Token(TokenType.DATE, value, start_line, start_col))

    def _validate_datetime_literal(self, value: str, line: int, col: int) -> None:
        """Validate date/time literal components are within valid ranges."""
        import re
        # Extract date portion (before T)
        date_part = value.split("T")[0] if "T" in value else value
        # Only validate if it looks like a date (has dashes)
        if "-" not in date_part:
            return
        parts = date_part.split("-")
        if len(parts) >= 1:
            year = parts[0]
            if not year.isdigit() or len(year) != 4:
                raise LexerError(f"Invalid year in date literal @{value} at line {line}, column {col}")
        if len(parts) >= 2:
            month = parts[1]
            if month.isdigit():
                m = int(month)
                if m < 1 or m > 12:
                    raise LexerError(f"Invalid month {m} in date literal @{value} at line {line}, column {col} (must be 1-12)")
        if len(parts) >= 3:
            day = parts[2]
            if day.isdigit():
                d = int(day)
                if d < 1 or d > 31:
                    raise LexerError(f"Invalid day {d} in date literal @{value} at line {line}, column {col} (must be 1-31)")
        # Validate time portion if present
        if "T" in value:
            time_part = value.split("T")[1]
            # Strip timezone
            time_only = re.split(r"[Z+-]", time_part)[0]
            time_parts = time_only.split(":")
            if len(time_parts) >= 1 and time_parts[0].isdigit():
                h = int(time_parts[0])
                if h > 23:
                    raise LexerError(f"Invalid hour {h} in datetime literal @{value} at line {line}, column {col} (must be 0-23)")
            if len(time_parts) >= 2 and time_parts[1].isdigit():
                mi = int(time_parts[1])
                if mi > 59:
                    raise LexerError(f"Invalid minute {mi} in datetime literal @{value} at line {line}, column {col} (must be 0-59)")
            if len(time_parts) >= 3:
                sec_str = time_parts[2].split(".")[0]
                if sec_str.isdigit():
                    s = int(sec_str)
                    if s > 59:
                        raise LexerError(f"Invalid second {s} in datetime literal @{value} at line {line}, column {col} (must be 0-59)")

    def _read_number(self) -> None:
        """Read an integer or decimal number."""
        start_line = self.line
        start_col = self.column
        value = ""
        has_decimal = False

        while self.pos < len(self.source):
            char = self.source[self.pos]
            if char.isdigit():
                value += char
                self._advance()
            elif char == "." and not has_decimal:
                # Check if it's a decimal point or a method call
                if self._peek() and self._peek().isdigit():
                    has_decimal = True
                    value += char
                    self._advance()
                else:
                    # It's a method call like 3.toString()
                    break
            else:
                break

        # Check for Long suffix (before has_decimal check)
        if not has_decimal and (self._current() == 'L' or self._current() == 'l'):
            self._advance()  # consume L
            self.tokens.append(Token(TokenType.LONG, value, start_line, start_col))
            return

        if has_decimal:
            self.tokens.append(Token(TokenType.DECIMAL, value, start_line, start_col))
        else:
            self.tokens.append(Token(TokenType.INTEGER, value, start_line, start_col))

    def _read_identifier(self) -> None:
        """Read an identifier or keyword."""
        start_line = self.line
        start_col = self.column
        value = ""

        while self.pos < len(self.source):
            char = self.source[self.pos]
            if char.isalnum() or char == "_":
                value += char
                self._advance()
            else:
                break

        # Check for multi-word keywords by looking ahead
        # Try to match longer multi-word sequences first
        saved_pos = self.pos
        saved_col = self.column
        matched_multi = self._try_match_multi_word_keyword(value, start_line, start_col)

        if matched_multi:
            return

        # Check if it's a keyword (try exact match first for types, then case-insensitive)
        token_type = KEYWORDS.get(value)
        if not token_type:
            # Try case-insensitive match
            token_type = KEYWORDS.get(value.lower())
        if token_type:
            self.tokens.append(Token(token_type, value, start_line, start_col))
        else:
            self.tokens.append(Token(TokenType.IDENTIFIER, value, start_line, start_col))

    def _try_match_multi_word_keyword(
        self, first_word: str, start_line: int, start_col: int
    ) -> bool:
        """
        Try to match a multi-word keyword starting with the given word.

        Returns True if a multi-word keyword was matched, False otherwise.
        """
        # Get the lowercased first word for comparison
        first_lower = first_word.lower()

        # Collect potential words to match
        words = [first_lower]
        positions = [(self.pos, self.column)]

        # Read ahead to collect more words
        temp_pos = self.pos
        temp_col = self.column
        temp_line = self.line

        while temp_pos < len(self.source):
            # Skip whitespace
            while temp_pos < len(self.source) and self.source[temp_pos] in " \t\n\r":
                if self.source[temp_pos] == "\n":
                    temp_line += 1
                    temp_col = 1
                else:
                    temp_col += 1
                temp_pos += 1

            if temp_pos >= len(self.source):
                break

            char = self.source[temp_pos]
            if char.isalpha() or char == "_":
                word = ""
                while temp_pos < len(self.source) and (
                    self.source[temp_pos].isalnum() or self.source[temp_pos] == "_"
                ):
                    word += self.source[temp_pos]
                    temp_pos += 1
                    temp_col += 1
                words.append(word.lower())
                positions.append((temp_pos, temp_col))
            else:
                break

        # Try to match multi-word keywords (longest first)
        for kw_words, token_type in MULTI_WORD_KEYWORDS:
            if len(words) >= len(kw_words):
                match = True
                for i, kw_word in enumerate(kw_words):
                    if words[i] != kw_word:
                        match = False
                        break
                if match:
                    # Found a match - update position
                    self.pos = positions[len(kw_words) - 1][0]
                    self.column = positions[len(kw_words) - 1][1]

                    # Build the value string
                    value = " ".join(words[: len(kw_words)])
                    self.tokens.append(Token(token_type, value, start_line, start_col))
                    return True

        return False


def tokenize_cql(source: str) -> list[Token]:
    """
    Convenience function to tokenize CQL source.

    Args:
        source: CQL source code

    Returns:
        List of Token objects
    """
    lexer = Lexer(source)
    return lexer.tokenize()


__all__ = [
    "Lexer",
    "Token",
    "TokenType",
    "tokenize_cql",
]
