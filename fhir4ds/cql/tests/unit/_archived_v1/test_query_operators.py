"""
Unit tests for CQL query operators.

Tests the parsing and translation of the 8 query operators:
- SkipExpression
- TakeExpression
- FirstExpression
- LastExpression
- AnyExpression
- AllExpression
- SingletonExpression
- DistinctExpression
"""

import pytest

from ....parser.ast_nodes import (
    AllExpression,
    AnyExpression,
    BinaryExpression,
    DistinctExpression,
    FirstExpression,
    Identifier,
    LastExpression,
    ListExpression,
    Literal,
    SingletonExpression,
    SkipExpression,
    TakeExpression,
)
from ....translator import CQLTranslator


class TestSkipExpression:
    """Tests for skip expression translation."""

    @pytest.fixture
    def translator(self) -> CQLTranslator:
        """Create a translator instance for testing."""
        return CQLTranslator()

    def test_skip_translate(self, translator: CQLTranslator):
        """Test translation: skip N -> subset(N, count)"""
        expr = SkipExpression(
            source=ListExpression(elements=[
                Literal(value=1),
                Literal(value=2),
                Literal(value=3),
                Literal(value=4),
                Literal(value=5),
            ]),
            count=Literal(value=2),
        )
        result = translator.translate_expression(expr)
        assert "subset" in result
        assert "2" in result

    def test_skip_with_identifier_source(self, translator: CQLTranslator):
        """Test skip with identifier source."""
        expr = SkipExpression(
            source=Identifier(name="items"),
            count=Literal(value=5),
        )
        result = translator.translate_expression(expr)
        assert "items" in result
        assert "subset" in result

    def test_skip_with_zero(self, translator: CQLTranslator):
        """Test skip with zero count."""
        expr = SkipExpression(
            source=Identifier(name="data"),
            count=Literal(value=0),
        )
        result = translator.translate_expression(expr)
        assert "subset" in result
        assert "0" in result


class TestTakeExpression:
    """Tests for take expression translation."""

    @pytest.fixture
    def translator(self) -> CQLTranslator:
        """Create a translator instance for testing."""
        return CQLTranslator()

    def test_take_translate(self, translator: CQLTranslator):
        """Test translation: take N -> take(N)"""
        expr = TakeExpression(
            source=ListExpression(elements=[
                Literal(value=1),
                Literal(value=2),
                Literal(value=3),
                Literal(value=4),
                Literal(value=5),
            ]),
            count=Literal(value=3),
        )
        result = translator.translate_expression(expr)
        assert "take(3)" in result

    def test_take_with_identifier_source(self, translator: CQLTranslator):
        """Test take with identifier source."""
        expr = TakeExpression(
            source=Identifier(name="items"),
            count=Literal(value=10),
        )
        result = translator.translate_expression(expr)
        assert "items.take(10)" in result

    def test_take_with_one(self, translator: CQLTranslator):
        """Test take with count of 1."""
        expr = TakeExpression(
            source=Identifier(name="data"),
            count=Literal(value=1),
        )
        result = translator.translate_expression(expr)
        assert "take(1)" in result


class TestFirstExpression:
    """Tests for first expression translation."""

    @pytest.fixture
    def translator(self) -> CQLTranslator:
        """Create a translator instance for testing."""
        return CQLTranslator()

    def test_first_translate(self, translator: CQLTranslator):
        """Test translation: first -> .first()"""
        expr = FirstExpression(
            source=ListExpression(elements=[
                Literal(value=1),
                Literal(value=2),
                Literal(value=3),
            ])
        )
        result = translator.translate_expression(expr)
        assert ".first()" in result

    def test_first_with_identifier(self, translator: CQLTranslator):
        """Test first with identifier source."""
        expr = FirstExpression(
            source=Identifier(name="observations")
        )
        result = translator.translate_expression(expr)
        assert "observations.first()" in result

    def test_first_empty_list(self, translator: CQLTranslator):
        """Test first with empty list."""
        expr = FirstExpression(
            source=ListExpression(elements=[])
        )
        result = translator.translate_expression(expr)
        assert ".first()" in result


class TestLastExpression:
    """Tests for last expression translation."""

    @pytest.fixture
    def translator(self) -> CQLTranslator:
        """Create a translator instance for testing."""
        return CQLTranslator()

    def test_last_translate(self, translator: CQLTranslator):
        """Test translation: last -> .last()"""
        expr = LastExpression(
            source=ListExpression(elements=[
                Literal(value=1),
                Literal(value=2),
                Literal(value=3),
            ])
        )
        result = translator.translate_expression(expr)
        assert ".last()" in result

    def test_last_with_identifier(self, translator: CQLTranslator):
        """Test last with identifier source."""
        expr = LastExpression(
            source=Identifier(name="results")
        )
        result = translator.translate_expression(expr)
        assert "results.last()" in result

    def test_last_empty_list(self, translator: CQLTranslator):
        """Test last with empty list."""
        expr = LastExpression(
            source=ListExpression(elements=[])
        )
        result = translator.translate_expression(expr)
        assert ".last()" in result


class TestAnyExpression:
    """Tests for any expression translation."""

    @pytest.fixture
    def translator(self) -> CQLTranslator:
        """Create a translator instance for testing."""
        return CQLTranslator()

    def test_any_translate(self, translator: CQLTranslator):
        """Test translation: any X where condition -> where(condition).exists()"""
        expr = AnyExpression(
            source=ListExpression(elements=[
                Literal(value=1),
                Literal(value=2),
                Literal(value=3),
            ]),
            alias="X",
            condition=BinaryExpression(
                operator=">",
                left=Identifier(name="X"),
                right=Literal(value=2),
            ),
        )
        result = translator.translate_expression(expr)
        assert ".where(" in result
        assert ".exists()" in result

    def test_any_with_identifier_source(self, translator: CQLTranslator):
        """Test any with identifier source."""
        expr = AnyExpression(
            source=Identifier(name="values"),
            alias="V",
            condition=BinaryExpression(
                operator="=",
                left=Identifier(name="V"),
                right=Literal(value=5),
            ),
        )
        result = translator.translate_expression(expr)
        assert "values.where(" in result
        assert ".exists()" in result

    def test_any_with_complex_condition(self, translator: CQLTranslator):
        """Test any with complex condition."""
        expr = AnyExpression(
            source=Identifier(name="items"),
            alias="I",
            condition=BinaryExpression(
                operator="and",
                left=BinaryExpression(
                    operator=">",
                    left=Identifier(name="I"),
                    right=Literal(value=0),
                ),
                right=BinaryExpression(
                    operator="<",
                    left=Identifier(name="I"),
                    right=Literal(value=100),
                ),
            ),
        )
        result = translator.translate_expression(expr)
        assert ".where(" in result
        assert ".exists()" in result


class TestAllExpression:
    """Tests for all expression translation."""

    @pytest.fixture
    def translator(self) -> CQLTranslator:
        """Create a translator instance for testing."""
        return CQLTranslator()

    def test_all_translate(self, translator: CQLTranslator):
        """Test translation: all X where condition -> all(condition)"""
        expr = AllExpression(
            source=ListExpression(elements=[
                Literal(value=2),
                Literal(value=4),
                Literal(value=6),
            ]),
            alias="X",
            condition=BinaryExpression(
                operator=">",
                left=Identifier(name="X"),
                right=Literal(value=0),
            ),
        )
        result = translator.translate_expression(expr)
        assert ".all(" in result

    def test_all_with_identifier_source(self, translator: CQLTranslator):
        """Test all with identifier source."""
        expr = AllExpression(
            source=Identifier(name="values"),
            alias="V",
            condition=BinaryExpression(
                operator="!=",
                left=Identifier(name="V"),
                right=Literal(value=None),
            ),
        )
        result = translator.translate_expression(expr)
        assert "values.all(" in result

    def test_all_with_modulo_condition(self, translator: CQLTranslator):
        """Test all with modulo condition (even numbers check)."""
        expr = AllExpression(
            source=Identifier(name="numbers"),
            alias="N",
            condition=BinaryExpression(
                operator="=",
                left=BinaryExpression(
                    operator="mod",
                    left=Identifier(name="N"),
                    right=Literal(value=2),
                ),
                right=Literal(value=0),
            ),
        )
        result = translator.translate_expression(expr)
        assert ".all(" in result


class TestSingletonExpression:
    """Tests for singleton expression translation."""

    @pytest.fixture
    def translator(self) -> CQLTranslator:
        """Create a translator instance for testing."""
        return CQLTranslator()

    def test_singleton_translate(self, translator: CQLTranslator):
        """Test translation: singleton from -> .single()"""
        expr = SingletonExpression(
            source=ListExpression(elements=[Literal(value=5)])
        )
        result = translator.translate_expression(expr)
        assert ".single()" in result

    def test_singleton_with_identifier(self, translator: CQLTranslator):
        """Test singleton with identifier source."""
        expr = SingletonExpression(
            source=Identifier(name="result")
        )
        result = translator.translate_expression(expr)
        assert "result.single()" in result

    def test_singleton_empty_list(self, translator: CQLTranslator):
        """Test singleton with empty list (returns null)."""
        expr = SingletonExpression(
            source=ListExpression(elements=[])
        )
        result = translator.translate_expression(expr)
        assert ".single()" in result


class TestDistinctExpression:
    """Tests for distinct expression translation."""

    @pytest.fixture
    def translator(self) -> CQLTranslator:
        """Create a translator instance for testing."""
        return CQLTranslator()

    def test_distinct_translate(self, translator: CQLTranslator):
        """Test translation: distinct -> .distinct()"""
        expr = DistinctExpression(
            source=ListExpression(elements=[
                Literal(value=1),
                Literal(value=2),
                Literal(value=2),
                Literal(value=3),
                Literal(value=3),
                Literal(value=3),
            ])
        )
        result = translator.translate_expression(expr)
        assert ".distinct()" in result

    def test_distinct_with_identifier(self, translator: CQLTranslator):
        """Test distinct with identifier source."""
        expr = DistinctExpression(
            source=Identifier(name="duplicates")
        )
        result = translator.translate_expression(expr)
        assert "duplicates.distinct()" in result

    def test_distinct_empty_list(self, translator: CQLTranslator):
        """Test distinct with empty list."""
        expr = DistinctExpression(
            source=ListExpression(elements=[])
        )
        result = translator.translate_expression(expr)
        assert ".distinct()" in result

    def test_distinct_string_list(self, translator: CQLTranslator):
        """Test distinct with string list."""
        expr = DistinctExpression(
            source=ListExpression(elements=[
                Literal(value="a"),
                Literal(value="b"),
                Literal(value="a"),
                Literal(value="c"),
            ])
        )
        result = translator.translate_expression(expr)
        assert ".distinct()" in result


class TestQueryOperatorChaining:
    """Tests for chaining multiple query operators."""

    @pytest.fixture
    def translator(self) -> CQLTranslator:
        """Create a translator instance for testing."""
        return CQLTranslator()

    def test_skip_then_take(self, translator: CQLTranslator):
        """Test skip followed by take (pagination pattern)."""
        skip_expr = SkipExpression(
            source=Identifier(name="items"),
            count=Literal(value=10),
        )
        take_expr = TakeExpression(
            source=skip_expr,
            count=Literal(value=5),
        )
        result = translator.translate_expression(take_expr)
        assert "take(5)" in result
        assert "subset" in result

    def test_distinct_then_first(self, translator: CQLTranslator):
        """Test distinct followed by first."""
        distinct_expr = DistinctExpression(
            source=Identifier(name="values"),
        )
        first_expr = FirstExpression(
            source=distinct_expr,
        )
        result = translator.translate_expression(first_expr)
        assert ".distinct()" in result
        assert ".first()" in result

    def test_take_then_last(self, translator: CQLTranslator):
        """Test take followed by last."""
        take_expr = TakeExpression(
            source=Identifier(name="items"),
            count=Literal(value=10),
        )
        last_expr = LastExpression(
            source=take_expr,
        )
        result = translator.translate_expression(last_expr)
        assert ".take(10)" in result
        assert ".last()" in result
