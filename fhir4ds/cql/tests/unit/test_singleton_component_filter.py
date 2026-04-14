"""
Unit tests for singleton from with component filter (Gap 4).

Tests the translation of singleton from expressions with where clauses
on component arrays to FHIRPath .where() expressions.

Example:
    singleton from(BPReading.component C
        where C.code ~ "Systolic blood pressure"
        return C.value as Quantity
    )

Expected output:
    fhirpath_number(resource, 'component.where(code.display = ''Systolic blood pressure'').valueQuantity.value')
"""

import pytest

from ...parser.ast_nodes import (
    BinaryExpression,
    FunctionRef,
    Identifier,
    Literal,
    Property,
    Query,
    QuerySource,
    ReturnClause,
    SingletonExpression,
    WhereClause,
)
from ...translator.context import SQLTranslationContext
from ...translator.expressions import ExpressionTranslator
from ...translator.types import (
    SQLFunctionCall,
    SQLLiteral,
    SQLQualifiedIdentifier,
)


class TestComponentFilterDetection:
    """Tests for _is_component_filter_query detection method."""

    @pytest.fixture
    def translator(self) -> ExpressionTranslator:
        """Create an ExpressionTranslator instance for testing."""
        context = SQLTranslationContext()
        return ExpressionTranslator(context)

    def test_detects_component_filter_query(self, translator: ExpressionTranslator):
        """Test that component filter queries are detected."""
        # Build: O.component C where C.code ~ "Systolic" return C.value
        query = Query(
            source=QuerySource(
                alias="C",
                expression=Property(
                    source=Identifier(name="O"),
                    path="component"
                )
            ),
            where=WhereClause(
                expression=BinaryExpression(
                    operator="~",
                    left=Property(source=Identifier(name="C"), path="code"),
                    right=Literal(value="Systolic blood pressure")
                )
            ),
            return_clause=ReturnClause(
                expression=Property(source=Identifier(name="C"), path="value")
            )
        )

        assert translator._is_component_filter_query(query) is True

    def test_rejects_non_query(self, translator: ExpressionTranslator):
        """Test that non-Query expressions are rejected."""
        expr = Identifier(name="X")
        assert translator._is_component_filter_query(expr) is False

    def test_rejects_query_without_where(self, translator: ExpressionTranslator):
        """Test that queries without where clause are rejected."""
        query = Query(
            source=QuerySource(
                alias="C",
                expression=Property(
                    source=Identifier(name="O"),
                    path="component"
                )
            ),
            where=None,
            return_clause=ReturnClause(
                expression=Property(source=Identifier(name="C"), path="value")
            )
        )

        assert translator._is_component_filter_query(query) is False

    def test_rejects_query_without_return(self, translator: ExpressionTranslator):
        """Test that queries without return clause are rejected."""
        query = Query(
            source=QuerySource(
                alias="C",
                expression=Property(
                    source=Identifier(name="O"),
                    path="component"
                )
            ),
            where=WhereClause(
                expression=BinaryExpression(
                    operator="~",
                    left=Property(source=Identifier(name="C"), path="code"),
                    right=Literal(value="Systolic")
                )
            ),
            return_clause=None
        )

        assert translator._is_component_filter_query(query) is False

    def test_rejects_non_component_query(self, translator: ExpressionTranslator):
        """Test that queries on non-component paths are rejected."""
        query = Query(
            source=QuerySource(
                alias="C",
                expression=Property(
                    source=Identifier(name="O"),
                    path="identifier"  # Not component
                )
            ),
            where=WhereClause(
                expression=BinaryExpression(
                    operator="~",
                    left=Property(source=Identifier(name="C"), path="code"),
                    right=Literal(value="Systolic")
                )
            ),
            return_clause=ReturnClause(
                expression=Property(source=Identifier(name="C"), path="value")
            )
        )

        assert translator._is_component_filter_query(query) is False


class TestCodeDisplayExtraction:
    """Tests for _extract_code_display_from_where method."""

    @pytest.fixture
    def translator(self) -> ExpressionTranslator:
        """Create an ExpressionTranslator instance for testing."""
        context = SQLTranslationContext()
        return ExpressionTranslator(context)

    def test_extracts_literal_value(self, translator: ExpressionTranslator):
        """Test extraction of display string from literal."""
        where_expr = BinaryExpression(
            operator="~",
            left=Property(source=Identifier(name="C"), path="code"),
            right=Literal(value="Systolic blood pressure")
        )

        result = translator._extract_code_display_from_where(where_expr)
        assert result == "Systolic blood pressure"

    def test_extracts_identifier_name(self, translator: ExpressionTranslator):
        """Test extraction of display string from identifier."""
        where_expr = BinaryExpression(
            operator="~",
            left=Property(source=Identifier(name="C"), path="code"),
            right=Identifier(name="SystolicCode")
        )

        result = translator._extract_code_display_from_where(where_expr)
        assert result == "SystolicCode"

    def test_returns_none_for_wrong_operator(self, translator: ExpressionTranslator):
        """Test that wrong operator returns None."""
        where_expr = BinaryExpression(
            operator="=",
            left=Property(source=Identifier(name="C"), path="code"),
            right=Literal(value="Systolic")
        )

        result = translator._extract_code_display_from_where(where_expr)
        assert result is None


class TestReturnPathExtraction:
    """Tests for _extract_return_path method."""

    @pytest.fixture
    def translator(self) -> ExpressionTranslator:
        """Create an ExpressionTranslator instance for testing."""
        context = SQLTranslationContext()
        return ExpressionTranslator(context)

    def test_maps_value_to_quantity(self, translator: ExpressionTranslator):
        """Test that 'value' maps to 'valueQuantity.value'."""
        return_expr = Property(source=Identifier(name="C"), path="value")
        result = translator._extract_return_path(return_expr)
        assert result == "valueQuantity.value"

    def test_maps_valueQuantity(self, translator: ExpressionTranslator):
        """Test that 'valueQuantity' maps to 'valueQuantity.value'."""
        return_expr = Property(source=Identifier(name="C"), path="valueQuantity")
        result = translator._extract_return_path(return_expr)
        assert result == "valueQuantity.value"

    def test_preserves_other_paths(self, translator: ExpressionTranslator):
        """Test that unmapped paths are preserved."""
        return_expr = Property(source=Identifier(name="C"), path="valueString")
        result = translator._extract_return_path(return_expr)
        assert result == "valueString"


class TestFhirpathFuncInference:
    """Tests for _infer_fhirpath_func_from_return method."""

    @pytest.fixture
    def translator(self) -> ExpressionTranslator:
        """Create an ExpressionTranslator instance for testing."""
        context = SQLTranslationContext()
        return ExpressionTranslator(context)

    def test_infers_number_for_quantity(self, translator: ExpressionTranslator):
        """Test that Quantity type returns fhirpath_number."""
        return_clause = ReturnClause(
            expression=FunctionRef(
                name="as",
                arguments=[
                    Property(source=Identifier(name="C"), path="value"),
                    Identifier(name="Quantity")
                ]
            )
        )

        result = translator._infer_fhirpath_func_from_return(return_clause)
        assert result == "fhirpath_number"

    def test_infers_number_for_decimal(self, translator: ExpressionTranslator):
        """Test that Decimal type returns fhirpath_number."""
        return_clause = ReturnClause(
            expression=FunctionRef(
                name="as",
                arguments=[
                    Property(source=Identifier(name="C"), path="value"),
                    Identifier(name="Decimal")
                ]
            )
        )

        result = translator._infer_fhirpath_func_from_return(return_clause)
        assert result == "fhirpath_number"

    def test_infers_text_for_string(self, translator: ExpressionTranslator):
        """Test that String type returns fhirpath_text."""
        return_clause = ReturnClause(
            expression=FunctionRef(
                name="as",
                arguments=[
                    Property(source=Identifier(name="C"), path="value"),
                    Identifier(name="String")
                ]
            )
        )

        result = translator._infer_fhirpath_func_from_return(return_clause)
        assert result == "fhirpath_text"

    def test_infers_date_for_datetime(self, translator: ExpressionTranslator):
        """Test that DateTime type returns fhirpath_date."""
        return_clause = ReturnClause(
            expression=FunctionRef(
                name="as",
                arguments=[
                    Property(source=Identifier(name="C"), path="value"),
                    Identifier(name="DateTime")
                ]
            )
        )

        result = translator._infer_fhirpath_func_from_return(return_clause)
        assert result == "fhirpath_date"

    def test_defaults_to_number_for_value_property(self, translator: ExpressionTranslator):
        """Test that simple 'value' property defaults to fhirpath_number."""
        return_clause = ReturnClause(
            expression=Property(source=Identifier(name="C"), path="value")
        )

        result = translator._infer_fhirpath_func_from_return(return_clause)
        assert result == "fhirpath_number"


class TestFhirpathGeneration:
    """Tests for _generate_component_fhirpath method."""

    @pytest.fixture
    def translator(self) -> ExpressionTranslator:
        """Create an ExpressionTranslator instance for testing."""
        context = SQLTranslationContext()
        return ExpressionTranslator(context)

    def test_generates_correct_fhirpath(self, translator: ExpressionTranslator):
        """Test that correct FHIRPath expression is generated."""
        query = Query(
            source=QuerySource(
                alias="C",
                expression=Property(
                    source=Identifier(name="O"),
                    path="component"
                )
            ),
            where=WhereClause(
                expression=BinaryExpression(
                    operator="~",
                    left=Property(source=Identifier(name="C"), path="code"),
                    right=Literal(value="Systolic blood pressure")
                )
            ),
            return_clause=ReturnClause(
                expression=Property(source=Identifier(name="C"), path="value")
            )
        )

        resource_sql = SQLQualifiedIdentifier(parts=["r1", "resource"])
        result = translator._generate_component_fhirpath(query, resource_sql)

        assert isinstance(result, SQLFunctionCall)
        assert result.name == "fhirpath_number"
        assert len(result.args) == 2
        assert isinstance(result.args[0], SQLQualifiedIdentifier)
        assert isinstance(result.args[1], SQLLiteral)

        # Check the FHIRPath expression
        fhirpath_expr = result.args[1].value
        assert "component.where" in fhirpath_expr
        assert "Systolic blood pressure" in fhirpath_expr
        assert "valueQuantity.value" in fhirpath_expr

    def test_sql_output_format(self, translator: ExpressionTranslator):
        """Test that generated SQL has correct format."""
        query = Query(
            source=QuerySource(
                alias="C",
                expression=Property(
                    source=Identifier(name="O"),
                    path="component"
                )
            ),
            where=WhereClause(
                expression=BinaryExpression(
                    operator="~",
                    left=Property(source=Identifier(name="C"), path="code"),
                    right=Literal(value="Diastolic blood pressure")
                )
            ),
            return_clause=ReturnClause(
                expression=Property(source=Identifier(name="C"), path="value")
            )
        )

        resource_sql = SQLQualifiedIdentifier(parts=["obs", "resource"])
        result = translator._generate_component_fhirpath(query, resource_sql)
        sql = result.to_sql()

        assert "fhirpath_number" in sql
        assert "component.where" in sql
        assert "Diastolic blood pressure" in sql
        assert "valueQuantity.value" in sql


class TestSingletonExpressionTranslation:
    """Integration tests for singleton from with component filter translation."""

    @pytest.fixture
    def translator(self) -> ExpressionTranslator:
        """Create an ExpressionTranslator instance for testing."""
        context = SQLTranslationContext()
        return ExpressionTranslator(context)

    def test_full_translation_systolic(self, translator: ExpressionTranslator):
        """Test full translation of systolic BP component extraction."""
        # Build the Query
        query = Query(
            source=QuerySource(
                alias="BPComponent",
                expression=Property(
                    source=Identifier(name="BPReading"),
                    path="component"
                )
            ),
            where=WhereClause(
                expression=BinaryExpression(
                    operator="~",
                    left=Property(source=Identifier(name="BPComponent"), path="code"),
                    right=Literal(value="Systolic blood pressure")
                )
            ),
            return_clause=ReturnClause(
                expression=FunctionRef(
                    name="as",
                    arguments=[
                        Property(source=Identifier(name="BPComponent"), path="value"),
                        Identifier(name="Quantity")
                    ]
                )
            )
        )

        # Wrap in SingletonExpression
        singleton = SingletonExpression(source=query)

        # Register BPReading as an alias with table_alias
        translator.context.push_alias_scope("BPReading")
        translator.context.add_symbol(
            name="BPReading",
            symbol_type="alias",
            sql_expr=None,
            table_alias="r1",
            cte_name="Observation:BP"
        )

        result = translator._translate_singleton_expression(singleton)

        # Verify result
        assert isinstance(result, SQLFunctionCall)
        assert result.name == "fhirpath_number"

        sql = result.to_sql()
        assert "component.where" in sql
        assert "Systolic blood pressure" in sql

    def test_full_translation_diastolic(self, translator: ExpressionTranslator):
        """Test full translation of diastolic BP component extraction."""
        query = Query(
            source=QuerySource(
                alias="BPComponent",
                expression=Property(
                    source=Identifier(name="BPReading"),
                    path="component"
                )
            ),
            where=WhereClause(
                expression=BinaryExpression(
                    operator="~",
                    left=Property(source=Identifier(name="BPComponent"), path="code"),
                    right=Literal(value="Diastolic blood pressure")
                )
            ),
            return_clause=ReturnClause(
                expression=FunctionRef(
                    name="as",
                    arguments=[
                        Property(source=Identifier(name="BPComponent"), path="value"),
                        Identifier(name="Quantity")
                    ]
                )
            )
        )

        singleton = SingletonExpression(source=query)

        # Register BPReading as an alias with table_alias
        translator.context.push_alias_scope("BPReading")
        translator.context.add_symbol(
            name="BPReading",
            symbol_type="alias",
            sql_expr=None,
            table_alias="r2",
            cte_name="Observation:BP"
        )

        result = translator._translate_singleton_expression(singleton)

        sql = result.to_sql()
        assert "component.where" in sql
        assert "Diastolic blood pressure" in sql
        assert "valueQuantity.value" in sql
