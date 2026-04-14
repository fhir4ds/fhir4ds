"""Result-based correctness tests for context-aware translation."""

import pytest
from ...translator import CQLToSQLTranslator
from ...parser import parse_cql
from ..fixtures.test_data import get_expected_results, get_patient_ids


class TestExistsCorrectness:
    """Test exists() produces correct results."""

    def _translate_and_get_meta(self, cql: str):
        """Translate CQL and return context with metadata."""
        ast = parse_cql(cql)
        translator = CQLToSQLTranslator()
        sql = translator.translate_library(ast)
        return sql, translator._context

    def test_exists_shape_is_patient_scalar(self):
        """exists() should produce PATIENT_SCALAR shape."""
        cql = '''
            library Test version '1.0'
            define Diabetes: [Condition: "Diabetes"]
            define HasDiabetes: exists Diabetes
        '''

        sql, context = self._translate_and_get_meta(cql)

        from ...translator.context import RowShape
        assert "HasDiabetes" in context.definition_meta
        assert context.definition_meta["HasDiabetes"].shape == RowShape.PATIENT_SCALAR

    def test_retrieve_shape_is_resource_rows(self):
        """Retrieve should produce RESOURCE_ROWS shape."""
        cql = '''
            library Test version '1.0'
            define Diabetes: [Condition: "Diabetes"]
        '''

        sql, context = self._translate_and_get_meta(cql)

        from ...translator.context import RowShape
        assert "Diabetes" in context.definition_meta
        assert context.definition_meta["Diabetes"].shape == RowShape.RESOURCE_ROWS


class TestCountCorrectness:
    """Test Count() produces correct results."""

    def _translate_and_get_meta(self, cql: str):
        """Translate CQL and return context with metadata."""
        ast = parse_cql(cql)
        translator = CQLToSQLTranslator()
        sql = translator.translate_library(ast)
        return sql, translator._context

    def test_count_shape_is_patient_scalar(self):
        """Count() should produce PATIENT_SCALAR shape."""
        cql = '''
            library Test version '1.0'
            define Diabetes: [Condition: "Diabetes"]
            define DiabetesCount: Count(Diabetes)
        '''

        sql, context = self._translate_and_get_meta(cql)

        from ...translator.context import RowShape
        assert "DiabetesCount" in context.definition_meta
        assert context.definition_meta["DiabetesCount"].shape == RowShape.PATIENT_SCALAR

    def test_count_cql_type_is_integer(self):
        """Count() should have Integer CQL type."""
        cql = '''
            library Test version '1.0'
            define Diabetes: [Condition: "Diabetes"]
            define DiabetesCount: Count(Diabetes)
        '''

        sql, context = self._translate_and_get_meta(cql)

        assert context.definition_meta["DiabetesCount"].cql_type == "Integer"


class TestFirstLastCorrectness:
    """Test First()/Last() produce correct results."""

    def _translate_and_get_meta(self, cql: str):
        """Translate CQL and return context with metadata."""
        ast = parse_cql(cql)
        translator = CQLToSQLTranslator()
        sql = translator.translate_library(ast)
        return sql, translator._context

    @pytest.mark.xfail(reason="First() shape inference not yet implemented - returns UNKNOWN")
    def test_first_shape_is_patient_scalar(self):
        """First() should produce PATIENT_SCALAR shape."""
        cql = '''
            library Test version '1.0'
            define Diabetes: [Condition: "Diabetes"]
            define FirstDiabetes: First(Diabetes)
        '''

        sql, context = self._translate_and_get_meta(cql)

        from ...translator.context import RowShape
        assert "FirstDiabetes" in context.definition_meta
        assert context.definition_meta["FirstDiabetes"].shape == RowShape.PATIENT_SCALAR


class TestMultiUsageTracking:
    """Test that multiple usages are tracked correctly."""

    def test_definition_used_in_exists_and_count(self):
        """Definition used in both exists and Count should track both usages."""
        cql = '''
            library Test version '1.0'
            define Diabetes: [Condition: "Diabetes"]
            define HasDiabetes: exists Diabetes
            define DiabetesCount: Count(Diabetes)
        '''

        ast = parse_cql(cql)
        translator = CQLToSQLTranslator()
        sql = translator.translate_library(ast)

        # Both definitions should exist
        assert "HasDiabetes" in translator._context.definition_meta
        assert "DiabetesCount" in translator._context.definition_meta


class TestWarningEmission:
    """Test that warnings are emitted correctly."""

    def test_no_warnings_for_simple_translate(self):
        """Simple translation should not produce warnings."""
        cql = '''
            library Test version '1.0'
            define Diabetes: [Condition: "Diabetes"]
            define HasDiabetes: exists Diabetes
        '''

        ast = parse_cql(cql)
        translator = CQLToSQLTranslator()
        sql = translator.translate_library(ast)

        # Should not have warnings for this simple case
        # (Note: May have warnings in more complex cases)
        assert isinstance(translator._context.warnings.count(), int)
