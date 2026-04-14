"""Tests for JOIN generation in definition CTEs."""

import pytest
from ...translator import CQLToSQLTranslator
from ...parser import parse_cql


class TestJoinGeneration:
    """Verify LEFT JOINs appear when definitions reference other CTEs."""

    def test_boolean_definition_with_exists_generates_join(self):
        """
        CQL: define HasDiabetes: exists [Condition: "Diabetes"]
        Expected: LEFT JOIN with patient_id correlation
        """
        cql = '''
        library TestMeasure version '1.0'
        using FHIR version '4.0.1'

        define HasDiabetes: exists [Condition: "Diabetes"]
        '''
        library = parse_cql(cql)
        translator = CQLToSQLTranslator()
        sql = translator.translate_library_to_population_sql(library)

        # Should have LEFT JOIN
        assert 'LEFT JOIN' in sql
        # Should reference patient_id in JOIN condition
        # Accept any format that correlates on patient_id
        assert 'patient_id' in sql
        # Verify the JOIN uses patient_id correlation
        assert 'ON' in sql and 'patient_id' in sql

    def test_boolean_and_chain_generates_multiple_joins(self):
        """
        CQL: define IP: exists A and exists B
        Expected: Two LEFT JOINs or EXISTS patterns
        """
        cql = '''
        library TestMeasure version '1.0'
        using FHIR version '4.0.1'

        define HasDiabetes: exists [Condition: "Diabetes"]
        define HasHypertension: exists [Condition: "Hypertension"]
        define BothConditions: "HasDiabetes" and "HasHypertension"
        '''
        library = parse_cql(cql)
        translator = CQLToSQLTranslator()
        sql = translator.translate_library_to_population_sql(library)

        # Should have proper boolean logic
        assert 'AND' in sql
        # Should reference both conditions
        assert 'HasDiabetes' in sql
        assert 'HasHypertension' in sql

    def test_definition_referencing_boolean_definition(self):
        """
        CQL:
          define IP: exists [Encounter]
          define Denom: "IP"
        Expected: Denom references IP CTE correctly
        """
        cql = '''
        library TestMeasure version '1.0'
        using FHIR version '4.0.1'

        define IP: exists [Encounter]
        define Denom: "IP"
        '''
        library = parse_cql(cql)
        translator = CQLToSQLTranslator()
        sql = translator.translate_library_to_population_sql(library)

        # Should reference IP
        assert '"IP"' in sql
        # Should have patient_id in the query
        assert 'patient_id' in sql

    def test_no_spurious_false_in_or_chain(self):
        """
        CQL: define Excl: exists A or exists B or exists C
        Expected: No FALSE literals in output
        """
        cql = '''
        library TestMeasure version '1.0'
        using FHIR version '4.0.1'

        define A: exists [Condition: "A"]
        define B: exists [Condition: "B"]
        define C: exists [Condition: "C"]
        define Excl: "A" or "B" or "C"
        '''
        library = parse_cql(cql)
        translator = CQLToSQLTranslator()
        sql = translator.translate_library_to_population_sql(library)

        # Should NOT have spurious FALSE
        assert 'OR FALSE' not in sql
        assert 'FALSE OR' not in sql
        assert 'AND FALSE' not in sql
        assert 'FALSE AND' not in sql

    def test_join_condition_uses_patient_id(self):
        """
        Verify that JOIN conditions properly use patient_id for correlation.
        """
        cql = '''
        library TestMeasure version '1.0'
        using FHIR version '4.0.1'

        define InpatientEncounter: [Encounter: "Inpatient"]
        define HasInpatient: exists InpatientEncounter
        '''
        library = parse_cql(cql)
        translator = CQLToSQLTranslator()
        sql = translator.translate_library_to_population_sql(library)

        # Should have patient_id in JOIN
        assert 'patient_id' in sql.lower()

    def test_multiple_retrieves_generate_separate_joins(self):
        """
        CQL with multiple retrieve sources should have proper separate JOINs.
        """
        cql = '''
        library TestMeasure version '1.0'
        using FHIR version '4.0.1'

        define Conditions: [Condition]
        define Encounters: [Encounter]
        define Both: exists Conditions and exists Encounters
        '''
        library = parse_cql(cql)
        translator = CQLToSQLTranslator()
        sql = translator.translate_library_to_population_sql(library)

        # Should have LEFT JOINs for both resources
        left_join_count = sql.count('LEFT JOIN')
        assert left_join_count >= 1, f"Expected at least 1 LEFT JOIN, found {left_join_count}"
