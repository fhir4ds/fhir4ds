"""
CQL Parser.

Recursive descent parser for CQL R1.5 that constructs an Abstract Syntax Tree (AST)
from CQL tokens produced by the lexer.

Reference: https://cql.hl7.org/05-libraries.html

TODO (Task C1): Fix parsing of QICoreCommon.cql
The parser currently fails on QICoreCommon.cql at line 488 due to two issues:
1. `Resource` type is not recognized as a valid base FHIR type
2. `&` character in URL string literals causes lexer issues

Once fixed, Tasks C2-C5 can dynamically extract library knowledge:
- C2: Extract code constants from parsed library ASTs
- C3: Extract status filter logic from function body ASTs
- C4: Inline all fluent function bodies from parsed ASTs (eliminate body_sql)
- C5: Resolve component codes via valueset queries from CQL context
"""

from __future__ import annotations

import logging
from typing import Callable, List, Optional, Union

from ..errors import ParseError

_logger = logging.getLogger(__name__)
from ..parser.ast_nodes import (
    AliasRef,
    AggregateClause,
    AggregateExpression,
    AllExpression,
    AnyExpression,
    BinaryExpression,
    CaseExpression,
    CaseItem,
    CodeDefinition,
    CodeSystemDefinition,
    ConceptDefinition,
    ConditionalExpression,
    ContextDefinition,
    DateComponent,
    DateTimeLiteral,
    Definition,
    DifferenceBetween,
    DistinctExpression,
    DurationBetween,
    ExistsExpression,
    Expression,
    FirstExpression,
    FunctionDefinition,
    FunctionRef,
    Identifier,
    IncludeDefinition,
    IndexerExpression,
    InstanceExpression,
    Interval,
    IntervalTypeSpecifier,
    LastExpression,
    LetClause,
    Library,
    ListExpression,
    ListTypeSpecifier,
    Literal,
    MethodInvocation,
    NamedTypeSpecifier,
    ParameterDef,
    ParameterDefinition,
    Property,
    QualifiedIdentifier,
    Query,
    QuerySource,
    Quantity,
    Retrieve,
    ReturnClause,
    SingletonExpression,
    SkipExpression,
    SortByItem,
    SortClause,
    TakeExpression,
    TimeLiteral,
    TupleElement,
    TupleExpression,
    TupleTypeSpecifier,
    TypeSpecifier,
    UnaryExpression,
    UsingDefinition,
    ValueSetDefinition,
    WhereClause,
    WithClause,
    ChoiceTypeSpecifier,
)
from ..parser.lexer import Lexer, Token, TokenType


class CQLParser:
    """
    Recursive descent parser for CQL R1.5.

    This parser uses the tokens produced by the Lexer to construct
    an Abstract Syntax Tree (AST) representing the CQL program structure.

    Operator Precedence (lowest to highest):
        - or
        - xor
        - and
        - implies
        - equality (=, !=, ~, !~)
        - comparison (<, >, <=, >=)
        - type operator (is, as)
        - addition (+, -, &, |)
        - multiplication (*, /, div, mod)
        - power (^)
        - unary (not, -, exists, distinct)
        - postfix (., [], ())
        - primary
    """

    def __init__(self, tokens: List[Token]):
        """
        Initialize the parser with a list of tokens.

        Args:
            tokens: List of tokens from the lexer.
        """
        self.tokens = tokens
        self.pos = 0

    # =========================================================================
    # Helper Methods
    # =========================================================================

    def current(self) -> Token:
        """Get the current token, skipping comments."""
        self._skip_comments()
        if self.pos >= len(self.tokens):
            return self.tokens[-1]  # Return EOF
        return self.tokens[self.pos]

    def peek(self, offset: int = 1) -> Token:
        """
        Look ahead at a token without advancing, skipping comments.

        Args:
            offset: Number of tokens to look ahead (default 1).
        """
        peek_pos = self.pos + offset
        while peek_pos < len(self.tokens) and self.tokens[peek_pos].type in (TokenType.LINE_COMMENT, TokenType.BLOCK_COMMENT):
            peek_pos += 1
        if peek_pos >= len(self.tokens):
            return self.tokens[-1]  # Return EOF
        return self.tokens[peek_pos]

    def advance(self) -> Token:
        """Move to the next token and return the previous one."""
        token = self.current()
        self.pos += 1
        return token

    def _skip_comments(self) -> None:
        """Skip over comment tokens (LINE_COMMENT and BLOCK_COMMENT)."""
        while self.pos < len(self.tokens) and self.tokens[self.pos].type in (TokenType.LINE_COMMENT, TokenType.BLOCK_COMMENT):
            self.pos += 1

    def match(self, *types: TokenType) -> bool:
        """
        Check if current token matches any of the given types.

        Args:
            types: Token types to match.
        """
        return self.current().type in types

    def check(self, token_type: TokenType) -> bool:
        """Check if current token is of the given type."""
        return self.current().type == token_type

    def expect(self, token_type: TokenType, message: str) -> Token:
        """
        Expect a specific token type or raise an error.

        Args:
            token_type: Expected token type.
            message: Error message if expectation fails.
        """
        if self.current().type != token_type:
            token = self.current()
            raise ParseError(
                f"{message}. Got {token.type.name} '{token.value}'",
                position=(token.line, token.column),
            )
        return self.advance()

    def match_and_advance(self, *types: TokenType) -> Optional[Token]:
        """
        Match and consume if current token matches any of the given types.

        Args:
            types: Token types to match.
        """
        if self.match(*types):
            return self.advance()
        return None

    # =========================================================================
    # Library Structure Parsing
    # =========================================================================

    def parse_library(self) -> Library:
        """
        Parse a complete CQL library.

        This is the main entry point for parsing CQL source code.
        """
        # Parse library declaration
        self.expect(TokenType.LIBRARY, "Expected 'library' declaration")
        identifier = self._parse_identifier_name()
        version = None

        # Optional version
        if self.match_and_advance(TokenType.VERSION):
            version_token = self.expect(TokenType.STRING, "Expected version string")
            version = version_token.value

        library = Library(identifier=identifier, version=version)

        # Parse library body
        while not self.check(TokenType.EOF):
            self._parse_library_element(library)

        return library

    def _parse_library_element(self, library: Library) -> None:
        """Parse a library element (using, include, define, etc.)."""
        if self.match(TokenType.USING):
            library.using.append(self.parse_using_definition())
        elif self.match(TokenType.INCLUDE):
            library.includes.append(self.parse_include_definition())
        elif self.match(TokenType.CODESYSTEM):
            library.codesystems.append(self.parse_codesystem_definition())
        elif self.match(TokenType.VALUESYSTEM):
            library.valuesets.append(self.parse_valueset_definition())
        elif self.match(TokenType.CODE):
            library.codes.append(self.parse_code_definition())
        elif self.match(TokenType.CONCEPT):
            library.concepts.append(self.parse_concept_definition())
        elif self.match(TokenType.PARAMETER):
            library.parameters.append(self.parse_parameter_definition())
        elif self.match(TokenType.CONTEXT):
            library.context = self.parse_context_definition()
        elif self.match(TokenType.DEFINE):
            statement = self._parse_define_statement()
            if isinstance(statement, FunctionDefinition):
                library.statements.append(statement)
            else:
                library.statements.append(statement)
        else:
            token = self.current()
            raise ParseError(
                f"Unexpected token in library: {token.type.name} '{token.value}'",
                position=(token.line, token.column),
            )

    def parse_using_definition(self) -> UsingDefinition:
        """Parse a using definition (e.g., 'using FHIR version \"4.0.1\"')."""
        self.expect(TokenType.USING, "Expected 'using'")
        model = self._parse_identifier_name()
        version = None

        if self.match_and_advance(TokenType.VERSION):
            version_token = self.expect(TokenType.STRING, "Expected version string")
            version = version_token.value

        return UsingDefinition(model=model, version=version)

    def parse_include_definition(self) -> IncludeDefinition:
        """Parse an include definition."""
        self.expect(TokenType.INCLUDE, "Expected 'include'")
        path = self._parse_identifier_name()
        # Consume additional .segment parts for namespaced paths
        # e.g. hl7.fhir.uv.cql.FHIRHelpers
        while self.match(TokenType.DOT):
            self.advance()  # consume DOT
            segment = self._parse_identifier_name()
            path = f"{path}.{segment}"

        version = None
        alias = None

        if self.match_and_advance(TokenType.VERSION):
            version_token = self.expect(TokenType.STRING, "Expected version string")
            version = version_token.value

        if self.match_and_advance(TokenType.CALLED):
            alias = self._parse_identifier_name()

        return IncludeDefinition(path=path, version=version, alias=alias)

    def parse_parameter_definition(self) -> ParameterDefinition:
        """Parse a parameter definition."""
        self.expect(TokenType.PARAMETER, "Expected 'parameter'")
        name = self._parse_identifier_name()
        param_type = None
        default = None

        # Optional type specifier
        if self.match(TokenType.IDENTIFIER, TokenType.QUOTED_IDENTIFIER,
                      TokenType.BOOLEAN, TokenType.INTEGER_TYPE, TokenType.LONG_TYPE, TokenType.DECIMAL_TYPE,
                      TokenType.STRING_TYPE, TokenType.DATE_TYPE, TokenType.DATETIME_TYPE,
                      TokenType.TIME_TYPE, TokenType.QUANTITY, TokenType.INTERVAL,
                      TokenType.LIST_TYPE, TokenType.TUPLE, TokenType.CHOICE,
                      TokenType.CODE_TYPE, TokenType.CONCEPT_TYPE, TokenType.CODESYSTEM_TYPE,
                      TokenType.VALUESET_TYPE, TokenType.ANY,
                      TokenType.RESOURCE, TokenType.PATIENT, TokenType.PRACTITIONER,
                      TokenType.ORGANIZATION, TokenType.LOCATION, TokenType.BUNDLE,
                      TokenType.DATE_FROM, TokenType.TIME_FROM,
                      TokenType.CODE, TokenType.CONCEPT):
            param_type = self.parse_type_specifier()

        # Optional default value
        if self.match_and_advance(TokenType.DEFAULT):
            default = self.parse_expression()

        return ParameterDefinition(name=name, type=param_type, default=default)

    def parse_context_definition(self) -> ContextDefinition:
        """Parse a context definition."""
        self.expect(TokenType.CONTEXT, "Expected 'context'")
        name = self._parse_identifier_name()
        return ContextDefinition(name=name)

    def _parse_define_statement(self) -> Union[Definition, FunctionDefinition]:
        """Parse a define statement (expression or function)."""
        self.expect(TokenType.DEFINE, "Expected 'define'")

        # Check for fluent function definition
        is_fluent = self.match(TokenType.FLUENT)
        if is_fluent:
            self.advance()  # consume FLUENT token

        # Check for function definition
        if self.match_and_advance(TokenType.FUNCTION):
            return self._parse_function_definition(fluent=is_fluent)

        name = self._parse_identifier_name()
        self.expect(TokenType.COLON, "Expected ':' after definition name")

        expression = self.parse_expression()
        return Definition(name=name, expression=expression)

    def _parse_function_definition(self, fluent: bool = False) -> FunctionDefinition:
        """Parse a function definition.

        Args:
            fluent: Whether this is a fluent function definition.
        """
        name = self._parse_identifier_name()
        self.expect(TokenType.LPAREN, "Expected '(' after function name")

        parameters = []
        if not self.check(TokenType.RPAREN):
            parameters.append(self._parse_parameter_def())
            while self.match_and_advance(TokenType.COMMA):
                parameters.append(self._parse_parameter_def())

        self.expect(TokenType.RPAREN, "Expected ')' after parameters")

        return_type = None
        # Check for 'returns' keyword or colon for return type
        if self.match_and_advance(TokenType.RETURNS):
            return_type = self.parse_type_specifier()

        expression = None
        if self.match_and_advance(TokenType.COLON):
            expression = self.parse_expression()

        return FunctionDefinition(
            name=name,
            parameters=parameters,
            return_type=return_type,
            expression=expression,
            fluent=fluent,
        )

    def _parse_parameter_def(self) -> ParameterDef:
        """Parse a function parameter definition."""
        name = self._parse_identifier_name()
        param_type = None
        default = None

        # Type can be specified with or without colon
        if self.match_and_advance(TokenType.COLON):
            param_type = self.parse_type_specifier()
        elif self.match(TokenType.IDENTIFIER, TokenType.QUOTED_IDENTIFIER,
                        TokenType.BOOLEAN, TokenType.INTEGER_TYPE, TokenType.LONG_TYPE, TokenType.DECIMAL_TYPE,
                        TokenType.STRING_TYPE, TokenType.DATE_TYPE, TokenType.DATETIME_TYPE,
                        TokenType.TIME_TYPE, TokenType.QUANTITY, TokenType.INTERVAL,
                        TokenType.LIST_TYPE, TokenType.TUPLE, TokenType.CHOICE,
                        TokenType.CODE_TYPE, TokenType.CONCEPT_TYPE, TokenType.CODESYSTEM_TYPE,
                        TokenType.VALUESET_TYPE, TokenType.ANY,
                        TokenType.RESOURCE, TokenType.PATIENT, TokenType.PRACTITIONER,
                        TokenType.ORGANIZATION, TokenType.LOCATION, TokenType.BUNDLE,
                        TokenType.DATE_FROM, TokenType.TIME_FROM,
                        TokenType.CODE, TokenType.CONCEPT):
            param_type = self.parse_type_specifier()

        if self.match_and_advance(TokenType.EQUALS):
            default = self.parse_expression()

        return ParameterDef(name=name, type=param_type, default=default)

    def parse_codesystem_definition(self) -> CodeSystemDefinition:
        """Parse a codesystem definition."""
        self.expect(TokenType.CODESYSTEM, "Expected 'codesystem'")
        name = self._parse_identifier_name()
        self.expect(TokenType.COLON, "Expected ':' after codesystem name")

        id_token = self.expect(TokenType.STRING, "Expected codesystem identifier")
        codesystem_id = id_token.value
        version = None

        if self.match_and_advance(TokenType.VERSION):
            version_token = self.expect(TokenType.STRING, "Expected version string")
            version = version_token.value

        return CodeSystemDefinition(name=name, id=codesystem_id, version=version)

    def parse_valueset_definition(self) -> ValueSetDefinition:
        """Parse a valueset definition."""
        self.expect(TokenType.VALUESYSTEM, "Expected 'valueset'")
        name = self._parse_identifier_name()
        self.expect(TokenType.COLON, "Expected ':' after valueset name")

        id_token = self.expect(TokenType.STRING, "Expected valueset identifier")
        valueset_id = id_token.value
        version = None
        codesystem = None

        if self.match_and_advance(TokenType.VERSION):
            version_token = self.expect(TokenType.STRING, "Expected version string")
            version = version_token.value

        return ValueSetDefinition(name=name, id=valueset_id, version=version, codesystem=codesystem)

    def parse_code_definition(self) -> CodeDefinition:
        """Parse a code definition."""
        self.expect(TokenType.CODE, "Expected 'code'")
        name = self._parse_identifier_name()
        self.expect(TokenType.COLON, "Expected ':' after code name")

        code_token = self.expect(TokenType.STRING, "Expected code value")
        code_value = code_token.value

        self.expect(TokenType.FROM, "Expected 'from' before codesystem reference")
        codesystem = self._parse_identifier_name()
        # Support qualified codesystem references like QICoreCommon."SNOMEDCT"
        while self.match_and_advance(TokenType.DOT):
            codesystem = codesystem + "." + self._parse_identifier_name()

        display = None
        if self.match_and_advance(TokenType.DISPLAY):
            display_token = self.expect(TokenType.STRING, "Expected display string")
            display = display_token.value

        return CodeDefinition(name=name, codesystem=codesystem, code=code_value, display=display)

    def parse_concept_definition(self) -> ConceptDefinition:
        """Parse a concept definition."""
        self.expect(TokenType.CONCEPT, "Expected 'concept'")
        name = self._parse_identifier_name()
        self.expect(TokenType.COLON, "Expected ':' after concept name")

        codes = []

        if self.match_and_advance(TokenType.LBRACE):
            # Parse code list
            while not self.check(TokenType.RBRACE):
                if self.match(TokenType.CODE):
                    codes.append(self.parse_code_definition())
                elif self.match(TokenType.IDENTIFIER, TokenType.QUOTED_IDENTIFIER):
                    codes.append(self._parse_identifier_name())

                if not self.match_and_advance(TokenType.COMMA):
                    break

            self.expect(TokenType.RBRACE, "Expected '}' after concept codes")

        display = None
        if self.match_and_advance(TokenType.DISPLAY):
            display_token = self.expect(TokenType.STRING, "Expected display string")
            display = display_token.value

        return ConceptDefinition(name=name, codes=codes, display=display)

    # =========================================================================
    # Expression Parsing with Precedence
    # =========================================================================

    def parse_expression(self) -> Expression:
        """Entry point for expression parsing."""
        return self.parse_or_expression()

    def parse_or_expression(self) -> Expression:
        """Parse OR expression (lowest precedence)."""
        left = self.parse_xor_expression()

        while self.match_and_advance(TokenType.OR):
            right = self.parse_xor_expression()
            left = BinaryExpression(operator="or", left=left, right=right)

        return left

    def parse_xor_expression(self) -> Expression:
        """Parse XOR expression."""
        left = self.parse_and_expression()

        while self.match_and_advance(TokenType.XOR):
            right = self.parse_and_expression()
            left = BinaryExpression(operator="xor", left=left, right=right)

        return left

    def parse_and_expression(self) -> Expression:
        """Parse AND expression."""
        left = self.parse_implies_expression()

        while self.match_and_advance(TokenType.AND):
            right = self.parse_implies_expression()
            left = BinaryExpression(operator="and", left=left, right=right)

        return left

    def parse_implies_expression(self) -> Expression:
        """Parse IMPLIES expression."""
        left = self.parse_equality_expression()

        while self.match_and_advance(TokenType.IMPLIES):
            right = self.parse_equality_expression()
            left = BinaryExpression(operator="implies", left=left, right=right)

        return left

    def parse_equality_expression(self) -> Expression:
        """Parse equality expression (=, !=, ~, !~)."""
        left = self.parse_comparison_expression()

        while True:
            if self.match_and_advance(TokenType.EQUALS):
                right = self.parse_comparison_expression()
                left = BinaryExpression(operator="=", left=left, right=right)
            elif self.match_and_advance(TokenType.NOT_EQUALS):
                right = self.parse_comparison_expression()
                left = BinaryExpression(operator="!=", left=left, right=right)
            elif self.match_and_advance(TokenType.TILDE):
                right = self.parse_comparison_expression()
                left = BinaryExpression(operator="~", left=left, right=right)
            elif self.match_and_advance(TokenType.NOT_EQUIVALENT):
                right = self.parse_comparison_expression()
                left = BinaryExpression(operator="!~", left=left, right=right)
            else:
                break

        return left

    def parse_comparison_expression(self) -> Expression:
        """Parse comparison expression (<, >, <=, >=) and list/interval membership operators."""
        left = self.parse_type_expression()

        while True:
            if self.match_and_advance(TokenType.LESS_THAN):
                right = self.parse_type_expression()
                left = BinaryExpression(operator="<", left=left, right=right)
            elif self.match_and_advance(TokenType.GREATER_THAN):
                right = self.parse_type_expression()
                left = BinaryExpression(operator=">", left=left, right=right)
            elif self.match_and_advance(TokenType.LESS_EQUAL):
                right = self.parse_type_expression()
                left = BinaryExpression(operator="<=", left=left, right=right)
            elif self.match_and_advance(TokenType.GREATER_EQUAL):
                right = self.parse_type_expression()
                left = BinaryExpression(operator=">=", left=left, right=right)
            # List membership operators
            elif self.match_and_advance(TokenType.IN):
                right = self.parse_type_expression()
                left = BinaryExpression(operator="in", left=left, right=right)
            elif self.match_and_advance(TokenType.CONTAINS):
                right = self.parse_type_expression()
                left = BinaryExpression(operator="contains", left=left, right=right)
            elif self.match_and_advance(TokenType.PROPER_CONTAINS):
                right = self.parse_type_expression()
                left = BinaryExpression(operator="properly contains", left=left, right=right)
            elif self.match_and_advance(TokenType.PROPER_IN):
                right = self.parse_type_expression()
                left = BinaryExpression(operator="properly included in", left=left, right=right)
            # Interval/List inclusion operators
            elif self.match_and_advance(TokenType.INCLUDES):
                right = self.parse_type_expression()
                left = BinaryExpression(operator="includes", left=left, right=right)
            elif self.match_and_advance(TokenType.INCLUDED_IN):
                right = self.parse_type_expression()
                left = BinaryExpression(operator="included in", left=left, right=right)
            # Temporal/Interval operators
            elif self.match_and_advance(TokenType.AFTER):
                # Handle "after or on" = "on or after"
                if self.match(TokenType.OR) and self.peek().type == TokenType.IDENTIFIER and self.peek().value.lower() == "on":
                    self.advance()  # consume 'or'
                    self.advance()  # consume 'on'
                    precision = self._try_parse_precision_of()
                    right = self.parse_type_expression()
                    op = f"on or after {precision} of" if precision else "on or after"
                    left = BinaryExpression(operator=op, left=left, right=right)
                else:
                    # Check for precision specifier: after year of, after month of, etc.
                    precision = self._try_parse_precision_of()
                    if precision:
                        right = self.parse_type_expression()
                        left = BinaryExpression(operator=f"after {precision} of", left=left, right=right)
                    else:
                        right = self.parse_type_expression()
                        left = BinaryExpression(operator="after", left=left, right=right)
            elif self.match_and_advance(TokenType.BEFORE):
                # Handle "before or on" = "on or before"
                if self.match(TokenType.OR) and self.peek().type == TokenType.IDENTIFIER and self.peek().value.lower() == "on":
                    self.advance()  # consume 'or'
                    self.advance()  # consume 'on'
                    precision = self._try_parse_precision_of()
                    right = self.parse_type_expression()
                    op = f"on or before {precision} of" if precision else "on or before"
                    left = BinaryExpression(operator=op, left=left, right=right)
                else:
                    # Check for precision specifier: before year of, before month of, etc.
                    precision = self._try_parse_precision_of()
                    if precision:
                        right = self.parse_type_expression()
                        left = BinaryExpression(operator=f"before {precision} of", left=left, right=right)
                    else:
                        right = self.parse_type_expression()
                        left = BinaryExpression(operator="before", left=left, right=right)
            elif self.match_and_advance(TokenType.DURING):
                right = self.parse_type_expression()
                left = BinaryExpression(operator="during", left=left, right=right)
            elif self.match_and_advance(TokenType.OVERLAPS):
                right = self.parse_type_expression()
                left = BinaryExpression(operator="overlaps", left=left, right=right)
            elif self.match_and_advance(TokenType.OVERLAPS_BEFORE):
                right = self.parse_type_expression()
                left = BinaryExpression(operator="overlaps before", left=left, right=right)
            elif self.match_and_advance(TokenType.OVERLAPS_AFTER):
                right = self.parse_type_expression()
                left = BinaryExpression(operator="overlaps after", left=left, right=right)
            elif self.match_and_advance(TokenType.MEETS):
                right = self.parse_type_expression()
                left = BinaryExpression(operator="meets", left=left, right=right)
            elif self.match_and_advance(TokenType.MEETS_BEFORE):
                right = self.parse_type_expression()
                left = BinaryExpression(operator="meets before", left=left, right=right)
            elif self.match_and_advance(TokenType.MEETS_AFTER):
                right = self.parse_type_expression()
                left = BinaryExpression(operator="meets after", left=left, right=right)
            elif self.match_and_advance(TokenType.STARTS):
                # Handle "starts same [precision] as EXPR" temporal operator
                if self.match(TokenType.IDENTIFIER) and self.current().value.lower() == "same" \
                        and (self.peek().type == TokenType.AS or self.peek().type in (
                            TokenType.YEAR, TokenType.MONTH, TokenType.DAY, TokenType.HOUR,
                            TokenType.MINUTE, TokenType.SECOND, TokenType.MILLISECOND, TokenType.WEEK)):
                    self.advance()  # consume 'same'
                    # Optionally consume precision unit (e.g. "day" in "same day as")
                    precision = ""
                    if self.match(TokenType.YEAR, TokenType.MONTH, TokenType.DAY, TokenType.HOUR,
                                  TokenType.MINUTE, TokenType.SECOND, TokenType.MILLISECOND, TokenType.WEEK):
                        precision = " " + self.advance().value
                    self.advance()  # consume 'as'
                    right = self.parse_type_expression()
                    left = BinaryExpression(operator=f"starts same{precision} as", left=left, right=right)
                # Handle "starts before or on EXPR" = "starts on or before EXPR"
                elif self.match(TokenType.BEFORE) and self.peek().type == TokenType.OR and \
                        self.peek(2).type == TokenType.IDENTIFIER and self.peek(2).value.lower() == "on":
                    self.advance(); self.advance(); self.advance()
                    precision = self._try_parse_precision_of()
                    right = self.parse_type_expression()
                    op = f"on or before {precision} of" if precision else "on or before"
                    left = BinaryExpression(operator=f"starts {op}", left=left, right=right)
                # Handle "starts after or on EXPR" = "starts on or after EXPR"
                elif self.match(TokenType.AFTER) and self.peek().type == TokenType.OR and \
                        self.peek(2).type == TokenType.IDENTIFIER and self.peek(2).value.lower() == "on":
                    self.advance(); self.advance(); self.advance()
                    precision = self._try_parse_precision_of()
                    right = self.parse_type_expression()
                    op = f"on or after {precision} of" if precision else "on or after"
                    left = BinaryExpression(operator=f"starts {op}", left=left, right=right)
                # Handle "starts within N unit of EXPR" timing operator
                elif self.match(TokenType.IDENTIFIER) and self.current().value.lower() == "within":
                    self.advance()  # consume 'within'
                    if self.match(TokenType.INTEGER, TokenType.DECIMAL):
                        quantity_value = self.advance().value
                        if self.match(TokenType.YEAR, TokenType.MONTH, TokenType.DAY,
                                      TokenType.HOUR, TokenType.MINUTE, TokenType.SECOND,
                                      TokenType.MILLISECOND, TokenType.WEEK, TokenType.YEARS,
                                      TokenType.MONTHS, TokenType.DAYS, TokenType.HOURS,
                                      TokenType.MINUTES, TokenType.SECONDS, TokenType.MILLISECONDS,
                                      TokenType.WEEKS):
                            unit = self.advance().value
                            self.expect(TokenType.OF, "Expected 'of' after unit in 'starts within N unit of'")
                            right = self.parse_type_expression()
                            left = BinaryExpression(
                                operator=f"starts within {quantity_value} {unit} of",
                                left=left,
                                right=right,
                            )
                        else:
                            right = self.parse_type_expression()
                            left = BinaryExpression(operator="starts", left=left, right=right)
                    else:
                        right = self.parse_type_expression()
                        left = BinaryExpression(operator="starts", left=left, right=right)
                else:
                    # Check for complex temporal comparison pattern:
                    # starts <quantity> or less/or more on or after/on or before <precision> of start of/end of <expr>
                    right = self._try_parse_complex_interval_comparison("starts")
                    if right is None:
                        right = self.parse_type_expression()
                    left = BinaryExpression(operator="starts", left=left, right=right)
            elif self.match_and_advance(TokenType.ENDS):
                # Handle "ends same [precision] as EXPR" temporal operator
                if self.match(TokenType.IDENTIFIER) and self.current().value.lower() == "same" \
                        and (self.peek().type == TokenType.AS or self.peek().type in (
                            TokenType.YEAR, TokenType.MONTH, TokenType.DAY, TokenType.HOUR,
                            TokenType.MINUTE, TokenType.SECOND, TokenType.MILLISECOND, TokenType.WEEK)):
                    self.advance()  # consume 'same'
                    # Optionally consume precision unit (e.g. "day" in "same day as")
                    precision = ""
                    if self.match(TokenType.YEAR, TokenType.MONTH, TokenType.DAY, TokenType.HOUR,
                                  TokenType.MINUTE, TokenType.SECOND, TokenType.MILLISECOND, TokenType.WEEK):
                        precision = " " + self.advance().value
                    self.advance()  # consume 'as'
                    right = self.parse_type_expression()
                    left = BinaryExpression(operator=f"ends same{precision} as", left=left, right=right)
                # Handle "ends before or on EXPR" = "ends on or before EXPR"
                elif self.match(TokenType.BEFORE) and self.peek().type == TokenType.OR and \
                        self.peek(2).type == TokenType.IDENTIFIER and self.peek(2).value.lower() == "on":
                    self.advance(); self.advance(); self.advance()
                    precision = self._try_parse_precision_of()
                    right = self.parse_type_expression()
                    op = f"on or before {precision} of" if precision else "on or before"
                    left = BinaryExpression(operator=f"ends {op}", left=left, right=right)
                # Handle "ends after or on EXPR" = "ends on or after EXPR"
                elif self.match(TokenType.AFTER) and self.peek().type == TokenType.OR and \
                        self.peek(2).type == TokenType.IDENTIFIER and self.peek(2).value.lower() == "on":
                    self.advance(); self.advance(); self.advance()
                    precision = self._try_parse_precision_of()
                    right = self.parse_type_expression()
                    op = f"on or after {precision} of" if precision else "on or after"
                    left = BinaryExpression(operator=f"ends {op}", left=left, right=right)
                # Handle "ends within N unit of EXPR" timing operator
                elif self.match(TokenType.IDENTIFIER) and self.current().value.lower() == "within":
                    self.advance()  # consume 'within'
                    if self.match(TokenType.INTEGER, TokenType.DECIMAL):
                        quantity_value = self.advance().value
                        if self.match(TokenType.YEAR, TokenType.MONTH, TokenType.DAY,
                                      TokenType.HOUR, TokenType.MINUTE, TokenType.SECOND,
                                      TokenType.MILLISECOND, TokenType.WEEK, TokenType.YEARS,
                                      TokenType.MONTHS, TokenType.DAYS, TokenType.HOURS,
                                      TokenType.MINUTES, TokenType.SECONDS, TokenType.MILLISECONDS,
                                      TokenType.WEEKS):
                            unit = self.advance().value
                            self.expect(TokenType.OF, "Expected 'of' after unit in 'ends within N unit of'")
                            right = self.parse_type_expression()
                            left = BinaryExpression(
                                operator=f"ends within {quantity_value} {unit} of",
                                left=left,
                                right=right,
                            )
                        else:
                            right = self.parse_type_expression()
                            left = BinaryExpression(operator="ends", left=left, right=right)
                    else:
                        right = self.parse_type_expression()
                        left = BinaryExpression(operator="ends", left=left, right=right)
                else:
                    # Same pattern for ends
                    right = self._try_parse_complex_interval_comparison("ends")
                    if right is None:
                        right = self.parse_type_expression()
                    left = BinaryExpression(operator="ends", left=left, right=right)
            # On or before/after operators
            elif self.match_and_advance(TokenType.ON_OR_AFTER):
                right = self.parse_type_expression()
                left = BinaryExpression(operator="on or after", left=left, right=right)
            elif self.match_and_advance(TokenType.ON_OR_BEFORE):
                right = self.parse_type_expression()
                left = BinaryExpression(operator="on or before", left=left, right=right)
            # Properly modifier for various operators (pre-tokenized multi-word keywords)
            elif self.match_and_advance(TokenType.PROPER_INCLUDES):
                right = self.parse_type_expression()
                left = BinaryExpression(operator="properly includes", left=left, right=right)
            elif self.match_and_advance(TokenType.PROPER_CONTAINS):
                right = self.parse_type_expression()
                left = BinaryExpression(operator="properly contains", left=left, right=right)
            elif self.match_and_advance(TokenType.PROPER_IN):
                right = self.parse_type_expression()
                left = BinaryExpression(operator="properly included in", left=left, right=right)
            # Properly modifier for various operators (when properly is separate token)
            elif self.match_and_advance(TokenType.PROPERLY):
                # Handle "properly includes", "properly contains", "properly included in"
                if self.match_and_advance(TokenType.INCLUDES):
                    right = self.parse_type_expression()
                    left = BinaryExpression(operator="properly includes", left=left, right=right)
                elif self.match_and_advance(TokenType.CONTAINS):
                    right = self.parse_type_expression()
                    left = BinaryExpression(operator="properly contains", left=left, right=right)
                elif self.match_and_advance(TokenType.INCLUDED_IN):
                    right = self.parse_type_expression()
                    left = BinaryExpression(operator="properly included in", left=left, right=right)
                elif self.match_and_advance(TokenType.IN):
                    right = self.parse_type_expression()
                    left = BinaryExpression(operator="properly in", left=left, right=right)
                else:
                    # Unknown properly combination
                    break
            # Between operator (ternary): X between Y and Z
            elif self.match_and_advance(TokenType.BETWEEN):
                low = self.parse_type_expression()
                self.expect(TokenType.AND, "Expected 'and' in between expression")
                high = self.parse_type_expression()
                # Represent as a special BinaryExpression with low and high bounds
                left = BinaryExpression(operator="between", left=left, right=BinaryExpression(operator="and", left=low, right=high))
            # "occurs" is a transparent optional CQL temporal prefix — consume and re-loop
            elif self.match(TokenType.IDENTIFIER) and self.current().value.lower() == "occurs":
                self.advance()
            # "within N days/weeks/... of EXPR" timing operator
            elif self.match(TokenType.IDENTIFIER) and self.current().value.lower() == "within":
                self.advance()  # consume 'within'
                if not self.match(TokenType.INTEGER, TokenType.DECIMAL):
                    break
                quantity_value = self.advance().value
                if not self.match(TokenType.YEAR, TokenType.MONTH, TokenType.DAY,
                                  TokenType.HOUR, TokenType.MINUTE, TokenType.SECOND,
                                  TokenType.MILLISECOND, TokenType.WEEK, TokenType.YEARS,
                                  TokenType.MONTHS, TokenType.DAYS, TokenType.HOURS,
                                  TokenType.MINUTES, TokenType.SECONDS, TokenType.MILLISECONDS,
                                  TokenType.WEEKS):
                    break
                unit = self.advance().value
                self.expect(TokenType.OF, "Expected 'of' after unit in 'within N unit of'")
                right = self.parse_type_expression()
                left = BinaryExpression(
                    operator=f"within {quantity_value} {unit} of",
                    left=left,
                    right=right,
                )
            # Integer-led timing quantifier: N unit or more/less before/after [precision of] EXPR
            elif self.match(TokenType.INTEGER, TokenType.DECIMAL):
                saved_pos = self.pos
                quantity_value = self.advance().value
                if self.match(TokenType.YEAR, TokenType.MONTH, TokenType.DAY,
                              TokenType.HOUR, TokenType.MINUTE, TokenType.SECOND,
                              TokenType.MILLISECOND, TokenType.WEEK, TokenType.YEARS,
                              TokenType.MONTHS, TokenType.DAYS, TokenType.HOURS,
                              TokenType.MINUTES, TokenType.SECONDS, TokenType.MILLISECONDS,
                              TokenType.WEEKS):
                    unit = self.advance().value
                    if self.match(TokenType.OR_MORE, TokenType.OR_LESS):
                        modifier = self.advance().value
                        # Handle "before or on" = "on or before" and "after or on" = "on or after"
                        if self.match(TokenType.BEFORE) and self.peek().type == TokenType.OR and \
                                self.peek(2).type == TokenType.IDENTIFIER and self.peek(2).value.lower() == "on":
                            self.advance(); self.advance(); self.advance()
                            direction = "on or before"
                        elif self.match(TokenType.AFTER) and self.peek().type == TokenType.OR and \
                                self.peek(2).type == TokenType.IDENTIFIER and self.peek(2).value.lower() == "on":
                            self.advance(); self.advance(); self.advance()
                            direction = "on or after"
                        elif self.match(TokenType.BEFORE, TokenType.AFTER,
                                        TokenType.ON_OR_BEFORE, TokenType.ON_OR_AFTER):
                            direction = self.advance().value
                        else:
                            self.pos = saved_pos
                            break
                        precision = self._try_parse_precision_of()
                        right = self.parse_type_expression()
                        op = f"{quantity_value} {unit} {modifier} {direction}"
                        if precision:
                            op += f" {precision} of"
                        left = BinaryExpression(operator=op, left=left, right=right)
                    else:
                        self.pos = saved_pos
                        break
                else:
                    self.pos = saved_pos
                    break
            # Same as: same year as, same month as, etc.
            elif self.match(TokenType.IDENTIFIER) and self.current().value.lower() == "same":
                # Check for "same or after" or "same or before" patterns
                if self.peek().type == TokenType.OR_AFTER:
                    self.advance()  # consume 'same'
                    self.advance()  # consume 'or after'
                    precision = self._try_parse_precision_of()
                    if precision:
                        right = self.parse_type_expression()
                        left = BinaryExpression(operator=f"same or after {precision} of", left=left, right=right)
                    else:
                        right = self.parse_type_expression()
                        left = BinaryExpression(operator="same or after", left=left, right=right)
                elif self.peek().type == TokenType.OR_BEFORE:
                    self.advance()  # consume 'same'
                    self.advance()  # consume 'or before'
                    precision = self._try_parse_precision_of()
                    if precision:
                        right = self.parse_type_expression()
                        left = BinaryExpression(operator=f"same or before {precision} of", left=left, right=right)
                    else:
                        right = self.parse_type_expression()
                        left = BinaryExpression(operator="same or before", left=left, right=right)
                elif self.peek().type in (TokenType.YEAR, TokenType.MONTH, TokenType.DAY,
                                          TokenType.HOUR, TokenType.MINUTE, TokenType.SECOND,
                                          TokenType.MILLISECOND, TokenType.WEEK):
                    # Pattern: same <precision> as OR same <precision> or after/before
                    self.advance()  # consume 'same'
                    precision_token = self.advance()  # consume precision
                    precision = precision_token.value.lower()
                    # Check for "or after" or "or before" after precision
                    if self.match_and_advance(TokenType.OR_AFTER):
                        right = self.parse_type_expression()
                        left = BinaryExpression(operator=f"same {precision} or after", left=left, right=right)
                    elif self.match_and_advance(TokenType.OR_BEFORE):
                        right = self.parse_type_expression()
                        left = BinaryExpression(operator=f"same {precision} or before", left=left, right=right)
                    else:
                        self.expect(TokenType.AS, "Expected 'as'")
                        right = self.parse_type_expression()
                        left = BinaryExpression(operator=f"same {precision} as", left=left, right=right)
                else:
                    # Just "same" as identifier
                    break
            else:
                break

        return left

    def parse_type_expression(self) -> Expression:
        """Parse type expression (is, as)."""
        left = self.parse_addition_expression()

        while True:
            # Handle IS_NULL, IS_NOT_NULL, etc. as single tokens
            if self.match_and_advance(TokenType.IS_NULL):
                left = UnaryExpression(operator="is null", operand=left)
            elif self.match_and_advance(TokenType.IS_NOT_NULL):
                left = UnaryExpression(operator="is not null", operand=left)
            elif self.match_and_advance(TokenType.IS_TRUE):
                left = UnaryExpression(operator="is true", operand=left)
            elif self.match_and_advance(TokenType.IS_FALSE):
                left = UnaryExpression(operator="is false", operand=left)
            elif self.match_and_advance(TokenType.IS):
                # Check for is null, is not null, is true, is false
                if self.match_and_advance(TokenType.NULL):
                    left = UnaryExpression(operator="is null", operand=left)
                elif self.match_and_advance(TokenType.IS_NULL):
                    left = UnaryExpression(operator="is null", operand=left)
                elif self.match_and_advance(TokenType.IS_NOT_NULL):
                    left = UnaryExpression(operator="is not null", operand=left)
                elif self.match_and_advance(TokenType.TRUE):
                    left = UnaryExpression(operator="is true", operand=left)
                elif self.match_and_advance(TokenType.IS_TRUE):
                    left = UnaryExpression(operator="is true", operand=left)
                elif self.match_and_advance(TokenType.FALSE):
                    left = UnaryExpression(operator="is false", operand=left)
                elif self.match_and_advance(TokenType.IS_FALSE):
                    left = UnaryExpression(operator="is false", operand=left)
                elif self.match_and_advance(TokenType.NOT):
                    # Handle "is not null", "is not true", "is not false" when lexed as separate tokens
                    if self.match_and_advance(TokenType.NULL):
                        left = UnaryExpression(operator="is not null", operand=left)
                    elif self.match_and_advance(TokenType.TRUE):
                        left = UnaryExpression(operator="is not true", operand=left)
                    elif self.match_and_advance(TokenType.FALSE):
                        left = UnaryExpression(operator="is not false", operand=left)
                    else:
                        token = self.current()
                        raise ParseError(
                            f"Expected 'null', 'true', or 'false' after 'is not', got {token.type.name} '{token.value}'",
                            position=(token.line, token.column),
                        )
                else:
                    # Type check
                    type_spec = self.parse_type_specifier()
                    left = BinaryExpression(operator="is", left=left, right=type_spec)
            elif self.match_and_advance(TokenType.AS):
                type_spec = self.parse_type_specifier()
                left = BinaryExpression(operator="as", left=left, right=type_spec)
            else:
                break

        return left

    def parse_addition_expression(self) -> Expression:
        """Parse addition expression (+, -, |, &) and list set operators (union, intersect, except)."""
        left = self.parse_multiplication_expression()

        while True:
            if self.match_and_advance(TokenType.PLUS):
                right = self.parse_multiplication_expression()
                left = BinaryExpression(operator="+", left=left, right=right)
            elif self.match_and_advance(TokenType.MINUS):
                right = self.parse_multiplication_expression()
                left = BinaryExpression(operator="-", left=left, right=right)
            elif self.match_and_advance(TokenType.PIPE):
                right = self.parse_multiplication_expression()
                left = BinaryExpression(operator="|", left=left, right=right)
            elif self.match_and_advance(TokenType.CONCATENATE):
                right = self.parse_multiplication_expression()
                left = BinaryExpression(operator="&", left=left, right=right)
            # List set operators
            elif self.match_and_advance(TokenType.UNION):
                right = self.parse_multiplication_expression()
                left = BinaryExpression(operator="union", left=left, right=right)
            elif self.match_and_advance(TokenType.INTERSECT):
                right = self.parse_multiplication_expression()
                left = BinaryExpression(operator="intersect", left=left, right=right)
            elif self.match_and_advance(TokenType.EXCEPT):
                right = self.parse_multiplication_expression()
                left = BinaryExpression(operator="except", left=left, right=right)
            else:
                break

        return left

    def parse_multiplication_expression(self) -> Expression:
        """Parse multiplication expression (*, /, div, mod)."""
        left = self.parse_power_expression()

        while True:
            if self.match_and_advance(TokenType.MULTIPLY):
                right = self.parse_power_expression()
                left = BinaryExpression(operator="*", left=left, right=right)
            elif self.match_and_advance(TokenType.DIVIDE):
                right = self.parse_power_expression()
                left = BinaryExpression(operator="/", left=left, right=right)
            elif self.match_and_advance(TokenType.DIV):
                right = self.parse_power_expression()
                left = BinaryExpression(operator="div", left=left, right=right)
            elif self.match_and_advance(TokenType.MOD):
                right = self.parse_power_expression()
                left = BinaryExpression(operator="mod", left=left, right=right)
            else:
                break

        return left

    def parse_power_expression(self) -> Expression:
        """Parse power expression (^). Right-associative."""
        left = self.parse_unary_expression()

        if self.match_and_advance(TokenType.CARET):
            right = self.parse_power_expression()  # Right-associative: recurse
            left = BinaryExpression(operator="^", left=left, right=right)

        return left

    def parse_unary_expression(self) -> Expression:
        """Parse unary expression (not, -, exists, distinct, start of, end of, point from)."""
        if self.match_and_advance(TokenType.NOT):
            operand = self.parse_unary_expression()
            return UnaryExpression(operator="not", operand=operand)

        if self.match_and_advance(TokenType.MINUS):
            operand = self.parse_unary_expression()
            return UnaryExpression(operator="-", operand=operand)

        # Unary plus - just return the operand (no-op)
        if self.match_and_advance(TokenType.PLUS):
            return self.parse_unary_expression()

        # Cast expression: cast X as Type
        if self.match_and_advance(TokenType.CAST):
            operand = self.parse_unary_expression()
            self.expect(TokenType.AS, "Expected 'as' after cast expression")
            target_type = self.parse_type_specifier()
            return BinaryExpression(operator="as", left=operand, right=target_type)

        # Convert expression: convert X to Type
        if self.match_and_advance(TokenType.CONVERT):
            operand = self.parse_unary_expression()
            # Expect 'to' keyword
            self.expect(TokenType.TO, "Expected 'to' after convert expression")
            target_type = self.parse_type_specifier()
            return BinaryExpression(operator="convert", left=operand, right=target_type)

        if self.match_and_advance(TokenType.EXISTS):
            operand = self.parse_unary_expression()
            return ExistsExpression(source=operand)

        if self.match_and_advance(TokenType.DISTINCT) or self.match_and_advance(TokenType.DISTINCT_FN):
            operand = self.parse_unary_expression()
            return DistinctExpression(source=operand)

        # Interval operators: start of, end of, point from
        if self.match(TokenType.START):
            if self.peek().type == TokenType.OF:
                self.advance()  # consume START
                self.advance()  # consume OF
                operand = self.parse_unary_expression()
                return UnaryExpression(operator="start of", operand=operand)

        if self.match(TokenType.END):
            # Check if this is "end of" (interval operator) or just "end" (case expression keyword)
            # Look ahead to see if "of" follows
            if self.peek().type == TokenType.OF:
                self.advance()  # consume END
                self.advance()  # consume OF
                operand = self.parse_unary_expression()
                return UnaryExpression(operator="end of", operand=operand)

        if self.match_and_advance(TokenType.POINT):
            self.expect(TokenType.FROM, "Expected 'from' after 'point'")
            operand = self.parse_unary_expression()
            return UnaryExpression(operator="point from", operand=operand)

        # Width of operator
        if self.match_and_advance(TokenType.WIDTH):
            self.expect(TokenType.OF, "Expected 'of' after 'width'")
            operand = self.parse_unary_expression()
            return UnaryExpression(operator="width of", operand=operand)

        # Singleton from operator
        if self.match_and_advance(TokenType.SINGLETON_FROM):
            operand = self.parse_unary_expression()
            return UnaryExpression(operator="singleton from", operand=operand)

        # Predecessor of operator
        if self.match_and_advance(TokenType.PREDECESSOR):
            self.expect(TokenType.OF, "Expected 'of' after 'predecessor'")
            operand = self.parse_unary_expression()
            return UnaryExpression(operator="predecessor of", operand=operand)

        # Successor of operator
        if self.match_and_advance(TokenType.SUCCESSOR):
            self.expect(TokenType.OF, "Expected 'of' after 'successor'")
            operand = self.parse_unary_expression()
            return UnaryExpression(operator="successor of", operand=operand)

        # Minimum and Maximum value selectors (e.g., minimum Integer, maximum Decimal)
        if self.match_and_advance(TokenType.MINIMUM):
            type_name = self._parse_identifier_name()
            return FunctionRef(name="minimum", arguments=[Identifier(name=type_name)])

        if self.match_and_advance(TokenType.MAXIMUM):
            type_name = self._parse_identifier_name()
            return FunctionRef(name="maximum", arguments=[Identifier(name=type_name)])

        return self.parse_postfix_expression()

    def parse_postfix_expression(self) -> Expression:
        """Parse postfix expression (., [], (), and query clauses)."""
        expr = self.parse_primary_expression()

        while True:
            if self.match_and_advance(TokenType.DOT):
                name = self._parse_identifier_name()

                # Check if this is a method call (followed by parentheses)
                if self.match_and_advance(TokenType.LPAREN):
                    # Method invocation
                    args = []
                    if not self.check(TokenType.RPAREN):
                        args.append(self.parse_expression())
                        while self.match_and_advance(TokenType.COMMA):
                            args.append(self.parse_expression())
                    self.expect(TokenType.RPAREN, "Expected ')' after method arguments")
                    expr = MethodInvocation(source=expr, method=name, arguments=args)
                else:
                    # Property access
                    expr = Property(source=expr, path=name)
                # Check if this is followed by { for type constructor (e.g., System.ValueSet{...})
                if self.match(TokenType.LBRACE):
                    self.advance()  # consume {
                    elements = []
                    while not self.match(TokenType.RBRACE):
                        name = self._parse_identifier_name()
                        self.expect(TokenType.COLON, "Expected ':'")
                        value = self.parse_expression()
                        elements.append(TupleElement(name=name, type=value))
                        if not self.match_and_advance(TokenType.COMMA):
                            break
                    self.expect(TokenType.RBRACE, "Expected '}'")
                    # Build the type name from the property chain
                    type_name = self._build_qualified_name_from_property(expr)
                    expr = InstanceExpression(type=type_name, elements=elements)
            elif self.match_and_advance(TokenType.LBRACKET):
                # Indexer
                index = self.parse_expression()
                self.expect(TokenType.RBRACKET, "Expected ']' after index")
                expr = IndexerExpression(source=expr, index=index)
            elif self.match(TokenType.LPAREN) and isinstance(expr, (Identifier, QualifiedIdentifier, Property)):
                # Function call (including method calls on properties)
                expr = self._parse_function_call(expr)
            elif self.match(TokenType.IDENTIFIER, TokenType.QUOTED_IDENTIFIER,
                           TokenType.LOCATION, TokenType.PATIENT, TokenType.PRACTITIONER,
                           TokenType.ORGANIZATION, TokenType.RESOURCE, TokenType.BUNDLE):
                # Check if this is a query with alias (e.g., [Encounter] E where ...)
                # or ({1,2,3}) X sort asc
                # or (Query1) Alias1 union (Query2) ...
                # Also allow FHIR resource type keywords as aliases (e.g., "location Location where")
                # Look ahead to see if there's a query keyword after the identifier
                next_token = self.peek()
                if next_token.type in (TokenType.WHERE, TokenType.RETURN, TokenType.SORT,
                                       TokenType.WITH, TokenType.WITHOUT, TokenType.LET,
                                       TokenType.EOF, TokenType.DEFINE, TokenType.RPAREN,
                                       TokenType.AGGREGATE, TokenType.COMMA, TokenType.RBRACKET, TokenType.RBRACE,
                                       TokenType.UNION, TokenType.INTERSECT, TokenType.EXCEPT):
                    # This is a query with an alias
                    alias = self._parse_identifier_name()
                    source = QuerySource(alias=alias, expression=expr)
                    query = Query(source=source)

                    # Parse query clauses
                    while True:
                        if self.match(TokenType.WHERE) and query.where is None:
                            query.where = self.parse_where_clause()
                        elif self.match(TokenType.RETURN) and query.return_clause is None:
                            query.return_clause = self.parse_return_clause()
                        elif self.match(TokenType.SORT) and query.sort is None:
                            query.sort = self.parse_sort_clause()
                        elif self.match(TokenType.WITH, TokenType.WITHOUT):
                            query.with_clauses.append(self.parse_with_clause())
                        elif self.match(TokenType.LET):
                            query.let_clauses.extend(self.parse_let_clause())
                        elif self.match(TokenType.AGGREGATE) and query.aggregate is None:
                            query.aggregate = self.parse_aggregate_clause()
                        else:
                            break

                    expr = query
                else:
                    break
            # Check for query operators (skip, take, first, last, any, all, singleton from, distinct)
            elif self.match(TokenType.SKIP):
                expr = self._parse_skip_expression(expr)
            elif self.match(TokenType.TAKE):
                expr = self._parse_take_expression(expr)
            elif self.match(TokenType.FIRST):
                expr = self._parse_first_expression(expr)
            elif self.match(TokenType.LAST):
                expr = self._parse_last_expression(expr)
            elif self.match(TokenType.ANY):
                expr = self._parse_any_expression(expr)
            elif self.match(TokenType.ALL):
                expr = self._parse_all_expression(expr)
            elif self.match(TokenType.SINGLETON_FROM):
                expr = self._parse_singleton_expression(expr)
            elif self.match(TokenType.DISTINCT, TokenType.DISTINCT_FN):
                expr = self._parse_distinct_expression(expr)
            else:
                break

        return expr

    # =========================================================================
    # Primary Expression Parsing
    # =========================================================================

    def parse_primary_expression(self) -> Expression:
        """Parse primary expression (literals, identifiers, groupings)."""
        token = self.current()

        # Component extraction: year from X (check before duration between)
        # Only singular forms can be component extraction
        if self.match(TokenType.YEAR, TokenType.MONTH, TokenType.DAY,
                      TokenType.HOUR, TokenType.MINUTE, TokenType.SECOND, TokenType.MILLISECOND):
            # Check if followed by 'from'
            if self.peek().type == TokenType.FROM:
                return self._parse_component_extraction()

        # timezoneoffset from X — CQL §18.12 component extraction
        if self.match(TokenType.TIMEZONE_FROM):
            if self.peek().type == TokenType.FROM:
                return self._parse_component_extraction()

        # Duration between: years between X and Y (singular or plural + BETWEEN)
        # But NOT "month of" or "year of" which are precision specifiers for temporal operators
        if self.match(TokenType.YEAR, TokenType.YEARS, TokenType.MONTH, TokenType.MONTHS,
                      TokenType.WEEK, TokenType.WEEKS, TokenType.DAY, TokenType.DAYS,
                      TokenType.HOUR, TokenType.HOURS, TokenType.MINUTE, TokenType.MINUTES,
                      TokenType.SECOND, TokenType.SECONDS, TokenType.MILLISECOND, TokenType.MILLISECONDS):
            # Check if followed by 'between' (duration between) - only then parse as duration
            next_token = self.peek()
            if next_token.type == TokenType.BETWEEN:
                return self._parse_duration_between()
            # Check if followed by 'of' (precision specifier for temporal comparisons)
            if next_token.type == TokenType.OF:
                return self._parse_precision_of()
            # Otherwise fall through - it might be a quantity

        # Difference between: difference in years between X and Y
        if self.match(TokenType.IDENTIFIER) and token.value.lower() == "difference":
            return self._parse_difference_between()

        # Literals
        if self.match(TokenType.INTEGER, TokenType.LONG, TokenType.DECIMAL):
            return self.parse_literal()

        if self.match(TokenType.STRING):
            return self.parse_literal()

        if self.match(TokenType.TRUE, TokenType.FALSE, TokenType.NULL):
            return self.parse_literal()

        if self.match(TokenType.DATE, TokenType.DATETIME):
            return self.parse_datetime_literal()

        if self.match(TokenType.TIME):
            return self.parse_time_literal()

        # Code selector: Code '73211009' from "SNOMED-CT" [display 'text']
        if self.match(TokenType.CODE_TYPE):
            next_type = self.peek().type
            if next_type == TokenType.STRING:
                return self.parse_code_selector()

        # Interval literal: only if followed by a bracket/paren delimiter
        if self.match(TokenType.INTERVAL):
            next_type = self.peek().type
            if next_type in (TokenType.LBRACKET, TokenType.LPAREN,
                             TokenType.OPEN, TokenType.CLOSED,
                             TokenType.OPEN_CLOSED, TokenType.CLOSED_OPEN):
                return self.parse_interval()

        # List literal
        if self.match(TokenType.LBRACE):
            return self._parse_brace_expression()

        # Retrieve expression
        if self.match(TokenType.LBRACKET):
            return self.parse_retrieve()

        # Query with 'from' keyword
        if self.match(TokenType.FROM):
            return self.parse_from_query()

        # Tuple/Instance expression
        if self.match(TokenType.TUPLE):
            return self.parse_tuple_expression()

        # Case expression
        if self.match(TokenType.CASE):
            return self.parse_case_expression()

        # Conditional expression (if)
        if self.match(TokenType.IFF):
            return self.parse_conditional_expression()

        # Parenthesized expression or tuple type
        if self.match(TokenType.LPAREN):
            return self._parse_parenthesized_or_tuple()

        # Type constructor
        if self._is_type_constructor():
            return self._parse_type_constructor()

        # Identifier (variable, function, or qualified identifier)
        # Also accept keywords that can be used as identifiers
        if self.match(TokenType.IDENTIFIER, TokenType.QUOTED_IDENTIFIER,
                      TokenType.PATIENT, TokenType.PRACTITIONER, TokenType.ORGANIZATION,
                      TokenType.LOCATION, TokenType.RESOURCE, TokenType.BUNDLE,
                      TokenType.COUNT, TokenType.SUM, TokenType.MIN, TokenType.MAX,
                      TokenType.AVG, TokenType.MEDIAN, TokenType.MODE, TokenType.LENGTH,
                      TokenType.UPPER, TokenType.LOWER, TokenType.CONCATENATE,
                      TokenType.COMBINE, TokenType.SPLIT, TokenType.POSITION_OF,
                      TokenType.SUBSTRING, TokenType.STARTS_WITH, TokenType.ENDS_WITH,
                      TokenType.MATCHES, TokenType.REPLACE_MATCHES, TokenType.REPLACE,
                      TokenType.COALESCE, TokenType.IFF, TokenType.CASE, TokenType.WHEN,
                      TokenType.THEN, TokenType.ELSE, TokenType.END, TokenType.TO_BOOLEAN,
                      TokenType.TO_CONCEPT, TokenType.TO_DATE, TokenType.TO_DATETIME,
                      TokenType.TO_DECIMAL, TokenType.TO_INTEGER, TokenType.TO_QUANTITY,
                      TokenType.TO_STRING, TokenType.TO_TIME, TokenType.TO_CODE,
                      TokenType.TO_CHARS, TokenType.FROM_CHARS, TokenType.FIRST,
                      TokenType.LAST, TokenType.INDEXER, TokenType.FLATTEN,
                      TokenType.DISTINCT_FN, TokenType.CURRENT, TokenType.CHILDREN,
                      TokenType.DESCENDENTS, TokenType.ENCODE, TokenType.ESCAPE,
                      TokenType.PREVIOUS, TokenType.PREDECESSOR, TokenType.SUCCESSOR, TokenType.SINGLE,
                      TokenType.SELECT, TokenType.FOR, TokenType.OF, TokenType.REPEAT,
                      TokenType.INTERSECT, TokenType.EXCEPT, TokenType.UNION,
                      TokenType.EXPAND, TokenType.ROUND, TokenType.ABS, TokenType.CEILING,
                      TokenType.FLOOR, TokenType.LN, TokenType.LOG, TokenType.POWER,
                      TokenType.TRUNCATE, TokenType.EXP, TokenType.SQRT, TokenType.DIV,
                      TokenType.MOD, TokenType.REMAINDER, TokenType.WIDTH, TokenType.SIZE,
                      TokenType.POINT_FROM, TokenType.LOWBOUNDARY, TokenType.HIGHBOUNDARY,
                      TokenType.PRECISION, TokenType.MINIMUM, TokenType.MAXIMUM,
                      TokenType.BOOLEAN, TokenType.INTEGER_TYPE, TokenType.LONG_TYPE,
                      TokenType.DECIMAL_TYPE, TokenType.STRING_TYPE, TokenType.DATE_TYPE,
                      TokenType.DATETIME_TYPE, TokenType.TIME_TYPE, TokenType.QUANTITY,
                      TokenType.RATIO, TokenType.INTERVAL, TokenType.LIST_TYPE,
                      TokenType.TUPLE, TokenType.CHOICE, TokenType.ANY, TokenType.CODE_TYPE,
                      TokenType.CONCEPT_TYPE, TokenType.CODESYSTEM_TYPE, TokenType.VALUESET_TYPE,
                      TokenType.ALL_TRUE, TokenType.ANY_TRUE, TokenType.VARIANCE, TokenType.STDDEV,
                      TokenType.SKIP, TokenType.TAKE,
                      TokenType.VERSION, TokenType.DISPLAY, TokenType.CALLED,
                      TokenType.CODE, TokenType.CONCEPT, TokenType.VALUESYSTEM,
                      TokenType.START, TokenType.STARTING):
            return self._parse_identifier_or_function()

        # Quantified expression keywords
        if self.match(TokenType.COUNT, TokenType.SUM, TokenType.MIN, TokenType.MAX,
                      TokenType.AVG, TokenType.MEDIAN, TokenType.MODE):
            return self._parse_aggregate_expression()

        # Temporal operators
        if self.match(TokenType.AFTER, TokenType.BEFORE, TokenType.DURING,
                      TokenType.INCLUDES, TokenType.INCLUDED_IN, TokenType.OVERLAPS,
                      TokenType.MEETS, TokenType.STARTS, TokenType.ENDS,
                      TokenType.MEETS_BEFORE, TokenType.MEETS_AFTER,
                      TokenType.OVERLAPS_BEFORE, TokenType.OVERLAPS_AFTER,
                      TokenType.ON_OR_BEFORE, TokenType.ON_OR_AFTER):
            return self._parse_temporal_expression()

        # Date/Time component extraction: date from X, time from X
        if self.match(TokenType.DATE_FROM, TokenType.TIME_FROM):
            return self._parse_date_component_extraction()

        # $this - special CQL keyword for current item in iteration context
        if self.match(TokenType.DOLLAR):
            self.advance()  # consume $
            nxt = self.current()
            if nxt.type == TokenType.IDENTIFIER and nxt.value.lower() == 'this':
                self.advance()  # consume 'this'
                return Identifier(name='$this')
            raise ParseError(
                f"Expected 'this' after '$', got {nxt.type.name} '{nxt.value}'",
                position=(nxt.line, nxt.column),
            )

        # Error
        raise ParseError(
            f"Unexpected token in expression: {token.type.name} '{token.value}'",
            position=(token.line, token.column),
        )

    def _parse_date_component_extraction(self) -> FunctionRef:
        """Parse date/time component extraction: date from X, time from X.

        Also handles date()/time() function calls when 'from' is not present.
        """
        token = self.advance()  # consume DATE_FROM or TIME_FROM

        # Determine the component name
        if token.type == TokenType.DATE_FROM:
            component_name = "date"
        else:  # TIME_FROM
            component_name = "time"

        # Check if this is 'date from X' or just 'date()' function call
        if self.match_and_advance(TokenType.FROM):
            # It's component extraction: date from X
            # Per CQL grammar, 'date from' takes an expressionTerm (not a full
            # expression), so parse at the type-expression level to avoid
            # absorbing comparison and boolean operators.
            source = self.parse_type_expression()
            return FunctionRef(
                name=component_name,
                arguments=[source],
            )
        else:
            # It's a function call: date() or date(arg)
            # Parse as a regular function call
            return self._parse_function_call(Identifier(name=component_name))

    def parse_literal(self) -> Union[Literal, Quantity]:
        """Parse a literal value, potentially with a temporal unit or UCUM unit."""
        token = self.advance()

        if token.type == TokenType.INTEGER:
            value = int(token.value)
            # Check for temporal unit (e.g., 5 years, 10 days)
            if self.match(TokenType.YEAR, TokenType.YEARS, TokenType.MONTH, TokenType.MONTHS,
                          TokenType.WEEK, TokenType.WEEKS, TokenType.DAY, TokenType.DAYS,
                          TokenType.HOUR, TokenType.HOURS, TokenType.MINUTE, TokenType.MINUTES,
                          TokenType.SECOND, TokenType.SECONDS, TokenType.MILLISECOND, TokenType.MILLISECONDS):
                unit_token = self.advance()
                # Normalize to singular form
                unit = unit_token.value.lower().rstrip('s')
                return Quantity(value=float(value), unit=unit)
            # Check for UCUM unit string (e.g., 1 'ml', 10 'cm', 19.99 '[lb_av]')
            if self.match(TokenType.STRING):
                unit_token = self.advance()
                unit = unit_token.value
                return Quantity(value=float(value), unit=unit)
            return Literal(value=value, type="Integer")
        elif token.type == TokenType.LONG:
            value = int(token.value)
            return Literal(value=value, type="Long")
        elif token.type == TokenType.DECIMAL:
            value = float(token.value)
            # Check for temporal unit (e.g., 3.5 hours)
            if self.match(TokenType.YEAR, TokenType.YEARS, TokenType.MONTH, TokenType.MONTHS,
                          TokenType.WEEK, TokenType.WEEKS, TokenType.DAY, TokenType.DAYS,
                          TokenType.HOUR, TokenType.HOURS, TokenType.MINUTE, TokenType.MINUTES,
                          TokenType.SECOND, TokenType.SECONDS, TokenType.MILLISECOND, TokenType.MILLISECONDS):
                unit_token = self.advance()
                unit = unit_token.value.lower().rstrip('s')
                return Quantity(value=value, unit=unit)
            # Check for UCUM unit string (e.g., 1.5 'ml', 19.99 '[lb_av]')
            if self.match(TokenType.STRING):
                unit_token = self.advance()
                unit = unit_token.value
                return Quantity(value=value, unit=unit)
            # CQL §2.3: standalone Decimal has max 28 integer digits and 8 fractional digits.
            # Validation only applies to Decimal literals, not Quantity values.
            raw_decimal = token.value.lstrip('+').lstrip('-')
            if '.' in raw_decimal:
                int_part, frac_part = raw_decimal.split('.', 1)
                if len(frac_part) > 8:
                    raise ValueError(
                        f"Decimal literal '{token.value}' exceeds maximum 8 fractional digits "
                        f"(CQL §2.3)"
                    )
                int_digits = int_part.lstrip('0') or '0'
                if len(int_digits) > 28:
                    raise ValueError(
                        f"Decimal literal '{token.value}' exceeds maximum 28 integer digits "
                        f"(CQL §2.3)"
                    )
            return Literal(value=value, type="Decimal", raw_str=token.value)
        elif token.type == TokenType.STRING:
            return Literal(value=token.value, type="String")
        elif token.type == TokenType.TRUE:
            return Literal(value=True, type="Boolean")
        elif token.type == TokenType.FALSE:
            return Literal(value=False, type="Boolean")
        elif token.type == TokenType.NULL:
            return Literal(value=None, type=None)
        else:
            raise ParseError(f"Unexpected literal type: {token.type}")

    def parse_datetime_literal(self) -> DateTimeLiteral:
        """Parse a date/time literal."""
        token = self.advance()
        return DateTimeLiteral(value=token.value)

    def parse_time_literal(self) -> TimeLiteral:
        """Parse a time literal."""
        token = self.advance()
        return TimeLiteral(value=token.value)

    def parse_code_selector(self) -> "CodeSelector":
        """Parse a Code selector expression.

        Grammar: 'Code' STRING 'from' (identifier) ('display' STRING)?

        Examples:
            Code '73211009' from "SNOMED-CT"
            Code '73211009' from "SNOMED-CT" display 'Diabetes'
        """
        from .ast_nodes import CodeSelector

        self.expect(TokenType.CODE_TYPE, "Expected 'Code'")

        code_token = self.expect(TokenType.STRING, "Expected code value string after 'Code'")
        code_value = code_token.value

        self.expect(TokenType.FROM, "Expected 'from' after code value")
        system_name = self._parse_identifier_name()

        display = None
        if self.match_and_advance(TokenType.DISPLAY):
            display_token = self.expect(TokenType.STRING, "Expected display string after 'display'")
            display = display_token.value

        return CodeSelector(code=code_value, system=system_name, display=display)

    def parse_interval(self) -> Interval:
        """Parse an interval expression."""
        self.expect(TokenType.INTERVAL, "Expected 'Interval'")

        # Determine open/closed bounds
        low_closed = True
        high_closed = True

        if self.match(TokenType.OPEN):
            self.advance()
            low_closed = False
        elif self.match(TokenType.CLOSED):
            self.advance()
            low_closed = True
        elif self.match(TokenType.OPEN_CLOSED):
            self.advance()
            low_closed = False
            high_closed = True
        elif self.match(TokenType.CLOSED_OPEN):
            self.advance()
            low_closed = True
            high_closed = False

        # Parse the bounds
        if self.match(TokenType.LBRACKET):
            self.advance()
        elif self.match(TokenType.LPAREN):
            self.advance()
            low_closed = False
        else:
            self.expect(TokenType.LBRACKET, "Expected '[' or '(' for interval")

        low = self.parse_expression()
        self.expect(TokenType.COMMA, "Expected ',' in interval")
        high = self.parse_expression()

        if self.match(TokenType.RBRACKET):
            self.advance()
            high_closed = True
        elif self.match(TokenType.RPAREN):
            self.advance()
            high_closed = False
        else:
            self.expect(TokenType.RBRACKET, "Expected ']' or ')' for interval")

        return Interval(low=low, high=high, low_closed=low_closed, high_closed=high_closed)

    def _parse_brace_expression(self) -> Expression:
        """Parse a brace expression: either a list literal or anonymous tuple selector.

        Distinguishes between:
        - List literal: { expr, expr, ... }
        - Tuple selector: { identifier: expr, identifier: expr, ... }
        """
        # Save position to peek inside
        save_pos = self.pos
        # Consume the LBRACE
        self.advance()

        # Check if this is empty braces (empty list)
        if self.match(TokenType.RBRACE):
            self.pos = save_pos
            return self.parse_list_literal()

        # Check if first element is identifier-like followed by colon (tuple selector)
        is_tuple = False
        inner_save = self.pos
        try:
            self._parse_identifier_name()
            if self.match(TokenType.COLON):
                is_tuple = True
        except Exception as e:
            _logger.debug("Lookahead for tuple selector failed: %s", e)
        self.pos = inner_save

        # Restore to before LBRACE
        self.pos = save_pos

        if is_tuple:
            return self._parse_anonymous_tuple()
        else:
            return self.parse_list_literal()

    def _parse_anonymous_tuple(self) -> TupleExpression:
        """Parse an anonymous tuple selector: { name: expr, ... }."""
        self.expect(TokenType.LBRACE, "Expected '{'")
        elements = []

        while not self.match(TokenType.RBRACE):
            name = self._parse_identifier_name()
            self.expect(TokenType.COLON, "Expected ':'")
            value = self.parse_expression()
            elements.append(TupleElement(name=name, type=value))

            if not self.match_and_advance(TokenType.COMMA):
                break

        self.expect(TokenType.RBRACE, "Expected '}'")
        return TupleExpression(elements=elements)

    def parse_list_literal(self) -> ListExpression:
        """Parse a list literal expression."""
        self.expect(TokenType.LBRACE, "Expected '{'")
        elements = []

        if not self.match(TokenType.RBRACE):
            elements.append(self.parse_expression())
            while self.match_and_advance(TokenType.COMMA):
                if self.match(TokenType.RBRACE):
                    break
                elements.append(self.parse_expression())

        self.expect(TokenType.RBRACE, "Expected '}'")
        return ListExpression(elements=elements)

    def parse_retrieve(self) -> Retrieve:
        """Parse a retrieve expression ([Type], [Type: "code"], [Type -> prop])."""
        self.expect(TokenType.LBRACKET, "Expected '['")

        # Parse the resource type
        resource_type = self._parse_identifier_name()
        # Handle model-qualified retrieve type: QICore.Procedure, FHIR.Claim, etc.
        # Discard the model qualifier and keep only the local type name.
        if self.match(TokenType.DOT):
            self.advance()  # consume DOT
            resource_type = self._parse_identifier_name()

        terminology = None
        terminology_property = None
        navigation_path = None

        # Check for navigation (->) for related context retrieve
        if self.match_and_advance(TokenType.ARROW):
            navigation_path = self._parse_identifier_name()
        # Check for terminology filter
        elif self.match_and_advance(TokenType.COLON):
            # Optional property specification
            if self.match(TokenType.IDENTIFIER, TokenType.QUOTED_IDENTIFIER):
                # Check if this is a property name or the start of terminology
                if self.peek().type == TokenType.COLON:
                    terminology_property = self._parse_identifier_name()
                    self.expect(TokenType.COLON, "Expected ':' after property name")

            terminology = self.parse_expression()

        self.expect(TokenType.RBRACKET, "Expected ']'")
        return Retrieve(type=resource_type, terminology=terminology, terminology_property=terminology_property, navigation_path=navigation_path)

    def parse_tuple_expression(self) -> TupleExpression:
        """Parse a tuple literal expression."""
        self.expect(TokenType.TUPLE, "Expected 'Tuple'")
        self.expect(TokenType.LBRACE, "Expected '{'")

        elements = []
        while not self.match(TokenType.RBRACE):
            name = self._parse_identifier_name()
            self.expect(TokenType.COLON, "Expected ':'")
            value = self.parse_expression()
            elements.append(TupleElement(name=name, type=value))  # Using type field to store value temporarily

            if not self.match_and_advance(TokenType.COMMA):
                break

        self.expect(TokenType.RBRACE, "Expected '}'")
        return TupleExpression(elements=elements)

    def parse_case_expression(self) -> CaseExpression:
        """Parse a case expression."""
        self.expect(TokenType.CASE, "Expected 'case'")

        comparand = None
        case_items = []
        else_expr = None

        # Check for simple case (case X when ...)
        if not self.match(TokenType.WHEN):
            comparand = self.parse_expression()

        # Parse when clauses
        while self.match_and_advance(TokenType.WHEN):
            when_expr = self.parse_expression()
            self.expect(TokenType.THEN, "Expected 'then'")
            then_expr = self.parse_expression()
            case_items.append(CaseItem(when=when_expr, then=then_expr))

        # Parse else clause
        if self.match_and_advance(TokenType.ELSE):
            else_expr = self.parse_expression()

        self.expect(TokenType.END, "Expected 'end'")

        return CaseExpression(case_items=case_items, else_expr=else_expr, comparand=comparand)

    def parse_conditional_expression(self) -> ConditionalExpression:
        """Parse a conditional (if-then-else) expression."""
        self.expect(TokenType.IFF, "Expected 'if'")
        condition = self.parse_expression()
        self.expect(TokenType.THEN, "Expected 'then'")
        then_expr = self.parse_expression()
        self.expect(TokenType.ELSE, "Expected 'else'")
        else_expr = self.parse_expression()

        return ConditionalExpression(
            condition=condition,
            then_expr=then_expr,
            else_expr=else_expr,
        )

    def _parse_parenthesized_or_tuple(self) -> Expression:
        """Parse a parenthesized expression or tuple."""
        self.expect(TokenType.LPAREN, "Expected '('")
        expr = self.parse_expression()

        if self.match_and_advance(TokenType.COMMA):
            # This is a tuple
            elements = [expr]
            while True:
                elements.append(self.parse_expression())
                if not self.match_and_advance(TokenType.COMMA):
                    break
            self.expect(TokenType.RPAREN, "Expected ')'")
            # Convert to tuple - this is a simplification
            return ListExpression(elements=elements)

        self.expect(TokenType.RPAREN, "Expected ')'")
        return expr

    def _parse_duration_between(self) -> DurationBetween:
        """Parse a duration between expression: years between X and Y."""
        precision_token = self.advance()
        precision = precision_token.value.lower().rstrip('s')

        self.expect(TokenType.BETWEEN, "Expected 'between'")
        left = self.parse_implies_expression()
        self.expect(TokenType.AND, "Expected 'and'")
        right = self.parse_implies_expression()

        return DurationBetween(precision=precision, operand_left=left, operand_right=right)

    def _parse_difference_between(self) -> DifferenceBetween:
        """Parse a difference between expression: difference in years between X and Y."""
        self.expect(TokenType.IDENTIFIER, "Expected 'difference'")
        self.expect(TokenType.IN, "Expected 'in'")

        precision_token = self.advance()
        precision = precision_token.value.lower().rstrip('s')

        self.expect(TokenType.BETWEEN, "Expected 'between'")
        left = self.parse_implies_expression()
        self.expect(TokenType.AND, "Expected 'and'")
        right = self.parse_implies_expression()

        return DifferenceBetween(precision=precision, operand_left=left, operand_right=right)

    def _parse_component_extraction(self) -> DateComponent:
        """Parse a date component extraction: year from X."""
        component_token = self.advance()
        component = component_token.value.lower()

        # Skip 'from'
        self.expect(TokenType.FROM, "Expected 'from'")
        # Parse operand without type operators (is/as) so they apply to the whole expression
        operand = self.parse_addition_expression()

        return DateComponent(component=component, operand=operand)

    def _try_parse_precision_of(self) -> Optional[str]:
        """
        Try to parse a precision specifier like 'year of', 'month of', etc.
        Returns the precision string if found, None otherwise.
        Does not consume any tokens if the pattern doesn't match.
        """
        # Check if current token is a precision unit followed by 'of'
        if self.match(TokenType.YEAR, TokenType.MONTH, TokenType.DAY,
                      TokenType.HOUR, TokenType.MINUTE, TokenType.SECOND, TokenType.MILLISECOND,
                      TokenType.WEEK):
            # Look ahead for 'of'
            if self.peek().type == TokenType.OF:
                precision_token = self.advance()  # consume precision
                self.advance()  # consume 'of'
                return precision_token.value.lower()
        return None

    def _try_parse_complex_interval_comparison(self, operator_name: str) -> Optional[Expression]:
        """
        Try to parse complex temporal comparison patterns for starts/ends operators.

        Patterns:
        - <quantity> or less/or more on or after/on or before <precision> of start of/end of <expr>
        - more than/less than <quantity> before/after [precision of] [start of/end of] <expr>

        Example: starts 1 day or less on or after day of start of Interval[...]
        Example: starts more than 1 hour before start of X

        Returns the parsed expression if the pattern matches, None otherwise.
        """
        saved_pos = self.pos

        # Handle "more than N unit" / "less than N unit" prefix (e.g. "starts more than 1 hour before")
        more_less_prefix = None
        if self.match(TokenType.IDENTIFIER) and self.current().value.lower() in ("more", "less"):
            if self.peek().type == TokenType.IDENTIFIER and self.peek().value.lower() == "than":
                more_less_prefix = self.current().value.lower()  # "more" or "less"
                self.advance()  # consume 'more'/'less'
                self.advance()  # consume 'than'

        # Check if we have a quantity (number followed by time unit)
        if not self.match(TokenType.INTEGER, TokenType.DECIMAL):
            self.pos = saved_pos
            return None

        # Peek ahead to see if this is the complex pattern
        # We need: <number> <unit> or less/or more on or after/on or before
        # Parse quantity
        quantity_value = self.current().value
        self.advance()

        # Check for time unit
        if not self.match(TokenType.YEAR, TokenType.MONTH, TokenType.DAY,
                          TokenType.HOUR, TokenType.MINUTE, TokenType.SECOND, TokenType.MILLISECOND,
                          TokenType.WEEK, TokenType.YEARS, TokenType.MONTHS, TokenType.DAYS,
                          TokenType.HOURS, TokenType.MINUTES, TokenType.SECONDS, TokenType.MILLISECONDS,
                          TokenType.WEEKS):
            # Not a quantity, restore position
            self.pos = saved_pos
            return None

        unit = self.current().value
        self.advance()

        # Determine modifier: either from the "more/less than" prefix or from "or more/or less" token
        if more_less_prefix is not None:
            modifier = "or more" if more_less_prefix == "more" else "or less"
        else:
            # Check for 'or less' or 'or more'
            if not self.match(TokenType.OR_LESS, TokenType.OR_MORE):
                # Not the complex pattern, restore position
                self.pos = saved_pos
                return None
            modifier = self.current().value  # "or less" or "or more"
            self.advance()

        # Check for 'on or after', 'on or before', bare 'before'/'after',
        # or compound 'before or on' / 'after or on' (equivalent to 'on or before' / 'on or after')
        if self.match(TokenType.BEFORE) and self.peek().type == TokenType.OR and \
                self.peek(2).type == TokenType.IDENTIFIER and self.peek(2).value.lower() == "on":
            self.advance()  # consume 'before'
            self.advance()  # consume 'or'
            self.advance()  # consume 'on'
            direction = "on or before"
        elif self.match(TokenType.AFTER) and self.peek().type == TokenType.OR and \
                self.peek(2).type == TokenType.IDENTIFIER and self.peek(2).value.lower() == "on":
            self.advance()  # consume 'after'
            self.advance()  # consume 'or'
            self.advance()  # consume 'on'
            direction = "on or after"
        elif self.match(TokenType.ON_OR_AFTER, TokenType.ON_OR_BEFORE,
                        TokenType.BEFORE, TokenType.AFTER):
            direction = self.current().value
            self.advance()
        else:
            # Not the complex pattern, restore position
            self.pos = saved_pos
            return None

        # Check for precision specifier (e.g., "day of", "month of")
        precision = self._try_parse_precision_of()

        # Check for 'start of' or 'end of'
        inner_operator = None
        if self.match(TokenType.START):
            self.advance()
            if self.match(TokenType.OF):
                self.advance()
                inner_operator = "start of"
        elif self.match(TokenType.END):
            self.advance()
            if self.match(TokenType.OF):
                self.advance()
                inner_operator = "end of"

        # Parse the operand (the interval or expression)
        operand = self.parse_type_expression()

        # Wrap in inner operator if present (start of / end of)
        if inner_operator:
            operand = UnaryExpression(operator=inner_operator, operand=operand)

        # Build the complex expression
        # The operator encodes all the components: "starts 1 day or less on or after day of"
        operator_parts = [operator_name, f"{quantity_value} {unit}", modifier, direction]
        if precision:
            operator_parts.append(f"{precision} of")

        full_operator = " ".join(operator_parts)

        # Return a special BinaryExpression with metadata about the comparison
        # Store quantity info in a wrapper
        return BinaryExpression(
            operator=full_operator,
            left=Quantity(value=float(quantity_value), unit=unit),
            right=operand
        )

    def _parse_precision_of(self) -> Expression:
        """
        Parse a precision specifier expression: month of X, year of X, etc.
        Used in temporal comparisons like 'on or after month of @2012-11-15'.
        Returns a BinaryExpression with operator 'precision_of'.
        """
        precision_token = self.advance()  # consume precision unit
        precision = precision_token.value.lower()

        self.expect(TokenType.OF, "Expected 'of'")
        operand = self.parse_expression()

        # Return as a BinaryExpression with the precision as metadata
        return BinaryExpression(operator="precision of", left=Literal(value=precision, type="String"), right=operand)

    def _is_type_constructor(self) -> bool:
        """Check if current position is a type constructor."""
        # Type constructors like Quantity { value: 5, unit: 'mg' }
        # Also Code { code: 'xxx' }, ValueSet { id: 'xxx' }, Concept { ... }
        # And qualified names like System.ValueSet { ... }
        # NOTE: We must lookahead for '{' even for type-keyword tokens like QUANTITY,
        # because these tokens also serve as identifiers (e.g., parameter name 'quantity').
        if self.match(TokenType.QUANTITY, TokenType.RATIO, TokenType.CODE_TYPE,
                      TokenType.VALUESET_TYPE, TokenType.CONCEPT_TYPE,
                      TokenType.STRING_TYPE, TokenType.BOOLEAN, TokenType.INTEGER_TYPE,
                      TokenType.DECIMAL_TYPE, TokenType.DATE_TYPE, TokenType.DATETIME_TYPE,
                      TokenType.TIME_TYPE):
            saved_pos = self.pos
            self.advance()  # consume the type keyword
            # Check for qualified form (e.g., System.Quantity { ... })
            while self.match_and_advance(TokenType.DOT):
                if not self.match(TokenType.IDENTIFIER, TokenType.QUOTED_IDENTIFIER,
                                  TokenType.CODE_TYPE, TokenType.VALUESET_TYPE,
                                  TokenType.CONCEPT_TYPE, TokenType.QUANTITY,
                                  TokenType.STRING_TYPE, TokenType.BOOLEAN,
                                  TokenType.INTEGER_TYPE, TokenType.DECIMAL_TYPE):
                    break
                self.advance()
            is_constructor = self.match(TokenType.LBRACE)
            self.pos = saved_pos  # restore position
            return is_constructor
        # Check for identifier followed by { (e.g., Code, ValueSet, or System.ValueSet)
        if self.match(TokenType.IDENTIFIER, TokenType.QUOTED_IDENTIFIER):
            # Skip known function names that use { } for list arguments
            current_value = self.current().value.lower() if self.current().value else ""
            if current_value in ("collapse", "expand", "union", "intersect", "except"):
                return False
            # Look ahead to see if this is followed by . and more identifiers then {
            saved_pos = self.pos
            self.advance()  # consume the identifier
            # Check for qualified identifier (e.g., System.ValueSet)
            while self.match_and_advance(TokenType.DOT):
                if not self.match(TokenType.IDENTIFIER, TokenType.QUOTED_IDENTIFIER,
                                  TokenType.CODE_TYPE, TokenType.VALUESET_TYPE,
                                  TokenType.CONCEPT_TYPE, TokenType.QUANTITY):
                    break
            is_constructor = self.match(TokenType.LBRACE)
            self.pos = saved_pos  # restore position
            return is_constructor
        return False

    def _parse_type_constructor(self) -> InstanceExpression:
        """Parse a type constructor expression."""
        # Parse the type name (possibly qualified like System.ValueSet)
        type_parts = []
        type_parts.append(self._parse_identifier_name())

        # Check for qualified identifier (e.g., System.ValueSet)
        while self.match_and_advance(TokenType.DOT):
            type_parts.append(self._parse_identifier_name())

        type_name = ".".join(type_parts)
        self.expect(TokenType.LBRACE, "Expected '{'")

        elements = []
        while not self.match(TokenType.RBRACE):
            name = self._parse_identifier_name()
            self.expect(TokenType.COLON, "Expected ':'")
            value = self.parse_expression()
            elements.append(TupleElement(name=name, type=value))

            if not self.match_and_advance(TokenType.COMMA):
                break

        self.expect(TokenType.RBRACE, "Expected '}'")
        return InstanceExpression(type=type_name, elements=elements)

    def _parse_identifier_or_function(self) -> Expression:
        """Parse an identifier that may be a function call."""
        name = self._parse_identifier_name()

        # Check for function call with parentheses
        if self.match(TokenType.LPAREN):
            return self._parse_function_call(Identifier(name=name))

        # Check for function call with curly braces (e.g., collapse { ... }, expand { ... })
        # This is valid CQL syntax for aggregate functions that take a list
        if self.match_and_advance(TokenType.LBRACE):
            return self._parse_function_call_with_braces(name)

        # Special handling for 'expand'/'collapse' without braces: expand/collapse X per ...
        if name.lower() in ("expand", "collapse"):
            # Parse the list/interval argument (could be Interval[...] or identifier)
            interval_arg = self.parse_primary_expression()
            # Check for 'per' keyword
            if self.match_and_advance(TokenType.PER):
                per_value = self._parse_per_value()
                return FunctionRef(name=name, arguments=[interval_arg, per_value])
            return FunctionRef(name=name, arguments=[interval_arg])

        return Identifier(name=name)

    def _parse_function_call_with_braces(self, name: str) -> FunctionRef:
        """Parse a function call with curly brace syntax (e.g., collapse { ... })."""
        # The { has already been matched, so parse the list content
        elements = []
        if not self.match(TokenType.RBRACE):
            elements.append(self.parse_expression())
            while self.match_and_advance(TokenType.COMMA):
                if self.match(TokenType.RBRACE):
                    break
                elements.append(self.parse_expression())

        self.expect(TokenType.RBRACE, "Expected '}'")

        # Check for 'per' keyword after expand/collapse (e.g., expand { ... } per day)
        if name.lower() in ("expand", "collapse") and self.match_and_advance(TokenType.PER):
            per_value = self._parse_per_value()
            return FunctionRef(name=name, arguments=[ListExpression(elements=elements), per_value])

        return FunctionRef(name=name, arguments=[ListExpression(elements=elements)])

    def _parse_per_value(self) -> Expression:
        """Parse the value after 'per' keyword in expand expression.

        Examples:
            per day
            per 2
            per 2 days
            per hour
            per 0.1
        """
        # Check for a number first (e.g., per 2, per 0.1)
        if self.match(TokenType.INTEGER, TokenType.DECIMAL):
            value_token = self.advance()
            value = float(value_token.value) if value_token.type == TokenType.DECIMAL else int(value_token.value)

            # Check for optional temporal unit (e.g., per 2 days)
            if self.match(TokenType.YEAR, TokenType.YEARS, TokenType.MONTH, TokenType.MONTHS,
                          TokenType.WEEK, TokenType.WEEKS, TokenType.DAY, TokenType.DAYS,
                          TokenType.HOUR, TokenType.HOURS, TokenType.MINUTE, TokenType.MINUTES,
                          TokenType.SECOND, TokenType.SECONDS, TokenType.MILLISECOND, TokenType.MILLISECONDS):
                unit_token = self.advance()
                unit = unit_token.value.lower().rstrip('s')
                return Quantity(value=float(value), unit=unit)

            # Just a number without unit
            return Quantity(value=float(value), unit="")

        # Check for temporal unit only (e.g., per day, per hour)
        if self.match(TokenType.YEAR, TokenType.YEARS, TokenType.MONTH, TokenType.MONTHS,
                      TokenType.WEEK, TokenType.WEEKS, TokenType.DAY, TokenType.DAYS,
                      TokenType.HOUR, TokenType.HOURS, TokenType.MINUTE, TokenType.MINUTES,
                      TokenType.SECOND, TokenType.SECONDS, TokenType.MILLISECOND, TokenType.MILLISECONDS):
            unit_token = self.advance()
            unit = unit_token.value.lower().rstrip('s')
            return Quantity(value=1.0, unit=unit)

        # Fallback: parse as general expression
        return self.parse_primary_expression()

    def _parse_function_call(self, func: Union[Identifier, QualifiedIdentifier, Property]) -> FunctionRef:
        """Parse a function call."""
        if isinstance(func, Identifier):
            name = func.name
        elif isinstance(func, QualifiedIdentifier):
            name = ".".join(func.parts)
        elif isinstance(func, Property):
            # For property access like FHIRHelpers.ToQuantity, build the full path
            parts = []
            current = func
            while isinstance(current, Property):
                parts.insert(0, current.path)
                current = current.source
            if isinstance(current, Identifier):
                parts.insert(0, current.name)
            name = ".".join(parts)
        else:
            name = str(func)

        self.expect(TokenType.LPAREN, "Expected '('")

        arguments = []
        if not self.match(TokenType.RPAREN):
            arguments.append(self.parse_expression())
            while self.match_and_advance(TokenType.COMMA):
                arguments.append(self.parse_expression())

        self.expect(TokenType.RPAREN, "Expected ')'")
        return FunctionRef(name=name, arguments=arguments)

    def _parse_aggregate_expression(self) -> AggregateExpression:
        """Parse an aggregate expression."""
        operator = self.advance().value.lower()
        self.expect(TokenType.LPAREN, "Expected '('")

        source = self.parse_expression()
        initializer = None

        if self.match_and_advance(TokenType.COMMA):
            initializer = self.parse_expression()

        self.expect(TokenType.RPAREN, "Expected ')'")
        return AggregateExpression(source=source, operator=operator, initializer=initializer)

    def _parse_temporal_expression(self) -> Expression:
        """Parse a temporal expression."""
        token = self.advance()
        operator = token.value.lower()

        # These are typically binary operators
        right = self.parse_unary_expression()
        # Temporal operators need a left operand - this is handled in comparison
        # For now, return as unary (this should be refactored)
        return UnaryExpression(operator=operator, operand=right)

    # =========================================================================
    # Query Parsing
    # =========================================================================

    def parse_from_query(self) -> Query:
        """Parse a CQL query expression starting with 'from' keyword.

        Example: from ({2, 3}) A, ({5, 6}) B where A > B return A
        """
        self.expect(TokenType.FROM, "Expected 'from'")

        # Parse source clause
        source = self.parse_query_source()
        sources = [source]

        # Parse additional sources (with commas)
        while self.match_and_advance(TokenType.COMMA):
            sources.append(self.parse_query_source())

        if len(sources) == 1:
            query_source = sources[0]
        else:
            query_source = sources

        query = Query(source=query_source)

        # When there are multiple sources, parse_postfix_expression may have
        # parsed each source as an inner Query that greedily absorbed an alias
        # and possibly where/return/sort/let clauses meant for this outer from-query.
        # Detect this and unwrap all inner Query sources back to plain QuerySources.
        if len(sources) > 1:
            for i, src in enumerate(sources):
                inner_expr = src.expression
                if isinstance(inner_expr, Query) and isinstance(inner_expr.source, QuerySource):
                    has_clauses = (
                        inner_expr.where is not None
                        or inner_expr.return_clause is not None
                        or inner_expr.sort is not None
                        or inner_expr.with_clauses
                        or inner_expr.let_clauses
                        or inner_expr.aggregate is not None
                    )
                    if has_clauses:
                        # Lift clauses from the inner query to the outer from-query
                        query.where = inner_expr.where
                        query.return_clause = inner_expr.return_clause
                        query.sort = inner_expr.sort
                        query.with_clauses = inner_expr.with_clauses
                        query.let_clauses = inner_expr.let_clauses
                        query.aggregate = inner_expr.aggregate
                    # Unwrap the inner Query to a plain QuerySource
                    sources[i] = inner_expr.source

        # Parse query clauses
        while True:
            if self.match(TokenType.WHERE) and query.where is None:
                query.where = self.parse_where_clause()
            elif self.match(TokenType.RETURN) and query.return_clause is None:
                query.return_clause = self.parse_return_clause()
            elif self.match(TokenType.SORT) and query.sort is None:
                query.sort = self.parse_sort_clause()
            elif self.match(TokenType.WITH, TokenType.WITHOUT):
                query.with_clauses.append(self.parse_with_clause())
            elif self.match(TokenType.LET):
                query.let_clauses.extend(self.parse_let_clause())
            elif self.match(TokenType.AGGREGATE) and query.aggregate is None:
                query.aggregate = self.parse_aggregate_clause()
            else:
                break

        return query

    def parse_query(self) -> Query:
        """Parse a CQL query expression."""
        # Parse source clause
        source = self.parse_query_source()
        sources = [source]

        # Parse additional sources (with commas)
        while self.match_and_advance(TokenType.COMMA):
            sources.append(self.parse_query_source())

        if len(sources) == 1:
            query_source = sources[0]
        else:
            query_source = sources

        query = Query(source=query_source)

        # Parse query clauses
        while True:
            if self.match(TokenType.WHERE) and query.where is None:
                query.where = self.parse_where_clause()
            elif self.match(TokenType.RETURN) and query.return_clause is None:
                query.return_clause = self.parse_return_clause()
            elif self.match(TokenType.SORT) and query.sort is None:
                query.sort = self.parse_sort_clause()
            elif self.match(TokenType.WITH, TokenType.WITHOUT):
                query.with_clauses.append(self.parse_with_clause())
            elif self.match(TokenType.LET):
                query.let_clauses.extend(self.parse_let_clause())
            else:
                break

        return query

    def parse_query_source(self) -> QuerySource:
        """Parse a query source clause."""
        expression = self.parse_expression()

        # Check for alias (accept identifiers and FHIR resource type keywords)
        alias = None
        if self.match(TokenType.IDENTIFIER, TokenType.QUOTED_IDENTIFIER,
                      TokenType.LOCATION, TokenType.PATIENT, TokenType.PRACTITIONER,
                      TokenType.ORGANIZATION, TokenType.RESOURCE, TokenType.BUNDLE):
            # Peek ahead to see if this is an alias
            next_token = self.peek()
            if next_token.type in (TokenType.WHERE, TokenType.RETURN, TokenType.SORT,
                                   TokenType.WITH, TokenType.WITHOUT, TokenType.LET,
                                   TokenType.COMMA, TokenType.EOF, TokenType.RPAREN,
                                   TokenType.AGGREGATE, TokenType.COMMA, TokenType.RBRACKET, TokenType.RBRACE):
                alias = self._parse_identifier_name()

        return QuerySource(alias=alias or "", expression=expression)

    def parse_where_clause(self) -> WhereClause:
        """Parse a where clause."""
        self.expect(TokenType.WHERE, "Expected 'where'")
        expression = self.parse_expression()
        return WhereClause(expression=expression)

    def parse_return_clause(self) -> ReturnClause:
        """Parse a return clause.

        Supports:
            return <expr>
            return all <expr>
            return distinct <expr>
        """
        self.expect(TokenType.RETURN, "Expected 'return'")
        distinct = False
        if self.match_and_advance(TokenType.DISTINCT, TokenType.DISTINCT_FN):
            distinct = True
        elif self.match_and_advance(TokenType.ALL):
            distinct = False  # explicit 'all' means no distinct
        expression = self.parse_expression()
        return ReturnClause(expression=expression, distinct=distinct)

    def parse_sort_clause(self) -> SortClause:
        """Parse a sort clause.

        Supports two forms:
        - sort asc/desc (simple sort on whole item)
        - sort by [asc/desc] expression (sort by expression)
        """
        self.expect(TokenType.SORT, "Expected 'sort'")

        # Check for simple sort: sort asc or sort desc (without 'by')
        if self.match(TokenType.ASC):
            direction = "asc"
            self.advance()
            return SortClause(by=[SortByItem(direction=direction, expression=None)])
        elif self.match(TokenType.DESC):
            direction = "desc"
            self.advance()
            return SortClause(by=[SortByItem(direction=direction, expression=None)])

        # Full sort by expression: sort by [asc/desc] expr
        self.expect(TokenType.BY, "Expected 'by'")

        by_items = []
        while True:
            direction = "asc"
            # Direction can appear before or after the expression
            direction_before = False
            if self.match_and_advance(TokenType.ASC):
                direction = "asc"
                direction_before = True
            elif self.match_and_advance(TokenType.DESC):
                direction = "desc"
                direction_before = True

            expression = self.parse_expression()

            # Also check for trailing asc/desc after the expression
            if not direction_before:
                if self.match_and_advance(TokenType.ASC):
                    direction = "asc"
                elif self.match_and_advance(TokenType.DESC):
                    direction = "desc"

            by_items.append(SortByItem(direction=direction, expression=expression))

            if not self.match_and_advance(TokenType.COMMA):
                break

        return SortClause(by=by_items)

    def parse_with_clause(self) -> WithClause:
        """Parse a with/without clause."""
        is_without = self.match_and_advance(TokenType.WITHOUT) is not None
        if not is_without:
            self.expect(TokenType.WITH, "Expected 'with' or 'without'")

        expression = self.parse_expression()
        alias = None

        if self.match(TokenType.IDENTIFIER, TokenType.QUOTED_IDENTIFIER,
                      TokenType.LOCATION, TokenType.PATIENT, TokenType.PRACTITIONER,
                      TokenType.ORGANIZATION, TokenType.RESOURCE, TokenType.BUNDLE):
            alias = self._parse_identifier_name()

        self.expect(TokenType.SUCH, "Expected 'such that'")
        self.expect(TokenType.THAT, "Expected 'such that'")
        such_that = self.parse_expression()

        return WithClause(alias=alias or "", expression=expression, such_that=such_that, is_without=is_without)

    def parse_let_clause(self) -> List[LetClause]:
        """Parse a let clause with potentially multiple comma-separated bindings.

        Examples:
            let S: expression
            let S: expression1, E: expression2
        """
        self.expect(TokenType.LET, "Expected 'let'")

        clauses = []
        while True:
            alias = self._parse_identifier_name()
            self.expect(TokenType.COLON, "Expected ':'")
            expression = self.parse_expression()
            clauses.append(LetClause(alias=alias, expression=expression))

            # Check for comma-separated additional bindings
            if self.match_and_advance(TokenType.COMMA):
                # Check if next token is an identifier (or keyword-as-identifier)
                # followed by colon (another binding)
                # Use lookahead: save position, try consuming identifier, check for ':'
                saved_pos = self.pos
                try:
                    self._parse_identifier_name()
                    if self.match(TokenType.COLON):
                        self.pos = saved_pos  # restore, let the loop re-parse
                        continue  # Parse another binding
                except Exception as e:
                    _logger.warning("Lookahead for let binding failed: %s", e)
                self.pos = saved_pos
            break

        return clauses

    def parse_aggregate_clause(self) -> AggregateClause:
        """Parse an aggregate clause.

        Examples:
            aggregate Result starting 1: Result + X
            aggregate distinct Result: Coalesce(Result, 0) + X
            aggregate all Result: Result + X
            aggregate Result: Result + X  (no starting value)
        """
        self.expect(TokenType.AGGREGATE, "Expected 'aggregate'")

        # Check for 'distinct' or 'all' modifiers
        # Note: 'distinct' can be tokenized as DISTINCT or DISTINCT_FN
        distinct = False
        all_ = False
        if self.match_and_advance(TokenType.DISTINCT, TokenType.DISTINCT_FN):
            distinct = True
        elif self.match_and_advance(TokenType.ALL):
            all_ = True

        # Parse the accumulator identifier
        identifier = self._parse_identifier_name()

        # Check for 'starting' clause
        starting = None
        if self.match_and_advance(TokenType.STARTING):
            starting = self.parse_expression()

        # Expect colon and parse the aggregation expression
        self.expect(TokenType.COLON, "Expected ':' after aggregate clause")
        expression = self.parse_expression()

        return AggregateClause(
            identifier=identifier,
            expression=expression,
            starting=starting,
            distinct=distinct,
            all_=all_
        )

    # =========================================================================
    # Type Specifier Parsing
    # =========================================================================

    def parse_type_specifier(self) -> TypeSpecifier:
        """Parse a type specifier."""
        # Check for interval type
        if self.match(TokenType.INTERVAL):
            return self._parse_interval_type_specifier()

        # Check for list type
        if self.match(TokenType.LIST_TYPE):
            return self._parse_list_type_specifier()

        # Check for tuple type
        if self.match(TokenType.TUPLE):
            return self._parse_tuple_type_specifier()

        # Check for choice type
        if self.match(TokenType.CHOICE):
            return self._parse_choice_type_specifier()

        # Default to named type
        return self._parse_named_type_specifier()

    def _parse_named_type_specifier(self) -> NamedTypeSpecifier:
        """Parse a named type specifier, including qualified names like System.Any."""
        name = self._parse_identifier_name()
        # Handle qualified names like System.Any, FHIR.Patient, etc.
        while self.match_and_advance(TokenType.DOT):
            name += "." + self._parse_identifier_name()
        return NamedTypeSpecifier(name=name)

    def _parse_interval_type_specifier(self) -> IntervalTypeSpecifier:
        """Parse an interval type specifier."""
        self.expect(TokenType.INTERVAL, "Expected 'Interval'")
        self.expect(TokenType.LESS_THAN, "Expected '<'")
        point_type = self.parse_type_specifier()
        self.expect(TokenType.GREATER_THAN, "Expected '>'")
        return IntervalTypeSpecifier(point_type=point_type)

    def _parse_list_type_specifier(self) -> ListTypeSpecifier:
        """Parse a list type specifier."""
        self.expect(TokenType.LIST_TYPE, "Expected 'List'")
        self.expect(TokenType.LESS_THAN, "Expected '<'")
        element_type = self.parse_type_specifier()
        self.expect(TokenType.GREATER_THAN, "Expected '>'")
        return ListTypeSpecifier(element_type=element_type)

    def _parse_tuple_type_specifier(self) -> TupleTypeSpecifier:
        """Parse a tuple type specifier."""
        self.expect(TokenType.TUPLE, "Expected 'Tuple'")
        self.expect(TokenType.LBRACE, "Expected '{'")

        elements = []
        while not self.match(TokenType.RBRACE):
            name = self._parse_identifier_name()
            self.expect(TokenType.COLON, "Expected ':'")
            element_type = self.parse_type_specifier()
            elements.append(TupleElement(name=name, type=element_type))

            if not self.match_and_advance(TokenType.COMMA):
                break

        self.expect(TokenType.RBRACE, "Expected '}'")
        return TupleTypeSpecifier(elements=elements)

    def _parse_choice_type_specifier(self) -> ChoiceTypeSpecifier:
        """Parse a choice type specifier."""
        self.expect(TokenType.CHOICE, "Expected 'Choice'")
        self.expect(TokenType.LESS_THAN, "Expected '<'")

        choices = [self.parse_type_specifier()]
        while self.match_and_advance(TokenType.COMMA):
            choices.append(self.parse_type_specifier())

        self.expect(TokenType.GREATER_THAN, "Expected '>'")
        return ChoiceTypeSpecifier(choices=choices)

    # =========================================================================
    # Query Operator Parsing Methods
    # =========================================================================

    def _parse_skip_expression(self, source: Expression) -> SkipExpression:
        """Parse: skip SOURCE COUNT"""
        self.expect(TokenType.SKIP, "Expected 'skip'")
        count = self.parse_expression()
        return SkipExpression(source=source, count=count)

    def _parse_take_expression(self, source: Expression) -> TakeExpression:
        """Parse: take SOURCE COUNT"""
        self.expect(TokenType.TAKE, "Expected 'take'")
        count = self.parse_expression()
        return TakeExpression(source=source, count=count)

    def _parse_first_expression(self, source: Expression) -> FirstExpression:
        """Parse: first SOURCE"""
        self.expect(TokenType.FIRST, "Expected 'first'")
        return FirstExpression(source=source)

    def _parse_last_expression(self, source: Expression) -> LastExpression:
        """Parse: last SOURCE"""
        self.expect(TokenType.LAST, "Expected 'last'")
        return LastExpression(source=source)

    def _parse_any_expression(self, source: Expression) -> AnyExpression:
        """Parse: any SOURCE ALIAS where CONDITION"""
        self.expect(TokenType.ANY, "Expected 'any'")
        alias = self._parse_identifier_name()
        self.expect(TokenType.WHERE, "Expected 'where'")
        condition = self.parse_expression()
        return AnyExpression(source=source, alias=alias, condition=condition)

    def _parse_all_expression(self, source: Expression) -> AllExpression:
        """Parse: all SOURCE ALIAS where CONDITION"""
        self.expect(TokenType.ALL, "Expected 'all'")
        alias = self._parse_identifier_name()
        self.expect(TokenType.WHERE, "Expected 'where'")
        condition = self.parse_expression()
        return AllExpression(source=source, alias=alias, condition=condition)

    def _parse_singleton_expression(self, source: Expression) -> SingletonExpression:
        """Parse: singleton from SOURCE"""
        self.expect(TokenType.SINGLETON_FROM, "Expected 'singleton from'")
        return SingletonExpression(source=source)

    def _parse_distinct_expression(self, source: Expression) -> DistinctExpression:
        """Parse: distinct SOURCE"""
        # Accept both DISTINCT and DISTINCT_FN tokens
        if self.match(TokenType.DISTINCT):
            self.expect(TokenType.DISTINCT, "Expected 'distinct'")
        else:
            self.expect(TokenType.DISTINCT_FN, "Expected 'distinct'")
        return DistinctExpression(source=source)

    # =========================================================================
    # Helper Methods for Identifiers
    # =========================================================================

    def _build_qualified_name_from_property(self, expr: Expression) -> str:
        """Build a qualified type name from a Property chain (e.g., System.ValueSet)."""
        parts = []
        current = expr
        while isinstance(current, Property):
            parts.insert(0, current.path)
            current = current.source
        if isinstance(current, Identifier):
            parts.insert(0, current.name)
        return ".".join(parts)

    def _parse_identifier_name(self) -> str:
        """Parse an identifier name (regular or quoted)."""
        if self.match(TokenType.IDENTIFIER):
            return self.advance().value
        elif self.match(TokenType.QUOTED_IDENTIFIER):
            return self.advance().value
        elif self.match(TokenType.PATIENT, TokenType.PRACTITIONER, TokenType.ORGANIZATION,
                        TokenType.LOCATION, TokenType.RESOURCE, TokenType.BUNDLE):
            return self.advance().value
        elif self.match(TokenType.BOOLEAN, TokenType.INTEGER_TYPE, TokenType.LONG_TYPE, TokenType.DECIMAL_TYPE,
                        TokenType.STRING_TYPE, TokenType.DATE_TYPE, TokenType.DATETIME_TYPE,
                        TokenType.TIME_TYPE, TokenType.QUANTITY, TokenType.RATIO,
                        TokenType.INTERVAL, TokenType.LIST_TYPE, TokenType.TUPLE,
                        TokenType.CHOICE, TokenType.ANY, TokenType.CODE_TYPE,
                        TokenType.CONCEPT_TYPE, TokenType.CODESYSTEM_TYPE, TokenType.VALUESET_TYPE):
            return self.advance().value
        # Also accept function keywords as identifiers (they may be used as names)
        elif self.match(TokenType.COUNT, TokenType.SUM, TokenType.MIN, TokenType.MAX,
                        TokenType.AVG, TokenType.MEDIAN, TokenType.MODE, TokenType.LENGTH,
                        TokenType.CODE, TokenType.CONCEPT, TokenType.VALUESYSTEM,
                        TokenType.UPPER, TokenType.LOWER, TokenType.CONCATENATE,
                        TokenType.COMBINE, TokenType.SPLIT, TokenType.POSITION_OF,
                        TokenType.SUBSTRING, TokenType.STARTS_WITH, TokenType.ENDS_WITH,
                        TokenType.MATCHES, TokenType.REPLACE_MATCHES, TokenType.REPLACE,
                        TokenType.COALESCE, TokenType.IFF, TokenType.CASE, TokenType.WHEN,
                        TokenType.THEN, TokenType.ELSE, TokenType.END, TokenType.TO_BOOLEAN,
                        TokenType.TO_CONCEPT, TokenType.TO_DATE, TokenType.TO_DATETIME,
                        TokenType.TO_DECIMAL, TokenType.TO_INTEGER, TokenType.TO_QUANTITY,
                        TokenType.TO_STRING, TokenType.TO_TIME, TokenType.TO_CODE,
                        TokenType.TO_CHARS, TokenType.FROM_CHARS, TokenType.FIRST,
                        TokenType.LAST, TokenType.INDEXER, TokenType.FLATTEN,
                        TokenType.DISTINCT_FN, TokenType.CURRENT, TokenType.CHILDREN,
                        TokenType.DESCENDENTS, TokenType.ENCODE, TokenType.ESCAPE,
                        TokenType.PREVIOUS, TokenType.PREDECESSOR, TokenType.SUCCESSOR, TokenType.SINGLE,
                        TokenType.SELECT, TokenType.FOR, TokenType.OF, TokenType.REPEAT,
                        TokenType.INTERSECT, TokenType.EXCEPT, TokenType.UNION,
                        TokenType.EXPAND, TokenType.ROUND, TokenType.ABS, TokenType.CEILING,
                        TokenType.FLOOR, TokenType.LN, TokenType.LOG, TokenType.POWER,
                        TokenType.TRUNCATE, TokenType.EXP, TokenType.SQRT, TokenType.DIV,
                        TokenType.MOD, TokenType.REMAINDER, TokenType.WIDTH, TokenType.SIZE,
                        TokenType.POINT_FROM, TokenType.LOWBOUNDARY, TokenType.HIGHBOUNDARY,
                        TokenType.PRECISION, TokenType.MINIMUM, TokenType.MAXIMUM,
                        TokenType.ALL_TRUE, TokenType.ANY_TRUE,
                        TokenType.VARIANCE, TokenType.STDDEV,
                        TokenType.SKIP, TokenType.TAKE,
                        TokenType.DISPLAY, TokenType.CALLED,
                        TokenType.ASC, TokenType.DESC,
                        TokenType.SORT, TokenType.BY,
                        TokenType.VERSION,
                        TokenType.DATE_FROM, TokenType.TIME_FROM,
                        TokenType.YEAR, TokenType.YEARS, TokenType.MONTH, TokenType.MONTHS,
                        TokenType.WEEK, TokenType.WEEKS, TokenType.DAY, TokenType.DAYS,
                        TokenType.HOUR, TokenType.HOURS, TokenType.MINUTE, TokenType.MINUTES,
                        TokenType.SECOND, TokenType.SECONDS,
                        TokenType.MILLISECOND, TokenType.MILLISECONDS,
                        TokenType.IS, TokenType.AS,
                        TokenType.START, TokenType.STARTING,
                        TokenType.EXISTS, TokenType.CONTAINS,
                        TokenType.OVERLAPS, TokenType.BEFORE, TokenType.AFTER,
                        TokenType.MEETS, TokenType.STARTS, TokenType.ENDS,
                        TokenType.DURING, TokenType.INCLUDES, TokenType.PROPERLY):
            return self.advance().value
        else:
            token = self.current()
            raise ParseError(
                f"Expected identifier, got {token.type.name} '{token.value}'",
                position=(token.line, token.column),
            )


# Convenience function
def parse_cql(source: str) -> Library:
    """
    Parse CQL source code and return the AST.

    Args:
        source: CQL source code.

    Returns:
        Library AST node.
    """
    lexer = Lexer(source)
    tokens = lexer.tokenize()
    parser = CQLParser(tokens)
    return parser.parse_library()


def parse_expression(source: str) -> Expression:
    """
    Parse a CQL expression and return the AST.

    Args:
        source: CQL expression source code.

    Returns:
        Expression AST node.
    """
    lexer = Lexer(source)
    tokens = lexer.tokenize()
    parser = CQLParser(tokens)
    return parser.parse_expression()


__all__ = [
    "CQLParser",
    "Parser",  # Alias for backward compatibility
    "parse_cql",
    "parse_expression",
]

# Alias for backward compatibility
Parser = CQLParser
