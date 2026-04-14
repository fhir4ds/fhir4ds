"""
Integration tests for JOIN generation in the CQL-to-SQL pipeline.

Tests verify that the full translation pipeline produces correct JOINs
for boolean definitions and avoids FALSE literals in boolean chains.
"""

import pytest

from ...parser import parse_cql
from ...translator import translate_cql, translate_library_to_sql


class TestJoinGenerationIntegration:
    """Integration tests for JOIN generation from CQL definitions."""

    def test_boolean_definition_generates_boolean_pattern(self):
        """Test that CQL 'define HasDiabetes: exists [Condition: "Diabetes"]' produces valid boolean pattern."""
        cql = """
        library TestLibrary version '1.0'
        using FHIR version '4.0.1'

        define HasDiabetes:
          exists [Condition: "Diabetes"]
        """

        library = parse_cql(cql)
        sql = translate_library_to_sql(library)
        sql_lower = sql.lower()

        # Should have one of: EXISTS, LEFT JOIN, or IS NOT NULL pattern
        # (All are valid patterns for boolean definitions)
        has_boolean_pattern = (
            "exists" in sql_lower or
            "left join" in sql_lower or
            "is not null" in sql_lower
        )
        assert has_boolean_pattern, f"Expected EXISTS, LEFT JOIN, or IS NOT NULL in SQL, got:\n{sql}"

    def test_boolean_and_chain_avoids_false_literals(self):
        """Test that 'define IP: exists A and exists B' avoids FALSE literals in chains."""
        cql = """
        library TestLibrary version '1.0'
        using FHIR version '4.0.1'

        define HasConditionA:
          exists [Condition: "CodeA"]

        define HasConditionB:
          exists [Condition: "CodeB"]

        define BothConditions:
          HasConditionA and HasConditionB
        """

        library = parse_cql(cql)
        sql = translate_library_to_sql(library)
        sql_lower = sql.lower()

        # Should NOT have FALSE patterns in boolean chains
        assert "or false" not in sql_lower, f"Should not have 'OR FALSE' in SQL, got:\n{sql}"
        assert "and false" not in sql_lower, f"Should not have 'AND FALSE' in SQL, got:\n{sql}"

    def test_definition_referencing_boolean_definition_uses_join(self):
        """Test that referencing a boolean definition uses JOIN, not subquery."""
        cql = """
        library TestLibrary version '1.0'
        using FHIR version '4.0.1'

        define "Initial Population":
          exists [Condition: "Diabetes"]

        define Denominator:
          "Initial Population"
        """

        library = parse_cql(cql)
        sql = translate_library_to_sql(library)
        sql_lower = sql.lower()

        # Should NOT contain the subquery pattern (SELECT resource FROM "Boolean Def")
        # The boolean definition should be referenced via JOIN, not subquery
        assert "select resource from" not in sql_lower, \
            f"Should not have subquery pattern (SELECT resource FROM), got:\n{sql}"

    def test_no_false_in_or_chain(self):
        """Test that 'define Excl: exists A or exists B or exists C' has no FALSE literals."""
        cql = """
        library TestLibrary version '1.0'
        using FHIR version '4.0.1'

        define Exclusion1:
          exists [Condition: "CodeA"]

        define Exclusion2:
          exists [Condition: "CodeB"]

        define Exclusion3:
          exists [Condition: "CodeC"]

        define AllExclusions:
          Exclusion1 or Exclusion2 or Exclusion3
        """

        library = parse_cql(cql)
        sql = translate_library_to_sql(library)
        sql_lower = sql.lower()

        # Should NOT have OR FALSE pattern
        assert "or false" not in sql_lower, f"Should not have 'OR FALSE' in SQL, got:\n{sql}"

        # Should NOT have AND FALSE pattern
        assert "and false" not in sql_lower, f"Should not have 'AND FALSE' in SQL, got:\n{sql}"


class TestSQLOutput:
    """Tests verifying SQL output patterns for boolean definitions."""

    def test_no_select_resource_from_boolean_def(self):
        """Test that SQL does not contain (SELECT resource FROM "Boolean Def")."""
        cql = """
        library TestLibrary version '1.0'
        using FHIR version '4.0.1'

        define IsActive:
          exists [Condition: "Active"]

        define Result:
          IsActive
        """

        library = parse_cql(cql)
        sql = translate_library_to_sql(library)
        sql_lower = sql.lower()

        # Should not have subquery selecting from boolean definition
        assert "(select resource from" not in sql_lower, \
            f"Should not have subquery pattern, got:\n{sql}"

    def test_no_and_false(self):
        """Test that SQL does not contain 'AND FALSE' pattern."""
        cql = """
        library TestLibrary version '1.0'
        using FHIR version '4.0.1'

        define HasA:
          exists [Condition: "A"]

        define HasB:
          exists [Condition: "B"]

        define Combined:
          HasA and HasB
        """

        library = parse_cql(cql)
        sql = translate_library_to_sql(library)
        sql_lower = sql.lower()

        assert "and false" not in sql_lower, f"Should not have 'AND FALSE' in SQL, got:\n{sql}"

    def test_no_or_false(self):
        """Test that SQL does not contain 'OR FALSE' pattern."""
        cql = """
        library TestLibrary version '1.0'
        using FHIR version '4.0.1'

        define HasA:
          exists [Condition: "A"]

        define HasB:
          exists [Condition: "B"]

        define Either:
          HasA or HasB
        """

        library = parse_cql(cql)
        sql = translate_library_to_sql(library)
        sql_lower = sql.lower()

        assert "or false" not in sql_lower, f"Should not have 'OR FALSE' in SQL, got:\n{sql}"

    def test_nested_boolean_expressions(self):
        """Test that nested boolean expressions work correctly."""
        cql = """
        library TestLibrary version '1.0'
        using FHIR version '4.0.1'

        define HasA:
          exists [Condition: "A"]

        define HasB:
          exists [Condition: "B"]

        define HasC:
          exists [Condition: "C"]

        define ComplexLogic:
          (HasA and HasB) or HasC
        """

        library = parse_cql(cql)
        sql = translate_library_to_sql(library)
        sql_lower = sql.lower()

        # Should not have any FALSE patterns
        assert "and false" not in sql_lower, f"Should not have 'AND FALSE' in SQL, got:\n{sql}"
        assert "or false" not in sql_lower, f"Should not have 'OR FALSE' in SQL, got:\n{sql}"

    def test_not_exists_pattern(self):
        """Test that NOT EXISTS patterns are handled correctly."""
        cql = """
        library TestLibrary version '1.0'
        using FHIR version '4.0.1'

        define HasExclusion:
          exists [Condition: "Exclusion"]

        define InPopulation:
          not HasExclusion
        """

        library = parse_cql(cql)
        sql = translate_library_to_sql(library)
        sql_lower = sql.lower()

        # Should have some form of negation
        # Could be NOT, IS NULL, or similar
        has_negation = ("not " in sql_lower or "is null" in sql_lower)
        assert has_negation, f"Expected some negation pattern in SQL, got:\n{sql}"


class TestComplexJoinScenarios:
    """Tests for complex scenarios involving multiple JOINs."""

    def test_multiple_retrieves_in_exists_avoids_false(self):
        """Test multiple retrieve expressions with exists avoid FALSE literals."""
        cql = """
        library TestLibrary version '1.0'
        using FHIR version '4.0.1'

        define HasDiabetes:
          exists [Condition: "Diabetes"]

        define HasHypertension:
          exists [Condition: "Hypertension"]

        define HasBoth:
          HasDiabetes and HasHypertension
        """

        library = parse_cql(cql)
        sql = translate_library_to_sql(library)
        sql_lower = sql.lower()

        # Should not have FALSE patterns
        assert "and false" not in sql_lower, f"Should not have 'AND FALSE' in SQL, got:\n{sql}"
        assert "or false" not in sql_lower, f"Should not have 'OR FALSE' in SQL, got:\n{sql}"

    def test_chained_boolean_references(self):
        """Test chained references through multiple boolean definitions."""
        cql = """
        library TestLibrary version '1.0'
        using FHIR version '4.0.1'

        define IP:
          exists [Condition: "Diabetes"]

        define Denom:
          IP

        define Numer:
          Denom and exists [Observation: "HbA1c"]
        """

        library = parse_cql(cql)
        sql = translate_library_to_sql(library)
        sql_lower = sql.lower()

        # Should not have subquery patterns
        assert "select resource from" not in sql_lower, f"Should not have subquery pattern, got:\n{sql}"

        # Should not have FALSE patterns
        assert "and false" not in sql_lower and "or false" not in sql_lower, \
            f"Should not have FALSE patterns, got:\n{sql}"
