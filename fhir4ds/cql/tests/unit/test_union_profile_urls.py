"""
Unit tests for union CTE generation with profile URLs.

Tests that all retrieve sources in a union generate distinct CTEs
even when they share the same resource type but have different profiles.
This addresses P1.5: Multi-Valueset Union Defines.
"""

import pytest
import sys
from pathlib import Path

# Add src to path

from ...translator import CQLToSQLTranslator
from ...parser import parse_cql
from ...translator.placeholder import RetrievePlaceholder, find_all_placeholders


class TestUnionWithProfiles:
    """Tests for union CTE generation with profile URLs."""

    def test_union_with_different_profiles_same_valueset(self):
        """Union of same resource type with different profiles should generate separate CTEs."""
        cql = """
        library Test version '1.0'

        valueset "Pregnancy": 'http://cts.nlm.nih.gov/fhir/ValueSet/pregnancy'

        context Patient

        define "Combined":
            [ConditionProblemsHealthConcerns: "Pregnancy"]
            union [ConditionEncounterDiagnosis: "Pregnancy"]
        """
        library = parse_cql(cql)
        translator = CQLToSQLTranslator()
        sql = translator.translate_library_to_population_sql(library)

        # ConditionEncounterDiagnosis and ConditionProblemsHealthConcerns have
        # meta_profile_filter=True, so they produce separate CTEs with profile
        # WHERE clauses — one per profile, not deduplicated.
        lines = sql.split('\n')
        condition_ctes = [l for l in lines if '"Condition' in l and 'AS (' in l]

        assert len(condition_ctes) == 2, \
            f"Expected 2 Condition CTEs (one per profile with meta_profile_filter), got {len(condition_ctes)}\nSQL:\n{sql[:3000]}"

    def test_pregnancy_or_renal_diagnosis_pattern(self):
        """Test the full 'Pregnancy or Renal Diagnosis' pattern from CMS165."""
        cql = """
        library Test version '1.0'

        valueset "Pregnancy": 'http://cts.nlm.nih.gov/fhir/ValueSet/2.16.840.1.113883.3.526.3.378'
        valueset "ESRD": 'http://cts.nlm.nih.gov/fhir/ValueSet/2.16.840.1.113883.3.526.3.353'
        valueset "CKD5": 'http://cts.nlm.nih.gov/fhir/ValueSet/2.16.840.1.113883.3.526.3.1002'

        context Patient

        define "Pregnancy or Renal Diagnosis":
            ( [ConditionProblemsHealthConcerns: "Pregnancy"]
            union [ConditionEncounterDiagnosis: "Pregnancy"]
            union [ConditionProblemsHealthConcerns: "ESRD"]
            union [ConditionEncounterDiagnosis: "ESRD"]
            union [ConditionProblemsHealthConcerns: "CKD5"]
            union [ConditionEncounterDiagnosis: "CKD5"]
            )
        """
        library = parse_cql(cql)
        translator = CQLToSQLTranslator()
        sql = translator.translate_library_to_population_sql(library)

        # Should have 6 CTEs (3 valuesets x 2 profiles each)
        # Check that all valuesets appear in the SQL
        assert '2.16.840.1.113883.3.526.3.378' in sql or 'pregnancy' in sql.lower() or 'Pregnancy' in sql, \
            f"Expected Pregnancy valueset in SQL:\n{sql[:3000]}"
        assert '2.16.840.1.113883.3.526.3.353' in sql or 'esrd' in sql.lower() or 'ESRD' in sql, \
            f"Expected ESRD valueset in SQL:\n{sql[:3000]}"
        assert '2.16.840.1.113883.3.526.3.1002' in sql or 'ckd' in sql.lower() or 'CKD5' in sql, \
            f"Expected CKD5 valueset in SQL:\n{sql[:3000]}"

        # Check for UNION in the define
        assert 'UNION' in sql, f"Expected UNION in SQL:\n{sql[:3000]}"

        # ConditionEncounterDiagnosis and ConditionProblemsHealthConcerns have
        # meta_profile_filter=True, so each (profile, valueset) pair produces a
        # separate CTE — 6 CTEs total (3 valuesets × 2 profiles).
        lines = sql.split('\n')
        condition_ctes = [l for l in lines if '"Condition' in l and 'AS (' in l]
        assert len(condition_ctes) == 6, \
            f"Expected 6 Condition CTEs (3 valuesets × 2 profiles with meta_profile_filter), got {len(condition_ctes)}\nSQL:\n{sql[:3000]}"

    def test_placeholder_keys_include_profile_url(self):
        """Verify that placeholder keys include profile_url for profile-based retrieves."""
        from ...translator.context import SQLTranslationContext
        from ...translator.expressions import ExpressionTranslator
        from ...parser.ast_nodes import Retrieve, Identifier

        context = SQLTranslationContext()
        context.valuesets = {
            "Pregnancy": "http://cts.nlm.nih.gov/fhir/ValueSet/pregnancy",
        }

        translator = ExpressionTranslator(context)

        # Create retrieve with ConditionProblemsHealthConcerns profile
        retrieve1 = Retrieve(
            type="ConditionProblemsHealthConcerns",
            terminology=Identifier(name="Pregnancy"),
        )
        result1 = translator.translate(retrieve1)

        # Create retrieve with ConditionEncounterDiagnosis profile
        retrieve2 = Retrieve(
            type="ConditionEncounterDiagnosis",
            terminology=Identifier(name="Pregnancy"),
        )
        result2 = translator.translate(retrieve2)

        # Both should be placeholders
        assert isinstance(result1, RetrievePlaceholder), f"Expected placeholder, got {type(result1)}"
        assert isinstance(result2, RetrievePlaceholder), f"Expected placeholder, got {type(result2)}"

        # Both should have Condition as resource type
        assert result1.resource_type == "Condition"
        assert result2.resource_type == "Condition"

        # Both should have the same valueset
        assert result1.valueset == result2.valueset

        # But they should have different profile URLs
        assert result1.profile_url != result2.profile_url, \
            f"Expected different profile URLs, got {result1.profile_url} and {result2.profile_url}"

        # And thus different keys
        assert result1.key != result2.key, \
            f"Expected different keys for different profiles, got {result1.key} and {result2.key}"

        # Verify the profile URLs match expected QICore profiles
        assert "qicore-condition-problems-health-concerns" in result1.profile_url, \
            f"Expected problems-health-concerns profile URL, got {result1.profile_url}"
        assert "qicore-condition-encounter-diagnosis" in result2.profile_url, \
            f"Expected encounter-diagnosis profile URL, got {result2.profile_url}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
