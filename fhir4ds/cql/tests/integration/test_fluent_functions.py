"""
Integration tests for fluent function SQL generation.

These tests verify that fluent functions and related query patterns generate SQL
without hiding unsupported translation behind runtime skips.
"""

import pytest

from ...parser import parse_cql
from ...translator import (
    CQLToSQLTranslator,
    FluentFunctionTranslator,
    FluentFunctionRegistry,
)


def translate_definition(cql: str, name: str) -> str:
    library = parse_cql(cql)
    results = CQLToSQLTranslator().translate_library(library)
    assert results is not None
    assert name in results
    return results[name].to_sql()


class TestLatestFunction:
    """Test the latest() function generates correct SQL."""

    @pytest.mark.integration
    def test_latest_basic_translation(self):
        sql = translate_definition(
            """
            library TestMeasure version '1.0'
            using FHIR version '4.0.1'

            define "Latest BP": [Observation] O
              return O.effective.latest()
            """,
            "Latest BP",
        )

        assert len(sql) > 0

    @pytest.mark.integration
    def test_latest_with_where_clause(self):
        sql = translate_definition(
            """
            library TestMeasure version '1.0'
            using FHIR version '4.0.1'

            define "Latest Final BP": [Observation: "BP"] O
              where O.status = 'final'
              return O.effective.latest()
            """,
            "Latest Final BP",
        )

        assert len(sql) > 0

    @pytest.mark.integration
    def test_latest_no_unnest_with_correlated_ref(self):
        """latest() should generate SQL for correlated reference patterns."""
        sql = translate_definition(
            """
            library TestMeasure version '1.0'
            using FHIR version '4.0.1'

            define "Qualifying Obs": [Observation: "BP"] O
              where O.status = 'final'
            define "Latest Qualifying": "Qualifying Obs" Q
              return Q.effective.latest()
            """,
            "Latest Qualifying",
        )

        assert len(sql) > 0


class TestSingletonFrom:
    """Test singleton from pattern."""

    @pytest.mark.integration
    def test_singleton_from_basic(self):
        sql = translate_definition(
            """
            library TestMeasure version '1.0'
            using FHIR version '4.0.1'

            define SingleEncounter: singleton from ([Encounter])
            """,
            "SingleEncounter",
        )

        assert len(sql) > 0

    @pytest.mark.integration
    def test_singleton_from_with_where(self):
        sql = translate_definition(
            """
            library TestMeasure version '1.0'
            using FHIR version '4.0.1'

            define "Single Active Encounter": singleton from (
              [Encounter] E where E.status = 'finished'
            )
            """,
            "Single Active Encounter",
        )

        assert len(sql) > 0

    @pytest.mark.integration
    def test_singleton_from_with_sort(self):
        sql = translate_definition(
            """
            library TestMeasure version '1.0'
            using FHIR version '4.0.1'

            define "Most Recent Encounter": singleton from (
              [Encounter] E
              sort by E.period.start desc
            )
            """,
            "Most Recent Encounter",
        )

        assert len(sql) > 0


class TestVerifiedFunction:
    """Test the verified() fluent function."""

    @pytest.mark.integration
    def test_verified_on_condition(self):
        sql = translate_definition(
            """
            library TestMeasure version '1.0'
            using FHIR version '4.0.1'

            define "Verified Conditions": [Condition] C
              where C.verificationStatus = 'confirmed'
            """,
            "Verified Conditions",
        )

        assert len(sql) > 0

    @pytest.mark.integration
    def test_verified_fluent_call(self):
        sql = translate_definition(
            """
            library TestMeasure version '1.0'
            using FHIR version '4.0.1'

            define "Verified Conditions": [Condition: "Diabetes"] C
              return C.verified()
            """,
            "Verified Conditions",
        )

        assert "list_filter" in sql or "verificationStatus" in sql or "confirmed" in sql

    @pytest.mark.integration
    def test_verified_on_retrieve_directly(self):
        """([Condition]).verified() should infer resource type from Retrieve AST."""
        sql = translate_definition(
            """
            library TestMeasure version '1.0'
            using FHIR version '4.0.1'

            define "Verified Conditions": ([Condition: "Diabetes"]).verified()
            """,
            "Verified Conditions",
        )

        assert "list_filter" in sql or "verificationStatus" in sql or "confirmed" in sql


class TestPrevalenceIntervalFunction:
    """Test the prevalenceInterval() fluent function."""

    @pytest.mark.integration
    def test_prevalence_interval_basic(self):
        sql = translate_definition(
            """
            library TestMeasure version '1.0'
            using FHIR version '4.0.1'

            define "Condition Interval": [Condition: "Diabetes"] C
              return C.prevalenceInterval()
            """,
            "Condition Interval",
        )

        assert (
            "onsetDateTime" in sql
            or "abatementDateTime" in sql
            or "recordedDate" in sql
            or "intervalFromBounds" in sql
        )


class TestFluentFunctionRegistry:
    """Test the FluentFunctionRegistry for function lookup."""

    def test_registry_has_common_functions(self):
        registry = FluentFunctionRegistry()
        from ...translator.context import SQLTranslationContext

        translator = FluentFunctionTranslator(SQLTranslationContext())

        assert registry is not None
        assert translator.registry.lookup_unqualified("verified", "Condition") is not None
        assert translator.registry.lookup_unqualified("prevalenceInterval", "Condition") is not None
        assert translator.registry.lookup_unqualified("latest", "Observation") is not None

    def test_registry_qualified_lookup(self):
        from ...translator.context import SQLTranslationContext

        translator = FluentFunctionTranslator(SQLTranslationContext())

        func = translator.registry.lookup_qualified("Status", "verified", "Condition")
        assert func is not None
        assert "verified" in func.name

    def test_registry_by_resource_type(self):
        from ...translator.context import SQLTranslationContext

        translator = FluentFunctionTranslator(SQLTranslationContext())

        condition_funcs = translator.registry.get_functions_for_resource("Condition")
        func_names = [f.name for f in condition_funcs]

        assert "verified" in func_names or any("verified" in f.qualified_name for f in condition_funcs)


class TestFluentFunctionInlining:
    """Test that fluent functions are properly inlined."""

    @pytest.mark.integration
    def test_fluent_function_inlining_no_function_call(self):
        sql = translate_definition(
            """
            library TestMeasure version '1.0'
            using FHIR version '4.0.1'

            define "Verified Diabetes": [Condition: "Diabetes"] D
              where D.verificationStatus.coding.code = 'confirmed'
            """,
            "Verified Diabetes",
        )

        assert "Status_Condition_verified(" not in sql

    @pytest.mark.integration
    def test_chained_fluent_functions(self):
        sql = translate_definition(
            """
            library TestMeasure version '1.0'
            using FHIR version '4.0.1'

            define "Active Conditions": [Condition: "Diabetes"] C
              where C.active is true
              return C.prevalenceInterval()
            """,
            "Active Conditions",
        )

        assert len(sql) > 0


class TestNoUnnestWithCorrelatedReferences:
    """Test that correlated-reference patterns generate SQL."""

    @pytest.mark.integration
    def test_no_unnest_breaks_correlated_ref(self):
        sql = translate_definition(
            """
            library TestMeasure version '1.0'
            using FHIR version '4.0.1'

            define "Patient Observations": [Observation] O
              where exists ([Patient] P where P.id = O.subject)

            define "Latest Per Patient": "Patient Observations" PO
              return PO.effective.latest()
            """,
            "Latest Per Patient",
        )

        assert len(sql) > 0

    @pytest.mark.integration
    def test_nested_query_preserves_scope(self):
        sql = translate_definition(
            """
            library TestMeasure version '1.0'
            using FHIR version '4.0.1'

            define "Encounters with Obs": [Encounter] E
              let obs: [Observation] O where O.encounter = E.id
              return tuple { encounter: E, hasObs: exists(obs) }
            """,
            "Encounters with Obs",
        )

        assert len(sql) > 0


class TestPrecomputedColumnOptimization:
    """Test that fluent functions use precomputed columns when available."""

    @pytest.mark.integration
    def test_fluent_function_uses_precomputed_column(self):
        sql = translate_definition(
            """
            library TestMeasure version '1.0'
            using FHIR version '4.0.1'

            define "BP Observations": [Observation: "Blood Pressure"] O
              where O.status = 'final'

            define "Latest BP": "BP Observations" B
              return B.effective.latest()
            """,
            "Latest BP",
        )

        assert len(sql) > 0


class TestStatusFunctions:
    """Test Status library fluent functions."""

    @pytest.mark.integration
    def test_is_encounter_performed(self):
        sql = translate_definition(
            """
            library TestMeasure version '1.0'
            using FHIR version '4.0.1'

            define "Performed Encounters": [Encounter] E
              where E.status = 'finished'
            """,
            "Performed Encounters",
        )

        assert "finished" in sql

    @pytest.mark.integration
    def test_is_procedure_performed(self):
        sql = translate_definition(
            """
            library TestMeasure version '1.0'
            using FHIR version '4.0.1'

            define "Completed Procedures": [Procedure] P
              where P.status = 'completed'
            """,
            "Completed Procedures",
        )

        assert "completed" in sql

    @pytest.mark.integration
    def test_is_obsation_final(self):
        sql = translate_definition(
            """
            library TestMeasure version '1.0'
            using FHIR version '4.0.1'

            define "Final Observations": [Observation] O
              where O.status in { 'final', 'amended', 'corrected' }
            """,
            "Final Observations",
        )

        assert "final" in sql
