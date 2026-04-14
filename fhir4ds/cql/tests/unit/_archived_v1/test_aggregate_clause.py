"""
Unit tests for aggregate clause translation.

Tests the translation of CQL aggregate clauses in query expressions
to FHIRPath aggregate functions.
"""

import pytest

from ....parser.ast_nodes import (
    AggregateClause,
    BinaryExpression,
    FunctionRef,
    Identifier,
    Literal,
    Property,
    Query,
    QuerySource,
    Retrieve,
    WhereClause,
)
from ....translator import CQLTranslator


class TestAggregateClauseBasics:
    """Tests for basic aggregate clause structure."""

    @pytest.fixture
    def translator(self) -> CQLTranslator:
        """Create a translator instance for testing."""
        return CQLTranslator()


class TestSimpleCountAggregate:
    """Tests for Count aggregate translation."""

    @pytest.fixture
    def translator(self) -> CQLTranslator:
        """Create a translator instance for testing."""
        return CQLTranslator()

    def test_simple_count_aggregate(self, translator: CQLTranslator):
        """Simple count aggregate should translate."""
        # from [Observation] O return aggregate: Count(1)
        query = Query(
            source=QuerySource(alias="O", expression=Retrieve(type="Observation")),
            aggregate=AggregateClause(
                identifier="Result",
                expression=FunctionRef(name="Count", arguments=[Literal(value=1)]),
            ),
        )
        result = translator.translate_expression(query)
        assert result is not None
        assert "count" in result.lower() or "aggregate" in result.lower()

    def test_count_with_property(self, translator: CQLTranslator):
        """Count with property reference."""
        # from [Observation] O return aggregate: Count(O.id)
        query = Query(
            source=QuerySource(alias="O", expression=Retrieve(type="Observation")),
            aggregate=AggregateClause(
                identifier="Result",
                expression=FunctionRef(
                    name="Count",
                    arguments=[Property(source=Identifier(name="O"), path="id")],
                ),
            ),
        )
        result = translator.translate_expression(query)
        assert result is not None
        assert "count" in result.lower()

    def test_count_on_empty(self, translator: CQLTranslator):
        """Count on empty collection."""
        query = Query(
            source=QuerySource(alias="O", expression=Retrieve(type="Observation")),
            where=WhereClause(expression=Literal(value=False)),
            aggregate=AggregateClause(
                identifier="Result",
                expression=FunctionRef(name="Count", arguments=[Literal(value=1)]),
            ),
        )
        result = translator.translate_expression(query)
        assert result is not None


class TestSimpleSumAggregate:
    """Tests for Sum aggregate translation."""

    @pytest.fixture
    def translator(self) -> CQLTranslator:
        """Create a translator instance for testing."""
        return CQLTranslator()

    def test_simple_sum_aggregate(self, translator: CQLTranslator):
        """Simple sum aggregate should translate."""
        # from [Observation] O return aggregate: Sum(O.value.value)
        query = Query(
            source=QuerySource(alias="O", expression=Retrieve(type="Observation")),
            aggregate=AggregateClause(
                identifier="Result",
                expression=FunctionRef(
                    name="Sum",
                    arguments=[
                        Property(
                            source=Property(
                                source=Identifier(name="O"),
                                path="value",
                            ),
                            path="value",
                        )
                    ],
                ),
            ),
        )
        result = translator.translate_expression(query)
        assert result is not None
        assert "sum" in result.lower() or "aggregate" in result.lower()

    def test_sum_with_literal_values(self, translator: CQLTranslator):
        """Sum with literal values."""
        query = Query(
            source=QuerySource(alias="X", expression=Retrieve(type="Observation")),
            aggregate=AggregateClause(
                identifier="Total",
                expression=FunctionRef(name="Sum", arguments=[Literal(value=1)]),
            ),
        )
        result = translator.translate_expression(query)
        assert result is not None


class TestMinAggregates:
    """Tests for Min aggregate translation."""

    @pytest.fixture
    def translator(self) -> CQLTranslator:
        """Create a translator instance for testing."""
        return CQLTranslator()

    def test_min_aggregate(self, translator: CQLTranslator):
        """Min aggregate should translate."""
        # from [Observation] O return aggregate: Min(O.value.value)
        query = Query(
            source=QuerySource(alias="O", expression=Retrieve(type="Observation")),
            aggregate=AggregateClause(
                identifier="Result",
                expression=FunctionRef(
                    name="Min",
                    arguments=[Property(source=Identifier(name="O"), path="value")],
                ),
            ),
        )
        result = translator.translate_expression(query)
        assert result is not None
        assert "min" in result.lower()

    def test_min_on_dates(self, translator: CQLTranslator):
        """Min on date values."""
        query = Query(
            source=QuerySource(alias="P", expression=Retrieve(type="Patient")),
            aggregate=AggregateClause(
                identifier="Earliest",
                expression=FunctionRef(
                    name="Min",
                    arguments=[Property(source=Identifier(name="P"), path="birthDate")],
                ),
            ),
        )
        result = translator.translate_expression(query)
        assert result is not None


class TestMaxAggregates:
    """Tests for Max aggregate translation."""

    @pytest.fixture
    def translator(self) -> CQLTranslator:
        """Create a translator instance for testing."""
        return CQLTranslator()

    def test_max_aggregate(self, translator: CQLTranslator):
        """Max aggregate should translate."""
        # from [Observation] O return aggregate: Max(O.value.value)
        query = Query(
            source=QuerySource(alias="O", expression=Retrieve(type="Observation")),
            aggregate=AggregateClause(
                identifier="Result",
                expression=FunctionRef(
                    name="Max",
                    arguments=[Property(source=Identifier(name="O"), path="value")],
                ),
            ),
        )
        result = translator.translate_expression(query)
        assert result is not None
        assert "max" in result.lower()

    def test_max_on_numeric(self, translator: CQLTranslator):
        """Max on numeric values."""
        query = Query(
            source=QuerySource(
                alias="O", expression=Retrieve(type="Observation")
            ),
            aggregate=AggregateClause(
                identifier="Highest",
                expression=FunctionRef(
                    name="Max",
                    arguments=[
                        Property(
                            source=Property(
                                source=Identifier(name="O"),
                                path="value",
                            ),
                            path="value",
                        )
                    ],
                ),
            ),
        )
        result = translator.translate_expression(query)
        assert result is not None


class TestAvgAggregates:
    """Tests for Avg aggregate translation."""

    @pytest.fixture
    def translator(self) -> CQLTranslator:
        """Create a translator instance for testing."""
        return CQLTranslator()

    def test_avg_aggregate(self, translator: CQLTranslator):
        """Avg aggregate should translate."""
        # from [Observation] O return aggregate: Avg(O.value.value)
        query = Query(
            source=QuerySource(alias="O", expression=Retrieve(type="Observation")),
            aggregate=AggregateClause(
                identifier="Result",
                expression=FunctionRef(
                    name="Avg",
                    arguments=[Property(source=Identifier(name="O"), path="value")],
                ),
            ),
        )
        result = translator.translate_expression(query)
        assert result is not None
        assert "avg" in result.lower()


class TestAggregateWithWhereClause:
    """Tests for aggregate with where clause."""

    @pytest.fixture
    def translator(self) -> CQLTranslator:
        """Create a translator instance for testing."""
        return CQLTranslator()

    def test_aggregate_with_where(self, translator: CQLTranslator):
        """Aggregate with where clause should work."""
        # from [Observation] O
        # where O.status = 'final'
        # return aggregate: Count(1)
        query = Query(
            source=QuerySource(alias="O", expression=Retrieve(type="Observation")),
            where=WhereClause(
                expression=BinaryExpression(
                    operator="=",
                    left=Property(source=Identifier(name="O"), path="status"),
                    right=Literal(value="final"),
                )
            ),
            aggregate=AggregateClause(
                identifier="Result",
                expression=FunctionRef(name="Count", arguments=[Literal(value=1)]),
            ),
        )
        result = translator.translate_expression(query)
        assert result is not None
        assert "where" in result
        assert "count" in result.lower()

    def test_sum_with_where(self, translator: CQLTranslator):
        """Sum with where clause."""
        # from [Observation] O
        # where O.value.value > 0
        # return aggregate: Sum(O.value.value)
        query = Query(
            source=QuerySource(alias="O", expression=Retrieve(type="Observation")),
            where=WhereClause(
                expression=BinaryExpression(
                    operator=">",
                    left=Property(
                        source=Property(
                            source=Identifier(name="O"),
                            path="value",
                        ),
                        path="value",
                    ),
                    right=Literal(value=0),
                )
            ),
            aggregate=AggregateClause(
                identifier="Total",
                expression=FunctionRef(
                    name="Sum",
                    arguments=[
                        Property(
                            source=Property(
                                source=Identifier(name="O"),
                                path="value",
                            ),
                            path="value",
                        )
                    ],
                ),
            ),
        )
        result = translator.translate_expression(query)
        assert result is not None
        assert "where" in result

    def test_aggregate_with_complex_where(self, translator: CQLTranslator):
        """Aggregate with complex where clause using and/or."""
        query = Query(
            source=QuerySource(alias="O", expression=Retrieve(type="Observation")),
            where=WhereClause(
                expression=BinaryExpression(
                    operator="and",
                    left=BinaryExpression(
                        operator="=",
                        left=Property(source=Identifier(name="O"), path="status"),
                        right=Literal(value="final"),
                    ),
                    right=BinaryExpression(
                        operator=">",
                        left=Property(source=Identifier(name="O"), path="value"),
                        right=Literal(value=0),
                    ),
                )
            ),
            aggregate=AggregateClause(
                identifier="Result",
                expression=FunctionRef(name="Count", arguments=[Literal(value=1)]),
            ),
        )
        result = translator.translate_expression(query)
        assert result is not None


class TestAggregateWithStartingValue:
    """Tests for aggregate with starting value."""

    @pytest.fixture
    def translator(self) -> CQLTranslator:
        """Create a translator instance for testing."""
        return CQLTranslator()

    def test_aggregate_with_starting_value(self, translator: CQLTranslator):
        """Aggregate with starting value."""
        query = Query(
            source=QuerySource(alias="O", expression=Retrieve(type="Observation")),
            aggregate=AggregateClause(
                identifier="Result",
                expression=BinaryExpression(
                    operator="+",
                    left=Identifier(name="Result"),
                    right=Literal(value=1),
                ),
                starting=Literal(value=0),
            ),
        )
        result = translator.translate_expression(query)
        assert result is not None


class TestAggregateExpressionTypes:
    """Tests for different expression types in aggregate."""

    @pytest.fixture
    def translator(self) -> CQLTranslator:
        """Create a translator instance for testing."""
        return CQLTranslator()

    def test_aggregate_with_property_expression(self, translator: CQLTranslator):
        """Aggregate with property expression."""
        query = Query(
            source=QuerySource(alias="P", expression=Retrieve(type="Patient")),
            aggregate=AggregateClause(
                identifier="Result",
                expression=Property(source=Identifier(name="P"), path="birthDate"),
            ),
        )
        result = translator.translate_expression(query)
        assert result is not None

    def test_aggregate_with_binary_expression(self, translator: CQLTranslator):
        """Aggregate with binary expression."""
        query = Query(
            source=QuerySource(alias="X", expression=Retrieve(type="Observation")),
            aggregate=AggregateClause(
                identifier="Total",
                expression=BinaryExpression(
                    operator="+",
                    left=Identifier(name="Total"),
                    right=Property(source=Identifier(name="X"), path="value"),
                ),
                starting=Literal(value=0),
            ),
        )
        result = translator.translate_expression(query)
        assert result is not None

    def test_aggregate_with_function_ref(self, translator: CQLTranslator):
        """Aggregate with function reference."""
        query = Query(
            source=QuerySource(alias="X", expression=Retrieve(type="Patient")),
            aggregate=AggregateClause(
                identifier="Result",
                expression=FunctionRef(
                    name="Coalesce",
                    arguments=[
                        Identifier(name="Result"),
                        Literal(value=0),
                    ],
                ),
                starting=Literal(value=None),
            ),
        )
        result = translator.translate_expression(query)
        assert result is not None


class TestAggregateOnDifferentSources:
    """Tests for aggregate on different source types."""

    @pytest.fixture
    def translator(self) -> CQLTranslator:
        """Create a translator instance for testing."""
        return CQLTranslator()

    def test_aggregate_on_patient_retrieve(self, translator: CQLTranslator):
        """Aggregate on Patient retrieve."""
        query = Query(
            source=QuerySource(alias="P", expression=Retrieve(type="Patient")),
            aggregate=AggregateClause(
                identifier="Count",
                expression=FunctionRef(name="Count", arguments=[Literal(value=1)]),
            ),
        )
        result = translator.translate_expression(query)
        assert result is not None
        assert "Patient" in result

    def test_aggregate_on_condition_retrieve(self, translator: CQLTranslator):
        """Aggregate on Condition retrieve."""
        query = Query(
            source=QuerySource(alias="C", expression=Retrieve(type="Condition")),
            aggregate=AggregateClause(
                identifier="Result",
                expression=FunctionRef(name="Count", arguments=[Literal(value=1)]),
            ),
        )
        result = translator.translate_expression(query)
        assert result is not None
        assert "Condition" in result

    def test_aggregate_on_encounter_retrieve(self, translator: CQLTranslator):
        """Aggregate on Encounter retrieve."""
        query = Query(
            source=QuerySource(alias="E", expression=Retrieve(type="Encounter")),
            aggregate=AggregateClause(
                identifier="Total",
                expression=FunctionRef(name="Sum", arguments=[Literal(value=1)]),
            ),
        )
        result = translator.translate_expression(query)
        assert result is not None
        assert "Encounter" in result


class TestAggregateDistinctModifier:
    """Tests for aggregate with distinct modifier."""

    @pytest.fixture
    def translator(self) -> CQLTranslator:
        """Create a translator instance for testing."""
        return CQLTranslator()

    def test_aggregate_distinct(self, translator: CQLTranslator):
        """Aggregate with distinct modifier."""
        query = Query(
            source=QuerySource(alias="O", expression=Retrieve(type="Observation")),
            aggregate=AggregateClause(
                identifier="Result",
                expression=FunctionRef(name="Count", arguments=[Literal(value=1)]),
                distinct=True,
            ),
        )
        result = translator.translate_expression(query)
        assert result is not None


class TestAggregateAllModifier:
    """Tests for aggregate with all modifier."""

    @pytest.fixture
    def translator(self) -> CQLTranslator:
        """Create a translator instance for testing."""
        return CQLTranslator()

    def test_aggregate_all(self, translator: CQLTranslator):
        """Aggregate with all modifier."""
        query = Query(
            source=QuerySource(alias="O", expression=Retrieve(type="Observation")),
            aggregate=AggregateClause(
                identifier="Result",
                expression=FunctionRef(name="Count", arguments=[Literal(value=1)]),
                all_=True,
            ),
        )
        result = translator.translate_expression(query)
        assert result is not None
