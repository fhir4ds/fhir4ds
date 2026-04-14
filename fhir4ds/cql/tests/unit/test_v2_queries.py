"""
Unit tests for QueryTranslator class (translator_v2.queries).

Tests query translation from CQL AST to SQL expressions.
"""

import pytest

from ...parser.ast_nodes import (
    BinaryExpression,
    Identifier,
    LetClause,
    Literal,
    Property,
    Query,
    QuerySource,
    Retrieve,
    ReturnClause,
    SortByItem,
    SortClause,
    WhereClause,
    WithClause,
    FunctionRef,
)
from ...translator.context import SQLTranslationContext
from ...translator.expressions import ExpressionTranslator
from ...translator.queries import QueryTranslator
from ...translator.types import (
    SQLSelect,
    SQLExists,
    SQLBinaryOp,
    SQLLiteral,
    SQLIdentifier,
    SQLQualifiedIdentifier,
)


@pytest.fixture
def context():
    """Create a fresh translation context for each test."""
    return SQLTranslationContext()


@pytest.fixture
def expr_translator(context):
    """Create an expression translator with context."""
    return ExpressionTranslator(context)


@pytest.fixture
def query_translator(context, expr_translator):
    """Create a query translator with context and expression translator."""
    return QueryTranslator(context, expr_translator)


class TestBasicRetrieve:
    """Tests for basic retrieve translation."""

    def test_retrieve_condition(self, query_translator, context):
        """Test [Condition] -> SELECT with resource_type filter."""
        query = Query(
            source=QuerySource(
                alias="C",
                expression=Retrieve(type="Condition"),
            ),
        )

        result = query_translator.translate_query(query)

        assert isinstance(result, SQLSelect)
        assert result.from_clause is not None
        # Check that resource_type filter is in WHERE
        assert result.where is not None
        where_sql = result.where.to_sql()
        assert "resource_type" in where_sql
        assert "Condition" in where_sql

    def test_retrieve_observation(self, query_translator):
        """Test [Observation] -> SELECT with resource_type filter."""
        query = Query(
            source=QuerySource(
                alias="O",
                expression=Retrieve(type="Observation"),
            ),
        )

        result = query_translator.translate_query(query)

        assert isinstance(result, SQLSelect)
        where_sql = result.where.to_sql()
        assert "Observation" in where_sql


class TestRetrieveWithTerminology:
    """Tests for retrieve with terminology filters."""

    def test_retrieve_with_valueset(self, query_translator):
        """Test [Condition: "Diabetes"] -> SELECT with in_valueset filter."""
        query = Query(
            source=QuerySource(
                alias="C",
                expression=Retrieve(
                    type="Condition",
                    terminology=Literal(value="http://example.org/ValueSet/diabetes"),
                ),
            ),
        )

        result = query_translator.translate_query(query)

        assert isinstance(result, SQLSelect)
        where_sql = result.where.to_sql()
        assert "Condition" in where_sql
        # Should include valueset filter
        assert "fhirpath_in_valueset" in where_sql or "fhirpath_text" in where_sql

    def test_retrieve_with_code(self, query_translator):
        """Test [Observation: LOINC "8480-6"] -> SELECT with code filter."""
        query = Query(
            source=QuerySource(
                alias="O",
                expression=Retrieve(
                    type="Observation",
                    terminology=Literal(value="8480-6"),
                    terminology_property="code",
                ),
            ),
        )

        result = query_translator.translate_query(query)

        assert isinstance(result, SQLSelect)
        where_sql = result.where.to_sql()
        assert "Observation" in where_sql


class TestQueryWithWhere:
    """Tests for query with where clause."""

    def test_where_with_boolean_literal(self, query_translator):
        """Test [Condition] C where C.verified = true."""
        query = Query(
            source=QuerySource(
                alias="C",
                expression=Retrieve(type="Condition"),
            ),
            where=WhereClause(
                expression=BinaryExpression(
                    operator="=",
                    left=Property(source=Identifier(name="C"), path="verified"),
                    right=Literal(value=True),
                )
            ),
        )

        result = query_translator.translate_query(query)

        assert isinstance(result, SQLSelect)
        where_sql = result.where.to_sql()
        assert "AND" in where_sql  # resource_type AND condition
        assert "TRUE" in where_sql

    def test_where_with_string_literal(self, query_translator):
        """Test [Observation] O where O.status = 'final'."""
        query = Query(
            source=QuerySource(
                alias="O",
                expression=Retrieve(type="Observation"),
            ),
            where=WhereClause(
                expression=BinaryExpression(
                    operator="=",
                    left=Property(source=Identifier(name="O"), path="status"),
                    right=Literal(value="final"),
                )
            ),
        )

        result = query_translator.translate_query(query)

        assert isinstance(result, SQLSelect)
        where_sql = result.where.to_sql()
        assert "'final'" in where_sql


class TestLetClause:
    """Tests for let clause translation."""

    def test_single_let_clause(self, query_translator, context):
        """Test let BP = 5 generates CTE.

        Note: Complex expressions like First([Observation]) require a full Retrieve
        handler in the expression translator. For now, test with a simple literal.
        """
        query = Query(
            source=QuerySource(
                alias="O",
                expression=Retrieve(type="Observation"),
            ),
            let_clauses=[
                LetClause(
                    alias="BP",
                    expression=Literal(value=120),
                ),
            ],
        )

        result = query_translator.translate_query(query)

        assert isinstance(result, SQLSelect)
        # CTEs should be added to context
        ctes = context.get_ctes()
        assert len(ctes) >= 1
        assert ctes[0].name.startswith("let_")

    def test_multiple_let_clauses(self, query_translator, context):
        """Test multiple let clauses generate multiple CTEs."""
        query = Query(
            source=QuerySource(
                alias="O",
                expression=Retrieve(type="Observation"),
            ),
            let_clauses=[
                LetClause(alias="x", expression=Literal(value=5)),
                LetClause(alias="y", expression=Literal(value=10)),
            ],
        )

        result = query_translator.translate_query(query)

        assert isinstance(result, SQLSelect)
        ctes = context.get_ctes()
        assert len(ctes) >= 2


class TestWithWithoutClauses:
    """Tests for with/without clause translation."""

    def test_with_clause_exists(self, query_translator):
        """Test A with B such that A.id = B.ref -> EXISTS subquery."""
        query = Query(
            source=QuerySource(
                alias="A",
                expression=Retrieve(type="Condition"),
            ),
            with_clauses=[
                WithClause(
                    alias="B",
                    expression=Retrieve(type="Encounter"),
                    such_that=BinaryExpression(
                        operator="=",
                        left=Property(source=Identifier(name="A"), path="id"),
                        right=Property(source=Identifier(name="B"), path="subject"),
                    ),
                    is_without=False,
                ),
            ],
        )

        result = query_translator.translate_query(query)

        assert isinstance(result, SQLSelect)
        where_sql = result.where.to_sql()
        assert "EXISTS" in where_sql

    def test_without_clause_not_exists(self, query_translator):
        """Test A without B such that A.id = B.ref -> NOT EXISTS subquery.

        Note: The without clause uses SQLUnaryOp with NOT prefix around SQLExists.
        """
        query = Query(
            source=QuerySource(
                alias="A",
                expression=Retrieve(type="Condition"),
            ),
            with_clauses=[
                WithClause(
                    alias="B",
                    expression=Retrieve(type="Encounter"),
                    such_that=BinaryExpression(
                        operator="=",
                        left=Property(source=Identifier(name="A"), path="id"),
                        right=Property(source=Identifier(name="B"), path="subject"),
                    ),
                    is_without=True,
                ),
            ],
        )

        result = query_translator.translate_query(query)

        assert isinstance(result, SQLSelect)
        where_sql = result.where.to_sql()
        # Check that NOT EXISTS is in the SQL output
        # The translator generates "NOT EXISTS (...)" for without clauses
        assert "NOT" in where_sql
        assert "EXISTS" in where_sql

    def test_without_clause_with_union_source(self, query_translator):
        """Test 'without (A union B) X such that ...' produces multiple NOT EXISTS clauses.

        Per the design spec, when the 'without' source is a union, we generate
        multiple NOT EXISTS clauses (one per branch) for better query optimization.
        """
        from ...parser.ast_nodes import BinaryExpression

        # CQL: [Condition] A without ([Encounter: "Inpatient"] union [Encounter: "ED"]) B such that A.subject = B.subject
        query = Query(
            source=QuerySource(
                alias="A",
                expression=Retrieve(type="Condition"),
            ),
            with_clauses=[
                WithClause(
                    alias="B",
                    expression=BinaryExpression(
                        operator="union",
                        left=Retrieve(type="Encounter"),  # First encounter branch
                        right=Retrieve(type="Observation"),  # Second branch (using Observation as proxy for ED encounter)
                    ),
                    such_that=BinaryExpression(
                        operator="=",
                        left=Property(source=Identifier(name="A"), path="subject"),
                        right=Property(source=Identifier(name="B"), path="subject"),
                    ),
                    is_without=True,
                ),
            ],
        )

        result = query_translator.translate_query(query)

        assert isinstance(result, SQLSelect)
        where_sql = result.where.to_sql()

        # Check that we have two NOT EXISTS clauses (one per union branch)
        not_exists_count = where_sql.count("NOT EXISTS")
        assert not_exists_count == 2, f"Expected 2 NOT EXISTS clauses, got {not_exists_count}: {where_sql}"

        # Both should have patient correlation
        assert "patient_ref" in where_sql, "Expected patient correlation in NOT EXISTS clauses"

    def test_without_clause_with_nested_union_source(self, query_translator):
        """Test 'without (A union B union C) X such that ...' produces 3 NOT EXISTS clauses.

        Tests deeply nested union flattening.
        """
        from ...parser.ast_nodes import BinaryExpression

        # CQL: [Condition] A without (E1 union E2 union E3) B such that ...
        # Parsed as: ((E1 union E2) union E3)
        query = Query(
            source=QuerySource(
                alias="A",
                expression=Retrieve(type="Condition"),
            ),
            with_clauses=[
                WithClause(
                    alias="B",
                    expression=BinaryExpression(
                        operator="union",
                        left=BinaryExpression(
                            operator="union",
                            left=Retrieve(type="Encounter"),
                            right=Retrieve(type="Observation"),
                        ),
                        right=Retrieve(type="Procedure"),
                    ),
                    such_that=BinaryExpression(
                        operator="=",
                        left=Property(source=Identifier(name="A"), path="subject"),
                        right=Property(source=Identifier(name="B"), path="subject"),
                    ),
                    is_without=True,
                ),
            ],
        )

        result = query_translator.translate_query(query)

        assert isinstance(result, SQLSelect)
        where_sql = result.where.to_sql()

        # Check that we have three NOT EXISTS clauses (one per union branch)
        not_exists_count = where_sql.count("NOT EXISTS")
        assert not_exists_count == 3, f"Expected 3 NOT EXISTS clauses, got {not_exists_count}: {where_sql}"


class TestSortClause:
    """Tests for sort clause translation."""

    def test_sort_asc(self, query_translator):
        """Test [Observation] O sort by effectiveDateTime asc."""
        query = Query(
            source=QuerySource(
                alias="O",
                expression=Retrieve(type="Observation"),
            ),
            sort=SortClause(
                by=[
                    SortByItem(
                        direction="asc",
                        expression=Property(source=Identifier(name="O"), path="effectiveDateTime"),
                    ),
                ]
            ),
        )

        result = query_translator.translate_query(query)

        assert isinstance(result, SQLSelect)
        assert result.order_by is not None
        assert len(result.order_by) == 1
        expr, direction = result.order_by[0]
        assert direction == "ASC"

    def test_sort_desc(self, query_translator):
        """Test [Observation] O sort by effectiveDateTime desc."""
        query = Query(
            source=QuerySource(
                alias="O",
                expression=Retrieve(type="Observation"),
            ),
            sort=SortClause(
                by=[
                    SortByItem(
                        direction="desc",
                        expression=Property(source=Identifier(name="O"), path="effectiveDateTime"),
                    ),
                ]
            ),
        )

        result = query_translator.translate_query(query)

        assert isinstance(result, SQLSelect)
        assert result.order_by is not None
        expr, direction = result.order_by[0]
        assert direction == "DESC"

    def test_sort_default_direction(self, query_translator):
        """Test sort with no direction defaults to ASC."""
        query = Query(
            source=QuerySource(
                alias="O",
                expression=Retrieve(type="Observation"),
            ),
            sort=SortClause(
                by=[
                    SortByItem(
                        expression=Property(source=Identifier(name="O"), path="effectiveDateTime"),
                    ),
                ]
            ),
        )

        result = query_translator.translate_query(query)

        assert isinstance(result, SQLSelect)
        expr, direction = result.order_by[0]
        assert direction == "ASC"


class TestFirstLast:
    """Tests for First/Last expression handling in queries."""

    def test_first_with_sort(self, query_translator):
        """Test First([Observation] O sort by effectiveDateTime desc) -> ORDER BY ... LIMIT 1.

        Note: First is typically handled at the expression level, not query level.
        This test verifies the sort clause works correctly for such patterns.
        """
        query = Query(
            source=QuerySource(
                alias="O",
                expression=Retrieve(type="Observation"),
            ),
            sort=SortClause(
                by=[
                    SortByItem(
                        direction="desc",
                        expression=Property(source=Identifier(name="O"), path="effectiveDateTime"),
                    ),
                ]
            ),
        )

        result = query_translator.translate_query(query)

        assert isinstance(result, SQLSelect)
        assert result.order_by is not None
        expr, direction = result.order_by[0]
        assert direction == "DESC"
        # Note: LIMIT would be applied by FirstExpression handler, not QueryTranslator

    def test_last_sort_pattern(self, query_translator):
        """Test Last([Observation] O sort by effectiveDateTime asc) -> ORDER BY ... DESC LIMIT 1.

        Note: Last is typically handled at the expression level, not query level.
        This test verifies the sort clause works correctly.
        """
        query = Query(
            source=QuerySource(
                alias="O",
                expression=Retrieve(type="Observation"),
            ),
            sort=SortClause(
                by=[
                    SortByItem(
                        direction="asc",
                        expression=Property(source=Identifier(name="O"), path="effectiveDateTime"),
                    ),
                ]
            ),
        )

        result = query_translator.translate_query(query)

        assert isinstance(result, SQLSelect)
        assert result.order_by is not None
        expr, direction = result.order_by[0]
        assert direction == "ASC"


class TestUnion:
    """Tests for union query patterns.

    Note: Union is typically handled at a higher level (combine operator),
    but we include placeholder tests for completeness.
    """

    def test_union_pattern_not_directly_in_query(self, query_translator):
        """Verify that union is not directly handled by QueryTranslator.

        Union of [Condition: "A"] union [Condition: "B"] is handled
        at the expression level, not the Query level.
        """
        # QueryTranslator handles individual queries
        # Union is a combine operator at the expression level
        query = Query(
            source=QuerySource(
                alias="C",
                expression=Retrieve(type="Condition"),
            ),
        )

        result = query_translator.translate_query(query)
        assert isinstance(result, SQLSelect)


class TestMultiSourceQueries:
    """Tests for multi-source queries (CROSS JOIN pattern)."""

    def test_two_sources_cross_join(self, query_translator):
        """Test from [A], [B] where A.id = B.ref -> CROSS JOIN with WHERE."""
        query = Query(
            source=[
                QuerySource(
                    alias="A",
                    expression=Retrieve(type="Patient"),
                ),
                QuerySource(
                    alias="B",
                    expression=Retrieve(type="Condition"),
                ),
            ],
            where=WhereClause(
                expression=BinaryExpression(
                    operator="=",
                    left=Property(source=Identifier(name="A"), path="id"),
                    right=Property(source=Identifier(name="B"), path="subject"),
                )
            ),
        )

        result = query_translator.translate_query(query)

        assert isinstance(result, SQLSelect)
        # Check that CROSS JOIN is in the FROM clause
        from_sql = result.from_clause.to_sql()
        assert "CROSS JOIN" in from_sql

    def test_three_sources(self, query_translator):
        """Test from [A], [B], [C] generates multiple CROSS JOINs."""
        query = Query(
            source=[
                QuerySource(
                    alias="A",
                    expression=Retrieve(type="Patient"),
                ),
                QuerySource(
                    alias="B",
                    expression=Retrieve(type="Condition"),
                ),
                QuerySource(
                    alias="C",
                    expression=Retrieve(type="Encounter"),
                ),
            ],
        )

        result = query_translator.translate_query(query)

        assert isinstance(result, SQLSelect)
        from_sql = result.from_clause.to_sql()
        # Should have 2 CROSS JOINs for 3 sources
        assert from_sql.count("CROSS JOIN") == 2


class TestReturnClause:
    """Tests for return clause translation."""

    def test_return_property(self, query_translator):
        """Test return C.resource selects specific column."""
        query = Query(
            source=QuerySource(
                alias="C",
                expression=Retrieve(type="Condition"),
            ),
            return_clause=ReturnClause(
                expression=Property(source=Identifier(name="C"), path="resource"),
            ),
        )

        result = query_translator.translate_query(query)

        assert isinstance(result, SQLSelect)
        assert len(result.columns) == 1

    def test_default_return_is_resource(self, query_translator):
        """Test default return (no return clause) selects alias.resource."""
        query = Query(
            source=QuerySource(
                alias="C",
                expression=Retrieve(type="Condition"),
            ),
        )

        result = query_translator.translate_query(query)

        assert isinstance(result, SQLSelect)
        assert len(result.columns) == 1
        col = result.columns[0]
        assert isinstance(col, SQLQualifiedIdentifier)
        assert "resource" in col.to_sql()


class TestBooleanContext:
    """Tests for boolean context handling."""

    def test_query_in_boolean_context(self, query_translator):
        """Test query in boolean context wraps in EXISTS."""
        query = Query(
            source=QuerySource(
                alias="C",
                expression=Retrieve(type="Condition"),
            ),
            where=WhereClause(
                expression=Literal(value=True),
            ),
        )

        result = query_translator.translate_query(query, boolean_context=True)

        # In boolean context, should return SQLExists
        assert isinstance(result, SQLExists)
        exists_sql = result.to_sql()
        assert "EXISTS" in exists_sql
        assert "SELECT 1" in exists_sql


class TestCombinedClauses:
    """Tests for queries combining multiple clauses."""

    def test_where_and_sort(self, query_translator):
        """Test query with both where and sort clauses."""
        query = Query(
            source=QuerySource(
                alias="O",
                expression=Retrieve(type="Observation"),
            ),
            where=WhereClause(
                expression=BinaryExpression(
                    operator="=",
                    left=Property(source=Identifier(name="O"), path="status"),
                    right=Literal(value="final"),
                )
            ),
            sort=SortClause(
                by=[
                    SortByItem(
                        direction="desc",
                        expression=Property(source=Identifier(name="O"), path="effectiveDateTime"),
                    ),
                ]
            ),
        )

        result = query_translator.translate_query(query)

        assert isinstance(result, SQLSelect)
        assert result.where is not None
        assert result.order_by is not None
        sql = result.to_sql()
        assert "WHERE" in sql
        assert "ORDER BY" in sql

    def test_let_where_and_return(self, query_translator, context):
        """Test query with let, where, and return clauses."""
        query = Query(
            source=QuerySource(
                alias="O",
                expression=Retrieve(type="Observation"),
            ),
            let_clauses=[
                LetClause(alias="threshold", expression=Literal(value=100)),
            ],
            where=WhereClause(
                expression=BinaryExpression(
                    operator=">",
                    left=Property(source=Identifier(name="O"), path="value"),
                    right=Identifier(name="threshold"),
                )
            ),
            return_clause=ReturnClause(
                expression=Property(source=Identifier(name="O"), path="id"),
            ),
        )

        result = query_translator.translate_query(query)

        assert isinstance(result, SQLSelect)
        # Should have CTEs for let clause
        ctes = context.get_ctes()
        assert len(ctes) >= 1
