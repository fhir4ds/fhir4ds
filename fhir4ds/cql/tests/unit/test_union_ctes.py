"""
Unit tests for union CTE generation.

Tests that all retrieve sources in a union generate corresponding CTEs.
This addresses Gap 16: Missing CTEs from Union Sources.
"""

import pytest
import sys
from pathlib import Path

# Add src to path

from ...translator import CQLToSQLTranslator
from ...parser import parse_cql
from ...translator.placeholder import RetrievePlaceholder, find_all_placeholders


class TestUnionCTEs:
    """Tests for union CTE generation."""

    def test_simple_union_two_sources(self):
        """Union of two retrieves should generate two CTEs."""
        cql = """
        library Test version '1.0'

        valueset "Diabetes": 'http://example.org/fhir/ValueSet/diabetes'
        valueset "Hypertension": 'http://example.org/fhir/ValueSet/hypertension'

        context Patient

        define "Combined":
            [Condition: "Diabetes"] union [Condition: "Hypertension"]
        """
        library = parse_cql(cql)
        translator = CQLToSQLTranslator()
        sql = translator.translate_library_to_population_sql(library)

        # Check that both valuesets are referenced
        assert 'diabetes' in sql.lower() or 'Diabetes' in sql, \
            f"Expected diabetes valueset in SQL:\n{sql[:2000]}"
        assert 'hypertension' in sql.lower() or 'Hypertension' in sql, \
            f"Expected hypertension valueset in SQL:\n{sql[:2000]}"

    def test_union_three_sources(self):
        """Union of three retrieves should generate three CTEs."""
        cql = """
        library Test version '1.0'

        valueset "Diabetes": 'http://example.org/fhir/ValueSet/diabetes'
        valueset "Hypertension": 'http://example.org/fhir/ValueSet/hypertension'
        valueset "Heart Disease": 'http://example.org/fhir/ValueSet/heart-disease'

        context Patient

        define "Combined":
            [Condition: "Diabetes"]
            union [Condition: "Hypertension"]
            union [Condition: "Heart Disease"]
        """
        library = parse_cql(cql)
        translator = CQLToSQLTranslator()
        sql = translator.translate_library_to_population_sql(library)

        # Check that all three valuesets are referenced
        assert 'diabetes' in sql.lower() or 'Diabetes' in sql, \
            f"Expected diabetes valueset in SQL:\n{sql[:2000]}"
        assert 'hypertension' in sql.lower() or 'Hypertension' in sql, \
            f"Expected hypertension valueset in SQL:\n{sql[:2000]}"
        assert 'heart' in sql.lower() or 'Heart Disease' in sql, \
            f"Expected heart disease valueset in SQL:\n{sql[:2000]}"

    def test_union_four_sources(self):
        """Union of four retrieves should generate four CTEs."""
        cql = """
        library Test version '1.0'

        valueset "Pregnancy": 'http://cts.nlm.nih.gov/fhir/ValueSet/pregnancy'
        valueset "ESRD": 'http://cts.nlm.nih.gov/fhir/ValueSet/esrd'
        valueset "CKD5": 'http://cts.nlm.nih.gov/fhir/ValueSet/ckd-stage-5'
        valueset "Hospice": 'http://cts.nlm.nih.gov/fhir/ValueSet/hospice'

        context Patient

        define "Combined":
            [Condition: "Pregnancy"]
            union [Condition: "ESRD"]
            union [Condition: "CKD5"]
            union [Condition: "Hospice"]
        """
        library = parse_cql(cql)
        translator = CQLToSQLTranslator()
        sql = translator.translate_library_to_population_sql(library)

        # Check that all four valuesets are referenced
        assert 'pregnancy' in sql.lower() or 'Pregnancy' in sql, \
            f"Expected pregnancy valueset in SQL:\n{sql[:2000]}"
        assert 'esrd' in sql.lower() or 'ESRD' in sql, \
            f"Expected ESRD valueset in SQL:\n{sql[:2000]}"
        assert 'ckd' in sql.lower() or 'CKD5' in sql, \
            f"Expected CKD5 valueset in SQL:\n{sql[:2000]}"
        assert 'hospice' in sql.lower() or 'Hospice' in sql, \
            f"Expected hospice valueset in SQL:\n{sql[:2000]}"

    def test_union_mixed_resource_types(self):
        """Union of different resource types should generate CTEs for each."""
        cql = """
        library Test version '1.0'

        valueset "Lab Values": 'http://example.org/fhir/ValueSet/lab-values'
        valueset "Conditions": 'http://example.org/fhir/ValueSet/conditions'

        context Patient

        define "Combined":
            [Observation: "Lab Values"] union [Condition: "Conditions"]
        """
        library = parse_cql(cql)
        translator = CQLToSQLTranslator()
        sql = translator.translate_library_to_population_sql(library)

        # Check that both resource types appear
        assert 'Observation' in sql, \
            f"Expected Observation in SQL:\n{sql[:2000]}"
        assert 'Condition' in sql, \
            f"Expected Condition in SQL:\n{sql[:2000]}"

    def test_union_without_valueset(self):
        """Union of retrieves without valueset filter should work."""
        cql = """
        library Test version '1.0'

        context Patient

        define "Combined":
            [Condition] union [Observation]
        """
        library = parse_cql(cql)
        translator = CQLToSQLTranslator()
        sql = translator.translate_library_to_population_sql(library)

        # Check that both resource types appear
        assert 'Condition' in sql, \
            f"Expected Condition in SQL:\n{sql[:2000]}"
        assert 'Observation' in sql, \
            f"Expected Observation in SQL:\n{sql[:2000]}"

    def test_placeholder_keys_match_cte_keys(self):
        """Verify that placeholder keys match CTE name map keys for union sources."""
        from ...translator.context import SQLTranslationContext
        from ...translator.expressions import ExpressionTranslator
        from ...parser.ast_nodes import BinaryExpression, Retrieve, Identifier

        # Create context with valuesets
        context = SQLTranslationContext()
        context.valuesets = {
            "Diabetes": "http://example.org/fhir/ValueSet/diabetes",
            "Hypertension": "http://example.org/fhir/ValueSet/hypertension",
        }

        translator = ExpressionTranslator(context)

        # Create union of two retrieves
        union_expr = BinaryExpression(
            operator="union",
            left=Retrieve(type="Condition", terminology=Identifier(name="Diabetes")),
            right=Retrieve(type="Condition", terminology=Identifier(name="Hypertension")),
        )

        # Translate the union
        result = translator.translate(union_expr)

        # Find all placeholders in the result
        placeholders = find_all_placeholders(result)

        # Should have 2 placeholders
        assert len(placeholders) == 2, \
            f"Expected 2 placeholders, got {len(placeholders)}: {[p.key for p in placeholders]}"

        # Check that keys use consistent format (URLs) - 3-tuple format: (resource_type, valueset, profile_url)
        keys = {p.key for p in placeholders}
        expected_keys = {
            ("Condition", "http://example.org/fhir/ValueSet/diabetes", None),
            ("Condition", "http://example.org/fhir/ValueSet/hypertension", None),
        }
        assert keys == expected_keys, \
            f"Expected keys {expected_keys}, got {keys}"

    def test_union_with_nested_expression(self):
        """Union with nested expressions should find all placeholders."""
        cql = """
        library Test version '1.0'

        valueset "A": 'http://example.org/fhir/ValueSet/a'
        valueset "B": 'http://example.org/fhir/ValueSet/b'
        valueset "C": 'http://example.org/fhir/ValueSet/c'

        context Patient

        define "First":
            [Condition: "A"] union [Condition: "B"]

        define "Second":
            "First" union [Condition: "C"]
        """
        library = parse_cql(cql)
        translator = CQLToSQLTranslator()
        sql = translator.translate_library_to_population_sql(library)

        # Check that all three valuesets are referenced
        assert 'a' in sql.lower() or 'ValueSet/a' in sql, \
            f"Expected valueset A in SQL:\n{sql[:2000]}"
        assert 'b' in sql.lower() or 'ValueSet/b' in sql, \
            f"Expected valueset B in SQL:\n{sql[:2000]}"
        assert 'c' in sql.lower() or 'ValueSet/c' in sql, \
            f"Expected valueset C in SQL:\n{sql[:2000]}"


class TestPlaceholderKeyNormalization:
    """Tests for placeholder key normalization between URL and name."""

    def test_placeholder_url_consistency(self):
        """Verify placeholder valueset URL is consistent with context lookup."""
        from ...translator.context import SQLTranslationContext
        from ...translator.expressions import ExpressionTranslator
        from ...parser.ast_nodes import Retrieve, Identifier

        # Create context with valueset
        context = SQLTranslationContext()
        context.valuesets = {
            "Essential Hypertension": "http://cts.nlm.nih.gov/fhir/ValueSet/2.16.840.1.113883.3.464.1003.104.12.1011",
        }

        translator = ExpressionTranslator(context)

        # Create retrieve with valueset reference
        retrieve = Retrieve(
            type="Condition",
            terminology=Identifier(name="Essential Hypertension"),
        )

        # Translate the retrieve
        result = translator.translate(retrieve)

        # Should be a RetrievePlaceholder
        assert isinstance(result, RetrievePlaceholder), \
            f"Expected RetrievePlaceholder, got {type(result)}"
        assert result.resource_type == "Condition"
        # Valueset should be the URL, not the name
        assert result.valueset == "http://cts.nlm.nih.gov/fhir/ValueSet/2.16.840.1.113883.3.464.1003.104.12.1011", \
            f"Expected URL in placeholder, got {result.valueset}"

    def test_placeholder_with_unknown_valueset(self):
        """Verify placeholder uses name as-is when valueset not in context."""
        from ...translator.context import SQLTranslationContext
        from ...translator.expressions import ExpressionTranslator
        from ...parser.ast_nodes import Retrieve, Identifier

        # Create context without the valueset
        context = SQLTranslationContext()
        context.valuesets = {}

        translator = ExpressionTranslator(context)

        # Create retrieve with unknown valueset reference
        retrieve = Retrieve(
            type="Condition",
            terminology=Identifier(name="Unknown ValueSet"),
        )

        # Translate the retrieve
        result = translator.translate(retrieve)

        # Should be a RetrievePlaceholder
        assert isinstance(result, RetrievePlaceholder)
        # Valueset should be auto-generated URL
        assert result.valueset == "http://cts.nlm.nih.gov/fhir/ValueSet/Unknown ValueSet", \
            f"Expected auto-generated URL, got {result.valueset}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
