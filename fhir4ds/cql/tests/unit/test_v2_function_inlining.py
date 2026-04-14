"""
Unit tests for FunctionInliner class.

Tests the function inlining and cycle detection capabilities of the
CQL to SQL translator's function inliner.

Key test cases:
- Simple function inlining
- Nested function inlining
- Direct cycle detection
- Indirect cycle detection
- Library prefixing
- Parameter substitution
- Expression tree substitution
"""

import pytest

from ...parser.ast_nodes import (
    BinaryExpression,
    FunctionRef,
    Identifier,
    Literal,
)
from ...translator.context import SQLTranslationContext
from ...translator.function_inliner import (
    FunctionDef,
    FunctionInliner,
    ParameterPlaceholder,
    TranslationError,
)
from ...translator.types import SQLLiteral


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def context() -> SQLTranslationContext:
    """Create a fresh translation context for each test."""
    return SQLTranslationContext()


@pytest.fixture
def inliner(context: SQLTranslationContext) -> FunctionInliner:
    """Create a function inliner with a fresh context."""
    return FunctionInliner(context)


# =============================================================================
# Helper Functions
# =============================================================================


def make_double_function() -> FunctionDef:
    """Create a simple Double function: define function "Double"(x): x * 2"""
    return FunctionDef(
        name="Double",
        parameters=[("x", "Integer")],
        return_type="Integer",
        body=BinaryExpression(
            operator="*",
            left=Identifier(name="x"),
            right=Literal(value=2),
        ),
    )


def make_quadruple_function() -> FunctionDef:
    """Create Quadruple function: define function "Quadruple"(x): Double(Double(x))"""
    return FunctionDef(
        name="Quadruple",
        parameters=[("x", "Integer")],
        return_type="Integer",
        body=FunctionRef(
            name="Double",
            arguments=[
                FunctionRef(
                    name="Double",
                    arguments=[Identifier(name="x")],
                )
            ],
        ),
    )


def make_recursive_function_a() -> FunctionDef:
    """Create a directly recursive function: define function "A"(x): A(x)"""
    return FunctionDef(
        name="A",
        parameters=[("x", "Integer")],
        return_type="Integer",
        body=FunctionRef(
            name="A",
            arguments=[Identifier(name="x")],
        ),
    )


def make_cycle_function_a() -> FunctionDef:
    """Create function A that calls B: define function "A"(x): B(x)"""
    return FunctionDef(
        name="A",
        parameters=[("x", "Integer")],
        return_type="Integer",
        body=FunctionRef(
            name="B",
            arguments=[Identifier(name="x")],
        ),
    )


def make_cycle_function_b() -> FunctionDef:
    """Create function B that calls C: define function "B"(x): C(x)"""
    return FunctionDef(
        name="B",
        parameters=[("x", "Integer")],
        return_type="Integer",
        body=FunctionRef(
            name="C",
            arguments=[Identifier(name="x")],
        ),
    )


def make_cycle_function_c() -> FunctionDef:
    """Create function C that calls A: define function "C"(x): A(x)"""
    return FunctionDef(
        name="C",
        parameters=[("x", "Integer")],
        return_type="Integer",
        body=FunctionRef(
            name="A",
            arguments=[Identifier(name="x")],
        ),
    )


# =============================================================================
# Test: Simple Inline
# =============================================================================


class TestSimpleInline:
    """Tests for simple function inlining."""

    def test_simple_inline_basic(self, inliner: FunctionInliner, context: SQLTranslationContext):
        """Test that Double(5) inlines to 5 * 2."""
        # Register the Double function
        inliner.register_function(make_double_function())

        # Inline Double(5)
        args = [SQLLiteral(value=5)]
        result = inliner.inline_function("Double", args, context)

        # Result should be 5 * 2 = 10
        sql = result.to_sql()
        assert "5" in sql
        assert "*" in sql
        assert "2" in sql

    def test_simple_inline_with_identifier(self, inliner: FunctionInliner, context: SQLTranslationContext):
        """Test inlining with identifier argument."""
        inliner.register_function(make_double_function())

        # Inline Double(someVar)
        args = [SQLLiteral(value="someVar")]  # Using SQLLiteral to represent the arg
        result = inliner.inline_function("Double", args, context)

        sql = result.to_sql()
        assert "*" in sql
        assert "2" in sql

    def test_simple_inline_preserves_literal_value(self, inliner: FunctionInliner, context: SQLTranslationContext):
        """Test that literal values are correctly substituted."""
        inliner.register_function(make_double_function())

        # Test with different values
        for value in [0, 1, 10, 100, -5]:
            args = [SQLLiteral(value=value)]
            result = inliner.inline_function("Double", args, context)
            sql = result.to_sql()
            assert str(value) in sql


# =============================================================================
# Test: Nested Inline
# =============================================================================


class TestNestedInline:
    """Tests for nested function inlining."""

    def test_nested_inline_basic(self, inliner: FunctionInliner, context: SQLTranslationContext):
        """Test that Quadruple(5) inlines nested Double calls."""
        # Register both functions
        inliner.register_function(make_double_function())
        inliner.register_function(make_quadruple_function())

        # Inline Quadruple(5) -> Double(Double(5)) -> (5 * 2) * 2
        args = [SQLLiteral(value=5)]
        result = inliner.inline_function("Quadruple", args, context)

        sql = result.to_sql()
        # Should contain multiplication by 2 twice
        assert "*" in sql
        assert "2" in sql

    def test_nested_inline_multiple_levels(self, inliner: FunctionInliner, context: SQLTranslationContext):
        """Test inlining with multiple levels of nesting."""
        # Double function
        inliner.register_function(make_double_function())

        # Quadruple: Double(Double(x))
        inliner.register_function(make_quadruple_function())

        # Octuple: Quadruple(Double(x)) - 8x
        octuple_func = FunctionDef(
            name="Octuple",
            parameters=[("x", "Integer")],
            return_type="Integer",
            body=FunctionRef(
                name="Quadruple",
                arguments=[
                    FunctionRef(
                        name="Double",
                        arguments=[Identifier(name="x")],
                    )
                ],
            ),
        )
        inliner.register_function(octuple_func)

        # Inline Octuple(5) -> should have many * 2 operations
        args = [SQLLiteral(value=5)]
        result = inliner.inline_function("Octuple", args, context)

        sql = result.to_sql()
        # Should contain multiplication
        assert "*" in sql


# =============================================================================
# Test: Direct Cycle Detection
# =============================================================================


class TestCycleDetectionDirect:
    """Tests for direct cycle (self-recursion) detection."""

    def test_direct_cycle_raises_error(self, inliner: FunctionInliner, context: SQLTranslationContext):
        """Test that directly recursive function raises TranslationError."""
        # Register A that calls itself
        inliner.register_function(make_recursive_function_a())

        # Attempting to inline A(5) should raise error
        args = [SQLLiteral(value=5)]
        with pytest.raises(TranslationError) as exc_info:
            inliner.inline_function("A", args, context)

        # Error message should mention cycle
        assert "Cycle" in str(exc_info.value) or "cycle" in str(exc_info.value)

    def test_direct_cycle_error_contains_function_name(self, inliner: FunctionInliner, context: SQLTranslationContext):
        """Test that cycle error includes the function name in the cycle path."""
        inliner.register_function(make_recursive_function_a())

        args = [SQLLiteral(value=5)]
        with pytest.raises(TranslationError) as exc_info:
            inliner.inline_function("A", args, context)

        # Error should show the cycle path including A
        error_msg = str(exc_info.value)
        assert "A" in error_msg

    def test_detect_cycles_method_finds_direct_cycle(self, inliner: FunctionInliner):
        """Test that detect_cycles() finds direct cycles."""
        inliner.register_function(make_recursive_function_a())

        cycles = inliner.detect_cycles()

        # Should find exactly one cycle
        assert len(cycles) >= 1
        # The cycle should involve A
        cycle_functions = [func for cycle in cycles for func in cycle]
        assert "A" in cycle_functions


# =============================================================================
# Test: Indirect Cycle Detection
# =============================================================================


class TestCycleDetectionIndirect:
    """Tests for indirect cycle (A -> B -> C -> A) detection."""

    def test_indirect_cycle_raises_error(self, inliner: FunctionInliner, context: SQLTranslationContext):
        """Test that indirect cycle A -> B -> C -> A raises TranslationError."""
        # Register the mutually recursive functions
        inliner.register_function(make_cycle_function_a())
        inliner.register_function(make_cycle_function_b())
        inliner.register_function(make_cycle_function_c())

        # Attempting to inline A(5) should detect the cycle
        args = [SQLLiteral(value=5)]
        with pytest.raises(TranslationError) as exc_info:
            inliner.inline_function("A", args, context)

        # Error message should mention cycle
        assert "Cycle" in str(exc_info.value) or "cycle" in str(exc_info.value)

    def test_indirect_cycle_error_shows_path(self, inliner: FunctionInliner, context: SQLTranslationContext):
        """Test that cycle error shows the full cycle path."""
        inliner.register_function(make_cycle_function_a())
        inliner.register_function(make_cycle_function_b())
        inliner.register_function(make_cycle_function_c())

        args = [SQLLiteral(value=5)]
        with pytest.raises(TranslationError) as exc_info:
            inliner.inline_function("A", args, context)

        # Error should show the cycle involving A, B, C
        error_msg = str(exc_info.value)
        # At minimum, the error should mention cycle and some function names
        assert "A" in error_msg

    def test_detect_cycles_method_finds_indirect_cycle(self, inliner: FunctionInliner):
        """Test that detect_cycles() finds indirect cycles."""
        inliner.register_function(make_cycle_function_a())
        inliner.register_function(make_cycle_function_b())
        inliner.register_function(make_cycle_function_c())

        cycles = inliner.detect_cycles()

        # Should find at least one cycle
        assert len(cycles) >= 1

    def test_cycle_detection_at_different_entry_points(self, inliner: FunctionInliner, context: SQLTranslationContext):
        """Test that cycle is detected regardless of which function starts."""
        inliner.register_function(make_cycle_function_a())
        inliner.register_function(make_cycle_function_b())
        inliner.register_function(make_cycle_function_c())

        # Starting from B should also detect cycle
        args = [SQLLiteral(value=5)]
        with pytest.raises(TranslationError):
            inliner.inline_function("B", args, context)

        # Starting from C should also detect cycle
        with pytest.raises(TranslationError):
            inliner.inline_function("C", args, context)


# =============================================================================
# Test: Library Prefixing
# =============================================================================


class TestLibraryPrefixing:
    """Tests for library-prefixed function handling."""

    def test_library_function_registration(self, inliner: FunctionInliner):
        """Test registering a function with a library prefix."""
        func = FunctionDef(
            name="ToInterval",
            library_name="FHIRHelpers",
            parameters=[("p", "Period")],
            return_type="Interval",
            body=Identifier(name="p"),
        )

        inliner.register_function(func)

        # Should be able to retrieve with library prefix
        retrieved = inliner.get_function("ToInterval", "FHIRHelpers")
        assert retrieved is not None
        assert retrieved.name == "ToInterval"
        assert retrieved.library_name == "FHIRHelpers"

    def test_library_function_inline(self, inliner: FunctionInliner, context: SQLTranslationContext):
        """Test inlining a library-prefixed function call."""
        # Create a simple function in FHIRHelpers library
        func = FunctionDef(
            name="ToInterval",
            library_name="FHIRHelpers",
            parameters=[("period", "Period")],
            return_type="Interval",
            body=Identifier(name="period"),
        )
        inliner.register_function(func)

        # Inline FHIRHelpers.ToInterval(myPeriod)
        args = [SQLLiteral(value="myPeriod")]
        result = inliner.inline_function(
            "ToInterval",
            args,
            context,
            library_name="FHIRHelpers",
        )

        # Should return a result
        assert result is not None

    def test_separate_functions_same_name_different_libraries(self, inliner: FunctionInliner):
        """Test that functions with same name in different libraries are separate."""
        # Create Double in Library1
        lib1_func = FunctionDef(
            name="Double",
            library_name="Library1",
            parameters=[("x", "Integer")],
            body=BinaryExpression(
                operator="*",
                left=Identifier(name="x"),
                right=Literal(value=2),
            ),
        )

        # Create Double in Library2 with different multiplier
        lib2_func = FunctionDef(
            name="Double",
            library_name="Library2",
            parameters=[("x", "Integer")],
            body=BinaryExpression(
                operator="*",
                left=Identifier(name="x"),
                right=Literal(value=3),  # Different!
            ),
        )

        inliner.register_function(lib1_func)
        inliner.register_function(lib2_func)

        # Should retrieve different functions
        lib1_retrieved = inliner.get_function("Double", "Library1")
        lib2_retrieved = inliner.get_function("Double", "Library2")

        assert lib1_retrieved is not None
        assert lib2_retrieved is not None
        # They should have different bodies (different multipliers)
        lib1_body = lib1_retrieved.body
        lib2_body = lib2_retrieved.body
        # The right side of the binary expression should be different
        assert lib1_body.right.value == 2
        assert lib2_body.right.value == 3


# =============================================================================
# Test: Parameter Substitution
# =============================================================================


class TestParameterSubstitution:
    """Tests for parameter substitution during inlining."""

    def test_single_parameter_substitution(self, inliner: FunctionInliner, context: SQLTranslationContext):
        """Test substitution of a single parameter."""
        inliner.register_function(make_double_function())

        args = [SQLLiteral(value=42)]
        result = inliner.inline_function("Double", args, context)

        sql = result.to_sql()
        assert "42" in sql
        assert "*" in sql

    def test_multiple_parameter_substitution(self, inliner: FunctionInliner, context: SQLTranslationContext):
        """Test substitution of multiple parameters."""
        # Create Add(a, b) = a + b
        add_func = FunctionDef(
            name="Add",
            parameters=[("a", "Integer"), ("b", "Integer")],
            return_type="Integer",
            body=BinaryExpression(
                operator="+",
                left=Identifier(name="a"),
                right=Identifier(name="b"),
            ),
        )
        inliner.register_function(add_func)

        # Inline Add(10, 20)
        args = [SQLLiteral(value=10), SQLLiteral(value=20)]
        result = inliner.inline_function("Add", args, context)

        sql = result.to_sql()
        assert "10" in sql
        assert "20" in sql
        assert "+" in sql

    def test_three_parameter_substitution(self, inliner: FunctionInliner, context: SQLTranslationContext):
        """Test substitution with three parameters."""
        # Create Sum3(a, b, c) = a + b + c
        sum3_func = FunctionDef(
            name="Sum3",
            parameters=[("a", "Integer"), ("b", "Integer"), ("c", "Integer")],
            return_type="Integer",
            body=BinaryExpression(
                operator="+",
                left=BinaryExpression(
                    operator="+",
                    left=Identifier(name="a"),
                    right=Identifier(name="b"),
                ),
                right=Identifier(name="c"),
            ),
        )
        inliner.register_function(sum3_func)

        args = [SQLLiteral(value=1), SQLLiteral(value=2), SQLLiteral(value=3)]
        result = inliner.inline_function("Sum3", args, context)

        sql = result.to_sql()
        assert "1" in sql
        assert "2" in sql
        assert "3" in sql

    def test_parameter_used_multiple_times(self, inliner: FunctionInliner, context: SQLTranslationContext):
        """Test that a parameter used multiple times is substituted each time."""
        # Create Square(x) = x * x
        square_func = FunctionDef(
            name="Square",
            parameters=[("x", "Integer")],
            return_type="Integer",
            body=BinaryExpression(
                operator="*",
                left=Identifier(name="x"),
                right=Identifier(name="x"),
            ),
        )
        inliner.register_function(square_func)

        args = [SQLLiteral(value=7)]
        result = inliner.inline_function("Square", args, context)

        sql = result.to_sql()
        # 7 should appear twice (7 * 7)
        assert sql.count("7") >= 2


# =============================================================================
# Test: Expression Tree Substitution
# =============================================================================


class TestExpressionTreeSubstitution:
    """Tests for substitution in complex expression trees."""

    def test_nested_binary_expression(self, inliner: FunctionInliner, context: SQLTranslationContext):
        """Test substitution in nested binary expressions."""
        # Create Formula(a, b) = (a + b) * (a - b)
        formula_func = FunctionDef(
            name="Formula",
            parameters=[("a", "Integer"), ("b", "Integer")],
            return_type="Integer",
            body=BinaryExpression(
                operator="*",
                left=BinaryExpression(
                    operator="+",
                    left=Identifier(name="a"),
                    right=Identifier(name="b"),
                ),
                right=BinaryExpression(
                    operator="-",
                    left=Identifier(name="a"),
                    right=Identifier(name="b"),
                ),
            ),
        )
        inliner.register_function(formula_func)

        args = [SQLLiteral(value=10), SQLLiteral(value=5)]
        result = inliner.inline_function("Formula", args, context)

        sql = result.to_sql()
        # (10 + 5) * (10 - 5) = 75
        assert "10" in sql
        assert "5" in sql
        assert "+" in sql
        assert "-" in sql
        assert "*" in sql

    def test_function_call_in_body(self, inliner: FunctionInliner, context: SQLTranslationContext):
        """Test that nested function calls in body are properly inlined."""
        inliner.register_function(make_double_function())

        # Create Quadruple that uses Double
        inliner.register_function(make_quadruple_function())

        args = [SQLLiteral(value=3)]
        result = inliner.inline_function("Quadruple", args, context)

        # The result should have the nested calls inlined
        sql = result.to_sql()
        assert "*" in sql  # Should contain multiplication

    def test_conditional_expression_substitution(self, inliner: FunctionInliner, context: SQLTranslationContext):
        """Test substitution in conditional expressions."""
        from ...parser.ast_nodes import ConditionalExpression, UnaryExpression

        # Create Abs(x) = if x < 0 then -x else x
        abs_func = FunctionDef(
            name="Abs",
            parameters=[("x", "Integer")],
            return_type="Integer",
            body=ConditionalExpression(
                condition=BinaryExpression(
                    operator="<",
                    left=Identifier(name="x"),
                    right=Literal(value=0),
                ),
                then_expr=UnaryExpression(
                    operator="-",
                    operand=Identifier(name="x"),
                ),
                else_expr=Identifier(name="x"),
            ),
        )

        inliner.register_function(abs_func)

        args = [SQLLiteral(value=-5)]
        result = inliner.inline_function("Abs", args, context)

        # Should produce a CASE/conditional expression
        sql = result.to_sql()
        assert sql  # Should have some output


# =============================================================================
# Test: Function Registration
# =============================================================================


class TestFunctionRegistration:
    """Tests for function registration and retrieval."""

    def test_register_and_retrieve(self, inliner: FunctionInliner):
        """Test basic register and retrieve cycle."""
        func = make_double_function()
        inliner.register_function(func)

        retrieved = inliner.get_function("Double")
        assert retrieved is not None
        assert retrieved.name == "Double"

    def test_retrieve_nonexistent_function(self, inliner: FunctionInliner):
        """Test retrieving a function that doesn't exist."""
        result = inliner.get_function("NonExistent")
        assert result is None

    def test_inline_nonexistent_function_raises(self, inliner: FunctionInliner, context: SQLTranslationContext):
        """Test that inlining a non-existent function raises error."""
        args = [SQLLiteral(value=5)]
        with pytest.raises(TranslationError) as exc_info:
            inliner.inline_function("NonExistent", args, context)

        assert "not found" in str(exc_info.value).lower()

    def test_inline_function_with_no_body_raises(self, inliner: FunctionInliner, context: SQLTranslationContext):
        """Test that inlining a function with no body raises error."""
        func = FunctionDef(
            name="NoBody",
            parameters=[("x", "Integer")],
            body=None,
        )
        inliner.register_function(func)

        args = [SQLLiteral(value=5)]
        with pytest.raises(TranslationError) as exc_info:
            inliner.inline_function("NoBody", args, context)

        assert "no body" in str(exc_info.value).lower()


# =============================================================================
# Test: Call Graph Building
# =============================================================================


class TestCallGraphBuilding:
    """Tests for call graph building."""

    def test_build_call_graph_single_function(self, inliner: FunctionInliner):
        """Test call graph with a single function that calls no others."""
        inliner.register_function(make_double_function())

        graph = inliner.build_call_graph()

        # Double doesn't call any user functions
        assert "Double" in graph
        assert graph["Double"] == set()

    def test_build_call_graph_with_dependencies(self, inliner: FunctionInliner):
        """Test call graph with function dependencies."""
        inliner.register_function(make_double_function())
        inliner.register_function(make_quadruple_function())

        graph = inliner.build_call_graph()

        # Quadruple calls Double
        assert "Quadruple" in graph
        assert "Double" in graph["Quadruple"]

    def test_build_call_graph_with_cycle(self, inliner: FunctionInliner):
        """Test call graph correctly represents cyclic dependencies."""
        inliner.register_function(make_cycle_function_a())
        inliner.register_function(make_cycle_function_b())
        inliner.register_function(make_cycle_function_c())

        graph = inliner.build_call_graph()

        # A -> B, B -> C, C -> A
        assert graph.get("A") == {"B"}
        assert graph.get("B") == {"C"}
        assert graph.get("C") == {"A"}


# =============================================================================
# Test: ParameterPlaceholder
# =============================================================================


class TestParameterPlaceholder:
    """Tests for ParameterPlaceholder class."""

    def test_parameter_placeholder_creation(self):
        """Test creating a ParameterPlaceholder."""
        sql_expr = SQLLiteral(value=42)
        placeholder = ParameterPlaceholder(name="x", sql_expr=sql_expr)

        assert placeholder.name == "x"
        assert placeholder.sql_expr == sql_expr

    def test_parameter_placeholder_carries_sql(self):
        """Test that placeholder carries SQL expression through."""
        sql_expr = SQLLiteral(value=100)
        placeholder = ParameterPlaceholder(name="param", sql_expr=sql_expr)

        # The SQL expression should be retrievable
        assert placeholder.sql_expr.to_sql() == "100"


# =============================================================================
# Test: Check For Cycles
# =============================================================================


class TestCheckForCycles:
    """Tests for check_for_cycles method."""

    def test_check_no_cycles(self, inliner: FunctionInliner):
        """Test check_for_cycles with no cycles."""
        inliner.register_function(make_double_function())

        # Should not raise
        inliner.check_for_cycles()

    def test_check_with_cycle_raises(self, inliner: FunctionInliner):
        """Test check_for_cycles raises on cycle detection."""
        inliner.register_function(make_recursive_function_a())

        with pytest.raises(TranslationError):
            inliner.check_for_cycles()
