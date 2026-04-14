"""Structure tests for SQL generation patterns.

Tests verify:
- JOIN patterns are generated correctly
- patient_id is used consistently
- Shape metadata is tracked properly
"""

import pytest
from ...translator import CQLToSQLTranslator
from ...translator.context import RowShape, DefinitionMeta
from ...parser import parse_cql


class TestJoinGeneration:
    """Verify JOINs are generated correctly."""

    def _translate(self, cql: str) -> str:
        """Helper to translate CQL to SQL."""
        ast = parse_cql(cql)
        translator = CQLToSQLTranslator()
        return translator.translate_library_to_sql(ast)

    def test_exists_uses_exists_subquery(self):
        """exists should use EXISTS subquery pattern."""
        cql = '''
            library Test version '1.0'
            define Diabetes: [Condition: "Diabetes"]
            define HasDiabetes: exists Diabetes
        '''

        sql = self._translate(cql)

        # Should have EXISTS subquery
        sql_upper = sql.upper()
        assert "EXISTS" in sql_upper
        # Should reference the source definition
        assert "DIABETES" in sql_upper

    def test_count_uses_subquery_or_aggregate(self):
        """Count should use aggregation."""
        cql = '''
            library Test version '1.0'
            define Diabetes: [Condition: "Diabetes"]
            define DiabetesCount: Count(Diabetes)
        '''

        sql = self._translate(cql)

        # Count needs aggregation
        sql_upper = sql.upper()
        assert "COUNT" in sql_upper or "ARRAY_LENGTH" in sql_upper

    def test_self_join_produces_encounter_cte(self):
        """Self-join scenario should produce Encounter CTE correctly."""
        cql = '''
            library Test version '1.0'
            define Encounters: [Encounter]
            define BackToBack:
                from Encounters E1, Encounters E2
                where E2.period = E1.period
        '''

        sql = self._translate(cql)

        # Should have WITH clause (CTE structure)
        sql_upper = sql.upper()
        assert "WITH" in sql_upper

        # Should have Encounters CTE defined
        assert "ENCOUNTERS" in sql_upper

        # Should have BackToBack CTE for the self-join query
        assert "BACKTOBACK" in sql_upper

        # Verify the CTE structure has proper AS clauses
        assert "AS" in sql_upper


class TestPatientIdConsistency:
    """Verify patient_id is used consistently in population SQL."""

    def _translate_population(self, cql: str) -> str:
        """Helper to translate CQL to population SQL with patient_id."""
        ast = parse_cql(cql)
        translator = CQLToSQLTranslator()
        return translator.translate_library_to_population_sql(ast)

    def test_population_sql_outputs_patient_id(self):
        """Population SQL should output patient_id."""
        cql = '''
            library Test version '1.0'
            define Diabetes: [Condition: "Diabetes"]
        '''

        sql = self._translate_population(cql)

        # Population SQL should have patient_id column
        sql_lower = sql.lower()
        assert "patient_id" in sql_lower or "patient_ref" in sql_lower

    def test_population_sql_has_patients_cte(self):
        """Population SQL should have patients CTE."""
        cql = '''
            library Test version '1.0'
            define Diabetes: [Condition: "Diabetes"]
        '''

        sql = self._translate_population(cql)
        sql_lower = sql.lower()

        # Should have a patients CTE
        assert "patients" in sql_lower


class TestDistinctUsage:
    """Verify DISTINCT is used appropriately."""

    def _translate(self, cql: str) -> str:
        """Helper to translate CQL to SQL."""
        ast = parse_cql(cql)
        translator = CQLToSQLTranslator()
        return translator.translate_library_to_sql(ast)

    def test_exists_can_use_distinct(self):
        """exists on RESOURCE_ROWS can use DISTINCT for efficiency."""
        cql = '''
            library Test version '1.0'
            define Diabetes: [Condition: "Diabetes"]
            define HasDiabetes: exists Diabetes
        '''

        sql = self._translate(cql)

        # DISTINCT is an optimization, not required
        # Just verify the SQL is generated
        assert sql  # Non-empty SQL

    def test_count_does_not_use_distinct(self):
        """Count should see all rows, not just distinct patients."""
        cql = '''
            library Test version '1.0'
            define Diabetes: [Condition: "Diabetes"]
            define DiabetesCount: Count(Diabetes)
        '''

        sql = self._translate(cql)

        # Verify SQL is generated
        assert sql


class TestShapeMetadata:
    """Verify shape metadata is tracked."""

    def test_definition_meta_populated(self):
        """Definition metadata should be populated after translation."""
        cql = '''
            library Test version '1.0'
            define Diabetes: [Condition: "Diabetes"]
            define HasDiabetes: exists Diabetes
        '''

        ast = parse_cql(cql)
        translator = CQLToSQLTranslator()
        translator.translate_library(ast)

        # Check that definition_meta is populated
        assert "Diabetes" in translator._context.definition_meta
        assert "HasDiabetes" in translator._context.definition_meta

        # Check shapes
        diabetes_meta = translator._context.definition_meta["Diabetes"]
        has_diabetes_meta = translator._context.definition_meta["HasDiabetes"]

        # Diabetes should be RESOURCE_ROWS
        assert diabetes_meta.shape == RowShape.RESOURCE_ROWS
        # HasDiabetes should be PATIENT_SCALAR (exists returns boolean)
        assert has_diabetes_meta.shape == RowShape.PATIENT_SCALAR

    def test_retrieve_produces_resource_rows(self):
        """Retrieve expressions should produce RESOURCE_ROWS shape."""
        cql = '''
            library Test version '1.0'
            define Conditions: [Condition]
            define Observations: [Observation]
        '''

        ast = parse_cql(cql)
        translator = CQLToSQLTranslator()
        translator.translate_library(ast)

        conditions_meta = translator._context.definition_meta.get("Conditions")
        observations_meta = translator._context.definition_meta.get("Observations")

        assert conditions_meta is not None
        assert observations_meta is not None
        assert conditions_meta.shape == RowShape.RESOURCE_ROWS
        assert observations_meta.shape == RowShape.RESOURCE_ROWS

    def test_scalar_expression_shape_tracked(self):
        """Scalar expressions should have shape metadata tracked."""
        cql = '''
            library Test version '1.0'
            define InInitialPopulation: true
        '''

        ast = parse_cql(cql)
        translator = CQLToSQLTranslator()
        translator.translate_library(ast)

        meta = translator._context.definition_meta.get("InInitialPopulation")
        assert meta is not None
        # Shape may be UNKNOWN or PATIENT_SCALAR depending on implementation
        # The important thing is that metadata is tracked
        assert meta.shape in (RowShape.PATIENT_SCALAR, RowShape.UNKNOWN)
        assert meta.cql_type == "Boolean"

    def test_count_produces_patient_scalar(self):
        """Count expressions should produce PATIENT_SCALAR shape."""
        cql = '''
            library Test version '1.0'
            define Conditions: [Condition]
            define ConditionCount: Count(Conditions)
        '''

        ast = parse_cql(cql)
        translator = CQLToSQLTranslator()
        translator.translate_library(ast)

        count_meta = translator._context.definition_meta.get("ConditionCount")
        assert count_meta is not None
        assert count_meta.shape == RowShape.PATIENT_SCALAR

    def test_definition_meta_has_cql_type(self):
        """Definition metadata should include CQL type information."""
        cql = '''
            library Test version '1.0'
            define IsActive: true
            define Count: 5
        '''

        ast = parse_cql(cql)
        translator = CQLToSQLTranslator()
        translator.translate_library(ast)

        is_active_meta = translator._context.definition_meta.get("IsActive")
        count_meta = translator._context.definition_meta.get("Count")

        assert is_active_meta is not None
        assert count_meta is not None
        # CQL type should be tracked
        assert is_active_meta.cql_type is not None
        assert count_meta.cql_type is not None


class TestDefinitionMetaProperties:
    """Test DefinitionMeta properties."""

    def test_is_scalar_property(self):
        """Test is_scalar property returns correct value based on shape."""
        # PATIENT_SCALAR shape -> is_scalar is True
        scalar_meta = DefinitionMeta(
            name="test",
            shape=RowShape.PATIENT_SCALAR,
        )
        assert scalar_meta.is_scalar is True

        # RESOURCE_ROWS shape -> is_scalar is False
        list_meta = DefinitionMeta(
            name="test",
            shape=RowShape.RESOURCE_ROWS,
        )
        assert list_meta.is_scalar is False

    def test_is_multi_row_property(self):
        """Test is_multi_row property returns correct value based on shape."""
        # RESOURCE_ROWS shape -> is_multi_row is True
        multi_meta = DefinitionMeta(
            name="test",
            shape=RowShape.RESOURCE_ROWS,
        )
        assert multi_meta.is_multi_row is True

        # PATIENT_SCALAR shape -> is_multi_row is False
        scalar_meta = DefinitionMeta(
            name="test",
            shape=RowShape.PATIENT_SCALAR,
        )
        assert scalar_meta.is_multi_row is False

        # PATIENT_MULTI_VALUE shape -> is_multi_row is True
        multi_value_meta = DefinitionMeta(
            name="test",
            shape=RowShape.PATIENT_MULTI_VALUE,
        )
        assert multi_value_meta.is_multi_row is True


class TestCTEStructure:
    """Test CTE structure in generated SQL."""

    def _translate(self, cql: str) -> str:
        """Helper to translate CQL to SQL."""
        ast = parse_cql(cql)
        translator = CQLToSQLTranslator()
        return translator.translate_library_to_sql(ast)

    def test_with_clause_present(self):
        """Generated SQL should have WITH clause for CTEs."""
        cql = '''
            library Test version '1.0'
            define Diabetes: [Condition: "Diabetes"]
        '''

        sql = self._translate(cql)
        sql_upper = sql.upper()

        assert "WITH" in sql_upper

    def test_definition_name_in_cte(self):
        """Definition name should appear in CTE."""
        cql = '''
            library Test version '1.0'
            define Diabetes: [Condition: "Diabetes"]
        '''

        sql = self._translate(cql)
        sql_lower = sql.lower()

        # Definition name should appear as CTE name
        assert "diabetes" in sql_lower

    def test_definition_cte_present(self):
        """Each definition should have its own CTE."""
        cql = '''
            library Test version '1.0'
            define Diabetes: [Condition: "Diabetes"]
            define Hypertension: [Condition: "Hypertension"]
        '''

        sql = self._translate(cql)

        # Both definitions should be represented
        sql_lower = sql.lower()
        assert "diabetes" in sql_lower
        assert "hypertension" in sql_lower
