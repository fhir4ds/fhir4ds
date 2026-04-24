"""
Unit tests for ExpressionTranslator class (translator_v2).

Tests the translation of CQL expressions to SQL using the DuckDB FHIRPath UDFs,
including:
- Literal expressions (null, boolean, string, integer, decimal)
- DateTime and Time literals
- Identifier references (simple, qualified)
- Property access (with fhirpath UDFs)
- Arithmetic operators (+, -, *, /, div, mod, ^)
- Comparison operators (=, <>, <, <=, >, >=)
- Logical operators (and, or, not)
- Interval construction (closed, open, half-open)
- Conditional expressions (if-then-else)
"""

import pytest

from ...parser.ast_nodes import (
    AllExpression,
    AnyExpression,
    BinaryExpression,
    ConditionalExpression,
    DateTimeLiteral,
    DifferenceBetween,
    DurationBetween,
    FirstExpression,
    Identifier,
    Interval,
    LastExpression,
    Literal,
    Property,
    QualifiedIdentifier,
    Retrieve,
    SkipExpression,
    TakeExpression,
    UnaryExpression,
)
from ...translator.context import SQLTranslationContext
from ...translator.expressions import (
    BINARY_OPERATOR_MAP,
    ExpressionTranslator,
    UNARY_OPERATOR_MAP,
)
from ...translator.types import (
    SQLArray,
    SQLBinaryOp,
    SQLCase,
    SQLFunctionCall,
    SQLIdentifier,
    SQLInterval,
    SQLLiteral,
    SQLNull,
    SQLParameterRef,
    SQLQualifiedIdentifier,
    SQLRaw,
    SQLUnaryOp,
)


class TestLiterals:
    """Tests for literal expression translation."""

    @pytest.fixture
    def translator(self) -> ExpressionTranslator:
        """Create an ExpressionTranslator instance for testing."""
        context = SQLTranslationContext()
        return ExpressionTranslator(context)

    def test_integer_literal(self, translator: ExpressionTranslator):
        """Test integer literal translation: 5 -> 5."""
        result = translator.translate(Literal(value=5))
        assert isinstance(result, SQLLiteral)
        assert result.value == 5
        assert result.to_sql() == "5"

    def test_integer_zero(self, translator: ExpressionTranslator):
        """Test zero integer literal."""
        result = translator.translate(Literal(value=0))
        assert isinstance(result, SQLLiteral)
        assert result.value == 0
        assert result.to_sql() == "0"

    def test_integer_negative(self, translator: ExpressionTranslator):
        """Test negative integer literal."""
        result = translator.translate(Literal(value=-42))
        assert isinstance(result, SQLLiteral)
        assert result.value == -42
        assert result.to_sql() == "-42"

    def test_decimal_literal(self, translator: ExpressionTranslator):
        """Test decimal literal translation: 3.14 -> 3.14."""
        result = translator.translate(Literal(value=3.14))
        assert isinstance(result, SQLLiteral)
        assert result.value == 3.14
        assert result.to_sql() == "3.14"

    def test_decimal_small(self, translator: ExpressionTranslator):
        """Test small decimal literal."""
        result = translator.translate(Literal(value=0.001))
        assert isinstance(result, SQLLiteral)
        assert result.value == 0.001
        assert result.to_sql() == "0.001"

    def test_string_literal(self, translator: ExpressionTranslator):
        """Test string literal translation: 'hello' -> 'hello'."""
        result = translator.translate(Literal(value="hello"))
        assert isinstance(result, SQLLiteral)
        assert result.value == "hello"
        assert result.to_sql() == "'hello'"

    def test_string_empty(self, translator: ExpressionTranslator):
        """Test empty string literal."""
        result = translator.translate(Literal(value=""))
        assert isinstance(result, SQLLiteral)
        assert result.value == ""
        assert result.to_sql() == "''"

    def test_string_with_quotes(self, translator: ExpressionTranslator):
        """Test string with single quotes is escaped."""
        result = translator.translate(Literal(value="it's a test"))
        assert isinstance(result, SQLLiteral)
        assert result.to_sql() == "'it''s a test'"

    def test_boolean_true(self, translator: ExpressionTranslator):
        """Test boolean true literal translation: true -> TRUE."""
        result = translator.translate(Literal(value=True))
        assert isinstance(result, SQLLiteral)
        assert result.value is True
        assert result.to_sql() == "TRUE"

    def test_boolean_false(self, translator: ExpressionTranslator):
        """Test boolean false literal translation: false -> FALSE."""
        result = translator.translate(Literal(value=False))
        assert isinstance(result, SQLLiteral)
        assert result.value is False
        assert result.to_sql() == "FALSE"

    def test_null_literal(self, translator: ExpressionTranslator):
        """Test null literal translation: null -> NULL."""
        result = translator.translate(Literal(value=None))
        assert isinstance(result, SQLNull)
        assert result.to_sql() == "NULL"


class TestDateTimeLiterals:
    """Tests for DateTime literal translation."""

    @pytest.fixture
    def translator(self) -> ExpressionTranslator:
        """Create an ExpressionTranslator instance for testing."""
        context = SQLTranslationContext()
        return ExpressionTranslator(context)

    def test_date_only(self, translator: ExpressionTranslator):
        """Test date-only literal: @2026-01-15 -> '2026-01-15' (string for UDF compatibility)."""
        result = translator.translate(DateTimeLiteral(value="2026-01-15"))
        assert isinstance(result, SQLLiteral)
        # The value should have the @ prefix removed (if present)
        assert result.value == "2026-01-15"

    def test_datetime_no_timezone(self, translator: ExpressionTranslator):
        """Test datetime without timezone: @2026-01-15T10:30:00."""
        result = translator.translate(DateTimeLiteral(value="2026-01-15T10:30:00"))
        assert isinstance(result, SQLLiteral)
        # ISO 8601 T separator is preserved
        assert result.value == "2026-01-15T10:30:00"

    def test_datetime_with_at_prefix(self, translator: ExpressionTranslator):
        """Test datetime with @ prefix is handled."""
        result = translator.translate(DateTimeLiteral(value="@2026-01-15T10:30:00"))
        assert isinstance(result, SQLLiteral)
        # @ prefix should be removed, T separator preserved
        assert result.value == "2026-01-15T10:30:00"


class TestIdentifiers:
    """Tests for identifier translation."""

    @pytest.fixture
    def translator(self) -> ExpressionTranslator:
        """Create an ExpressionTranslator instance for testing."""
        context = SQLTranslationContext()
        return ExpressionTranslator(context)

    def test_simple_identifier(self, translator: ExpressionTranslator):
        """Test simple identifier lookup."""
        result = translator.translate(Identifier(name="SomeVar"))
        assert isinstance(result, SQLIdentifier)
        assert result.name == "SomeVar"

    def test_patient_identifier(self, translator: ExpressionTranslator):
        """Test Patient identifier references patient resource via subquery."""
        from ...translator.types import SQLSubquery
        result = translator.translate(Identifier(name="Patient"))
        # Patient identifier now returns a subquery fetching from _patient_demographics
        assert isinstance(result, SQLSubquery)

    def test_qualified_identifier(self, translator: ExpressionTranslator):
        """Test qualified identifier: Library.name."""
        result = translator.translate(QualifiedIdentifier(parts=["Library", "name"]))
        assert isinstance(result, SQLQualifiedIdentifier)
        assert result.parts == ["Library", "name"]
        assert result.to_sql() == "Library.name"

    def test_qualified_identifier_three_parts(self, translator: ExpressionTranslator):
        """Test qualified identifier with three parts: FHIR.Patient.name."""
        result = translator.translate(QualifiedIdentifier(parts=["FHIR", "Patient", "name"]))
        assert isinstance(result, SQLQualifiedIdentifier)
        assert result.parts == ["FHIR", "Patient", "name"]
        assert result.to_sql() == "FHIR.Patient.name"


class TestPropertyAccess:
    """Tests for property access translation."""

    @pytest.fixture
    def translator(self) -> ExpressionTranslator:
        """Create an ExpressionTranslator instance for testing."""
        context = SQLTranslationContext()
        return ExpressionTranslator(context)

    def test_property_with_source(self, translator: ExpressionTranslator):
        """Test property access with source: Patient.name."""
        result = translator.translate(
            Property(source=Identifier(name="Patient"), path="name")
        )
        # Should use fhirpath function
        assert isinstance(result, SQLFunctionCall)
        assert result.name in ("fhirpath_text", "fhirpath_bool")
        # First arg should reference the source, second should be the path
        assert result.args[1].value == "name"

    def test_property_without_source(self, translator: ExpressionTranslator):
        """Test property access without explicit source uses context."""
        result = translator.translate(Property(source=None, path="name"))
        # Without a resource context, should return simple identifier
        assert isinstance(result, SQLIdentifier)
        assert result.name == "name"

    def test_property_observation_value(self, translator: ExpressionTranslator):
        """Test Observation.value property access."""
        result = translator.translate(
            Property(source=Identifier(name="Observation"), path="value")
        )
        assert isinstance(result, SQLFunctionCall)
        assert result.name in ("fhirpath_text", "fhirpath_bool", "COALESCE")

    def test_property_nested(self, translator: ExpressionTranslator):
        """Test nested property access."""
        result = translator.translate(
            Property(
                source=Property(source=Identifier(name="Patient"), path="name"),
                path="given",
            )
        )
        assert isinstance(result, SQLFunctionCall)


class TestArithmeticOperators:
    """Tests for arithmetic operator translation."""

    @pytest.fixture
    def translator(self) -> ExpressionTranslator:
        """Create an ExpressionTranslator instance for testing."""
        context = SQLTranslationContext()
        return ExpressionTranslator(context)

    def test_addition(self, translator: ExpressionTranslator):
        """Test addition: 5 + 3 -> 5 + 3."""
        result = translator.translate(
            BinaryExpression(operator="+", left=Literal(value=5), right=Literal(value=3))
        )
        assert isinstance(result, SQLBinaryOp)
        assert result.operator == "+"
        assert result.left.value == 5
        assert result.right.value == 3
        assert result.to_sql() == "5 + 3"

    def test_subtraction(self, translator: ExpressionTranslator):
        """Test subtraction: 10 - 4 -> 10 - 4."""
        result = translator.translate(
            BinaryExpression(operator="-", left=Literal(value=10), right=Literal(value=4))
        )
        assert isinstance(result, SQLBinaryOp)
        assert result.operator == "-"
        assert result.to_sql() == "10 - 4"

    def test_multiplication(self, translator: ExpressionTranslator):
        """Test multiplication: 6 * 7 -> 6 * 7."""
        result = translator.translate(
            BinaryExpression(operator="*", left=Literal(value=6), right=Literal(value=7))
        )
        assert isinstance(result, SQLBinaryOp)
        assert result.operator == "*"
        assert result.to_sql() == "6 * 7"

    def test_division(self, translator: ExpressionTranslator):
        """Test division: 15 / 3 -> 15 / 3."""
        result = translator.translate(
            BinaryExpression(operator="/", left=Literal(value=15), right=Literal(value=3))
        )
        assert isinstance(result, SQLBinaryOp)
        assert result.operator == "/"
        assert result.to_sql() == "15 / NULLIF(3, 0)"

    def test_integer_division_div(self, translator: ExpressionTranslator):
        """Test integer division: 17 div 5 -> FLOOR(17 / 5)."""
        result = translator.translate(
            BinaryExpression(operator="div", left=Literal(value=17), right=Literal(value=5))
        )
        assert isinstance(result, SQLFunctionCall)
        assert result.name == "TRUNC"
        # TRUNC wraps a division
        assert isinstance(result.args[0], SQLBinaryOp)
        assert result.args[0].operator == "/"

    def test_modulo(self, translator: ExpressionTranslator):
        """Test modulo: 17 mod 5 -> 17 % 5 (via SQLBinaryOp)."""
        result = translator.translate(
            BinaryExpression(operator="mod", left=Literal(value=17), right=Literal(value=5))
        )
        # Note: mod is mapped to "%" in BINARY_OPERATOR_MAP but handled specially
        # The actual implementation may use SQLFunctionCall with MOD or SQLBinaryOp
        sql_str = result.to_sql()
        # Either "17 % 5" or "MOD(17, 5)" are acceptable
        assert "%" in sql_str or "MOD" in sql_str.upper() or "mod" in sql_str

    def test_power(self, translator: ExpressionTranslator):
        """Test power: 2 ^ 10 -> POW(2, 10)."""
        result = translator.translate(
            BinaryExpression(operator="^", left=Literal(value=2), right=Literal(value=10))
        )
        assert isinstance(result, SQLFunctionCall)
        assert result.name == "POW"
        assert result.args[0].value == 2
        assert result.args[1].value == 10


class TestComparisonOperators:
    """Tests for comparison operator translation."""

    @pytest.fixture
    def translator(self) -> ExpressionTranslator:
        """Create an ExpressionTranslator instance for testing."""
        context = SQLTranslationContext()
        return ExpressionTranslator(context)

    def test_equality(self, translator: ExpressionTranslator):
        """Test equality: 5 = 5 -> 5 = 5."""
        result = translator.translate(
            BinaryExpression(operator="=", left=Literal(value=5), right=Literal(value=5))
        )
        assert isinstance(result, SQLBinaryOp)
        assert result.operator == "="
        assert result.to_sql() == "5 = 5"

    def test_inequality_angle(self, translator: ExpressionTranslator):
        """Test inequality with <>: 5 <> 3 -> 5 != 3."""
        result = translator.translate(
            BinaryExpression(operator="<>", left=Literal(value=5), right=Literal(value=3))
        )
        assert isinstance(result, SQLBinaryOp)
        assert result.operator == "!="
        assert result.to_sql() == "5 != 3"

    def test_less_than(self, translator: ExpressionTranslator):
        """Test less than: 5 < 10 -> 5 < 10."""
        result = translator.translate(
            BinaryExpression(operator="<", left=Literal(value=5), right=Literal(value=10))
        )
        assert isinstance(result, SQLBinaryOp)
        assert result.operator == "<"
        assert result.to_sql() == "5 < 10"

    def test_less_than_or_equal(self, translator: ExpressionTranslator):
        """Test less than or equal: 5 <= 5 -> 5 <= 5."""
        result = translator.translate(
            BinaryExpression(operator="<=", left=Literal(value=5), right=Literal(value=5))
        )
        assert isinstance(result, SQLBinaryOp)
        assert result.operator == "<="
        assert result.to_sql() == "5 <= 5"

    def test_greater_than(self, translator: ExpressionTranslator):
        """Test greater than: 10 > 5 -> 10 > 5."""
        result = translator.translate(
            BinaryExpression(operator=">", left=Literal(value=10), right=Literal(value=5))
        )
        assert isinstance(result, SQLBinaryOp)
        assert result.operator == ">"
        assert result.to_sql() == "10 > 5"

    def test_greater_than_or_equal(self, translator: ExpressionTranslator):
        """Test greater than or equal: 10 >= 10 -> 10 >= 10."""
        result = translator.translate(
            BinaryExpression(operator=">=", left=Literal(value=10), right=Literal(value=10))
        )
        assert isinstance(result, SQLBinaryOp)
        assert result.operator == ">="
        assert result.to_sql() == "10 >= 10"


class TestLogicalOperators:
    """Tests for logical operator translation."""

    @pytest.fixture
    def translator(self) -> ExpressionTranslator:
        """Create an ExpressionTranslator instance for testing."""
        context = SQLTranslationContext()
        return ExpressionTranslator(context)

    def test_and(self, translator: ExpressionTranslator):
        """Test logical and: true and false -> TRUE AND FALSE."""
        result = translator.translate(
            BinaryExpression(
                operator="and", left=Literal(value=True), right=Literal(value=False)
            )
        )
        assert isinstance(result, SQLBinaryOp)
        assert result.operator == "AND"
        assert result.to_sql() == "TRUE AND FALSE"

    def test_or(self, translator: ExpressionTranslator):
        """Test logical or: true or false -> TRUE OR FALSE."""
        result = translator.translate(
            BinaryExpression(
                operator="or", left=Literal(value=True), right=Literal(value=False)
            )
        )
        assert isinstance(result, SQLBinaryOp)
        assert result.operator == "OR"
        assert result.to_sql() == "TRUE OR FALSE"

    def test_not(self, translator: ExpressionTranslator):
        """Test logical not: not true -> NOT TRUE."""
        result = translator.translate(
            UnaryExpression(operator="not", operand=Literal(value=True))
        )
        assert isinstance(result, SQLUnaryOp)
        assert result.operator == "NOT"
        assert result.to_sql() == "NOT TRUE"


class TestIntervalConstruction:
    """Tests for interval expression translation."""

    @pytest.fixture
    def translator(self) -> ExpressionTranslator:
        """Create an ExpressionTranslator instance for testing."""
        context = SQLTranslationContext()
        return ExpressionTranslator(context)

    def test_closed_interval(self, translator: ExpressionTranslator):
        """Test closed interval: Interval[1, 10]."""
        result = translator.translate(
            Interval(
                low=Literal(value=1),
                high=Literal(value=10),
                low_closed=True,
                high_closed=True,
            )
        )
        assert isinstance(result, SQLInterval)
        assert result.low_closed is True
        assert result.high_closed is True
        sql = result.to_sql()
        assert "intervalFromBounds" in sql
        assert "1" in sql
        assert "10" in sql
        assert "TRUE" in sql

    def test_open_interval(self, translator: ExpressionTranslator):
        """Test open interval: Interval(1, 10)."""
        result = translator.translate(
            Interval(
                low=Literal(value=1),
                high=Literal(value=10),
                low_closed=False,
                high_closed=False,
            )
        )
        assert isinstance(result, SQLInterval)
        assert result.low_closed is False
        assert result.high_closed is False
        sql = result.to_sql()
        assert "intervalFromBounds" in sql
        assert "FALSE" in sql

    def test_half_open_left_closed(self, translator: ExpressionTranslator):
        """Test half-open interval: Interval[1, 10)."""
        result = translator.translate(
            Interval(
                low=Literal(value=1),
                high=Literal(value=10),
                low_closed=True,
                high_closed=False,
            )
        )
        assert isinstance(result, SQLInterval)
        assert result.low_closed is True
        assert result.high_closed is False

    def test_half_open_right_closed(self, translator: ExpressionTranslator):
        """Test half-open interval: Interval(1, 10]."""
        result = translator.translate(
            Interval(
                low=Literal(value=1),
                high=Literal(value=10),
                low_closed=False,
                high_closed=True,
            )
        )
        assert isinstance(result, SQLInterval)
        assert result.low_closed is False
        assert result.high_closed is True


class TestConditionalExpressions:
    """Tests for conditional (if-then-else) expression translation."""

    @pytest.fixture
    def translator(self) -> ExpressionTranslator:
        """Create an ExpressionTranslator instance for testing."""
        context = SQLTranslationContext()
        return ExpressionTranslator(context)

    def test_simple_conditional(self, translator: ExpressionTranslator):
        """Test simple conditional: if true then 1 else 0."""
        result = translator.translate(
            ConditionalExpression(
                condition=Literal(value=True),
                then_expr=Literal(value=1),
                else_expr=Literal(value=0),
            )
        )
        assert isinstance(result, SQLCase)
        assert len(result.when_clauses) == 1
        condition, then_val = result.when_clauses[0]
        assert condition.to_sql() == "TRUE"
        assert then_val.to_sql() == "1"
        assert result.else_clause.to_sql() == "0"
        sql = result.to_sql()
        assert "CASE" in sql
        assert "WHEN" in sql
        assert "THEN" in sql
        assert "ELSE" in sql
        assert "END" in sql

    def test_conditional_with_comparison(self, translator: ExpressionTranslator):
        """Test conditional with comparison condition."""
        result = translator.translate(
            ConditionalExpression(
                condition=BinaryExpression(
                    operator=">", left=Literal(value=5), right=Literal(value=3)
                ),
                then_expr=Literal(value="yes"),
                else_expr=Literal(value="no"),
            )
        )
        assert isinstance(result, SQLCase)
        sql = result.to_sql()
        assert "CASE" in sql
        assert "5 > 3" in sql
        assert "'yes'" in sql
        assert "'no'" in sql


class TestOperatorMaps:
    """Tests for operator mapping constants."""

    def test_binary_operator_map_contains_arithmetic(self):
        """Test that BINARY_OPERATOR_MAP contains arithmetic operators."""
        assert "+" in BINARY_OPERATOR_MAP
        assert "-" in BINARY_OPERATOR_MAP
        assert "*" in BINARY_OPERATOR_MAP
        assert "/" in BINARY_OPERATOR_MAP
        assert "div" in BINARY_OPERATOR_MAP
        assert "mod" in BINARY_OPERATOR_MAP
        assert "^" in BINARY_OPERATOR_MAP

    def test_binary_operator_map_contains_comparison(self):
        """Test that BINARY_OPERATOR_MAP contains comparison operators."""
        assert "=" in BINARY_OPERATOR_MAP
        assert "<>" in BINARY_OPERATOR_MAP
        assert "<" in BINARY_OPERATOR_MAP
        assert "<=" in BINARY_OPERATOR_MAP
        assert ">" in BINARY_OPERATOR_MAP
        assert ">=" in BINARY_OPERATOR_MAP

    def test_binary_operator_map_contains_logical(self):
        """Test that BINARY_OPERATOR_MAP contains logical operators."""
        assert "and" in BINARY_OPERATOR_MAP
        assert "or" in BINARY_OPERATOR_MAP
        assert "xor" in BINARY_OPERATOR_MAP

    def test_unary_operator_map_contains_not(self):
        """Test that UNARY_OPERATOR_MAP contains 'not'."""
        assert "not" in UNARY_OPERATOR_MAP
        assert UNARY_OPERATOR_MAP["not"] == "NOT"

    def test_unary_operator_map_contains_null_checks(self):
        """Test that UNARY_OPERATOR_MAP contains null checks."""
        assert "is null" in UNARY_OPERATOR_MAP
        assert "is not null" in UNARY_OPERATOR_MAP


class TestClinicalFunctions:
    """Tests for clinical function translation."""

    @pytest.fixture
    def translator(self) -> ExpressionTranslator:
        """Create an ExpressionTranslator instance for testing."""
        context = SQLTranslationContext()
        return ExpressionTranslator(context)

    def test_latest_function(self, translator: ExpressionTranslator):
        """Test Latest function: Latest(values, date_path)."""
        from ...parser.ast_nodes import FunctionRef
        result = translator.translate(
            FunctionRef(
                name="Latest",
                arguments=[
                    Identifier(name="Observations"),
                    Literal(value="effectiveDateTime"),
                ]
            )
        )
        assert isinstance(result, SQLFunctionCall)
        assert result.name == "Latest"
        assert len(result.args) == 2

    def test_earliest_function(self, translator: ExpressionTranslator):
        """Test Earliest function: Earliest(values, date_path)."""
        from ...parser.ast_nodes import FunctionRef
        result = translator.translate(
            FunctionRef(
                name="Earliest",
                arguments=[
                    Identifier(name="Observations"),
                    Literal(value="effectiveDateTime"),
                ]
            )
        )
        assert isinstance(result, SQLFunctionCall)
        assert result.name == "Earliest"
        assert len(result.args) == 2


class TestDateTimeDifferenceFunctions:
    """Tests for datetime difference function translation."""

    @pytest.fixture
    def translator(self) -> ExpressionTranslator:
        """Create an ExpressionTranslator instance for testing."""
        context = SQLTranslationContext()
        return ExpressionTranslator(context)

    def test_weeks_between(self, translator: ExpressionTranslator):
        """Test weeksBetween function: weeksBetween(start, end)."""
        from ...parser.ast_nodes import FunctionRef
        result = translator.translate(
            FunctionRef(
                name="weeksBetween",
                arguments=[
                    Literal(value="2024-01-01"),
                    Literal(value="2024-01-29"),
                ]
            )
        )
        assert isinstance(result, SQLFunctionCall)
        assert result.name == "date_diff"
        assert result.args[0].value == "week"

    def test_milliseconds_between(self, translator: ExpressionTranslator):
        """Test millisecondsBetween function: millisecondsBetween(start, end)."""
        from ...parser.ast_nodes import FunctionRef
        result = translator.translate(
            FunctionRef(
                name="millisecondsBetween",
                arguments=[
                    Literal(value="2024-01-01T00:00:00"),
                    Literal(value="2024-01-01T00:00:01"),
                ]
            )
        )
        assert isinstance(result, SQLFunctionCall)
        assert result.name == "date_diff"
        assert result.args[0].value == "millisecond"


class TestAgeAtFunctions:
    """Tests for AgeAt function translation."""

    @pytest.fixture
    def translator(self) -> ExpressionTranslator:
        """Create an ExpressionTranslator instance for testing."""
        context = SQLTranslationContext()
        return ExpressionTranslator(context)

    def test_age_in_years_at(self, translator: ExpressionTranslator):
        """Test AgeInYearsAt function: AgeInYearsAt(patient, as_of)."""
        from ...parser.ast_nodes import FunctionRef
        result = translator.translate(
            FunctionRef(
                name="AgeInYearsAt",
                arguments=[
                    Identifier(name="Patient"),
                    Literal(value="2024-06-15"),
                ]
            )
        )
        assert isinstance(result, SQLFunctionCall)
        assert result.name == "AgeInYearsAt"
        assert len(result.args) == 2

    def test_age_in_months_at(self, translator: ExpressionTranslator):
        """Test AgeInMonthsAt function: AgeInMonthsAt(patient, as_of)."""
        from ...parser.ast_nodes import FunctionRef
        result = translator.translate(
            FunctionRef(
                name="AgeInMonthsAt",
                arguments=[
                    Identifier(name="Patient"),
                    Literal(value="2024-06-15"),
                ]
            )
        )
        assert isinstance(result, SQLFunctionCall)
        assert result.name == "AgeInMonthsAt"
        assert len(result.args) == 2

    def test_age_in_days_at(self, translator: ExpressionTranslator):
        """Test AgeInDaysAt function: AgeInDaysAt(patient, as_of)."""
        from ...parser.ast_nodes import FunctionRef
        result = translator.translate(
            FunctionRef(
                name="AgeInDaysAt",
                arguments=[
                    Identifier(name="Patient"),
                    Literal(value="2024-06-15"),
                ]
            )
        )
        assert isinstance(result, SQLFunctionCall)
        assert result.name == "AgeInDaysAt"
        assert len(result.args) == 2

    def test_age_in_years_at_single_arg(self, translator: ExpressionTranslator):
        """Test AgeInYearsAt with single arg is inlined as date arithmetic."""
        from ...parser.ast_nodes import FunctionRef
        from ...translator.types import SQLBinaryOp
        result = translator.translate(
            FunctionRef(
                name="AgeInYearsAt",
                arguments=[
                    Literal(value="2024-06-15"),
                ]
            )
        )
        # AgeInYearsAt is now inlined as EXTRACT-based date arithmetic
        assert isinstance(result, SQLBinaryOp)

    def test_age_in_years_at_population_context(self):
        """Test AgeInYearsAt in population context is inlined as date arithmetic."""
        from ...parser.ast_nodes import FunctionRef
        from ...translator.types import SQLBinaryOp
        # Create context with patient_alias set (population context)
        context = SQLTranslationContext()
        context.patient_alias = "p"  # Simulate "FROM patients p" context
        translator = ExpressionTranslator(context)

        result = translator.translate(
            FunctionRef(
                name="AgeInYearsAt",
                arguments=[
                    Literal(value="2024-06-15"),
                ]
            )
        )
        # AgeInYearsAt is now inlined as EXTRACT-based date arithmetic
        assert isinstance(result, SQLBinaryOp)


class TestIntervalOperations:
    """Tests for interval operation translation (start of, end of, width of)."""

    @pytest.fixture
    def translator(self) -> ExpressionTranslator:
        """Create an ExpressionTranslator instance for testing."""
        context = SQLTranslationContext()
        return ExpressionTranslator(context)

    def test_interval_start(self, translator: ExpressionTranslator):
        """Test start of interval: start of Interval[1, 10]."""
        result = translator.translate(
            UnaryExpression(
                operator="start of",
                operand=Interval(
                    low=Literal(value=1),
                    high=Literal(value=10),
                    low_closed=True,
                    high_closed=True,
                ),
            )
        )
        assert isinstance(result, SQLFunctionCall)
        assert result.name == "intervalStart"
        assert len(result.args) == 1

    def test_interval_end(self, translator: ExpressionTranslator):
        """Test end of interval: end of Interval[1, 10]."""
        result = translator.translate(
            UnaryExpression(
                operator="end of",
                operand=Interval(
                    low=Literal(value=1),
                    high=Literal(value=10),
                    low_closed=True,
                    high_closed=True,
                ),
            )
        )
        assert isinstance(result, SQLFunctionCall)
        assert result.name == "intervalEnd"
        assert len(result.args) == 1

    def test_interval_width(self, translator: ExpressionTranslator):
        """Test width of interval: width of Interval[1, 10]."""
        result = translator.translate(
            UnaryExpression(
                operator="width of",
                operand=Interval(
                    low=Literal(value=1),
                    high=Literal(value=10),
                    low_closed=True,
                    high_closed=True,
                ),
            )
        )
        assert isinstance(result, SQLFunctionCall)
        assert result.name == "intervalWidth"
        assert len(result.args) == 1

    def test_interval_width_with_date_interval(self, translator: ExpressionTranslator):
        """Test width of date interval: width of Interval[@2024-01-01, @2024-01-31]."""
        result = translator.translate(
            UnaryExpression(
                operator="width of",
                operand=Interval(
                    low=DateTimeLiteral(value="2024-01-01"),
                    high=DateTimeLiteral(value="2024-01-31"),
                    low_closed=True,
                    high_closed=True,
                ),
            )
        )
        assert isinstance(result, SQLFunctionCall)
        assert result.name == "intervalWidth"
        assert len(result.args) == 1


class TestDateComponent:
    """Tests for date component extraction translation."""

    @pytest.fixture
    def translator(self) -> ExpressionTranslator:
        """Create an ExpressionTranslator instance for testing."""
        context = SQLTranslationContext()
        return ExpressionTranslator(context)

    def test_date_component_year(self, translator: ExpressionTranslator):
        """Test year extraction: year from @2024-01-15 -> CASE WHEN LENGTH(...) >= 4 THEN CAST(SUBSTR(...))."""
        from ...parser.ast_nodes import DateComponent
        result = translator.translate(
            DateComponent(component="year", operand=DateTimeLiteral(value="2024-01-15"))
        )
        assert isinstance(result, SQLCase)
        assert "SUBSTR" in result.to_sql()

    def test_date_component_month(self, translator: ExpressionTranslator):
        """Test month extraction: month from @2024-06-15 -> CASE WHEN LENGTH(...) >= N THEN CAST(SUBSTR(...))."""
        from ...parser.ast_nodes import DateComponent
        result = translator.translate(
            DateComponent(component="month", operand=DateTimeLiteral(value="2024-06-15"))
        )
        assert isinstance(result, SQLCase)
        assert "SUBSTR" in result.to_sql()

    def test_date_component_millisecond(self, translator: ExpressionTranslator):
        """Test millisecond extraction: millisecond from @T12:30:45.123 -> CASE WHEN ..."""
        from ...parser.ast_nodes import DateComponent, TimeLiteral
        result = translator.translate(
            DateComponent(component="millisecond", operand=TimeLiteral(value="T12:30:45.123"))
        )
        assert isinstance(result, SQLCase)


class TestExistsExpression:
    """Tests for exists expression translation."""

    @pytest.fixture
    def translator(self) -> ExpressionTranslator:
        """Create an ExpressionTranslator instance for testing."""
        context = SQLTranslationContext()
        return ExpressionTranslator(context)

    def test_exists_expression(self, translator: ExpressionTranslator):
        """Test exists expression: exists [Condition: "Diabetes"] -> array_length(...) > 0."""
        from ...parser.ast_nodes import ExistsExpression, ListExpression
        result = translator.translate(
            ExistsExpression(source=ListExpression(elements=[Literal(value=1), Literal(value=2)]))
        )
        assert isinstance(result, SQLBinaryOp)
        assert result.operator == ">"
        assert isinstance(result.left, SQLFunctionCall)
        assert result.left.name == "list_count"
        assert result.right.value == 0


class TestAggregateExpression:
    """Tests for aggregate expression translation."""

    @pytest.fixture
    def translator(self) -> ExpressionTranslator:
        """Create an ExpressionTranslator instance for testing."""
        context = SQLTranslationContext()
        return ExpressionTranslator(context)

    def test_aggregate_sum(self, translator: ExpressionTranslator):
        """Test sum aggregate: Sum([1, 2, 3]) -> list_sum(...)."""
        from ...parser.ast_nodes import AggregateExpression, ListExpression
        result = translator.translate(
            AggregateExpression(
                source=ListExpression(elements=[Literal(value=1), Literal(value=2), Literal(value=3)]),
                operator="Sum"
            )
        )
        assert isinstance(result, SQLFunctionCall)
        assert result.name == "list_sum"
        assert len(result.args) == 1

    def test_aggregate_count(self, translator: ExpressionTranslator):
        """Test count aggregate: Count([1, 2, 3]) -> COUNT(...)."""
        from ...parser.ast_nodes import AggregateExpression, ListExpression
        result = translator.translate(
            AggregateExpression(
                source=ListExpression(elements=[Literal(value=1), Literal(value=2), Literal(value=3)]),
                operator="Count"
            )
        )
        assert isinstance(result, SQLFunctionCall)
        assert result.name == "COUNT"
        assert len(result.args) == 1


class TestDurationBetween:
    """Tests for DurationBetween AST node translation."""

    @pytest.fixture
    def translator(self) -> ExpressionTranslator:
        """Create an ExpressionTranslator instance for testing."""
        context = SQLTranslationContext()
        return ExpressionTranslator(context)

    def test_duration_between_years(self, translator: ExpressionTranslator):
        """Test years between: years between @2020-01-01 and @2024-01-01 -> YearsBetween(...)."""
        result = translator.translate(
            DurationBetween(
                precision="year",
                operand_left=DateTimeLiteral(value="2020-01-01"),
                operand_right=DateTimeLiteral(value="2024-01-01"),
            )
        )
        assert isinstance(result, SQLFunctionCall)
        assert result.name == "cqlDurationBetween"
        assert len(result.args) == 3

    def test_duration_between_months(self, translator: ExpressionTranslator):
        """Test months between: months between A and B -> MonthsBetween(...)."""
        result = translator.translate(
            DurationBetween(
                precision="month",
                operand_left=DateTimeLiteral(value="2024-01-01"),
                operand_right=DateTimeLiteral(value="2024-06-15"),
            )
        )
        assert isinstance(result, SQLFunctionCall)
        assert result.name == "cqlDurationBetween"
        assert len(result.args) == 3

    def test_duration_between_days(self, translator: ExpressionTranslator):
        """Test days between: days between A and B -> DaysBetween(...)."""
        result = translator.translate(
            DurationBetween(
                precision="day",
                operand_left=DateTimeLiteral(value="2024-01-01"),
                operand_right=DateTimeLiteral(value="2024-01-31"),
            )
        )
        assert isinstance(result, SQLFunctionCall)
        assert result.name == "cqlDurationBetween"
        assert len(result.args) == 3

    def test_duration_between_weeks(self, translator: ExpressionTranslator):
        """Test weeks between: weeks between A and B -> weeksBetween(...)."""
        result = translator.translate(
            DurationBetween(
                precision="week",
                operand_left=DateTimeLiteral(value="2024-01-01"),
                operand_right=DateTimeLiteral(value="2024-01-29"),
            )
        )
        assert isinstance(result, SQLFunctionCall)
        assert result.name == "cqlDurationBetween"
        assert len(result.args) == 3

    def test_duration_between_hours(self, translator: ExpressionTranslator):
        """Test hours between: hours between A and B -> HoursBetween(...)."""
        result = translator.translate(
            DurationBetween(
                precision="hour",
                operand_left=DateTimeLiteral(value="2024-01-01T00:00:00"),
                operand_right=DateTimeLiteral(value="2024-01-01T12:00:00"),
            )
        )
        assert isinstance(result, SQLFunctionCall)
        assert result.name == "cqlDurationBetween"
        assert len(result.args) == 3


class TestDifferenceBetween:
    """Tests for DifferenceBetween AST node translation."""

    @pytest.fixture
    def translator(self) -> ExpressionTranslator:
        """Create an ExpressionTranslator instance for testing."""
        context = SQLTranslationContext()
        return ExpressionTranslator(context)

    def test_difference_between_years(self, translator: ExpressionTranslator):
        """Test difference in years: difference in years between A and B -> differenceInYears(...)."""
        result = translator.translate(
            DifferenceBetween(
                precision="year",
                operand_left=DateTimeLiteral(value="2020-12-31"),
                operand_right=DateTimeLiteral(value="2024-01-01"),
            )
        )
        assert isinstance(result, SQLFunctionCall)
        assert result.name == "differenceInYears"
        assert len(result.args) == 2

    def test_difference_between_months(self, translator: ExpressionTranslator):
        """Test difference in months: difference in months between A and B -> differenceInMonths(...)."""
        result = translator.translate(
            DifferenceBetween(
                precision="month",
                operand_left=DateTimeLiteral(value="2024-01-15"),
                operand_right=DateTimeLiteral(value="2024-06-15"),
            )
        )
        assert isinstance(result, SQLFunctionCall)
        assert result.name == "differenceInMonths"
        assert len(result.args) == 2

    def test_difference_between_days(self, translator: ExpressionTranslator):
        """Test difference in days: difference in days between A and B -> differenceInDays(...)."""
        result = translator.translate(
            DifferenceBetween(
                precision="day",
                operand_left=DateTimeLiteral(value="2024-01-01"),
                operand_right=DateTimeLiteral(value="2024-01-31"),
            )
        )
        assert isinstance(result, SQLFunctionCall)
        assert result.name == "differenceInDays"
        assert len(result.args) == 2

    def test_difference_between_unknown_precision(self, translator: ExpressionTranslator):
        """Test unknown precision defaults to differenceInDays."""
        result = translator.translate(
            DifferenceBetween(
                precision="unknown",
                operand_left=DateTimeLiteral(value="2024-01-01"),
                operand_right=DateTimeLiteral(value="2024-01-31"),
            )
        )
        assert isinstance(result, SQLFunctionCall)
        assert result.name == "differenceInDays"


class TestTypeConversion:
    """Tests for type conversion function translation."""

    @pytest.fixture
    def translator(self) -> ExpressionTranslator:
        """Create an ExpressionTranslator instance for testing."""
        context = SQLTranslationContext()
        return ExpressionTranslator(context)

    def test_to_decimal(self, translator: ExpressionTranslator):
        """Test ToDecimal function: ToDecimal('3.14') -> CAST('3.14' AS DOUBLE)."""
        from ...parser.ast_nodes import FunctionRef
        from ...translator.types import SQLCast
        result = translator.translate(
            FunctionRef(name="ToDecimal", arguments=[Literal(value="3.14")])
        )
        assert isinstance(result, SQLCast)
        assert result.target_type == "DOUBLE"
        sql = result.to_sql()
        assert "CAST" in sql
        assert "DOUBLE" in sql

    def test_to_decimal_from_integer(self, translator: ExpressionTranslator):
        """Test ToDecimal from integer: ToDecimal(42) -> CAST(42 AS DOUBLE)."""
        from ...parser.ast_nodes import FunctionRef
        from ...translator.types import SQLCast
        result = translator.translate(
            FunctionRef(name="ToDecimal", arguments=[Literal(value=42)])
        )
        assert isinstance(result, SQLCast)
        assert result.target_type == "DOUBLE"

    def test_to_integer(self, translator: ExpressionTranslator):
        """Test ToInteger function: ToInteger('42') -> CAST('42' AS INTEGER)."""
        from ...parser.ast_nodes import FunctionRef
        from ...translator.types import SQLCast
        result = translator.translate(
            FunctionRef(name="ToInteger", arguments=[Literal(value="42")])
        )
        assert isinstance(result, SQLCast)
        assert result.target_type == "INTEGER"
        sql = result.to_sql()
        assert "CAST" in sql
        assert "INTEGER" in sql

    def test_to_integer_from_decimal(self, translator: ExpressionTranslator):
        """Test ToInteger from decimal: ToInteger(3.14) -> CAST(3.14 AS INTEGER)."""
        from ...parser.ast_nodes import FunctionRef
        from ...translator.types import SQLCast
        result = translator.translate(
            FunctionRef(name="ToInteger", arguments=[Literal(value=3.14)])
        )
        assert isinstance(result, SQLCast)
        assert result.target_type == "INTEGER"

    def test_to_string(self, translator: ExpressionTranslator):
        """Test ToString function: ToString(42) -> CAST(42 AS VARCHAR)."""
        from ...parser.ast_nodes import FunctionRef
        from ...translator.types import SQLCast
        result = translator.translate(
            FunctionRef(name="ToString", arguments=[Literal(value=42)])
        )
        assert isinstance(result, SQLCast)
        assert result.target_type == "VARCHAR"
        sql = result.to_sql()
        assert "CAST" in sql
        assert "VARCHAR" in sql

    def test_to_string_from_boolean(self, translator: ExpressionTranslator):
        """Test ToString from boolean: ToString(true) -> CAST(TRUE AS VARCHAR)."""
        from ...parser.ast_nodes import FunctionRef
        from ...translator.types import SQLCast
        result = translator.translate(
            FunctionRef(name="ToString", arguments=[Literal(value=True)])
        )
        assert isinstance(result, SQLCast)
        assert result.target_type == "VARCHAR"

    def test_to_boolean(self, translator: ExpressionTranslator):
        """Test ToBoolean function: ToBoolean('true') -> CAST('true' AS BOOLEAN)."""
        from ...parser.ast_nodes import FunctionRef
        from ...translator.types import SQLCast
        result = translator.translate(
            FunctionRef(name="ToBoolean", arguments=[Literal(value="true")])
        )
        assert isinstance(result, SQLCast)
        assert result.target_type == "BOOLEAN"
        sql = result.to_sql()
        assert "CAST" in sql
        assert "BOOLEAN" in sql

    def test_to_boolean_from_integer(self, translator: ExpressionTranslator):
        """Test ToBoolean from integer: ToBoolean(1) -> CAST(1 AS BOOLEAN)."""
        from ...parser.ast_nodes import FunctionRef
        from ...translator.types import SQLCast
        result = translator.translate(
            FunctionRef(name="ToBoolean", arguments=[Literal(value=1)])
        )
        assert isinstance(result, SQLCast)
        assert result.target_type == "BOOLEAN"

    def test_to_datetime(self, translator: ExpressionTranslator):
        """Test ToDateTime function: ToDateTime('2024-01-15') -> SQLRaw with CASE WHEN."""
        from ...parser.ast_nodes import FunctionRef
        result = translator.translate(
            FunctionRef(name="ToDateTime", arguments=[Literal(value="2024-01-15")])
        )
        assert isinstance(result, SQLRaw)
        sql = result.to_sql()
        assert "CASE WHEN" in sql

    def test_to_datetime_from_string(self, translator: ExpressionTranslator):
        """Test ToDateTime with time: ToDateTime('2024-01-15T10:30:00') -> SQLRaw with CASE WHEN."""
        from ...parser.ast_nodes import FunctionRef
        result = translator.translate(
            FunctionRef(name="ToDateTime", arguments=[Literal(value="2024-01-15T10:30:00")])
        )
        assert isinstance(result, SQLRaw)
        sql = result.to_sql()
        assert "CASE WHEN" in sql

    def test_to_date(self, translator: ExpressionTranslator):
        """Test ToDate function: ToDate('2024-01-15') -> SQLRaw with CASE WHEN."""
        from ...parser.ast_nodes import FunctionRef
        result = translator.translate(
            FunctionRef(name="ToDate", arguments=[Literal(value="2024-01-15")])
        )
        assert isinstance(result, SQLRaw)
        sql = result.to_sql()
        assert "CASE WHEN" in sql

    def test_to_date_from_datetime(self, translator: ExpressionTranslator):
        """Test ToDate from datetime string: ToDate('2024-01-15T10:30:00') -> SQLRaw with CASE WHEN."""
        from ...parser.ast_nodes import FunctionRef
        result = translator.translate(
            FunctionRef(name="ToDate", arguments=[Literal(value="2024-01-15T10:30:00")])
        )
        assert isinstance(result, SQLRaw)
        sql = result.to_sql()
        assert "CASE WHEN" in sql

    def test_to_time(self, translator: ExpressionTranslator):
        """Test ToTime function: ToTime('10:30:00') -> ToTime(...)."""
        from ...parser.ast_nodes import FunctionRef
        result = translator.translate(
            FunctionRef(name="ToTime", arguments=[Literal(value="10:30:00")])
        )
        assert isinstance(result, SQLFunctionCall)
        assert result.name == "ToTime"

    def test_to_time_with_milliseconds(self, translator: ExpressionTranslator):
        """Test ToTime with milliseconds: ToTime('10:30:00.123') -> ToTime(...)."""
        from ...parser.ast_nodes import FunctionRef
        result = translator.translate(
            FunctionRef(name="ToTime", arguments=[Literal(value="10:30:00.123")])
        )
        assert isinstance(result, SQLFunctionCall)
        assert result.name == "ToTime"

    def test_type_conversion_with_identifier(self, translator: ExpressionTranslator):
        """Test type conversion with identifier: ToInteger(someVar) -> CAST(someVar AS INTEGER)."""
        from ...parser.ast_nodes import FunctionRef
        from ...translator.types import SQLCast
        result = translator.translate(
            FunctionRef(name="ToInteger", arguments=[Identifier(name="someVar")])
        )
        assert isinstance(result, SQLCast)
        assert result.target_type == "INTEGER"
        sql = result.to_sql()
        assert "someVar" in sql

    def test_type_conversion_case_insensitive(self, translator: ExpressionTranslator):
        """Test type conversion is case-insensitive: todecimal, ToDecimal, TODECIMAL all work."""
        from ...parser.ast_nodes import FunctionRef
        from ...translator.types import SQLCast

        # Test various casings
        for name in ["todecimal", "ToDecimal", "TODECIMAL", "toDecimal"]:
            result = translator.translate(
                FunctionRef(name=name, arguments=[Literal(value="3.14")])
            )
            assert isinstance(result, SQLCast), f"Failed for name: {name}"
            assert result.target_type == "DOUBLE", f"Failed for name: {name}"


class TestQueryOperators:
    """Tests for query operator translation (skip, take, first, last, any, all)."""

    @pytest.fixture
    def translator(self) -> ExpressionTranslator:
        """Create an ExpressionTranslator instance for testing."""
        context = SQLTranslationContext()
        return ExpressionTranslator(context)

    def test_skip_expression(self, translator: ExpressionTranslator):
        """Test skip expression: skip 2 elements -> list_slice(arr, 3, length)."""
        from ...parser.ast_nodes import ListExpression
        result = translator.translate(
            SkipExpression(
                source=ListExpression(elements=[Literal(value=1), Literal(value=2), Literal(value=3), Literal(value=4)]),
                count=Literal(value=2)
            )
        )
        assert isinstance(result, SQLFunctionCall)
        assert result.name == "LIST_SLICE"
        assert len(result.args) == 3
        sql = result.to_sql()
        assert "LIST_SLICE" in sql

    def test_take_expression(self, translator: ExpressionTranslator):
        """Test take expression: take 2 elements -> list_slice(arr, 1, 2)."""
        from ...parser.ast_nodes import ListExpression
        result = translator.translate(
            TakeExpression(
                source=ListExpression(elements=[Literal(value=1), Literal(value=2), Literal(value=3), Literal(value=4)]),
                count=Literal(value=2)
            )
        )
        assert isinstance(result, SQLFunctionCall)
        assert result.name == "LIST_SLICE"
        assert len(result.args) == 3
        sql = result.to_sql()
        assert "LIST_SLICE" in sql

    def test_first_expression(self, translator: ExpressionTranslator):
        """Test first expression: first element -> list_extract(arr, 1)."""
        from ...parser.ast_nodes import ListExpression
        result = translator.translate(
            FirstExpression(
                source=ListExpression(elements=[Literal(value=1), Literal(value=2), Literal(value=3)])
            )
        )
        assert isinstance(result, SQLFunctionCall)
        assert result.name == "LIST_EXTRACT"
        assert len(result.args) == 2
        assert result.args[1].value == 1

    def test_last_expression(self, translator: ExpressionTranslator):
        """Test last expression: last element -> list_extract(arr, -1)."""
        from ...parser.ast_nodes import ListExpression
        result = translator.translate(
            LastExpression(
                source=ListExpression(elements=[Literal(value=1), Literal(value=2), Literal(value=3)])
            )
        )
        assert isinstance(result, SQLFunctionCall)
        assert result.name == "LIST_EXTRACT"
        assert len(result.args) == 2
        assert result.args[1].value == -1

    def test_any_expression(self, translator: ExpressionTranslator):
        """Test any expression: any X where condition -> list_any(arr, alias, condition)."""
        from ...parser.ast_nodes import ListExpression
        result = translator.translate(
            AnyExpression(
                source=ListExpression(elements=[Literal(value=1), Literal(value=2), Literal(value=3)]),
                alias="X",
                condition=BinaryExpression(operator=">", left=Identifier(name="X"), right=Literal(value=1))
            )
        )
        assert isinstance(result, SQLFunctionCall)
        assert result.name == "LIST_ANY"
        assert len(result.args) == 3
        assert result.args[1].value == "X"

    def test_all_expression(self, translator: ExpressionTranslator):
        """Test all expression: all X where condition -> list_all(arr, alias, condition)."""
        from ...parser.ast_nodes import ListExpression
        result = translator.translate(
            AllExpression(
                source=ListExpression(elements=[Literal(value=1), Literal(value=2), Literal(value=3)]),
                alias="X",
                condition=BinaryExpression(operator=">", left=Identifier(name="X"), right=Literal(value=0))
            )
        )
        assert isinstance(result, SQLFunctionCall)
        assert result.name == "LIST_ALL"
        assert len(result.args) == 3
        assert result.args[1].value == "X"


class TestPredecessorSuccessor:
    """Tests for predecessor/successor ordinal operator translation."""

    @pytest.fixture
    def translator(self) -> ExpressionTranslator:
        """Create an ExpressionTranslator instance for testing."""
        context = SQLTranslationContext()
        return ExpressionTranslator(context)

    def test_predecessor_of_integer(self, translator: ExpressionTranslator):
        """Test predecessor of integer: predecessor of 5 -> predecessorOf(5)."""
        result = translator.translate(
            UnaryExpression(
                operator="predecessor of",
                operand=Literal(value=5),
            )
        )
        assert isinstance(result, SQLFunctionCall)
        assert result.name == "predecessorOf"
        assert len(result.args) == 1
        assert result.args[0].value == 5

    def test_successor_of_integer(self, translator: ExpressionTranslator):
        """Test successor of integer: successor of 5 -> successorOf(5)."""
        result = translator.translate(
            UnaryExpression(
                operator="successor of",
                operand=Literal(value=5),
            )
        )
        assert isinstance(result, SQLFunctionCall)
        assert result.name == "successorOf"
        assert len(result.args) == 1
        assert result.args[0].value == 5

    def test_predecessor_of_zero(self, translator: ExpressionTranslator):
        """Test predecessor of zero: predecessor of 0 -> predecessorOf(0)."""
        result = translator.translate(
            UnaryExpression(
                operator="predecessor of",
                operand=Literal(value=0),
            )
        )
        assert isinstance(result, SQLFunctionCall)
        assert result.name == "predecessorOf"
        assert len(result.args) == 1
        assert result.args[0].value == 0

    def test_successor_of_negative(self, translator: ExpressionTranslator):
        """Test successor of negative: successor of -1 -> successorOf(-1)."""
        result = translator.translate(
            UnaryExpression(
                operator="successor of",
                operand=Literal(value=-1),
            )
        )
        assert isinstance(result, SQLFunctionCall)
        assert result.name == "successorOf"
        assert len(result.args) == 1
        assert result.args[0].value == -1

    def test_predecessor_of_identifier(self, translator: ExpressionTranslator):
        """Test predecessor of identifier: predecessor of X -> predecessorOf(X)."""
        result = translator.translate(
            UnaryExpression(
                operator="predecessor of",
                operand=Identifier(name="X"),
            )
        )
        assert isinstance(result, SQLFunctionCall)
        assert result.name == "predecessorOf"
        assert len(result.args) == 1
        assert isinstance(result.args[0], SQLIdentifier)
        assert result.args[0].name == "X"

    def test_successor_of_identifier(self, translator: ExpressionTranslator):
        """Test successor of identifier: successor of X -> successorOf(X)."""
        result = translator.translate(
            UnaryExpression(
                operator="successor of",
                operand=Identifier(name="X"),
            )
        )
        assert isinstance(result, SQLFunctionCall)
        assert result.name == "successorOf"
        assert len(result.args) == 1
        assert isinstance(result.args[0], SQLIdentifier)
        assert result.args[0].name == "X"


class TestStatisticalFunctions:
    """Tests for statistical function translation."""

    @pytest.fixture
    def translator(self) -> ExpressionTranslator:
        """Create an ExpressionTranslator instance for testing."""
        context = SQLTranslationContext()
        return ExpressionTranslator(context)

    def test_median_function(self, translator: ExpressionTranslator):
        """Test Median function: Median(values) -> MEDIAN(...)."""
        from ...parser.ast_nodes import FunctionRef, ListExpression
        result = translator.translate(
            FunctionRef(
                name="Median",
                arguments=[
                    ListExpression(elements=[Literal(value=1), Literal(value=2), Literal(value=3)])
                ]
            )
        )
        assert isinstance(result, SQLFunctionCall)
        # List literal → list_aggregate (DuckDB's MEDIAN is a column aggregate)
        assert result.name == "list_aggregate"
        assert len(result.args) == 2

    def test_mode_function(self, translator: ExpressionTranslator):
        """Test Mode function: Mode(values) -> list_aggregate(values, 'mode')."""
        from ...parser.ast_nodes import FunctionRef, ListExpression
        result = translator.translate(
            FunctionRef(
                name="Mode",
                arguments=[
                    ListExpression(elements=[Literal(value=1), Literal(value=2), Literal(value=2), Literal(value=3)])
                ]
            )
        )
        assert isinstance(result, SQLFunctionCall)
        assert result.name == "list_aggregate"
        assert len(result.args) == 2

    def test_variance_function(self, translator: ExpressionTranslator):
        """Test Variance function: Variance(values) -> list_aggregate(..., 'var_samp')."""
        from ...parser.ast_nodes import FunctionRef, ListExpression
        result = translator.translate(
            FunctionRef(
                name="Variance",
                arguments=[
                    ListExpression(elements=[Literal(value=1), Literal(value=2), Literal(value=3), Literal(value=4)])
                ]
            )
        )
        assert isinstance(result, SQLFunctionCall)
        assert result.name == "list_aggregate"
        assert len(result.args) == 2
        assert "'var_samp'" in result.to_sql()

    def test_stddev_function(self, translator: ExpressionTranslator):
        """Test StdDev function: StdDev(values) -> list_aggregate(..., 'stddev_samp')."""
        from ...parser.ast_nodes import FunctionRef, ListExpression
        result = translator.translate(
            FunctionRef(
                name="StdDev",
                arguments=[
                    ListExpression(elements=[Literal(value=1), Literal(value=2), Literal(value=3)])
                ]
            )
        )
        assert isinstance(result, SQLFunctionCall)
        assert result.name == "list_aggregate"
        assert len(result.args) == 2
        assert "'stddev_samp'" in result.to_sql()

    def test_population_variance_function(self, translator: ExpressionTranslator):
        """Test PopulationVariance function -> list_aggregate(..., 'var_pop')."""
        from ...parser.ast_nodes import FunctionRef, ListExpression
        result = translator.translate(
            FunctionRef(
                name="PopulationVariance",
                arguments=[
                    ListExpression(elements=[Literal(value=1), Literal(value=2), Literal(value=3)])
                ]
            )
        )
        assert isinstance(result, SQLFunctionCall)
        assert result.name == "list_aggregate"
        assert len(result.args) == 2
        assert "'var_pop'" in result.to_sql()

    def test_population_stddev_function(self, translator: ExpressionTranslator):
        """Test PopulationStdDev function -> list_aggregate(..., 'stddev_pop')."""
        from ...parser.ast_nodes import FunctionRef, ListExpression
        result = translator.translate(
            FunctionRef(
                name="PopulationStdDev",
                arguments=[
                    ListExpression(elements=[Literal(value=1), Literal(value=2), Literal(value=3)])
                ]
            )
        )
        assert isinstance(result, SQLFunctionCall)
        assert result.name == "list_aggregate"
        assert len(result.args) == 2
        assert "'stddev_pop'" in result.to_sql()


class TestOrdinalFunctions:
    """Tests for ordinal function translation (predecessor, successor)."""

    @pytest.fixture
    def translator(self) -> ExpressionTranslator:
        """Create an ExpressionTranslator instance for testing."""
        context = SQLTranslationContext()
        return ExpressionTranslator(context)

    def test_predecessor_of_integer(self, translator: ExpressionTranslator):
        """Test predecessor of integer: predecessor of 5 -> predecessorOf(5)."""
        result = translator.translate(
            UnaryExpression(operator="predecessor of", operand=Literal(value=5))
        )
        assert isinstance(result, SQLFunctionCall)
        assert result.name == "predecessorOf"
        assert len(result.args) == 1
        assert result.args[0].value == 5

    def test_successor_of_integer(self, translator: ExpressionTranslator):
        """Test successor of integer: successor of 5 -> successorOf(5)."""
        result = translator.translate(
            UnaryExpression(operator="successor of", operand=Literal(value=5))
        )
        assert isinstance(result, SQLFunctionCall)
        assert result.name == "successorOf"
        assert len(result.args) == 1
        assert result.args[0].value == 5

    def test_predecessor_of_identifier(self, translator: ExpressionTranslator):
        """Test predecessor of identifier: predecessor of X -> predecessorOf(X)."""
        result = translator.translate(
            UnaryExpression(operator="predecessor of", operand=Identifier(name="X"))
        )
        assert isinstance(result, SQLFunctionCall)
        assert result.name == "predecessorOf"
        assert len(result.args) == 1
        assert isinstance(result.args[0], SQLIdentifier)
        assert result.args[0].name == "X"

    def test_successor_of_identifier(self, translator: ExpressionTranslator):
        """Test successor of identifier: successor of X -> successorOf(X)."""
        result = translator.translate(
            UnaryExpression(operator="successor of", operand=Identifier(name="X"))
        )
        assert isinstance(result, SQLFunctionCall)
        assert result.name == "successorOf"
        assert len(result.args) == 1
        assert isinstance(result.args[0], SQLIdentifier)
        assert result.args[0].name == "X"


class TestSpecialAggregateFunctions:
    """Tests for special aggregate function translation (GeometricMean, Product)."""

    @pytest.fixture
    def translator(self) -> ExpressionTranslator:
        """Create an ExpressionTranslator instance for testing."""
        context = SQLTranslationContext()
        return ExpressionTranslator(context)

    def test_geometric_mean(self, translator: ExpressionTranslator):
        """Test GeometricMean: GeometricMean([2, 8]) -> EXP(AVG(LOG(source)))."""
        from ...parser.ast_nodes import AggregateExpression, ListExpression
        result = translator.translate(
            AggregateExpression(
                source=ListExpression(elements=[Literal(value=2), Literal(value=8)]),
                operator="GeometricMean"
            )
        )
        # Should produce EXP(AVG(LOG(source)))
        assert isinstance(result, SQLFunctionCall)
        assert result.name == "EXP"
        assert len(result.args) == 1
        # Inner should be AVG
        inner = result.args[0]
        assert isinstance(inner, SQLFunctionCall)
        assert inner.name == "AVG"
        # Innermost should be LOG
        log_call = inner.args[0]
        assert isinstance(log_call, SQLFunctionCall)
        assert log_call.name == "LOG"

    def test_geometric_mean_lowercase(self, translator: ExpressionTranslator):
        """Test GeometricMean with lowercase operator name."""
        from ...parser.ast_nodes import AggregateExpression, ListExpression
        result = translator.translate(
            AggregateExpression(
                source=ListExpression(elements=[Literal(value=2), Literal(value=8)]),
                operator="geometricmean"
            )
        )
        assert isinstance(result, SQLFunctionCall)
        assert result.name == "EXP"

    def test_product(self, translator: ExpressionTranslator):
        """Test Product: Product([2, 3, 4]) -> EXP(SUM(LOG(source)))."""
        from ...parser.ast_nodes import AggregateExpression, ListExpression
        result = translator.translate(
            AggregateExpression(
                source=ListExpression(elements=[Literal(value=2), Literal(value=3), Literal(value=4)]),
                operator="Product"
            )
        )
        # Should produce EXP(SUM(LOG(source)))
        assert isinstance(result, SQLFunctionCall)
        assert result.name == "EXP"
        assert len(result.args) == 1
        # Inner should be SUM
        inner = result.args[0]
        assert isinstance(inner, SQLFunctionCall)
        assert inner.name == "SUM"
        # Innermost should be LOG
        log_call = inner.args[0]
        assert isinstance(log_call, SQLFunctionCall)
        assert log_call.name == "LOG"

    def test_product_lowercase(self, translator: ExpressionTranslator):
        """Test Product with lowercase operator name."""
        from ...parser.ast_nodes import AggregateExpression, ListExpression
        result = translator.translate(
            AggregateExpression(
                source=ListExpression(elements=[Literal(value=2), Literal(value=3), Literal(value=4)]),
                operator="product"
            )
        )
        assert isinstance(result, SQLFunctionCall)
        assert result.name == "EXP"

    def test_geometric_mean_sql_output(self, translator: ExpressionTranslator):
        """Test GeometricMean produces correct SQL string."""
        from ...parser.ast_nodes import AggregateExpression, ListExpression
        result = translator.translate(
            AggregateExpression(
                source=ListExpression(elements=[Literal(value=2), Literal(value=8)]),
                operator="GeometricMean"
            )
        )
        sql = result.to_sql()
        assert "EXP" in sql
        assert "AVG" in sql
        assert "LOG" in sql

    def test_product_sql_output(self, translator: ExpressionTranslator):
        """Test Product produces correct SQL string."""
        from ...parser.ast_nodes import AggregateExpression, ListExpression
        result = translator.translate(
            AggregateExpression(
                source=ListExpression(elements=[Literal(value=2), Literal(value=3)]),
                operator="Product"
            )
        )
        sql = result.to_sql()
        assert "EXP" in sql
        assert "SUM" in sql
        assert "LOG" in sql


class TestStringPositionFunctions:
    """Tests for string position function translation (PositionOf, LastPositionOf)."""

    @pytest.fixture
    def translator(self) -> ExpressionTranslator:
        """Create an ExpressionTranslator instance for testing."""
        context = SQLTranslationContext()
        return ExpressionTranslator(context)

    def test_position_of(self, translator: ExpressionTranslator):
        """Test PositionOf function: PositionOf('lo', 'hello') -> CASE WHEN strpos=0 THEN -1 ELSE strpos-1 END."""
        from ...parser.ast_nodes import FunctionRef
        from ...translator.types import SQLCase
        result = translator.translate(
            FunctionRef(
                name="PositionOf",
                arguments=[
                    Literal(value="lo"),
                    Literal(value="hello"),
                ]
            )
        )
        # PositionOf now returns SQLCase for proper 0-based indexing (CQL semantics)
        assert isinstance(result, SQLCase)
        # When not found (strpos=0), returns -1; otherwise returns strpos-1 for 0-based index

    def test_position_of_not_found(self, translator: ExpressionTranslator):
        """Test PositionOf when substring not found returns -1 (CQL 0-based semantics)."""
        from ...parser.ast_nodes import FunctionRef
        from ...translator.types import SQLCase, SQLLiteral
        result = translator.translate(
            FunctionRef(
                name="PositionOf",
                arguments=[
                    Literal(value="xyz"),
                    Literal(value="hello"),
                ]
            )
        )
        # PositionOf now returns SQLCase - returns -1 when not found
        assert isinstance(result, SQLCase)
        # The when clause checks strpos=0 and returns -1
        assert result.when_clauses[0][1].value == -1

    def test_last_position_of(self, translator: ExpressionTranslator):
        """Test LastPositionOf function: LastPositionOf('l', 'hello') -> UDF call."""
        from ...parser.ast_nodes import FunctionRef
        result = translator.translate(
            FunctionRef(
                name="LastPositionOf",
                arguments=[
                    Literal(value="l"),
                    Literal(value="hello"),
                ]
            )
        )
        assert isinstance(result, SQLFunctionCall)
        assert result.name == "LastPositionOf"

    def test_last_position_of_multiple_occurrences(self, translator: ExpressionTranslator):
        """Test LastPositionOf with multiple occurrences finds last one."""
        from ...parser.ast_nodes import FunctionRef
        result = translator.translate(
            FunctionRef(
                name="LastPositionOf",
                arguments=[
                    Literal(value="o"),
                    Literal(value="hello world"),
                ]
            )
        )
        assert isinstance(result, SQLFunctionCall)
        assert result.name == "LastPositionOf"

    def test_position_of_case_insensitive(self, translator: ExpressionTranslator):
        """Test PositionOf function name is case-insensitive."""
        from ...parser.ast_nodes import FunctionRef
        from ...translator.types import SQLCase
        for name in ["PositionOf", "positionof", "POSITIONOF"]:
            result = translator.translate(
                FunctionRef(
                    name=name,
                    arguments=[
                        Literal(value="a"),
                        Literal(value="abc"),
                    ]
                )
            )
            # PositionOf now returns SQLCase for proper 0-based indexing
            assert isinstance(result, SQLCase)

    def test_last_position_of_case_insensitive(self, translator: ExpressionTranslator):
        """Test LastPositionOf function name is case-insensitive."""
        from ...parser.ast_nodes import FunctionRef
        for name in ["LastPositionOf", "lastpositionof", "LASTPOSITIONOF"]:
            result = translator.translate(
                FunctionRef(
                    name=name,
                    arguments=[
                        Literal(value="a"),
                        Literal(value="abc"),
                    ]
                )
            )
            assert isinstance(result, SQLFunctionCall)
            assert result.name == "LastPositionOf"

    def test_position_of_with_identifiers(self, translator: ExpressionTranslator):
        """Test PositionOf with identifier arguments."""
        from ...parser.ast_nodes import FunctionRef
        from ...translator.types import SQLCase
        result = translator.translate(
            FunctionRef(
                name="PositionOf",
                arguments=[
                    Identifier(name="substr"),
                    Identifier(name="source"),
                ]
            )
        )
        # PositionOf now returns SQLCase for proper 0-based indexing
        assert isinstance(result, SQLCase)


class TestTimezoneOffset:
    """Tests for timezoneoffset date component extraction."""

    @pytest.fixture
    def translator(self) -> ExpressionTranslator:
        """Create an ExpressionTranslator instance for testing."""
        context = SQLTranslationContext()
        return ExpressionTranslator(context)

    def test_timezoneoffset_from_datetime(self, translator: ExpressionTranslator):
        """Test timezoneoffset from dateTime returns UDF call."""
        from ...parser.ast_nodes import DateComponent
        result = translator.translate(
            DateComponent(component="timezoneoffset", operand=DateTimeLiteral(value="2024-01-15T10:30:00"))
        )
        assert isinstance(result, SQLFunctionCall)
        assert result.name == "cqlTimezoneOffset"

    def test_timezoneoffset_case_insensitive(self, translator: ExpressionTranslator):
        """Test timezoneoffset is case-insensitive."""
        from ...parser.ast_nodes import DateComponent
        for component in ["timezoneoffset", "TimeZoneOffset", "TIMEZONEOFFSET"]:
            result = translator.translate(
                DateComponent(component=component, operand=DateTimeLiteral(value="2024-01-15"))
            )
            assert isinstance(result, SQLFunctionCall)
            assert result.name == "cqlTimezoneOffset"

    def test_timezoneoffset_with_identifier(self, translator: ExpressionTranslator):
        """Test timezoneoffset from identifier returns UDF call."""
        from ...parser.ast_nodes import DateComponent
        result = translator.translate(
            DateComponent(component="timezoneoffset", operand=Identifier(name="someDateTime"))
        )
        assert isinstance(result, SQLFunctionCall)
        assert result.name == "cqlTimezoneOffset"


class TestIntervalCollapseExpand:
    """Tests for interval collapse and expand functions."""

    @pytest.fixture
    def translator(self) -> ExpressionTranslator:
        """Create an ExpressionTranslator instance for testing."""
        context = SQLTranslationContext()
        return ExpressionTranslator(context)

    def test_collapse_intervals(self, translator: ExpressionTranslator):
        """Test collapse function: collapse intervals -> collapse(...)."""
        from ...parser.ast_nodes import FunctionRef, ListExpression
        result = translator.translate(
            FunctionRef(
                name="collapse",
                arguments=[
                    ListExpression(elements=[
                        Interval(
                            low=Literal(value=1),
                            high=Literal(value=5),
                            low_closed=True,
                            high_closed=True,
                        ),
                        Interval(
                            low=Literal(value=3),
                            high=Literal(value=10),
                            low_closed=True,
                            high_closed=True,
                        ),
                    ])
                ]
            )
        )
        assert isinstance(result, SQLFunctionCall)
        assert result.name == "collapse_intervals"
        assert len(result.args) == 1

    def test_expand_interval(self, translator: ExpressionTranslator):
        """Test expand function: expand interval -> expand UDF call."""
        from ...parser.ast_nodes import FunctionRef
        result = translator.translate(
            FunctionRef(
                name="expand",
                arguments=[
                    Interval(
                        low=Literal(value=1),
                        high=Literal(value=5),
                        low_closed=True,
                        high_closed=True,
                    ),
                ]
            )
        )
        assert isinstance(result, SQLFunctionCall)
        # expand may use expand_points1 or expand internally
        assert "expand" in result.name.lower()

    def test_expand_interval_with_per(self, translator: ExpressionTranslator):
        """Test expand function with per quantity."""
        from ...parser.ast_nodes import FunctionRef, Quantity
        result = translator.translate(
            FunctionRef(
                name="expand",
                arguments=[
                    Interval(
                        low=DateTimeLiteral(value="2024-01-01"),
                        high=DateTimeLiteral(value="2024-01-31"),
                        low_closed=True,
                        high_closed=True,
                    ),
                    Quantity(value=1, unit="day"),
                ]
            )
        )
        assert isinstance(result, SQLFunctionCall)
        assert "expand" in result.name.lower()

    def test_collapse_case_insensitive(self, translator: ExpressionTranslator):
        """Test collapse function name is case-insensitive."""
        from ...parser.ast_nodes import FunctionRef, ListExpression
        for name in ["collapse", "Collapse", "COLLAPSE"]:
            result = translator.translate(
                FunctionRef(
                    name=name,
                    arguments=[
                        ListExpression(elements=[])
                    ]
                )
            )
            assert isinstance(result, SQLFunctionCall)

    def test_expand_case_insensitive(self, translator: ExpressionTranslator):
        """Test expand function name is case-insensitive."""
        from ...parser.ast_nodes import FunctionRef
        for name in ["expand", "Expand", "EXPAND"]:
            result = translator.translate(
                FunctionRef(
                    name=name,
                    arguments=[
                        Interval(
                            low=Literal(value=1),
                            high=Literal(value=5),
                            low_closed=True,
                            high_closed=True,
                        ),
                    ]
                )
            )
            assert isinstance(result, SQLFunctionCall)


class TestPatientCorrelation:
    """Test that retrieve returns placeholders (patient correlation is in CTE builder)."""

    @pytest.fixture
    def context(self) -> SQLTranslationContext:
        """Create a fresh context for each test."""
        return SQLTranslationContext()

    @pytest.fixture
    def translator(self, context: SQLTranslationContext) -> ExpressionTranslator:
        """Create an ExpressionTranslator instance for testing."""
        return ExpressionTranslator(context)

    def test_retrieve_returns_placeholder(self, translator: ExpressionTranslator):
        """Test that retrieve returns a RetrievePlaceholder."""
        from ...translator.placeholder import RetrievePlaceholder

        retrieve_node = Retrieve(type="Condition", terminology=None)
        result = translator.translate(retrieve_node)

        assert isinstance(result, RetrievePlaceholder)
        assert result.resource_type == "Condition"
        assert result.valueset is None

    def test_retrieve_with_valueset_returns_placeholder(self, context: SQLTranslationContext):
        """Test that retrieve with valueset returns placeholder with valueset."""
        from ...translator.placeholder import RetrievePlaceholder

        context.valuesets["Diabetes"] = "http://example.com/ValueSet/Diabetes"
        translator = ExpressionTranslator(context)

        retrieve_node = Retrieve(type="Condition", terminology="Diabetes")
        result = translator.translate(retrieve_node)

        assert isinstance(result, RetrievePlaceholder)
        assert result.resource_type == "Condition"
        assert result.valueset == "http://example.com/ValueSet/Diabetes"

    def test_placeholder_key_is_unique(self, translator: ExpressionTranslator):
        """Test that placeholder key uniquely identifies retrieve."""
        from ...translator.placeholder import RetrievePlaceholder

        retrieve_node = Retrieve(type="Observation", terminology=None)
        result = translator.translate(retrieve_node)

        assert isinstance(result, RetrievePlaceholder)
        assert result.key == ("Observation", None, None)

    def test_placeholder_with_valueset_key(self, context: SQLTranslationContext):
        """Test placeholder key with valueset."""
        from ...translator.placeholder import RetrievePlaceholder

        context.valuesets["BP"] = "http://example.com/ValueSet/BP"
        translator = ExpressionTranslator(context)

        retrieve_node = Retrieve(type="Observation", terminology="BP")
        result = translator.translate(retrieve_node)

        assert isinstance(result, RetrievePlaceholder)
        assert result.key == ("Observation", "http://example.com/ValueSet/BP", None)


class TestDuringOperatorNullHandling:
    """Tests for 'during precision of' operator with NULL end date handling.

    Tests that COALESCE is applied to handle NULL end dates in intervals,
    which can occur when a Period is ongoing (no end date specified).
    """

    @pytest.fixture
    def translator(self) -> ExpressionTranslator:
        """Create an ExpressionTranslator instance for testing."""
        context = SQLTranslationContext()
        return ExpressionTranslator(context)

    def test_during_day_of_uses_boundary_comparisons(self, translator: ExpressionTranslator):
        """Test 'during day of' uses boundary-aware AND comparisons (Gap 11)."""
        result = translator.translate(
            BinaryExpression(
                operator="during day of",
                left=DateTimeLiteral(value="2024-06-15"),
                right=Interval(
                    low=DateTimeLiteral(value="2024-01-01"),
                    high=DateTimeLiteral(value="2024-12-31"),
                    low_closed=True,
                    high_closed=True,
                ),
            )
        )

        # Gap 11: Result should be AND (not BETWEEN) for boundary awareness
        assert isinstance(result, SQLBinaryOp)
        assert result.operator == "AND"
        # For closed-closed [A, B], use >= and <=
        assert isinstance(result.left, SQLBinaryOp)
        assert result.left.operator == ">="
        assert isinstance(result.right, SQLBinaryOp)
        assert result.right.operator == "<="

    def test_during_month_of_uses_boundary_comparisons(self, translator: ExpressionTranslator):
        """Test 'during month of' uses boundary-aware AND comparisons (Gap 11)."""
        result = translator.translate(
            BinaryExpression(
                operator="during month of",
                left=DateTimeLiteral(value="2024-06-15"),
                right=Interval(
                    low=DateTimeLiteral(value="2024-01-01"),
                    high=DateTimeLiteral(value="2024-12-31"),
                    low_closed=True,
                    high_closed=True,
                ),
            )
        )

        # Gap 11: Result should be AND for boundary awareness
        assert isinstance(result, SQLBinaryOp)
        assert result.operator == "AND"

    def test_during_year_of_uses_boundary_comparisons(self, translator: ExpressionTranslator):
        """Test 'during year of' uses boundary-aware AND comparisons (Gap 11)."""
        result = translator.translate(
            BinaryExpression(
                operator="during year of",
                left=DateTimeLiteral(value="2024-06-15"),
                right=Interval(
                    low=DateTimeLiteral(value="2024-01-01"),
                    high=DateTimeLiteral(value="2024-12-31"),
                    low_closed=True,
                    high_closed=True,
                ),
            )
        )

        # Gap 11: Result should be AND for boundary awareness
        assert isinstance(result, SQLBinaryOp)
        assert result.operator == "AND"

    def test_during_half_open_uses_less_than(self, translator: ExpressionTranslator):
        """Test 'during day of' with half-open [A, B) uses < for end (Gap 11)."""
        result = translator.translate(
            BinaryExpression(
                operator="during day of",
                left=DateTimeLiteral(value="2024-06-15"),
                right=Interval(
                    low=DateTimeLiteral(value="2024-01-01"),
                    high=DateTimeLiteral(value="2024-12-31"),
                    low_closed=True,
                    high_closed=False,  # Half-open
                ),
            )
        )

        # Gap 11: Half-open end should use < not <=
        assert isinstance(result, SQLBinaryOp)
        assert result.operator == "AND"
        assert result.left.operator == ">="
        assert result.right.operator == "<"  # NOT <= because high_closed=False

    def test_during_without_precision_uses_intervalcontains(
        self, translator: ExpressionTranslator
    ):
        """Test 'during' without precision uses intervalContains UDF (no COALESCE)."""
        result = translator.translate(
            BinaryExpression(
                operator="during",
                left=DateTimeLiteral(value="2024-06-15"),
                right=Interval(
                    low=DateTimeLiteral(value="2024-01-01"),
                    high=DateTimeLiteral(value="2024-12-31"),
                    low_closed=True,
                    high_closed=True,
                ),
            )
        )

        # Without precision, should use intervalContains
        assert isinstance(result, SQLFunctionCall)
        assert result.name == "intervalContains"

    def test_during_hour_of_uses_boundary_comparisons(self, translator: ExpressionTranslator):
        """Test 'during hour of' uses boundary-aware AND comparisons (Gap 11)."""
        result = translator.translate(
            BinaryExpression(
                operator="during hour of",
                left=DateTimeLiteral(value="2024-06-15T10:30:00"),
                right=Interval(
                    low=DateTimeLiteral(value="2024-06-15T08:00:00"),
                    high=DateTimeLiteral(value="2024-06-15T18:00:00"),
                    low_closed=True,
                    high_closed=True,
                ),
            )
        )

        # Gap 11: Result should be AND for boundary awareness
        assert isinstance(result, SQLBinaryOp)
        assert result.operator == "AND"

