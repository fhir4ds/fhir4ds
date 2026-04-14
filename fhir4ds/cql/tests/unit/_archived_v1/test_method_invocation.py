"""
Unit tests for method invocation syntax.

Tests the parsing and translation of CQL method invocation expressions
like Patient.ageInYears() and observations.where($this.status = 'final').
"""

import pytest

from ....parser.ast_nodes import (
    FunctionRef,
    Identifier,
    Literal,
    MethodInvocation,
    Property,
)
from ....translator import CQLTranslator


class TestMethodInvocationParsing:
    """Tests for method invocation parsing via AST."""

    # Note: These tests use the translator's ability to handle MethodInvocation
    # AST nodes directly. End-to-end parsing tests would use CQLParser.


class TestMethodInvocationTranslation:
    """Tests for method invocation translation to FHIRPath."""

    @pytest.fixture
    def translator(self) -> CQLTranslator:
        """Create a translator instance for testing."""
        return CQLTranslator()

    # === Simple method with no args ===

    def test_simple_method_no_args(self, translator: CQLTranslator):
        """Patient.ageInYears() should translate correctly."""
        result = translator.translate_expression(
            MethodInvocation(
                source=Identifier(name="Patient"),
                method="ageInYears",
                arguments=[],
            )
        )
        assert "ageInYears" in result
        assert "." in result
        assert "()" in result

    def test_method_on_identifier(self, translator: CQLTranslator):
        """Method invocation on a simple identifier."""
        result = translator.translate_expression(
            MethodInvocation(
                source=Identifier(name="observations"),
                method="first",
                arguments=[],
            )
        )
        assert result == "observations.first()"

    def test_method_on_literal(self, translator: CQLTranslator):
        """'hello'.upper() should work."""
        result = translator.translate_expression(
            MethodInvocation(
                source=Literal(value="hello"),
                method="upper",
                arguments=[],
            )
        )
        assert result == "'hello'.upper()"

    # === Method with args ===

    def test_method_with_single_arg(self, translator: CQLTranslator):
        """Method with a single argument."""
        result = translator.translate_expression(
            MethodInvocation(
                source=Identifier(name="items"),
                method="where",
                arguments=[Literal(value=True)],
            )
        )
        assert "where" in result
        assert "true" in result

    def test_method_with_multiple_args(self, translator: CQLTranslator):
        """Method with multiple arguments."""
        result = translator.translate_expression(
            MethodInvocation(
                source=Literal(value="hello world"),
                method="substring",
                arguments=[Literal(value=0), Literal(value=5)],
            )
        )
        assert "substring" in result
        assert "0" in result
        assert "5" in result

    def test_method_with_identifier_arg(self, translator: CQLTranslator):
        """Method with identifier as argument."""
        result = translator.translate_expression(
            MethodInvocation(
                source=Identifier(name="list"),
                method="take",
                arguments=[Identifier(name="count")],
            )
        )
        assert result == "list.take(count)"

    # === Chained methods ===

    def test_chained_methods(self, translator: CQLTranslator):
        """Chained method calls should work."""
        # observations.where(...).first()
        inner = MethodInvocation(
            source=Identifier(name="observations"),
            method="where",
            arguments=[Literal(value=True)],
        )
        result = translator.translate_expression(
            MethodInvocation(
                source=inner,
                method="first",
                arguments=[],
            )
        )
        assert "where" in result
        assert "first" in result
        assert result.index("where") < result.index("first")

    def test_triple_chained_methods(self, translator: CQLTranslator):
        """Three chained method calls."""
        # items.select($this).where(true).first()
        select = MethodInvocation(
            source=Identifier(name="items"),
            method="select",
            arguments=[Identifier(name="$this")],
        )
        where = MethodInvocation(
            source=select,
            method="where",
            arguments=[Literal(value=True)],
        )
        result = translator.translate_expression(
            MethodInvocation(
                source=where,
                method="first",
                arguments=[],
            )
        )
        assert "select" in result
        assert "where" in result
        assert "first" in result

    # === Property chain then method ===

    def test_property_then_method(self, translator: CQLTranslator):
        """Patient.name.given.first() - property chain then method."""
        prop = Property(
            source=Property(source=Identifier(name="Patient"), path="name"),
            path="given",
        )
        result = translator.translate_expression(
            MethodInvocation(
                source=prop,
                method="first",
                arguments=[],
            )
        )
        assert "name" in result
        assert "given" in result
        assert "first" in result

    def test_deep_property_then_method(self, translator: CQLTranslator):
        """Deep property chain then method call."""
        # Observation.value.quantity.value.first()
        prop = Property(
            source=Property(
                source=Property(source=Identifier(name="Observation"), path="value"),
                path="quantity",
            ),
            path="value",
        )
        result = translator.translate_expression(
            MethodInvocation(
                source=prop,
                method="first",
                arguments=[],
            )
        )
        assert "value" in result
        assert "quantity" in result
        assert "first" in result

    # === Method vs Function equivalence ===

    def test_method_vs_function_equivalence_age(self, translator: CQLTranslator):
        """AgeInYears(Patient) function form vs Patient.ageInYears() method form."""
        # Function form
        func_result = translator.translate_expression(
            FunctionRef(name="AgeInYears", arguments=[Identifier(name="Patient")])
        )
        # Method form
        method_result = translator.translate_expression(
            MethodInvocation(
                source=Identifier(name="Patient"),
                method="ageInYears",
                arguments=[],
            )
        )
        # Both should mention ageInYears (case-insensitive)
        assert "ageInYears".lower() in func_result.lower() or "age" in func_result.lower()
        assert "ageInYears".lower() in method_result.lower()

    # === Method with lambda-like expressions ===

    def test_method_with_function_arg(self, translator: CQLTranslator):
        """Method with a function call as an argument."""
        inner_func = FunctionRef(name="Upper", arguments=[Literal(value="test")])
        result = translator.translate_expression(
            MethodInvocation(
                source=Identifier(name="strings"),
                method="select",
                arguments=[inner_func],
            )
        )
        assert "select" in result
        assert "upper" in result.lower()

    # === Method returning value used in expression ===

    def test_method_in_binary_expression(self, translator: CQLTranslator):
        """Method result used in comparison."""
        from ....parser.ast_nodes import BinaryExpression

        method = MethodInvocation(
            source=Identifier(name="items"),
            method="count",
            arguments=[],
        )
        result = translator.translate_expression(
            BinaryExpression(
                operator=">",
                left=method,
                right=Literal(value=0),
            )
        )
        assert "count" in result
        assert ">" in result
        assert "0" in result

    # === Edge cases ===

    def test_empty_method_name(self, translator: CQLTranslator):
        """Method with empty name should still produce output."""
        result = translator.translate_expression(
            MethodInvocation(
                source=Identifier(name="obj"),
                method="",
                arguments=[],
            )
        )
        assert "obj" in result

    def test_method_with_null_arg(self, translator: CQLTranslator):
        """Method with null argument."""
        result = translator.translate_expression(
            MethodInvocation(
                source=Identifier(name="items"),
                method="where",
                arguments=[Literal(value=None)],
            )
        )
        assert "where" in result
        assert "null" in result

    def test_method_on_null_source(self, translator: CQLTranslator):
        """Method on null literal."""
        result = translator.translate_expression(
            MethodInvocation(
                source=Literal(value=None),
                method="toString",
                arguments=[],
            )
        )
        assert "null" in result
        assert "toString" in result


class TestMethodInvocationWithQueries:
    """Tests for method invocation in query context."""

    @pytest.fixture
    def translator(self) -> CQLTranslator:
        """Create a translator instance for testing."""
        return CQLTranslator()

    def test_where_method_on_retrieve(self, translator: CQLTranslator):
        """where() method on a retrieve expression."""
        from ....parser.ast_nodes import Retrieve

        result = translator.translate_expression(
            MethodInvocation(
                source=Retrieve(type="Observation"),
                method="where",
                arguments=[Literal(value=True)],
            )
        )
        assert "Observation" in result
        assert "where" in result

    def test_select_method_on_list(self, translator: CQLTranslator):
        """select() method on a list expression."""
        from ....parser.ast_nodes import ListExpression

        result = translator.translate_expression(
            MethodInvocation(
                source=ListExpression(
                    elements=[Literal(value=1), Literal(value=2), Literal(value=3)]
                ),
                method="select",
                arguments=[Identifier(name="$this")],
            )
        )
        assert "select" in result
        assert "$this" in result


class TestMethodInvocationCaseSensitivity:
    """Tests for case sensitivity in method names."""

    @pytest.fixture
    def translator(self) -> CQLTranslator:
        """Create a translator instance for testing."""
        return CQLTranslator()

    def test_lowercase_method(self, translator: CQLTranslator):
        """Lowercase method name."""
        result = translator.translate_expression(
            MethodInvocation(
                source=Identifier(name="items"),
                method="first",
                arguments=[],
            )
        )
        assert "first" in result

    def test_uppercase_method(self, translator: CQLTranslator):
        """Uppercase method name."""
        result = translator.translate_expression(
            MethodInvocation(
                source=Identifier(name="items"),
                method="FIRST",
                arguments=[],
            )
        )
        assert "FIRST" in result

    def test_mixed_case_method(self, translator: CQLTranslator):
        """Mixed case method name."""
        result = translator.translate_expression(
            MethodInvocation(
                source=Identifier(name="items"),
                method="First",
                arguments=[],
            )
        )
        assert "First" in result


class TestComplexMethodInvocations:
    """Tests for complex method invocation scenarios."""

    @pytest.fixture
    def translator(self) -> CQLTranslator:
        """Create a translator instance for testing."""
        return CQLTranslator()

    def test_nested_method_in_args(self, translator: CQLTranslator):
        """Method call with nested method in arguments."""
        inner_method = MethodInvocation(
            source=Identifier(name="inner"),
            method="value",
            arguments=[],
        )
        result = translator.translate_expression(
            MethodInvocation(
                source=Identifier(name="outer"),
                method="select",
                arguments=[inner_method],
            )
        )
        assert "outer" in result
        assert "select" in result
        assert "inner" in result
        assert "value" in result

    def test_method_with_list_arg(self, translator: CQLTranslator):
        """Method with list as argument."""
        from ....parser.ast_nodes import ListExpression

        result = translator.translate_expression(
            MethodInvocation(
                source=Identifier(name="items"),
                method="combine",
                arguments=[
                    ListExpression(
                        elements=[Literal(value="a"), Literal(value="b")]
                    )
                ],
            )
        )
        assert "combine" in result
        assert "a" in result
        assert "b" in result
