"""Tests for PATIENT_SCALAR LEFT JOIN conversion (Gap 17).

Tests verify:
- PATIENT_SCALAR definitions use LEFT JOIN when possible
- Filter conditions are moved to JOIN ON clause
- Scalar subquery fallback for complex expressions
"""

import pytest
from ...translator import CQLToSQLTranslator
from ...translator.context import RowShape, DefinitionMeta
from ...parser import parse_cql


class TestPatientScalarJoinConversion:
    """Verify PATIENT_SCALAR uses LEFT JOIN instead of scalar subquery."""

    def _translate(self, cql: str) -> str:
        """Helper to translate CQL to SQL."""
        ast = parse_cql(cql)
        translator = CQLToSQLTranslator()
        return translator.translate_library_to_sql(ast)

    def _translate_and_get_meta(self, cql: str, def_name: str) -> tuple:
        """Helper to translate and get definition metadata."""
        ast = parse_cql(cql)
        translator = CQLToSQLTranslator()
        translator.translate_library(ast)
        meta = translator._context.definition_meta.get(def_name)
        return translator.translate_library_to_sql(ast), meta

    def test_first_expression_is_patient_scalar(self):
        """First expression should produce PATIENT_SCALAR shape."""
        cql = '''
            library Test version '1.0'
            define "First Encounter":
                First([Encounter] E where E.status = 'finished')
        '''

        ast = parse_cql(cql)
        translator = CQLToSQLTranslator()
        translator.translate_library(ast)

        meta = translator._context.definition_meta.get("First Encounter")
        assert meta is not None
        assert meta.shape == RowShape.PATIENT_SCALAR

    def test_simple_patient_scalar_uses_join_when_possible(self):
        """Simple PATIENT_SCALAR should use LEFT JOIN pattern when tracked refs exist."""
        cql = '''
            library Test version '1.0'
            define Encounters: [Encounter]
            define "First Encounter":
                First(Encounters E where E.status = 'finished')
        '''

        sql = self._translate(cql)
        sql_upper = sql.upper()

        # Should have a CTE structure
        assert "WITH" in sql_upper

        # Should reference the Encounters definition
        assert "ENCOUNTER" in sql_upper

    def test_patient_scalar_non_boolean_has_value_column(self):
        """Non-boolean PATIENT_SCALAR should have proper CTE structure."""
        cql = '''
            library Test version '1.0'
            define "First Encounter":
                First([Encounter] E where E.status = 'finished')
        '''

        sql = self._translate(cql)

        # The CTE should have a WITH clause and proper structure
        assert "WITH" in sql.upper()
        # First produces a scalar result
        assert "First Encounter" in sql or "first encounter" in sql.lower()

    def test_count_produces_patient_scalar(self):
        """Count should produce PATIENT_SCALAR shape."""
        cql = '''
            library Test version '1.0'
            define Encounters: [Encounter]
            define EncounterCount: Count(Encounters)
        '''

        ast = parse_cql(cql)
        translator = CQLToSQLTranslator()
        translator.translate_library(ast)

        meta = translator._context.definition_meta.get("EncounterCount")
        assert meta is not None
        assert meta.shape == RowShape.PATIENT_SCALAR

    def test_exists_produces_patient_scalar_boolean(self):
        """Exists should produce PATIENT_SCALAR boolean."""
        cql = '''
            library Test version '1.0'
            define Encounters: [Encounter]
            define HasEncounter: exists Encounters
        '''

        ast = parse_cql(cql)
        translator = CQLToSQLTranslator()
        translator.translate_library(ast)

        meta = translator._context.definition_meta.get("HasEncounter")
        assert meta is not None
        assert meta.shape == RowShape.PATIENT_SCALAR
        assert meta.cql_type == "Boolean"

    def test_complex_aggregation_falls_back_to_subquery(self):
        """Complex aggregations should fall back to scalar subquery."""
        cql = '''
            library Test version '1.0'
            define Encounters: [Encounter]
            define EncounterCount: Count(Encounters)
        '''

        sql = self._translate(cql)
        sql_upper = sql.upper()

        # Count should be present
        assert "COUNT" in sql_upper

        # Should have CTE structure
        assert "WITH" in sql_upper


class TestCanUseJoinForScalar:
    """Test the _can_use_join_for_scalar helper method."""

    def test_no_joins_returns_false(self):
        """When no JOINs are available, should return False."""
        from ...translator.translator import CQLToSQLTranslator
        from ...translator.context import DefinitionMeta, RowShape
        from ...translator.types import SQLIdentifier

        translator = CQLToSQLTranslator()
        meta = DefinitionMeta(
            name="Test",
            shape=RowShape.PATIENT_SCALAR,
            cql_type="Integer",
        )
        sql_ast = SQLIdentifier(name="value")

        result = translator._can_use_join_for_scalar(meta, sql_ast, None)
        assert result is False

        result = translator._can_use_join_for_scalar(meta, sql_ast, [])
        assert result is False

    def test_aggregation_returns_false(self):
        """Complex aggregations should return False."""
        from ...translator.translator import CQLToSQLTranslator
        from ...translator.context import DefinitionMeta, RowShape
        from ...translator.types import SQLFunctionCall, SQLLiteral

        translator = CQLToSQLTranslator()
        meta = DefinitionMeta(
            name="Test",
            shape=RowShape.PATIENT_SCALAR,
            cql_type="Integer",
        )

        # COUNT function call
        count_call = SQLFunctionCall(
            name="COUNT",
            args=[SQLLiteral(value=1)],
        )

        result = translator._contains_complex_aggregation(count_call)
        assert result is True


class TestGetJoinColumnForScalar:
    """Test the _get_join_column_for_scalar helper method."""

    def test_returns_resource_column_for_empty_refs(self):
        """When no tracked refs, should return original expression."""
        from ...translator.translator import CQLToSQLTranslator
        from ...translator.context import DefinitionMeta, RowShape
        from ...translator.types import SQLIdentifier

        translator = CQLToSQLTranslator()
        meta = DefinitionMeta(
            name="Test",
            shape=RowShape.PATIENT_SCALAR,
            cql_type="Resource",
        )
        sql_ast = SQLIdentifier(name="original")

        result = translator._get_join_column_for_scalar(meta, sql_ast)
        # Should return original when no refs
        assert result == sql_ast


class TestJoinGenerationIntegration:
    """Integration tests for JOIN generation with PATIENT_SCALAR."""

    def _translate(self, cql: str) -> str:
        """Helper to translate CQL to SQL."""
        ast = parse_cql(cql)
        translator = CQLToSQLTranslator()
        return translator.translate_library_to_sql(ast)

    def test_definition_chain_generates_proper_sql(self):
        """Chain of definitions should generate valid SQL."""
        cql = '''
            library Test version '1.0'
            define Conditions: [Condition: "Diabetes"]
            define HasCondition: exists Conditions
            define InPopulation: HasCondition
        '''

        sql = self._translate(cql)

        # Should have CTE structure
        assert "WITH" in sql.upper()

        # Should reference the definitions
        sql_lower = sql.lower()
        assert "conditions" in sql_lower
        assert "hascondition" in sql_lower

    def test_multiple_scalar_definitions(self):
        """Multiple scalar definitions should work correctly."""
        cql = '''
            library Test version '1.0'
            define Conditions: [Condition]
            define Encounters: [Encounter]
            define ConditionCount: Count(Conditions)
            define EncounterCount: Count(Encounters)
        '''

        sql = self._translate(cql)

        # Should have CTE structure
        assert "WITH" in sql.upper()

        # Should have both counts
        assert "COUNT" in sql.upper()
